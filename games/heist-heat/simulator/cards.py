"""
Heist Heat — Component Definitions

Card dataclass for the Hamsters & Monsters deck (66 cards: 6 factions × ranks 0-10),
Deck utility class, and VaultGrid for the spatial vault layout.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Set
import random


FACTION_NAMES = {
    "RED": "Super-Dupes",
    "ORANGE": "Finders-Keepers",
    "YELLOW": "Tinkerers",
    "GREEN": "Prognosticationers",
    "BLUE": "Magicians",
    "PURPLE": "Time Travelers",
}

FACTION_EMOJI = {
    "RED": "🔴", "ORANGE": "🟠", "YELLOW": "🟡",
    "GREEN": "🟢", "BLUE": "🔵", "PURPLE": "🟣",
}


@dataclass
class Card:
    """A single H&M card."""
    faction: str   # RED, ORANGE, YELLOW, GREEN, BLUE, PURPLE
    rank: int      # 0-10

    @property
    def is_alarm(self) -> bool:
        return self.rank == 0

    @property
    def heat_value(self) -> int:
        """Heat added when this card is the highest claimed."""
        if self.rank == 0:
            return 3
        elif self.rank <= 3:
            return 1
        elif self.rank <= 7:
            return 2
        else:
            return 3

    @property
    def id(self) -> str:
        return f"{self.faction}-{self.rank}"

    @property
    def short(self) -> str:
        emoji = FACTION_EMOJI.get(self.faction, "?")
        return f"{emoji}{self.rank}"

    def __hash__(self):
        return hash(self.id)

    def __eq__(self, other):
        if not isinstance(other, Card):
            return False
        return self.faction == other.faction and self.rank == other.rank

    def __repr__(self):
        return f"{self.faction[0]}{self.rank}"

    def __lt__(self, other):
        return (self.faction, self.rank) < (other.faction, other.rank)


class Deck:
    """Generic ordered card container."""

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

    def peek(self, n: int = 1) -> List[Card]:
        return self.cards[:n]

    @property
    def size(self) -> int:
        return len(self.cards)

    @property
    def empty(self) -> bool:
        return len(self.cards) == 0


class VaultGrid:
    """
    Spatial grid of vault cards. Supports orthogonal adjacency lookups
    for chain reactions.
    """

    def __init__(self, rows: int, cols: int):
        self.rows = rows
        self.cols = cols
        # grid[r][c] = Card or None (claimed/empty)
        self.grid: List[List[Optional[Card]]] = [
            [None for _ in range(cols)] for _ in range(rows)
        ]
        # Track which cards are face-up
        self.revealed: List[List[bool]] = [
            [False for _ in range(cols)] for _ in range(rows)
        ]

    def place(self, cards: List[Card]):
        """Place cards into grid left-to-right, top-to-bottom."""
        idx = 0
        for r in range(self.rows):
            for c in range(self.cols):
                if idx < len(cards):
                    self.grid[r][c] = cards[idx]
                    idx += 1

    def get(self, r: int, c: int) -> Optional[Card]:
        if 0 <= r < self.rows and 0 <= c < self.cols:
            return self.grid[r][c]
        return None

    def is_face_down(self, r: int, c: int) -> bool:
        return (self.grid[r][c] is not None and not self.revealed[r][c])

    def is_face_up(self, r: int, c: int) -> bool:
        return (self.grid[r][c] is not None and self.revealed[r][c])

    def reveal(self, r: int, c: int) -> Optional[Card]:
        """Flip a card face-up; return it."""
        if self.grid[r][c] is not None:
            self.revealed[r][c] = True
            return self.grid[r][c]
        return None

    def remove(self, r: int, c: int) -> Optional[Card]:
        """Remove (claim) a card from the grid."""
        card = self.grid[r][c]
        self.grid[r][c] = None
        self.revealed[r][c] = False
        return card

    def orthogonal_neighbors(self, r: int, c: int) -> List[Tuple[int, int]]:
        """Return valid neighbor positions (up, down, left, right)."""
        neighbors = []
        for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nr, nc = r + dr, c + dc
            if 0 <= nr < self.rows and 0 <= nc < self.cols:
                neighbors.append((nr, nc))
        return neighbors

    def occupied_positions(self) -> List[Tuple[int, int]]:
        """All positions that still have cards."""
        positions = []
        for r in range(self.rows):
            for c in range(self.cols):
                if self.grid[r][c] is not None:
                    positions.append((r, c))
        return positions

    def face_down_positions(self) -> List[Tuple[int, int]]:
        return [(r, c) for r, c in self.occupied_positions()
                if not self.revealed[r][c]]

    def face_up_positions(self) -> List[Tuple[int, int]]:
        return [(r, c) for r, c in self.occupied_positions()
                if self.revealed[r][c]]

    @property
    def card_count(self) -> int:
        return len(self.occupied_positions())

    @property
    def empty(self) -> bool:
        return self.card_count == 0

    def __repr__(self):
        lines = []
        for r in range(self.rows):
            row_str = []
            for c in range(self.cols):
                card = self.grid[r][c]
                if card is None:
                    row_str.append("  ··  ")
                elif self.revealed[r][c]:
                    row_str.append(f" {card!r:>4} ")
                else:
                    row_str.append("  ??  ")
            lines.append("|".join(row_str))
        return "\n".join(lines)


def build_full_deck() -> List[Card]:
    """Build the complete 66-card H&M deck."""
    cards = []
    for faction in FACTION_NAMES:
        for rank in range(0, 11):
            cards.append(Card(faction=faction, rank=rank))
    return cards
