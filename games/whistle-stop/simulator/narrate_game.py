#!/usr/bin/env python3
"""Narrate a single Whistle Stop game with full AI reasoning.

Generates a Markdown play-by-play of one game session, showing what
each AI considered and why it made each decision.

Usage:
    python narrate_game.py
    python narrate_game.py --seed 42 -p 3 -o game_narration.md
"""

import argparse
import json
import os
import sys
from typing import List

from cards import build_deck
from game_state import GameState, Player
from ai_player import HeuristicAI, STYLE_PROFILES


def load_config(config_path: str = None) -> dict:
    if config_path:
        with open(config_path) as f:
            return json.load(f)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    for candidate in [os.path.join(script_dir, "config.json"),
                      os.path.join(script_dir, "..", "config.json")]:
        if os.path.exists(candidate):
            with open(candidate) as f:
                return json.load(f)
    raise FileNotFoundError("config.json not found")


class NarratedGame:
    """Play a single game with full narration."""

    def __init__(self, config: dict, num_players: int, seed: int,
                 player_configs: List[dict] = None):
        self.config = config
        self.num_players = num_players
        self.seed = seed

        factions = list(config["game_rules"]["factions"])
        rng = __import__("random").Random(seed)

        if player_configs:
            faction_assignments = [
                pc.get("faction", factions[i % len(factions)])
                for i, pc in enumerate(player_configs)
            ]
        else:
            rng.shuffle(factions)
            faction_assignments = factions[:num_players]

        self.game = GameState(config, num_players, seed=seed,
                              faction_assignments=faction_assignments)

        self.ais = []
        for i in range(num_players):
            pc = player_configs[i] if player_configs and i < len(player_configs) else {}
            ai = HeuristicAI(
                player_id=i,
                faction=self.game.players[i].faction,
                skill=pc.get("skill", 1.0),
                style=pc.get("style", "balanced"),
                aggression=pc.get("aggression", 0.5),
                rng_seed=seed + i * 1000,
            )
            self.ais.append(ai)

        self.narrative: List[str] = []

    def play(self, max_turns: int = 50):
        """Play the full game, collecting narrative."""
        self._narrate_setup()

        round_num = 0
        while not self.game.game_over and round_num < max_turns:
            round_num += 1
            self._narrate_round(round_num)

        self._narrate_finale()

    def _narrate_setup(self):
        self.narrative.append(f"# Whistle Stop — Narrated Game")
        self.narrative.append(f"**Seed:** {self.seed} | "
                              f"**Players:** {self.num_players}")
        self.narrative.append("")

        # Player introductions
        self.narrative.append("## Players\n")
        for i, p in enumerate(self.game.players):
            ai = self.ais[i]
            self.narrative.append(
                f"- **Player {p.id}** — {p.faction} "
                f"({self.config['game_rules']['faction_colors'].get(p.faction, '')}) "
                f"| Style: {ai.style_name} | Skill: {ai.skill:.1f}"
            )

        # Depot
        depot = self.game.route[0].card
        self.narrative.append(f"\n## Setup\n")
        self.narrative.append(f"Depot card: **{depot.id}** (rank {depot.rank})")
        self.narrative.append(f"Each player starts with 5 cards.\n")

        for p in self.game.players:
            hand_str = ", ".join(c.id for c in p.hand)
            self.narrative.append(f"- P{p.id} hand: [{hand_str}]")

        self.narrative.append("\n---\n")

    def _narrate_round(self, round_num: int):
        game = self.game

        self.narrative.append(f"## Round {round_num}\n")
        self.narrative.append(
            f"Route length: {game.get_route_length()} | "
            + " | ".join(f"P{p.id}: {p.vp} VP" for p in game.players)
        )
        self.narrative.append("")

        # Each AI decides card + placement (movement decided after placement)
        decisions = []
        for i, player in enumerate(game.players):
            ai = self.ais[i]
            card, placement, _, reasoning = ai.choose_all_with_reasoning(
                player, game)
            decisions.append((i, card, placement, reasoning))

        # Show AI thinking (card/placement decisions)
        for i, card, placement, reasoning in decisions:
            player = game.players[i]
            self.narrative.append(f"### Player {i} ({player.faction})\n")
            self.narrative.append(
                f"Hand: [{', '.join(c.id for c in player.hand)}] | "
                f"Position: {player.position}"
            )
            self.narrative.append("")
            for line in reasoning:
                self.narrative.append(f"> {line}")
            self.narrative.append("")

        # Execute the round
        card_choices = [(i, card) for i, card, _, _ in decisions if card]
        placement_choices = [p for _, _, p, _ in decisions]

        if not card_choices:
            self.narrative.append("*No cards to play — round skipped.*\n")
            return

        # Movement callback: AI decides AFTER card placement
        ais_ref = self.ais
        def movement_fn(player, card, game_state):
            return ais_ref[player.id].choose_movement(card, player, game_state)

        results = game.play_round(card_choices, placement_choices,
                                  movement_fn=movement_fn)

        # Narrate results
        self.narrative.append("### Results\n")
        for r in results:
            pid = r["player_id"]
            card = r["card"]
            sr = r["score_result"]
            mr = r["move_result"]

            parts = [f"**P{pid}** plays **{card.id}**"]
            parts.append(f"at {r['placement']} of route")
            parts.append(f"→ moves {mr['steps_taken']} steps {mr['direction']}")
            if mr.get("orange_bonus"):
                parts.append("(+1 Orange bonus!)")
            parts.append(f"→ **{sr['total_vp']} VP**")
            if sr["ten_multiplier"]:
                parts.append("(×2 from 10!)")

            self.narrative.append("- " + " ".join(parts))

        # Route state
        route_str = " → ".join(
            f"[{s.card.id}]" for s in game.route
        )
        self.narrative.append(f"\nRoute: {route_str}")

        # Standings
        standings = game.get_standings()
        self.narrative.append(
            "Standings: " +
            " | ".join(f"P{pid}: {vp} VP" for pid, vp in standings)
        )

        if game.station_placed:
            self.narrative.append(
                f"\n**Station placed by P{game.station_placer_id}!** "
                f"+{game.config['game_rules']['station_placer_bonus']} bonus VP"
            )

        self.narrative.append("\n---\n")

    def _narrate_finale(self):
        game = self.game
        self.narrative.append("## Final Results\n")

        standings = game.get_standings()
        for rank, (pid, vp) in enumerate(standings):
            player = game.players[pid]
            medal = ["🥇", "🥈", "🥉", "4th"][rank] if rank < 4 else f"{rank+1}th"
            self.narrative.append(
                f"{medal} **Player {pid}** ({player.faction}) — **{vp} VP**"
            )

        self.narrative.append(f"\nGame ended after **{game.round_number} rounds**.")
        self.narrative.append(f"Route: {game.get_route_length()} cards.")
        if game.station_placed:
            self.narrative.append(f"Station placed by P{game.station_placer_id}.")
        else:
            self.narrative.append("Station was NOT placed (game timed out).")

    def to_markdown(self) -> str:
        return "\n".join(self.narrative)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Narrate a single Whistle Stop game")
    parser.add_argument("-p", "--players", type=int, default=4)
    parser.add_argument("-s", "--seed", type=int, default=42)
    parser.add_argument("--max-turns", type=int, default=50)
    parser.add_argument("-o", "--output", type=str, default=None,
                        help="Output markdown file (default: stdout)")
    parser.add_argument("--config", type=str, default=None)
    parser.add_argument("--preset", type=str, default="experts",
                        choices=["experts", "beginners", "mixed", "styles"])

    args = parser.parse_args()
    config = load_config(args.config)

    factions = config["game_rules"]["factions"]
    if args.preset == "styles":
        style_list = list(STYLE_PROFILES.keys())
        player_configs = [
            {"skill": 1.0, "style": style_list[i % len(style_list)],
             "faction": factions[i % len(factions)]}
            for i in range(args.players)
        ]
    elif args.preset == "mixed":
        player_configs = [
            {"skill": 1.0, "style": "balanced", "faction": factions[0]}
        ] + [
            {"skill": 0.3, "style": "balanced",
             "faction": factions[(i+1) % len(factions)]}
            for i in range(args.players - 1)
        ]
    else:
        player_configs = [
            {"skill": 1.0 if args.preset == "experts" else 0.3,
             "style": "balanced",
             "faction": factions[i % len(factions)]}
            for i in range(args.players)
        ]

    narration = NarratedGame(config, args.players, args.seed,
                              player_configs=player_configs)
    narration.play(max_turns=args.max_turns)
    md = narration.to_markdown()

    if args.output:
        with open(args.output, "w") as f:
            f.write(md)
        print(f"Narration written to {args.output}")
    else:
        print(md)
