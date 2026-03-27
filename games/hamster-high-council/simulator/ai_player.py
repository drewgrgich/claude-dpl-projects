"""
Hamster High Council — Heuristic AI Player.

Three tunable axes: skill, style, aggression.
Strategic evaluation for all faction talents.
Priority-based action selection via scoring.
"""

import random
from typing import List, Optional, Tuple, Dict
from cards import Card, FACTIONS, FACTION_SYMBOLS
from game_state import GameState, Player, DIAL_MULTIPLIER, LOW_WINS_POSITIONS, next_dial


# ── Style Profiles ─────────────────────────────────────────────────

STYLE_PROFILES = {
    "balanced": {
        "description": "Well-rounded default play.",
        "high_card_weight": 1.0,       # value of high-rank cards
        "low_card_weight": 1.0,        # value of low-rank cards (for RIGHT)
        "trump_weight": 1.5,           # bonus for trump cards
        "partner_cooperation": 0.6,    # willingness to sacrifice for partner
        "dial_manipulation": 0.5,      # desire to control dial position
        "talent_eagerness": 0.7,       # how much to prioritize talent-eligible wins
    },
    "aggressive": {
        "description": "Maximize VP. Win every trick possible, especially at RIGHT.",
        "high_card_weight": 1.3,
        "low_card_weight": 1.3,
        "trump_weight": 2.0,
        "partner_cooperation": 0.3,
        "dial_manipulation": 0.3,
        "talent_eagerness": 0.5,
    },
    "tactical": {
        "description": "Dial control. Prioritize talents and alliance manipulation.",
        "high_card_weight": 0.8,
        "low_card_weight": 0.8,
        "trump_weight": 1.0,
        "partner_cooperation": 0.7,
        "dial_manipulation": 1.0,
        "talent_eagerness": 1.0,
    },
    "cooperative": {
        "description": "Partner-focused. Sacrifice personal wins for partner advantage.",
        "high_card_weight": 0.7,
        "low_card_weight": 0.7,
        "trump_weight": 1.0,
        "partner_cooperation": 1.0,
        "dial_manipulation": 0.4,
        "talent_eagerness": 0.5,
    },
}


class HeuristicAI:
    """Heuristic AI player for Hamster High Council.

    Uses priority-based scoring to select which card to play,
    and strategic evaluation for talent decisions.
    """

    def __init__(self, player_id: int, skill: float = 1.0,
                 style: str = "balanced", aggression: float = 0.5,
                 rng_seed: int = 0):
        self.player_id = player_id
        self.skill = max(0.0, min(1.0, skill))
        self.style_name = style
        self.style = STYLE_PROFILES.get(style, STYLE_PROFILES["balanced"])
        self.aggression = max(0.0, min(1.0, aggression))
        self.rng = random.Random(rng_seed)

        # Reasoning log (for narration mode)
        self.last_reasoning: List[str] = []

    # ── Card Selection ─────────────────────────────────────────────

    def choose_card(self, player: Player, game: GameState,
                    led_faction: Optional[str]) -> Card:
        """Choose which card to play in a trick."""
        self.last_reasoning = []
        legal = game.get_legal_plays(player, led_faction)

        if len(legal) == 1:
            self.last_reasoning.append(f"Only one legal play: {legal[0]}")
            return legal[0]

        if led_faction is None:
            # We're leading
            return self._choose_lead(player, game, legal)
        else:
            # We're following
            return self._choose_follow(player, game, legal, led_faction)

    def _choose_lead(self, player: Player, game: GameState,
                     legal: List[Card]) -> Card:
        """Choose which card to lead with."""
        candidates = []
        dial = game.dial_position
        low_wins = dial in LOW_WINS_POSITIONS
        multiplier = DIAL_MULTIPLIER[dial]
        partner_id = game.get_partner_id(player.id)

        self.last_reasoning.append(
            f"Leading at {dial} ({'low wins' if low_wins else 'high wins'}, ×{multiplier})")

        for card in legal:
            score = 0.0
            reasons = []

            # Base: how likely are we to win with this card?
            win_chance = self._estimate_win_chance(card, game, low_wins, None)
            score += win_chance * 10.0 * multiplier
            reasons.append(f"win_chance={win_chance:.1%}")

            # Trump bonus
            if card.faction == game.trump_faction:
                bonus = 3.0 * self.style["trump_weight"]
                score += bonus
                reasons.append(f"trump_bonus=+{bonus:.1f}")

            # Talent bonus — prefer leading with factions whose talents we want
            talent_value = self._talent_value(card.faction, player, game)
            score += talent_value * self.style["talent_eagerness"]
            if talent_value > 0:
                reasons.append(f"talent_value=+{talent_value:.1f}")

            # At RIGHT (×2), low cards are gold — lead with strong low cards
            if low_wins:
                low_strength = max(0, 5 - card.rank) * self.style["low_card_weight"]
                score += low_strength
                reasons.append(f"low_strength=+{low_strength:.1f}")
            else:
                high_strength = card.rank * 0.5 * self.style["high_card_weight"]
                score += high_strength

            # Dial manipulation: do we WANT to win and rotate?
            next_pos = next_dial(dial)
            dial_desire = self._dial_desire(next_pos, player, game)
            score += dial_desire * self.style["dial_manipulation"]

            # Prefer leading factions where we have depth (more cards = harder to beat)
            faction_depth = len(player.cards_of_faction(card.faction))
            if faction_depth >= 3:
                score += 1.0

            # Skill noise
            score = self._noisy_score(score)

            candidates.append((card, score, reasons))

        candidates.sort(key=lambda x: x[1], reverse=True)

        # Log top 3 for narration
        for card, score, reasons in candidates[:3]:
            self.last_reasoning.append(
                f"  {card.short()}: score={score:.1f} ({', '.join(reasons)})")

        choice = candidates[0][0]
        self.last_reasoning.append(f"  → Lead {choice.short()}")
        return choice

    def _choose_follow(self, player: Player, game: GameState,
                       legal: List[Card], led_faction: str) -> Card:
        """Choose which card to play when following."""
        dial = game.dial_position
        low_wins = dial in LOW_WINS_POSITIONS
        multiplier = DIAL_MULTIPLIER[dial]
        on_suit = [c for c in legal if c.faction == led_faction]
        off_suit = [c for c in legal if c.faction != led_faction]
        partner_id = game.get_partner_id(player.id)

        self.last_reasoning.append(
            f"Following {led_faction} at {dial} "
            f"({'low wins' if low_wins else 'high wins'}, ×{multiplier}). "
            f"On-suit: {len(on_suit)}, Off-suit: {len(off_suit)}")

        candidates = []

        for card in legal:
            score = 0.0
            reasons = []

            if card.faction == led_faction:
                # On-suit: we can win
                win_chance = self._estimate_win_chance(card, game, low_wins, led_faction)
                if win_chance > 0.5:
                    # We likely win — value the VP
                    score += win_chance * 8.0 * multiplier
                    reasons.append(f"likely_win={win_chance:.0%}")

                    # Talent bonus
                    talent_value = self._talent_value(card.faction, player, game)
                    score += talent_value * self.style["talent_eagerness"]
                else:
                    # Unlikely to win — dump lowest card to conserve good ones
                    if low_wins:
                        score -= card.rank * 0.5  # high = bad at RIGHT
                    else:
                        score -= (10 - card.rank) * 0.5  # low = bad at CROSS/LEFT

                    # But if partner might win, play cooperatively
                    if partner_id is not None:
                        coop_factor = self.style["partner_cooperation"]
                        # Dump a card that won't accidentally beat partner
                        if low_wins:
                            # At RIGHT, play HIGH (bad) card to not steal partner's low win
                            score += card.rank * coop_factor
                            reasons.append("dump_high_for_partner")
                        else:
                            # At CROSS/LEFT, play LOW card to not steal partner's high win
                            score += (10 - card.rank) * coop_factor
                            reasons.append("dump_low_for_partner")

            elif card.faction == game.trump_faction:
                # Trump override — strong play but costly
                trump_win_chance = self._estimate_trump_win(card, game)
                if trump_win_chance > 0.5:
                    score += trump_win_chance * 10.0 * multiplier * self.style["trump_weight"]
                    reasons.append(f"trump_override={trump_win_chance:.0%}")
                    # Talent bonus for trump faction
                    talent_value = self._talent_value(card.faction, player, game)
                    score += talent_value * self.style["talent_eagerness"]
                else:
                    # Bad trump — waste
                    score -= 2.0

            else:
                # Off-suit, non-trump — can't win. Dump least useful card.
                # Prefer dumping cards we don't need for future tricks
                usefulness = self._card_future_value(card, player, game)
                score = -usefulness  # lower future value = better to dump
                reasons.append(f"dump_value={usefulness:.1f}")

            score = self._noisy_score(score)
            candidates.append((card, score, reasons))

        candidates.sort(key=lambda x: x[1], reverse=True)

        for card, score, reasons in candidates[:3]:
            self.last_reasoning.append(
                f"  {card.short()}: score={score:.1f} ({', '.join(reasons)})")

        choice = candidates[0][0]
        self.last_reasoning.append(f"  → Play {choice.short()}")
        return choice

    # ── Talent Decisions ───────────────────────────────────────────

    def choose_talent(self, player: Player, game: GameState,
                      faction: str) -> bool:
        """Decide whether to use a faction talent."""
        self.last_reasoning.append(f"Talent available: {FACTION_SYMBOLS[faction]} {faction}")

        if faction == "RED":
            return self._decide_red_talent(player, game)
        elif faction == "ORANGE":
            return self._decide_orange_talent(player, game)
        elif faction == "YELLOW":
            return self._decide_yellow_talent(player, game)
        elif faction == "GREEN":
            return True  # Always good: free card + information
        elif faction == "BLUE":
            return self._decide_blue_talent(player, game)
        elif faction == "PURPLE":
            # Pocket the Past: bank 1 VP but costs a hand card
            use = len(player.hand) >= 2  # need cards to bank + discard
            self.last_reasoning.append(
                f"  Purple talent: hand={len(player.hand)} → {'USE' if use else 'SKIP'}")
            return use
        return False

    def _decide_red_talent(self, player: Player, game: GameState) -> bool:
        """Red: Rotate dial back. Use if the next position is unfavorable."""
        # The dial already rotated forward after winning. Red undoes that.
        # Current dial = position AFTER forward rotation.
        # If we use Red, dial goes back to where it was BEFORE we won.
        current = game.dial_position
        would_be = game.dial_position  # stays at current if we DON'T use Red
        # Using Red moves it back one
        from game_state import prev_dial
        would_revert_to = prev_dial(current)

        # Do we prefer the reverted position?
        desire_current = self._dial_desire(current, player, game)
        desire_reverted = self._dial_desire(would_revert_to, player, game)

        use = desire_reverted > desire_current
        self.last_reasoning.append(
            f"  Red talent: current={current}(score={desire_current:.1f}), "
            f"revert={would_revert_to}(score={desire_reverted:.1f}) → {'USE' if use else 'SKIP'}")
        return use

    def _decide_orange_talent(self, player: Player, game: GameState) -> bool:
        """Orange: Swap hand card for crate card. Use if there's a good swap."""
        if game.crate.empty or not player.hand:
            return False
        # Look for a significant upgrade
        weakest = min(player.hand, key=lambda c: self._card_future_value(c, player, game))
        best_crate = max(game.crate.cards,
                         key=lambda c: self._card_future_value(c, player, game))
        weak_val = self._card_future_value(weakest, player, game)
        best_val = self._card_future_value(best_crate, player, game)
        use = best_val > weak_val + 1.0  # require meaningful improvement
        self.last_reasoning.append(
            f"  Orange talent: weakest={weakest}(val={weak_val:.1f}), "
            f"best_crate={best_crate}(val={best_val:.1f}) → {'USE' if use else 'SKIP'}")
        return use

    def _decide_yellow_talent(self, player: Player, game: GameState) -> bool:
        """Yellow: Quick Fix (2 cards next trick). Use if we have a strong pair."""
        for f in FACTIONS:
            cards = player.cards_of_faction(f)
            if len(cards) >= 2:
                # Worth it if the pair is strong
                cards.sort(key=lambda c: c.rank, reverse=True)
                top_pair_rank = cards[0].rank + cards[1].rank
                if top_pair_rank >= 10:  # decent pair
                    self.last_reasoning.append(
                        f"  Yellow talent: strong pair in {f} "
                        f"({cards[0]}, {cards[1]}) → USE")
                    return True
        self.last_reasoning.append(f"  Yellow talent: no strong pair → SKIP")
        return False

    def _decide_blue_talent(self, player: Player, game: GameState) -> bool:
        """Blue: Make 2 opponents swap a random card each. Use strategically."""
        # Use it to disrupt the leading player, or when we're behind
        opponents = [p for p in game.players if p.id != player.id and len(p.hand) > 0]
        if len(opponents) < 2:
            return False

        # Always use if someone is close to winning
        leader = max(game.players, key=lambda p: p.vp)
        if leader.id != player.id and leader.vp >= game.vp_target * 0.75:
            self.last_reasoning.append(
                f"  Blue talent: P{leader.id} at {leader.vp} VP, disrupting → USE")
            return True

        # Use with some probability based on aggression
        use = self.rng.random() < self.aggression
        self.last_reasoning.append(
            f"  Blue talent: aggression={self.aggression:.1f} → {'USE' if use else 'SKIP'}")
        return use

    # ── Strategic Orange Swap ──────────────────────────────────────

    def choose_orange_swap(self, player: Player, game: GameState
                           ) -> Tuple[Optional[Card], Optional[Card]]:
        """Strategically choose which cards to swap for Orange talent."""
        if not player.hand or game.crate.empty:
            return None, None

        # Evaluate every possible swap
        best_swap = None
        best_improvement = -999

        for hand_card in player.hand:
            hand_val = self._card_future_value(hand_card, player, game)
            for crate_card in game.crate.cards:
                crate_val = self._card_future_value(crate_card, player, game)
                improvement = crate_val - hand_val
                if improvement > best_improvement:
                    best_improvement = improvement
                    best_swap = (hand_card, crate_card)

        if best_swap and best_improvement > 0.5:
            self.last_reasoning.append(
                f"  Orange swap: {best_swap[0]} → {best_swap[1]} "
                f"(improvement={best_improvement:.1f})")
            return best_swap
        return None, None

    # ── Strategic Green Keep ───────────────────────────────────────

    def choose_green_keep(self, player: Player, peeked: List[Card],
                          game: GameState) -> Tuple[Card, List[Card]]:
        """Strategically choose which peeked card to keep (Green talent)."""
        # Keep the card with highest future value
        scored = [(c, self._card_future_value(c, player, game)) for c in peeked]
        scored.sort(key=lambda x: x[1], reverse=True)

        keep = scored[0][0]
        rest = [c for c, _ in scored[1:]]

        self.last_reasoning.append(
            f"  Green keep: {keep} (val={scored[0][1]:.1f}), "
            f"return {rest}")
        return keep, rest

    # ── Strategic Blue Targets ─────────────────────────────────────

    def choose_blue_targets(self, player: Player,
                            opponents: List[Player],
                            game: GameState) -> Tuple[Player, Player]:
        """Choose which 2 opponents swap cards (Blue talent)."""
        # Target the leader and whoever is closest to them
        opponents_sorted = sorted(opponents, key=lambda p: p.vp, reverse=True)
        target1 = opponents_sorted[0]  # highest VP opponent

        # Second target: pick the one we want to disrupt least (our partner if possible)
        partner_id = game.get_partner_id(player.id)
        remaining = [p for p in opponents_sorted[1:] if p.id != partner_id]
        if remaining:
            target2 = remaining[0]
        else:
            target2 = opponents_sorted[1] if len(opponents_sorted) > 1 else opponents_sorted[0]

        self.last_reasoning.append(
            f"  Blue targets: P{target1.id}(VP={target1.vp}) ↔ "
            f"P{target2.id}(VP={target2.vp})")
        return target1, target2

    # ── Quick Fix Card Selection ───────────────────────────────────

    def choose_quick_fix_cards(self, player: Player,
                               game: GameState) -> Tuple[Optional[Card], Optional[Card]]:
        """Choose 2 cards of same faction for Quick Fix lead."""
        dial = game.dial_position
        low_wins = dial in LOW_WINS_POSITIONS
        multiplier = DIAL_MULTIPLIER[dial]

        best_pair = None
        best_score = -999

        for faction in FACTIONS:
            cards = player.cards_of_faction(faction)
            if len(cards) < 2:
                continue

            # Try all pairs
            for i in range(len(cards)):
                for j in range(i + 1, len(cards)):
                    c1, c2 = cards[i], cards[j]

                    # The competing card is the better one for current dial
                    if low_wins:
                        compete = min(c1, c2, key=lambda c: c.rank)
                    else:
                        compete = max(c1, c2, key=lambda c: c.rank)

                    win_chance = self._estimate_win_chance(compete, game, low_wins, None)
                    # 5-card trick = more VP
                    score = win_chance * 5 * multiplier

                    # Trump pair is extra strong
                    if faction == game.trump_faction:
                        score *= 1.5

                    # Talent bonus
                    score += self._talent_value(faction, player, game) * 0.5

                    if score > best_score:
                        best_score = score
                        best_pair = (c1, c2)

        if best_pair:
            self.last_reasoning.append(
                f"  Quick Fix pair: {best_pair[0]} + {best_pair[1]} "
                f"(score={best_score:.1f})")
        return best_pair if best_pair else (None, None)

    # ── Castle's Blessing Card Selection ───────────────────────────

    def choose_blessing_keep(self, player: Player, all_cards: List[Card],
                             game: GameState) -> Tuple[List[Card], List[Card]]:
        """Choose best 8 cards from expanded hand (Castle's Blessing)."""
        scored = [(c, self._card_future_value(c, player, game)) for c in all_cards]
        scored.sort(key=lambda x: x[1], reverse=True)
        keep = [c for c, _ in scored[:8]]
        discard = [c for c, _ in scored[8:]]
        return keep, discard

    # ── Evaluation Helpers ─────────────────────────────────────────

    def _estimate_win_chance(self, card: Card, game: GameState,
                             low_wins: bool, led_faction: Optional[str]) -> float:
        """Estimate probability this card wins the trick.

        Rough heuristic based on rank position within the faction.
        """
        if card.faction == game.trump_faction:
            # Trump always beats non-trump
            # Estimate based on rank vs other potential trump cards
            return 0.5 + card.rank * 0.045  # rank 10 ≈ 95%, rank 0 ≈ 50%

        if led_faction and card.faction != led_faction:
            return 0.0  # off-suit non-trump can't win

        if low_wins:
            # Lower rank = better. Rank 0 ≈ 90%, rank 10 ≈ 10%
            return max(0.05, 0.9 - card.rank * 0.08)
        else:
            # Higher rank = better. Rank 10 ≈ 90%, rank 0 ≈ 10%
            return max(0.05, 0.1 + card.rank * 0.08)

    def _estimate_trump_win(self, card: Card, game: GameState) -> float:
        """Estimate probability of winning with a trump card."""
        if card.faction != game.trump_faction:
            return 0.0
        return 0.5 + card.rank * 0.045

    def _card_future_value(self, card: Card, player: Player,
                           game: GameState) -> float:
        """How valuable is this card for future tricks?"""
        value = 0.0

        # High-rank cards are generally valuable
        value += card.rank * 0.3

        # Trump cards are premium
        if card.faction == game.trump_faction:
            value += 4.0 + card.rank * 0.3

        # Elite faction gets tiebreak advantage
        if card.faction == game.elite_faction:
            value += 1.5

        # Low-rank cards have value for RIGHT tricks
        if card.rank <= 3:
            value += (4 - card.rank) * 0.5  # Rank 0 = +2, rank 3 = +0.5

        # Faction depth: cards in factions we have many of are more flexible
        depth = len(player.cards_of_faction(card.faction))
        value += depth * 0.2

        # Interns (rank 0) have the draw bonus
        if card.is_intern:
            value += 1.0

        return value

    def _talent_value(self, faction: str, player: Player,
                      game: GameState) -> float:
        """How valuable is triggering this faction's talent right now?"""
        if faction == "RED":
            # Value depends on whether we want to control the dial
            return 2.0 * self.style["dial_manipulation"]

        elif faction == "ORANGE":
            # More valuable with a larger crate (more swap options)
            crate_size = game.crate.size
            return min(3.0, crate_size * 0.15)

        elif faction == "YELLOW":
            # Quick Fix: valuable if we have a same-faction pair
            for f in FACTIONS:
                if len(player.cards_of_faction(f)) >= 2:
                    return 2.5
            return 0.0

        elif faction == "GREEN":
            # Free card + deck manipulation. Always decent.
            return 2.0 if not game.vault.empty else 0.0

        elif faction == "BLUE":
            # Disruption. More valuable when opponents are strong.
            leader = max(game.players, key=lambda p: p.vp)
            if leader.id != player.id:
                lead_gap = leader.vp - player.vp
                return min(3.0, lead_gap * 0.1)
            return 0.5

        elif faction == "PURPLE":
            # Pocket the Past: free 1 VP but costs a hand card.
            if len(player.hand) >= 2:
                return 2.0
            return 0.0

        return 0.0

    def _dial_desire(self, position: str, player: Player,
                     game: GameState) -> float:
        """How much do we want the dial at this position?

        Considers: multiplier, win capability, partner alignment.
        """
        multiplier = DIAL_MULTIPLIER[position]
        low_wins = position in LOW_WINS_POSITIONS

        score = 0.0

        # Base desire for high multiplier
        score += (multiplier - 1) * 2.0 * self.aggression

        # Do we have good cards for this position?
        if low_wins:
            low_cards = [c for c in player.hand if c.rank <= 3]
            score += len(low_cards) * 0.5
        else:
            high_cards = [c for c in player.hand if c.rank >= 7]
            score += len(high_cards) * 0.3

        # Trump cards work at any position
        trump_cards = [c for c in player.hand if c.faction == game.trump_faction]
        score += len(trump_cards) * 0.3

        return score

    def _noisy_score(self, base_score: float) -> float:
        """Add skill-based noise to a score."""
        noise_range = 4.0 * (1.0 - self.skill)
        if noise_range == 0:
            return base_score
        noise = self.rng.uniform(-noise_range, noise_range)
        return base_score + noise
