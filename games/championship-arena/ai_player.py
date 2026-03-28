"""AI decision-making for Championship Arena."""

import random
from typing import List, Dict, Tuple, Optional
from cards import HMCard
from game_state import Player, Ring, GameState


class AIPlayer:
    """Heuristic AI for Championship Arena."""

    def __init__(self, player: Player, num_players: int):
        self.player = player
        self.num_players = num_players
        self.name = f"AI-P{player.id}"

    # ─── Dice Assignment ─────────────────────────────────────────────────────────

    def assign_dice(self, gs: GameState) -> Dict[str, List[int]]:
        """
        Assign dice to rings (max 2/ring, must use 2+ rings).
        Returns dict: ring_color -> [die_values].
        """
        dice = self.player.dice[:]
        active_colors = [r.color for r in gs.active_rings]
        assignment: Dict[str, List[int]] = {c: [] for c in active_colors}

        # For Red ring: want highest dice
        # For Purple ring: want lowest dice (to lose intentionally)
        # For others: want highest dice

        red_ring = gs.get_ring_by_color("Red")
        purple_ring = gs.get_ring_by_color("Purple")

        sorted_dice = sorted(dice, reverse=True)

        # Strategy: assign best dice to contested rings
        # For Purple, put lowest dice
        if purple_ring and len(dice) >= 2:
            # Put lowest dice on Purple (to lose intentionally)
            assignment["Purple"] = [min(dice)]
            dice.remove(min(dice))
            # Put next lowest on Purple if we have another die
            if dice:
                assignment["Purple"].append(min(dice))
                dice.remove(min(dice))

        if red_ring:
            # Put highest dice on Red
            if dice:
                assignment["Red"].append(max(dice))
                dice.remove(max(dice))
                if dice:
                    assignment["Red"].append(max(dice))
                    dice.remove(max(dice))

        # Distribute remaining dice to other rings
        remaining = [r.color for r in gs.active_rings if r.color not in ["Red", "Purple"]]
        for die in dice:
            if remaining:
                ring = remaining.pop(0)
                assignment[ring].append(die)

        # Fill remaining rings
        remaining = [r.color for r in gs.active_rings if len(assignment[r.color]) == 0]
        for i, die in enumerate(dice):
            if remaining:
                ring = remaining.pop(0)
                assignment[ring].append(die)

        # Ensure at least 2 rings used
        rings_used = [c for c in active_colors if assignment[c]]
        if len(rings_used) < 2:
            # Force split
            assignment = self._force_min_rings(dice, active_colors)

        # Trim to max 2 per ring
        for c in active_colors:
            assignment[c] = assignment[c][:2]

        self.player.assigned_dice = assignment
        return assignment

    def _force_min_rings(self, dice: List[int], active_colors: List[str]) -> Dict[str, List[int]]:
        """Ensure at least 2 rings get dice."""
        assignment: Dict[str, List[int]] = {c: [] for c in active_colors}
        if len(active_colors) >= 2 and len(dice) >= 2:
            assignment[active_colors[0]] = [dice[0]]
            assignment[active_colors[1]] = [dice[1]]
        return assignment

    # ─── Card Playing ───────────────────────────────────────────────────────────

    def play_cards(self, gs: GameState):
        """
        Play one card face-down per ring with assigned dice.
        Optionally play a stunt double.
        """
        active_colors = [r.color for r in gs.active_rings]

        for ring_color in active_colors:
            if self.player.assigned_dice.get(ring_color, []):
                # Play best card for this ring
                card = self._best_card_for_ring(ring_color, gs)
                if card:
                    self.player.hand.remove(card)
                    self.player.played_cards[ring_color] = card

        # Decide whether to play stunt double
        # Save it for contested moments
        should_use_sd = self._should_use_stunt_double(gs)
        if should_use_sd and self.player.stunt_double:
            # Stunt double is already set, leave it
            pass
        elif self.player.hand and random.random() < 0.3:
            # Randomly use stunt double 30% of time
            sd_card = self.player.hand[0]
            self.player.stunt_double = sd_card
            self.player.hand.remove(sd_card)

    def _best_card_for_ring(self, ring_color: str, gs: GameState) -> Optional[HMCard]:
        """Choose the best card to play at a given ring."""
        if not self.player.hand:
            return None

        ring = gs.get_ring_by_color(ring_color)
        if not ring:
            return None

        # For Yellow ring: prefer 0 or 10
        if ring.power_type == "extremes":
            extremes = [c for c in self.player.hand if c.rank in [0, 10]]
            if extremes:
                return max(extremes, key=lambda c: c.rank)
            return max(self.player.hand, key=lambda c: c.rank)

        # For Blue ring: prefer even ranks (doubled)
        if ring.power_type == "even_double":
            evens = [c for c in self.player.hand if c.rank % 2 == 0]
            if evens:
                return max(evens, key=lambda c: c.rank)
            return max(self.player.hand, key=lambda c: c.rank)

        # For Purple ring: prefer low ranks (to lose intentionally)
        if ring.power_type == "lowest_wins":
            # Actually we want LOW ranks to lose
            return min(self.player.hand, key=lambda c: c.rank)

        # Default: play highest rank
        return max(self.player.hand, key=lambda c: c.rank)

    def _should_use_stunt_double(self, gs: GameState) -> bool:
        """Decide whether to use stunt double this round."""
        # Use if we have a good card for the most contested ring
        if not self.player.stunt_double:
            return False
        return random.random() < 0.4

    def use_talent(self, gs: GameState) -> bool:
        """
        Attempt to use talent. Returns True if used.
        Talents: Showman, Sprinter, Illusionist used before roll.
        Time Traveler, Analyst used during/after reveal.
        Collector is passive.
        """
        if self.player.talent_used_this_round or not self.player.talent:
            return False

        talent_name = self.player.talent["name"]

        # Before roll talents
        if talent_name == "The Showman":
            # Use when we expect to win at least 1 ring
            if random.random() < 0.5:  # Simple heuristic
                self.player.talent_used_this_round = True
                return True
        elif talent_name == "The Sprinter":
            # Always good to use
            self.player.talent_used_this_round = True
            return True
        elif talent_name == "The Illusionist":
            # Use on a ring where we have matching suit cards
            self.player.talent_used_this_round = True
            return True
        # Time Traveler and Analyst are resolved in simulate_round
        return False

    def draft_from_stunt_pool(self, gs: GameState) -> bool:
        """
        Attempt to draft from stunt pool.
        Returns True if drafted.
        """
        if not self.player.dice:
            return False

        for die_val in self.player.dice:
            # Find matching rank in stunt pool
            for card in gs.stunt_pool[:]:
                if card.rank == die_val:
                    gs.stunt_pool.remove(card)
                    self.player.hand.append(card)
                    return True
        return False

    def reveal_stunt_double(self) -> bool:
        """Decide whether to reveal stunt double for Peace Offering."""
        return self.player.stunt_double is not None


# ─── AI Factory ─────────────────────────────────────────────────────────────────

def create_ai_player(player: Player, num_players: int) -> AIPlayer:
    return AIPlayer(player, num_players)
