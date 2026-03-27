"""Card definitions and Deck class for The Merch Stand Mob."""

from dataclasses import dataclass, field
from typing import List, Optional
import random


# Faction constants
FACTIONS = {
    "RED": "Super-Dupes",
    "ORANGE": "Finders-Keepers",
    "YELLOW": "Tinkerers",
    "GREEN": "Prognosticationers",
    "BLUE": "Magicians",
    "PURPLE": "Time Travelers",
}

FACTION_COLORS = list(FACTIONS.keys())

FACTION_ABILITIES = {
    "RED": "Stadium Sweep",      # Remove 1 card from Mosh Pit
    "ORANGE": "Keen Eye",        # Peek top supply; swap with Stand card
    "YELLOW": "Quick Hands",     # Draw top supply to Score Pile (blind)
    "GREEN": "Small Prophecies", # See top 3 supply; keep 1 ≤5; reorder rest
    "BLUE": "Sleight of Paw",   # Move 1 Mosh Pit card to different faction
    "PURPLE": "Temporal Recall", # Retrieve 1 bid card from Pit; discard different to Pit
}


@dataclass
class Card:
    """A single card in the Hamsters & Monsters deck."""
    faction: str   # RED, ORANGE, YELLOW, GREEN, BLUE, PURPLE
    rank: int      # 0-10

    @property
    def is_wild(self) -> bool:
        """Wilds are rank 0 (Sneak) and rank 10 (Shove)."""
        return self.rank == 0 or self.rank == 10

    @property
    def is_sneak(self) -> bool:
        return self.rank == 0

    @property
    def is_shove(self) -> bool:
        return self.rank == 10

    @property
    def vp(self) -> int:
        """Victory points = printed rank."""
        return self.rank

    @property
    def faction_name(self) -> str:
        return FACTIONS.get(self.faction, self.faction)

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
        return f"{self.faction}-{self.rank}"


class Deck:
    """Generic ordered collection of cards. Used for supply, hands, piles."""

    def __init__(self, cards: List[Card] = None):
        self.cards: List[Card] = list(cards) if cards else []

    def shuffle(self, rng: random.Random = None):
        """Shuffle using provided RNG for reproducibility."""
        if rng:
            rng.shuffle(self.cards)
        else:
            random.shuffle(self.cards)

    def draw(self, n: int = 1) -> List[Card]:
        """Draw n cards from the top. Returns fewer if not enough."""
        n = min(n, len(self.cards))
        drawn = self.cards[:n]
        self.cards = self.cards[n:]
        return drawn

    def draw_one(self) -> Optional[Card]:
        """Draw a single card from the top."""
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

    def __contains__(self, card):
        return card in self.cards

    def __repr__(self):
        return f"Deck({len(self.cards)} cards)"


def build_full_deck() -> List[Card]:
    """Build the complete 66-card Hamsters & Monsters deck.

    6 factions x 11 ranks (0-10) = 66 cards.
    """
    cards = []
    for faction in FACTION_COLORS:
        for rank in range(11):  # 0 through 10
            cards.append(Card(faction=faction, rank=rank))
    return cards
