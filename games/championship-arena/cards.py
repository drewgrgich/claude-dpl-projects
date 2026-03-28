"""Cards and Deck for Championship Arena."""

import random
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class HMCard:
    suit: str
    rank: int

    def __repr__(self):
        return f"{self.suit[0]}{self.rank}"


class Deck:
    def __init__(self, suits: List[str], rank_min: int, rank_max: int):
        self.cards: List[HMCard] = []
        for suit in suits:
            for rank in range(rank_min, rank_max + 1):
                self.cards.append(HMCard(suit=suit, rank=rank))
        self._shuffle()

    def _shuffle(self):
        random.shuffle(self.cards)

    def draw(self, n: int = 1) -> List[HMCard]:
        """Draw n cards from the deck. Returns empty list if not enough cards."""
        if n > len(self.cards):
            return []
        drawn = self.cards[:n]
        self.cards = self.cards[n:]
        return drawn

    def add_to_bottom(self, cards: List[HMCard]):
        """Add cards to bottom of deck."""
        self.cards.extend(cards)

    def shuffle_discard_back(self, discards: List[HMCard]):
        """Shuffle discard pile back into deck."""
        self.cards.extend(discards)
        self._shuffle()

    def __len__(self):
        return len(self.cards)

    def is_empty(self):
        return len(self.cards) == 0
