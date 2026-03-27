#!/usr/bin/env python3
"""Parameter sweep for rule improvement experiments.

Tests three proposed rule changes:
1. Trample threshold at 3 players (3 vs 4 vs 5)
2. Set bonus progression (baseline vs mid-set bonus vs lower 2nd set)
3. Sneak cancellation at 5 players (2+ vs 3+ cancel)
"""

import json
import copy
import sys
from collections import defaultdict

from cards import build_full_deck, FACTION_COLORS
from game_state import load_config
from run_simulation import run_batch, print_report

NUM_GAMES = 500
SEED = 1


def run_experiment(label: str, config: dict, num_players: int,
                   player_configs=None) -> dict:
    """Run a batch and return aggregated stats."""
    print(f"\n  Running: {label} ({num_players}p, {NUM_GAMES} games)...", flush=True)
    agg = run_batch(config, NUM_GAMES, num_players,
                    start_seed=SEED, player_configs=player_configs)
    return agg


def compare_metric(label: str, experiments: dict, metric_path: str,
                   fmt: str = ".2f", higher_is: str = "neutral"):
    """Print a comparison table for a metric across experiments."""
    print(f"\n  {label}:")
    values = {}
    for name, agg in experiments.items():
        val = agg
        for key in metric_path.split("."):
            val = val[key] if isinstance(val, dict) else val
        values[name] = val
        print(f"    {name:30s}: {val:{fmt}}")

    if len(values) >= 2:
        vals = list(values.values())
        best_name = min(values, key=values.get) if higher_is == "lower" else \
                    max(values, key=values.get) if higher_is == "higher" else None
        if best_name:
            print(f"    → Best: {best_name}")


def sweep_trample_threshold():
    """Sweep 1: Trample threshold at 3 players."""
    print(f"\n{'='*70}")
    print(f"  SWEEP 1: TRAMPLE THRESHOLD AT 3 PLAYERS")
    print(f"{'='*70}")

    base_config = load_config()
    experiments = {}

    for threshold in [3, 4, 5]:
        config = copy.deepcopy(base_config)
        config["game_rules"]["trample_threshold"]["3_player"] = threshold
        label = f"Threshold={threshold}"
        experiments[label] = run_experiment(label, config, num_players=3)

    print(f"\n{'─'*70}")
    print(f"  COMPARISON: Trample Threshold at 3 Players")
    print(f"{'─'*70}")

    compare_metric("Avg Tramples/game", experiments, "avg_tramples",
                   fmt=".2f", higher_is="neutral")
    compare_metric("Zero-Trample rate", experiments, "zero_trample_rate",
                   fmt=".1%", higher_is="neutral")
    compare_metric("Avg cards trampled/game", experiments, "avg_cards_trampled_per_game",
                   fmt=".1f", higher_is="lower")
    compare_metric("Avg VP", experiments, "avg_vp",
                   fmt=".1f", higher_is="neutral")
    compare_metric("Avg VP spread", experiments, "avg_vp_spread",
                   fmt=".1f", higher_is="lower")
    compare_metric("1st set rate", experiments, "first_set_rate",
                   fmt=".1%", higher_is="neutral")
    compare_metric("Win rate spread", experiments, "win_rate_spread",
                   fmt=".1%", higher_is="lower")
    compare_metric("Avg rounds", experiments, "avg_rounds",
                   fmt=".1f", higher_is="neutral")
    compare_metric("Sneak success rate", experiments, "sneak_success_rate",
                   fmt=".1%", higher_is="neutral")

    return experiments


def sweep_set_bonus():
    """Sweep 2: Set bonus progression."""
    print(f"\n{'='*70}")
    print(f"  SWEEP 2: SET BONUS PROGRESSION (4 players)")
    print(f"{'='*70}")

    base_config = load_config()
    experiments = {}

    # Baseline: 3 colors = 5VP, 6 colors = 8VP
    config_a = copy.deepcopy(base_config)
    experiments["Baseline (3=5, 6=8)"] = run_experiment(
        "Baseline", config_a, num_players=4)

    # Option B: Add 4-color bonus of 3VP
    config_b = copy.deepcopy(base_config)
    config_b["game_rules"]["set_bonus"]["mid_set_colors"] = 4
    config_b["game_rules"]["set_bonus"]["mid_set_vp"] = 3
    experiments["+ Mid bonus (3=5, 4=3, 6=8)"] = run_experiment(
        "+ Mid 4-color=3VP", config_b, num_players=4)

    # Option C: Lower 2nd set to 5 colors
    config_c = copy.deepcopy(base_config)
    config_c["game_rules"]["set_bonus"]["second_set_colors"] = 5
    experiments["Lower 2nd (3=5, 5=8)"] = run_experiment(
        "Lower 2nd set to 5 colors", config_c, num_players=4)

    # Option D: Both — mid bonus + lower 2nd
    config_d = copy.deepcopy(base_config)
    config_d["game_rules"]["set_bonus"]["mid_set_colors"] = 4
    config_d["game_rules"]["set_bonus"]["mid_set_vp"] = 3
    config_d["game_rules"]["set_bonus"]["second_set_colors"] = 5
    experiments["Both (3=5, 4=3, 5=8)"] = run_experiment(
        "Both: mid + lower 2nd", config_d, num_players=4)

    print(f"\n{'─'*70}")
    print(f"  COMPARISON: Set Bonus Progression")
    print(f"{'─'*70}")

    compare_metric("Avg VP", experiments, "avg_vp", fmt=".1f")
    compare_metric("Avg set bonus", experiments, "avg_set_bonus", fmt=".1f")
    compare_metric("1st set rate (3+ colors)", experiments, "first_set_rate", fmt=".1%")
    compare_metric("2nd set rate", experiments, "second_set_rate", fmt=".1%")
    compare_metric("Avg VP spread", experiments, "avg_vp_spread", fmt=".1f", higher_is="lower")
    compare_metric("Win rate spread", experiments, "win_rate_spread", fmt=".1%", higher_is="lower")

    # Show color distributions side by side
    print(f"\n  Color distribution:")
    all_color_counts = set()
    for agg in experiments.values():
        all_color_counts.update(agg["color_distribution"].keys())
    header = f"    {'Colors':<8}"
    for name in experiments:
        header += f" {name[:18]:>18}"
    print(header)
    for colors in sorted(all_color_counts):
        row = f"    {colors:<8}"
        for name, agg in experiments.items():
            rate = agg["color_distribution"].get(colors, 0)
            row += f" {rate:>17.1%}"
        print(row)

    return experiments


def sweep_sneak_cancel():
    """Sweep 3: Sneak cancellation at 5 players."""
    print(f"\n{'='*70}")
    print(f"  SWEEP 3: SNEAK CANCELLATION AT 5 PLAYERS")
    print(f"{'='*70}")

    base_config = load_config()
    experiments = {}

    # Baseline: cancel at 2+
    config_a = copy.deepcopy(base_config)
    config_a["game_rules"]["sneak_cancel_threshold"] = {
        "3_player": 2, "4_player": 2, "5_player": 2
    }
    experiments["Cancel at 2+ (baseline)"] = run_experiment(
        "Cancel at 2+", config_a, num_players=5)

    # Option B: cancel at 3+ at 5 players
    config_b = copy.deepcopy(base_config)
    config_b["game_rules"]["sneak_cancel_threshold"] = {
        "3_player": 2, "4_player": 2, "5_player": 3
    }
    experiments["Cancel at 3+ (5p only)"] = run_experiment(
        "Cancel at 3+", config_b, num_players=5)

    print(f"\n{'─'*70}")
    print(f"  COMPARISON: Sneak Cancellation at 5 Players")
    print(f"{'─'*70}")

    compare_metric("Sneak success rate", experiments, "sneak_success_rate",
                   fmt=".1%", higher_is="neutral")
    compare_metric("Avg Sneak attempts/game", experiments, "avg_sneak_attempts",
                   fmt=".1f", higher_is="neutral")
    compare_metric("Avg Sneak successes/game", experiments, "avg_sneak_successes",
                   fmt=".1f", higher_is="neutral")
    compare_metric("Avg Shoves/game", experiments, "avg_shoves",
                   fmt=".1f", higher_is="neutral")
    compare_metric("Avg VP", experiments, "avg_vp", fmt=".1f")
    compare_metric("Avg VP spread", experiments, "avg_vp_spread",
                   fmt=".1f", higher_is="lower")
    compare_metric("Win rate spread", experiments, "win_rate_spread",
                   fmt=".1%", higher_is="lower")
    compare_metric("Avg Tramples/game", experiments, "avg_tramples",
                   fmt=".2f", higher_is="neutral")
    compare_metric("1st set rate", experiments, "first_set_rate", fmt=".1%")
    compare_metric("Avg rounds", experiments, "avg_rounds", fmt=".1f")

    return experiments


if __name__ == "__main__":
    print(f"RULE IMPROVEMENT PARAMETER SWEEPS")
    print(f"{NUM_GAMES} games per configuration, seed={SEED}")

    exp1 = sweep_trample_threshold()
    exp2 = sweep_set_bonus()
    exp3 = sweep_sneak_cancel()

    print(f"\n{'='*70}")
    print(f"  ALL SWEEPS COMPLETE")
    print(f"{'='*70}")
