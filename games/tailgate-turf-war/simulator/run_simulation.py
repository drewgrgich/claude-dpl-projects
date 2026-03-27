#!/usr/bin/env python3
"""
Batch simulation runner for Tailgate Turf War.

Run hundreds of AI-vs-AI games and collect balance metrics:
  - Win rate by player seat
  - Score distributions
  - Zone control patterns
  - Mishap frequency
  - Card-count-per-zone patterns
  - Hype value distributions
  - Bonus frequency (underdog, sweep, die-hard)

Usage:
  python run_simulation.py -n 500 -p 3
  python run_simulation.py -n 200 -p 4 --preset styles
  python run_simulation.py -n 100 --crew-bonus 3 --json results.json
"""

import argparse
import json
import math
import os
import sys
import statistics
from collections import defaultdict
from typing import List, Dict, Optional

# Add parent dir to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cards import Card, FACTIONS
from game_state import GameState
from ai_player import AIPlayer, STYLE_PROFILES


# ---------------------------------------------------------------------------
# Single game runner
# ---------------------------------------------------------------------------

def run_single_game(config: dict, num_players: int, seed: int,
                    player_configs: Optional[List[dict]] = None) -> dict:
    """Run one complete game, return stats dict."""
    game = GameState(config, num_players, seed=seed)

    # Create AIs
    ais: List[AIPlayer] = []
    for i in range(num_players):
        pc = player_configs[i] if player_configs and i < len(player_configs) else {}
        ais.append(AIPlayer(
            player_id=i,
            skill=pc.get("skill", config.get("ai_defaults", {}).get("skill", 1.0)),
            style=pc.get("style", config.get("ai_defaults", {}).get("style", "balanced")),
            aggression=pc.get("aggression", config.get("ai_defaults", {}).get("aggression", 0.5)),
            rng_seed=seed * 100 + i
        ))

    def deployment_fn(player, gs, round_num):
        ai = ais[player.id]
        return ai.choose_deployment_v2(player, gs, round_num)

    stats = game.play_game(deployment_fn)
    stats["log"] = game.log
    return stats


# ---------------------------------------------------------------------------
# Batch runner
# ---------------------------------------------------------------------------

def run_batch(config: dict, num_games: int, num_players: int,
              start_seed: int = 1,
              player_configs: Optional[List[dict]] = None) -> dict:
    """Run N games and aggregate statistics."""
    all_stats = []

    for i in range(num_games):
        seed = start_seed + i
        stats = run_single_game(config, num_players, seed, player_configs)
        all_stats.append(stats)

    return aggregate_stats(all_stats, num_players)


# ---------------------------------------------------------------------------
# Stats aggregation
# ---------------------------------------------------------------------------

def aggregate_stats(all_stats: List[dict], num_players: int) -> dict:
    """Aggregate stats across all games."""
    num_games = len(all_stats)

    # Win tracking
    wins = defaultdict(int)
    ties = 0

    # Score tracking
    all_scores = defaultdict(list)
    score_spreads = []

    # Zone wins
    total_zone_wins = defaultdict(int)
    zone_faction_wins = defaultdict(lambda: defaultdict(int))

    # Cards played
    cards_played = defaultdict(list)
    cards_remaining = defaultdict(list)
    hand_value_remaining = defaultdict(list)

    # Bonuses
    total_underdog = 0
    total_sweep = 0
    underdog_per_player = defaultdict(int)
    sweep_per_player = defaultdict(int)

    # Mishaps
    total_mishaps = defaultdict(int)

    # Hype values
    all_hype = []

    # Cards per zone play
    all_cards_per_zone = []

    for stats in all_stats:
        # Winner
        winner = stats["winner"]
        if isinstance(winner, list):
            ties += 1
            for w in winner:
                wins[w] += 0.5
        else:
            wins[winner] += 1

        # Scores
        for pid, score in stats["scores"].items():
            all_scores[pid].append(score)
        scores_list = list(stats["scores"].values())
        score_spreads.append(max(scores_list) - min(scores_list))

        # Zone wins
        for pid, zw in stats["zones_won"].items():
            total_zone_wins[pid] += zw

        for pid, fw in stats.get("zone_wins_by_faction", {}).items():
            for faction, count in fw.items():
                zone_faction_wins[pid][faction] += count

        # Cards
        for pid, cp in stats["cards_played"].items():
            cards_played[pid].append(cp)
        for pid, cr in stats["cards_remaining"].items():
            cards_remaining[pid].append(cr)
        for pid, hv in stats["hand_value_remaining"].items():
            hand_value_remaining[pid].append(hv)

        # Bonuses
        for pid, ub in stats["underdog_bonuses"].items():
            total_underdog += ub
            underdog_per_player[pid] += ub
        for pid, sb in stats["sweep_bonuses"].items():
            total_sweep += sb
            sweep_per_player[pid] += sb

        # Mishaps
        for faction, count in stats.get("mishap_triggers", {}).items():
            total_mishaps[faction] += count

        # Hype
        all_hype.extend(stats.get("hype_values", []))

        # Cards per zone
        all_cards_per_zone.extend(stats.get("cards_per_zone_play", []))

    # --- Compile aggregated results ---
    agg = {
        "num_games": num_games,
        "num_players": num_players,

        "win_rates": {pid: wins[pid] / num_games for pid in range(num_players)},
        "tie_rate": ties / num_games,

        "avg_scores": {pid: statistics.mean(scores)
                       for pid, scores in all_scores.items()},
        "score_stddev": {pid: statistics.stdev(scores) if len(scores) > 1 else 0
                         for pid, scores in all_scores.items()},
        "avg_score_spread": statistics.mean(score_spreads) if score_spreads else 0,

        "avg_zone_wins": {pid: total_zone_wins[pid] / num_games
                          for pid in range(num_players)},

        "avg_cards_played": {pid: statistics.mean(cp)
                             for pid, cp in cards_played.items()},
        "avg_cards_remaining": {pid: statistics.mean(cr)
                                for pid, cr in cards_remaining.items()},
        "avg_hand_value_remaining": {pid: statistics.mean(hv)
                                     for pid, hv in hand_value_remaining.items()},

        "underdog_per_game": total_underdog / num_games,
        "sweep_per_game": total_sweep / num_games,
        "underdog_per_player": {pid: underdog_per_player[pid] / num_games
                                for pid in range(num_players)},
        "sweep_per_player": {pid: sweep_per_player[pid] / num_games
                             for pid in range(num_players)},

        "mishap_frequency": {f: total_mishaps[f] / num_games for f in FACTIONS},

        "hype_stats": {
            "mean": statistics.mean(all_hype) if all_hype else 0,
            "median": statistics.median(all_hype) if all_hype else 0,
            "stdev": statistics.stdev(all_hype) if len(all_hype) > 1 else 0,
            "min": min(all_hype) if all_hype else 0,
            "max": max(all_hype) if all_hype else 0,
        },

        "cards_per_zone_stats": {
            "mean": statistics.mean(all_cards_per_zone) if all_cards_per_zone else 0,
            "distribution": _distribution(all_cards_per_zone, range(1, 7)),
        },

        "zone_faction_wins": {
            f: sum(zone_faction_wins[pid].get(f, 0)
                   for pid in range(num_players)) / num_games
            for f in FACTIONS
        },
    }

    return agg


def _distribution(values: list, buckets) -> dict:
    """Count occurrences of each bucket value."""
    counts = defaultdict(int)
    for v in values:
        counts[v] += 1
    total = len(values) if values else 1
    return {str(b): counts[b] / total for b in buckets}


# ---------------------------------------------------------------------------
# Report printer
# ---------------------------------------------------------------------------

def print_report(agg: dict, player_configs: Optional[List[dict]] = None):
    """Print a formatted simulation report."""
    n = agg["num_games"]
    p = agg["num_players"]

    print(f"\n{'='*60}")
    print(f"  TAILGATE TURF WAR — SIMULATION REPORT")
    print(f"  {n} games, {p} players")
    if player_configs:
        for i, pc in enumerate(player_configs):
            style = pc.get('style', 'balanced')
            skill = pc.get('skill', 1.0)
            print(f"    P{i}: {style} (skill={skill:.1f})")
    print(f"{'='*60}")

    # --- Win Rates ---
    print(f"\n--- Win Rates (by seat position) ---")
    for pid in range(p):
        rate = agg["win_rates"][pid]
        bar = "█" * int(rate * 50)
        expected = 1.0 / p
        delta = rate - expected
        flag = " ⚠️" if abs(delta) > 0.08 else ""
        print(f"  P{pid}: {rate:6.1%}  {bar}{flag}")
    print(f"  Tie rate: {agg['tie_rate']:.1%}")

    fair_rate = 1.0 / p
    max_deviation = max(abs(agg["win_rates"][pid] - fair_rate) for pid in range(p))
    print(f"  Max deviation from fair ({fair_rate:.1%}): {max_deviation:.1%}")

    # --- Scores ---
    print(f"\n--- Score Distribution ---")
    for pid in range(p):
        avg = agg["avg_scores"][pid]
        std = agg["score_stddev"][pid]
        print(f"  P{pid}: avg={avg:.1f} ± {std:.1f}")
    print(f"  Avg score spread (winner - loser): {agg['avg_score_spread']:.1f}")

    # --- Zone Control ---
    print(f"\n--- Zone Control ---")
    for pid in range(p):
        avg_zw = agg["avg_zone_wins"][pid]
        print(f"  P{pid}: {avg_zw:.1f} zones/game")

    print(f"\n  Zone contestedness (avg wins per zone per game):")
    for f in FACTIONS:
        wins_per_game = agg["zone_faction_wins"][f]
        print(f"    {f:8s}: {wins_per_game:.2f}")

    # --- Cards & Economy ---
    print(f"\n--- Card Economy ---")
    for pid in range(p):
        played = agg["avg_cards_played"][pid]
        remaining = agg["avg_cards_remaining"][pid]
        hand_val = agg["avg_hand_value_remaining"][pid]
        print(f"  P{pid}: played={played:.1f}, saved={remaining:.1f}, "
              f"saved_value={hand_val:.1f}")

    # --- Cards Per Zone ---
    print(f"\n--- Cards Per Zone Play ---")
    print(f"  Mean: {agg['cards_per_zone_stats']['mean']:.2f}")
    dist = agg["cards_per_zone_stats"]["distribution"]
    for k in sorted(dist.keys(), key=int):
        pct = dist[k]
        bar = "█" * int(pct * 40)
        print(f"    {k} card(s): {pct:5.1%} {bar}")

    # --- Hype Values ---
    print(f"\n--- Hype Distribution ---")
    hs = agg["hype_stats"]
    print(f"  Mean: {hs['mean']:.1f}, Median: {hs['median']:.0f}, "
          f"StdDev: {hs['stdev']:.1f}")
    print(f"  Range: {hs['min']:.0f} – {hs['max']:.0f}")

    # --- Mishaps ---
    print(f"\n--- Mishap Triggers (per game) ---")
    for f in FACTIONS:
        freq = agg["mishap_frequency"][f]
        bar = "█" * int(freq * 10)
        print(f"  {f:8s}: {freq:.2f} {bar}")

    # --- Bonuses ---
    print(f"\n--- Bonus Frequency (per game) ---")
    print(f"  Underdog: {agg['underdog_per_game']:.2f}")
    print(f"  Sweep:    {agg['sweep_per_game']:.2f}")

    # --- Warnings ---
    print(f"\n--- Balance Warnings ---")
    warnings = []

    # Check seat advantage
    for pid in range(p):
        rate = agg["win_rates"][pid]
        if rate > fair_rate + 0.08:
            warnings.append(f"⚠️  P{pid} (seat {pid}) wins {rate:.1%} "
                            f"— possible seat advantage")
        elif rate < fair_rate - 0.08:
            warnings.append(f"⚠️  P{pid} (seat {pid}) wins only {rate:.1%} "
                            f"— possible seat disadvantage")

    # Check if a zone is never contested
    for f in FACTIONS:
        if agg["zone_faction_wins"][f] < 0.5:
            warnings.append(f"⚠️  {f} zone is rarely won (avg {agg['zone_faction_wins'][f]:.2f}/game)")

    # Check score spread
    if agg["avg_score_spread"] > 20:
        warnings.append(f"⚠️  High score spread ({agg['avg_score_spread']:.1f}) — "
                        f"games may feel non-competitive")

    # Check underdog frequency
    if agg["underdog_per_game"] < 0.1:
        warnings.append("⚠️  Underdog bonus rarely triggers — "
                         "may need adjustment")
    if agg["underdog_per_game"] > 3.0:
        warnings.append("⚠️  Underdog bonus triggers very often — "
                         "single-card play may be too dominant")

    if agg["sweep_per_game"] > 1.5:
        warnings.append("⚠️  Sweep bonus triggers very often — "
                         "spread strategy may be too strong")

    if not warnings:
        warnings.append("✅ No major balance warnings detected")

    for w in warnings:
        print(f"  {w}")

    print(f"\n{'='*60}\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def load_config(config_path: Optional[str] = None) -> dict:
    """Load config.json from default or specified path."""
    if config_path:
        path = config_path
    else:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        path = os.path.join(script_dir, "config.json")

    with open(path, 'r') as f:
        return json.load(f)


def build_player_configs(args, num_players: int) -> Optional[List[dict]]:
    """Build player configuration from CLI arguments."""
    configs = None

    if args.preset:
        if args.preset == "experts":
            configs = [{"skill": 1.0, "style": "balanced"} for _ in range(num_players)]
        elif args.preset == "beginners":
            configs = [{"skill": 0.3, "style": "balanced"} for _ in range(num_players)]
        elif args.preset == "mixed":
            configs = [{"skill": 1.0, "style": "balanced"}]
            configs += [{"skill": 0.3, "style": "balanced"} for _ in range(num_players - 1)]
        elif args.preset == "styles":
            style_list = list(STYLE_PROFILES.keys())
            configs = [{"skill": 1.0, "style": style_list[i % len(style_list)]}
                       for i in range(num_players)]
        elif args.preset == "aggression":
            agg_levels = [0.2, 0.5, 0.8, 1.0, 0.0]
            configs = [{"skill": 1.0, "style": "balanced",
                        "aggression": agg_levels[i % len(agg_levels)]}
                       for i in range(num_players)]

    if args.skill:
        if configs is None:
            configs = [{} for _ in range(num_players)]
        skills = [float(s) for s in args.skill.split(",")]
        for i, s in enumerate(skills):
            if i < len(configs):
                configs[i]["skill"] = s

    if args.styles:
        if configs is None:
            configs = [{} for _ in range(num_players)]
        styles = args.styles.split(",")
        for i, s in enumerate(styles):
            if i < len(configs):
                configs[i]["style"] = s.strip()

    return configs


def main():
    parser = argparse.ArgumentParser(
        description="Tailgate Turf War — Batch Simulation Runner"
    )
    parser.add_argument("-n", "--num-games", type=int, default=500,
                        help="Number of games to simulate (default: 500)")
    parser.add_argument("-p", "--players", type=int, default=3,
                        help="Number of players (2-5, default: 3)")
    parser.add_argument("-s", "--seed", type=int, default=1,
                        help="Starting random seed (default: 1)")
    parser.add_argument("--config", type=str, default=None,
                        help="Path to config.json")
    parser.add_argument("--json", type=str, default=None,
                        help="Export results to JSON file")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Print game logs")

    # Player configuration
    parser.add_argument("--skill", type=str, default=None,
                        help="Comma-separated skill levels (e.g., '1.0,0.5,0.3')")
    parser.add_argument("--styles", type=str, default=None,
                        help="Comma-separated play styles (e.g., 'aggressive,sniper,hoarder')")
    parser.add_argument("--preset", type=str, default=None,
                        choices=["experts", "beginners", "mixed", "styles", "aggression"],
                        help="Preset player configurations")

    # Rule overrides
    parser.add_argument("--crew-bonus", type=int, default=None,
                        help="Override Crew bonus (default: 2)")
    parser.add_argument("--yellow-crew-bonus", type=int, default=None,
                        help="Override Yellow Crew bonus (default: 4)")
    parser.add_argument("--underdog-vp", type=int, default=None,
                        help="Override Underdog bonus VP (default: 2)")
    parser.add_argument("--sweep-vp", type=int, default=None,
                        help="Override Sweep bonus VP (default: 3)")
    parser.add_argument("--sweep-threshold", type=int, default=None,
                        help="Override Sweep zone threshold (default: 3)")
    parser.add_argument("--diehard-vp", type=int, default=None,
                        help="Override Die-Hard Fan VP (default: 5)")
    parser.add_argument("--mult-2", type=float, default=None,
                        help="Override 2-card multiplier (default: 0.8)")
    parser.add_argument("--mult-3", type=float, default=None,
                        help="Override 3-card multiplier (default: 0.6)")
    parser.add_argument("--mult-4", type=float, default=None,
                        help="Override 4+-card multiplier (default: 0.5)")
    parser.add_argument("--min-hype", type=int, default=None,
                        help="Minimum Hype to win a zone (default: 0)")

    args = parser.parse_args()

    # Validate
    if args.players < 2 or args.players > 5:
        print("Error: players must be 2-5")
        sys.exit(1)

    # Load config
    config = load_config(args.config)

    # Apply rule overrides
    rules = config["game_rules"]
    if args.crew_bonus is not None:
        rules["crew_bonus"] = args.crew_bonus
    if args.yellow_crew_bonus is not None:
        rules["yellow_crew_bonus"] = args.yellow_crew_bonus
    if args.underdog_vp is not None:
        rules["bonuses"]["underdog_vp"] = args.underdog_vp
    if args.sweep_vp is not None:
        rules["bonuses"]["sweep_vp"] = args.sweep_vp
    if args.sweep_threshold is not None:
        rules["bonuses"]["sweep_threshold"] = args.sweep_threshold
    if args.diehard_vp is not None:
        rules["bonuses"]["diehard_fan_vp"] = args.diehard_vp
    if args.mult_2 is not None:
        rules["hype_multipliers"]["2"] = args.mult_2
    if args.mult_3 is not None:
        rules["hype_multipliers"]["3"] = args.mult_3
    if args.mult_4 is not None:
        rules["hype_multipliers"]["4+"] = args.mult_4
    if args.min_hype is not None:
        rules["min_hype_threshold"] = args.min_hype

    # Build player configs
    player_configs = build_player_configs(args, args.players)

    # Run simulation
    print(f"Running {args.num_games} games with {args.players} players...")
    agg = run_batch(config, args.num_games, args.players,
                    start_seed=args.seed, player_configs=player_configs)

    # Print report
    print_report(agg, player_configs)

    # Export JSON
    if args.json:
        # Convert defaultdict and int keys for JSON serialization
        def make_serializable(obj):
            if isinstance(obj, defaultdict):
                return dict(obj)
            if isinstance(obj, dict):
                return {str(k): make_serializable(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [make_serializable(i) for i in obj]
            return obj

        with open(args.json, 'w') as f:
            json.dump(make_serializable(agg), f, indent=2)
        print(f"Results exported to {args.json}")


if __name__ == "__main__":
    main()
