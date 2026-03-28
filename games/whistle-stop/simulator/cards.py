"""Card dataclasses and Deck container for Whistle Stop."""

from dataclasses import dataclass, field
from typing import List, Optional
import random


@dataclass
class Card:
    """A single Whistle Stop card."""
    faction: str       # RED, ORANGE, YELLOW, GREEN, BLUE, PURPLE
    rank: int          # 0-10
    placed_by: int = -1  # Player ID who placed this on the route (-1 = unplaced)

    @property
    def is_wild(self) -> bool:
        """Rank 0 and 10 are wild (count as any faction for requirements)."""
        return self.rank in (0, 10)

    @property
    def id(self) -> str:
        return f"{self.faction}-{self.rank}"

    def __hash__(self):
        return hash((self.faction, self.rank))

    def __eq__(self, other):
        if not isinstance(other, Card):
            return False
        return self.faction == other.faction and self.rank == other.rank

    def __repr__(self):
        wild_tag = "W" if self.is_wild else ""
        return f"{self.faction[0]}{self.rank}{wild_tag}"


class Deck:
    """Generic card container — draw pile, hand, discard, route."""

    def __init__(self, cards: list = None):
        self.cards: List[Card] = list(cards) if cards else []

    def shuffle(self, rng: random.Random = None):
        if rng:
            rng.shuffle(self.cards)
        else:
            random.shuffle(self.cards)

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

    def peek(self, n: int = 1) -> list:
        return self.cards[:n]

    @property
    def size(self) -> int:
        return len(self.cards)

    @property
    def empty(self) -> bool:
        return len(self.cards) == 0


def build_deck(config: dict) -> List[Card]:
    """Build the full 66-card Whistle Stop deck from config."""
    cards = []
    factions = config["game_rules"]["factions"]
    ranks = config["game_rules"]["ranks"]
    for faction in factions:
        for rank in ranks:
            cards.append(Card(faction=faction, rank=rank))
    return cards
