#!/usr/bin/env python3
"""
Test flip-before-deploy with reduced HF bonus: HF=1, HF=2, HF=3.
All use per-round passing (1 card/round).
Goal: keep the skill edge from flip-before without the sniper blowout.
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

from cards_v4 import Card, COLORS, CARD_TYPE_NUMBER
from game_state_v4 import GameStateV4, Zone
from ai_player_v4 import AIPlayerV4


class RandomHFGame(GameStateV4):
    def __init__(self, num_players, seed=42, config=None,
                 hf_mode='before_deploy', pass_per_round=1):
        self.hf_mode = hf_mode
        self.pass_per_round = pass_per_round
        self._hot_color = None
        self._hf_hits = 0
        self._hf_misses = 0
        self._lead_changes = 0
        self._round_leaders = []
        super().__init__(num_players, seed=seed, config=config)

    def play_game(self, deployment_fn, pass_fn=None):
        for round_num in range(self.num_rounds):
            self.current_round = round_num
            self._execute_round_pass(pass_fn)

            if self.hf_mode == 'zone_matched':
                self._hot_color = None
            elif self.hf_mode == 'before_deploy':
                if self.unused_cards:
                    self._hot_color = self.unused_cards[0].color
                    self.unused_cards = self.unused_cards[1:] + [self.unused_cards[0]]
                else:
                    self._hot_color = self.rng.choice(COLORS)
            else:
                self._hot_color = None

            round_stats = self._play_round_custom(round_num, deployment_fn)
            self.stats["rounds"].append(round_stats)

            scores = [p.score for p in self.players]
            leader = scores.index(max(scores))
            if self._round_leaders and self._round_leaders[-1] != leader:
                self._lead_changes += 1
            self._round_leaders.append(leader)

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

        for p in self.players:
            p.zones_won_this_round = 0

        self.zones = [Zone(color=c, index=i) for i, c in enumerate(self.colors)]

        for player in self.players:
            deploy = deployment_fn(player, self, round_num)
            self._execute_deployment(player, deploy)

        self._resolve_actions()
        zone_strengths = self._calculate_all_strength()
        round_stats = self._score_round(zone_strengths)
        self.active_condition = None
        return round_stats

    def _calculate_strength(self, cards, zone_color):
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

        home_field = 0
        no_hf = (self.active_condition and
                 self.active_condition.effect == "no_home_field")
        if not no_hf:
            if self.hf_mode == 'zone_matched':
                if any(c.color == zone_color and c.is_natural for c in cards):
                    home_field = self.home_field_bonus
                    self.stats["home_field_triggers"] += 1
                    self._hf_hits += 1
                else:
                    self._hf_misses += 1
            elif self.hf_mode == 'before_deploy' and self._hot_color:
                if any(c.color == self._hot_color and c.is_natural for c in cards):
                    home_field = self.home_field_bonus
                    self.stats["home_field_triggers"] += 1
                    self._hf_hits += 1
                else:
                    self._hf_misses += 1

        return best_rank + extra_bonus + home_field


class HotColorAI(AIPlayerV4):
    def __init__(self, *args, hot_color=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.hot_color = hot_color

    def _score_card_at_zone(self, card, zone_color, vp, zone_counts):
        score = card.effective_rank
        if self.hot_color:
            if card.color == self.hot_color and card.is_natural:
                score += 3.0 * self.style["home_field_weight"]
        else:
            if card.color == zone_color and card.is_natural:
                score += 3.0 * self.style["home_field_weight"]

        if zone_counts[zone_color] == 0:
            score += vp * 0.35 * self.style["spread_bonus"]
        if zone_counts[zone_color] >= 1:
            score -= (card.effective_rank - 2) * 0.4
            score -= 0.5 * zone_counts[zone_color]
        return score


def load_config():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config_v4.json")
    with open(path) as f:
        return json.load(f)


def make_config(base, hf_bonus):
    cfg = copy.deepcopy(base)
    cfg["game_rules"]["strength"]["home_field_bonus"] = hf_bonus
    return cfg


def run_scenario(label, N, np, styles, config, hf_mode):
    style_wins = defaultdict(float)
    style_games = defaultdict(int)
    style_scores = defaultdict(list)
    all_winner = []
    all_spread = []
    total_lc = 0
    total_hf_h = 0
    total_hf_t = 0

    for i in range(N):
        seed = 1 + i
        gs = [styles[(i + j) % len(styles)] for j in range(np)]
        game = RandomHFGame(np, seed=seed, config=config, hf_mode=hf_mode)
        ais = [HotColorAI(pid, skill=1.0, style=gs[pid], rng_seed=seed*100+pid)
               for pid in range(np)]

        def dfn(p, g, rn):
            ais[p.id].hot_color = g._hot_color
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
            style_scores[gs[pid]].append(sc)
            style_games[gs[pid]] += 1
        total_lc += game._lead_changes
        total_hf_h += game._hf_hits
        total_hf_t += game._hf_hits + game._hf_misses

    wr = {s: style_wins[s]/style_games[s] if style_games[s]>0 else 0 for s in set(styles)}
    return {
        "label": label, "win_rates": wr,
        "style_gap": max(wr.values())-min(wr.values()),
        "avg_winner": statistics.mean(all_winner),
        "winner_stdev": statistics.stdev(all_winner),
        "avg_spread": statistics.mean(all_spread),
        "blowout_pct": sum(1 for s in all_spread if s>=25)/N,
        "close_pct": sum(1 for s in all_spread if s<=5)/N,
        "lead_changes": total_lc/N,
        "hf_hit": total_hf_h/total_hf_t if total_hf_t>0 else 0,
    }


def run_skill(label, N, np, config, hf_mode):
    expert_wins = 0
    for i in range(N):
        seed = 1+i
        game = RandomHFGame(np, seed=seed, config=config, hf_mode=hf_mode)
        expert = HotColorAI(0, skill=1.0, style="balanced", rng_seed=seed*100)
        novices = [HotColorAI(pid, skill=0.3, style="balanced", rng_seed=seed*100+pid)
                   for pid in range(1, np)]
        all_ai = [expert]+novices

        def dfn(p, g, rn):
            all_ai[p.id].hot_color = g._hot_color
            return all_ai[p.id].choose_deployment(p, g, rn)
        def pfn(p, g, pc):
            return all_ai[p.id].choose_pass(p, g, pc)

        result = game.play_game(dfn, pfn)
        w = result["winner"]
        if isinstance(w, int) and w==0: expert_wins += 1
        elif isinstance(w, list) and 0 in w: expert_wins += 1.0/len(w)

    fair = 1.0/np
    actual = expert_wins/N
    return {"expert_wr": actual, "edge": actual-fair, "edge_pct": (actual-fair)/fair*100}


def main():
    N = 2000
    base = load_config()
    style_sets = {
        3: ["balanced", "aggressive", "sniper"],
        4: ["balanced", "aggressive", "sniper", "hoarder"],
        5: ["balanced", "aggressive", "sniper", "hoarder", "spread"],
    }

    # Test: zone-matched baseline, then flip-before at HF=1, 2, 3
    variants = [
        ("Zone-matched HF=3", make_config(base, 3), "zone_matched"),
        ("Flip-before HF=3", make_config(base, 3), "before_deploy"),
        ("Flip-before HF=2", make_config(base, 2), "before_deploy"),
        ("Flip-before HF=1", make_config(base, 1), "before_deploy"),
    ]

    print("="*85)
    print("  FLIP-BEFORE HF TUNING: HF=3 vs HF=2 vs HF=1")
    print(f"  All variants use per-round passing (1 card/round)")
    print(f"  {N} games per cell")
    print("="*85)

    for np in [3, 4, 5]:
        styles = style_sets[np]
        print(f"\n{'='*85}")
        print(f"  {np} PLAYERS")
        print(f"{'='*85}")

        results = []
        skill_res = []
        for label, cfg, mode in variants:
            print(f"  Running {label}...", end="", flush=True)
            r = run_scenario(label, N, np, styles, cfg, mode)
            s = run_skill(label, N, np, cfg, mode)
            results.append(r)
            skill_res.append(s)
            print(" done")

        # Print
        cw = 18
        print(f"\n  {'Metric':<24}", end="")
        for r in results:
            short = r['label'][:cw]
            print(f" {short:>{cw}}", end="")
        print()
        print(f"  {'-'*(24+(cw+1)*len(results))}")

        # Style gap + win rates
        print(f"  {'Style gap':<24}", end="")
        for r in results:
            print(f" {r['style_gap']:>{cw}.1%}", end="")
        print()

        all_s = sorted(set(s for r in results for s in r["win_rates"]))
        for st in all_s:
            print(f"  {st+' win%':<24}", end="")
            for r in results:
                print(f" {r['win_rates'].get(st,0):>{cw}.1%}", end="")
            print()

        print(f"  {'-'*(24+(cw+1)*len(results))}")

        for metric, key, fmt in [
            ("Winner VP","avg_winner",".1f"),
            ("Winner σ","winner_stdev",".1f"),
            ("Avg spread","avg_spread",".1f"),
            ("Blowouts (≥25)","blowout_pct",".0%"),
            ("Close games (≤5)","close_pct",".0%"),
            ("Lead changes/game","lead_changes",".2f"),
            ("HF hit rate","hf_hit",".0%"),
        ]:
            print(f"  {metric:<24}", end="")
            for r in results:
                print(f" {r[key]:>{cw}{fmt}}", end="")
            print()

        print(f"  {'-'*(24+(cw+1)*len(results))}")

        print(f"  {'Expert win%':<24}", end="")
        for s in skill_res:
            print(f" {s['expert_wr']:>{cw}.1%}", end="")
        print()
        print(f"  {'Skill edge':<24}", end="")
        for s in skill_res:
            print(f" {s['edge']:+>{cw}.1%}", end="")
        print()
        print(f"  {'Edge vs fair':<24}", end="")
        for s in skill_res:
            print(f" {s['edge_pct']:+>{cw}.0f}%", end="")
        print()

    print(f"\n{'='*85}")
    print("  TARGET: skill edge UP, style gap DOWN, blowouts DOWN")
    print("="*85)


if __name__ == "__main__":
    main()
