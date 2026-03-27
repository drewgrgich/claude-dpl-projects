#!/usr/bin/env python3
"""The Drop — Championship Mode for The Merch Stand Mob.

Plays 4-6 rounds of the core game with 6-card hands.
Players accumulate Heat (penalty points) based on finish position.
Championship ends when any player hits 15+ Heat. Lowest Heat wins.
"""

import argparse
import json
import os
import sys
from collections import defaultdict
from typing import List, Dict, Optional

from cards import Card, build_full_deck, FACTION_COLORS
from game_state import GameState, Bid, Player, load_config
from ai_player import HeuristicAI, STYLE_PROFILES
from run_simulation import run_single_game


# ─── SINGLE CHAMPIONSHIP ─────────────────────────────────────

def run_single_championship(config: dict, num_players: int, seed: int,
                            max_rounds: int = 6, max_turns_per_game: int = 30,
                            player_configs: List[dict] = None) -> dict:
    """Run one full Drop championship (multiple games).

    Returns championship stats including Heat progression and final standings.
    """
    drop_config = config["the_drop"]
    heat_table = drop_config["heat_by_finish"]
    # Use player-count-scaled boiling point if available, else fallback
    bp_by_players = drop_config.get("boiling_point_by_players", {})
    boiling_point = bp_by_players.get(str(num_players),
                                       drop_config.get("boiling_point", 15))

    # Track Heat per player
    heat = {i: 0 for i in range(num_players)}
    round_results = []

    for game_num in range(max_rounds):
        # Override hand size for The Drop
        drop_game_config = json.loads(json.dumps(config))  # Deep copy
        for key in drop_game_config["game_rules"]["hand_size"]:
            drop_game_config["game_rules"]["hand_size"][key] = drop_config["hand_size"]

        # Run one game
        game_seed = seed + game_num * 100
        result = run_single_game(
            drop_game_config, num_players, game_seed,
            max_turns=max_turns_per_game,
            player_configs=player_configs
        )

        # Assign Heat based on finish position
        scores = result["scores"]
        round_heat = {}
        for s in scores:
            pid = s["player_id"]
            pos = s["finish_position"]
            h = heat_table.get(str(pos), 10)  # Default 10 for positions beyond table
            heat[pid] += h
            round_heat[pid] = h

        round_results.append({
            "game_num": game_num + 1,
            "seed": game_seed,
            "scores": scores,
            "heat_awarded": round_heat,
            "heat_totals": dict(heat),
            "rounds": result["rounds"],
            "trample_count": result["trample_count"],
        })

        # Check boiling point
        if any(h >= boiling_point for h in heat.values()):
            break

    # Final standings: lowest Heat wins
    standings = sorted(heat.items(), key=lambda x: x[1])

    # Tiebreaker: most 1st-place finishes
    first_place_counts = defaultdict(int)
    best_vp = defaultdict(int)
    for rr in round_results:
        for s in rr["scores"]:
            if s["finish_position"] == 1:
                first_place_counts[s["player_id"]] += 1
            best_vp[s["player_id"]] = max(best_vp[s["player_id"]], s["total_vp"])

    return {
        "seed": seed,
        "num_players": num_players,
        "games_played": len(round_results),
        "round_results": round_results,
        "final_heat": dict(heat),
        "standings": standings,
        "champion": standings[0][0],
        "first_place_counts": dict(first_place_counts),
        "best_vp": dict(best_vp),
        "boiling_point_reached": any(h >= boiling_point for h in heat.values()),
    }


# ─── BATCH CHAMPIONSHIP RUNNER ────────────────────────────────

def run_batch_championships(config: dict, num_championships: int,
                            num_players: int, start_seed: int = 1,
                            player_configs: List[dict] = None,
                            verbose: bool = False) -> dict:
    """Run N championships and aggregate."""
    all_results = []

    for i in range(num_championships):
        seed = start_seed + i * 1000
        result = run_single_championship(
            config, num_players, seed,
            player_configs=player_configs
        )
        all_results.append(result)

        if verbose and (i + 1) % 10 == 0:
            print(f"  ... completed {i + 1}/{num_championships} championships")

    return aggregate_championship_stats(all_results, num_players)


def aggregate_championship_stats(all_results: List[dict], num_players: int) -> dict:
    """Aggregate championship statistics."""
    n = len(all_results)
    if n == 0:
        return {}

    agg = {
        "num_championships": n,
        "num_players": num_players,
    }

    # Games per championship
    games = [r["games_played"] for r in all_results]
    agg["avg_games_per_championship"] = sum(games) / n
    agg["min_games"] = min(games)
    agg["max_games"] = max(games)

    # Championship win rates
    wins = defaultdict(int)
    for r in all_results:
        wins[r["champion"]] += 1
    agg["championship_win_rates"] = {pid: wins[pid] / n for pid in range(num_players)}

    # Heat distribution
    all_heat = defaultdict(list)
    for r in all_results:
        for pid, h in r["final_heat"].items():
            all_heat[pid].append(h)
    agg["avg_heat_by_player"] = {pid: sum(v) / len(v) for pid, v in all_heat.items()}

    # First-place counts
    all_firsts = defaultdict(list)
    for r in all_results:
        for pid in range(num_players):
            all_firsts[pid].append(r["first_place_counts"].get(pid, 0))
    agg["avg_first_places"] = {pid: sum(v) / len(v) for pid, v in all_firsts.items()}

    # Boiling point rate
    agg["boiling_point_rate"] = sum(1 for r in all_results if r["boiling_point_reached"]) / n

    return agg


# ─── REPORT PRINTER ───────────────────────────────────────────

def print_drop_report(agg: dict, player_configs: List[dict] = None):
    """Print championship simulation report."""
    n = agg["num_championships"]
    np = agg["num_players"]

    print(f"\n{'='*65}")
    print(f"  THE DROP — CHAMPIONSHIP SIMULATION REPORT")
    print(f"  {n} championships, {np} players")
    print(f"{'='*65}")

    if player_configs:
        print(f"\n--- Player Setup ---")
        for i, pc in enumerate(player_configs):
            print(f"  P{i}: skill={pc.get('skill', 1.0):.1f}, "
                  f"style={pc.get('style', 'balanced')}, "
                  f"aggression={pc.get('aggression', 0.5):.1f}")

    print(f"\n--- Championship Length ---")
    print(f"  Avg games/championship: {agg['avg_games_per_championship']:.1f}")
    print(f"  Range: {agg['min_games']}–{agg['max_games']} games")
    print(f"  Boiling point reached: {agg['boiling_point_rate']:.1%}")

    print(f"\n--- Championship Win Rates ---")
    for pid in range(np):
        rate = agg["championship_win_rates"].get(pid, 0)
        expected = 1.0 / np
        delta = rate - expected
        indicator = "  " if abs(delta) < 0.05 else (" ▲" if delta > 0 else " ▼")
        style_label = ""
        if player_configs and pid < len(player_configs):
            style_label = f" ({player_configs[pid].get('style', 'balanced')})"
        print(f"  P{pid}{style_label}: {rate:.1%}{indicator}")

    print(f"\n--- Average Heat ---")
    for pid in range(np):
        avg_h = agg["avg_heat_by_player"].get(pid, 0)
        print(f"  P{pid}: {avg_h:.1f} Heat")

    print(f"\n--- First-Place Frequency ---")
    for pid in range(np):
        avg_f = agg["avg_first_places"].get(pid, 0)
        print(f"  P{pid}: {avg_f:.2f} 1st-places/championship")

    # Warnings
    print(f"\n{'='*65}")
    print(f"  HEALTH WARNINGS")
    print(f"{'='*65}")
    warnings = []

    win_rates = agg["championship_win_rates"]
    spread = max(win_rates.values()) - min(win_rates.values())
    if spread > 0.15:
        warnings.append(f"⚠  Championship win spread of {spread:.1%}")

    if agg["avg_games_per_championship"] < 4.0:
        warnings.append(f"⚠  Avg {agg['avg_games_per_championship']:.1f} games — "
                        f"championships end too quickly")

    if not warnings:
        print(f"  ✓ No major health issues!")
    else:
        for w in warnings:
            print(f"  {w}")
    print()


# ─── CLI ──────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="The Drop — Championship Simulation for The Merch Stand Mob"
    )
    parser.add_argument("-n", "--num-championships", type=int, default=50,
                       help="Number of championships to simulate (default: 50)")
    parser.add_argument("-p", "--players", type=int, default=4,
                       help="Number of players (3-5, default: 4)")
    parser.add_argument("-s", "--seed", type=int, default=1,
                       help="Starting random seed")
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--config", type=str, default=None)
    parser.add_argument("--json", type=str, default=None)
    parser.add_argument("--preset", type=str, default=None,
                       choices=["experts", "beginners", "mixed", "styles"])
    parser.add_argument("--skill", type=str, default=None)
    parser.add_argument("--styles", type=str, default=None)
    parser.add_argument("--aggression", type=str, default=None)

    args = parser.parse_args()

    config = load_config(args.config)

    # Build player configs
    num_players = args.players
    player_configs = [{"skill": 1.0, "style": "balanced", "aggression": 0.5}
                     for _ in range(num_players)]

    if args.preset == "styles":
        style_list = list(STYLE_PROFILES.keys())
        player_configs = [{"skill": 1.0, "style": style_list[i % len(style_list)],
                          "aggression": 0.5}
                         for i in range(num_players)]
    elif args.preset == "mixed":
        player_configs[0]["skill"] = 1.0
        for i in range(1, num_players):
            player_configs[i]["skill"] = 0.3
    elif args.preset == "beginners":
        for pc in player_configs:
            pc["skill"] = 0.3

    if args.skill:
        for i, s in enumerate(args.skill.split(",")):
            if i < len(player_configs):
                player_configs[i]["skill"] = float(s)
    if args.styles:
        for i, s in enumerate(args.styles.split(",")):
            if i < len(player_configs):
                player_configs[i]["style"] = s.strip()
    if args.aggression:
        for i, a in enumerate(args.aggression.split(",")):
            if i < len(player_configs):
                player_configs[i]["aggression"] = float(a)

    print(f"Running {args.num_championships} Drop championships "
          f"with {num_players} players...")
    agg = run_batch_championships(config, args.num_championships, num_players,
                                  start_seed=args.seed,
                                  player_configs=player_configs,
                                  verbose=args.verbose)
    print_drop_report(agg, player_configs)

    if args.json:
        with open(args.json, 'w') as f:
            json.dump(agg, f, indent=2, default=str)
        print(f"Stats exported to {args.json}")


if __name__ == "__main__":
    main()
