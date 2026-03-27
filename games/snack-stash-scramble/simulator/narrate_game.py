#!/usr/bin/env python3
"""Narrated game replay for Snack Stash Scramble.

Plays a single game with full AI thinking exposed, producing a Markdown
file that reads like play-by-play commentary.
"""

import argparse
import json
import os
from typing import List, Dict, Optional

from cards import Card, build_deck
from game_state import GameState, Player
from ai_player import HeuristicAI, game_progress


FACTION_EMOJI = {
    "RED": "🔴", "ORANGE": "🟠", "YELLOW": "🟡",
    "GREEN": "🟢", "BLUE": "🔵", "PURPLE": "🟣",
}

FACTION_NAME = {
    "RED": "Super-Dupes", "ORANGE": "Finders-Keepers",
    "YELLOW": "Tinkerers", "GREEN": "Prognosticationers",
    "BLUE": "Magicians", "PURPLE": "Time Travelers",
}


class NarratedGame:
    """Play one game with full narration."""

    def __init__(self, config: dict, num_players: int, seed: int,
                 player_configs: List[dict] = None):
        self.game = GameState(config, num_players, seed=seed)
        self.game.setup()
        self.seed = seed

        self.ais = []
        for i in range(num_players):
            pc = player_configs[i] if player_configs and i < len(player_configs) else {}
            self.ais.append(HeuristicAI(
                skill=pc.get("skill", 1.0),
                style=pc.get("style", "balanced"),
                aggression=pc.get("aggression", 0.5),
                rng_seed=seed + i * 1000,
            ))

        self.narrative: List[str] = []
        self.turn_count = 0
        self.could_bank_last: Dict[int, bool] = {i: True for i in range(num_players)}

    def play(self):
        """Play the full game with narration."""
        self._narrate_setup()

        while not self.game.game_over and self.turn_count < 200:
            player = self.game.get_current_player()
            ai = self.ais[player.id]
            self._narrate_turn(player, ai)
            self.turn_count += 1

            if self.game.game_over:
                break

        self._narrate_endgame()

    def _narrate_setup(self):
        self.narrative.append(f"# 🐹 Snack Stash Scramble — Narrated Game")
        self.narrative.append(f"**Seed:** {self.seed} | "
                              f"**Players:** {self.game.num_players}")
        self.narrative.append("")

        for i, ai in enumerate(self.ais):
            self.narrative.append(f"- **P{i}**: skill={ai.skill}, "
                                  f"style={ai.style}, aggression={ai.aggression}")

        self.narrative.append("")
        self.narrative.append("---")
        self.narrative.append("")

        # Show starting hands
        for p in self.game.players:
            hand_str = ", ".join(str(c) for c in sorted(p.hand))
            self.narrative.append(f"**P{p.id} starting hand ({len(p.hand)}):** {hand_str}")
        self.narrative.append("")
        self.narrative.append(f"**Feeder:** {self.game.feeder.size} cards | "
                              f"**Litter Box top:** "
                              f"{self.game.litter_box[-1] if self.game.litter_box else 'empty'}")
        self.narrative.append("")

    def _narrate_turn(self, player: Player, ai: HeuristicAI):
        g = self.game
        progress = game_progress(g)

        # Scoreboard
        scores = " | ".join(f"P{p.id}: {p.banked_score}pts ({p.hand_size} cards)"
                            for p in g.players)

        self.narrative.append(f"## Turn {self.turn_count + 1} — Player {player.id}")
        self.narrative.append(f"*{scores} | Feeder: {g.feeder.size} | "
                              f"Progress: {progress:.0%}*")
        self.narrative.append("")

        hand_str = ", ".join(str(c) for c in sorted(player.hand))
        self.narrative.append(f"**Hand ({player.hand_size}):** {hand_str}")
        self.narrative.append("")

        # --- DRAW ---
        draw_choice = ai.choose_draw(player, g)
        self._narrate_ai_thinking(ai, "Draw")

        # Check scavenge eligibility (Desperate Sniffing)
        use_scavenge = (not self.could_bank_last.get(player.id, True)
                        and draw_choice == "draw_feeder")

        if draw_choice == "snack_floor":
            result = g.action_snack_floor(player)
            drawn = result.get("cards", [])
            self.narrative.append(f"📥 **Snack Floor!** Draws {len(drawn)} cards: "
                                  f"{', '.join(str(c) for c in drawn)}")
        elif draw_choice == "draw_litter_box":
            result = g.action_draw_litter_box(player)
            if result["success"]:
                restock = result.get("restock_card")
                msg = f"📥 Takes **{result['card']}** from Litter Box"
                if restock:
                    msg += f" (🔄 Pantry Restock: {restock} flipped to Litter Box)"
                self.narrative.append(msg)
            else:
                result = g.action_draw_feeder(player)
                self.narrative.append(f"📥 Litter box blocked — draws from Feeder: "
                                      f"{result.get('card', '?')}")
        else:
            result = g.action_draw_feeder(player, scavenge=use_scavenge)
            if result.get("action") == "scavenge":
                drawn = result.get("cards", [])
                self.narrative.append(f"📥 🐽 **Desperate Sniffing!** Couldn't bank last turn — "
                                      f"draws {len(drawn)} cards: "
                                      f"{', '.join(str(c) for c in drawn)}")
            else:
                self.narrative.append(f"📥 Draws from Feeder: {result.get('card', '?')}")

        self.narrative.append("")

        if g.game_over:
            return

        # --- BANK ---
        bank_actions = ai.choose_banks(player, g)
        self._narrate_ai_thinking(ai, "Bank")

        for ba in bank_actions:
            faction = ba.get("faction_trigger")
            target = None
            if faction == "BLUE":
                target = ai.choose_blue_swap(player, g)
            elif faction == "PURPLE":
                target = ai.choose_purple_tuck(g)

            result = g.action_bank_set(
                player, ba["cards"], ba["set_type"],
                faction_trigger=faction, trigger_target=target
            )

            if result["success"]:
                cards_str = ", ".join(str(c) for c in ba["cards"])
                self.narrative.append(
                    f"🏦 **Banks {ba['set_type']}:** {cards_str} "
                    f"(+{result['value']} points)")

                if faction:
                    emoji = FACTION_EMOJI.get(faction, "")
                    name = FACTION_NAME.get(faction, faction)
                    pr = result.get("power_result", {})
                    effect = pr.get("effect", "")

                    self.narrative.append(f"  {emoji} **{faction} ({name}):** {effect}")

                    if faction == "GREEN" and "peeked" in pr:
                        order = ai.choose_green_reorder(pr["peeked"], player, g)
                        reordered = [pr["peeked"][i] for i in order]
                        for _ in range(len(reordered)):
                            g.feeder.draw_one()
                        g.feeder.add_to_top(reordered)
                        self.narrative.append(
                            f"  Reordered top of feeder: "
                            f"{', '.join(str(c) for c in reordered)}")

                    if faction == "YELLOW":
                        yellow_action = ai.choose_yellow_extend(player, g)
                        if yellow_action:
                            ext_r = g.action_extend_set(
                                player, yellow_action["card"],
                                yellow_action["target_player_id"],
                                yellow_action["target_set_idx"]
                            )
                            if ext_r["success"]:
                                tp = yellow_action["target_player_id"]
                                c = yellow_action["card"]
                                if tp != player.id:
                                    self.narrative.append(
                                        f"  🥜 **POISONED PEANUT!** Attaches {c} "
                                        f"to P{tp}'s set!")
                                else:
                                    self.narrative.append(
                                        f"  Extends own set with {c}")

                self.narrative.append("")

            if g.game_over:
                return

        # Track whether player banked this turn (for Desperate Sniffing next turn)
        self.could_bank_last[player.id] = len(bank_actions) > 0

        # --- EXTENSIONS ---
        extensions = ai.choose_extensions(player, g)
        for ext in extensions:
            if not player.hand:
                break
            result = g.action_extend_set(
                player, ext["card"],
                ext["target_player_id"],
                ext["target_set_idx"]
            )
            if result["success"]:
                self.narrative.append(
                    f"➕ Extends set with {ext['card']}")

        if g.game_over:
            return

        # --- DISCARD ---
        if player.hand:
            discard = ai.choose_discard(player, g)
            if discard:
                g.action_discard(player, discard)
                self.narrative.append(f"🗑️ Discards **{discard}**")
        else:
            self.narrative.append(f"✨ Hand empty — no discard needed!")

        self.narrative.append("")
        g.advance_turn()

        # Halftime check
        if g.halftime_done and g.halftime_turn == g.turn_number - 1:
            self.narrative.append(f"---\n\n⏰ **HALFTIME SWEEP!** "
                                  f"Litter box reshuffled into feeder "
                                  f"({g.feeder.size} cards)\n\n---")
            self.narrative.append("")

    def _narrate_ai_thinking(self, ai: HeuristicAI, phase: str):
        if ai.reasoning:
            self.narrative.append(f"> **{phase} thinking:**")
            for line in ai.reasoning:
                self.narrative.append(f"> {line}")
            self.narrative.append("")
            ai._clear_reasoning()

    def _narrate_endgame(self):
        g = self.game
        self.narrative.append("---")
        self.narrative.append("")
        self.narrative.append("# 🏁 GAME OVER — The Greedy Cheeks Check!")
        self.narrative.append("")
        self.narrative.append(f"Game ended after **{self.turn_count} turns**.")
        if g.mid_bite_whistles:
            self.narrative.append("🚨 **Mid-Bite Whistle** was blown!")
        self.narrative.append("")

        scores = g.get_final_scores()
        scores.sort(key=lambda s: -s["final_score"])

        has_poison = any(s.get("poison_damage", 0) > 0 for s in scores)

        if has_poison:
            self.narrative.append("| Player | Banked | Poison Dmg | Hand Penalty | Wilds in Hand | Final Score |")
            self.narrative.append("|--------|--------|-----------|-------------|---------------|-------------|")
            for s in scores:
                pd = s.get("poison_damage", 0)
                self.narrative.append(
                    f"| P{s['player_id']} | {s['banked_score']} | "
                    f"-{pd} | -{s['hand_penalty']} | {s['wilds_in_hand']} | "
                    f"**{s['final_score']:+d}** |")
        else:
            self.narrative.append("| Player | Banked | Hand Penalty | Wilds in Hand | Final Score |")
            self.narrative.append("|--------|--------|-------------|---------------|-------------|")
            for s in scores:
                self.narrative.append(
                    f"| P{s['player_id']} | {s['banked_score']} | "
                    f"-{s['hand_penalty']} | {s['wilds_in_hand']} | "
                    f"**{s['final_score']:+d}** |")

        self.narrative.append("")
        winner = g.get_winner()
        self.narrative.append(f"## 🏆 Player {winner} wins!")
        self.narrative.append("")

        # Show what each player banked
        for p in g.players:
            self.narrative.append(f"### P{p.id}'s Stash:")
            for bset in p.banked_sets:
                prot = " 🛡️" if bset.protected else ""
                poison = ""
                if hasattr(bset, 'poisoned_cards') and bset.poisoned_cards:
                    poison_str = ", ".join(str(c) for c in bset.poisoned_cards)
                    poison = f" 🥜 Poisoned: [{poison_str}] = -{bset.poison_penalty}pts"
                self.narrative.append(f"- {bset}{prot}{poison}")
            remaining = ", ".join(str(c) for c in p.hand) if p.hand else "(empty)"
            self.narrative.append(f"- *Remaining hand:* {remaining}")
            self.narrative.append("")

    def to_markdown(self) -> str:
        return "\n".join(self.narrative)


def load_config(path: str = None) -> dict:
    if path:
        with open(path) as f:
            return json.load(f)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    for c in [os.path.join(script_dir, "config.json"),
              os.path.join(script_dir, "..", "config.json")]:
        if os.path.exists(c):
            with open(c) as f:
                return json.load(f)
    raise FileNotFoundError("Could not find config.json")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Play a narrated game of Snack Stash Scramble")
    parser.add_argument("-s", "--seed", type=int, default=42,
                        help="Random seed for the game")
    parser.add_argument("-p", "--players", type=int, default=3,
                        help="Number of players (2-4)")
    parser.add_argument("-o", "--output", type=str, default=None,
                        help="Output Markdown file path")
    parser.add_argument("--config", type=str, default=None)
    parser.add_argument("--preset", type=str, default=None,
                        choices=["experts", "beginners", "mixed", "styles"])

    args = parser.parse_args()
    config = load_config(args.config)

    # Build player configs from preset
    num_p = args.players
    if args.preset == "styles":
        styles = ["rush", "balanced", "hoarder", "aggressive"]
        pconfigs = [{"skill": 1.0, "style": styles[i % len(styles)]}
                    for i in range(num_p)]
    elif args.preset == "mixed":
        pconfigs = [{"skill": 1.0, "style": "balanced"}]
        pconfigs += [{"skill": 0.3, "style": "balanced"} for _ in range(num_p - 1)]
    else:
        pconfigs = [{"skill": 1.0, "style": "balanced"} for _ in range(num_p)]

    narrated = NarratedGame(config, num_p, seed=args.seed, player_configs=pconfigs)
    narrated.play()
    md = narrated.to_markdown()

    if args.output:
        with open(args.output, 'w') as f:
            f.write(md)
        print(f"Narrated game saved to {args.output}")
    else:
        print(md)
