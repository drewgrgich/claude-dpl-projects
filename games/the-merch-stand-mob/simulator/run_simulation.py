#!/usr/bin/env python3
"""Batch simulation runner for The Merch Stand Mob.

Runs N AI-vs-AI games and reports game health metrics:
win rates, game length, Trample frequency, scoring distribution,
Sneak/Shove dynamics, faction ability usage, and more.
"""

import argparse
import json
import os
import sys
from collections import defaultdict
from typing import List, Dict, Optional

from cards import Card, build_full_deck, FACTION_COLORS, FACTIONS
from game_state import GameState, Bid, Player, load_config
from ai_player import HeuristicAI, STYLE_PROFILES


# ─── SINGLE GAME RUNNER ──────────────────────────────────────

def run_single_game(config: dict, num_players: int, seed: int,
                    max_turns: int = 50,
                    player_configs: List[dict] = None) -> dict:
    """Run one complete game and return stats dict."""
    game = GameState(config, num_players, seed=seed)
    game.setup()

    # Create AIs
    ais = []
    for i in range(num_players):
        pc = player_configs[i] if player_configs and i < len(player_configs) else {}
        ais.append(HeuristicAI(
            player_id=i,
            skill=pc.get("skill", 1.0),
            style=pc.get("style", "balanced"),
            aggression=pc.get("aggression", 0.5),
            rng_seed=seed + i * 1000,
        ))

    # Track per-round stats
    round_stats = []

    while not game.game_over and game.round_number < max_turns:
        # All players choose bids simultaneously
        bids = []
        for i, player in enumerate(game.players):
            if player.hand:
                bid = ais[i].choose_bid(player, game)
                # Remove bid cards from hand
                player.hand.remove(bid.primary)
                if bid.anchor and bid.anchor in player.hand:
                    player.hand.remove(bid.anchor)
                bids.append(bid)

        if not bids:
            break

        # Execute round with AI ability callbacks
        def make_callback(ai_list):
            def callback(player, ability_type, gs, context):
                return ai_list[player.id].ability_callback(player, ability_type, gs, context)
            return callback

        result = game.play_round(bids, ability_callback=make_callback(ais))

        # Update AI sneak history
        sneak_occurred = result["sneaks"]["attempts"] > 0
        for ai in ais:
            ai.update_sneak_history(sneak_occurred)

        round_stats.append(result)

    # Compile stats
    scores = game.get_final_scores()
    winner_id = scores[0]["player_id"]

    return {
        "seed": seed,
        "num_players": num_players,
        "rounds": game.round_number,
        "winner": winner_id,
        "end_reason": game.end_reason,
        "scores": scores,
        "max_vp": scores[0]["total_vp"],
        "min_vp": scores[-1]["total_vp"],
        "vp_spread": scores[0]["total_vp"] - scores[-1]["total_vp"],
        "vp_by_player": {s["player_id"]: s["total_vp"] for s in scores},
        "card_vp_by_player": {s["player_id"]: s["card_vp"] for s in scores},
        "set_bonus_by_player": {s["player_id"]: s["set_bonus"] for s in scores},
        "unique_colors_by_player": {s["player_id"]: s["unique_colors"] for s in scores},
        "tramples": game.stats["tramples"],
        "trample_count": len(game.stats["tramples"]),
        "trampled_factions": [t[1] for t in game.stats["tramples"]],
        "cards_trampled": dict(game.stats["cards_trampled"]),
        "sneak_attempts": game.stats["sneak_attempts"],
        "sneak_successes": game.stats["sneak_successes"],
        "shove_count": game.stats["shove_count"],
        "ties": game.stats["ties"],
        "abilities_triggered": dict(game.stats["abilities_triggered"]),
        "claims_per_player": dict(game.stats["claims_per_player"]),
        "hit_max_turns": game.round_number >= max_turns,
    }


# ─── BATCH RUNNER ─────────────────────────────────────────────

def run_batch(config: dict, num_games: int, num_players: int,
              start_seed: int = 1, max_turns: int = 50,
              player_configs: List[dict] = None,
              verbose: bool = False) -> dict:
    """Run N games and aggregate statistics."""
    all_stats = []

    for i in range(num_games):
        seed = start_seed + i
        stats = run_single_game(config, num_players, seed,
                               max_turns=max_turns,
                               player_configs=player_configs)
        all_stats.append(stats)

        if verbose and (i + 1) % 50 == 0:
            print(f"  ... completed {i + 1}/{num_games} games")

    return aggregate_stats(all_stats, num_players)


def aggregate_stats(all_stats: List[dict], num_players: int) -> dict:
    """Aggregate statistics from multiple games."""
    n = len(all_stats)
    if n == 0:
        return {}

    agg = {
        "num_games": n,
        "num_players": num_players,
    }

    # ── Game Length ──
    rounds = [s["rounds"] for s in all_stats]
    agg["avg_rounds"] = sum(rounds) / n
    agg["min_rounds"] = min(rounds)
    agg["max_rounds"] = max(rounds)
    agg["median_rounds"] = sorted(rounds)[n // 2]
    agg["hit_max_turns_rate"] = sum(1 for s in all_stats if s["hit_max_turns"]) / n

    # ── End Reasons ──
    end_reasons = defaultdict(int)
    for s in all_stats:
        reason_type = "hand_empty" if "emptied" in s["end_reason"] else \
                      "supply_empty" if "Supply" in s["end_reason"] else "max_turns"
        end_reasons[reason_type] += 1
    agg["end_reasons"] = {k: v / n for k, v in end_reasons.items()}

    # ── Win Rates ──
    wins = defaultdict(int)
    for s in all_stats:
        wins[s["winner"]] += 1
    agg["win_rates"] = {pid: wins[pid] / n for pid in range(num_players)}
    agg["win_rate_spread"] = max(agg["win_rates"].values()) - min(agg["win_rates"].values())

    # ── Scoring ──
    all_vp = []
    for s in all_stats:
        for pid in range(num_players):
            all_vp.append(s["vp_by_player"].get(pid, 0))
    agg["avg_vp"] = sum(all_vp) / len(all_vp)
    agg["max_vp_seen"] = max(all_vp)
    agg["min_vp_seen"] = min(all_vp)

    # VP by player position
    agg["avg_vp_by_position"] = {}
    for pid in range(num_players):
        vps = [s["vp_by_player"].get(pid, 0) for s in all_stats]
        agg["avg_vp_by_position"][pid] = sum(vps) / len(vps)

    # VP spread
    spreads = [s["vp_spread"] for s in all_stats]
    agg["avg_vp_spread"] = sum(spreads) / n

    # Card VP vs Set Bonus breakdown
    all_card_vp = []
    all_set_bonus = []
    for s in all_stats:
        for pid in range(num_players):
            all_card_vp.append(s["card_vp_by_player"].get(pid, 0))
            all_set_bonus.append(s["set_bonus_by_player"].get(pid, 0))
    agg["avg_card_vp"] = sum(all_card_vp) / len(all_card_vp)
    agg["avg_set_bonus"] = sum(all_set_bonus) / len(all_set_bonus)

    # Set completion rates
    color_counts = defaultdict(int)
    for s in all_stats:
        for pid in range(num_players):
            colors = s["unique_colors_by_player"].get(pid, 0)
            color_counts[colors] += 1
    total_entries = n * num_players
    agg["color_distribution"] = {k: v / total_entries for k, v in sorted(color_counts.items())}
    agg["first_set_rate"] = sum(v for k, v in color_counts.items() if k >= 3) / total_entries
    agg["second_set_rate"] = sum(v for k, v in color_counts.items() if k >= 6) / total_entries

    # ── Trample ──
    tramples = [s["trample_count"] for s in all_stats]
    agg["avg_tramples"] = sum(tramples) / n
    agg["max_tramples"] = max(tramples)
    agg["zero_trample_rate"] = sum(1 for t in tramples if t == 0) / n

    # Trample by faction
    faction_tramples = defaultdict(int)
    for s in all_stats:
        for faction in s["trampled_factions"]:
            faction_tramples[faction] += 1
    agg["trample_by_faction"] = {f: faction_tramples.get(f, 0) / n for f in FACTION_COLORS}

    # Cards lost to Trample
    all_trampled = []
    for s in all_stats:
        total = sum(s["cards_trampled"].values())
        all_trampled.append(total)
    agg["avg_cards_trampled_per_game"] = sum(all_trampled) / n

    # ── Sneak / Shove ──
    sneak_attempts = [s["sneak_attempts"] for s in all_stats]
    sneak_successes = [s["sneak_successes"] for s in all_stats]
    shoves = [s["shove_count"] for s in all_stats]
    ties = [s["ties"] for s in all_stats]

    agg["avg_sneak_attempts"] = sum(sneak_attempts) / n
    agg["avg_sneak_successes"] = sum(sneak_successes) / n
    total_attempts = sum(sneak_attempts)
    agg["sneak_success_rate"] = sum(sneak_successes) / total_attempts if total_attempts > 0 else 0
    agg["avg_shoves"] = sum(shoves) / n
    agg["avg_ties"] = sum(ties) / n

    # ── Abilities ──
    ability_totals = defaultdict(int)
    for s in all_stats:
        for ability, count in s["abilities_triggered"].items():
            ability_totals[ability] += count
    agg["avg_abilities"] = {k: v / n for k, v in ability_totals.items()}

    # ── Claims per Player ──
    claims = defaultdict(list)
    for s in all_stats:
        for pid in range(num_players):
            claims[pid].append(s["claims_per_player"].get(pid, 0))
    agg["avg_claims_per_player"] = {pid: sum(v) / len(v) for pid, v in claims.items()}

    return agg


# ─── REPORT PRINTER ───────────────────────────────────────────

def print_report(agg: dict, player_configs: List[dict] = None):
    """Print a formatted simulation report."""
    n = agg["num_games"]
    np = agg["num_players"]

    print(f"\n{'='*65}")
    print(f"  THE MERCH STAND MOB — SIMULATION REPORT")
    print(f"  {n} games, {np} players")
    print(f"{'='*65}")

    # Player configs
    if player_configs:
        print(f"\n--- Player Setup ---")
        for i, pc in enumerate(player_configs):
            print(f"  P{i}: skill={pc.get('skill', 1.0):.1f}, "
                  f"style={pc.get('style', 'balanced')}, "
                  f"aggression={pc.get('aggression', 0.5):.1f}")

    # Game Length
    print(f"\n--- Game Length ---")
    print(f"  Average: {agg['avg_rounds']:.1f} rounds")
    print(f"  Range: {agg['min_rounds']}–{agg['max_rounds']} rounds")
    print(f"  Median: {agg['median_rounds']} rounds")
    if agg['hit_max_turns_rate'] > 0:
        print(f"  ⚠  Hit max turns: {agg['hit_max_turns_rate']:.1%}")

    # End Reasons
    print(f"\n--- End Reasons ---")
    for reason, rate in agg["end_reasons"].items():
        print(f"  {reason}: {rate:.1%}")

    # Win Rates
    print(f"\n--- Win Rates ---")
    for pid in range(np):
        rate = agg["win_rates"].get(pid, 0)
        expected = 1.0 / np
        delta = rate - expected
        indicator = "  " if abs(delta) < 0.05 else (" ▲" if delta > 0 else " ▼")
        style_label = ""
        if player_configs and pid < len(player_configs):
            style_label = f" ({player_configs[pid].get('style', 'balanced')})"
        print(f"  P{pid}{style_label}: {rate:.1%}{indicator}")
    print(f"  Spread: {agg['win_rate_spread']:.1%}")

    # Scoring
    print(f"\n--- Scoring ---")
    print(f"  Average VP: {agg['avg_vp']:.1f}")
    print(f"  Range: {agg['min_vp_seen']}–{agg['max_vp_seen']} VP")
    print(f"  Avg VP spread (winner vs last): {agg['avg_vp_spread']:.1f}")
    print(f"  Card VP: {agg['avg_card_vp']:.1f} | Set Bonus: {agg['avg_set_bonus']:.1f}")

    # VP by position
    print(f"\n  VP by seat:")
    for pid in range(np):
        vp = agg["avg_vp_by_position"].get(pid, 0)
        print(f"    P{pid}: {vp:.1f}")

    # Sets
    print(f"\n--- Set Completion ---")
    print(f"  1st set (3 colors) rate: {agg['first_set_rate']:.1%}")
    print(f"  2nd set (6 colors) rate: {agg['second_set_rate']:.1%}")
    print(f"  Color distribution:")
    for colors, rate in agg["color_distribution"].items():
        print(f"    {colors} colors: {rate:.1%}")

    # Trample
    print(f"\n--- Trample ---")
    print(f"  Avg tramples/game: {agg['avg_tramples']:.2f}")
    print(f"  Max in a game: {agg['max_tramples']}")
    print(f"  Zero-trample games: {agg['zero_trample_rate']:.1%}")
    print(f"  Avg cards lost/game: {agg['avg_cards_trampled_per_game']:.1f}")
    print(f"\n  By faction:")
    sorted_factions = sorted(agg["trample_by_faction"].items(), key=lambda x: -x[1])
    for faction, rate in sorted_factions:
        bar = "█" * int(rate * 40)
        print(f"    {faction:8s} {rate:.2f}/game {bar}")

    # Sneak / Shove
    print(f"\n--- Sneak & Shove Dynamics ---")
    print(f"  Avg Sneak attempts/game: {agg['avg_sneak_attempts']:.1f}")
    print(f"  Avg Sneak successes/game: {agg['avg_sneak_successes']:.1f}")
    print(f"  Sneak success rate: {agg['sneak_success_rate']:.1%}")
    print(f"  Avg Shoves/game: {agg['avg_shoves']:.1f}")
    print(f"  Avg ties/game: {agg['avg_ties']:.1f}")

    # Abilities
    print(f"\n--- Faction Abilities ---")
    sorted_abilities = sorted(agg["avg_abilities"].items(), key=lambda x: -x[1])
    for ability, avg in sorted_abilities:
        print(f"  {ability:20s}: {avg:.2f}/game")

    # Claims
    print(f"\n--- Claims per Player ---")
    for pid in range(np):
        avg = agg["avg_claims_per_player"].get(pid, 0)
        print(f"  P{pid}: {avg:.1f} claims/game")

    # Warnings
    print(f"\n{'='*65}")
    print(f"  HEALTH WARNINGS")
    print(f"{'='*65}")
    warnings = []

    if agg["hit_max_turns_rate"] > 0.05:
        warnings.append(f"⚠  {agg['hit_max_turns_rate']:.1%} of games hit max turns limit")

    if agg["win_rate_spread"] > 0.15:
        warnings.append(f"⚠  Win rate spread of {agg['win_rate_spread']:.1%} suggests positional imbalance")

    if agg["zero_trample_rate"] > 0.5:
        warnings.append(f"⚠  {agg['zero_trample_rate']:.1%} of games had zero Tramples — Pit may be too forgiving")

    if agg["avg_tramples"] > 4.0:
        warnings.append(f"⚠  Avg {agg['avg_tramples']:.1f} Tramples/game — may be too punishing")

    if agg["sneak_success_rate"] > 0.85:
        warnings.append(f"⚠  Sneak succeeds {agg['sneak_success_rate']:.1%} — may be too safe/dominant")
    elif agg["sneak_success_rate"] < 0.3:
        warnings.append(f"⚠  Sneak succeeds only {agg['sneak_success_rate']:.1%} — may be too risky to attempt")

    if agg["second_set_rate"] > 0.5:
        warnings.append(f"⚠  {agg['second_set_rate']:.1%} achieve 2nd set — set bonuses may be too easy")
    elif agg["first_set_rate"] < 0.2:
        warnings.append(f"⚠  Only {agg['first_set_rate']:.1%} achieve 1st set — sets may be too hard")

    for ability, avg in agg["avg_abilities"].items():
        if avg < 0.5:
            warnings.append(f"⚠  {ability} triggers only {avg:.2f}/game — may be underused")

    if not warnings:
        print(f"  ✓ No major health issues detected!")
    else:
        for w in warnings:
            print(f"  {w}")

    print()


# ─── PLAYER CONFIG HELPERS ────────────────────────────────────

def build_player_configs(args, num_players: int) -> List[dict]:
    """Build player configurations from CLI args."""
    configs = [{"skill": 1.0, "style": "balanced", "aggression": 0.5}
               for _ in range(num_players)]

    if args.preset == "experts":
        configs = [{"skill": 1.0, "style": "balanced", "aggression": 0.5}
                   for _ in range(num_players)]
    elif args.preset == "beginners":
        configs = [{"skill": 0.3, "style": "balanced", "aggression": 0.5}
                   for _ in range(num_players)]
    elif args.preset == "mixed":
        configs = [{"skill": 1.0, "style": "balanced", "aggression": 0.5}]
        configs += [{"skill": 0.3, "style": "balanced", "aggression": 0.5}
                    for _ in range(num_players - 1)]
    elif args.preset == "styles":
        style_list = list(STYLE_PROFILES.keys())
        configs = [{"skill": 1.0, "style": style_list[i % len(style_list)],
                    "aggression": 0.5}
                   for i in range(num_players)]

    # Override with explicit flags
    if args.skill:
        skills = [float(s) for s in args.skill.split(",")]
        for i, s in enumerate(skills):
            if i < len(configs):
                configs[i]["skill"] = s

    if args.styles:
        styles = args.styles.split(",")
        for i, s in enumerate(styles):
            if i < len(configs):
                configs[i]["style"] = s.strip()

    if args.aggression:
        aggrs = [float(a) for a in args.aggression.split(",")]
        for i, a in enumerate(aggrs):
            if i < len(configs):
                configs[i]["aggression"] = a

    return configs


# ─── CLI ──────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="The Merch Stand Mob — Batch Simulation Runner"
    )
    parser.add_argument("-n", "--num-games", type=int, default=100,
                       help="Number of games to simulate (default: 100)")
    parser.add_argument("-p", "--players", type=int, default=4,
                       help="Number of players (3-5, default: 4)")
    parser.add_argument("-s", "--seed", type=int, default=1,
                       help="Starting random seed (default: 1)")
    parser.add_argument("--max-turns", type=int, default=50,
                       help="Maximum rounds per game (default: 50)")
    parser.add_argument("-v", "--verbose", action="store_true",
                       help="Print progress during simulation")
    parser.add_argument("--config", type=str, default=None,
                       help="Path to config.json")
    parser.add_argument("--json", type=str, default=None,
                       help="Export results to JSON file")

    # Player configuration
    parser.add_argument("--skill", type=str, default=None,
                       help="Comma-separated skill levels: '1.0,0.5,0.3'")
    parser.add_argument("--styles", type=str, default=None,
                       help="Comma-separated styles: 'rush,collector,balanced'")
    parser.add_argument("--aggression", type=str, default=None,
                       help="Comma-separated aggression: '0.8,0.3,0.5'")
    parser.add_argument("--preset", type=str, default=None,
                       choices=["experts", "beginners", "mixed", "styles"],
                       help="Preset player configurations")

    # Rule overrides
    parser.add_argument("--trample-threshold", type=int, default=None,
                       help="Override trample threshold for all player counts")
    parser.add_argument("--hand-size", type=int, default=None,
                       help="Override starting hand size")
    parser.add_argument("--sneak-cancel", type=int, default=None,
                       help="Sneaks cancel when this many+ attempt (default: 2)")
    parser.add_argument("--mid-set-colors", type=int, default=None,
                       help="Colors needed for intermediate set bonus (0=disabled)")
    parser.add_argument("--mid-set-vp", type=int, default=None,
                       help="VP for intermediate set bonus")
    parser.add_argument("--second-set-colors", type=int, default=None,
                       help="Colors needed for second set bonus (default: 6)")

    args = parser.parse_args()

    # Validate player count
    if args.players < 3 or args.players > 5:
        print("Error: Player count must be 3-5")
        sys.exit(1)

    # Load config
    config = load_config(args.config)

    # Apply rule overrides
    if args.trample_threshold is not None:
        for key in config["game_rules"]["trample_threshold"]:
            config["game_rules"]["trample_threshold"][key] = args.trample_threshold

    if args.hand_size is not None:
        for key in config["game_rules"]["hand_size"]:
            config["game_rules"]["hand_size"][key] = args.hand_size

    if args.sneak_cancel is not None:
        if "sneak_cancel_threshold" not in config["game_rules"]:
            config["game_rules"]["sneak_cancel_threshold"] = {}
        for key in ["3_player", "4_player", "5_player"]:
            config["game_rules"]["sneak_cancel_threshold"][key] = args.sneak_cancel

    if args.mid_set_colors is not None:
        config["game_rules"]["set_bonus"]["mid_set_colors"] = args.mid_set_colors
    if args.mid_set_vp is not None:
        config["game_rules"]["set_bonus"]["mid_set_vp"] = args.mid_set_vp
    if args.second_set_colors is not None:
        config["game_rules"]["set_bonus"]["second_set_colors"] = args.second_set_colors

    # Build player configs
    player_configs = build_player_configs(args, args.players)

    # Run simulation
    print(f"Running {args.num_games} games with {args.players} players (seed: {args.seed})...")
    agg = run_batch(config, args.num_games, args.players,
                    start_seed=args.seed, max_turns=args.max_turns,
                    player_configs=player_configs, verbose=args.verbose)

    # Print report
    print_report(agg, player_configs)

    # JSON export
    if args.json:
        with open(args.json, 'w') as f:
            json.dump(agg, f, indent=2, default=str)
        print(f"Stats exported to {args.json}")


if __name__ == "__main__":
    main()
