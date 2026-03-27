#!/usr/bin/env python3
"""
Test Kimi's proposed mechanics: Debt Cards and Rotating Exile.
All variants use per-round passing (1 card/round) + zone-matched HF=3.

DEBT CARDS:
  When you win a zone, take a Debt token. At game end, player with the
  most Debt loses 5 VP. (Ties: all tied players lose 5 VP.)
  Creates "do I really want to win this?" tension.

ROTATING EXILE:
  After each round, the color of the zone(s) you won is "exiled" for you —
  you can't play cards of that color next round. Forces adaptation.

BOTH COMBINED:
  Debt + Exile together. Maximum pressure against snowballing.

Metrics:
  - Style balance / gap
  - Skill expression (expert vs novices)
  - Lead changes (comeback potential)
  - VP spread (tighter = more competitive)
  - Intentional loss rate (Debt only: do players ever tank a zone?)
  - Close games / blowouts
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
from ai_player_v4 import AIPlayerV4, STYLE_PROFILES


# ─── DEBT + EXILE GAME ───────────────────────────────────────────────────

class MechanicsTestGame(GameStateV4):
    """Game state with optional Debt Cards and/or Rotating Exile."""

    def __init__(self, num_players, seed=42, config=None,
                 pass_per_round=1,
                 use_debt=False, debt_penalty=5,
                 use_exile=False):
        self.pass_per_round = pass_per_round
        self.use_debt = use_debt
        self.debt_penalty = debt_penalty
        self.use_exile = use_exile

        # Debt tracking
        self._debt = defaultdict(int)  # pid -> debt tokens

        # Exile tracking
        self._exiled_colors = defaultdict(set)  # pid -> set of exiled colors

        # Metrics
        self._lead_changes = 0
        self._round_leaders = []

        super().__init__(num_players, seed=seed, config=config)

    def play_game(self, deployment_fn, pass_fn=None):
        for round_num in range(self.num_rounds):
            self.current_round = round_num

            # Per-round pass
            self._execute_round_pass(pass_fn)

            round_stats = self._play_round_custom(round_num, deployment_fn)
            self.stats["rounds"].append(round_stats)

            # Track lead changes (before debt penalty)
            scores = [p.score for p in self.players]
            leader = scores.index(max(scores))
            if self._round_leaders and self._round_leaders[-1] != leader:
                self._lead_changes += 1
            self._round_leaders.append(leader)

            # Update exile based on round results
            if self.use_exile:
                self._update_exile(round_stats)

        # Apply debt penalty at game end
        if self.use_debt:
            self._apply_debt_penalty()

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

        # Award debt tokens to zone winners
        if self.use_debt:
            for zone_color, winners in round_stats["zone_winners"].items():
                if winners and isinstance(winners, list):
                    for w in winners:
                        self._debt[w] += 1

        self.active_condition = None
        return round_stats

    def _update_exile(self, round_stats):
        """After round, exile the colors of zones each player won."""
        # Clear previous exile
        self._exiled_colors = defaultdict(set)

        for zone_color, winners in round_stats["zone_winners"].items():
            if winners and isinstance(winners, list):
                for w in winners:
                    self._exiled_colors[w].add(zone_color)

    def _apply_debt_penalty(self):
        """At game end, highest-debt player(s) lose penalty VP."""
        if not self._debt:
            return
        max_debt = max(self._debt.values())
        if max_debt == 0:
            return
        for pid, debt in self._debt.items():
            if debt == max_debt:
                self.players[pid].score -= self.debt_penalty
                # Don't go below 0
                self.players[pid].score = max(0, self.players[pid].score)

    def _execute_deployment(self, player, deploy):
        """Override to enforce exile restrictions."""
        if self.use_exile:
            exiled = self._exiled_colors.get(player.id, set())
            filtered_deploy = {}
            for color, cards in deploy.items():
                # Remove exiled-color cards from this deployment
                allowed = [c for c in cards
                           if c.color not in exiled or not c.is_natural]
                # Actually: exile means you can't play cards OF that color anywhere
                # So filter out cards whose color is exiled
                allowed = [c for c in cards if c.color not in exiled]
                if allowed:
                    filtered_deploy[color] = allowed
            deploy = filtered_deploy

        super()._execute_deployment(player, deploy)


# ─── DEBT-AWARE AI ────────────────────────────────────────────────────────

class DebtAwareAI(AIPlayerV4):
    """AI that considers debt when making deployment decisions."""

    def __init__(self, *args, game_ref=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.game_ref = None  # set per-game

    def _score_card_at_zone(self, card, zone_color, vp, zone_counts):
        score = super()._score_card_at_zone(card, zone_color, vp, zone_counts)

        # If we have high debt, slightly discount winning (reduce card scores)
        if self.game_ref and hasattr(self.game_ref, '_debt'):
            my_debt = self.game_ref._debt.get(self.player_id, 0)
            max_debt = max(self.game_ref._debt.values()) if self.game_ref._debt else 0

            if my_debt > 0 and my_debt >= max_debt:
                # We're the debt leader — slightly reduce incentive to win more
                # Scale: at 2 debt lead, reduce by ~20%
                debt_discount = min(0.3, my_debt * 0.08)
                score *= (1.0 - debt_discount)

        return score


class ExileAwareAI(AIPlayerV4):
    """AI that knows which colors are exiled for it."""

    def choose_deployment(self, player, game_state, round_num):
        # Let parent do deployment, exile filtering happens in game state
        return super().choose_deployment(player, game_state, round_num)


# ─── SIMULATION ───────────────────────────────────────────────────────────

def load_config():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config_v4.json")
    with open(path) as f:
        return json.load(f)


def run_scenario(label, N, np, styles, config,
                 use_debt=False, use_exile=False, debt_penalty=5):
    style_wins = defaultdict(float)
    style_games = defaultdict(int)
    style_scores = defaultdict(list)
    all_winner = []
    all_spread = []
    total_lc = 0
    total_debt_penalties = 0

    for i in range(N):
        seed = 1 + i
        gs = [styles[(i + j) % len(styles)] for j in range(np)]

        game = MechanicsTestGame(np, seed=seed, config=config,
                                  use_debt=use_debt, debt_penalty=debt_penalty,
                                  use_exile=use_exile)

        if use_debt:
            ais = [DebtAwareAI(pid, skill=1.0, style=gs[pid], rng_seed=seed*100+pid)
                   for pid in range(np)]
            for ai in ais:
                ai.game_ref = game
        else:
            ais = [AIPlayerV4(pid, skill=1.0, style=gs[pid], rng_seed=seed*100+pid)
                   for pid in range(np)]

        def dfn(p, g, rn):
            if use_debt and hasattr(ais[p.id], 'game_ref'):
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

        # Count debt penalties applied
        if use_debt and game._debt:
            max_d = max(game._debt.values())
            penalized = sum(1 for d in game._debt.values() if d == max_d and d > 0)
            total_debt_penalties += penalized

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
        "debt_penalties_per_game": total_debt_penalties/N if use_debt else 0,
    }


def run_skill(label, N, np, config, use_debt=False, use_exile=False, debt_penalty=5):
    expert_wins = 0
    for i in range(N):
        seed = 1+i
        game = MechanicsTestGame(np, seed=seed, config=config,
                                  use_debt=use_debt, debt_penalty=debt_penalty,
                                  use_exile=use_exile)

        if use_debt:
            expert = DebtAwareAI(0, skill=1.0, style="balanced", rng_seed=seed*100)
            expert.game_ref = game
            novices = [AIPlayerV4(pid, skill=0.3, style="balanced", rng_seed=seed*100+pid)
                       for pid in range(1, np)]
        else:
            expert = AIPlayerV4(0, skill=1.0, style="balanced", rng_seed=seed*100)
            novices = [AIPlayerV4(pid, skill=0.3, style="balanced", rng_seed=seed*100+pid)
                       for pid in range(1, np)]

        all_ai = [expert] + novices

        def dfn(p, g, rn):
            if use_debt and hasattr(all_ai[p.id], 'game_ref'):
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

    scenarios = [
        ("BASELINE (per-round pass only)", False, False, 0),
        ("DEBT CARDS (-5 VP)", True, False, 5),
        ("DEBT CARDS (-3 VP)", True, False, 3),
        ("ROTATING EXILE", False, True, 0),
        ("DEBT (-5) + EXILE", True, True, 5),
    ]

    print("="*90)
    print("  KIMI MECHANICS TEST: Debt Cards & Rotating Exile")
    print(f"  All variants use per-round passing + zone-matched HF=3")
    print(f"  {N} games per scenario")
    print("="*90)

    for np in [3, 4, 5]:
        styles = style_sets[np]

        print(f"\n{'='*90}")
        print(f"  {np} PLAYERS")
        print(f"{'='*90}")

        results = []
        skill_res = []

        for label, debt, exile, dp in scenarios:
            print(f"  Running {label}...", end="", flush=True)
            r = run_scenario(label, N, np, styles, config,
                             use_debt=debt, use_exile=exile, debt_penalty=dp)
            s = run_skill(label, N, np, config,
                          use_debt=debt, use_exile=exile, debt_penalty=dp)
            results.append(r)
            skill_res.append(s)
            print(" done")

        # Print
        cw = 16
        print(f"\n  {'Metric':<24}", end="")
        for r in results:
            short = r['label'][:cw]
            print(f" {short:>{cw}}", end="")
        print()
        print(f"  {'-'*(24+(cw+1)*len(results))}")

        print(f"  {'Style gap':<24}", end="")
        for r in results: print(f" {r['style_gap']:>{cw}.1%}", end="")
        print()

        all_s = sorted(set(s for r in results for s in r["win_rates"]))
        for st in all_s:
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
        ]:
            print(f"  {metric:<24}", end="")
            for r in results: print(f" {r[key]:>{cw}{fmt}}", end="")
            print()

        # Debt-specific
        print(f"  {'Debt penalties/game':<24}", end="")
        for r in results: print(f" {r['debt_penalties_per_game']:>{cw}.2f}", end="")
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
    print("  WHAT WE'RE LOOKING FOR")
    print("="*90)
    print("""
  DEBT CARDS — "Do I want to win?" tension:
    ✓ Lead changes should go UP (leaders pull back, trailers catch up)
    ✓ Close games should go UP (debt compresses final scores)
    ✓ Blowouts should go DOWN
    ✓ Skill edge should go UP (managing debt = new decision axis)

  ROTATING EXILE — Anti-snowball:
    ✓ Style gap should stay tight (no style exploits exile)
    ✓ Lead changes should go UP (winners lose options)
    ✓ Sniper should be hit hardest (loses access to best color)

  COMBINED — Maximum comeback potential:
    ✓ Both effects compound
    ? Might over-punish winners and make winning feel bad
""")


if __name__ == "__main__":
    main()
