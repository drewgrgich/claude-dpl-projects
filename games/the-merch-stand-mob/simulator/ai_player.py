"""Heuristic AI player for The Merch Stand Mob.

Three tunable axes:
  - Skill (0.0-1.0): mistake frequency
  - Style (categorical): strategic preferences
  - Aggression (0.0-1.0): spending/risk willingness
"""

import random
from typing import List, Dict, Optional, Tuple, Any
from collections import defaultdict

from cards import Card, FACTION_COLORS
from game_state import GameState, Player, Bid


# ─── PLAY STYLE PROFILES ─────────────────────────────────────

STYLE_PROFILES = {
    "balanced": {
        "description": "Well-rounded default play.",
        "sneak_threshold": 0.25,     # Base probability of attempting Sneak
        "shove_threshold": 0.30,     # Base probability of attempting Shove
        "high_card_preference": 1.0, # Weight for preferring high-rank Stand cards
        "set_bonus_weight": 1.5,     # Weight for cards completing color sets
        "trample_fear": 1.0,         # How much to avoid factions near Trample
        "pit_aggression": 0.0,       # Willingness to push opponent factions toward Trample
        "bid_conservation": 0.5,     # Tendency to bid low to conserve cards
    },
    "rush": {
        "description": "Burn hand fast, force game end.",
        "sneak_threshold": 0.15,
        "shove_threshold": 0.45,     # Love Shoves — they burn 2 cards
        "high_card_preference": 0.5,
        "set_bonus_weight": 0.5,     # Don't chase sets, just grab anything
        "trample_fear": 0.3,         # Doesn't care much about Trample
        "pit_aggression": 0.5,
        "bid_conservation": 0.0,     # Burn cards freely
    },
    "collector": {
        "description": "Chase set bonuses aggressively.",
        "sneak_threshold": 0.35,     # Sneaks to grab specific colors
        "shove_threshold": 0.20,
        "high_card_preference": 0.7,
        "set_bonus_weight": 3.0,     # Heavy set bonus focus
        "trample_fear": 1.5,         # Very worried about losing collected colors
        "pit_aggression": 0.0,
        "bid_conservation": 0.7,
    },
    "disruptor": {
        "description": "Push opponent factions toward Trample.",
        "sneak_threshold": 0.20,
        "shove_threshold": 0.35,
        "high_card_preference": 0.8,
        "set_bonus_weight": 1.0,
        "trample_fear": 0.5,         # Less concerned about own Trample risk
        "pit_aggression": 2.0,       # Actively tries to Trample opponent colors
        "bid_conservation": 0.3,
    },
}


class HeuristicAI:
    """AI player that makes heuristic decisions for The Merch Stand Mob."""

    def __init__(self, player_id: int, skill: float = 1.0,
                 style: str = "balanced", aggression: float = 0.5,
                 rng_seed: int = None):
        self.player_id = player_id
        self.skill = max(0.0, min(1.0, skill))
        self.style = style
        self.aggression = max(0.0, min(1.0, aggression))
        self.profile = STYLE_PROFILES.get(style, STYLE_PROFILES["balanced"])
        self.rng = random.Random(rng_seed)

        # Track history for adaptive decisions
        self.sneak_history: List[bool] = []  # True = someone sneaked this round
        self.rounds_played: int = 0

    # ─── MAIN DECISION: CHOOSE A BID ─────────────────────────

    def choose_bid(self, player: Player, game: GameState) -> Bid:
        """Choose which card(s) to bid this round.

        Returns a Bid object with primary card and optional anchor.
        """
        self.rounds_played += 1
        hand = player.hand

        if not hand:
            raise ValueError(f"P{self.player_id} has no cards to bid!")

        # If only one card left, must play it
        if len(hand) == 1:
            return Bid(player_id=self.player_id, primary=hand[0])

        # Score all possible bids
        candidates = []

        # Option 1: Normal bids (rank 1-9)
        normal_cards = [c for c in hand if 1 <= c.rank <= 9]
        for card in normal_cards:
            score = self._score_normal_bid(card, player, game)
            candidates.append(("normal", score, card, None))

        # Option 2: Sneak (rank 0 + anchor)
        sneaks = [c for c in hand if c.rank == 0]
        anchors = [c for c in hand if 1 <= c.rank <= 9]
        if sneaks and anchors:
            for sneak_card in sneaks:
                best_anchor, anchor_score = self._choose_anchor(anchors, player, game)
                sneak_score = self._score_sneak(sneak_card, best_anchor, player, game)
                candidates.append(("sneak", sneak_score, sneak_card, best_anchor))

        # Option 3: Shove (rank 10 + anchor)
        shoves = [c for c in hand if c.rank == 10]
        if shoves and anchors:
            for shove_card in shoves:
                best_anchor, anchor_score = self._choose_anchor(anchors, player, game)
                shove_score = self._score_shove(shove_card, best_anchor, player, game)
                candidates.append(("shove", shove_score, shove_card, best_anchor))

        # Wilds with no anchor: must play as failed bid
        lonely_wilds = []
        if not anchors:
            lonely_wilds = [c for c in hand if c.is_wild]
            for card in lonely_wilds:
                candidates.append(("failed_wild", -10.0, card, None))

        if not candidates:
            # Absolute fallback
            return Bid(player_id=self.player_id, primary=hand[0])

        # Apply skill noise and pick best
        best = max(candidates, key=lambda x: self._noisy_score(x[1]))
        bid_type, score, primary, anchor = best

        return Bid(player_id=self.player_id, primary=primary, anchor=anchor)

    def choose_bid_with_reasoning(self, player: Player, game: GameState) -> Tuple[Bid, str]:
        """Choose a bid and return reasoning for narration."""
        hand = player.hand
        reasoning_lines = []

        if not hand:
            raise ValueError(f"P{self.player_id} has no cards to bid!")

        if len(hand) == 1:
            bid = Bid(player_id=self.player_id, primary=hand[0])
            reasoning_lines.append(f"Only card left: {hand[0]}. Must play it.")
            return bid, "\n".join(reasoning_lines)

        candidates = []

        # Normal bids
        normal_cards = [c for c in hand if 1 <= c.rank <= 9]
        for card in normal_cards:
            score = self._score_normal_bid(card, player, game)
            candidates.append(("normal", score, card, None))
            reasoning_lines.append(f"Normal bid {card}: score {score:.1f}")

        # Sneaks
        sneaks = [c for c in hand if c.rank == 0]
        anchors = [c for c in hand if 1 <= c.rank <= 9]
        if sneaks and anchors:
            for sneak_card in sneaks:
                best_anchor, _ = self._choose_anchor(anchors, player, game)
                score = self._score_sneak(sneak_card, best_anchor, player, game)
                candidates.append(("sneak", score, sneak_card, best_anchor))
                reasoning_lines.append(
                    f"Sneak {sneak_card}+{best_anchor}: score {score:.1f} "
                    f"(sneak success rate: {self._estimate_sneak_success():.0%})")

        # Shoves
        shoves = [c for c in hand if c.rank == 10]
        if shoves and anchors:
            for shove_card in shoves:
                best_anchor, _ = self._choose_anchor(anchors, player, game)
                score = self._score_shove(shove_card, best_anchor, player, game)
                candidates.append(("shove", score, shove_card, best_anchor))
                reasoning_lines.append(
                    f"Shove {shove_card}+{best_anchor}: score {score:.1f}")

        if not candidates:
            bid = Bid(player_id=self.player_id, primary=hand[0])
            return bid, "No good options. Playing first card."

        best = max(candidates, key=lambda x: self._noisy_score(x[1]))
        bid_type, score, primary, anchor = best
        reasoning_lines.append(f"**Decision: {bid_type} with {primary}" +
                              (f"+{anchor}" if anchor else "") + f" (score: {score:.1f})**")

        return Bid(player_id=self.player_id, primary=primary, anchor=anchor), \
               "\n".join(reasoning_lines)

    # ─── BID SCORING ──────────────────────────────────────────

    def _score_normal_bid(self, card: Card, player: Player,
                          game: GameState) -> float:
        """Score a normal (rank 1-9) bid."""
        score = 0.0

        # Higher rank = better chance of claiming
        claim_prob = self._estimate_claim_probability(card.rank, game)
        score += claim_prob * 5.0

        # What's on the Stand worth?
        stand_value = self._evaluate_stand(player, game)
        score += claim_prob * stand_value

        # Cost: losing this card from hand
        card_cost = self._card_hand_value(card, player, game)
        score -= card_cost

        # Mosh Pit impact: this card enters the Pit
        pit_penalty = self._pit_impact(card, player, game)
        score -= pit_penalty

        # Conservation preference
        score -= card.rank * self.profile["bid_conservation"] * 0.3

        return score

    def _score_sneak(self, sneak: Card, anchor: Card,
                     player: Player, game: GameState) -> float:
        """Score a Sneak (rank 0) bid."""
        score = 0.0

        # Sneak success probability based on history and player count
        success_prob = self._estimate_sneak_success()
        score += success_prob * 8.0  # High value if it works — first pick!

        # Stand value (Sneak gets first pick of best card)
        if game.stand:
            best_stand = max(game.stand, key=lambda c: self._stand_card_value(c, player, game))
            best_value = self._stand_card_value(best_stand, player, game)
            score += success_prob * best_value

        # Risk: failed Sneak = both cards in Pit + no claim
        failure_cost = self._pit_impact(sneak, player, game) + \
                       self._pit_impact(anchor, player, game) + 3.0  # Wasted turn
        score -= (1.0 - success_prob) * failure_cost

        # Benefit: successful Sneak leaves NO trace in Pit
        score += success_prob * 2.0  # Pit avoidance bonus

        # Cost: two cards from hand
        score -= self._card_hand_value(anchor, player, game)

        # Style modifier
        score += self.profile["sneak_threshold"] * 3.0

        # Aggression modifier
        score += (self.aggression - 0.5) * 2.0

        return score

    def _score_shove(self, shove: Card, anchor: Card,
                     player: Player, game: GameState) -> float:
        """Score a Shove (rank 10) bid."""
        score = 0.0

        # Shove always claims (unless tied with another 10)
        # Estimate tie probability
        tie_prob = self._estimate_shove_tie(game)
        claim_prob = 1.0 - tie_prob
        score += claim_prob * 6.0

        # Stand value (Shove picks after successful Sneak, but before everyone else)
        stand_value = self._evaluate_stand(player, game)
        score += claim_prob * stand_value

        # Heavy Pit cost: both cards enter Pit
        pit_penalty = self._pit_impact(shove, player, game) + \
                      self._pit_impact(anchor, player, game)
        score -= pit_penalty * 1.5  # Extra weight — Shoves are Pit-heavy

        # Benefit: burns 2 cards (good for rush style)
        if self.profile["bid_conservation"] < 0.3:
            score += 2.0  # Rush players like burning cards

        # Hand cost
        score -= self._card_hand_value(anchor, player, game)

        # Style modifier
        score += self.profile["shove_threshold"] * 3.0

        return score

    def _choose_anchor(self, anchors: List[Card], player: Player,
                       game: GameState) -> Tuple[Card, float]:
        """Choose the best anchor card for a Wild bid.

        Prefer cards that:
        - Have low hand value (don't mind losing)
        - Push a faction we DON'T care about into the Pit
        """
        best = None
        best_score = float('-inf')

        for card in anchors:
            score = 0.0
            # Lower hand value = better anchor (less costly to lose)
            score -= self._card_hand_value(card, player, game)
            # Prefer anchors in factions we don't care about
            my_colors = set(c.faction for c in player.score_pile)
            if card.faction not in my_colors:
                score += 1.0
            # Disruptor: prefer factions opponent is collecting
            if self.profile["pit_aggression"] > 0:
                score += self._opponent_faction_threat(card.faction, player, game) * \
                         self.profile["pit_aggression"]

            if score > best_score:
                best_score = score
                best = card

        return best, best_score

    # ─── STAND CARD SELECTION ─────────────────────────────────

    def choose_stand_card(self, player: Player, game: GameState,
                          stand: List[Card]) -> int:
        """Choose which Stand card to claim. Returns index."""
        if not stand:
            return 0

        best_idx = 0
        best_score = float('-inf')

        for i, card in enumerate(stand):
            score = self._stand_card_value(card, player, game)
            score = self._noisy_score(score)
            if score > best_score:
                best_score = score
                best_idx = i

        return best_idx

    def _stand_card_value(self, card: Card, player: Player,
                          game: GameState) -> float:
        """Evaluate how valuable a Stand card is to claim."""
        score = 0.0

        # Base: VP value
        score += card.vp * self.profile["high_card_preference"]

        # Set bonus potential
        my_colors = set(c.faction for c in player.score_pile)
        if card.faction not in my_colors:
            # New color — contributes to set bonus
            new_count = len(my_colors) + 1
            if new_count == 3:
                score += 5.0 * self.profile["set_bonus_weight"]
            elif new_count == 6:
                score += 8.0 * self.profile["set_bonus_weight"]
            elif new_count < 3:
                score += 2.0 * self.profile["set_bonus_weight"]  # Progress toward set
            elif new_count < 6:
                score += 3.0 * self.profile["set_bonus_weight"]  # Progress toward 2nd set

        # Trample risk: claiming a color near Trample is risky
        pit_count = game.get_mosh_pit_faction_count(card.faction)
        threshold = game.rules["trample_threshold"][game.pkey]
        if pit_count >= threshold - 1:
            # This color is about to Trample
            penalty = (len(player.cards_of_faction(card.faction)) + 1) * card.vp * 0.5
            score -= penalty * self.profile["trample_fear"]

        return score

    # ─── ABILITY DECISIONS ────────────────────────────────────

    def ability_callback(self, player: Player, ability_type: str,
                         game: GameState, context: Any) -> Any:
        """Central callback for all AI decisions during the round."""

        if ability_type == "choose_stand":
            return self.choose_stand_card(player, game, context)

        elif ability_type == "stadium_sweep":
            return self._decide_stadium_sweep(player, game, context)

        elif ability_type == "keen_eye":
            return self._decide_keen_eye(player, game, context)

        elif ability_type == "small_prophecies":
            return self._decide_small_prophecies(player, game, context)

        elif ability_type == "small_prophecies_reorder":
            return self._decide_prophecy_reorder(player, game, context)

        elif ability_type == "sleight_of_paw":
            return self._decide_sleight_of_paw(player, game, context)

        elif ability_type == "temporal_recall":
            return self._decide_temporal_recall(player, game, context)

        return None

    def _decide_stadium_sweep(self, player: Player, game: GameState,
                               pit_cards: List[Tuple]) -> Optional[Tuple]:
        """RED: Choose which Mosh Pit card to remove."""
        if not pit_cards:
            return None

        threshold = game.rules["trample_threshold"][game.pkey]

        # Priority 1: Remove from a faction I'm collecting that's near Trample
        my_colors = set(c.faction for c in player.score_pile)
        best = None
        best_score = float('-inf')

        for faction, card in pit_cards:
            score = 0.0
            pit_count = game.get_mosh_pit_faction_count(faction)

            # High priority if I have cards of this color
            if faction in my_colors:
                my_count = len(player.cards_of_faction(faction))
                score += my_count * 3.0
                # Extra urgency if near threshold
                if pit_count >= threshold - 1:
                    score += 10.0

            # Also valuable to reduce any faction near threshold
            if pit_count >= threshold - 1:
                score += 5.0

            # Disruptor: might NOT remove opponent-threatening factions
            if self.profile["pit_aggression"] > 1.0:
                opponent_investment = self._opponent_faction_investment(faction, player, game)
                if opponent_investment > 0 and faction not in my_colors:
                    score -= opponent_investment * self.profile["pit_aggression"]

            if score > best_score:
                best_score = score
                best = (faction, card)

        return best

    def _decide_keen_eye(self, player: Player, game: GameState,
                          context: dict) -> Optional[int]:
        """ORANGE: Decide whether to swap top supply with a Stand card."""
        top_supply = context["top_supply"]
        stand = context["stand"]

        if not stand:
            return None

        supply_value = self._stand_card_value(top_supply, player, game)

        # Find worst Stand card
        worst_idx = 0
        worst_value = float('inf')
        for i, card in enumerate(stand):
            val = self._stand_card_value(card, player, game)
            if val < worst_value:
                worst_value = val
                worst_idx = i

        # Swap if supply card is better than the worst Stand card
        if supply_value > worst_value + 1.0:
            return worst_idx

        return None  # Don't swap

    def _decide_small_prophecies(self, player: Player, game: GameState,
                                  context: dict) -> Optional[Card]:
        """GREEN: Choose which keepable card (rank ≤5) to take."""
        keepable = context["keepable"]
        if not keepable:
            return None

        # Pick the one with best value (considering sets)
        best = max(keepable, key=lambda c: self._stand_card_value(c, player, game))
        return best

    def _decide_prophecy_reorder(self, player: Player, game: GameState,
                                  remaining: List[Card]) -> List[Card]:
        """GREEN: Reorder remaining supply cards."""
        # Put worst cards on top (they'll appear on Stand next, visible to opponents)
        # Unless we plan to use Tinkerer (Yellow) — then put best on top
        # Simple heuristic: put lowest-value cards on top
        return sorted(remaining, key=lambda c: c.rank)

    def _decide_sleight_of_paw(self, player: Player, game: GameState,
                                mosh_pit: Dict[str, List[Card]]) -> Optional[Tuple]:
        """BLUE: Choose which card to move between factions in the Pit."""
        threshold = game.rules["trample_threshold"][game.pkey]
        my_colors = set(c.faction for c in player.score_pile)

        best_move = None
        best_score = 0.0

        for from_faction in FACTION_COLORS:
            for card in mosh_pit.get(from_faction, []):
                for to_faction in FACTION_COLORS:
                    if from_faction == to_faction:
                        continue

                    score = 0.0

                    # Defensive: move card AWAY from my threatened faction
                    if from_faction in my_colors:
                        from_count = game.get_mosh_pit_faction_count(from_faction)
                        if from_count >= threshold - 1:
                            my_cards = len(player.cards_of_faction(from_faction))
                            score += my_cards * 3.0 + 5.0

                    # Offensive: move card INTO opponent's invested faction
                    to_count = game.get_mosh_pit_faction_count(to_faction)
                    opponent_inv = self._opponent_faction_investment(to_faction, player, game)
                    if to_count >= threshold - 2 and opponent_inv > 0:
                        score += opponent_inv * self.profile["pit_aggression"]

                    # Trigger Trample intentionally?
                    if to_count + 1 >= threshold:
                        if to_faction not in my_colors and opponent_inv > 0:
                            score += 8.0 * self.profile["pit_aggression"]
                        elif to_faction in my_colors:
                            score -= 20.0  # Don't Trample ourselves!

                    # Don't move into a faction we care about
                    if to_faction in my_colors:
                        my_to_cards = len(player.cards_of_faction(to_faction))
                        to_count_after = to_count + 1
                        if to_count_after >= threshold - 1:
                            score -= my_to_cards * 4.0

                    if score > best_score:
                        best_score = score
                        best_move = (from_faction, card, to_faction)

        return best_move

    def _decide_temporal_recall(self, player: Player, game: GameState,
                                 context: dict) -> Optional[Tuple]:
        """PURPLE: Choose card to retrieve from Pit and card to discard from hand."""
        pit_cards = context["pit_cards"]
        hand = context["hand"]

        if not pit_cards or not hand:
            return None

        # Find highest-value card in Pit to retrieve
        best_retrieve = None
        best_score = float('-inf')

        for faction, card in pit_cards:
            score = card.rank  # Higher rank = more valuable to get back
            # Bonus if retrieving reduces a faction near Trample
            threshold = game.rules["trample_threshold"][game.pkey]
            pit_count = game.get_mosh_pit_faction_count(faction)
            my_colors = set(c.faction for c in player.score_pile)
            if faction in my_colors and pit_count >= threshold - 1:
                score += 5.0  # Retrieval also defuses Trample

            if score > best_score:
                best_score = score
                best_retrieve = (faction, card)

        if best_retrieve is None:
            return None

        retrieve_faction, retrieve_card = best_retrieve

        # Choose hand card to discard: least valuable
        best_discard = None
        lowest_value = float('inf')
        for card in hand:
            if card == retrieve_card:
                continue  # Can't discard what we're retrieving
            val = self._card_hand_value(card, player, game)
            # Prefer discarding into factions we don't care about
            if card.faction not in set(c.faction for c in player.score_pile):
                val -= 1.0
            if val < lowest_value:
                lowest_value = val
                best_discard = card

        if best_discard is None:
            return None

        return (retrieve_faction, retrieve_card, best_discard)

    # ─── EVALUATION HELPERS ───────────────────────────────────

    def _estimate_claim_probability(self, rank: int, game: GameState) -> float:
        """Estimate probability that this rank wins a claim."""
        # Simple model: higher rank = higher probability
        # Adjusted by player count (more players = more competition)
        base = rank / 10.0
        competition = 1.0 / game.num_players
        return min(1.0, base * (0.5 + competition))

    def _estimate_sneak_success(self) -> float:
        """Estimate probability of a successful Sneak."""
        # Base rate depends on player count
        # More players = more likely someone else also Sneaks
        base_rate = 0.6  # Assume ~60% base success

        # Adjust based on recent history
        if len(self.sneak_history) >= 2:
            recent_sneaks = sum(self.sneak_history[-3:])
            if recent_sneaks >= 2:
                base_rate += 0.15  # Others have been Sneaking → risky
            elif recent_sneaks == 0:
                base_rate += 0.10  # Nobody Sneaked recently → safe

        return max(0.1, min(0.9, base_rate))

    def _estimate_shove_tie(self, game: GameState) -> float:
        """Estimate probability of tying with another Shove."""
        # Rough estimate based on player count
        return 0.05 * (game.num_players - 1)

    def _evaluate_stand(self, player: Player, game: GameState) -> float:
        """Average value of available Stand cards."""
        if not game.stand:
            return 0.0
        values = [self._stand_card_value(c, player, game) for c in game.stand]
        return sum(values) / len(values)

    def _card_hand_value(self, card: Card, player: Player,
                         game: GameState) -> float:
        """How valuable is keeping this card in hand?"""
        value = 0.0

        # Wild cards are very valuable in hand
        if card.is_sneak:
            value += 3.0 + self.profile["sneak_threshold"] * 5.0
        elif card.is_shove:
            value += 4.0 + self.profile["shove_threshold"] * 5.0

        # High-rank cards are useful for winning claims
        value += card.rank * 0.3

        # Anchor potential: cards rank 1-9 can anchor Wilds
        wilds_in_hand = sum(1 for c in player.hand if c.is_wild and c is not card)
        if 1 <= card.rank <= 9 and wilds_in_hand > 0:
            value += 1.5

        return value

    def _pit_impact(self, card: Card, player: Player,
                    game: GameState) -> float:
        """How bad is it for this card to enter the Mosh Pit?"""
        pit_count = game.get_mosh_pit_faction_count(card.faction)
        threshold = game.rules["trample_threshold"][game.pkey]
        my_cards = len(player.cards_of_faction(card.faction))

        impact = 0.0

        # Near threshold = bad if we're invested
        if pit_count + 1 >= threshold and my_cards > 0:
            impact += my_cards * 3.0 * self.profile["trample_fear"]
        elif pit_count + 1 >= threshold - 1 and my_cards > 0:
            impact += my_cards * 1.5 * self.profile["trample_fear"]

        return impact

    def _opponent_faction_threat(self, faction: str, player: Player,
                                  game: GameState) -> float:
        """How much are opponents invested in this faction?"""
        threat = 0.0
        for p in game.players:
            if p.id == player.id:
                continue
            count = len(p.cards_of_faction(faction))
            threat += count
        return threat

    def _opponent_faction_investment(self, faction: str, player: Player,
                                     game: GameState) -> float:
        """Total VP opponents have invested in this faction."""
        total = 0.0
        for p in game.players:
            if p.id == player.id:
                continue
            for card in p.cards_of_faction(faction):
                total += card.vp
        return total

    # ─── SKILL / NOISE ────────────────────────────────────────

    def _noisy_score(self, base_score: float) -> float:
        """Add noise based on skill level. Lower skill = more noise."""
        noise_range = 4.0 * (1.0 - self.skill)
        if noise_range == 0:
            return base_score
        noise = self.rng.uniform(-noise_range, noise_range)
        return base_score + noise

    def _maybe_miss_opportunity(self) -> bool:
        """Beginners sometimes miss optimal plays."""
        miss_rate = 0.3 * (1.0 - self.skill)
        return self.rng.random() < miss_rate

    def update_sneak_history(self, sneak_occurred: bool):
        """Track whether Sneaks occurred for adaptive play."""
        self.sneak_history.append(sneak_occurred)
        if len(self.sneak_history) > 10:
            self.sneak_history = self.sneak_history[-10:]

    def __repr__(self):
        return (f"AI(P{self.player_id}, skill={self.skill:.1f}, "
                f"style={self.style}, aggr={self.aggression:.1f})")
