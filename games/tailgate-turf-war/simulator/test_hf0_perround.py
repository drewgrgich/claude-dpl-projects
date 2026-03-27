#!/usr/bin/env python3
"""
Test the full 2×2 matrix:
  - HF=3 + single pass (current baseline)
  - HF=3 + per-round pass
  - HF=0 + single pass
  - HF=0 + per-round pass  ← the candidate

Plus skill expression test for each.

The hypothesis: HF=0 + per-round pass turns each round into a fresh
"maximize with what you have" puzzle. Cards don't belong to zones,
and your hand shifts every round. This should:
  - Increase decision variety (different hand each round)
  - Reduce auto-pilot (no "always play Red at Red zone")
  - Maintain or increase skill expression
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

from cards_v4 import Card, COLORS, CARD_TYPE_ACTION
from game_state_v4 import GameStateV4
from ai_player_v4 import AIPlayerV4


# ─── PER-ROUND PASS GAME (copied from test_per_round_pass.py) ────────────

class PerRoundPassGame(GameStateV4):
    def __init__(self, num_players, seed=42, config=None, pass_per_round=1):
        self.pass_per_round = pass_per_round
        super().__init__(num_players, seed=seed, config=config)

    def play_game(self, deployment_fn, pass_fn=None):
        for round_num in range(self.num_rounds):
            self.current_round = round_num
            self._execute_round_pass(pass_fn)
            round_stats = self._play_round(round_num, deployment_fn)
            self.stats["rounds"].append(round_stats)
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
                candidates = ranked + non_ranked
                to_pass = candidates[:pass_count]
            passed_cards[player.id] = to_pass

        for player in self.players:
            for card in passed_cards[player.id]:
                if card in player.hand:
                    player.hand.remove(card)
            right_id = (player.id - 1) % self.num_players
            player.hand.extend(passed_cards[right_id])

    def _play_round(self, round_num, deployment_fn):
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

        from game_state_v4 import Zone
        self.zones = [Zone(color=c, index=i) for i, c in enumerate(self.colors)]

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


# ─── METRICS COLLECTION ──────────────────────────────────────────────────

def load_config():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config_v4.json")
    with open(path) as f:
        return json.load(f)


def make_config(base, hf_bonus):
    cfg = copy.deepcopy(base)
    cfg["game_rules"]["strength"]["home_field_bonus"] = hf_bonus
    return cfg


def run_games(label, num_games, num_players, styles, config,
              game_class=GameStateV4, game_kwargs=None):
    game_kwargs = game_kwargs or {}
    style_wins = defaultdict(float)
    style_games = defaultdict(int)
    style_scores = defaultdict(list)
    all_winner_scores = []
    all_spreads = []
    ties = 0
    close_games = 0  # spread <= 5
    blowouts = 0     # spread >= 25

    # Track round-by-round VP share
    round_vp = defaultdict(list)  # round_num -> [vp_this_round, ...]

    for i in range(num_games):
        seed = 1 + i
        game_styles = [styles[(i + j) % len(styles)] for j in range(num_players)]

        game = game_class(num_players, seed=seed, config=config, **game_kwargs)
        ais = [AIPlayerV4(pid, skill=1.0, style=game_styles[pid],
                           rng_seed=seed * 100 + pid) for pid in range(num_players)]

        def dfn(p, gs, rn):
            return ais[p.id].choose_deployment(p, gs, rn)
        def pfn(p, gs, pc):
            return ais[p.id].choose_pass(p, gs, pc)

        result = game.play_game(dfn, pfn)

        winner = result["winner"]
        if isinstance(winner, list):
            ties += 1
            for w in winner:
                style_wins[game_styles[w]] += 1.0 / len(winner)
        else:
            style_wins[game_styles[winner]] += 1

        scores = list(result["scores"].values())
        spread = max(scores) - min(scores)
        all_winner_scores.append(max(scores))
        all_spreads.append(spread)
        if spread <= 5:
            close_games += 1
        if spread >= 25:
            blowouts += 1

        for pid, score in result["scores"].items():
            style_scores[game_styles[pid]].append(score)
            style_games[game_styles[pid]] += 1

        # Track VP per round
        for rn, rs in enumerate(game.stats["rounds"]):
            total_vp = sum(rs["vp_awarded"].values())
            round_vp[rn].append(total_vp)

    wr = {s: style_wins[s] / style_games[s] if style_games[s] > 0 else 0
          for s in set(styles)}

    return {
        "label": label,
        "win_rates": wr,
        "style_gap": max(wr.values()) - min(wr.values()),
        "avg_vp": {s: statistics.mean(style_scores[s]) for s in set(styles)},
        "avg_winner": statistics.mean(all_winner_scores),
        "winner_stdev": statistics.stdev(all_winner_scores),
        "avg_spread": statistics.mean(all_spreads),
        "tie_pct": ties / num_games,
        "close_pct": close_games / num_games,
        "blowout_pct": blowouts / num_games,
        "round_vp": {rn: statistics.mean(vps) for rn, vps in round_vp.items()},
    }


def run_skill_test(label, num_games, num_players, config,
                   game_class=GameStateV4, game_kwargs=None):
    game_kwargs = game_kwargs or {}
    expert_wins = 0

    for i in range(num_games):
        seed = 1 + i
        skills = [1.0] + [0.3] * (num_players - 1)
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
    return {"label": label, "expert_wr": actual, "fair": fair,
            "edge": actual - fair, "edge_pct": (actual - fair) / fair * 100}


# ─── MAIN ─────────────────────────────────────────────────────────────────

def main():
    N = 2000
    base = load_config()

    hf3 = make_config(base, 3)
    hf0 = make_config(base, 0)

    style_sets = {
        3: ["balanced", "aggressive", "sniper"],
        4: ["balanced", "aggressive", "sniper", "hoarder"],
        5: ["balanced", "aggressive", "sniper", "hoarder", "spread"],
    }

    configs = [
        ("HF=3 + single pass", hf3, GameStateV4, {}),
        ("HF=3 + per-round pass", hf3, PerRoundPassGame, {"pass_per_round": 1}),
        ("HF=0 + single pass", hf0, GameStateV4, {}),
        ("HF=0 + per-round pass", hf0, PerRoundPassGame, {"pass_per_round": 1}),
    ]

    print("=" * 85)
    print("  2×2 MATRIX: Home Field × Pass Timing")
    print(f"  {N} games per cell")
    print("=" * 85)

    for np in [3, 4, 5]:
        styles = style_sets[np]
        fair = 1.0 / np

        print(f"\n{'='*85}")
        print(f"  {np} PLAYERS")
        print(f"{'='*85}")

        results = []
        skills = []

        for label, cfg, cls, kwargs in configs:
            print(f"  Running {label}...", end="", flush=True)
            r = run_games(label, N, np, styles, cfg, cls, kwargs)
            s = run_skill_test(label, N, np, cfg, cls, kwargs)
            results.append(r)
            skills.append(s)
            print(" done")

        # ── Comparison table ──
        headers = [r["label"] for r in results]
        col_w = 22

        print(f"\n  {'Metric':<24}", end="")
        for h in headers:
            # Abbreviate
            short = h.replace(" + single pass", "+1x").replace(" + per-round pass", "+4x")
            print(f" {short:>{col_w}}", end="")
        print()
        print(f"  {'-'* (24 + (col_w + 1) * len(headers))}")

        # Style gap
        print(f"  {'Style gap':<24}", end="")
        for r in results:
            print(f" {r['style_gap']:>{col_w}.1%}", end="")
        print()

        # Win rates per style
        all_styles = sorted(set(s for r in results for s in r["win_rates"]))
        for st in all_styles:
            print(f"  {st + ' win%':<24}", end="")
            for r in results:
                print(f" {r['win_rates'].get(st, 0):>{col_w}.1%}", end="")
            print()

        print(f"  {'-'* (24 + (col_w + 1) * len(headers))}")

        # Scores
        print(f"  {'Winner VP':<24}", end="")
        for r in results:
            print(f" {r['avg_winner']:>{col_w}.1f}", end="")
        print()

        print(f"  {'Winner σ':<24}", end="")
        for r in results:
            print(f" {r['winner_stdev']:>{col_w}.1f}", end="")
        print()

        print(f"  {'Avg spread':<24}", end="")
        for r in results:
            print(f" {r['avg_spread']:>{col_w}.1f}", end="")
        print()

        print(f"  {'Close games (≤5)':<24}", end="")
        for r in results:
            print(f" {r['close_pct']:>{col_w}.0%}", end="")
        print()

        print(f"  {'Blowouts (≥25)':<24}", end="")
        for r in results:
            print(f" {r['blowout_pct']:>{col_w}.0%}", end="")
        print()

        print(f"  {'Ties':<24}", end="")
        for r in results:
            print(f" {r['tie_pct']:>{col_w}.1%}", end="")
        print()

        print(f"  {'-'* (24 + (col_w + 1) * len(headers))}")

        # Skill
        print(f"  {'Expert win%':<24}", end="")
        for s in skills:
            print(f" {s['expert_wr']:>{col_w}.1%}", end="")
        print()

        print(f"  {'Skill edge':<24}", end="")
        for s in skills:
            print(f" {s['edge']:+>{col_w}.1%}", end="")
        print()

        print(f"  {'Edge vs fair':<24}", end="")
        for s in skills:
            print(f" {s['edge_pct']:+>{col_w}.0f}%", end="")
        print()

        # VP by round
        print(f"\n  VP by round:")
        for rn in range(4):
            print(f"    Round {rn+1}:  ", end="")
            for r in results:
                vp = r["round_vp"].get(rn, 0)
                print(f" {vp:>{col_w - 5}.1f}     ", end="")
            print()

    print(f"\n{'='*85}")
    print("  KEY QUESTIONS")
    print(f"{'='*85}")
    print("""
  1. Does HF=0 + per-round pass produce more CLOSE GAMES?
     (Close games = players feel competitive, not steamrolled)

  2. Does the SKILL EDGE increase?
     (Higher = decisions matter more, not just card luck)

  3. Is VP distributed more evenly across rounds?
     (Flat = every round matters; front/back-loaded = some rounds are dead)

  4. Does the STYLE GAP stay reasonable?
     (If one style dominates, the optimization puzzle has a solved answer)

  The ideal outcome: similar balance, higher skill edge, more close games,
  flatter VP curve across rounds.
""")


if __name__ == "__main__":
    main()
