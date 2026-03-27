#!/usr/bin/env python3
"""
Test Debt Card timing variants:
  A) LUMP SUM (-3 at end): Current best — penalty at game end
  B) BLEED (-1/round): Debt leader loses 1 VP per round. Visible, ongoing.
  C) BLEED (-1/round, visible threshold): Only bleeds when debt >= 3 tokens.
     Gives a grace period before punishment kicks in.

All use per-round passing + zone-matched HF=3.

The hypothesis: per-round bleeding creates visible comeback moments.
Players SEE the leader losing points, creating "next round is my round" hope.
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

from cards_v4 import Card, COLORS
from game_state_v4 import GameStateV4, Zone
from ai_player_v4 import AIPlayerV4


class DebtVariantGame(GameStateV4):
    """
    Game with Debt Cards — multiple timing variants.

    debt_mode:
      'lump_end'   — penalty applied at game end to highest-debt player(s)
      'bleed'      — debt leader loses 1 VP per round (after scoring)
      'bleed_threshold' — bleed kicks in only when debt >= threshold
    """

    def __init__(self, num_players, seed=42, config=None,
                 pass_per_round=1,
                 debt_mode='lump_end', lump_penalty=3,
                 bleed_per_round=1, bleed_threshold=0):
        self.pass_per_round = pass_per_round
        self.debt_mode = debt_mode
        self.lump_penalty = lump_penalty
        self.bleed_per_round = bleed_per_round
        self.bleed_threshold = bleed_threshold

        self._debt = defaultdict(int)
        self._lead_changes = 0
        self._round_leaders = []
        self._bleed_applied = 0  # total bleed VP lost across game

        super().__init__(num_players, seed=seed, config=config)

    def play_game(self, deployment_fn, pass_fn=None):
        for round_num in range(self.num_rounds):
            self.current_round = round_num
            self._execute_round_pass(pass_fn)
            round_stats = self._play_round_custom(round_num, deployment_fn)
            self.stats["rounds"].append(round_stats)

            # Award debt to zone winners
            for zone_color, winners in round_stats["zone_winners"].items():
                if winners and isinstance(winners, list):
                    for w in winners:
                        self._debt[w] += 1

            # Apply bleed if applicable
            if self.debt_mode in ('bleed', 'bleed_threshold'):
                self._apply_bleed()

            # Track lead changes
            scores = [p.score for p in self.players]
            leader = scores.index(max(scores))
            if self._round_leaders and self._round_leaders[-1] != leader:
                self._lead_changes += 1
            self._round_leaders.append(leader)

        # Lump sum at end
        if self.debt_mode == 'lump_end':
            self._apply_lump_penalty()

        self.game_over = True
        return self._compile_final_stats()

    def _apply_bleed(self):
        """Debt leader loses VP this round."""
        if not self._debt:
            return
        max_debt = max(self._debt.values())
        if max_debt <= 0:
            return
        if self.debt_mode == 'bleed_threshold' and max_debt < self.bleed_threshold:
            return

        for pid, debt in self._debt.items():
            if debt == max_debt:
                self.players[pid].score -= self.bleed_per_round
                self.players[pid].score = max(0, self.players[pid].score)
                self._bleed_applied += self.bleed_per_round

    def _apply_lump_penalty(self):
        if not self._debt:
            return
        max_debt = max(self._debt.values())
        if max_debt <= 0:
            return
        for pid, debt in self._debt.items():
            if debt == max_debt:
                self.players[pid].score -= self.lump_penalty
                self.players[pid].score = max(0, self.players[pid].score)

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


class DebtAwareAI(AIPlayerV4):
    """AI that pulls back when it's the debt leader."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.game_ref = None

    def _score_card_at_zone(self, card, zone_color, vp, zone_counts):
        score = super()._score_card_at_zone(card, zone_color, vp, zone_counts)

        if self.game_ref and self.game_ref._debt:
            my_debt = self.game_ref._debt.get(self.player_id, 0)
            max_debt = max(self.game_ref._debt.values()) if self.game_ref._debt else 0
            if my_debt > 0 and my_debt >= max_debt:
                # Discount winning proportional to debt lead
                others_max = max((d for pid, d in self.game_ref._debt.items()
                                  if pid != self.player_id), default=0)
                lead = my_debt - others_max
                discount = min(0.35, lead * 0.12)
                score *= (1.0 - discount)

        return score


def load_config():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config_v4.json")
    with open(path) as f:
        return json.load(f)


def run_scenario(label, N, np, styles, config, debt_mode, **kwargs):
    style_wins = defaultdict(float)
    style_games = defaultdict(int)
    style_scores = defaultdict(list)
    all_winner = []
    all_spread = []
    total_lc = 0
    total_bleed = 0

    for i in range(N):
        seed = 1 + i
        gs = [styles[(i + j) % len(styles)] for j in range(np)]
        game = DebtVariantGame(np, seed=seed, config=config,
                                debt_mode=debt_mode, **kwargs)

        ais = [DebtAwareAI(pid, skill=1.0, style=gs[pid], rng_seed=seed*100+pid)
               for pid in range(np)]
        for ai in ais:
            ai.game_ref = game

        def dfn(p, g, rn):
            ais[p.id].game_ref = g
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
        total_bleed += game._bleed_applied

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
        "bleed_vp_per_game": total_bleed/N,
    }


def run_skill(label, N, np, config, debt_mode, **kwargs):
    expert_wins = 0
    for i in range(N):
        seed = 1+i
        game = DebtVariantGame(np, seed=seed, config=config,
                                debt_mode=debt_mode, **kwargs)

        expert = DebtAwareAI(0, skill=1.0, style="balanced", rng_seed=seed*100)
        expert.game_ref = game
        novices = [AIPlayerV4(pid, skill=0.3, style="balanced", rng_seed=seed*100+pid)
                   for pid in range(1, np)]
        all_ai = [expert] + novices

        def dfn(p, g, rn):
            if hasattr(all_ai[p.id], 'game_ref'):
                all_ai[p.id].game_ref = g
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
    config = load_config()

    style_sets = {
        3: ["balanced", "aggressive", "sniper"],
        4: ["balanced", "aggressive", "sniper", "hoarder"],
        5: ["balanced", "aggressive", "sniper", "hoarder", "spread"],
    }

    # No-debt baseline uses same game class with debt_mode that doesn't trigger
    scenarios = [
        ("NO DEBT (baseline)", "lump_end", {"lump_penalty": 0}),
        ("LUMP -3 (end)", "lump_end", {"lump_penalty": 3}),
        ("BLEED -1/round", "bleed", {"bleed_per_round": 1}),
        ("BLEED -1 (≥3 debt)", "bleed_threshold", {"bleed_per_round": 1, "bleed_threshold": 3}),
        ("BLEED -2/round", "bleed", {"bleed_per_round": 2}),
    ]

    print("="*90)
    print("  DEBT TIMING VARIANTS")
    print(f"  All use per-round passing + zone-matched HF=3")
    print(f"  {N} games per scenario")
    print("="*90)

    for np in [3, 4, 5]:
        styles = style_sets[np]

        print(f"\n{'='*90}")
        print(f"  {np} PLAYERS")
        print(f"{'='*90}")

        results = []
        skill_res = []

        for label, mode, kw in scenarios:
            print(f"  Running {label}...", end="", flush=True)
            r = run_scenario(label, N, np, styles, config, mode, **kw)
            s = run_skill(label, N, np, config, mode, **kw)
            results.append(r)
            skill_res.append(s)
            print(" done")

        cw = 16
        print(f"\n  {'Metric':<24}", end="")
        for r in results:
            print(f" {r['label'][:cw]:>{cw}}", end="")
        print()
        print(f"  {'-'*(24+(cw+1)*len(results))}")

        print(f"  {'Style gap':<24}", end="")
        for r in results: print(f" {r['style_gap']:>{cw}.1%}", end="")
        print()

        for st in sorted(set(s for r in results for s in r["win_rates"])):
            print(f"  {st+' win%':<24}", end="")
            for r in results: print(f" {r['win_rates'].get(st,0):>{cw}.1%}", end="")
            print()

        print(f"  {'-'*(24+(cw+1)*len(results))}")

        for metric, key, fmt in [
            ("Winner VP","avg_winner",".1f"),
            ("Winner σ","winner_stdev",".1f"),
            ("Avg spread","avg_spread",".1f"),
            ("Blowouts (≥25)","blowout_pct",".0%"),
            ("Close games (≤5)","close_pct",".0%"),
            ("Lead changes/game","lead_changes",".2f"),
            ("Bleed VP lost/game","bleed_vp_per_game",".1f"),
        ]:
            print(f"  {metric:<24}", end="")
            for r in results: print(f" {r[key]:>{cw}{fmt}}", end="")
            print()

        print(f"  {'-'*(24+(cw+1)*len(results))}")

        print(f"  {'Expert win%':<24}", end="")
        for s in skill_res: print(f" {s['expert_wr']:>{cw}.1%}", end="")
        print()
        print(f"  {'Skill edge':<24}", end="")
        for s in skill_res: print(f" {s['edge']:+>{cw}.1%}", end="")
        print()
        print(f"  {'Edge vs fair':<24}", end="")
        for s in skill_res: print(f" {s['edge_pct']:+>{cw}.0f}%", end="")
        print()

    print(f"\n{'='*90}")
    print("  KEY QUESTION: Does bleeding create more lead changes than lump sum?")
    print("  If yes → players FEEL the comeback mid-game, not just at final scoring.")
    print("="*90)


if __name__ == "__main__":
    main()
