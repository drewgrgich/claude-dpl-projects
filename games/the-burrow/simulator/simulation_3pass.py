#!/usr/bin/env python3
"""
Simulation for The Burrow - 3 passes per round, 3 cards per round.
Game ends when any burrow is complete (3 rounds to fill 3x3 grid).
This tests the actual rules as written.
"""
from __future__ import annotations
import random
from collections import Counter
from dataclasses import dataclass
from typing import Dict, List, Optional

from cards import Card, build_deck
from game_state import GameState, BurrowGrid, BurrowAI


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


class Simulation3Pass:
    def __init__(self, num_players: int, seed: Optional[int] = None):
        self.num_players = num_players
        self.rng = random.Random(seed)

    def run_game(self, seed: Optional[int] = None) -> SimResult:
        game = GameState(self.num_players, seed=seed)
        game.setup(hand_size=3)

        strategies = [BurrowAI.SUIT_DIVERSE, BurrowAI.CENTER_FOCUS,
                      BurrowAI.SPREAD_EARLY, BurrowAI.GREEDY_HIGH, BurrowAI.BALANCED]
        ais = [
            BurrowAI(
                skill=0.72 + self.rng.random() * 0.16,
                strategy=strategies[i % len(strategies)],
                seed=(seed or 0) * 17 + i * 31 + self.rng.randint(0, 9999)
            )
            for i in range(self.num_players)
        ]

        lead_history = []
        total_doubles = 0

        for round_num in range(1, 10):
            game.round = round_num

            # 3 passes per round
            for pass_num in range(3):
                chosen: Dict[int, Optional[Card]] = {}
                passing: Dict[int, List[Card]] = {}

                for i, p in enumerate(game.players):
                    if not p.hand:
                        chosen[i] = None; passing[i] = []; continue
                    keep_idx = ais[i].choose_card_to_keep(p.hand, p.burrow, round_num)
                    chosen[i] = p.hand[keep_idx]
                    passing[i] = p.hand[:keep_idx] + p.hand[keep_idx+1:]

                new_hands: Dict[int, List[Card]] = {i: [] for i in range(self.num_players)}
                for i in range(self.num_players):
                    from_i = (i + 1) % self.num_players
                    new_hands[i].extend(passing[from_i])

                for i, p in enumerate(game.players):
                    if chosen[i] is not None:
                        p.drafted_this_round.append(chosen[i])
                    p.hand = new_hands[i]

            # After 3 passes, place 3 drafted cards
            for i, p in enumerate(game.players):
                for card in p.drafted_this_round:
                    col = ais[i].choose_column(card, p.burrow, round_num)
                    p.burrow.add_card(card, col)
                p.drafted_this_round = []

            # Track lead
            scores = game.final_scores()
            leaders = sorted(scores.items(), key=lambda x: -x[1])
            lead_history.append(leaders[0][0])

            # Check completion
            if all(p.burrow.is_complete() for p in game.players):
                break

            # Draw 3 new cards per player
            for p in game.players:
                drawn = []
                for _ in range(3):
                    if game.deck:
                        drawn.append(game.deck.pop())
                p.hand.extend(drawn)
                if not game.deck:
                    break

        final_scores = game.final_scores()
        winner = max(final_scores.items(), key=lambda x: x[1])[0]
        ordered = sorted(final_scores.items(), key=lambda x: -x[1])
        win_spread = ordered[0][1] - ordered[1][1] if len(ordered) > 1 else 0

        for p in game.players:
            for col in "ABC":
                if Card.all_same_suit(p.burrow.columns[col]):
                    total_doubles += 1

        lead_changes = sum(1 for i in range(1, len(lead_history))
                          if lead_history[i] != lead_history[i-1])
        first_leader = lead_history[0] if lead_history else winner

        return SimResult(
            winner=winner, scores=[final_scores[i] for i in range(self.num_players)],
            rounds_played=round_num, total_doubles=total_doubles,
            deck_exhausted=len(game.deck) == 0, win_spread=win_spread,
            lead_changes=lead_history, first_leader=first_leader,
        )


def run_games_3pass(num_games: int, num_players: int = 4, seed: int = 42) -> dict:
    results: List[SimResult] = []
    for i in range(num_games):
        sim = Simulation3Pass(num_players, seed=seed + i)
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
    cfb = sum(1 for r in results if r.winner != r.first_leader)
    deck_ex = sum(1 for r in results if r.deck_exhausted) / len(results)
    win_div = len(Counter(r.winner for r in results))
    close = sum(1 for r in results if r.win_spread < 5)

    # Doublerate: fraction of non-empty columns that doubled
    total_cols = 0
    total_doubs = 0
    for r in results:
        for s in r.scores:
            total_cols += 3  # 3 columns per player
    # Approximate
    doublerate = avg_doubles / max(1, total_cols) * 3 if total_cols else 0

    return {
        "avg_rounds": round(avg_rounds, 2),
        "avg_doubles": round(avg_doubles, 2),
        "avg_win_spread": round(avg_spread, 2),
        "avg_lead_changes": round(avg_lead_changes, 2),
        "come_from_behind_wins": cfb,
        "deck_exhaustion_rate": round(deck_ex, 2),
        "winner_diversity": win_div,
        "close_game_rate": round(close / len(results), 2),
        "doublerate": round(avg_doubles / (num_players * 3), 2),
    }
