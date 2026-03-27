"""
Card definitions and Deck class for Get Stuffed.

66-card deck: 6 factions x 11 ranks (0-10).
Purple (Time Travelers) are wild.
Cards ranked 6-10 trigger faction powers.
"""

from dataclasses import dataclass
import random
from typing import List, Optional


FACTION_SYMBOLS = {
    "RED": "🔴",
    "ORANGE": "🟠",
    "YELLOW": "🟡",
    "GREEN": "🟢",
    "BLUE": "🔵",
    "PURPLE": "🟣",
}

FACTION_NAMES = {
    "RED": "Super-Dupes",
    "ORANGE": "Finders-Keepers",
    "YELLOW": "Tinkerers",
    "GREEN": "Prognosticationers",
    "BLUE": "Magicians",
    "PURPLE": "Time Travelers",
}


@dataclass
class Card:
    """A single card in the Hamsters & Monsters deck."""
    faction: str   # RED, ORANGE, YELLOW, GREEN, BLUE, PURPLE
    rank: int      # 0-10

    @property
    def is_wild(self) -> bool:
        return self.faction == "PURPLE"

    @property
    def has_power(self) -> bool:
        return self.rank >= 6

    @property
    def power_name(self) -> str:
        if not self.has_power:
            return ""
        if self.faction == "RED":
            return "Hot Potato!"
        elif self.faction == "ORANGE":
            return "Dib It!"
        elif self.faction == "YELLOW":
            return "Re-Tinker!"
        elif self.faction == "GREEN":
            return "I Foresaw This!"
        elif self.faction == "BLUE":
            return "VANISH!" if self.rank == 10 else "Sleight of Paw"
        elif self.faction == "PURPLE":
            return "Time Warp"
        return ""

    @property
    def symbol(self) -> str:
        return FACTION_SYMBOLS.get(self.faction, "?")

    @property
    def id(self) -> str:
        return f"{self.faction}-{self.rank}"

    def matches_pit(self, pit_card: 'Card', declared_faction: Optional[str] = None) -> bool:
        """Check if this card can be legally played on the pit card.

        Args:
            pit_card: The current top of the pit.
            declared_faction: If a Time Traveler declared a faction, match against that.
        """
        # Wild cards always match
        if self.is_wild:
            return True
        # Match by rank
        if self.rank == pit_card.rank:
            return True
        # Match by faction (use declared faction if set, otherwise pit card's faction)
        target_faction = declared_faction if declared_faction else pit_card.faction
        if self.faction == target_faction:
            return True
        return False

    def __hash__(self):
        return hash(self.id)

    def __eq__(self, other):
        if not isinstance(other, Card):
            return False
        return self.faction == other.faction and self.rank == other.rank

    def __repr__(self):
        return f"{self.symbol}{self.faction[0]}{self.rank}"

    def __str__(self):
        return f"{self.symbol} {FACTION_NAMES[self.faction]} {self.rank}"


class Deck:
    """A generic pile of cards (draw pile, discard pile, hand)."""

    def __init__(self, cards: List[Card] = None):
        self.cards: List[Card] = list(cards) if cards else []

    def shuffle(self, rng: random.Random):
        """Shuffle using seeded RNG."""
        rng.shuffle(self.cards)

    def draw_one(self) -> Optional[Card]:
        """Draw the top card, or None if empty."""
        return self.cards.pop(0) if self.cards else None

    def draw(self, n: int = 1) -> List[Card]:
        """Draw up to n cards from the top."""
        drawn = self.cards[:n]
        self.cards = self.cards[n:]
        return drawn

    def add_to_top(self, cards):
        """Add card(s) to the top of the deck."""
        if isinstance(cards, list):
            self.cards = cards + self.cards
        else:
            self.cards.insert(0, cards)

    def add_to_bottom(self, cards):
        """Add card(s) to the bottom of the deck."""
        if isinstance(cards, list):
            self.cards.extend(cards)
        else:
            self.cards.append(cards)

    def peek(self, n: int = 1) -> List[Card]:
        """Look at the top n cards without removing them."""
        return self.cards[:n]

    @property
    def size(self) -> int:
        return len(self.cards)

    @property
    def empty(self) -> bool:
        return len(self.cards) == 0

    def __repr__(self):
        return f"Deck({self.size} cards)"


def build_deck(config: dict) -> List[Card]:
    """Build the full 66-card deck from config."""
    factions = config["game_rules"]["deck"]["factions"]
    ranks = config["game_rules"]["deck"]["ranks"]
    cards = []
    for faction in factions:
        for rank in ranks:
            cards.append(Card(faction=faction, rank=rank))
    return cards
