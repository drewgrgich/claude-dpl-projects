#!/usr/bin/env python3
"""
Condition card stress test for the Bookends 56-card / 4-round configuration.

For each condition, runs games where EVERY round uses that condition (forced),
then compares against a no-condition baseline. This isolates each condition's
impact on:
  - Stuck rate: % of players who can't legally play any cards
  - Zero rate: % of players who score 0 in the round
  - Avg playable cards: how many cards can the AI actually deploy?
  - Restriction bite: how much does the condition reduce playable options?
  - Score impact: does the condition change average VP per round?
  - Style disruption: does the condition favor/kill any particular style?
  - Fun factor: does the condition create interesting decisions or just frustration?

Tested at 2, 3, 4, and 5 players × 500 games each.
"""

import copy
import json
import math
import os
import statistics
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cards_v4 import (
    Card, COLORS, build_deck,
    CARD_TYPE_NUMBER, CARD_TYPE_MASCOT, CARD_TYPE_ACTION, CARD_TYPE_DUD,
)
from game_state_v4 import GameStateV4, Zone, ConditionCard
from ai_player_v4 import AIPlayerV4, STYLE_PROFILES

GAMES = 500
PLAYER_COUNTS = [2, 3, 4, 5]


def make_forced_config(condition_effect=None):
    """Load base config. If condition_effect given, we'll force it externally."""
    config_path = os.path.join(os.path.dirname(__file__), "config_v4.json")
    with open(config_path) as f:
        return json.load(f)


def run_condition_test(condition_name, condition_effect, category):
    """Run games forcing a specific condition every round. Return metrics."""
    config = make_forced_config()
    results = {}

    for np in PLAYER_COUNTS:
        stuck = 0
        zero_rounds = 0
        total_player_rounds = 0
        cards_played_per_round = []
        vp_per_round = []
        style_vp = defaultdict(list)

        for game_idx in range(GAMES):
            seed = game_idx + 1
            game = GameStateV4(np, seed=seed, config=config)

            styles = list(STYLE_PROFILES.keys())
            ais = [AIPlayerV4(pid, skill=1.0,
                               style=styles[pid % len(styles)],
                               rng_seed=seed * 100 + pid)
                   for pid in range(np)]

            # Card passing
            pass_selections = {}
            for player in game.players:
                ai = ais[player.id]
                to_pass = ai.choose_pass(player, game,
                                          game.rules["pass_count"][game.pkey])
                pass_selections[player.id] = to_pass

            def pass_fn(player, gs, count):
                return pass_selections[player.id]
            game.execute_pass(pass_fn)

            for round_num in range(game.num_rounds):
                game.current_round = round_num
                for p in game.players:
                    p.zones_won_this_round = 0

                # Force the condition
                if condition_effect:
                    game.active_condition = ConditionCard(
                        condition_name, category, condition_effect)
                else:
                    game.active_condition = None

                game.zones = [Zone(color=c, index=i)
                              for i, c in enumerate(COLORS)]

                scores_before = {p.id: p.score for p in game.players}

                for player in game.players:
                    ai = ais[player.id]
                    deploy = ai.choose_deployment(player, game, round_num)

                    all_cards = [c for cards in deploy.values() for c in cards]
                    total_player_rounds += 1
                    cards_played_per_round.append(len(all_cards))

                    # Check if stuck (wanted to play but couldn't)
                    if len(all_cards) == 0 and len(player.hand) > 0:
                        stuck += 1

                    # Validate deployment
                    if all_cards and not game.validate_deployment(deploy, player):
                        stuck += 1  # AI tried but failed validation

                    game._execute_deployment(player, deploy)

                game._resolve_actions()
                zone_strengths = game._calculate_all_strength()
                game._score_round(zone_strengths)

                for player in game.players:
                    vp_gained = player.score - scores_before[player.id]
                    vp_per_round.append(vp_gained)
                    if vp_gained == 0:
                        zero_rounds += 1
                    style = styles[player.id % len(styles)]
                    style_vp[style].append(vp_gained)

                game.active_condition = None

        results[np] = {
            "stuck_rate": stuck / max(1, total_player_rounds),
            "zero_rate": zero_rounds / max(1, total_player_rounds),
            "avg_cards_played": statistics.mean(cards_played_per_round) if cards_played_per_round else 0,
            "avg_vp_per_round": statistics.mean(vp_per_round) if vp_per_round else 0,
            "vp_std": statistics.stdev(vp_per_round) if len(vp_per_round) > 1 else 0,
            "style_avg_vp": {s: statistics.mean(v) if v else 0
                             for s, v in style_vp.items()},
            "total_player_rounds": total_player_rounds,
        }

    return results


def main():
    # All conditions from config
    config = make_forced_config()
    conditions = config["game_rules"]["condition_cards"]

    # Add baseline (no condition)
    all_tests = [{"name": "NO CONDITION (baseline)", "category": "none", "effect": None}]
    all_tests.extend(conditions)

    all_results = {}

    for cond in all_tests:
        name = cond["name"]
        effect = cond.get("effect")
        cat = cond.get("category", "none")
        print(f"  Testing: {name}...", end="", flush=True)
        results = run_condition_test(name, effect, cat)
        all_results[name] = {"spec": cond, "results": results}
        # Quick summary
        r3 = results[3]
        print(f" stuck={r3['stuck_rate']:.1%} zero={r3['zero_rate']:.1%} "
              f"cards={r3['avg_cards_played']:.1f} vp={r3['avg_vp_per_round']:.1f}")

    # Get baseline for comparison
    baseline = all_results["NO CONDITION (baseline)"]["results"]

    # ── REPORT ──
    print("\n")
    print("=" * 100)
    print("  CONDITION CARD STRESS TEST — Bookends 56-card / 4 rounds")
    print("=" * 100)

    for np in PLAYER_COUNTS:
        bl = baseline[np]
        print(f"\n{'─'*100}")
        print(f"  {np} PLAYERS — {GAMES} games each, condition forced every round")
        print(f"{'─'*100}")

        header = (f"{'Condition':<24} {'Cat':>6} {'Stuck%':>6} {'Zero%':>6} "
                  f"{'Cards':>5} {'Bite%':>5} {'VP/R':>5} {'VPΔ':>5} "
                  f"{'Status':>8}")
        print(header)
        print("-" * len(header))

        for name, data in all_results.items():
            r = data["results"][np]
            spec = data["spec"]
            cat = spec.get("category", "none")[:6]

            bite = 1.0 - (r["avg_cards_played"] / max(0.01, bl["avg_cards_played"]))
            vp_delta = r["avg_vp_per_round"] - bl["avg_vp_per_round"]

            # Status flags
            flags = []
            if r["stuck_rate"] > 0.15:
                flags.append("STUCK")
            if r["zero_rate"] > 0.50:
                flags.append("ZEROS")
            if bite > 0.60:
                flags.append("HARSH")
            if bite < 0.05 and spec.get("effect") and cat in ["card_r", "placem"]:
                flags.append("SOFT")

            status = " ".join(flags) if flags else "OK"
            marker = "⚠️ " if flags else "✅"

            print(f"  {marker}{name:<22} {cat:>6} {r['stuck_rate']:>6.1%} "
                  f"{r['zero_rate']:>6.1%} {r['avg_cards_played']:>5.1f} "
                  f"{bite:>5.0%} {r['avg_vp_per_round']:>5.1f} "
                  f"{vp_delta:>+5.1f} {status:>8}")

    # Style disruption at 3P
    print(f"\n{'─'*100}")
    print("  STYLE DISRUPTION (3P) — avg VP/round by style under each condition")
    print(f"{'─'*100}")

    styles = list(STYLE_PROFILES.keys())
    header = f"{'Condition':<24} " + " ".join(f"{s:>10}" for s in styles) + f" {'Range':>6}"
    print(header)
    print("-" * len(header))

    for name, data in all_results.items():
        r = data["results"][3]
        sv = r["style_avg_vp"]
        vals = [sv.get(s, 0) for s in styles]
        if not any(vals):
            continue
        spread = max(vals) - min(vals) if vals else 0
        val_strs = [f"{v:>10.1f}" for v in vals]
        flag = " ⚠️" if spread > 3 else ""
        print(f"  {name:<22} {''.join(val_strs)} {spread:>6.1f}{flag}")

    # Detailed verdicts
    print(f"\n{'─'*100}")
    print("  CONDITION VERDICTS")
    print(f"{'─'*100}")

    for name, data in all_results.items():
        if name == "NO CONDITION (baseline)":
            continue

        issues = []
        notes = []

        for np in PLAYER_COUNTS:
            r = data["results"][np]
            bl_r = baseline[np]
            bite = 1.0 - (r["avg_cards_played"] / max(0.01, bl_r["avg_cards_played"]))

            if r["stuck_rate"] > 0.15:
                issues.append(f"{np}P stuck {r['stuck_rate']:.0%}")
            if r["zero_rate"] > 0.50:
                issues.append(f"{np}P zero {r['zero_rate']:.0%}")
            if bite > 0.60:
                issues.append(f"{np}P too harsh (bite {bite:.0%})")
            if r["stuck_rate"] > 0.05 and np >= 4:
                notes.append(f"{np}P stuck {r['stuck_rate']:.0%}")

        # Style disruption at 3P
        sv = data["results"][3]["style_avg_vp"]
        vals = [sv.get(s, 0) for s in styles]
        if vals:
            spread = max(vals) - min(vals)
            if spread > 3:
                worst = styles[vals.index(min(vals))]
                issues.append(f"style disruption ({worst} hurt, range {spread:.1f})")

        if issues:
            print(f"  ⚠️  {name}")
            for i in issues:
                print(f"       {i}")
        elif notes:
            print(f"  ⚡ {name} — minor notes: {', '.join(notes)}")
        else:
            print(f"  ✅ {name} — clean at all player counts")


if __name__ == "__main__":
    main()
