from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional
import random

SUITS = ["Spades", "Hearts", "Diamonds", "Clubs"]
SUIT_PRIORITY = {"Spades": 0, "Hearts": 1, "Diamonds": 2, "Clubs": 3}
RANK_LABELS = {11: "J", 12: "Q", 13: "K", 14: "A"}


@dataclass(frozen=True)
class Card:
    suit: str
    rank: Optional[int] = None
    is_wild: bool = False

    @property
    def bid_rank(self) -> int:
        return -1 if self.is_wild else int(self.rank)

    @property
    def points(self) -> int:
        return 0 if self.is_wild else int(self.rank)

    @property
    def tie_priority(self) -> int:
        return SUIT_PRIORITY.get(self.suit, 99)

    @property
    def can_bid(self) -> bool:
        return not self.is_wild

    def short(self) -> str:
        if self.is_wild:
            return "W"
        label = RANK_LABELS.get(self.rank, str(self.rank))
        return f"{label}{self.suit[0]}"

    def __repr__(self) -> str:
        return self.short()


class Deck:
    def __init__(self, cards: Optional[List[Card]] = None):
        self.cards = list(cards or [])

    def shuffle(self, rng: random.Random):
        rng.shuffle(self.cards)

    def draw(self, n: int = 1) -> List[Card]:
        drawn = self.cards[:n]
        self.cards = self.cards[n:]
        return drawn

    def draw_one(self) -> Optional[Card]:
        return self.cards.pop(0) if self.cards else None

    def peek(self, n: int = 1) -> List[Card]:
        return self.cards[:n]

    def add_to_bottom(self, cards):
        if isinstance(cards, list):
            self.cards.extend(cards)
        else:
            self.cards.append(cards)

    def clear(self) -> List[Card]:
        out = self.cards[:]
        self.cards = []
        return out

    @property
    def size(self) -> int:
        return len(self.cards)


def build_bid_brawl_deck() -> List[Card]:
    deck: List[Card] = []
    for suit in SUITS:
        for rank in range(2, 15):
            deck.append(Card(suit=suit, rank=rank))
    for _ in range(6):
        deck.append(Card(suit="Wild", is_wild=True))
    return deck
