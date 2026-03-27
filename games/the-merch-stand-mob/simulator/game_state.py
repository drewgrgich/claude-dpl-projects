"""Game state machine for The Merch Stand Mob.

Handles simultaneous bidding, claim resolution, Mosh Pit management,
Trample checks, faction abilities, scoring, and game end conditions.
"""

import json
import os
import random
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Callable, Any
from collections import defaultdict

from cards import Card, Deck, build_full_deck, FACTION_COLORS, FACTIONS


@dataclass
class Bid:
    """A player's face-down bid for the round."""
    player_id: int
    primary: Card          # The bid card (determines claim priority)
    anchor: Optional[Card] = None  # Required for rank 0 and 10

    @property
    def is_wild(self) -> bool:
        return self.primary.is_wild

    @property
    def is_sneak(self) -> bool:
        return self.primary.is_sneak

    @property
    def is_shove(self) -> bool:
        return self.primary.is_shove

    @property
    def has_valid_anchor(self) -> bool:
        """Wilds need an anchor card with rank 1-9."""
        if not self.is_wild:
            return True  # Non-wilds don't need anchors
        if self.anchor is None:
            return False
        return 1 <= self.anchor.rank <= 9

    @property
    def effective_rank(self) -> int:
        """Rank used for claim ordering. Failed wilds bid as 0."""
        if self.is_wild and not self.has_valid_anchor:
            return 0  # Failed wild = lowest priority
        return self.primary.rank

    @property
    def cards_committed(self) -> List[Card]:
        """All cards committed in this bid."""
        if self.anchor:
            return [self.primary, self.anchor]
        return [self.primary]

    def __repr__(self):
        if self.anchor:
            return f"Bid(P{self.player_id}: {self.primary} + {self.anchor})"
        return f"Bid(P{self.player_id}: {self.primary})"


@dataclass
class Player:
    """Player state within a game."""
    id: int
    hand: List[Card] = field(default_factory=list)
    score_pile: List[Card] = field(default_factory=list)

    @property
    def hand_size(self) -> int:
        return len(self.hand)

    @property
    def vp(self) -> int:
        """Total VP: card ranks + set bonuses."""
        card_vp = sum(c.vp for c in self.score_pile)
        return card_vp + self.set_bonus_vp

    @property
    def unique_colors(self) -> int:
        """Number of distinct faction colors in score pile."""
        return len(set(c.faction for c in self.score_pile))

    def set_bonus_vp_with_config(self, set_bonus_config: dict = None) -> int:
        """VP from color set bonuses, driven by config.

        Default (no config): 3 colors = 5VP, 6 colors = +8VP.
        Config can specify mid_set_colors/mid_set_vp for intermediate bonus.
        """
        colors = self.unique_colors
        bonus = 0
        if set_bonus_config:
            if colors >= set_bonus_config.get("first_set_colors", 3):
                bonus += set_bonus_config.get("first_set_vp", 5)
            mid_colors = set_bonus_config.get("mid_set_colors", 0)
            if mid_colors > 0 and colors >= mid_colors:
                bonus += set_bonus_config.get("mid_set_vp", 0)
            if colors >= set_bonus_config.get("second_set_colors", 6):
                bonus += set_bonus_config.get("second_set_vp", 8)
        else:
            if colors >= 3:
                bonus += 5
            if colors >= 6:
                bonus += 8
        return bonus

    @property
    def set_bonus_vp(self) -> int:
        """VP from color set bonuses (default rules)."""
        return self.set_bonus_vp_with_config()

    @property
    def highest_card(self) -> int:
        """Highest single card rank in score pile (for tiebreaker)."""
        if not self.score_pile:
            return 0
        return max(c.rank for c in self.score_pile)

    @property
    def score_pile_count(self) -> int:
        return len(self.score_pile)

    def cards_of_faction(self, faction: str) -> List[Card]:
        """All scored cards of a given faction."""
        return [c for c in self.score_pile if c.faction == faction]

    def remove_faction_cards(self, faction: str) -> List[Card]:
        """Remove and return all scored cards of a faction (Trample)."""
        removed = [c for c in self.score_pile if c.faction == faction]
        self.score_pile = [c for c in self.score_pile if c.faction != faction]
        return removed

    def __repr__(self):
        return f"P{self.id}(VP:{self.vp} Hand:{self.hand_size} Scored:{self.score_pile_count})"


class GameState:
    """Full game state machine for The Merch Stand Mob."""

    def __init__(self, config: dict, num_players: int, seed: int = None):
        self.config = config
        self.rules = config["game_rules"]
        self.num_players = num_players
        self.pkey = f"{num_players}_player"
        self.rng = random.Random(seed)
        self.seed = seed

        # Build and shuffle the deck
        all_cards = build_full_deck()
        self.supply = Deck(all_cards)
        self.supply.shuffle(self.rng)

        # Game zones
        self.stand: List[Card] = []           # Available merch (face-up)
        self.mosh_pit: Dict[str, List[Card]] = {f: [] for f in FACTION_COLORS}
        self.discard: List[Card] = []

        # Players
        self.players: List[Player] = []

        # Game tracking
        self.round_number: int = 0
        self.game_over: bool = False
        self.end_reason: str = ""

        # Logging
        self.log: List[str] = []

        # Stats tracking
        self.stats = {
            "tramples": [],             # List of (round, faction) tuples
            "sneak_attempts": 0,
            "sneak_successes": 0,
            "shove_count": 0,
            "ties": 0,
            "abilities_triggered": defaultdict(int),
            "cards_trampled": defaultdict(int),  # Per player
            "claims_per_player": defaultdict(int),
        }

    # ─── SETUP ────────────────────────────────────────────────

    def setup(self):
        """Initialize the game: deal hands, fill the stand."""
        hand_size = self.rules["hand_size"][self.pkey]

        for i in range(self.num_players):
            hand = self.supply.draw(hand_size)
            self.players.append(Player(id=i, hand=hand))

        self._fill_stand()
        self._log(f"Game setup: {self.num_players} players, {hand_size} cards each, "
                  f"{self.supply.size} in supply")

    def setup_drop(self):
        """Initialize a Drop (championship) round: 6-card hands."""
        hand_size = self.config["the_drop"]["hand_size"]

        # Reset game zones but keep player objects (caller handles Heat)
        all_cards = build_full_deck()
        self.supply = Deck(all_cards)
        self.supply.shuffle(self.rng)
        self.stand = []
        self.mosh_pit = {f: [] for f in FACTION_COLORS}
        self.discard = []
        self.round_number = 0
        self.game_over = False
        self.end_reason = ""

        self.players = []
        for i in range(self.num_players):
            hand = self.supply.draw(hand_size)
            self.players.append(Player(id=i, hand=hand))

        self._fill_stand()
        self._log(f"Drop round setup: {self.num_players} players, {hand_size} cards each")

    def _fill_stand(self):
        """Fill stand to (players - 1) cards from supply."""
        target = self.num_players - 1
        while len(self.stand) < target and not self.supply.empty:
            card = self.supply.draw_one()
            if card:
                self.stand.append(card)

    # ─── ROUND EXECUTION ─────────────────────────────────────

    def play_round(self, bids: List[Bid],
                   ability_callback: Callable = None) -> dict:
        """Execute a full round: reveal → claim → mosh pit → restock.

        Args:
            bids: List of Bid objects, one per player.
            ability_callback: Function(player, faction, game_state) -> ability decisions.
                             Called when a player's claimed faction ability triggers.

        Returns:
            Round result dict with all events.
        """
        self.round_number += 1
        result = {
            "round": self.round_number,
            "bids": [],
            "claims": [],
            "sneaks": {"attempts": 0, "successes": 0},
            "mosh_pit_additions": [],
            "tramples": [],
            "abilities": [],
            "stand_before": [c.id for c in self.stand],
        }

        # ── STEP 1: Reveal and resolve bids ──
        claim_order = self._resolve_bids(bids, result)

        # ── STEP 2: Claims in order ──
        for claim_info in claim_order:
            pid = claim_info["player_id"]
            player = self.players[pid]

            if not self.stand:
                claim_info["claimed"] = None
                result["claims"].append(claim_info)
                continue

            # Player picks from stand (AI decides which)
            if ability_callback:
                chosen_idx = ability_callback(player, "choose_stand", self, self.stand)
                if chosen_idx is None or chosen_idx >= len(self.stand):
                    chosen_idx = 0
            else:
                chosen_idx = 0  # Default: take first

            claimed_card = self.stand.pop(chosen_idx)
            player.score_pile.append(claimed_card)
            claim_info["claimed"] = claimed_card
            self.stats["claims_per_player"][pid] += 1
            result["claims"].append(claim_info)

            self._log(f"  P{pid} claims {claimed_card} from Stand")

            # ── Trigger faction ability ──
            ability_result = self._resolve_ability(
                player, claimed_card.faction, ability_callback
            )
            if ability_result:
                result["abilities"].append(ability_result)

        # ── STEP 3: Mosh Pit ──
        pit_additions = self._process_mosh_pit(bids, result)
        result["mosh_pit_additions"] = pit_additions

        # ── Check for Trample ──
        tramples = self._check_trample()
        result["tramples"] = tramples

        # ── STEP 4: Restock ──
        self._restock_stand()

        # ── Check game end ──
        self._check_game_end()

        result["game_over"] = self.game_over
        result["end_reason"] = self.end_reason
        result["mosh_pit_state"] = {f: len(cards) for f, cards in self.mosh_pit.items()}

        return result

    def _resolve_bids(self, bids: List[Bid], result: dict) -> List[dict]:
        """Determine claim order from simultaneous bids.

        Returns ordered list of claim_info dicts for players who get to claim.
        """
        # Record bids
        for bid in bids:
            result["bids"].append({
                "player_id": bid.player_id,
                "primary": bid.primary,
                "anchor": bid.anchor,
                "is_sneak": bid.is_sneak,
                "is_shove": bid.is_shove,
                "has_valid_anchor": bid.has_valid_anchor,
            })

        # Identify Sneaks
        sneak_bids = [b for b in bids if b.is_sneak and b.has_valid_anchor]
        result["sneaks"]["attempts"] = len(sneak_bids)
        self.stats["sneak_attempts"] += len(sneak_bids)

        # Configurable Sneak cancellation threshold (default: 2+ = cancel)
        sneak_cancel = self.rules.get("sneak_cancel_threshold", {}).get(self.pkey, 2)

        # Successful Sneak: fewer than sneak_cancel players played a 0
        successful_sneak = None
        failed_sneaks = []
        if 0 < len(sneak_bids) < sneak_cancel:
            # All Sneaks succeed (they don't interfere)
            # For simplicity, first Sneak claims first, rest claim after
            successful_sneak = sneak_bids[0]
            result["sneaks"]["successes"] = len(sneak_bids)
            self.stats["sneak_successes"] += len(sneak_bids)
            if len(sneak_bids) == 1:
                self._log(f"  P{successful_sneak.player_id} Sneaks successfully!")
            else:
                self._log(f"  {len(sneak_bids)} Sneaks all succeed! (cancel threshold: {sneak_cancel}+)")
        elif len(sneak_bids) >= sneak_cancel:
            failed_sneaks = sneak_bids
            self._log(f"  {len(sneak_bids)} Sneaks cancel each other! (threshold: {sneak_cancel}+)")

        # Count Shoves
        shove_bids = [b for b in bids if b.is_shove and b.has_valid_anchor]
        self.stats["shove_count"] += len(shove_bids)

        # Build claim order: Sneak first, then 10→9→...→1→0(failed)
        claim_order = []

        # 1. Successful Sneak claims first
        if successful_sneak:
            claim_order.append({
                "player_id": successful_sneak.player_id,
                "bid_rank": 0,
                "type": "sneak_success",
            })

        # 2. Remaining bids sorted high to low (excluding successful sneak)
        remaining = [b for b in bids if b is not successful_sneak]

        # Group by effective rank to detect ties
        rank_groups: Dict[int, List[Bid]] = defaultdict(list)
        for bid in remaining:
            if bid in failed_sneaks:
                rank_groups[-1].append(bid)  # Failed sneaks go last
            else:
                rank_groups[bid.effective_rank].append(bid)

        # Process from highest to lowest rank
        for rank in sorted(rank_groups.keys(), reverse=True):
            group = rank_groups[rank]
            if rank == -1:
                continue  # Handle failed sneaks last

            if len(group) == 1:
                bid = group[0]
                claim_order.append({
                    "player_id": bid.player_id,
                    "bid_rank": bid.effective_rank,
                    "type": "shove" if bid.is_shove else "normal",
                })
            else:
                # Tie — nobody claims
                self.stats["ties"] += len(group)
                for bid in group:
                    self._log(f"  P{bid.player_id} ties at rank {bid.effective_rank} — no claim")

        # Failed sneaks claim last (effectively rank 0, but after everything)
        for bid in failed_sneaks:
            claim_order.append({
                "player_id": bid.player_id,
                "bid_rank": 0,
                "type": "sneak_failed",
            })

        return claim_order

    def _process_mosh_pit(self, bids: List[Bid], result: dict) -> List[dict]:
        """Move bid cards to the Mosh Pit (except successful Sneaks)."""
        additions = []

        # Find the successful sneak (if any)
        sneak_bids = [b for b in bids if b.is_sneak and b.has_valid_anchor]
        successful_sneak = sneak_bids[0] if len(sneak_bids) == 1 else None

        for bid in bids:
            if bid is successful_sneak:
                # Successful Sneak: cards go to discard, NOT pit
                for card in bid.cards_committed:
                    self.discard.append(card)
                additions.append({
                    "player_id": bid.player_id,
                    "cards": bid.cards_committed,
                    "destination": "discard",
                    "reason": "successful_sneak",
                })
                self._log(f"  P{bid.player_id}'s Sneak cards vanish (discard)")
            else:
                # All other bids: cards enter Mosh Pit under their printed colors
                for card in bid.cards_committed:
                    self.mosh_pit[card.faction].append(card)
                    additions.append({
                        "player_id": bid.player_id,
                        "cards": [card],
                        "destination": "mosh_pit",
                        "faction": card.faction,
                    })
                self._log(f"  P{bid.player_id}'s bid enters Mosh Pit: "
                          f"{', '.join(c.id for c in bid.cards_committed)}")

        return additions

    def _check_trample(self) -> List[dict]:
        """Check all factions for Trample. Returns list of trample events."""
        threshold = self.rules["trample_threshold"][self.pkey]
        tramples = []

        for faction in FACTION_COLORS:
            pit_count = len(self.mosh_pit[faction])
            if pit_count >= threshold:
                trample_event = self._execute_trample(faction)
                tramples.append(trample_event)

        return tramples

    def _execute_trample(self, faction: str) -> dict:
        """Execute a Trample: all players lose scored cards of this faction."""
        self._log(f"  ** {faction} TRAMPLES! ({len(self.mosh_pit[faction])} cards in Pit) **")
        self.stats["tramples"].append((self.round_number, faction))

        event = {
            "faction": faction,
            "pit_count": len(self.mosh_pit[faction]),
            "casualties": {},
        }

        for player in self.players:
            removed = player.remove_faction_cards(faction)
            if removed:
                event["casualties"][player.id] = removed
                self.stats["cards_trampled"][player.id] += len(removed)
                self._log(f"    P{player.id} loses {len(removed)} {faction} cards: "
                          f"{', '.join(c.id for c in removed)}")

        # Clear faction from Mosh Pit
        self.mosh_pit[faction] = []

        return event

    # ─── FACTION ABILITIES ────────────────────────────────────

    def _resolve_ability(self, player: Player, faction: str,
                         ability_callback: Callable = None) -> Optional[dict]:
        """Resolve a faction ability when a player claims that faction's card.

        The ability_callback handles AI decisions for each ability.
        """
        ability = self.config["factions"][faction]["ability"]

        if ability == "stadium_sweep":
            return self._ability_stadium_sweep(player, ability_callback)
        elif ability == "keen_eye":
            return self._ability_keen_eye(player, ability_callback)
        elif ability == "quick_hands":
            return self._ability_quick_hands(player)
        elif ability == "small_prophecies":
            return self._ability_small_prophecies(player, ability_callback)
        elif ability == "sleight_of_paw":
            return self._ability_sleight_of_paw(player, ability_callback)
        elif ability == "temporal_recall":
            return self._ability_temporal_recall(player, ability_callback)
        return None

    def _ability_stadium_sweep(self, player: Player,
                                callback: Callable = None) -> Optional[dict]:
        """RED: Remove 1 card of any faction from the Mosh Pit."""
        # Find all cards in Mosh Pit
        pit_cards = []
        for faction, cards in self.mosh_pit.items():
            for card in cards:
                pit_cards.append((faction, card))

        if not pit_cards:
            return None

        # AI decides which card to remove
        chosen = None
        if callback:
            chosen = callback(player, "stadium_sweep", self, pit_cards)

        if chosen is None:
            # Default: remove from faction closest to trample threshold
            threshold = self.rules["trample_threshold"][self.pkey]
            closest = max(FACTION_COLORS,
                         key=lambda f: len(self.mosh_pit[f]))
            if self.mosh_pit[closest]:
                chosen = (closest, self.mosh_pit[closest][0])
            else:
                return None

        faction, card = chosen
        if card in self.mosh_pit[faction]:
            self.mosh_pit[faction].remove(card)
            self.discard.append(card)
            self.stats["abilities_triggered"]["stadium_sweep"] += 1
            self._log(f"    RED ability: P{player.id} removes {card} from {faction} Pit")
            return {"ability": "stadium_sweep", "player": player.id,
                    "removed": card, "from_faction": faction}
        return None

    def _ability_keen_eye(self, player: Player,
                          callback: Callable = None) -> Optional[dict]:
        """ORANGE: Peek top supply card. May swap with unclaimed Stand card."""
        if self.supply.empty:
            return None

        top_card = self.supply.peek(1)[0]

        # AI decides whether to swap, and which Stand card
        swap_idx = None
        if callback and self.stand:
            swap_idx = callback(player, "keen_eye", self,
                               {"top_supply": top_card, "stand": self.stand})

        if swap_idx is not None and 0 <= swap_idx < len(self.stand):
            # Swap top supply with chosen Stand card
            supply_card = self.supply.draw_one()
            stand_card = self.stand[swap_idx]
            self.stand[swap_idx] = supply_card
            self.supply.add_to_top(stand_card)
            self.stats["abilities_triggered"]["keen_eye"] += 1
            self._log(f"    ORANGE ability: P{player.id} swaps supply {supply_card} "
                      f"with Stand {stand_card}")
            return {"ability": "keen_eye", "player": player.id,
                    "supply_card": supply_card, "stand_card": stand_card,
                    "swapped": True}
        else:
            self.stats["abilities_triggered"]["keen_eye"] += 1
            self._log(f"    ORANGE ability: P{player.id} peeks but doesn't swap")
            return {"ability": "keen_eye", "player": player.id,
                    "supply_card": top_card, "swapped": False}

    def _ability_quick_hands(self, player: Player) -> Optional[dict]:
        """YELLOW: Draw top supply card directly to Score Pile (blind)."""
        if self.supply.empty:
            return None

        drawn = self.supply.draw_one()
        player.score_pile.append(drawn)
        self.stats["abilities_triggered"]["quick_hands"] += 1
        self._log(f"    YELLOW ability: P{player.id} draws {drawn} to Score Pile")
        return {"ability": "quick_hands", "player": player.id, "drawn": drawn}

    def _ability_small_prophecies(self, player: Player,
                                   callback: Callable = None) -> Optional[dict]:
        """GREEN: See top 3 supply. Keep 1 of rank ≤5. Reorder rest."""
        if self.supply.empty:
            return None

        top3 = self.supply.draw(min(3, self.supply.size))
        keepable = [c for c in top3 if c.rank <= 5]

        kept = None
        reorder = list(top3)

        if keepable and callback:
            choice = callback(player, "small_prophecies", self,
                            {"top3": top3, "keepable": keepable})
            if choice is not None and choice in keepable:
                kept = choice
                reorder = [c for c in top3 if c is not kept]

        # AI also decides reorder
        if callback and reorder:
            new_order = callback(player, "small_prophecies_reorder", self, reorder)
            if new_order and len(new_order) == len(reorder):
                reorder = new_order

        # Put remaining back on top in chosen order
        self.supply.add_to_top(reorder)

        if kept:
            player.score_pile.append(kept)
            self._log(f"    GREEN ability: P{player.id} keeps {kept}, reorders supply")
        else:
            self._log(f"    GREEN ability: P{player.id} can't keep anything, reorders supply")

        self.stats["abilities_triggered"]["small_prophecies"] += 1
        return {"ability": "small_prophecies", "player": player.id,
                "seen": top3, "kept": kept}

    def _ability_sleight_of_paw(self, player: Player,
                                 callback: Callable = None) -> Optional[dict]:
        """BLUE: Move 1 Mosh Pit card from one faction to another."""
        # Need at least one card in the pit
        total_pit = sum(len(cards) for cards in self.mosh_pit.values())
        if total_pit == 0:
            return None

        move = None
        if callback:
            move = callback(player, "sleight_of_paw", self, self.mosh_pit)

        if move is None:
            return None

        from_faction, card, to_faction = move
        if (card in self.mosh_pit[from_faction] and
                from_faction != to_faction and
                to_faction in FACTION_COLORS):
            self.mosh_pit[from_faction].remove(card)
            self.mosh_pit[to_faction].append(card)
            self.stats["abilities_triggered"]["sleight_of_paw"] += 1
            self._log(f"    BLUE ability: P{player.id} moves {card} "
                      f"from {from_faction} to {to_faction}")

            # Check if this triggers an immediate Trample
            threshold = self.rules["trample_threshold"][self.pkey]
            if len(self.mosh_pit[to_faction]) >= threshold:
                self._log(f"    ** Sleight of Paw triggers {to_faction} TRAMPLE! **")
                trample = self._execute_trample(to_faction)
                return {"ability": "sleight_of_paw", "player": player.id,
                        "card": card, "from": from_faction, "to": to_faction,
                        "triggered_trample": trample}

            return {"ability": "sleight_of_paw", "player": player.id,
                    "card": card, "from": from_faction, "to": to_faction}
        return None

    def _ability_temporal_recall(self, player: Player,
                                  callback: Callable = None) -> Optional[dict]:
        """PURPLE: Retrieve 1 bid card from Pit to hand. Discard different card to Pit."""
        # Find this player's cards in the pit (from this round's bids)
        # For simplicity, we look for any cards in the pit the player could retrieve
        pit_cards = []
        for faction, cards in self.mosh_pit.items():
            for card in cards:
                pit_cards.append((faction, card))

        if not pit_cards or not player.hand:
            return None

        choice = None
        if callback:
            choice = callback(player, "temporal_recall", self,
                            {"pit_cards": pit_cards, "hand": player.hand})

        if choice is None:
            return None

        retrieve_faction, retrieve_card, discard_card = choice

        # Validate: retrieve card must be in pit, discard must be in hand,
        # and they must be different cards
        if (retrieve_card not in self.mosh_pit.get(retrieve_faction, []) or
                discard_card not in player.hand or
                retrieve_card == discard_card):
            return None

        # Execute: retrieve from pit, add to hand
        self.mosh_pit[retrieve_faction].remove(retrieve_card)
        player.hand.append(retrieve_card)

        # Discard from hand to pit
        player.hand.remove(discard_card)
        self.mosh_pit[discard_card.faction].append(discard_card)

        self.stats["abilities_triggered"]["temporal_recall"] += 1
        self._log(f"    PURPLE ability: P{player.id} retrieves {retrieve_card}, "
                  f"discards {discard_card} to Pit")

        # Check if discard triggers Trample
        threshold = self.rules["trample_threshold"][self.pkey]
        trample = None
        if len(self.mosh_pit[discard_card.faction]) >= threshold:
            trample = self._execute_trample(discard_card.faction)

        return {"ability": "temporal_recall", "player": player.id,
                "retrieved": retrieve_card, "discarded": discard_card,
                "triggered_trample": trample}

    # ─── RESTOCK & GAME END ───────────────────────────────────

    def _restock_stand(self):
        """Discard unclaimed Stand cards, refill from supply."""
        # Discard remaining Stand cards
        for card in self.stand:
            self.discard.append(card)
        self.stand = []

        # Refill
        self._fill_stand()

    def _check_game_end(self):
        """Check if the game has ended."""
        # Any player out of cards
        for player in self.players:
            if player.hand_size == 0:
                self.game_over = True
                self.end_reason = f"P{player.id} emptied their hand"
                self._log(f"GAME OVER: {self.end_reason}")
                return

        # Supply and Stand both empty
        if self.supply.empty and not self.stand:
            self.game_over = True
            self.end_reason = "Supply and Stand both empty"
            self._log(f"GAME OVER: {self.end_reason}")
            return

        # Safety: max rounds
        if self.round_number >= self.rules["max_rounds"]:
            self.game_over = True
            self.end_reason = "Max rounds reached"
            self._log(f"GAME OVER: {self.end_reason}")

    # ─── SCORING ──────────────────────────────────────────────

    def get_final_scores(self) -> List[dict]:
        """Calculate final scores with tiebreaker info."""
        set_bonus_config = self.rules.get("set_bonus", None)
        scores = []
        for p in self.players:
            set_bonus = p.set_bonus_vp_with_config(set_bonus_config)
            card_vp = sum(c.vp for c in p.score_pile)
            scores.append({
                "player_id": p.id,
                "card_vp": card_vp,
                "set_bonus": set_bonus,
                "total_vp": card_vp + set_bonus,
                "unique_colors": p.unique_colors,
                "highest_card": p.highest_card,
                "card_count": p.score_pile_count,
                "score_pile": [c.id for c in p.score_pile],
            })

        # Sort by total VP desc, then highest card desc, then card count desc
        scores.sort(key=lambda s: (s["total_vp"], s["highest_card"], s["card_count"]),
                    reverse=True)

        for i, s in enumerate(scores):
            s["finish_position"] = i + 1

        return scores

    def get_winner(self) -> int:
        """Return the player ID of the winner."""
        scores = self.get_final_scores()
        return scores[0]["player_id"]

    # ─── HELPERS ──────────────────────────────────────────────

    def get_player(self, pid: int) -> Player:
        return self.players[pid]

    def get_mosh_pit_total(self) -> int:
        return sum(len(cards) for cards in self.mosh_pit.values())

    def get_mosh_pit_faction_count(self, faction: str) -> int:
        return len(self.mosh_pit.get(faction, []))

    def get_stand_cards(self) -> List[Card]:
        return list(self.stand)

    def _log(self, msg: str):
        self.log.append(f"[R{self.round_number}] {msg}")


def load_config(config_path: str = None) -> dict:
    """Load config from JSON file."""
    if config_path is None:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.join(script_dir, "config.json")
    with open(config_path, 'r') as f:
        return json.load(f)
