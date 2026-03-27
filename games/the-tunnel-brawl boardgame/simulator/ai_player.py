"""
Heuristic AI player for The Tunnel Brawl v2.0.

Three tunable axes:
  - Skill (0.0–1.0): mistake frequency
  - Style (categorical): strategic preferences
  - Aggression (0.0–1.0): willingness to play high cards early
"""

from typing import List, Tuple, Optional, Dict
import random

from cards import Card

# ─── Play Style Profiles ───────────────────────────────────────

STYLE_PROFILES = {
    "balanced": {
        "description": "Well-rounded default play.",
        "high_card_home_weight": 1.0,     # Bias toward putting best card in Home
        "wild_eagerness": 0.5,            # How eager to play Wilds
        "clash_aggression": 0.5,          # How high to play in CLASH!
        "talent_priority": 1.0,           # How much to optimize for talent trigger
        "split_strength": True,           # Spread strength across both tunnels
        "domination_eagerness": 0.5,      # How much to chase domination bonus
    },
    "aggressive": {
        "description": "All-in on one tunnel. Plays high cards, chases dominations.",
        "high_card_home_weight": 2.0,
        "wild_eagerness": 0.8,
        "clash_aggression": 0.9,
        "talent_priority": 0.5,
        "split_strength": False,
        "domination_eagerness": 1.0,      # Loves the big-win bonus
    },
    "defensive": {
        "description": "Spread strength evenly. Aim for consistent small wins.",
        "high_card_home_weight": 0.5,
        "wild_eagerness": 0.3,
        "clash_aggression": 0.3,
        "talent_priority": 1.5,
        "split_strength": True,
        "domination_eagerness": 0.2,      # Doesn't chase dominations
    },
    "wild_gambler": {
        "description": "Loves playing Wilds. Lives for the Wild Surge draw.",
        "high_card_home_weight": 1.0,
        "wild_eagerness": 1.0,
        "clash_aggression": 0.6,
        "talent_priority": 0.8,
        "split_strength": True,
        "domination_eagerness": 0.7,      # Wilds can dominate
    },
    "clash_baiter": {
        "description": "Plays middle-rank cards hoping for ties. Loves CLASH! moments.",
        "high_card_home_weight": 0.3,
        "wild_eagerness": 0.2,
        "clash_aggression": 0.8,
        "talent_priority": 0.5,
        "split_strength": True,
        "domination_eagerness": 0.1,      # Actively avoids big-rank plays
    },
}


class HeuristicAI:
    """AI player that makes reasonable deployment decisions."""

    def __init__(self, player_id: int, skill: float = 1.0,
                 style: str = "balanced", aggression: float = 0.5,
                 rng_seed: int = None):
        self.player_id = player_id
        self.skill = max(0.0, min(1.0, skill))
        self.style = style
        self.aggression = max(0.0, min(1.0, aggression))
        self.style_profile = STYLE_PROFILES.get(style, STYLE_PROFILES["balanced"])
        self.rng = random.Random(rng_seed if rng_seed is not None else player_id * 7919)

        # Track info across rounds
        self.opponent_history: Dict[int, List[Card]] = {}  # opponent_id -> cards they played

    # ─── Main Decision: Choose Deployment ────────────────────────

    def choose_deployment(self, hand: List[Card], game_state,
                          forced_card: Optional[Card] = None) -> Tuple[Card, Card]:
        """
        Choose which card to play in Home tunnel and Away tunnel.
        Returns (home_card, away_card).
        """
        if len(hand) < 2:
            # Shouldn't happen, but fallback
            return hand[0], hand[0] if len(hand) == 1 else hand[1]

        # If Green talent forced a card, we must play it somewhere
        forced = forced_card
        if forced and forced not in hand:
            forced = None  # Card no longer in hand

        candidates = self._generate_deployment_candidates(hand, forced)

        if not candidates:
            # Absolute fallback: play first two cards
            return hand[0], hand[1]

        # Score each candidate
        scored = []
        for home, away in candidates:
            score = self._score_deployment(home, away, hand, game_state)
            scored.append((score, home, away))

        # Skill-based noise
        if self.skill < 1.0:
            scored = [(self._noisy_score(s), h, a) for s, h, a in scored]

        # Skill-based chance of picking randomly
        if self._should_make_random_choice():
            idx = self.rng.randint(0, len(scored) - 1)
            return scored[idx][1], scored[idx][2]

        # Pick the best
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[0][1], scored[0][2]

    def _generate_deployment_candidates(self, hand: List[Card],
                                         forced: Optional[Card] = None) -> List[Tuple[Card, Card]]:
        """Generate possible (home, away) pairs from hand."""
        candidates = []

        # If we have a forced card, it must be one of the two
        if forced:
            for other in hand:
                if other != forced or hand.count(other) >= 2:
                    candidates.append((forced, other))
                    if other != forced:
                        candidates.append((other, forced))
            return candidates

        # For small hands, enumerate all pairs
        if len(hand) <= 8:
            for i, c1 in enumerate(hand):
                for j, c2 in enumerate(hand):
                    if i != j:
                        candidates.append((c1, c2))
            return candidates

        # For larger hands (shouldn't happen normally), sample
        seen = set()
        for _ in range(min(30, len(hand) * 4)):
            i, j = self.rng.sample(range(len(hand)), 2)
            pair = (id(hand[i]), id(hand[j]))
            if pair not in seen:
                seen.add(pair)
                candidates.append((hand[i], hand[j]))
        return candidates

    def _score_deployment(self, home: Card, away: Card,
                           hand: List[Card], game_state) -> float:
        """Score a (home, away) deployment pair."""
        score = 0.0
        profile = self.style_profile
        strict = game_state.rules.get("wild_strict_mode", False)

        # Base value: rank of each card (higher is usually better)
        home_rank = self._effective_rank(home, away, strict)
        away_rank = self._effective_rank(away, home, strict)

        # Weight Home vs Away (some styles bias one direction)
        score += home_rank * profile["high_card_home_weight"]
        score += away_rank * (2.0 - profile["high_card_home_weight"])

        # Wild bonus/penalty
        if home.is_wild or away.is_wild:
            wild_card = home if home.is_wild else away
            anchor_card = away if home.is_wild else home

            will_activate = (not anchor_card.is_wild and
                             anchor_card.faction == wild_card.faction and
                             (not strict or anchor_card.rank <= 5))

            if will_activate:
                # Wild will activate — bonus based on eagerness
                score += 3.0 * profile["wild_eagerness"]
            else:
                # Wild will trip — penalty
                score -= 4.0 * (1.0 - profile["wild_eagerness"])

        # Split strength preference
        if profile["split_strength"]:
            # Prefer balanced deployment — penalize lopsided plays
            diff = abs(home_rank - away_rank)
            score -= diff * 0.3
        else:
            # Aggressive: prefer lopsided (all-in on one tunnel)
            diff = abs(home_rank - away_rank)
            score += diff * 0.2

        # Clash baiting: prefer middle ranks (4-6) that might tie
        if self.style == "clash_baiter":
            for card, rank in [(home, home_rank), (away, away_rank)]:
                if 4 <= rank <= 6:
                    score += 1.5

        # Power Play bonus awareness: winning with rank 8+ gives extra VP
        pp_min = game_state.rules.get("power_play_min_rank", 0)
        pp_bonus = game_state.rules.get("power_play_bonus_vp", 0)
        if pp_min > 0 and pp_bonus > 0:
            for rank in [home_rank, away_rank]:
                if rank >= pp_min:
                    # High card deployed = potential Power Play
                    score += pp_bonus * 1.5 * profile.get("domination_eagerness", 0.5)

        # Aggression modifier: prefer higher total rank
        total_rank = home_rank + away_rank
        score += total_rank * self.aggression * 0.2

        # Conservation: with few cards in hand, prefer playing low cards
        remaining_hand_size = len(hand) - 2
        if remaining_hand_size <= 2 and not self.style == "aggressive":
            # Save strong cards
            if home_rank >= 8 or away_rank >= 8:
                score -= 1.0

        return score

    def _effective_rank(self, card: Card, other_tunnel_card: Card,
                         strict_wild: bool = False) -> int:
        """Get the effective rank of a card considering Wild rules."""
        if not card.is_wild:
            return card.rank

        # Wild card — check cross-body activation
        if (not other_tunnel_card.is_wild and
                other_tunnel_card.faction == card.faction):
            # In strict mode, anchor must be rank 1-5
            if strict_wild and other_tunnel_card.rank > 5:
                return 0
            return card.rank  # Activated: 0 or 10
        else:
            return 0  # Tripped

    # ─── CLASH! Decision ─────────────────────────────────────────

    def choose_clash_card(self, player_id: int, game_state, clash_round: int) -> Card:
        """Choose a card to play in a CLASH! resolution."""
        hand = game_state.players[player_id].hand
        if not hand:
            return None

        profile = self.style_profile

        # Score each card for CLASH!
        scored = []
        for card in hand:
            score = card.rank  # Base: higher rank = better in CLASH!
            # Aggression: play stronger cards in CLASH!
            score *= (0.5 + profile["clash_aggression"])
            # Higher clash rounds = higher stakes = play better cards
            score += clash_round * 0.5
            scored.append((self._noisy_score(score), card))

        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[0][1]

    # ─── Green Talent: Choose forced card ────────────────────────

    def choose_green_target(self, my_id: int, target_id: int,
                            target_hand: List[Card], game_state) -> Card:
        """Green talent: pick a card in opponent's hand to force them to play."""
        # Force them to play their worst card (lowest rank, or a trippable Wild)
        scored = []
        for card in target_hand:
            # Lower score = worse for the opponent = better for us
            score = card.rank
            if card.is_wild:
                score = -5  # Wilds are hardest to use well when forced
            scored.append((score, card))

        scored.sort(key=lambda x: x[0])
        return scored[0][1]  # Force their worst card

    # ─── Talent Selection ────────────────────────────────────────

    def choose_talent_faction(self, winning_cards: List[Card],
                               can_double: bool, game_state) -> Optional[str]:
        """Choose which faction talent to trigger based on winning cards."""
        if not winning_cards:
            return None

        # Get unique factions from winning cards
        factions = list(set(c.faction for c in winning_cards if c.faction != "NONE"))
        if not factions:
            return None

        # Score each faction talent
        player = game_state.players[self.player_id]
        scored = []
        for faction in factions:
            score = self._score_talent(faction, player, game_state)
            scored.append((self._noisy_score(score), faction))

        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[0][1]

    def _score_talent(self, faction: str, player, game_state) -> float:
        """Score how valuable a faction talent is right now."""
        if faction == "RED":
            return 3.0  # Disruption is usually good
        elif faction == "ORANGE":
            if not game_state.discard_pile.empty:
                top_card = game_state.discard_pile.cards[-1]
                return 2.0 + (top_card.rank / 10.0) * 3.0
            return 0.5
        elif faction == "YELLOW":
            # More valuable when hand is small
            return 4.0 - len(player.hand) * 0.3
        elif faction == "GREEN":
            return 3.5  # Information + disruption
        elif faction == "BLUE":
            # Chaos — good when opponents have strong hands
            return 2.5
        elif faction == "PURPLE":
            # Return-to-deck is much weaker than return-to-hand
            return_to_deck = game_state.rules.get("purple_return_to_deck", False)
            if return_to_deck:
                # Card goes back to draw pile — barely useful. Score low.
                return 1.0
            else:
                # Card goes to hand — very strong with high-rank cards
                winning = game_state.round_winning_cards.get(self.player_id, [])
                best_rank = max((c.rank for c in winning), default=0)
                return 1.0 + best_rank * 0.4
        return 1.0

    # ─── Hand Management ─────────────────────────────────────────

    def choose_discard(self, hand: List[Card], excess: int) -> List[Card]:
        """Choose which cards to discard when over hand limit."""
        # Discard lowest-ranked cards
        sorted_hand = sorted(hand, key=lambda c: c.rank)
        return sorted_hand[:excess]

    # ─── Skill-Based Mistakes ────────────────────────────────────

    def _noisy_score(self, base_score: float) -> float:
        """Add noise to scores based on skill level."""
        noise_range = 4.0 * (1.0 - self.skill)
        if noise_range == 0:
            return base_score
        return base_score + self.rng.uniform(-noise_range, noise_range)

    def _should_make_random_choice(self) -> bool:
        """Beginners sometimes just play randomly."""
        rate = 0.2 * (1.0 - self.skill)
        return self.rng.random() < rate

    def _forget_wild_rule(self) -> bool:
        """Beginners sometimes forget about Wild cross-body requirement."""
        rate = 0.3 * (1.0 - self.skill)
        return self.rng.random() < rate
