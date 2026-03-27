#!/usr/bin/env python3
"""Game state for The Burrow - 9 rounds, 1 card per round, 3x3 grid."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import random

from cards import Card, build_deck, ALL_SUITS


@dataclass
class BurrowGrid:
    """3 columns (A/B/C) × 3 rows. Column B gets +5 center bonus."""
    columns: Dict[str, List[Card]] = field(default_factory=lambda: {
        "A": [], "B": [], "C": []
    })

    def add_card(self, card: Card, column: str) -> None:
        if len(self.columns[column]) < 3:
            self.columns[column].append(card)

    def is_complete(self) -> bool:
        return all(len(c) == 3 for c in self.columns.values())

    def all_empty_columns(self) -> List[str]:
        return [col for col in "ABC" if len(self.columns[col]) < 3]

    def score_column(self, col: str) -> int:
        cards = self.columns[col]
        if not cards:
            return 0
        base = sum(c.value for c in cards)
        if Card.all_same_suit(cards):
            base *= 2
        if col == "B":
            base += 5
        return base

    def total_score(self) -> int:
        return sum(self.score_column(col) for col in "ABC")


@dataclass
class Player:
    idx: int
    name: str
    hand: List[Card] = field(default_factory=list)
    drafted_this_round: List[Card] = field(default_factory=list)
    burrow: BurrowGrid = field(default_factory=BurrowGrid)


class GameState:
    """Manages a full game of The Burrow."""

    def __init__(self, num_players: int, seed: Optional[int] = None):
        self.num_players = num_players
        self.rng = random.Random(seed)
        self.seed = seed or 0
        self.round = 0
        self.deck: List[Card] = []
        self.players: List[Player] = []
        self.center_starter: Optional[Card] = None
        self.game_over = False

    def setup(self, hand_size: int = 1) -> None:
        self.deck = build_deck(self.rng.randint(0, 10**9))
        self.rng.shuffle(self.deck)
        names = [f"P{i}" for i in range(self.num_players)]
        self.players = [Player(idx=i, name=n) for i, n in enumerate(names)]
        # Deal initial hand
        for _ in range(hand_size):
            for p in self.players:
                if self.deck:
                    p.hand.append(self.deck.pop())
        if self.num_players < 5 and self.deck:
            self.center_starter = self.deck.pop()
        self.round = 1

    def pass_to(self, player_idx: int) -> int:
        return (player_idx - 1) % self.num_players

    def pass_from(self, player_idx: int) -> int:
        return (player_idx + 1) % self.num_players

    def final_scores(self) -> Dict[int, int]:
        return {p.idx: p.burrow.total_score() for p in self.players}

    def column_doubled(self, player_idx: int, col: str) -> bool:
        p = self.players[player_idx]
        return Card.all_same_suit(p.burrow.columns[col])


class BurrowAI:
    """AI for The Burrow with configurable strategy."""

    SUIT_DIVERSE = "suit_diverse"
    CENTER_FOCUS = "center_focus"
    SPREAD_EARLY = "spread_early"
    GREEDY_HIGH = "greedy_high"
    BALANCED = "balanced"

    STRATEGIES = [SUIT_DIVERSE, CENTER_FOCUS, SPREAD_EARLY, GREEDY_HIGH, BALANCED]

    def __init__(self, skill: float = 0.7, strategy: str = BALANCED, seed: Optional[int] = None):
        self.skill = skill
        self.strategy = strategy
        self.rng = random.Random(seed)

    def choose_card_to_keep(self, hand: List[Card], burrow: BurrowGrid,
                            round_num: int) -> int:
        """Choose which card to keep from hand (0=keep, otherwise pass left)."""
        if len(hand) <= 1:
            return 0
        scored = []
        for i, card in enumerate(hand):
            score = self._card_urgency(card, hand, burrow, round_num)
            scored.append((score, i, card))
        scored.sort(key=lambda x: -x[0])
        if self.rng.random() > self.skill:
            idx = scored[self.rng.randint(0, min(2, len(scored)-1))][1]
        else:
            idx = scored[0][1]
        return idx

    def choose_column(self, card: Card, burrow: BurrowGrid, round_num: int) -> str:
        """Choose which column to place a card in."""
        candidates = burrow.all_empty_columns()
        if not candidates:
            return "A"
        best_col, best_score = candidates[0], -999.0
        for col in candidates:
            score = self._col_score(card, burrow, col, round_num)
            if score > best_score:
                best_score = score
                best_col = col
        return best_col

    def _card_urgency(self, card: Card, hand: List[Card], burrow: BurrowGrid,
                      round_num: int) -> float:
        if self.strategy == self.SUIT_DIVERSE:
            return self._suit_diverse(card, hand, burrow, round_num)
        elif self.strategy == self.CENTER_FOCUS:
            return self._center_focus(card, hand, burrow, round_num)
        elif self.strategy == self.SPREAD_EARLY:
            return self._spread_early(card, hand, burrow, round_num)
        elif self.strategy == self.GREEDY_HIGH:
            return self._greedy_high(card, hand, burrow, round_num)
        return self._balanced(card, hand, burrow, round_num)

    def _suit_diverse(self, card: Card, hand: List[Card], burrow: BurrowGrid,
                       round_num: int) -> float:
        score = 0.0
        for col in "ABC":
            col_cards = burrow.columns[col]
            if len(col_cards) >= 3:
                continue
            suits_in_col = {s for c in col_cards for s in c.suits}
            overlap = set(card.suits) & suits_in_col
            if len(col_cards) == 0:
                score += 2.0
                if len(set(card.suits)) == 2:
                    score += 2.5
            elif len(col_cards) == 1:
                score += 10.0 if overlap else 1.0
            elif len(col_cards) == 2:
                score += 14.0 if overlap else 1.5
        return max(0.1, score + self.rng.gauss(0, 0.3))

    def _center_focus(self, card: Card, hand: List[Card], burrow: BurrowGrid,
                        round_num: int) -> float:
        score = 0.0
        b_cards = burrow.columns["B"]
        if len(b_cards) < 3:
            overlap = set(card.suits) & {s for c in b_cards for s in c.suits}
            score += 8.0 if len(b_cards) == 0 else (12.0 if overlap else 2.0)
            if len(b_cards) == 2 and overlap:
                score += 15.0
        for col in ["A", "C"]:
            col_cards = burrow.columns[col]
            if len(col_cards) < 3 and set(card.suits) & {s for c in col_cards for s in c.suits}:
                score += 5.0 if len(col_cards) <= 1 else 9.0
        return max(0.1, score + card.value * 0.2 + self.rng.gauss(0, 0.3))

    def _spread_early(self, card: Card, hand: List[Card], burrow: BurrowGrid,
                        round_num: int) -> float:
        score = 0.0
        for col in "ABC":
            if len(burrow.columns[col]) >= 2:
                score -= 2.0
            elif len(burrow.columns[col]) == 2:
                if set(card.suits) & {s for c in burrow.columns[col] for s in c.suits}:
                    score += 12.0
        score += card.value * 0.4
        return max(0.1, score + self.rng.gauss(0, 0.4))

    def _greedy_high(self, card: Card, hand: List[Card], burrow: BurrowGrid,
                       round_num: int) -> float:
        score = card.value * 1.2
        for col in "ABC":
            col_cards = burrow.columns[col]
            if len(col_cards) < 3 and set(card.suits) & {s for c in col_cards for s in c.suits}:
                score += 8.0 if len(col_cards) == 2 else 4.0
        return max(0.1, score + self.rng.gauss(0, 0.25))

    def _balanced(self, card: Card, hand: List[Card], burrow: BurrowGrid,
                     round_num: int) -> float:
        score = card.value * 0.5
        for col in "ABC":
            col_cards = burrow.columns[col]
            if len(col_cards) >= 3:
                continue
            overlap = set(card.suits) & {s for c in col_cards for s in c.suits}
            if len(col_cards) == 0:
                score += 2.0
                if len(set(card.suits)) == 2:
                    score += 1.5
            elif len(col_cards) == 1:
                score += 7.0 if overlap else 1.0
            elif len(col_cards) == 2:
                score += 12.0 if overlap else 1.5
        if len(burrow.columns["B"]) < 3:
            if set(card.suits) & {s for c in burrow.columns["B"] for s in c.suits}:
                score += 2.5
        return max(0.1, score + self.rng.gauss(0, 0.3))

    def _col_score(self, card: Card, burrow: BurrowGrid, col: str, round_num: int) -> float:
        col_cards = burrow.columns[col]
        if len(col_cards) >= 3:
            return -999.0
        suits_in_col = {s for c in col_cards for s in c.suits}
        overlap = set(card.suits) & suits_in_col
        score = 0.0
        if len(col_cards) == 0:
            score = 3.0
            if len(set(card.suits)) == 2:
                score += 2.5
        elif len(col_cards) == 1:
            score = 14.0 if overlap else 1.5
        elif len(col_cards) == 2:
            score = 20.0 if overlap else 2.0
        if col == "B":
            score += 2.5
        score += card.value * 0.3
        return score + self.rng.gauss(0, 0.2)
