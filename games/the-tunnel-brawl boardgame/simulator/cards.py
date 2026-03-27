"""Card dataclass and Deck container for The Tunnel Brawl simulator."""

from dataclasses import dataclass
from typing import List, Optional
import random


@dataclass
class Card:
    """A single card in the Hamsters & Monsters deck."""
    faction: str   # RED, ORANGE, YELLOW, GREEN, BLUE, PURPLE
    rank: int      # 0-10

    @property
    def is_wild(self) -> bool:
        """Ranks 0 and 10 are Wilds (Sugar Rush)."""
        return self.rank in (0, 10)

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
        faction_short = self.faction[0]
        wild_tag = "*" if self.is_wild else ""
        return f"{faction_short}{self.rank}{wild_tag}"


class Deck:
    """Generic container for any pile of cards."""

    def __init__(self, cards: List[Card] = None):
        self.cards: List[Card] = list(cards) if cards else []

    def shuffle(self, rng: random.Random):
        """Shuffle using provided seeded RNG."""
        rng.shuffle(self.cards)

    def draw(self, n: int = 1) -> List[Card]:
        """Draw n cards from the top. Returns fewer if deck is short."""
        drawn = self.cards[:n]
        self.cards = self.cards[n:]
        return drawn

    def draw_one(self) -> Optional[Card]:
        """Draw a single card, or None if empty."""
        return self.cards.pop(0) if self.cards else None

    def add_to_bottom(self, cards):
        """Add card(s) to the bottom of the pile."""
        if isinstance(cards, list):
            self.cards.extend(cards)
        else:
            self.cards.append(cards)

    def add_to_top(self, cards):
        """Add card(s) to the top of the pile."""
        if isinstance(cards, list):
            self.cards = cards + self.cards
        else:
            self.cards.insert(0, cards)

    def peek(self, n: int = 1) -> List[Card]:
        """Look at top n cards without removing them."""
        return self.cards[:n]

    @property
    def size(self) -> int:
        return len(self.cards)

    @property
    def empty(self) -> bool:
        return len(self.cards) == 0


def build_deck(config: dict) -> List[Card]:
    """Build the full 66-card Hamsters & Monsters deck from config."""
    cards = []
    for faction in config["deck"]["factions"]:
        for rank in config["deck"]["ranks"]:
            cards.append(Card(faction=faction, rank=rank))
    return cards
