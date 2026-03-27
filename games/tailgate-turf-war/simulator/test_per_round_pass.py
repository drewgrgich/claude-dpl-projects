#!/usr/bin/env python3
"""
Test per-round passing vs single-pass baseline.

Current: Pass once at game start (3 cards at 3P, 2 at 4P, etc.)
Variant: Pass before each round (1 card per round at 3-5P, 2 at 2P)

Key questions:
  1. Does per-round pass change style balance?
  2. Does it increase strategic differentiation (skill expression)?
  3. Does it create more varied game outcomes?
  4. Does it change how much Home Field matters?

Interaction proxies:
  - Style gap: does any style gain/lose edge? (strategic depth signal)
  - Skill gap: test smart AI vs dumb AI — does per-round pass widen the gap?
  - VP variance (σ): does it go up (more varied outcomes) or down (more convergent)?
  - Hand volatility: how much does your hand change across rounds?
  - HF in wins: does per-round pass reduce HF lock-in?
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
    Card, COLORS,
    CARD_TYPE_NUMBER, CARD_TYPE_MASCOT, CARD_TYPE_ACTION, CARD_TYPE_DUD,
    ACTION_SHIELD, ACTION_BOMB, ACTION_SWAP, ACTION_BOUNTY,
)
from game_state_v4 import GameStateV4, Player
from ai_player_v4 import AIPlayerV4, STYLE_PROFILES


# ─── PER-ROUND PASS GAME STATE ───────────────────────────────────────────

class PerRoundPassGame(GameStateV4):
    """Game that passes cards before each round instead of once at start."""

    def __init__(self, num_players, seed=42, config=None, pass_per_round=1):
        self.pass_per_round = pass_per_round
        self._colors_received = defaultdict(lambda: defaultdict(int))  # pid -> color -> count
        self._colors_sent = defaultdict(lambda: defaultdict(int))
        self._hand_sizes_by_round = defaultdict(list)  # pid -> [sizes]
        self._hf_wins = 0
        self._total_wins = 0
        super().__init__(num_players, seed=seed, config=config)

    def play_game(self, deployment_fn, pass_fn=None):
        """Play game with per-round passing."""
        # NO initial pass — instead, pass before each round
        for round_num in range(self.num_rounds):
            self.current_round = round_num

            # Track hand sizes before pass
            for p in self.players:
                self._hand_sizes_by_round[p.id].append(len(p.hand))

            # Pass phase (before each round)
            self._execute_round_pass(pass_fn)

            # Then play the round (condition draw + deploy + score)
            round_stats = self._play_round(round_num, deployment_fn)
            self.stats["rounds"].append(round_stats)

            # Track HF in wins
            for zone_color, winners in round_stats["zone_winners"].items():
                if winners and isinstance(winners, list):
                    for w in winners:
                        self._total_wins += 1
                        zone = self._get_zone(zone_color)
                        zp = zone.get_placement(w)
                        has_hf = any(c.color == zone_color and c.is_natural
                                     for c in zp.cards)
                        if has_hf:
                            self._hf_wins += 1

        self.game_over = True
        return self._compile_final_stats()

    def _execute_round_pass(self, pass_fn=None):
        """Pass cards left — smaller amount each round."""
        pass_count = self.pass_per_round
        passed_cards = {}

        for player in self.players:
            if len(player.hand) <= pass_count:
                passed_cards[player.id] = []
                continue

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

            # Track what colors are being sent
            for c in to_pass:
                self._colors_sent[player.id][c.color] += 1

        # Execute pass left
        for player in self.players:
            to_pass = passed_cards[player.id]
            for card in to_pass:
                if card in player.hand:
                    player.hand.remove(card)

            right_id = (player.id - 1) % self.num_players
            received = passed_cards[right_id]
            player.hand.extend(received)

            for c in received:
                self._colors_received[player.id][c.color] += 1

    def _play_round(self, round_num, deployment_fn):
        """Override to skip the pass that happens in the normal flow."""
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

        self.zones = [__import__('game_state_v4').Zone(color=c, index=i)
                      for i, c in enumerate(self.colors)]

        for player in self.players:
            deploy = deployment_fn(player, self, round_num)
            self._execute_deployment(player, deploy)

        self._log("\n--- REVEAL ---")
        for zone in self.zones:
            for pid in zone.active_players:
                zp = zone.get_placement(pid)
                self._log(f"  {zone.color}: P{pid} played {zp.cards}")

        self._resolve_actions()
        zone_strengths = self._calculate_all_strength()
        round_stats = self._score_round(zone_strengths)

        self._log(f"\nScores: {', '.join(f'P{p.id}={p.score}' for p in self.players)}")
        self.active_condition = None
        return round_stats


class BaselineGame(GameStateV4):
    """Baseline game with HF win tracking."""

    def __init__(self, num_players, seed=42, config=None):
        self._hf_wins = 0
        self._total_wins = 0
        super().__init__(num_players, seed=seed, config=config)

    def _score_round(self, zone_strengths):
        result = super()._score_round(zone_strengths)
        # Track HF in wins
        for zone_color, winners in result["zone_winners"].items():
            if winners and isinstance(winners, list):
                for w in winners:
                    self._total_wins += 1
                    zone = self._get_zone(zone_color)
                    zp = zone.get_placement(w)
                    has_hf = any(c.color == zone_color and c.is_natural
                                 for c in zp.cards)
                    if has_hf:
                        self._hf_wins += 1
        return result


# ─── SIMULATION ───────────────────────────────────────────────────────────

def load_config():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config_v4.json")
    with open(path) as f:
        return json.load(f)


def run_scenario(label, num_games, num_players, styles, config,
                 game_class, game_kwargs=None, skill_levels=None):
    """Run games and collect comprehensive stats."""
    game_kwargs = game_kwargs or {}
    style_wins = defaultdict(float)
    style_games = defaultdict(int)
    style_scores = defaultdict(list)
    all_winner_scores = []
    all_spreads = []
    all_score_stdevs = []
    hf_wins_total = 0
    total_wins_total = 0

    for i in range(num_games):
        seed = 1 + i
        game_styles = [styles[(i + j) % len(styles)] for j in range(num_players)]

        game = game_class(num_players, seed=seed, config=config, **game_kwargs)

        if skill_levels:
            ais = [AIPlayerV4(pid, skill=skill_levels[pid % len(skill_levels)],
                               style=game_styles[pid], rng_seed=seed * 100 + pid)
                   for pid in range(num_players)]
        else:
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
        if len(scores) > 1:
            all_score_stdevs.append(statistics.stdev(scores))

        for pid, score in result["scores"].items():
            style_scores[game_styles[pid]].append(score)
            style_games[game_styles[pid]] += 1

        hf_wins_total += game._hf_wins
        total_wins_total += game._total_wins

    wr = {s: style_wins[s] / style_games[s] if style_games[s] > 0 else 0
          for s in set(styles)}
    max_wr = max(wr.values()) if wr else 0
    min_wr = min(wr.values()) if wr else 0

    return {
        "label": label,
        "win_rates": wr,
        "style_gap": max_wr - min_wr,
        "avg_winner_score": statistics.mean(all_winner_scores),
        "winner_score_stdev": statistics.stdev(all_winner_scores),
        "avg_spread": statistics.mean(all_spreads),
        "avg_in_game_stdev": statistics.mean(all_score_stdevs) if all_score_stdevs else 0,
        "hf_in_wins": hf_wins_total / total_wins_total if total_wins_total > 0 else 0,
    }


def run_skill_test(label, num_games, num_players, config, game_class, game_kwargs=None):
    """Test skill expression: 1 expert vs N-1 novices. How often does expert win?"""
    game_kwargs = game_kwargs or {}
    expert_wins = 0

    for i in range(num_games):
        seed = 1 + i
        # Player 0 is expert (skill=1.0), others are novices (skill=0.3)
        skills = [1.0] + [0.3] * (num_players - 1)
        styles = ["balanced"] * num_players

        game = game_class(num_players, seed=seed, config=config, **game_kwargs)
        ais = [AIPlayerV4(pid, skill=skills[pid], style="balanced",
                           rng_seed=seed * 100 + pid) for pid in range(num_players)]

        def dfn(p, gs, rn):
            return ais[p.id].choose_deployment(p, gs, rn)

        def pfn(p, gs, pc):
            return ais[p.id].choose_pass(p, gs, pc)

        result = game.play_game(dfn, pfn)
        winner = result["winner"]
        if isinstance(winner, int) and winner == 0:
            expert_wins += 1
        elif isinstance(winner, list) and 0 in winner:
            expert_wins += 1.0 / len(winner)

    fair = 1.0 / num_players
    actual = expert_wins / num_games
    edge = actual - fair
    return {
        "label": label,
        "expert_win_rate": actual,
        "fair_rate": fair,
        "skill_edge": edge,
        "edge_pct": edge / fair * 100,
    }


# ─── MAIN ─────────────────────────────────────────────────────────────────

def main():
    N = 2000
    config = load_config()

    style_sets = {
        3: ["balanced", "aggressive", "sniper"],
        4: ["balanced", "aggressive", "sniper", "hoarder"],
        5: ["balanced", "aggressive", "sniper", "hoarder", "spread"],
    }

    # Pass counts per round for per-round variant
    # Current total pass: 3P=3, 4P=2, 5P=2
    # Per-round (4 rounds): 3P=1/round (4 total), 4P=1/round (4 total), 5P=1/round (4 total)
    pass_per_round = {3: 1, 4: 1, 5: 1}

    print("=" * 70)
    print("  PER-ROUND PASS TEST")
    print(f"  {N} games per scenario")
    print("=" * 70)

    for np in [3, 4, 5]:
        styles = style_sets[np]
        fair = 1.0 / np
        ppr = pass_per_round[np]

        print(f"\n{'='*70}")
        print(f"  {np} PLAYERS  (per-round pass = {ppr} card/round, total = {ppr * 4})")
        print(f"  (baseline single pass = {config['game_rules']['pass_count'][f'{np}_player']} cards)")
        print(f"{'='*70}")

        # ── Test 1: Style balance ──
        print("\n  TEST 1: Style Balance")
        print("  " + "-" * 50)

        baseline = run_scenario(
            "BASELINE (single pass)", N, np, styles, config,
            BaselineGame)

        per_round = run_scenario(
            f"PER-ROUND PASS ({ppr}/round)", N, np, styles, config,
            PerRoundPassGame, {"pass_per_round": ppr})

        for data in [baseline, per_round]:
            print(f"\n  {data['label']}:")
            sorted_styles = sorted(data["win_rates"].keys(),
                                   key=lambda s: -data["win_rates"][s])
            for s in sorted_styles:
                print(f"    {s:<12} {data['win_rates'][s]:6.1%}")
            print(f"    Gap: {data['style_gap']:.1%} | "
                  f"Winner VP: {data['avg_winner_score']:.1f} (σ={data['winner_score_stdev']:.1f}) | "
                  f"Spread: {data['avg_spread']:.1f} | "
                  f"HF in wins: {data['hf_in_wins']:.0%}")

        # ── Test 2: Skill expression ──
        print(f"\n  TEST 2: Skill Expression (expert vs {np-1} novices)")
        print("  " + "-" * 50)

        baseline_skill = run_skill_test(
            "BASELINE", N, np, config, BaselineGame)
        perround_skill = run_skill_test(
            "PER-ROUND", N, np, config, PerRoundPassGame, {"pass_per_round": ppr})

        for data in [baseline_skill, perround_skill]:
            print(f"    {data['label']:<15} Expert wins: {data['expert_win_rate']:.1%} "
                  f"(fair={data['fair_rate']:.1%}, edge=+{data['skill_edge']:.1%}, "
                  f"+{data['edge_pct']:.0f}% above fair)")

        # ── Test 3: Hand volatility (per-round only) ──
        print(f"\n  TEST 3: Outcome Variance")
        print("  " + "-" * 50)
        print(f"    Baseline winner σ:  {baseline['winner_score_stdev']:.1f}")
        print(f"    Per-round winner σ: {per_round['winner_score_stdev']:.1f}")
        delta_sigma = per_round['winner_score_stdev'] - baseline['winner_score_stdev']
        print(f"    Δσ: {delta_sigma:+.1f} ({'more varied' if delta_sigma > 0 else 'more convergent'})")

    # ── Bonus: test 2 cards per round at 3P ──
    print(f"\n{'='*70}")
    print("  BONUS: Higher pass rate (2/round at 3P)")
    print(f"{'='*70}")

    np = 3
    styles = style_sets[np]

    high_pass = run_scenario(
        "2 cards/round at 3P", N, np, styles, config,
        PerRoundPassGame, {"pass_per_round": 2})

    high_skill = run_skill_test(
        "2/round skill", N, np, config, PerRoundPassGame, {"pass_per_round": 2})

    baseline_3p = run_scenario(
        "BASELINE (single pass)", N, np, styles, config, BaselineGame)

    print(f"\n  BASELINE (single pass, 3 cards):")
    for s in sorted(baseline_3p["win_rates"].keys(), key=lambda s: -baseline_3p["win_rates"][s]):
        print(f"    {s:<12} {baseline_3p['win_rates'][s]:6.1%}")
    print(f"    Gap: {baseline_3p['style_gap']:.1%} | HF: {baseline_3p['hf_in_wins']:.0%}")

    print(f"\n  PER-ROUND (2 cards/round, 8 total):")
    for s in sorted(high_pass["win_rates"].keys(), key=lambda s: -high_pass["win_rates"][s]):
        print(f"    {s:<12} {high_pass['win_rates'][s]:6.1%}")
    print(f"    Gap: {high_pass['style_gap']:.1%} | HF: {high_pass['hf_in_wins']:.0%}")
    print(f"    Skill edge: +{high_skill['skill_edge']:.1%} (+{high_skill['edge_pct']:.0f}% above fair)")

    # ── SUMMARY ──
    print(f"\n{'='*70}")
    print("  SUMMARY")
    print(f"{'='*70}")
    print("""
  Key metrics to compare:
  - Skill edge: higher = more skill expression (game rewards good play)
  - HF in wins: lower = less automatic lane assignment (more room for reads)
  - Style gap: ideally stays similar (per-round pass shouldn't break balance)
  - Winner σ: higher = more game-to-game variety

  The core hypothesis: per-round passing creates an ongoing information
  channel between players, reducing the solitaire feeling and rewarding
  players who adapt to what they receive each round.
""")


if __name__ == "__main__":
    main()
