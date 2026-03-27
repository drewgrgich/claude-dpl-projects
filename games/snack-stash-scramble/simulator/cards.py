"""Card definitions and Deck class for Snack Stash Scramble."""

from dataclasses import dataclass, field
from typing import List, Optional
import random


@dataclass
class Card:
    """A single card in the 66-card deck."""
    faction: str   # RED, ORANGE, YELLOW, GREEN, BLUE, PURPLE
    rank: int      # 0-10

    @property
    def is_wild(self) -> bool:
        return self.rank in (0, 10)

    @property
    def face_value(self) -> int:
        return self.rank

    @property
    def hand_penalty(self) -> int:
        """Penalty if caught in hand at end of game."""
        if self.is_wild:
            return 10  # Jawbreaker Hazard: wilds are always -10
        return self.rank

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
        wild_tag = "*" if self.is_wild else ""
        return f"{self.faction[0]}{self.rank}{wild_tag}"

    def __lt__(self, other):
        if not isinstance(other, Card):
            return NotImplemented
        return (self.faction, self.rank) < (other.faction, other.rank)


@dataclass
class BankedSet:
    """A set of cards banked on the table."""
    cards: List[Card] = field(default_factory=list)
    set_type: str = ""       # "group" or "run"
    protected: bool = False  # RED power: opponents can't extend
    owner_id: int = -1
    poisoned_cards: List[Card] = field(default_factory=list)  # Cards placed by opponents (horizontal)

    @property
    def total_value(self) -> int:
        return sum(c.face_value for c in self.cards)

    @property
    def poison_penalty(self) -> int:
        """Total face value of opponent-placed (sideways) cards."""
        return sum(c.face_value for c in self.poisoned_cards)

    @property
    def base_rank(self) -> Optional[int]:
        """For groups, the shared rank. For runs, None."""
        if self.set_type == "group":
            naturals = [c for c in self.cards if not c.is_wild]
            return naturals[0].rank if naturals else None
        return None

    @property
    def base_faction(self) -> Optional[str]:
        """For runs, the faction. For groups, None."""
        if self.set_type == "run":
            naturals = [c for c in self.cards if not c.is_wild]
            return naturals[0].faction if naturals else None
        return None

    def can_extend_with(self, card: Card) -> bool:
        """Check if a card can legally extend this set."""
        if self.set_type == "group":
            if card.is_wild:
                return True
            return card.rank == self.base_rank
        elif self.set_type == "run":
            faction = self.base_faction
            if card.is_wild:
                return True  # Wild can extend a run
            if card.faction != faction:
                return False
            ranks = sorted(c.rank for c in self.cards if not c.is_wild)
            # Card must extend the sequence at either end
            if not ranks:
                return True
            return card.rank == ranks[0] - 1 or card.rank == ranks[-1] + 1
        return False

    def __repr__(self):
        cards_str = ",".join(str(c) for c in self.cards)
        prot = " [PROTECTED]" if self.protected else ""
        return f"{self.set_type}({cards_str}){prot}"


class Deck:
    """A generic pile of cards (draw pile, discard pile, etc.)."""

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

    def add_to_bottom(self, item):
        if isinstance(item, list):
            self.cards.extend(item)
        else:
            self.cards.append(item)

    def add_to_top(self, item):
        if isinstance(item, list):
            self.cards = item + self.cards
        else:
            self.cards.insert(0, item)

    def peek(self, n: int = 1) -> List[Card]:
        return self.cards[:n]

    def remove(self, card: Card) -> bool:
        """Remove a specific card. Returns True if found."""
        for i, c in enumerate(self.cards):
            if c == card:
                self.cards.pop(i)
                return True
        return False

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
    cards = []
    factions = config["deck"]["factions"]
    min_rank = config["deck"]["min_rank"]
    max_rank = config["deck"]["max_rank"]
    for faction in factions:
        for rank in range(min_rank, max_rank + 1):
            cards.append(Card(faction=faction, rank=rank))
    return cards
