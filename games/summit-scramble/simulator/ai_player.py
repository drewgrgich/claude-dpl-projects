"""
Heuristic AI for Summit Scramble.

Uses priority-based scoring across three tunable axes:
- Skill (0.0-1.0): mistake frequency
- Style (aggressive, balanced, conservative): strategic preferences
- Aggression (0.0-1.0): willingness to play big vs. conserve cards
"""

import random
from typing import List, Dict, Optional, Tuple
from collections import defaultdict

from cards import Card, FACTIONS, FACTION_RANK, FACTION_ABILITIES
from game_state import (
    GameState, Player, Formation, FormationType,
    classify_formation, formation_beats,
)


# ---------------------------------------------------------------------------
# Style profiles
# ---------------------------------------------------------------------------

STYLE_PROFILES = {
    "balanced": {
        "description": "Well-rounded default play.",
        "lead_big_threshold": 0.5,     # willingness to lead with big cards
        "pass_threshold": 0.3,         # how readily to pass
        "ability_value": 1.0,          # how much to value triggering abilities
        "acceleration_weight": 1.0,    # value of shedding cards
        "disruption_weight": 1.0,      # value of disrupting opponents
        "conservation_weight": 1.0,    # value of keeping strong cards
    },
    "aggressive": {
        "description": "Play big, shed fast, trigger abilities.",
        "lead_big_threshold": 0.3,
        "pass_threshold": 0.5,         # more willing to pass weak tricks
        "ability_value": 1.5,
        "acceleration_weight": 1.5,
        "disruption_weight": 0.8,
        "conservation_weight": 0.5,
    },
    "conservative": {
        "description": "Hoard strong cards, pass often, strike when ready.",
        "lead_big_threshold": 0.7,
        "pass_threshold": 0.2,         # less willing to pass
        "ability_value": 0.8,
        "acceleration_weight": 0.8,
        "disruption_weight": 0.5,
        "conservation_weight": 1.8,
    },
    "rush": {
        "description": "Shed cards ASAP. Minimize hand size at all costs.",
        "lead_big_threshold": 0.2,
        "pass_threshold": 0.6,
        "ability_value": 1.2,
        "acceleration_weight": 2.0,
        "disruption_weight": 0.3,
        "conservation_weight": 0.3,
    },
}


class HeuristicAI:
    """Priority-based heuristic AI player."""

    def __init__(self, skill: float = 1.0, style: str = "balanced",
                 aggression: float = 0.5, rng_seed: int = 42):
        self.skill = max(0.0, min(1.0, skill))
        self.style_name = style
        self.style = STYLE_PROFILES.get(style, STYLE_PROFILES["balanced"])
        self.aggression = max(0.0, min(1.0, aggression))
        self.rng = random.Random(rng_seed)

    # -------------------------------------------------------------------
    # Skill-based mistakes
    # -------------------------------------------------------------------

    def _noisy_score(self, base: float) -> float:
        noise_range = 3.0 * (1.0 - self.skill)
        if noise_range == 0:
            return base
        return base + self.rng.uniform(-noise_range, noise_range)

    def _miss_opportunity(self) -> bool:
        """Beginners sometimes miss good plays."""
        rate = 0.25 * (1.0 - self.skill)
        return self.rng.random() < rate

    def _bad_timing(self) -> bool:
        rate = 0.15 * (1.0 - self.skill)
        return self.rng.random() < rate

    # -------------------------------------------------------------------
    # Leading (choosing what to play when starting a new trick)
    # -------------------------------------------------------------------

    def choose_lead(self, player: Player, game: GameState) -> Optional[Formation]:
        """Choose a formation to lead with."""
        formations = game.get_legal_formations(player)
        if not formations:
            return None

        scored = []
        for f in formations:
            score = self._score_lead(f, player, game)
            scored.append((f, score))

        scored.sort(key=lambda x: -x[1])

        # Pick best (with some noise for low skill)
        if scored:
            return scored[0][0]
        return None

    def _score_lead(self, f: Formation, player: Player, game: GameState) -> float:
        """Score a formation for leading."""
        score = 0.0
        cards_shed = len(f.cards)
        hand_after = player.hand_size - cards_shed

        # Acceleration: shedding cards is good (racing game!)
        accel = cards_shed * 2.0 * self.style["acceleration_weight"]
        score += accel

        # Going out bonus: huge if this empties the hand
        if hand_after == 0:
            return self._noisy_score(1000.0)

        # Ability trigger value
        if f.triggers_power:
            ability_bonus = 5.0 * self.style["ability_value"]
            # Extra value for acceleration abilities
            if f.ftype == FormationType.SOLO:
                ability = FACTION_ABILITIES.get(f.faction, "")
                if ability in ("streamline", "recalibrate"):
                    ability_bonus += 3.0 * self.style["acceleration_weight"]
            score += ability_bonus

        # Conservation: penalize using high cards early
        avg_rank = sum(c.rank for c in f.cards) / len(f.cards)
        conservation_penalty = (avg_rank / 10.0) * 3.0 * self.style["conservation_weight"]

        # Reduce penalty if we're close to going out
        if player.hand_size <= 5:
            conservation_penalty *= 0.3

        score -= conservation_penalty

        # Multi-card formations are harder to beat (good for winning trick)
        if f.ftype in (FormationType.SURGE, FormationType.DAISY_CHAIN):
            score += 2.0 * (1.0 - self.style["conservation_weight"] * 0.3)

        # Confetti Cannon: powerful but costs 4 cards
        if f.ftype == FormationType.CONFETTI_CANNON:
            score += 8.0  # very strong play
            if hand_after <= 3:
                score += 5.0  # near finish!

        # Aggression modifier
        score += (self.aggression - 0.5) * 3.0

        # Lead with lower cards when possible (save high for following)
        if f.rank <= 4 and f.ftype == FormationType.SOLO:
            score += 1.5  # lead low is generally good

        return self._noisy_score(score)

    # -------------------------------------------------------------------
    # Following (beat current formation or pass)
    # -------------------------------------------------------------------

    def choose_follow(self, player: Player, game: GameState) -> Optional[Formation]:
        """Choose to play a formation to beat current, or None to pass."""
        legal = game.get_legal_formations(player)
        if not legal:
            return None  # must pass

        scored = []
        for f in legal:
            score = self._score_follow(f, player, game)
            scored.append((f, score))

        scored.sort(key=lambda x: -x[1])

        # Compare best play vs. passing
        if scored:
            best_play, best_score = scored[0]

            # Pass threshold: sometimes better to conserve
            pass_score = self._score_pass(player, game)

            if best_score > pass_score:
                return best_play

        return None  # pass

    def _score_follow(self, f: Formation, player: Player, game: GameState) -> float:
        """Score a formation for following (beating current trick)."""
        score = 0.0
        cards_shed = len(f.cards)
        hand_after = player.hand_size - cards_shed

        # Going out is always best
        if hand_after == 0:
            return self._noisy_score(1000.0)

        # Winning trick value
        score += 3.0

        # Ability trigger
        if f.triggers_power:
            ability_bonus = 5.0 * self.style["ability_value"]
            if f.ftype == FormationType.SOLO:
                ability = FACTION_ABILITIES.get(f.faction, "")
                if ability in ("streamline", "recalibrate"):
                    ability_bonus += 3.0 * self.style["acceleration_weight"]
            score += ability_bonus

        # Cards shed
        score += cards_shed * 1.5 * self.style["acceleration_weight"]

        # Conservation cost
        avg_rank = sum(c.rank for c in f.cards) / len(f.cards)
        conservation_cost = (avg_rank / 10.0) * 4.0 * self.style["conservation_weight"]
        if player.hand_size <= 5:
            conservation_cost *= 0.2
        score -= conservation_cost

        # Penalize barely-beating (wastes a high card)
        current = game.current_formation
        if current and f.rank == current.rank + 1:
            score -= 0.5  # minimal advantage, might get beaten again

        # Aggression
        score += (self.aggression - 0.5) * 2.0

        return self._noisy_score(score)

    def _score_pass(self, player: Player, game: GameState) -> float:
        """Score the value of passing."""
        base = 2.0 * self.style["conservation_weight"]

        # Pass more when hand is strong (save for later)
        high_cards = sum(1 for c in player.hand if c.rank >= 8)
        base += high_cards * 0.5 * self.style["conservation_weight"]

        # Pass less when close to going out
        if player.hand_size <= 4:
            base -= 3.0

        # Pass less when we need to shed cards
        base -= self.style["acceleration_weight"] * 0.5

        return self._noisy_score(base)

    # -------------------------------------------------------------------
    # Interrupt decisions (Cannon / Trip-Up)
    # -------------------------------------------------------------------

    def choose_interrupt(self, player: Player, game: GameState) -> Optional[Formation]:
        """Decide whether to fire a Cannon or Trip-Up interrupt."""
        if self._miss_opportunity():
            return None

        interrupts = game.get_interrupt_formations(player)
        if not interrupts:
            return None

        best = None
        best_score = -999.0

        for intr in interrupts:
            score = self._score_interrupt(intr, player, game)
            if score > best_score:
                best_score = score
                best = intr

        # Only interrupt if it's clearly worth it
        if best_score > 5.0:
            return best
        return None

    def _score_interrupt(self, f: Formation, player: Player,
                         game: GameState) -> float:
        """Score an interrupt play."""
        hand_after = player.hand_size - len(f.cards)

        # Going out = always do it
        if hand_after == 0:
            return 1000.0

        score = 0.0

        if f.ftype == FormationType.TRIP_UP:
            # Trip-Up: surgical, costs 1 card, seize initiative
            score += 8.0
            score += (1.0 / max(1, player.hand_size)) * 5.0  # better when hand small
            # But 0 cards are also defensive insurance
            score -= 3.0 * self.style["conservation_weight"]

        elif f.ftype == FormationType.CONFETTI_CANNON:
            # Cannon: costs 4 cards, very powerful
            score += 6.0
            score += 4 * 2.0 * self.style["acceleration_weight"]  # shed 4 cards!
            if f.triggers_power:
                score += 4.0 * self.style["ability_value"]
            if hand_after <= 3:
                score += 8.0  # near finish!
            # Conservation cost of using 4 cards of same rank
            score -= f.rank * 0.3 * self.style["conservation_weight"]

        score += (self.aggression - 0.5) * 3.0
        return self._noisy_score(score)

    # -------------------------------------------------------------------
    # Ability choices
    # -------------------------------------------------------------------

    def choose_ability_faction(self, formation: Formation,
                               player: Player, game: GameState) -> str:
        """For Surges/Cannons, choose which faction ability to trigger."""
        if not formation.triggers_power:
            return None

        best_ability = None
        best_score = -999.0

        factions_in_formation = set(c.faction for c in formation.cards)
        for faction in factions_in_formation:
            ability = FACTION_ABILITIES[faction]
            score = self._score_ability(ability, player, game)
            if score > best_score:
                best_score = score
                best_ability = ability

        return best_ability

    def _score_ability(self, ability: str, player: Player,
                       game: GameState) -> float:
        """Score the value of a specific ability in current game state."""
        score = 0.0

        if ability == "streamline":
            # Discard 1 card — pure acceleration
            score = 6.0 * self.style["acceleration_weight"]
            if player.hand_size <= 4:
                score += 5.0  # very close to going out!

        elif ability == "recalibrate":
            # Draw 1, discard 2 — net -1 card + hand improvement
            score = 7.0 * self.style["acceleration_weight"]
            # Less valuable if hand is already small (risk drawing bad)
            if player.hand_size <= 3:
                score -= 2.0

        elif ability == "rotation":
            # Pass cards around — disruption
            score = 4.0 * self.style["disruption_weight"]
            # Better when opponents are close to going out
            for p in game.get_active_players():
                if p.pid != player.pid and p.hand_size <= 4:
                    score += 2.0  # disrupt a leader

        elif ability == "scout":
            # Peek and swap — hand quality improvement
            score = 3.5
            # Better with more low-value cards to swap out
            low_cards = sum(1 for c in player.hand if c.rank <= 3)
            score += low_cards * 0.5

        elif ability == "revelation":
            # Intel + swap with any other active player (no restriction)
            eligible = [p for p in game.get_active_players()
                       if p.pid != player.pid and p.hand_size > 0]
            if eligible:
                score = 5.0 * self.style["disruption_weight"]
                # Extra value when targeting leader (close to going out)
                leader = min(eligible, key=lambda p: p.hand_size)
                if leader.hand_size <= 4:
                    score += 3.0  # stealing from a near-winner is huge
            else:
                score = -10.0  # can't use it

        elif ability == "reclaim":
            # Swap with Base Camp — quality improvement
            score = 4.0
            if game.base_camp.size > 10:
                score += 2.0  # more options in camp

        return self._noisy_score(score)

    def make_ability_choices(self, ability: str, player: Player,
                             game: GameState) -> dict:
        """Generate the choices dict for executing an ability."""
        choices = {}

        if ability == "rotation":
            # Choose direction to hurt the leader most
            active = game.get_active_players()
            others = [p for p in active if p.pid != player.pid]

            # Find the player closest to winning
            if others:
                leader = min(others, key=lambda p: p.hand_size)
                # Pass left or right depending on where leader is
                left_neighbor = game._next_active_player(player.pid)
                if left_neighbor == leader.pid:
                    choices["direction"] = "left"
                else:
                    choices["direction"] = "right"
            else:
                choices["direction"] = "left"

            # Choose card to pass: worst card in hand
            if player.hand:
                # Pass lowest-value card
                worst = self._pick_worst_card(player)
                choices["cards_to_pass"] = {player.pid: worst}

        elif ability == "scout":
            game._ensure_trail(2)
            top_cards = game.trail.peek(min(2, game.trail.size))
            if top_cards and player.hand:
                # Find worst card in hand and best card in top
                worst_hand = self._pick_worst_card(player)
                best_trail = max(top_cards, key=lambda c: c.rank)
                if best_trail.rank > worst_hand.rank:
                    choices["swap_from_hand"] = worst_hand
                    choices["swap_from_trail"] = best_trail

        elif ability == "streamline":
            if player.hand:
                choices["discard"] = self._pick_worst_card(player)

        elif ability == "recalibrate":
            # Will draw 1 first, then discard 2
            # Pre-decide to discard 2 worst (AI will see drawn card)
            if len(player.hand) >= 2:
                sorted_hand = sorted(player.hand, key=lambda c: self._card_value(c))
                choices["discards"] = sorted_hand[:2]

        elif ability == "revelation":
            eligible = [p for p in game.get_active_players()
                       if p.pid != player.pid and p.hand_size > 0]
            if eligible:
                # Target the player closest to winning (steal from leaders)
                target = min(eligible, key=lambda p: p.hand_size)
                choices["target"] = target.pid
                # Take their best card, give them our worst
                if target.hand and player.hand:
                    take = max(target.hand, key=lambda c: self._card_value(c))
                    give = self._pick_worst_card(player)
                    choices["take_card"] = take
                    choices["give_card"] = give

        elif ability == "reclaim":
            if game.base_camp.cards and player.hand:
                # Find best card in base camp
                best_camp = max(game.base_camp.cards,
                              key=lambda c: self._card_value(c))
                worst_hand = self._pick_worst_card(player)
                if self._card_value(best_camp) > self._card_value(worst_hand):
                    choices["take_from_camp"] = best_camp
                    choices["give_to_camp"] = worst_hand

        return choices

    # -------------------------------------------------------------------
    # Card valuation helpers
    # -------------------------------------------------------------------

    def _card_value(self, card: Card) -> float:
        """How valuable is this card to hold?"""
        value = card.rank * 1.0
        # High cards are disproportionately valuable (can beat more things)
        if card.rank >= 8:
            value += 2.0
        if card.rank == 10:
            value += 3.0
        # 0s have special Trip-Up value
        if card.rank == 0:
            value += 4.0
        # Higher faction priority is a small bonus for solos
        value += (5 - FACTION_RANK[card.faction]) * 0.2
        return value

    def _pick_worst_card(self, player: Player) -> Card:
        """Pick the least valuable card in hand."""
        return min(player.hand, key=lambda c: self._card_value(c))

    # -------------------------------------------------------------------
    # Stored Surge decisions
    # -------------------------------------------------------------------

    def should_store_surge(self, player: Player, game: GameState,
                           winning_formation: Formation) -> bool:
        """Decide whether to store a power card instead of triggering now."""
        if not game.use_stored_surge:
            return False
        if player.stored_surge is not None:
            return False
        if player.hand_size <= 3:
            return False  # too close to end, trigger now

        # Store if hand is large and we want a bigger effect later
        if player.hand_size > 7 and self.aggression < 0.6:
            return self.rng.random() < 0.3
        return False

    def should_release_surge(self, player: Player, game: GameState) -> bool:
        """Decide whether to release stored surge for double trigger."""
        if not player.stored_surge:
            return False
        # Release when hand is small (maximize acceleration impact)
        if player.hand_size <= 5:
            return True
        return self.rng.random() < 0.2
