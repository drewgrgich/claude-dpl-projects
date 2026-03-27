#!/usr/bin/env python3
"""
Test randomized Home Field color each round.

Current: HF = card color matches zone color → always knowable, always +3.
Variants:
  A) FLIP AFTER DEPLOY: Deploy blind, then flip top of leftover pile.
     That color gets HF at ALL zones. Pure gambling/hedging.
  B) FLIP BEFORE DEPLOY (after pass): See hot color, then deploy.
     Strategic — but per-round pass means you might not have it.
  C) ZONE-MATCHED (current baseline): each zone rewards its own color.
  D) NO HF: removed entirely (for comparison).

All variants use per-round passing (1 card/round) since Drew is
already committed to that change.

Key metrics:
  - Color diversity in deployments (do players mix colors more?)
  - Skill expression (does randomized HF reward or punish good play?)
  - Style balance
  - "Comeback" rate (leader changes between rounds)
  - Round-by-round VP distribution
  - HF hit rate (what % of plays actually get the bonus?)
"""

import copy
import json
import math
import os
import random
import statistics
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cards_v4 import (
    Card, COLORS, COLOR_ORDER,
    CARD_TYPE_NUMBER, CARD_TYPE_MASCOT, CARD_TYPE_ACTION, CARD_TYPE_DUD,
    ACTION_SHIELD, ACTION_BOMB, ACTION_SWAP, ACTION_BOUNTY,
)
from game_state_v4 import GameStateV4, Zone
from ai_player_v4 import AIPlayerV4


# ─── RANDOM HF GAME ──────────────────────────────────────────────────────

class RandomHFGame(GameStateV4):
    """
    Game with randomized HF color each round + per-round passing.

    Modes:
      'after_deploy'  — HF color revealed after deployment (blind)
      'before_deploy' — HF color revealed after pass, before deployment
      'zone_matched'  — classic: each zone's own color (current rules)
      'none'          — no HF at all
    """

    def __init__(self, num_players, seed=42, config=None,
                 hf_mode='after_deploy', pass_per_round=1):
        self.hf_mode = hf_mode
        self.pass_per_round = pass_per_round
        self._hot_color = None  # this round's HF color
        self._hf_hits = 0
        self._hf_misses = 0
        self._lead_changes = 0
        self._round_leaders = []
        self._round_vp = defaultdict(list)
        self._color_diversity_per_deploy = []
        self._hot_color_in_hand = []  # did player even have hot color cards?
        super().__init__(num_players, seed=seed, config=config)

    def play_game(self, deployment_fn, pass_fn=None):
        for round_num in range(self.num_rounds):
            self.current_round = round_num
            self._execute_round_pass(pass_fn)

            # Determine hot color for this round
            if self.hf_mode == 'zone_matched':
                self._hot_color = None  # handled in strength calc
            elif self.hf_mode == 'none':
                self._hot_color = None
            else:
                # Random color from leftover pile (or just random)
                if self.unused_cards:
                    # Flip top card of leftover pile
                    flip_card = self.unused_cards[0]
                    self._hot_color = flip_card.color
                    # Rotate the leftover pile so next round gets a different card
                    self.unused_cards = self.unused_cards[1:] + [self.unused_cards[0]]
                else:
                    self._hot_color = self.rng.choice(COLORS)

            # If before_deploy, AI can see the hot color (passed via game state)
            # If after_deploy, AI deploys blind (hot_color set but not used in AI scoring)

            # Track who has hot color cards before deploy
            if self._hot_color:
                for p in self.players:
                    has_hot = any(c.color == self._hot_color and c.is_natural
                                 for c in p.hand)
                    self._hot_color_in_hand.append(1 if has_hot else 0)

            round_stats = self._play_round_custom(round_num, deployment_fn)
            self.stats["rounds"].append(round_stats)

            # Track lead changes
            scores = [p.score for p in self.players]
            leader = scores.index(max(scores))
            if self._round_leaders and self._round_leaders[-1] != leader:
                self._lead_changes += 1
            self._round_leaders.append(leader)

            # Track VP this round
            round_total = sum(round_stats["vp_awarded"].values())
            self._round_vp[round_num].append(round_total)

        self.game_over = True
        return self._compile_final_stats()

    def _execute_round_pass(self, pass_fn=None):
        pass_count = self.pass_per_round
        passed_cards = {}
        for player in self.players:
            if len(player.hand) <= pass_count:
                passed_cards[player.id] = []
                continue
            if pass_fn:
                to_pass = pass_fn(player, self, pass_count)
            else:
                ranked = sorted([c for c in player.hand if c.has_rank],
                                key=lambda c: c.effective_rank)
                non_ranked = [c for c in player.hand if not c.has_rank]
                to_pass = (ranked + non_ranked)[:pass_count]
            passed_cards[player.id] = to_pass

        for player in self.players:
            for card in passed_cards[player.id]:
                if card in player.hand:
                    player.hand.remove(card)
            right_id = (player.id - 1) % self.num_players
            player.hand.extend(passed_cards[right_id])

    def _play_round_custom(self, round_num, deployment_fn):
        if self.condition_deck:
            self.active_condition = self.condition_deck.pop(0)
            self.stats["condition_cards_drawn"].append(self.active_condition.name)
        else:
            self.active_condition = None

        self._log(f"\n{'='*50}")
        hot_str = f" | Hot Color: {self._hot_color}" if self._hot_color and self.hf_mode == 'before_deploy' else ""
        cond_str = f" | Condition: {self.active_condition}" if self.active_condition else ""
        self._log(f"ROUND {round_num + 1}{cond_str}{hot_str}")

        for p in self.players:
            p.zones_won_this_round = 0

        self.zones = [Zone(color=c, index=i) for i, c in enumerate(self.colors)]

        for player in self.players:
            deploy = deployment_fn(player, self, round_num)
            self._execute_deployment(player, deploy)

            # Track color diversity
            all_deployed = [c for z in self.zones
                           for c in z.get_placement(player.id).cards
                           if c.has_rank]
            if all_deployed:
                unique_colors = len(set(c.color for c in all_deployed))
                self._color_diversity_per_deploy.append(unique_colors)

        # After deploy, reveal hot color if after_deploy mode
        if self.hf_mode == 'after_deploy' and self._hot_color:
            self._log(f"\n  ★ HOT COLOR REVEALED: {self._hot_color} ★")

        self._resolve_actions()
        zone_strengths = self._calculate_all_strength()
        round_stats = self._score_round(zone_strengths)
        self._log(f"\nScores: {', '.join(f'P{p.id}={p.score}' for p in self.players)}")
        self.active_condition = None
        return round_stats

    def _calculate_strength(self, cards, zone_color):
        """Modified strength calc for random HF."""
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

        # Home Field calculation depends on mode
        home_field = 0
        no_hf = (self.active_condition and
                 self.active_condition.effect == "no_home_field")

        if not no_hf:
            if self.hf_mode == 'zone_matched':
                # Classic: card color matches zone color
                has_match = any(c.color == zone_color and c.is_natural for c in cards)
                if has_match:
                    home_field = self.home_field_bonus
                    self.stats["home_field_triggers"] += 1
                    self._hf_hits += 1
                else:
                    self._hf_misses += 1

            elif self.hf_mode in ('after_deploy', 'before_deploy'):
                # Random: card color matches THIS ROUND'S hot color
                if self._hot_color:
                    has_hot = any(c.color == self._hot_color and c.is_natural
                                 for c in cards)
                    if has_hot:
                        home_field = self.home_field_bonus
                        self.stats["home_field_triggers"] += 1
                        self._hf_hits += 1
                    else:
                        self._hf_misses += 1

            elif self.hf_mode == 'none':
                self._hf_misses += 1

        return best_rank + extra_bonus + home_field


# ─── AI THAT KNOWS HOT COLOR ─────────────────────────────────────────────

class HotColorAI(AIPlayerV4):
    """AI that adjusts deployment based on known hot color (before_deploy mode)."""

    def __init__(self, *args, hot_color=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.hot_color = hot_color

    def _score_card_at_zone(self, card, zone_color, vp, zone_counts):
        score = card.effective_rank

        if self.hot_color:
            # Play toward hot color instead of zone color
            if card.color == self.hot_color and card.is_natural:
                score += 3.0 * self.style["home_field_weight"]
        else:
            # Classic: play toward zone color
            if card.color == zone_color and card.is_natural:
                score += 3.0 * self.style["home_field_weight"]

        if zone_counts[zone_color] == 0:
            score += vp * 0.35 * self.style["spread_bonus"]

        if zone_counts[zone_color] >= 1:
            opportunity_cost = card.effective_rank - 2
            score -= opportunity_cost * 0.4
            score -= 0.5 * zone_counts[zone_color]

        return score


# ─── BLIND AI (for after_deploy mode) ────────────────────────────────────

class BlindAI(AIPlayerV4):
    """AI that can't optimize for HF (doesn't know hot color).
    Uses card rank + spread as primary heuristic."""

    def _score_card_at_zone(self, card, zone_color, vp, zone_counts):
        score = card.effective_rank

        # Without knowing HF, just play highest cards at diverse zones
        # Slight preference for color diversity (hedging)
        if zone_counts[zone_color] == 0:
            score += vp * 0.35 * self.style["spread_bonus"]

        if zone_counts[zone_color] >= 1:
            opportunity_cost = card.effective_rank - 2
            score -= opportunity_cost * 0.4
            score -= 0.5 * zone_counts[zone_color]

        return score


# ─── SIMULATION ───────────────────────────────────────────────────────────

def load_config():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config_v4.json")
    with open(path) as f:
        return json.load(f)


def run_scenario(label, num_games, num_players, styles, config,
                 hf_mode, pass_per_round=1):
    style_wins = defaultdict(float)
    style_games = defaultdict(int)
    style_scores = defaultdict(list)
    all_winner_scores = []
    all_spreads = []
    total_lead_changes = 0
    total_hf_hits = 0
    total_hf_total = 0
    all_color_div = []

    for i in range(num_games):
        seed = 1 + i
        game_styles = [styles[(i + j) % len(styles)] for j in range(num_players)]

        game = RandomHFGame(num_players, seed=seed, config=config,
                            hf_mode=hf_mode, pass_per_round=pass_per_round)

        # Choose AI type based on mode
        if hf_mode == 'before_deploy':
            # AI knows hot color — but needs to be told each round
            # We approximate: AI uses zone-matched heuristic for first deploy,
            # then we use HotColorAI with the revealed color
            # Actually, the deployment_fn is called per-round, so we can
            # create AIs that read game._hot_color
            ais = [HotColorAI(pid, skill=1.0, style=game_styles[pid],
                               rng_seed=seed * 100 + pid)
                   for pid in range(num_players)]

            def dfn(p, gs, rn):
                ai = ais[p.id]
                ai.hot_color = gs._hot_color
                return ai.choose_deployment(p, gs, rn)
        elif hf_mode == 'after_deploy':
            # AI is blind — doesn't know hot color
            ais = [BlindAI(pid, skill=1.0, style=game_styles[pid],
                            rng_seed=seed * 100 + pid)
                   for pid in range(num_players)]

            def dfn(p, gs, rn):
                return ais[p.id].choose_deployment(p, gs, rn)
        else:
            # Zone-matched or none — standard AI
            ais = [AIPlayerV4(pid, skill=1.0, style=game_styles[pid],
                               rng_seed=seed * 100 + pid)
                   for pid in range(num_players)]

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

        total_lead_changes += game._lead_changes
        total_hf_hits += game._hf_hits
        total_hf_total += game._hf_hits + game._hf_misses
        all_color_div.extend(game._color_diversity_per_deploy)

    wr = {s: style_wins[s] / style_games[s] if style_games[s] > 0 else 0
          for s in set(styles)}

    return {
        "label": label,
        "win_rates": wr,
        "style_gap": max(wr.values()) - min(wr.values()),
        "avg_winner": statistics.mean(all_winner_scores),
        "winner_stdev": statistics.stdev(all_winner_scores),
        "avg_spread": statistics.mean(all_spreads),
        "lead_changes_per_game": total_lead_changes / num_games,
        "hf_hit_rate": total_hf_hits / total_hf_total if total_hf_total > 0 else 0,
        "avg_color_diversity": statistics.mean(all_color_div) if all_color_div else 0,
        "close_pct": sum(1 for s in all_spreads if s <= 5) / num_games,
        "blowout_pct": sum(1 for s in all_spreads if s >= 25) / num_games,
    }


def run_skill_test(label, num_games, num_players, config, hf_mode, pass_per_round=1):
    expert_wins = 0
    for i in range(num_games):
        seed = 1 + i
        game = RandomHFGame(num_players, seed=seed, config=config,
                            hf_mode=hf_mode, pass_per_round=pass_per_round)

        if hf_mode == 'before_deploy':
            ais_e = HotColorAI(0, skill=1.0, style="balanced", rng_seed=seed * 100)
            ais_n = [BlindAI(pid, skill=0.3, style="balanced", rng_seed=seed * 100 + pid)
                     for pid in range(1, num_players)]
            all_ais = [ais_e] + ais_n

            def dfn(p, gs, rn):
                ai = all_ais[p.id]
                if hasattr(ai, 'hot_color'):
                    ai.hot_color = gs._hot_color
                return ai.choose_deployment(p, gs, rn)
        elif hf_mode == 'after_deploy':
            ais_e = BlindAI(0, skill=1.0, style="balanced", rng_seed=seed * 100)
            ais_n = [BlindAI(pid, skill=0.3, style="balanced", rng_seed=seed * 100 + pid)
                     for pid in range(1, num_players)]
            all_ais = [ais_e] + ais_n

            def dfn(p, gs, rn):
                return all_ais[p.id].choose_deployment(p, gs, rn)
        else:
            all_ais = [AIPlayerV4(0, skill=1.0, style="balanced", rng_seed=seed * 100)]
            all_ais += [AIPlayerV4(pid, skill=0.3, style="balanced", rng_seed=seed * 100 + pid)
                        for pid in range(1, num_players)]

            def dfn(p, gs, rn):
                return all_ais[p.id].choose_deployment(p, gs, rn)

        def pfn(p, gs, pc):
            return all_ais[p.id].choose_pass(p, gs, pc)

        result = game.play_game(dfn, pfn)
        winner = result["winner"]
        if isinstance(winner, int) and winner == 0:
            expert_wins += 1
        elif isinstance(winner, list) and 0 in winner:
            expert_wins += 1.0 / len(winner)

    fair = 1.0 / num_players
    actual = expert_wins / num_games
    return {"expert_wr": actual, "fair": fair, "edge": actual - fair,
            "edge_pct": (actual - fair) / fair * 100}


# ─── MAIN ─────────────────────────────────────────────────────────────────

def main():
    N = 2000
    config = load_config()

    style_sets = {
        3: ["balanced", "aggressive", "sniper"],
        4: ["balanced", "aggressive", "sniper", "hoarder"],
        5: ["balanced", "aggressive", "sniper", "hoarder", "spread"],
    }

    modes = [
        ("ZONE-MATCHED (current)", "zone_matched"),
        ("RANDOM — FLIP BEFORE DEPLOY", "before_deploy"),
        ("RANDOM — FLIP AFTER DEPLOY", "after_deploy"),
        ("NO HF", "none"),
    ]

    print("=" * 90)
    print("  RANDOMIZED HOME FIELD TEST")
    print(f"  All variants use per-round passing (1 card/round)")
    print(f"  {N} games per scenario")
    print("=" * 90)

    for np in [3, 4, 5]:
        styles = style_sets[np]

        print(f"\n{'='*90}")
        print(f"  {np} PLAYERS")
        print(f"{'='*90}")

        results = []
        skill_results = []

        for label, mode in modes:
            print(f"  Running {label}...", end="", flush=True)
            r = run_scenario(label, N, np, styles, config, mode)
            s = run_skill_test(label, N, np, config, mode)
            results.append(r)
            skill_results.append(s)
            print(" done")

        # ── Print comparison ──
        col_w = 18
        headers = [r["label"][:20] for r in results]

        print(f"\n  {'Metric':<26}", end="")
        for h in headers:
            print(f" {h:>{col_w}}", end="")
        print()
        print(f"  {'-'*(26 + (col_w + 1) * len(results))}")

        # Style gap
        print(f"  {'Style gap':<26}", end="")
        for r in results:
            print(f" {r['style_gap']:>{col_w}.1%}", end="")
        print()

        # Win rates
        all_styles = sorted(set(s for r in results for s in r["win_rates"]))
        for st in all_styles:
            print(f"  {st + ' win%':<26}", end="")
            for r in results:
                print(f" {r['win_rates'].get(st, 0):>{col_w}.1%}", end="")
            print()

        print(f"  {'-'*(26 + (col_w + 1) * len(results))}")

        # Scores
        for metric, key, fmt in [
            ("Winner VP", "avg_winner", ".1f"),
            ("Winner σ", "winner_stdev", ".1f"),
            ("Avg spread", "avg_spread", ".1f"),
            ("Close games (≤5)", "close_pct", ".0%"),
            ("Blowouts (≥25)", "blowout_pct", ".0%"),
        ]:
            print(f"  {metric:<26}", end="")
            for r in results:
                val = r[key]
                print(f" {val:>{col_w}{fmt}}", end="")
            print()

        print(f"  {'-'*(26 + (col_w + 1) * len(results))}")

        # Interaction metrics
        print(f"  {'Lead changes/game':<26}", end="")
        for r in results:
            print(f" {r['lead_changes_per_game']:>{col_w}.2f}", end="")
        print()

        print(f"  {'HF hit rate':<26}", end="")
        for r in results:
            print(f" {r['hf_hit_rate']:>{col_w}.0%}", end="")
        print()

        print(f"  {'Color diversity/deploy':<26}", end="")
        for r in results:
            print(f" {r['avg_color_diversity']:>{col_w}.2f}", end="")
        print()

        print(f"  {'-'*(26 + (col_w + 1) * len(results))}")

        # Skill
        print(f"  {'Expert win%':<26}", end="")
        for s in skill_results:
            print(f" {s['expert_wr']:>{col_w}.1%}", end="")
        print()

        print(f"  {'Skill edge':<26}", end="")
        for s in skill_results:
            print(f" {s['edge']:+>{col_w}.1%}", end="")
        print()

        print(f"  {'Edge vs fair':<26}", end="")
        for s in skill_results:
            print(f" {s['edge_pct']:+>{col_w}.0f}%", end="")
        print()

    print(f"\n{'='*90}")
    print("  WHAT TO LOOK FOR")
    print(f"{'='*90}")
    print("""
  ★ LEAD CHANGES: More = more comeback potential, more "next round is MY round"
  ★ HF HIT RATE:  Lower = more surprising HF outcomes (zone-matched is ~85-95%)
  ★ COLOR DIVERSITY: Higher = players mixing colors more freely
  ★ SKILL EDGE: Does randomized HF reward adaptation or just add noise?
  ★ CLOSE GAMES: Do randomized variants produce tighter finishes?

  FLIP AFTER DEPLOY is the purest version of Drew's idea — total surprise.
  FLIP BEFORE DEPLOY lets smart players adapt (but they might not have the right cards).

  The ideal: more lead changes, similar skill edge, lower HF hit rate (less autopilot).
""")


if __name__ == "__main__":
    main()
