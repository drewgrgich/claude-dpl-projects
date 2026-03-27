"""
Heuristic AI player for Get Stuffed.

Three tunable axes:
  - Skill (0.0-1.0): How many mistakes the AI makes.
  - Style (categorical): Strategic approach (balanced, aggressive_shed, disruptive, hoarder).
  - Aggression (0.0-1.0): Willingness to use powers offensively.

The AI scores all legal plays and picks the best one. It also makes
decisions for faction powers (who to target, whether to swap, etc.).
"""

import random
from typing import List, Optional, Tuple, Dict
from cards import Card


# ─── Style Profiles ──────────────────────────────────

STYLE_PROFILES = {
    "balanced": {
        "description": "Well-rounded default play.",
        "prefer_powers": 1.0,        # How much to favor high-rank cards
        "wild_conservation": 0.5,     # Reluctance to play wilds (0=play freely, 1=hoard)
        "hot_potato_target": "leader",  # who to target: "leader", "next", "random"
        "dib_it_target": "leader",
        "retinker_preference": "extra_turn",  # "extra_turn" or "reverse" or "smart"
        "vanish_threshold": 3,        # Min hand size difference to trigger VANISH swap
        "foresaw_prefer_playable": True,  # Take a card that's immediately playable?
        "mercy_always_take": True,    # Always take mercy saves?
    },
    "aggressive_shed": {
        "description": "Play cards fast. Prioritize shedding over powers.",
        "prefer_powers": 0.3,
        "wild_conservation": 0.2,
        "hot_potato_target": "leader",
        "dib_it_target": "leader",
        "retinker_preference": "extra_turn",
        "vanish_threshold": 1,
        "foresaw_prefer_playable": True,
        "mercy_always_take": True,
    },
    "disruptive": {
        "description": "Maximize pain for opponents. Use powers aggressively.",
        "prefer_powers": 2.0,
        "wild_conservation": 0.7,
        "hot_potato_target": "leader",
        "dib_it_target": "leader",
        "retinker_preference": "smart",
        "vanish_threshold": 2,
        "foresaw_prefer_playable": False,  # Take best card even if not playable now
        "mercy_always_take": True,
    },
    "hoarder": {
        "description": "Hold onto wilds and high cards. Play low cards first.",
        "prefer_powers": -0.5,  # Actually prefer low-rank cards
        "wild_conservation": 0.9,
        "hot_potato_target": "next",
        "dib_it_target": "next",
        "retinker_preference": "reverse",
        "vanish_threshold": 5,
        "foresaw_prefer_playable": True,
        "mercy_always_take": True,
    },
}


class HeuristicAI:
    """A heuristic AI that makes reasonable decisions for Get Stuffed."""

    def __init__(self, player_id: int = 0, skill: float = 1.0,
                 style: str = "balanced", aggression: float = 0.5,
                 rng_seed: int = 42):
        self.player_id = player_id
        self.skill = max(0.0, min(1.0, skill))
        self.style_name = style
        self.style = STYLE_PROFILES.get(style, STYLE_PROFILES["balanced"])
        self.aggression = max(0.0, min(1.0, aggression))
        self.rng = random.Random(rng_seed)

    # ─── Mistake Modeling ────────────────────────────

    def _noisy_score(self, base_score: float) -> float:
        """Add noise to valuations. Lower skill = more noise."""
        noise_range = 4.0 * (1.0 - self.skill)
        if noise_range == 0:
            return base_score
        return base_score + self.rng.uniform(-noise_range, noise_range)

    def _forget_wild(self) -> bool:
        """Beginners sometimes forget they can play wilds."""
        rate = 0.25 * (1.0 - self.skill)
        return self.rng.random() < rate

    def _misjudge_target(self) -> bool:
        """Beginners sometimes target the wrong player with powers."""
        rate = 0.3 * (1.0 - self.skill)
        return self.rng.random() < rate

    # ─── Card Selection ──────────────────────────────

    def choose_card_to_play(self, player, game_state) -> Tuple[Optional[Card], Optional[str]]:
        """Pick the best card to play from hand.

        Returns (card, declared_faction) or (None, None) if nothing playable.
        """
        pit_top = game_state.pit_top
        declared = game_state.declared_faction
        playable = player.get_playable(pit_top, declared)

        # Skill: sometimes forget wilds are playable
        if self._forget_wild():
            playable = [c for c in playable if not c.is_wild]

        if not playable:
            return None, None

        # Score each playable card
        scored = []
        for card in playable:
            score = self._score_card(card, player, game_state)
            scored.append((card, score))

        # Pick the highest-scored card
        scored.sort(key=lambda x: x[1], reverse=True)
        best_card = scored[0][0]

        # Determine declaration if wild
        decl = None
        if best_card.is_wild:
            decl = self._choose_faction_declaration(player, game_state)

        return best_card, decl

    def _score_card(self, card: Card, player, game_state) -> float:
        """Score a card for play priority."""
        score = 0.0

        # Base: prefer playing cards (any card shed is good)
        score += 10.0

        # Power bonus/penalty based on style
        if card.has_power:
            score += self.style["prefer_powers"] * 2.0

        # Wild conservation: penalize playing wilds based on style
        if card.is_wild:
            score -= self.style["wild_conservation"] * 5.0
            # But if it's our only option, still play it
            non_wild_playable = [c for c in player.get_playable(game_state.pit_top,
                                                                 game_state.declared_faction)
                                 if not c.is_wild]
            if not non_wild_playable:
                score += 8.0  # Override conservation if it's our only play

        # Prefer cards that leave us with more options
        # (favor the faction we have fewer of — preserve flexibility)
        faction_count = sum(1 for c in player.hand if c.faction == card.faction and c != card)
        if not card.is_wild:
            # Playing a card from a large faction group is safer
            score += faction_count * 0.5

        # Low rank cards are "wasted" plays (no power) — prefer them when shedding is priority
        if not card.has_power:
            score += (1.0 - self.style["prefer_powers"]) * 1.0

        # Hot Potato special: if we have 1 card left and it's Red 6+, DON'T play it
        # (power won't trigger, but that's actually fine for winning)
        # Actually wait — if it's our last card, we win regardless. Score highly.
        if player.hand_size == 1:
            score += 100.0  # WIN!

        # If second-to-last card and it's Red 6+, power won't trigger (hand will be empty after)
        # Actually that's wrong: Hot Potato doesn't trigger if hand is empty AFTER playing.
        # So playing Red 6+ as second-to-last card means we play it (1 card remains), then
        # Hot Potato fires and we give away our last card... but then we have 0 cards!
        # Wait, the rules say "If you had only 1 card left in your hand when you played
        # your Super-Dupe, Hot Potato does not trigger"
        # So if we have 2 cards, play Red 6+ -> 1 card left -> Hot Potato fires -> give 1 card
        # -> 0 cards. But the rule says you can only win by playing to pit, not handing off.
        # So that would NOT be a win. Penalize this!
        if player.hand_size == 2 and card.faction == "RED" and card.has_power:
            score -= 15.0  # Don't play this — Hot Potato will force us to give away our last card

        return self._noisy_score(score)

    def _choose_faction_declaration(self, player, game_state) -> str:
        """Choose what faction to declare when playing a wild."""
        # Count factions in remaining hand (excluding wilds)
        faction_counts: Dict[str, int] = {}
        for c in player.hand:
            if not c.is_wild:
                faction_counts[c.faction] = faction_counts.get(c.faction, 0) + 1

        if not faction_counts:
            # All wilds or empty hand — pick randomly
            factions = game_state.rules["deck"]["factions"]
            non_wild = [f for f in factions if f != "PURPLE"]
            return self.rng.choice(non_wild)

        # Declare our most common faction
        return max(faction_counts, key=faction_counts.get)

    # ─── Power Decisions ─────────────────────────────

    def get_power_decisions(self, player, game_state) -> dict:
        """Return a dict of decision callbacks for faction powers."""
        return {
            "hot_potato": lambda p, g: self._decide_hot_potato(p, g),
            "dib_it": lambda p, g: self._decide_dib_it(p, g),
            "retinker": lambda p, g: self._decide_retinker(p, g),
            "vanish": lambda p, g: self._decide_vanish(p, g),
            "foresaw": lambda p, peeked, g: self._decide_foresaw(p, peeked, g),
            "foresaw_play": lambda p, playable, g: self._decide_foresaw_play(p, playable, g),
            "sleight_target": lambda p, g: self._decide_sleight_target(p, g),
            "declare_faction": lambda p, g: self._choose_faction_declaration(p, g),
        }

    def _decide_hot_potato(self, player, game_state) -> Tuple[int, Card]:
        """Choose target and card for Hot Potato."""
        opponents = [p for p in game_state.players if p.id != player.id]

        # Choose target
        if self._misjudge_target():
            target = self.rng.choice(opponents)
        elif self.style["hot_potato_target"] == "leader":
            target = min(opponents, key=lambda p: p.hand_size)
        elif self.style["hot_potato_target"] == "next":
            next_idx = game_state.get_next_player_idx()
            target = game_state.players[next_idx]
            if target.id == player.id:
                target = self.rng.choice(opponents)
        else:
            target = self.rng.choice(opponents)

        # Choose card to give — give our worst card (highest rank = biggest penalty if they scavenge)
        # But actually, give them a card that's hard for them to play
        # Simplification: give highest rank non-wild card
        non_wilds = [c for c in player.hand if not c.is_wild]
        if non_wilds:
            card_to_give = max(non_wilds, key=lambda c: c.rank)
        else:
            card_to_give = player.hand[0]

        return target.id, card_to_give

    def _decide_dib_it(self, player, game_state) -> int:
        """Choose target for Dib It (forced scavenge)."""
        opponents = [p for p in game_state.players if p.id != player.id]

        if self._misjudge_target():
            return self.rng.choice(opponents).id

        if self.style["dib_it_target"] == "leader":
            return min(opponents, key=lambda p: p.hand_size).id
        elif self.style["dib_it_target"] == "next":
            next_idx = game_state.get_next_player_idx()
            target = game_state.players[next_idx]
            if target.id == player.id:
                return self.rng.choice(opponents).id
            return target.id
        else:
            return self.rng.choice(opponents).id

    def _decide_retinker(self, player, game_state) -> str:
        """Choose Re-Tinker effect: 'reverse' or 'extra_turn'."""
        pref = self.style["retinker_preference"]

        if pref == "smart":
            # Smart: reverse if the next player is close to winning, extra turn otherwise
            next_idx = game_state.get_next_player_idx()
            next_player = game_state.players[next_idx]
            if next_player.hand_size <= 2:
                return "reverse"
            # Take extra turn if we have good plays available
            playable = player.get_playable(game_state.pit_top, game_state.declared_faction)
            if len(playable) >= 2:
                return "extra_turn"
            return "extra_turn"

        return pref

    def _decide_vanish(self, player, game_state) -> Tuple[bool, Optional[int]]:
        """Decide whether to VANISH (swap entire hand) and with whom."""
        opponents = [p for p in game_state.players if p.id != player.id]
        best_target = min(opponents, key=lambda p: p.hand_size)

        hand_diff = player.hand_size - best_target.hand_size
        threshold = self.style["vanish_threshold"]

        # Swap if we have significantly more cards
        if hand_diff >= threshold:
            return True, best_target.id
        # Aggressive players swap more readily
        elif hand_diff > 0 and self.aggression > 0.7:
            return True, best_target.id
        return False, None

    def _decide_foresaw(self, player, peeked: List[Card],
                        game_state) -> Tuple[int, Optional[List[int]]]:
        """Choose which card to take from foresaw peek, and reorder the rest."""
        pit_top = game_state.pit_top
        declared = game_state.declared_faction

        # Score each peeked card
        best_idx = 0
        best_score = -999

        for i, card in enumerate(peeked):
            score = 0
            # Strongly prefer cards that match current pit (can play immediately in foresaw)
            if card.matches_pit(pit_top, declared):
                score += 10
                if card.has_power:
                    score += 3
            # Otherwise value cards we have many of (easier to play later)
            faction_count = sum(1 for c in player.hand if c.faction == card.faction)
            score += faction_count
            # Wilds are always useful
            if card.is_wild:
                score += 5

            score = self._noisy_score(score)
            if score > best_score:
                best_score = score
                best_idx = i

        # Reorder: put good cards on top for opponents? Or bad cards?
        # Simple: just leave them in original order
        remaining_indices = [i for i in range(len(peeked)) if i != best_idx]
        return best_idx, None  # None = default ordering

    def _decide_foresaw_play(self, player, playable: List[Card],
                             game_state) -> Card:
        """Choose which card to play as the foresaw follow-up."""
        # Prefer shedding high-rank cards (trigger more powers)
        scored = []
        for card in playable:
            score = self._score_card(card, player, game_state)
            scored.append((card, score))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[0][0]

    def _decide_sleight_target(self, player, game_state) -> int:
        """Choose opponent for Sleight of Paw."""
        opponents = [p for p in game_state.players if p.id != player.id and p.hand_size > 0]
        if not opponents:
            return game_state.players[(player.id + 1) % game_state.num_players].id

        if self._misjudge_target():
            return self.rng.choice(opponents).id

        # Target player with fewest cards (we might get a good card, they get our bad one)
        return min(opponents, key=lambda p: p.hand_size).id

    # ─── P0 Bonus Card Discard ────────────────────────

    def choose_p0_discard(self, player, game_state) -> 'Card':
        """Choose which card to discard after seeing the pit (P0 bonus rule)."""
        pit_top = game_state.pit_top
        declared = game_state.declared_faction

        # Score each card — discard the one we'd least want to keep
        scored = []
        for card in player.hand:
            score = 0
            # Playable cards are valuable — don't discard them
            if card.matches_pit(pit_top, declared):
                score += 10
            # Wilds are always valuable
            if card.is_wild:
                score += 8
            # Cards matching factions we have multiples of are more useful
            faction_count = sum(1 for c in player.hand if c.faction == card.faction and c != card)
            score += faction_count * 1.5
            # Low rank cards are easier to play (lower scavenge penalty if opponent flips)
            score += (10 - card.rank) * 0.3
            scored.append((card, self._noisy_score(score)))

        # Discard the lowest-scored card
        scored.sort(key=lambda x: x[1])
        return scored[0][0]

    # ─── Mercy Clause Decision ───────────────────────

    def decide_mercy(self, card: Card, player, game_state) -> bool:
        """During penalty draw, should we play a matching card to stop?"""
        if self.style["mercy_always_take"]:
            return True
        # Some edge case: if the card is really valuable to keep, maybe don't play it
        # For now, always take the mercy save (stopping penalty is almost always better)
        return True

    # ─── Sugar Crash Free Dump ───────────────────────

    def choose_sugar_crash_dump(self, player, game_state) -> Card:
        """Choose a card to dump for free during Sugar Crash."""
        # Dump our worst card: highest rank non-wild first (saves wilds for matching)
        non_wilds = [c for c in player.hand if not c.is_wild]
        if non_wilds:
            # Dump highest rank (these are hardest to play safely)
            return max(non_wilds, key=lambda c: c.rank)
        # All wilds? Dump any one
        return player.hand[0] if player.hand else None
