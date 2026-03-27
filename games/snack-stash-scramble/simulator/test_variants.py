#!/usr/bin/env python3
"""A/B test rule variants against the v1.4 baseline.

Tests each proposed rule change independently, then tests the best
combined fix. All tests use 4 players (where issues are worst) with
500 games each.
"""

import copy
import json
import os
import sys

from run_simulation import run_batch, load_config


NUM_GAMES = 500
NUM_PLAYERS = 4
SEED = 1


def make_config(base_config: dict, overrides: dict) -> dict:
    """Deep-copy base config and apply overrides."""
    cfg = copy.deepcopy(base_config)
    for key_path, value in overrides.items():
        parts = key_path.split(".")
        d = cfg
        for p in parts[:-1]:
            d = d[p]
        d[parts[-1]] = value
    return cfg


def extract_key_metrics(agg: dict) -> dict:
    """Pull the metrics we care about from aggregated stats."""
    wr = agg.get("win_rates", {})
    pp = agg.get("per_player", {})
    return {
        "avg_turns": agg["avg_turns"],
        "stag_5_plus": agg["stagnation_5_plus_rate"],
        "avg_stag": agg["avg_max_stagnation"],
        "seat_spread": max(wr.values()) - min(wr.values()) if wr else 0,
        "seat_1_wr": wr.get(0, 0),
        "seat_4_wr": wr.get(3, 0),
        "avg_score": sum(pp[pid]["avg_final_score"] for pid in pp) / len(pp) if pp else 0,
        "score_spread": (max(pp[pid]["avg_final_score"] for pid in pp) -
                         min(pp[pid]["avg_final_score"] for pid in pp)) if pp else 0,
        "lb_draws": agg.get("action_per_game", {}).get("draw_litter_box", 0),
        "scavenge": agg.get("action_per_game", {}).get("scavenge", 0),
        "snack_floor": agg["snack_floor_per_game"],
        "wilds_in_hand": sum(pp[pid]["avg_wilds_in_hand"] for pid in pp) if pp else 0,
        "faction_spread": (max(agg["faction_powers_per_game"].values()) -
                           min(agg["faction_powers_per_game"].values()))
                          if agg.get("faction_powers_per_game") else 0,
        "red_usage": agg.get("faction_powers_per_game", {}).get("RED", 0),
        "green_usage": agg.get("faction_powers_per_game", {}).get("GREEN", 0),
        "orange_usage": agg.get("faction_powers_per_game", {}).get("ORANGE", 0),
    }


def print_comparison(name: str, baseline: dict, variant: dict):
    """Print a formatted comparison of two metric sets."""
    def delta(key, invert=False):
        b, v = baseline[key], variant[key]
        d = v - b
        sign = "+" if d > 0 else ""
        # For some metrics, down is good (stagnation, seat spread)
        if invert:
            color = "BETTER" if d < 0 else ("WORSE" if d > 0 else "SAME")
        else:
            color = "BETTER" if d > 0 else ("WORSE" if d < 0 else "SAME")
        return f"{v:.2f} ({sign}{d:.2f} {color})"

    print(f"\n{'='*70}")
    print(f"  VARIANT: {name}")
    print(f"{'='*70}")
    print(f"  {'Metric':<28} {'Baseline':>12} {'Variant':>25}")
    print(f"  {'-'*28} {'-'*12} {'-'*25}")
    print(f"  {'Stagnation 5+ rate':<28} {baseline['stag_5_plus']:>11.1%} {delta('stag_5_plus', invert=True):>25}")
    print(f"  {'Avg worst stagnation':<28} {baseline['avg_stag']:>12.1f} {delta('avg_stag', invert=True):>25}")
    print(f"  {'Seat win-rate spread':<28} {baseline['seat_spread']:>11.1%} {delta('seat_spread', invert=True):>25}")
    print(f"  {'Seat 1 win rate':<28} {baseline['seat_1_wr']:>11.1%} {delta('seat_1_wr'):>25}")
    print(f"  {'Seat 4 win rate':<28} {baseline['seat_4_wr']:>11.1%} {delta('seat_4_wr'):>25}")
    print(f"  {'Avg game length (turns)':<28} {baseline['avg_turns']:>12.1f} {delta('avg_turns'):>25}")
    print(f"  {'Avg final score':<28} {baseline['avg_score']:>12.1f} {delta('avg_score'):>25}")
    print(f"  {'Score spread (P0-P3)':<28} {baseline['score_spread']:>12.1f} {delta('score_spread', invert=True):>25}")
    print(f"  {'Litter Box draws/game':<28} {baseline['lb_draws']:>12.2f} {delta('lb_draws'):>25}")
    print(f"  {'Scavenge draws/game':<28} {baseline['scavenge']:>12.2f} {delta('scavenge'):>25}")
    print(f"  {'Snack Floor/game':<28} {baseline['snack_floor']:>12.2f} {delta('snack_floor'):>25}")
    print(f"  {'Wilds stuck in hand':<28} {baseline['wilds_in_hand']:>12.2f} {delta('wilds_in_hand'):>25}")
    print(f"  {'Faction usage spread':<28} {baseline['faction_spread']:>12.2f} {delta('faction_spread', invert=True):>25}")
    print(f"  {'RED usage/game':<28} {baseline['red_usage']:>12.2f} {delta('red_usage'):>25}")
    print(f"  {'GREEN usage/game':<28} {baseline['green_usage']:>12.2f} {delta('green_usage'):>25}")
    print(f"  {'ORANGE usage/game':<28} {baseline['orange_usage']:>12.2f} {delta('orange_usage'):>25}")


if __name__ == "__main__":
    base_config = load_config()

    # ============================
    # BASELINE
    # ============================
    print("Running BASELINE (v1.4 rules, 4 players)...")
    baseline_agg = run_batch(base_config, NUM_GAMES, NUM_PLAYERS, start_seed=SEED)
    baseline = extract_key_metrics(baseline_agg)
    print(f"  Baseline: stag={baseline['stag_5_plus']:.1%}, seat_spread={baseline['seat_spread']:.1%}, "
          f"turns={baseline['avg_turns']:.1f}")

    # ============================
    # VARIANT A: Snack Floor draws 4
    # ============================
    print("\nRunning VARIANT A: Snack Floor draws 4 instead of 3...")
    cfg_a = make_config(base_config, {"draw.snack_floor_draw_count": 4})
    agg_a = run_batch(cfg_a, NUM_GAMES, NUM_PLAYERS, start_seed=SEED)
    metrics_a = extract_key_metrics(agg_a)
    print_comparison("A: Snack Floor draws 4", baseline, metrics_a)

    # ============================
    # VARIANT B: Remove Stale Snack Rule
    # ============================
    print("\nRunning VARIANT B: No Stale Snack Rule...")
    cfg_b = make_config(base_config, {"draw.stale_snack_rule": False})
    agg_b = run_batch(cfg_b, NUM_GAMES, NUM_PLAYERS, start_seed=SEED)
    metrics_b = extract_key_metrics(agg_b)
    print_comparison("B: No Stale Snack Rule", baseline, metrics_b)

    # ============================
    # VARIANT C: Asymmetric starting hands (6/7/7/8)
    # ============================
    print("\nRunning VARIANT C: Asymmetric hands (6/7/7/8)...")
    cfg_c = make_config(base_config, {
        "setup.asymmetric_hands": True,
        "setup.hand_size_per_seat": [6, 7, 7, 8],
    })
    agg_c = run_batch(cfg_c, NUM_GAMES, NUM_PLAYERS, start_seed=SEED)
    metrics_c = extract_key_metrics(agg_c)
    print_comparison("C: Asymmetric hands (6/7/7/8)", baseline, metrics_c)

    # ============================
    # VARIANT D: Scavenge (draw 2 when stuck)
    # ============================
    print("\nRunning VARIANT D: Scavenge (draw 2 if couldn't bank last turn)...")
    cfg_d = make_config(base_config, {
        "draw.scavenge_enabled": True,
        "draw.scavenge_draw": 2,
    })
    agg_d = run_batch(cfg_d, NUM_GAMES, NUM_PLAYERS, start_seed=SEED)
    metrics_d = extract_key_metrics(agg_d)
    print_comparison("D: Scavenge (draw 2 when stuck)", baseline, metrics_d)

    # ============================
    # VARIANT E: Wilds bank at 0 points
    # ============================
    print("\nRunning VARIANT E: Banked wilds worth 0 points...")
    cfg_e = make_config(base_config, {"scoring.wild_bank_value_override": 0})
    agg_e = run_batch(cfg_e, NUM_GAMES, NUM_PLAYERS, start_seed=SEED)
    metrics_e = extract_key_metrics(agg_e)
    print_comparison("E: Banked wilds worth 0", baseline, metrics_e)

    # ============================
    # VARIANT F: RED +3 bonus, GREEN peek 5 + take one
    # ============================
    print("\nRunning VARIANT F: Buffed RED (+3 bonus) & GREEN (peek 5, take 1)...")
    cfg_f = make_config(base_config, {
        "scoring.red_protection_bonus": 3,
        "faction_variants.green_peek_count": 5,
        "faction_variants.green_take_one": True,
    })
    agg_f = run_batch(cfg_f, NUM_GAMES, NUM_PLAYERS, start_seed=SEED)
    metrics_f = extract_key_metrics(agg_f)
    print_comparison("F: Buffed RED & GREEN", baseline, metrics_f)

    # ============================
    # VARIANT G: Snack Floor threshold 3 (triggers at ≤3 cards)
    # ============================
    print("\nRunning VARIANT G: Snack Floor at ≤3 cards (instead of ≤2)...")
    cfg_g = make_config(base_config, {"draw.snack_floor_threshold": 3})
    agg_g = run_batch(cfg_g, NUM_GAMES, NUM_PLAYERS, start_seed=SEED)
    metrics_g = extract_key_metrics(agg_g)
    print_comparison("G: Snack Floor threshold ≤3", baseline, metrics_g)

    # ============================
    # COMBINED: Best fixes together
    # ============================
    print("\nRunning COMBINED FIX: Scavenge + Asymmetric hands + Buffed RED/GREEN + No Stale Snack...")
    cfg_combined = make_config(base_config, {
        "draw.scavenge_enabled": True,
        "draw.scavenge_draw": 2,
        "draw.stale_snack_rule": False,
        "setup.asymmetric_hands": True,
        "setup.hand_size_per_seat": [6, 7, 7, 8],
        "scoring.red_protection_bonus": 3,
        "faction_variants.green_peek_count": 5,
        "faction_variants.green_take_one": True,
    })
    agg_combined = run_batch(cfg_combined, NUM_GAMES, NUM_PLAYERS, start_seed=SEED)
    metrics_combined = extract_key_metrics(agg_combined)
    print_comparison("COMBINED: Best fixes together", baseline, metrics_combined)

    print(f"\n{'='*70}")
    print(f"  ALL TESTS COMPLETE — {NUM_GAMES} games × 9 configs = {NUM_GAMES * 9} games total")
    print(f"{'='*70}\n")
