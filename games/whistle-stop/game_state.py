"""
game_state.py — Whistle Stop v1.0
Route: depot=0, route cards=1-N, station at position N+1
Players can only move up to the LAST placed card's position (not past it).
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict
from cards import HMCard, Deck


DEPOT_INDEX = 0
# Route grows from depot outward. Station at position ROUTE_CARDS_BEFORE_STATION + 1.
# Players can only move up to the current last card's position.
ROUTE_CARDS_BEFORE_STATION = 20  # station appears after 20 route cards placed
STATION_POS = ROUTE_CARDS_BEFORE_STATION + 1  # = 15


@dataclass
class RouteCard:
    card: HMCard
    position: int

    def __repr__(self):
        return f"{self.card}"


class Route:
    def __init__(self):
        self.cards: List[RouteCard] = []

    def place_card(self, card: HMCard, position: int) -> int:
        self.cards.append(RouteCard(card=card, position=position))
        return position

    def next_position(self) -> int:
        if not self.cards:
            return 1
        return max(rc.position for rc in self.cards) + 1

    def last_card_position(self) -> int:
        """Position of the last placed card (excluding depot)."""
        non_depot = [rc for rc in self.cards if rc.position > 0]
        if not non_depot:
            return 0
        return max(rc.position for rc in non_depot)

    def is_station_reached(self) -> bool:
        return len([rc for rc in self.cards if rc.position > 0]) >= ROUTE_CARDS_BEFORE_STATION

    def station_position(self) -> int:
        return STATION_POS

    def get_card_at(self, pos: int) -> Optional[RouteCard]:
        for rc in self.cards:
            if rc.position == pos:
                return rc
        return None

    def route_card_count(self) -> int:
        return len([rc for rc in self.cards if rc.position > 0])

    def __repr__(self):
        if not self.cards:
            return "[Depot]"
        parts = [str(rc) for rc in sorted(self.cards, key=lambda x: x.position)]
        return " → ".join(parts)


@dataclass
class Player:
    player_id: int
    name: str
    faction: str
    hand: List[HMCard] = field(default_factory=list)
    position: int = DEPOT_INDEX
    score: float = 0.0
    placed_station: bool = False

    def reset(self):
        self.position = DEPOT_INDEX
        self.score = 0.0
        self.placed_station = False
        self.hand = []

    def move_train(self, steps: int, route: Route) -> tuple[int, List[int]]:
        """
        Move up to `steps` steps. Can only move up to the last placed card's position.
        Cannot move past the last card currently in the route.
        Returns (new_pos, passed_positions).
        """
        if steps <= 0:
            return self.position, []

        last_card_pos = route.last_card_position()
        passed = []
        current = self.position

        while steps > 0 and current < last_card_pos:
            next_pos = current + 1
            passed.append(next_pos)
            current = next_pos
            steps -= 1

        # Can also move TO the last card (if not already there)
        if current < last_card_pos and steps > 0:
            next_pos = current + 1
            if next_pos <= last_card_pos:
                passed.append(next_pos)
                current = next_pos

        self.position = current
        return current, passed


@dataclass
class GameState:
    players: List[Player]
    deck: Deck
    route: Route = field(default_factory=Route)
    round_number: int = 0
    is_game_over: bool = False
    station_placer_id: Optional[int] = None
    winner_id: Optional[int] = None
    station_bonus: float = 10.0
    hand_size: int = 3

    FACTION_BONUS = {"red": 1, "blue": 1, "green": 1, "yellow": 1}

    def setup(self):
        self.deck.reset()
        self.route = Route()
        self.round_number = 0
        self.is_game_over = False
        self.station_placer_id = None
        self.winner_id = None
        for p in self.players:
            p.reset()
        for _ in range(self.hand_size):
            for p in self.players:
                p.hand.extend(self.deck.draw())
        self.route.place_card(self.deck.draw()[0], position=0)

    def player_by_id(self, pid: int) -> Player:
        for p in self.players:
            if p.player_id == pid:
                return p
        raise ValueError(f"No player id {pid}")

    def check_endgame(self):
        if self.route.is_station_reached() and not self.is_game_over:
            self.is_game_over = True
            # Station placement bonus
            if self.station_placer_id is not None:
                self.player_by_id(self.station_placer_id).score += self.station_bonus
            # Comeback bonus: trailing players get bonus based on how far behind they are
            # (station_position - player_position) × 0.5 VP per step behind
            max_pos = max(p.position for p in self.players)
            for p in self.players:
                if p.position < max_pos:
                    behind = max_pos - p.position
                    comeback_bonus = behind * 1.0
                    p.score += comeback_bonus
            # Determine winner
            max_score = max(p.score for p in self.players)
            winners = [p for p in self.players if p.score == max_score]
            self.winner_id = winners[0].player_id

    def draw_phase(self):
        for p in self.players:
            while len(p.hand) < self.hand_size and not self.deck.is_exhausted():
                p.hand.extend(self.deck.draw())

    def __repr__(self):
        pos_str = ", ".join(f"P{p.player_id}:{p.position}" for p in self.players)
        return (f"round={self.round_number}, "
                f"route={self.route.route_card_count()}/{ROUTE_CARDS_BEFORE_STATION}, "
                f"over={self.is_game_over}, {pos_str})")
