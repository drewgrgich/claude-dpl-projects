#!/usr/bin/env python3
"""
Compare rank distributions for 56-card / 4-round decks.

All configs have exactly 56 cards: 11 number cards + 1 mascot + 1 action + 1 dud
per color × 4 colors. The difference is WHICH 11 ranks each color gets.

Distributions:
  D_flat:      0,1,2,3,4,5,6,7,8,9,10  — one of each (Config D baseline)
  D_bell:      1,2,3,4,4,5,5,6,6,7,8   — double 4,5,6; cut 0,9,10
  D_steep:     0,1,1,2,2,3,4,5,6,7,9   — double low; single high; cut 8,10
  D_topheavy:  1,3,5,6,7,7,8,8,9,9,10  — double 7,8,9; cut 0,2,4
  D_bookends:  0,0,1,1,3,5,7,9,9,10,10 — double extremes; thin middle
  D_pyramid:   0,1,2,3,4,5,6,7,8,9,9   — double 9 only; full range 0-9
  D_valley:    0,1,2,2,3,5,7,8,8,9,10  — double 2,8; gap at 4,6 (valley)

Each tested at 3P × 800 games + style matchup.
"""

import copy
import json
import math
import os
import statistics
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from run_simulation_v4 import run_batch, aggregate, run_style_matchup


def make_config_with_ranks(ranks_per_color, num_rounds=4):
    """Create config with specific ranks per color."""
    base_path = os.path.join(os.path.dirname(__file__), "config_v4.json")
    with open(base_path) as f:
        config = json.load(f)

    config["game_rules"]["ranks"] = ranks_per_color
    config["game_rules"]["num_rounds"] = num_rounds

    num_colors = 4
    specials_per_color = 3
    deck_size = num_colors * (len(ranks_per_color) + specials_per_color)

    total_deal_target = int(deck_size * 0.88)
    hand_sizes = {}
    for np in [2, 3, 4, 5]:
        hand = min(total_deal_target // np, deck_size // np)
        hand = max(hand, num_rounds * 2)
        hand_sizes[f"{np}_player"] = hand
    config["game_rules"]["hand_sizes"] = hand_sizes

    pass_counts = {}
    for np in [2, 3, 4, 5]:
        pc = max(1, round(hand_sizes[f"{np}_player"] * 0.17))
        pass_counts[f"{np}_player"] = pc
    config["game_rules"]["pass_count"] = pass_counts

    return config, deck_size


DISTRIBUTIONS = {
    "D_flat (0-10)": {
        "ranks": [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
        "desc": "One of each rank. Baseline.",
    },
    "D_bell (dbl 4,5,6)": {
        "ranks": [1, 2, 3, 4, 4, 5, 5, 6, 6, 7, 8],
        "desc": "Double mid-ranks. No extremes (0,9,10).",
    },
    "D_steep (dbl 1,2)": {
        "ranks": [0, 1, 1, 2, 2, 3, 4, 5, 6, 7, 9],
        "desc": "Lots of low cards. High cards rare. Cut 8,10.",
    },
    "D_topheavy (dbl 7,8,9)": {
        "ranks": [1, 3, 5, 6, 7, 7, 8, 8, 9, 9, 10],
        "desc": "Double high ranks. Cut 0,2,4.",
    },
    "D_bookends (dbl 0,1,9,10)": {
        "ranks": [0, 0, 1, 1, 3, 5, 7, 9, 9, 10, 10],
        "desc": "Double extremes. Thin middle.",
    },
    "D_pyramid (dbl 9)": {
        "ranks": [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 9],
        "desc": "Full range 0-9 + extra 9. Mild top boost.",
    },
    "D_valley (dbl 2,8)": {
        "ranks": [0, 1, 2, 2, 3, 5, 7, 8, 8, 9, 10],
        "desc": "Double 2 and 8. Gap at 4,6. Polarized mid.",
    },
}

GAMES = 800
STYLE_GAMES = 500
PLAYER_COUNTS = [3, 4, 5]


def rank_stats(ranks):
    """Descriptive stats for a rank list."""
    return {
        "mean": statistics.mean(ranks),
        "median": statistics.median(ranks),
        "stdev": statistics.stdev(ranks) if len(ranks) > 1 else 0,
        "min": min(ranks),
        "max": max(ranks),
        "unique": len(set(ranks)),
        "duplicates": len(ranks) - len(set(ranks)),
    }


def main():
    results = {}

    for name, spec in DISTRIBUTIONS.items():
        ranks = spec["ranks"]
        rs = rank_stats(ranks)
        config, deck_size = make_config_with_ranks(ranks)

        print(f"\n{'='*60}")
        print(f"  {name}")
        print(f"  {spec['desc']}")
        print(f"  Ranks: {ranks}")
        print(f"  Mean={rs['mean']:.1f} Med={rs['median']:.1f} "
              f"SD={rs['stdev']:.1f} Range={rs['min']}-{rs['max']} "
              f"Unique={rs['unique']} Dupes={rs['duplicates']}")
        print(f"  Deck: {deck_size}, Hand@3P: {config['game_rules']['hand_sizes']['3_player']}")
        print(f"{'='*60}")

        results[name] = {"spec": spec, "rank_stats": rs, "by_players": {}}

        for np in PLAYER_COUNTS:
            print(f"  {np}P: {GAMES} games...", end="", flush=True)
            try:
                batch = run_batch(GAMES, np, ["balanced"] * np, config=config)
                agg = aggregate(batch, np)

                style_data = None
                if np == 3:
                    style_data = run_style_matchup(STYLE_GAMES, np, config=config)

                results[name]["by_players"][np] = {"agg": agg, "style": style_data}

                spread = agg["avg_score_spread"]
                str_std = agg["strength_std"]
                print(f" spread={spread:.1f}, str_sd={str_std:.1f}, "
                      f"seat={agg['max_seat_deviation']:.1%}")
            except Exception as e:
                print(f" ERROR: {e}")
                results[name]["by_players"][np] = None

    # ── REPORT ──
    print("\n\n")
    print("=" * 100)
    print("  56-CARD DECK DISTRIBUTION COMPARISON (4 rounds)")
    print("=" * 100)

    for np in PLAYER_COUNTS:
        print(f"\n{'─'*100}")
        print(f"  {np} PLAYERS — {GAMES} games each")
        print(f"{'─'*100}")

        header = (f"{'Distribution':<26} {'RkMn':>4} {'RkSD':>4} "
                  f"{'AvgVP':>6} {'Spread':>6} {'SpMax':>5} "
                  f"{'Tie%':>5} {'SeatD':>5} "
                  f"{'StrMn':>5} {'StrSD':>5} {'StrMx':>5} "
                  f"{'CPZ':>4} {'HF/g':>5} {'Masc':>4} "
                  f"{'Emp%':>5} {'Unc%':>5}")
        print(header)
        print("-" * len(header))

        for name, data in results.items():
            pd = data["by_players"].get(np)
            if pd is None:
                continue
            agg = pd["agg"]
            rs = data["rank_stats"]

            cd = agg["contested_distribution"]
            total_zp = sum(cd.values()) if cd else 1
            empty_pct = cd.get(0, 0) / total_zp
            uncon_pct = cd.get(1, 0) / total_zp

            print(f"  {name:<24} {rs['mean']:>4.1f} {rs['stdev']:>4.1f} "
                  f"{agg['avg_score']:>6.1f} "
                  f"{agg['avg_score_spread']:>6.1f} "
                  f"{agg['score_spread_max']:>5} "
                  f"{agg['tie_rate']:>5.1%} "
                  f"{agg['max_seat_deviation']:>5.1%} "
                  f"{agg['strength_mean']:>5.1f} "
                  f"{agg['strength_std']:>5.1f} "
                  f"{agg['strength_max']:>5} "
                  f"{agg['cpz_mean']:>4.2f} "
                  f"{agg['hf_per_game']:>5.1f} "
                  f"{agg['mascot_per_game']:>4.1f} "
                  f"{empty_pct:>5.1%} "
                  f"{uncon_pct:>5.1%}")

    # Style matchup at 3P
    print(f"\n{'─'*100}")
    print("  STYLE MATCHUP (3P)")
    print(f"{'─'*100}")
    print(f"{'Distribution':<26} {'balanced':>9} {'aggress':>9} {'sniper':>9} "
          f"{'hoarder':>9} {'spread':>9} {'Range':>6} {'Dominant':>12}")
    print("-" * 100)

    for name, data in results.items():
        pd = data["by_players"].get(3)
        if pd is None or pd.get("style") is None:
            continue
        wr = pd["style"]["win_rates"]
        styles = ["balanced", "aggressive", "sniper", "hoarder", "spread"]
        vals = [wr.get(s, 0) for s in styles]
        spread = max(vals) - min(vals)
        dominant = styles[vals.index(max(vals))]
        weakest = styles[vals.index(min(vals))]
        val_strs = [f"{v:>9.1%}" for v in vals]
        flag = " ⚠️" if spread > 0.10 else ""
        print(f"  {name:<24} {''.join(val_strs)} {spread:>6.1%} {dominant:>12}{flag}")

    # Action cards at 3P
    print(f"\n{'─'*100}")
    print("  ACTION CARD IMPACT (3P)")
    print(f"{'─'*100}")
    print(f"{'Distribution':<26} {'ShSave':>7} {'BmKill':>7} {'SwUse':>7} "
          f"{'BnW':>5} {'BnF':>5} {'Bn%':>6} {'Duds':>6}")
    print("-" * 80)

    for name, data in results.items():
        pd = data["by_players"].get(3)
        if pd is None:
            continue
        agg = pd["agg"]
        print(f"  {name:<24} "
              f"{agg['shield_saves_per_game']:>7.2f} "
              f"{agg['bomb_kills_per_game']:>7.2f} "
              f"{agg['swap_uses_per_game']:>7.2f} "
              f"{agg['bounty_wins_per_game']:>5.2f} "
              f"{agg['bounty_fails_per_game']:>5.2f} "
              f"{agg['bounty_success_rate']:>6.1%} "
              f"{agg['dud_plays_per_game']:>6.2f}")

    # Strength percentile comparison at 3P
    print(f"\n{'─'*100}")
    print("  STRENGTH PERCENTILES (3P)")
    print(f"{'─'*100}")
    print(f"{'Distribution':<26} {'p10':>4} {'p25':>4} {'p50':>4} "
          f"{'p75':>4} {'p90':>4} {'Max':>4} {'Range':>5}")
    print("-" * 60)

    for name, data in results.items():
        pd = data["by_players"].get(3)
        if pd is None:
            continue
        agg = pd["agg"]
        rng = agg["strength_max"] - agg["strength_min"]
        print(f"  {name:<24} "
              f"{agg['strength_p10']:>4} {agg['strength_p25']:>4} "
              f"{agg['strength_p50']:>4} {agg['strength_p75']:>4} "
              f"{agg['strength_p90']:>4} {agg['strength_max']:>4} "
              f"{rng:>5}")

    # Health verdicts
    print(f"\n{'─'*100}")
    print("  HEALTH VERDICTS (3P)")
    print(f"{'─'*100}")

    for name, data in results.items():
        pd = data["by_players"].get(3)
        if pd is None:
            continue
        agg = pd["agg"]
        issues = []
        goods = []

        if agg["max_seat_deviation"] > 0.05:
            issues.append(f"seat {agg['max_seat_deviation']:.0%}")
        else:
            goods.append("fair seats")

        if agg["avg_score_spread"] > 25:
            issues.append(f"blowouts ({agg['avg_score_spread']:.0f})")
        elif agg["avg_score_spread"] < 8:
            issues.append(f"too flat ({agg['avg_score_spread']:.0f})")
        else:
            goods.append(f"spread {agg['avg_score_spread']:.0f}")

        cd = agg["contested_distribution"]
        total_zp = sum(cd.values()) if cd else 1
        empty_pct = cd.get(0, 0) / total_zp
        if empty_pct > 0.12:
            issues.append(f"empty {empty_pct:.0%}")
        else:
            goods.append(f"empty {empty_pct:.0%}")

        if agg["strength_std"] < 3.0:
            issues.append(f"low str variance (σ={agg['strength_std']:.1f})")
        elif agg["strength_std"] > 7.0:
            issues.append(f"high str variance (σ={agg['strength_std']:.1f})")
        else:
            goods.append(f"str σ={agg['strength_std']:.1f}")

        sd = pd.get("style")
        if sd:
            wr = sd["win_rates"]
            gap = max(wr.values()) - min(wr.values())
            if gap > 0.12:
                dom = max(wr, key=wr.get)
                issues.append(f"dominant: {dom} ({gap:.0%})")
            else:
                goods.append(f"style gap {gap:.0%}")

        # Bounty health
        br = agg["bounty_success_rate"]
        if br > 0.75:
            issues.append(f"bounty too safe ({br:.0%})")
        elif br < 0.25:
            issues.append(f"bounty too risky ({br:.0%})")
        else:
            goods.append(f"bounty {br:.0%}")

        verdict = "✅" if not issues else "⚠️"
        print(f"  {verdict} {name}")
        if goods:
            print(f"      ✅ {', '.join(goods)}")
        if issues:
            print(f"      ⚠️  {', '.join(issues)}")

    # RECOMMENDATION
    print(f"\n{'='*100}")
    print("  RECOMMENDATION")
    print(f"{'='*100}")

    # Score each distribution
    scores = {}
    for name, data in results.items():
        pd = data["by_players"].get(3)
        if pd is None:
            continue
        agg = pd["agg"]
        score = 0

        # Seat balance (lower deviation = better)
        score += max(0, 5 - agg["max_seat_deviation"] * 100)

        # Score spread (sweet spot 12-20)
        sp = agg["avg_score_spread"]
        if 12 <= sp <= 20:
            score += 5
        elif 10 <= sp <= 22:
            score += 3
        else:
            score += 1

        # Strength variance (sweet spot 4-6)
        sv = agg["strength_std"]
        if 4 <= sv <= 6:
            score += 5
        elif 3 <= sv <= 7:
            score += 3
        else:
            score += 1

        # Style balance (lower gap = better)
        sd = pd.get("style")
        if sd:
            gap = max(sd["win_rates"].values()) - min(sd["win_rates"].values())
            score += max(0, 5 - gap * 40)

        # Empty zones (lower = better)
        cd = agg["contested_distribution"]
        total_zp = sum(cd.values()) if cd else 1
        ep = cd.get(0, 0) / total_zp
        score += max(0, 5 - ep * 50)

        # Bounty balance (closer to 50% = better)
        br = agg["bounty_success_rate"]
        score += max(0, 5 - abs(br - 0.5) * 20)

        scores[name] = score

    ranked = sorted(scores.items(), key=lambda x: -x[1])
    for i, (name, sc) in enumerate(ranked):
        medal = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else "  "
        print(f"  {medal} {name:<26} score: {sc:.1f}")


if __name__ == "__main__":
    main()
