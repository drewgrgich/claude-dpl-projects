#!/usr/bin/env python3
"""Parameter sweep for The Drop (Championship Mode).

Tests whether The Drop's scaling problems at 4-5 players
are fixable with parameter tuning, or structurally broken.

Sweeps:
1. Boiling point scaling by player count
2. Heat table flattening
3. Hybrid: both changes together
4. Alternative: top-half-gets-zero Heat model
"""

import json
import copy
import sys
from collections import defaultdict

from game_state import load_config
from run_drop import run_batch_championships, print_drop_report

NUM_CHAMPIONSHIPS = 100
SEED = 1


def run_drop_experiment(label: str, config: dict, num_players: int,
                        player_configs=None) -> dict:
    """Run a batch of championships and return aggregated stats."""
    print(f"\n  Running: {label} ({num_players}p, {NUM_CHAMPIONSHIPS} champs)...",
          flush=True)
    agg = run_batch_championships(
        config, NUM_CHAMPIONSHIPS, num_players,
        start_seed=SEED, player_configs=player_configs, verbose=False
    )
    return agg


def compare_drop_metric(label: str, experiments: dict, key: str,
                        fmt: str = ".2f", higher_is: str = "neutral"):
    """Print a comparison table for a Drop metric."""
    print(f"\n  {label}:")
    values = {}
    for name, agg in experiments.items():
        val = agg.get(key, 0)
        values[name] = val
        print(f"    {name:40s}: {val:{fmt}}")

    if len(values) >= 2 and higher_is != "neutral":
        best_name = min(values, key=values.get) if higher_is == "lower" else \
                    max(values, key=values.get)
        print(f"    → Best: {best_name}")


def sweep_drop_for_player_count(num_players: int):
    """Run all Drop variants for a given player count."""
    print(f"\n{'='*70}")
    print(f"  THE DROP SWEEP — {num_players} PLAYERS")
    print(f"{'='*70}")

    base_config = load_config()
    experiments = {}

    # ── A: Baseline (current v4.6) ──
    config_a = copy.deepcopy(base_config)
    experiments["A: Baseline (BP=15, 0/2/4/6/8)"] = run_drop_experiment(
        "Baseline", config_a, num_players)

    # ── B: Higher boiling point ──
    # Scale BP by player count: 3p=15, 4p=20, 5p=28
    bp_map = {3: 15, 4: 20, 5: 28}
    config_b = copy.deepcopy(base_config)
    bp = bp_map[num_players]
    config_b["the_drop"]["boiling_point"] = bp
    experiments[f"B: Higher BP ({bp})"] = run_drop_experiment(
        f"Boiling point={bp}", config_b, num_players)

    # ── C: Flatter Heat curve ──
    # 0/1/3/5/7 instead of 0/2/4/6/8
    config_c = copy.deepcopy(base_config)
    flat_heat = {3: {"1": 0, "2": 1, "3": 3},
                 4: {"1": 0, "2": 1, "3": 3, "4": 5},
                 5: {"1": 0, "2": 1, "3": 3, "4": 5, "5": 7}}
    config_c["the_drop"]["heat_by_finish"] = flat_heat[num_players]
    experiments["C: Flat Heat (0/1/3/5/7)"] = run_drop_experiment(
        "Flat Heat", config_c, num_players)

    # ── D: Hybrid — higher BP + flatter Heat ──
    config_d = copy.deepcopy(base_config)
    config_d["the_drop"]["boiling_point"] = bp
    config_d["the_drop"]["heat_by_finish"] = flat_heat[num_players]
    experiments[f"D: Hybrid (BP={bp} + flat)"] = run_drop_experiment(
        "Hybrid", config_d, num_players)

    # ── E: Top-half-zero model ──
    # Only bottom half gets Heat. Reduces total Heat entering system.
    # 3p: 1st=0, 2nd=0, 3rd=4
    # 4p: 1st=0, 2nd=0, 3rd=3, 4th=6
    # 5p: 1st=0, 2nd=0, 3rd=2, 4th=5, 5th=8
    config_e = copy.deepcopy(base_config)
    top_half_zero = {3: {"1": 0, "2": 0, "3": 4},
                     4: {"1": 0, "2": 0, "3": 3, "4": 6},
                     5: {"1": 0, "2": 0, "3": 2, "4": 5, "5": 8}}
    config_e["the_drop"]["heat_by_finish"] = top_half_zero[num_players]
    experiments["E: Top-half-zero (0/0/...)"] = run_drop_experiment(
        "Top-half-zero", config_e, num_players)

    # ── F: Steeper curve, higher BP ──
    # More dramatic spread but more room to breathe
    # 0/1/2/4/8 with BP=25 at 5p, BP=18 at 4p
    bp_map_f = {3: 15, 4: 18, 5: 25}
    config_f = copy.deepcopy(base_config)
    config_f["the_drop"]["boiling_point"] = bp_map_f[num_players]
    steep_heat = {3: {"1": 0, "2": 1, "3": 2},
                  4: {"1": 0, "2": 1, "3": 2, "4": 4},
                  5: {"1": 0, "2": 1, "3": 2, "4": 4, "5": 8}}
    config_f["the_drop"]["heat_by_finish"] = steep_heat[num_players]
    experiments[f"F: Steep+room (BP={bp_map_f[num_players]}, 0/1/2/4/8)"] = \
        run_drop_experiment("Steep+room", config_f, num_players)

    # ── Print comparison ──
    print(f"\n{'─'*70}")
    print(f"  COMPARISON: The Drop at {num_players} Players")
    print(f"{'─'*70}")

    compare_drop_metric("Avg games/championship", experiments,
                        "avg_games_per_championship", fmt=".1f", higher_is="neutral")
    compare_drop_metric("Min games", experiments, "min_games", fmt="d")
    compare_drop_metric("Max games", experiments, "max_games", fmt="d")
    compare_drop_metric("Boiling point reached", experiments,
                        "boiling_point_rate", fmt=".1%", higher_is="neutral")

    # Championship win spread
    print(f"\n  Championship win spread:")
    for name, agg in experiments.items():
        rates = agg["championship_win_rates"]
        spread = max(rates.values()) - min(rates.values())
        print(f"    {name:40s}: {spread:.1%}")

    # Heat distribution
    print(f"\n  Avg Heat (mean across players):")
    for name, agg in experiments.items():
        heats = list(agg["avg_heat_by_player"].values())
        mean_heat = sum(heats) / len(heats)
        heat_spread = max(heats) - min(heats)
        print(f"    {name:40s}: {mean_heat:.1f} (spread: {heat_spread:.1f})")

    return experiments


def print_summary(all_experiments: dict):
    """Print final summary across all player counts."""
    print(f"\n{'='*70}")
    print(f"  SUMMARY: THE DROP FEASIBILITY")
    print(f"{'='*70}")

    # For each player count, identify which config hits the sweet spot
    # Target: 4-6 games/championship, <20% win spread, 50-80% boiling rate
    for pcount, experiments in all_experiments.items():
        print(f"\n  --- {pcount} Players ---")
        for name, agg in experiments.items():
            games = agg["avg_games_per_championship"]
            bp_rate = agg["boiling_point_rate"]
            rates = agg["championship_win_rates"]
            spread = max(rates.values()) - min(rates.values())

            # Grade it
            grade_parts = []
            if 4.0 <= games <= 6.0:
                grade_parts.append("✓ length")
            else:
                grade_parts.append(f"✗ length ({games:.1f})")

            if spread <= 0.15:
                grade_parts.append("✓ balance")
            else:
                grade_parts.append(f"✗ balance ({spread:.0%})")

            grade = " | ".join(grade_parts)
            print(f"    {name:40s}: {games:.1f} games, {spread:.0%} spread → {grade}")


if __name__ == "__main__":
    print(f"THE DROP — PARAMETER SWEEP")
    print(f"{NUM_CHAMPIONSHIPS} championships per configuration, seed={SEED}")

    all_experiments = {}
    for pc in [3, 4, 5]:
        all_experiments[pc] = sweep_drop_for_player_count(pc)

    print_summary(all_experiments)

    print(f"\n{'='*70}")
    print(f"  ALL DROP SWEEPS COMPLETE")
    print(f"{'='*70}")
