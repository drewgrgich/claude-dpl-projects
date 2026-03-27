"""
Zone Scramble — Heuristic AI with tunable skill, style, and aggression.

The AI scores every legal action and picks the highest.  Style shifts weights,
skill adds noise / mistakes, aggression tunes spending willingness.
"""

from __future__ import annotations
from typing import List, Tuple, Optional, Dict
import random

from cards import Card
from game_state import GameState, Arena, Player


# ---------------------------------------------------------------------------
# Style profiles
# ---------------------------------------------------------------------------

STYLE_PROFILES = {
    "balanced": {
        "description": "Well-rounded default play.",
        "arena_rank_weight": 1.0,      # how much we value high-rank plays
        "chameleon_eagerness": 0.5,     # willingness to spend chameleons
        "fumble_threshold": 0.3,        # how bad hand must be to fumble
        "signature_eagerness": 0.7,     # how eagerly to use signature moves
        "arena_spread_bonus": 1.0,      # bonus for playing in arenas with few of our monsters
        "deny_bonus": 0.5,             # bonus for playing where opponent is strong
    },
    "rush": {
        "description": "Play fast, try to trigger Crowd Roars on your terms.",
        "arena_rank_weight": 0.6,
        "chameleon_eagerness": 0.8,
        "fumble_threshold": 0.2,
        "signature_eagerness": 0.9,
        "arena_spread_bonus": 0.3,
        "deny_bonus": 0.3,
    },
    "control": {
        "description": "Deny opponent's arenas and play for value.",
        "arena_rank_weight": 1.3,
        "chameleon_eagerness": 0.4,
        "fumble_threshold": 0.4,
        "signature_eagerness": 0.6,
        "arena_spread_bonus": 0.5,
        "deny_bonus": 1.5,
    },
    "tempo": {
        "description": "Play for momentum bonuses by winning multiple arenas.",
        "arena_rank_weight": 0.9,
        "chameleon_eagerness": 0.6,
        "fumble_threshold": 0.25,
        "signature_eagerness": 0.8,
        "arena_spread_bonus": 1.5,
        "deny_bonus": 0.4,
    },
}


class HeuristicAI:
    """
    AI player for Zone Scramble.

    Args:
        skill: 0.0 (beginner) to 1.0 (expert).  Controls mistake rate.
        style: one of STYLE_PROFILES keys.
        aggression: 0.0 (conservative) to 1.0 (aggressive).
        rng_seed: seed for this AI's random decisions.
    """

    def __init__(self, skill: float = 1.0, style: str = "balanced",
                 aggression: float = 0.5, rng_seed: int = 42):
        self.skill = max(0.0, min(1.0, skill))
        self.style_name = style
        self.style = STYLE_PROFILES.get(style, STYLE_PROFILES["balanced"])
        self.aggression = max(0.0, min(1.0, aggression))
        self.rng = random.Random(rng_seed)

        # Track first-monster for Yellow Fast Start
        self._first_monster_arena: Optional[str] = None

    # -----------------------------------------------------------------------
    # Skill-based mistakes
    # -----------------------------------------------------------------------

    def _noisy_score(self, base: float) -> float:
        noise_range = 3.0 * (1.0 - self.skill)
        if noise_range == 0:
            return base
        return base + self.rng.uniform(-noise_range, noise_range)

    def _miss_opportunity(self) -> bool:
        """Beginner sometimes misses a good play."""
        return self.rng.random() < 0.3 * (1.0 - self.skill)

    # -----------------------------------------------------------------------
    # Faction Draft
    # -----------------------------------------------------------------------

    def choose_factions(self, player_id: int, available: List[str],
                        num_to_pick: int, game: GameState) -> List[str]:
        """Pick factions during draft.  Balanced AI picks at random with slight preferences."""
        # Simple heuristic: rank factions by general strength, add noise
        faction_value = {
            "RED": 5.0, "ORANGE": 5.5, "YELLOW": 5.0,
            "GREEN": 5.0, "BLUE": 5.5, "PURPLE": 5.0,
        }
        scored = []
        for f in available:
            base = faction_value.get(f, 5.0)
            scored.append((f, self._noisy_score(base)))
        scored.sort(key=lambda x: -x[1])
        return [s[0] for s in scored[:num_to_pick]]

    # -----------------------------------------------------------------------
    # Green Peek decision
    # -----------------------------------------------------------------------

    def decide_green_peek(self, player: Player, top_card: Card,
                          game: GameState) -> bool:
        """Return True to discard the top card, False to keep it on top."""
        # Discard if it doesn't match our turf colors and isn't a chameleon
        if top_card.is_chameleon:
            return False  # keep chameleons

        # Check if it matches any arena turf we could play to
        can_use = False
        for arena in game.arenas:
            if arena.turf_color is None or arena.turf_color == top_card.faction:
                can_use = True
                break

        if not can_use:
            return True  # discard unhelpful card

        # Keep high-rank cards more often
        if top_card.rank >= 7:
            return False
        return self.rng.random() < 0.3

    # -----------------------------------------------------------------------
    # Purple Time Capsule: choose card to keep
    # -----------------------------------------------------------------------

    def choose_time_capsule_keep(self, player: Player,
                                  game: GameState) -> Optional[Card]:
        """Choose which card to keep at end of round (Purple personality)."""
        if not player.hand:
            return None
        # Keep highest-rank card, preferring chameleons
        chameleons = [c for c in player.hand if c.is_chameleon]
        if chameleons:
            return max(chameleons, key=lambda c: c.rank)
        return max(player.hand, key=lambda c: c.rank)

    # -----------------------------------------------------------------------
    # Core: choose action
    # -----------------------------------------------------------------------

    def choose_action(self, player: Player, game: GameState) -> dict:
        """
        Evaluate all options and return the best action dict.

        Returns:
            dict with 'type' and type-specific fields.
        """
        # Check if benched first
        if game.is_benched(player):
            card = self._worst_card(player)
            return {"type": "bench", "discard": card}

        candidates = []  # (score, action_dict)

        # Option 1: Play a monster
        legal_plays = game.get_legal_plays(player)
        for card, arena in legal_plays:
            if self._miss_opportunity():
                continue
            score = self._score_play(player, card, arena, game)
            candidates.append((score, {
                "type": "play_monster",
                "card": card,
                "arena": arena.name,
                "chameleon_turf_choice": self._choose_turf_color(player, arena, card),
            }))

        # Option 2: Fumble
        if game.can_fumble(player):
            fumble_score = self._score_fumble(player, game, legal_plays)
            worst = self._worst_card(player)
            if worst:
                candidates.append((fumble_score, {
                    "type": "fumble",
                    "discard": worst,
                }))

        if not candidates:
            # Shouldn't happen, but safety net
            if player.hand:
                return {"type": "fumble", "discard": player.hand[0]}
            return {"type": "bench", "discard": None}

        # Pick best
        candidates.sort(key=lambda x: -x[0])
        return candidates[0][1]

    # -----------------------------------------------------------------------
    # Signature move decisions
    # -----------------------------------------------------------------------

    def choose_signature(self, player: Player, game: GameState,
                          just_played: Card, arena_name: str) -> Optional[dict]:
        """
        After playing a monster, decide whether to use a signature move.
        Returns None if no signature used, or a dict describing the move.
        """
        if game.signature_used_this_turn:
            return None

        arena = game.get_arena(arena_name)

        # RED: Heroic Intervention
        if (just_played.faction == "RED" and
            game.can_use_signature(player, "RED")):
            move = self._evaluate_red_sig(player, game, arena_name)
            if move and self.rng.random() < self.style["signature_eagerness"]:
                return move

        # YELLOW: Double Install
        if (just_played.faction == "YELLOW" and
            game.can_use_signature(player, "YELLOW")):
            move = self._evaluate_yellow_sig(player, game, arena_name)
            if move and self.rng.random() < self.style["signature_eagerness"]:
                return move

        # GREEN: Scheduled Outcome
        if (just_played.faction == "GREEN" and
            game.can_use_signature(player, "GREEN")):
            if self.rng.random() < self.style["signature_eagerness"]:
                return {"type": "sig_green"}

        # BLUE: Is This Your Card?
        if (just_played.faction == "BLUE" and
            game.can_use_signature(player, "BLUE")):
            move = self._evaluate_blue_sig(player, game, arena_name)
            if move and self.rng.random() < self.style["signature_eagerness"]:
                return move

        # PURPLE: Rewind
        if (just_played.faction == "PURPLE" and
            game.can_use_signature(player, "PURPLE")):
            if not game.discard_pile.empty:
                top = game.discard_pile.cards[-1]
                lo, hi = game.faction_cfg["PURPLE"]["rewind_rank_range"]
                if lo <= top.rank <= hi:
                    if self.rng.random() < self.style["signature_eagerness"]:
                        return {"type": "sig_purple"}

        return None

    # -----------------------------------------------------------------------
    # Blue personality: decide whether to bounce
    # -----------------------------------------------------------------------

    def choose_blue_bounce(self, player: Player, game: GameState,
                            arena_name: str, just_played: Card) -> Optional[Card]:
        """
        When playing Blue, optionally bounce one of your other monsters
        from this arena to your hand.  Return the card to bounce, or None.
        """
        arena = game.get_arena(arena_name)
        my_other = [s for s in arena.player_slots(player.id)
                    if s.card != just_played]

        if not my_other:
            return None

        # Bounce low-rank monsters to replay elsewhere
        low = [s for s in my_other if s.card.rank <= 3]
        if low:
            return min(low, key=lambda s: s.card.rank).card

        # Don't bounce high-value monsters unless aggressive
        if self.aggression > 0.7 and my_other:
            weakest = min(my_other, key=lambda s: s.card.rank)
            if weakest.card.rank <= 5:
                return weakest.card

        return None

    # -----------------------------------------------------------------------
    # Scoring helpers
    # -----------------------------------------------------------------------

    def _score_play(self, player: Player, card: Card, arena: Arena,
                     game: GameState) -> float:
        """Score playing a card to an arena."""
        score = 0.0
        style = self.style

        # Base value: card rank
        effective_rank = card.rank

        # Yellow Fast Start bonus potential
        if player.has_faction("YELLOW") and player.monsters_played_this_round == 0:
            effective_rank += 2

        # RED Bodyguard: if this becomes the highest, +1
        if player.has_faction("RED"):
            my_cards = arena.player_cards(player.id)
            current_max = max((c.rank for c in my_cards), default=-1)
            if card.rank > current_max:
                effective_rank += 1

        # ORANGE Dibs Mine: first orange in arena with no opponent orange
        if (player.has_faction("ORANGE") and card.faction == "ORANGE"):
            my_oranges = [c for c in arena.player_cards(player.id) if c.faction == "ORANGE"]
            opp_oranges = [c for c in arena.player_cards(1 - player.id) if c.faction == "ORANGE"]
            if not my_oranges and not opp_oranges:
                effective_rank += 1

        score += effective_rank * style["arena_rank_weight"]

        # Center arena bonus: AI values Center more when it awards extra VP
        center_bonus = game.rules.get("center_arena_bonus_vp", 0)
        if arena.name == "Center" and center_bonus > 0:
            score += center_bonus * 1.5  # weight the bonus VP

        # Arena position analysis
        my_count = len(arena.player_slots(player.id))
        opp_count = len(arena.player_slots(1 - player.id))
        total_after = arena.monster_count + 1

        # Bonus for arenas where we have few monsters (spread)
        if my_count == 0:
            score += 2.0 * style["arena_spread_bonus"]
        elif my_count < opp_count:
            score += 1.0 * style["arena_spread_bonus"]

        # Deny bonus: play where opponent is investing
        if opp_count >= 2:
            score += opp_count * 0.5 * style["deny_bonus"]

        # Roar timing analysis
        if total_after >= game.rules["arena_roar_threshold"]:
            # This play triggers the roar!
            my_rank_sum = sum(c.rank for c in arena.player_cards(player.id)) + effective_rank
            opp_rank_sum = sum(c.rank for c in arena.player_cards(1 - player.id))
            if my_rank_sum > opp_rank_sum:
                score += 5.0  # we'd win this arena
            elif my_rank_sum < opp_rank_sum:
                score -= 3.0  # we'd lose — bad to trigger
            else:
                score -= 1.0  # tie = waste

        # Chameleon conservation
        if card.is_chameleon:
            remaining = game.rules["max_chameleons_per_round"] - player.chameleons_played
            if remaining <= 1:
                score -= 2.0 * (1.0 - style["chameleon_eagerness"])

        # Aggression modifier
        score += (self.aggression - 0.5) * 1.5

        return self._noisy_score(score)

    def _score_fumble(self, player: Player, game: GameState,
                       legal_plays: list) -> float:
        """Score the fumble option."""
        # Fumble is better when hand is bad
        if not legal_plays:
            return 3.0  # can't play, fumble is our only option

        # Count how many of our cards match available turfs
        matching = 0
        for c in player.hand:
            for a in game.arenas:
                if game.can_play_to_arena(c, a, player):
                    matching += 1
                    break

        ratio = matching / max(len(player.hand), 1)
        if ratio < self.style["fumble_threshold"]:
            return 2.0  # hand is bad enough to fumble
        return -2.0  # hand is fine, don't fumble

    def _worst_card(self, player: Player) -> Optional[Card]:
        """Pick the worst card to discard."""
        if not player.hand:
            return None
        # Discard lowest rank non-chameleon first
        non_cham = [c for c in player.hand if not c.is_chameleon]
        if non_cham:
            return min(non_cham, key=lambda c: c.rank)
        return min(player.hand, key=lambda c: c.rank)

    def _choose_turf_color(self, player: Player, arena: Arena,
                            card: Card) -> Optional[str]:
        """If playing a chameleon to an empty arena, choose turf color."""
        if not (card.is_chameleon and arena.is_empty):
            return None
        # Pick our command faction that we have the most cards of in hand
        faction_counts = {}
        for f in player.command_factions:
            faction_counts[f] = sum(1 for c in player.hand if c.faction == f)
        if faction_counts:
            return max(faction_counts, key=faction_counts.get)
        return player.command_factions[0] if player.command_factions else "RED"

    # -----------------------------------------------------------------------
    # Signature evaluators
    # -----------------------------------------------------------------------

    def _evaluate_red_sig(self, player: Player, game: GameState,
                           target_arena_name: str) -> Optional[dict]:
        """Evaluate RED Heroic Intervention."""
        target = game.get_arena(target_arena_name)
        best_move = None
        best_score = 0

        for adj_name in game.adjacent_arenas(target_arena_name):
            adj = game.get_arena(adj_name)
            for slot in adj.player_slots(player.id):
                if game.can_play_to_arena(slot.card, target, player):
                    # Score: how much does moving help?
                    score = slot.card.rank * 0.5  # value of adding rank to target
                    # Penalty if removing from a contested arena
                    if len(adj.player_slots(player.id)) <= len(adj.player_slots(1 - player.id)):
                        score -= 2.0
                    if score > best_score:
                        best_score = score
                        best_move = {
                            "type": "sig_red",
                            "source_arena": adj_name,
                            "target_arena": target_arena_name,
                            "monster": slot.card,
                        }
        return best_move

    def _evaluate_yellow_sig(self, player: Player, game: GameState,
                              arena_name: str) -> Optional[dict]:
        """Evaluate YELLOW Double-Install."""
        arena = game.get_arena(arena_name)
        if arena.monster_count >= game.rules["arena_roar_threshold"]:
            return None  # arena already roared

        best = None
        best_score = -999
        for card in player.hand:
            if game.can_play_to_arena(card, arena, player):
                score = card.rank
                if score > best_score:
                    best_score = score
                    best = card

        if best:
            return {
                "type": "sig_yellow",
                "card": best,
                "arena": arena_name,
                "chameleon_turf_choice": self._choose_turf_color(player, arena, best),
            }
        return None

    def _evaluate_blue_sig(self, player: Player, game: GameState,
                            arena_name: str) -> Optional[dict]:
        """Evaluate BLUE Is This Your Card? swap."""
        arena = game.get_arena(arena_name)
        opp_id = 1 - player.id
        max_diff = game.faction_cfg["BLUE"]["swap_rank_range"]

        best_gain = 0
        best_swap = None

        for my_slot in arena.player_slots(player.id):
            for their_slot in arena.player_slots(opp_id):
                if abs(my_slot.card.rank - their_slot.card.rank) <= max_diff:
                    gain = their_slot.card.rank - my_slot.card.rank
                    if gain > best_gain:
                        best_gain = gain
                        best_swap = {
                            "type": "sig_blue",
                            "arena": arena_name,
                            "my_card": my_slot.card,
                            "their_card": their_slot.card,
                        }
        return best_swap

    # -----------------------------------------------------------------------
    # Reasoning (for narration)
    # -----------------------------------------------------------------------

    def choose_action_with_reasoning(self, player: Player,
                                      game: GameState) -> Tuple[dict, str]:
        """Same as choose_action but returns (action, reasoning_text)."""
        reasoning_parts = []

        if game.is_benched(player):
            card = self._worst_card(player)
            reasoning_parts.append("Benched — no legal plays and no fumbles remaining.")
            return {"type": "bench", "discard": card}, "\n".join(reasoning_parts)

        candidates = []

        # Plays
        legal_plays = game.get_legal_plays(player)
        reasoning_parts.append(f"Legal plays: {len(legal_plays)}")

        for card, arena in legal_plays:
            score = self._score_play(player, card, arena, game)
            candidates.append((score, {
                "type": "play_monster",
                "card": card,
                "arena": arena.name,
                "chameleon_turf_choice": self._choose_turf_color(player, arena, card),
            }))
            reasoning_parts.append(
                f"  - {card} to {arena.name}: score {score:.1f}"
            )

        # Fumble
        if game.can_fumble(player):
            fumble_score = self._score_fumble(player, game, legal_plays)
            worst = self._worst_card(player)
            candidates.append((fumble_score, {
                "type": "fumble", "discard": worst,
            }))
            reasoning_parts.append(f"  - Fumble (discard {worst}): score {fumble_score:.1f}")

        if not candidates:
            return {"type": "bench", "discard": player.hand[0] if player.hand else None}, "No options."

        candidates.sort(key=lambda x: -x[0])
        best = candidates[0]
        reasoning_parts.append(f"**Decision:** {best[1]['type']} (score {best[0]:.1f})")

        return best[1], "\n".join(reasoning_parts)
