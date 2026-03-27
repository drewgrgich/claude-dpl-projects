#!/usr/bin/env python3
"""
Test per-round pass volume: 1, 2, or 3 cards per round.

Hand sizes: 3P=16, 4P=12, 5P=9
At 4 rounds:
  Pass 1/round = 4 total (25-44% of hand)
  Pass 2/round = 8 total (50-89% of hand)
  Pass 3/round = 12 total (75-133% — impossible at 5P late game)

More passing = more hand churn = more adaptation required.
But too much = you never keep anything, can't plan at all.
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


class PerRoundPassGame(GameStateV4):
    def __init__(self, num_players, seed=42, config=None, pass_per_round=1):
        self.pass_per_round = pass_per_round
        self._lead_changes = 0
        self._round_leaders = []
        self._hand_change_pct = []  # % of hand that's new each round
        super().__init__(num_players, seed=seed, config=config)

    def play_game(self, deployment_fn, pass_fn=None):
        for round_num in range(self.num_rounds):
            self.current_round = round_num

            # Snapshot hands before pass
            pre_pass = {p.id: set(id(c) for c in p.hand) for p in self.players}

            self._execute_round_pass(pass_fn)

            # Measure hand change
            for p in self.players:
                post = set(id(c) for c in p.hand)
                if pre_pass[p.id]:
                    new_cards = len(post - pre_pass[p.id])
                    total = len(post)
                    if total > 0:
                        self._hand_change_pct.append(new_cards / total)

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


def load_config():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config_v4.json")
    with open(path) as f:
        return json.load(f)


def run_scenario(label, N, np, styles, config, ppr):
    style_wins = defaultdict(float)
    style_games = defaultdict(int)
    style_scores = defaultdict(list)
    all_winner = []
    all_spread = []
    total_lc = 0
    all_hand_change = []

    for i in range(N):
        seed = 1 + i
        gs = [styles[(i + j) % len(styles)] for j in range(np)]
        game = PerRoundPassGame(np, seed=seed, config=config, pass_per_round=ppr)
        ais = [AIPlayerV4(pid, skill=1.0, style=gs[pid], rng_seed=seed*100+pid)
               for pid in range(np)]

        def dfn(p, g, rn): return ais[p.id].choose_deployment(p, g, rn)
        def pfn(p, g, pc): return ais[p.id].choose_pass(p, g, pc)

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
        all_hand_change.extend(game._hand_change_pct)

    wr = {s: style_wins[s]/style_games[s] if style_games[s]>0 else 0 for s in set(styles)}
    return {
        "label": label, "win_rates": wr,
        "style_gap": max(wr.values())-min(wr.values()),
        "avg_winner": statistics.mean(all_winner),
        "avg_spread": statistics.mean(all_spread),
        "blowout_pct": sum(1 for s in all_spread if s>=25)/N,
        "close_pct": sum(1 for s in all_spread if s<=5)/N,
        "lead_changes": total_lc/N,
        "hand_churn": statistics.mean(all_hand_change) if all_hand_change else 0,
    }


def run_skill(label, N, np, config, ppr):
    expert_wins = 0
    for i in range(N):
        seed = 1+i
        game = PerRoundPassGame(np, seed=seed, config=config, pass_per_round=ppr)
        all_ai = [AIPlayerV4(0, skill=1.0, style="balanced", rng_seed=seed*100)]
        all_ai += [AIPlayerV4(pid, skill=0.3, style="balanced", rng_seed=seed*100+pid)
                   for pid in range(1, np)]

        def dfn(p, g, rn): return all_ai[p.id].choose_deployment(p, g, rn)
        def pfn(p, g, pc): return all_ai[p.id].choose_pass(p, g, pc)

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

    print("="*80)
    print("  PER-ROUND PASS VOLUME: 1 vs 2 vs 3 cards/round")
    print(f"  {N} games per scenario")
    print("="*80)

    for np in [3, 4, 5]:
        styles = style_sets[np]
        hand_size = config["game_rules"]["hand_sizes"][f"{np}_player"]

        print(f"\n{'='*80}")
        print(f"  {np} PLAYERS (hand size: {hand_size})")
        print(f"{'='*80}")

        pass_counts = [1, 2, 3]
        results = []
        skill_res = []

        for ppr in pass_counts:
            total_passed = ppr * 4
            pct = total_passed / hand_size * 100
            label = f"Pass {ppr}/round ({total_passed} total, {pct:.0f}%)"
            print(f"  Running {label}...", end="", flush=True)
            r = run_scenario(label, N, np, styles, config, ppr)
            s = run_skill(label, N, np, config, ppr)
            results.append(r)
            skill_res.append(s)
            print(" done")

        cw = 22
        print(f"\n  {'Metric':<24}", end="")
        for r in results: print(f" {r['label'][:cw]:>{cw}}", end="")
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
            ("Avg spread","avg_spread",".1f"),
            ("Blowouts (≥25)","blowout_pct",".0%"),
            ("Close games (≤5)","close_pct",".0%"),
            ("Lead changes/game","lead_changes",".2f"),
            ("Hand churn %","hand_churn",".0%"),
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

    print(f"\n{'='*80}")
    print("  WHAT TO LOOK FOR")
    print("="*80)
    print("""
  ★ HAND CHURN: % of hand that's new each round. Higher = more adaptation.
  ★ SNIPER WIN%: More passing should hurt sniper (can't hoard on-color cards).
  ★ LEAD CHANGES: More passing = more variance = more comebacks?
  ★ SKILL EDGE: Does more churn reward adaptation skill or just add noise?
  ★ 5P FEASIBILITY: With only 9 cards, can you even pass 3/round?
""")


if __name__ == "__main__":
    main()
