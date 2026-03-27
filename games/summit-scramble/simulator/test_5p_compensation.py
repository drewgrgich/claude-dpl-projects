#!/usr/bin/env python3
"""
Test late-seat compensation variants for 5-player Summit Scramble.

Baseline: all players get 11 cards.
Results from V2 rules: P0=24.3%, P1=20.2%, P2=19.3%, P3=19.1%, P4=17.1%
"""

import json
import os
import sys
from collections import defaultdict

from run_simulation import run_single_round

# Load config
script_dir = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(script_dir, "config.json")) as f:
    config = json.load(f)

NUM_GAMES = 1000
NUM_PLAYERS = 5
BASE_HAND = 11  # standard 5-player hand

VARIANTS = {
    "baseline": {
        "desc": "All players: 11 cards (no compensation)",
        "overrides": {},
    },
    "p4_minus_1": {
        "desc": "P4 gets 10 cards (-1)",
        "overrides": {4: 10},
    },
    "p3p4_minus_1": {
        "desc": "P3 gets 10, P4 gets 10 (-1 each)",
        "overrides": {3: 10, 4: 10},
    },
    "gradient": {
        "desc": "P0:12, P1:11, P2:11, P3:10, P4:10 (gradient)",
        "overrides": {0: 12, 3: 10, 4: 10},
    },
    "steep_gradient": {
        "desc": "P0:12, P1:12, P2:11, P3:10, P4:10 (steep)",
        "overrides": {0: 12, 1: 12, 3: 10, 4: 10},
    },
    "p4_minus_2": {
        "desc": "P4 gets 9 cards (-2)",
        "overrides": {4: 9},
    },
}

player_configs = [{"skill": 1.0, "style": "balanced", "aggression": 0.5}
                  for _ in range(NUM_PLAYERS)]

results = {}

for name, variant in VARIANTS.items():
    print(f"\n{'='*60}")
    print(f"  VARIANT: {name}")
    print(f"  {variant['desc']}")
    print(f"  Running {NUM_GAMES} games...")
    print(f"{'='*60}")

    overrides = variant["overrides"]
    win_counts = defaultdict(int)
    finish_positions = defaultdict(list)
    all_turns = []

    for i in range(NUM_GAMES):
        seed = 1 + i
        stats = run_single_round(
            config, NUM_PLAYERS, seed,
            player_configs=player_configs,
            hand_size_overrides=overrides,
        )
        if stats["finish_order"]:
            win_counts[stats["finish_order"][0]] += 1
        for pos_idx, pid in enumerate(stats["finish_order"]):
            finish_positions[pid].append(pos_idx + 1)
        all_turns.append(stats["turns"])

    # Report
    print(f"\n  Win Rates:")
    hand_sizes = [overrides.get(i, BASE_HAND) for i in range(NUM_PLAYERS)]
    win_rates = {}
    for pid in range(NUM_PLAYERS):
        rate = win_counts[pid] / NUM_GAMES
        win_rates[pid] = rate
        avg_pos = sum(finish_positions[pid]) / len(finish_positions[pid]) if finish_positions[pid] else 0
        bar = "█" * int(rate * 50)
        print(f"    P{pid} ({hand_sizes[pid]} cards): {rate:.1%}  avg_pos={avg_pos:.2f}  {bar}")

    rates = list(win_rates.values())
    spread = max(rates) - min(rates)
    avg_turns = sum(all_turns) / len(all_turns)
    print(f"\n  Spread: {spread:.1%}  |  Avg turns: {avg_turns:.1f}")

    # Check balance quality
    expected = 1.0 / NUM_PLAYERS  # 20%
    total_deviation = sum(abs(r - expected) for r in rates)
    print(f"  Total deviation from 20%: {total_deviation:.3f}")

    results[name] = {
        "win_rates": win_rates,
        "spread": spread,
        "total_deviation": total_deviation,
        "avg_turns": avg_turns,
        "hand_sizes": hand_sizes,
    }

# Summary comparison
print(f"\n\n{'='*60}")
print(f"  SUMMARY COMPARISON")
print(f"{'='*60}")
print(f"\n  {'Variant':<20s} {'Spread':>8s} {'Deviation':>10s} {'Avg Turns':>10s}  {'Hand Sizes'}")
print(f"  {'-'*20} {'-'*8} {'-'*10} {'-'*10}  {'-'*20}")
for name, r in results.items():
    hs = r["hand_sizes"]
    hs_str = "/".join(str(h) for h in hs)
    print(f"  {name:<20s} {r['spread']:>7.1%} {r['total_deviation']:>10.3f} "
          f"{r['avg_turns']:>10.1f}  {hs_str}")

# Find best
best = min(results.items(), key=lambda x: x[1]["total_deviation"])
print(f"\n  Best balance: {best[0]} (deviation {best[1]['total_deviation']:.3f})")

# Save JSON
with open(os.path.join(script_dir, "compensation_results.json"), "w") as f:
    json.dump(results, f, indent=2, default=str)
print(f"\n  Saved to compensation_results.json")
