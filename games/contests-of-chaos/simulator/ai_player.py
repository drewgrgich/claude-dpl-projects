"""Heuristic AI player for Contests of Chaos simulation.

Supports:
  - skill:  0.0 (beginner) to 1.0 (expert) — controls mistake frequency
  - style:  "balanced", "rush", "economy", "control" — distinct strategies
  - aggression: 0.0 (conservative) to 1.0 (aggressive) — spending tendency
"""

import random
from typing import List, Tuple, Optional
from collections import Counter
from cards import RecruitCard, EventCard, PlaybookCard
from event_checker import find_completable_events, find_best_card_combo
from game_state import GameState, Player


# ── Play Style Profiles ──────────────────────────────────────────────

STYLE_PROFILES = {
    "balanced": {
        "description": "Well-rounded play. Completes events as available, drafts sensibly.",
        "event_vp_weight": 1.0,      # How much VP matters when picking events
        "card_count_weight": 0.0,    # Preference for using fewer cards (0 = don't care)
        "draft_threshold": 2.0,      # Minimum draft score to act
        "wipe_patience": 3,          # Turns stuck before considering wipe
        "hoard_shinies": False,      # Try to accumulate shinies?
        "rush_low_tier": False,      # Prioritize fast Tier 1-2 completions?
        "prefer_factions": None,     # Lock onto specific factions? (set during game)
        "timeout_discard_threshold": 3.0,  # Card value below which we discard on timeout
        "scramble_lineup_threshold": 2.0,  # Avg lineup value below which we scramble
    },
    "rush": {
        "description": "Speed strategy. Grab cheap events fast, reach Standing Ovation early.",
        "event_vp_weight": 0.5,      # Don't care about VP as much — volume matters
        "card_count_weight": 2.0,    # Strongly prefer events using fewer cards
        "draft_threshold": 1.0,      # Lower bar — draft more aggressively
        "wipe_patience": 2,          # Impatient — wipe sooner
        "hoard_shinies": False,
        "rush_low_tier": True,       # Actively seek Tier 1-2 events
        "prefer_factions": None,
        "timeout_discard_threshold": 2.0,
        "scramble_lineup_threshold": 3.0,  # More willing to scramble for better options
    },
    "economy": {
        "description": "Resource hoarder. Builds up Shinies, waits for big Tier 4-6 payoffs.",
        "event_vp_weight": 2.0,      # Only go for high-VP events
        "card_count_weight": -1.0,   # Willing to use more cards for more VP
        "draft_threshold": 3.0,      # Pickier about drafts — only great value
        "wipe_patience": 5,          # Very patient — hates spending on wipes
        "hoard_shinies": True,
        "rush_low_tier": False,
        "prefer_factions": None,
        "timeout_discard_threshold": 4.0,  # Keeps more cards (higher bar to discard)
        "scramble_lineup_threshold": 1.0,  # Rarely scrambles — hates spending
    },
    "control": {
        "description": "Disruptive. Wipes often, scrambles the lineup, flushes Jumbotron events.",
        "event_vp_weight": 1.0,
        "card_count_weight": 0.0,
        "draft_threshold": 2.0,
        "wipe_patience": 2,          # Wipes early and often
        "hoard_shinies": False,
        "rush_low_tier": False,
        "prefer_factions": None,
        "timeout_discard_threshold": 3.0,
        "scramble_lineup_threshold": 4.0,  # Very willing to scramble
    },
}


class HeuristicAI:
    """A heuristic-based AI with configurable skill level and play style.

    Strategy priorities:
    1. Complete an event if possible (highest VP first, modified by style)
    2. Draft a card that enables an event completion within 1-2 turns
    3. Draft free/cheap cards with good Shiny value
    4. Wipe Jumbotron if stuck for multiple turns and can afford it
    5. Timeout to gain resources and flush stale events
    """

    def __init__(self, aggression: float = 0.5, skill: float = 1.0,
                 style: str = "balanced", rng_seed: Optional[int] = None):
        """
        aggression: 0.0 = conservative, 1.0 = aggressive (spending tendency)
        skill:      0.0 = beginner (frequent mistakes), 1.0 = expert (optimal play)
        style:      "balanced", "rush", "economy", "control"
        rng_seed:   Seed for the mistake RNG (for reproducibility)
        """
        self.aggression = aggression
        self.skill = max(0.0, min(1.0, skill))
        self.style = style
        self.profile = STYLE_PROFILES.get(style, STYLE_PROFILES["balanced"])
        self.turns_since_event = 0
        self.turns_without_completable = 0
        self.faction_commitment = Counter()  # Track which factions we've invested in

        # Mistake RNG — separate from game RNG so skill noise doesn't alter game state
        self._rng = random.Random(rng_seed)

    # ── Skill: Mistake Modeling ──────────────────────────────────────

    def _maybe_miss_event(self, completable: list) -> list:
        """Beginners sometimes fail to notice completable events.

        At skill=0.0, 40% chance to miss each event.
        At skill=0.5, 10% chance.
        At skill=1.0, 0% chance.
        """
        if self.skill >= 1.0 or not completable:
            return completable

        miss_chance = 0.4 * (1.0 - self.skill)
        seen = [c for c in completable if self._rng.random() > miss_chance]

        # Never miss ALL of them if there are multiple — even beginners notice one
        if not seen and len(completable) > 1:
            seen = [self._rng.choice(completable)]
        elif not seen and len(completable) == 1:
            # Single event: beginners can still miss it
            return seen  # empty — they missed it

        return seen

    def _noisy_score(self, base_score: float) -> float:
        """Add noise to a score based on skill level.

        At skill=1.0, returns exact score.
        At skill=0.0, adds +/-4 noise (beginners misjudge card value badly).
        """
        if self.skill >= 1.0:
            return base_score

        noise_range = 4.0 * (1.0 - self.skill)
        noise = self._rng.uniform(-noise_range, noise_range)
        return base_score + noise

    def _should_overcommit_faction(self) -> bool:
        """Beginners tend to fixate on one faction too long.

        At skill=0.0, 30% chance per turn to ignore non-committed factions.
        """
        if self.skill >= 0.8:
            return False
        chance = 0.3 * (1.0 - self.skill)
        return self._rng.random() < chance

    def _forget_free_agents(self) -> bool:
        """Beginners sometimes forget Free Agents can substitute.

        This affects card valuation — FAs get scored lower.
        """
        if self.skill >= 0.7:
            return False
        chance = 0.25 * (1.0 - self.skill)
        return self._rng.random() < chance

    def _bad_wipe_decision(self) -> bool:
        """Beginners sometimes wipe when they shouldn't, or don't when they should.

        Returns True to invert the wipe decision.
        """
        if self.skill >= 0.8:
            return False
        chance = 0.2 * (1.0 - self.skill)
        return self._rng.random() < chance

    # ── Setup Choices ────────────────────────────────────────────────

    def choose_starting_hand(self, player: Player, dealt: List[RecruitCard],
                              game: GameState) -> Tuple[List[RecruitCard], List[RecruitCard]]:
        """Choose which 3 of 5 dealt cards to keep."""
        scores = []
        for i, card in enumerate(dealt):
            score = self._card_value(card, game)
            score = self._noisy_score(score)  # Skill noise
            scores.append((score, i, card))

        scores.sort(key=lambda x: -x[0])
        keep = [c for _, _, c in scores[:game.rules["starting_keep"]]]
        discard = [c for _, _, c in scores[game.rules["starting_keep"]:]]

        # Track faction commitment from kept cards
        for c in keep:
            if not c.is_free_agent:
                self.faction_commitment[c.faction] += 1

        return keep, discard

    def choose_playbook(self, player: Player, options: List[PlaybookCard],
                         game: GameState) -> Tuple[PlaybookCard, PlaybookCard]:
        """Choose which playbook to keep."""
        scored = []
        for i, pb in enumerate(options):
            score = pb.vp
            trigger = pb.trigger.lower()

            # Style-specific adjustments
            if self.style == "rush":
                if "3 or fewer cards" in trigger:
                    score += 3  # Rush loves cheap completions
                if "4th event" in trigger or "5th event" in trigger:
                    score += 2  # Rush expects many events
                if "9 vp or more" in trigger:
                    score -= 2  # Rush doesn't aim for big events

            elif self.style == "economy":
                if "9 vp or more" in trigger:
                    score += 2  # Economy goes big
                if "8+ shinies" in trigger:
                    score += 3  # Economy hoards
                if "5 shinies" in trigger or "sponsorship" in trigger:
                    score += 1
                if "3 or fewer cards" in trigger:
                    score -= 1  # Economy uses more cards

            elif self.style == "control":
                if "flush" in trigger or "jumbotron" in trigger:
                    score += 3  # Control uses flush/wipe
                if "2 or fewer cards in hand" in trigger:
                    score += 1
                if "slot 3" in trigger or "slot 4" in trigger:
                    score -= 1  # Control doesn't draft expensive slots often

            # General adjustments
            if "5th event" in trigger:
                score -= 3
            if "slot 4" in trigger or "slot 3" in trigger:
                score += 1
            if "3 or fewer cards" in trigger:
                score += 1
            if "exactly 0 shinies" in trigger:
                score -= 1

            score = self._noisy_score(score)  # Skill noise
            scored.append((score, i, pb))

        scored.sort(key=lambda x: -x[0])
        keep = scored[0][2]
        discard = scored[1][2] if len(scored) > 1 else scored[0][2]
        return keep, discard

    # ── Turn Action ──────────────────────────────────────────────────

    def choose_action(self, player: Player, game: GameState) -> dict:
        """Choose the best action for this turn."""
        state = game.get_state_summary()

        # Priority 1: Complete an event if possible
        completable = find_completable_events(player.hand, game.jumbotron)

        # Skill filter: beginners miss some events
        completable = self._maybe_miss_event(completable)

        if completable:
            self.turns_since_event = 0
            self.turns_without_completable = 0

            # Style-aware event selection
            event, cards = self._pick_event(completable, player)
            event_idx = game.jumbotron.index(event)
            card_indices = [player.hand.index(c) for c in cards]
            return {
                "type": "complete_event",
                "event_index": event_idx,
                "card_indices": card_indices,
            }

        self.turns_since_event += 1
        self.turns_without_completable += 1

        # Priority 2: Wipe Jumbotron if stuck (supports targeted and full wipe)
        wipe_action = self._evaluate_wipe(player, game)
        if wipe_action:
            self.turns_without_completable = 0
            return wipe_action

        # Priority 3: Draft a card that moves us toward an event
        draft_action = self._evaluate_drafts(player, game)
        if draft_action:
            return draft_action

        # Priority 4: Scramble if lineup is bad and we can afford it
        if self._should_scramble(player, game):
            return {"type": "scramble"}

        # Priority 5: Timeout
        return self._build_timeout_action(player, game)

    # ── Event Selection (Style-Aware) ────────────────────────────────

    def _pick_event(self, completable: list, player: Player) -> Tuple[EventCard, List[RecruitCard]]:
        """Pick which event to complete, influenced by play style."""
        if len(completable) == 1:
            return completable[0]

        scored_events = []
        for event, cards in completable:
            score = event.vp * self.profile["event_vp_weight"]

            # Card count preference (rush prefers fewer cards, economy doesn't mind more)
            card_penalty = len(cards) * self.profile["card_count_weight"]
            score -= card_penalty

            # Rush bonus for low-tier events
            if self.profile["rush_low_tier"] and event.tier <= 2:
                score += 3.0

            # Economy bonus for high-tier events
            if self.style == "economy" and event.tier >= 4:
                score += event.vp * 0.5

            # Faction commitment bonus: prefer events matching factions we've invested in
            if self.faction_commitment:
                req_factions = event.requirements.get("factions", {})
                commitment_match = sum(
                    self.faction_commitment.get(f, 0)
                    for f in req_factions
                )
                score += commitment_match * 0.5

            # Skill noise
            score = self._noisy_score(score)

            scored_events.append((score, event, cards))

        scored_events.sort(key=lambda x: -x[0])
        return scored_events[0][1], scored_events[0][2]

    # ── Wipe Evaluation ────────────────────────────────────────────────

    def _evaluate_wipe(self, player: Player, game: GameState) -> Optional[dict]:
        """Evaluate whether to wipe and how many events to target.

        Supports two modes:
        - Tiered (targeted): choose 1, 2, or all events based on cost/benefit
        - Flat (legacy): all-or-nothing full wipe
        """
        wipe_config = game.rules.get("wipe_jumbotron", {})
        if not wipe_config.get("enabled"):
            return None

        min_hand = wipe_config.get("min_hand_size", 0)
        if min_hand > 0 and len(player.hand) < min_hand:
            return None

        patience = self.profile["wipe_patience"]
        tiered = wipe_config.get("tiered_cost", None)

        if tiered:
            return self._evaluate_tiered_wipe(player, game, wipe_config, tiered, patience)
        else:
            return self._evaluate_full_wipe(player, game, wipe_config, patience)

    def _evaluate_full_wipe(self, player, game, wipe_config, patience) -> Optional[dict]:
        """Legacy all-or-nothing wipe logic."""
        cost = wipe_config["cost"]
        if player.shinies < cost:
            return None

        should_wipe = self.turns_without_completable >= patience

        # Control style: also wipe to deny opponents high-VP events
        if self.style == "control" and not should_wipe:
            if self.turns_without_completable >= 2:
                high_vp_visible = any(ev.vp >= 8 for ev in game.jumbotron)
                if high_vp_visible:
                    should_wipe = True

        # Skill noise
        if self._bad_wipe_decision():
            should_wipe = not should_wipe

        if should_wipe:
            return {"type": "wipe_jumbotron", "target_indices": None}
        return None

    def _evaluate_tiered_wipe(self, player, game, wipe_config, tiered, patience) -> Optional[dict]:
        """Evaluate targeted wipe options with tiered pricing.

        Strategy: score each Jumbotron event by how "bad" it is for us
        (low closeness, high VP for opponents, stale). Then decide how
        many to remove based on cost/benefit.
        """
        if self.turns_without_completable < max(patience - 1, 1):
            # Not stuck enough yet for even a cheap wipe
            # Exception: control style is more aggressive
            if self.style != "control" or self.turns_without_completable < 1:
                return None

        # Score each Jumbotron event: negative = bad for us (want to remove)
        event_scores = []
        for i, ev in enumerate(game.jumbotron):
            score = 0.0

            # How close are WE to completing this event?
            closeness = self._evaluate_closeness(player.hand, [ev])
            score += closeness * 2.0  # Events we're close to = keep them

            # VP value: high-VP events we can't complete are threats
            if closeness < 1.0:
                score -= ev.vp * 0.3  # Penalize high-VP events we can't reach

            # Control style: extra penalty for high-VP events (deny opponents)
            if self.style == "control" and ev.vp >= 8:
                score -= ev.vp * 0.5

            # Events in factions we've invested in: keep them
            if "factions" in ev.requirements:
                for faction in ev.requirements["factions"]:
                    if self.faction_commitment.get(faction, 0) >= 2:
                        score += 3.0

            # Skill noise
            score = self._noisy_score(score)

            event_scores.append((score, i, ev))

        # Sort: lowest score = most desirable to remove
        event_scores.sort(key=lambda x: x[0])

        # Evaluate each tier option
        best_action = None
        best_value = -float('inf')

        valid_tiers = sorted((int(k), v) for k, v in tiered.items())

        for num_to_remove, cost in valid_tiers:
            if num_to_remove > len(game.jumbotron):
                continue
            if player.shinies < cost:
                continue

            # Pick the N worst events to remove
            targets = [idx for _, idx, _ in event_scores[:num_to_remove]]
            removed_events = [ev for _, _, ev in event_scores[:num_to_remove]]

            # Value = how bad the removed events are (sum of negative scores)
            removal_value = -sum(s for s, _, _ in event_scores[:num_to_remove])

            # Cost penalty
            cost_penalty = cost * 1.5

            # Stagnation urgency bonus: the longer we're stuck, the more valuable any wipe
            urgency = self.turns_without_completable * 1.0

            net_value = removal_value - cost_penalty + urgency

            # Economy style: much higher bar for spending
            if self.profile["hoard_shinies"]:
                net_value -= cost * 1.0

            if net_value > best_value and net_value > 0:
                best_value = net_value
                best_action = {
                    "type": "wipe_jumbotron",
                    "target_indices": sorted(targets),
                    "num_targets": num_to_remove,
                    "cost": cost,
                }

        return best_action

    # ── Card Valuation ───────────────────────────────────────────────

    def _card_value(self, card: RecruitCard, game: GameState) -> float:
        """Score a card's general value, influenced by style and skill."""
        score = 0.0

        # Free agents are very valuable (unless beginner forgets)
        if card.is_free_agent:
            if self._forget_free_agents():
                score += 2.0  # Beginner undervalues FAs
            else:
                score += 8.0

        # Mid-rank cards are versatile for sums
        if 3 <= card.rank <= 7:
            score += 2.0

        # High-rank cards good for sum requirements
        if card.rank >= 8:
            score += 1.5

        # Low-rank cards good for Limbo Contest type events
        if card.rank <= 2:
            score += 1.0

        # Faction diversity bonus based on what's on the Jumbotron
        for event in game.jumbotron:
            if "factions" in event.requirements:
                if card.faction in event.requirements["factions"]:
                    score += 3.0
            if "any_factions" in event.requirements:
                score += 1.0

        # Style modifiers
        if self.style == "economy":
            # Economy values high-rank cards more (big sum events)
            if card.rank >= 7:
                score += 1.5
        elif self.style == "rush":
            # Rush values faction matches more (quick completions)
            for event in game.jumbotron:
                if event.tier <= 2 and "factions" in event.requirements:
                    if card.faction in event.requirements["factions"]:
                        score += 2.0  # Extra bonus for low-tier matches

        # Faction overcommitment (beginner mistake)
        if self._should_overcommit_faction() and self.faction_commitment:
            top_faction = self.faction_commitment.most_common(1)[0][0]
            if card.faction == top_faction:
                score += 4.0  # Beginner fixates on their favorite faction
            elif not card.is_free_agent:
                score -= 2.0  # Beginner undervalues other factions

        return score

    def _evaluate_drafts(self, player: Player, game: GameState) -> Optional[dict]:
        """Evaluate each Lineup slot for drafting potential."""
        best_slot = None
        best_score = -float('inf')
        threshold = self.profile["draft_threshold"]

        for i, slot in enumerate(game.lineup):
            if slot.card is None:
                continue

            cost = game.rules["slot_pricing"][i]
            if player.shinies < cost:
                continue

            # Economy style: reluctant to spend on expensive slots
            if self.profile["hoard_shinies"] and cost >= 2 and player.shinies < cost + 3:
                continue

            score = 0.0

            # Value of the card itself
            card_val = self._card_value(slot.card, game)
            score += card_val

            # Value of Shinies on the card
            score += slot.shinies * 1.5

            # Cost penalty
            score -= cost * 2.0

            # Check if drafting this card enables any event completion
            hypothetical_hand = player.hand + [slot.card]
            completable_after = find_completable_events(hypothetical_hand, game.jumbotron)
            if completable_after:
                best_event = max(completable_after, key=lambda x: x[0].vp)
                score += best_event[0].vp * 2.0

            # Check how close we get to event requirements
            closeness = self._evaluate_closeness(player.hand + [slot.card], game.jumbotron)
            score += closeness

            # Prefer free cards
            if cost == 0:
                score += 3.0

            # Skill noise on draft evaluation
            score = self._noisy_score(score)

            # Track faction commitment for drafted cards
            if score > best_score:
                best_score = score
                best_slot = i

        if best_slot is not None and best_score > threshold:
            # Update faction commitment
            drafted = game.lineup[best_slot].card
            if drafted and not drafted.is_free_agent:
                self.faction_commitment[drafted.faction] += 1
            return {"type": "recruit_lineup", "slot": best_slot}

        return None

    def _evaluate_closeness(self, hand: List[RecruitCard], jumbotron: List[EventCard]) -> float:
        """Evaluate how close a hand is to completing any event."""
        best_closeness = 0.0

        for event in jumbotron:
            req = event.requirements
            closeness = 0.0

            # Style filter: rush cares more about low-tier closeness
            tier_multiplier = 1.0
            if self.profile["rush_low_tier"] and event.tier <= 2:
                tier_multiplier = 1.5
            elif self.style == "economy" and event.tier >= 4:
                tier_multiplier = 1.3

            # Faction matching
            if "factions" in req:
                for faction, needed in req["factions"].items():
                    matching = sum(1 for c in hand
                                   if c.faction == faction and not c.is_free_agent)
                    free_agents = sum(1 for c in hand if c.is_free_agent)
                    available = matching + free_agents
                    ratio = min(available / needed, 1.0)
                    closeness += ratio * event.vp * tier_multiplier

            # Run matching
            if "run_length" in req:
                ranks = sorted(set(c.rank for c in hand))
                max_consec = 1
                current_consec = 1
                for j in range(1, len(ranks)):
                    if ranks[j] == ranks[j-1] + 1:
                        current_consec += 1
                        max_consec = max(max_consec, current_consec)
                    else:
                        current_consec = 1
                ratio = min(max_consec / req["run_length"], 1.0)
                closeness += ratio * event.vp * tier_multiplier

            # Same number matching
            if "same_number" in req:
                rank_counts = Counter(c.rank for c in hand)
                max_same = max(rank_counts.values()) if rank_counts else 0
                ratio = min(max_same / req["same_number"], 1.0)
                closeness += ratio * event.vp * tier_multiplier

            best_closeness = max(best_closeness, closeness * 0.3)

        return best_closeness

    def _should_scramble(self, player: Player, game: GameState) -> bool:
        """Decide whether to Scramble."""
        cost = game.rules["scramble_cost"][game.pkey]
        if player.shinies < cost:
            return False

        # Economy style: almost never scrambles
        if self.profile["hoard_shinies"] and player.shinies < cost + 5:
            return False

        lineup_value = sum(self._card_value(s.card, game) for s in game.lineup if s.card)
        avg_value = lineup_value / max(len(game.lineup), 1)

        threshold = self.profile["scramble_lineup_threshold"]

        # Control style: scramble more liberally to disrupt
        if self.style == "control":
            return avg_value < threshold and player.shinies >= cost + 1

        return avg_value < threshold and player.shinies >= cost + 2

    def _build_timeout_action(self, player: Player, game: GameState) -> dict:
        """Build a Timeout action with discard and flush decisions."""
        discard_indices = []
        discard_threshold = self.profile["timeout_discard_threshold"]

        # Discard cards that don't help with any Jumbotron event
        if len(player.hand) >= 6:
            card_scores = []
            for i, card in enumerate(player.hand):
                score = self._card_value(card, game)
                card_scores.append((score, i))
            card_scores.sort()
            max_discards = min(2, len(player.hand) - 3)
            for j in range(max_discards):
                if card_scores[j][0] < discard_threshold:
                    discard_indices.append(card_scores[j][1])

        # Flush Jumbotron decision
        should_flush = self.turns_without_completable >= 2

        # Control style: flush more aggressively, especially high-VP events
        if self.style == "control" and not should_flush:
            # Flush if Slot 1 has a high-VP event that opponents might use
            if game.jumbotron and game.jumbotron[0].vp >= 7:
                should_flush = True

        # Economy style: less likely to flush (patient)
        if self.style == "economy":
            should_flush = self.turns_without_completable >= 4

        return {
            "type": "timeout",
            "discard_indices": discard_indices,
            "flush_jumbotron": should_flush,
        }

    def choose_discard_for_hand_limit(self, player: Player, game: GameState) -> List[int]:
        """Choose which cards to discard to meet hand limit."""
        limit = game.rules["hand_limit"]
        if len(player.hand) <= limit:
            return []

        card_scores = []
        for i, card in enumerate(player.hand):
            score = self._card_value(card, game)
            card_scores.append((score, i))

        card_scores.sort()
        num_to_discard = len(player.hand) - limit
        return [idx for _, idx in card_scores[:num_to_discard]]
