"""
cards.py — HMCard and Deck for Whistle Stop
Deck: 4 factions × ranks 0-10 (44) + wild 0s (11) + wild 10s (11) = 66
Plus 10 Station marker cards = 76 total
"""

import random
from dataclasses import dataclass
from typing import Optional

RANKS = list(range(11))  # 0-10
FACTIONS = ["red", "blue", "green", "yellow"]
WILD_0_COUNT = 11
WILD_10_COUNT = 11


@dataclass
class HMCard:
    """
    A single card in Whistle Stop.
    - rank: 0-10
    - faction: 'red', 'blue', 'green', 'yellow', or None (wild)
    - is_wild: bool
    """
    rank: int
    faction: Optional[str] = None  # None means wild
    is_wild: bool = False

    def __repr__(self):
        if self.is_wild:
            return f"Wild{'0' if self.rank == 0 else '10'}"
        return f"{self.faction.capitalize()} {self.rank}"

    def get_effective_rank(self, declared_rank: Optional[int] = None) -> int:
        """For wild 0s, can be declared as a different rank."""
        return declared_rank if declared_rank is not None else self.rank

    def get_effective_faction(self, declared_faction: Optional[str] = None) -> Optional[str]:
        """For wild 0s, can be declared as a different faction."""
        if self.is_wild:
            return declared_faction
        return self.faction

    def score_multiplier(self) -> float:
        """Wild 10s give ×2 score. Red gives ×2 VP on all scoring."""
        return 2.0 if (self.is_wild and self.rank == 10) else 1.0

    def movement_steps(self, declared_rank: Optional[int] = None) -> int:
        """How many steps this card lets you move."""
        return declared_rank if declared_rank is not None else self.rank


class Deck:
    """66-card Whistle Stop deck (44 faction + 22 wild)."""

    def __init__(self, seed: Optional[int] = None):
        self.seed = seed
        self.rng = random.Random(seed)
        self._reset()

    def _reset(self):
        self.cards = []
        # 4 factions × 11 ranks = 44 cards
        for faction in FACTIONS:
            for rank in RANKS:
                self.cards.append(HMCard(rank=rank, faction=faction, is_wild=False))
        # 11 wild 0s (factionless, rank 0)
        for _ in range(WILD_0_COUNT):
            self.cards.append(HMCard(rank=0, faction=None, is_wild=True))
        # 11 wild 10s (factionless, rank 10)
        for _ in range(WILD_10_COUNT):
            self.cards.append(HMCard(rank=10, faction=None, is_wild=True))
        self.rng.shuffle(self.cards)
        self._index = 0

    def draw(self, n: int = 1):
        """Draw n cards. Raises IndexError if not enough cards."""
        if self._index + n > len(self.cards):
            raise IndexError(f"Drawing {n} cards but only {len(self.cards) - self._index} left")
        drawn = self.cards[self._index:self._index + n]
        self._index += n
        return drawn

    def cards_remaining(self) -> int:
        return len(self.cards) - self._index

    def is_exhausted(self) -> bool:
        return self._index >= len(self.cards)

    def reset(self):
        """Reset and reshuffle the deck."""
        self._reset()
