"""
Hamster High Council — Card definitions, Deck class, and deck builder.

66 cards: 6 factions × 11 ranks (0–10).
"""

from dataclasses import dataclass
from typing import List, Optional
import random


# Faction constants
FACTIONS = ["RED", "ORANGE", "YELLOW", "GREEN", "BLUE", "PURPLE"]

FACTION_SYMBOLS = {
    "RED": "🔴", "ORANGE": "🟠", "YELLOW": "🟡",
    "GREEN": "🟢", "BLUE": "🔵", "PURPLE": "🟣",
}

FACTION_NAMES = {
    "RED": "Super-Dupes", "ORANGE": "Finders-Keepers", "YELLOW": "Tinkerers",
    "GREEN": "Prognosticationers", "BLUE": "Magicians", "PURPLE": "Time Travelers",
}


@dataclass
class Card:
    """A single Hamster High Council card."""
    faction: str
    rank: int

    @property
    def is_intern(self) -> bool:
        """Rank 0 cards are Interns — draw 1 when played."""
        return self.rank == 0

    @property
    def id(self) -> str:
        return f"{self.faction}-{self.rank}"

    def short(self) -> str:
        """Short display: e.g. 'RED-7' or '🔴7'."""
        return f"{FACTION_SYMBOLS.get(self.faction, '?')}{self.rank}"

    def __hash__(self):
        return hash((self.faction, self.rank))

    def __eq__(self, other):
        if not isinstance(other, Card):
            return False
        return self.faction == other.faction and self.rank == other.rank

    def __repr__(self):
        return f"{self.faction}-{self.rank}"

    def __lt__(self, other):
        """Sort by faction then rank."""
        if self.faction != other.faction:
            return FACTIONS.index(self.faction) < FACTIONS.index(other.faction)
        return self.rank < other.rank


class Deck:
    """Generic ordered card container — draw pile, discard pile, hand, etc."""

    def __init__(self, cards: Optional[List[Card]] = None):
        self.cards: List[Card] = list(cards) if cards else []

    def shuffle(self, rng: random.Random):
        """Shuffle using seeded RNG for reproducibility."""
        rng.shuffle(self.cards)

    def draw(self, n: int = 1) -> List[Card]:
        """Draw up to n cards from the top. Returns fewer if not enough."""
        n = min(n, len(self.cards))
        drawn = self.cards[:n]
        self.cards = self.cards[n:]
        return drawn

    def draw_one(self) -> Optional[Card]:
        """Draw a single card, or None if empty."""
        return self.cards.pop(0) if self.cards else None

    def add_to_bottom(self, cards):
        """Add card(s) to the bottom of the deck."""
        if isinstance(cards, list):
            self.cards.extend(cards)
        else:
            self.cards.append(cards)

    def add_to_top(self, cards):
        """Add card(s) to the top of the deck."""
        if isinstance(cards, list):
            self.cards = cards + self.cards
        else:
            self.cards.insert(0, cards)

    def peek(self, n: int = 1) -> List[Card]:
        """Look at top n cards without removing them."""
        return self.cards[:n]

    def remove(self, card: Card) -> bool:
        """Remove a specific card. Returns True if found."""
        try:
            self.cards.remove(card)
            return True
        except ValueError:
            return False

    def contains(self, card: Card) -> bool:
        return card in self.cards

    @property
    def size(self) -> int:
        return len(self.cards)

    @property
    def empty(self) -> bool:
        return len(self.cards) == 0

    def __len__(self):
        return len(self.cards)

    def __iter__(self):
        return iter(self.cards)

    def __repr__(self):
        return f"Deck({len(self.cards)} cards)"


def build_full_deck() -> List[Card]:
    """Build the complete 66-card Hamsters & Monsters deck.

    6 factions × 11 ranks (0–10) = 66 cards.
    """
    cards = []
    for faction in FACTIONS:
        for rank in range(0, 11):  # 0 through 10
            cards.append(Card(faction=faction, rank=rank))
    assert len(cards) == 66, f"Expected 66 cards, got {len(cards)}"
    return cards
