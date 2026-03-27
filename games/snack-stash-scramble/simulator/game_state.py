"""Game state machine for Snack Stash Scramble."""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict, Any
import random
from itertools import combinations

from cards import Card, BankedSet, Deck, build_deck


@dataclass
class Player:
    """A single player's state."""
    id: int
    hand: List[Card] = field(default_factory=list)
    banked_sets: List[BankedSet] = field(default_factory=list)

    @property
    def banked_score(self) -> int:
        return sum(s.total_value for s in self.banked_sets)

    @property
    def hand_penalty(self) -> int:
        return sum(c.hand_penalty for c in self.hand)

    @property
    def final_score(self) -> int:
        return self.banked_score - self.hand_penalty

    @property
    def hand_size(self) -> int:
        return len(self.hand)

    def __repr__(self):
        return (f"P{self.id}(Banked:{self.banked_score} "
                f"Hand:{self.hand_size} Penalty:-{self.hand_penalty})")


class GameState:
    """Full state machine for Snack Stash Scramble."""

    def __init__(self, config: dict, num_players: int, seed: int = None):
        self.config = config
        self.rules = config
        self.num_players = num_players
        self.rng = random.Random(seed)
        self.seed = seed

        # Build and shuffle the deck
        all_cards = build_deck(config)
        self.feeder = Deck(all_cards)
        self.feeder.shuffle(self.rng)

        # Litter Box (discard pile) — top card is index -1 (end of list)
        self.litter_box: List[Card] = []

        # Players
        self.players: List[Player] = []
        for i in range(num_players):
            self.players.append(Player(id=i))

        # Game state tracking
        self.current_player_idx: int = 0
        self.turn_number: int = 0
        self.halftime_done: bool = False
        self.game_over: bool = False
        self.feeder_empty_count: int = 0
        self.last_discarded_card: Optional[Card] = None
        self.last_discarder_id: int = -1

        # Logging
        self.log: List[str] = []

        # Stats tracking
        self.action_log: List[Dict[str, Any]] = []
        self.faction_power_uses: Dict[str, int] = {f: 0 for f in config["deck"]["factions"]}
        self.sets_banked_count: int = 0
        self.extensions_count: int = 0
        self.halftime_turn: int = -1
        self.snack_floor_triggers: int = 0
        self.stale_snack_blocks: int = 0
        self.mid_bite_whistles: int = 0

    def setup(self):
        """Deal starting hands and flip first litter box card."""
        asymmetric = self.config.get("setup", {}).get("asymmetric_hands", False)
        hand_sizes = self.config.get("setup", {}).get("hand_size_per_seat", [])
        default_hand = self.config["setup"]["starting_hand_size"]

        for player in self.players:
            if asymmetric and player.id < len(hand_sizes):
                hs = hand_sizes[player.id]
            else:
                hs = default_hand
            player.hand = self.feeder.draw(hs)

        # Flip top card to start the litter box
        first_discard = self.feeder.draw_one()
        if first_discard:
            self.litter_box.append(first_discard)
        self._log(f"Game setup: {self.num_players} players, "
                  f"{self.feeder.size} cards in feeder")

    def get_current_player(self) -> Player:
        return self.players[self.current_player_idx]

    def get_previous_player_id(self) -> int:
        return (self.current_player_idx - 1) % self.num_players

    # ----------------------------------------------------------------
    # DRAW PHASE
    # ----------------------------------------------------------------

    def get_draw_options(self, player: Player) -> List[str]:
        """Return available draw actions for the player."""
        if player.hand_size <= self.config["draw"]["snack_floor_threshold"]:
            return ["snack_floor"]

        options = ["draw_feeder"]
        if self.litter_box and not self._is_stale_snack():
            options.append("draw_litter_box")
        return options

    def _is_stale_snack(self) -> bool:
        """Check if top of litter box is the stale snack (previous player's discard)."""
        # Variant: stale snack rule can be disabled
        if not self.config.get("draw", {}).get("stale_snack_rule", True):
            return False
        if not self.litter_box:
            return False
        prev_id = self.get_previous_player_id()
        return (self.last_discarder_id == prev_id and
                self.last_discarded_card is not None and
                self.litter_box[-1] == self.last_discarded_card)

    def action_draw_feeder(self, player: Player, scavenge: bool = False) -> dict:
        """Draw one card from the feeder (or 2 if scavenging)."""
        if self.feeder.empty:
            return {"success": False, "error": "Feeder is empty"}

        scavenge_enabled = self.config.get("draw", {}).get("scavenge_enabled", False)
        draw_count = 1
        if scavenge and scavenge_enabled:
            draw_count = self.config.get("draw", {}).get("scavenge_draw", 2)

        drawn = []
        for _ in range(draw_count):
            if self.feeder.empty:
                self._check_feeder_empty()
                break
            card = self.feeder.draw_one()
            player.hand.append(card)
            drawn.append(card)

        if len(drawn) == 1:
            self._log(f"P{player.id} draws {drawn[0]} from feeder")
            result = {"success": True, "action": "draw_feeder", "card": drawn[0]}
        else:
            self._log(f"P{player.id} scavenges {len(drawn)} cards: {drawn}")
            result = {"success": True, "action": "scavenge", "cards": drawn}

        self._check_feeder_empty()
        return result

    def action_draw_litter_box(self, player: Player) -> dict:
        """Draw the top card from the litter box."""
        if not self.litter_box:
            return {"success": False, "error": "Litter box is empty"}
        if self._is_stale_snack():
            self.stale_snack_blocks += 1
            return {"success": False, "error": "Stale snack — can't take previous player's discard"}

        card = self.litter_box.pop()
        player.hand.append(card)
        self._log(f"P{player.id} draws {card} from litter box")

        # Pantry Restock: flip top of Feeder into Litter Box to keep game clock ticking
        pantry_restock = self.config.get("draw", {}).get("pantry_restock", False)
        restock_card = None
        if pantry_restock and not self.feeder.empty:
            restock_card = self.feeder.draw_one()
            self.litter_box.append(restock_card)
            self._log(f"  Pantry Restock: {restock_card} flipped from Feeder to Litter Box")
            self._check_feeder_empty()

        return {"success": True, "action": "draw_litter_box", "card": card,
                "restock_card": restock_card}

    def action_snack_floor(self, player: Player) -> dict:
        """Snack floor: draw 3 cards from feeder (hand <=2)."""
        if player.hand_size > self.config["draw"]["snack_floor_threshold"]:
            return {"success": False, "error": "Hand too large for snack floor"}

        self.snack_floor_triggers += 1
        draw_count = self.config["draw"]["snack_floor_draw_count"]
        drawn = []
        for _ in range(draw_count):
            if self.feeder.empty:
                # Mid-bite whistle check
                self._check_feeder_empty()
                if self.game_over:
                    self.mid_bite_whistles += 1
                    self._log(f"P{player.id} MID-BITE WHISTLE during snack floor!")
                    break
            if not self.feeder.empty:
                card = self.feeder.draw_one()
                drawn.append(card)
                player.hand.append(card)

        self._log(f"P{player.id} snack floor draws {len(drawn)} cards: {drawn}")
        if not self.game_over:
            self._check_feeder_empty()
        return {"success": True, "action": "snack_floor", "cards": drawn,
                "count": len(drawn)}

    # ----------------------------------------------------------------
    # BANK PHASE — Set finding and banking
    # ----------------------------------------------------------------

    def find_valid_groups(self, hand: List[Card]) -> List[List[Card]]:
        """Find all valid groups (3+ cards of same rank) in hand."""
        from collections import defaultdict
        rank_buckets: Dict[int, List[Card]] = defaultdict(list)
        wilds = []
        for card in hand:
            if card.is_wild:
                wilds.append(card)
            else:
                rank_buckets[card.rank].append(card)

        groups = []
        min_size = self.config["banking"]["min_set_size"]

        for rank, cards in rank_buckets.items():
            if len(cards) >= min_size:
                # Use just the natural cards
                groups.append(list(cards))

            elif len(cards) + len(wilds) >= min_size:
                # Need wilds to fill
                needed = min_size - len(cards)
                if needed <= len(wilds):
                    group = list(cards) + wilds[:needed]
                    groups.append(group)

        return groups

    def find_valid_runs(self, hand: List[Card]) -> List[List[Card]]:
        """Find all valid runs (3+ consecutive same-faction) in hand."""
        from collections import defaultdict
        faction_cards: Dict[str, List[Card]] = defaultdict(list)
        wilds = []
        for card in hand:
            if card.is_wild:
                wilds.append(card)
            else:
                faction_cards[card.faction].append(card)

        runs = []
        min_size = self.config["banking"]["min_set_size"]

        for faction, cards in faction_cards.items():
            sorted_cards = sorted(cards, key=lambda c: c.rank)
            unique_ranks = sorted(set(c.rank for c in sorted_cards))

            if len(unique_ranks) < 2:
                continue

            # Try to find consecutive sequences, allowing wilds to fill gaps
            best_run = self._find_best_run(sorted_cards, wilds, min_size, faction)
            if best_run and len(best_run) >= min_size:
                runs.append(best_run)

        return runs

    def _find_best_run(self, sorted_natural: List[Card], wilds: List[Card],
                       min_size: int, faction: str) -> Optional[List[Card]]:
        """Find the longest run in a single faction, using wilds to fill gaps."""
        if not sorted_natural:
            return None

        # Get unique rank cards (prefer one per rank)
        rank_to_card = {}
        for c in sorted_natural:
            if c.rank not in rank_to_card:
                rank_to_card[c.rank] = c

        ranks = sorted(rank_to_card.keys())
        best_run = None

        # Try starting from each rank
        for start_idx in range(len(ranks)):
            run_cards = [rank_to_card[ranks[start_idx]]]
            wilds_used = 0
            max_wilds = len(wilds)
            current_rank = ranks[start_idx]

            for next_idx in range(start_idx + 1, len(ranks)):
                gap = ranks[next_idx] - current_rank - 1
                if gap > max_wilds - wilds_used:
                    break  # Can't fill this gap
                wilds_used += gap
                run_cards.append(rank_to_card[ranks[next_idx]])
                current_rank = ranks[next_idx]

            total_len = len(run_cards) + wilds_used
            if total_len >= min_size:
                # Build the actual run with wilds inserted
                full_run = list(run_cards)
                # Add needed wilds
                for i in range(wilds_used):
                    if i < len(wilds):
                        full_run.append(wilds[i])
                if best_run is None or len(full_run) > len(best_run):
                    best_run = full_run

        return best_run

    def find_all_valid_sets(self, hand: List[Card]) -> List[Tuple[str, List[Card]]]:
        """Find all valid bankable sets in a hand. Returns (type, cards) tuples."""
        results = []
        for g in self.find_valid_groups(hand):
            results.append(("group", g))
        for r in self.find_valid_runs(hand):
            results.append(("run", r))
        return results

    def action_bank_set(self, player: Player, cards: List[Card],
                        set_type: str, faction_trigger: Optional[str] = None,
                        trigger_target: Any = None) -> dict:
        """Bank a new set of cards. Returns result dict."""
        min_size = self.config["banking"]["min_set_size"]
        if len(cards) < min_size:
            return {"success": False, "error": f"Need at least {min_size} cards"}

        # Verify player has all these cards
        hand_copy = list(player.hand)
        for card in cards:
            found = False
            for i, hc in enumerate(hand_copy):
                if hc == card:
                    hand_copy.pop(i)
                    found = True
                    break
            if not found:
                return {"success": False, "error": f"Card {card} not in hand"}

        # Validate the set
        if set_type == "group":
            if not self._validate_group(cards):
                return {"success": False, "error": "Invalid group"}
        elif set_type == "run":
            if not self._validate_run(cards):
                return {"success": False, "error": "Invalid run"}
        else:
            return {"success": False, "error": f"Unknown set type: {set_type}"}

        # Remove cards from hand
        for card in cards:
            for i, hc in enumerate(player.hand):
                if hc == card:
                    player.hand.pop(i)
                    break

        # Create the banked set
        banked = BankedSet(cards=list(cards), set_type=set_type, owner_id=player.id)
        player.banked_sets.append(banked)
        self.sets_banked_count += 1

        self._log(f"P{player.id} banks {set_type}: {cards} (value: {banked.total_value})")

        # Determine faction power trigger
        power_result = None
        if faction_trigger:
            power_result = self._resolve_faction_power(
                player, faction_trigger, banked, trigger_target)

        return {
            "success": True,
            "action": "bank_set",
            "set_type": set_type,
            "cards": cards,
            "value": banked.total_value,
            "faction_trigger": faction_trigger,
            "power_result": power_result,
            "banked_set": banked
        }

    def _validate_group(self, cards: List[Card]) -> bool:
        """Check if cards form a valid group (3+ same rank)."""
        naturals = [c for c in cards if not c.is_wild]
        if not naturals:
            return False  # Need at least one natural
        target_rank = naturals[0].rank
        return all(c.rank == target_rank for c in naturals)

    def _validate_run(self, cards: List[Card]) -> bool:
        """Check if cards form a valid run (3+ consecutive same faction)."""
        naturals = [c for c in cards if not c.is_wild]
        if not naturals:
            return False
        target_faction = naturals[0].faction
        if not all(c.faction == target_faction for c in naturals):
            return False

        # Check that natural ranks + wilds can form a consecutive sequence
        natural_ranks = sorted(c.rank for c in naturals)
        num_wilds = len(cards) - len(naturals)

        # Check for gaps that wilds need to fill
        gaps = 0
        for i in range(1, len(natural_ranks)):
            gap = natural_ranks[i] - natural_ranks[i - 1] - 1
            gaps += gap

        return gaps <= num_wilds

    def find_extendable_sets(self, player: Player, card: Card) -> List[Tuple[int, BankedSet]]:
        """Find all banked sets (any player) that this card can extend."""
        results = []
        for p in self.players:
            for idx, bset in enumerate(p.banked_sets):
                if bset.protected and p.id != player.id:
                    continue  # RED power blocks opponent extensions
                if bset.can_extend_with(card):
                    results.append((p.id, bset))
        return results

    def action_extend_set(self, player: Player, card: Card,
                          target_player_id: int, target_set_idx: int) -> dict:
        """Extend an existing banked set with a card from hand."""
        if card not in player.hand:
            return {"success": False, "error": "Card not in hand"}

        target = self.players[target_player_id]
        if target_set_idx >= len(target.banked_sets):
            return {"success": False, "error": "Invalid set index"}

        bset = target.banked_sets[target_set_idx]
        if bset.protected and target_player_id != player.id:
            return {"success": False, "error": "Set is protected (RED power)"}

        if not bset.can_extend_with(card):
            return {"success": False, "error": "Card can't extend this set"}

        # Execute
        player.hand.remove(card)
        bset.cards.append(card)
        self.extensions_count += 1

        # Track poisoned cards (placed by opponent, scored sideways)
        poisoned_peanut = self.config.get("scoring", {}).get("poisoned_peanut_negative", False)
        is_opponent_placing = (player.id != target_player_id)
        if poisoned_peanut and is_opponent_placing:
            bset.poisoned_cards.append(card)

        self._log(f"P{player.id} extends P{target_player_id}'s {bset} with {card}")
        return {
            "success": True,
            "action": "extend_set",
            "card": card,
            "target_player": target_player_id,
            "target_set": bset
        }

    # ----------------------------------------------------------------
    # FACTION POWERS
    # ----------------------------------------------------------------

    def get_available_faction_triggers(self, cards: List[Card]) -> List[str]:
        """Get factions that can be triggered from a set (need a natural card)."""
        factions = set()
        for c in cards:
            if not c.is_wild:
                factions.add(c.faction)
        return list(factions)

    def _resolve_faction_power(self, player: Player, faction: str,
                                banked_set: BankedSet,
                                target: Any = None) -> dict:
        """Resolve a faction power trigger."""
        self.faction_power_uses[faction] += 1
        result = {"faction": faction, "effect": None}

        if faction == "RED":
            # Protect one of your banked sets (+ optional bonus points)
            red_bonus = self.config.get("scoring", {}).get("red_protection_bonus", 0)
            if target is not None and isinstance(target, int):
                if target < len(player.banked_sets):
                    player.banked_sets[target].protected = True
                    result["effect"] = f"Protected set {target}"
                    if red_bonus > 0:
                        result["effect"] += f" (+{red_bonus} bonus)"
                    self._log(f"  RED POWER: P{player.id} protects set {target}")
            else:
                best_idx = self._best_unprotected_set(player)
                if best_idx is not None:
                    player.banked_sets[best_idx].protected = True
                    result["effect"] = f"Protected set {best_idx}"
                    if red_bonus > 0:
                        result["effect"] += f" (+{red_bonus} bonus)"
                    self._log(f"  RED POWER: P{player.id} protects set {best_idx}")

        elif faction == "ORANGE":
            # Draw top of litter box
            if self.litter_box:
                card = self.litter_box.pop()
                player.hand.append(card)
                result["effect"] = f"Drew {card} from litter box"
                self._log(f"  ORANGE POWER: P{player.id} grabs {card} from litter box")
            else:
                result["effect"] = "Litter box empty, no draw"

        elif faction == "YELLOW":
            # Play one card from hand to extend any player's banked set
            result["effect"] = "yellow_pending"
            # Actual execution handled by AI calling action_extend_set

        elif faction == "GREEN":
            # Peek top N of feeder, reorder (variant: take one into hand)
            fv = self.config.get("faction_variants", {})
            green_peek = fv.get("green_peek_count", 3)
            green_take = fv.get("green_take_one", False)

            if not self.feeder.empty:
                peek_count = min(green_peek, self.feeder.size)
                peeked = self.feeder.draw(peek_count)

                if green_take and peeked:
                    # Take the best card into hand, put rest back
                    result["peeked"] = peeked
                    result["effect"] = f"Peeked {peek_count}, takes 1 into hand"
                    result["green_take"] = True
                    self._log(f"  GREEN POWER: P{player.id} peeks {peek_count}, takes 1")
                    # AI will handle selection; for now put them back
                    self.feeder.add_to_top(peeked)
                else:
                    if target and isinstance(target, list) and len(target) == len(peeked):
                        reordered = [peeked[i] for i in target]
                        self.feeder.add_to_top(reordered)
                    else:
                        self.feeder.add_to_top(peeked)
                    result["effect"] = f"Peeked {peek_count} cards"
                    result["peeked"] = peeked
                    self._log(f"  GREEN POWER: P{player.id} peeks at top {peek_count}")

        elif faction == "BLUE":
            # Take random card from opponent, give one back
            opponents = [p for p in self.players
                         if p.id != player.id and p.hand_size > 0]
            if opponents:
                if target and isinstance(target, dict):
                    opp_id = target.get("opponent_id", opponents[0].id)
                    give_card = target.get("give_card", None)
                else:
                    opp_id = self.rng.choice(opponents).id
                    give_card = None

                opponent = self.players[opp_id]
                if opponent.hand_size > 0:
                    stolen = opponent.hand.pop(self.rng.randint(0, opponent.hand_size - 1))
                    player.hand.append(stolen)

                    if give_card and give_card in player.hand:
                        player.hand.remove(give_card)
                        opponent.hand.append(give_card)
                        result["effect"] = f"Stole {stolen} from P{opp_id}, gave {give_card}"
                        self._log(f"  BLUE POWER: P{player.id} swaps with P{opp_id}: "
                                  f"took {stolen}, gave {give_card}")
                    elif player.hand:
                        # Default: give worst card
                        worst = max(player.hand, key=lambda c: c.hand_penalty)
                        player.hand.remove(worst)
                        opponent.hand.append(worst)
                        result["effect"] = f"Stole {stolen} from P{opp_id}, gave {worst}"
                        self._log(f"  BLUE POWER: P{player.id} swaps with P{opp_id}: "
                                  f"took {stolen}, gave {worst}")
                else:
                    result["effect"] = "Opponent hand empty"
            else:
                # Empty Pockets Contingency: draw from feeder
                if not self.feeder.empty:
                    card = self.feeder.draw_one()
                    player.hand.append(card)
                    result["effect"] = f"No opponents have cards, drew {card} from feeder"
                    self._log(f"  BLUE POWER: Empty pockets, P{player.id} draws from feeder")
                    self._check_feeder_empty()

        elif faction == "PURPLE":
            # Take any card from litter box, put at bottom of feeder
            if self.litter_box:
                if target is not None and isinstance(target, int) and target < len(self.litter_box):
                    card = self.litter_box.pop(target)
                else:
                    # Default: take the least useful card (highest rank for penalty reduction)
                    card = self.litter_box.pop(0)  # Bottom of litter box
                self.feeder.add_to_bottom(card)
                result["effect"] = f"Moved {card} from litter box to bottom of feeder"
                self._log(f"  PURPLE POWER: P{player.id} tucks {card} under feeder")
            else:
                result["effect"] = "Litter box empty"

        return result

    def _best_unprotected_set(self, player: Player) -> Optional[int]:
        """Find the index of the most valuable unprotected set."""
        best_idx = None
        best_val = -1
        for i, bset in enumerate(player.banked_sets):
            if not bset.protected and bset.total_value > best_val:
                best_val = bset.total_value
                best_idx = i
        return best_idx

    # ----------------------------------------------------------------
    # DISCARD PHASE
    # ----------------------------------------------------------------

    def action_discard(self, player: Player, card: Card) -> dict:
        """Discard a card from hand to the litter box."""
        if card not in player.hand:
            return {"success": False, "error": "Card not in hand"}

        player.hand.remove(card)
        self.litter_box.append(card)
        self.last_discarded_card = card
        self.last_discarder_id = player.id

        self._log(f"P{player.id} discards {card}")
        return {"success": True, "action": "discard", "card": card}

    # ----------------------------------------------------------------
    # TURN MANAGEMENT
    # ----------------------------------------------------------------

    def advance_turn(self):
        """Move to the next player's turn."""
        self.current_player_idx = (self.current_player_idx + 1) % self.num_players
        self.turn_number += 1

    # ----------------------------------------------------------------
    # FEEDER / HALFTIME / ENDGAME
    # ----------------------------------------------------------------

    def _check_feeder_empty(self):
        """Check if feeder is empty and handle halftime/endgame."""
        if not self.feeder.empty:
            return

        self.feeder_empty_count += 1

        if self.feeder_empty_count == 1 and not self.halftime_done:
            # HALFTIME SWEEP
            self.halftime_done = True
            self.halftime_turn = self.turn_number
            self._halftime_sweep()
        elif self.feeder_empty_count >= 2 or (self.halftime_done and self.feeder.empty):
            # GAME OVER
            self.game_over = True
            self._log("GAME OVER — Feeder empty for the second time!")

    def _halftime_sweep(self):
        """Halftime: reshuffle litter box (except top card) into feeder."""
        if len(self.litter_box) <= 1:
            # Not enough cards to reshuffle — game effectively ends
            self.game_over = True
            self._log("GAME OVER — Not enough cards for halftime reshuffle")
            return

        top_card = self.litter_box.pop()  # Keep the top card
        reshuffle = list(self.litter_box)
        self.litter_box.clear()
        self.litter_box.append(top_card)

        self.feeder = Deck(reshuffle)
        self.feeder.shuffle(self.rng)
        self._log(f"HALFTIME SWEEP: Reshuffled {len(reshuffle)} cards into feeder. "
                  f"Top of litter box: {top_card}")

    # ----------------------------------------------------------------
    # SCORING
    # ----------------------------------------------------------------

    def get_final_scores(self) -> List[Dict[str, Any]]:
        """Calculate final scores for all players."""
        red_bonus = self.config.get("scoring", {}).get("red_protection_bonus", 0)
        wild_override = self.config.get("scoring", {}).get("wild_bank_value_override", None)
        poison_negative = self.config.get("scoring", {}).get("poisoned_peanut_negative", False)

        scores = []
        for p in self.players:
            banked = 0
            poison_damage = 0
            for bset in p.banked_sets:
                for c in bset.cards:
                    if c.is_wild and wild_override is not None:
                        banked += wild_override
                    else:
                        banked += c.face_value
                # Poisoned Peanut: sideways cards subtract DOUBLE
                # (once to undo the face value already counted, once to penalize)
                if poison_negative:
                    for c in bset.poisoned_cards:
                        poison_damage += c.face_value * 2  # net effect: -face_value
                # RED bonus for protected sets
                if bset.protected and red_bonus > 0:
                    banked += red_bonus

            banked -= poison_damage
            penalty = sum(c.hand_penalty for c in p.hand)

            total_poisoned = sum(len(bset.poisoned_cards) for bset in p.banked_sets)

            scores.append({
                "player_id": p.id,
                "banked_score": banked,
                "hand_penalty": penalty,
                "hand_size": p.hand_size,
                "final_score": banked - penalty,
                "sets_count": len(p.banked_sets),
                "wilds_in_hand": sum(1 for c in p.hand if c.is_wild),
                "poisoned_cards": total_poisoned,
                "poison_damage": poison_damage // 2 if poison_negative else 0,
            })
        return scores

    def get_winner(self) -> int:
        """Return the player id with the highest score. Ties go to lower id."""
        scores = self.get_final_scores()
        best = max(scores, key=lambda s: (s["final_score"], -s["player_id"]))
        return best["player_id"]

    # ----------------------------------------------------------------
    # LOGGING
    # ----------------------------------------------------------------

    def _log(self, message: str):
        self.log.append(f"[T{self.turn_number}] {message}")
