#!/usr/bin/env python3
"""
Test new action card designs and the "Spice Option" randomized pool.

New actions (joining Shield, Bomb, Swap, Bounty):
  - Heist:       Steal opponent's best card at this zone, add to your stack
  - Contaminate: This zone scores inverted (lowest wins) regardless of condition
  - Ambush:      If you're the only player at this zone, +5 Strength

Pool system: randomize 4 from 7 at game setup.

Metrics:
  - Style balance (gap)
  - HF in wins
  - Action fire/success rates
  - VP distribution
  - Yomi proxy: does the pool create more varied game outcomes?
"""

import copy
import json
import math
import os
import random
import statistics
import sys
from collections import defaultdict
from typing import List, Dict, Optional
from itertools import combinations

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cards_v4 import (
    Card, COLORS, COLOR_ORDER,
    CARD_TYPE_NUMBER, CARD_TYPE_MASCOT, CARD_TYPE_ACTION, CARD_TYPE_DUD,
    ACTION_SHIELD, ACTION_BOMB, ACTION_SWAP, ACTION_BOUNTY,
    ACTION_RESOLUTION,
)
from game_state_v4 import GameStateV4, Zone, ConditionCard
from ai_player_v4 import AIPlayerV4, STYLE_PROFILES


# ─── NEW ACTION CONSTANTS ─────────────────────────────────────────────────

ACTION_HEIST = "heist"
ACTION_CONTAMINATE = "contaminate"
ACTION_AMBUSH = "ambush"

# Extended resolution order (Heist before Bomb so stolen card is gone first)
EXTENDED_RESOLUTION = {
    ACTION_SHIELD: 1,
    ACTION_HEIST: 2,       # Resolve before Bomb — steal first
    ACTION_BOMB: 3,
    ACTION_SWAP: 4,
    ACTION_CONTAMINATE: 5, # Contaminate is a scoring modifier, resolves late
    ACTION_BOUNTY: 6,
    ACTION_AMBUSH: 7,      # Ambush is strength modifier, resolves last
}

# All 7 action cards with their "default" color assignments
ALL_ACTIONS = {
    ACTION_SHIELD:      {"color": "RED",    "name": "Shield"},
    ACTION_BOMB:        {"color": "YELLOW", "name": "Bomb"},
    ACTION_SWAP:        {"color": "GREEN",  "name": "Swap"},
    ACTION_BOUNTY:      {"color": "BLUE",   "name": "Bounty"},
    ACTION_HEIST:       {"color": "RED",    "name": "Heist"},      # shares RED
    ACTION_CONTAMINATE: {"color": "GREEN",  "name": "Contaminate"}, # shares GREEN
    ACTION_AMBUSH:      {"color": "YELLOW", "name": "Ambush"},     # shares YELLOW
}


# ─── POOL GAME STATE ──────────────────────────────────────────────────────

class PoolGameState(GameStateV4):
    """Game state that supports a configurable action card pool."""

    def __init__(self, num_players, seed=42, config=None,
                 action_pool=None):
        """
        action_pool: list of 4 action type strings to use in this game.
                     e.g. ["shield", "bomb", "contaminate", "ambush"]
                     Each gets assigned to one of the 4 colors.
        """
        self.action_pool = action_pool or [
            ACTION_SHIELD, ACTION_BOMB, ACTION_SWAP, ACTION_BOUNTY
        ]
        # Track new action stats
        self._heist_steals = 0
        self._contaminate_inversions = 0
        self._ambush_triggers = 0
        self._ambush_blocked = 0
        self._contaminated_zones = set()  # zone colors inverted this round

        super().__init__(num_players, seed=seed, config=config)

    def _build_custom_deck(self):
        """Override deck building to use custom action pool."""
        # This is called indirectly — we patch after __init__
        pass

    def __init__(self, num_players, seed=42, config=None, action_pool=None):
        self.action_pool = action_pool or [
            ACTION_SHIELD, ACTION_BOMB, ACTION_SWAP, ACTION_BOUNTY
        ]
        self._heist_steals = 0
        self._contaminate_inversions = 0
        self._ambush_triggers = 0
        self._ambush_blocked = 0
        self._contaminated_zones = set()

        # Do normal init but then patch the deck
        super().__init__(num_players, seed=seed, config=config)

        # Replace action cards in hands with our pool assignments
        # Map: pool index → color
        pool_color_map = {}
        for i, action_type in enumerate(self.action_pool):
            pool_color_map[COLORS[i]] = action_type

        # Walk through all player hands and replace action cards
        for player in self.players:
            new_hand = []
            for card in player.hand:
                if card.is_action:
                    # Replace with the pool's action for this color
                    new_action_type = pool_color_map.get(card.color, card.action_type)
                    new_card = Card(
                        color=card.color,
                        card_type=CARD_TYPE_ACTION,
                        rank=0,
                        action_type=new_action_type
                    )
                    new_hand.append(new_card)
                else:
                    new_hand.append(card)
            player.hand = new_hand

        # Also patch unused cards
        new_unused = []
        for card in self.unused_cards:
            if card.is_action:
                new_action_type = pool_color_map.get(card.color, card.action_type)
                new_card = Card(
                    color=card.color,
                    card_type=CARD_TYPE_ACTION,
                    rank=0,
                    action_type=new_action_type
                )
                new_unused.append(new_card)
            else:
                new_unused.append(card)
        self.unused_cards = new_unused

    def _resolve_actions(self):
        """Extended action resolution with Heist, Contaminate, Ambush."""
        self._log("\n--- ACTION RESOLUTION ---")
        self._contaminated_zones = set()

        for zone in self.zones:
            actions_here = []
            for pid in zone.active_players:
                zp = zone.get_placement(pid)
                for card in zp.cards:
                    if card.is_action:
                        actions_here.append((card, pid))

            if not actions_here:
                continue

            # Sort by extended resolution order
            actions_here.sort(
                key=lambda x: EXTENDED_RESOLUTION.get(x[0].action_type, 99)
            )

            shielded = set()

            for card, pid in actions_here:
                if card.action_type == ACTION_SHIELD:
                    shielded.add(pid)
                    self._log(f"  {zone.color}: P{pid} Shield active")

                elif card.action_type == ACTION_HEIST:
                    # Steal best card from strongest unshielded opponent
                    best_target_card = None
                    best_target_pid = None
                    best_rank = -1

                    for other_pid in zone.active_players:
                        if other_pid == pid or other_pid in shielded:
                            continue
                        other_zp = zone.get_placement(other_pid)
                        for c in other_zp.cards:
                            if c.has_rank and c.effective_rank > best_rank:
                                best_rank = c.effective_rank
                                best_target_card = c
                                best_target_pid = other_pid

                    if best_target_card and best_target_pid is not None:
                        # Remove from opponent, add to heist player
                        zone.get_placement(best_target_pid).cards.remove(best_target_card)
                        zone.get_placement(pid).cards.append(best_target_card)
                        self._heist_steals += 1
                        self._log(f"  {zone.color}: P{pid} Heist steals {best_target_card} from P{best_target_pid}")
                    else:
                        self._log(f"  {zone.color}: P{pid} Heist — no valid target")

                elif card.action_type == ACTION_BOMB:
                    # Standard Bomb logic
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

                elif card.action_type == ACTION_SWAP:
                    # Standard Swap logic
                    zp = zone.get_placement(pid)
                    ranked_here = [c for c in zp.cards if c.has_rank]
                    best_swap = None
                    best_gain = 0

                    for other_zone in self.zones:
                        if other_zone.index == zone.index:
                            continue
                        other_zp = other_zone.get_placement(pid)
                        other_ranked = [c for c in other_zp.cards if c.has_rank]

                        for here_card in ranked_here:
                            for other_card in other_ranked:
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
                        self._log(f"  {zone.color}: P{pid} Swap {here_card}↔{other_card}")

                elif card.action_type == ACTION_CONTAMINATE:
                    # Mark this zone as inverted for scoring
                    self._contaminated_zones.add(zone.color)
                    self._contaminate_inversions += 1
                    self._log(f"  {zone.color}: P{pid} Contaminate — zone scores inverted!")

                elif card.action_type == ACTION_BOUNTY:
                    self._log(f"  {zone.color}: P{pid} Bounty active")

                elif card.action_type == ACTION_AMBUSH:
                    # Ambush resolves during strength calc, just log it here
                    self._log(f"  {zone.color}: P{pid} Ambush set")

    def _calculate_strength(self, cards, zone_color):
        """Extended strength calc with Ambush bonus."""
        ranked_cards = [c for c in cards if c.has_rank]
        mascots = [c for c in cards if c.is_mascot]

        if not ranked_cards:
            return 0

        best_card = max(ranked_cards, key=lambda c: c.effective_rank)
        best_rank = best_card.effective_rank

        if mascots:
            best_rank *= 2
            self.stats["mascot_combos"] += 1
            extra_cards = len(ranked_cards) - 1
        else:
            extra_cards = len(ranked_cards) - 1

        extra_bonus = max(0, extra_cards) * self.extra_card_bonus

        # Home Field
        home_field = 0
        no_hf = (self.active_condition and
                 self.active_condition.effect == "no_home_field")

        if not no_hf:
            has_matching_natural = any(
                c.color == zone_color and c.is_natural for c in cards
            )
            if has_matching_natural:
                home_field = self.home_field_bonus
                self.stats["home_field_triggers"] += 1

        # Ambush: +5 if alone at this zone
        ambush_bonus = 0
        has_ambush = any(c.is_action and c.action_type == ACTION_AMBUSH for c in cards)
        if has_ambush:
            # Check if player is alone at this zone
            zone = None
            for z in self.zones:
                if z.color == zone_color:
                    zone = z
                    break
            if zone and len(zone.active_players) == 1:
                ambush_bonus = 5
                self._ambush_triggers += 1
            else:
                self._ambush_blocked += 1

        return best_rank + extra_bonus + home_field + ambush_bonus

    def _score_round(self, zone_strengths):
        """Extended scoring with Contaminate inversion."""
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

            # Inversion: from condition OR from Contaminate
            inversion = (cond and cond.effect == "lowest_wins") or \
                        (zone.color in self._contaminated_zones)

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
                    self._log(f"  {zone.color}: TIE — Sudden Death, nobody scores")
                    round_stats["zone_winners"][zone.color] = []
                    continue
                elif cond and cond.effect == "fewer_cards_wins_ties":
                    min_cards = min(len(zone.get_placement(w).cards) for w in winners)
                    winners = [w for w in winners
                               if len(zone.get_placement(w).cards) == min_cards]

            # VP awards with Bounty
            zone_vp_awards = {}
            for w in winners:
                player_vp = vp if len(winners) == 1 else math.floor(vp / len(winners))
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

                player_vp += lone_wolf_bonus.get(w, 0)
                zone_vp_awards[w] = player_vp

            for w, award in zone_vp_awards.items():
                self.players[w].score += award
                self.players[w].zones_won_this_round += 1
                self.players[w].total_zones_won += 1
                round_stats["vp_awarded"][w] += award

            # Losers
            if len(winners) >= 1:
                losers = [pid for pid in zone.active_players if pid not in winners]
                for loser in losers:
                    zp = zone.get_placement(loser)
                    has_bounty_loss = any(
                        c.is_action and c.action_type == ACTION_BOUNTY for c in zp.cards
                    )
                    if has_bounty_loss:
                        self.stats["bounty_fails"] += 1
                    has_shield = any(
                        c.is_action and c.action_type == ACTION_SHIELD for c in zp.cards
                    )
                    if has_shield and not has_bounty_loss:
                        consolation = self.rules["action_cards"]["shield"]["consolation_vp"]
                        self.players[loser].score += consolation
                        self.stats["shield_saves"] += 1
                        round_stats["vp_awarded"][loser] += consolation

            # 2nd-place VP
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

            winner_str = ", ".join(f"P{w}" for w in winners)
            inv_tag = " [CONTAMINATED]" if zone.color in self._contaminated_zones else ""
            self._log(f"  {zone.color}{inv_tag}: {winner_str} wins ({target_strength} str)")
            round_stats["zone_winners"][zone.color] = winners

        # Fortify bonus
        if cond and cond.effect == "big_stack_bonus":
            for player in self.players:
                for zone in self.zones:
                    zp = zone.get_placement(player.id)
                    if len(zp.cards) >= 3:
                        player.score += 2
                        round_stats["vp_awarded"][player.id] += 2

        self.stats["cards_per_zone"].extend(
            len(zone.get_placement(pid).cards)
            for zone in self.zones
            for pid in zone.active_players
        )

        return round_stats

    def _play_round(self, round_num, deployment_fn):
        """Reset contaminated zones each round."""
        self._contaminated_zones = set()
        return super()._play_round(round_num, deployment_fn)


# ─── EXTENDED AI ──────────────────────────────────────────────────────────

class PoolAIPlayer(AIPlayerV4):
    """AI that understands the new action cards."""

    def _choose_zone_for_action(self, card, assignments, colors,
                                 max_zones, cond_effect, used):
        """Extended action placement for new cards."""
        # Handle original 4 actions normally
        if card.action_type in (ACTION_SHIELD, ACTION_BOMB, ACTION_SWAP, ACTION_BOUNTY):
            return super()._choose_zone_for_action(
                card, assignments, colors, max_zones, cond_effect, used
            )

        def populated_zones():
            result = {}
            for color in colors:
                cards_there = assignments.get(color, [])
                ranked = [c for c in cards_there if c.has_rank]
                if ranked:
                    result[color] = sum(c.effective_rank for c in ranked)
            return result

        if card.action_type == ACTION_HEIST:
            # Heist: play at zones where we're present but outgunned.
            # Also good at contested zones with opponents likely to stack.
            # Best: zone where we have moderate strength (we benefit from stolen card).
            pz = populated_zones()
            if not pz:
                return None
            # Prefer zones where we have some presence (stolen card adds to our stack)
            # but not our absolute strongest (opponents might dodge our strongest zone)
            sorted_zones = sorted(pz.keys(), key=lambda z: pz[z])
            if len(sorted_zones) >= 2:
                # Second-strongest zone — likely contested
                return sorted_zones[-2]
            return sorted_zones[0]

        elif card.action_type == ACTION_CONTAMINATE:
            # Contaminate: play at zones where we have LOW cards.
            # Under inversion, low strength wins — so deploy junk + Contaminate.
            pz = populated_zones()
            if not pz:
                # No presence yet — pick a zone we'd play weak cards at
                return None

            # Find zone where our strength is lowest (best for inversion)
            weakest = min(pz, key=pz.get)
            return weakest

        elif card.action_type == ACTION_AMBUSH:
            # Ambush: play at zones we think will be uncontested.
            # Heuristic: play at zone where we have moderate cards
            # (opponents less likely to contest non-premium zones)
            pz = populated_zones()
            if not pz:
                return None

            # Best zone: moderate strength (not so strong others will contest,
            # not so weak it's not worth it even with +5)
            if len(pz) >= 2:
                sorted_zones = sorted(pz.keys(), key=lambda z: pz[z])
                # Pick middle-ish zone
                return sorted_zones[len(sorted_zones) // 2]
            return list(pz.keys())[0]

        return None


# ─── SIMULATION RUNNER ────────────────────────────────────────────────────

def load_config():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config_v4.json")
    with open(path) as f:
        return json.load(f)


def run_pool_games(num_games, num_players, styles, config, action_pool, label=""):
    """Run games with a specific action pool and collect comprehensive stats."""
    style_wins = defaultdict(float)
    style_games = defaultdict(int)
    style_scores = defaultdict(list)
    all_winner_scores = []
    all_spreads = []
    total_heists = 0
    total_contaminates = 0
    total_ambush_fire = 0
    total_ambush_block = 0
    hf_in_wins = 0
    no_hf_in_wins = 0

    for i in range(num_games):
        seed = 1 + i
        game_styles = [styles[(i + j) % len(styles)] for j in range(num_players)]

        game = PoolGameState(num_players, seed=seed, config=config,
                             action_pool=action_pool)
        ais = [PoolAIPlayer(pid, skill=1.0, style=game_styles[pid],
                             rng_seed=seed * 100 + pid) for pid in range(num_players)]

        def dfn(p, gs, rn):
            return ais[p.id].choose_deployment(p, gs, rn)

        def pfn(p, gs, pc):
            return ais[p.id].choose_pass(p, gs, pc)

        result = game.play_game(dfn, pfn)

        winner = result["winner"]
        if isinstance(winner, list):
            for w in winner:
                style_wins[game_styles[w]] += 1.0 / len(winner)
        else:
            style_wins[game_styles[winner]] += 1

        scores = list(result["scores"].values())
        all_winner_scores.append(max(scores))
        all_spreads.append(max(scores) - min(scores))

        for pid, score in result["scores"].items():
            style_scores[game_styles[pid]].append(score)
            style_games[game_styles[pid]] += 1

        total_heists += game._heist_steals
        total_contaminates += game._contaminate_inversions
        total_ambush_fire += game._ambush_triggers
        total_ambush_block += game._ambush_blocked

    return {
        "label": label,
        "action_pool": action_pool,
        "win_rates": {s: style_wins[s] / style_games[s]
                      if style_games[s] > 0 else 0
                      for s in set(styles)},
        "avg_vp": {s: statistics.mean(style_scores[s])
                   if style_scores[s] else 0
                   for s in set(styles)},
        "avg_winner_score": statistics.mean(all_winner_scores),
        "avg_spread": statistics.mean(all_spreads),
        "heists_per_game": total_heists / num_games,
        "contaminates_per_game": total_contaminates / num_games,
        "ambush_fires_per_game": total_ambush_fire / num_games,
        "ambush_blocks_per_game": total_ambush_block / num_games,
    }


def run_randomized_pool(num_games, num_players, styles, config, full_pool, pool_size=4):
    """Run games where the action pool is randomized each game from full_pool."""
    style_wins = defaultdict(float)
    style_games = defaultdict(int)
    style_scores = defaultdict(list)
    all_winner_scores = []
    all_spreads = []
    pool_counts = defaultdict(int)

    for i in range(num_games):
        seed = 1 + i
        game_rng = random.Random(seed * 7)
        game_styles = [styles[(i + j) % len(styles)] for j in range(num_players)]

        # Randomize the pool for this game
        pool = sorted(game_rng.sample(full_pool, pool_size))
        for a in pool:
            pool_counts[a] += 1

        game = PoolGameState(num_players, seed=seed, config=config,
                             action_pool=pool)
        ais = [PoolAIPlayer(pid, skill=1.0, style=game_styles[pid],
                             rng_seed=seed * 100 + pid) for pid in range(num_players)]

        def dfn(p, gs, rn):
            return ais[p.id].choose_deployment(p, gs, rn)

        def pfn(p, gs, pc):
            return ais[p.id].choose_pass(p, gs, pc)

        result = game.play_game(dfn, pfn)

        winner = result["winner"]
        if isinstance(winner, list):
            for w in winner:
                style_wins[game_styles[w]] += 1.0 / len(winner)
        else:
            style_wins[game_styles[winner]] += 1

        scores = list(result["scores"].values())
        all_winner_scores.append(max(scores))
        all_spreads.append(max(scores) - min(scores))

        for pid, score in result["scores"].items():
            style_scores[game_styles[pid]].append(score)
            style_games[game_styles[pid]] += 1

    return {
        "label": f"RANDOM POOL (pick {pool_size} from {len(full_pool)})",
        "win_rates": {s: style_wins[s] / style_games[s]
                      if style_games[s] > 0 else 0
                      for s in set(styles)},
        "avg_vp": {s: statistics.mean(style_scores[s])
                   if style_scores[s] else 0
                   for s in set(styles)},
        "avg_winner_score": statistics.mean(all_winner_scores),
        "avg_spread": statistics.mean(all_spreads),
        "pool_frequency": dict(pool_counts),
        "score_stdev": statistics.stdev(all_winner_scores),
    }


# ─── MAIN ─────────────────────────────────────────────────────────────────

def main():
    N = 2000
    config = load_config()

    ORIGINAL_4 = [ACTION_SHIELD, ACTION_BOMB, ACTION_SWAP, ACTION_BOUNTY]
    FULL_POOL_7 = ORIGINAL_4 + [ACTION_HEIST, ACTION_CONTAMINATE, ACTION_AMBUSH]

    # Test scenarios: original 4, each new card swapped in, and random pool
    swap_scenarios = [
        (ORIGINAL_4, "ORIGINAL 4 (Shield/Bomb/Swap/Bounty)"),
        # Swap in Heist for Bomb (both destruction)
        ([ACTION_SHIELD, ACTION_HEIST, ACTION_SWAP, ACTION_BOUNTY],
         "HEIST replaces Bomb"),
        # Swap in Contaminate for Swap (both positional)
        ([ACTION_SHIELD, ACTION_BOMB, ACTION_CONTAMINATE, ACTION_BOUNTY],
         "CONTAMINATE replaces Swap"),
        # Swap in Ambush for Bounty (both reward gambles)
        ([ACTION_SHIELD, ACTION_BOMB, ACTION_SWAP, ACTION_AMBUSH],
         "AMBUSH replaces Bounty"),
        # All new
        ([ACTION_SHIELD, ACTION_HEIST, ACTION_CONTAMINATE, ACTION_AMBUSH],
         "ALL NEW (Shield/Heist/Contaminate/Ambush)"),
    ]

    style_sets = {
        3: ["balanced", "aggressive", "sniper"],
        4: ["balanced", "aggressive", "sniper", "hoarder"],
    }

    print("=" * 70)
    print("  ACTION CARD POOL TEST")
    print(f"  {N} games per scenario per player count")
    print("=" * 70)

    for np in [3, 4]:
        styles = style_sets[np]
        fair = 1.0 / np

        print(f"\n{'='*70}")
        print(f"  {np} PLAYERS")
        print(f"{'='*70}")

        results = []

        # Fixed pool scenarios
        for pool, label in swap_scenarios:
            print(f"\n▶ {label}...", end="", flush=True)
            data = run_pool_games(N, np, styles, config, pool, label)
            results.append(data)
            print(" done")

        # Random pool from all 7
        print(f"\n▶ RANDOM POOL (4 from 7)...", end="", flush=True)
        rp_data = run_randomized_pool(N, np, styles, config, FULL_POOL_7, 4)
        results.append(rp_data)
        print(" done")

        # ── Print results ──
        for data in results:
            label = data["label"]
            print(f"\n  ── {label} ──")

            sorted_styles = sorted(data["win_rates"].keys(),
                                   key=lambda s: -data["win_rates"][s])
            max_wr = max(data["win_rates"].values())
            min_wr = min(data["win_rates"].values())
            gap = max_wr - min_wr

            print(f"  {'Style':<12} {'Win%':>7} {'Avg VP':>8}")
            for s in sorted_styles:
                wr = data["win_rates"][s]
                vp = data["avg_vp"][s]
                print(f"  {s:<12} {wr:6.1%} {vp:7.1f}")

            print(f"\n  Style gap: {gap:.1%}  |  Winner VP: {data['avg_winner_score']:.1f}  |  Spread: {data['avg_spread']:.1f}")

            # New action stats
            if "heists_per_game" in data:
                extras = []
                if data.get("heists_per_game", 0) > 0:
                    extras.append(f"Heists: {data['heists_per_game']:.2f}/game")
                if data.get("contaminates_per_game", 0) > 0:
                    extras.append(f"Contaminates: {data['contaminates_per_game']:.2f}/game")
                if data.get("ambush_fires_per_game", 0) > 0:
                    fires = data["ambush_fires_per_game"]
                    blocks = data.get("ambush_blocks_per_game", 0)
                    total = fires + blocks
                    rate = fires / total if total > 0 else 0
                    extras.append(f"Ambush: {fires:.2f}/game ({rate:.0%} success)")
                if extras:
                    print(f"  {' | '.join(extras)}")

            if "pool_frequency" in data:
                print(f"  Pool appearances: ", end="")
                pf = data["pool_frequency"]
                print(", ".join(f"{a}={pf.get(a,0)}" for a in FULL_POOL_7))
                print(f"  Score σ: {data.get('score_stdev', 0):.1f}")

            # Grade
            if gap <= 0.08:
                bal_grade = "✅ balanced"
            elif gap <= 0.15:
                bal_grade = "👍 acceptable"
            else:
                bal_grade = "⚠️ imbalanced"
            print(f"  Verdict: {bal_grade}")

    # ── SUMMARY ──
    print(f"\n{'='*70}")
    print("  SUMMARY")
    print(f"{'='*70}")
    print("""
  Compare across scenarios:
  - Style gap: lower is better (target < 10%)
  - Winner VP: should stay ~same as original (no inflation)
  - New action fire rates: are they actually getting used?
  - Ambush success rate: if too high, +5 is too easy; if too low, card is dead

  Key questions:
  1. Do any new actions break balance?
  2. Does the random pool create enough variety without chaos?
  3. Which fixed-4 set has the best combination of balance + interaction?
""")


if __name__ == "__main__":
    main()
