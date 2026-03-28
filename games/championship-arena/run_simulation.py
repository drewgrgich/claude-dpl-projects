"""Batch simulation runner for Championship Arena."""

import json
import random
from collections import defaultdict
from typing import Dict, List, Tuple
from simulate_game import simulate_game


def run_batch(
    num_games: int,
    num_players: int,
    config: dict
) -> Dict:
    """Run batch of games and collect statistics."""
    wins = defaultdict(int)
    total_fp = defaultdict(list)
    round_counts = []
    sweep_count = 0
    spectators_impact = 0

    for i in range(num_games):
        # Set seed for reproducibility in aggregate
        random.seed(i * 1000 + num_players)

        winner, num_rounds, players = simulate_game(num_players, config)

        # Track wins
        if winner:
            wins[winner.id] += 1

        # Track FP
        for p in players:
            total_fp[p.id].append(p.fp)

        round_counts.append(num_rounds)

    # Compute win rates
    win_rates = {pid: count / num_games * 100 for pid, count in wins.items()}

    # Average scores
    avg_scores = {}
    for pid, fp_list in total_fp.items():
        avg_scores[pid] = sum(fp_list) / len(fp_list) if fp_list else 0

    # Overall average final FP
    all_fp = [fp for fp_list in total_fp.values() for fp in fp_list]
    overall_avg_fp = sum(all_fp) / len(all_fp) if all_fp else 0

    # Average rounds
    avg_rounds = sum(round_counts) / len(round_counts) if round_counts else 0

    return {
        "num_games": num_games,
        "num_players": num_players,
        "win_rates": win_rates,
        "avg_scores": avg_scores,
        "avg_rounds": avg_rounds,
        "all_final_fp": all_fp,
        "round_counts": round_counts,
    }


def print_results(results: Dict):
    """Print batch simulation results."""
    print(f"\n{'='*50}")
    print(f"  {results['num_players']}-PLAYER GAMES")
    print(f"{'='*50}")
    print(f"  Games played: {results['num_games']}")
    print(f"  Avg rounds: {results['avg_rounds']:.1f}")
    print(f"  Overall avg final FP: {sum(results['all_final_fp'])/len(results['all_final_fp']):.1f}")
    print(f"\n  Win rates:")
    for pid, rate in sorted(results['win_rates'].items()):
        print(f"    Player {pid}: {rate:.1f}%")
    print(f"\n  Avg scores:")
    for pid, score in sorted(results['avg_scores'].items()):
        print(f"    Player {pid}: {score:.1f} FP")


def main():
    with open("config.json") as f:
        config = json.load(f)

    num_games = 250

    print("CHAMPIONSHIP ARENA — SIMULATION BATCH")
    print(f"Running {num_games} games per player count...\n")

    all_results = {}
    for num_players in [2, 3, 4]:
        results = run_batch(num_games, num_players, config)
        all_results[num_players] = results
        print_results(results)

    # Summary across all player counts
    print(f"\n{'='*50}")
    print("  OVERALL SUMMARY")
    print(f"{'='*50}")
    for num_players, results in all_results.items():
        print(f"  {num_players}p: avg {results['avg_rounds']:.1f} rounds, "
              f"avg final FP {sum(results['all_final_fp'])/len(results['all_final_fp']):.1f}")


if __name__ == "__main__":
    main()
