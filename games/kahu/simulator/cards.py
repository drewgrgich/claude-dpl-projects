"""Card definitions and Deck class for Kahu simulator."""

from dataclasses import dataclass, field
from typing import List, Optional
import random


@dataclass
class Card:
    """A single Kahu card."""
    name: str
    card_type: str       # Flower, ITEM, WILDLIFE, ISLANDER, Surf, Starter, Lava, Hula, Tiki
    cost: int
    influence: int
    vp: int
    icon: str            # Red, Blue, Yellow, Wild, or "" (none)
    effect_text: str     # Raw effect text
    effect_id: str = ""  # Machine-readable effect key

    @property
    def has_pua_icon(self) -> bool:
        return self.icon in ("Red", "Blue", "Yellow", "Wild")

    @property
    def is_wild(self) -> bool:
        return self.icon == "Wild"

    @property
    def normalized_type(self) -> str:
        """Normalize card type for comparisons."""
        t = self.card_type.lower().strip()
        if t in ("item",):
            return "Item"
        if t in ("wildlife",):
            return "Wildlife"
        if t in ("flower",):
            return "Flower"
        if t in ("islander",):
            return "Islander"
        if t in ("surf",):
            return "Surf"
        if t in ("tiki",):
            return "Tiki"
        if t in ("lava",):
            return "Lava"
        if t in ("hula",):
            return "Hula"
        if t in ("starter",):
            return "Starter"
        return self.card_type

    def __repr__(self):
        icon_str = f"/{self.icon}" if self.icon else ""
        return f"{self.name}({self.cost}c/{self.influence}i/{self.vp}vp{icon_str})"

    def __hash__(self):
        return id(self)  # Each card instance is unique

    def __eq__(self, other):
        return self is other


@dataclass
class Offering:
    """An offering card that players try to complete."""
    name: str
    pua_cost: dict        # e.g. {"Red": 2, "Blue": 1, "Yellow": 1}
    bonus_type: str       # e.g. "removed_cards", "card_types", "islander", etc.
    bonus_text: str
    vp_tokens: List[int] = field(default_factory=lambda: [4, 3, 2, 1])
    completed_by: List[int] = field(default_factory=list)  # player ids

    @property
    def total_pua_cost(self) -> int:
        return sum(self.pua_cost.values())

    @property
    def top_vp_token(self) -> int:
        remaining = [v for i, v in enumerate(self.vp_tokens) if i >= len(self.completed_by)]
        return remaining[0] if remaining else 0

    @property
    def available(self) -> bool:
        return len(self.completed_by) < len(self.vp_tokens)

    def complete(self, player_id: int) -> int:
        """Complete this offering for a player. Returns VP earned."""
        if player_id in self.completed_by:
            return 0
        vp = self.top_vp_token
        self.completed_by.append(player_id)
        return vp

    def __repr__(self):
        cost_str = "".join(c[0] * n for c, n in self.pua_cost.items())
        return f"Offering({cost_str}: {self.bonus_type})"


class Deck:
    """Generic ordered card container — draw pile, discard pile, hand, market."""

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

    def peek(self, n: int = 1) -> list:
        return self.cards[:n]

    def remove(self, card):
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

    def __contains__(self, item):
        return item in self.cards

    def __iter__(self):
        return iter(self.cards)

    def __repr__(self):
        return f"Deck({len(self.cards)} cards)"


def make_starter_card(influence: int, icon: str = "") -> Card:
    """Create a starter deck card."""
    name = f"{influence}-Influence"
    if icon:
        name += f"+{icon}"
    return Card(
        name=name, card_type="Starter", cost=0,
        influence=influence, vp=0, icon=icon, effect_text="",
        effect_id="starter"
    )


def make_lava_flow() -> Card:
    return Card(
        name="Lava Flow", card_type="Lava", cost=0,
        influence=0, vp=0, icon="", effect_text="Advance lava tracker",
        effect_id="lava_flow"
    )


def make_hula() -> Card:
    return Card(
        name="Hula", card_type="Hula", cost=0,
        influence=0, vp=0, icon="", effect_text="Remove a non-Lava card from hand",
        effect_id="hula_remove"
    )


def make_tiki(index: int, vp: int = 0) -> Card:
    tiki_names = ["Kū", "Kāne", "Lono", "Kanaloa"]
    name = tiki_names[index] if index < len(tiki_names) else f"Tiki-{index}"
    return Card(
        name=name, card_type="Tiki", cost=0,
        influence=0, vp=vp, icon="", effect_text="Lava shield",
        effect_id="tiki"
    )


def build_starter_deck() -> List[Card]:
    """Build one player's starting deck of 11 cards."""
    cards = []
    # 5x 1-Influence (plain)
    for _ in range(5):
        cards.append(make_starter_card(1))
    # 1x 1-Influence + Wild (new in v3)
    cards.append(make_starter_card(1, "Wild"))
    # 1x each colored
    cards.append(make_starter_card(1, "Red"))
    cards.append(make_starter_card(1, "Blue"))
    cards.append(make_starter_card(1, "Yellow"))
    # 1x Hula
    cards.append(make_hula())
    # 1x Lava Flow
    cards.append(make_lava_flow())
    return cards


# All 8 possible offerings, split into two stacks
# 3-Pua stack: all cost RBY (1R + 1B + 1Y = 3 Pua)
OFFERINGS_3PUA = [
    Offering(
        name="Card Types",
        pua_cost={"Red": 1, "Blue": 1, "Yellow": 1},
        bonus_type="card_types",
        bonus_text="1 VP per different card type in deck (Flower/Item/Wildlife/Islander/Surf/Tiki — max 6)"
    ),
    Offering(
        name="Flowers",
        pua_cost={"Red": 1, "Blue": 1, "Yellow": 1},
        bonus_type="flower_count",
        bonus_text="1 VP for each Flower card you own at end of game"
    ),
    Offering(
        name="Tikis",
        pua_cost={"Red": 1, "Blue": 1, "Yellow": 1},
        bonus_type="tiki_count",
        bonus_text="3 VP for each Tiki card you own at end of game"
    ),
    Offering(
        name="Surfs",
        pua_cost={"Red": 1, "Blue": 1, "Yellow": 1},
        bonus_type="surf_count",
        bonus_text="1 VP for each Surf card you own at end of game"
    ),
]

# 4-Pua stack: each costs 4 Pua in various color combinations
OFFERINGS_4PUA = [
    Offering(
        name="Removed Cards",
        pua_cost={"Red": 2, "Blue": 1, "Yellow": 1},
        bonus_type="removed_cards",
        bonus_text="1 VP for each card you removed from your deck during the game"
    ),
    Offering(
        name="Islanders",
        pua_cost={"Red": 1, "Blue": 1, "Yellow": 2},
        bonus_type="islander_count",
        bonus_text="1 VP for each Islander card you own at end of game"
    ),
    Offering(
        name="Items",
        pua_cost={"Red": 1, "Blue": 1, "Yellow": 2},
        bonus_type="item_count",
        bonus_text="1 VP for each Item card you own at end of game"
    ),
    Offering(
        name="Wildlife",
        pua_cost={"Red": 1, "Blue": 2, "Yellow": 1},
        bonus_type="wildlife_count",
        bonus_text="1 VP for each Wildlife card you own at end of game"
    ),
]

# Combined for backward compatibility
ALL_OFFERINGS = OFFERINGS_3PUA + OFFERINGS_4PUA
