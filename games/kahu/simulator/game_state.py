"""Kahu game state machine — the heart of the simulator."""

import json
import os
import random
import copy
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Callable
from cards import (Card, Offering, Deck, build_starter_deck, make_lava_flow,
                   make_tiki, ALL_OFFERINGS, OFFERINGS_3PUA, OFFERINGS_4PUA,
                   make_starter_card)
from kahu_parser import load_market_cards, find_csv


@dataclass
class Player:
    """One player's full state."""
    id: int
    draw_pile: Deck = field(default_factory=Deck)
    discard_pile: Deck = field(default_factory=Deck)
    hand: List[Card] = field(default_factory=list)
    play_area: List[Card] = field(default_factory=list)
    pua: Dict[str, int] = field(default_factory=lambda: {"Red": 0, "Blue": 0, "Yellow": 0})
    tiki: Optional[Card] = None
    vp_tokens: List[int] = field(default_factory=list)
    completed_offerings: List[str] = field(default_factory=list)
    removed_cards: int = 0
    influence_this_turn: int = 0
    cards_purchased_this_turn: List[Card] = field(default_factory=list)
    has_islander_in_play: bool = False
    has_surf_in_play: bool = False
    wildlife_discount: int = 0
    free_pua_this_turn: List[str] = field(default_factory=list)
    topdeck_purchase: bool = False  # Plumeria effect
    bonus_influence_first_turn: int = 0  # v3: seat compensation tokens
    first_turn_done: bool = False

    @property
    def total_vp_tokens(self) -> int:
        return sum(self.vp_tokens)

    @property
    def num_vp_tokens(self) -> int:
        return len(self.vp_tokens)

    @property
    def all_cards(self) -> List[Card]:
        """Every card the player owns (for final scoring)."""
        cards = list(self.hand) + list(self.play_area)
        cards += list(self.draw_pile.cards) + list(self.discard_pile.cards)
        if self.tiki:
            cards.append(self.tiki)
        return cards

    def __repr__(self):
        return (f"P{self.id}(VP:{self.total_vp_tokens} Tokens:{self.num_vp_tokens} "
                f"Pua:R{self.pua['Red']}B{self.pua['Blue']}Y{self.pua['Yellow']})")


class GameState:
    """Full game state for Kahu."""

    def __init__(self, config: dict, num_players: int, seed: int = None,
                 market_cards: List[Card] = None):
        self.config = config
        self.rules = config["game_rules"]
        self.num_players = num_players
        self.rng = random.Random(seed)
        self.seed = seed
        self.pkey = f"{num_players}_player"

        # Lava track
        self.lava_position = self.rules["lava_start"][self.pkey]
        self.lava_start = self.lava_position
        self.tiki_lockout = False
        self.pua_prices_increased = False
        self.market_shrunk = False

        # Pua market: randomize starting prices
        colors = ["Red", "Blue", "Yellow"]
        prices = list(self.rules["pua_starting_prices"])
        self.rng.shuffle(prices)
        self.pua_prices = dict(zip(colors, prices))
        self.pua_supply = {c: self.rules["pua_supply_per_color"] for c in colors}

        # Market
        all_market = list(market_cards) if market_cards else []
        self.rng.shuffle(all_market)

        # Separate Tiki cards (4 Tiki cards in the CSV are not in market — we make them)
        self.market_cards_filtered = [c for c in all_market if c.card_type.lower() != "surf"]
        # Surf are separate supply
        self.surf_supply = self.rules["surf_supply"]

        self.market_deck = Deck(self.market_cards_filtered)
        self.market_deck.shuffle(self.rng)
        self.market_row: List[Optional[Card]] = []
        self.market_size = self.rules["market_size"]

        # Fill initial market
        for _ in range(self.market_size):
            card = self.market_deck.draw_one()
            self.market_row.append(card)

        # Tikis — with VP from config
        tiki_vp = self.rules.get("tiki_vp", 0)
        self.tiki_display: List[Card] = [make_tiki(i, vp=tiki_vp) for i in range(self.rules["tiki_count"])]

        # Offerings — stack-based or legacy random
        if self.rules.get("offering_stacks", False):
            # v3: Draw 2 from 3-Pua stack + 2 from 4-Pua stack
            pool_3 = [copy.deepcopy(o) for o in OFFERINGS_3PUA]
            pool_4 = [copy.deepcopy(o) for o in OFFERINGS_4PUA]
            self.rng.shuffle(pool_3)
            self.rng.shuffle(pool_4)
            self.offerings: List[Offering] = pool_3[:2] + pool_4[:2]
        else:
            # Legacy: pick 4 random from 8
            offering_pool = [copy.deepcopy(o) for o in ALL_OFFERINGS]
            self.rng.shuffle(offering_pool)
            self.offerings: List[Offering] = offering_pool[:self.rules["offerings_active"]]

        # Apply VP token override from config
        vp_tokens_cfg = self.rules.get("vp_tokens_per_offering", [4, 3, 2, 1])
        for off in self.offerings:
            off.vp_tokens = list(vp_tokens_cfg)

        # Surf VP override
        self.surf_vp = self.rules.get("surf_vp", 0)

        # Offering cooldown
        self.offering_cooldown_enabled = self.rules.get("offering_cooldown", False)
        self.offering_cooldown_waiver = self.rules.get("offering_cooldown_waiver_lava", 5)

        # Players
        self.players: List[Player] = []
        for i in range(num_players):
            p = Player(id=i)
            starter = build_starter_deck()
            # Lava Flow goes straight to discard
            lava = [c for c in starter if c.effect_id == "lava_flow"][0]
            starter.remove(lava)
            p.discard_pile.add_to_bottom(lava)
            # Shuffle remaining 10 into draw pile
            self.rng.shuffle(starter)
            p.draw_pile = Deck(starter)
            # Draw opening hand of 5
            p.hand = p.draw_pile.draw(self.rules["hand_size"])

            # v2.0: Starting Pua for 2-player (legacy)
            starting_pua = self.rules.get("starting_pua_2p")
            if starting_pua and num_players == 2:
                for color, amount in starting_pua.items():
                    p.pua[color] = p.pua.get(color, 0) + amount
                    self.pua_supply[color] -= amount

            # v2.1: Seat-based compensation Pua (legacy)
            seat_comp = self.rules.get("seat_compensation_pua", {})
            seat_key = str(i)
            if seat_key in seat_comp:
                comp = seat_comp[seat_key]
                if "_random" in comp:
                    n = comp["_random"]
                    available_colors = [c for c in ["Red", "Blue", "Yellow"]
                                        if self.pua_supply[c] > 0]
                    for _ in range(n):
                        if available_colors:
                            color = self.rng.choice(available_colors)
                            p.pua[color] = p.pua.get(color, 0) + 1
                            self.pua_supply[color] -= 1
                            if self.pua_supply[color] <= 0:
                                available_colors.remove(color)
                else:
                    for color, amount in comp.items():
                        if amount > 0 and self.pua_supply.get(color, 0) >= amount:
                            p.pua[color] = p.pua.get(color, 0) + amount
                            self.pua_supply[color] -= amount

            # v3: Seat-based compensation Influence (bonus tokens for first turn)
            seat_comp_inf = self.rules.get("seat_compensation_influence", {})
            pkey_comp = f"{num_players}_player"
            if pkey_comp in seat_comp_inf:
                comp_map = seat_comp_inf[pkey_comp]
                seat_str = str(i)
                if seat_str in comp_map:
                    p.bonus_influence_first_turn = comp_map[seat_str]

            self.players.append(p)

        # Turn tracking
        self.current_player_idx = 0
        self.turn_number = 0
        self.round_number = 0  # increments after all players go

        # Game state flags
        self.game_over = False
        self.endgame_triggered = False
        self.endgame_trigger_player = -1
        self.finishing_round = False

        # Offering cooldown tracking: turn number when each player last completed
        self.last_offering_turn: Dict[int, int] = {}

        # Logging
        self.log: List[str] = []

        # Stats tracking
        self.lava_advances = 0
        self.tikis_used = 0

    def _log(self, msg: str):
        self.log.append(msg)

    # ----------------------------------------------------------------
    # Helpers
    # ----------------------------------------------------------------

    def get_current_player(self) -> Player:
        return self.players[self.current_player_idx]

    def _ensure_draw(self, player: Player, n: int) -> List[Card]:
        """Draw n cards, reshuffling discard into draw pile if needed."""
        drawn = []
        for _ in range(n):
            if player.draw_pile.empty:
                if player.discard_pile.empty:
                    break
                player.draw_pile = Deck(list(player.discard_pile.cards))
                player.discard_pile = Deck()
                player.draw_pile.shuffle(self.rng)
            card = player.draw_pile.draw_one()
            if card:
                drawn.append(card)
        return drawn

    def _get_market_cost(self, slot: int) -> int:
        """Get cost for a market slot (rightmost gets discount)."""
        if slot >= len(self.market_row) or self.market_row[slot] is None:
            return 999
        card = self.market_row[slot]
        cost = card.cost
        rightmost = len(self.market_row) - 1
        if slot == rightmost:
            cost = max(0, cost - self.rules["market_discount"])
        return cost

    def _refill_market(self):
        """Slide cards right and refill empty slots."""
        # Remove Nones, slide remaining to the right
        existing = [c for c in self.market_row if c is not None]
        new_row = [None] * self.market_size
        # Place existing cards at rightmost positions
        for i, card in enumerate(reversed(existing)):
            pos = self.market_size - 1 - i
            if pos >= 0:
                new_row[pos] = card
        # Fill remaining from left
        for i in range(self.market_size):
            if new_row[i] is None and not self.market_deck.empty:
                new_row[i] = self.market_deck.draw_one()
        self.market_row = new_row

    def _adjust_pua_prices(self, color_bought: str):
        """After buying pua, adjust market prices."""
        price_range = self.rules["pua_price_range"]["increased" if self.pua_prices_increased else "normal"]
        min_price, _, max_price = sorted(price_range)
        current_price = self.pua_prices[color_bought]

        # If bought at the highest price, no change
        if current_price >= max_price:
            return

        # The bought color goes up by 1
        new_price = current_price + 1
        # Find which color is at that new price and swap it down
        for other_color, other_price in self.pua_prices.items():
            if other_color != color_bought and other_price == new_price:
                self.pua_prices[other_color] = current_price
                break
        self.pua_prices[color_bought] = new_price

    # ----------------------------------------------------------------
    # Escalation Events
    # ----------------------------------------------------------------

    def _check_escalation(self):
        """Check and trigger escalation events based on lava position."""
        events = self.rules["escalation_events"]
        for threshold_str, event_name in events.items():
            threshold = int(threshold_str)
            # Trigger if lava just reached or passed this threshold (from above)
            if self.lava_position <= threshold < self.lava_position + 1:
                self._trigger_escalation(event_name)

    def _trigger_escalation(self, event: str):
        """Execute an escalation event."""
        self._log(f"  ESCALATION: {event} (lava at {self.lava_position})")

        if event == "second_lava":
            # Each player gets a second Lava Flow in their discard
            for p in self.players:
                p.discard_pile.add_to_bottom(make_lava_flow())

        elif event == "tiki_lockout":
            self.tiki_lockout = True

        elif event == "market_wipe_shrink":
            # Wipe market and shrink from 5 to 4
            for card in self.market_row:
                if card:
                    self.market_deck.add_to_bottom(card)
            self.market_deck.shuffle(self.rng)
            self.market_size = 4
            self.market_shrunk = True
            self.market_row = []
            for _ in range(self.market_size):
                c = self.market_deck.draw_one()
                self.market_row.append(c)

        elif event == "pua_price_increase":
            # All prices +1
            self.pua_prices_increased = True
            for color in self.pua_prices:
                self.pua_prices[color] += 1

        elif event == "market_wipe":
            for card in self.market_row:
                if card:
                    self.market_deck.add_to_bottom(card)
            self.market_deck.shuffle(self.rng)
            self.market_row = []
            for _ in range(self.market_size):
                c = self.market_deck.draw_one()
                self.market_row.append(c)

    def advance_lava(self):
        """Advance lava tracker by 1. Check escalation and game end."""
        old = self.lava_position
        self.lava_position -= 1
        self.lava_advances += 1
        self._log(f"  Lava advances: {old} -> {self.lava_position}")

        # Check each threshold we passed through
        events = self.rules["escalation_events"]
        for threshold_str in sorted(events.keys(), key=int, reverse=True):
            threshold = int(threshold_str)
            if self.lava_position <= threshold < old:
                self._trigger_escalation(events[threshold_str])

        if self.lava_position <= 0:
            self.endgame_triggered = True
            self._log("  LAVA REACHES 0 — endgame triggered!")

    # ----------------------------------------------------------------
    # Turn Phases
    # ----------------------------------------------------------------

    def play_hand(self, player: Player, ai_callback=None) -> dict:
        """Step 1: Play entire hand, resolve Lava Flow first.
        In v3, Hula fires before cards enter play area (remove a non-Lava card from hand).
        """
        result = {
            "lava_triggered": False,
            "tiki_used": False,
            "lava_advanced": False,
            "cards_drawn_mid_turn": [],
            "influence_total": 0,
            "hula_removed": None,
        }

        # v3 Hula: fires before playing cards — remove a non-Lava card from hand
        hula_in_hand = [c for c in player.hand if c.effect_id == "hula_remove"]
        if hula_in_hand:
            removable = [c for c in player.hand
                         if c.effect_id not in ("lava_flow", "hula_remove")]
            if removable and ai_callback:
                remove_idx = ai_callback("hula_remove_card", player, self,
                                          {"cards": removable})
                if remove_idx is not None and 0 <= remove_idx < len(removable):
                    removed = removable[remove_idx]
                    player.hand.remove(removed)
                    player.removed_cards += 1
                    result["hula_removed"] = removed
                    self._log(f"  P{player.id} Hula removes {removed.name} from hand")

        # Move all hand cards to play area
        player.play_area = list(player.hand)
        player.hand = []

        # Check for Lava Flow in play area
        lava_cards = [c for c in player.play_area if c.effect_id == "lava_flow"]
        for lava in lava_cards:
            result["lava_triggered"] = True
            if player.tiki is not None:
                # Tiki absorbs it
                player.discard_pile.add_to_bottom(player.tiki)
                player.tiki = None
                result["tiki_used"] = True
                self.tikis_used += 1
                self._log(f"  P{player.id} Tiki absorbs Lava Flow")
            else:
                self.advance_lava()
                result["lava_advanced"] = True

        # Determine synergy flags
        player.has_islander_in_play = any(
            c.normalized_type == "Islander" for c in player.play_area
        )
        player.has_surf_in_play = any(
            c.normalized_type == "Surf" for c in player.play_area
        )

        # Calculate base influence from all cards
        total_inf = 0
        player.wildlife_discount = 0
        player.free_pua_this_turn = []
        player.topdeck_purchase = False

        for card in player.play_area:
            inf = card.influence

            # Synergy bonuses
            if card.effect_id == "surfboard_synergy" and player.has_surf_in_play:
                inf = 5  # "If played with a surf card this card's value is 5"
            elif card.effect_id == "lei_islander_synergy" and player.has_islander_in_play:
                inf = 3
            elif card.effect_id == "grass_hut_islander_synergy" and player.has_islander_in_play:
                inf = 5
            elif card.effect_id == "islander_empty_discard" and player.discard_pile.empty:
                inf = 4
            elif card.effect_id == "islander_tiki_bonus" and player.tiki is not None:
                inf = 5
            elif card.effect_id == "islander_islander_synergy":
                # Check if another islander is in play
                other_islanders = [c for c in player.play_area
                                   if c.normalized_type == "Islander" and c is not card]
                if other_islanders:
                    inf = 5
            elif card.effect_id == "islander_surf_synergy" and player.has_surf_in_play:
                inf = 5
            elif card.effect_id == "fish_surf_pua" and player.has_surf_in_play:
                # Gain a pua (AI will choose color later)
                player.free_pua_this_turn.append("choice")

            total_inf += inf

            # Track special effects for AI to use
            if card.effect_id == "islander_wildlife_discount":
                player.wildlife_discount = 1
            if card.effect_id == "plate_lunch_free_pua" and player.has_islander_in_play:
                player.free_pua_this_turn.append("choice")
            if card.effect_id in ("plumeria_topdeck",):
                player.topdeck_purchase = True

        # v3: Add bonus influence from seat compensation (first turn only)
        if not player.first_turn_done and player.bonus_influence_first_turn > 0:
            total_inf += player.bonus_influence_first_turn
            self._log(f"  P{player.id} uses {player.bonus_influence_first_turn} bonus influence tokens")

        player.influence_this_turn = total_inf
        result["influence_total"] = total_inf

        return result

    def resolve_card_effects(self, player: Player, ai_callback=None) -> dict:
        """Resolve activated card abilities (post-Lava, pre-spending).
        ai_callback(effect_id, player, game, options) -> choice
        """
        result = {"cards_drawn": 0, "cards_removed": 0, "pua_gained": []}

        for card in list(player.play_area):
            if card.effect_id == "lava_flow":
                continue  # Already resolved

            eid = card.effect_id

            # --- Draw/cycle effects ---
            if eid == "pineapple_draw2":
                drawn = self._ensure_draw(player, 2)
                for d in drawn:
                    if d.effect_id == "lava_flow":
                        # Safe discard — Pineapple exception
                        player.discard_pile.add_to_bottom(d)
                        self._log(f"  P{player.id} Pineapple safely discards Lava Flow")
                    else:
                        # AI decides keep or discard
                        keep = True
                        if ai_callback:
                            keep = ai_callback("pineapple_keep", player, self, {"card": d})
                        if keep:
                            player.play_area.append(d)
                            player.influence_this_turn += d.influence
                            result["cards_drawn"] += 1
                        else:
                            player.discard_pile.add_to_bottom(d)

            elif eid == "outrigger_draw3":
                drawn = self._ensure_draw(player, 3)
                safe_drawn = []
                for d in drawn:
                    if d.effect_id == "lava_flow":
                        player.discard_pile.add_to_bottom(d)
                        self._log(f"  P{player.id} Outrigger safely discards Lava Flow")
                    else:
                        safe_drawn.append(d)
                # v3: If played with a Surf card, keep all three (no discard)
                if player.has_surf_in_play:
                    for d in safe_drawn:
                        player.play_area.append(d)
                        player.influence_this_turn += d.influence
                    result["cards_drawn"] += len(safe_drawn)
                else:
                    # Discard 1 of the safe ones (AI picks worst)
                    if safe_drawn:
                        discard_idx = 0
                        if ai_callback and len(safe_drawn) > 1:
                            discard_idx = ai_callback("outrigger_discard", player, self,
                                                       {"cards": safe_drawn})
                        if 0 <= discard_idx < len(safe_drawn):
                            player.discard_pile.add_to_bottom(safe_drawn.pop(discard_idx))
                        for d in safe_drawn:
                            player.play_area.append(d)
                            player.influence_this_turn += d.influence
                        result["cards_drawn"] += len(safe_drawn)

            elif eid == "sugar_cane_cycle":
                # Discard 4 from play area to draw 4 — simplified:
                # AI rarely wants to discard play area cards, so skip if not enough
                pass  # Complex — modeled as no-op for simulation

            elif eid == "islander_draw2":
                drawn = self._ensure_draw(player, 2)
                for d in drawn:
                    if d.effect_id == "lava_flow":
                        # Not safe — triggers immediately
                        if player.tiki:
                            player.discard_pile.add_to_bottom(player.tiki)
                            player.tiki = None
                            self.tikis_used += 1
                        else:
                            self.advance_lava()
                        player.discard_pile.add_to_bottom(d)
                    else:
                        player.play_area.append(d)
                        player.influence_this_turn += d.influence
                result["cards_drawn"] += len(drawn)

            # --- Retrieve effects ---
            elif eid == "ginger_retrieve_flower":
                flowers = [c for c in player.discard_pile.cards
                           if c.normalized_type == "Flower"]
                if flowers:
                    pick = flowers[0]
                    if ai_callback:
                        idx = ai_callback("retrieve_card", player, self,
                                          {"cards": flowers, "type": "Flower"})
                        if 0 <= idx < len(flowers):
                            pick = flowers[idx]
                    player.discard_pile.remove(pick)
                    player.play_area.append(pick)
                    player.influence_this_turn += pick.influence

            elif eid == "bird_retrieve_wildlife":
                wildlife = [c for c in player.discard_pile.cards
                            if c.normalized_type == "Wildlife"]
                if wildlife:
                    pick = wildlife[0]
                    if ai_callback:
                        idx = ai_callback("retrieve_card", player, self,
                                          {"cards": wildlife, "type": "Wildlife"})
                        if 0 <= idx < len(wildlife):
                            pick = wildlife[idx]
                    player.discard_pile.remove(pick)
                    player.play_area.append(pick)
                    player.influence_this_turn += pick.influence

            elif eid == "hibiscus_retrieve_item":
                items = [c for c in player.discard_pile.cards
                         if c.normalized_type == "Item"]
                if items:
                    pick = items[0]
                    if ai_callback:
                        idx = ai_callback("retrieve_card", player, self,
                                          {"cards": items, "type": "Item"})
                        if 0 <= idx < len(items):
                            pick = items[idx]
                    player.discard_pile.remove(pick)
                    player.play_area.append(pick)
                    player.influence_this_turn += pick.influence

            elif eid == "islander_discard_retrieve":
                if not player.discard_pile.empty:
                    top = player.discard_pile.cards[-1]
                    player.discard_pile.cards.remove(top)
                    player.play_area.append(top)
                    player.influence_this_turn += top.influence

            # --- Deck manipulation ---
            elif eid == "orchid_scry":
                top = player.draw_pile.peek(1)
                if top:
                    # AI decides top or bottom
                    to_bottom = False
                    if ai_callback:
                        to_bottom = ai_callback("orchid_place", player, self,
                                                 {"card": top[0]})
                    if to_bottom:
                        c = player.draw_pile.draw_one()
                        player.draw_pile.add_to_bottom(c)

            elif eid == "pua_kalaunu_thin":
                top = player.draw_pile.peek(1)
                if top:
                    remove = False
                    if ai_callback:
                        remove = ai_callback("pua_kalaunu_remove", player, self,
                                              {"card": top[0]})
                    c = player.draw_pile.draw_one()
                    if remove:
                        player.removed_cards += 1
                        result["cards_removed"] += 1
                    else:
                        player.discard_pile.add_to_bottom(c)

            elif eid == "ukulele_recycle":
                # Put 2 cards from discard to bottom of draw
                if player.discard_pile.size >= 2:
                    # AI picks best 2
                    chosen = player.discard_pile.cards[-2:]
                    if ai_callback:
                        indices = ai_callback("ukulele_pick", player, self,
                                               {"discard": list(player.discard_pile.cards)})
                        if indices and len(indices) == 2:
                            chosen = [player.discard_pile.cards[i]
                                      for i in indices
                                      if 0 <= i < player.discard_pile.size]
                    for c in chosen:
                        player.discard_pile.remove(c)
                        player.draw_pile.add_to_bottom(c)

            # --- Remove effects ---
            elif eid == "sea_shell_remove":
                # Remove a card from hand or discard
                candidates = list(player.discard_pile.cards)
                if candidates:
                    pick = candidates[0]
                    if ai_callback:
                        idx = ai_callback("remove_card", player, self,
                                          {"cards": candidates})
                        if 0 <= idx < len(candidates):
                            pick = candidates[idx]
                    player.discard_pile.remove(pick)
                    player.removed_cards += 1
                    result["cards_removed"] += 1

            elif eid == "dolphin_remove":
                candidates = [c for c in player.discard_pile.cards
                              if c.effect_id != "lava_flow"]
                if candidates:
                    pick = candidates[0]
                    if ai_callback:
                        idx = ai_callback("remove_card", player, self,
                                          {"cards": candidates})
                        if 0 <= idx < len(candidates):
                            pick = candidates[idx]
                    player.discard_pile.remove(pick)
                    player.removed_cards += 1
                    result["cards_removed"] += 1

            # --- Pua effects ---
            elif eid == "pig_exchange_pua":
                # Exchange 1 pua for another color — AI picks
                if ai_callback and sum(player.pua.values()) > 0:
                    swap = ai_callback("pig_swap", player, self, {})
                    if swap:
                        src, dst = swap
                        if player.pua.get(src, 0) > 0:
                            player.pua[src] -= 1
                            player.pua[dst] = player.pua.get(dst, 0) + 1

            elif eid in ("islander_gain_red",):
                player.pua["Red"] = player.pua.get("Red", 0) + 1
                result["pua_gained"].append("Red")

            elif eid in ("islander_gain_blue",):
                player.pua["Blue"] = player.pua.get("Blue", 0) + 1
                result["pua_gained"].append("Blue")

            elif eid in ("islander_gain_yellow",):
                player.pua["Yellow"] = player.pua.get("Yellow", 0) + 1
                result["pua_gained"].append("Yellow")

            # --- Sea Turtle ---
            elif eid == "sea_turtle_flower_draw":
                top = player.draw_pile.peek(1)
                if top:
                    card = player.draw_pile.draw_one()
                    if card.normalized_type == "Flower":
                        player.play_area.append(card)
                        player.influence_this_turn += card.influence
                    else:
                        player.discard_pile.add_to_bottom(card)

            # --- Free card gain islander effects ---
            elif eid == "islander_free_surf":
                if self.surf_supply > 0:
                    surf = Card(name="Surf", card_type="Surf", cost=2,
                                influence=2, vp=self.surf_vp, icon="", effect_text="",
                                effect_id="surf")
                    self.surf_supply -= 1
                    player.discard_pile.add_to_bottom(surf)

            elif eid == "islander_free_item":
                items_in_market = [(i, c) for i, c in enumerate(self.market_row)
                                   if c and c.normalized_type == "Item"]
                if items_in_market:
                    pick_idx = 0
                    if ai_callback and len(items_in_market) > 1:
                        pick_idx = ai_callback("free_market_card", player, self,
                                               {"cards": [c for _, c in items_in_market]})
                    slot, card = items_in_market[min(pick_idx, len(items_in_market) - 1)]
                    self.market_row[slot] = None
                    player.discard_pile.add_to_bottom(card)

            elif eid == "islander_free_flower":
                flowers_in_market = [(i, c) for i, c in enumerate(self.market_row)
                                     if c and c.normalized_type == "Flower"]
                if flowers_in_market:
                    pick_idx = 0
                    slot, card = flowers_in_market[min(pick_idx, len(flowers_in_market) - 1)]
                    self.market_row[slot] = None
                    player.discard_pile.add_to_bottom(card)

        # Resolve free pua from effects
        for pua_type in player.free_pua_this_turn:
            if pua_type == "choice" and ai_callback:
                color = ai_callback("choose_free_pua", player, self, {})
                if color in self.pua_supply and self.pua_supply[color] > 0:
                    player.pua[color] = player.pua.get(color, 0) + 1
                    self.pua_supply[color] -= 1
                    result["pua_gained"].append(color)
            elif pua_type in ("Red", "Blue", "Yellow"):
                if self.pua_supply[pua_type] > 0:
                    player.pua[pua_type] += 1
                    self.pua_supply[pua_type] -= 1
                    result["pua_gained"].append(pua_type)

        return result

    # ----------------------------------------------------------------
    # Step 2: Spend Influence — actions
    # ----------------------------------------------------------------

    def action_buy_market(self, player: Player, slot: int) -> dict:
        """Buy a card from the market row."""
        if slot >= len(self.market_row) or self.market_row[slot] is None:
            return {"success": False, "error": "Empty slot"}
        card = self.market_row[slot]
        cost = self._get_market_cost(slot)
        # Wildlife discount from Islander
        if card.normalized_type == "Wildlife" and player.wildlife_discount > 0:
            cost = max(0, cost - player.wildlife_discount)
        if player.influence_this_turn < cost:
            return {"success": False, "error": f"Need {cost}, have {player.influence_this_turn}"}

        player.influence_this_turn -= cost
        self.market_row[slot] = None

        if player.topdeck_purchase:
            player.draw_pile.add_to_top(card)
            player.topdeck_purchase = False  # Only first purchase
        else:
            player.discard_pile.add_to_bottom(card)
        player.cards_purchased_this_turn.append(card)

        self._log(f"  P{player.id} buys {card.name} from slot {slot} for {cost}")
        return {"success": True, "card": card, "cost": cost}

    def action_buy_surf(self, player: Player) -> dict:
        """Buy a Surf card from the shared supply."""
        cost = self.rules["surf_cost"]
        if self.surf_supply <= 0:
            return {"success": False, "error": "No surf cards left"}
        if player.influence_this_turn < cost:
            return {"success": False, "error": f"Need {cost}"}

        player.influence_this_turn -= cost
        self.surf_supply -= 1
        surf = Card(name="Surf", card_type="Surf", cost=2,
                    influence=2, vp=self.surf_vp, icon="", effect_text="", effect_id="surf")
        if player.topdeck_purchase:
            player.draw_pile.add_to_top(surf)
            player.topdeck_purchase = False
        else:
            player.discard_pile.add_to_bottom(surf)
        player.cards_purchased_this_turn.append(surf)

        self._log(f"  P{player.id} buys Surf for {cost}")
        return {"success": True, "cost": cost}

    def action_buy_pua(self, player: Player, color: str) -> dict:
        """Buy a Pua token of the specified color."""
        if color not in self.pua_prices:
            return {"success": False, "error": "Invalid color"}
        price = self.pua_prices[color]
        if player.influence_this_turn < price:
            return {"success": False, "error": f"Need {price}"}
        if self.pua_supply[color] <= 0:
            return {"success": False, "error": "No supply"}

        # Check for matching icon in play area
        has_icon = any(
            c.icon == color or c.is_wild
            for c in player.play_area
        )
        if not has_icon:
            return {"success": False, "error": f"No {color} icon in play"}

        player.influence_this_turn -= price
        player.pua[color] += 1
        self.pua_supply[color] -= 1
        self._adjust_pua_prices(color)

        self._log(f"  P{player.id} buys {color} Pua for {price}")
        return {"success": True, "color": color, "cost": price}

    def is_offering_on_cooldown(self, player: Player) -> bool:
        """Check if player is on offering cooldown (v2.0 rule)."""
        if not self.offering_cooldown_enabled:
            return False
        # Waiver: if lava at or below the waiver threshold, cooldown is off
        if self.lava_position <= self.offering_cooldown_waiver:
            return False
        # Check if player completed an offering this round or last turn
        last_turn = self.last_offering_turn.get(player.id, -999)
        # Must have at least num_players turns pass (one full round)
        if self.turn_number - last_turn < self.num_players:
            return True
        return False

    def action_complete_offering(self, player: Player, offering_idx: int) -> dict:
        """Complete an offering by spending required Pua."""
        if offering_idx >= len(self.offerings):
            return {"success": False, "error": "Invalid offering"}
        offering = self.offerings[offering_idx]

        if not offering.available:
            return {"success": False, "error": "Offering fully claimed"}
        if offering.name in player.completed_offerings:
            return {"success": False, "error": "Already completed this offering"}

        # v2.0: Offering cooldown check
        if self.is_offering_on_cooldown(player):
            return {"success": False, "error": "Offering cooldown active"}

        # Check Pua cost
        for color, needed in offering.pua_cost.items():
            if player.pua.get(color, 0) < needed:
                return {"success": False, "error": f"Need {needed} {color} Pua"}

        # Pay the cost
        for color, needed in offering.pua_cost.items():
            player.pua[color] -= needed
            self.pua_supply[color] += needed  # Return to supply

        vp = offering.complete(player.id)
        player.vp_tokens.append(vp)
        player.completed_offerings.append(offering.name)

        # Track cooldown
        self.last_offering_turn[player.id] = self.turn_number

        self._log(f"  P{player.id} completes {offering.name} for {vp} VP token")

        # Check endgame trigger
        if player.num_vp_tokens >= self.rules["endgame_vp_token_count"]:
            if not self.endgame_triggered:
                self.endgame_triggered = True
                self.endgame_trigger_player = player.id
                self._log(f"  P{player.id} has {player.num_vp_tokens} VP tokens — ENDGAME!")

        return {"success": True, "vp": vp, "offering": offering.name}

    def action_claim_tiki(self, player: Player) -> dict:
        """Claim a Tiki card from the display."""
        if self.tiki_lockout:
            return {"success": False, "error": "Tiki lockout active"}
        if player.tiki is not None:
            return {"success": False, "error": "Already have a Tiki"}
        if not self.tiki_display:
            return {"success": False, "error": "No Tikis available"}

        tiki_cost = self.rules["tiki_pua_cost"]
        for color, needed in tiki_cost.items():
            if player.pua.get(color, 0) < needed:
                return {"success": False, "error": f"Need {needed} {color} Pua for Tiki"}

        for color, needed in tiki_cost.items():
            player.pua[color] -= needed
            self.pua_supply[color] += needed

        tiki = self.tiki_display.pop()
        player.tiki = tiki

        self._log(f"  P{player.id} claims a Tiki")
        return {"success": True}

    # ----------------------------------------------------------------
    # Step 3 & 4: Refresh Market & Cleanup
    # ----------------------------------------------------------------

    def refresh_market(self):
        """Slide remaining market cards right, refill from deck."""
        self._refill_market()

    def cleanup_and_draw(self, player: Player):
        """Step 4: Discard play area, draw new hand."""
        # Move play area to discard (except Tiki, which stays)
        for card in player.play_area:
            if card.effect_id != "tiki":
                player.discard_pile.add_to_bottom(card)
        player.play_area = []
        player.cards_purchased_this_turn = []
        player.influence_this_turn = 0
        player.free_pua_this_turn = []
        player.topdeck_purchase = False
        player.wildlife_discount = 0
        player.first_turn_done = True  # v3: bonus influence expires after first turn

        # Draw 5
        player.hand = self._ensure_draw(player, self.rules["hand_size"])

    # ----------------------------------------------------------------
    # Turn Management
    # ----------------------------------------------------------------

    def advance_turn(self):
        """Move to next player. Handle round completion and endgame."""
        self.current_player_idx = (self.current_player_idx + 1) % self.num_players
        self.turn_number += 1

        if self.current_player_idx == 0:
            self.round_number += 1

        # Check if we should end (endgame trigger + finish round)
        if self.endgame_triggered:
            if self.current_player_idx == 0:
                # Full round complete
                self.game_over = True
            self.finishing_round = True

        if self.turn_number >= self.rules["max_turns"]:
            self.game_over = True

    # ----------------------------------------------------------------
    # Scoring
    # ----------------------------------------------------------------

    def calculate_final_scores(self) -> Dict[int, dict]:
        """Calculate final scores for all players."""
        results = {}
        for p in self.players:
            all_cards = p.all_cards
            # 1. Card VP
            # Surf VP threshold: if player has >= threshold Surf cards, each is worth bonus VP
            surf_threshold = self.rules.get("surf_vp_threshold", 0)
            surf_vp_bonus = self.rules.get("surf_vp_if_threshold", 0)
            if surf_threshold > 0 and surf_vp_bonus > 0:
                surf_count = sum(1 for c in all_cards if c.normalized_type == "Surf")
                if surf_count >= surf_threshold:
                    # Apply bonus VP to Surf cards (on top of their base vp from card data)
                    card_vp = sum(c.vp for c in all_cards) + surf_count * surf_vp_bonus
                else:
                    card_vp = sum(c.vp for c in all_cards)
            else:
                card_vp = sum(c.vp for c in all_cards)

            # 2. Offering bonuses
            offering_bonus = 0
            bonus_details = {}
            for off_name in p.completed_offerings:
                off = next((o for o in self.offerings if o.name == off_name), None)
                if not off:
                    continue
                bonus = self._calc_offering_bonus(p, off, all_cards)
                offering_bonus += bonus
                bonus_details[off_name] = bonus

            # 3. VP tokens
            token_vp = sum(p.vp_tokens)

            total = card_vp + offering_bonus + token_vp
            results[p.id] = {
                "card_vp": card_vp,
                "offering_bonus": offering_bonus,
                "bonus_details": bonus_details,
                "token_vp": token_vp,
                "total": total,
                "pua_remaining": sum(p.pua.values()),
            }
        return results

    def _calc_offering_bonus(self, player: Player, offering: Offering,
                             all_cards: List[Card]) -> int:
        """Calculate the bonus VP from a completed offering."""
        bt = offering.bonus_type
        if bt == "removed_cards":
            return player.removed_cards
        elif bt == "card_types":
            types = set(c.normalized_type for c in all_cards)
            return min(len(types), 6)
        elif bt == "islander_count":
            return sum(1 for c in all_cards if c.normalized_type == "Islander")
        elif bt == "item_count":
            return sum(1 for c in all_cards if c.normalized_type == "Item")
        elif bt == "wildlife_count":
            return sum(1 for c in all_cards if c.normalized_type == "Wildlife")
        elif bt == "flower_count":
            return sum(1 for c in all_cards if c.normalized_type == "Flower")
        elif bt == "tiki_count":
            return 3 * sum(1 for c in all_cards if c.normalized_type == "Tiki")
        elif bt == "surf_count":
            return sum(1 for c in all_cards if c.normalized_type == "Surf")
        return 0


def load_config(version: str = "v1") -> dict:
    """Load config by version name ('v1' or 'v2') or explicit path.

    - 'v1' loads config.json (rules as written)
    - 'v2' loads config_v2.json (OpenClaw 2.0 changes)
    - Any other string is treated as a file path
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))

    if version == "v1":
        filename = "config.json"
    elif version == "v2":
        filename = "config_v2.json"
    elif version == "v2.1":
        filename = "config_v2_1.json"
    elif version == "v3":
        filename = "config_v3.json"
    else:
        # Treat as explicit path
        if os.path.exists(version):
            with open(version) as f:
                return json.load(f)
        raise FileNotFoundError(f"Config not found: {version}")

    for candidate in [
        os.path.join(script_dir, filename),
        os.path.join(script_dir, "..", filename),
    ]:
        if os.path.exists(candidate):
            with open(candidate) as f:
                return json.load(f)
    raise FileNotFoundError(f"{filename} not found")
