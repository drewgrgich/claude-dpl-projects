#!/usr/bin/env python3
"""Comprehensive stress test of v1.5 rules.

Runs the full battery:
  1. Baseline at 2P, 3P, 4P (experts) — seat balance, pacing, scoring
  2. Strategy diversity (4 styles head-to-head at 4P)
  3. Skill gap (1 expert vs 2-3 beginners)
  4. Edge cases: high aggression, all-rush, all-hoarder
  5. v1.4 baselines for direct comparison
"""

import copy
import json
import os
import sys
from collections import defaultdict

from run_simulation import run_batch, load_config, print_report


GAMES_PER_TEST = 500


def load_v14():
    return load_config(os.path.join(os.path.dirname(__file__), "config.json"))


def load_v15():
    return load_config(os.path.join(os.path.dirname(__file__), "config_v15.json"))


def quick_summary(label, agg, num_players):
    """One-line summary of key metrics."""
    wr = agg.get("win_rates", {})
    pp = agg.get("per_player", {})
    wr_vals = list(wr.values())
    spread = max(wr_vals) - min(wr_vals) if wr_vals else 0
    best_seat = max(wr, key=wr.get) if wr else -1
    worst_seat = min(wr, key=wr.get) if wr else -1
    avg_score = sum(pp[pid]["avg_final_score"] for pid in pp) / len(pp) if pp else 0
    score_spread = (max(pp[pid]["avg_final_score"] for pid in pp) -
                    min(pp[pid]["avg_final_score"] for pid in pp)) if pp else 0
    stag = agg.get("stagnation_5_plus_rate", 0)
    lb = agg.get("action_per_game", {}).get("draw_litter_box", 0)
    scav = agg.get("action_per_game", {}).get("scavenge", 0)
    turns = agg.get("avg_turns", 0)
    tlr = agg.get("turn_limit_rate", 0)

    return {
        "label": label,
        "num_players": num_players,
        "avg_turns": turns,
        "turn_limit_rate": tlr,
        "stag_5_plus": stag,
        "avg_stag": agg.get("avg_max_stagnation", 0),
        "seat_spread": spread,
        "best_seat": best_seat,
        "worst_seat": worst_seat,
        "best_seat_wr": wr.get(best_seat, 0),
        "worst_seat_wr": wr.get(worst_seat, 0),
        "avg_score": avg_score,
        "score_spread": score_spread,
        "lb_draws": lb,
        "scavenge": scav,
        "snack_floor": agg.get("snack_floor_per_game", 0),
        "wilds_in_hand": sum(pp[pid]["avg_wilds_in_hand"] for pid in pp) if pp else 0,
        "halftime_rate": agg.get("halftime_rate", 0),
        "mid_bite": agg.get("mid_bite_whistle_rate", 0),
        "poison_peanuts": agg.get("poison_peanuts_per_game", 0),
        "faction_powers": agg.get("faction_powers_per_game", {}),
        "win_rates": dict(wr),
        "per_player": {k: dict(v) for k, v in pp.items()},
    }


def print_table(rows, title):
    """Print a formatted comparison table."""
    print(f"\n{'='*90}")
    print(f"  {title}")
    print(f"{'='*90}")

    header = (f"  {'Test':<32} {'Turns':>6} {'Stag5+':>7} {'SeatSprd':>8} "
              f"{'BestSeat':>9} {'WorstSeat':>10} {'AvgScore':>9} {'LB/game':>8} "
              f"{'Scav/g':>7} {'TLR':>5}")
    print(header)
    print(f"  {'-'*32} {'-'*6} {'-'*7} {'-'*8} {'-'*9} {'-'*10} {'-'*9} {'-'*8} {'-'*7} {'-'*5}")

    for r in rows:
        best_str = f"P{r['best_seat']}:{r['best_seat_wr']:.0%}"
        worst_str = f"P{r['worst_seat']}:{r['worst_seat_wr']:.0%}"
        print(f"  {r['label']:<32} {r['avg_turns']:>6.1f} {r['stag_5_plus']:>6.0%} "
              f"{r['seat_spread']:>7.1%} {best_str:>9} {worst_str:>10} "
              f"{r['avg_score']:>9.1f} {r['lb_draws']:>8.1f} {r['scavenge']:>7.1f} "
              f"{r['turn_limit_rate']:>4.0%}")


def print_faction_table(rows, title):
    """Print faction power usage comparison."""
    print(f"\n{'='*90}")
    print(f"  {title}")
    print(f"{'='*90}")

    factions = ["RED", "ORANGE", "YELLOW", "GREEN", "BLUE", "PURPLE"]
    header = f"  {'Test':<32} " + " ".join(f"{f:>8}" for f in factions)
    print(header)
    print(f"  {'-'*32} " + " ".join(f"{'-'*8}" for _ in factions))

    for r in rows:
        fp = r["faction_powers"]
        vals = " ".join(f"{fp.get(f, 0):>8.2f}" for f in factions)
        print(f"  {r['label']:<32} {vals}")


def print_scoring_detail(rows, title):
    """Print per-player scoring breakdown."""
    print(f"\n{'='*90}")
    print(f"  {title}")
    print(f"{'='*90}")

    for r in rows:
        print(f"\n  --- {r['label']} ({r['num_players']}P) ---")
        pp = r["per_player"]
        wr = r["win_rates"]
        print(f"  {'Player':<8} {'WinRate':>8} {'AvgScore':>9} {'Banked':>8} "
              f"{'Penalty':>8} {'Sets':>6} {'WildsHand':>10} {'ScoreRange':>14}")
        print(f"  {'-'*8} {'-'*8} {'-'*9} {'-'*8} {'-'*8} {'-'*6} {'-'*10} {'-'*14}")
        for pid in sorted(pp.keys()):
            p = pp[pid]
            w = wr.get(pid, 0)
            rng = f"[{p['score_min']:+d}, {p['score_max']:+d}]"
            print(f"  P{pid:<7} {w:>7.1%} {p['avg_final_score']:>+9.1f} "
                  f"{p['avg_banked_score']:>8.1f} {p['avg_hand_penalty']:>8.1f} "
                  f"{p['avg_sets_count']:>6.1f} {p['avg_wilds_in_hand']:>10.2f} "
                  f"{rng:>14}")


if __name__ == "__main__":
    v14 = load_v14()
    v15 = load_v15()

    all_rows = []
    detail_rows = []

    # ================================================================
    # SECTION 1: v1.4 baselines (for comparison)
    # ================================================================
    print("=" * 50)
    print("  SECTION 1: v1.4 BASELINES")
    print("=" * 50)

    for np in [2, 3, 4]:
        print(f"  Running v1.4 baseline at {np}P...")
        agg = run_batch(v14, GAMES_PER_TEST, np, start_seed=1)
        row = quick_summary(f"v1.4 — {np}P experts", agg, np)
        all_rows.append(row)
        detail_rows.append(row)

    # ================================================================
    # SECTION 2: v1.5 at all player counts
    # ================================================================
    print("\n" + "=" * 50)
    print("  SECTION 2: v1.5 AT ALL PLAYER COUNTS")
    print("=" * 50)

    # For 2P, use symmetric hands (7/7 per the rules)
    v15_2p = copy.deepcopy(v15)
    v15_2p["setup"]["hand_size_per_seat"] = [7, 7, 7, 7]

    # For 3P, use 6/7/7
    v15_3p = copy.deepcopy(v15)
    v15_3p["setup"]["hand_size_per_seat"] = [6, 7, 7, 8]

    for np, cfg, label in [
        (2, v15_2p, "v1.5 — 2P experts"),
        (3, v15_3p, "v1.5 — 3P experts"),
        (4, v15,    "v1.5 — 4P experts"),
    ]:
        print(f"  Running {label}...")
        agg = run_batch(cfg, GAMES_PER_TEST, np, start_seed=1)
        row = quick_summary(label, agg, np)
        all_rows.append(row)
        detail_rows.append(row)

    # ================================================================
    # SECTION 3: Strategy diversity (4P, all styles)
    # ================================================================
    print("\n" + "=" * 50)
    print("  SECTION 3: STRATEGY DIVERSITY")
    print("=" * 50)

    styles_configs = [
        {"skill": 1.0, "style": "rush", "aggression": 0.5},
        {"skill": 1.0, "style": "balanced", "aggression": 0.5},
        {"skill": 1.0, "style": "hoarder", "aggression": 0.5},
        {"skill": 1.0, "style": "aggressive", "aggression": 0.5},
    ]

    for version_name, cfg in [("v1.4", v14), ("v1.5", v15)]:
        print(f"  Running {version_name} styles showdown...")
        agg = run_batch(cfg, GAMES_PER_TEST, 4, start_seed=1,
                        player_configs=styles_configs)
        label = f"{version_name} — 4P styles"
        row = quick_summary(label, agg, 4)
        # Annotate with style names
        for pid in range(4):
            row[f"P{pid}_style"] = styles_configs[pid]["style"]
        all_rows.append(row)
        detail_rows.append(row)

    # ================================================================
    # SECTION 4: Skill gap tests
    # ================================================================
    print("\n" + "=" * 50)
    print("  SECTION 4: SKILL GAP (EXPERT vs BEGINNERS)")
    print("=" * 50)

    mixed_3p = [
        {"skill": 1.0, "style": "balanced", "aggression": 0.5},
        {"skill": 0.3, "style": "balanced", "aggression": 0.5},
        {"skill": 0.3, "style": "balanced", "aggression": 0.5},
    ]
    mixed_4p = [
        {"skill": 1.0, "style": "balanced", "aggression": 0.5},
        {"skill": 0.3, "style": "balanced", "aggression": 0.5},
        {"skill": 0.3, "style": "balanced", "aggression": 0.5},
        {"skill": 0.3, "style": "balanced", "aggression": 0.5},
    ]

    for version_name, cfg in [("v1.4", v14), ("v1.5", v15)]:
        print(f"  Running {version_name} mixed skill 3P...")
        agg = run_batch(cfg, GAMES_PER_TEST, 3, start_seed=1,
                        player_configs=mixed_3p)
        row = quick_summary(f"{version_name} — 3P mixed skill", agg, 3)
        all_rows.append(row)
        detail_rows.append(row)

        print(f"  Running {version_name} mixed skill 4P...")
        agg = run_batch(cfg, GAMES_PER_TEST, 4, start_seed=1,
                        player_configs=mixed_4p)
        row = quick_summary(f"{version_name} — 4P mixed skill", agg, 4)
        all_rows.append(row)
        detail_rows.append(row)

    # ================================================================
    # SECTION 5: Edge cases — degenerate strategies
    # ================================================================
    print("\n" + "=" * 50)
    print("  SECTION 5: EDGE CASES")
    print("=" * 50)

    # All-rush: does the game end too fast?
    all_rush = [{"skill": 1.0, "style": "rush", "aggression": 0.8}] * 4
    print("  Running v1.5 all-rush 4P...")
    agg = run_batch(v15, GAMES_PER_TEST, 4, start_seed=1, player_configs=all_rush)
    row = quick_summary("v1.5 — 4P all-rush", agg, 4)
    all_rows.append(row)

    # All-hoarder: does the game stall?
    all_hoard = [{"skill": 1.0, "style": "hoarder", "aggression": 0.2}] * 4
    print("  Running v1.5 all-hoarder 4P...")
    agg = run_batch(v15, GAMES_PER_TEST, 4, start_seed=1, player_configs=all_hoard)
    row = quick_summary("v1.5 — 4P all-hoarder", agg, 4)
    all_rows.append(row)

    # All-beginners: is it still playable?
    all_beginner = [{"skill": 0.2, "style": "balanced", "aggression": 0.5}] * 4
    print("  Running v1.5 all-beginners 4P...")
    agg = run_batch(v15, GAMES_PER_TEST, 4, start_seed=1, player_configs=all_beginner)
    row = quick_summary("v1.5 — 4P all-beginners", agg, 4)
    all_rows.append(row)

    # High aggression + aggressive style
    all_aggro = [{"skill": 1.0, "style": "aggressive", "aggression": 1.0}] * 4
    print("  Running v1.5 max-aggression 4P...")
    agg = run_batch(v15, GAMES_PER_TEST, 4, start_seed=1, player_configs=all_aggro)
    row = quick_summary("v1.5 — 4P max-aggro", agg, 4)
    all_rows.append(row)

    # ================================================================
    # PRINT RESULTS
    # ================================================================

    # Main comparison table
    v14_rows = [r for r in all_rows if r["label"].startswith("v1.4")]
    v15_rows = [r for r in all_rows if r["label"].startswith("v1.5")]
    print_table(v14_rows, "v1.4 BASELINE RESULTS")
    print_table(v15_rows, "v1.5 RESULTS")

    # Faction usage
    faction_rows = [r for r in all_rows if "experts" in r["label"] or "styles" in r["label"]]
    print_faction_table(faction_rows, "FACTION POWER USAGE (per game)")

    # Scoring detail
    score_rows = [r for r in detail_rows if "experts" in r["label"] and ("4P" in r["label"] or "3P" in r["label"])]
    print_scoring_detail(score_rows, "PER-PLAYER SCORING DETAIL")

    # ================================================================
    # VERDICT
    # ================================================================
    print(f"\n{'='*90}")
    print(f"  STRESS TEST VERDICT")
    print(f"{'='*90}")

    issues = []
    warnings = []

    # Check all v1.5 rows for problems
    for r in v15_rows:
        label = r["label"]
        if r["turn_limit_rate"] > 0.02:
            issues.append(f"CRITICAL: {label} — {r['turn_limit_rate']:.0%} of games hit turn limit (stalling)")
        if r["stag_5_plus"] > 0.40:
            warnings.append(f"WARNING: {label} — stagnation still at {r['stag_5_plus']:.0%}")
        if r["seat_spread"] > 0.15 and r["num_players"] >= 3:
            warnings.append(f"WARNING: {label} — seat spread {r['seat_spread']:.1%} "
                          f"(P{r['best_seat']}:{r['best_seat_wr']:.0%} vs P{r['worst_seat']}:{r['worst_seat_wr']:.0%})")
        if r["avg_turns"] < 20:
            warnings.append(f"WARNING: {label} — games very short at {r['avg_turns']:.0f} turns")
        if r["avg_turns"] > 60:
            warnings.append(f"WARNING: {label} — games very long at {r['avg_turns']:.0f} turns")

        # Check for negative average scores
        pp = r.get("per_player", {})
        for pid in pp:
            if pp[pid]["avg_final_score"] < 0:
                warnings.append(f"WARNING: {label} — P{pid} avg score is negative ({pp[pid]['avg_final_score']:+.1f})")

    if issues:
        print("\n  CRITICAL ISSUES:")
        for i in issues:
            print(f"    ✗ {i}")
    else:
        print("\n  ✓ No critical issues found")

    if warnings:
        print("\n  WARNINGS:")
        for w in warnings:
            print(f"    ⚠ {w}")
    else:
        print("\n  ✓ No warnings")

    # Summary comparison: v1.4 4P vs v1.5 4P
    v14_4p = next((r for r in all_rows if r["label"] == "v1.4 — 4P experts"), None)
    v15_4p = next((r for r in all_rows if r["label"] == "v1.5 — 4P experts"), None)
    if v14_4p and v15_4p:
        print(f"\n  HEAD-TO-HEAD: v1.4 vs v1.5 (4P experts)")
        print(f"  {'Metric':<28} {'v1.4':>10} {'v1.5':>10} {'Delta':>10}")
        print(f"  {'-'*28} {'-'*10} {'-'*10} {'-'*10}")
        comparisons = [
            ("Stagnation 5+", "stag_5_plus", True),
            ("Avg stagnation streak", "avg_stag", True),
            ("Seat win-rate spread", "seat_spread", True),
            ("Worst seat win rate", "worst_seat_wr", False),
            ("Avg game length", "avg_turns", None),
            ("Avg final score", "avg_score", False),
            ("Score spread", "score_spread", True),
            ("Litter Box draws/game", "lb_draws", False),
            ("Snack Floor/game", "snack_floor", None),
        ]
        for name, key, lower_better in comparisons:
            v14_val = v14_4p[key]
            v15_val = v15_4p[key]
            delta = v15_val - v14_val
            if isinstance(v14_val, float) and abs(v14_val) < 1:
                v14_str = f"{v14_val:.1%}"
                v15_str = f"{v15_val:.1%}"
                d_str = f"{delta:+.1%}"
            else:
                v14_str = f"{v14_val:.1f}"
                v15_str = f"{v15_val:.1f}"
                d_str = f"{delta:+.1f}"

            if lower_better is not None:
                if lower_better:
                    tag = " ✓" if delta < -0.01 else (" ✗" if delta > 0.01 else "")
                else:
                    tag = " ✓" if delta > 0.01 else (" ✗" if delta < -0.01 else "")
            else:
                tag = ""

            print(f"  {name:<28} {v14_str:>10} {v15_str:>10} {d_str:>8}{tag}")

    print(f"\n{'='*90}")
    print(f"  STRESS TEST COMPLETE — {GAMES_PER_TEST} games × {len(all_rows)} configs "
          f"= {GAMES_PER_TEST * len(all_rows)} total games")
    print(f"{'='*90}\n")
