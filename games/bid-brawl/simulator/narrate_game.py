#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

from ai_player import BidBrawlAI
from game_state import GameState

CONFIG = json.loads((Path(__file__).resolve().parent / "config.json").read_text())


def main(players: int = 4, seed: int = 42):
    game = GameState(CONFIG, players, seed=seed)
    profiles = [
        {"style": "shark", "skill": 0.92},
        {"style": "balanced", "skill": 0.76},
        {"style": "sandbagger", "skill": 0.58},
        {"style": "spoiler", "skill": 0.66},
    ][:players]
    game.assign_profiles(profiles)
    ais = [BidBrawlAI(skill=p["skill"], style=p["style"], rng_seed=seed * 17 + i) for i, p in enumerate(profiles)]
    round_no = 1
    while not game.game_over:
        record = game.play_round(ais)
        if not record["market"]:
            break
        print(f"\nRound {round_no}")
        print("Market:", " ".join(card.short() for card in record["market"]))
        for play in sorted(record["plays"], key=lambda p: (p.actual_position or 99, p.player_id)):
            result = f"P{play.player_id} bids {play.card.short()}"
            if play.rerolled:
                result += " -> REROLL"
            elif play.prize_taken:
                result += f" -> takes {play.prize_taken.short()}"
            if play.fed_to is not None and play.fed_to != play.player_id:
                result += f" / feeds P{play.fed_to}"
            print(result)
        print("Scores:", record["scores_after"])
        round_no += 1
    print("\nFinal:", game.final_scores())


if __name__ == "__main__":
    main()
