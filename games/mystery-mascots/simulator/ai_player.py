"""
Mystery Mascots — Heuristic AI Player.

Handles: draft picks, card placement, wild declaration,
faction power usage, accusation timing, and allegiance tracking.

Three axes: skill (0-1), style (sneaky/bold/balanced/disruptive), aggression (0-1).
"""

from typing import List, Dict, Tuple, Optional
from collections import defaultdict
import random

from cards import Card, FACTIONS, WILD_RANKS
from game_state import GameState, Player, LockerRoom, Placement


# ── Style profiles ─────────────────────────────────────────────────
STYLE_PROFILES = {
    "sneaky": {
        "description": "Plays low cards, avoids exposure, subtle support",
        "low_card_preference": 2.0,
        "exposure_fear": 3.0,
        "own_faction_stealth": 2.0,  # bonus for disguising own faction
        "accuse_eagerness": 0.3,
        "power_eagerness": 0.4,
    },
    "bold": {
        "description": "Plays high cards for big scores, accepts exposure risk",
        "low_card_preference": -1.0,
        "exposure_fear": 0.5,
        "own_faction_stealth": 0.3,
        "accuse_eagerness": 0.5,
        "power_eagerness": 0.7,
    },
    "balanced": {
        "description": "Well-rounded default play",
        "low_card_preference": 0.5,
        "exposure_fear": 1.5,
        "own_faction_stealth": 1.0,
        "accuse_eagerness": 0.5,
        "power_eagerness": 0.5,
    },
    "disruptive": {
        "description": "Interferes with opponents, uses powers aggressively",
        "low_card_preference": 0.0,
        "exposure_fear": 1.0,
        "own_faction_stealth": 0.5,
        "accuse_eagerness": 0.8,
        "power_eagerness": 0.9,
    },
}


class HeuristicAI:
    """AI player for Mystery Mascots."""

    def __init__(self, skill: float = 1.0, style: str = "balanced",
                 aggression: float = 0.5, rng_seed: int = None):
        self.skill = max(0.0, min(1.0, skill))
        self.style_name = style
        self.style = STYLE_PROFILES.get(style, STYLE_PROFILES["balanced"])
        self.aggression = max(0.0, min(1.0, aggression))
        self.rng = random.Random(rng_seed)

        # Tracking / memory
        self.known_allegiances: Dict[int, str] = {}  # pid → faction (from green power or accusation)
        self.suspected_factions: Dict[int, Dict[str, float]] = {}  # pid → faction → probability
        self.draft_observations: Dict[int, List[str]] = {}  # pid → factions they kept

    # ── Skill-based mistakes ───────────────────────────────────────
    def _noisy_score(self, base: float) -> float:
        noise_range = 3.0 * (1.0 - self.skill)
        if noise_range == 0:
            return base
        return base + self.rng.uniform(-noise_range, noise_range)

    def _miss_opportunity(self) -> bool:
        return self.rng.random() < 0.3 * (1.0 - self.skill)

    def _bad_timing(self) -> bool:
        return self.rng.random() < 0.2 * (1.0 - self.skill)

    # ── Draft ──────────────────────────────────────────────────────
    def choose_draft_picks(self, player: Player, packs: List[List[Card]],
                           keep_count: int, game: GameState) -> List[List[Card]]:
        """
        Full draft: given rotating packs, return list of kept-hand per round.
        This is called by the batch runner's draft orchestrator.
        """
        my_faction = player.faction
        kept = []

        for pack in packs:
            if len(kept) >= keep_count:
                break
            if not pack:
                continue

            # Score each card
            scores = []
            for card in pack:
                score = self._score_draft_card(card, my_faction, kept)
                scores.append((card, score))

            scores.sort(key=lambda x: -x[1])
            pick = scores[0][0]
            kept.append(pick)

        return kept

    def choose_one_draft_pick(self, player: Player, pack: List[Card],
                              already_kept: List[Card], game: GameState) -> Card:
        """Pick one card from a draft pack."""
        my_faction = player.faction
        scores = []
        for card in pack:
            score = self._score_draft_card(card, my_faction, already_kept)
            scores.append((card, score))
        scores.sort(key=lambda x: -x[1])
        return scores[0][0]

    def _score_draft_card(self, card: Card, my_faction: str,
                          already_kept: List[Card]) -> float:
        """Score a card for drafting."""
        score = 0.0

        # Wilds are universally good
        if card.is_wild:
            score += 6.0 + card.rank * 0.3  # 10-wilds score higher for points

        # Cards of own faction: want them for scoring
        if card.faction == my_faction:
            score += 4.0 + card.rank * 0.3
            # But sneaky players are cautious about collecting too many of their faction
            own_count = sum(1 for c in already_kept if c.faction == my_faction)
            if own_count >= 2:
                score -= self.style["own_faction_stealth"] * 1.5

        # High-rank cards of OTHER factions: can help make majority
        if card.faction != my_faction:
            score += card.rank * 0.15

        # Low cards: less exposure risk
        score += (10 - card.rank) * 0.1 * self.style["low_card_preference"]

        # Hate-drafting: deny high cards from other factions
        if card.rank >= 8 and card.faction != my_faction:
            score += 1.5 * (1.0 - self.style.get("own_faction_stealth", 1.0))

        return self._noisy_score(score)

    # ── Main turn decision ─────────────────────────────────────────
    def choose_action(self, player: Player, game: GameState) -> dict:
        """
        Evaluate all legal actions and return the best one.
        Returns dict with 'type' and action-specific data.
        """
        candidates = []

        # Option 1: Place a card
        if player.hand:
            place_options = self._evaluate_placements(player, game)
            candidates.extend(place_options)

        # Option 2: Use faction power
        if not player.power_used and not self._miss_opportunity():
            power_options = self._evaluate_power(player, game)
            candidates.extend(power_options)

        # Option 3: Make an accusation
        if player.accusation_tokens > 0:
            accuse_options = self._evaluate_accusations(player, game)
            candidates.extend(accuse_options)

        if not candidates:
            return {"type": "pass"}

        # Pick best
        best = max(candidates, key=lambda x: x[1])
        return best[0]

    # ── Placement evaluation ───────────────────────────────────────
    def _evaluate_placements(self, player: Player, game: GameState) -> List[Tuple[dict, float]]:
        """Score every (card, room) combination."""
        candidates = []
        legal_rooms = game.get_legal_rooms()

        for card in player.hand:
            for room_idx in legal_rooms:
                score = self._score_placement(player, card, room_idx, game)
                action = {"type": "place", "card": card, "room": room_idx}
                candidates.append((action, score))

        return candidates

    def _score_placement(self, player: Player, card: Card,
                         room_idx: int, game: GameState) -> float:
        """Score placing a specific card in a specific room."""
        room = game.rooms[room_idx]
        my_faction = player.faction
        score = 0.0

        # Will this be the 3rd card (triggering resolution)?
        will_resolve = (room.size == 2)

        if will_resolve:
            score += self._score_resolution_placement(player, card, room, game)
        else:
            score += self._score_buildup_placement(player, card, room, game)

        # Exposure risk: if this card triggers resolution, highest rank gets exposed
        if will_resolve and not player.exposed:
            # Estimate if our card will be highest
            existing_ranks = [p.card.rank for p in room.placements if p.face_up]
            # For face-down cards, assume average rank of ~5
            hidden_count = sum(1 for p in room.placements if not p.face_up)
            est_max_existing = max(existing_ranks) if existing_ranks else 5
            if hidden_count > 0:
                est_max_existing = max(est_max_existing, 5)

            if card.rank > est_max_existing:
                score -= self.style["exposure_fear"] * (card.rank / 10.0) * 3.0
            elif card.rank == est_max_existing:
                score -= self.style["exposure_fear"] * 1.0  # might get exposed

        # Low card preference
        score += (10 - card.rank) * 0.1 * self.style["low_card_preference"]

        # STRONG preference for rooms that are close to resolving
        # This is critical: the game ends when all rooms resolve
        if room.size == 2:
            score += 4.0  # strongly prefer triggering resolutions
        elif room.size == 1:
            score += 1.5  # building toward resolution
        elif room.size == 0:
            score += 0.0  # empty rooms are low priority

        return self._noisy_score(score)

    def _score_resolution_placement(self, player: Player, card: Card,
                                     room: LockerRoom, game: GameState) -> float:
        """Score placing the 3rd card (triggers resolution)."""
        my_faction = player.faction
        score = 0.0

        # What factions are in this room?
        known_factions = defaultdict(int)
        known_rank_sum = defaultdict(int)
        unknown_count = 0

        for p in room.placements:
            if p.face_up:
                known_factions[p.card.faction] += 1
                known_rank_sum[p.card.faction] += p.card.rank
            else:
                unknown_count += 1

        # Add our card
        card_eff_faction = card.faction  # wilds will be declared later
        if card.is_wild:
            card_eff_faction = my_faction  # assume we'll declare it as our faction

        known_factions[card_eff_faction] += 1
        known_rank_sum[card_eff_faction] += card.rank

        # Can my faction win this room?
        my_count = known_factions.get(my_faction, 0)
        other_max = max((c for f, c in known_factions.items() if f != my_faction), default=0)

        if my_count >= 2:
            # Good chance my faction wins
            score += 5.0 + known_rank_sum.get(my_faction, 0) * 0.5
        elif my_count == 1 and unknown_count > 0:
            # Maybe, depends on hidden cards
            score += 1.5
        else:
            # Likely not winning for my faction — but might bust it to deny others
            if other_max >= 2:
                score -= 2.0  # helping an opponent
            else:
                score += 0.5  # likely bust, which is neutral

        return score

    def _score_buildup_placement(self, player: Player, card: Card,
                                  room: LockerRoom, game: GameState) -> float:
        """Score placing in a room that won't resolve yet."""
        my_faction = player.faction
        score = 0.0

        # Placing own-faction card builds toward majority
        if card.faction == my_faction or card.is_wild:
            score += 2.0
            # But being too obvious is risky when hidden
            if not player.exposed:
                score -= self.style["own_faction_stealth"] * 0.5

        # Empty room: fresh start
        if room.size == 0:
            score += 0.5
        elif room.size == 1:
            # Check if existing card helps or hurts
            existing = room.placements[0]
            if existing.face_up and existing.card.faction == my_faction:
                score += 2.0  # matching faction already here
            elif existing.face_up and existing.card.faction != my_faction:
                score -= 0.5

        return score

    # ── Wild declaration ───────────────────────────────────────────
    def declare_wild(self, player: Player, card: Card, room_idx: int,
                     game: GameState) -> str:
        """Decide which faction a wild card counts as."""
        my_faction = player.faction
        room = game.rooms[room_idx]

        # Count factions in room (excluding this wild)
        faction_counts = defaultdict(int)
        for p in room.placements:
            if p.card.uid != card.uid:
                if p.card.is_wild:
                    continue  # other wilds also being declared
                faction_counts[p.card.faction] += 1

        # If declaring as my faction gives majority, do it
        faction_counts_with_me = dict(faction_counts)
        faction_counts_with_me[my_faction] = faction_counts_with_me.get(my_faction, 0) + 1
        max_count = max(faction_counts_with_me.values()) if faction_counts_with_me else 1

        if faction_counts_with_me.get(my_faction, 0) == max_count:
            # Check if it's unique majority
            winners = [f for f, c in faction_counts_with_me.items() if c == max_count]
            if len(winners) == 1:
                return my_faction

        # If declaring as my faction doesn't help, try to create a bust
        # (tie) to deny opponents
        for faction in FACTIONS:
            if faction == my_faction:
                continue
            test = dict(faction_counts)
            test[faction] = test.get(faction, 0) + 1
            max_c = max(test.values())
            winners = [f for f, c in test.items() if c == max_c]
            if len(winners) > 1:
                # This creates a bust — good if opponents would score
                return faction

        # Default: declare as own faction
        return my_faction

    # ── Power evaluation ───────────────────────────────────────────
    def _evaluate_power(self, player: Player, game: GameState) -> List[Tuple[dict, float]]:
        """Evaluate faction power options."""
        candidates = []
        faction = player.faction
        eagerness = self.style["power_eagerness"]

        # Only evaluate the power matching the player's faction
        if faction == "RED":
            candidates.extend(self._eval_red_power(player, game, eagerness))
        elif faction == "ORANGE":
            candidates.extend(self._eval_orange_power(player, game, eagerness))
        elif faction == "YELLOW":
            candidates.extend(self._eval_yellow_power(player, game, eagerness))
        elif faction == "GREEN":
            candidates.extend(self._eval_green_power(player, game, eagerness))
        elif faction == "BLUE":
            candidates.extend(self._eval_blue_power(player, game, eagerness))
        elif faction == "PURPLE":
            candidates.extend(self._eval_purple_power(player, game, eagerness))

        return candidates

    def _eval_red_power(self, player, game, eagerness):
        """Red: Flip a face-down card. Best when it reveals useful info or disrupts."""
        results = []
        for ri, room in enumerate(game.rooms):
            facedown = game.get_face_down_placements(ri)
            for pi, placement in facedown:
                score = 5.0 * eagerness
                if room.size == 2:
                    score += 3.0  # about to resolve — info is critical
                elif room.size == 1:
                    score += 1.0
                # Bonus: if opponent placed this card, revealing it is disruptive
                if placement.player_id != player.pid:
                    score += 1.5
                results.append(({"type": "power_red", "room": ri, "placement_idx": pi},
                                self._noisy_score(score)))
        return results

    def _eval_orange_power(self, player, game, eagerness):
        """Orange: Peek at face-down card. Best for strategic planning."""
        results = []
        for ri, room in enumerate(game.rooms):
            facedown = game.get_face_down_placements(ri)
            for pi, placement in facedown:
                score = 5.0 * eagerness
                if room.size == 2:
                    score += 2.5  # about to resolve, need to know
                elif room.size == 1:
                    score += 1.0
                results.append(({"type": "power_orange", "room": ri, "placement_idx": pi},
                                self._noisy_score(score)))
        return results

    def _eval_yellow_power(self, player, game, eagerness):
        """Yellow: Change exposure rank. Best when avoiding exposure on high card."""
        results = []
        my_placements = game.get_player_placements(player.pid)
        for ri, pi, placement in my_placements:
            room = game.rooms[ri]
            # If our card is high-rank and room will resolve soon, set to 0
            if placement.card.rank >= 5 and not player.exposed:
                score = 5.0 + (placement.card.rank / 10.0) * 5.0
                score *= eagerness
                if room.size >= 1:
                    score += 2.0  # room has other cards, more likely to resolve
                results.append(({"type": "power_yellow", "room": ri,
                                 "placement_idx": pi, "new_rank": 0},
                                self._noisy_score(score)))
            # Set to 11 to intentionally take exposure (if already exposed)
            if player.exposed and placement.card.rank < 5:
                score = 2.0 * eagerness
                results.append(({"type": "power_yellow", "room": ri,
                                 "placement_idx": pi, "new_rank": 11},
                                self._noisy_score(score)))
        return results

    def _eval_green_power(self, player, game, eagerness):
        """Green: Mutual peek. Best early for allegiance info + better accusations."""
        results = []
        for other in game.players:
            if other.pid == player.pid:
                continue
            if other.pid in self.known_allegiances:
                continue
            if other.exposed:
                continue
            score = 7.0 * eagerness  # very valuable — guaranteed info
            # More valuable early
            progress = game.total_resolutions / max(game.target_resolutions, 1)
            score *= (1.0 - progress * 0.3)
            results.append(({"type": "power_green", "target": other.pid},
                            self._noisy_score(score)))
        return results

    def _eval_blue_power(self, player, game, eagerness):
        """Blue: Move own card. Best for triggering favorable resolutions."""
        results = []
        my_placements = game.get_player_placements(player.pid)
        legal_rooms = game.get_legal_rooms()

        for ri, pi, placement in my_placements:
            for to_room in legal_rooms:
                if to_room == ri:
                    continue
                score = 4.0 * eagerness
                dst = game.rooms[to_room]
                src = game.rooms[ri]
                # Big bonus if moving to a room that will trigger resolution
                if dst.size == 2:
                    score += 5.0
                # Bonus if the source room only has our card (remove from dead room)
                if src.size == 1:
                    score += 1.0
                results.append(({"type": "power_blue", "from_room": ri,
                                 "from_idx": pi, "to_room": to_room},
                                self._noisy_score(score)))
        return results

    def _eval_purple_power(self, player, game, eagerness):
        """Purple: Rewind and replay. Best for repositioning to trigger favorable rooms."""
        results = []
        my_placements = game.get_player_placements(player.pid)
        legal_rooms = game.get_legal_rooms()

        for ri, pi, placement in my_placements:
            for to_room in legal_rooms:
                if to_room == ri:
                    continue
                score = 4.5 * eagerness
                dst = game.rooms[to_room]
                # Huge bonus for triggering a resolution
                if dst.size == 2:
                    score += 5.0
                # Bonus if repositioning improves faction majority chances
                my_faction = player.faction
                dst_faction_match = sum(
                    1 for p in dst.placements
                    if p.face_up and p.card.faction == my_faction
                )
                score += dst_faction_match * 2.0
                results.append(({"type": "power_purple", "from_room": ri,
                                 "from_idx": pi, "to_room": to_room},
                                self._noisy_score(score)))
        return results

    # ── Accusation evaluation ──────────────────────────────────────
    def _evaluate_accusations(self, player: Player, game: GameState) -> List[Tuple[dict, float]]:
        """Evaluate whether to accuse and who."""
        candidates = []
        eagerness = self.style["accuse_eagerness"]

        # Don't accuse too early — placing cards is more important
        progress = game.total_resolutions / max(game.target_resolutions, 1)
        if progress < 0.4 and not self._bad_timing():
            return candidates

        # If we still have cards to place, be less eager to accuse
        if player.hand:
            eagerness *= 0.4  # placing cards matters more

        for other in game.players:
            if other.pid == player.pid:
                continue
            # Already accused this player?
            already_accused = any(a["target"] == other.pid for a in player.accusations_made)
            if already_accused:
                continue

            # Do we know their faction?
            if other.pid in self.known_allegiances:
                known_faction = self.known_allegiances[other.pid]
                score = 7.0 * eagerness  # very confident
                candidates.append(({"type": "accuse", "target": other.pid,
                                    "faction": known_faction},
                                   self._noisy_score(score)))
            elif other.exposed:
                # They're exposed, we know their faction from allegiance reveal
                score = 7.0 * eagerness
                candidates.append(({"type": "accuse", "target": other.pid,
                                    "faction": other.faction},
                                   self._noisy_score(score)))
            else:
                # Guess based on observed play
                best_guess = self._guess_faction(other, game)
                if best_guess:
                    confidence = self._guess_confidence(other, game)
                    score = confidence * 4.0 * eagerness
                    if score > 2.0:  # only accuse if somewhat confident
                        candidates.append(({"type": "accuse", "target": other.pid,
                                            "faction": best_guess},
                                           self._noisy_score(score)))

        return candidates

    def _guess_faction(self, target: Player, game: GameState) -> Optional[str]:
        """Guess a player's faction based on face-up cards they've played."""
        # Count face-up cards by faction played by this target
        faction_plays = defaultdict(int)
        for room in game.rooms:
            for p in room.placements:
                if p.player_id == target.pid and p.face_up:
                    faction_plays[p.card.faction] += 1

        # Also check resolution log for their cards
        for res in game.resolution_log:
            for card_str, pid, eff_faction in res["cards"]:
                if pid == target.pid:
                    faction_plays[eff_faction] += 1

        if not faction_plays:
            return None

        # Most frequently played faction is the guess
        return max(faction_plays, key=faction_plays.get)

    def _guess_confidence(self, target: Player, game: GameState) -> float:
        """How confident are we in our faction guess? 0-1."""
        faction_plays = defaultdict(int)
        total = 0
        for res in game.resolution_log:
            for card_str, pid, eff_faction in res["cards"]:
                if pid == target.pid:
                    faction_plays[eff_faction] += 1
                    total += 1

        if total == 0:
            return 0.1

        max_count = max(faction_plays.values())
        return min(1.0, max_count / max(total, 1) * 0.8)

    # ── Reasoning (for narration) ──────────────────────────────────
    def choose_action_with_reasoning(self, player: Player, game: GameState) -> Tuple[dict, str]:
        """Like choose_action but also returns reasoning string."""
        action = self.choose_action(player, game)
        reasoning = self._explain_action(player, action, game)
        return action, reasoning

    def _explain_action(self, player: Player, action: dict, game: GameState) -> str:
        t = action.get("type", "pass")
        if t == "place":
            card = action["card"]
            room = action["room"]
            room_obj = game.rooms[room]
            return (f"Place {card} in Room {room} "
                    f"(room has {room_obj.size}/3 cards, "
                    f"{'will resolve!' if room_obj.size == 2 else 'building up'})")
        elif t.startswith("power_"):
            return f"Use {player.faction} faction power"
        elif t == "accuse":
            return f"Accuse P{action['target']} of being {action['faction']}"
        elif t == "pass":
            return "No good options — pass"
        return str(action)
