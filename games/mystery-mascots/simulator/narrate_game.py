#!/usr/bin/env python3
"""
Mystery Mascots — Narration Engine.

Plays a single game with full AI reasoning exposed,
producing a Markdown play-by-play.
"""

import argparse
import json
import os
import sys
from typing import List, Dict

from cards import FACTIONS, FACTION_NAMES, build_full_deck
from game_state import GameState, Player
from ai_player import HeuristicAI
from run_simulation import run_draft, execute_action, load_config


class NarratedGame:
    """Wrapper that plays a game and collects narrative."""

    def __init__(self, config: dict, num_players: int, seed: int,
                 player_configs: List[Dict] = None):
        self.config = config
        self.num_players = num_players
        self.seed = seed
        self.game = GameState(config, num_players, seed=seed)
        self.narrative: List[str] = []

        # Create AIs
        self.ais = []
        for i in range(num_players):
            pc = player_configs[i] if player_configs and i < len(player_configs) else {}
            self.ais.append(HeuristicAI(
                skill=pc.get("skill", 1.0),
                style=pc.get("style", "balanced"),
                aggression=pc.get("aggression", 0.5),
                rng_seed=seed + i * 10000,
            ))

    def play(self, max_turns: int = 200):
        """Play the full game with narration."""
        game = self.game
        ais = self.ais

        # Setup
        game.setup(draft_fn=lambda players, hands, g: run_draft(players, hands, ais, g))

        # Patch resolution for wilds
        original_resolve = game._resolve_room
        def resolve_with_wilds(room_idx, wild_fn=None):
            def ai_wild_fn(player, card, ri, g):
                return ais[player.pid].declare_wild(player, card, ri, g)
            return original_resolve(room_idx, wild_fn=ai_wild_fn)
        game._resolve_room = resolve_with_wilds

        self._narrate_setup()

        turn_count = 0
        consecutive_passes = 0

        while not game.game_over and turn_count < max_turns:
            player = game.get_current_player()
            ai = ais[player.pid]

            if not game.can_player_act(player):
                consecutive_passes += 1
                if consecutive_passes >= self.num_players:
                    game.game_over = True
                    self._add(f"\n**All players have passed. Game ends.**")
                    break
                game.advance_turn()
                turn_count += 1
                continue

            consecutive_passes = 0
            self._narrate_turn(player, ai, turn_count)

            action, reasoning = ai.choose_action_with_reasoning(player, game)
            self._add(f"\n> **Thinking:** {reasoning}")

            result = execute_action(game, player, action, ai)

            self._narrate_result(player, action, result)

            # Check for resolution
            if result.get("triggered_resolution"):
                self._narrate_resolution(result.get("resolution", {}))

            game.advance_turn()
            turn_count += 1

        self._narrate_final()

    def _add(self, text: str):
        self.narrative.append(text)

    def _narrate_setup(self):
        game = self.game
        self._add(f"# Mystery Mascots — Narrated Game")
        self._add(f"**Seed:** {self.seed} | **Players:** {self.num_players} | "
                  f"**Rooms:** {game.num_rooms}")
        self._add(f"\n---\n")
        self._add(f"## Setup")
        self._add(f"\n**Secret Allegiances:**")
        for p in game.players:
            style = self.ais[p.pid].style_name
            self._add(f"- P{p.pid}: {p.faction} ({FACTION_NAMES[p.faction]}) "
                      f"[AI style: {style}]")
        self._add(f"\n**Drafted Hands:**")
        for p in game.players:
            hand_str = ", ".join(str(c) for c in p.hand)
            self._add(f"- P{p.pid}: {hand_str}")
        self._add(f"\n---\n")
        self._add(f"## Game Play\n")

    def _narrate_turn(self, player: Player, ai: HeuristicAI, turn: int):
        status = "EXPOSED" if player.exposed else "Hidden"
        hand_str = ", ".join(str(c) for c in player.hand)
        power = "used" if player.power_used else "available"
        tokens = player.accusation_tokens

        self._add(f"\n### Turn {turn + 1} — P{player.pid} "
                  f"({player.faction[:3]}, {status})")
        self._add(f"Hand: [{hand_str}] | Power: {power} | "
                  f"Accusation tokens: {tokens}")

        # Room state
        room_lines = []
        for r in self.game.rooms:
            cards = ", ".join(
                f"{p.card if p.face_up else '???'}(P{p.player_id})"
                for p in r.placements
            )
            room_lines.append(f"Room {r.room_id}: [{cards}] ({r.size}/3)")
        self._add(f"Rooms: " + " | ".join(room_lines))

    def _narrate_result(self, player: Player, action: dict, result: dict):
        t = action.get("type", "pass")

        if t == "place":
            card = action["card"]
            room = action["room"]
            face = "face-up" if result.get("face_up") else "face-down"
            self._add(f"\n**Action:** Places **{card}** in Room {room} ({face})")

        elif t.startswith("power_"):
            power_name = t.replace("power_", "").upper()
            self._add(f"\n**Action:** Uses **{power_name}** faction power")
            if t == "power_red" and result.get("success"):
                self._add(f"  Reveals: {result.get('revealed')} in Room {action['room']}")
            elif t == "power_green" and result.get("success"):
                self._add(f"  Peeks at P{action['target']}'s allegiance: {result.get('your_peek')}")
            elif t == "power_blue" and result.get("success"):
                self._add(f"  Moves card from Room {action['from_room']} to Room {action['to_room']}")
            elif t == "power_purple" and result.get("success"):
                self._add(f"  Rewinds card from Room {action['from_room']} to Room {action['to_room']}")

        elif t == "accuse":
            correct = "CORRECT" if result.get("correct") else "WRONG"
            self._add(f"\n**Action:** Accuses P{action['target']} of being "
                      f"{action['faction']} — **{correct}**!")

        elif t == "pass":
            self._add(f"\n**Action:** Passes (no useful actions available)")

    def _narrate_resolution(self, res: dict):
        room = res.get("room", "?")
        self._add(f"\n---")
        self._add(f"#### Room {room} Resolves!")
        cards_str = ", ".join(
            f"{c}(P{pid}, eff:{eff})" for c, pid, eff in res.get("cards", [])
        )
        self._add(f"Cards: {cards_str}")

        if res.get("scored"):
            self._add(f"**Winner:** {res['winning_faction']} scores "
                      f"**{res['score']} points!**")
        else:
            self._add(f"**BUST!** Tied majority — no one scores.")

        self._add(f"Exposure: P{res.get('exposed_player', '?')} "
                  f"has the highest rank")
        self._add(f"---")

    def _narrate_final(self):
        game = self.game
        self._add(f"\n## Final Scores\n")
        self._add(f"**Faction Totals:**")
        for f in FACTIONS:
            if game.faction_scores[f] > 0:
                self._add(f"- {f} ({FACTION_NAMES[f]}): {game.faction_scores[f]} pts")

        scores = game.compute_final_scores()
        self._add(f"\n**Player Standings:**")
        self._add(f"| Rank | Player | Faction | Faction Pts | Acc Bonus | Total | Exposed |")
        self._add(f"|------|--------|---------|-------------|-----------|-------|---------|")
        for i, s in enumerate(scores):
            self._add(f"| {i + 1} | P{s['pid']} | {s['faction']} | "
                      f"{s['faction_points']} | {s['accusation_bonus']:+d} | "
                      f"**{s['total']}** | {'Yes' if s['exposed'] else 'No'} |")

        winner = scores[0]
        self._add(f"\n**Winner: P{winner['pid']} ({winner['faction']}) "
                  f"with {winner['total']} points!**")

    def to_markdown(self) -> str:
        return "\n".join(self.narrative)


# ── CLI ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Mystery Mascots Narrated Game")
    parser.add_argument("-s", "--seed", type=int, default=42)
    parser.add_argument("-p", "--players", type=int, default=4)
    parser.add_argument("-o", "--output", type=str, default=None)
    parser.add_argument("--config", type=str, default=None)
    parser.add_argument("--preset", type=str, default=None,
                        choices=["experts", "beginners", "mixed", "styles"])

    args = parser.parse_args()

    config = load_config(args.config)

    # Build player configs
    player_configs = None
    if args.preset == "styles":
        from ai_player import STYLE_PROFILES
        style_list = list(STYLE_PROFILES.keys())
        player_configs = [{"skill": 1.0, "style": style_list[i % len(style_list)]}
                          for i in range(args.players)]

    narrated = NarratedGame(config, args.players, args.seed, player_configs)
    narrated.play()

    md = narrated.to_markdown()

    if args.output:
        with open(args.output, 'w') as f:
            f.write(md)
        print(f"Narrated game saved to {args.output}")
    else:
        print(md)
