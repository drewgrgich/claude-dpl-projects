"""
Mystery Mascots — Full game state machine.

Manages: deck, allegiances, draft, locker rooms, placement,
resolution, exposure, faction powers, accusations, scoring.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Callable
from collections import defaultdict
import random
import json
import os

from cards import Card, Deck, FACTIONS, FACTION_NAMES, build_full_deck, WILD_RANKS


# ── Placement record (card in a locker room) ──────────────────────
@dataclass
class Placement:
    """A card placed into a locker room."""
    card: Card
    player_id: int
    face_up: bool
    play_order: int  # global play-order counter for tiebreaking
    tinkered_exposure_rank: Optional[int] = None  # Yellow power override


# ── Player ─────────────────────────────────────────────────────────
@dataclass
class Player:
    pid: int
    allegiance: Optional[Card] = None
    hand: List[Card] = field(default_factory=list)
    exposed: bool = False
    power_used: bool = False
    accusation_tokens: int = 2
    accusations_made: List[Dict] = field(default_factory=list)
    times_exposed: int = 0  # for tiebreaker

    @property
    def faction(self) -> str:
        return self.allegiance.faction if self.allegiance else "UNKNOWN"

    def __repr__(self):
        status = "EXPOSED" if self.exposed else "hidden"
        return f"P{self.pid}({self.faction[:3]} {status} hand={len(self.hand)})"


# ── Locker Room ────────────────────────────────────────────────────
@dataclass
class LockerRoom:
    room_id: int
    placements: List[Placement] = field(default_factory=list)

    @property
    def size(self) -> int:
        return len(self.placements)

    @property
    def full(self) -> bool:
        return self.size >= 3

    @property
    def has_space(self) -> bool:
        return self.size < 3

    def add(self, placement: Placement):
        self.placements.append(placement)

    def clear(self):
        self.placements.clear()


# ── Game State ─────────────────────────────────────────────────────
class GameState:
    """Full Mystery Mascots state machine."""

    def __init__(self, config: dict, num_players: int, seed: int = None):
        assert 3 <= num_players <= 5, "Mystery Mascots supports 3–5 players"
        self.config = config
        self.rules = config["game_rules"]
        self.num_players = num_players
        self.rng = random.Random(seed)
        self.seed = seed
        self.pkey = f"{num_players}_player"

        # Build and shuffle deck
        all_cards = build_full_deck()
        self.deck = Deck(all_cards)
        self.deck.shuffle(self.rng)

        # Rooms
        self.num_rooms = self.rules["locker_rooms"][self.pkey]
        self.rooms: List[LockerRoom] = [LockerRoom(room_id=i) for i in range(self.num_rooms)]

        # Players
        self.players: List[Player] = []
        self.current_player_idx: int = 0
        self.turn_number: int = 0
        self.play_order_counter: int = 0

        # Game flags
        self.game_over: bool = False
        self.total_resolutions: int = 0
        self.target_resolutions: int = self.num_rooms

        # Faction scores (global — all players with that faction share it)
        self.faction_scores: Dict[str, int] = {f: 0 for f in FACTIONS}

        # Logging
        self.log: List[str] = []

        # Tracking for metrics
        self.resolution_log: List[Dict] = []  # per-resolution data
        self.turn_log: List[Dict] = []  # per-turn data
        self.exposure_events: List[Dict] = []

    # ── Setup ──────────────────────────────────────────────────────
    def setup(self, draft_fn: Callable = None):
        """
        Full game setup:
        1. Deal secret allegiances
        2. Draft hands (5 from 7)
        """
        # 1. Deal allegiances
        for i in range(self.num_players):
            allegiance_card = self.deck.draw_one()
            p = Player(pid=i, allegiance=allegiance_card,
                       accusation_tokens=self.rules["accusations"]["tokens_per_player"])
            self.players.append(p)
            self._log(f"P{i} secretly allegiant to {allegiance_card.faction}")

        # 2. Deal 7 to each, draft 5
        deal_size = self.rules["setup"]["deal_size"]
        keep_size = self.rules["setup"]["keep_size"]

        hands = []
        for i in range(self.num_players):
            dealt = self.deck.draw(deal_size)
            hands.append(dealt)

        if draft_fn:
            # AI-driven draft
            drafted_hands = draft_fn(self.players, hands, self)
        else:
            # Simple draft: clockwise pass, keep 1 each round
            drafted_hands = self._default_draft(hands, keep_size)

        for i, player in enumerate(self.players):
            player.hand = drafted_hands[i]
            self._log(f"P{i} drafted: {[str(c) for c in player.hand]}")

    def _default_draft(self, hands: List[List[Card]], keep: int) -> List[List[Card]]:
        """Default draft: pick first card each round, pass clockwise."""
        n = self.num_players
        kept = [[] for _ in range(n)]
        packs = [list(h) for h in hands]

        for round_num in range(keep):
            # Each player picks the first card from their current pack
            picks = []
            for i in range(n):
                if packs[i]:
                    picks.append(packs[i].pop(0))
                else:
                    picks.append(None)

            for i in range(n):
                if picks[i]:
                    kept[i].append(picks[i])

            # Pass packs clockwise
            packs = [packs[(i - 1) % n] for i in range(n)]

        # Remaining cards discarded
        return kept

    # ── Turn management ────────────────────────────────────────────
    def get_current_player(self) -> Player:
        return self.players[self.current_player_idx]

    def advance_turn(self):
        self.current_player_idx = (self.current_player_idx + 1) % self.num_players
        self.turn_number += 1

    def can_player_act(self, player: Player) -> bool:
        """Check if player has any legal action."""
        if player.hand:
            return True
        if not player.power_used:
            return True
        if player.accusation_tokens > 0:
            return True
        return False

    def get_legal_rooms(self) -> List[int]:
        """Room indices with space."""
        return [i for i, r in enumerate(self.rooms) if r.has_space]

    # ── Place card action ──────────────────────────────────────────
    def action_place_card(self, player: Player, card: Card, room_idx: int) -> dict:
        """Place a card into a locker room."""
        room = self.rooms[room_idx]
        if not room.has_space:
            return {"success": False, "error": "Room is full"}
        if card not in player.hand:
            return {"success": False, "error": "Card not in hand"}

        player.hand.remove(card)
        face_up = player.exposed
        self.play_order_counter += 1
        placement = Placement(card=card, player_id=player.pid,
                              face_up=face_up, play_order=self.play_order_counter)
        room.add(placement)

        self._log(f"P{player.pid} places {card if face_up else '???'} "
                  f"{'face-up' if face_up else 'face-down'} in Room {room_idx}")

        result = {
            "success": True,
            "action": "place",
            "card": card,
            "room": room_idx,
            "face_up": face_up,
            "triggered_resolution": False,
        }

        # Check if room is now full → resolve
        if room.full:
            res_result = self._resolve_room(room_idx)
            result["triggered_resolution"] = True
            result["resolution"] = res_result

        return result

    # ── Room Resolution ────────────────────────────────────────────
    def _resolve_room(self, room_idx: int, wild_fn: Callable = None) -> dict:
        """
        Resolve a full locker room:
        1. Reveal all cards
        2. Declare wilds (AI callback)
        3. Check majority → score
        4. Check exposure
        5. Clear room
        """
        room = self.rooms[room_idx]
        placements = list(room.placements)

        self._log(f"\n--- Resolving Room {room_idx} ---")

        # Step 1: Reveal
        for p in placements:
            p.face_up = True
            self._log(f"  Revealed: {p.card} (played by P{p.player_id})")

        # Step 2: Declare wilds
        # Build effective factions (wilds get declared)
        effective_factions = {}
        for p in placements:
            if p.card.is_wild and wild_fn:
                declared = wild_fn(self.players[p.player_id], p.card, room_idx, self)
                effective_factions[p.card.uid] = declared
                self._log(f"  P{p.player_id} declares {p.card} as {declared}")
            else:
                effective_factions[p.card.uid] = p.card.faction

        # Step 3: Majority check
        faction_counts = defaultdict(int)
        faction_rank_sums = defaultdict(int)
        for p in placements:
            eff_faction = effective_factions[p.card.uid]
            faction_counts[eff_faction] += 1
            faction_rank_sums[eff_faction] += p.card.rank

        max_count = max(faction_counts.values()) if faction_counts else 0
        winners = [f for f, c in faction_counts.items() if c == max_count]

        scored = False
        winning_faction = None
        score = 0

        if len(winners) == 1:
            # Clear majority
            winning_faction = winners[0]
            score = faction_rank_sums[winning_faction]
            self.faction_scores[winning_faction] += score
            scored = True
            self._log(f"  {winning_faction} wins Room {room_idx} with {faction_counts[winning_faction]} "
                      f"cards for {score} points!")
        else:
            self._log(f"  Room {room_idx} is a BUST — tied majority ({winners})")

        # Step 4: Exposure — highest rank
        # Use tinkered rank if Yellow power was applied
        def exposure_rank(p: Placement) -> int:
            if p.tinkered_exposure_rank is not None:
                return p.tinkered_exposure_rank
            return p.card.rank

        max_rank = max(exposure_rank(p) for p in placements)
        high_placements = [p for p in placements if exposure_rank(p) == max_rank]

        # Tiebreak: most recently played (highest play_order)
        exposer = max(high_placements, key=lambda p: p.play_order)
        exposed_player = self.players[exposer.player_id]

        if not exposed_player.exposed:
            exposed_player.exposed = True
            exposed_player.times_exposed += 1
            self._log(f"  P{exposer.player_id} is now EXPOSED! "
                      f"(played {exposer.card}, rank {exposure_rank(exposer)})")
            self.exposure_events.append({
                "turn": self.turn_number,
                "player": exposer.player_id,
                "card": str(exposer.card),
                "rank": exposure_rank(exposer),
                "room": room_idx,
            })
        else:
            self._log(f"  P{exposer.player_id} would be exposed but already is")

        # Step 5: Clear room
        room.clear()
        self.total_resolutions += 1

        res_data = {
            "room": room_idx,
            "scored": scored,
            "winning_faction": winning_faction,
            "score": score,
            "bust": not scored,
            "faction_counts": dict(faction_counts),
            "exposed_player": exposer.player_id,
            "cards": [(str(p.card), p.player_id, effective_factions[p.card.uid]) for p in placements],
        }
        self.resolution_log.append(res_data)

        # Check game end
        if self.total_resolutions >= self.target_resolutions:
            self.game_over = True
            self._log("\n*** GAME OVER — all rooms have resolved ***")

        return res_data

    # ── Faction Powers ─────────────────────────────────────────────
    def action_power_red(self, player: Player, room_idx: int, placement_idx: int) -> dict:
        """Red: Flip any face-down card face-up."""
        room = self.rooms[room_idx]
        if placement_idx >= len(room.placements):
            return {"success": False, "error": "Invalid placement"}
        p = room.placements[placement_idx]
        if p.face_up:
            return {"success": False, "error": "Already face-up"}

        p.face_up = True
        player.power_used = True
        self._log(f"P{player.pid} uses RED POWER: flips {p.card} face-up in Room {room_idx}")
        return {"success": True, "action": "power_red", "revealed": p.card,
                "room": room_idx, "player_of_card": p.player_id}

    def action_power_orange(self, player: Player, room_idx: int, placement_idx: int) -> dict:
        """Orange: Secretly peek at a face-down card."""
        room = self.rooms[room_idx]
        if placement_idx >= len(room.placements):
            return {"success": False, "error": "Invalid placement"}
        p = room.placements[placement_idx]
        if p.face_up:
            return {"success": False, "error": "Already face-up"}

        player.power_used = True
        self._log(f"P{player.pid} uses ORANGE POWER: peeks at a card in Room {room_idx}")
        return {"success": True, "action": "power_orange", "peeked": p.card,
                "room": room_idx, "player_of_card": p.player_id}

    def action_power_yellow(self, player: Player, room_idx: int, placement_idx: int,
                            new_exposure_rank: int) -> dict:
        """Yellow: Set exposure rank of own card to 0 or 11."""
        room = self.rooms[room_idx]
        if placement_idx >= len(room.placements):
            return {"success": False, "error": "Invalid placement"}
        p = room.placements[placement_idx]
        if p.player_id != player.pid:
            return {"success": False, "error": "Not your card"}
        if new_exposure_rank not in (0, 11):
            return {"success": False, "error": "Must be 0 or 11"}

        p.tinkered_exposure_rank = new_exposure_rank
        player.power_used = True
        self._log(f"P{player.pid} uses YELLOW POWER: card in Room {room_idx} "
                  f"now counts as rank {new_exposure_rank} for exposure")
        return {"success": True, "action": "power_yellow",
                "room": room_idx, "new_exposure_rank": new_exposure_rank}

    def action_power_green(self, player: Player, target_pid: int) -> dict:
        """Green: Mutual allegiance peek."""
        target = self.players[target_pid]
        player.power_used = True
        self._log(f"P{player.pid} uses GREEN POWER: mutual peek with P{target_pid}")
        return {"success": True, "action": "power_green",
                "your_peek": target.allegiance.faction,
                "they_see": player.allegiance.faction,
                "target": target_pid}

    def action_power_blue(self, player: Player, from_room: int, from_idx: int,
                          to_room: int) -> dict:
        """Blue: Move own card to different room."""
        src = self.rooms[from_room]
        dst = self.rooms[to_room]
        if from_idx >= len(src.placements):
            return {"success": False, "error": "Invalid source"}
        if not dst.has_space:
            return {"success": False, "error": "Destination full"}
        if from_room == to_room:
            return {"success": False, "error": "Must move to different room"}

        p = src.placements[from_idx]
        if p.player_id != player.pid:
            return {"success": False, "error": "Not your card"}

        # Move it
        src.placements.pop(from_idx)
        dst.add(p)
        player.power_used = True
        self._log(f"P{player.pid} uses BLUE POWER: moves {p.card} from Room {from_room} to Room {to_room}")

        result = {"success": True, "action": "power_blue",
                  "card": p.card, "from_room": from_room, "to_room": to_room,
                  "triggered_resolution": False}

        if dst.full:
            res = self._resolve_room(to_room)
            result["triggered_resolution"] = True
            result["resolution"] = res

        return result

    def action_power_purple(self, player: Player, from_room: int, from_idx: int,
                            to_room: int, wild_fn: Callable = None) -> dict:
        """Purple: Return own card to hand, replay it to different room."""
        src = self.rooms[from_room]
        if from_idx >= len(src.placements):
            return {"success": False, "error": "Invalid source"}

        p = src.placements[from_idx]
        if p.player_id != player.pid:
            return {"success": False, "error": "Not your card"}

        dst = self.rooms[to_room]
        if not dst.has_space:
            return {"success": False, "error": "Destination full"}
        if from_room == to_room:
            return {"success": False, "error": "Must replay to different room"}

        # Return to hand
        src.placements.pop(from_idx)
        card = p.card

        # Replay with current hidden/exposed status
        face_up = player.exposed
        self.play_order_counter += 1
        new_placement = Placement(card=card, player_id=player.pid,
                                  face_up=face_up, play_order=self.play_order_counter)
        dst.add(new_placement)
        player.power_used = True

        self._log(f"P{player.pid} uses PURPLE POWER: rewinds {card} from Room {from_room} "
                  f"to Room {to_room}")

        result = {"success": True, "action": "power_purple",
                  "card": card, "from_room": from_room, "to_room": to_room,
                  "triggered_resolution": False}

        if dst.full:
            res = self._resolve_room(to_room, wild_fn=wild_fn)
            result["triggered_resolution"] = True
            result["resolution"] = res

        return result

    # ── Accusation ─────────────────────────────────────────────────
    def action_accuse(self, player: Player, target_pid: int, guessed_faction: str) -> dict:
        """Make an accusation against another player."""
        if player.accusation_tokens <= 0:
            return {"success": False, "error": "No tokens left"}
        if target_pid == player.pid:
            return {"success": False, "error": "Cannot accuse yourself"}

        target = self.players[target_pid]
        correct = (target.allegiance.faction == guessed_faction)

        player.accusation_tokens -= 1
        player.accusations_made.append({
            "target": target_pid,
            "guessed": guessed_faction,
            "actual": target.allegiance.faction,
            "correct": correct,
        })

        self._log(f"P{player.pid} accuses P{target_pid} of being {guessed_faction} — "
                  f"{'CORRECT' if correct else 'WRONG'}")

        return {
            "success": True,
            "action": "accuse",
            "target": target_pid,
            "guessed": guessed_faction,
            "correct": correct,
            "actual_faction": target.allegiance.faction,
        }

    # ── Final Scoring ──────────────────────────────────────────────
    def compute_final_scores(self) -> List[Dict]:
        """Compute final scores for all players."""
        results = []
        for p in self.players:
            faction_pts = self.faction_scores.get(p.faction, 0)
            acc_bonus = sum(
                self.rules["accusations"]["correct_bonus"] if a["correct"]
                else self.rules["accusations"]["incorrect_penalty"]
                for a in p.accusations_made
            )
            total = faction_pts + acc_bonus
            results.append({
                "pid": p.pid,
                "faction": p.faction,
                "faction_points": faction_pts,
                "accusation_bonus": acc_bonus,
                "total": total,
                "exposed": p.exposed,
                "times_exposed": p.times_exposed,
                "correct_accusations": sum(1 for a in p.accusations_made if a["correct"]),
                "accusations_made": len(p.accusations_made),
            })

        # Sort by total desc, then tiebreakers
        results.sort(key=lambda r: (
            -r["total"],
            r["times_exposed"],       # fewer exposures = better
            -r["correct_accusations"]  # more correct = better
        ))

        return results

    # ── Helpers ─────────────────────────────────────────────────────
    def get_face_down_placements(self, room_idx: int) -> List[Tuple[int, Placement]]:
        """Get indices of face-down placements in a room."""
        return [(i, p) for i, p in enumerate(self.rooms[room_idx].placements) if not p.face_up]

    def get_player_placements(self, player_id: int) -> List[Tuple[int, int, Placement]]:
        """Get all placements by a player: (room_idx, placement_idx, placement)."""
        result = []
        for ri, room in enumerate(self.rooms):
            for pi, p in enumerate(room.placements):
                if p.player_id == player_id:
                    result.append((ri, pi, p))
        return result

    def _log(self, msg: str):
        self.log.append(msg)

    def state_summary(self) -> str:
        """Human-readable state summary."""
        lines = [f"\n=== Turn {self.turn_number} (P{self.current_player_idx}'s turn) ==="]
        lines.append(f"Resolutions: {self.total_resolutions}/{self.target_resolutions}")
        for f in FACTIONS:
            if self.faction_scores[f] > 0:
                lines.append(f"  {f}: {self.faction_scores[f]} pts")
        for r in self.rooms:
            cards_str = ", ".join(
                f"{p.card if p.face_up else '???'}(P{p.player_id})"
                for p in r.placements
            )
            lines.append(f"  Room {r.room_id}: [{cards_str}] ({r.size}/3)")
        for p in self.players:
            lines.append(f"  {p}")
        return "\n".join(lines)
