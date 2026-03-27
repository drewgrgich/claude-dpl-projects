#!/usr/bin/env python3
"""Card definitions for The Burrow."""
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Optional, Tuple

ALL_SUITS = ["Hearts", "Diamonds", "Clubs", "Spades", "Moons", "Stars"]
RANK_MAX = 10


def rank_value(rank: int) -> int:
    return min(rank, 10)


@dataclass(frozen=True)
class Card:
    rank: int
    suits: Tuple[str, ...]

    @property
    def is_split(self) -> bool:
        return len(self.suits) == 2

    @property
    def primary_suit(self) -> str:
        return self.suits[0]

    @property
    def value(self) -> int:
        return rank_value(self.rank)

    def shares_suit(self, other: Card) -> bool:
        return bool(set(self.suits) & set(other.suits))

    @staticmethod
    def all_same_suit(cards: List[Card]) -> bool:
        if not cards:
            return True
        for suit in ALL_SUITS:
            if all(suit in card.suits for card in cards):
                return True
        return False

    def __repr__(self) -> str:
        if self.is_split:
            return f"{self.rank}{self.primary_suit[0]}{self.suits[1][0]}"
        return f"{self.rank}{self.primary_suit[0]}"


def build_deck(seed: Optional[int] = None) -> List[Card]:
    import random
    rng = random.Random(seed)
    deck: List[Card] = []
    for suit in ALL_SUITS:
        for rank in range(RANK_MAX + 1):
            deck.append(Card(rank=rank, suits=(suit,)))
    split_combos = [
        (5, "Hearts", "Diamonds"), (5, "Clubs", "Spades"), (5, "Moons", "Stars"),
        (3, "Hearts", "Clubs"), (3, "Diamonds", "Spades"), (3, "Moons", "Hearts"),
        (7, "Hearts", "Stars"), (7, "Diamonds", "Moons"), (7, "Clubs", "Spades"),
        (9, "Hearts", "Spades"), (9, "Diamonds", "Clubs"), (9, "Moons", "Stars"),
        (1, "Hearts", "Diamonds"), (1, "Clubs", "Moons"), (2, "Spades", "Stars"),
        (4, "Hearts", "Moons"), (6, "Diamonds", "Clubs"), (8, "Spades", "Hearts"),
        (0, "Moons", "Stars"), (10, "Diamonds", "Stars"),
    ]
    for rank, s1, s2 in split_combos:
        deck.append(Card(rank=rank, suits=(s1, s2)))
    rng.shuffle(deck)
    return deck
