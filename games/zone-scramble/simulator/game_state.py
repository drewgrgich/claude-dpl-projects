"""
Zone Scramble — Full game state machine.

Every game action is a method that validates preconditions, mutates state,
and returns a result dict.  The state never makes decisions — all choices
come from the AI layer.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
import random
import copy

from cards import Card, Deck, build_full_deck


# ---------------------------------------------------------------------------
# Arena
# ---------------------------------------------------------------------------

@dataclass
class ArenaSlot:
    """One monster placed in an arena, tracking ownership."""
    card: Card
    owner: int          # player id
    effective_rank: int = 0   # computed at scoring time


@dataclass
class Arena:
    name: str                               # Left / Center / Right
    turf_color: Optional[str] = None        # faction that claimed turf
    slots: List[ArenaSlot] = field(default_factory=list)

    @property
    def monster_count(self) -> int:
        return len(self.slots)

    @property
    def is_empty(self) -> bool:
        return len(self.slots) == 0

    def player_slots(self, pid: int) -> List[ArenaSlot]:
        return [s for s in self.slots if s.owner == pid]

    def player_cards(self, pid: int) -> List[Card]:
        return [s.card for s in self.slots if s.owner == pid]

    def clear(self) -> List[Card]:
        """Remove all monsters, return the cards, reset turf."""
        cards = [s.card for s in self.slots]
        self.slots.clear()
        self.turf_color = None
        return cards


# ---------------------------------------------------------------------------
# Player
# ---------------------------------------------------------------------------

@dataclass
class Player:
    id: int
    command_factions: List[str] = field(default_factory=list)
    hand: List[Card] = field(default_factory=list)
    vp: int = 0
    trophy_pile: List[Card] = field(default_factory=list)

    # Per-round trackers (reset each round)
    chameleons_played: int = 0
    fumbles_used: int = 0
    signature_used: Dict[str, bool] = field(default_factory=dict)
    monsters_played_this_round: int = 0

    # Per-game trackers
    big_borrow_used: bool = False

    # Stats
    arenas_won_this_round: int = 0

    def reset_round(self):
        self.chameleons_played = 0
        self.fumbles_used = 0
        self.signature_used = {}
        self.monsters_played_this_round = 0
        self.arenas_won_this_round = 0

    def has_faction(self, faction: str) -> bool:
        return faction in self.command_factions

    @property
    def total_vp(self) -> int:
        """VP + trophy pile VP."""
        return self.vp + len(self.trophy_pile)

    def __repr__(self):
        return f"P{self.id}(VP:{self.total_vp} Hand:{len(self.hand)})"


# ---------------------------------------------------------------------------
# GameState
# ---------------------------------------------------------------------------

ADJACENT = {
    "Left": ["Center"],
    "Center": ["Left", "Right"],
    "Right": ["Center"],
}


class GameState:
    """Full game state machine for Zone Scramble."""

    def __init__(self, config: dict, seed: int = 0):
        self.config = config
        self.rules = config["game_rules"]
        self.faction_cfg = config["factions"]
        self.rng = random.Random(seed)
        self.seed = seed

        # Build deck
        all_cards = build_full_deck(config)
        self.draw_pile = Deck(all_cards)
        self.draw_pile.shuffle(self.rng)
        self.discard_pile = Deck()

        # Arenas
        self.arenas: List[Arena] = [
            Arena(name=n) for n in self.rules["arenas"]
        ]

        # Players
        self.players: List[Player] = [Player(id=0), Player(id=1)]

        # Turn tracking
        self.current_round: int = 0          # 0-indexed
        self.current_turn_in_round: int = 0  # 0-indexed, counts both players' turns
        self.start_player: int = 0           # alternates each round
        self.current_player_idx: int = 0
        self.game_over: bool = False
        self.winner: Optional[int] = None

        # Signature move used this turn?
        self.signature_used_this_turn: bool = False

        # Log
        self.log: List[str] = []

        # Optional modes
        self.pop_bonus = config.get("optional_modes", {}).get("pop_bonus", False)
        self.pop_bonus_value = config.get("optional_modes", {}).get("pop_bonus_value", 2)
        self.high_dopamine = config.get("optional_modes", {}).get("high_dopamine", False)
        self.pop_tax = config.get("optional_modes", {}).get("pop_tax", False)

        # Track who played the 5th monster (for pop bonus)
        self._pop_trigger_player: Optional[int] = None

        # Track total arenas won per player across entire game (for tiebreaker)
        self.total_arenas_won: Dict[int, int] = {0: 0, 1: 0}
        # Track highest single-arena rank total per player (for tiebreaker)
        self.highest_arena_total: Dict[int, int] = {0: 0, 1: 0}
        # Track who scored most recently (for tiebreaker)
        self.last_scorer: Optional[int] = None

        # Center arena bonus
        self.center_bonus_vp = self.rules.get("center_arena_bonus_vp", 0)

        # Yellow Fast Start: track first N monsters per round per player
        self._yellow_early_monsters: Dict[int, List[ArenaSlot]] = {0: [], 1: []}

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    def _log_msg(self, msg: str):
        self.log.append(msg)

    def get_current_player(self) -> Player:
        return self.players[self.current_player_idx]

    def get_opponent(self, pid: int) -> Player:
        return self.players[1 - pid]

    def get_arena(self, name: str) -> Arena:
        for a in self.arenas:
            if a.name == name:
                return a
        raise ValueError(f"No arena named {name}")

    def adjacent_arenas(self, arena_name: str) -> List[str]:
        return ADJACENT.get(arena_name, [])

    # -----------------------------------------------------------------------
    # Setup: Faction Draft
    # -----------------------------------------------------------------------

    def faction_draft(self, draft_fn=None):
        """
        Reveal cards until 5 different factions seen.
        Snake draft 4 of those 5 factions.
        draft_fn(player_id, available_factions, num_to_pick, game_state) -> list of picked factions
        """
        # Reveal from top until 5 factions seen
        revealed = []
        factions_seen = set()
        while len(factions_seen) < 5 and not self.draw_pile.empty:
            card = self.draw_pile.draw_one()
            revealed.append(card)
            factions_seen.add(card.faction)

        # Discard revealed cards
        for c in revealed:
            self.discard_pile.add_to_bottom(c)

        available = list(factions_seen)
        self.rng.shuffle(available)

        self._log_msg(f"Faction draft: {available} available")

        # Snake draft: P_start picks 1, P_other picks 2, P_start picks 1
        draft_order = self.config["faction_draft"]["snake_draft_order"]
        # draft_order = [0, 1, 1, 0] means seat indices relative to start_player
        picks_needed = [1, 2, 1]  # how many to pick in each step
        step_player = [
            self.start_player,
            1 - self.start_player,
            self.start_player,
        ]
        # But step 1 picks 2 (the other player picks 2 at once)
        # Flatten: step 0 = start picks 1, step 1 = other picks 2, step 2 = start picks 1

        pick_idx = 0
        for step in range(3):
            pid = step_player[step]
            num = picks_needed[step]
            if draft_fn:
                picked = draft_fn(pid, available, num, self)
            else:
                picked = available[:num]

            for f in picked:
                self.players[pid].command_factions.append(f)
                available.remove(f)
                self._log_msg(f"P{pid} drafts {f}")

        self._log_msg(f"P0 factions: {self.players[0].command_factions}")
        self._log_msg(f"P1 factions: {self.players[1].command_factions}")

    # -----------------------------------------------------------------------
    # Setup: Deal hands
    # -----------------------------------------------------------------------

    def deal_hands(self):
        """Deal 6 cards to each player."""
        n = self.rules["cards_per_hand"]
        for p in self.players:
            p.hand = self.draw_pile.draw(n)
            self._log_msg(f"P{p.id} dealt {len(p.hand)} cards: {p.hand}")

    # -----------------------------------------------------------------------
    # Legality checks
    # -----------------------------------------------------------------------

    def can_play_to_arena(self, card: Card, arena: Arena, player: Player) -> bool:
        """Check if this card can legally be placed in this arena."""
        if card.is_chameleon:
            if player.chameleons_played >= self.rules["max_chameleons_per_round"]:
                return False
            return True

        if arena.is_empty:
            return True  # first card sets turf

        if arena.turf_color is None:
            return True  # cleared arena

        return card.faction == arena.turf_color

    def get_legal_plays(self, player: Player) -> List[Tuple[Card, Arena]]:
        """Return all (card, arena) pairs the player can legally play."""
        plays = []
        for card in player.hand:
            for arena in self.arenas:
                if self.can_play_to_arena(card, arena, player):
                    plays.append((card, arena))
        return plays

    def can_fumble(self, player: Player) -> bool:
        return player.fumbles_used < self.rules["max_fumbles_per_round"]

    def is_benched(self, player: Player) -> bool:
        """Player must bench if no legal plays AND fumbles exhausted."""
        return len(self.get_legal_plays(player)) == 0 and not self.can_fumble(player)

    # -----------------------------------------------------------------------
    # Actions
    # -----------------------------------------------------------------------

    def action_play_monster(self, player: Player, card: Card, arena_name: str,
                            chameleon_turf_choice: Optional[str] = None) -> dict:
        """
        Play a monster to an arena.
        chameleon_turf_choice: if chameleon in empty arena, which faction to set as turf.
        Returns result dict.
        """
        arena = self.get_arena(arena_name)

        if card not in player.hand:
            return {"success": False, "error": "Card not in hand"}

        if not self.can_play_to_arena(card, arena, player):
            return {"success": False, "error": f"Cannot play {card} to {arena.name}"}

        # Remove from hand
        player.hand.remove(card)

        # Track chameleon usage
        if card.is_chameleon:
            player.chameleons_played += 1

        # Set turf color if arena is empty
        if arena.is_empty and arena.turf_color is None:
            if card.is_chameleon:
                arena.turf_color = chameleon_turf_choice or player.command_factions[0]
            else:
                arena.turf_color = card.faction

        # Place monster
        new_slot = ArenaSlot(card=card, owner=player.id)
        arena.slots.append(new_slot)
        player.monsters_played_this_round += 1

        # Track for Yellow Fast Start (store reference to the actual slot)
        fast_count = self.faction_cfg["YELLOW"].get("fast_start_count", 2)
        if len(self._yellow_early_monsters[player.id]) < fast_count:
            self._yellow_early_monsters[player.id].append(new_slot)

        self._log_msg(f"P{player.id} plays {card} to {arena.name} (turf={arena.turf_color})")

        # Check for Crowd Roar
        roar_result = None
        self._pop_trigger_player = player.id
        if arena.monster_count >= self.rules["arena_roar_threshold"]:
            roar_result = self._crowd_roars(arena)

        # Draw a card (if draw pile not empty) — but pop_tax may prevent this
        drew_card = None
        skip_draw = False
        if self.pop_tax and roar_result is not None:
            skip_draw = True

        if not skip_draw and not self.draw_pile.empty:
            drew_card = self.draw_pile.draw_one()
            player.hand.append(drew_card)

        # High dopamine: extra draw if you triggered the roar
        if self.high_dopamine and roar_result is not None and not self.draw_pile.empty:
            extra = self.draw_pile.draw_one()
            player.hand.append(extra)

        return {
            "success": True,
            "action": "play_monster",
            "card": card,
            "arena": arena_name,
            "drew": drew_card,
            "roar": roar_result,
        }

    def action_fumble(self, player: Player, discard_card: Card) -> dict:
        """Fumble the Bag: discard 1, draw 1."""
        if not self.can_fumble(player):
            return {"success": False, "error": "No fumbles remaining"}

        if discard_card not in player.hand:
            return {"success": False, "error": "Card not in hand"}

        player.hand.remove(discard_card)
        self.discard_pile.add_to_bottom(discard_card)
        player.fumbles_used += 1

        drew_card = None
        if not self.draw_pile.empty:
            drew_card = self.draw_pile.draw_one()
            player.hand.append(drew_card)

        self._log_msg(f"P{player.id} fumbles: discards {discard_card}, draws {drew_card}")
        return {
            "success": True,
            "action": "fumble",
            "discarded": discard_card,
            "drew": drew_card,
        }

    def action_bench(self, player: Player, discard_card: Card) -> dict:
        """The Bench (forced pass): discard 1, draw 1."""
        if not self.is_benched(player):
            return {"success": False, "error": "Not benched — can still play or fumble"}

        if discard_card not in player.hand:
            return {"success": False, "error": "Card not in hand"}

        player.hand.remove(discard_card)
        self.discard_pile.add_to_bottom(discard_card)

        drew_card = None
        if not self.draw_pile.empty:
            drew_card = self.draw_pile.draw_one()
            player.hand.append(drew_card)

        self._log_msg(f"P{player.id} benched: discards {discard_card}, draws {drew_card}")
        return {
            "success": True,
            "action": "bench",
            "discarded": discard_card,
            "drew": drew_card,
        }

    # -----------------------------------------------------------------------
    # Green Personality: peek before playing
    # -----------------------------------------------------------------------

    def action_green_peek(self, player: Player, discard_it: bool) -> dict:
        """
        Green personality: look at top card, put back or discard.
        Must be called before playing a monster on the same turn.
        """
        if not player.has_faction("GREEN"):
            return {"success": False, "error": "No GREEN faction"}
        if self.draw_pile.empty:
            return {"success": False, "error": "Draw pile empty"}

        top = self.draw_pile.peek(1)[0]
        if discard_it:
            self.draw_pile.draw_one()
            self.discard_pile.add_to_bottom(top)
            self._log_msg(f"P{player.id} GREEN peek: discards {top}")
        else:
            self._log_msg(f"P{player.id} GREEN peek: keeps {top} on top")

        return {"success": True, "action": "green_peek", "card": top, "discarded": discard_it}

    # -----------------------------------------------------------------------
    # Blue Personality: bounce own monster
    # -----------------------------------------------------------------------

    def action_blue_bounce(self, player: Player, arena_name: str,
                           bounce_card: Card) -> dict:
        """
        Blue personality: return one of your other monsters from this arena
        to your hand.  Called right after playing a Blue card.
        """
        arena = self.get_arena(arena_name)
        # Find the slot to bounce (must be player's, not the blue just played)
        target_slot = None
        for s in arena.slots:
            if s.owner == player.id and s.card == bounce_card:
                target_slot = s
                break

        if target_slot is None:
            return {"success": False, "error": "Target not found in arena"}

        arena.slots.remove(target_slot)
        player.hand.append(bounce_card)
        self._log_msg(f"P{player.id} BLUE bounces {bounce_card} from {arena_name}")
        return {"success": True, "action": "blue_bounce", "card": bounce_card}

    # -----------------------------------------------------------------------
    # Signature Moves
    # -----------------------------------------------------------------------

    def can_use_signature(self, player: Player, faction: str) -> bool:
        """Check if the player can use this faction's signature this turn/round/game."""
        if self.signature_used_this_turn:
            return False  # max 1 signature per turn
        if not player.has_faction(faction):
            return False

        limit = self.faction_cfg[faction]["signature_limit"]
        if limit == "per_round":
            return not player.signature_used.get(faction, False)
        elif limit == "per_game":
            if faction == "ORANGE":
                return not player.big_borrow_used
        return False

    def sig_red_heroic_intervention(self, player: Player, source_arena_name: str,
                                     target_arena_name: str,
                                     monster_card: Card) -> dict:
        """
        RED Signature: Move one of your monsters from an adjacent arena
        into the arena where you just played Red.
        """
        if not self.can_use_signature(player, "RED"):
            return {"success": False, "error": "Cannot use RED signature"}

        # Validate adjacency
        if source_arena_name not in self.adjacent_arenas(target_arena_name):
            return {"success": False, "error": "Arenas not adjacent"}

        source = self.get_arena(source_arena_name)
        target = self.get_arena(target_arena_name)

        # Find monster in source arena
        slot = None
        for s in source.slots:
            if s.owner == player.id and s.card == monster_card:
                slot = s
                break
        if slot is None:
            return {"success": False, "error": "Monster not in source arena"}

        # Check legality in target arena
        if not self.can_play_to_arena(monster_card, target, player):
            return {"success": False, "error": "Monster can't enter target arena"}

        # Move
        source.slots.remove(slot)
        target.slots.append(ArenaSlot(card=monster_card, owner=player.id))
        player.signature_used["RED"] = True
        self.signature_used_this_turn = True

        self._log_msg(f"P{player.id} RED Heroic Intervention: moves {monster_card} from {source_arena_name} to {target_arena_name}")

        # Check roar in target
        roar_result = None
        if target.monster_count >= self.rules["arena_roar_threshold"]:
            roar_result = self._crowd_roars(target)

        return {"success": True, "action": "sig_red", "moved": monster_card, "roar": roar_result}

    def sig_orange_big_borrow(self, player: Player, arena: Arena,
                               steal_card: Card) -> dict:
        """
        ORANGE Signature (ONCE PER GAME): When you lose an arena by 3 or less,
        take one rank 1-5 monster as trophy.
        This is called during arena scoring resolution.
        """
        if player.big_borrow_used:
            return {"success": False, "error": "Already used Big Borrow"}

        cfg = self.faction_cfg["ORANGE"]
        lo, hi = cfg["borrow_rank_range"]
        if not (lo <= steal_card.rank <= hi):
            return {"success": False, "error": f"Rank {steal_card.rank} not in {lo}-{hi}"}

        # Steal it
        player.trophy_pile.append(steal_card)
        player.big_borrow_used = True
        player.signature_used["ORANGE"] = True
        self.signature_used_this_turn = True

        self._log_msg(f"P{player.id} ORANGE Big Borrow: steals {steal_card} as trophy")
        return {"success": True, "action": "sig_orange", "stolen": steal_card}

    def sig_yellow_double_install(self, player: Player, arena_name: str,
                                   second_card: Card,
                                   chameleon_turf_choice: Optional[str] = None) -> dict:
        """
        YELLOW Signature: Play a second monster to the same arena, then draw 1.
        """
        if not self.can_use_signature(player, "YELLOW"):
            return {"success": False, "error": "Cannot use YELLOW signature"}

        arena = self.get_arena(arena_name)

        # If the arena already roared from the first play, cannot double-install
        if arena.monster_count >= self.rules["arena_roar_threshold"]:
            return {"success": False, "error": "Arena already at roar threshold"}

        if not self.can_play_to_arena(second_card, arena, player):
            return {"success": False, "error": f"Cannot play {second_card} to {arena_name}"}

        if second_card not in player.hand:
            return {"success": False, "error": "Card not in hand"}

        player.hand.remove(second_card)
        if second_card.is_chameleon:
            player.chameleons_played += 1

        arena.slots.append(ArenaSlot(card=second_card, owner=player.id))
        player.monsters_played_this_round += 1

        player.signature_used["YELLOW"] = True
        self.signature_used_this_turn = True

        self._log_msg(f"P{player.id} YELLOW Double-Install: plays {second_card} to {arena_name}")

        # Check roar
        roar_result = None
        self._pop_trigger_player = player.id
        if arena.monster_count >= self.rules["arena_roar_threshold"]:
            roar_result = self._crowd_roars(arena)

        # Draw 1
        drew_card = None
        if not self.draw_pile.empty:
            drew_card = self.draw_pile.draw_one()
            player.hand.append(drew_card)

        return {"success": True, "action": "sig_yellow", "card": second_card, "roar": roar_result, "drew": drew_card}

    def sig_green_scheduled_outcome(self, player: Player) -> dict:
        """GREEN Signature: Draw 2, keep 1, discard 1. AI chooses which to keep."""
        if not self.can_use_signature(player, "GREEN"):
            return {"success": False, "error": "Cannot use GREEN signature"}

        drawn = self.draw_pile.draw(min(2, self.draw_pile.size))
        player.signature_used["GREEN"] = True
        self.signature_used_this_turn = True

        self._log_msg(f"P{player.id} GREEN Scheduled Outcome: drew {drawn}")
        # Return drawn cards — AI will choose which to keep
        return {"success": True, "action": "sig_green", "drawn": drawn}

    def sig_green_keep_choice(self, player: Player, keep_card: Card,
                               discard_card: Card) -> dict:
        """Resolve green scheduled outcome choice."""
        player.hand.append(keep_card)
        self.discard_pile.add_to_bottom(discard_card)
        self._log_msg(f"P{player.id} GREEN keeps {keep_card}, discards {discard_card}")
        return {"success": True}

    def sig_blue_swap(self, player: Player, arena_name: str,
                       my_card: Card, their_card: Card) -> dict:
        """
        BLUE Signature: Swap one of your monsters with opponent's in same arena.
        Ranks must be within 2.
        """
        if not self.can_use_signature(player, "BLUE"):
            return {"success": False, "error": "Cannot use BLUE signature"}

        arena = self.get_arena(arena_name)
        max_diff = self.faction_cfg["BLUE"]["swap_rank_range"]
        if abs(my_card.rank - their_card.rank) > max_diff:
            return {"success": False, "error": f"Rank diff > {max_diff}"}

        # Find slots
        my_slot = None
        their_slot = None
        opp_id = 1 - player.id
        for s in arena.slots:
            if s.owner == player.id and s.card == my_card:
                my_slot = s
            if s.owner == opp_id and s.card == their_card:
                their_slot = s

        if my_slot is None or their_slot is None:
            return {"success": False, "error": "Cards not found in arena"}

        # Swap ownership
        my_slot.card, their_slot.card = their_slot.card, my_slot.card

        player.signature_used["BLUE"] = True
        self.signature_used_this_turn = True

        self._log_msg(f"P{player.id} BLUE Swap: {my_card} <-> {their_card} in {arena_name}")
        return {"success": True, "action": "sig_blue", "gave": my_card, "got": their_card}

    def sig_purple_rewind(self, player: Player) -> dict:
        """
        PURPLE Signature: Take top card of discard if rank 1-6.
        Cannot take a card you just discarded this moment.
        """
        if not self.can_use_signature(player, "PURPLE"):
            return {"success": False, "error": "Cannot use PURPLE signature"}

        if self.discard_pile.empty:
            return {"success": False, "error": "Discard pile empty"}

        top = self.discard_pile.cards[-1]  # top of discard = last added
        lo, hi = self.faction_cfg["PURPLE"]["rewind_rank_range"]
        if not (lo <= top.rank <= hi):
            return {"success": False, "error": f"Top discard {top} rank not in {lo}-{hi}"}

        self.discard_pile.cards.pop()
        player.hand.append(top)
        player.signature_used["PURPLE"] = True
        self.signature_used_this_turn = True

        self._log_msg(f"P{player.id} PURPLE Rewind: takes {top} from discard")
        return {"success": True, "action": "sig_purple", "card": top}

    # -----------------------------------------------------------------------
    # Crowd Roars (arena scoring)
    # -----------------------------------------------------------------------

    def _compute_effective_ranks(self, arena: Arena):
        """Apply personality bonuses for scoring."""
        for s in arena.slots:
            s.effective_rank = s.card.rank

        for pid in range(2):
            player = self.players[pid]
            p_slots = arena.player_slots(pid)

            # RED Bodyguard: highest-rank monster gets +1, but only if
            # the player has 2+ monsters in this arena (requires investment)
            if player.has_faction("RED"):
                min_monsters = self.faction_cfg["RED"].get("bodyguard_min_monsters", 1)
                if len(p_slots) >= min_monsters and p_slots:
                    best = max(p_slots, key=lambda s: s.card.rank)
                    best.effective_rank += self.faction_cfg["RED"]["personality_bonus"]

            # ORANGE Dibs Mine: first Orange in arena with no other Orange gets +1
            if player.has_faction("ORANGE"):
                orange_slots = [s for s in p_slots if s.card.faction == "ORANGE"]
                opp_oranges = [s for s in arena.player_slots(1 - pid)
                               if s.card.faction == "ORANGE"]
                if orange_slots and not opp_oranges:
                    orange_slots[0].effective_rank += self.faction_cfg["ORANGE"]["personality_bonus"]

            # YELLOW Fast Start: +1 to each of the first N monsters played this round
            # (N from config, default 2). Applied to monsters tracked during play.
            if player.has_faction("YELLOW"):
                fast_count = self.faction_cfg["YELLOW"].get("fast_start_count", 2)
                bonus = self.faction_cfg["YELLOW"]["personality_bonus"]
                early = self._yellow_early_monsters.get(pid, [])[:fast_count]
                for early_slot in early:
                    # Find this slot in the current arena
                    for s in p_slots:
                        if s is early_slot:
                            s.effective_rank += bonus
                            break

        # Pop Bonus
        if self.pop_bonus and self._pop_trigger_player is not None:
            pid = self._pop_trigger_player
            p_slots = arena.player_slots(pid)
            if p_slots:
                target = min(p_slots, key=lambda s: s.effective_rank)
                target.effective_rank += self.pop_bonus_value

    def _crowd_roars(self, arena: Arena) -> dict:
        """Score an arena when it reaches 5 monsters."""
        self._log_msg(f"*** CROWD ROARS in {arena.name}! ***")

        # Compute effective ranks
        self._compute_effective_ranks(arena)

        # Sum ranks per player
        totals = {}
        for pid in range(2):
            slots = arena.player_slots(pid)
            totals[pid] = sum(s.effective_rank for s in slots)

        self._log_msg(f"  Totals: P0={totals[0]}, P1={totals[1]}")

        # Determine winner
        winner = None
        margin = abs(totals[0] - totals[1])
        if totals[0] > totals[1]:
            winner = 0
        elif totals[1] > totals[0]:
            winner = 1
        # else tie: nobody scores

        vp_awarded = 0
        if winner is not None:
            base_vp = self.rules["arena_win_vp"]
            # Center arena bonus: extra VP for winning the middle
            center_bonus = 0
            if arena.name == "Center" and self.center_bonus_vp > 0:
                center_bonus = self.center_bonus_vp
            vp_awarded = base_vp + center_bonus
            self.players[winner].vp += vp_awarded
            self.players[winner].arenas_won_this_round += 1
            self.total_arenas_won[winner] += 1
            self.last_scorer = winner

            # Track highest single-arena total for tiebreaker
            if totals[winner] > self.highest_arena_total[winner]:
                self.highest_arena_total[winner] = totals[winner]

            bonus_msg = f" (+{center_bonus} Center bonus)" if center_bonus else ""
            self._log_msg(f"  P{winner} wins {arena.name}! +{vp_awarded} VP{bonus_msg}")

            # ORANGE Big Borrow check (loser can steal if margin <= 3)
            loser = 1 - winner
            loser_player = self.players[loser]
            if (loser_player.has_faction("ORANGE") and
                not loser_player.big_borrow_used and
                margin <= self.faction_cfg["ORANGE"]["borrow_max_loss_margin"]):
                # Find stealable cards (rank 1-5 in this arena)
                lo, hi = self.faction_cfg["ORANGE"]["borrow_rank_range"]
                stealable = [s.card for s in arena.slots
                             if lo <= s.card.rank <= hi]
                if stealable:
                    # AI will choose which to steal — for now pick highest rank
                    steal = max(stealable, key=lambda c: c.rank)
                    self.sig_orange_big_borrow(loser_player, arena, steal)
        else:
            self._log_msg(f"  Tie in {arena.name} — nobody scores")

        # Check exact-15 tiebreaker tracking
        exact_15 = {}
        for pid in range(2):
            exact_15[pid] = (totals[pid] == self.rules["tiebreaker_target_rank"])

        # Clear arena
        cleared_cards = arena.clear()
        for c in cleared_cards:
            self.discard_pile.add_to_bottom(c)

        return {
            "arena": arena.name,
            "totals": totals,
            "winner": winner,
            "margin": margin,
            "vp_awarded": vp_awarded,
            "exact_15": exact_15,
        }

    # -----------------------------------------------------------------------
    # Yellow Fast Start tracker
    # -----------------------------------------------------------------------

    def is_first_monster_this_round(self, player: Player) -> bool:
        return player.monsters_played_this_round == 1  # just played the first one

    # -----------------------------------------------------------------------
    # End of Turn
    # -----------------------------------------------------------------------

    def end_turn(self) -> dict:
        """Advance to next player's turn. Reset per-turn flags."""
        self.signature_used_this_turn = False
        self.current_turn_in_round += 1
        self.current_player_idx = 1 - self.current_player_idx

        result = {"round_ended": False}

        # Check if round is over (both players took 6 turns = 12 total turns)
        total_turns = self.rules["turns_per_round_per_player"] * 2
        if self.current_turn_in_round >= total_turns:
            result = self._end_round()

        return result

    # -----------------------------------------------------------------------
    # End of Round
    # -----------------------------------------------------------------------

    def _end_round(self) -> dict:
        """Score remaining arenas, award momentum, reset for next round."""
        self._log_msg(f"=== End of Round {self.current_round + 1} ===")

        round_results = {"round_ended": True, "arena_scores": [], "momentum": {}}

        # Score any unscored arenas
        for arena in self.arenas:
            if not arena.is_empty:
                result = self._crowd_roars(arena)
                round_results["arena_scores"].append(result)

        # Momentum: +1 VP if a player won 2+ arenas this round
        for p in self.players:
            if p.arenas_won_this_round >= self.rules["momentum_threshold"]:
                p.vp += self.rules["momentum_vp"]
                round_results["momentum"][p.id] = True
                self._log_msg(f"P{p.id} earns Momentum! +{self.rules['momentum_vp']} VP")

        # Purple Time Capsule: keep N cards (from config)
        keep_count = self.faction_cfg["PURPLE"].get("time_capsule_keep", 1)
        for p in self.players:
            if p.has_faction("PURPLE") and p.hand:
                # Keep the N highest-rank cards
                sorted_hand = sorted(p.hand, key=lambda c: c.rank, reverse=True)
                kept = sorted_hand[:min(keep_count, len(sorted_hand))]
                discarded = sorted_hand[min(keep_count, len(sorted_hand)):]
                for c in discarded:
                    self.discard_pile.add_to_bottom(c)
                p.hand = kept
                self._log_msg(f"P{p.id} PURPLE Time Capsule: keeps {kept}")
            else:
                # Discard entire hand
                for c in p.hand:
                    self.discard_pile.add_to_bottom(c)
                p.hand = []

        # Advance round
        self.current_round += 1

        if self.current_round >= self.rules["rounds"]:
            self._end_game()
        else:
            # Deal new hands
            self._prepare_new_round()

        return round_results

    def _prepare_new_round(self):
        """Reset per-round trackers and deal new hands."""
        for p in self.players:
            p.reset_round()

        # Reset Yellow Fast Start tracking
        self._yellow_early_monsters = {0: [], 1: []}

        # Alternate start player
        self.start_player = 1 - self.start_player
        self.current_player_idx = self.start_player
        self.current_turn_in_round = 0

        # Deal 6 cards
        # If not enough cards, shuffle discard into draw pile
        if self.draw_pile.size < self.rules["cards_per_hand"] * 2:
            self.draw_pile.add_to_bottom(self.discard_pile.cards)
            self.discard_pile.cards = []
            self.draw_pile.shuffle(self.rng)

        self.deal_hands()
        self._log_msg(f"=== Round {self.current_round + 1} begins (P{self.start_player} starts) ===")

    def _end_game(self):
        """Determine winner with cascading tiebreaker."""
        self.game_over = True

        scores = {p.id: p.total_vp for p in self.players}
        self._log_msg(f"GAME OVER — P0: {scores[0]} VP, P1: {scores[1]} VP")

        if scores[0] > scores[1]:
            self.winner = 0
        elif scores[1] > scores[0]:
            self.winner = 1
        else:
            # Cascading tiebreaker
            self._log_msg("VP tied — applying tiebreakers...")

            # Tiebreaker 1: Most total arenas won across the game
            aw0, aw1 = self.total_arenas_won[0], self.total_arenas_won[1]
            if aw0 > aw1:
                self.winner = 0
                self._log_msg(f"  Tiebreaker (arenas won): P0 {aw0} > P1 {aw1}")
            elif aw1 > aw0:
                self.winner = 1
                self._log_msg(f"  Tiebreaker (arenas won): P1 {aw1} > P0 {aw0}")
            else:
                # Tiebreaker 2: Highest single-arena rank total
                ha0, ha1 = self.highest_arena_total[0], self.highest_arena_total[1]
                if ha0 > ha1:
                    self.winner = 0
                    self._log_msg(f"  Tiebreaker (best arena): P0 {ha0} > P1 {ha1}")
                elif ha1 > ha0:
                    self.winner = 1
                    self._log_msg(f"  Tiebreaker (best arena): P1 {ha1} > P0 {ha0}")
                else:
                    # Tiebreaker 3: Most recent scorer
                    if self.last_scorer is not None:
                        self.winner = self.last_scorer
                        self._log_msg(f"  Tiebreaker (last scorer): P{self.last_scorer}")
                    else:
                        self.winner = None
                        self._log_msg("  All tiebreakers exhausted — true draw")

        if self.winner is not None:
            self._log_msg(f"P{self.winner} wins!")

    # -----------------------------------------------------------------------
    # Full setup convenience
    # -----------------------------------------------------------------------

    def full_setup(self, draft_fn=None):
        """Run complete setup: faction draft + deal hands."""
        self.faction_draft(draft_fn=draft_fn)
        self.deal_hands()
        self._log_msg(f"=== Round 1 begins (P{self.start_player} starts) ===")
