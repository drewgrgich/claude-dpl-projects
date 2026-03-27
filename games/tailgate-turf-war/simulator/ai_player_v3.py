"""
AI player for Tailgate Turf War v3.0 (Streamlined Edition).

Simplified scoring: Strength = best card + 2 per extra + 3 if color matches zone.
No mishaps, no multipliers, no bonuses to chase.

The core decision: where to deploy limited cards across 6 zones and 3 rounds.
"""

import math
import random
from typing import List, Dict, Tuple
from collections import defaultdict

from cards import Card, FACTIONS, FACTION_ORDER


STYLE_PROFILES = {
    "balanced": {
        "description": "Well-rounded play. Moderate spread, moderate saving.",
        "zones_per_round": (3, 4),
        "save_ratio": 0.30,
        "mascot_combo_weight": 2.5,
        "spread_bonus": 1.2,
        "home_field_weight": 1.5,
    },
    "aggressive": {
        "description": "Play many cards, contest many zones.",
        "zones_per_round": (4, 6),
        "save_ratio": 0.15,
        "mascot_combo_weight": 1.5,
        "spread_bonus": 2.5,
        "home_field_weight": 1.0,
    },
    "sniper": {
        "description": "Focus on 1-2 zones with strong plays. Mascot combo hunter.",
        "zones_per_round": (1, 3),
        "save_ratio": 0.35,
        "mascot_combo_weight": 3.5,
        "spread_bonus": 0.3,
        "home_field_weight": 2.0,
    },
    "hoarder": {
        "description": "Save cards for later rounds when VP is higher.",
        "zones_per_round": (2, 3),
        "save_ratio": 0.45,
        "mascot_combo_weight": 1.5,
        "spread_bonus": 0.8,
        "home_field_weight": 1.5,
    },
    "spread": {
        "description": "Contest every zone with single cards.",
        "zones_per_round": (5, 6),
        "save_ratio": 0.20,
        "mascot_combo_weight": 1.0,
        "spread_bonus": 3.0,
        "home_field_weight": 1.0,
    },
}


class AIPlayerV3:
    """Heuristic AI for Tailgate Turf War v3.0."""

    def __init__(self, player_id: int, skill: float = 1.0,
                 style: str = "balanced", rng_seed: int = 42):
        self.player_id = player_id
        self.skill = max(0.0, min(1.0, skill))
        self.style_name = style
        self.style = STYLE_PROFILES.get(style, STYLE_PROFILES["balanced"])
        self.rng = random.Random(rng_seed)

    def choose_deployment(self, player, game_state, round_num: int) -> Dict[str, List[Card]]:
        hand = list(player.hand)
        if not hand:
            return {}

        rounds_remaining = game_state.num_rounds - round_num
        vp = game_state.zone_vp[round_num]

        cards_to_play = self._decide_cards_to_play(hand, round_num, rounds_remaining)
        assignments: Dict[str, List[Card]] = defaultdict(list)
        used = set()

        # Priority 1: Mascot + high natural combos (max 1 per round for most styles)
        mascots = [c for c in hand if c.is_mascot]
        non_mascots = sorted([c for c in hand if not c.is_mascot],
                             key=lambda c: c.rank, reverse=True)

        max_combos = 1 if self.style_name != "sniper" else 2
        combos_placed = 0

        for mascot in mascots:
            if cards_to_play < 2 or combos_placed >= max_combos:
                break
            for nat in non_mascots:
                if nat in used or nat.rank < 5:  # Only combo with decent cards
                    break
                # Play at the zone matching the natural card's color (home field!)
                zone = nat.faction
                assignments[zone].append(mascot)
                assignments[zone].append(nat)
                used.add(mascot)
                used.add(nat)
                cards_to_play -= 2
                combos_placed += 1
                break

        # Priority 2: Fill remaining zones with best available cards
        remaining = [c for c in hand if c not in used and not c.is_mascot]
        remaining.sort(key=lambda c: c.rank, reverse=True)

        # Also consider lone mascots — they're rank 0 so usually bad solo
        lone_mascots = [c for c in hand if c.is_mascot and c not in used]

        zone_counts = defaultdict(int, {f: len(cards) for f, cards in assignments.items()})

        # Use game_state factions if available, else global FACTIONS
        factions = getattr(game_state, 'factions', FACTIONS)

        for _ in range(cards_to_play):
            best_score = -999
            best_card = None
            best_zone = None

            for card in remaining:
                if card in used:
                    continue
                for faction in factions:
                    score = self._score_card_at_zone(card, faction, vp, zone_counts)

                    if self.skill < 1.0 and self.rng.random() < 0.3 * (1 - self.skill):
                        score += self.rng.uniform(-3, 3)

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

    def _decide_cards_to_play(self, hand: List[Card], round_num: int,
                              rounds_remaining: int) -> int:
        total = len(hand)

        if rounds_remaining == 1:
            # Last round: play everything (no Die-Hard bonus in v3.0)
            return total

        round_weights = [1.0, 1.0, 1.0]  # Flat VP — all rounds equally important
        remaining_weight = sum(round_weights[round_num:])
        this_share = round_weights[round_num] / remaining_weight

        save_ratio = self.style["save_ratio"]
        playable = total * (1.0 - save_ratio * 0.4)
        base_play = playable * this_share

        min_play = min(3, total)
        play_count = max(min_play, round(base_play))
        return min(play_count, total)

    def choose_deployment_with_reasoning(self, player, game_state,
                                          round_num: int) -> tuple:
        """Same as choose_deployment but returns (assignments, reasoning_lines)."""
        hand = list(player.hand)
        if not hand:
            return {}, []

        reasoning = []
        rounds_remaining = game_state.num_rounds - round_num
        vp = game_state.zone_vp[round_num]

        # Summarize hand by faction
        by_faction = defaultdict(list)
        for c in sorted(hand):
            by_faction[c.faction].append(c.rank)
        hand_summary = ", ".join(f"{f[:3]}: {ranks}" for f, ranks in by_faction.items())
        reasoning.append(f"Hand ({len(hand)} cards): {hand_summary}")
        reasoning.append(f"Round {round_num+1}/3 — {vp} VP per zone, "
                         f"{rounds_remaining} round(s) left (including this one)")

        cards_to_play = self._decide_cards_to_play(hand, round_num, rounds_remaining)
        saving = len(hand) - cards_to_play
        reasoning.append(f"Budget: play {cards_to_play}, save {saving} for later")

        # Check for mascot combos
        mascots = [c for c in hand if c.is_mascot]
        best_naturals = sorted([c for c in hand if c.is_natural],
                               key=lambda c: c.rank, reverse=True)[:3]
        if mascots and best_naturals and best_naturals[0].rank >= 5:
            m = mascots[0]
            n = best_naturals[0]
            doubled = n.rank * 2
            home = "+3 home field" if n.is_natural else ""
            reasoning.append(f"Mascot combo available: {m} + {n} "
                             f"→ {doubled} strength{' ' + home if n.faction else ''}")

        deploy = self.choose_deployment(player, game_state, round_num)

        factions = getattr(game_state, 'factions', FACTIONS)
        for faction in factions:
            cards = deploy.get(faction, [])
            if not cards:
                continue
            # Calculate what the strength will be
            strength = self._estimate_strength(cards, faction)
            card_str = ", ".join(str(c) for c in cards)
            reasoning.append(f"  → {faction} Zone: [{card_str}] → est. strength {strength}")

        return deploy, reasoning

    def _estimate_strength(self, cards: list, zone_faction: str) -> int:
        """Quick strength estimate matching game_state_v3 logic."""
        if not cards:
            return 0
        mascots = [c for c in cards if c.is_mascot]
        non_mascots = [c for c in cards if not c.is_mascot]
        if not non_mascots:
            return 0
        best = max(non_mascots, key=lambda c: c.rank)
        best_rank = best.rank
        if mascots:
            best_rank *= 2
            extra = len(cards) - 2
        else:
            extra = len(cards) - 1
        bonus = max(0, extra) * 2
        home = 3 if any(c.faction == zone_faction and c.is_natural for c in cards) else 0
        return best_rank + bonus + home

    def _score_card_at_zone(self, card: Card, zone_faction: str,
                            vp: int, zone_counts: dict) -> float:
        score = card.rank  # Higher rank = higher base strength

        # Home Field Advantage (Anchor Rule): +3 if a natural (1-9) matches zone
        # Only naturals can anchor home field — 0s and 10s can't
        if card.faction == zone_faction and card.is_natural:
            score += 3.0 * self.style["home_field_weight"]

        # New zone bonus (uncontested zone = free VP)
        if zone_counts[zone_faction] == 0:
            score += vp * 0.35 * self.style["spread_bonus"]

        # Stacking penalty (extra cards only add +2, less than their face value elsewhere)
        if zone_counts[zone_faction] >= 1:
            # The card adds +2 here vs its rank at a new zone
            opportunity_cost = card.rank - 2
            score -= opportunity_cost * 0.4
            score -= 0.5 * zone_counts[zone_faction]

        # VP scaling
        score *= (vp / 5.0)

        return score
