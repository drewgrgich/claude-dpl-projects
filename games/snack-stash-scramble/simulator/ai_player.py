"""Heuristic AI player for Snack Stash Scramble.

Three tunable axes:
  - skill (0.0-1.0): mistake frequency
  - style (rush/balanced/hoarder/aggressive): strategic preferences
  - aggression (0.0-1.0): spending/risk willingness
"""

from typing import List, Dict, Tuple, Optional, Any
import random

from cards import Card, BankedSet
from game_state import GameState, Player


STYLE_PROFILES = {
    "balanced": {
        "description": "Well-rounded default play.",
        "bank_threshold": 0,       # Bank any valid set
        "prefer_big_sets": 0.5,    # Slight preference for larger sets
        "wild_discard_aversion": 5, # Avoid discarding wilds (might need them)
        "extend_opponent_bonus": 0, # No preference for poisoned peanut
        "protect_priority": 1.0,   # RED power: protect valuable sets
        "green_value": 1.0,        # GREEN power: peek value
    },
    "rush": {
        "description": "Bank fast, empty hand, minimize penalty risk.",
        "bank_threshold": -5,      # Bank anything, even low-value sets
        "prefer_big_sets": -1.0,   # Prefer small sets (faster to bank)
        "wild_discard_aversion": 2, # More willing to discard wilds
        "extend_opponent_bonus": -2, # Avoid extending opponents
        "protect_priority": 0.5,
        "green_value": 0.5,
    },
    "hoarder": {
        "description": "Hold cards, build bigger sets, maximize banked value.",
        "bank_threshold": 5,       # Only bank high-value sets
        "prefer_big_sets": 3.0,    # Strongly prefer larger sets
        "wild_discard_aversion": 8, # Never discard wilds
        "extend_opponent_bonus": -3, # Avoid extending opponents
        "protect_priority": 2.0,
        "green_value": 2.0,
    },
    "aggressive": {
        "description": "Use powers offensively. Poisoned peanuts, theft.",
        "bank_threshold": 0,
        "prefer_big_sets": 0.5,
        "wild_discard_aversion": 4,
        "extend_opponent_bonus": 5, # Love the poisoned peanut
        "protect_priority": 1.5,
        "green_value": 1.0,
    },
}


class HeuristicAI:
    """A heuristic AI that plays Snack Stash Scramble with tunable behavior."""

    def __init__(self, skill: float = 1.0, style: str = "balanced",
                 aggression: float = 0.5, rng_seed: int = None):
        self.skill = max(0.0, min(1.0, skill))
        self.style = style
        self.aggression = max(0.0, min(1.0, aggression))
        self.profile = STYLE_PROFILES.get(style, STYLE_PROFILES["balanced"])
        self.rng = random.Random(rng_seed)
        self.reasoning: List[str] = []  # For narration

    def _clear_reasoning(self):
        self.reasoning = []

    def _reason(self, msg: str):
        self.reasoning.append(msg)

    # ----------------------------------------------------------------
    # SKILL-BASED MISTAKES
    # ----------------------------------------------------------------

    def _maybe_miss_opportunity(self) -> bool:
        miss_rate = 0.35 * (1.0 - self.skill)
        return self.rng.random() < miss_rate

    def _noisy_score(self, base: float) -> float:
        noise_range = 4.0 * (1.0 - self.skill)
        if noise_range == 0:
            return base
        return base + self.rng.uniform(-noise_range, noise_range)

    def _forget_wilds(self) -> bool:
        rate = 0.25 * (1.0 - self.skill)
        return self.rng.random() < rate

    # ----------------------------------------------------------------
    # DRAW PHASE DECISION
    # ----------------------------------------------------------------

    def choose_draw(self, player: Player, game: GameState) -> str:
        """Decide draw action: snack_floor, draw_feeder, or draw_litter_box."""
        self._clear_reasoning()
        options = game.get_draw_options(player)

        if "snack_floor" in options:
            self._reason(f"Hand size {player.hand_size} <= {game.config['draw']['snack_floor_threshold']}: "
                         f"Snack Floor triggered, draw 3")
            return "snack_floor"

        if "draw_litter_box" in options and game.litter_box:
            top_card = game.litter_box[-1]
            lb_score = self._evaluate_litter_box_draw(player, top_card, game)
            feeder_score = self._evaluate_feeder_draw(player, game)
            self._reason(f"Litter box top: {top_card} (score: {lb_score:.1f}) "
                         f"vs Feeder blind (score: {feeder_score:.1f})")

            if lb_score > feeder_score:
                self._reason(f"Taking {top_card} from litter box")
                return "draw_litter_box"

        self._reason("Drawing from feeder")
        return "draw_feeder"

    def _evaluate_litter_box_draw(self, player: Player, card: Card,
                                   game: GameState) -> float:
        """Score the value of taking the litter box card."""
        score = 0.0

        # Does it help complete a set?
        test_hand = list(player.hand) + [card]
        current_sets = game.find_all_valid_sets(player.hand)
        new_sets = game.find_all_valid_sets(test_hand)
        if len(new_sets) > len(current_sets):
            score += 8.0
            self._reason(f"  {card} enables a new set!")

        # Is it a wild? Useful but risky
        if card.is_wild:
            score += 3.0 - self.aggression * 2  # Less attractive if aggressive (risky)

        # Does it have high face value (good for banking)?
        score += card.face_value * 0.3

        # Does it match cards we already have?
        matching_faction = sum(1 for c in player.hand
                               if c.faction == card.faction and not c.is_wild)
        matching_rank = sum(1 for c in player.hand
                            if c.rank == card.rank and not c.is_wild)
        score += matching_faction * 0.8
        score += matching_rank * 1.5

        return self._noisy_score(score)

    def _evaluate_feeder_draw(self, player: Player, game: GameState) -> float:
        """Baseline score for a blind feeder draw."""
        # Base value of unknown card — average expected value
        return self._noisy_score(3.0)

    # ----------------------------------------------------------------
    # BANK PHASE DECISIONS
    # ----------------------------------------------------------------

    def choose_banks(self, player: Player, game: GameState) -> List[Dict[str, Any]]:
        """Decide which sets to bank. Returns list of bank actions."""
        self._clear_reasoning()
        actions = []

        if self._maybe_miss_opportunity():
            self._reason("*Missed opportunity — didn't notice bankable sets*")
            return actions

        available_sets = game.find_all_valid_sets(player.hand)
        if not available_sets:
            self._reason("No valid sets to bank")
            return actions

        self._reason(f"Found {len(available_sets)} possible set(s)")

        # Score each set
        scored = []
        for set_type, cards in available_sets:
            score = self._score_set(set_type, cards, player, game)
            scored.append((score, set_type, cards))
            self._reason(f"  {set_type}: {cards} — value {sum(c.face_value for c in cards)}, "
                         f"score {score:.1f}")

        scored.sort(reverse=True, key=lambda x: x[0])

        # Bank sets greedily (no card conflicts)
        used_cards = set()
        for score, set_type, cards in scored:
            threshold = self.profile["bank_threshold"]
            if score < threshold:
                self._reason(f"  Skipping {set_type} {cards} — score {score:.1f} below "
                             f"threshold {threshold}")
                continue

            # Check no card overlap
            card_ids = [id(c) for c in cards]
            if any(cid in used_cards for cid in card_ids):
                continue

            # Determine faction trigger
            available_factions = game.get_available_faction_triggers(cards)
            faction = self._choose_faction_trigger(available_factions, player, game)

            actions.append({
                "set_type": set_type,
                "cards": cards,
                "faction_trigger": faction,
            })
            for cid in card_ids:
                used_cards.add(cid)
            self._reason(f"  Banking {set_type} {cards}, triggering {faction}")

        return actions

    def _score_set(self, set_type: str, cards: List[Card],
                   player: Player, game: GameState) -> float:
        """Score a potential set for banking priority."""
        value = sum(c.face_value for c in cards)
        size = len(cards)

        # Base score: banked value + avoided penalty
        penalty_avoided = sum(c.hand_penalty for c in cards)
        score = value + penalty_avoided * 0.5

        # Style: prefer big or small sets
        score += size * self.profile["prefer_big_sets"]

        # Faction power value
        factions = game.get_available_faction_triggers(cards)
        best_power = max(
            (self._faction_power_value(f, player, game) for f in factions),
            default=0
        )
        score += best_power

        # Late-game urgency: banking is more valuable as cards run low
        cards_remaining = game.feeder.size
        total_cards = 66
        game_progress = 1.0 - (cards_remaining / total_cards)
        score += game_progress * 5.0  # More urgent to bank later

        # Wild cards in the set are risky to hold
        wilds_in_set = sum(1 for c in cards if c.is_wild)
        score += wilds_in_set * 3.0  # Bonus for getting wilds banked safely

        return self._noisy_score(score)

    def _faction_power_value(self, faction: str, player: Player,
                              game: GameState) -> float:
        """Estimate value of triggering a faction power."""
        poison_active = game.config.get("scoring", {}).get("poisoned_peanut_negative", False)

        if faction == "RED":
            # Value of protecting a set — much higher when Poisoned Peanut is real
            unprotected = [s for s in player.banked_sets if not s.protected]
            if unprotected:
                base = self.profile["protect_priority"] * 2.0
                if poison_active:
                    # Protect your most valuable set from enemy peanuts
                    best_val = max(s.total_value for s in unprotected)
                    base += best_val * 0.3  # Scale with what we're protecting
                return base
            return 0.0

        elif faction == "ORANGE":
            # Free card from litter box
            if game.litter_box:
                top = game.litter_box[-1]
                return 2.0 + (1.0 if not top.is_wild else 0.5)
            return 0.0

        elif faction == "YELLOW":
            # Extend a set (or poisoned peanut)
            extend_targets = self._find_extend_targets(player, game)
            if not extend_targets:
                return 0.5
            if poison_active:
                # Check if we have good peanut ammo (high-value cards or wilds)
                opponent_targets = [t for t in extend_targets if t[0] != player.id]
                if opponent_targets and player.hand:
                    best_ammo = max(c.face_value if not c.is_wild else 10
                                    for c in player.hand)
                    # High value = devastating peanut
                    return 3.0 + best_ammo * 0.5 + self.profile["extend_opponent_bonus"]
            return 2.0 + self.profile["extend_opponent_bonus"]

        elif faction == "GREEN":
            return self.profile["green_value"] * 2.0

        elif faction == "BLUE":
            # Card swap with opponent
            opponents_with_cards = [p for p in game.players
                                    if p.id != player.id and p.hand_size > 0]
            if opponents_with_cards:
                return 2.5
            return 0.5

        elif faction == "PURPLE":
            # Extend the game — more valuable if we're ahead
            if player.banked_score > max(
                    (p.banked_score for p in game.players if p.id != player.id), default=0):
                return 1.0
            return 2.5  # More valuable if behind (extends game)

        return 0.0

    def _choose_faction_trigger(self, factions: List[str], player: Player,
                                 game: GameState) -> Optional[str]:
        """Choose which faction power to trigger."""
        if not factions:
            return None

        scored = [(self._faction_power_value(f, player, game), f) for f in factions]
        scored.sort(reverse=True)
        return scored[0][1]

    # ----------------------------------------------------------------
    # YELLOW POWER — Extend decision
    # ----------------------------------------------------------------

    def choose_yellow_extend(self, player: Player, game: GameState) -> Optional[Dict]:
        """Choose a card and target for Yellow power (extend any set)."""
        targets = self._find_extend_targets(player, game)
        if not targets or not player.hand:
            return None

        poison_active = game.config.get("scoring", {}).get("poisoned_peanut_negative", False)
        best_score = -999
        best_action = None

        for card in player.hand:
            for target_pid, target_set, set_idx in targets:
                if not target_set.can_extend_with(card):
                    continue

                score = 0
                if target_pid == player.id:
                    # Extending own set: value gain + penalty avoidance
                    score = card.face_value + card.hand_penalty * 0.5
                elif poison_active:
                    # OPTION A: Sideways cards subtract face value from opponent
                    # Attacker benefit: avoid own hand penalty
                    # Defender damage: -face_value to their banked score
                    # Total swing = hand_penalty_avoided + face_value_damage
                    damage = card.face_value
                    if card.is_wild:
                        damage = card.rank  # Rank 10 wild = 10 damage, Rank 0 = 0
                    penalty_avoided = card.hand_penalty
                    score = damage + penalty_avoided * 0.5 + self.profile["extend_opponent_bonus"]
                    if card.is_wild and card.rank == 10:
                        score += 5.0  # Rank 10 wild is the ultimate peanut
                        self._reason(f"  DEVASTATING Peanut! Rank 10 wild on P{target_pid}: -10 to them!")
                    elif damage >= 7:
                        score += 2.0
                        self._reason(f"  Strong Peanut! {card} on P{target_pid}: -{damage} to them!")
                    elif damage >= 4:
                        self._reason(f"  Peanut: {card} on P{target_pid}: -{damage}")
                    else:
                        score -= 1.0  # Low damage cards aren't great peanuts
                else:
                    # Old behavior: peanuts don't actually hurt
                    if card.is_wild:
                        score = self.profile["extend_opponent_bonus"] + 5.0
                    elif card.rank <= 2:
                        score = self.profile["extend_opponent_bonus"] + 1.0
                    else:
                        score = self.profile["extend_opponent_bonus"] - card.face_value

                score = self._noisy_score(score)
                if score > best_score:
                    best_score = score
                    best_action = {
                        "card": card,
                        "target_player_id": target_pid,
                        "target_set_idx": set_idx,
                    }

        if best_action and best_score > 0:
            return best_action
        return None

    def _find_extend_targets(self, player: Player,
                              game: GameState) -> List[Tuple[int, BankedSet, int]]:
        """Find all (player_id, banked_set, set_idx) that could be extended."""
        targets = []
        for p in game.players:
            for idx, bset in enumerate(p.banked_sets):
                if bset.protected and p.id != player.id:
                    continue
                targets.append((p.id, bset, idx))
        return targets

    # ----------------------------------------------------------------
    # GREEN POWER — Reorder decision
    # ----------------------------------------------------------------

    def choose_green_reorder(self, peeked: List[Card], player: Player,
                              game: GameState) -> List[int]:
        """Choose ordering for peeked cards (GREEN power). Return index list."""
        # Put cards we want on top (best first)
        scored = []
        for i, card in enumerate(peeked):
            score = self._evaluate_litter_box_draw(player, card, game)
            scored.append((score, i))
        scored.sort(reverse=True)
        return [idx for _, idx in scored]

    # ----------------------------------------------------------------
    # BLUE POWER — Swap decision
    # ----------------------------------------------------------------

    def choose_blue_swap(self, player: Player, game: GameState) -> Dict:
        """Choose opponent and card to give for BLUE power."""
        opponents = [p for p in game.players
                     if p.id != player.id and p.hand_size > 0]
        if not opponents:
            return {}

        # Target the opponent with the most cards (highest chance of good steal)
        target = max(opponents, key=lambda p: p.hand_size)

        # Give away our worst card (highest penalty risk, lowest value)
        if player.hand:
            give_card = self._worst_card(player)
            return {"opponent_id": target.id, "give_card": give_card}
        return {"opponent_id": target.id}

    # ----------------------------------------------------------------
    # PURPLE POWER — Tuck decision
    # ----------------------------------------------------------------

    def choose_purple_tuck(self, game: GameState) -> int:
        """Choose which litter box card to tuck under feeder."""
        if not game.litter_box:
            return 0
        # Tuck the card most useful to opponents (hardest to evaluate;
        # heuristic: tuck highest rank cards since they're valuable)
        scores = [(c.face_value, i) for i, c in enumerate(game.litter_box)]
        scores.sort(reverse=True)
        return scores[0][1]

    # ----------------------------------------------------------------
    # DISCARD PHASE
    # ----------------------------------------------------------------

    def choose_discard(self, player: Player, game: GameState) -> Card:
        """Choose which card to discard."""
        if not player.hand:
            return None

        self._reason(f"Choosing discard from hand of {player.hand_size}")

        # Score each card (lower = more disposable)
        scored = []
        for card in player.hand:
            score = self._card_keep_value(card, player, game)
            scored.append((score, card))

        scored.sort()
        worst = scored[0][1]
        self._reason(f"  Discarding {worst} (keep value: {scored[0][0]:.1f})")
        return worst

    def _card_keep_value(self, card: Card, player: Player,
                          game: GameState) -> float:
        """How valuable is it to keep this card in hand?"""
        score = 0.0

        # Penalty risk: higher penalty = less want to keep
        score -= card.hand_penalty * (0.3 + game_progress(game) * 0.7)

        # Set potential: does this card contribute to completing a set?
        hand_without = [c for c in player.hand if c is not card]
        sets_without = game.find_all_valid_sets(hand_without)
        sets_with = game.find_all_valid_sets(player.hand)
        if len(sets_with) > len(sets_without):
            score += 10.0  # Critical for a set

        # Wild card versatility
        if card.is_wild:
            if not self._forget_wilds():
                score += self.profile["wild_discard_aversion"]

        # Matching cards in hand (run/group potential)
        matching_rank = sum(1 for c in player.hand
                            if c.rank == card.rank and c is not card and not c.is_wild)
        matching_faction = sum(1 for c in player.hand
                                if c.faction == card.faction and c is not card
                                and not c.is_wild)
        score += matching_rank * 2.0
        score += matching_faction * 1.0

        # Face value (higher value = better for banking)
        score += card.face_value * 0.2

        return self._noisy_score(score)

    def _worst_card(self, player: Player) -> Card:
        """Find the worst card in hand (least valuable to keep)."""
        if not player.hand:
            return None
        return min(player.hand,
                   key=lambda c: c.face_value - c.hand_penalty * 2)

    # ----------------------------------------------------------------
    # EXTEND PHASE (non-Yellow, voluntary extensions)
    # ----------------------------------------------------------------

    def choose_extensions(self, player: Player, game: GameState) -> List[Dict]:
        """Choose cards to extend existing banked sets (not from Yellow power)."""
        extensions = []
        hand_copy = list(player.hand)

        for card in hand_copy:
            extendable = game.find_extendable_sets(player, card)
            for target_pid, bset in extendable:
                # Only extend our own sets voluntarily (save poisoned peanut for Yellow)
                if target_pid != player.id:
                    continue
                if not bset.can_extend_with(card):
                    continue

                # Worth extending if card penalty risk > value gained
                penalty_risk = card.hand_penalty * game_progress(game)
                value_gain = card.face_value
                if penalty_risk > 2 or value_gain >= 5:
                    set_idx = player.banked_sets.index(bset)
                    extensions.append({
                        "card": card,
                        "target_player_id": player.id,
                        "target_set_idx": set_idx,
                    })
                    break  # Only extend this card once

        return extensions


def game_progress(game: GameState) -> float:
    """How far through the game are we (0.0 = start, 1.0 = near end)."""
    total_cards = 66
    in_feeder = game.feeder.size
    progress = 1.0 - (in_feeder / total_cards)
    if game.halftime_done:
        progress = max(progress, 0.5)
    return min(1.0, progress)
