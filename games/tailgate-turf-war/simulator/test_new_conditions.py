#!/usr/bin/env python3
"""
Test 20 candidate condition cards (5 existing + 15 new).
Goal: find 12 that create the most varied, interesting rounds.

Each condition is tested by running 2000 games where EVERY round uses
that condition (to measure its isolated effect). Metrics:
  - Style gap (does it break balance?)
  - Winner VP / spread (does it warp scoring?)
  - HF relevance (does it change how much HF matters?)
  - Sniper win% (does it shake up dominant strategies?)
  - VP variance σ (does it create different outcomes?)

All games use per-round passing (2 cards/round) + zone-matched HF=3.
"""

import copy
import json
import math
import os
import random
import statistics
import sys
from collections import defaultdict
from typing import List, Dict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cards_v4 import (
    Card, COLORS, COLOR_ORDER,
    CARD_TYPE_NUMBER, CARD_TYPE_MASCOT, CARD_TYPE_ACTION, CARD_TYPE_DUD,
    ACTION_SHIELD, ACTION_BOMB, ACTION_SWAP, ACTION_BOUNTY,
)
from game_state_v4 import GameStateV4, Zone, ConditionCard
from ai_player_v4 import AIPlayerV4


# ─── CONDITION DEFINITIONS ────────────────────────────────────────────────

# Each condition has: name, effect key, category, description
CANDIDATE_CONDITIONS = [
    # === EXISTING (5) ===
    ("Inversion", "lowest_wins", "scoring", "Lowest strength wins each zone"),
    ("Double Stakes", "double_vp", "scoring", "Zones worth 10 VP instead of 5"),
    ("Neutral Ground", "no_home_field", "scoring", "No Home Field this round"),
    ("Sudden Death", "ties_lose", "scoring", "Ties score 0 for all tied players"),
    ("Spread Out", "min_2_zones", "placement", "Must play to 2+ zones"),

    # === NEW HF DISRUPTORS (5) ===
    ("Foreign Exchange", "foreign_exchange", "hf_disrupt",
     "HF triggers only if card color does NOT match zone color"),
    ("Exile", "exile", "hf_disrupt",
     "Cannot play cards at the zone matching their color"),
    ("Color Tax", "color_tax", "hf_disrupt",
     "Home Field is -2 instead of +3 (matching color penalized)"),
    ("Mercenary", "mercenary", "hf_disrupt",
     "Off-color cards at a zone get +1 strength each"),
    ("Peasant Revolt", "peasant_revolt", "rank_disrupt",
     "Cards ranked 3 or below get +5 bonus"),

    # === NEW RANK/SCORING (5) ===
    ("Mirror", "mirror_ranks", "rank_disrupt",
     "Card rank becomes 10 minus printed rank"),
    ("Ceiling", "ceiling_5", "rank_disrupt",
     "All cards capped at rank 5"),
    ("Diminishing Returns", "diminishing_returns", "scoring",
     "1st zone=7 VP, 2nd=5, 3rd=3, 4th=1"),
    ("Consolation Prize", "consolation_prize", "scoring",
     "Losers at contested zones get 2 VP each"),
    ("Charity", "charity", "scoring",
     "2nd place gets 3 VP instead of 1"),

    # === NEW DEPLOYMENT/INTERACTION (5) ===
    ("Overkill", "overkill", "placement",
     "Must play ALL remaining cards this round"),
    ("Minimalist", "minimalist", "card_restriction",
     "Max 2 cards total this round"),
    ("Lone Wolf", "lone_wolf_max1", "placement",
     "Max 1 card per zone"),
    ("Grudge Match", "grudge_match", "momentum",
     "Fewest zones won last round → +3 all cards"),
    ("Second Wave", "second_wave", "interaction",
     "After reveal, deploy 1 more card from hand"),
]


# ─── CONDITION GAME STATE ─────────────────────────────────────────────────

class ConditionTestGame(GameStateV4):
    """Game that applies a specific new condition every round."""

    def __init__(self, num_players, seed=42, config=None,
                 pass_per_round=2, test_condition=None):
        self.pass_per_round = pass_per_round
        self.test_condition_effect = test_condition
        self._hf_hits = 0
        self._hf_checks = 0
        self._zones_won_last_round = defaultdict(int)
        self._grudge_bonus_applied = 0
        super().__init__(num_players, seed=seed, config=config)

        # Override condition deck with our test condition
        if test_condition:
            cond_name = next((c[0] for c in CANDIDATE_CONDITIONS
                             if c[1] == test_condition), test_condition)
            self.condition_deck = [
                ConditionCard(cond_name, "test", test_condition)
                for _ in range(self.num_rounds)
            ]

    def play_game(self, deployment_fn, pass_fn=None):
        for round_num in range(self.num_rounds):
            self.current_round = round_num
            self._execute_round_pass(pass_fn)
            round_stats = self._play_round_with_condition(round_num, deployment_fn)
            self.stats["rounds"].append(round_stats)

            # Track zones won per player for Grudge Match
            self._zones_won_last_round = defaultdict(int)
            for zone_color, winners in round_stats["zone_winners"].items():
                if winners and isinstance(winners, list):
                    for w in winners:
                        self._zones_won_last_round[w] += 1

        self.game_over = True
        return self._compile_final_stats()

    def _execute_round_pass(self, pass_fn=None):
        pass_count = self.pass_per_round
        passed_cards = {}
        for player in self.players:
            actual_pass = min(pass_count, max(0, len(player.hand) - 1))
            if actual_pass <= 0:
                passed_cards[player.id] = []
                continue
            if pass_fn:
                to_pass = pass_fn(player, self, actual_pass)
            else:
                ranked = sorted([c for c in player.hand if c.has_rank],
                                key=lambda c: c.effective_rank)
                non_ranked = [c for c in player.hand if not c.has_rank]
                to_pass = (ranked + non_ranked)[:actual_pass]
            passed_cards[player.id] = to_pass

        for player in self.players:
            for card in passed_cards[player.id]:
                if card in player.hand:
                    player.hand.remove(card)
            right_id = (player.id - 1) % self.num_players
            player.hand.extend(passed_cards[right_id])

    def _play_round_with_condition(self, round_num, deployment_fn):
        # Draw condition
        if self.condition_deck:
            self.active_condition = self.condition_deck.pop(0)
            self.stats["condition_cards_drawn"].append(self.active_condition.name)
        else:
            self.active_condition = None

        for p in self.players:
            p.zones_won_this_round = 0
        self.zones = [Zone(color=c, index=i) for i, c in enumerate(self.colors)]

        # Deploy
        for player in self.players:
            deploy = deployment_fn(player, self, round_num)

            # Apply deployment-modifying conditions
            cond = self.test_condition_effect
            if cond == "exile":
                deploy = self._apply_exile(deploy)
            elif cond == "overkill":
                # Force all remaining cards to be played
                # (AI already handles this — just ensure nothing held back)
                pass
            elif cond == "minimalist":
                deploy = self._apply_minimalist(deploy, 2)
            elif cond == "lone_wolf_max1":
                deploy = self._apply_lone_wolf(deploy)

            self._execute_deployment(player, deploy)

        # Second Wave: after reveal, deploy 1 more card each
        if self.test_condition_effect == "second_wave":
            for player in self.players:
                if player.hand:
                    # Pick best remaining card, deploy to strongest zone
                    best_card = max(
                        [c for c in player.hand if c.has_rank],
                        key=lambda c: c.effective_rank,
                        default=None
                    )
                    if best_card:
                        # Deploy to zone where player already has presence
                        best_zone = None
                        best_str = -1
                        for zone in self.zones:
                            zp = zone.get_placement(player.id)
                            if zp.cards:
                                s = sum(c.effective_rank for c in zp.cards if c.has_rank)
                                if s > best_str:
                                    best_str = s
                                    best_zone = zone
                        if best_zone:
                            player.hand.remove(best_card)
                            best_zone.get_placement(player.id).cards.append(best_card)
                            player.cards_played_total += 1

        self._resolve_actions()
        zone_strengths = self._calculate_all_strength_custom()
        round_stats = self._score_round_custom(zone_strengths)
        self.active_condition = None
        return round_stats

    def _apply_exile(self, deploy):
        """Remove cards whose color matches the zone they're deployed to."""
        filtered = {}
        for zone_color, cards in deploy.items():
            allowed = [c for c in cards if c.color != zone_color or not c.is_natural]
            if allowed:
                filtered[zone_color] = allowed
        return filtered if filtered else deploy  # fallback if everything exiled

    def _apply_minimalist(self, deploy, max_cards):
        """Limit total deployed cards."""
        all_cards = [(c, zone) for zone, cards in deploy.items() for c in cards]
        all_cards.sort(key=lambda x: x[0].effective_rank, reverse=True)
        result = defaultdict(list)
        for card, zone in all_cards[:max_cards]:
            result[zone].append(card)
        return dict(result)

    def _apply_lone_wolf(self, deploy):
        """Max 1 card per zone — keep highest."""
        result = {}
        for zone, cards in deploy.items():
            if cards:
                best = max(cards, key=lambda c: c.effective_rank if c.has_rank else -1)
                result[zone] = [best]
        return result

    def _calculate_all_strength_custom(self):
        zone_strengths = {}
        for zone in self.zones:
            zone_strengths[zone.color] = {}
            for pid in zone.active_players:
                zp = zone.get_placement(pid)
                if not zp.cards:
                    continue
                strength = self._calc_strength_custom(zp.cards, zone.color, pid)
                zone_strengths[zone.color][pid] = strength
                self.stats["strength_values"].append(strength)
        return zone_strengths

    def _calc_strength_custom(self, cards, zone_color, pid):
        """Strength calc with all condition modifiers."""
        cond = self.test_condition_effect
        ranked_cards = [c for c in cards if c.has_rank]
        mascots = [c for c in cards if c.is_mascot]

        if not ranked_cards:
            return 0

        # Apply rank modifications
        effective_ranks = []
        for c in ranked_cards:
            r = c.effective_rank
            if cond == "mirror_ranks":
                r = 10 - r
            elif cond == "ceiling_5":
                r = min(r, 5)
            elif cond == "peasant_revolt" and c.effective_rank <= 3:
                r = c.effective_rank + 5
            effective_ranks.append((c, r))

        best_card, best_rank = max(effective_ranks, key=lambda x: x[1])

        # Mascot doubling
        if mascots:
            if cond == "mirror_ranks" or cond == "ceiling_5":
                # Mascot doubles the modified rank
                best_rank *= 2
            else:
                best_rank *= 2
            self.stats["mascot_combos"] += 1
            extra_cards = len(ranked_cards) - 1
        else:
            extra_cards = len(ranked_cards) - 1

        extra_bonus = max(0, extra_cards) * self.extra_card_bonus

        # Home Field calculation
        home_field = 0
        self._hf_checks += 1

        if cond == "no_home_field":
            pass  # No HF
        elif cond == "foreign_exchange":
            # HF triggers on NON-matching color
            has_foreign = any(c.color != zone_color and c.is_natural for c in cards)
            if has_foreign:
                home_field = self.home_field_bonus
                self._hf_hits += 1
        elif cond == "color_tax":
            # Matching color = -2 penalty
            has_matching = any(c.color == zone_color and c.is_natural for c in cards)
            if has_matching:
                home_field = -2
                self._hf_hits += 1
        elif cond == "exile":
            # Normal HF (but exile prevents matching-color cards from being here)
            has_matching = any(c.color == zone_color and c.is_natural for c in cards)
            if has_matching:
                home_field = self.home_field_bonus
                self._hf_hits += 1
        elif cond == "mercenary":
            # Normal HF, but off-color naturals get +1 each
            has_matching = any(c.color == zone_color and c.is_natural for c in cards)
            if has_matching:
                home_field = self.home_field_bonus
                self._hf_hits += 1
            off_color_naturals = sum(1 for c in cards
                                     if c.is_natural and c.color != zone_color)
            home_field += off_color_naturals  # +1 per off-color
        else:
            # Default HF
            has_matching = any(c.color == zone_color and c.is_natural for c in cards)
            if has_matching:
                home_field = self.home_field_bonus
                self.stats["home_field_triggers"] += 1
                self._hf_hits += 1

        # Grudge Match: +3 to player with fewest zones last round
        grudge_bonus = 0
        if cond == "grudge_match" and self.current_round > 0:
            min_zones = min(self._zones_won_last_round.get(pid, 0)
                           for pid in range(self.num_players))
            my_zones = self._zones_won_last_round.get(pid, 0)
            if my_zones == min_zones:
                grudge_bonus = 3
                self._grudge_bonus_applied += 1

        return max(0, best_rank + extra_bonus + home_field + grudge_bonus)

    def _score_round_custom(self, zone_strengths):
        """Scoring with condition modifiers."""
        cond = self.test_condition_effect
        vp = self.base_vp

        if cond == "double_vp":
            vp = self.base_vp * 2

        round_stats = {
            "zone_winners": {},
            "vp_awarded": defaultdict(int),
            "strength_by_zone": zone_strengths,
            "condition": cond,
        }

        # Track zones won per player this round (for Diminishing Returns)
        zones_won_this_round = defaultdict(int)

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

            # Determine winner based on condition
            inversion = (cond == "lowest_wins")

            if inversion:
                target = min(strength_map.values())
            else:
                target = max(strength_map.values())

            if target <= 0:
                round_stats["zone_winners"][zone.color] = None
                continue

            winners = [pid for pid, s in strength_map.items() if s == target]

            # Tie handling
            if len(winners) > 1:
                if cond == "ties_lose":
                    round_stats["zone_winners"][zone.color] = []
                    continue

            # Award VP
            zone_vp_awards = {}
            for w in winners:
                if cond == "diminishing_returns":
                    # VP based on how many zones already won this round
                    prev_won = zones_won_this_round[w]
                    dim_vp = [7, 5, 3, 1]
                    player_vp = dim_vp[min(prev_won, 3)]
                    if len(winners) > 1:
                        player_vp = math.floor(player_vp / len(winners))
                else:
                    player_vp = vp if len(winners) == 1 else math.floor(vp / len(winners))

                # Bounty check
                has_bounty = any(c.is_action and c.action_type == ACTION_BOUNTY
                                 for c in zone.get_placement(w).cards)
                if has_bounty:
                    if len(winners) == 1:
                        player_vp *= 2
                        self.stats["bounty_wins"] += 1
                    else:
                        player_vp = 0
                        self.stats["bounty_fails"] += 1

                zone_vp_awards[w] = player_vp
                zones_won_this_round[w] += 1

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

                    # Consolation Prize: losers at contested zones get 2 VP
                    if cond == "consolation_prize" and contested >= 2:
                        self.players[loser].score += 2
                        round_stats["vp_awarded"][loser] += 2

                    # Shield consolation
                    has_shield = any(c.is_action and c.action_type == ACTION_SHIELD
                                     for c in zp.cards)
                    has_bounty_loss = any(c.is_action and c.action_type == ACTION_BOUNTY
                                          for c in zp.cards)
                    if has_bounty_loss:
                        self.stats["bounty_fails"] += 1
                    if has_shield and not has_bounty_loss:
                        consolation = self.rules["action_cards"]["shield"]["consolation_vp"]
                        self.players[loser].score += consolation
                        self.stats["shield_saves"] += 1
                        round_stats["vp_awarded"][loser] += consolation

            # 2nd place VP (or Charity)
            if len(winners) == 1 and len(strength_map) >= 2:
                sorted_str = sorted(strength_map.values(), reverse=(not inversion))
                second_best = sorted_str[1] if len(sorted_str) > 1 else 0
                if second_best > 0:
                    runners_up = [pid for pid, s in strength_map.items()
                                  if s == second_best and pid not in winners]
                    second_vp = 3 if cond == "charity" else self.second_place_vp
                    for pid in runners_up:
                        self.players[pid].score += second_vp
                        round_stats["vp_awarded"][pid] += second_vp
                        self.stats["second_place_awards"] += 1

            round_stats["zone_winners"][zone.color] = winners

        # Fortify bonus
        if cond == "big_stack_bonus":
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


# ─── CONDITION-AWARE AI ───────────────────────────────────────────────────

class ConditionAI(AIPlayerV4):
    """AI that adapts to condition effects."""

    def _score_card_at_zone(self, card, zone_color, vp, zone_counts):
        score = card.effective_rank
        cond = None
        if hasattr(self, '_game_ref') and self._game_ref:
            cond = self._game_ref.test_condition_effect

        # Rank modifications
        if cond == "mirror_ranks" and card.has_rank:
            score = 10 - card.effective_rank
        elif cond == "ceiling_5" and card.has_rank:
            score = min(card.effective_rank, 5)
        elif cond == "peasant_revolt" and card.has_rank and card.effective_rank <= 3:
            score = card.effective_rank + 5

        # HF scoring
        if cond == "no_home_field":
            pass  # No HF bonus in scoring
        elif cond == "foreign_exchange":
            if card.color != zone_color and card.is_natural:
                score += 3.0 * self.style["home_field_weight"]
        elif cond == "color_tax":
            if card.color == zone_color and card.is_natural:
                score -= 2.0 * self.style["home_field_weight"]
        elif cond == "exile":
            if card.color == zone_color and card.is_natural:
                score -= 10  # Can't play here
        elif cond == "mercenary":
            if card.color == zone_color and card.is_natural:
                score += 3.0 * self.style["home_field_weight"]
            elif card.is_natural:
                score += 1.0  # Off-color bonus
        elif cond == "lowest_wins":
            # Inversion: low rank is good
            if card.has_rank:
                score = 10 - card.effective_rank
                if card.color == zone_color and card.is_natural:
                    score -= 3.0 * self.style["home_field_weight"]  # HF hurts under inversion
        else:
            # Default HF
            if card.color == zone_color and card.is_natural:
                score += 3.0 * self.style["home_field_weight"]

        # Zone bonuses
        if zone_counts[zone_color] == 0:
            score += vp * 0.35 * self.style["spread_bonus"]
        if zone_counts[zone_color] >= 1:
            score -= (card.effective_rank - 2) * 0.4
            score -= 0.5 * zone_counts[zone_color]

        return score


# ─── SIMULATION ───────────────────────────────────────────────────────────

def load_config():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config_v4.json")
    with open(path) as f:
        return json.load(f)


def test_condition(cond_name, cond_effect, N, np, styles, config):
    """Test a single condition across N games."""
    style_wins = defaultdict(float)
    style_games = defaultdict(int)
    all_winner = []
    all_spread = []
    total_hf_hit = 0
    total_hf_check = 0

    for i in range(N):
        seed = 1 + i
        gs = [styles[(i + j) % len(styles)] for j in range(np)]
        game = ConditionTestGame(np, seed=seed, config=config,
                                  pass_per_round=2 if np <= 4 else 1,
                                  test_condition=cond_effect)
        ais = [ConditionAI(pid, skill=1.0, style=gs[pid], rng_seed=seed*100+pid)
               for pid in range(np)]
        for ai in ais:
            ai._game_ref = game

        def dfn(p, g, rn):
            ais[p.id]._game_ref = g
            return ais[p.id].choose_deployment(p, g, rn)
        def pfn(p, g, pc):
            return ais[p.id].choose_pass(p, g, pc)

        result = game.play_game(dfn, pfn)
        w = result["winner"]
        if isinstance(w, list):
            for x in w: style_wins[gs[x]] += 1.0/len(w)
        else:
            style_wins[gs[w]] += 1

        scores = list(result["scores"].values())
        all_winner.append(max(scores))
        all_spread.append(max(scores)-min(scores))
        for pid, sc in result["scores"].items():
            style_games[gs[pid]] += 1

        total_hf_hit += game._hf_hits
        total_hf_check += game._hf_checks

    wr = {s: style_wins[s]/style_games[s] if style_games[s]>0 else 0 for s in set(styles)}
    gap = max(wr.values()) - min(wr.values())
    sniper_wr = wr.get("sniper", 0)

    return {
        "name": cond_name,
        "effect": cond_effect,
        "style_gap": gap,
        "sniper_wr": sniper_wr,
        "winner_vp": statistics.mean(all_winner),
        "vp_stdev": statistics.stdev(all_winner),
        "avg_spread": statistics.mean(all_spread),
        "hf_rate": total_hf_hit / total_hf_check if total_hf_check > 0 else 0,
        "close_pct": sum(1 for s in all_spread if s <= 5) / N,
        "blowout_pct": sum(1 for s in all_spread if s >= 25) / N,
        "win_rates": wr,
    }


def main():
    N = 2000
    config = load_config()

    # Test at 4P (primary balance target)
    np = 4
    styles = ["balanced", "aggressive", "sniper", "hoarder"]

    print("=" * 100)
    print("  CONDITION CARD CANDIDATES — 20 conditions tested at 4P")
    print(f"  {N} games per condition (every round uses the same condition)")
    print(f"  Per-round passing: 2 cards/round")
    print("=" * 100)

    # First: run baseline (mixed conditions from deck)
    print("\n  Running BASELINE (mixed conditions)...", end="", flush=True)
    baseline = test_condition("BASELINE (mixed)", None, N, np, styles, config)
    # Baseline uses None which means normal condition deck
    # Actually let me fix: None won't work. Let me run with no override.
    # For baseline, just use a normal game
    style_wins_b = defaultdict(float)
    style_games_b = defaultdict(int)
    all_winner_b = []
    all_spread_b = []

    for i in range(N):
        seed = 1 + i
        gs = [styles[(i + j) % len(styles)] for j in range(np)]
        game = ConditionTestGame(np, seed=seed, config=config,
                                  pass_per_round=2, test_condition=None)
        # With test_condition=None, it uses the normal condition deck
        game.condition_deck = [
            ConditionCard(c["name"], c["category"], c["effect"])
            for c in config["game_rules"]["condition_cards"]
        ]
        game.rng.shuffle(game.condition_deck)

        ais = [ConditionAI(pid, skill=1.0, style=gs[pid], rng_seed=seed*100+pid)
               for pid in range(np)]
        for ai in ais:
            ai._game_ref = game

        def dfn(p, g, rn):
            ais[p.id]._game_ref = g
            return ais[p.id].choose_deployment(p, g, rn)
        def pfn(p, g, pc):
            return ais[p.id].choose_pass(p, g, pc)

        result = game.play_game(dfn, pfn)
        w = result["winner"]
        if isinstance(w, list):
            for x in w: style_wins_b[gs[x]] += 1.0/len(w)
        else:
            style_wins_b[gs[w]] += 1
        scores = list(result["scores"].values())
        all_winner_b.append(max(scores))
        all_spread_b.append(max(scores)-min(scores))
        for pid, sc in result["scores"].items():
            style_games_b[gs[pid]] += 1

    wr_b = {s: style_wins_b[s]/style_games_b[s] for s in set(styles)}
    baseline = {
        "name": "BASELINE (mixed)",
        "style_gap": max(wr_b.values())-min(wr_b.values()),
        "sniper_wr": wr_b.get("sniper", 0),
        "winner_vp": statistics.mean(all_winner_b),
        "vp_stdev": statistics.stdev(all_winner_b),
        "avg_spread": statistics.mean(all_spread_b),
        "hf_rate": 0.90,
        "close_pct": sum(1 for s in all_spread_b if s <= 5)/N,
        "blowout_pct": sum(1 for s in all_spread_b if s >= 25)/N,
    }
    print(" done")

    # Test each condition
    results = []
    for cond_name, cond_effect, cond_cat, cond_desc in CANDIDATE_CONDITIONS:
        print(f"  Running {cond_name:<22}...", end="", flush=True)
        r = test_condition(cond_name, cond_effect, N, np, styles, config)
        r["category"] = cond_cat
        r["description"] = cond_desc
        results.append(r)
        print(f" gap={r['style_gap']:.1%} sniper={r['sniper_wr']:.0%} "
              f"HF={r['hf_rate']:.0%} spread={r['avg_spread']:.1f}")

    # ── Summary table ──
    print(f"\n{'='*100}")
    print(f"  {'Name':<22} {'Cat':<12} {'Gap':>6} {'Sniper':>7} {'HF%':>5} "
          f"{'WinVP':>6} {'σ':>5} {'Spread':>7} {'Close':>6} {'Blow':>6} {'Grade'}")
    print(f"  {'-'*98}")

    # Print baseline first
    print(f"  {'BASELINE':<22} {'mixed':<12} "
          f"{baseline['style_gap']:5.1%} {baseline['sniper_wr']:6.0%} "
          f"{baseline['hf_rate']:4.0%} {baseline['winner_vp']:5.1f} "
          f"{baseline['vp_stdev']:4.1f} {baseline['avg_spread']:6.1f} "
          f"{baseline['close_pct']:5.0%} {baseline['blowout_pct']:5.0%} {'ref'}")
    print(f"  {'-'*98}")

    for r in sorted(results, key=lambda x: x['style_gap']):
        # Grade: ✅ if gap < 5% and interesting (HF < 80% or spread different from baseline)
        interesting = (r['hf_rate'] < 0.80 or
                      abs(r['avg_spread'] - baseline['avg_spread']) > 2 or
                      abs(r['sniper_wr'] - baseline['sniper_wr']) > 0.03)
        balanced = r['style_gap'] < 0.08
        broken = r['style_gap'] > 0.15

        if broken:
            grade = "❌ broken"
        elif balanced and interesting:
            grade = "⭐ great"
        elif balanced:
            grade = "✅ safe"
        elif interesting:
            grade = "👍 interesting"
        else:
            grade = "😐 meh"

        print(f"  {r['name']:<22} {r['category']:<12} "
              f"{r['style_gap']:5.1%} {r['sniper_wr']:6.0%} "
              f"{r['hf_rate']:4.0%} {r['winner_vp']:5.1f} "
              f"{r['vp_stdev']:4.1f} {r['avg_spread']:6.1f} "
              f"{r['close_pct']:5.0%} {r['blowout_pct']:5.0%} {grade}")

    # ── Category analysis ──
    print(f"\n{'='*100}")
    print("  CATEGORY ANALYSIS")
    print(f"{'='*100}")

    cats = defaultdict(list)
    for r in results:
        cats[r["category"]].append(r)

    for cat, items in sorted(cats.items()):
        avg_gap = statistics.mean(r['style_gap'] for r in items)
        avg_hf = statistics.mean(r['hf_rate'] for r in items)
        print(f"\n  {cat}: avg gap={avg_gap:.1%}, avg HF={avg_hf:.0%}")
        for r in sorted(items, key=lambda x: x['style_gap']):
            print(f"    {r['name']:<22} gap={r['style_gap']:.1%} HF={r['hf_rate']:.0%}")

    print(f"\n{'='*100}")
    print("  TOP 12 RECOMMENDATION")
    print(f"{'='*100}")

    # Score each: low gap + interesting effects + variety of categories
    for r in results:
        r['score'] = 0
        if r['style_gap'] < 0.05: r['score'] += 3
        elif r['style_gap'] < 0.08: r['score'] += 2
        elif r['style_gap'] < 0.12: r['score'] += 1

        if r['hf_rate'] < 0.50: r['score'] += 3  # Major HF disruptor
        elif r['hf_rate'] < 0.80: r['score'] += 2
        elif r['hf_rate'] < 0.90: r['score'] += 1

        if abs(r['avg_spread'] - baseline['avg_spread']) > 3: r['score'] += 1
        if r['close_pct'] > baseline['close_pct']: r['score'] += 1

    top12 = sorted(results, key=lambda x: -x['score'])[:12]
    print(f"\n  {'Rank':<5} {'Name':<22} {'Score':>5} {'Gap':>6} {'HF%':>5} {'Why'}")
    print(f"  {'-'*80}")
    for i, r in enumerate(top12, 1):
        whys = []
        if r['hf_rate'] < 0.50: whys.append("HF disruptor")
        if r['style_gap'] < 0.05: whys.append("tight balance")
        if r['close_pct'] > baseline['close_pct'] + 0.02: whys.append("more close games")
        if abs(r['avg_spread'] - baseline['avg_spread']) > 3: whys.append("changes spread")
        if not whys: whys.append(r['category'])
        print(f"  {i:<5} {r['name']:<22} {r['score']:>5} {r['style_gap']:5.1%} "
              f"{r['hf_rate']:4.0%} {', '.join(whys)}")


if __name__ == "__main__":
    main()
