"""Heuristic AI for Whistle Stop.

The AI makes three decisions each round:
1. Which card to play from hand
2. Where to place it (start or end of route)
3. How to move (direction and steps)

Uses a scoring system: evaluate all options, pick the highest.
Three tunable axes: skill, style, aggression.
"""

from typing import List, Dict, Tuple, Optional
import random

from cards import Card
from game_state import GameState, Player, RouteSlot


# -- Style profiles ----------------------------------------------------------

STYLE_PROFILES = {
    "balanced": {
        "description": "Well-rounded. Balances scoring with route building.",
        "high_card_weight": 1.0,
        "low_card_weight": 1.0,
        "placement_aggression": 0.5,
        "movement_greed": 1.0,   # How much to prioritize high-rank landing
        "route_build_value": 1.0,  # Value of extending route strategically
        "backward_willingness": 0.3,  # Purple: how often to consider backward
    },
    "rush": {
        "description": "Play high cards fast. Maximize movement and scoring.",
        "high_card_weight": 2.0,
        "low_card_weight": 0.3,
        "placement_aggression": 0.8,
        "movement_greed": 2.0,
        "route_build_value": 0.3,
        "backward_willingness": 0.1,
    },
    "builder": {
        "description": "Play low cards early to shape the route.",
        "high_card_weight": 0.5,
        "low_card_weight": 2.0,
        "placement_aggression": 0.3,
        "movement_greed": 0.5,
        "route_build_value": 2.0,
        "backward_willingness": 0.2,
    },
    "opportunist": {
        "description": "Adapt to the route. Score when possible, build when needed.",
        "high_card_weight": 1.2,
        "low_card_weight": 0.8,
        "placement_aggression": 0.6,
        "movement_greed": 1.5,
        "route_build_value": 0.8,
        "backward_willingness": 0.5,
    },
}


class HeuristicAI:
    """AI player for Whistle Stop."""

    def __init__(self, player_id: int, faction: str,
                 skill: float = 1.0, style: str = "balanced",
                 aggression: float = 0.5, rng_seed: int = 42):
        self.player_id = player_id
        self.faction = faction
        self.skill = max(0.0, min(1.0, skill))
        self.style_name = style
        self.style = STYLE_PROFILES.get(style, STYLE_PROFILES["balanced"])
        self.aggression = max(0.0, min(1.0, aggression))
        self.rng = random.Random(rng_seed)

    # -- Noise / mistake helpers -----------------------------------------------

    def _noisy_score(self, base: float) -> float:
        noise_range = 3.0 * (1.0 - self.skill)
        if noise_range == 0:
            return base
        return base + self.rng.uniform(-noise_range, noise_range)

    def _maybe_blunder(self, rate: float = 0.3) -> bool:
        """Skill-dependent chance of making a bad choice."""
        return self.rng.random() < rate * (1.0 - self.skill)

    # -- Card selection --------------------------------------------------------

    def choose_card(self, player: Player, game: GameState) -> Card:
        """Pick the best card to play this round."""
        if not player.hand:
            return None

        scored = []
        for card in player.hand:
            score = self._score_card_choice(card, player, game)
            scored.append((card, score))

        # Blunder: sometimes pick a random card instead
        if self._maybe_blunder(0.25):
            return self.rng.choice(player.hand)

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[0][0]

    def _score_card_choice(self, card: Card, player: Player,
                           game: GameState) -> float:
        """Score a card for how good it is to play this round."""
        route_len = game.get_route_length()
        cards_to_station = game.rules["route_length_to_end"] - route_len

        # Base value: rank determines movement
        score = card.rank * self.style["high_card_weight"]

        # Low cards are good early (route building)
        if card.rank <= 3:
            early_bonus = max(0, 5 - route_len) * self.style["low_card_weight"]
            score += early_bonus

        # High cards are better later (more route to traverse)
        if card.rank >= 7:
            late_bonus = min(route_len, 8) * self.style["high_card_weight"] * 0.5
            score += late_bonus

        # Faction match bonus — you get extra steps
        if card.faction == player.faction:
            score += 2.0

        # 10s are powerful (x2 scoring) — but only when route is long enough
        if card.rank == 10:
            if route_len >= 6:
                score += 5.0 * self.style["movement_greed"]
            else:
                score -= 2.0  # Too early, waste the doubler

        # 0s are strategic — play early to build route
        if card.rank == 0:
            if route_len < 5:
                score += 3.0 * self.style["route_build_value"]
            else:
                score -= 1.0  # Late 0s are weak

        # Approaching station: prefer cards that get us close to route end
        if cards_to_station <= 2:
            # We want high movement to reach the station
            score += card.rank * 0.5

        # Red cards score double — bonus if we'll pass through good stuff
        if card.faction == "RED":
            score += 1.0

        return self._noisy_score(score)

    # -- Placement decision ----------------------------------------------------

    def choose_placement(self, card: Card, player: Player,
                         game: GameState) -> str:
        """Choose whether to extend route at 'start' or 'end'."""
        # Evaluate both ends
        start_score = self._score_placement("start", card, player, game)
        end_score = self._score_placement("end", card, player, game)

        if self._maybe_blunder(0.15):
            return self.rng.choice(["start", "end"])

        return "start" if start_score > end_score else "end"

    def _score_placement(self, end: str, card: Card, player: Player,
                         game: GameState) -> float:
        """Score a placement option."""
        route = game.route
        pos = player.position

        if end == "end":
            # Placing at the end: good if player is near the end already
            distance_to_end = len(route) - 1 - pos
            score = -distance_to_end * 0.5  # Closer = better
            # Placing at end extends the route forward — good for forward movers
            score += 2.0 * self.style["placement_aggression"]
        else:
            # Placing at start: good if player is near the start
            distance_to_start = pos
            score = -distance_to_start * 0.5
            # Placing at start can create backward opportunities (Purple)
            if player.faction == "PURPLE":
                score += 2.0

        # High-rank cards: prefer placing where we can move toward them
        # (Placing at end means the card is ahead of most players)
        if card.rank >= 7:
            if end == "end":
                score += 1.0
            else:
                score -= 0.5

        return self._noisy_score(score)

    # -- Movement decision -----------------------------------------------------

    def choose_movement(self, card: Card, player: Player,
                        game: GameState) -> dict:
        """Choose movement direction and steps."""
        can_backward = (card.faction == player.faction
                        and player.faction == "PURPLE")

        # Score forward movement
        fwd_score, fwd_steps = self._score_movement_direction(
            "forward", card, player, game)

        # Score backward movement (Purple only)
        bwd_score, bwd_steps = (-999, 0)
        if can_backward and self.rng.random() < self.style["backward_willingness"]:
            bwd_score, bwd_steps = self._score_movement_direction(
                "backward", card, player, game)

        if bwd_score > fwd_score:
            return {"direction": "backward", "steps": bwd_steps}
        return {"direction": "forward", "steps": fwd_steps}

    def _score_movement_direction(self, direction: str, card: Card,
                                   player: Player,
                                   game: GameState) -> Tuple[float, int]:
        """Score a movement direction. Returns (score, optimal_steps)."""
        max_steps = card.rank
        # Add faction bonus for non-orange, non-purple
        if card.faction == player.faction and player.faction not in ("ORANGE", "PURPLE"):
            max_steps += 1

        pos = player.position
        best_score = -999
        best_steps = max_steps

        # Try each step count from 0 to max
        for steps in range(max_steps + 1):
            if direction == "forward":
                end_pos = min(pos + steps, len(game.route) - 1)
            else:
                end_pos = max(pos - steps, 0)

            actual_steps = abs(end_pos - pos)
            if actual_steps == 0 and steps > 0:
                continue  # Can't move further

            # Estimate VP
            vp = self._estimate_vp(pos, end_pos, direction, game, card, player)

            score = vp * self.style["movement_greed"]

            if score > best_score:
                best_score = score
                best_steps = actual_steps

        return (best_score, best_steps)

    def _estimate_vp(self, start: int, end: int, direction: str,
                     game: GameState, card: Card, player: Player) -> float:
        """Estimate VP from moving start->end."""
        if start == end:
            return 0.0

        vp = 0.0

        # Pass-through VP
        if end > start:
            for i in range(start + 1, end):
                if 0 <= i < len(game.route):
                    base = 1.0
                    if game.route[i].card.faction == "RED":
                        base *= 2.0
                    vp += base
        elif end < start:
            for i in range(start - 1, end, -1):
                if 0 <= i < len(game.route):
                    base = 1.0
                    if game.route[i].card.faction == "RED":
                        base *= 2.0
                    vp += base

        # Landing VP
        if 0 <= end < len(game.route):
            landing = game.route[end].card
            land_vp = landing.rank
            if landing.faction == "RED":
                land_vp *= 2.0
            vp += land_vp

        # 10 multiplier
        if card.rank == 10:
            vp *= 2.0

        return vp

    # -- Reasoning (for narration) ---------------------------------------------

    def choose_card_with_reasoning(self, player: Player,
                                   game: GameState) -> Tuple[Card, List[str]]:
        """Choose a card and return reasoning strings."""
        reasoning = []
        if not player.hand:
            return None, ["No cards in hand!"]

        scored = []
        for card in player.hand:
            score = self._score_card_choice(card, player, game)
            scored.append((card, score))
            reasoning.append(f"  {card.id}: score={score:.1f}")

        scored.sort(key=lambda x: x[1], reverse=True)
        chosen = scored[0][0]
        reasoning.insert(0, f"Evaluating {len(player.hand)} cards (style={self.style_name}, skill={self.skill:.1f}):")
        reasoning.append(f"**Chose {chosen.id}** (score={scored[0][1]:.1f})")
        return chosen, reasoning

    def choose_all_with_reasoning(self, player: Player,
                                  game: GameState) -> Tuple[Card, str, dict, List[str]]:
        """Full decision with reasoning. Returns (card, placement, movement, reasoning)."""
        reasoning = []

        # Card choice
        card, card_reasons = self.choose_card_with_reasoning(player, game)
        reasoning.extend(card_reasons)

        if card is None:
            return None, "end", {"direction": "forward", "steps": 0}, reasoning

        # Placement
        placement = self.choose_placement(card, player, game)
        reasoning.append(f"Placing at **{placement}** of route")

        # Movement
        movement = self.choose_movement(card, player, game)
        reasoning.append(f"Moving **{movement['direction']}** {movement['steps']} steps")

        return card, placement, movement, reasoning
