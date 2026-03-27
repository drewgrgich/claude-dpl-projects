#!/usr/bin/env python3
"""
Batch simulation runner for Tailgate Turf War v3.0 (Streamlined Edition).

Usage:
  python run_simulation_v3.py -n 500 -p 3
  python run_simulation_v3.py -n 500 -p 5 --preset styles
  python run_simulation_v3.py -n 500 -p 3 --home-field 4 --extra-card 3
"""

import argparse
import json
import os
import sys
import statistics
from collections import defaultdict
from typing import List, Dict, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cards import FACTIONS
from game_state_v3 import GameStateV3
from ai_player_v3 import AIPlayerV3, STYLE_PROFILES


def run_single_game(num_players: int, seed: int,
                    player_configs: Optional[List[dict]] = None,
                    home_field_bonus: int = 3,
                    extra_card_bonus: int = 2) -> dict:
    game = GameStateV3(num_players, seed=seed,
                       home_field_bonus=home_field_bonus,
                       extra_card_bonus=extra_card_bonus)

    ais: List[AIPlayerV3] = []
    for i in range(num_players):
        pc = player_configs[i] if player_configs and i < len(player_configs) else {}
        ais.append(AIPlayerV3(
            player_id=i,
            skill=pc.get("skill", 1.0),
            style=pc.get("style", "balanced"),
            rng_seed=seed * 100 + i
        ))

    def deployment_fn(player, gs, round_num):
        return ais[player.id].choose_deployment(player, gs, round_num)

    stats = game.play_game(deployment_fn)
    return stats


def run_batch(num_games: int, num_players: int, start_seed: int = 1,
              player_configs: Optional[List[dict]] = None,
              home_field_bonus: int = 3,
              extra_card_bonus: int = 2) -> dict:
    all_stats = []
    for i in range(num_games):
        stats = run_single_game(num_players, start_seed + i, player_configs,
                                home_field_bonus, extra_card_bonus)
        all_stats.append(stats)
    return aggregate_stats(all_stats, num_players)


def aggregate_stats(all_stats: List[dict], num_players: int) -> dict:
    num_games = len(all_stats)
    wins = defaultdict(int)
    ties = 0
    all_scores = defaultdict(list)
    score_spreads = []
    total_zone_wins = defaultdict(int)
    zone_faction_wins = defaultdict(lambda: defaultdict(int))
    cards_played = defaultdict(list)
    cards_remaining = defaultdict(list)
    all_strength = []
    all_cards_per_zone = []
    total_home_field = 0
    total_mascot = 0

    for stats in all_stats:
        winner = stats["winner"]
        if isinstance(winner, list):
            ties += 1
            for w in winner:
                wins[w] += 0.5
        else:
            wins[winner] += 1

        for pid, score in stats["scores"].items():
            all_scores[pid].append(score)
        scores_list = list(stats["scores"].values())
        score_spreads.append(max(scores_list) - min(scores_list))

        for pid, zw in stats["zones_won"].items():
            total_zone_wins[pid] += zw

        for pid, fw in stats.get("zone_wins_by_faction", {}).items():
            for faction, count in fw.items():
                zone_faction_wins[pid][faction] += count

        for pid, cp in stats["cards_played"].items():
            cards_played[pid].append(cp)
        for pid, cr in stats["cards_remaining"].items():
            cards_remaining[pid].append(cr)

        all_strength.extend(stats.get("strength_values", []))
        all_cards_per_zone.extend(stats.get("cards_per_zone_play", []))
        total_home_field += stats.get("home_field_triggers", 0)
        total_mascot += stats.get("mascot_combos", 0)

    def dist(values, buckets):
        counts = defaultdict(int)
        for v in values:
            counts[v] += 1
        total = len(values) if values else 1
        return {str(b): counts[b] / total for b in buckets}

    fair_rate = 1.0 / num_players

    return {
        "num_games": num_games,
        "num_players": num_players,
        "win_rates": {pid: wins[pid] / num_games for pid in range(num_players)},
        "tie_rate": ties / num_games,
        "avg_scores": {pid: statistics.mean(s) for pid, s in all_scores.items()},
        "score_stddev": {pid: (statistics.stdev(s) if len(s) > 1 else 0)
                         for pid, s in all_scores.items()},
        "avg_score_spread": statistics.mean(score_spreads) if score_spreads else 0,
        "avg_zone_wins": {pid: total_zone_wins[pid] / num_games
                          for pid in range(num_players)},
        "avg_cards_played": {pid: statistics.mean(cp) for pid, cp in cards_played.items()},
        "avg_cards_remaining": {pid: statistics.mean(cr) for pid, cr in cards_remaining.items()},
        "strength_stats": {
            "mean": statistics.mean(all_strength) if all_strength else 0,
            "median": statistics.median(all_strength) if all_strength else 0,
            "stdev": statistics.stdev(all_strength) if len(all_strength) > 1 else 0,
            "min": min(all_strength) if all_strength else 0,
            "max": max(all_strength) if all_strength else 0,
        },
        "cards_per_zone_stats": {
            "mean": statistics.mean(all_cards_per_zone) if all_cards_per_zone else 0,
            "distribution": dist(all_cards_per_zone, range(1, 7)),
        },
        "zone_faction_wins": {
            f: sum(zone_faction_wins[pid].get(f, 0)
                   for pid in range(num_players)) / num_games
            for f in FACTIONS
        },
        "home_field_per_game": total_home_field / num_games,
        "mascot_combos_per_game": total_mascot / num_games,
    }


def print_report(agg: dict, player_configs: Optional[List[dict]] = None):
    n = agg["num_games"]
    p = agg["num_players"]

    print(f"\n{'='*60}")
    print(f"  TAILGATE TURF WAR v3.0 — SIMULATION REPORT")
    print(f"  {n} games, {p} players")
    if player_configs:
        for i, pc in enumerate(player_configs):
            print(f"    P{i}: {pc.get('style', 'balanced')} (skill={pc.get('skill', 1.0):.1f})")
    print(f"{'='*60}")

    # Win Rates
    print(f"\n--- Win Rates ---")
    fair = 1.0 / p
    for pid in range(p):
        rate = agg["win_rates"][pid]
        bar = "█" * int(rate * 50)
        delta = rate - fair
        flag = " ⚠️" if abs(delta) > 0.08 else ""
        print(f"  P{pid}: {rate:6.1%}  {bar}{flag}")
    print(f"  Tie rate: {agg['tie_rate']:.1%}")
    max_dev = max(abs(agg["win_rates"][pid] - fair) for pid in range(p))
    print(f"  Max seat deviation: {max_dev:.1%}")

    # Scores
    print(f"\n--- Scores ---")
    for pid in range(p):
        avg = agg["avg_scores"][pid]
        std = agg["score_stddev"][pid]
        print(f"  P{pid}: avg={avg:.1f} ± {std:.1f}")
    print(f"  Avg spread (winner-loser): {agg['avg_score_spread']:.1f}")

    # Zone Control
    print(f"\n--- Zone Control ---")
    for pid in range(p):
        print(f"  P{pid}: {agg['avg_zone_wins'][pid]:.1f} zones/game")

    print(f"\n  Wins per zone per game:")
    for f in FACTIONS:
        w = agg["zone_faction_wins"][f]
        print(f"    {f:8s}: {w:.2f}")

    # Cards
    print(f"\n--- Card Economy ---")
    for pid in range(p):
        played = agg["avg_cards_played"][pid]
        saved = agg["avg_cards_remaining"][pid]
        print(f"  P{pid}: played={played:.1f}, saved={saved:.1f}")

    # Cards per zone
    print(f"\n--- Cards Per Zone ---")
    print(f"  Mean: {agg['cards_per_zone_stats']['mean']:.2f}")
    d = agg["cards_per_zone_stats"]["distribution"]
    for k in sorted(d.keys(), key=int):
        pct = d[k]
        bar = "█" * int(pct * 40)
        print(f"    {k} card(s): {pct:5.1%} {bar}")

    # Strength
    print(f"\n--- Strength Distribution ---")
    ss = agg["strength_stats"]
    print(f"  Mean: {ss['mean']:.1f}, Median: {ss['median']:.0f}, StdDev: {ss['stdev']:.1f}")
    print(f"  Range: {ss['min']:.0f} – {ss['max']:.0f}")

    # Features
    print(f"\n--- Feature Usage ---")
    print(f"  Home Field triggers/game: {agg['home_field_per_game']:.1f}")
    print(f"  Mascot combos/game: {agg['mascot_combos_per_game']:.1f}")

    # Warnings
    print(f"\n--- Balance Warnings ---")
    warnings = []

    for pid in range(p):
        rate = agg["win_rates"][pid]
        if abs(rate - fair) > 0.08:
            warnings.append(f"⚠️  P{pid} wins {rate:.1%} (expected {fair:.1%})")

    for f in FACTIONS:
        if agg["zone_faction_wins"][f] < 0.5:
            warnings.append(f"⚠️  {f} zone rarely won ({agg['zone_faction_wins'][f]:.2f}/game)")

    if agg["avg_score_spread"] > 25:
        warnings.append(f"⚠️  High score spread ({agg['avg_score_spread']:.1f})")

    if not warnings:
        warnings.append("✅ No major balance warnings")

    for w in warnings:
        print(f"  {w}")

    print(f"\n{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(description="TTW v3.0 Simulation Runner")
    parser.add_argument("-n", "--num-games", type=int, default=500)
    parser.add_argument("-p", "--players", type=int, default=3)
    parser.add_argument("-s", "--seed", type=int, default=1)
    parser.add_argument("--preset", choices=["experts", "beginners", "mixed", "styles"])
    parser.add_argument("--styles", type=str, default=None,
                        help="Comma-separated styles")
    parser.add_argument("--home-field", type=int, default=3,
                        help="Home Field Advantage bonus (default: 3)")
    parser.add_argument("--extra-card", type=int, default=2,
                        help="Extra card bonus (default: 2)")
    parser.add_argument("--json", type=str, default=None)

    args = parser.parse_args()

    if args.players < 2 or args.players > 5:
        print("Error: players must be 2-5")
        sys.exit(1)

    # Build player configs
    player_configs = None
    if args.preset:
        style_list = list(STYLE_PROFILES.keys())
        if args.preset == "experts":
            player_configs = [{"skill": 1.0, "style": "balanced"} for _ in range(args.players)]
        elif args.preset == "beginners":
            player_configs = [{"skill": 0.3, "style": "balanced"} for _ in range(args.players)]
        elif args.preset == "mixed":
            player_configs = [{"skill": 1.0, "style": "balanced"}]
            player_configs += [{"skill": 0.3, "style": "balanced"} for _ in range(args.players - 1)]
        elif args.preset == "styles":
            player_configs = [{"skill": 1.0, "style": style_list[i % len(style_list)]}
                              for i in range(args.players)]

    if args.styles:
        if player_configs is None:
            player_configs = [{} for _ in range(args.players)]
        for i, s in enumerate(args.styles.split(",")):
            if i < len(player_configs):
                player_configs[i]["style"] = s.strip()

    print(f"Running {args.num_games} v3.0 games with {args.players} players "
          f"(home_field={args.home_field}, extra_card={args.extra_card})...")
    agg = run_batch(args.num_games, args.players, args.seed,
                    player_configs, args.home_field, args.extra_card)
    print_report(agg, player_configs)

    if args.json:
        def serialize(obj):
            if isinstance(obj, defaultdict):
                return dict(obj)
            if isinstance(obj, dict):
                return {str(k): serialize(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [serialize(i) for i in obj]
            return obj
        with open(args.json, 'w') as f:
            json.dump(serialize(agg), f, indent=2)
        print(f"Exported to {args.json}")


if __name__ == "__main__":
    main()
