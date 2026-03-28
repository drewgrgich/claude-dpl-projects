"""
run_simulation.py — Batch runner for Whistle Stop simulation
Runs 250 games × 2/3/4 players and collects statistics.
"""

import random
import json
from typing import Dict, List, Tuple
from collections import defaultdict
from simulate_game import play_game, create_game
from game_state import GameState


def run_batch(
    num_players: int,
    num_games: int = 250,
    seed_start: int = 42
) -> Dict:
    """
    Run `num_games` simulations with `num_players`.
    Returns aggregate statistics.
    """
    total_rounds = []
    final_scores = []
    winners = defaultdict(int)
    comeback_wins = 0  # winner wasn't leading at any point
    first_to_station = 0  # did the station placer win?
    blocking_events = 0
    fun_rounds = 0  # rounds where 2+ players scored VP

    for game_idx in range(num_games):
        seed = seed_start + game_idx

        # All AI
        gs, results = play_game(
            num_players=num_players,
            ai_player_ids=list(range(num_players)),
            seed=seed,
            verbose=False
        )

        total_rounds.append(gs.round_number)
        final_scores.append([p.score for p in gs.players])

        # Winner tracking
        winner_id = gs.winner_id
        winners[winner_id] += 1

        # Was winner trailing at any point?
        # Simple heuristic: if winner's final position is not the furthest
        winner_player = gs.player_by_id(winner_id)
        max_pos = max(p.position for p in gs.players)
        if winner_player.position < max_pos:
            comeback_wins += 1

        # Did station placer win?
        if gs.station_placer_id == winner_id:
            first_to_station += 1

        # Blocking: did anyone's placement affect another's movement?
        for result in results:
            if len(result.placements) >= 2:
                # Check if multiple players placed cards that could block
                blocking_events += 1

        # Fun rounds: multiple players scored VP in same round
        for result in results:
            scoring_players = [pid for pid, vp in result.scoring if vp > 0]
            if len(scoring_players) >= 2:
                fun_rounds += 1

    # Aggregate
    avg_rounds = sum(total_rounds) / len(total_rounds) if total_rounds else 0
    all_scores_flat = [s for fs in final_scores for s in fs]
    avg_score = sum(all_scores_flat) / len(all_scores_flat) if all_scores_flat else 0

    # Win rate spread
    win_rates = {pid: count / num_games for pid, count in winners.items()}
    win_rate_spread = max(win_rates.values()) - min(win_rates.values()) if win_rates else 0

    comeback_rate = comeback_wins / num_games if num_games > 0 else 0
    station_placer_winrate = first_to_station / num_games if num_games > 0 else 0
    avg_fun_rounds = fun_rounds / num_games if num_games > 0 else 0
    blocking_rate = blocking_events / num_games if num_games > 0 else 0

    return {
        "num_players": num_players,
        "num_games": num_games,
        "avg_rounds": avg_rounds,
        "avg_score": avg_score,
        "win_rates": dict(win_rates),
        "win_rate_spread": win_rate_spread,
        "comeback_rate": comeback_rate,
        "station_placer_winrate": station_placer_winrate,
        "blocking_rate": blocking_rate,
        "avg_fun_rounds": avg_fun_rounds,
    }


def main():
    results = {}
    for num_players in [2, 3, 4]:
        print(f"Running {num_players} players × 250 games...")
        r = run_batch(num_players, num_games=250)
        results[num_players] = r
        print(f"  Avg rounds: {r['avg_rounds']:.1f}")
        print(f"  Avg score: {r['avg_score']:.1f}")
        print(f"  Win rate spread: {r['win_rate_spread']:.3f}")
        print(f"  Comeback rate: {r['comeback_rate']:.3f}")
        print(f"  Fun rounds: {r['avg_fun_rounds']:.1f}")
        print()

    # Save results
    with open("simulation_results.json", "w") as f:
        json.dump(results, f, indent=2)
    print("Results saved to simulation_results.json")

    return results


if __name__ == "__main__":
    main()
