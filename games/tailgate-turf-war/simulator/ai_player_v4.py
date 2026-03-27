"""
AI player for v0.1 — heuristic zone deployment with action card tactics.

Styles:
  balanced  — moderate spread, moderate saving, plays it safe
  aggressive — contest many zones, spend cards freely
  sniper    — focus on 1-2 zones with strong combos
  hoarder   — save cards for later rounds
  spread    — thin coverage everywhere, chase Lone Wolf bonus
"""

import random
from typing import List, Dict
from collections import defaultdict

from cards_v4 import (
    Card, COLORS, COLOR_ORDER,
    CARD_TYPE_NUMBER, CARD_TYPE_MASCOT, CARD_TYPE_ACTION, CARD_TYPE_DUD,
    ACTION_SHIELD, ACTION_BOMB, ACTION_SWAP, ACTION_BOUNTY,
)


STYLE_PROFILES = {
    "balanced": {
        "description": "Well-rounded play.",
        "zones_per_round": (2, 3),
        "save_ratio": 0.30,
        "mascot_combo_weight": 2.5,
        "spread_bonus": 1.2,
        "home_field_weight": 1.5,
        "action_aggression": 0.5,
    },
    "aggressive": {
        "description": "Contest many zones, play lots of cards.",
        "zones_per_round": (3, 4),
        "save_ratio": 0.15,
        "mascot_combo_weight": 1.5,
        "spread_bonus": 2.5,
        "home_field_weight": 1.0,
        "action_aggression": 0.8,
    },
    "sniper": {
        "description": "Focus on 1-2 zones with strong plays.",
        "zones_per_round": (1, 2),
        "save_ratio": 0.35,
        "mascot_combo_weight": 3.5,
        "spread_bonus": 0.3,
        "home_field_weight": 2.0,
        "action_aggression": 0.6,
    },
    "hoarder": {
        "description": "Save cards for later rounds.",
        "zones_per_round": (1, 3),
        "save_ratio": 0.45,
        "mascot_combo_weight": 1.5,
        "spread_bonus": 0.8,
        "home_field_weight": 1.5,
        "action_aggression": 0.3,
    },
    "spread": {
        "description": "Thin coverage everywhere.",
        "zones_per_round": (3, 4),
        "save_ratio": 0.20,
        "mascot_combo_weight": 1.0,
        "spread_bonus": 3.0,
        "home_field_weight": 1.0,
        "action_aggression": 0.4,
    },
}


class AIPlayerV4:
    def __init__(self, player_id: int, skill: float = 1.0,
                 style: str = "balanced", rng_seed: int = 42):
        self.player_id = player_id
        self.skill = max(0.0, min(1.0, skill))
        self.style_name = style
        self.style = STYLE_PROFILES.get(style, STYLE_PROFILES["balanced"])
        self.rng = random.Random(rng_seed)

    # ─── CARD PASSING ────────────────────────────────────────────────────

    def choose_pass(self, player, game_state, pass_count: int) -> List[Card]:
        """Choose cards to pass left."""
        hand = list(player.hand)
        if len(hand) <= pass_count:
            return hand

        # Score each card — lower score = more willing to pass
        scored = []
        for card in hand:
            score = self._card_keep_value(card, hand, game_state)
            scored.append((card, score))

        scored.sort(key=lambda x: x[1])
        return [c for c, s in scored[:pass_count]]

    def _card_keep_value(self, card: Card, hand: List[Card],
                         game_state) -> float:
        """How much do we want to keep this card?"""
        if card.is_action:
            # Actions are valuable — keep them
            return 8.0 + self.style["action_aggression"] * 3
        if card.is_mascot:
            # Mascots are valuable if we have high-rank cards to pair with
            best_rank = max((c.effective_rank for c in hand if c.has_rank), default=0)
            return best_rank * self.style["mascot_combo_weight"] * 0.5
        if card.is_dud:
            # Duds are mediocre — rank 5 with action disguise
            return 5.0
        # Number cards: higher rank = more valuable
        score = card.rank
        # Home field potential
        matching = sum(1 for c in hand if c.color == card.color and c.has_rank)
        if matching >= 2:
            score += 1.5 * self.style["home_field_weight"]
        return score

    # ─── DEPLOYMENT ──────────────────────────────────────────────────────

    def choose_deployment(self, player, game_state, round_num: int) -> Dict[str, List[Card]]:
        """
        Deploy cards to zones.  Priority order:
          1. Mascot combos — pair mascots with high-rank naturals (rank >= 5)
          2. Number/Dud cards — fill zones with best available ranked cards
          3. Action cards — attach to already-populated zones for maximum impact
          4. Validate — ensure no naked modifiers remain
        """
        hand = list(player.hand)
        if not hand:
            return {}

        rounds_remaining = game_state.num_rounds - round_num
        colors = game_state.colors
        cond_effect = game_state.get_active_condition_effect()

        # Decide how many cards to play
        min_cpr_cfg = game_state.rules.get("min_cards_per_round", 3)
        if isinstance(min_cpr_cfg, dict):
            min_cpr = min_cpr_cfg.get(game_state.pkey, 3)
        else:
            min_cpr = min_cpr_cfg
        cards_to_play = self._decide_cards_to_play(hand, round_num, rounds_remaining, min_cpr)

        # Filter hand based on condition
        playable = self._filter_for_condition(hand, cond_effect)

        # Determine max/min zones from condition
        max_zones = 4
        min_zones = 0
        if cond_effect == "max_2_zones":
            max_zones = 2
        elif cond_effect == "min_2_zones":
            min_zones = 2

        # Cap by condition
        if cond_effect == "max_cards_4":
            cards_to_play = min(cards_to_play, 4)

        assignments: Dict[str, List[Card]] = defaultdict(list)
        used = set()

        # ── Priority 1: Mascot combos (if allowed) ──
        # Only pair mascots with rank >= 5 naturals; rank 0 pairings are worthless
        if cond_effect != "no_mascots":
            mascots = [c for c in playable if c.is_mascot and c not in used]
            naturals = sorted(
                [c for c in playable if c.is_number and c not in used],
                key=lambda c: c.effective_rank, reverse=True
            )
            for mascot in mascots:
                if cards_to_play < 2:
                    break
                for nat in naturals:
                    if nat in used or nat.effective_rank < 5:
                        break
                    # Play at zone matching natural's color for home field
                    zone_color = nat.color
                    if self._can_add_to_zone(zone_color, assignments, max_zones, min_zones,
                                             cond_effect, used, [mascot, nat]):
                        assignments[zone_color].append(mascot)
                        assignments[zone_color].append(nat)
                        used.add(mascot)
                        used.add(nat)
                        cards_to_play -= 2
                        break

        # ── Priority 2: Number/Dud cards — build zone presence first ──
        remaining_ranked = [c for c in playable if c not in used and (c.has_rank or c.is_dud)]
        remaining_ranked.sort(key=lambda c: c.effective_rank, reverse=True)

        # Reserve slots for action cards we intend to play
        action_cards = [c for c in playable if c.is_action and c not in used]
        action_slots = min(len(action_cards), cards_to_play)
        ranked_slots = cards_to_play - action_slots

        zone_counts = defaultdict(int, {c: len(cards) for c, cards in assignments.items()})
        vp = game_state.base_vp

        for _ in range(ranked_slots):
            best_score = -999
            best_card = None
            best_zone = None

            for card in remaining_ranked:
                if card in used:
                    continue

                for color in colors:
                    if not self._can_add_card_to_zone(
                        card, color, assignments, max_zones, cond_effect, used
                    ):
                        continue

                    score = self._score_card_at_zone(card, color, vp, zone_counts)

                    if self.skill < 1.0 and self.rng.random() < 0.3 * (1 - self.skill):
                        score += self.rng.uniform(-3, 3)

                    if score > best_score:
                        best_score = score
                        best_card = card
                        best_zone = color

            if best_card is None:
                # Couldn't place any more ranked cards — give slots back to actions
                action_slots += (ranked_slots - _)
                break

            assignments[best_zone].append(best_card)
            used.add(best_card)
            zone_counts[best_zone] += 1

        # ── Priority 3: Action cards — attach to zones that already have strength ──
        for card in action_cards:
            if card in used or action_slots <= 0:
                continue
            best_zone = self._choose_zone_for_action(card, assignments, colors,
                                                     max_zones, cond_effect, used)
            if best_zone:
                assignments[best_zone].append(card)
                used.add(card)
                action_slots -= 1

        # If we still have action_slots left (actions couldn't place), use them
        # for any remaining ranked cards
        if action_slots > 0:
            for card in remaining_ranked:
                if card in used or action_slots <= 0:
                    continue
                best_score = -999
                best_zone = None
                for color in colors:
                    if not self._can_add_card_to_zone(
                        card, color, assignments, max_zones, cond_effect, used
                    ):
                        continue
                    score = self._score_card_at_zone(card, color, vp, zone_counts)
                    if score > best_score:
                        best_score = score
                        best_zone = color
                if best_zone:
                    assignments[best_zone].append(card)
                    used.add(card)
                    zone_counts[best_zone] += 1
                    action_slots -= 1

        # Enforce min_zones: if we haven't reached min, redistribute
        if min_zones > 0 and len([c for c in assignments if assignments[c]]) < min_zones:
            assignments = self._enforce_min_zones(assignments, min_zones, colors)

        # Safety net: no naked modifiers (action/mascot) without an anchor (number/dud)
        assignments = self._ensure_anchors(assignments, hand, used)

        return dict(assignments)

    def _ensure_anchors(self, assignments: dict, full_hand: List[Card],
                         used: set) -> dict:
        """
        Post-deployment sanity check: prevent playing naked modifiers
        (action cards / mascots) at a zone with no anchor (number / dud).

        For each zone with modifiers but no anchor:
          1. Try to rescue it by attaching the cheapest unused anchor card.
          2. If no anchors remain, pull the modifiers back into the hand.
        """
        zones_to_cancel = []
        remaining = [c for c in full_hand if c not in used]

        for zone_color, cards in assignments.items():
            if not cards:
                continue

            has_anchor = any(c.has_rank for c in cards)  # numbers + duds
            has_modifier = any(c.is_action or c.is_mascot for c in cards)

            if has_modifier and not has_anchor:
                # Look for cheapest unused anchor to rescue this zone
                available_anchors = sorted(
                    [c for c in remaining if c.has_rank],
                    key=lambda c: c.effective_rank
                )
                if available_anchors:
                    rescue = available_anchors[0]
                    cards.append(rescue)
                    used.add(rescue)
                    remaining.remove(rescue)
                else:
                    zones_to_cancel.append(zone_color)

        # Pull back doomed deployments
        for zone_color in zones_to_cancel:
            doomed = assignments.pop(zone_color, [])
            for c in doomed:
                used.discard(c)

        return assignments

    def _filter_for_condition(self, hand: List[Card], cond_effect: str) -> List[Card]:
        if cond_effect == "no_mascots":
            return [c for c in hand if not c.is_mascot]
        return list(hand)

    def _can_add_card_to_zone(self, card: Card, zone_color: str,
                               assignments: dict, max_zones: int,
                               cond_effect: str, used: set) -> bool:
        zones_used = set(c for c, cards in assignments.items() if cards)
        if zone_color not in zones_used and len(zones_used) >= max_zones:
            return False

        if cond_effect == "unique_colors_per_zone":
            existing_colors = set(c.color for c in assignments.get(zone_color, [])
                                  if c.has_rank or c.is_mascot)
            if card.color in existing_colors and (card.has_rank or card.is_mascot):
                return False

        return True

    def _can_add_to_zone(self, zone_color, assignments, max_zones, min_zones,
                          cond_effect, used, cards_to_add):
        zones_used = set(c for c, cards in assignments.items() if cards)
        if zone_color not in zones_used and len(zones_used) >= max_zones:
            return False
        return True

    def _enforce_min_zones(self, assignments, min_zones, colors):
        """Redistribute cards to meet minimum zone count."""
        zones_used = [c for c in assignments if assignments[c]]
        if len(zones_used) >= min_zones:
            return assignments

        # Find zones with multiple cards and split
        all_cards = [(c, color) for color, cards in assignments.items() for c in cards]
        new_assignments = defaultdict(list)
        available_zones = list(colors)

        for card, orig_zone in all_cards:
            if len(new_assignments) < min_zones and orig_zone in new_assignments:
                # Put in a new zone
                for z in available_zones:
                    if z not in new_assignments or not new_assignments[z]:
                        new_assignments[z].append(card)
                        break
                else:
                    new_assignments[orig_zone].append(card)
            else:
                new_assignments[orig_zone].append(card)

        return dict(new_assignments)

    def _choose_zone_for_action(self, card: Card, assignments: dict,
                                 colors: list, max_zones: int,
                                 cond_effect: str, used: set) -> str:
        """Pick the best zone for an action card.

        Actions are placed AFTER number cards, so assignments already has
        ranked cards in zones.  We attach actions to populated zones.
        """
        # Helper: zones with ranked cards and their total strength
        def populated_zones():
            result = {}
            for color in colors:
                cards_there = assignments.get(color, [])
                ranked = [c for c in cards_there if c.has_rank]
                if ranked:
                    result[color] = sum(c.effective_rank for c in ranked)
            return result

        if card.action_type == ACTION_SHIELD:
            # Shield protects our strongest stack
            pz = populated_zones()
            if pz:
                return max(pz, key=pz.get)
            return None  # Don't play Shield to an empty zone

        elif card.action_type == ACTION_BOMB:
            # Bomb: prefer zones where we're present but weaker (levels the field).
            # Also fine at populated zones where we want disruption.
            aggression = self.style["action_aggression"]
            pz = populated_zones()

            zone_scores = {}
            for color in colors:
                cards_there = assignments.get(color, [])
                strength = pz.get(color, 0)
                count = len(cards_there)
                if count > 0:
                    # Present but weak — bomb helps the most
                    zone_scores[color] = count * 3 - strength * 0.5
                else:
                    # Empty zone: only aggressive players consider this
                    zone_scores[color] = 1.0 * aggression

            if zone_scores:
                best = max(zone_scores, key=zone_scores.get)
                if self.rng.random() < aggression * 0.4 and len(zone_scores) > 1:
                    return self.rng.choice(list(zone_scores.keys()))
                return best
            return None

        elif card.action_type == ACTION_SWAP:
            # Swap: place at a zone where we have a LOW card and ANY other
            # zone has a HIGH card (no adjacency restriction).
            # Best placement: zone with weakest card, when we have strength
            # elsewhere that could be redirected post-reveal.
            pz = populated_zones()
            best_zone = None
            best_gain = -999

            for color in colors:
                ranked_here = [c for c in assignments.get(color, []) if c.has_rank]
                if not ranked_here:
                    continue
                min_here = min(c.effective_rank for c in ranked_here)

                # Check ALL other zones (not just adjacent)
                for other_color in colors:
                    if other_color == color:
                        continue
                    other_ranked = [c for c in assignments.get(other_color, []) if c.has_rank]
                    if not other_ranked:
                        continue
                    max_other = max(c.effective_rank for c in other_ranked)
                    gain = max_other - min_here
                    if gain > best_gain:
                        best_gain = gain
                        best_zone = color

            if best_zone and best_gain > 0:
                return best_zone

            # Fallback: place at zone with most cards (flexibility after reveal)
            occupied = [(color, len(assignments.get(color, [])))
                        for color in colors if assignments.get(color)]
            if occupied:
                return max(occupied, key=lambda x: x[1])[0]
            return None

        elif card.action_type == ACTION_BOUNTY:
            # Bounty = double VP if win, 0 if lose.
            # Only worth playing at zones where we have real strength (rank >= 5).
            aggression = self.style["action_aggression"]
            pz = populated_zones()

            # Filter to zones with meaningful strength
            strong_zones = {z: s for z, s in pz.items() if s >= 5}
            if not strong_zones:
                return None  # Don't gamble Bounty on garbage — save it

            sorted_zones = sorted(strong_zones, key=strong_zones.get, reverse=True)

            # High-aggression styles sometimes gamble on a non-top zone
            if len(sorted_zones) > 1 and self.rng.random() < aggression * 0.7:
                weights = [max(0.1, 1.0 - i * 0.4) for i in range(len(sorted_zones))]
                total_w = sum(weights)
                roll = self.rng.random() * total_w
                cumulative = 0
                for i, z in enumerate(sorted_zones):
                    cumulative += weights[i]
                    if roll <= cumulative:
                        return z
                return sorted_zones[0]
            else:
                return sorted_zones[0]

        return None

    def _decide_cards_to_play(self, hand: List[Card], round_num: int,
                               rounds_remaining: int,
                               min_cards_per_round: int = 3) -> int:
        total = len(hand)
        if rounds_remaining == 1:
            return total  # Play everything in the last round

        this_share = 1.0 / rounds_remaining
        save_ratio = self.style["save_ratio"]
        playable = total * (1.0 - save_ratio * 0.4)
        base_play = playable * this_share

        # Enforce game rule: minimum cards per round
        min_play = min(min_cards_per_round, total)
        play_count = max(min_play, round(base_play))
        return min(play_count, total)

    def _score_card_at_zone(self, card: Card, zone_color: str,
                             vp: int, zone_counts: dict) -> float:
        score = card.effective_rank

        # Home Field bonus
        if card.color == zone_color and card.is_natural:
            score += 3.0 * self.style["home_field_weight"]

        # New zone bonus
        if zone_counts[zone_color] == 0:
            score += vp * 0.35 * self.style["spread_bonus"]

        # Stacking penalty
        if zone_counts[zone_color] >= 1:
            opportunity_cost = card.effective_rank - 2
            score -= opportunity_cost * 0.4
            score -= 0.5 * zone_counts[zone_color]

        return score
