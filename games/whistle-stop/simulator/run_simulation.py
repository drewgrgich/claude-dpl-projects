#!/usr/bin/env python3
"""Batch simulation runner for Whistle Stop.

Runs N AI-vs-AI games and reports aggregate statistics:
win rates, VP distributions, faction performance, game length, etc.

Usage:
    python run_simulation.py -n 200 -p 4
    python run_simulation.py -n 100 -p 3 --preset experts --json results.json
    python run_simulation.py -n 500 --styles rush,builder,balanced,opportunist
"""

import argparse
import json
import os
import sys
from collections import defaultdict
from typing import List, Dict, Optional

from cards import build_deck, Card
from game_state import GameState, Player
from ai_player import HeuristicAI, STYLE_PROFILES


def load_config(config_path: str = None) -> dict:
    """Load config.json from default or specified path."""
    if config_path:
        with open(config_path) as f:
            return json.load(f)
    # Auto-detect
    script_dir = os.path.dirname(os.path.abspath(__file__))
    for candidate in [os.path.join(script_dir, "config.json"),
                      os.path.join(script_dir, "..", "config.json")]:
        if os.path.exists(candidate):
            with open(candidate) as f:
                return json.load(f)
    raise FileNotFoundError("config.json not found")


def run_single_game(config: dict, num_players: int, seed: int,
                    player_configs: List[dict] = None,
                    max_turns: int = 50,
                    verbose: bool = False) -> dict:
    """Run one complete game. Returns a stats dict."""
    factions = list(config["game_rules"]["factions"])

    # Assign factions from player configs or randomly
    rng = __import__("random").Random(seed)
    if player_configs:
        faction_assignments = []
        for i, pc in enumerate(player_configs):
            if "faction" in pc:
                faction_assignments.append(pc["faction"])
            else:
                faction_assignments.append(factions[i % len(factions)])
    else:
        rng.shuffle(factions)
        faction_assignments = factions[:num_players]

    game = GameState(config, num_players, seed=seed,
                     faction_assignments=faction_assignments)

    # Create AIs
    ais = []
    for i in range(num_players):
        pc = player_configs[i] if player_configs and i < len(player_configs) else {}
        ai = HeuristicAI(
            player_id=i,
            faction=game.players[i].faction,
            skill=pc.get("skill", 1.0),
            style=pc.get("style", "balanced"),
            aggression=pc.get("aggression", 0.5),
            rng_seed=seed + i * 1000,
        )
        ais.append(ai)

    # Tracking
    per_player_vp_history = defaultdict(list)
    round_count = 0
    action_log = []

    # Play the game
    while not game.game_over and round_count < max_turns:
        # Each AI chooses a card
        card_choices = []
        placement_choices = []

        for i, player in enumerate(game.players):
            ai = ais[i]

            # Choose card and placement (before round starts)
            card = ai.choose_card(player, game)
            if card is None:
                card = player.hand[0] if player.hand else None
                if card is None:
                    continue

            placement = ai.choose_placement(card, player, game)

            card_choices.append((player.id, card))
            placement_choices.append(placement)

        if not card_choices:
            break

        # Movement callback: AI decides AFTER card is placed on route
        def movement_fn(player, card, game_state):
            return ais[player.id].choose_movement(card, player, game_state)

        results = game.play_round(card_choices, placement_choices,
                                  movement_fn=movement_fn)

        for r in results:
            action_log.append({
                "round": round_count,
                "player": r["player_id"],
                "card": r["card"].id,
                "placement": r["placement"],
                "steps": r["move_result"]["steps_taken"],
                "vp_earned": r["score_result"]["total_vp"],
                "ten_multi": r["score_result"]["ten_multiplier"],
            })

        round_count += 1

        for p in game.players:
            per_player_vp_history[p.id].append(p.vp)

        if verbose:
            standings = game.get_standings()
            print(f"  Round {round_count}: Route={game.get_route_length()} | "
                  + " | ".join(f"P{pid}:{vp}VP" for pid, vp in standings))

    # Compile stats
    winner = game.get_winner()
    standings = game.get_standings()

    # Per-faction stats
    faction_vp = {}
    for p in game.players:
        faction_vp[p.faction] = p.vp

    # Per-player card play stats from action log
    cards_by_faction = defaultdict(lambda: defaultdict(int))
    ten_plays = defaultdict(int)
    zero_plays = defaultdict(int)
    total_vp_per_round = defaultdict(list)

    for entry in action_log:
        pid = entry["player"]
        card_faction = entry["card"].split("-")[0]
        cards_by_faction[pid][card_faction] += 1
        if entry["ten_multi"]:
            ten_plays[pid] += 1
        if entry["card"].endswith("-0"):
            zero_plays[pid] += 1
        total_vp_per_round[pid].append(entry["vp_earned"])

    stats = {
        "seed": seed,
        "num_players": num_players,
        "rounds": round_count,
        "winner_id": winner.id if winner else -1,
        "winner_faction": winner.faction if winner else "NONE",
        "winner_vp": winner.vp if winner else 0,
        "standings": standings,
        "station_placed": game.station_placed,
        "station_placer": game.station_placer_id,
        "route_length": game.get_route_length(),
        "player_factions": {p.id: p.faction for p in game.players},
        "player_vp": {p.id: p.vp for p in game.players},
        "faction_vp": faction_vp,
        "timed_out": round_count >= max_turns,
        "vp_spread": max(p.vp for p in game.players) - min(p.vp for p in game.players),
        "ten_plays": dict(ten_plays),
        "zero_plays": dict(zero_plays),
    }

    return stats


def run_batch(config: dict, num_games: int, num_players: int,
              start_seed: int = 1, max_turns: int = 50,
              player_configs: List[dict] = None,
              verbose: bool = False) -> dict:
    """Run N games and aggregate stats."""
    all_stats = []
    for i in range(num_games):
        seed = start_seed + i
        stats = run_single_game(config, num_players, seed,
                                player_configs=player_configs,
                                max_turns=max_turns,
                                verbose=verbose)
        all_stats.append(stats)

    return aggregate_stats(all_stats, num_players)


def aggregate_stats(all_stats: List[dict], num_players: int) -> dict:
    """Aggregate stats from multiple games."""
    n = len(all_stats)
    if n == 0:
        return {}

    # Win rates
    win_counts = defaultdict(int)
    faction_wins = defaultdict(int)
    faction_games = defaultdict(int)

    # VP tracking
    all_vp = defaultdict(list)
    all_spreads = []
    all_rounds = []
    all_route_lengths = []
    timeout_count = 0
    station_placed_count = 0

    # Faction VP
    faction_total_vp = defaultdict(list)

    for stats in all_stats:
        win_counts[stats["winner_id"]] += 1
        faction_wins[stats["winner_faction"]] += 1
        all_spreads.append(stats["vp_spread"])
        all_rounds.append(stats["rounds"])
        all_route_lengths.append(stats["route_length"])

        if stats["timed_out"]:
            timeout_count += 1
        if stats["station_placed"]:
            station_placed_count += 1

        for pid, vp in stats["player_vp"].items():
            all_vp[pid].append(vp)

        for pid, faction in stats["player_factions"].items():
            faction_games[faction] += 1

        for faction, vp in stats["faction_vp"].items():
            faction_total_vp[faction].append(vp)

    # Compute aggregates
    agg = {
        "num_games": n,
        "num_players": num_players,

        # Win rates by seat
        "win_rates_by_seat": {
            pid: win_counts[pid] / n for pid in range(num_players)
        },

        # Win rates by faction
        "win_rates_by_faction": {
            f: faction_wins[f] / max(faction_games[f], 1)
            for f in set(s["winner_faction"] for s in all_stats) if f != "NONE"
        },

        # VP stats
        "avg_winner_vp": sum(s["winner_vp"] for s in all_stats) / n,
        "avg_vp_by_seat": {
            pid: sum(vps) / len(vps) for pid, vps in all_vp.items()
        },
        "avg_vp_spread": sum(all_spreads) / n,

        # Game length
        "avg_rounds": sum(all_rounds) / n,
        "min_rounds": min(all_rounds),
        "max_rounds": max(all_rounds),

        # Route
        "avg_route_length": sum(all_route_lengths) / n,

        # Health
        "timeout_rate": timeout_count / n,
        "station_rate": station_placed_count / n,

        # Faction performance
        "avg_vp_by_faction": {
            f: sum(vps) / len(vps)
            for f, vps in faction_total_vp.items()
        },
    }

    return agg


def print_report(agg: dict):
    """Print a readable report."""
    print(f"\n{'='*60}")
    print(f"WHISTLE STOP SIMULATION REPORT")
    print(f"{agg['num_games']} games | {agg['num_players']} players")
    print(f"{'='*60}")

    print(f"\n--- Game Health ---")
    print(f"  Avg game length:    {agg['avg_rounds']:.1f} rounds "
          f"(range: {agg['min_rounds']}–{agg['max_rounds']})")
    print(f"  Avg route length:   {agg['avg_route_length']:.1f} cards")
    print(f"  Station placed:     {agg['station_rate']:.0%} of games")
    print(f"  Timeout rate:       {agg['timeout_rate']:.0%}")

    print(f"\n--- Win Rates by Seat ---")
    for pid, rate in sorted(agg["win_rates_by_seat"].items()):
        bar = "█" * int(rate * 40)
        print(f"  Seat {pid}: {rate:6.1%}  {bar}")

    print(f"\n--- Win Rates by Faction ---")
    for faction, rate in sorted(agg["win_rates_by_faction"].items(),
                                 key=lambda x: x[1], reverse=True):
        bar = "█" * int(rate * 40)
        print(f"  {faction:8s}: {rate:6.1%}  {bar}")

    print(f"\n--- VP Statistics ---")
    print(f"  Avg winner VP:      {agg['avg_winner_vp']:.1f}")
    print(f"  Avg VP spread:      {agg['avg_vp_spread']:.1f}")

    print(f"\n  Avg VP by seat:")
    for pid, vp in sorted(agg["avg_vp_by_seat"].items()):
        print(f"    Seat {pid}: {vp:.1f}")

    print(f"\n  Avg VP by faction:")
    for faction, vp in sorted(agg["avg_vp_by_faction"].items(),
                               key=lambda x: x[1], reverse=True):
        print(f"    {faction:8s}: {vp:.1f}")

    # Balance warnings
    print(f"\n--- Balance Alerts ---")
    alerts = []

    # Check seat imbalance
    seat_rates = list(agg["win_rates_by_seat"].values())
    if seat_rates:
        expected = 1.0 / agg["num_players"]
        max_dev = max(abs(r - expected) for r in seat_rates)
        if max_dev > 0.1:
            alerts.append(f"⚠ Seat imbalance: max deviation from expected "
                         f"({expected:.0%}) is {max_dev:.1%}")

    # Check faction imbalance
    faction_rates = list(agg["win_rates_by_faction"].values())
    if len(faction_rates) >= 2:
        fr_max = max(faction_rates)
        fr_min = min(faction_rates)
        if fr_max - fr_min > 0.15:
            alerts.append(f"⚠ Faction imbalance: win rate spread is "
                         f"{fr_max:.0%} vs {fr_min:.0%}")

    # Check timeout rate
    if agg["timeout_rate"] > 0.05:
        alerts.append(f"⚠ High timeout rate: {agg['timeout_rate']:.0%} "
                     f"of games didn't finish naturally")

    if not alerts:
        print("  ✓ No major balance issues detected")
    else:
        for a in alerts:
            print(f"  {a}")

    print(f"\n{'='*60}")


def build_player_configs(args, num_players: int, config: dict) -> List[dict]:
    """Build player configs from CLI args."""
    factions = config["game_rules"]["factions"]
    configs = [{"faction": factions[i % len(factions)]}
               for i in range(num_players)]

    if args.preset == "experts":
        for c in configs:
            c.update({"skill": 1.0, "style": "balanced"})
    elif args.preset == "beginners":
        for c in configs:
            c.update({"skill": 0.3, "style": "balanced"})
    elif args.preset == "mixed":
        configs[0].update({"skill": 1.0, "style": "balanced"})
        for c in configs[1:]:
            c.update({"skill": 0.3, "style": "balanced"})
    elif args.preset == "styles":
        style_list = list(STYLE_PROFILES.keys())
        for i, c in enumerate(configs):
            c.update({"skill": 1.0, "style": style_list[i % len(style_list)]})
    elif args.preset == "factions":
        # Each player gets a different faction, all expert balanced
        for i, c in enumerate(configs):
            c.update({"skill": 1.0, "style": "balanced",
                      "faction": factions[i % len(factions)]})

    # CLI overrides
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

    if args.factions:
        faction_list = [f.strip().upper() for f in args.factions.split(",")]
        for i, f in enumerate(faction_list):
            if i < len(configs):
                configs[i]["faction"] = f

    return configs


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Whistle Stop batch simulation runner")
    parser.add_argument("-n", "--num-games", type=int, default=100,
                        help="Number of games to simulate (default: 100)")
    parser.add_argument("-p", "--players", type=int, default=4,
                        help="Number of players (2-4, default: 4)")
    parser.add_argument("-s", "--seed", type=int, default=1,
                        help="Starting seed (default: 1)")
    parser.add_argument("--max-turns", type=int, default=50,
                        help="Max rounds before timeout (default: 50)")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Print each round's state")
    parser.add_argument("--config", type=str, default=None,
                        help="Path to config.json")
    parser.add_argument("--json", type=str, default=None,
                        help="Export results to JSON file")

    # Player config
    parser.add_argument("--preset", type=str, default="experts",
                        choices=["experts", "beginners", "mixed", "styles", "factions"],
                        help="AI preset (default: experts)")
    parser.add_argument("--skill", type=str, default=None,
                        help="Comma-separated skill levels per player")
    parser.add_argument("--styles", type=str, default=None,
                        help="Comma-separated play styles per player")
    parser.add_argument("--factions", type=str, default=None,
                        help="Comma-separated faction assignments per player")

    # Rule overrides
    parser.add_argument("--station-bonus", type=int, default=None,
                        help="Override station placer bonus VP")
    parser.add_argument("--red-multiplier", type=int, default=None,
                        help="Override red scoring multiplier")
    parser.add_argument("--ten-multiplier", type=int, default=None,
                        help="Override 10-card scoring multiplier")
    parser.add_argument("--hand-size", type=int, default=None,
                        help="Override starting hand size")
    parser.add_argument("--route-length", type=int, default=None,
                        help="Override route length to end game")

    args = parser.parse_args()

    config = load_config(args.config)

    # Apply rule overrides
    if args.station_bonus is not None:
        config["game_rules"]["station_placer_bonus"] = args.station_bonus
    if args.red_multiplier is not None:
        config["game_rules"]["red_scoring_multiplier"] = args.red_multiplier
    if args.ten_multiplier is not None:
        config["game_rules"]["ten_scoring_multiplier"] = args.ten_multiplier
    if args.hand_size is not None:
        config["game_rules"]["hand_size"] = args.hand_size
    if args.route_length is not None:
        config["game_rules"]["route_length_to_end"] = args.route_length

    player_configs = build_player_configs(args, args.players, config)

    print(f"Running {args.num_games} games with {args.players} players...")
    print(f"Preset: {args.preset}")
    for i, pc in enumerate(player_configs):
        print(f"  P{i}: {pc.get('faction', '?')} | "
              f"skill={pc.get('skill', 1.0):.1f} | "
              f"style={pc.get('style', 'balanced')}")

    agg = run_batch(config, args.num_games, args.players,
                    start_seed=args.seed, max_turns=args.max_turns,
                    player_configs=player_configs,
                    verbose=args.verbose)

    print_report(agg)

    if args.json:
        with open(args.json, "w") as f:
            json.dump(agg, f, indent=2, default=str)
        print(f"\nResults saved to {args.json}")
