#!/usr/bin/env python3
"""
Compare round count × deck size configurations.

Tests multiple combinations to find the sweet spot for hand management tension,
zone contestation, and game feel.

Configurations:
  A: 48 cards (4×9 + specials), 3 rounds  — current baseline
  B: 48 cards (4×9 + specials), 4 rounds  — tighter hands, same deck
  C: 56 cards (4×10 + specials), 4 rounds — +1 rank per color (0-9)
  D: 60 cards (4×11 + specials), 4 rounds — +2 ranks (0-10), wider range
  E: 64 cards (4×12 + specials), 4 rounds — +3 ranks (0-11), big deck
  F: 56 cards (4×10 + specials), 3 rounds — bigger deck, same rounds

Each tested at 2, 3, 4, and 5 players × 500 games.
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


def make_config(ranks_list, num_rounds, label=""):
    """Create a config dict with custom ranks and round count."""
    base_path = os.path.join(os.path.dirname(__file__), "config_v4.json")
    with open(base_path) as f:
        config = json.load(f)

    config["game_rules"]["ranks"] = ranks_list
    config["game_rules"]["num_rounds"] = num_rounds

    # Recalculate hand sizes based on deck size
    num_colors = 4
    specials_per_color = 3  # mascot + action + dud
    deck_size = num_colors * (len(ranks_list) + specials_per_color)

    # Hand sizes: deal most of the deck, leave a small buffer
    # At 2P: ~70% of deck each is too many, cap reasonably
    # General rule: total dealt ≈ 85-90% of deck
    total_deal_target = int(deck_size * 0.88)

    hand_sizes = {}
    for np in [2, 3, 4, 5]:
        hand = total_deal_target // np
        # Ensure not more than deck_size // np
        hand = min(hand, deck_size // np)
        # Ensure at least num_rounds * 2 cards (minimum 2 per round)
        hand = max(hand, num_rounds * 2)
        hand_sizes[f"{np}_player"] = hand

    config["game_rules"]["hand_sizes"] = hand_sizes

    # Adjust pass count based on hand size
    pass_counts = {}
    for np in [2, 3, 4, 5]:
        hs = hand_sizes[f"{np}_player"]
        # Pass about 15-20% of hand
        pc = max(1, round(hs * 0.17))
        pass_counts[f"{np}_player"] = pc
    config["game_rules"]["pass_count"] = pass_counts

    return config, deck_size


CONFIGS = {
    "A: 48 cards / 3R (baseline)": {
        "ranks": list(range(1, 10)),   # 1-9
        "rounds": 3,
    },
    "B: 48 cards / 4R": {
        "ranks": list(range(1, 10)),   # 1-9
        "rounds": 4,
    },
    "C: 56 cards / 4R (0-9)": {
        "ranks": list(range(0, 10)),   # 0-9
        "rounds": 4,
    },
    "D: 60 cards / 4R (0-10)": {
        "ranks": list(range(0, 11)),   # 0-10
        "rounds": 4,
    },
    "E: 64 cards / 4R (0-11)": {
        "ranks": list(range(0, 12)),   # 0-11
        "rounds": 4,
    },
    "F: 56 cards / 3R (0-9)": {
        "ranks": list(range(0, 10)),   # 0-9
        "rounds": 3,
    },
}

PLAYER_COUNTS = [2, 3, 4, 5]
GAMES_PER = 500
STYLE_GAMES = 300


def main():
    results = {}

    for name, spec in CONFIGS.items():
        print(f"\n{'='*60}")
        print(f"  {name}")
        config, deck_size = make_config(spec["ranks"], spec["rounds"])
        hand_sizes = config["game_rules"]["hand_sizes"]
        print(f"  Deck: {deck_size} cards, Rounds: {spec['rounds']}")
        print(f"  Ranks: {spec['ranks']}")
        print(f"  Hand sizes: {hand_sizes}")
        print(f"  Pass counts: {config['game_rules']['pass_count']}")
        print(f"{'='*60}")

        results[name] = {"deck_size": deck_size, "spec": spec, "by_players": {}}

        for np in PLAYER_COUNTS:
            print(f"  {np}P: {GAMES_PER} games...", end="", flush=True)
            try:
                batch = run_batch(GAMES_PER, np,
                                  ["balanced"] * np,
                                  config=config)
                agg = aggregate(batch, np)

                # Style matchup at 3P only (the reference player count)
                style_data = None
                if np == 3:
                    style_data = run_style_matchup(STYLE_GAMES, np, config=config)

                results[name]["by_players"][np] = {
                    "agg": agg,
                    "style": style_data,
                    "hand_size": hand_sizes[f"{np}_player"],
                    "cards_per_round": hand_sizes[f"{np}_player"] / spec["rounds"],
                }
                spread = agg["avg_score_spread"]
                cpz = agg["cpz_mean"]
                print(f" spread={spread:.1f}, cpz={cpz:.2f}, "
                      f"seat_dev={agg['max_seat_deviation']:.1%}")
            except Exception as e:
                print(f" ERROR: {e}")
                results[name]["by_players"][np] = None

    # ── REPORT ──
    print("\n\n")
    print("=" * 90)
    print("  ROUNDS × DECK SIZE COMPARISON REPORT")
    print("=" * 90)

    # Summary table per player count
    for np in PLAYER_COUNTS:
        print(f"\n{'─'*90}")
        print(f"  {np} PLAYERS")
        print(f"{'─'*90}")

        header = (f"{'Config':<28} {'Deck':>4} {'R':>1} {'Hand':>4} "
                  f"{'C/R':>4} {'AvgVP':>6} {'Spread':>6} {'Tie%':>5} "
                  f"{'SeatD':>5} {'CPZ':>4} {'HF/g':>5} {'Masc':>4} "
                  f"{'StrM':>5} {'StrS':>5} {'Empty%':>6} {'Uncon%':>6}")
        print(header)
        print("-" * len(header))

        for name, data in results.items():
            pd = data["by_players"].get(np)
            if pd is None:
                print(f"  {name:<26} — ERROR —")
                continue

            agg = pd["agg"]
            spec = data["spec"]
            ds = data["deck_size"]
            hs = pd["hand_size"]
            cpr = pd["cards_per_round"]

            # Calculate empty and uncontested %
            cd = agg["contested_distribution"]
            total_zp = sum(cd.values()) if cd else 1
            empty_pct = cd.get(0, 0) / total_zp
            uncon_pct = cd.get(1, 0) / total_zp

            print(f"  {name:<26} {ds:>4} {spec['rounds']:>1} {hs:>4} "
                  f"{cpr:>4.1f} {agg['avg_score']:>6.1f} "
                  f"{agg['avg_score_spread']:>6.1f} "
                  f"{agg['tie_rate']:>5.1%} "
                  f"{agg['max_seat_deviation']:>5.1%} "
                  f"{agg['cpz_mean']:>4.2f} "
                  f"{agg['hf_per_game']:>5.1f} "
                  f"{agg['mascot_per_game']:>4.1f} "
                  f"{agg['strength_mean']:>5.1f} "
                  f"{agg['strength_std']:>5.1f} "
                  f"{empty_pct:>6.1%} "
                  f"{uncon_pct:>6.1%}")

    # Style matchup at 3P
    print(f"\n{'─'*90}")
    print("  STYLE MATCHUP (3 players)")
    print(f"{'─'*90}")

    header = f"{'Config':<28} ", " ".join(f"{'  ' + s:>11}" for s in STYLE_PROFILES_NAMES())
    print(f"{'Config':<28} {'balanced':>10} {'aggress.':>10} {'sniper':>10} {'hoarder':>10} {'spread':>10} {'Range':>6}")
    print("-" * 96)

    for name, data in results.items():
        pd = data["by_players"].get(3)
        if pd is None or pd.get("style") is None:
            continue
        sd = pd["style"]
        wr = sd["win_rates"]
        styles = ["balanced", "aggressive", "sniper", "hoarder", "spread"]
        vals = [wr.get(s, 0) for s in styles]
        spread = max(vals) - min(vals)
        val_strs = [f"{v:>10.1%}" for v in vals]
        print(f"  {name:<26} {''.join(val_strs)} {spread:>6.1%}")

    # Action card comparison at 3P
    print(f"\n{'─'*90}")
    print("  ACTION CARD IMPACT (3 players)")
    print(f"{'─'*90}")

    print(f"{'Config':<28} {'Shield':>7} {'Bomb':>7} {'Swap':>7} {'Bounty':>7} "
          f"{'ShSave':>7} {'BmKill':>7} {'BnWin%':>7} {'Duds':>7}")
    print("-" * 96)

    for name, data in results.items():
        pd = data["by_players"].get(3)
        if pd is None:
            continue
        agg = pd["agg"]
        ap = agg["action_plays_per_game"]
        bn_total = agg["bounty_wins_per_game"] + agg["bounty_fails_per_game"]
        bn_pct = agg["bounty_success_rate"]
        print(f"  {name:<26} "
              f"{ap.get('shield', 0):>7.2f} "
              f"{ap.get('bomb', 0):>7.2f} "
              f"{ap.get('swap', 0):>7.2f} "
              f"{ap.get('bounty', 0):>7.2f} "
              f"{agg['shield_saves_per_game']:>7.2f} "
              f"{agg['bomb_kills_per_game']:>7.2f} "
              f"{bn_pct:>7.1%} "
              f"{agg['dud_plays_per_game']:>7.2f}")

    # Health verdicts
    print(f"\n{'─'*90}")
    print("  HEALTH VERDICTS (3 players)")
    print(f"{'─'*90}")

    for name, data in results.items():
        pd = data["by_players"].get(3)
        if pd is None:
            continue
        agg = pd["agg"]
        spec = data["spec"]
        hs = pd["hand_size"]
        cpr = pd["cards_per_round"]

        cd = agg["contested_distribution"]
        total_zp = sum(cd.values()) if cd else 1
        empty_pct = cd.get(0, 0) / total_zp

        issues = []
        goods = []

        if agg["max_seat_deviation"] > 0.05:
            issues.append(f"seat dev {agg['max_seat_deviation']:.1%}")
        else:
            goods.append("fair seats")

        if agg["avg_score_spread"] > 25:
            issues.append(f"blowouts (spread {agg['avg_score_spread']:.1f})")
        elif agg["avg_score_spread"] < 5:
            issues.append(f"too close (spread {agg['avg_score_spread']:.1f})")
        else:
            goods.append(f"spread {agg['avg_score_spread']:.1f}")

        if empty_pct > 0.15:
            issues.append(f"too many empty zones ({empty_pct:.0%})")
        else:
            goods.append(f"empty {empty_pct:.0%}")

        if cpr < 2.5:
            issues.append(f"thin hands ({cpr:.1f} cards/round)")
        elif cpr > 5:
            issues.append(f"fat hands ({cpr:.1f} cards/round)")
        else:
            goods.append(f"{cpr:.1f} cards/round")

        if agg["tie_rate"] > 0.20:
            issues.append(f"high ties ({agg['tie_rate']:.0%})")
        else:
            goods.append(f"ties {agg['tie_rate']:.0%}")

        sd = pd.get("style")
        if sd:
            wr = sd["win_rates"]
            style_spread = max(wr.values()) - min(wr.values())
            if style_spread > 0.12:
                dominant = max(wr, key=wr.get)
                issues.append(f"dominant: {dominant} ({style_spread:.0%} gap)")
            else:
                goods.append(f"style spread {style_spread:.0%}")

        verdict = "✅" if not issues else "⚠️"
        good_str = ", ".join(goods)
        issue_str = ", ".join(issues)
        print(f"  {verdict} {name}")
        if goods:
            print(f"      ✅ {good_str}")
        if issues:
            print(f"      ⚠️  {issue_str}")


def STYLE_PROFILES_NAMES():
    return ["balanced", "aggressive", "sniper", "hoarder", "spread"]


if __name__ == "__main__":
    main()
