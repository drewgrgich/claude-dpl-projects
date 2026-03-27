"""Heuristic AI player for Kahu simulator."""

import random
from typing import List, Dict, Optional, Tuple
from cards import Card, Offering
from game_state import GameState, Player


STYLE_PROFILES = {
    "balanced": {
        "description": "Well-rounded default play.",
        "pua_weight": 1.0,
        "offering_weight": 1.0,
        "tiki_weight": 1.0,
        "market_weight": 1.0,
        "surf_weight": 1.0,
        "thinning_priority": 0.5,    # How much to prioritize deck thinning
        "rush_cheap_offerings": False,
    },
    "rush": {
        "description": "Speed strategy. Complete cheap offerings fast.",
        "pua_weight": 1.5,
        "offering_weight": 2.0,
        "tiki_weight": 0.5,
        "market_weight": 0.5,
        "surf_weight": 0.8,
        "thinning_priority": 0.3,
        "rush_cheap_offerings": True,
    },
    "economy": {
        "description": "Build deck engine, buy expensive cards.",
        "pua_weight": 0.8,
        "offering_weight": 0.8,
        "tiki_weight": 0.8,
        "market_weight": 1.5,
        "surf_weight": 1.2,
        "thinning_priority": 0.8,
        "rush_cheap_offerings": False,
    },
    "defensive": {
        "description": "Prioritize Tikis and lava protection.",
        "pua_weight": 1.0,
        "offering_weight": 1.0,
        "tiki_weight": 2.5,
        "market_weight": 0.8,
        "surf_weight": 0.5,
        "thinning_priority": 0.4,
        "rush_cheap_offerings": False,
    },
}


class KahuAI:
    """Heuristic AI player for Kahu."""

    def __init__(self, skill: float = 1.0, style: str = "balanced",
                 aggression: float = 0.5, rng_seed: int = None):
        self.skill = max(0.0, min(1.0, skill))
        self.style_name = style
        self.style = STYLE_PROFILES.get(style, STYLE_PROFILES["balanced"])
        self.aggression = max(0.0, min(1.0, aggression))
        self.rng = random.Random(rng_seed)

    # ----------------------------------------------------------------
    # Skill-based mistake modeling
    # ----------------------------------------------------------------

    def _noisy_score(self, base: float) -> float:
        noise_range = 3.0 * (1.0 - self.skill)
        if noise_range == 0:
            return base
        return base + self.rng.uniform(-noise_range, noise_range)

    def _miss_opportunity(self, rate: float = 0.3) -> bool:
        return self.rng.random() < rate * (1.0 - self.skill)

    # ----------------------------------------------------------------
    # Card effect callbacks
    # ----------------------------------------------------------------

    def effect_callback(self, effect_id: str, player: Player,
                        game: GameState, options: dict):
        """Handle AI decisions for card effects."""

        if effect_id == "pineapple_keep":
            card = options["card"]
            # Keep high-influence or VP cards, discard low-value starters
            return card.influence >= 2 or card.vp >= 2

        elif effect_id == "outrigger_discard":
            cards = options["cards"]
            # Discard lowest influence card
            worst = min(range(len(cards)), key=lambda i: cards[i].influence + cards[i].vp)
            return worst

        elif effect_id == "retrieve_card":
            cards = options["cards"]
            # Pick highest influence
            best = max(range(len(cards)), key=lambda i: cards[i].influence)
            return best

        elif effect_id == "orchid_place":
            card = options["card"]
            # If it's a low-value card (starter), put to bottom
            return card.influence <= 1 and card.vp == 0

        elif effect_id == "pua_kalaunu_remove":
            card = options["card"]
            # Remove low-value starter cards
            return card.card_type == "Starter" and card.influence <= 1

        elif effect_id == "ukulele_pick":
            discard = options["discard"]
            # Pick 2 highest-value cards
            if len(discard) < 2:
                return list(range(len(discard)))
            scored = sorted(range(len(discard)),
                            key=lambda i: discard[i].influence + discard[i].vp * 2,
                            reverse=True)
            return scored[:2]

        elif effect_id == "remove_card":
            cards = options["cards"]
            # Remove lowest-value non-lava card
            removable = [(i, c) for i, c in enumerate(cards)
                         if c.effect_id != "lava_flow"]
            if not removable:
                return 0
            worst = min(removable, key=lambda x: x[1].influence + x[1].vp * 2)
            return worst[0]

        elif effect_id == "pig_swap":
            # Swap the color we have most of for the color we need most
            needs = self._get_pua_needs(player, game)
            if not needs:
                return None
            have_most = max(player.pua.keys(), key=lambda c: player.pua[c])
            if player.pua[have_most] > 0:
                need_most = max(needs.keys(), key=lambda c: needs[c])
                return (have_most, need_most)
            return None

        elif effect_id == "choose_free_pua":
            return self._choose_best_pua_color(player, game)

        elif effect_id == "free_market_card":
            cards = options["cards"]
            best = max(range(len(cards)),
                       key=lambda i: cards[i].influence + cards[i].vp * 2)
            return best

        elif effect_id == "hula_remove_card":
            # v3: Hula fires pre-play — remove worst non-Lava card from hand
            cards = options["cards"]
            if not cards:
                return None
            # Remove lowest-value card (prefer removing 1-influence starters)
            worst = min(range(len(cards)),
                        key=lambda i: cards[i].influence * 2 + cards[i].vp * 3
                        + (5 if cards[i].has_pua_icon else 0)
                        + (3 if cards[i].effect_id not in ("starter", "hula", "surf") else 0))
            # Only remove if the card is low-value enough (don't remove good cards)
            card = cards[worst]
            if card.influence <= 1 and card.vp <= 0 and not card.has_pua_icon:
                return worst
            # Also remove if thinning priority is high
            if self.style.get("thinning_priority", 0.5) >= 0.5 and card.influence <= 1:
                return worst
            return None  # Don't remove if hand is all good cards

        return 0

    # ----------------------------------------------------------------
    # Spending phase decision-making
    # ----------------------------------------------------------------

    def plan_spending(self, player: Player, game: GameState) -> List[dict]:
        """Plan all spending actions for this turn. Returns ordered list of actions."""
        actions = []

        # Evaluate all possible spending actions
        while player.influence_this_turn > 0:
            candidates = []

            # 1. Complete offerings
            if not self._miss_opportunity(0.2):
                for i, off in enumerate(game.offerings):
                    score = self._score_complete_offering(player, game, i, off)
                    if score > 0:
                        candidates.append(("complete_offering", score, {"idx": i}))

            # 2. Buy Pua
            for color in ["Red", "Blue", "Yellow"]:
                score = self._score_buy_pua(player, game, color)
                if score > 0:
                    candidates.append(("buy_pua", score, {"color": color}))

            # 3. Claim Tiki
            score = self._score_claim_tiki(player, game)
            if score > 0:
                candidates.append(("claim_tiki", score, {}))

            # 4. Buy market cards
            for slot in range(len(game.market_row)):
                if game.market_row[slot] is not None:
                    score = self._score_buy_market(player, game, slot)
                    if score > 0:
                        candidates.append(("buy_market", score, {"slot": slot}))

            # 5. Buy surf
            score = self._score_buy_surf(player, game)
            if score > 0:
                candidates.append(("buy_surf", score, {}))

            if not candidates:
                break

            # Pick best action
            best = max(candidates, key=lambda x: x[1])
            action_type, _, params = best

            # Execute action
            if action_type == "complete_offering":
                result = game.action_complete_offering(player, params["idx"])
                if result["success"]:
                    actions.append({"type": "complete_offering", **result})
                else:
                    break
            elif action_type == "buy_pua":
                result = game.action_buy_pua(player, params["color"])
                if result["success"]:
                    actions.append({"type": "buy_pua", **result})
                else:
                    # Can't buy this pua, remove from candidates and retry
                    break
            elif action_type == "claim_tiki":
                result = game.action_claim_tiki(player)
                if result["success"]:
                    actions.append({"type": "claim_tiki", **result})
                else:
                    break
            elif action_type == "buy_market":
                result = game.action_buy_market(player, params["slot"])
                if result["success"]:
                    actions.append({"type": "buy_market", **result})
                else:
                    break
            elif action_type == "buy_surf":
                result = game.action_buy_surf(player)
                if result["success"]:
                    actions.append({"type": "buy_surf", **result})
                else:
                    break

        return actions

    # ----------------------------------------------------------------
    # Scoring functions
    # ----------------------------------------------------------------

    def _score_complete_offering(self, player: Player, game: GameState,
                                  idx: int, offering: Offering) -> float:
        """Score completing an offering."""
        if offering.name in player.completed_offerings:
            return -999
        if not offering.available:
            return -999
        # v2.0: Offering cooldown check
        if game.is_offering_on_cooldown(player):
            return -999

        # Check if we can afford it
        for color, needed in offering.pua_cost.items():
            if player.pua.get(color, 0) < needed:
                return -999

        vp = offering.top_vp_token
        score = vp * 5.0 * self.style["offering_weight"]

        # Bonus for 3rd token (triggers endgame)
        if player.num_vp_tokens == 2:
            score += 20.0

        # Bonus for cheap offerings in rush style
        if self.style["rush_cheap_offerings"] and offering.total_pua_cost <= 3:
            score += 5.0

        # Consider offering bonus value
        bonus_est = self._estimate_offering_bonus(player, game, offering)
        score += bonus_est * 1.5

        return self._noisy_score(score)

    def _score_buy_pua(self, player: Player, game: GameState, color: str) -> float:
        """Score buying a specific Pua color."""
        price = game.pua_prices[color]
        if player.influence_this_turn < price:
            return -999
        if game.pua_supply[color] <= 0:
            return -999

        # Must have matching icon
        has_icon = any(c.icon == color or c.is_wild for c in player.play_area)
        if not has_icon:
            return -999

        # How much do we need this color?
        needs = self._get_pua_needs(player, game)
        need_this = needs.get(color, 0)

        if need_this == 0:
            return -0.5  # Don't buy pua we don't need

        score = need_this * 4.0 * self.style["pua_weight"]
        # Cheaper pua = better
        score -= price * 0.5
        # Urgency: if close to completing an offering
        score += self._pua_urgency(player, game, color) * 3.0

        return self._noisy_score(score)

    def _score_claim_tiki(self, player: Player, game: GameState) -> float:
        """Score claiming a Tiki."""
        if game.tiki_lockout or player.tiki is not None or not game.tiki_display:
            return -999
        cost = game.rules["tiki_pua_cost"]
        for color, needed in cost.items():
            if player.pua.get(color, 0) < needed:
                return -999

        # Value depends on lava position
        lava_danger = 1.0 - (game.lava_position / game.lava_start)
        score = 5.0 + lava_danger * 10.0
        score *= self.style["tiki_weight"]

        # Consider if Tiki offering is active
        tiki_offering = any(o.bonus_type == "tiki_count" and o.name not in player.completed_offerings
                           for o in game.offerings)
        if tiki_offering:
            score += 5.0

        return self._noisy_score(score)

    def _score_buy_market(self, player: Player, game: GameState, slot: int) -> float:
        """Score buying a market card."""
        card = game.market_row[slot]
        if card is None:
            return -999
        cost = game._get_market_cost(slot)
        if card.normalized_type == "Wildlife" and player.wildlife_discount > 0:
            cost = max(0, cost - player.wildlife_discount)
        if player.influence_this_turn < cost:
            return -999

        # Base value: influence + VP
        value = card.influence * 1.0 + card.vp * 2.0

        # Pua icon bonus
        if card.has_pua_icon:
            value += 2.0

        # Card type synergy with offerings
        for off in game.offerings:
            if off.name not in player.completed_offerings:
                if off.bonus_type == f"{card.normalized_type.lower()}_count":
                    value += 1.5

        # Effect value
        value += self._estimate_effect_value(card)

        score = (value - cost * 0.8) * self.style["market_weight"]
        score += (self.aggression - 0.5) * 2.0

        return self._noisy_score(score)

    def _score_buy_surf(self, player: Player, game: GameState) -> float:
        """Score buying a Surf card."""
        cost = game.rules["surf_cost"]
        if game.surf_supply <= 0 or player.influence_this_turn < cost:
            return -999

        score = 2.0 * self.style["surf_weight"]  # 2 influence card for 2 cost = decent

        # Synergy with surf-dependent cards
        surf_synergy_cards = sum(1 for c in player.all_cards
                                  if c.effect_id in ("surfboard_synergy", "fish_surf_pua",
                                                     "islander_surf_synergy"))
        score += surf_synergy_cards * 1.5

        # Surf offering bonus
        if any(o.bonus_type == "surf_count" and o.name not in player.completed_offerings
               for o in game.offerings):
            score += 2.0

        return self._noisy_score(score)

    # ----------------------------------------------------------------
    # Helpers
    # ----------------------------------------------------------------

    def _get_pua_needs(self, player: Player, game: GameState) -> Dict[str, int]:
        """Determine how much of each Pua color the player needs."""
        needs = {"Red": 0, "Blue": 0, "Yellow": 0}
        for off in game.offerings:
            if off.name in player.completed_offerings:
                continue
            if not off.available:
                continue
            for color, needed in off.pua_cost.items():
                deficit = max(0, needed - player.pua.get(color, 0))
                needs[color] = max(needs[color], deficit)
        return needs

    def _pua_urgency(self, player: Player, game: GameState, color: str) -> float:
        """How urgent is buying this color? Higher if close to completing."""
        urgency = 0.0
        for off in game.offerings:
            if off.name in player.completed_offerings or not off.available:
                continue
            total_needed = sum(max(0, v - player.pua.get(c, 0))
                               for c, v in off.pua_cost.items())
            if total_needed <= 2:  # Close to completing
                color_needed = max(0, off.pua_cost.get(color, 0) - player.pua.get(color, 0))
                if color_needed > 0:
                    urgency = max(urgency, 3.0 - total_needed)
        return urgency

    def _estimate_offering_bonus(self, player: Player, game: GameState,
                                  offering: Offering) -> float:
        """Estimate the bonus VP from an offering at game end."""
        all_cards = player.all_cards
        bt = offering.bonus_type
        if bt == "removed_cards":
            return player.removed_cards * 0.5
        elif bt == "card_types":
            return min(len(set(c.normalized_type for c in all_cards)), 6) * 0.8
        elif bt == "islander_count":
            return sum(1 for c in all_cards if c.normalized_type == "Islander") * 0.7
        elif bt == "item_count":
            return sum(1 for c in all_cards if c.normalized_type == "Item") * 0.7
        elif bt == "wildlife_count":
            return sum(1 for c in all_cards if c.normalized_type == "Wildlife") * 0.7
        elif bt == "flower_count":
            return sum(1 for c in all_cards if c.normalized_type == "Flower") * 0.7
        elif bt == "tiki_count":
            count = 1 if player.tiki else 0
            return count * 2.0
        elif bt == "surf_count":
            return sum(1 for c in all_cards if c.normalized_type == "Surf") * 0.7
        return 0

    def _estimate_effect_value(self, card: Card) -> float:
        """Estimate the value of a card's effect."""
        eid = card.effect_id
        values = {
            "pineapple_draw2": 2.0,
            "outrigger_draw3": 2.5,
            "orchid_scry": 0.5,
            "pua_kalaunu_thin": 1.5,
            "sea_shell_remove": 1.5,
            "dolphin_remove": 1.5,
            "ukulele_recycle": 1.0,
            "ginger_retrieve_flower": 1.0,
            "bird_retrieve_wildlife": 1.0,
            "hibiscus_retrieve_item": 1.0,
            "plumeria_topdeck": 1.0,
            "surfboard_synergy": 1.5,
            "lei_islander_synergy": 0.8,
            "grass_hut_islander_synergy": 1.5,
            "plate_lunch_free_pua": 2.5,
            "sea_turtle_flower_draw": 0.8,
            "chicken_steal": 1.0,
            "nene_goose_copy": 0.8,
            "pig_exchange_pua": 2.0,
            "fish_surf_pua": 2.5,
            "islander_draw2": 2.0,
            "islander_free_surf": 2.0,
            "islander_free_item": 2.5,
            "islander_free_flower": 2.0,
            "islander_gain_red": 3.0,
            "islander_gain_blue": 3.0,
            "islander_gain_yellow": 3.0,
            "islander_replay": 3.0,
            "islander_empty_discard": 1.0,
            "islander_tiki_bonus": 1.0,
            "islander_wildlife_discount": 1.0,
            "islander_islander_synergy": 1.0,
            "islander_surf_synergy": 1.0,
            "islander_market_borrow": 1.5,
            "islander_self_topdeck": 0.5,
            "islander_discard_retrieve": 1.0,
            "islander_mutual_draw": 0.5,
            "islander_mutual_pua": 1.5,
        }
        return values.get(eid, 0.0)

    def _choose_best_pua_color(self, player: Player, game: GameState) -> str:
        """Choose the best Pua color for a free gain."""
        needs = self._get_pua_needs(player, game)
        # Pick highest-need color with supply
        best = "Red"
        best_need = -1
        for color in ["Red", "Blue", "Yellow"]:
            if game.pua_supply.get(color, 0) > 0 and needs.get(color, 0) > best_need:
                best = color
                best_need = needs[color]
        return best
