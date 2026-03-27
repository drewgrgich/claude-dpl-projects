"""Card definitions and Deck class for Tailgate Turf War."""

from dataclasses import dataclass, field
from typing import List, Optional
import random


# Faction constants
FACTIONS = ["RED", "ORANGE", "YELLOW", "GREEN", "BLUE", "PURPLE"]
FACTION_ORDER = {f: i for i, f in enumerate(FACTIONS)}  # ROYGBP order


@dataclass
class Card:
    """A single H&M card."""
    faction: str   # RED, ORANGE, YELLOW, GREEN, BLUE, PURPLE
    rank: int      # 0-10

    @property
    def is_natural(self) -> bool:
        """Ranks 1-9 are 'natural' cards that trigger mishaps."""
        return 1 <= self.rank <= 9

    @property
    def is_mascot(self) -> bool:
        """Rank 0 is the Mascot."""
        return self.rank == 0

    @property
    def is_superstar(self) -> bool:
        """Rank 10 is the Superstar (or highest rank in custom distributions)."""
        return self.rank == 10

    def is_superstar_for(self, max_rank: int) -> bool:
        """Check if this card is the superstar for a given max rank."""
        return self.rank == max_rank

    @property
    def is_wild(self) -> bool:
        """Ranks 0 and 10 are 'wild' cards (don't trigger mishaps alone)."""
        return self.rank == 0 or self.rank == 10

    @property
    def id(self) -> str:
        return f"{self.faction}-{self.rank}"

    def __hash__(self):
        return hash(self.id)

    def __eq__(self, other):
        if not isinstance(other, Card):
            return False
        return self.faction == other.faction and self.rank == other.rank

    def __repr__(self):
        names = {0: "Mascot", 10: "Superstar"}
        name = names.get(self.rank, str(self.rank))
        return f"{self.faction[:3]}-{name}"

    def __lt__(self, other):
        """Sort by faction order then rank."""
        if self.faction != other.faction:
            return FACTION_ORDER[self.faction] < FACTION_ORDER[other.faction]
        return self.rank < other.rank


class Deck:
    """Generic ordered collection of cards — draw pile, hand, etc."""

    def __init__(self, cards: List[Card] = None):
        self.cards: List[Card] = list(cards) if cards else []

    def shuffle(self, rng: random.Random):
        rng.shuffle(self.cards)

    def draw(self, n: int = 1) -> List[Card]:
        drawn = self.cards[:n]
        self.cards = self.cards[n:]
        return drawn

    def draw_one(self) -> Optional[Card]:
        return self.cards.pop(0) if self.cards else None

    def add_to_bottom(self, cards):
        if isinstance(cards, list):
            self.cards.extend(cards)
        else:
            self.cards.append(cards)

    def add_to_top(self, cards):
        if isinstance(cards, list):
            self.cards = cards + self.cards
        else:
            self.cards.insert(0, cards)

    def peek(self, n: int = 1) -> List[Card]:
        return self.cards[:n]

    @property
    def size(self) -> int:
        return len(self.cards)

    @property
    def empty(self) -> bool:
        return len(self.cards) == 0

    def __repr__(self):
        return f"Deck({self.size} cards)"


def build_full_deck(factions: List[str] = None,
                    ranks_per_faction: List[int] = None) -> List[Card]:
    """Build a deck with configurable factions and rank distribution.

    Args:
        factions: List of faction names (default: FACTIONS — 6 colors)
        ranks_per_faction: List of ranks each faction gets (default: 0-10).
            Duplicates allowed, e.g. [1,1,2,2,3,3,4,4,5,6,7,8] for compressed.
            Rank 0 = Mascot, highest rank = Superstar (wild).
    """
    factions = factions or FACTIONS
    ranks = ranks_per_faction or list(range(0, 11))
    cards = []
    for faction in factions:
        for rank in ranks:
            cards.append(Card(faction=faction, rank=rank))
    return cards


def build_zone_cards() -> List[Card]:
    """Build the 6 zone marker cards (one per faction, rank -1 as sentinel)."""
    return [Card(faction=f, rank=-1) for f in FACTIONS]
