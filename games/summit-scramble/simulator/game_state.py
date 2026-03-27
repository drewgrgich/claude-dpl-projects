"""
Summit Scramble game state machine.

Handles the full game: trick-taking with formations, faction abilities,
interrupts (Confetti Cannon, Trip-Up), going out, and multi-round championship.
"""

import random
import json
import os
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Callable
from collections import defaultdict

from cards import Card, Deck, build_full_deck, FACTIONS, FACTION_RANK, FACTION_ABILITIES


# ---------------------------------------------------------------------------
# Formation types
# ---------------------------------------------------------------------------

class FormationType:
    SOLO = "solo"
    SURGE = "surge"
    DAISY_CHAIN = "daisy_chain"
    CONFETTI_CANNON = "confetti_cannon"
    TRIP_UP = "trip_up"


@dataclass
class Formation:
    """A played formation of cards."""
    ftype: str
    cards: List[Card]
    rank: int  # effective rank for comparison (top card for chains, set rank for surges)
    length: int  # number of cards (matters for chains and surges)
    faction: Optional[str] = None  # relevant for solo tie-breaks, chosen for cannon

    @property
    def triggers_power(self) -> bool:
        return self.rank >= 6

    def __repr__(self):
        card_str = " ".join(repr(c) for c in self.cards)
        return f"{self.ftype}[{card_str}]"


def classify_formation(cards: List[Card]) -> Optional[Formation]:
    """
    Classify a set of cards as a valid formation, or None if invalid.
    Does NOT handle Trip-Up (that's context-dependent).
    """
    if not cards:
        return None

    n = len(cards)
    ranks = sorted(c.rank for c in cards)
    unique_ranks = set(ranks)

    # Solo Sprint
    if n == 1:
        c = cards[0]
        return Formation(
            ftype=FormationType.SOLO,
            cards=list(cards),
            rank=c.rank,
            length=1,
            faction=c.faction,
        )

    # Confetti Cannon (4 of a kind)
    if n == 4 and len(unique_ranks) == 1:
        return Formation(
            ftype=FormationType.CONFETTI_CANNON,
            cards=list(cards),
            rank=ranks[0],
            length=4,
            faction=None,  # chosen by player when triggering
        )

    # Surge (2 or 3 of same rank)
    if n in (2, 3) and len(unique_ranks) == 1:
        return Formation(
            ftype=FormationType.SURGE,
            cards=list(cards),
            rank=ranks[0],
            length=n,
        )

    # Daisy Chain (3+ consecutive ranks)
    if n >= 3:
        if len(unique_ranks) == n and (max(ranks) - min(ranks) == n - 1):
            return Formation(
                ftype=FormationType.DAISY_CHAIN,
                cards=sorted(cards, key=lambda c: c.rank),
                rank=max(ranks),  # top card determines comparison
                length=n,
            )

    return None


def formation_beats(attacker: Formation, defender: Formation) -> bool:
    """Does the attacker formation beat the defender? Same type required."""
    if attacker.ftype != defender.ftype:
        return False

    if attacker.ftype == FormationType.SOLO:
        if attacker.rank > defender.rank:
            return True
        if attacker.rank == defender.rank:
            return FACTION_RANK[attacker.faction] < FACTION_RANK[defender.faction]
        return False

    if attacker.ftype == FormationType.SURGE:
        if attacker.length != defender.length:
            return False
        return attacker.rank > defender.rank

    if attacker.ftype == FormationType.DAISY_CHAIN:
        if attacker.length != defender.length:
            return False
        return attacker.rank > defender.rank

    if attacker.ftype == FormationType.CONFETTI_CANNON:
        if attacker.rank > defender.rank:
            return True
        if attacker.rank == defender.rank:
            # Tie-break by faction hierarchy of chosen faction
            if attacker.faction and defender.faction:
                return FACTION_RANK[attacker.faction] < FACTION_RANK[defender.faction]
        return False

    return False


# ---------------------------------------------------------------------------
# Player
# ---------------------------------------------------------------------------

@dataclass
class Player:
    pid: int
    hand: List[Card] = field(default_factory=list)
    finished: bool = False
    finish_position: int = -1
    stored_surge: Optional[Card] = None  # advanced rule

    @property
    def hand_size(self) -> int:
        return len(self.hand)

    @property
    def is_out(self) -> bool:
        return self.finished

    def remove_cards(self, cards: List[Card]):
        for c in cards:
            self.hand.remove(c)

    def __repr__(self):
        return f"P{self.pid}({len(self.hand)}cards{'*' if self.finished else ''})"


# ---------------------------------------------------------------------------
# Game State
# ---------------------------------------------------------------------------

class GameState:
    """Full state machine for one round of Summit Scramble."""

    def __init__(self, config: dict, num_players: int, seed: int = 42,
                 use_stored_surge: bool = False,
                 hand_size_overrides: Dict[int, int] = None):
        self.config = config
        self.rules = config["game_rules"]
        self.num_players = num_players
        self.rng = random.Random(seed)
        self.seed = seed
        self.pkey = f"{num_players}_player"
        self.use_stored_surge = use_stored_surge
        self.hand_size_overrides = hand_size_overrides or {}

        # Build deck
        all_cards = build_full_deck()
        self.trail = Deck(all_cards)
        self.trail.shuffle(self.rng)
        self.base_camp = Deck()  # discard pile

        # Players
        self.players: List[Player] = []
        self.finish_order: List[int] = []
        self.current_leader_idx: int = 0

        # Trick state
        self.current_formation: Optional[Formation] = None
        self.current_trick_cards: List[List[Card]] = []  # all cards played this trick
        self.trick_winner_idx: int = -1
        self.passed_players: set = set()  # pids who passed this trick

        # Rotation tracking (for 3-player alternation rule)
        self.last_rotation_direction: Optional[str] = None

        # Game flags
        self.round_over: bool = False
        self.active_player_count: int = num_players

        # Logging
        self.log: List[str] = []

        # Stats tracking
        self.turn_count: int = 0
        self.trick_count: int = 0
        self.tricks_per_player: Dict[int, int] = defaultdict(int)
        self.formations_played: Dict[str, int] = defaultdict(int)
        self.abilities_triggered: Dict[str, int] = defaultdict(int)
        self.cannons_fired: int = 0
        self.trip_ups: int = 0
        self.cards_played_per_player: Dict[int, int] = defaultdict(int)

    def setup(self):
        """Deal starting hands (with optional per-seat overrides)."""
        base_hand_size = self.rules["starting_hand"][self.pkey]
        for i in range(self.num_players):
            hand_size = self.hand_size_overrides.get(i, base_hand_size)
            hand = self.trail.draw(hand_size)
            p = Player(pid=i, hand=hand)
            self.players.append(p)
        sizes = [self.hand_size_overrides.get(i, base_hand_size)
                 for i in range(self.num_players)]
        self._log(f"Dealt hands {sizes} to {self.num_players} players. "
                  f"Trail has {self.trail.size} cards remaining.")

    def _log(self, msg: str):
        self.log.append(msg)

    # -------------------------------------------------------------------
    # Trail / Base Camp management
    # -------------------------------------------------------------------

    def _ensure_trail(self, needed: int = 1):
        """If trail can't supply needed cards, reshuffle base camp into trail."""
        if self.trail.size < needed and self.base_camp.size > 0:
            reshuffled = self.base_camp.cards[:]
            self.base_camp.cards.clear()
            self.trail.add_to_bottom(reshuffled)
            self.trail.shuffle(self.rng)
            self._log(f"Trail exhausted — reshuffled {len(reshuffled)} cards from Base Camp.")

    def _draw_from_trail(self, n: int = 1) -> List[Card]:
        self._ensure_trail(n)
        return self.trail.draw(min(n, self.trail.size))

    # -------------------------------------------------------------------
    # Active players (not finished)
    # -------------------------------------------------------------------

    def get_active_players(self) -> List[Player]:
        return [p for p in self.players if not p.finished]

    def get_active_pids(self) -> List[int]:
        return [p.pid for p in self.players if not p.finished]

    def _next_active_player(self, from_idx: int) -> int:
        """Find next active (not finished) player clockwise from from_idx."""
        for offset in range(1, self.num_players + 1):
            idx = (from_idx + offset) % self.num_players
            if not self.players[idx].finished:
                return idx
        return from_idx

    # -------------------------------------------------------------------
    # Formation validation helpers
    # -------------------------------------------------------------------

    def get_legal_formations(self, player: Player) -> List[Formation]:
        """Get all legal formations player can play given current trick state."""
        hand = player.hand
        formations = []

        if self.current_formation is None:
            # Leading: can play any valid formation
            formations.extend(self._all_possible_formations(hand))
        else:
            # Following: must match type and beat current
            formations.extend(self._matching_formations(hand, self.current_formation))

        return formations

    def get_interrupt_formations(self, player: Player) -> List[Formation]:
        """Get interrupt plays available (Trip-Ups only — Cannons are no longer interrupts)."""
        interrupts = []

        # Confetti Cannon: NO LONGER an interrupt.
        # Cannons are now lead/follow only (handled by get_legal_formations).

        # Trip-Up: single 0 can beat solo 10 (the only interrupt mechanic)
        if (self.current_formation and
            self.current_formation.ftype == FormationType.SOLO and
            self.current_formation.rank == 10):
            zeros = [c for c in player.hand if c.rank == 0]
            for z in zeros:
                interrupts.append(Formation(
                    ftype=FormationType.TRIP_UP,
                    cards=[z],
                    rank=0,
                    length=1,
                    faction=z.faction,
                ))

        return interrupts

    def _all_possible_formations(self, hand: List[Card]) -> List[Formation]:
        """All valid formations from hand (for leading)."""
        formations = []
        by_rank = defaultdict(list)
        for c in hand:
            by_rank[c.rank].append(c)

        # Solos
        for c in hand:
            formations.append(Formation(
                ftype=FormationType.SOLO, cards=[c],
                rank=c.rank, length=1, faction=c.faction))

        # Surges (pairs and triples)
        for rank, cards in by_rank.items():
            if len(cards) >= 2:
                # All pairs
                for i in range(len(cards)):
                    for j in range(i + 1, len(cards)):
                        formations.append(Formation(
                            ftype=FormationType.SURGE, cards=[cards[i], cards[j]],
                            rank=rank, length=2))
                # All triples
                if len(cards) >= 3:
                    for i in range(len(cards)):
                        for j in range(i + 1, len(cards)):
                            for k in range(j + 1, len(cards)):
                                formations.append(Formation(
                                    ftype=FormationType.SURGE,
                                    cards=[cards[i], cards[j], cards[k]],
                                    rank=rank, length=3))

            # Confetti Cannon
            if len(cards) >= 4:
                formations.append(Formation(
                    ftype=FormationType.CONFETTI_CANNON, cards=cards[:4],
                    rank=rank, length=4))

        # Daisy Chains (runs of 3+)
        sorted_ranks = sorted(by_rank.keys())
        for start_idx in range(len(sorted_ranks)):
            chain_ranks = [sorted_ranks[start_idx]]
            for next_idx in range(start_idx + 1, len(sorted_ranks)):
                if sorted_ranks[next_idx] == chain_ranks[-1] + 1:
                    chain_ranks.append(sorted_ranks[next_idx])
                    if len(chain_ranks) >= 3:
                        # Pick one card per rank for this chain
                        chain_cards = [by_rank[r][0] for r in chain_ranks]
                        formations.append(Formation(
                            ftype=FormationType.DAISY_CHAIN,
                            cards=chain_cards,
                            rank=chain_ranks[-1],
                            length=len(chain_ranks)))
                else:
                    break

        return formations

    def _matching_formations(self, hand: List[Card],
                             current: Formation) -> List[Formation]:
        """Formations that beat the current formation."""
        candidates = self._all_possible_formations(hand)
        return [f for f in candidates
                if f.ftype == current.ftype and formation_beats(f, current)]

    def _find_cannons(self, hand: List[Card]) -> List[Formation]:
        by_rank = defaultdict(list)
        for c in hand:
            by_rank[c.rank].append(c)
        cannons = []
        for rank, cards in by_rank.items():
            if len(cards) >= 4:
                cannons.append(Formation(
                    ftype=FormationType.CONFETTI_CANNON,
                    cards=cards[:4], rank=rank, length=4))
        return cannons

    # -------------------------------------------------------------------
    # Play actions
    # -------------------------------------------------------------------

    def play_formation(self, player: Player, formation: Formation) -> dict:
        """Player plays a formation (lead or follow)."""
        # Remove cards from hand
        player.remove_cards(formation.cards)
        self.current_trick_cards.append(formation.cards)
        self.cards_played_per_player[player.pid] += len(formation.cards)
        self.formations_played[formation.ftype] += 1

        # Check going out
        if player.hand_size == 0:
            return self._player_goes_out(player, formation)

        # Update trick state
        self.current_formation = formation
        self.trick_winner_idx = player.pid

        self._log(f"P{player.pid} plays {formation}")
        return {"success": True, "went_out": False, "formation": formation}

    def play_interrupt(self, player: Player, formation: Formation) -> dict:
        """Player fires a Cannon or Trip-Up interrupt."""
        player.remove_cards(formation.cards)
        self.current_trick_cards.append(formation.cards)
        self.cards_played_per_player[player.pid] += len(formation.cards)
        self.formations_played[formation.ftype] += 1

        if formation.ftype == FormationType.CONFETTI_CANNON:
            self.cannons_fired += 1
        elif formation.ftype == FormationType.TRIP_UP:
            self.trip_ups += 1

        # Check going out
        if player.hand_size == 0:
            return self._player_goes_out(player, formation)

        self.current_formation = formation
        self.trick_winner_idx = player.pid

        self._log(f"P{player.pid} interrupts with {formation}")
        return {"success": True, "went_out": False, "interrupt": True,
                "formation": formation, "ends_trick": True}

    def player_passes(self, player: Player) -> dict:
        """Player passes on current trick."""
        self.passed_players.add(player.pid)
        self._log(f"P{player.pid} passes")
        return {"success": True, "passed": True}

    def _player_goes_out(self, player: Player, formation: Formation) -> dict:
        """Handle a player emptying their hand (reaching The Summit)."""
        player.finished = True
        self.finish_order.append(player.pid)
        pos = len(self.finish_order)
        player.finish_position = pos
        self.active_player_count -= 1

        self._log(f"P{player.pid} REACHES THE SUMMIT (position {pos})!")

        # Trick ends instantly — no interrupts allowed
        return {
            "success": True,
            "went_out": True,
            "finish_position": pos,
            "formation": formation,
            "ends_trick": True,
        }

    # -------------------------------------------------------------------
    # Trick resolution
    # -------------------------------------------------------------------

    def resolve_trick(self) -> dict:
        """Resolve completed trick: discard to base camp, check power."""
        winner_pid = self.trick_winner_idx
        winner = self.players[winner_pid]
        winning_formation = self.current_formation

        # All trick cards to Base Camp
        for card_list in self.current_trick_cards:
            for c in card_list:
                self.base_camp.add_to_bottom(c)

        self.tricks_per_player[winner_pid] += 1
        self.trick_count += 1

        result = {
            "winner": winner_pid,
            "formation": winning_formation,
            "power_triggered": False,
            "ability": None,
        }

        # Power check: rank 6+ triggers faction ability
        if winning_formation and winning_formation.triggers_power and not winner.finished:
            ability = self._get_ability_for_formation(winning_formation)
            result["power_triggered"] = True
            result["ability"] = ability

        # Reset trick state
        self.current_formation = None
        self.current_trick_cards = []
        self.trick_winner_idx = -1
        self.passed_players.clear()

        # Leader for next trick
        if winner.finished:
            # Player to winner's left leads
            self.current_leader_idx = self._next_active_player(winner_pid)
        else:
            self.current_leader_idx = winner_pid

        self._log(f"Trick won by P{winner_pid}. Next leader: P{self.current_leader_idx}")
        return result

    def _get_ability_for_formation(self, formation: Formation) -> str:
        """Determine which faction ability triggers."""
        if formation.ftype == FormationType.SOLO:
            return FACTION_ABILITIES[formation.faction]
        elif formation.ftype == FormationType.TRIP_UP:
            return None  # Trip-Up: tripped card doesn't trigger
        elif formation.ftype in (FormationType.SURGE, FormationType.CONFETTI_CANNON):
            # Player chooses faction — AI will decide, but return the options
            return "choose"  # caller (AI) picks
        elif formation.ftype == FormationType.DAISY_CHAIN:
            # Highest card in chain determines (it's the winning card)
            top_card = max(formation.cards, key=lambda c: c.rank)
            return FACTION_ABILITIES[top_card.faction]
        return None

    # -------------------------------------------------------------------
    # Faction abilities
    # -------------------------------------------------------------------

    def execute_ability(self, player: Player, ability: str,
                        ability_choices: dict = None) -> dict:
        """Execute a faction ability. ability_choices contains AI decisions."""
        if ability_choices is None:
            ability_choices = {}

        self.abilities_triggered[ability] += 1

        if ability == "rotation":
            result = self._ability_rotation(player, ability_choices)
        elif ability == "scout":
            result = self._ability_scout(player, ability_choices)
        elif ability == "streamline":
            result = self._ability_streamline(player, ability_choices)
        elif ability == "recalibrate":
            result = self._ability_recalibrate(player, ability_choices)
        elif ability == "revelation":
            result = self._ability_revelation(player, ability_choices)
        elif ability == "reclaim":
            result = self._ability_reclaim(player, ability_choices)
        else:
            return {"success": False, "error": f"Unknown ability: {ability}"}

        # EDGE CASE: Check if any player's hand was reduced to 0 by ability
        # (e.g., Streamline discards last card, Recalibrate nets -1)
        # Rules say "play your last card" = summit, but abilities can empty hands.
        # We flag this as an ability-finish (distinct from a played-out finish).
        for p in self.get_active_players():
            if p.hand_size == 0 and not p.finished:
                p.finished = True
                self.finish_order.append(p.pid)
                p.finish_position = len(self.finish_order)
                self.active_player_count -= 1
                self._log(f"P{p.pid} REACHES THE SUMMIT via ability "
                          f"(hand emptied by {ability})!")
                result["ability_finish"] = p.pid

        return result

    def _ability_rotation(self, player: Player, choices: dict) -> dict:
        """RED: All players pass 1 card in chosen direction."""
        direction = choices.get("direction", "left")

        # 3-player alternation rule
        if self.num_players == 3 and self.last_rotation_direction is not None:
            if direction == self.last_rotation_direction:
                direction = "right" if direction == "left" else "left"
        self.last_rotation_direction = direction

        # cards_to_pass: {pid: Card} chosen by AI
        cards_to_pass = choices.get("cards_to_pass", {})
        active = self.get_active_players()

        # Build pass map
        pass_map = {}  # pid -> card they're passing
        for p in active:
            if p.pid in cards_to_pass and cards_to_pass[p.pid] in p.hand:
                pass_map[p.pid] = cards_to_pass[p.pid]
            elif p.hand:
                # Fallback: pass worst card
                pass_map[p.pid] = min(p.hand, key=lambda c: c.rank)

        # Execute passes
        received = {}
        for p in active:
            if p.pid not in pass_map:
                continue
            card = pass_map[p.pid]
            if direction == "left":
                target = self._next_active_player(p.pid)
            else:
                # Find previous active player
                target = self._prev_active_player(p.pid)
            p.hand.remove(card)
            received.setdefault(target, []).append(card)

        for pid, cards in received.items():
            self.players[pid].hand.extend(cards)

        self._log(f"ROTATION ({direction}): all active players pass 1 card")
        return {"success": True, "ability": "rotation", "direction": direction}

    def _prev_active_player(self, from_pid: int) -> int:
        """Find previous active player counter-clockwise."""
        for offset in range(1, self.num_players + 1):
            idx = (from_pid - offset) % self.num_players
            if not self.players[idx].finished:
                return idx
        return from_pid

    def _ability_scout(self, player: Player, choices: dict) -> dict:
        """ORANGE: Look at top 2 of Trail, may swap 1 from hand."""
        self._ensure_trail(2)
        top_cards = self.trail.peek(min(2, self.trail.size))

        swap_from_hand = choices.get("swap_from_hand")  # Card to give
        swap_from_trail = choices.get("swap_from_trail")  # Card to take

        if swap_from_hand and swap_from_trail and swap_from_trail in top_cards:
            player.hand.remove(swap_from_hand)
            self.trail.remove(swap_from_trail)
            player.hand.append(swap_from_trail)
            self.trail.add_to_top(swap_from_hand)
            self._log(f"SCOUT: P{player.pid} swaps {swap_from_hand} for {swap_from_trail}")
        else:
            self._log(f"SCOUT: P{player.pid} peeks but keeps hand")

        return {"success": True, "ability": "scout", "peeked": top_cards}

    def _ability_streamline(self, player: Player, choices: dict) -> dict:
        """YELLOW: Discard 1 card from hand."""
        card = choices.get("discard")
        if card and card in player.hand:
            player.hand.remove(card)
            self.base_camp.add_to_bottom(card)
            self._log(f"STREAMLINE: P{player.pid} discards {card}")
        elif player.hand:
            worst = min(player.hand, key=lambda c: c.rank)
            player.hand.remove(worst)
            self.base_camp.add_to_bottom(worst)
            self._log(f"STREAMLINE: P{player.pid} discards {worst} (fallback)")
        return {"success": True, "ability": "streamline"}

    def _ability_recalibrate(self, player: Player, choices: dict) -> dict:
        """GREEN: Draw 1 from Trail, then discard 2 from hand."""
        drawn = self._draw_from_trail(1)
        if drawn:
            player.hand.extend(drawn)
            self._log(f"RECALIBRATE: P{player.pid} draws {drawn[0]}")

        discards = choices.get("discards", [])
        discarded = []
        for card in discards[:2]:
            if card in player.hand:
                player.hand.remove(card)
                self.base_camp.add_to_bottom(card)
                discarded.append(card)

        # Fallback: discard worst cards if AI didn't specify enough
        while len(discarded) < 2 and player.hand:
            worst = min(player.hand, key=lambda c: c.rank)
            player.hand.remove(worst)
            self.base_camp.add_to_bottom(worst)
            discarded.append(worst)

        self._log(f"RECALIBRATE: P{player.pid} discards {discarded}")
        return {"success": True, "ability": "recalibrate", "drawn": drawn,
                "discarded": discarded}

    def _ability_revelation(self, player: Player, choices: dict) -> dict:
        """BLUE: Target any other player — see hand, take 1, give 1."""
        target_pid = choices.get("target")
        if target_pid is None:
            # Find eligible targets (any other active player)
            eligible = [p for p in self.get_active_players()
                       if p.pid != player.pid and p.hand_size > 0]
            if not eligible:
                self._log(f"REVELATION: P{player.pid} has no valid targets")
                return {"success": False, "ability": "revelation",
                        "error": "no valid targets"}
            target_pid = eligible[0].pid

        target = self.players[target_pid]
        if target.finished or target.hand_size == 0:
            self._log(f"REVELATION: Invalid target P{target_pid} (finished or empty hand)")
            return {"success": False, "ability": "revelation",
                    "error": "target has no cards"}

        take_card = choices.get("take_card")
        give_card = choices.get("give_card")

        if take_card and take_card in target.hand and give_card and give_card in player.hand:
            target.hand.remove(take_card)
            player.hand.append(take_card)
            player.hand.remove(give_card)
            target.hand.append(give_card)
            self._log(f"REVELATION: P{player.pid} takes {take_card} from P{target_pid}, "
                      f"gives {give_card}")
        else:
            self._log(f"REVELATION: P{player.pid} reveals P{target_pid}'s hand but no swap")

        return {"success": True, "ability": "revelation", "target": target_pid,
                "target_hand": list(target.hand)}

    def _ability_reclaim(self, player: Player, choices: dict) -> dict:
        """PURPLE: Swap 1 from hand with any card in Base Camp."""
        take_card = choices.get("take_from_camp")
        give_card = choices.get("give_to_camp")

        if (take_card and give_card and
            take_card in self.base_camp.cards and give_card in player.hand):
            self.base_camp.remove(take_card)
            player.hand.append(take_card)
            player.hand.remove(give_card)
            self.base_camp.add_to_bottom(give_card)
            self._log(f"RECLAIM: P{player.pid} takes {take_card} from Base Camp, "
                      f"gives {give_card}")
        else:
            self._log(f"RECLAIM: P{player.pid} keeps hand (no valid swap)")

        return {"success": True, "ability": "reclaim"}

    # -------------------------------------------------------------------
    # Stored Surge (advanced)
    # -------------------------------------------------------------------

    def store_surge(self, player: Player, card: Card) -> dict:
        """Store a power-rank winning card for future double trigger."""
        if not self.use_stored_surge:
            return {"success": False, "error": "Stored Surge not enabled"}
        if player.stored_surge is not None:
            return {"success": False, "error": "Already have stored surge"}
        player.stored_surge = card
        self._log(f"P{player.pid} STORES {card} for future double surge")
        return {"success": True}

    def release_surge(self, player: Player) -> dict:
        """Release stored surge for double ability trigger."""
        if not player.stored_surge:
            return {"success": False, "error": "No stored surge"}
        card = player.stored_surge
        player.stored_surge = None
        self.base_camp.add_to_bottom(card)
        self._log(f"P{player.pid} RELEASES stored surge {card} — DOUBLE TRIGGER!")
        return {"success": True, "released_card": card}

    # -------------------------------------------------------------------
    # Round completion
    # -------------------------------------------------------------------

    def check_round_over(self) -> bool:
        """Check if all players have finished (or only 1 remains)."""
        active = self.get_active_players()
        if len(active) <= 1:
            # Last player auto-finishes
            for p in active:
                if not p.finished:
                    p.finished = True
                    self.finish_order.append(p.pid)
                    p.finish_position = len(self.finish_order)
            self.round_over = True
            return True
        return False

    def calculate_fatigue(self, mercy_rule: bool = True) -> Dict[int, int]:
        """Calculate fatigue for each player based on finish position."""
        fatigue_table = self.rules["fatigue"]
        fatigue = {}

        for p in self.players:
            pos = p.finish_position
            if pos == 1:
                f = fatigue_table["1st"]
            elif pos == 2:
                f = fatigue_table["2nd"]
            elif pos == 3:
                f = fatigue_table["3rd"]
            elif pos == 4:
                f = fatigue_table["4th"]
            else:
                # Last place
                f = fatigue_table["last_base"] + fatigue_table["last_per_card"] * p.hand_size

            if mercy_rule:
                f = min(f, self.rules["mercy_rule_cap"])

            fatigue[p.pid] = f

        return fatigue

    def get_stats(self) -> dict:
        """Compile end-of-round statistics."""
        return {
            "seed": self.seed,
            "num_players": self.num_players,
            "trick_count": self.trick_count,
            "turn_count": self.turn_count,
            "finish_order": list(self.finish_order),
            "tricks_per_player": dict(self.tricks_per_player),
            "formations_played": dict(self.formations_played),
            "abilities_triggered": dict(self.abilities_triggered),
            "cannons_fired": self.cannons_fired,
            "trip_ups": self.trip_ups,
            "cards_played_per_player": dict(self.cards_played_per_player),
            "remaining_cards": {p.pid: p.hand_size for p in self.players},
            "fatigue": self.calculate_fatigue(),
        }
