"""
Mystery Mascots — Card and Deck definitions.
66-card deck: 6 factions × ranks 0–10.
"""

from dataclasses import dataclass, field
from typing import List, Optional
import random


# ── Faction constants ──────────────────────────────────────────────
FACTIONS = ["RED", "ORANGE", "YELLOW", "GREEN", "BLUE", "PURPLE"]

FACTION_NAMES = {
    "RED":    "Super-Dupes",
    "ORANGE": "Finders-Keepers",
    "YELLOW": "Tinkerers",
    "GREEN":  "Prognosticationers",
    "BLUE":   "Magicians",
    "PURPLE": "Time Travelers",
}

FACTION_POWERS = {
    "RED":    "Forced Assist — Flip any face-down room card face-up",
    "ORANGE": "Just Dibs Mine — Secretly peek at any face-down room card",
    "YELLOW": "Scoreboard Mod — Your room card counts as 0 or 11 for Exposure only",
    "GREEN":  "Smug Foreknowledge — Peek at a player's allegiance; they peek at yours",
    "BLUE":   "Sleight of Paw — Move one of your played cards to a different room",
    "PURPLE": "The Rewind — Return one of your played cards to hand, then replay elsewhere",
}

MIN_RANK = 0
MAX_RANK = 10
WILD_RANKS = {0, 10}


# ── Card ───────────────────────────────────────────────────────────
@dataclass
class Card:
    """A single Mystery Mascots card."""
    faction: str
    rank: int
    uid: int = 0  # unique id for tracking through game

    @property
    def is_wild(self) -> bool:
        return self.rank in WILD_RANKS

    @property
    def short(self) -> str:
        return f"{self.faction[:3]}{self.rank}"

    def __hash__(self):
        return hash(self.uid)

    def __eq__(self, other):
        if not isinstance(other, Card):
            return False
        return self.uid == other.uid

    def __repr__(self):
        return f"{self.faction[:3]}-{self.rank}"


# ── Deck ───────────────────────────────────────────────────────────
class Deck:
    """Generic ordered pile of cards."""

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

    @property
    def size(self) -> int:
        return len(self.cards)

    @property
    def empty(self) -> bool:
        return len(self.cards) == 0


# ── Build helpers ──────────────────────────────────────────────────
def build_full_deck() -> List[Card]:
    """Build the 66-card Hamsters & Monsters deck."""
    cards = []
    uid = 0
    for faction in FACTIONS:
        for rank in range(MIN_RANK, MAX_RANK + 1):
            cards.append(Card(faction=faction, rank=rank, uid=uid))
            uid += 1
    return cards
