"""Card definitions and Deck class for Summit Scramble."""

from dataclasses import dataclass, field
from typing import List, Optional
import random


# Faction order (highest to lowest priority for tie-breaking)
FACTIONS = ["RED", "ORANGE", "YELLOW", "GREEN", "BLUE", "PURPLE"]
FACTION_RANK = {f: i for i, f in enumerate(FACTIONS)}  # lower = higher priority

FACTION_NAMES = {
    "RED": "Super-Dupes",
    "ORANGE": "Finders-Keepers",
    "YELLOW": "Tinkerers",
    "GREEN": "Prognosticationers",
    "BLUE": "Magicians",
    "PURPLE": "Time Travelers",
}

FACTION_ABILITIES = {
    "RED": "rotation",
    "ORANGE": "scout",
    "YELLOW": "streamline",
    "GREEN": "recalibrate",
    "BLUE": "revelation",
    "PURPLE": "reclaim",
}


@dataclass
class Card:
    """A single card in the H&M deck."""
    faction: str
    rank: int

    @property
    def faction_priority(self) -> int:
        """Lower = higher priority in tie-breaking."""
        return FACTION_RANK[self.faction]

    @property
    def triggers_power(self) -> bool:
        return self.rank >= 6

    @property
    def ability(self) -> Optional[str]:
        return FACTION_ABILITIES.get(self.faction)

    def beats_solo(self, other: 'Card') -> bool:
        """Can this card beat another in a Solo Sprint?"""
        if self.rank > other.rank:
            return True
        if self.rank == other.rank:
            return self.faction_priority < other.faction_priority
        return False

    def __hash__(self):
        return hash((self.faction, self.rank))

    def __eq__(self, other):
        if not isinstance(other, Card):
            return False
        return self.faction == other.faction and self.rank == other.rank

    def __repr__(self):
        return f"{self.faction[0]}{self.rank}"

    def __str__(self):
        return f"{self.faction} {self.rank}"


class Deck:
    """Generic ordered collection of cards (draw pile, discard, hand)."""

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

    def remove(self, card: Card) -> bool:
        if card in self.cards:
            self.cards.remove(card)
            return True
        return False

    @property
    def size(self) -> int:
        return len(self.cards)

    @property
    def empty(self) -> bool:
        return len(self.cards) == 0

    def __len__(self):
        return len(self.cards)

    def __repr__(self):
        return f"Deck({len(self.cards)} cards)"


def build_full_deck() -> List[Card]:
    """Build the complete 66-card H&M deck."""
    cards = []
    for faction in FACTIONS:
        for rank in range(11):  # 0-10
            cards.append(Card(faction=faction, rank=rank))
    return cards
