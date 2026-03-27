#!/usr/bin/env python3
"""Quick validation of v0.1.4 (2nd-place VP) across 3P/4P/5P."""

import json
import os
import statistics
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from game_state_v4 import GameStateV4
from ai_player_v4 import AIPlayerV4, STYLE_PROFILES

N = 2000

config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config_v4.json")
with open(config_path) as f:
    config = json.load(f)

style_sets = {
    3: ["balanced", "aggressive", "sniper"],
    4: ["balanced", "aggressive", "sniper", "hoarder"],
    5: ["balanced", "aggressive", "sniper", "hoarder", "spread"],
}

print("=" * 65)
print("  v0.1.4 VALIDATION — 2nd-Place VP (1 VP)")
print(f"  {N} games per player count")
print("=" * 65)

for np in [3, 4, 5]:
    styles = style_sets[np]
    style_wins = defaultdict(float)
    style_scores = defaultdict(list)
    style_games = defaultdict(int)
    total_2nd = 0
    all_winner_scores = []
    all_spreads = []

    for i in range(N):
        seed = 1 + i
        game_styles = [styles[(i + j) % len(styles)] for j in range(np)]
        game = GameStateV4(np, seed=seed, config=config)
        ais = [AIPlayerV4(pid, skill=1.0, style=game_styles[pid],
                           rng_seed=seed * 100 + pid) for pid in range(np)]

        def dfn(p, gs, rn):
            return ais[p.id].choose_deployment(p, gs, rn)

        def pfn(p, gs, pc):
            return ais[p.id].choose_pass(p, gs, pc)

        result = game.play_game(dfn, pfn)
        winner = result["winner"]

        if isinstance(winner, list):
            for w in winner:
                style_wins[game_styles[w]] += 1.0 / len(winner)
        else:
            style_wins[game_styles[winner]] += 1

        scores = list(result["scores"].values())
        all_winner_scores.append(max(scores))
        all_spreads.append(max(scores) - min(scores))
        total_2nd += result.get("second_place_awards", 0)

        for pid, score in result["scores"].items():
            style_scores[game_styles[pid]].append(score)
            style_games[game_styles[pid]] += 1

    fair = 1.0 / np
    print(f"\n── {np}P ──")
    print(f"  {'Style':<12} {'Win%':>7} {'Δ':>7} {'Avg VP':>8}")

    for s in sorted(styles, key=lambda s: -style_wins.get(s, 0)):
        wr = style_wins[s] / style_games[s]
        delta = wr - fair
        vp = statistics.mean(style_scores[s])
        flag = " ⚠️" if abs(delta) > 0.08 else ""
        print(f"  {s:<12} {wr:6.1%} {delta:+6.1%} {vp:7.1f}{flag}")

    gap = max(style_wins[s] / style_games[s] for s in styles) - \
          min(style_wins[s] / style_games[s] for s in styles)
    print(f"\n  Style gap: {gap:.1%}  |  Avg winner: {statistics.mean(all_winner_scores):.1f}  |"
          f"  Spread: {statistics.mean(all_spreads):.1f}  |  2nd-place/game: {total_2nd/N:.1f}")

print(f"\n{'=' * 65}")
