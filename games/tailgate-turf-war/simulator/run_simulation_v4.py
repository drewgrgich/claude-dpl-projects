#!/usr/bin/env python3
"""
Batch simulation runner for the v0.1 custom deck zone-control game.

Runs N AI-vs-AI games and produces a comprehensive balance report covering:
  - Win rate balance (seat fairness)
  - Score distribution (blowout vs close games)
  - Strength statistics
  - Action card impact (Shield saves, Bomb kills, Swap uses, Bounty risk/reward)
  - Condition card effects
  - Strategy diversity (style matchup testing)
  - Home Field and Mascot combo rates

Usage:
  python run_simulation_v4.py
  python run_simulation_v4.py -n 2000
  python run_simulation_v4.py -n 1000 --players 4
  python run_simulation_v4.py -n 500 --players 2 --json results.json
"""

import argparse
import json
import math
import os
import statistics
import sys
from collections import defaultdict
from typing import List, Dict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cards_v4 import Card
from game_state_v4 import GameStateV4
from ai_player_v4 import AIPlayerV4, STYLE_PROFILES


# ─── SIMULATION ENGINE ──────────────────────────────────────────────────────

def run_single_game(num_players: int, seed: int, styles: List[str],
                    config: dict = None) -> dict:
    """Play one complete game and return the result dict."""
    game = GameStateV4(num_players, seed=seed, config=config)

    ais = []
    for pid in range(num_players):
        style = styles[pid % len(styles)]
        ais.append(AIPlayerV4(
            player_id=pid, skill=1.0, style=style,
            rng_seed=seed * 100 + pid
        ))

    def deployment_fn(player, gs, round_num):
        return ais[player.id].choose_deployment(player, gs, round_num)

    def pass_fn(player, gs, pass_count):
        return ais[player.id].choose_pass(player, gs, pass_count)

    return game.play_game(deployment_fn, pass_fn)


def run_batch(num_games: int, num_players: int, styles: List[str],
              start_seed: int = 1, config: dict = None) -> List[dict]:
    """Run a batch of games and return all result dicts."""
    results = []
    for i in range(num_games):
        seed = start_seed + i
        result = run_single_game(num_players, seed, styles, config)
        results.append(result)
    return results


# ─── AGGREGATION ─────────────────────────────────────────────────────────────

def aggregate(results: List[dict], num_players: int) -> dict:
    """Aggregate game results into summary statistics."""
    n = len(results)
    wins = defaultdict(float)
    all_scores = defaultdict(list)
    score_spreads = []
    all_strength = []
    all_cpz = []
    total_hf = 0
    total_mascot = 0
    zone_wins = defaultdict(int)
    ties = 0

    # Action card stats
    action_plays = defaultdict(int)
    total_shield_saves = 0
    total_bomb_kills = 0
    total_swap_uses = 0
    total_bounty_wins = 0
    total_bounty_fails = 0
    total_dud_plays = 0
    total_lone_wolf = 0

    # Condition tracking
    condition_counts = defaultdict(int)

    # Cards played / remaining
    total_cards_played = defaultdict(list)
    total_cards_remaining = defaultdict(list)

    # Contested zone tracking
    contested_counts = defaultdict(int)  # num_players_at_zone -> count

    for r in results:
        winner = r["winner"]
        if isinstance(winner, list):
            ties += 1
            for w in winner:
                wins[w] += 1.0 / len(winner)
        else:
            wins[winner] += 1

        scores = list(r["scores"].values())
        for pid, s in r["scores"].items():
            all_scores[pid].append(s)
        score_spreads.append(max(scores) - min(scores))

        all_strength.extend(r.get("strength_values", []))
        all_cpz.extend(r.get("cards_per_zone", []))
        total_hf += r.get("home_field_triggers", 0)
        total_mascot += r.get("mascot_combos", 0)

        for pid, zw in r["zones_won"].items():
            zone_wins[pid] += zw

        # Action stats
        for action_type, count in r.get("action_plays", {}).items():
            action_plays[action_type] += count
        total_shield_saves += r.get("shield_saves", 0)
        total_bomb_kills += r.get("bomb_kills", 0)
        total_swap_uses += r.get("swap_uses", 0)
        total_bounty_wins += r.get("bounty_wins", 0)
        total_bounty_fails += r.get("bounty_fails", 0)
        total_dud_plays += r.get("dud_plays", 0)
        total_lone_wolf += r.get("lone_wolf_zones", 0)

        # Condition cards
        for cond in r.get("condition_cards", []):
            condition_counts[cond] += 1

        # Cards played/remaining
        for pid, cp in r.get("cards_played", {}).items():
            total_cards_played[pid].append(cp)
        for pid, cr in r.get("cards_remaining", {}).items():
            total_cards_remaining[pid].append(cr)

        # Contested zones
        for c in r.get("contested_zones", []):
            contested_counts[c] += 1

    # Strength percentiles
    sorted_str = sorted(all_strength) if all_strength else [0]
    p10 = sorted_str[len(sorted_str) // 10] if all_strength else 0
    p25 = sorted_str[len(sorted_str) // 4] if all_strength else 0
    p50 = sorted_str[len(sorted_str) // 2] if all_strength else 0
    p75 = sorted_str[3 * len(sorted_str) // 4] if all_strength else 0
    p90 = sorted_str[9 * len(sorted_str) // 10] if all_strength else 0

    fair = 1.0 / num_players
    win_rates = {pid: wins[pid] / n for pid in range(num_players)}
    max_seat_dev = max(abs(wr - fair) for wr in win_rates.values())

    return {
        "num_games": n,
        "num_players": num_players,

        # Balance
        "win_rates": win_rates,
        "max_seat_deviation": max_seat_dev,
        "tie_rate": ties / n,
        "avg_zones_won": {pid: zone_wins[pid] / n for pid in range(num_players)},

        # Scores
        "avg_score": statistics.mean([s for scores in all_scores.values() for s in scores]),
        "avg_winner_score": statistics.mean([max(r["scores"].values()) for r in results]),
        "avg_loser_score": statistics.mean([min(r["scores"].values()) for r in results]),
        "avg_score_spread": statistics.mean(score_spreads),
        "score_spread_std": statistics.stdev(score_spreads) if len(score_spreads) > 1 else 0,
        "score_spread_max": max(score_spreads),

        # Strength
        "strength_mean": statistics.mean(all_strength) if all_strength else 0,
        "strength_std": statistics.stdev(all_strength) if len(all_strength) > 1 else 0,
        "strength_p10": p10,
        "strength_p25": p25,
        "strength_p50": p50,
        "strength_p75": p75,
        "strength_p90": p90,
        "strength_max": max(all_strength) if all_strength else 0,
        "strength_min": min(all_strength) if all_strength else 0,

        # Features
        "hf_per_game": total_hf / n,
        "mascot_per_game": total_mascot / n,
        "cpz_mean": statistics.mean(all_cpz) if all_cpz else 0,

        # Action cards
        "action_plays_per_game": {k: v / n for k, v in action_plays.items()},
        "shield_saves_per_game": total_shield_saves / n,
        "bomb_kills_per_game": total_bomb_kills / n,
        "swap_uses_per_game": total_swap_uses / n,
        "bounty_wins_per_game": total_bounty_wins / n,
        "bounty_fails_per_game": total_bounty_fails / n,
        "bounty_success_rate": (total_bounty_wins / max(1, total_bounty_wins + total_bounty_fails)),
        "dud_plays_per_game": total_dud_plays / n,
        "lone_wolf_per_game": total_lone_wolf / n,

        # Condition cards
        "condition_frequency": dict(condition_counts),

        # Cards management
        "avg_cards_played": {pid: statistics.mean(v) for pid, v in total_cards_played.items()},
        "avg_cards_remaining": {pid: statistics.mean(v) for pid, v in total_cards_remaining.items()},

        # Zone contestation
        "contested_distribution": dict(contested_counts),
    }


# ─── STYLE MATCHUP ──────────────────────────────────────────────────────────

def run_style_matchup(num_games: int, num_players: int,
                      start_seed: int = 10001, config: dict = None) -> dict:
    """Run games rotating all 5 styles to check for dominant strategies."""
    styles = list(STYLE_PROFILES.keys())
    style_wins = defaultdict(float)
    style_scores = defaultdict(list)

    for i in range(num_games):
        seed = start_seed + i
        game_styles = [styles[(i + j) % len(styles)] for j in range(num_players)]

        game = GameStateV4(num_players, seed=seed, config=config)
        ais = [AIPlayerV4(pid, skill=1.0, style=game_styles[pid],
                          rng_seed=seed * 100 + pid)
               for pid in range(num_players)]

        def deployment_fn(player, gs, round_num):
            return ais[player.id].choose_deployment(player, gs, round_num)

        def pass_fn(player, gs, pass_count):
            return ais[player.id].choose_pass(player, gs, pass_count)

        result = game.play_game(deployment_fn, pass_fn)
        winner = result["winner"]

        if isinstance(winner, list):
            for w in winner:
                style_wins[game_styles[w]] += 1.0 / len(winner)
        else:
            style_wins[game_styles[winner]] += 1

        for pid, score in result["scores"].items():
            style_scores[game_styles[pid]].append(score)

    return {
        "win_rates": {s: style_wins[s] / num_games for s in styles},
        "avg_scores": {s: statistics.mean(style_scores[s]) if style_scores[s] else 0
                       for s in styles},
    }


# ─── PLAYER COUNT SWEEP ─────────────────────────────────────────────────────

def run_player_count_sweep(num_games: int, config: dict = None) -> dict:
    """Run games at 2-5 players and compare key metrics."""
    sweep = {}
    base_styles = ["balanced", "balanced", "balanced", "balanced", "balanced"]

    for np in range(2, 6):
        print(f"    {np}P...", end="", flush=True)
        results = run_batch(num_games, np, base_styles[:np], config=config)
        agg = aggregate(results, np)
        sweep[np] = {
            "avg_score": agg["avg_score"],
            "avg_winner_score": agg["avg_winner_score"],
            "avg_score_spread": agg["avg_score_spread"],
            "tie_rate": agg["tie_rate"],
            "max_seat_deviation": agg["max_seat_deviation"],
            "hf_per_game": agg["hf_per_game"],
            "mascot_per_game": agg["mascot_per_game"],
            "cpz_mean": agg["cpz_mean"],
            "strength_mean": agg["strength_mean"],
            "strength_std": agg["strength_std"],
        }
        print(f" done (avg spread={agg['avg_score_spread']:.1f})", flush=True)

    return sweep


# ─── REPORTING ───────────────────────────────────────────────────────────────

def print_report(agg: dict, style_data: dict = None, sweep: dict = None):
    """Print a comprehensive simulation report."""
    print()
    print("=" * 70)
    print("  v0.1 GAME SIMULATION REPORT")
    print(f"  {agg['num_games']} games × {agg['num_players']} players")
    print("=" * 70)

    # ── BALANCE ──
    print("\n── SEAT BALANCE ──")
    for pid, wr in sorted(agg["win_rates"].items()):
        fair = 1.0 / agg["num_players"]
        bar = "█" * int(wr * 50)
        dev = wr - fair
        print(f"  P{pid}: {wr:6.1%}  {bar}  ({dev:+.1%})")
    print(f"  Max seat deviation: {agg['max_seat_deviation']:.1%}")
    print(f"  Tie rate: {agg['tie_rate']:.1%}")

    # ── SCORES ──
    print("\n── SCORES ──")
    print(f"  Avg score (all):     {agg['avg_score']:.1f}")
    print(f"  Avg winner score:    {agg['avg_winner_score']:.1f}")
    print(f"  Avg loser score:     {agg['avg_loser_score']:.1f}")
    print(f"  Avg score spread:    {agg['avg_score_spread']:.1f} (±{agg['score_spread_std']:.1f})")
    print(f"  Max score spread:    {agg['score_spread_max']}")

    # ── STRENGTH ──
    print("\n── STRENGTH DISTRIBUTION ──")
    print(f"  Mean:   {agg['strength_mean']:.1f}")
    print(f"  Std:    {agg['strength_std']:.1f}")
    print(f"  10th:   {agg['strength_p10']}")
    print(f"  25th:   {agg['strength_p25']}")
    print(f"  50th:   {agg['strength_p50']}")
    print(f"  75th:   {agg['strength_p75']}")
    print(f"  90th:   {agg['strength_p90']}")
    print(f"  Range:  {agg['strength_min']} – {agg['strength_max']}")

    # ── ACTION CARDS ──
    print("\n── ACTION CARD IMPACT ──")
    for action, rate in sorted(agg["action_plays_per_game"].items()):
        print(f"  {action.title():8s} played: {rate:.2f}/game")
    print(f"  Shield saves:    {agg['shield_saves_per_game']:.2f}/game")
    print(f"  Bomb kills:      {agg['bomb_kills_per_game']:.2f}/game")
    print(f"  Swap uses:       {agg['swap_uses_per_game']:.2f}/game")
    print(f"  Bounty wins:     {agg['bounty_wins_per_game']:.2f}/game")
    print(f"  Bounty fails:    {agg['bounty_fails_per_game']:.2f}/game")
    print(f"  Bounty success:  {agg['bounty_success_rate']:.1%}")
    print(f"  Dud plays:       {agg['dud_plays_per_game']:.2f}/game")

    # ── FEATURES ──
    print("\n── GAME FEATURES ──")
    print(f"  Home Field triggers:  {agg['hf_per_game']:.1f}/game")
    print(f"  Mascot combos:        {agg['mascot_per_game']:.1f}/game")
    print(f"  Avg cards/zone play:  {agg['cpz_mean']:.2f}")
    print(f"  Lone Wolf zones:      {agg['lone_wolf_per_game']:.2f}/game")

    # ── ZONE CONTESTATION ──
    print("\n── ZONE CONTESTATION ──")
    total_zone_plays = sum(agg["contested_distribution"].values())
    for num_players_at, count in sorted(agg["contested_distribution"].items()):
        pct = count / total_zone_plays if total_zone_plays > 0 else 0
        label = {0: "Empty", 1: "Uncontested"}.get(num_players_at,
                                                     f"{num_players_at}-way fight")
        print(f"  {label:16s}: {pct:5.1%} ({count})")

    # ── CARDS MANAGEMENT ──
    print("\n── CARD MANAGEMENT ──")
    for pid in sorted(agg["avg_cards_played"].keys()):
        played = agg["avg_cards_played"][pid]
        remaining = agg["avg_cards_remaining"][pid]
        print(f"  P{pid}: played {played:.1f}, remaining {remaining:.1f}")

    # ── CONDITION CARDS ──
    if agg["condition_frequency"]:
        print("\n── CONDITION CARD APPEARANCES ──")
        for cond, count in sorted(agg["condition_frequency"].items(),
                                   key=lambda x: -x[1]):
            print(f"  {cond:22s}: {count:4d} ({count/agg['num_games']:.1%} of games)")

    # ── STYLE MATCHUP ──
    if style_data:
        print("\n── STRATEGY MATCHUP (style win rates) ──")
        fair = 1.0 / agg["num_players"]
        for style, wr in sorted(style_data["win_rates"].items(), key=lambda x: -x[1]):
            avg_s = style_data["avg_scores"].get(style, 0)
            dev = wr - fair
            flag = " ⚠️" if abs(dev) > 0.05 else ""
            print(f"  {style:12s}: {wr:6.1%} (avg VP: {avg_s:.1f}){flag}")

        max_style = max(style_data["win_rates"], key=style_data["win_rates"].get)
        min_style = min(style_data["win_rates"], key=style_data["win_rates"].get)
        spread = style_data["win_rates"][max_style] - style_data["win_rates"][min_style]
        if spread > 0.10:
            print(f"\n  ⚠️  Dominant strategy detected: {max_style} ({style_data['win_rates'][max_style]:.1%}) "
                  f"vs {min_style} ({style_data['win_rates'][min_style]:.1%})")
        else:
            print(f"\n  ✅ Style spread {spread:.1%} — balanced")

    # ── PLAYER COUNT SWEEP ──
    if sweep:
        print("\n── PLAYER COUNT COMPARISON ──")
        header = f"{'Metric':<25}"
        for np in sorted(sweep.keys()):
            header += f"  {np}P{' ':>7}"
        print(header)
        print("-" * (25 + 11 * len(sweep)))

        metrics = [
            ("Avg score", "avg_score", ".1f"),
            ("Avg winner score", "avg_winner_score", ".1f"),
            ("Score spread", "avg_score_spread", ".1f"),
            ("Tie rate", "tie_rate", ".1%"),
            ("Seat deviation", "max_seat_deviation", ".1%"),
            ("Home field/game", "hf_per_game", ".1f"),
            ("Mascot combos/game", "mascot_per_game", ".1f"),
            ("Cards/zone play", "cpz_mean", ".2f"),
            ("Strength mean", "strength_mean", ".1f"),
            ("Strength std", "strength_std", ".1f"),
        ]
        for label, key, fmt in metrics:
            line = f"  {label:<23}"
            for np in sorted(sweep.keys()):
                val = sweep[np][key]
                line += f"  {val:>9{fmt}}"
            print(line)

    # ── HEALTH CHECK ──
    print("\n── HEALTH CHECK ──")
    issues = []
    strengths = []

    if agg["max_seat_deviation"] > 0.05:
        issues.append(f"Seat imbalance: {agg['max_seat_deviation']:.1%} deviation")
    else:
        strengths.append(f"Fair seating ({agg['max_seat_deviation']:.1%} max deviation)")

    if agg["avg_score_spread"] > 25:
        issues.append(f"Blowouts too common (avg spread {agg['avg_score_spread']:.1f})")
    elif agg["avg_score_spread"] < 3:
        issues.append(f"Games too close (avg spread {agg['avg_score_spread']:.1f})")
    else:
        strengths.append(f"Healthy score spread ({agg['avg_score_spread']:.1f})")

    if agg["strength_std"] < 2.0:
        issues.append("Low strength variance — plays feel similar")
    else:
        strengths.append(f"Good strength variance (σ={agg['strength_std']:.1f})")

    if agg["hf_per_game"] < 1.0:
        issues.append(f"Home field too rare ({agg['hf_per_game']:.1f}/game)")
    else:
        strengths.append(f"Home field active ({agg['hf_per_game']:.1f}/game)")

    if agg["mascot_per_game"] < 0.3:
        issues.append(f"Mascot combos too rare ({agg['mascot_per_game']:.1f}/game)")
    else:
        strengths.append(f"Mascot combos firing ({agg['mascot_per_game']:.1f}/game)")

    bounty_sr = agg["bounty_success_rate"]
    if bounty_sr > 0.80:
        issues.append(f"Bounty too safe ({bounty_sr:.0%} success) — not enough risk")
    elif bounty_sr < 0.20:
        issues.append(f"Bounty too risky ({bounty_sr:.0%} success) — never worth playing")
    else:
        strengths.append(f"Bounty risk/reward balanced ({bounty_sr:.0%} success)")

    if style_data:
        max_wr = max(style_data["win_rates"].values())
        min_wr = min(style_data["win_rates"].values())
        if max_wr - min_wr > 0.10:
            max_s = max(style_data["win_rates"], key=style_data["win_rates"].get)
            issues.append(f"Dominant strategy: {max_s} ({max_wr:.0%})")
        else:
            strengths.append(f"No dominant strategy (spread {max_wr - min_wr:.0%})")

    for s in strengths:
        print(f"  ✅ {s}")
    for i in issues:
        print(f"  ⚠️  {i}")

    print(f"\n{'=' * 70}")


# ─── MAIN ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="v0.1 Game Simulator — batch runner and balance report"
    )
    parser.add_argument("-n", "--num-games", type=int, default=1000,
                        help="Number of games to simulate (default: 1000)")
    parser.add_argument("-p", "--players", type=int, default=3,
                        help="Number of players (default: 3)")
    parser.add_argument("--style-games", type=int, default=500,
                        help="Games for style matchup test (default: 500)")
    parser.add_argument("--sweep", action="store_true",
                        help="Run player count sweep (2-5 players)")
    parser.add_argument("--sweep-games", type=int, default=200,
                        help="Games per player count in sweep (default: 200)")
    parser.add_argument("--json", type=str, default=None,
                        help="Export results to JSON file")
    parser.add_argument("--seed", type=int, default=1,
                        help="Starting seed (default: 1)")
    parser.add_argument("--styles", type=str, nargs="+",
                        default=["balanced", "balanced", "balanced", "balanced", "balanced"],
                        help="AI styles for each seat")
    args = parser.parse_args()

    print(f"v0.1 Game Simulator")
    print(f"Running {args.num_games} games × {args.players} players...")
    print()

    # Main batch
    print("  Main batch...", end="", flush=True)
    styles = args.styles[:args.players]
    results = run_batch(args.num_games, args.players, styles,
                        start_seed=args.seed)
    agg = aggregate(results, args.players)
    print(f" done (avg score={agg['avg_score']:.1f}, spread={agg['avg_score_spread']:.1f})")

    # Style matchup
    print(f"  Style matchup ({args.style_games} games)...", end="", flush=True)
    style_data = run_style_matchup(args.style_games, args.players)
    dominant = max(style_data["win_rates"], key=style_data["win_rates"].get)
    print(f" done (top={dominant} {style_data['win_rates'][dominant]:.1%})")

    # Player count sweep
    sweep = None
    if args.sweep:
        print(f"  Player count sweep ({args.sweep_games} games each)...")
        sweep = run_player_count_sweep(args.sweep_games)
        print("  Sweep complete.")

    # Print report
    print_report(agg, style_data, sweep)

    # JSON export
    if args.json:
        export = {
            "summary": agg,
            "style_matchup": style_data,
            "player_sweep": sweep,
        }
        # Convert any non-serializable keys
        def fix_keys(d):
            if isinstance(d, dict):
                return {str(k): fix_keys(v) for k, v in d.items()}
            elif isinstance(d, list):
                return [fix_keys(x) for x in d]
            return d

        with open(args.json, "w") as f:
            json.dump(fix_keys(export), f, indent=2)
        print(f"\nResults exported to {args.json}")


if __name__ == "__main__":
    main()
