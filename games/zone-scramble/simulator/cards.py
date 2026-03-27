"""
Zone Scramble — Card definitions and Deck container.
"""

from __future__ import annotations
from dataclasses import dataclass
import random
from typing import List, Optional


# ---------------------------------------------------------------------------
# Card
# ---------------------------------------------------------------------------

@dataclass
class Card:
    """A single Monster card."""
    faction: str        # RED, ORANGE, YELLOW, GREEN, BLUE, PURPLE
    rank: int           # 0-10

    @property
    def is_chameleon(self) -> bool:
        return self.rank in (0, 10)

    @property
    def id(self) -> str:
        return f"{self.faction}-{self.rank}"

    def __hash__(self):
        return hash(self.id)

    def __eq__(self, other):
        if not isinstance(other, Card):
            return False
        return self.id == other.id

    def __repr__(self):
        tag = "*" if self.is_chameleon else ""
        return f"{self.faction[0]}{self.rank}{tag}"


# ---------------------------------------------------------------------------
# Deck (generic pile)
# ---------------------------------------------------------------------------

class Deck:
    """Ordered pile of cards — used for draw pile, discard, hands, etc."""

    def __init__(self, cards: list | None = None):
        self.cards: List[Card] = list(cards) if cards else []

    def shuffle(self, rng: random.Random | None = None):
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

    def add_to_bottom(self, items):
        if isinstance(items, list):
            self.cards.extend(items)
        else:
            self.cards.append(items)

    def add_to_top(self, items):
        if isinstance(items, list):
            self.cards = items + self.cards
        else:
            self.cards.insert(0, items)

    def peek(self, n: int = 1) -> List[Card]:
        return self.cards[:n]

    def remove(self, card: Card) -> bool:
        try:
            self.cards.remove(card)
            return True
        except ValueError:
            return False

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


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def build_full_deck(config: dict) -> List[Card]:
    """Build the 66-card deck from config."""
    deck_cfg = config["deck"]
    cards = []
    for faction in deck_cfg["factions"]:
        for rank in range(deck_cfg["rank_min"], deck_cfg["rank_max"] + 1):
            cards.append(Card(faction=faction, rank=rank))
    return cards
