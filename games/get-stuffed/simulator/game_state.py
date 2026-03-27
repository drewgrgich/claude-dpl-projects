"""
Game state machine for Get Stuffed.

Manages the full game lifecycle: setup, turn execution, scavenging,
faction powers, Sugar Crash, reshuffles, and win detection.
"""

import random
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Callable, Tuple
from cards import Card, Deck, build_deck


@dataclass
class Player:
    """One player's state."""
    id: int
    hand: List[Card] = field(default_factory=list)

    @property
    def hand_size(self) -> int:
        return len(self.hand)

    def has_playable(self, pit_card: Card, declared_faction: Optional[str] = None) -> bool:
        """Check if any card in hand can be played."""
        return any(c.matches_pit(pit_card, declared_faction) for c in self.hand)

    def get_playable(self, pit_card: Card, declared_faction: Optional[str] = None) -> List[Card]:
        """Return all playable cards from hand."""
        return [c for c in self.hand if c.matches_pit(pit_card, declared_faction)]

    def remove_card(self, card: Card) -> bool:
        """Remove a specific card from hand. Returns True if found."""
        if card in self.hand:
            self.hand.remove(card)
            return True
        return False

    def __repr__(self):
        return f"P{self.id}(hand:{self.hand_size})"


class GameState:
    """Full state machine for a Get Stuffed game."""

    def __init__(self, config: dict, num_players: int, seed: int = 0):
        self.config = config
        self.rules = config["game_rules"]
        self.num_players = num_players
        self.rng = random.Random(seed)
        self.seed = seed
        self.pkey = f"{num_players}_player"

        # Deck & pit
        all_cards = build_deck(config)
        self.stash = Deck(all_cards)
        self.stash.shuffle(self.rng)
        self.pit: List[Card] = []  # discard pile, last element = top
        self.declared_faction: Optional[str] = None  # set when a Purple card is played

        # Players
        self.players: List[Player] = []
        self.current_player_idx: int = 0
        self.play_direction: int = 1  # 1 = clockwise, -1 = counter-clockwise

        # Game flags
        self.game_over: bool = False
        self.winner: Optional[int] = None
        self.turn_number: int = 0
        self.reshuffle_count: int = 0
        self.sugar_crash: bool = False

        # Forced scavenge target (for Dib It)
        self.forced_scavenge_player: Optional[int] = None
        # Extra turn flag (for Re-Tinker)
        self.extra_turn: bool = False

        # Logging
        self.log: List[str] = []

        # Stats tracking
        self.stats = {
            "reshuffles": 0,
            "scavenges": 0,
            "scavenge_penalties": [],  # list of penalty amounts drawn
            "mercy_saves": 0,
            "powers_triggered": {f: 0 for f in self.rules["deck"]["factions"]},
            "sugar_crash_turn": None,
            "cards_played": 0,
            "cards_drawn_total": 0,
            "per_player": {},
        }

    def _log(self, msg: str):
        self.log.append(msg)

    # ─── Setup ───────────────────────────────────────────

    def setup(self, p0_discard_fn=None):
        """Initialize the game: deal hands, flip starting pit card.

        Args:
            p0_discard_fn: If P0 bonus card is enabled, function(player, game) -> Card
                that chooses which card P0 discards after seeing the pit.
                If None, discards the worst card (highest rank non-matching).
        """
        hand_size = self.rules["setup"]["starting_hand"][self.pkey]
        p0_bonus = self.rules["setup"].get("p0_bonus_card", False)
        p0_fewer = self.rules["setup"].get("p0_fewer_cards", 0)

        # Create players and deal
        for i in range(self.num_players):
            p = Player(id=i)
            deal_count = hand_size
            if i == 0 and p0_bonus:
                deal_count = hand_size + 1
            elif i == 0 and p0_fewer > 0:
                deal_count = max(1, hand_size - p0_fewer)
            p.hand = self.stash.draw(deal_count)
            self.players.append(p)
            self.stats["per_player"][i] = {
                "cards_played": 0,
                "cards_drawn": 0,
                "scavenges": 0,
                "powers_used": {f: 0 for f in self.rules["deck"]["factions"]},
                "mercy_saves": 0,
                "hot_potato_given": 0,
                "hot_potato_received": 0,
                "dib_it_forced": 0,
                "dib_it_received": 0,
                "retinker_reverse": 0,
                "retinker_extra_turn": 0,
                "foresaw_used": 0,
                "sleight_of_paw_used": 0,
                "vanish_used": 0,
                "vanish_swapped": 0,
                "time_warp_used": 0,
                "max_hand_size": hand_size,
                "sugar_crash_free_dumps": 0,
            }

        # Flip starting pit card — if Purple, tuck back and re-flip
        self._flip_starting_pit()

        # P0 bonus: now that the pit card is visible, P0 discards 1
        if p0_bonus and self.players:
            p0 = self.players[0]
            if p0.hand_size > hand_size:
                if p0_discard_fn:
                    discard = p0_discard_fn(p0, self)
                else:
                    discard = self._default_p0_discard(p0)
                if discard and p0.remove_card(discard):
                    # Tuck discarded card into middle of stash
                    mid = self.stash.size // 2
                    self.stash.cards.insert(mid, discard)
                    self._log(f"  P0 bonus: dealt {hand_size + 1} cards, "
                              f"discards {discard} after seeing pit. "
                              f"Now has {p0.hand_size} cards.")

        variant = ""
        if p0_bonus:
            variant = " (P0 got bonus card)"
        elif p0_fewer > 0:
            variant = f" (P0 starts with {p0_fewer} fewer)"
        self._log(f"Game setup: {self.num_players} players, {hand_size} cards each"
                  f"{variant}. Pit starts with {self.pit_top}")

    def _default_p0_discard(self, player: 'Player') -> 'Card':
        """Default discard choice for P0 bonus: drop the least useful card."""
        pit_top = self.pit_top
        declared = self.declared_faction

        # Separate playable vs non-playable
        non_playable = [c for c in player.hand
                        if not c.matches_pit(pit_top, declared)]
        if non_playable:
            # Discard the highest rank non-playable non-wild card
            non_wild_np = [c for c in non_playable if not c.is_wild]
            if non_wild_np:
                return max(non_wild_np, key=lambda c: c.rank)
            return non_playable[0]

        # All cards are playable — discard the worst playable
        non_wild = [c for c in player.hand if not c.is_wild]
        if non_wild:
            return max(non_wild, key=lambda c: c.rank)
        return player.hand[0]

    def _flip_starting_pit(self):
        """Flip the starting pit card (re-flip if Purple)."""
        while True:
            card = self.stash.draw_one()
            if card is None:
                break  # shouldn't happen with 66 cards
            if card.faction == self.rules["play"]["wild_faction"]:
                # Tuck into middle of stash
                mid = self.stash.size // 2
                self.stash.cards.insert(mid, card)
                continue
            self.pit.append(card)
            self.declared_faction = None
            break

    # ─── Properties ──────────────────────────────────────

    @property
    def pit_top(self) -> Card:
        """The current top card of the pit."""
        return self.pit[-1]

    @property
    def current_player(self) -> Player:
        return self.players[self.current_player_idx]

    # ─── Reshuffle ───────────────────────────────────────

    def _ensure_stash(self) -> bool:
        """If stash is empty, reshuffle pit (except top) into stash.
        Returns True if reshuffle happened."""
        if not self.stash.empty:
            return False

        if len(self.pit) <= 1:
            return False  # nothing to reshuffle

        top = self.pit[-1]
        reshuffle_cards = self.pit[:-1]
        self.pit = [top]
        self.stash = Deck(reshuffle_cards)
        self.stash.shuffle(self.rng)
        self.reshuffle_count += 1
        self.stats["reshuffles"] += 1

        self._log(f"  [Reshuffle #{self.reshuffle_count}] "
                  f"Stash replenished with {self.stash.size} cards.")

        if self.reshuffle_count >= self.rules["play"]["sugar_crash_reshuffle_count"]:
            if not self.sugar_crash:
                self.sugar_crash = True
                self.stats["sugar_crash_turn"] = self.turn_number
                self._log("  *** SUGAR CRASH ACTIVATED! Play 2 cards per turn! ***")

        return True

    def _draw_from_stash(self) -> Optional[Card]:
        """Draw one card from stash, reshuffling if needed."""
        if self.stash.empty:
            reshuffled = self._ensure_stash()
            if not reshuffled or self.stash.empty:
                return None
        return self.stash.draw_one()

    # ─── Core Actions ────────────────────────────────────

    def play_card(self, player: Player, card: Card,
                  declared_faction: Optional[str] = None,
                  is_side_effect: bool = False,
                  is_sugar_crash_free: bool = False,
                  power_decision_fn: Optional[dict] = None) -> dict:
        """Play a card from hand to the pit.

        Args:
            player: The player playing the card.
            card: The card to play.
            declared_faction: Faction to declare if playing a wild.
            is_side_effect: If True, this card was moved by a power (no power triggers).
            is_sugar_crash_free: If True, this is the free Sugar Crash dump (no match required, no powers).

        Returns:
            Result dict with success, power_triggered, etc.
        """
        result = {
            "success": False,
            "action": "play_card",
            "card": card,
            "power_triggered": None,
            "power_result": None,
            "game_over": False,
        }

        # Remove from hand
        if not player.remove_card(card):
            result["error"] = "Card not in hand"
            return result

        # Check for win FIRST — if this is the last card, no powers trigger
        if player.hand_size == 0:
            self.pit.append(card)
            if card.is_wild and declared_faction:
                self.declared_faction = declared_faction
            else:
                self.declared_faction = None
            self.game_over = True
            self.winner = player.id
            result["success"] = True
            result["game_over"] = True
            self.stats["cards_played"] += 1
            self.stats["per_player"][player.id]["cards_played"] += 1
            self._log(f"  P{player.id} plays {card} — LAST CARD! P{player.id} WINS!")
            return result

        # Place on pit
        self.pit.append(card)
        if card.is_wild and declared_faction:
            self.declared_faction = declared_faction
        elif not card.is_wild:
            self.declared_faction = None
        # If wild with no declaration, default to most common faction in hand
        elif card.is_wild and not declared_faction:
            self.declared_faction = self._default_declaration(player)

        result["success"] = True
        self.stats["cards_played"] += 1
        self.stats["per_player"][player.id]["cards_played"] += 1
        self._log(f"  P{player.id} plays {card}"
                  + (f" (declares {self.declared_faction})" if card.is_wild else ""))

        # Trigger faction power if rank >= 6 and not a side effect / free dump
        if card.has_power and not is_side_effect and not is_sugar_crash_free:
            power_result = self._trigger_power(player, card, power_decision_fn)
            result["power_triggered"] = card.power_name
            result["power_result"] = power_result
            if power_result and power_result.get("game_over"):
                result["game_over"] = True

        return result

    def _default_declaration(self, player: Player) -> str:
        """Pick the most common faction in hand for a wild card declaration."""
        if not player.hand:
            return "RED"  # fallback
        faction_counts: Dict[str, int] = {}
        for c in player.hand:
            if not c.is_wild:
                faction_counts[c.faction] = faction_counts.get(c.faction, 0) + 1
        if not faction_counts:
            return "RED"
        return max(faction_counts, key=faction_counts.get)

    # ─── Scavenging ──────────────────────────────────────

    def scavenge(self, player: Player,
                 mercy_decision_fn: Optional[Callable] = None) -> dict:
        """Execute a scavenge: flip, check, penalty draw with mercy clause.

        Args:
            mercy_decision_fn: Function(card, player, game) -> bool.
                Called when a mercy card is found during penalty draw.
                Returns True to play it and stop, False to keep drawing.
                If None, always take the mercy save.
        """
        result = {
            "action": "scavenge",
            "flipped_card": None,
            "flipped_matched": False,
            "penalty_amount": 0,
            "cards_drawn": 0,
            "mercy_save": False,
            "mercy_card": None,
            "power_triggered": None,
            "power_result": None,
            "game_over": False,
        }

        self.stats["scavenges"] += 1
        self.stats["per_player"][player.id]["scavenges"] += 1

        # Step 1: Flip top card of stash (public)
        flipped = self._draw_from_stash()
        if flipped is None:
            self._log(f"  P{player.id} tries to scavenge but stash is empty!")
            return result

        result["flipped_card"] = flipped
        self._log(f"  P{player.id} scavenges — flips {flipped} (shown to all)")

        # Step 2: Check if flipped card matches pit
        if flipped.matches_pit(self.pit_top, self.declared_faction):
            result["flipped_matched"] = True
            # Play it immediately
            # Determine declaration if wild
            decl = None
            if flipped.is_wild:
                decl = self._default_declaration(player)
            # Don't remove from hand — it was never in hand, play directly
            self.pit.append(flipped)
            if flipped.is_wild and decl:
                self.declared_faction = decl
            elif not flipped.is_wild:
                self.declared_faction = None

            self.stats["cards_played"] += 1
            self._log(f"  Flipped card matches! Played directly to pit."
                      + (f" (declares {self.declared_faction})" if flipped.is_wild else ""))

            # Trigger power if 6+
            if flipped.has_power:
                power_result = self._trigger_power(player, flipped)
                result["power_triggered"] = flipped.power_name
                result["power_result"] = power_result
                if power_result and power_result.get("game_over"):
                    result["game_over"] = True

            return result

        # Step 3: Doesn't match — add to hand, penalty draw
        player.hand.append(flipped)
        self.stats["cards_drawn_total"] += 1
        self.stats["per_player"][player.id]["cards_drawn"] += 1
        penalty_amount = flipped.rank
        result["penalty_amount"] = penalty_amount
        self._log(f"  No match. {flipped} added to hand. Penalty draw: {penalty_amount} cards.")

        cards_drawn = 0
        for i in range(penalty_amount):
            drawn = self._draw_from_stash()
            if drawn is None:
                self._log(f"  Stash exhausted during penalty draw after {cards_drawn} cards.")
                break
            cards_drawn += 1
            self.stats["cards_drawn_total"] += 1
            self.stats["per_player"][player.id]["cards_drawn"] += 1

            # Mercy clause: does this card match the pit?
            if drawn.matches_pit(self.pit_top, self.declared_faction):
                # Ask AI whether to play it or keep drawing
                should_play = True
                if mercy_decision_fn:
                    should_play = mercy_decision_fn(drawn, player, self)

                if should_play:
                    result["mercy_save"] = True
                    result["mercy_card"] = drawn
                    result["cards_drawn"] = cards_drawn
                    self.stats["mercy_saves"] += 1
                    self.stats["per_player"][player.id]["mercy_saves"] += 1

                    # Play the mercy card
                    decl = None
                    if drawn.is_wild:
                        decl = self._default_declaration(player)
                    self.pit.append(drawn)
                    if drawn.is_wild and decl:
                        self.declared_faction = decl
                    elif not drawn.is_wild:
                        self.declared_faction = None

                    self.stats["cards_played"] += 1
                    self._log(f"  MERCY! Drew {drawn} (card #{cards_drawn}) — matches pit! Played it."
                              + (f" (declares {self.declared_faction})" if drawn.is_wild else ""))

                    # Trigger power if 6+
                    if drawn.has_power:
                        power_result = self._trigger_power(player, drawn)
                        result["power_triggered"] = drawn.power_name
                        result["power_result"] = power_result
                        if power_result and power_result.get("game_over"):
                            result["game_over"] = True

                    self.stats["scavenge_penalties"].append(cards_drawn)
                    return result
                else:
                    # Chose not to play it — keep drawing
                    player.hand.append(drawn)
            else:
                player.hand.append(drawn)

        result["cards_drawn"] = cards_drawn
        self.stats["scavenge_penalties"].append(cards_drawn)
        self._log(f"  No mercy. Drew {cards_drawn} total penalty cards. "
                  f"P{player.id} now has {player.hand_size} cards.")

        # Track max hand size
        self.stats["per_player"][player.id]["max_hand_size"] = max(
            self.stats["per_player"][player.id]["max_hand_size"],
            player.hand_size
        )

        return result

    # ─── Faction Powers ──────────────────────────────────

    def _trigger_power(self, player: Player, card: Card,
                       power_decision_fn: Optional[dict] = None) -> dict:
        """Trigger the faction power for a played card.

        power_decision_fn is a dict of callbacks keyed by power type, provided by the AI.
        """
        if not card.has_power:
            return {}

        self.stats["powers_triggered"][card.faction] += 1
        self.stats["per_player"][player.id]["powers_used"][card.faction] += 1

        if card.faction == "RED":
            return self._power_hot_potato(player, power_decision_fn)
        elif card.faction == "ORANGE":
            return self._power_dib_it(player, power_decision_fn)
        elif card.faction == "YELLOW":
            return self._power_retinker(player, power_decision_fn)
        elif card.faction == "GREEN":
            return self._power_foresaw(player, card, power_decision_fn)
        elif card.faction == "BLUE":
            if card.rank == 10:
                return self._power_vanish(player, power_decision_fn)
            else:
                return self._power_sleight_of_paw(player, power_decision_fn)
        elif card.faction == "PURPLE":
            self.stats["per_player"][player.id]["time_warp_used"] += 1
            return {"power": "Time Warp", "description": "Wild — faction declared."}

        return {}

    def _power_hot_potato(self, player: Player,
                          decision_fn: Optional[dict] = None) -> dict:
        """RED 6-10: Give 1 card from hand to any opponent."""
        result = {"power": "Hot Potato!", "gave_card": False}

        # If hand is empty, power doesn't trigger
        if player.hand_size == 0:
            self._log(f"  Hot Potato fizzles — P{player.id} has no cards to give!")
            result["fizzled"] = True
            return result

        # AI decides which card and which opponent
        target_id = None
        card_to_give = None
        if decision_fn and "hot_potato" in decision_fn:
            target_id, card_to_give = decision_fn["hot_potato"](player, self)

        # Defaults
        if target_id is None:
            # Give to player with fewest cards (most threatening)
            opponents = [p for p in self.players if p.id != player.id]
            target = min(opponents, key=lambda p: p.hand_size)
            target_id = target.id
        if card_to_give is None:
            # Give highest rank card (most damaging penalty if they scavenge)
            card_to_give = max(player.hand, key=lambda c: c.rank)

        target = self.players[target_id]
        if player.remove_card(card_to_give):
            target.hand.append(card_to_give)
            result["gave_card"] = True
            result["card"] = card_to_give
            result["target"] = target_id
            self.stats["per_player"][player.id]["hot_potato_given"] += 1
            self.stats["per_player"][target_id]["hot_potato_received"] += 1
            self._log(f"  HOT POTATO! P{player.id} gives {card_to_give} to P{target_id}.")

            # Check if giving away last card = win
            if player.hand_size == 0:
                # Per rules: "You can only win by playing your last card to the Pit,
                # not by handing it off." So this shouldn't cause a win.
                # Actually the rule says Hot Potato doesn't trigger if you had 1 card
                # when you played the Super-Dupe. So this path shouldn't happen.
                pass

        return result

    def _power_dib_it(self, player: Player,
                      decision_fn: Optional[dict] = None) -> dict:
        """ORANGE 6-10: Force another player to scavenge on their next turn."""
        result = {"power": "Dib It!"}

        target_id = None
        if decision_fn and "dib_it" in decision_fn:
            target_id = decision_fn["dib_it"](player, self)

        if target_id is None:
            # Target the player with fewest cards
            opponents = [p for p in self.players if p.id != player.id]
            target = min(opponents, key=lambda p: p.hand_size)
            target_id = target.id

        self.forced_scavenge_player = target_id
        result["target"] = target_id
        self.stats["per_player"][player.id]["dib_it_forced"] += 1
        self.stats["per_player"][target_id]["dib_it_received"] += 1
        self._log(f"  DIB IT! P{player.id} forces P{target_id} to scavenge next turn.")

        return result

    def _power_retinker(self, player: Player,
                        decision_fn: Optional[dict] = None) -> dict:
        """YELLOW 6-10: Reverse direction OR take another turn."""
        result = {"power": "Re-Tinker!"}

        choice = None  # "reverse" or "extra_turn"
        if decision_fn and "retinker" in decision_fn:
            choice = decision_fn["retinker"](player, self)

        if choice is None:
            # Default: take extra turn (usually better for shedding)
            choice = "extra_turn"

        if choice == "reverse":
            self.play_direction *= -1
            result["choice"] = "reverse"
            self.stats["per_player"][player.id]["retinker_reverse"] += 1
            self._log(f"  RE-TINKER! P{player.id} reverses play direction.")
        else:
            self.extra_turn = True
            result["choice"] = "extra_turn"
            self.stats["per_player"][player.id]["retinker_extra_turn"] += 1
            self._log(f"  RE-TINKER! P{player.id} takes an extra turn!")

        return result

    def _power_foresaw(self, player: Player, played_card: Card,
                       decision_fn: Optional[dict] = None) -> dict:
        """GREEN 6-10: Peek top 3 of stash, take 1, reorder rest.
        Then play 1 card matching current pit (which is the Green card just played)."""
        result = {"power": "I Foresaw This!", "took_card": None, "played_card": None, "game_over": False}

        # Ensure stash has cards
        if self.stash.empty:
            self._ensure_stash()

        peek_count = min(self.rules["powers"]["foresaw_peek_count"], self.stash.size)
        if peek_count == 0:
            self._log(f"  I FORESAW THIS fizzles — stash is empty even after reshuffle!")
            return result

        peeked = self.stash.draw(peek_count)

        # AI decides which card to take and how to reorder the rest
        take_idx = 0
        if decision_fn and "foresaw" in decision_fn:
            take_idx, reorder = decision_fn["foresaw"](player, peeked, self)
        else:
            # Default: take the card most useful for next play
            take_idx = 0
            reorder = None

        taken = peeked.pop(take_idx)
        player.hand.append(taken)
        result["took_card"] = taken
        self._log(f"  I FORESAW THIS! P{player.id} peeks {peek_count} cards, takes {taken}.")

        # Put the rest back on top in chosen order
        if reorder and len(reorder) == len(peeked):
            ordered = [peeked[i] for i in reorder]
            self.stash.add_to_top(ordered)
        else:
            self.stash.add_to_top(peeked)

        self.stats["per_player"][player.id]["foresaw_used"] += 1

        # Now must play 1 card matching the GREEN card just played
        # The pit top is currently the green card
        playable = player.get_playable(self.pit_top, self.declared_faction)
        if not playable:
            self._log(f"  P{player.id} can't play anything matching the pit. Turn ends.")
            return result

        # AI picks which card to play
        card_to_play = None
        if decision_fn and "foresaw_play" in decision_fn:
            card_to_play = decision_fn["foresaw_play"](player, playable, self)
        if card_to_play is None:
            # Default: play highest rank (triggers powers)
            card_to_play = max(playable, key=lambda c: c.rank)

        # Determine wild declaration if needed
        decl = None
        if card_to_play.is_wild:
            if decision_fn and "declare_faction" in decision_fn:
                decl = decision_fn["declare_faction"](player, self)
            else:
                decl = self._default_declaration(player)

        play_result = self.play_card(player, card_to_play,
                                     declared_faction=decl)
        result["played_card"] = card_to_play
        result["play_result"] = play_result
        if play_result.get("game_over"):
            result["game_over"] = True

        return result

    def _power_sleight_of_paw(self, player: Player,
                              decision_fn: Optional[dict] = None) -> dict:
        """BLUE 6-9: Blind swap 1 card with an opponent."""
        result = {"power": "Sleight of Paw"}

        # AI chooses opponent
        target_id = None
        if decision_fn and "sleight_target" in decision_fn:
            target_id = decision_fn["sleight_target"](player, self)
        if target_id is None:
            opponents = [p for p in self.players if p.id != player.id and p.hand_size > 0]
            if not opponents:
                self._log(f"  Sleight of Paw fizzles — no opponents with cards!")
                return result
            target = min(opponents, key=lambda p: p.hand_size)
            target_id = target.id

        target = self.players[target_id]
        if player.hand_size == 0 or target.hand_size == 0:
            self._log(f"  Sleight of Paw fizzles — someone has no cards!")
            return result

        # Blind picks — random from each hand
        opp_picks_from_player = self.rng.randint(0, player.hand_size - 1)
        player_picks_from_opp = self.rng.randint(0, target.hand_size - 1)

        card_from_player = player.hand.pop(opp_picks_from_player)
        card_from_opp = target.hand.pop(player_picks_from_opp)

        player.hand.append(card_from_opp)
        target.hand.append(card_from_player)

        result["gave"] = card_from_player
        result["received"] = card_from_opp
        result["target"] = target_id
        self.stats["per_player"][player.id]["sleight_of_paw_used"] += 1
        self._log(f"  SLEIGHT OF PAW! P{player.id} swaps 1 card blind with P{target_id}. "
                  f"Gave {card_from_player}, got {card_from_opp}.")

        return result

    def _power_vanish(self, player: Player,
                      decision_fn: Optional[dict] = None) -> dict:
        """BLUE 10: May swap entire hand with any player."""
        result = {"power": "VANISH!", "swapped": False}

        should_swap = False
        target_id = None
        if decision_fn and "vanish" in decision_fn:
            should_swap, target_id = decision_fn["vanish"](player, self)

        if not should_swap:
            self._log(f"  VANISH! P{player.id} chooses NOT to swap hands.")
            self.stats["per_player"][player.id]["vanish_used"] += 1
            return result

        if target_id is None:
            # Swap with player who has fewest cards
            opponents = [p for p in self.players if p.id != player.id]
            target = min(opponents, key=lambda p: p.hand_size)
            target_id = target.id

        target = self.players[target_id]
        player.hand, target.hand = target.hand, player.hand
        result["swapped"] = True
        result["target"] = target_id
        result["my_new_size"] = player.hand_size
        result["their_new_size"] = target.hand_size
        self.stats["per_player"][player.id]["vanish_used"] += 1
        self.stats["per_player"][player.id]["vanish_swapped"] += 1
        self._log(f"  VANISH! P{player.id} swaps entire hand with P{target_id}! "
                  f"P{player.id} now has {player.hand_size}, P{target_id} has {target.hand_size}.")

        return result

    # ─── Turn Flow ───────────────────────────────────────

    def advance_turn(self):
        """Move to the next player (respecting direction, Dib It, extra turns)."""
        if self.game_over:
            return

        if self.extra_turn:
            self.extra_turn = False
            # Same player goes again
            self._log(f"  (Extra turn for P{self.current_player_idx})")
            return

        if self.forced_scavenge_player is not None:
            # Jump to the forced scavenge player
            self.current_player_idx = self.forced_scavenge_player
            self.forced_scavenge_player = None
            # Note: after forced scavenge, play continues from THAT player
            # in the current direction. We handle this by:
            # - Setting current to the forced player
            # - The main loop will execute their scavenge
            # - Then advance_turn will move normally from them
            return

        self.current_player_idx = (
            (self.current_player_idx + self.play_direction) % self.num_players
        )

    def get_next_player_idx(self) -> int:
        """Peek at who plays next (without advancing)."""
        if self.extra_turn:
            return self.current_player_idx
        if self.forced_scavenge_player is not None:
            return self.forced_scavenge_player
        return (self.current_player_idx + self.play_direction) % self.num_players
