"""Card definitions and deck management for Contests of Chaos."""

import random
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class RecruitCard:
    """A single recruit card with faction and rank."""
    faction: str       # e.g. "RED", "ORG", "YLW", "GRN", "BLU", "PUR"
    rank: int          # 0-10

    @property
    def is_free_agent(self) -> bool:
        return self.rank in (0, 10)

    @property
    def id(self) -> str:
        return f"{self.faction}-{self.rank}"

    def __repr__(self):
        fa = "*" if self.is_free_agent else ""
        return f"{self.faction}-{self.rank}{fa}"

    def __hash__(self):
        return hash((self.faction, self.rank))

    def __eq__(self, other):
        if not isinstance(other, RecruitCard):
            return False
        return self.faction == other.faction and self.rank == other.rank


@dataclass
class EventCard:
    """An event card with requirements and rewards."""
    name: str
    tier: int
    vp: int
    requirements: dict      # parsed requirement structure
    reward: str             # reward text
    raw_requirements: str   # original requirement string for display

    def __repr__(self):
        return f"{self.name}({self.vp}VP)"

    def __hash__(self):
        return hash(self.name)

    def __eq__(self, other):
        if not isinstance(other, EventCard):
            return False
        return self.name == other.name


@dataclass
class PlaybookCard:
    """A playbook card with scoring condition."""
    name: str
    category: str
    vp: int
    trigger: str
    timing: str

    def __repr__(self):
        return f"{self.name}({self.vp}VP)"


class Deck:
    """A generic deck of cards that supports shuffle, draw, and bottom-insert."""

    def __init__(self, cards: list = None):
        self.cards: list = list(cards) if cards else []

    def shuffle(self, rng: random.Random = None):
        if rng:
            rng.shuffle(self.cards)
        else:
            random.shuffle(self.cards)

    def draw(self, n: int = 1) -> list:
        drawn = self.cards[:n]
        self.cards = self.cards[n:]
        return drawn

    def draw_one(self):
        if self.cards:
            return self.cards.pop(0)
        return None

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

    def peek(self, n: int = 1) -> list:
        return self.cards[:n]

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


def build_recruit_deck(config: dict) -> List[RecruitCard]:
    """Build all 66 recruit cards from config."""
    cards = []
    for faction in config["factions"]:
        for rank in range(config["rank_range"][0], config["rank_range"][1] + 1):
            cards.append(RecruitCard(faction=faction, rank=rank))
    return cards
