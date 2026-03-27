#!/usr/bin/env python3
"""
Heist Heat — Batch Simulation Runner

Runs N AI-vs-AI games and collects comprehensive statistics:
- Win rates by player position
- Score distributions
- Heat dynamics (avg heat per round, getaway timing)
- Chain reaction frequency and size
- Faction power usage
- Bust vs getaway rates
- Scoring pattern distribution
"""

import argparse
import json
import os
import sys
import random
from collections import defaultdict, Counter
from typing import List, Dict, Tuple, Optional

from cards import Card, build_full_deck
from game_state import GameState, Player
from ai_player import HeuristicAI, STYLE_PROFILES


# ── Single Game Runner ──────────────────────────────────────────────

def run_single_game(config: dict, num_players: int, seed: int,
                    player_configs: List[dict] = None,
                    max_turns_per_round: int = 100,
                    verbose: bool = False) -> dict:
    """Run one complete game (all rounds). Returns stats dict."""

    game = GameState(config, num_players, seed=seed)

    # Create AIs
    ais = []
    for i in range(num_players):
        if player_configs and i < len(player_configs):
            pc = player_configs[i]
            ais.append(HeuristicAI(
                skill=pc.get("skill", 1.0),
                style=pc.get("style", "opportunistic"),
                aggression=pc.get("aggression", 0.5),
                rng_seed=seed + i * 10000,
            ))
        else:
            ais.append(HeuristicAI(rng_seed=seed + i * 10000))

    total_rounds = config["game_rules"]["rounds_per_game"]
    turns_per_round = []

    for round_num in range(total_rounds):
        game.setup_round()
        turn_count = 0

        while not game.round_over and turn_count < max_turns_per_round:
            player = game.get_current_player()

            if not player.active:
                game.advance_turn()
                continue

            if not game.can_player_act(player):
                # Player is stuck (no cards, can't getaway)
                game.advance_turn()
                turn_count += 1
                continue

            ai = ais[player.id]
            action = ai.choose_action(player, game)

            if action["type"] == "getaway":
                result = game.action_getaway(player)
            elif action["type"] == "crack":
                result = game.action_crack(
                    player,
                    action["row"], action["col"],
                    action["hand_card_idx"],
                    action.get("use_faction_power", False),
                )

                # Handle peek powers (Green, Orange)
                if result.get("action") == "green_peek":
                    follow_up = ai.choose_crack_after_green_peek(
                        player, game,
                        result["peek_results"],
                        result["played_card"],
                        result["hand_card_idx"],
                    )
                    if follow_up:
                        result = game.action_crack(
                            player, follow_up["row"], follow_up["col"],
                            result["hand_card_idx"], False,
                        )

                elif result.get("action") == "orange_peek":
                    follow_up = ai.choose_crack_after_orange_peek(
                        player, game,
                        result["target_card"],
                        result["target_pos"],
                        result["played_card"],
                    )
                    if follow_up and follow_up.get("keep_target"):
                        r, c = result["target_pos"]
                        result = game.action_crack(
                            player, r, c,
                            result["hand_card_idx"], False,
                        )
                    elif follow_up:
                        result = game.action_crack(
                            player, follow_up["new_row"], follow_up["new_col"],
                            result["hand_card_idx"], False,
                        )

            elif action["type"] == "pass":
                pass  # Do nothing

            if game.round_over:
                break

            game.advance_turn()
            turn_count += 1

        # End of round scoring
        round_result = game.end_round()
        turns_per_round.append(turn_count)

    game.finish_game()

    # Compile stats
    winner_id, winner_score = game.get_winner()
    scores = game.get_scores()

    return {
        "seed": seed,
        "num_players": num_players,
        "winner": winner_id,
        "scores": scores,
        "round_scores": [p.round_scores for p in game.players],
        "turns_per_round": turns_per_round,
        "metrics": game.metrics,
        "heat_per_round": game.metrics["heat_per_round"],
    }


# ── Batch Runner ────────────────────────────────────────────────────

def run_batch(config: dict, num_games: int, num_players: int,
              start_seed: int = 1, player_configs: List[dict] = None,
              verbose: bool = False) -> dict:
    """Run N games and aggregate statistics."""

    all_stats = []
    for i in range(num_games):
        if verbose and (i + 1) % 50 == 0:
            print(f"  Game {i + 1}/{num_games}...", file=sys.stderr)
        stats = run_single_game(
            config, num_players,
            seed=start_seed + i,
            player_configs=player_configs,
        )
        all_stats.append(stats)

    return aggregate_stats(all_stats, num_players)


def aggregate_stats(all_stats: list, num_players: int) -> dict:
    """Aggregate individual game stats into a summary."""
    num_games = len(all_stats)

    # Win rates
    win_counts = Counter()
    for s in all_stats:
        win_counts[s["winner"]] += 1
    win_rates = {pid: win_counts[pid] / num_games for pid in range(num_players)}

    # Score distributions
    all_scores = [[] for _ in range(num_players)]
    for s in all_stats:
        for pid, score in enumerate(s["scores"]):
            all_scores[pid].append(score)

    avg_scores = [sum(sc) / len(sc) if sc else 0 for sc in all_scores]
    max_scores = [max(sc) if sc else 0 for sc in all_scores]
    min_scores = [min(sc) if sc else 0 for sc in all_scores]

    # Score spread
    flat_scores = [s for ss in all_scores for s in ss]
    overall_avg = sum(flat_scores) / len(flat_scores) if flat_scores else 0
    overall_std = (sum((s - overall_avg) ** 2 for s in flat_scores) / len(flat_scores)) ** 0.5 if flat_scores else 0

    # Turns per round
    all_turns = []
    for s in all_stats:
        all_turns.extend(s["turns_per_round"])
    avg_turns = sum(all_turns) / len(all_turns) if all_turns else 0

    # Heat per round
    all_heat = []
    for s in all_stats:
        all_heat.extend(s["heat_per_round"])
    avg_heat = sum(all_heat) / len(all_heat) if all_heat else 0

    # Crack stats
    total_cracks_attempted = [0] * num_players
    total_cracks_succeeded = [0] * num_players
    total_cracks_failed = [0] * num_players
    total_chains = [0] * num_players
    all_chain_lengths = []
    total_cards_claimed = [0] * num_players
    total_getaways = [0] * num_players
    total_busts = [0] * num_players
    total_alarms = 0
    total_vault_empty = 0
    total_heat_cap = 0
    total_faction_powers = [Counter() for _ in range(num_players)]

    for s in all_stats:
        m = s["metrics"]
        for pid in range(num_players):
            total_cracks_attempted[pid] += m["cracks_attempted"][pid]
            total_cracks_succeeded[pid] += m["cracks_succeeded"][pid]
            total_cracks_failed[pid] += m["cracks_failed"][pid]
            total_chains[pid] += m["chains_triggered"][pid]
            total_cards_claimed[pid] += m["cards_claimed"][pid]
            total_getaways[pid] += m["getaways"][pid]
            total_busts[pid] += m["busts"][pid]
            total_faction_powers[pid] += m["faction_powers_used"][pid]
        all_chain_lengths.extend(m["chain_lengths"])
        total_alarms += m["alarms_hit"]
        total_vault_empty += m["vault_empty_ends"]
        total_heat_cap += m["heat_cap_ends"]

    total_rounds = num_games * all_stats[0]["num_players"]  # not quite right
    total_rounds_played = sum(len(s["turns_per_round"]) for s in all_stats)
    rounds_per_game = len(all_stats[0]["turns_per_round"]) if all_stats else 3

    # Per-round stats
    getaway_rate = sum(total_getaways) / (num_games * num_players * rounds_per_game) if num_games else 0
    bust_rate = sum(total_busts) / (num_games * num_players * rounds_per_game) if num_games else 0

    # Chain stats
    avg_chain_len = sum(all_chain_lengths) / len(all_chain_lengths) if all_chain_lengths else 0
    max_chain_len = max(all_chain_lengths) if all_chain_lengths else 0

    # Round-by-round scoring patterns
    round_avg_scores = [[] for _ in range(rounds_per_game)]
    for s in all_stats:
        for pid in range(num_players):
            for rnd, score in enumerate(s["round_scores"][pid]):
                if rnd < rounds_per_game:
                    round_avg_scores[rnd].append(score)

    round_averages = [
        sum(scores) / len(scores) if scores else 0
        for scores in round_avg_scores
    ]

    return {
        "num_games": num_games,
        "num_players": num_players,
        "win_rates": win_rates,
        "avg_scores": avg_scores,
        "min_scores": min_scores,
        "max_scores": max_scores,
        "overall_avg_score": overall_avg,
        "overall_score_std": overall_std,
        "avg_turns_per_round": avg_turns,
        "avg_final_heat": avg_heat,
        "getaway_rate": getaway_rate,
        "bust_rate": bust_rate,
        "cracks_attempted_per_player": [c / num_games for c in total_cracks_attempted],
        "cracks_succeeded_per_player": [c / num_games for c in total_cracks_succeeded],
        "crack_success_rate": (
            sum(total_cracks_succeeded) / sum(total_cracks_attempted)
            if sum(total_cracks_attempted) > 0 else 0
        ),
        "chains_per_player": [c / num_games for c in total_chains],
        "avg_chain_length": avg_chain_len,
        "max_chain_length": max_chain_len,
        "cards_claimed_per_player": [c / num_games for c in total_cards_claimed],
        "alarms_per_game": total_alarms / num_games if num_games else 0,
        "vault_empty_pct": total_vault_empty / (num_games * rounds_per_game) * 100,
        "heat_cap_pct": total_heat_cap / (num_games * rounds_per_game) * 100,
        "faction_powers_total": dict(sum(total_faction_powers, Counter())),
        "round_averages": round_averages,
    }


# ── Report Printer ──────────────────────────────────────────────────

def print_report(agg: dict, player_configs: list = None):
    """Print a formatted simulation report."""
    np = agg["num_players"]
    ng = agg["num_games"]

    print(f"\n{'='*65}")
    print(f"  HEIST HEAT SIMULATION REPORT")
    print(f"  {ng} games · {np} players")
    if player_configs:
        styles = [pc.get("style", "opportunistic") for pc in player_configs]
        print(f"  Styles: {', '.join(styles)}")
    print(f"{'='*65}")

    # Win Rates
    print(f"\n--- Win Rates ---")
    for pid in range(np):
        bar = "█" * int(agg["win_rates"][pid] * 40)
        print(f"  Player {pid}: {agg['win_rates'][pid]:6.1%}  {bar}")

    # Score Distribution
    print(f"\n--- Score Distribution ---")
    print(f"  Overall avg: {agg['overall_avg_score']:.1f} ± {agg['overall_score_std']:.1f}")
    for pid in range(np):
        print(f"  Player {pid}: avg {agg['avg_scores'][pid]:.1f} "
              f"(min {agg['min_scores'][pid]}, max {agg['max_scores'][pid]})")

    # Round-by-Round Scoring
    if agg["round_averages"]:
        print(f"\n--- Round-by-Round Avg Score ---")
        for rnd, avg in enumerate(agg["round_averages"]):
            print(f"  Round {rnd + 1}: {avg:.1f} pts")

    # Pacing
    print(f"\n--- Pacing & Heat ---")
    print(f"  Avg turns per round: {agg['avg_turns_per_round']:.1f}")
    print(f"  Avg final heat: {agg['avg_final_heat']:.1f}")
    print(f"  Rounds ending at heat cap: {agg['heat_cap_pct']:.1f}%")
    print(f"  Rounds ending vault empty: {agg['vault_empty_pct']:.1f}%")

    # Getaway vs Bust
    print(f"\n--- Getaway vs Bust ---")
    print(f"  Getaway rate: {agg['getaway_rate']:.1%}")
    print(f"  Bust rate: {agg['bust_rate']:.1%}")

    # Cracking
    print(f"\n--- Cracking ---")
    print(f"  Crack success rate: {agg['crack_success_rate']:.1%}")
    print(f"  Avg cracks per game (per player):")
    for pid in range(np):
        print(f"    P{pid}: {agg['cracks_attempted_per_player'][pid]:.1f} attempted, "
              f"{agg['cracks_succeeded_per_player'][pid]:.1f} succeeded")
    print(f"  Avg cards claimed per game (per player):")
    for pid in range(np):
        print(f"    P{pid}: {agg['cards_claimed_per_player'][pid]:.1f}")

    # Chain Reactions
    print(f"\n--- Chain Reactions ---")
    print(f"  Chains per game (per player): "
          + ", ".join(f"P{pid}: {c:.1f}" for pid, c in enumerate(agg["chains_per_player"])))
    print(f"  Avg chain length: {agg['avg_chain_length']:.1f}")
    print(f"  Max chain length: {agg['max_chain_length']}")

    # Alarms
    print(f"\n--- Alarms ---")
    print(f"  Alarms triggered per game: {agg['alarms_per_game']:.1f}")

    # Faction Powers
    print(f"\n--- Faction Power Usage ---")
    fp = agg["faction_powers_total"]
    total_fp = sum(fp.values()) if fp else 1
    for faction in ["RED", "ORANGE", "YELLOW", "GREEN", "BLUE", "PURPLE"]:
        count = fp.get(faction, 0)
        pct = count / total_fp * 100 if total_fp else 0
        bar = "█" * int(pct / 2)
        print(f"  {faction:8s}: {count:4d} ({pct:4.1f}%)  {bar}")

    print(f"\n{'='*65}")


# ── Player Config Builder ──────────────────────────────────────────

def build_player_configs(args, num_players: int) -> list:
    configs = [{"skill": 1.0, "style": "opportunistic", "aggression": 0.5}
               for _ in range(num_players)]

    if args.preset == "experts":
        configs = [{"skill": 1.0, "style": "opportunistic", "aggression": 0.5}
                   for _ in range(num_players)]
    elif args.preset == "beginners":
        configs = [{"skill": 0.3, "style": "opportunistic", "aggression": 0.5}
                   for _ in range(num_players)]
    elif args.preset == "mixed":
        configs = [{"skill": 1.0, "style": "opportunistic", "aggression": 0.5}]
        configs += [{"skill": 0.3, "style": "opportunistic", "aggression": 0.5}
                    for _ in range(num_players - 1)]
    elif args.preset == "styles":
        style_list = ["cautious", "aggressive", "opportunistic"]
        configs = [{"skill": 1.0, "style": style_list[i % len(style_list)],
                    "aggression": 0.5}
                   for i in range(num_players)]

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
        aggs = [float(a) for a in args.aggression.split(",")]
        for i, a in enumerate(aggs):
            if i < len(configs):
                configs[i]["aggression"] = a

    return configs


# ── CLI ─────────────────────────────────────────────────────────────

def find_config():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    for path in [
        os.path.join(script_dir, "config.json"),
        os.path.join(script_dir, "..", "config.json"),
    ]:
        if os.path.exists(path):
            return path
    return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Heist Heat — Batch Simulation Runner"
    )
    parser.add_argument("-n", "--num-games", type=int, default=500,
                        help="Number of games to simulate (default: 500)")
    parser.add_argument("-p", "--players", type=int, default=3,
                        help="Number of players (2-5, default: 3)")
    parser.add_argument("-s", "--seed", type=int, default=1,
                        help="Starting random seed (default: 1)")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Print progress during simulation")
    parser.add_argument("--config", type=str, default=None,
                        help="Path to config.json")
    parser.add_argument("--json", type=str, default=None,
                        help="Export stats to JSON file")

    # Player configuration
    parser.add_argument("--preset", type=str, default=None,
                        choices=["experts", "beginners", "mixed", "styles"],
                        help="Preset player configurations")
    parser.add_argument("--skill", type=str, default=None,
                        help="Comma-separated skill levels (0-1)")
    parser.add_argument("--styles", type=str, default=None,
                        help="Comma-separated styles: cautious,aggressive,opportunistic")
    parser.add_argument("--aggression", type=str, default=None,
                        help="Comma-separated aggression levels (0-1)")

    # Rule overrides
    parser.add_argument("--heat-end", type=int, default=None,
                        help="Override heat_end threshold")
    parser.add_argument("--heat-getaway", type=int, default=None,
                        help="Override heat_getaway threshold")
    parser.add_argument("--rounds", type=int, default=None,
                        help="Override rounds per game")
    parser.add_argument("--round-multipliers", type=str, default=None,
                        help="Comma-separated scoring multipliers per round (e.g., '1,1,2')")

    args = parser.parse_args()

    # Load config
    config_path = args.config or find_config()
    if not config_path:
        print("ERROR: config.json not found", file=sys.stderr)
        sys.exit(1)

    with open(config_path) as f:
        config = json.load(f)

    # Apply overrides
    if args.heat_end is not None:
        config["game_rules"]["heat_end"] = args.heat_end
    if args.heat_getaway is not None:
        pkey = f"{args.players}_player"
        config["game_rules"]["heat_getaway"][pkey] = args.heat_getaway
    if args.rounds is not None:
        config["game_rules"]["rounds_per_game"] = args.rounds
    if args.round_multipliers is not None:
        config["game_rules"]["round_score_multipliers"] = [
            float(x) for x in args.round_multipliers.split(",")
        ]

    # Build player configs
    player_configs = build_player_configs(args, args.players)

    print(f"Running {args.num_games} games with {args.players} players "
          f"(seed={args.seed})...", file=sys.stderr)

    agg = run_batch(
        config, args.num_games, args.players,
        start_seed=args.seed,
        player_configs=player_configs,
        verbose=args.verbose,
    )

    print_report(agg, player_configs)

    if args.json:
        with open(args.json, 'w') as f:
            json.dump(agg, f, indent=2, default=str)
        print(f"\nStats exported to {args.json}")
