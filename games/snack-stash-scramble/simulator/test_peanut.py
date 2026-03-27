#!/usr/bin/env python3
"""A/B test: Poisoned Peanut Option A (sideways cards subtract face value).

Compares v1.5 baseline vs v1.5 + Poisoned Peanut negative scoring.
Tests all player counts, styles, and mixed skill to see how offensive
Yellow play reshapes the game.
"""

import copy
import json
import os
from collections import defaultdict

from run_simulation import run_batch, load_config


GAMES = 500


def load_v15():
    return load_config(os.path.join(os.path.dirname(__file__), "config_v15.json"))


def extract(agg):
    wr = agg.get("win_rates", {})
    pp = agg.get("per_player", {})
    fp = agg.get("faction_powers_per_game", {})
    ap = agg.get("action_per_game", {})
    return {
        "avg_turns": agg["avg_turns"],
        "stag_5": agg["stagnation_5_plus_rate"],
        "seat_spread": max(wr.values()) - min(wr.values()) if wr else 0,
        "avg_score": sum(pp[p]["avg_final_score"] for p in pp) / len(pp) if pp else 0,
        "score_spread": (max(pp[p]["avg_final_score"] for p in pp) -
                         min(pp[p]["avg_final_score"] for p in pp)) if pp else 0,
        "yellow_usage": fp.get("YELLOW", 0),
        "red_usage": fp.get("RED", 0),
        "orange_usage": fp.get("ORANGE", 0),
        "green_usage": fp.get("GREEN", 0),
        "blue_usage": fp.get("BLUE", 0),
        "purple_usage": fp.get("PURPLE", 0),
        "poison_peanuts": agg.get("poison_peanuts_per_game", 0),
        "yellow_extend": ap.get("yellow_extend", 0),
        "lb_draws": ap.get("draw_litter_box", 0),
        "tlr": agg.get("turn_limit_rate", 0),
        "win_rates": dict(wr),
        "per_player": {k: dict(v) for k, v in pp.items()},
    }


def side_by_side(label, base, peanut):
    def delta(key, invert=False):
        b, v = base[key], peanut[key]
        d = v - b
        s = "+" if d > 0 else ""
        tag = ""
        if abs(d) > 0.01:
            if invert:
                tag = " BETTER" if d < 0 else " WORSE"
            else:
                tag = " BETTER" if d > 0 else " WORSE"
        return f"{v:.2f} ({s}{d:.2f}{tag})"

    print(f"\n{'='*75}")
    print(f"  {label}")
    print(f"{'='*75}")
    print(f"  {'Metric':<30} {'Baseline':>12} {'+ Peanut':>28}")
    print(f"  {'-'*30} {'-'*12} {'-'*28}")
    print(f"  {'Avg game length':<30} {base['avg_turns']:>12.1f} {delta('avg_turns'):>28}")
    print(f"  {'Stagnation 5+':<30} {base['stag_5']:>11.0%} {delta('stag_5', True):>28}")
    print(f"  {'Seat spread':<30} {base['seat_spread']:>11.1%} {delta('seat_spread', True):>28}")
    print(f"  {'Avg score':<30} {base['avg_score']:>12.1f} {delta('avg_score'):>28}")
    print(f"  {'Score spread':<30} {base['score_spread']:>12.1f} {delta('score_spread', True):>28}")
    print(f"  {'Turn limit rate':<30} {base['tlr']:>11.0%} {delta('tlr', True):>28}")
    print()
    print(f"  {'YELLOW triggers/game':<30} {base['yellow_usage']:>12.2f} {delta('yellow_usage'):>28}")
    print(f"  {'Yellow extends/game':<30} {base['yellow_extend']:>12.2f} {delta('yellow_extend'):>28}")
    print(f"  {'Poisoned Peanuts/game':<30} {base['poison_peanuts']:>12.2f} {delta('poison_peanuts'):>28}")
    print(f"  {'RED triggers/game':<30} {base['red_usage']:>12.2f} {delta('red_usage'):>28}")
    print()
    print(f"  {'ORANGE triggers/game':<30} {base['orange_usage']:>12.2f} {delta('orange_usage'):>28}")
    print(f"  {'GREEN triggers/game':<30} {base['green_usage']:>12.2f} {delta('green_usage'):>28}")
    print(f"  {'BLUE triggers/game':<30} {base['blue_usage']:>12.2f} {delta('blue_usage'):>28}")
    print(f"  {'PURPLE triggers/game':<30} {base['purple_usage']:>12.2f} {delta('purple_usage'):>28}")


def print_poison_detail(label, agg):
    """Show per-player poison damage stats."""
    pp = agg.get("per_player", {})
    wr = agg.get("win_rates", {})
    print(f"\n  --- {label}: Per-Player Detail ---")
    print(f"  {'Player':<8} {'WinRate':>8} {'AvgScore':>9} {'Banked':>8} "
          f"{'Penalty':>8} {'PoisonDmg':>10} {'PoisonCards':>12}")
    print(f"  {'-'*8} {'-'*8} {'-'*9} {'-'*8} {'-'*8} {'-'*10} {'-'*12}")
    for pid in sorted(pp.keys()):
        p = pp[pid]
        w = wr.get(pid, 0)
        pd_val = p.get("avg_poison_damage", 0)
        pc_val = p.get("avg_poisoned_cards", 0)
        print(f"  P{pid:<7} {w:>7.1%} {p['avg_final_score']:>+9.1f} "
              f"{p['avg_banked_score']:>8.1f} {p['avg_hand_penalty']:>8.1f} "
              f"{pd_val:>10.1f} {pc_val:>12.2f}")


if __name__ == "__main__":
    v15_base = load_v15()
    v15_peanut = copy.deepcopy(v15_base)
    v15_peanut["scoring"]["poisoned_peanut_negative"] = True

    results = []

    # ---- Test 1: All player counts, experts ----
    for np in [2, 3, 4]:
        # Adjust hand sizes for 2P
        cfg_base = copy.deepcopy(v15_base)
        cfg_pnut = copy.deepcopy(v15_peanut)
        if np == 2:
            cfg_base["setup"]["hand_size_per_seat"] = [7, 7, 7, 7]
            cfg_pnut["setup"]["hand_size_per_seat"] = [7, 7, 7, 7]

        print(f"Running {np}P experts baseline...")
        agg_b = run_batch(cfg_base, GAMES, np, start_seed=1)
        print(f"Running {np}P experts + Peanut...")
        agg_p = run_batch(cfg_pnut, GAMES, np, start_seed=1)

        side_by_side(f"{np}P Experts: Baseline vs Poisoned Peanut",
                     extract(agg_b), extract(agg_p))

        if np >= 3:
            print_poison_detail(f"{np}P + Peanut", agg_p)

    # ---- Test 2: 4P Styles showdown ----
    styles = [
        {"skill": 1.0, "style": "rush", "aggression": 0.5},
        {"skill": 1.0, "style": "balanced", "aggression": 0.5},
        {"skill": 1.0, "style": "hoarder", "aggression": 0.5},
        {"skill": 1.0, "style": "aggressive", "aggression": 0.5},
    ]

    print(f"\nRunning 4P styles baseline...")
    agg_sb = run_batch(v15_base, GAMES, 4, start_seed=1, player_configs=styles)
    print(f"Running 4P styles + Peanut...")
    agg_sp = run_batch(v15_peanut, GAMES, 4, start_seed=1, player_configs=styles)

    side_by_side("4P Styles: Baseline vs Poisoned Peanut", extract(agg_sb), extract(agg_sp))

    # Show style win rates
    print(f"\n  --- Style Win Rates ---")
    print(f"  {'Style':<12} {'Baseline':>10} {'+ Peanut':>10} {'Delta':>10}")
    print(f"  {'-'*12} {'-'*10} {'-'*10} {'-'*10}")
    style_names = ["rush", "balanced", "hoarder", "aggressive"]
    for i, sn in enumerate(style_names):
        bwr = agg_sb["win_rates"].get(i, 0)
        pwr = agg_sp["win_rates"].get(i, 0)
        d = pwr - bwr
        print(f"  {sn:<12} {bwr:>9.1%} {pwr:>9.1%} {d:>+9.1%}")

    print_poison_detail("4P Styles + Peanut", agg_sp)

    # ---- Test 3: Mixed skill ----
    mixed = [
        {"skill": 1.0, "style": "balanced", "aggression": 0.5},
        {"skill": 0.3, "style": "balanced", "aggression": 0.5},
        {"skill": 0.3, "style": "balanced", "aggression": 0.5},
        {"skill": 0.3, "style": "balanced", "aggression": 0.5},
    ]

    print(f"\nRunning 4P mixed skill baseline...")
    agg_mb = run_batch(v15_base, GAMES, 4, start_seed=1, player_configs=mixed)
    print(f"Running 4P mixed skill + Peanut...")
    agg_mp = run_batch(v15_peanut, GAMES, 4, start_seed=1, player_configs=mixed)

    side_by_side("4P Mixed Skill: Baseline vs Poisoned Peanut", extract(agg_mb), extract(agg_mp))
    print_poison_detail("4P Mixed + Peanut", agg_mp)

    print(f"\n{'='*75}")
    print(f"  COMPLETE — {GAMES * 12} total games")
    print(f"{'='*75}\n")
