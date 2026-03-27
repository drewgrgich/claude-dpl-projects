"""
Heuristic AI player for Tailgate Turf War.

Three tunable axes:
  - Skill (0.0-1.0): Mistake frequency. 1.0 = expert, 0.0 = total beginner.
  - Style (categorical): Strategic preferences — balanced, aggressive, spread, sniper, hoarder.
  - Aggression (0.0-1.0): Willingness to commit cards. High = play more, Low = save more.

The AI decides how to allocate cards across the 6 zones each round,
accounting for hand management across all 3 rounds.
"""

import math
import random
from typing import List, Dict, Tuple, Optional
from collections import defaultdict

from cards import Card, FACTIONS, FACTION_ORDER


# ---------------------------------------------------------------------------
# Style profiles
# ---------------------------------------------------------------------------

STYLE_PROFILES = {
    "balanced": {
        "description": "Well-rounded play. Moderate spread, moderate saving.",
        "zones_per_round": (2, 3),       # Target number of zones to contest
        "cards_per_zone_pref": (1, 2),   # Preferred cards per zone
        "save_ratio": 0.33,              # Fraction of hand to save per round
        "mascot_combo_weight": 2.0,      # How much to value 0+natural combos
        "superstar_weight": 1.5,         # How much to value playing a 10
        "mishap_weight": 1.0,            # How much to value/avoid mishaps
        "underdog_seeking": 0.3,         # Tendency to go for underdog bonus
        "spread_bonus": 1.0,             # Bonus for contesting more zones
    },
    "aggressive": {
        "description": "Play many cards, contest many zones. Go for sweeps.",
        "zones_per_round": (3, 5),
        "cards_per_zone_pref": (1, 2),
        "save_ratio": 0.2,
        "mascot_combo_weight": 1.5,
        "superstar_weight": 2.0,
        "mishap_weight": 0.5,
        "underdog_seeking": 0.1,
        "spread_bonus": 2.0,
    },
    "sniper": {
        "description": "Focus on 1-2 zones with strong single cards. Underdog hunter.",
        "zones_per_round": (1, 2),
        "cards_per_zone_pref": (1, 1),
        "save_ratio": 0.4,
        "mascot_combo_weight": 2.5,
        "superstar_weight": 2.0,
        "mishap_weight": 1.5,
        "underdog_seeking": 0.8,
        "spread_bonus": 0.0,
    },
    "hoarder": {
        "description": "Save cards for later rounds + Die-Hard Fan bonus.",
        "zones_per_round": (1, 2),
        "cards_per_zone_pref": (1, 2),
        "save_ratio": 0.5,
        "mascot_combo_weight": 1.0,
        "superstar_weight": 1.0,
        "mishap_weight": 1.0,
        "underdog_seeking": 0.5,
        "spread_bonus": 0.5,
    },
    "spread": {
        "description": "Contest every zone with single cards. Sweep chaser.",
        "zones_per_round": (4, 6),
        "cards_per_zone_pref": (1, 1),
        "save_ratio": 0.25,
        "mascot_combo_weight": 1.0,
        "superstar_weight": 1.5,
        "mishap_weight": 0.5,
        "underdog_seeking": 0.5,
        "spread_bonus": 3.0,
    },
}


# ---------------------------------------------------------------------------
# AI Player
# ---------------------------------------------------------------------------

class AIPlayer:
    """Heuristic AI for Tailgate Turf War."""

    def __init__(self, player_id: int, skill: float = 1.0,
                 style: str = "balanced", aggression: float = 0.5,
                 rng_seed: int = 42):
        self.player_id = player_id
        self.skill = max(0.0, min(1.0, skill))
        self.style_name = style
        self.style = STYLE_PROFILES.get(style, STYLE_PROFILES["balanced"])
        self.aggression = max(0.0, min(1.0, aggression))
        self.rng = random.Random(rng_seed)

        # Memory across rounds
        self.cards_played_by_round: List[int] = []
        self.round_history: List[dict] = []

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def choose_deployment(self, player, game_state, round_num: int) -> Dict[str, List[Card]]:
        """
        Decide which cards to play at which zones this round.

        Returns {faction: [cards]} mapping.
        """
        hand = list(player.hand)
        if not hand:
            return {}

        config = game_state.rules
        num_rounds = config["num_rounds"]
        rounds_remaining = num_rounds - round_num  # Including this one
        vp_this_round = config["zone_vp_by_round"][round_num]

        # --- Decide how many cards to play this round ---
        cards_to_play = self._decide_cards_to_play(hand, round_num, rounds_remaining)

        # --- Forced face-up cards (Purple mishap) must be played ---
        forced = list(player.forced_faceup)
        player.forced_faceup.clear()

        # Ensure forced cards are in our play budget
        available_for_choice = [c for c in hand if c not in forced]
        remaining_to_pick = max(0, cards_to_play - len(forced))

        # --- Score each possible zone assignment ---
        assignments = self._assign_cards_to_zones(
            available_for_choice, forced, remaining_to_pick,
            game_state, round_num
        )

        self.cards_played_by_round.append(
            sum(len(cards) for cards in assignments.values())
        )

        return assignments

    # ------------------------------------------------------------------
    # Card budget per round
    # ------------------------------------------------------------------

    def _decide_cards_to_play(self, hand: List[Card], round_num: int,
                              rounds_remaining: int) -> int:
        """Decide how many cards to commit this round.

        Key insight: you need to spread cards across 3 rounds × 6 zones.
        Playing too few cards means leaving zones uncontested (free VP for opponents).
        """
        total = len(hand)

        if rounds_remaining == 1:
            # Last round: play everything except Die-Hard saves
            save_for_diehard = self._diehard_save_count(hand)
            return max(1, total - save_for_diehard)

        # Base: divide remaining cards roughly evenly across remaining rounds
        # but weight later rounds a bit more (they're worth more VP)
        round_weights = [1.0, 1.3, 1.7]  # Round 1, 2, 3
        remaining_weight = sum(round_weights[round_num:])
        this_round_share = round_weights[round_num] / remaining_weight

        # Style modifies how many we play
        save_ratio = self.style["save_ratio"]
        save_ratio *= (1.0 - self.aggression * 0.4)

        # Cards available after saving
        playable = total * (1.0 - save_ratio * 0.5)  # Don't over-save
        base_play = playable * this_round_share

        # Minimum: try to contest at least 3 zones (need 3+ cards)
        min_play = min(3, total)
        play_count = max(min_play, round(base_play))
        play_count = min(play_count, total)

        # Skill noise
        if self._maybe_misjudge():
            play_count += self.rng.choice([-2, -1, 1, 2])
            play_count = max(min_play, min(play_count, total))

        return play_count

    def _diehard_save_count(self, hand: List[Card]) -> int:
        """How many high-value cards to save for Die-Hard Fan bonus."""
        if not hand:
            return 0

        # Sort by rank descending — save the highest cards
        sorted_hand = sorted(hand, key=lambda c: c.rank, reverse=True)

        # Style influences how much we care about Die-Hard
        if self.style_name == "hoarder":
            save_target = max(2, len(hand) // 3)
        elif self.style_name == "aggressive":
            save_target = 0
        else:
            save_target = max(1, len(hand) // 4)

        return save_target

    # ------------------------------------------------------------------
    # Zone assignment
    # ------------------------------------------------------------------

    def _assign_cards_to_zones(self, available: List[Card], forced: List[Card],
                               num_to_pick: int, game_state,
                               round_num: int) -> Dict[str, List[Card]]:
        """Assign cards to zones using a scoring approach."""
        assignments: Dict[str, List[Card]] = defaultdict(list)

        # Place forced cards first (at their matching faction zone, or best zone)
        for card in forced:
            best_zone = self._best_zone_for_card(card, game_state, round_num)
            assignments[best_zone].append(card)

        if num_to_pick <= 0:
            return dict(assignments)

        # --- Generate candidate plays ---
        # Score every card for every zone
        card_zone_scores: List[Tuple[float, Card, str]] = []
        for card in available:
            for faction in FACTIONS:
                score = self._score_card_at_zone(card, faction, game_state, round_num)
                card_zone_scores.append((score, card, faction))

        # Sort by score descending
        card_zone_scores.sort(key=lambda x: x[0], reverse=True)

        # --- Greedy assignment with zone diversity ---
        used_cards = set()
        zone_counts = defaultdict(int, {f: len(cards) for f, cards in assignments.items()})
        min_zones, max_zones_target = self.style["zones_per_round"]
        min_cpz, max_cpz = self.style["cards_per_zone_pref"]
        vp = game_state.rules["zone_vp_by_round"][round_num]

        for _ in range(num_to_pick):
            best_score = -999
            best_card = None
            best_zone = None

            for card in available:
                if card in used_cards:
                    continue
                for faction in FACTIONS:
                    if zone_counts[faction] >= max_cpz and zone_counts[faction] >= 4:
                        continue

                    score = self._score_card_at_zone(card, faction, game_state, round_num)

                    # Bonus for contesting a new zone
                    if zone_counts[faction] == 0:
                        score += vp * 0.4 * self.style["spread_bonus"]

                    # Penalty for stacking into an already-filled zone
                    if zone_counts[faction] >= 1:
                        score -= 1.0 * zone_counts[faction]

                    # Skill noise
                    if self._maybe_misjudge():
                        score += self.rng.uniform(-3, 3)

                    if score > best_score:
                        best_score = score
                        best_card = card
                        best_zone = faction

            if best_card is None:
                break

            assignments[best_zone].append(best_card)
            used_cards.add(best_card)
            zone_counts[best_zone] += 1

        return dict(assignments)

    # ------------------------------------------------------------------
    # Card scoring
    # ------------------------------------------------------------------

    def _score_card_at_zone(self, card: Card, zone_faction: str,
                            game_state, round_num: int) -> float:
        """Score how good it is to play this card at this zone."""
        vp = game_state.rules["zone_vp_by_round"][round_num]
        score = 0.0

        # --- Base value: higher rank = more hype ---
        if card.is_superstar:
            score += 12.0 * self.style["superstar_weight"]
        elif card.is_mascot:
            # Mascot is best when paired with a high natural
            score += 3.0 * self.style["mascot_combo_weight"]
        else:
            score += card.rank

        # --- Faction matching: triggers mishap (can be good or bad) ---
        if card.faction == zone_faction and card.is_natural:
            mishap_score = self._score_mishap(card, zone_faction)
            score += mishap_score * self.style["mishap_weight"]

        # --- Small bonus for playing at a zone where you DON'T match ---
        # (no mishap risk, and these zones are often less contested)
        if card.faction != zone_faction:
            score += 0.3

        # --- VP scaling: later rounds worth more, so cards score higher ---
        score *= (vp / 5.0)  # Normalize around round 2

        # --- Underdog seeking: bonus for single-card plays ---
        score += self.style["underdog_seeking"] * 0.5

        # --- Spread bonus: reward contesting new zones ---
        score += self.style["spread_bonus"] * 0.3

        # --- Aggression modifier ---
        score *= (0.7 + self.aggression * 0.6)

        return self._noisy_score(score)

    def _score_mishap(self, card: Card, zone_faction: str) -> float:
        """Score the mishap effect for a matching natural card."""
        mishap_scores = {
            "RED": 1.5,       # +2 to red naturals = good
            "ORANGE": 1.0,    # Steal opponent card = good
            "YELLOW": 1.0,    # Enhanced crew bonus = good
            "GREEN": 0.5,     # Taunt = minor VP bonus
            "BLUE": 0.5,      # Value swap = situational
            "PURPLE": -0.5,   # Card returns to hand = mild downside (you reuse it)
        }
        return mishap_scores.get(zone_faction, 0.0)

    def _best_zone_for_card(self, card: Card, game_state,
                            round_num: int) -> str:
        """Find the best zone for a single card."""
        best_faction = card.faction  # Default: matching zone
        best_score = -999

        for faction in FACTIONS:
            score = self._score_card_at_zone(card, faction, game_state, round_num)
            if score > best_score:
                best_score = score
                best_faction = faction

        return best_faction

    # ------------------------------------------------------------------
    # Skill-based mistakes
    # ------------------------------------------------------------------

    def _maybe_misjudge(self) -> bool:
        """Beginners sometimes misjudge card value."""
        rate = 0.35 * (1.0 - self.skill)
        return self.rng.random() < rate

    def _noisy_score(self, base_score: float) -> float:
        """Add noise to valuation. Beginners misjudge."""
        noise_range = 4.0 * (1.0 - self.skill)
        if noise_range == 0:
            return base_score
        noise = self.rng.uniform(-noise_range, noise_range)
        return base_score + noise

    def _maybe_forget_mascot_combo(self) -> bool:
        """Beginners forget that 0 doubles the headliner."""
        rate = 0.3 * (1.0 - self.skill)
        return self.rng.random() < rate

    # ------------------------------------------------------------------
    # Advanced deployment with combos
    # ------------------------------------------------------------------

    def choose_deployment_v2(self, player, game_state,
                             round_num: int) -> Dict[str, List[Card]]:
        """
        Enhanced deployment strategy:
        1. Place forced cards (Purple mishap)
        2. Find Mascot+Natural power combos
        3. Place Superstars solo
        4. Spread remaining cards to maximize zone coverage

        Key insight: each zone is worth VP, so covering more zones
        (even with weaker cards) is usually better than stacking one zone.
        """
        hand = list(player.hand)
        if not hand:
            return {}

        config = game_state.rules
        rounds_remaining = config["num_rounds"] - round_num
        cards_to_play = self._decide_cards_to_play(hand, round_num, rounds_remaining)

        forced = list(player.forced_faceup)
        player.forced_faceup.clear()
        available = [c for c in hand if c not in forced]
        remaining_to_pick = max(0, cards_to_play - len(forced))

        assignments: Dict[str, List[Card]] = defaultdict(list)

        # Place forced cards
        for card in forced:
            best_zone = self._best_zone_for_card(card, game_state, round_num)
            assignments[best_zone].append(card)

        if remaining_to_pick <= 0:
            return dict(assignments)

        used = set()
        vp = config["zone_vp_by_round"][round_num]

        # --- Priority 1: Mascot + high natural combos ---
        # But limit to at most 1 combo per round (saves budget for zone coverage)
        combos_placed = 0
        max_combos = 1 if self.style_name != "sniper" else 2

        if not self._maybe_forget_mascot_combo():
            mascots = [c for c in available if c.is_mascot]
            naturals = sorted([c for c in available if c.is_natural],
                              key=lambda c: c.rank, reverse=True)

            for mascot in mascots:
                if remaining_to_pick < 2 or combos_placed >= max_combos:
                    break
                for nat in naturals:
                    if nat in used:
                        continue
                    combo_hype = nat.rank * 2
                    if combo_hype * 0.8 >= vp:
                        zone = self._best_zone_for_card(nat, game_state, round_num)
                        assignments[zone].append(mascot)
                        assignments[zone].append(nat)
                        used.add(mascot)
                        used.add(nat)
                        remaining_to_pick -= 2
                        combos_placed += 1
                        break

        # --- Priority 2: Superstars solo ---
        superstars = [c for c in available if c.is_superstar and c not in used]
        for ss in superstars:
            if remaining_to_pick <= 0:
                break
            zone = self._best_zone_for_card(ss, game_state, round_num)
            assignments[zone].append(ss)
            used.add(ss)
            remaining_to_pick -= 1

        # --- Priority 3: Cover uncovered zones with single strong cards ---
        remaining = sorted([c for c in available if c not in used],
                           key=lambda c: c.rank, reverse=True)
        return self._greedy_fill(remaining, assignments, remaining_to_pick,
                                 game_state, round_num)

    def _greedy_fill(self, available: List[Card],
                     assignments: Dict[str, List[Card]],
                     num_to_pick: int, game_state,
                     round_num: int) -> Dict[str, List[Card]]:
        """Fill remaining slots greedily by card-zone score.

        Includes a 'new zone' bonus to encourage spreading to all zones,
        since uncontested zones are free VP.
        """
        used = set()
        zone_counts = defaultdict(int, {f: len(c) for f, c in assignments.items()})
        _, max_cpz = self.style["cards_per_zone_pref"]
        vp = game_state.rules["zone_vp_by_round"][round_num]

        for _ in range(num_to_pick):
            best_score = -999
            best_card = None
            best_zone = None

            for card in available:
                if card in used:
                    continue
                for faction in FACTIONS:
                    if zone_counts[faction] >= max_cpz + 1:
                        continue

                    score = self._score_card_at_zone(card, faction, game_state, round_num)

                    # Bonus for contesting a NEW zone (uncontested = free VP)
                    if zone_counts[faction] == 0:
                        score += vp * 0.4 * self.style["spread_bonus"]

                    # Penalty for stacking into an already-filled zone
                    if zone_counts[faction] >= 1:
                        score -= 1.0 * zone_counts[faction]

                    if score > best_score:
                        best_score = score
                        best_card = card
                        best_zone = faction

            if best_card is None:
                break

            assignments[best_zone].append(best_card)
            used.add(best_card)
            zone_counts[best_zone] += 1

        return dict(assignments)

    # ------------------------------------------------------------------
    # Reasoning (for narration)
    # ------------------------------------------------------------------

    def choose_deployment_with_reasoning(self, player, game_state,
                                          round_num: int) -> Tuple[Dict[str, List[Card]], List[str]]:
        """Same as choose_deployment_v2 but returns reasoning strings."""
        reasoning = []
        hand = list(player.hand)
        config = game_state.rules
        rounds_remaining = config["num_rounds"] - round_num
        vp = config["zone_vp_by_round"][round_num]

        reasoning.append(f"Hand: {sorted(hand)} ({len(hand)} cards)")
        reasoning.append(f"Round {round_num+1}/{config['num_rounds']} "
                         f"(VP per zone: {vp})")

        cards_to_play = self._decide_cards_to_play(hand, round_num, rounds_remaining)
        reasoning.append(f"Plan to play {cards_to_play} cards, "
                         f"save {len(hand) - cards_to_play} for later")

        deploy = self.choose_deployment_v2(player, game_state, round_num)

        for faction, cards in deploy.items():
            if cards:
                hype_est = self._estimate_hype(cards)
                reasoning.append(f"  → {faction} Zone: {cards} (est. hype ~{hype_est})")

        return deploy, reasoning

    def _estimate_hype(self, cards: List[Card]) -> int:
        """Quick hype estimate for a set of cards."""
        if not cards:
            return 0
        superstars = [c for c in cards if c.is_superstar]
        mascots = [c for c in cards if c.is_mascot]
        naturals = [c for c in cards if c.is_natural]

        if superstars:
            headliner = 12
            crew = [c for c in cards if c is not superstars[0]]
        elif naturals:
            best = max(naturals, key=lambda c: c.rank)
            headliner = best.rank
            if mascots:
                headliner *= 2
            crew = [c for c in cards if c is not best]
            if mascots:
                crew = [c for c in crew if not c.is_mascot or c is not mascots[0]]
        else:
            headliner = 0
            crew = cards[1:]

        base = headliner + len(crew) * 2
        mult = {1: 1.0, 2: 0.8, 3: 0.6}.get(len(cards), 0.5)
        return math.ceil(base * mult)
