#!/usr/bin/env python3
"""
Zone Scramble — Batch simulation runner.

Runs N AI-vs-AI games and reports balance metrics.
"""

from __future__ import annotations
import argparse
import json
import os
import sys
from collections import defaultdict
from typing import Dict, List, Optional

from cards import Card, build_full_deck
from game_state import GameState
from ai_player import HeuristicAI, STYLE_PROFILES


# ---------------------------------------------------------------------------
# Single game runner
# ---------------------------------------------------------------------------

def run_single_game(config: dict, seed: int, max_turns: int = 200,
                    player_configs: Optional[List[dict]] = None,
                    verbose: bool = False) -> dict:
    """Play one complete game, return stats dict."""

    game = GameState(config, seed=seed)

    # Create AIs
    ais = []
    for i in range(2):
        pc = player_configs[i] if player_configs and i < len(player_configs) else {}
        ais.append(HeuristicAI(
            skill=pc.get("skill", 1.0),
            style=pc.get("style", "balanced"),
            aggression=pc.get("aggression", 0.5),
            rng_seed=seed * 100 + i,
        ))

    # Setup: faction draft
    def draft_fn(pid, available, num_to_pick, gs):
        return ais[pid].choose_factions(pid, available, num_to_pick, gs)

    game.full_setup(draft_fn=draft_fn)

    # Tracking
    action_counts = defaultdict(lambda: defaultdict(int))
    signature_counts = defaultdict(lambda: defaultdict(int))
    arenas_won = defaultdict(int)
    roar_triggers = defaultdict(int)  # who triggered roars
    fumble_counts = defaultdict(int)
    bench_counts = defaultdict(int)
    chameleon_plays = defaultdict(int)
    round_scores = []  # per-round VP snapshots
    stagnation_turns = 0
    max_stagnation_streak = 0
    current_stagnation = 0

    turn_count = 0

    while not game.game_over and turn_count < max_turns:
        player = game.get_current_player()
        ai = ais[player.id]
        pid = player.id

        # Green peek (before playing)
        if player.has_faction("GREEN") and not game.draw_pile.empty:
            top = game.draw_pile.peek(1)[0]
            should_discard = ai.decide_green_peek(player, top, game)
            game.action_green_peek(player, should_discard)

        # Choose action
        action = ai.choose_action(player, game)
        action_type = action["type"]
        action_counts[pid][action_type] += 1

        if action_type == "play_monster":
            card = action["card"]
            arena_name = action["arena"]

            if card.is_chameleon:
                chameleon_plays[pid] += 1

            result = game.action_play_monster(
                player, card, arena_name,
                chameleon_turf_choice=action.get("chameleon_turf_choice"),
            )

            if result["success"]:
                current_stagnation = 0

                # Blue personality: bounce decision
                if card.faction == "BLUE" and player.has_faction("BLUE"):
                    bounce = ai.choose_blue_bounce(player, game, arena_name, card)
                    if bounce:
                        game.action_blue_bounce(player, arena_name, bounce)

                # Signature move decision
                sig = ai.choose_signature(player, game, card, arena_name)
                if sig:
                    sig_type = sig["type"]
                    signature_counts[pid][sig_type] += 1

                    if sig_type == "sig_red":
                        game.sig_red_heroic_intervention(
                            player, sig["source_arena"],
                            sig["target_arena"], sig["monster"]
                        )
                    elif sig_type == "sig_yellow":
                        game.sig_yellow_double_install(
                            player, sig["arena"], sig["card"],
                            sig.get("chameleon_turf_choice")
                        )
                    elif sig_type == "sig_green":
                        r = game.sig_green_scheduled_outcome(player)
                        if r["success"] and len(r["drawn"]) == 2:
                            # Keep higher rank
                            drawn = r["drawn"]
                            keep = max(drawn, key=lambda c: c.rank)
                            discard = [c for c in drawn if c != keep][0]
                            game.sig_green_keep_choice(player, keep, discard)
                        elif r["success"] and len(r["drawn"]) == 1:
                            player.hand.append(r["drawn"][0])
                    elif sig_type == "sig_blue":
                        game.sig_blue_swap(
                            player, sig["arena"],
                            sig["my_card"], sig["their_card"]
                        )
                    elif sig_type == "sig_purple":
                        game.sig_purple_rewind(player)

                if result.get("roar"):
                    roar = result["roar"]
                    roar_triggers[pid] += 1
                    if roar["winner"] is not None:
                        arenas_won[roar["winner"]] += 1
            else:
                current_stagnation += 1

        elif action_type == "fumble":
            fumble_counts[pid] += 1
            game.action_fumble(player, action["discard"])
            current_stagnation += 1

        elif action_type == "bench":
            bench_counts[pid] += 1
            if action.get("discard") and action["discard"] in player.hand:
                game.action_bench(player, action["discard"])
            current_stagnation += 1

        if current_stagnation > 0:
            stagnation_turns += 1
        max_stagnation_streak = max(max_stagnation_streak, current_stagnation)

        # End turn
        end_result = game.end_turn()

        if end_result.get("round_ended"):
            # Track round-end scores
            snapshot = {pid: game.players[pid].total_vp for pid in range(2)}
            round_scores.append(snapshot)

            # Track arena wins from end-of-round scoring
            for arena_res in end_result.get("arena_scores", []):
                if arena_res["winner"] is not None:
                    arenas_won[arena_res["winner"]] += 1

        turn_count += 1

    # Compile stats
    stats = {
        "seed": seed,
        "winner": game.winner,
        "turns": turn_count,
        "aborted": turn_count >= max_turns,
        "final_vp": {pid: game.players[pid].total_vp for pid in range(2)},
        "factions": {pid: game.players[pid].command_factions for pid in range(2)},
        "action_counts": dict(action_counts),
        "signature_counts": dict(signature_counts),
        "arenas_won": dict(arenas_won),
        "roar_triggers": dict(roar_triggers),
        "fumble_counts": dict(fumble_counts),
        "bench_counts": dict(bench_counts),
        "chameleon_plays": dict(chameleon_plays),
        "trophy_count": {pid: len(game.players[pid].trophy_pile) for pid in range(2)},
        "stagnation_turns": stagnation_turns,
        "max_stagnation_streak": max_stagnation_streak,
        "round_scores": round_scores,
    }
    return stats


# ---------------------------------------------------------------------------
# Batch runner
# ---------------------------------------------------------------------------

def run_batch(config: dict, num_games: int, start_seed: int = 1,
              max_turns: int = 200,
              player_configs: Optional[List[dict]] = None,
              verbose: bool = False) -> dict:
    """Run N games and aggregate statistics."""
    all_stats = []
    for i in range(num_games):
        s = run_single_game(config, seed=start_seed + i,
                            max_turns=max_turns,
                            player_configs=player_configs,
                            verbose=verbose)
        all_stats.append(s)
        if verbose and (i + 1) % 100 == 0:
            print(f"  ... {i + 1}/{num_games} games completed")

    return aggregate_stats(all_stats, num_games)


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def aggregate_stats(all_stats: List[dict], num_games: int) -> dict:
    """Aggregate per-game stats into a summary report."""
    wins = defaultdict(int)
    ties = 0
    total_turns = []
    aborted = 0
    vp_totals = defaultdict(list)
    action_totals = defaultdict(lambda: defaultdict(int))
    sig_totals = defaultdict(lambda: defaultdict(int))
    arenas_won_total = defaultdict(int)
    roar_total = defaultdict(int)
    fumble_total = defaultdict(int)
    bench_total = defaultdict(int)
    chameleon_total = defaultdict(int)
    trophy_total = defaultdict(int)
    stagnation_list = []
    max_stag_list = []

    # Faction pair win tracking
    faction_pair_wins = defaultdict(lambda: {"wins": 0, "games": 0})

    for s in all_stats:
        if s["winner"] is not None:
            wins[s["winner"]] += 1
        else:
            ties += 1

        total_turns.append(s["turns"])
        if s["aborted"]:
            aborted += 1

        for pid in range(2):
            vp_totals[pid].append(s["final_vp"].get(pid, 0))
            for atype, count in s["action_counts"].get(pid, {}).items():
                action_totals[pid][atype] += count
            for stype, count in s["signature_counts"].get(pid, {}).items():
                sig_totals[pid][stype] += count

        for pid_str, count in s["arenas_won"].items():
            arenas_won_total[int(pid_str)] += count
        for pid_str, count in s["roar_triggers"].items():
            roar_total[int(pid_str)] += count
        for pid_str, count in s["fumble_counts"].items():
            fumble_total[int(pid_str)] += count
        for pid_str, count in s["bench_counts"].items():
            bench_total[int(pid_str)] += count
        for pid_str, count in s["chameleon_plays"].items():
            chameleon_total[int(pid_str)] += count
        for pid_str, count in s["trophy_count"].items():
            trophy_total[int(pid_str)] += count

        stagnation_list.append(s["stagnation_turns"])
        max_stag_list.append(s["max_stagnation_streak"])

        # Track faction pair performance
        for pid in range(2):
            pair = tuple(sorted(s["factions"].get(pid, [])))
            faction_pair_wins[pair]["games"] += 1
            if s["winner"] == pid:
                faction_pair_wins[pair]["wins"] += 1

    avg_turns = sum(total_turns) / len(total_turns) if total_turns else 0
    min_turns = min(total_turns) if total_turns else 0
    max_turns_val = max(total_turns) if total_turns else 0

    return {
        "num_games": num_games,
        "wins": dict(wins),
        "ties": ties,
        "win_rates": {pid: wins[pid] / num_games for pid in range(2)},
        "tie_rate": ties / num_games,
        "avg_turns": avg_turns,
        "min_turns": min_turns,
        "max_turns": max_turns_val,
        "aborted": aborted,
        "abort_rate": aborted / num_games,
        "avg_vp": {pid: sum(vp_totals[pid]) / num_games for pid in range(2)},
        "vp_std": {pid: _std(vp_totals[pid]) for pid in range(2)},
        "action_totals": {pid: dict(v) for pid, v in action_totals.items()},
        "signature_totals": {pid: dict(v) for pid, v in sig_totals.items()},
        "arenas_won_total": dict(arenas_won_total),
        "avg_arenas_won": {pid: arenas_won_total[pid] / num_games for pid in range(2)},
        "roar_triggers": dict(roar_total),
        "fumble_total": dict(fumble_total),
        "avg_fumbles": {pid: fumble_total[pid] / num_games for pid in range(2)},
        "bench_total": dict(bench_total),
        "avg_benches": {pid: bench_total[pid] / num_games for pid in range(2)},
        "chameleon_total": dict(chameleon_total),
        "avg_chameleons": {pid: chameleon_total[pid] / num_games for pid in range(2)},
        "trophy_total": dict(trophy_total),
        "avg_stagnation": sum(stagnation_list) / len(stagnation_list) if stagnation_list else 0,
        "max_stagnation_streak": max(max_stag_list) if max_stag_list else 0,
        "avg_max_stagnation": sum(max_stag_list) / len(max_stag_list) if max_stag_list else 0,
        "faction_pair_performance": {
            str(k): {"win_rate": v["wins"] / v["games"] if v["games"] > 0 else 0,
                      "games": v["games"]}
            for k, v in sorted(faction_pair_wins.items(), key=lambda x: -x[1]["games"])
        },
    }


def _std(values: list) -> float:
    if not values:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    return variance ** 0.5


# ---------------------------------------------------------------------------
# Report printer
# ---------------------------------------------------------------------------

def print_report(agg: dict):
    """Print a formatted simulation report."""
    n = agg["num_games"]

    print(f"\n{'='*64}")
    print(f"  ZONE SCRAMBLE SIMULATION REPORT — {n:,} games")
    print(f"{'='*64}")

    # Game health
    print(f"\n--- Game Health ---")
    print(f"  Average game length:    {agg['avg_turns']:.1f} turns")
    print(f"  Range:                  {agg['min_turns']}–{agg['max_turns']} turns")
    print(f"  Abort rate (hit limit): {agg['abort_rate']:.1%}")

    # Win rates
    print(f"\n--- Win Rates ---")
    for pid in range(2):
        print(f"  Player {pid} (start {'1st' if pid == 0 else '2nd'}): "
              f"{agg['win_rates'][pid]:.1%}  ({agg['wins'].get(pid, 0)} wins)")
    print(f"  Ties:         {agg['tie_rate']:.1%}  ({agg['ties']} ties)")

    # VP distribution
    print(f"\n--- VP Distribution ---")
    for pid in range(2):
        print(f"  P{pid} avg VP:  {agg['avg_vp'][pid]:.2f}  (std: {agg['vp_std'][pid]:.2f})")

    # Arena performance
    print(f"\n--- Arena Performance ---")
    for pid in range(2):
        print(f"  P{pid} avg arenas won/game: {agg['avg_arenas_won'][pid]:.2f}")

    # Action breakdown
    print(f"\n--- Action Breakdown (per game avg) ---")
    for pid in range(2):
        actions = agg["action_totals"].get(pid, {})
        parts = []
        for atype in ["play_monster", "fumble", "bench"]:
            count = actions.get(atype, 0)
            parts.append(f"{atype}: {count / n:.1f}")
        print(f"  P{pid}: {' | '.join(parts)}")

    # Signature moves
    print(f"\n--- Signature Move Usage (total across all games) ---")
    for pid in range(2):
        sigs = agg["signature_totals"].get(pid, {})
        if sigs:
            parts = [f"{k}: {v}" for k, v in sorted(sigs.items())]
            print(f"  P{pid}: {' | '.join(parts)}")
        else:
            print(f"  P{pid}: none")

    # Stagnation
    print(f"\n--- Stagnation ---")
    print(f"  Avg stagnation turns/game:  {agg['avg_stagnation']:.1f}")
    print(f"  Worst stagnation streak:    {agg['max_stagnation_streak']}")
    print(f"  Avg worst streak:           {agg['avg_max_stagnation']:.1f}")

    # Chameleon + fumble + bench
    print(f"\n--- Special Mechanics (per game avg) ---")
    for pid in range(2):
        print(f"  P{pid}: chameleons {agg['avg_chameleons'][pid]:.1f} | "
              f"fumbles {agg['avg_fumbles'][pid]:.1f} | "
              f"benches {agg['avg_benches'][pid]:.1f}")

    # Faction pair performance
    print(f"\n--- Faction Pair Win Rates ---")
    fp = agg["faction_pair_performance"]
    for pair_str, data in list(fp.items())[:10]:
        print(f"  {pair_str}: {data['win_rate']:.1%} over {data['games']} games")

    # Alerts
    print(f"\n--- Alerts ---")
    alerts = []
    spread = abs(agg["win_rates"][0] - agg["win_rates"][1])
    if spread > 0.10:
        alerts.append(f"⚠ First-player advantage: {spread:.1%} win rate spread")
    if agg["abort_rate"] > 0.02:
        alerts.append(f"⚠ High abort rate: {agg['abort_rate']:.1%}")
    if agg["avg_max_stagnation"] > 5:
        alerts.append(f"⚠ High stagnation: avg worst streak {agg['avg_max_stagnation']:.1f}")
    for pid in range(2):
        if agg["avg_benches"][pid] > 2.0:
            alerts.append(f"⚠ P{pid} benched {agg['avg_benches'][pid]:.1f} times/game")

    if not alerts:
        print("  ✓ No major issues detected")
    else:
        for a in alerts:
            print(f"  {a}")

    print(f"\n{'='*64}\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def load_config(path: str = None) -> dict:
    if path is None:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        path = os.path.join(script_dir, "config.json")
    with open(path) as f:
        return json.load(f)


def build_player_configs(args) -> List[dict]:
    configs = [{}, {}]

    if args.preset == "experts":
        configs = [{"skill": 1.0, "style": "balanced"} for _ in range(2)]
    elif args.preset == "beginners":
        configs = [{"skill": 0.3, "style": "balanced"} for _ in range(2)]
    elif args.preset == "mixed":
        configs = [{"skill": 1.0, "style": "balanced"},
                   {"skill": 0.3, "style": "balanced"}]
    elif args.preset == "styles":
        styles = list(STYLE_PROFILES.keys())
        configs = [{"skill": 1.0, "style": styles[i % len(styles)]} for i in range(2)]

    if args.skill:
        skills = [float(s) for s in args.skill.split(",")]
        for i, s in enumerate(skills[:2]):
            configs[i]["skill"] = s

    if args.styles:
        styles = args.styles.split(",")
        for i, s in enumerate(styles[:2]):
            configs[i]["style"] = s.strip()

    if args.aggression:
        aggs = [float(a) for a in args.aggression.split(",")]
        for i, a in enumerate(aggs[:2]):
            configs[i]["aggression"] = a

    return configs


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Zone Scramble batch simulation runner"
    )
    parser.add_argument("-n", "--num-games", type=int, default=500,
                        help="Number of games to simulate (default: 500)")
    parser.add_argument("-s", "--seed", type=int, default=1,
                        help="Starting random seed (default: 1)")
    parser.add_argument("--max-turns", type=int, default=200,
                        help="Max turns before aborting a game (default: 200)")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Print progress updates")
    parser.add_argument("--config", type=str, default=None,
                        help="Path to config.json")
    parser.add_argument("--json", type=str, default=None,
                        help="Export results to JSON file")

    # Player configs
    parser.add_argument("--preset", type=str, default=None,
                        choices=["experts", "beginners", "mixed", "styles"],
                        help="Preset player configurations")
    parser.add_argument("--skill", type=str, default=None,
                        help="Comma-separated skill levels (0.0-1.0)")
    parser.add_argument("--styles", type=str, default=None,
                        help="Comma-separated play styles")
    parser.add_argument("--aggression", type=str, default=None,
                        help="Comma-separated aggression levels (0.0-1.0)")

    # Rule overrides
    parser.add_argument("--arena-threshold", type=int, default=None,
                        help="Override arena roar threshold")
    parser.add_argument("--max-chameleons", type=int, default=None,
                        help="Override max chameleons per round")
    parser.add_argument("--max-fumbles", type=int, default=None,
                        help="Override max fumbles per round")
    parser.add_argument("--pop-bonus", action="store_true",
                        help="Enable Pop Bonus mode")
    parser.add_argument("--high-dopamine", action="store_true",
                        help="Enable High-Dopamine mode")
    parser.add_argument("--pop-tax", action="store_true",
                        help="Enable Pop Tax mode")

    args = parser.parse_args()

    # Load config
    config = load_config(args.config)

    # Apply overrides
    if args.arena_threshold is not None:
        config["game_rules"]["arena_roar_threshold"] = args.arena_threshold
    if args.max_chameleons is not None:
        config["game_rules"]["max_chameleons_per_round"] = args.max_chameleons
    if args.max_fumbles is not None:
        config["game_rules"]["max_fumbles_per_round"] = args.max_fumbles
    if args.pop_bonus:
        config["optional_modes"]["pop_bonus"] = True
    if args.high_dopamine:
        config["optional_modes"]["high_dopamine"] = True
    if args.pop_tax:
        config["optional_modes"]["pop_tax"] = True

    player_configs = build_player_configs(args)

    print(f"Running {args.num_games} games (seed {args.seed})...")
    print(f"Player configs: {player_configs}")

    agg = run_batch(config, args.num_games, start_seed=args.seed,
                    max_turns=args.max_turns,
                    player_configs=player_configs,
                    verbose=args.verbose)

    print_report(agg)

    if args.json:
        with open(args.json, 'w') as f:
            json.dump(agg, f, indent=2, default=str)
        print(f"Results saved to {args.json}")
