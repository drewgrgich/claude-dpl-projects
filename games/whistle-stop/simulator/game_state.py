"""Whistle Stop game state machine.

The route is modeled as a linear list of RouteSlot objects.
Players have positions (index into the route).
Each round: simultaneous card selection, low-to-high reveal,
place card, move train, score.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
import random
import copy

from cards import Card, Deck, build_deck


@dataclass
class RouteSlot:
    """A single slot on the route."""
    card: Card
    placed_by: int  # Player ID who placed it (-1 for depot)
    index: int       # Position in route (0 = depot end)


@dataclass
class Player:
    """A player's state."""
    id: int
    faction: str
    hand: List[Card] = field(default_factory=list)
    vp: int = 0
    position: int = 0   # Index into the route
    cards_played: int = 0

    def __repr__(self):
        return f"P{self.id}({self.faction[0:3]} VP:{self.vp} Pos:{self.position} Hand:{len(self.hand)})"


class GameState:
    """Full Whistle Stop game state."""

    def __init__(self, config: dict, num_players: int, seed: int = 42,
                 faction_assignments: List[str] = None):
        self.config = config
        self.rules = config["game_rules"]
        self.scoring_rules = config["scoring"]
        self.bonus_config = config["faction_bonuses"]
        self.num_players = num_players
        self.rng = random.Random(seed)
        self.seed = seed

        # Build and shuffle deck
        all_cards = build_deck(config)
        self.draw_pile = Deck(all_cards)
        self.draw_pile.shuffle(self.rng)

        # Route: linear list of RouteSlots
        self.route: List[RouteSlot] = []

        # Place the Depot (first card flipped)
        depot_card = self.draw_pile.draw_one()
        depot_card.placed_by = -1
        self.route.append(RouteSlot(card=depot_card, placed_by=-1, index=0))

        # Assign factions
        factions = list(self.rules["factions"])
        if faction_assignments:
            assigned = faction_assignments[:num_players]
        else:
            self.rng.shuffle(factions)
            assigned = factions[:num_players]

        # Create players
        self.players: List[Player] = []
        for i in range(num_players):
            p = Player(id=i, faction=assigned[i], position=0)
            self.players.append(p)

        # Deal starting hands
        for p in self.players:
            p.hand = self.draw_pile.draw(self.rules["hand_size"])

        # Game state flags
        self.round_number: int = 0
        self.game_over: bool = False
        self.station_placed: bool = False
        self.station_placer_id: int = -1
        self.final_round: bool = False

        # Logging
        self.log: List[str] = []

    def _log(self, msg: str):
        self.log.append(f"R{self.round_number}: {msg}")

    # ------------------------------------------------------------------
    # Round execution
    # ------------------------------------------------------------------

    def play_round(self, card_choices: List[Tuple[int, Card]],
                   placement_choices: List[str],
                   movement_fn=None) -> List[dict]:
        """Execute one full round.

        Args:
            card_choices: List of (player_id, chosen_card) tuples
            placement_choices: List of "start" or "end" per player (where to extend route)
            movement_fn: Callable(player, card, game) -> dict with movement params.
                         Called AFTER card placement so AI sees the updated route.

        Returns:
            List of round result dicts per player (in reveal order).
        """
        self.round_number += 1
        results = []

        # Sort by rank (low to high) for reveal order
        # Ties are resolved randomly (shuffle among tied players)
        indexed = list(enumerate(card_choices))
        self.rng.shuffle(indexed)  # Randomize ties
        indexed.sort(key=lambda x: x[1][1].rank)

        for order_idx, (orig_idx, (pid, card)) in enumerate(indexed):
            player = self.players[pid]

            # Remove card from hand
            player.hand = [c for c in player.hand if not (c.faction == card.faction and c.rank == card.rank)]
            player.cards_played += 1

            # Place card on route
            place_end = placement_choices[orig_idx]
            slot = self._place_card(card, pid, place_end)

            # Movement decision happens AFTER placement (AI sees updated route)
            if movement_fn:
                mv = movement_fn(player, card, self)
            else:
                # Default: move forward max steps
                max_steps = card.rank + self._get_faction_bonus_steps(player, card)
                mv = {"direction": "forward", "steps": max_steps}

            move_result = self._move_player(player, card, mv)

            # Score
            score_result = self._score_movement(player, card, move_result)

            result = {
                "player_id": pid,
                "card": card,
                "placement": place_end,
                "slot_index": slot.index,
                "move_result": move_result,
                "score_result": score_result,
                "reveal_order": order_idx,
            }
            results.append(result)

            self._log(f"P{pid} plays {card} at {place_end}, "
                      f"moves {move_result['steps_taken']} steps, "
                      f"scores {score_result['total_vp']} VP")

            # Check if station placed (10th route card)
            if len(self.route) >= self.rules["route_length_to_end"] and not self.station_placed:
                self.station_placed = True
                self.station_placer_id = pid
                self.final_round = True
                player.vp += self.rules["station_placer_bonus"]
                self._log(f"P{pid} placed the Station! +{self.rules['station_placer_bonus']} bonus VP")

        # End of round: draw back to hand size
        for p in self.players:
            cards_needed = self.rules["hand_size"] - len(p.hand)
            if cards_needed > 0 and not self.draw_pile.empty:
                drawn = self.draw_pile.draw(min(cards_needed, self.draw_pile.size))
                p.hand.extend(drawn)

        # Check game over
        if self.final_round:
            self.game_over = True

        return results

    def _place_card(self, card: Card, player_id: int, end: str) -> RouteSlot:
        """Place a card at one end of the route."""
        card.placed_by = player_id
        if end == "start":
            new_index = self.route[0].index - 1
            slot = RouteSlot(card=card, placed_by=player_id, index=new_index)
            self.route.insert(0, slot)
            # Shift all player positions right by 1 (since we inserted at front)
            for p in self.players:
                p.position += 1
        else:  # "end"
            new_index = self.route[-1].index + 1
            slot = RouteSlot(card=card, placed_by=player_id, index=new_index)
            self.route.append(slot)
        return slot

    def _get_faction_bonus_steps(self, player: Player, card: Card) -> int:
        """Calculate bonus steps from faction match."""
        if card.faction != player.faction:
            return 0

        bonus_info = self.bonus_config.get(player.faction, {})
        bonus_type = bonus_info.get("type", "")

        if bonus_type == "directional":
            # For the linear route simulation, all directional bonuses give +1
            return bonus_info.get("steps", 1)
        elif bonus_type == "conditional":
            # Orange: +1 if ending on rival's card — handled in movement
            return 0  # Applied conditionally during movement
        elif bonus_type == "special":
            # Purple: backward movement — handled as direction choice, not extra steps
            return 0
        return 0

    def _check_orange_bonus(self, player: Player, card: Card,
                            end_position: int) -> bool:
        """Check if Orange faction bonus triggers (end on rival's card)."""
        if card.faction != player.faction or player.faction != "ORANGE":
            return False
        if 0 <= end_position < len(self.route):
            slot = self.route[end_position]
            if slot.placed_by != -1 and slot.placed_by != player.id:
                return True
        return False

    def _can_move_backward(self, player: Player, card: Card) -> bool:
        """Purple faction can move backward."""
        return card.faction == player.faction and player.faction == "PURPLE"

    def _move_player(self, player: Player, card: Card,
                     move_params: dict) -> dict:
        """Move a player along the route.

        move_params:
            direction: "forward" or "backward"
            steps: number of steps to take (may be less than max)
        """
        max_steps = card.rank
        bonus_steps = self._get_faction_bonus_steps(player, card)
        total_available = max_steps + bonus_steps

        direction = move_params.get("direction", "forward")
        requested_steps = move_params.get("steps", total_available)

        # Purple can move backward; others must move forward
        if direction == "backward" and not self._can_move_backward(player, card):
            direction = "forward"

        actual_steps = min(requested_steps, total_available)

        # Track cards passed through
        start_pos = player.position
        cards_passed = []
        end_pos = start_pos

        if direction == "forward":
            for i in range(actual_steps):
                next_pos = end_pos + 1
                if next_pos >= len(self.route):
                    break
                end_pos = next_pos
        else:  # backward
            for i in range(actual_steps):
                next_pos = end_pos - 1
                if next_pos < 0:
                    break
                end_pos = next_pos

        # Collect passed-through cards (not including start, not including end)
        if end_pos > start_pos:
            for i in range(start_pos + 1, end_pos):
                if 0 <= i < len(self.route):
                    cards_passed.append(self.route[i])
        elif end_pos < start_pos:
            for i in range(start_pos - 1, end_pos, -1):
                if 0 <= i < len(self.route):
                    cards_passed.append(self.route[i])

        steps_taken = abs(end_pos - start_pos)

        # Orange bonus: if ending on rival card, get +1 step
        orange_bonus_used = False
        if self._check_orange_bonus(player, card, end_pos):
            # Try to move one more step
            if direction == "forward" and end_pos + 1 < len(self.route):
                cards_passed.append(self.route[end_pos])
                end_pos += 1
                steps_taken += 1
                orange_bonus_used = True
            elif direction == "backward" and end_pos - 1 >= 0:
                cards_passed.append(self.route[end_pos])
                end_pos -= 1
                steps_taken += 1
                orange_bonus_used = True

        player.position = end_pos

        return {
            "start_pos": start_pos,
            "end_pos": end_pos,
            "steps_taken": steps_taken,
            "cards_passed": cards_passed,
            "direction": direction,
            "bonus_steps": bonus_steps,
            "orange_bonus": orange_bonus_used,
            "max_available": total_available,
        }

    def _score_movement(self, player: Player, card_played: Card,
                        move_result: dict) -> dict:
        """Calculate VP earned from this movement."""
        pass_through_vp = 0
        landing_vp = 0

        # VP for cards passed through
        for slot in move_result["cards_passed"]:
            base = self.scoring_rules["pass_through_vp"]
            # Red cards score double
            if self.scoring_rules["red_doubles_all"] and slot.card.faction == "RED":
                base *= self.rules["red_scoring_multiplier"]
            pass_through_vp += base

        # VP for landing card
        end_pos = move_result["end_pos"]
        if 0 <= end_pos < len(self.route) and move_result["steps_taken"] > 0:
            landing_card = self.route[end_pos].card
            # Station (if it's the last card when route is full) scores 0
            if (len(self.route) >= self.rules["route_length_to_end"]
                    and end_pos == len(self.route) - 1
                    and self.station_placed):
                landing_vp = self.rules["station_vp"]
            else:
                landing_vp = landing_card.rank
                if self.scoring_rules["red_doubles_all"] and landing_card.faction == "RED":
                    landing_vp *= self.rules["red_scoring_multiplier"]

        total_vp = pass_through_vp + landing_vp

        # Wild 10 doubles total round score
        if (self.scoring_rules["ten_doubles_round"] and card_played.rank == 10):
            total_vp *= self.rules["ten_scoring_multiplier"]

        player.vp += total_vp

        return {
            "pass_through_vp": pass_through_vp,
            "landing_vp": landing_vp,
            "total_vp": total_vp,
            "ten_multiplier": card_played.rank == 10,
        }

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_route_length(self) -> int:
        return len(self.route)

    def get_route_cards(self) -> List[Card]:
        return [slot.card for slot in self.route]

    def get_winner(self) -> Optional[Player]:
        if not self.game_over:
            return None
        return max(self.players, key=lambda p: p.vp)

    def get_standings(self) -> List[Tuple[int, int]]:
        """Return [(player_id, vp)] sorted by VP descending."""
        return sorted([(p.id, p.vp) for p in self.players],
                      key=lambda x: x[1], reverse=True)
