"""
Game state machine for v0.1 — the custom deck zone control game.

48-card deck, 4 zones, 3 rounds, simultaneous deployment.
Features: Mascot doubling, Action cards (Shield/Bomb/Swap/Bounty),
Duds, Condition cards, card passing, Home Field Advantage.
"""

import json
import math
import os
import random
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Callable, Tuple
from collections import defaultdict

from cards_v4 import (
    Card, Deck, build_deck, COLORS, COLOR_ORDER,
    CARD_TYPE_NUMBER, CARD_TYPE_MASCOT, CARD_TYPE_ACTION, CARD_TYPE_DUD,
    ACTION_SHIELD, ACTION_BOMB, ACTION_SWAP, ACTION_BOUNTY, ACTION_RESOLUTION,
)


# ─── CONDITION CARD ──────────────────────────────────────────────────────────

@dataclass
class ConditionCard:
    name: str
    category: str   # card_restriction, placement, scoring
    effect: str     # machine-readable effect key

    def __repr__(self):
        return f"[{self.name}]"


# ─── DATA STRUCTURES ─────────────────────────────────────────────────────────

@dataclass
class Player:
    id: int
    hand: List[Card] = field(default_factory=list)
    score: int = 0
    zones_won_this_round: int = 0
    total_zones_won: int = 0
    cards_played_total: int = 0

    def __repr__(self):
        return f"P{self.id}(VP:{self.score} Hand:{len(self.hand)})"


@dataclass
class ZonePlacement:
    player_id: int
    cards: List[Card] = field(default_factory=list)


@dataclass
class Zone:
    color: str
    index: int
    placements: Dict[int, ZonePlacement] = field(default_factory=dict)

    def get_placement(self, player_id: int) -> ZonePlacement:
        if player_id not in self.placements:
            self.placements[player_id] = ZonePlacement(player_id=player_id)
        return self.placements[player_id]

    @property
    def active_players(self) -> List[int]:
        return [pid for pid, zp in self.placements.items() if zp.cards]


# ─── GAME STATE ──────────────────────────────────────────────────────────────

class GameStateV4:
    def __init__(self, num_players: int, seed: int = 42, config: dict = None):
        self.num_players = num_players
        self.rng = random.Random(seed)
        self.seed = seed

        # Load config
        if config is None:
            config_path = os.path.join(os.path.dirname(__file__), "config_v4.json")
            with open(config_path) as f:
                config = json.load(f)
        self.config = config
        self.rules = config["game_rules"]
        self.pkey = f"{num_players}_player"

        # Game parameters from config
        self.colors = self.rules["colors"]
        self.num_rounds = self.rules["num_rounds"]
        self.base_vp = self.rules["vp_per_zone"]
        self.extra_card_bonus = self.rules["strength"]["extra_card_bonus"]
        self.home_field_bonus = self.rules["strength"]["home_field_bonus"]
        self.dud_rank = self.rules["dud_rank"]
        self.second_place_vp = self.rules.get("second_place_vp", 0)

        # Build and shuffle deck
        all_cards = build_deck(config)
        self.rng.shuffle(all_cards)

        # Deal hands
        hand_size = self.rules["hand_sizes"][self.pkey]
        self.players: List[Player] = []
        idx = 0
        for i in range(num_players):
            hand = all_cards[idx:idx + hand_size]
            self.players.append(Player(id=i, hand=hand))
            idx += hand_size
        self.unused_cards = all_cards[idx:]

        # Condition deck
        self.condition_deck = [
            ConditionCard(c["name"], c["category"], c["effect"])
            for c in self.rules["condition_cards"]
        ]
        self.rng.shuffle(self.condition_deck)
        self.active_condition: Optional[ConditionCard] = None

        # Game state
        self.current_round = 0
        self.game_over = False
        self.zones: List[Zone] = []
        self.log: List[str] = []

        # Stats tracking
        self.stats = {
            "rounds": [],
            "strength_values": [],
            "cards_per_zone": [],
            "home_field_triggers": 0,
            "mascot_combos": 0,
            "action_plays": defaultdict(int),  # action_type -> count
            "dud_plays": 0,
            "condition_cards_drawn": [],
            "shield_saves": 0,
            "bomb_kills": 0,
            "swap_uses": 0,
            "bounty_wins": 0,
            "bounty_fails": 0,
            "lone_wolf_zones": 0,
            "contested_zones": [],
            "empty_zones": [],
            "second_place_awards": 0,
        }

    # ─── CARD PASSING ────────────────────────────────────────────────────

    def execute_pass(self, pass_fn: Callable = None):
        """Each player selects cards to pass left."""
        pass_count = self.rules["pass_count"][self.pkey]
        passed_cards = {}

        for player in self.players:
            if pass_fn:
                to_pass = pass_fn(player, self, pass_count)
            else:
                # Default: pass lowest-ranked cards
                ranked = sorted(
                    [c for c in player.hand if c.has_rank],
                    key=lambda c: c.effective_rank
                )
                non_ranked = [c for c in player.hand if not c.has_rank]
                candidates = ranked + non_ranked
                to_pass = candidates[:pass_count]

            passed_cards[player.id] = to_pass

        # Execute pass (left = next player index)
        for player in self.players:
            to_pass = passed_cards[player.id]
            for card in to_pass:
                player.hand.remove(card)

            # Receive from right (previous player)
            right_id = (player.id - 1) % self.num_players
            received = passed_cards[right_id]
            player.hand.extend(received)

        self._log(f"Card pass complete ({pass_count} cards left)")

    # ─── MAIN GAME LOOP ─────────────────────────────────────────────────

    def play_game(self, deployment_fn: Callable, pass_fn: Callable = None) -> dict:
        """Play a complete game."""
        # Card passing phase
        self.execute_pass(pass_fn)

        # Play rounds
        for round_num in range(self.num_rounds):
            self.current_round = round_num
            round_stats = self._play_round(round_num, deployment_fn)
            self.stats["rounds"].append(round_stats)

        self.game_over = True
        return self._compile_final_stats()

    def _play_round(self, round_num: int, deployment_fn: Callable) -> dict:
        # Draw condition card
        if self.condition_deck:
            self.active_condition = self.condition_deck.pop(0)
            self.stats["condition_cards_drawn"].append(self.active_condition.name)
        else:
            self.active_condition = None

        self._log(f"\n{'='*50}")
        cond_str = f" | Condition: {self.active_condition}" if self.active_condition else ""
        self._log(f"ROUND {round_num + 1}{cond_str}")

        for p in self.players:
            p.zones_won_this_round = 0

        # Create fresh zones
        self.zones = [Zone(color=c, index=i) for i, c in enumerate(self.colors)]

        # Deploy phase
        for player in self.players:
            deploy = deployment_fn(player, self, round_num)
            self._execute_deployment(player, deploy)

        # Reveal phase
        self._log("\n--- REVEAL ---")
        for zone in self.zones:
            for pid in zone.active_players:
                zp = zone.get_placement(pid)
                self._log(f"  {zone.color}: P{pid} played {zp.cards}")

        # Resolve action cards
        self._resolve_actions()

        # Score phase
        zone_strengths = self._calculate_all_strength()
        round_stats = self._score_round(zone_strengths)

        self._log(f"\nScores: {', '.join(f'P{p.id}={p.score}' for p in self.players)}")

        self.active_condition = None
        return round_stats

    # ─── DEPLOYMENT ──────────────────────────────────────────────────────

    def _execute_deployment(self, player: Player, deploy: Dict[str, List[Card]]):
        for color, cards in deploy.items():
            if not cards:
                continue
            zone = self._get_zone(color)
            zp = zone.get_placement(player.id)
            for card in cards:
                if card in player.hand:
                    player.hand.remove(card)
                    zp.cards.append(card)
                    player.cards_played_total += 1
                    if card.is_action:
                        self.stats["action_plays"][card.action_type] += 1
                    elif card.is_dud:
                        self.stats["dud_plays"] += 1

    # ─── ACTION CARD RESOLUTION ──────────────────────────────────────────

    def _resolve_actions(self):
        """Resolve action cards at each zone in fixed order: Shield → Bomb → Swap → Bounty."""
        self._log("\n--- ACTION RESOLUTION ---")

        for zone in self.zones:
            actions_here = []
            for pid in zone.active_players:
                zp = zone.get_placement(pid)
                for card in zp.cards:
                    if card.is_action:
                        actions_here.append((card, pid))

            if not actions_here:
                continue

            # Sort by resolution order
            actions_here.sort(key=lambda x: ACTION_RESOLUTION[x[0].action_type])

            # Track which players are shielded at this zone
            shielded = set()

            for card, pid in actions_here:
                if card.action_type == ACTION_SHIELD:
                    shielded.add(pid)
                    self._log(f"  {zone.color}: P{pid} Shield active")

                elif card.action_type == ACTION_BOMB:
                    # Destroy highest-ranked number card among unshielded players
                    target_card = None
                    target_pid = None
                    target_rank = -1

                    for other_pid in zone.active_players:
                        if other_pid in shielded:
                            continue
                        zp = zone.get_placement(other_pid)
                        for c in zp.cards:
                            if c.has_rank and c.effective_rank > target_rank:
                                target_rank = c.effective_rank
                                target_card = c
                                target_pid = other_pid

                    if target_card and target_pid is not None:
                        zone.get_placement(target_pid).cards.remove(target_card)
                        self.stats["bomb_kills"] += 1
                        self._log(f"  {zone.color}: P{pid} Bomb destroys {target_card} (P{target_pid})")
                    else:
                        self._log(f"  {zone.color}: P{pid} Bomb — no valid target")

                elif card.action_type == ACTION_SWAP:
                    # Swap your top ranked card here with your top ranked card
                    # at ANY other zone you occupy (no adjacency restriction).
                    zp = zone.get_placement(pid)
                    ranked_here = [c for c in zp.cards if c.has_rank]

                    # Check ALL other zones this player occupies
                    best_swap = None
                    best_gain = 0

                    for other_zone in self.zones:
                        if other_zone.index == zone.index:
                            continue
                        other_zp = other_zone.get_placement(pid)
                        other_ranked = [c for c in other_zp.cards if c.has_rank]

                        for here_card in ranked_here:
                            for other_card in other_ranked:
                                # Swap if it improves this zone's strength
                                gain = other_card.effective_rank - here_card.effective_rank
                                if gain > best_gain:
                                    best_gain = gain
                                    best_swap = (here_card, other_card, other_zone)

                    if best_swap:
                        here_card, other_card, other_zone = best_swap
                        zp.cards.remove(here_card)
                        zp.cards.append(other_card)
                        other_zp = other_zone.get_placement(pid)
                        other_zp.cards.remove(other_card)
                        other_zp.cards.append(here_card)
                        self.stats["swap_uses"] += 1
                        self._log(f"  {zone.color}: P{pid} Swap {here_card}↔{other_card} "
                                  f"(from {other_zone.color})")
                    else:
                        self._log(f"  {zone.color}: P{pid} Swap — no beneficial swap")

                elif card.action_type == ACTION_BOUNTY:
                    # Bounty is resolved during scoring, not here
                    self._log(f"  {zone.color}: P{pid} Bounty active")

    # ─── STRENGTH CALCULATION ────────────────────────────────────────────

    def _calculate_all_strength(self) -> Dict[str, Dict[int, float]]:
        self._log("\n--- STRENGTH ---")
        zone_strengths = {}

        for zone in self.zones:
            zone_strengths[zone.color] = {}
            for pid in zone.active_players:
                zp = zone.get_placement(pid)
                if not zp.cards:
                    continue
                strength = self._calculate_strength(zp.cards, zone.color)
                zone_strengths[zone.color][pid] = strength
                self.stats["strength_values"].append(strength)
                self._log(f"  {zone.color}: P{pid} → {strength} str ({len(zp.cards)} cards)")

        return zone_strengths

    def _calculate_strength(self, cards: List[Card], zone_color: str) -> int:
        """
        Strength = best rank (doubled if mascot) + 2 per extra card + 3 home field.
        Action cards don't contribute rank or count as extra.
        """
        ranked_cards = [c for c in cards if c.has_rank]
        mascots = [c for c in cards if c.is_mascot]
        action_cards = [c for c in cards if c.is_action]

        if not ranked_cards:
            return 0

        best_card = max(ranked_cards, key=lambda c: c.effective_rank)
        best_rank = best_card.effective_rank

        # Mascot doubling
        if mascots:
            best_rank *= 2
            self.stats["mascot_combos"] += 1
            # Extra cards = ranked cards - 1 (best) — mascots don't count as extra
            extra_cards = len(ranked_cards) - 1
        else:
            extra_cards = len(ranked_cards) - 1

        extra_bonus = max(0, extra_cards) * self.extra_card_bonus

        # Home Field: need a natural card matching zone color
        # Check active condition for no_home_field
        home_field = 0
        no_hf = (self.active_condition and
                 self.active_condition.effect == "no_home_field")

        if not no_hf:
            has_matching_natural = any(
                c.color == zone_color and c.is_natural
                for c in cards
            )
            if has_matching_natural:
                home_field = self.home_field_bonus
                self.stats["home_field_triggers"] += 1

        return best_rank + extra_bonus + home_field

    # ─── SCORING ─────────────────────────────────────────────────────────

    def _score_round(self, zone_strengths: Dict[str, Dict[int, float]]) -> dict:
        self._log("\n--- SCORING ---")
        cond = self.active_condition
        vp = self.base_vp
        if cond and cond.effect == "double_vp":
            vp = self.base_vp * 2

        round_stats = {
            "zone_winners": {},
            "vp_awarded": defaultdict(int),
            "strength_by_zone": zone_strengths,
            "condition": cond.name if cond else None,
        }

        for zone in self.zones:
            strength_map = zone_strengths.get(zone.color, {})
            contested = len([s for s in strength_map.values() if s > 0])
            self.stats["contested_zones"].append(contested)
            if contested == 0:
                self.stats["empty_zones"].append(1)
                round_stats["zone_winners"][zone.color] = None
                continue
            else:
                self.stats["empty_zones"].append(0)

            # Lone Wolf bonus
            lone_wolf_bonus = {}
            if cond and cond.effect == "lone_wolf_bonus":
                for pid in zone.active_players:
                    if contested == 1 and pid in strength_map:
                        lone_wolf_bonus[pid] = 3
                        self.stats["lone_wolf_zones"] += 1

            # Inversion: lowest wins
            inversion = cond and cond.effect == "lowest_wins"

            if inversion:
                target_strength = min(strength_map.values())
            else:
                target_strength = max(strength_map.values())

            if target_strength <= 0:
                round_stats["zone_winners"][zone.color] = None
                continue

            winners = [pid for pid, s in strength_map.items() if s == target_strength]

            # Tie handling
            if len(winners) > 1:
                if cond and cond.effect == "ties_lose":
                    # Nobody scores
                    self._log(f"  {zone.color}: TIE — Sudden Death, nobody scores")
                    round_stats["zone_winners"][zone.color] = []
                    continue

                elif cond and cond.effect == "fewer_cards_wins_ties":
                    # Fewer cards wins
                    min_cards = min(
                        len(zone.get_placement(w).cards) for w in winners
                    )
                    winners = [w for w in winners
                               if len(zone.get_placement(w).cards) == min_cards]

            # Check for Bounty and Shield effects
            zone_vp_awards = {}
            for w in winners:
                player_vp = vp if len(winners) == 1 else math.floor(vp / len(winners))

                # Bounty: double VP if win, 0 if lose/tie
                has_bounty = any(
                    c.is_action and c.action_type == ACTION_BOUNTY
                    for c in zone.get_placement(w).cards
                )
                if has_bounty:
                    if len(winners) == 1:
                        player_vp *= 2
                        self.stats["bounty_wins"] += 1
                    else:
                        player_vp = 0
                        self.stats["bounty_fails"] += 1

                # Lone wolf bonus
                player_vp += lone_wolf_bonus.get(w, 0)

                zone_vp_awards[w] = player_vp

            # Award VP
            for w, award in zone_vp_awards.items():
                self.players[w].score += award
                self.players[w].zones_won_this_round += 1
                self.players[w].total_zones_won += 1
                round_stats["vp_awarded"][w] += award

            # Losers: Shield consolation + track Bounty outright losses
            if len(winners) >= 1:
                losers = [pid for pid in zone.active_players if pid not in winners]
                for loser in losers:
                    zp = zone.get_placement(loser)

                    # Track Bounty outright losses (player lost the zone entirely)
                    has_bounty_loss = any(
                        c.is_action and c.action_type == ACTION_BOUNTY
                        for c in zp.cards
                    )
                    if has_bounty_loss:
                        self.stats["bounty_fails"] += 1

                    has_shield = any(
                        c.is_action and c.action_type == ACTION_SHIELD
                        for c in zp.cards
                    )
                    if has_shield:
                        consolation = self.rules["action_cards"]["shield"]["consolation_vp"]
                        # Bounty overrides Shield consolation
                        if not has_bounty_loss:
                            self.players[loser].score += consolation
                            self.stats["shield_saves"] += 1
                            round_stats["vp_awarded"][loser] += consolation

            # 2nd-place VP: award to runner-up(s) if there's a clear winner
            if self.second_place_vp > 0 and len(winners) == 1 and len(strength_map) >= 2:
                sorted_strengths = sorted(strength_map.values(), reverse=True)
                second_best = sorted_strengths[1]
                if second_best > 0:
                    runners_up = [pid for pid, s in strength_map.items()
                                  if s == second_best and pid not in winners]
                    for pid in runners_up:
                        self.players[pid].score += self.second_place_vp
                        round_stats["vp_awarded"][pid] += self.second_place_vp
                        self.stats["second_place_awards"] += 1
                        self._log(f"  {zone.color}: P{pid} 2nd place → +{self.second_place_vp} VP")

            winner_str = ", ".join(f"P{w}" for w in winners)
            self._log(f"  {zone.color}: {winner_str} wins ({target_strength} str) "
                      f"→ {zone_vp_awards}")
            round_stats["zone_winners"][zone.color] = winners

        # Fortify bonus (3+ cards at a zone)
        if cond and cond.effect == "big_stack_bonus":
            for player in self.players:
                for zone in self.zones:
                    zp = zone.get_placement(player.id)
                    if len(zp.cards) >= 3:
                        player.score += 2
                        round_stats["vp_awarded"][player.id] += 2
                        self._log(f"  Fortify: P{player.id} +2 VP at {zone.color}")

        self.stats["cards_per_zone"].extend(
            len(zone.get_placement(pid).cards)
            for zone in self.zones
            for pid in zone.active_players
        )

        return round_stats

    # ─── CONDITION CARD HELPERS ──────────────────────────────────────────

    def get_active_condition_effect(self) -> str:
        """Return the active condition effect string, or empty."""
        if self.active_condition:
            return self.active_condition.effect
        return ""

    def validate_deployment(self, deploy: Dict[str, List[Card]],
                            player: Player) -> bool:
        """Check if a deployment satisfies the active condition."""
        cond = self.active_condition
        if not cond:
            return True

        all_cards = [c for cards in deploy.values() for c in cards]
        zones_used = [color for color, cards in deploy.items() if cards]

        if cond.effect == "no_mascots":
            if any(c.is_mascot for c in all_cards):
                return False

        elif cond.effect == "unique_colors_per_zone":
            # No two cards of the same color at the same zone
            for color, cards in deploy.items():
                card_colors = [c.color for c in cards if c.has_rank or c.is_mascot]
                if len(card_colors) != len(set(card_colors)):
                    return False

        elif cond.effect == "max_cards_4":
            if len(all_cards) > 4:
                return False

        elif cond.effect == "max_2_zones":
            if len(zones_used) > 2:
                return False

        elif cond.effect == "min_2_zones":
            # Spread Out: play to at least 2 zones (scaled down from 3)
            if len(all_cards) > 0 and len(zones_used) < 2:
                return False

        return True

    # ─── FINAL STATS ─────────────────────────────────────────────────────

    def _compile_final_stats(self) -> dict:
        scores = {p.id: p.score for p in self.players}
        max_score = max(scores.values())
        winners = [pid for pid, s in scores.items() if s == max_score]

        if len(winners) > 1:
            max_zones = max(self.players[w].total_zones_won for w in winners)
            winners = [w for w in winners if self.players[w].total_zones_won == max_zones]

        return {
            "seed": self.seed,
            "num_players": self.num_players,
            "winner": winners[0] if len(winners) == 1 else winners,
            "scores": scores,
            "zones_won": {p.id: p.total_zones_won for p in self.players},
            "cards_played": {p.id: p.cards_played_total for p in self.players},
            "cards_remaining": {p.id: len(p.hand) for p in self.players},
            "strength_values": self.stats["strength_values"],
            "cards_per_zone": self.stats["cards_per_zone"],
            "home_field_triggers": self.stats["home_field_triggers"],
            "mascot_combos": self.stats["mascot_combos"],
            "action_plays": dict(self.stats["action_plays"]),
            "dud_plays": self.stats["dud_plays"],
            "shield_saves": self.stats["shield_saves"],
            "bomb_kills": self.stats["bomb_kills"],
            "swap_uses": self.stats["swap_uses"],
            "bounty_wins": self.stats["bounty_wins"],
            "bounty_fails": self.stats["bounty_fails"],
            "condition_cards": self.stats["condition_cards_drawn"],
            "contested_zones": self.stats["contested_zones"],
            "lone_wolf_zones": self.stats["lone_wolf_zones"],
            "second_place_awards": self.stats["second_place_awards"],
        }

    # ─── HELPERS ─────────────────────────────────────────────────────────

    def _get_zone(self, color: str) -> Zone:
        idx = COLOR_ORDER[color]
        return self.zones[idx]

    def _log(self, msg: str):
        self.log.append(msg)
