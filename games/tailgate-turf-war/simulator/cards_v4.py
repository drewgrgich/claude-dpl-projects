"""
Card definitions for the v0.1 custom deck game.

48-card deck:
  - 36 Number cards (4 colors × ranks 1-9)
  - 4 Mascots (one per color, doubles best card)
  - 4 Action cards (Shield/Bomb/Swap/Bounty, one per color)
  - 4 Duds (one per color, look like actions, play as rank 5)
"""

from dataclasses import dataclass
from typing import List
import random


# ─── CONSTANTS ────────────────────────────────────────────────────────────────

COLORS = ["RED", "YELLOW", "GREEN", "BLUE"]
COLOR_ORDER = {c: i for i, c in enumerate(COLORS)}

CARD_TYPE_NUMBER = "number"
CARD_TYPE_MASCOT = "mascot"
CARD_TYPE_ACTION = "action"
CARD_TYPE_DUD = "dud"

ACTION_SHIELD = "shield"
ACTION_BOMB = "bomb"
ACTION_SWAP = "swap"
ACTION_BOUNTY = "bounty"

# Color → action type mapping
COLOR_ACTION = {
    "RED": ACTION_SHIELD,
    "YELLOW": ACTION_BOMB,
    "GREEN": ACTION_SWAP,
    "BLUE": ACTION_BOUNTY,
}

# Resolution order (lower = resolves first)
ACTION_RESOLUTION = {
    ACTION_SHIELD: 1,
    ACTION_BOMB: 2,
    ACTION_SWAP: 3,
    ACTION_BOUNTY: 4,
}


# ─── CARD DATACLASS ──────────────────────────────────────────────────────────

@dataclass
class Card:
    """A single game card."""
    color: str          # RED, YELLOW, GREEN, BLUE
    card_type: str      # number, mascot, action, dud
    rank: int = 0       # 1-9 for numbers, 0 for mascot/action, 5 for dud
    action_type: str = ""  # shield/bomb/swap/bounty for action cards

    @property
    def is_number(self) -> bool:
        return self.card_type == CARD_TYPE_NUMBER

    @property
    def is_mascot(self) -> bool:
        return self.card_type == CARD_TYPE_MASCOT

    @property
    def is_action(self) -> bool:
        return self.card_type == CARD_TYPE_ACTION

    @property
    def is_dud(self) -> bool:
        return self.card_type == CARD_TYPE_DUD

    @property
    def is_natural(self) -> bool:
        """Natural cards (ranks 1-9) can anchor Home Field."""
        if self.is_number:
            return True
        if self.is_dud:
            return True  # Duds count as natural rank 5
        return False

    @property
    def is_action_backed(self) -> bool:
        """Cards that share the action card border (opponents can't distinguish)."""
        return self.is_action or self.is_dud

    @property
    def effective_rank(self) -> int:
        """The rank this card contributes to strength calculation."""
        if self.is_number:
            return self.rank
        if self.is_dud:
            return 5  # Duds play as rank 5
        return 0  # Mascots and actions have no rank

    @property
    def has_rank(self) -> bool:
        """Does this card contribute a rank to strength?"""
        return self.is_number or self.is_dud

    @property
    def id(self) -> str:
        if self.is_number:
            return f"{self.color}-{self.rank}"
        elif self.is_mascot:
            return f"{self.color}-Mascot"
        elif self.is_action:
            return f"{self.color}-{self.action_type.title()}"
        else:
            return f"{self.color}-Dud"

    def __hash__(self):
        return hash((self.color, self.card_type, self.rank, self.action_type))

    def __eq__(self, other):
        if not isinstance(other, Card):
            return False
        return (self.color == other.color and
                self.card_type == other.card_type and
                self.rank == other.rank and
                self.action_type == other.action_type)

    def __repr__(self):
        c = self.color[:3]
        if self.is_number:
            return f"{c}-{self.rank}"
        elif self.is_mascot:
            return f"{c}-M"
        elif self.is_action:
            return f"{c}-{self.action_type[0].upper()}"
        else:
            return f"{c}-D"

    def __lt__(self, other):
        if self.color != other.color:
            return COLOR_ORDER[self.color] < COLOR_ORDER[other.color]
        type_order = {CARD_TYPE_MASCOT: 0, CARD_TYPE_ACTION: 1,
                      CARD_TYPE_DUD: 2, CARD_TYPE_NUMBER: 3}
        if self.card_type != other.card_type:
            return type_order[self.card_type] < type_order[other.card_type]
        return self.rank < other.rank


# ─── DECK BUILDING ───────────────────────────────────────────────────────────

def build_deck(config: dict = None) -> List[Card]:
    """Build the full 48-card deck from config."""
    colors = (config or {}).get("game_rules", {}).get("colors", COLORS)
    ranks = (config or {}).get("game_rules", {}).get("ranks", list(range(1, 10)))
    dud_rank = (config or {}).get("game_rules", {}).get("dud_rank", 5)

    cards = []

    for color in colors:
        # Number cards
        for rank in ranks:
            cards.append(Card(color=color, card_type=CARD_TYPE_NUMBER, rank=rank))

        # Mascot
        cards.append(Card(color=color, card_type=CARD_TYPE_MASCOT, rank=0))

        # Action card
        action = COLOR_ACTION[color]
        cards.append(Card(color=color, card_type=CARD_TYPE_ACTION,
                          rank=0, action_type=action))

        # Dud
        cards.append(Card(color=color, card_type=CARD_TYPE_DUD, rank=dud_rank))

    return cards


class Deck:
    """Generic ordered collection of cards."""

    def __init__(self, cards: List[Card] = None):
        self.cards: List[Card] = list(cards) if cards else []

    def shuffle(self, rng: random.Random):
        rng.shuffle(self.cards)

    def draw(self, n: int = 1) -> List[Card]:
        drawn = self.cards[:n]
        self.cards = self.cards[n:]
        return drawn

    def draw_one(self):
        return self.cards.pop(0) if self.cards else None

    def add_to_bottom(self, cards):
        if isinstance(cards, list):
            self.cards.extend(cards)
        else:
            self.cards.append(cards)

    @property
    def size(self) -> int:
        return len(self.cards)

    @property
    def empty(self) -> bool:
        return len(self.cards) == 0

    def __repr__(self):
        return f"Deck({self.size} cards)"
