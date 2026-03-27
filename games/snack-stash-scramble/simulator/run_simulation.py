#!/usr/bin/env python3
"""Batch simulation runner for Snack Stash Scramble.

Runs N AI-vs-AI games and collects comprehensive metrics:
  - Win rates by seat position
  - Game length distribution
  - Faction power usage
  - Scoring distributions
  - Pacing metrics (stagnation, snack floor, halftime timing)
  - Wild card risk/reward analysis
"""

import argparse
import json
import os
import sys
from collections import defaultdict
from typing import List, Dict, Any, Optional

from cards import Card, build_deck
from game_state import GameState, Player
from ai_player import HeuristicAI, game_progress


def run_single_game(config: dict, num_players: int, seed: int,
                    max_turns: int = 200,
                    player_configs: Optional[List[dict]] = None) -> dict:
    """Play one complete game. Returns stats dict."""
    game = GameState(config, num_players, seed=seed)
    game.setup()

    # Create AIs
    ais = []
    for i in range(num_players):
        pc = player_configs[i] if player_configs and i < len(player_configs) else {}
        ais.append(HeuristicAI(
            skill=pc.get("skill", 1.0),
            style=pc.get("style", "balanced"),
            aggression=pc.get("aggression", 0.5),
            rng_seed=seed + i * 1000,
        ))

    # Tracking
    action_counts = defaultdict(lambda: defaultdict(int))
    stagnation = defaultdict(int)  # turns without banking per player
    faction_triggers_by_player = defaultdict(lambda: defaultdict(int))
    wilds_banked = 0
    wilds_discarded = 0
    poison_peanuts = 0  # Yellow power on opponents
    turn_count = 0

    while not game.game_over and turn_count < max_turns:
        player = game.get_current_player()
        ai = ais[player.id]
        banked_this_turn = False

        # --- DRAW PHASE ---
        # Track if player could bank last turn (for scavenge eligibility)
        could_bank = len(game.find_all_valid_sets(player.hand)) > 0
        draw_choice = ai.choose_draw(player, game)
        if draw_choice == "snack_floor":
            result = game.action_snack_floor(player)
            action_counts[player.id]["snack_floor"] += 1
        elif draw_choice == "draw_litter_box":
            result = game.action_draw_litter_box(player)
            if not result["success"]:
                result = game.action_draw_feeder(player)
                action_counts[player.id]["draw_feeder"] += 1
            else:
                action_counts[player.id]["draw_litter_box"] += 1
        else:
            # Scavenge: draw 2 if player couldn't bank and stagnation > 1
            use_scavenge = (not could_bank and stagnation.get(player.id, 0) >= 1)
            result = game.action_draw_feeder(player, scavenge=use_scavenge)
            if result.get("action") == "scavenge":
                action_counts[player.id]["scavenge"] += 1
            else:
                action_counts[player.id]["draw_feeder"] += 1

        if game.game_over:
            break

        # --- BANK PHASE ---
        bank_actions = ai.choose_banks(player, game)
        for ba in bank_actions:
            # Prepare faction power target
            target = None
            faction = ba.get("faction_trigger")

            if faction == "GREEN":
                # Will handle after banking
                pass
            elif faction == "BLUE":
                target = ai.choose_blue_swap(player, game)
            elif faction == "PURPLE":
                target = ai.choose_purple_tuck(game)

            result = game.action_bank_set(
                player, ba["cards"], ba["set_type"],
                faction_trigger=faction, trigger_target=target
            )

            if result["success"]:
                banked_this_turn = True
                action_counts[player.id]["bank"] += 1
                wilds_banked += sum(1 for c in ba["cards"] if c.is_wild)

                # Handle faction-specific follow-ups
                if faction == "GREEN" and result.get("power_result"):
                    pr = result["power_result"]
                    if "peeked" in pr:
                        if pr.get("green_take"):
                            # Take-one variant: take best card, put rest back
                            peeked = pr["peeked"]
                            # Remove all peeked from feeder (they were put back)
                            for _ in range(len(peeked)):
                                game.feeder.draw_one()
                            # AI picks best
                            order = ai.choose_green_reorder(peeked, player, game)
                            best_idx = order[0]
                            taken = peeked[best_idx]
                            player.hand.append(taken)
                            rest = [peeked[i] for i in order[1:]]
                            game.feeder.add_to_top(rest)
                        else:
                            order = ai.choose_green_reorder(pr["peeked"], player, game)
                            reordered = [pr["peeked"][i] for i in order]
                            for _ in range(len(reordered)):
                                game.feeder.draw_one()
                            game.feeder.add_to_top(reordered)

                if faction == "YELLOW":
                    yellow_action = ai.choose_yellow_extend(player, game)
                    if yellow_action:
                        ext_result = game.action_extend_set(
                            player, yellow_action["card"],
                            yellow_action["target_player_id"],
                            yellow_action["target_set_idx"]
                        )
                        if ext_result["success"]:
                            if yellow_action["target_player_id"] != player.id:
                                poison_peanuts += 1
                            action_counts[player.id]["yellow_extend"] += 1

                faction_triggers_by_player[player.id][faction] += 1

            if game.game_over:
                break

        if game.game_over:
            break

        # --- VOLUNTARY EXTENSIONS ---
        extensions = ai.choose_extensions(player, game)
        for ext in extensions:
            if not player.hand:
                break
            ext_result = game.action_extend_set(
                player, ext["card"],
                ext["target_player_id"],
                ext["target_set_idx"]
            )
            if ext_result["success"]:
                action_counts[player.id]["extend"] += 1
                banked_this_turn = True

        if game.game_over:
            break

        # --- DISCARD PHASE ---
        if player.hand:
            discard_card = ai.choose_discard(player, game)
            if discard_card:
                if discard_card.is_wild:
                    wilds_discarded += 1
                game.action_discard(player, discard_card)
                action_counts[player.id]["discard"] += 1

        # Track stagnation
        if banked_this_turn:
            stagnation[player.id] = 0
        else:
            stagnation[player.id] += 1

        game.advance_turn()
        turn_count += 1

    # --- COMPILE STATS ---
    scores = game.get_final_scores()
    winner = game.get_winner()
    hit_turn_limit = turn_count >= max_turns

    return {
        "seed": seed,
        "num_players": num_players,
        "winner": winner,
        "scores": scores,
        "turn_count": turn_count,
        "hit_turn_limit": hit_turn_limit,
        "halftime_done": game.halftime_done,
        "halftime_turn": game.halftime_turn,
        "action_counts": dict(action_counts),
        "faction_power_uses": dict(game.faction_power_uses),
        "faction_triggers_by_player": dict(faction_triggers_by_player),
        "sets_banked": game.sets_banked_count,
        "extensions": game.extensions_count,
        "snack_floor_triggers": game.snack_floor_triggers,
        "stale_snack_blocks": game.stale_snack_blocks,
        "mid_bite_whistles": game.mid_bite_whistles,
        "wilds_banked": wilds_banked,
        "wilds_discarded": wilds_discarded,
        "poison_peanuts": poison_peanuts,
        "max_stagnation": max(stagnation.values()) if stagnation else 0,
        "player_configs": player_configs,
    }


def run_batch(config: dict, num_games: int, num_players: int,
              start_seed: int = 1, max_turns: int = 200,
              player_configs: Optional[List[dict]] = None,
              verbose: bool = False) -> dict:
    """Run N games and aggregate statistics."""
    all_stats = []
    for i in range(num_games):
        seed = start_seed + i
        stats = run_single_game(config, num_players, seed, max_turns, player_configs)
        all_stats.append(stats)
        if verbose and (i + 1) % 50 == 0:
            print(f"  ...completed {i+1}/{num_games} games")

    return aggregate_stats(all_stats, num_players)


def aggregate_stats(all_stats: List[dict], num_players: int) -> dict:
    """Aggregate per-game stats into a summary report."""
    n = len(all_stats)
    if n == 0:
        return {}

    # Win rates
    win_counts = defaultdict(int)
    for s in all_stats:
        win_counts[s["winner"]] += 1
    win_rates = {pid: count / n for pid, count in sorted(win_counts.items())}

    # Score distributions
    all_final_scores = defaultdict(list)
    all_banked_scores = defaultdict(list)
    all_hand_penalties = defaultdict(list)
    all_hand_sizes = defaultdict(list)
    all_wilds_in_hand = defaultdict(list)
    all_sets_counts = defaultdict(list)
    all_poison_damage = defaultdict(list)
    all_poisoned_cards = defaultdict(list)

    for s in all_stats:
        for ps in s["scores"]:
            pid = ps["player_id"]
            all_final_scores[pid].append(ps["final_score"])
            all_banked_scores[pid].append(ps["banked_score"])
            all_hand_penalties[pid].append(ps["hand_penalty"])
            all_poison_damage[pid].append(ps.get("poison_damage", 0))
            all_poisoned_cards[pid].append(ps.get("poisoned_cards", 0))
            all_hand_sizes[pid].append(ps["hand_size"])
            all_wilds_in_hand[pid].append(ps["wilds_in_hand"])
            all_sets_counts[pid].append(ps["sets_count"])

    # Game length
    turn_counts = [s["turn_count"] for s in all_stats]
    hit_limit = sum(1 for s in all_stats if s["hit_turn_limit"])

    # Halftime
    halftime_pct = sum(1 for s in all_stats if s["halftime_done"]) / n
    halftime_turns = [s["halftime_turn"] for s in all_stats if s["halftime_turn"] >= 0]

    # Faction powers
    faction_totals = defaultdict(int)
    for s in all_stats:
        for faction, count in s["faction_power_uses"].items():
            faction_totals[faction] += count

    # Action frequency
    action_totals = defaultdict(int)
    for s in all_stats:
        for pid, actions in s["action_counts"].items():
            for action, count in actions.items():
                action_totals[action] += count

    # Wild card stats
    total_wilds_banked = sum(s["wilds_banked"] for s in all_stats)
    total_wilds_discarded = sum(s["wilds_discarded"] for s in all_stats)
    total_poison_peanuts = sum(s["poison_peanuts"] for s in all_stats)

    # Stagnation
    max_stagnations = [s["max_stagnation"] for s in all_stats]

    # Snack floor
    total_snack_floors = sum(s["snack_floor_triggers"] for s in all_stats)
    total_mid_bite = sum(s["mid_bite_whistles"] for s in all_stats)

    def avg(lst):
        return sum(lst) / len(lst) if lst else 0

    def pct(lst, val):
        return sum(1 for x in lst if x == val) / len(lst) if lst else 0

    return {
        "num_games": n,
        "num_players": num_players,
        "win_rates": win_rates,
        "avg_turns": avg(turn_counts),
        "min_turns": min(turn_counts),
        "max_turns": max(turn_counts),
        "median_turns": sorted(turn_counts)[n // 2],
        "turn_limit_rate": hit_limit / n,
        "halftime_rate": halftime_pct,
        "avg_halftime_turn": avg(halftime_turns) if halftime_turns else -1,
        "per_player": {
            pid: {
                "avg_final_score": avg(all_final_scores[pid]),
                "avg_banked_score": avg(all_banked_scores[pid]),
                "avg_hand_penalty": avg(all_hand_penalties[pid]),
                "avg_hand_size_end": avg(all_hand_sizes[pid]),
                "avg_wilds_in_hand": avg(all_wilds_in_hand[pid]),
                "avg_sets_count": avg(all_sets_counts[pid]),
                "score_min": min(all_final_scores[pid]),
                "score_max": max(all_final_scores[pid]),
                "avg_poison_damage": avg(all_poison_damage[pid]),
                "avg_poisoned_cards": avg(all_poisoned_cards[pid]),
            }
            for pid in range(num_players)
        },
        "faction_powers": dict(faction_totals),
        "faction_powers_per_game": {f: c / n for f, c in faction_totals.items()},
        "action_totals": dict(action_totals),
        "action_per_game": {a: c / n for a, c in action_totals.items()},
        "wilds_banked_per_game": total_wilds_banked / n,
        "wilds_discarded_per_game": total_wilds_discarded / n,
        "poison_peanuts_per_game": total_poison_peanuts / n,
        "avg_max_stagnation": avg(max_stagnations),
        "stagnation_5_plus_rate": sum(1 for x in max_stagnations if x >= 5) / n,
        "snack_floor_per_game": total_snack_floors / n,
        "mid_bite_whistle_rate": total_mid_bite / n,
    }


def print_report(agg: dict):
    """Print a formatted simulation report."""
    n = agg["num_games"]
    np = agg["num_players"]

    print(f"\n{'='*65}")
    print(f"  SNACK STASH SCRAMBLE — SIMULATION REPORT")
    print(f"  {n} games, {np} players")
    print(f"{'='*65}")

    # Game Length
    print(f"\n--- Game Length ---")
    print(f"  Average: {agg['avg_turns']:.1f} turns")
    print(f"  Median:  {agg['median_turns']} turns")
    print(f"  Range:   {agg['min_turns']}–{agg['max_turns']}")
    print(f"  Turn limit aborts: {agg['turn_limit_rate']:.1%}")

    # Halftime
    print(f"\n--- Halftime Sweep ---")
    print(f"  Halftime reached: {agg['halftime_rate']:.1%} of games")
    if agg['avg_halftime_turn'] >= 0:
        print(f"  Avg halftime turn: {agg['avg_halftime_turn']:.1f}")

    # Win Rates
    print(f"\n--- Win Rates by Seat ---")
    for pid, rate in agg["win_rates"].items():
        marker = " <<<" if rate > 1.0 / np + 0.05 else ""
        print(f"  Player {pid} (Seat {pid+1}): {rate:.1%}{marker}")

    # Scoring
    print(f"\n--- Scoring ---")
    for pid in range(np):
        ps = agg["per_player"][pid]
        print(f"  P{pid}: avg final {ps['avg_final_score']:+.1f}  "
              f"(banked {ps['avg_banked_score']:.1f} - penalty {ps['avg_hand_penalty']:.1f})  "
              f"range [{ps['score_min']:+d}, {ps['score_max']:+d}]  "
              f"sets: {ps['avg_sets_count']:.1f}")

    # Faction Powers
    print(f"\n--- Faction Power Usage (per game) ---")
    for faction, count in sorted(agg["faction_powers_per_game"].items(),
                                  key=lambda x: -x[1]):
        bar = "#" * int(count * 5)
        print(f"  {faction:8s}: {count:.2f}  {bar}")

    # Wild Card Analysis
    print(f"\n--- Wild Card Risk/Reward ---")
    print(f"  Wilds banked per game:    {agg['wilds_banked_per_game']:.2f}")
    print(f"  Wilds discarded per game: {agg['wilds_discarded_per_game']:.2f}")
    for pid in range(np):
        ps = agg["per_player"][pid]
        print(f"  P{pid} avg wilds stuck in hand: {ps['avg_wilds_in_hand']:.2f}")

    # Pacing
    print(f"\n--- Pacing & Stagnation ---")
    print(f"  Snack floor triggers / game: {agg['snack_floor_per_game']:.2f}")
    print(f"  Mid-bite whistle rate:       {agg['mid_bite_whistle_rate']:.2f}")
    print(f"  Avg worst stagnation streak: {agg['avg_max_stagnation']:.1f} turns")
    print(f"  Games with 5+ stagnation:    {agg['stagnation_5_plus_rate']:.1%}")

    # Offensive play
    print(f"\n--- Offensive Play ---")
    print(f"  Poisoned Peanuts / game: {agg['poison_peanuts_per_game']:.2f}")

    # Action Frequency
    print(f"\n--- Action Frequency (per game) ---")
    for action, count in sorted(agg["action_per_game"].items(), key=lambda x: -x[1]):
        print(f"  {action:20s}: {count:.2f}")

    # Warnings
    print(f"\n--- Potential Issues ---")
    issues = []
    wr = agg["win_rates"]
    if wr:
        max_wr = max(wr.values())
        min_wr = min(wr.values())
        if max_wr - min_wr > 0.10:
            best_seat = max(wr, key=wr.get)
            issues.append(f"Seat imbalance: P{best_seat} wins {max_wr:.1%} "
                          f"(expected ~{1/np:.1%})")
    if agg["turn_limit_rate"] > 0.05:
        issues.append(f"Turn limit aborts at {agg['turn_limit_rate']:.1%} — "
                      f"games may be too long or stalling")
    if agg["stagnation_5_plus_rate"] > 0.3:
        issues.append(f"High stagnation: {agg['stagnation_5_plus_rate']:.1%} of games "
                      f"have 5+ turn streaks with no banking")
    fp = agg["faction_powers_per_game"]
    if fp:
        max_fp = max(fp.values())
        min_fp = min(fp.values())
        if max_fp > 0 and min_fp / max_fp < 0.3:
            weak = min(fp, key=fp.get)
            issues.append(f"Underused faction: {weak} triggered {fp[weak]:.2f}/game "
                          f"vs best {max_fp:.2f}/game")

    if issues:
        for issue in issues:
            print(f"  ⚠ {issue}")
    else:
        print(f"  No major issues detected.")

    print(f"\n{'='*65}\n")


def load_config(path: str = None) -> dict:
    """Load config.json from the given path or auto-detect."""
    if path:
        with open(path) as f:
            return json.load(f)

    script_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(script_dir, "config.json"),
        os.path.join(script_dir, "..", "config.json"),
    ]
    for c in candidates:
        if os.path.exists(c):
            with open(c) as f:
                return json.load(f)

    raise FileNotFoundError("Could not find config.json")


def build_player_configs(args, num_players: int) -> List[dict]:
    """Build player configs from CLI args."""
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
        style_list = ["rush", "balanced", "hoarder", "aggressive"]
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

    return configs


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run batch simulation of Snack Stash Scramble")
    parser.add_argument("-n", "--num-games", type=int, default=500,
                        help="Number of games to simulate (default: 500)")
    parser.add_argument("-p", "--players", type=int, default=3,
                        help="Number of players (2-4, default: 3)")
    parser.add_argument("-s", "--seed", type=int, default=1,
                        help="Starting random seed (default: 1)")
    parser.add_argument("--max-turns", type=int, default=200,
                        help="Max turns per game before abort (default: 200)")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Print progress during simulation")
    parser.add_argument("--config", type=str, default=None,
                        help="Path to config.json")
    parser.add_argument("--json", type=str, default=None,
                        help="Export stats to JSON file")

    # Player presets
    parser.add_argument("--preset", type=str, default=None,
                        choices=["experts", "beginners", "mixed", "styles"],
                        help="Preset player configurations")
    parser.add_argument("--skill", type=str, default=None,
                        help="Comma-separated skill levels per player")
    parser.add_argument("--styles", type=str, default=None,
                        help="Comma-separated play styles per player")

    # Rule overrides
    parser.add_argument("--snack-floor-threshold", type=int, default=None,
                        help="Override snack floor hand threshold")
    parser.add_argument("--snack-floor-draw", type=int, default=None,
                        help="Override snack floor draw count")
    parser.add_argument("--min-set-size", type=int, default=None,
                        help="Override minimum set size")
    parser.add_argument("--wild-penalty", type=int, default=None,
                        help="Override wild card hand penalty")
    parser.add_argument("--starting-hand", type=int, default=None,
                        help="Override starting hand size")

    args = parser.parse_args()

    config = load_config(args.config)

    # Apply rule overrides
    if args.snack_floor_threshold is not None:
        config["draw"]["snack_floor_threshold"] = args.snack_floor_threshold
    if args.snack_floor_draw is not None:
        config["draw"]["snack_floor_draw_count"] = args.snack_floor_draw
    if args.min_set_size is not None:
        config["banking"]["min_set_size"] = args.min_set_size
    if args.wild_penalty is not None:
        config["scoring"]["wild_hand_penalty"] = args.wild_penalty
    if args.starting_hand is not None:
        config["setup"]["starting_hand_size"] = args.starting_hand

    player_configs = build_player_configs(args, args.players)

    print(f"Running {args.num_games} games with {args.players} players...")
    if args.preset:
        print(f"  Preset: {args.preset}")
    for i, pc in enumerate(player_configs):
        print(f"  P{i}: skill={pc['skill']}, style={pc['style']}, "
              f"aggression={pc['aggression']}")

    agg = run_batch(config, args.num_games, args.players,
                    start_seed=args.seed, max_turns=args.max_turns,
                    player_configs=player_configs, verbose=args.verbose)

    print_report(agg)

    if args.json:
        with open(args.json, 'w') as f:
            json.dump(agg, f, indent=2, default=str)
        print(f"Stats saved to {args.json}")
