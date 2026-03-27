"""
Hamster High Council v1.0 — Heuristic AI Player.

No partnerships or dial awareness. Instead focuses on:
  - Wobbly faction awareness (low wins when Wobbly is led)
  - Council seat exploitation (Trump > Elite > Wobbly strategy)
  - Hand manipulation talents
  - Stash accumulation (more cards = more VP)
"""

import random
from typing import List, Optional, Tuple, Dict
from cards import Card, FACTIONS, FACTION_SYMBOLS
from game_state import GameState, Player


STYLE_PROFILES = {
    "balanced": {
        "description": "Well-rounded default play.",
        "trump_weight": 1.5,
        "wobbly_lead_desire": 0.5,
        "aggression": 0.5,
        "talent_eagerness": 0.7,
    },
    "aggressive": {
        "description": "Win every trick possible. Use Trump freely.",
        "trump_weight": 2.0,
        "wobbly_lead_desire": 0.3,
        "aggression": 0.8,
        "talent_eagerness": 0.5,
    },
    "wobbly_hunter": {
        "description": "Exploit the Wobbly seat. Lead Wobbly to win with low cards.",
        "trump_weight": 1.0,
        "wobbly_lead_desire": 1.0,
        "aggression": 0.5,
        "talent_eagerness": 0.7,
    },
    "hoarder": {
        "description": "Maximize hand size via talents. Value card draw.",
        "trump_weight": 1.0,
        "wobbly_lead_desire": 0.4,
        "aggression": 0.3,
        "talent_eagerness": 1.0,
    },
}


class HeuristicAI:
    """Heuristic AI for Hamster High Council v1.0."""

    def __init__(self, player_id: int, skill: float = 1.0,
                 style: str = "balanced", rng_seed: int = 0):
        self.player_id = player_id
        self.skill = max(0.0, min(1.0, skill))
        self.style_name = style
        self.style = STYLE_PROFILES.get(style, STYLE_PROFILES["balanced"])
        self.rng = random.Random(rng_seed)
        self.last_reasoning: List[str] = []

    # ── Card Selection ─────────────────────────────────────────────

    def choose_card(self, player: Player, game: GameState,
                    led_faction: Optional[str]) -> Card:
        self.last_reasoning = []
        legal = game.get_legal_plays(player, led_faction)

        if len(legal) == 1:
            self.last_reasoning.append(f"Only one legal play: {legal[0]}")
            return legal[0]

        if led_faction is None:
            return self._choose_lead(player, game, legal)
        else:
            return self._choose_follow(player, game, legal, led_faction)

    def _choose_lead(self, player: Player, game: GameState,
                     legal: List[Card]) -> Card:
        candidates = []
        wobbly = game.wobbly_faction

        self.last_reasoning.append("Leading trick")

        for card in legal:
            score = 0.0
            reasons = []

            # Trump leads are powerful
            if card.faction == game.trump_faction:
                win_chance = 0.5 + card.rank * 0.045
                score += win_chance * 8.0 * self.style["trump_weight"]
                reasons.append(f"trump={win_chance:.0%}")

            # Wobbly leads: LOW rank is strong (inversion)
            elif card.faction == wobbly:
                # Low rank = high win chance when Wobbly is led
                win_chance = max(0.1, 0.9 - card.rank * 0.08)
                wobbly_desire = self.style["wobbly_lead_desire"]
                score += win_chance * 6.0 * wobbly_desire
                reasons.append(f"wobbly_low={win_chance:.0%}")

                # Leading Wobbly with a high card is bad
                if card.rank >= 7:
                    score -= 3.0
                    reasons.append("high_wobbly_penalty")

            # Standard leads: high rank is good
            else:
                win_chance = 0.1 + card.rank * 0.08
                score += win_chance * 5.0
                reasons.append(f"standard={win_chance:.0%}")

            # Elite tiebreak bonus
            if card.faction == game.elite_faction:
                score += 1.0
                reasons.append("elite_bonus")

            # Talent bonus
            talent_val = self._talent_value(card.faction, player, game)
            score += talent_val * self.style["talent_eagerness"]
            if talent_val > 0:
                reasons.append(f"talent=+{talent_val:.1f}")

            # Faction depth bonus (we control more of this suit)
            depth = len(player.cards_of_faction(card.faction))
            if depth >= 3:
                score += 1.0

            score = self._noisy_score(score)
            candidates.append((card, score, reasons))

        candidates.sort(key=lambda x: x[1], reverse=True)
        for card, score, reasons in candidates[:3]:
            self.last_reasoning.append(
                f"  {card.short()}: score={score:.1f} ({', '.join(reasons)})")

        choice = candidates[0][0]
        self.last_reasoning.append(f"  → Lead {choice.short()}")
        return choice

    def _choose_follow(self, player: Player, game: GameState,
                       legal: List[Card], led_faction: str) -> Card:
        candidates = []
        wobbly = game.wobbly_faction
        is_wobbly_led = (led_faction == wobbly)
        on_suit = [c for c in legal if c.faction == led_faction]

        self.last_reasoning.append(
            f"Following {led_faction}"
            f"{' (WOBBLY — low wins!)' if is_wobbly_led else ''}")

        for card in legal:
            score = 0.0
            reasons = []

            if card.faction == led_faction:
                # On-suit: we can win
                if is_wobbly_led:
                    # Low wins — low rank is great
                    win_chance = max(0.1, 0.9 - card.rank * 0.08)
                    score += win_chance * 6.0
                    reasons.append(f"wobbly_follow={win_chance:.0%}")
                else:
                    # High wins
                    win_chance = 0.1 + card.rank * 0.08
                    score += win_chance * 5.0
                    reasons.append(f"follow={win_chance:.0%}")

                # Talent bonus if we win
                talent_val = self._talent_value(card.faction, player, game)
                score += talent_val * self.style["talent_eagerness"] * 0.5

            elif card.faction == game.trump_faction:
                # Trump override
                trump_chance = 0.5 + card.rank * 0.045
                score += trump_chance * 7.0 * self.style["trump_weight"]
                reasons.append(f"trump_override={trump_chance:.0%}")

                talent_val = self._talent_value(card.faction, player, game)
                score += talent_val * self.style["talent_eagerness"] * 0.5

            else:
                # Off-suit, non-trump: dump least useful card
                usefulness = self._card_value(card, player, game)
                score = -usefulness
                reasons.append(f"dump={usefulness:.1f}")

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
        self.last_reasoning.append(f"Talent available: {FACTION_SYMBOLS[faction]} {faction}")

        if faction == "RED":
            # Borrow Aggressively: use if opponents have cards and we have spare
            opponents = [p for p in game.players
                         if p.id != player.id and len(p.hand) > 0]
            use = len(opponents) > 0 and len(player.hand) > 2
            self.last_reasoning.append(f"  Red: {'USE' if use else 'SKIP'}")
            return use

        elif faction == "ORANGE":
            # Snack Forecast: always good (free card + info)
            use = not game.vault.empty
            self.last_reasoning.append(f"  Orange: always USE (free card)")
            return use

        elif faction == "YELLOW":
            # Quick Adjustment: usually good
            use = not game.vault.empty
            self.last_reasoning.append(f"  Yellow: USE if vault not empty")
            return use

        elif faction == "GREEN":
            # Flow Correction: draw 2, return 1 — net +1 card
            use = game.vault.size >= 1
            self.last_reasoning.append(f"  Green: USE (net +1 card)")
            return use

        elif faction == "BLUE":
            # Fair Trade: strategic swap — use against leading opponent
            opponents = [p for p in game.players
                         if p.id != player.id and len(p.hand) > 0]
            use = len(opponents) > 0 and len(player.hand) > 1
            self.last_reasoning.append(f"  Blue: {'USE' if use else 'SKIP'}")
            return use

        elif faction == "PURPLE":
            # Pocket the Past: FREE VP! Always use.
            use = len(player.hand) > 1  # need at least 1 card to bank + 1 to discard
            self.last_reasoning.append(f"  Purple: {'USE' if use else 'SKIP'} (free VP!)")
            return use

        return False

    # ── Talent Callbacks ───────────────────────────────────────────

    def choose_red_action(self, winner: Player, opponents: List[Player],
                          game: GameState):
        """Red talent: choose target and whether to force discard."""
        # Target the leader
        target = max(opponents, key=lambda p: p.vp)
        # Force discard if we have expendable cards
        do_discard = len(winner.hand) > 3
        return target, do_discard

    def choose_red_discard(self, winner: Player, revealed: Card,
                           game: GameState) -> Card:
        """Choose which card to discard from hand for Red talent."""
        return min(winner.hand, key=lambda c: self._card_value(c, winner, game))

    def choose_orange_keep(self, winner: Player, peeked: List[Card],
                           game: GameState) -> Tuple[Card, List[Card]]:
        """Orange talent: keep best peeked card."""
        scored = [(c, self._card_value(c, winner, game)) for c in peeked]
        scored.sort(key=lambda x: x[1], reverse=True)
        keep = scored[0][0]
        rest = [c for c, _ in scored[1:]]
        self.last_reasoning.append(f"  Orange keep: {keep}")
        return keep, rest

    def choose_yellow_swap(self, winner: Player, top_card: Card,
                           game: GameState) -> Tuple[bool, Optional[Card]]:
        """Yellow talent: swap hand card with top of vault?"""
        if not winner.hand:
            return False, None
        top_val = self._card_value(top_card, winner, game)
        worst = min(winner.hand, key=lambda c: self._card_value(c, winner, game))
        worst_val = self._card_value(worst, winner, game)
        do_swap = top_val > worst_val + 0.5
        self.last_reasoning.append(
            f"  Yellow: top={top_card}(val={top_val:.1f}), "
            f"worst={worst}(val={worst_val:.1f}) → {'SWAP' if do_swap else 'KEEP'}")
        return do_swap, worst if do_swap else None

    def choose_green_return(self, winner: Player, drawn: List[Card],
                            game: GameState) -> Optional[Card]:
        """Green talent: which card from hand to put on bottom."""
        if not winner.hand:
            return None
        return min(winner.hand, key=lambda c: self._card_value(c, winner, game))

    def choose_blue_action(self, winner: Player, opponents: List[Player],
                           game: GameState) -> Tuple[Player, Card]:
        """Blue talent: choose target and card to give."""
        target = max(opponents, key=lambda p: p.vp)
        give = min(winner.hand, key=lambda c: self._card_value(c, winner, game))
        self.last_reasoning.append(
            f"  Blue: target P{target.id}(VP={target.vp}), give {give}")
        return target, give

    def choose_purple_action(self, winner: Player,
                             game: GameState) -> Tuple[Optional[Card], Optional[Card]]:
        """Purple talent: which card to bank, which to discard after draw."""
        if not winner.hand:
            return None, None
        # Bank any card (they're all worth 1 VP in stash)
        # Prefer banking a card we're unlikely to win tricks with
        # But actually, just bank a mid-range card — keep best for tricks
        sorted_hand = sorted(winner.hand,
                             key=lambda c: self._card_value(c, winner, game))
        # Bank the least valuable for tricks (it's worth 1 VP in stash regardless)
        bank = sorted_hand[0]
        # Discard will be chosen after drawing
        discard = None  # game_state will pick worst
        self.last_reasoning.append(f"  Purple: bank {bank}")
        return bank, discard

    # ── Evaluation Helpers ─────────────────────────────────────────

    def _card_value(self, card: Card, player: Player,
                    game: GameState) -> float:
        """How valuable is this card for winning future tricks?"""
        value = 0.0

        # Trump cards are premium
        if card.faction == game.trump_faction:
            value += 4.0 + card.rank * 0.4
        # Elite cards get tiebreak
        elif card.faction == game.elite_faction:
            value += 1.5 + card.rank * 0.3
        # Wobbly cards: LOW rank is strong (when led)
        elif card.faction == game.wobbly_faction:
            value += (10 - card.rank) * 0.3 + 1.0  # invert: rank 0 = 4.0, rank 10 = 1.0
        else:
            # Standard: high rank preferred
            value += card.rank * 0.3

        # Faction depth
        depth = len(player.cards_of_faction(card.faction))
        value += depth * 0.15

        # Intern draw bonus
        if card.is_intern:
            value += 0.8

        return value

    def _talent_value(self, faction: str, player: Player,
                      game: GameState) -> float:
        """How valuable is this faction's talent right now?"""
        if faction == "RED":
            return 1.5  # disruption
        elif faction == "ORANGE":
            return 2.0 if not game.vault.empty else 0
        elif faction == "YELLOW":
            return 1.0 if not game.vault.empty else 0
        elif faction == "GREEN":
            return 2.5 if game.vault.size >= 2 else 0  # net +1 card
        elif faction == "BLUE":
            leader = max(game.players, key=lambda p: p.vp)
            if leader.id != player.id:
                return 2.0
            return 0.5
        elif faction == "PURPLE":
            return 3.0  # free VP is always great
        return 0

    def _noisy_score(self, base_score: float) -> float:
        noise_range = 4.0 * (1.0 - self.skill)
        if noise_range == 0:
            return base_score
        return base_score + self.rng.uniform(-noise_range, noise_range)
