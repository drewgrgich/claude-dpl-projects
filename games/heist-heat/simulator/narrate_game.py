#!/usr/bin/env python3
"""
Heist Heat — Narration Engine

Plays a single game with full AI reasoning exposed, outputting
a detailed Markdown play-by-play.
"""

import argparse
import json
import os
import sys
from typing import List

from cards import Card, FACTION_EMOJI, FACTION_NAMES
from game_state import GameState
from ai_player import HeuristicAI


class NarratedGame:
    """Play one game with full narration."""

    def __init__(self, config: dict, num_players: int, seed: int,
                 player_configs: list = None):
        self.config = config
        self.game = GameState(config, num_players, seed=seed)
        self.num_players = num_players
        self.seed = seed
        self.narrative: List[str] = []

        # Create AIs
        self.ais = []
        styles = []
        for i in range(num_players):
            if player_configs and i < len(player_configs):
                pc = player_configs[i]
                ai = HeuristicAI(
                    skill=pc.get("skill", 1.0),
                    style=pc.get("style", "opportunistic"),
                    aggression=pc.get("aggression", 0.5),
                    rng_seed=seed + i * 10000,
                )
                styles.append(pc.get("style", "opportunistic"))
            else:
                ai = HeuristicAI(rng_seed=seed + i * 10000)
                styles.append("opportunistic")
            self.ais.append(ai)
        self.styles = styles

    def play(self):
        """Play the full game with narration."""
        self._header()

        total_rounds = self.config["game_rules"]["rounds_per_game"]
        for round_num in range(total_rounds):
            self.game.setup_round()
            self._narrate_round_start()
            turn = 0

            while not self.game.round_over and turn < 100:
                player = self.game.get_current_player()

                if not player.active:
                    self.game.advance_turn()
                    continue

                if not self.game.can_player_act(player):
                    self.narrative.append(
                        f"**P{player.id}** has no cards and can't getaway. Passes."
                    )
                    self.game.advance_turn()
                    turn += 1
                    continue

                ai = self.ais[player.id]
                action, reasoning = ai.choose_action_with_reasoning(player, self.game)

                self._narrate_turn(player, turn, reasoning)

                # Execute
                if action["type"] == "getaway":
                    result = self.game.action_getaway(player)
                    self._narrate_getaway(player, result)
                elif action["type"] == "crack":
                    result = self.game.action_crack(
                        player,
                        action["row"], action["col"],
                        action["hand_card_idx"],
                        action.get("use_faction_power", False),
                    )
                    # Handle peek powers
                    if result.get("action") == "green_peek":
                        follow_up = ai.choose_crack_after_green_peek(
                            player, self.game,
                            result["peek_results"],
                            result["played_card"],
                            result["hand_card_idx"],
                        )
                        if follow_up:
                            self.narrative.append(
                                f"  *Green peek reveals cards — "
                                f"redirecting to ({follow_up['row']},{follow_up['col']})*"
                            )
                            result = self.game.action_crack(
                                player, follow_up["row"], follow_up["col"],
                                result["hand_card_idx"], False,
                            )
                    elif result.get("action") == "orange_peek":
                        follow_up = ai.choose_crack_after_orange_peek(
                            player, self.game,
                            result["target_card"],
                            result["target_pos"],
                            result["played_card"],
                        )
                        if follow_up and follow_up.get("keep_target"):
                            r, c = result["target_pos"]
                            result = self.game.action_crack(
                                player, r, c,
                                result["hand_card_idx"], False,
                            )
                        elif follow_up:
                            self.narrative.append(
                                f"  *Orange peek — bad target! "
                                f"Switching to ({follow_up['new_row']},{follow_up['new_col']})*"
                            )
                            result = self.game.action_crack(
                                player, follow_up["new_row"], follow_up["new_col"],
                                result["hand_card_idx"], False,
                            )

                    self._narrate_crack(player, result)
                elif action["type"] == "pass":
                    self.narrative.append(f"  P{player.id} **passes**.")

                if self.game.round_over:
                    break

                self.game.advance_turn()
                turn += 1

            # End round
            round_result = self.game.end_round()
            self._narrate_round_end(round_result)

        self.game.finish_game()
        self._narrate_final()

    def _header(self):
        self.narrative.append(f"# Heist Heat — Narrated Game")
        self.narrative.append(f"**Seed:** {self.seed} · **Players:** {self.num_players}")
        style_str = ", ".join(
            f"P{i}: {s}" for i, s in enumerate(self.styles)
        )
        self.narrative.append(f"**Styles:** {style_str}")
        self.narrative.append("---")

    def _narrate_round_start(self):
        g = self.game
        self.narrative.append(f"\n## Round {g.current_round}")
        self.narrative.append(
            f"Vault: {g.vault.rows}x{g.vault.cols} grid "
            f"({g.vault.card_count} cards) · Heat: {g.heat}"
        )
        for p in g.players:
            hand_str = ", ".join(f"{c!r}" for c in sorted(p.hand))
            self.narrative.append(f"- **P{p.id}** hand ({len(p.hand)}): {hand_str}")
        self.narrative.append("")

    def _narrate_turn(self, player, turn: int, reasoning: str):
        g = self.game
        self.narrative.append(
            f"### Turn {turn + 1} — P{player.id} "
            f"(Score: {player.total_score} | Hand: {player.hand_size} | "
            f"Stash: {len(player.stash)} | Heat: {g.heat})"
        )
        # AI thinking in blockquote
        for line in reasoning.split("\n"):
            self.narrative.append(f"> {line}")
        self.narrative.append("")

    def _narrate_crack(self, player, result: dict):
        if not result.get("success"):
            self.narrative.append(f"  *(Action failed: {result.get('error')})*")
            return

        if result.get("action") == "blue_steal":
            if result.get("stolen"):
                self.narrative.append(
                    f"  🔵 **BLUE STEAL** — P{player.id} steals "
                    f"{result['stolen_card']!r} from P{result['target_player']}!"
                )
            else:
                self.narrative.append(
                    f"  🔵 **BLUE STEAL** — No valid targets!"
                )
            return

        if result.get("purple_rewind"):
            drew = result.get("purple_drew")
            drew_str = f" Drew {drew!r}!" if drew else ""
            self.narrative.append(
                f"  🟣 **FAIL + TIME REWIND** — {result['played_card']!r} "
                f"vs {result['vault_card']!r}. Card saved!{drew_str}"
            )
            return

        played = result.get("played_card")
        vault = result.get("vault_card")
        power = result.get("power_used")
        power_str = f" (🔴 Power Through!)" if power == "RED" else ""
        power_str = f" (🟡 Perfect Fit!)" if power == "YELLOW" else power_str

        if result.get("cracked"):
            chain = result.get("chain_length", 1)
            heat = result.get("heat_added", 0)
            claimed_str = ", ".join(f"{c!r}" for c in result.get("claimed", []))
            self.narrative.append(
                f"  ✅ **CRACK SUCCESS**{power_str} — {played!r} ≥ {vault!r}"
            )
            if chain > 1:
                self.narrative.append(f"  ⛓️ **CHAIN x{chain}!** Claimed: {claimed_str}")
            else:
                self.narrative.append(f"  Claimed: {claimed_str}")

            if result.get("alarm_hit"):
                self.narrative.append(f"  🚨 **ALARM TRIGGERED!**")

            self.narrative.append(
                f"  🌡️ Heat +{heat} → **{result['total_heat']}**"
            )
        else:
            self.narrative.append(
                f"  ❌ **CRACK FAIL** — {played!r} < {vault!r}"
            )
            if result.get("heat_added", 0) > 0:
                self.narrative.append(
                    f"  🌡️ High-card penalty: Heat +{result['heat_added']} → "
                    f"**{result['total_heat']}**"
                )

        if result.get("round_over"):
            self.narrative.append(f"  **🔥 HEAT MAXED — ROUND OVER!**")
        self.narrative.append("")

    def _narrate_getaway(self, player, result: dict):
        self.narrative.append(
            f"  🏃 **GETAWAY!** P{player.id} escapes with "
            f"{result['stash_size']} cards at Heat {result['heat']}!"
        )
        self.narrative.append("")

    def _narrate_round_end(self, result: dict):
        self.narrative.append(f"\n### Round {result['round']} Results")
        end_reason = "Vault Empty!" if result.get("vault_empty") else "Heat Maxed!"
        self.narrative.append(f"Final Heat: **{result['final_heat']}** — {end_reason}\n")
        for pr in result["player_results"]:
            if pr["status"] in ("safe", "safe_vault_empty"):
                tag = "getaway" if pr["status"] == "safe" else "vault empty"
                self.narrative.append(
                    f"- **P{pr['player']}** 🟢 SAFE ({tag}) — "
                    f"{pr['stash_size']} cards → **{pr['score']} points**"
                )
            else:
                self.narrative.append(
                    f"- **P{pr['player']}** 🔴 BUSTED — "
                    f"lost {pr['stash_size']} cards!"
                )
        self.narrative.append("")

    def _narrate_final(self):
        self.narrative.append("\n## Final Scores")
        self.narrative.append("")
        players = sorted(self.game.players, key=lambda p: p.total_score, reverse=True)
        for rank, p in enumerate(players):
            medal = ["🥇", "🥈", "🥉"][rank] if rank < 3 else "  "
            rounds_str = " + ".join(str(s) for s in p.round_scores)
            self.narrative.append(
                f"{medal} **P{p.id}**: {p.total_score} points ({rounds_str})"
            )

        winner_id, winner_score = self.game.get_winner()
        self.narrative.append(f"\n**Winner: Player {winner_id} with {winner_score} points!**")

    def to_markdown(self) -> str:
        return "\n".join(self.narrative)


# ── CLI ─────────────────────────────────────────────────────────────

def find_config():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    for path in [
        os.path.join(script_dir, "config.json"),
        os.path.join(script_dir, "..", "config.json"),
    ]:
        if os.path.exists(path):
            return path
    return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Heist Heat — Narrated Game"
    )
    parser.add_argument("-p", "--players", type=int, default=3)
    parser.add_argument("-s", "--seed", type=int, default=42)
    parser.add_argument("-o", "--output", type=str, default=None,
                        help="Output Markdown file")
    parser.add_argument("--config", type=str, default=None)
    parser.add_argument("--styles", type=str, default=None,
                        help="Comma-separated styles per player")

    args = parser.parse_args()

    config_path = args.config or find_config()
    if not config_path:
        print("ERROR: config.json not found", file=sys.stderr)
        sys.exit(1)

    with open(config_path) as f:
        config = json.load(f)

    player_configs = None
    if args.styles:
        styles = args.styles.split(",")
        player_configs = [{"skill": 1.0, "style": s.strip(), "aggression": 0.5}
                          for s in styles]

    narrated = NarratedGame(config, args.players, args.seed, player_configs)
    narrated.play()
    md = narrated.to_markdown()

    if args.output:
        with open(args.output, 'w') as f:
            f.write(md)
        print(f"Narration saved to {args.output}")
    else:
        print(md)
