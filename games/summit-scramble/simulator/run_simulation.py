#!/usr/bin/env python3
"""
Summit Scramble Batch Simulator.

Runs N AI-vs-AI games and collects comprehensive metrics to surface
balance issues, edge cases, and design weaknesses.
"""

import argparse
import json
import os
import sys
import random
from typing import List, Dict, Optional
from collections import defaultdict
from dataclasses import dataclass

from cards import Card, build_full_deck, FACTIONS, FACTION_ABILITIES
from game_state import (
    GameState, Player, Formation, FormationType,
    classify_formation, formation_beats,
)
from ai_player import HeuristicAI, STYLE_PROFILES


# ---------------------------------------------------------------------------
# Single-round game loop
# ---------------------------------------------------------------------------

def run_single_round(config: dict, num_players: int, seed: int,
                     player_configs: List[dict] = None,
                     max_turns: int = 300,
                     use_stored_surge: bool = False,
                     hand_size_overrides: dict = None,
                     verbose: bool = False) -> dict:
    """Play one round of Summit Scramble. Returns stats dict."""
    game = GameState(config, num_players, seed=seed,
                     use_stored_surge=use_stored_surge,
                     hand_size_overrides=hand_size_overrides)
    game.setup()

    # Create AIs
    ais = []
    for i in range(num_players):
        pc = player_configs[i] if player_configs else {}
        ais.append(HeuristicAI(
            skill=pc.get("skill", 1.0),
            style=pc.get("style", "balanced"),
            aggression=pc.get("aggression", 0.5),
            rng_seed=seed + i * 1000,
        ))

    # Track stagnation
    stagnation_turns = 0
    max_stagnation = 0
    last_hand_sizes = [p.hand_size for p in game.players]

    turn = 0
    while not game.round_over and turn < max_turns:
        turn += 1
        game.turn_count = turn

        # Check if round is over
        if game.check_round_over():
            break

        leader_idx = game.current_leader_idx
        leader = game.players[leader_idx]
        ai_leader = ais[leader_idx]

        if leader.finished:
            game.current_leader_idx = game._next_active_player(leader_idx)
            continue

        # --- LEAD ---
        lead_formation = ai_leader.choose_lead(leader, game)
        if lead_formation is None:
            # Shouldn't happen, but safety valve
            game.current_leader_idx = game._next_active_player(leader_idx)
            stagnation_turns += 1
            max_stagnation = max(max_stagnation, stagnation_turns)
            continue

        result = game.play_formation(leader, lead_formation)

        if result.get("went_out"):
            _handle_trick_end(game, ais, result)
            if game.check_round_over():
                break
            continue

        # --- FOLLOW (clockwise) ---
        trick_ended = False
        follower_idx = game._next_active_player(leader_idx)
        players_acted = {leader_idx}

        while not trick_ended:
            if follower_idx in players_acted:
                # Everyone has had a chance — trick over
                break

            follower = game.players[follower_idx]
            ai_follower = ais[follower_idx]

            if follower.finished or follower.pid in game.passed_players:
                players_acted.add(follower_idx)
                follower_idx = game._next_active_player(follower_idx)
                continue

            # Check for interrupt (Cannon or Trip-Up) from any player
            interrupt = _check_interrupts(game, ais, follower_idx)
            if interrupt:
                interrupter_pid, int_formation = interrupt
                int_result = game.play_interrupt(
                    game.players[interrupter_pid], int_formation)
                if int_result.get("went_out"):
                    _handle_trick_end(game, ais, int_result)
                    trick_ended = True
                    break
                # Cannon/Trip-Up ends trick immediately
                trick_ended = True
                break

            # Normal follow
            follow_play = ai_follower.choose_follow(follower, game)
            if follow_play is None:
                game.player_passes(follower)
            else:
                f_result = game.play_formation(follower, follow_play)
                if f_result.get("went_out"):
                    _handle_trick_end(game, ais, f_result)
                    trick_ended = True
                    break

            players_acted.add(follower_idx)

            # Check if all active non-passed players have acted
            active_pids = game.get_active_pids()
            non_passed = [pid for pid in active_pids
                         if pid not in game.passed_players and pid != game.trick_winner_idx]
            if not non_passed:
                break

            follower_idx = game._next_active_player(follower_idx)

        # --- RESOLVE TRICK ---
        if not game.round_over:
            trick_result = game.resolve_trick()

            # Handle ability trigger
            if trick_result["power_triggered"] and trick_result["ability"]:
                winner = game.players[trick_result["winner"]]
                if not winner.finished:
                    ability = trick_result["ability"]
                    ai_winner = ais[trick_result["winner"]]

                    if ability == "choose":
                        # AI chooses faction for Surge/Cannon
                        winning_f = trick_result["formation"]
                        ability = ai_winner.choose_ability_faction(
                            winning_f, winner, game)

                    if ability:
                        # Stored Surge check
                        if (use_stored_surge and
                            ai_winner.should_store_surge(winner, game,
                                                         trick_result["formation"])):
                            # Store instead of trigger
                            pass  # simplified for now
                        else:
                            choices = ai_winner.make_ability_choices(
                                ability, winner, game)
                            game.execute_ability(winner, ability, choices)

                            # Double trigger from released surge
                            if (use_stored_surge and
                                ai_winner.should_release_surge(winner, game)):
                                game.release_surge(winner)
                                choices2 = ai_winner.make_ability_choices(
                                    ability, winner, game)
                                game.execute_ability(winner, ability, choices2)

            if game.check_round_over():
                break

        # Stagnation tracking
        current_sizes = [p.hand_size for p in game.players]
        if current_sizes == last_hand_sizes:
            stagnation_turns += 1
        else:
            max_stagnation = max(max_stagnation, stagnation_turns)
            stagnation_turns = 0
        last_hand_sizes = current_sizes

    # Finalize
    game.check_round_over()
    max_stagnation = max(max_stagnation, stagnation_turns)

    stats = game.get_stats()
    stats["turns"] = turn
    stats["hit_turn_limit"] = turn >= max_turns
    stats["max_stagnation"] = max_stagnation
    stats["total_stagnation_turns"] = stagnation_turns

    return stats


def _check_interrupts(game: GameState, ais: List[HeuristicAI],
                      current_follower_idx: int):
    """Check if any player wants to fire an interrupt."""
    for p in game.get_active_players():
        if p.pid == game.trick_winner_idx:
            continue  # current trick winner doesn't interrupt themselves
        ai = ais[p.pid]
        interrupt = ai.choose_interrupt(p, game)
        if interrupt:
            return (p.pid, interrupt)
    return None


def _handle_trick_end(game: GameState, ais: List[HeuristicAI], result: dict):
    """Handle trick ending from going out."""
    # Cards go to base camp
    for card_list in game.current_trick_cards:
        for c in card_list:
            game.base_camp.add_to_bottom(c)
    game.current_trick_cards = []
    game.current_formation = None
    game.passed_players.clear()
    game.trick_count += 1


# ---------------------------------------------------------------------------
# Championship (multi-round)
# ---------------------------------------------------------------------------

def run_championship(config: dict, num_players: int, seed: int,
                     player_configs: List[dict] = None,
                     max_turns_per_round: int = 300,
                     fatigue_limit: int = 30,
                     mercy_rule: bool = True,
                     use_stored_surge: bool = False,
                     verbose: bool = False) -> dict:
    """Run a full championship (multiple rounds until fatigue limit)."""
    total_fatigue = defaultdict(int)
    round_stats = []
    round_num = 0
    max_rounds = config["game_rules"].get("max_rounds", 50)

    while round_num < max_rounds:
        round_num += 1
        round_seed = seed + round_num * 10000

        stats = run_single_round(
            config, num_players, round_seed,
            player_configs=player_configs,
            max_turns=max_turns_per_round,
            use_stored_surge=use_stored_surge,
            verbose=verbose,
        )
        stats["round"] = round_num
        round_stats.append(stats)

        # Accumulate fatigue
        for pid, fat in stats["fatigue"].items():
            total_fatigue[pid] += fat

        # Check if any player hit the limit
        if any(f >= fatigue_limit for f in total_fatigue.values()):
            break

    # Winner = lowest total fatigue
    winner = min(total_fatigue.keys(), key=lambda k: total_fatigue[k])

    return {
        "seed": seed,
        "num_players": num_players,
        "rounds_played": round_num,
        "total_fatigue": dict(total_fatigue),
        "winner": winner,
        "round_stats": round_stats,
    }


# ---------------------------------------------------------------------------
# Batch runner
# ---------------------------------------------------------------------------

def run_batch(config: dict, num_games: int, num_players: int,
              start_seed: int = 1,
              player_configs: List[dict] = None,
              max_turns: int = 300,
              mode: str = "round",
              fatigue_limit: int = 30,
              mercy_rule: bool = True,
              use_stored_surge: bool = False,
              verbose: bool = False) -> dict:
    """Run N games and aggregate statistics."""
    all_stats = []

    for i in range(num_games):
        seed = start_seed + i
        if mode == "championship":
            stats = run_championship(
                config, num_players, seed,
                player_configs=player_configs,
                max_turns_per_round=max_turns,
                fatigue_limit=fatigue_limit,
                mercy_rule=mercy_rule,
                use_stored_surge=use_stored_surge,
                verbose=verbose,
            )
        else:
            stats = run_single_round(
                config, num_players, seed,
                player_configs=player_configs,
                max_turns=max_turns,
                use_stored_surge=use_stored_surge,
                verbose=verbose,
            )
        all_stats.append(stats)

        if verbose and (i + 1) % 50 == 0:
            print(f"  Completed {i + 1}/{num_games} games...")

    return aggregate_stats(all_stats, mode)


def aggregate_stats(all_stats: List[dict], mode: str = "round") -> dict:
    """Aggregate stats across many games."""
    n = len(all_stats)
    if n == 0:
        return {}

    agg = {
        "num_games": n,
        "mode": mode,
    }

    if mode == "championship":
        return _aggregate_championship(all_stats, agg)
    else:
        return _aggregate_rounds(all_stats, agg)


def _aggregate_rounds(all_stats: List[dict], agg: dict) -> dict:
    """Aggregate single-round stats."""
    n = agg["num_games"]

    # Turn counts
    turns = [s["turns"] for s in all_stats]
    agg["avg_turns"] = sum(turns) / n
    agg["min_turns"] = min(turns)
    agg["max_turns"] = max(turns)
    agg["hit_turn_limit_count"] = sum(1 for s in all_stats if s.get("hit_turn_limit"))
    agg["hit_turn_limit_rate"] = agg["hit_turn_limit_count"] / n

    # Trick counts
    tricks = [s["trick_count"] for s in all_stats]
    agg["avg_tricks"] = sum(tricks) / n
    agg["min_tricks"] = min(tricks)
    agg["max_tricks"] = max(tricks)

    # Win rates (1st place)
    num_players = all_stats[0]["num_players"]
    win_counts = defaultdict(int)
    finish_positions = defaultdict(list)
    for s in all_stats:
        if s["finish_order"]:
            win_counts[s["finish_order"][0]] += 1
        for pid, pos_idx in enumerate(s["finish_order"]):
            # finish_order is ordered list of pids
            pass
        # Track position distribution
        for i, pid in enumerate(s["finish_order"]):
            finish_positions[pid].append(i + 1)

    agg["win_rates"] = {pid: count / n for pid, count in sorted(win_counts.items())}
    agg["avg_finish_position"] = {
        pid: sum(positions) / len(positions)
        for pid, positions in sorted(finish_positions.items())
    }

    # Formation usage
    total_formations = defaultdict(int)
    for s in all_stats:
        for ftype, count in s["formations_played"].items():
            total_formations[ftype] += count
    total_f = sum(total_formations.values()) or 1
    agg["formation_usage"] = {
        ftype: {"total": count, "pct": count / total_f * 100}
        for ftype, count in sorted(total_formations.items())
    }

    # Ability usage
    total_abilities = defaultdict(int)
    for s in all_stats:
        for ability, count in s["abilities_triggered"].items():
            total_abilities[ability] += count
    agg["ability_usage"] = dict(sorted(total_abilities.items()))

    # Cannons and Trip-Ups
    cannons = [s["cannons_fired"] for s in all_stats]
    trip_ups = [s["trip_ups"] for s in all_stats]
    agg["avg_cannons_per_game"] = sum(cannons) / n
    agg["avg_trip_ups_per_game"] = sum(trip_ups) / n
    agg["games_with_cannon"] = sum(1 for c in cannons if c > 0) / n * 100
    agg["games_with_trip_up"] = sum(1 for t in trip_ups if t > 0) / n * 100

    # Stagnation
    stag = [s.get("max_stagnation", 0) for s in all_stats]
    agg["avg_max_stagnation"] = sum(stag) / n
    agg["worst_stagnation"] = max(stag)
    agg["games_with_stagnation_10plus"] = sum(1 for s in stag if s >= 10)

    # Fatigue
    fatigue_by_position = defaultdict(list)
    for s in all_stats:
        for pid, fat in s["fatigue"].items():
            pos = s["finish_order"].index(pid) + 1 if pid in s["finish_order"] else -1
            fatigue_by_position[pos].append(fat)
    agg["avg_fatigue_by_position"] = {
        pos: sum(vals) / len(vals)
        for pos, vals in sorted(fatigue_by_position.items())
    }

    # Remaining cards for last place
    remaining = []
    for s in all_stats:
        for pid, cards_left in s["remaining_cards"].items():
            if cards_left > 0:
                remaining.append(cards_left)
    agg["avg_remaining_cards_last"] = sum(remaining) / len(remaining) if remaining else 0
    agg["max_remaining_cards_last"] = max(remaining) if remaining else 0

    # Cards played per player
    cards_per_player = defaultdict(list)
    for s in all_stats:
        for pid, count in s["cards_played_per_player"].items():
            cards_per_player[pid].append(count)
    agg["avg_cards_played_per_player"] = {
        pid: sum(vals) / len(vals)
        for pid, vals in sorted(cards_per_player.items())
    }

    return agg


def _aggregate_championship(all_stats: List[dict], agg: dict) -> dict:
    """Aggregate championship stats."""
    n = agg["num_games"]

    rounds = [s["rounds_played"] for s in all_stats]
    agg["avg_rounds"] = sum(rounds) / n
    agg["min_rounds"] = min(rounds)
    agg["max_rounds"] = max(rounds)

    # Championship win rates
    win_counts = defaultdict(int)
    for s in all_stats:
        win_counts[s["winner"]] += 1
    agg["championship_win_rates"] = {
        pid: count / n for pid, count in sorted(win_counts.items())
    }

    # Average total fatigue
    total_fat = defaultdict(list)
    for s in all_stats:
        for pid, fat in s["total_fatigue"].items():
            total_fat[pid].append(fat)
    agg["avg_total_fatigue"] = {
        pid: sum(vals) / len(vals)
        for pid, vals in sorted(total_fat.items())
    }

    # Aggregate all round-level stats
    all_round_stats = []
    for s in all_stats:
        all_round_stats.extend(s["round_stats"])

    round_agg = _aggregate_rounds(all_round_stats, {"num_games": len(all_round_stats)})
    agg["round_level_stats"] = round_agg

    return agg


# ---------------------------------------------------------------------------
# Report printer
# ---------------------------------------------------------------------------

def print_report(agg: dict, num_players: int):
    """Print formatted simulation report."""
    mode = agg.get("mode", "round")
    n = agg["num_games"]

    print(f"\n{'='*65}")
    print(f"  SUMMIT SCRAMBLE SIMULATION REPORT")
    print(f"  {n} {'championships' if mode == 'championship' else 'rounds'}, "
          f"{num_players} players")
    print(f"{'='*65}")

    if mode == "championship":
        _print_championship_report(agg, num_players)
    else:
        _print_round_report(agg, num_players)


def _print_round_report(agg: dict, num_players: int):
    """Print single-round aggregated report."""

    print(f"\n--- GAME LENGTH ---")
    print(f"  Avg turns:  {agg['avg_turns']:.1f}  (range: {agg['min_turns']}–{agg['max_turns']})")
    print(f"  Avg tricks: {agg['avg_tricks']:.1f}  (range: {agg['min_tricks']}–{agg['max_tricks']})")
    if agg["hit_turn_limit_rate"] > 0:
        print(f"  ⚠️  HIT TURN LIMIT: {agg['hit_turn_limit_rate']:.1%} of games "
              f"({agg['hit_turn_limit_count']} games)")

    print(f"\n--- WIN RATES (1st Place) ---")
    for pid, rate in agg["win_rates"].items():
        bar = "█" * int(rate * 40)
        print(f"  Player {pid}: {rate:.1%}  {bar}")
    # Flag imbalance
    rates = list(agg["win_rates"].values())
    if rates:
        spread = max(rates) - min(rates)
        expected = 1.0 / num_players
        if spread > 0.15:
            print(f"  ⚠️  POSITION IMBALANCE: {spread:.1%} spread "
                  f"(expected ~{expected:.1%} each)")

    print(f"\n--- AVERAGE FINISH POSITION ---")
    for pid, avg_pos in agg.get("avg_finish_position", {}).items():
        print(f"  Player {pid}: {avg_pos:.2f}")

    print(f"\n--- FORMATION USAGE ---")
    for ftype, data in agg.get("formation_usage", {}).items():
        print(f"  {ftype:20s}: {data['total']:6d} ({data['pct']:.1f}%)")

    print(f"\n--- FACTION ABILITIES ---")
    for ability, count in agg.get("ability_usage", {}).items():
        avg = count / agg["num_games"]
        print(f"  {ability:15s}: {count:5d} total ({avg:.1f}/game)")

    print(f"\n--- SPECIAL PLAYS ---")
    print(f"  Confetti Cannons: {agg['avg_cannons_per_game']:.2f}/game "
          f"(in {agg['games_with_cannon']:.1f}% of games)")
    print(f"  Trip-Ups:         {agg['avg_trip_ups_per_game']:.2f}/game "
          f"(in {agg['games_with_trip_up']:.1f}% of games)")

    print(f"\n--- STAGNATION ---")
    print(f"  Avg max stagnation streak: {agg['avg_max_stagnation']:.1f} turns")
    print(f"  Worst stagnation:          {agg['worst_stagnation']} turns")
    if agg["games_with_stagnation_10plus"] > 0:
        print(f"  ⚠️  Games with 10+ stagnation: {agg['games_with_stagnation_10plus']}")

    print(f"\n--- FATIGUE BY POSITION ---")
    for pos, avg_fat in agg.get("avg_fatigue_by_position", {}).items():
        print(f"  Position {pos}: {avg_fat:.1f} Zzz's avg")

    if agg.get("avg_remaining_cards_last", 0) > 0:
        print(f"\n--- LAST PLACE ---")
        print(f"  Avg remaining cards: {agg['avg_remaining_cards_last']:.1f}")
        print(f"  Max remaining cards: {agg['max_remaining_cards_last']}")

    # Flag potential issues
    _flag_issues(agg, num_players)


def _print_championship_report(agg: dict, num_players: int):
    """Print championship report."""
    print(f"\n--- CHAMPIONSHIP LENGTH ---")
    print(f"  Avg rounds: {agg['avg_rounds']:.1f} "
          f"(range: {agg['min_rounds']}–{agg['max_rounds']})")

    print(f"\n--- CHAMPIONSHIP WIN RATES ---")
    for pid, rate in agg["championship_win_rates"].items():
        bar = "█" * int(rate * 40)
        print(f"  Player {pid}: {rate:.1%}  {bar}")

    print(f"\n--- AVERAGE TOTAL FATIGUE ---")
    for pid, avg_fat in agg["avg_total_fatigue"].items():
        print(f"  Player {pid}: {avg_fat:.1f} Zzz's")

    # Print round-level breakdown
    print(f"\n{'─'*65}")
    print(f"  ROUND-LEVEL BREAKDOWN ({agg['round_level_stats']['num_games']} total rounds)")
    print(f"{'─'*65}")
    _print_round_report(agg["round_level_stats"], num_players)


def _flag_issues(agg: dict, num_players: int):
    """Flag potential design issues."""
    issues = []

    # Turn limit hits
    if agg.get("hit_turn_limit_rate", 0) > 0.01:
        issues.append(f"STALEMATE RISK: {agg['hit_turn_limit_rate']:.1%} of games "
                      f"hit the turn limit — possible infinite loops or deadlocks")

    # Position imbalance
    rates = list(agg.get("win_rates", {}).values())
    if rates:
        spread = max(rates) - min(rates)
        if spread > 0.15:
            best_pid = max(agg["win_rates"], key=agg["win_rates"].get)
            worst_pid = min(agg["win_rates"], key=agg["win_rates"].get)
            issues.append(f"POSITION IMBALANCE: Player {best_pid} wins "
                          f"{agg['win_rates'][best_pid]:.1%} vs Player {worst_pid} "
                          f"at {agg['win_rates'][worst_pid]:.1%}")

    # Stagnation
    if agg.get("worst_stagnation", 0) >= 20:
        issues.append(f"SEVERE STAGNATION: worst streak of "
                      f"{agg['worst_stagnation']} turns with no progress")

    # Unused mechanics
    if agg.get("avg_cannons_per_game", 0) == 0:
        issues.append("UNUSED MECHANIC: No Confetti Cannons fired in any game")
    if agg.get("avg_trip_ups_per_game", 0) == 0:
        issues.append("UNUSED MECHANIC: No Trip-Ups in any game")

    # Ability imbalance
    abilities = agg.get("ability_usage", {})
    if abilities:
        max_use = max(abilities.values())
        for ability, count in abilities.items():
            if count < max_use * 0.1:
                issues.append(f"UNDERUSED ABILITY: {ability} triggered only "
                              f"{count} times (vs {max_use} for most used)")

    # Formation dominance
    formations = agg.get("formation_usage", {})
    if formations:
        total = sum(d["total"] for d in formations.values())
        for ftype, data in formations.items():
            if data["pct"] > 80:
                issues.append(f"FORMATION DOMINANCE: {ftype} used {data['pct']:.1f}% "
                              f"of the time — other formations may be too hard to form")
            if data["pct"] < 1 and ftype not in ("confetti_cannon", "trip_up"):
                issues.append(f"UNUSED FORMATION: {ftype} used only {data['pct']:.1f}%")

    if issues:
        print(f"\n{'!'*65}")
        print(f"  POTENTIAL ISSUES DETECTED")
        print(f"{'!'*65}")
        for i, issue in enumerate(issues, 1):
            print(f"  {i}. {issue}")
    else:
        print(f"\n  ✓ No major issues detected")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def load_config():
    """Load config.json from standard locations."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(script_dir, "config.json"),
        os.path.join(script_dir, "..", "config.json"),
    ]
    for c in candidates:
        if os.path.exists(c):
            with open(c) as f:
                return json.load(f)
    print("ERROR: config.json not found")
    sys.exit(1)


def build_player_configs(args, num_players):
    """Build player config dicts from CLI args."""
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
        style_list = ["aggressive", "balanced", "conservative", "rush"]
        configs = [{"skill": 1.0, "style": style_list[i % len(style_list)],
                    "aggression": 0.5}
                   for i in range(num_players)]

    if args.skill:
        skills = [float(s) for s in args.skill.split(",")]
        for i, s in enumerate(skills[:num_players]):
            configs[i]["skill"] = s

    if args.styles:
        styles = args.styles.split(",")
        for i, s in enumerate(styles[:num_players]):
            configs[i]["style"] = s.strip()

    if args.aggression:
        aggs = [float(a) for a in args.aggression.split(",")]
        for i, a in enumerate(aggs[:num_players]):
            configs[i]["aggression"] = a

    return configs


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Summit Scramble Batch Simulator")
    parser.add_argument("-n", "--num-games", type=int, default=200,
                       help="Number of games to simulate (default: 200)")
    parser.add_argument("-p", "--players", type=int, default=4,
                       help="Number of players (3-5, default: 4)")
    parser.add_argument("-s", "--seed", type=int, default=1,
                       help="Starting random seed (default: 1)")
    parser.add_argument("--max-turns", type=int, default=300,
                       help="Max turns per round before abort (default: 300)")
    parser.add_argument("-v", "--verbose", action="store_true",
                       help="Print progress during simulation")
    parser.add_argument("--json", type=str, default=None,
                       help="Export results to JSON file")

    # Game mode
    parser.add_argument("--mode", choices=["round", "championship"],
                       default="round",
                       help="Simulate single rounds or full championships")
    parser.add_argument("--fatigue-limit", type=int, default=30,
                       help="Championship fatigue limit (default: 30)")
    parser.add_argument("--no-mercy", action="store_true",
                       help="Disable mercy rule cap")
    parser.add_argument("--stored-surge", action="store_true",
                       help="Enable Stored Surge advanced rule")

    # Player configuration
    parser.add_argument("--preset", type=str, default=None,
                       choices=["experts", "beginners", "mixed", "styles"],
                       help="Preset player configurations")
    parser.add_argument("--skill", type=str, default=None,
                       help="Comma-separated skill levels (e.g., '1.0,0.5,0.3')")
    parser.add_argument("--styles", type=str, default=None,
                       help="Comma-separated play styles")
    parser.add_argument("--aggression", type=str, default=None,
                       help="Comma-separated aggression levels")

    args = parser.parse_args()

    if args.players < 3 or args.players > 5:
        print("ERROR: Players must be 3-5")
        sys.exit(1)

    config = load_config()
    player_configs = build_player_configs(args, args.players)

    print(f"Running {args.num_games} {args.mode}s with {args.players} players...")
    print(f"Player configs: {player_configs}")

    agg = run_batch(
        config,
        num_games=args.num_games,
        num_players=args.players,
        start_seed=args.seed,
        player_configs=player_configs,
        max_turns=args.max_turns,
        mode=args.mode,
        fatigue_limit=args.fatigue_limit,
        mercy_rule=not args.no_mercy,
        use_stored_surge=args.stored_surge,
        verbose=args.verbose,
    )

    print_report(agg, args.players)

    if args.json:
        with open(args.json, 'w') as f:
            json.dump(agg, f, indent=2, default=str)
        print(f"\nResults saved to {args.json}")
