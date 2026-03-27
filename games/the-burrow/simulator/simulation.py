#!/usr/bin/env python3
"""
Simulation runner for The Burrow.
9 rounds, 1 card per round (wheel draft, 1 pass), 3x3 burrow.
"""
from __future__ import annotations
import argparse
import random
from collections import Counter
from dataclasses import dataclass
from typing import Dict, List, Optional

from cards import Card, build_deck, ALL_SUITS
from game_state import GameState, Player, BurrowGrid, BurrowAI


@dataclass
class SimResult:
    winner: int
    scores: List[int]
    rounds_played: int
    total_doubles: int
    deck_exhausted: bool
    win_spread: int
    lead_changes: List[int]
    first_leader: int
    doublerate: float  # fraction of columns that doubled


class Simulation:
    def __init__(self, num_players: int, seed: Optional[int] = None):
        self.num_players = num_players
        self.rng = random.Random(seed)

    def run_game(self, seed: Optional[int] = None) -> SimResult:
        game = GameState(self.num_players, seed=seed)
        game.setup()

        strategies = [
            BurrowAI.SUIT_DIVERSE, BurrowAI.CENTER_FOCUS,
            BurrowAI.SPREAD_EARLY, BurrowAI.GREEDY_HIGH, BurrowAI.BALANCED,
        ]
        ais = [
            BurrowAI(
                skill=0.72 + self.rng.random() * 0.16,
                strategy=strategies[i % len(strategies)],
                seed=(seed or 0) * 17 + i * 31 + self.rng.randint(0, 9999)
            )
            for i in range(self.num_players)
        ]

        lead_history = []
        col_doubles_total = 0
        total_col_slots = 0

        for round_num in range(1, 10):
            game.round = round_num

            # Each player chooses 1 card from hand to keep; pass rest left simultaneously
            # Then receive from right
            chosen: Dict[int, Card] = {}
            passing: Dict[int, List[Card]] = {}

            for i, p in enumerate(game.players):
                if not p.hand:
                    chosen[i] = None
                    passing[i] = []
                    continue
                # Choose card to keep
                keep_idx = ais[i].choose_card_to_keep(p.hand, p.burrow, round_num)
                chosen[i] = p.hand[keep_idx]
                passing[i] = p.hand[:keep_idx] + p.hand[keep_idx+1:]

            # Build new hands: player i receives from player (i+1)%n
            new_hands: Dict[int, List[Card]] = {i: [] for i in range(self.num_players)}
            for i in range(self.num_players):
                from_i = (i + 1) % self.num_players
                new_hands[i].extend(passing[from_i])

            # Place kept card in burrow, receive new hand
            for i, p in enumerate(game.players):
                if chosen[i] is not None:
                    col = ais[i].choose_column(chosen[i], p.burrow, round_num)
                    p.burrow.add_card(chosen[i], col)
                p.hand = new_hands[i]

            # Track lead
            scores = game.final_scores()
            leaders = sorted(scores.items(), key=lambda x: -x[1])
            lead_history.append(leaders[0][0])

            # Check completion
            if all(p.burrow.is_complete() for p in game.players):
                break

            # Draw 1 new card for each player
            for p in game.players:
                if game.deck:
                    p.hand.append(game.deck.pop())

            if all(not p.hand for p in game.players):
                break

        # Final scoring
        final_scores = game.final_scores()
        winner = max(final_scores.items(), key=lambda x: x[1])[0]
        ordered = sorted(final_scores.items(), key=lambda x: -x[1])
        win_spread = ordered[0][1] - ordered[1][1] if len(ordered) > 1 else 0

        # Count doubling stats
        total_doubles = 0
        total_cols_with_cards = 0
        for p in game.players:
            for col in "ABC":
                col_cards = p.burrow.columns[col]
                if col_cards:
                    total_cols_with_cards += 1
                    if Card.all_same_suit(col_cards):
                        total_doubles += 1

        doublerate = total_doubles / max(1, total_cols_with_cards)

        lead_changes = sum(1 for i in range(1, len(lead_history))
                          if lead_history[i] != lead_history[i-1])
        first_leader = lead_history[0] if lead_history else winner

        return SimResult(
            winner=winner,
            scores=[final_scores[i] for i in range(self.num_players)],
            rounds_played=round_num,
            total_doubles=total_doubles,
            deck_exhausted=len(game.deck) == 0,
            win_spread=win_spread,
            lead_changes=lead_history,
            first_leader=first_leader,
            doublerate=doublerate,
        )


def run_games(num_games: int, num_players: int = 4, seed: int = 42) -> dict:
    results: List[SimResult] = []
    for i in range(num_games):
        sim = Simulation(num_players, seed=seed + i)
        result = sim.run_game(seed=seed + i)
        results.append(result)

    avg_rounds = sum(r.rounds_played for r in results) / len(results)
    avg_doubles = sum(r.total_doubles for r in results) / len(results)
    avg_spread = sum(r.win_spread for r in results) / len(results)
    avg_lead_changes = sum(
        sum(1 for i in range(1, len(r.lead_changes))
            if r.lead_changes[i] != r.lead_changes[i-1])
        for r in results
    ) / len(results)
    come_from_behind = sum(1 for r in results if r.winner != r.first_leader)
    deck_exhausted_rate = sum(1 for r in results if r.deck_exhausted) / len(results)
    win_counter = Counter(r.winner for r in results)
    winner_diversity = len(win_counter)

    close_games = sum(1 for r in results if r.win_spread < 5)

    return {
        "avg_rounds": round(avg_rounds, 2),
        "avg_doubles": round(avg_doubles, 2),
        "avg_win_spread": round(avg_spread, 2),
        "avg_lead_changes": round(avg_lead_changes, 2),
        "come_from_behind_wins": come_from_behind,
        "deck_exhaustion_rate": round(deck_exhausted_rate, 2),
        "winner_diversity": winner_diversity,
        "close_game_rate": round(close_games / len(results), 2),
        "doublerate": round(sum(r.doublerate for r in results) / len(results), 2),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--games", type=int, default=250)
    parser.add_argument("--players", type=int, default=4)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    result = run_games(args.games, args.players, args.seed)
    print(f"Games: {args.games} x {args.players}P")
    for k, v in result.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
