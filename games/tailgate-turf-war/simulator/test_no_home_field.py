#!/usr/bin/env python3
"""
Test removing Home Field entirely (HF=0) vs baseline (HF=3).

HF currently determines 90-99% of wins. Removing it should fundamentally
change the decision landscape — cards are no longer locked to "their" zone
by color. Does that create more interesting decisions or just chaos?

Metrics:
  - Style balance
  - Skill expression (expert vs novices)
  - Zone concentration (do players spread more without HF pulling them to specific zones?)
  - VP distribution
  - Score variance
  - Cards-per-zone distribution (do stacking patterns change?)
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
    Card, COLORS,
    CARD_TYPE_NUMBER, CARD_TYPE_MASCOT, CARD_TYPE_ACTION, CARD_TYPE_DUD,
)
from game_state_v4 import GameStateV4
from ai_player_v4 import AIPlayerV4


# ─── INSTRUMENTED GAME ────────────────────────────────────────────────────

class InstrumentedGame(GameStateV4):
    """Tracks extra metrics for analysis."""

    def __init__(self, num_players, seed=42, config=None):
        self._zone_player_counts = []    # how many players at each zone
        self._cards_per_deployment = []  # cards per player per zone
        self._unique_zones_per_player = defaultdict(list)  # pid -> [zones_used_per_round]
        self._winner_had_best_hand = 0   # winner had highest sum of ranks
        self._total_games_tracked = 0
        self._color_diversity = []       # how many unique colors per zone deployment
        super().__init__(num_players, seed=seed, config=config)

    def _play_round(self, round_num, deployment_fn):
        result = super()._play_round(round_num, deployment_fn)

        # Track zone usage patterns
        for zone in self.zones:
            active = zone.active_players
            self._zone_player_counts.append(len(active))
            for pid in active:
                zp = zone.get_placement(pid)
                self._cards_per_deployment.append(len(zp.cards))
                # Track color diversity at each zone
                colors_used = set(c.color for c in zp.cards if c.has_rank)
                self._color_diversity.append(len(colors_used))

        # Track zones used per player this round
        for player in self.players:
            zones_used = sum(1 for zone in self.zones
                            if zone.get_placement(player.id).cards)
            self._unique_zones_per_player[player.id].append(zones_used)

        return result


def load_config():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config_v4.json")
    with open(path) as f:
        return json.load(f)


def make_config(base_config, hf_bonus):
    """Create config with specified HF bonus."""
    cfg = copy.deepcopy(base_config)
    cfg["game_rules"]["strength"]["home_field_bonus"] = hf_bonus
    return cfg


def run_scenario(label, num_games, num_players, styles, config):
    """Run full analysis."""
    style_wins = defaultdict(float)
    style_games = defaultdict(int)
    style_scores = defaultdict(list)
    all_winner_scores = []
    all_spreads = []
    all_zone_counts = []
    all_cards_per_deploy = []
    all_zones_per_player = []
    all_color_diversity = []
    ties = 0

    for i in range(num_games):
        seed = 1 + i
        game_styles = [styles[(i + j) % len(styles)] for j in range(num_players)]

        game = InstrumentedGame(num_players, seed=seed, config=config)
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
        all_winner_scores.append(max(scores))
        all_spreads.append(max(scores) - min(scores))

        for pid, score in result["scores"].items():
            style_scores[game_styles[pid]].append(score)
            style_games[game_styles[pid]] += 1

        all_zone_counts.extend(game._zone_player_counts)
        all_cards_per_deploy.extend(game._cards_per_deployment)
        all_color_diversity.extend(game._color_diversity)

        for pid in range(num_players):
            all_zones_per_player.extend(game._unique_zones_per_player[pid])

    wr = {s: style_wins[s] / style_games[s] if style_games[s] > 0 else 0
          for s in set(styles)}

    return {
        "label": label,
        "win_rates": wr,
        "style_gap": max(wr.values()) - min(wr.values()),
        "avg_vp": {s: statistics.mean(style_scores[s]) for s in set(styles)},
        "avg_winner_score": statistics.mean(all_winner_scores),
        "winner_stdev": statistics.stdev(all_winner_scores),
        "avg_spread": statistics.mean(all_spreads),
        "tie_rate": ties / num_games,
        "avg_players_per_zone": statistics.mean(all_zone_counts),
        "avg_cards_per_deploy": statistics.mean(all_cards_per_deploy),
        "avg_zones_per_player": statistics.mean(all_zones_per_player),
        "avg_color_diversity": statistics.mean(all_color_diversity),
        "hf_bonus": config["game_rules"]["strength"]["home_field_bonus"],
    }


def run_skill_test(label, num_games, num_players, config):
    """Expert vs novices."""
    expert_wins = 0

    for i in range(num_games):
        seed = 1 + i
        skills = [1.0] + [0.3] * (num_players - 1)

        game = GameStateV4(num_players, seed=seed, config=config)
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
    return {
        "label": label,
        "expert_win_rate": actual,
        "fair_rate": fair,
        "skill_edge": actual - fair,
    }


def print_comparison(baseline, variant, baseline_skill, variant_skill, np):
    """Print side-by-side comparison."""
    print(f"\n  {'Metric':<28} {'HF=3 (baseline)':>18} {'HF=0 (no HF)':>18} {'Delta':>12}")
    print(f"  {'-'*76}")

    # Win rates
    all_styles = sorted(set(list(baseline["win_rates"].keys()) + list(variant["win_rates"].keys())))
    for s in all_styles:
        bwr = baseline["win_rates"].get(s, 0)
        vwr = variant["win_rates"].get(s, 0)
        delta = vwr - bwr
        print(f"  {s + ' win%':<28} {bwr:17.1%} {vwr:17.1%} {delta:+11.1%}")

    print(f"  {'-'*76}")
    print(f"  {'Style gap':<28} {baseline['style_gap']:17.1%} {variant['style_gap']:17.1%} {variant['style_gap'] - baseline['style_gap']:+11.1%}")
    print(f"  {'Winner VP':<28} {baseline['avg_winner_score']:17.1f} {variant['avg_winner_score']:17.1f} {variant['avg_winner_score'] - baseline['avg_winner_score']:+11.1f}")
    print(f"  {'Winner σ':<28} {baseline['winner_stdev']:17.1f} {variant['winner_stdev']:17.1f} {variant['winner_stdev'] - baseline['winner_stdev']:+11.1f}")
    print(f"  {'Score spread':<28} {baseline['avg_spread']:17.1f} {variant['avg_spread']:17.1f} {variant['avg_spread'] - baseline['avg_spread']:+11.1f}")
    print(f"  {'Tie rate':<28} {baseline['tie_rate']:17.1%} {variant['tie_rate']:17.1%} {variant['tie_rate'] - baseline['tie_rate']:+11.1%}")
    print(f"  {'-'*76}")
    print(f"  {'Players per zone':<28} {baseline['avg_players_per_zone']:17.2f} {variant['avg_players_per_zone']:17.2f} {variant['avg_players_per_zone'] - baseline['avg_players_per_zone']:+11.2f}")
    print(f"  {'Cards per deployment':<28} {baseline['avg_cards_per_deploy']:17.2f} {variant['avg_cards_per_deploy']:17.2f} {variant['avg_cards_per_deploy'] - baseline['avg_cards_per_deploy']:+11.2f}")
    print(f"  {'Zones per player/round':<28} {baseline['avg_zones_per_player']:17.2f} {variant['avg_zones_per_player']:17.2f} {variant['avg_zones_per_player'] - baseline['avg_zones_per_player']:+11.2f}")
    print(f"  {'Colors per zone deploy':<28} {baseline['avg_color_diversity']:17.2f} {variant['avg_color_diversity']:17.2f} {variant['avg_color_diversity'] - baseline['avg_color_diversity']:+11.2f}")
    print(f"  {'-'*76}")

    be = baseline_skill["skill_edge"]
    ve = variant_skill["skill_edge"]
    print(f"  {'Expert win rate':<28} {baseline_skill['expert_win_rate']:17.1%} {variant_skill['expert_win_rate']:17.1%} {variant_skill['expert_win_rate'] - baseline_skill['expert_win_rate']:+11.1%}")
    print(f"  {'Skill edge vs fair':<28} {be:+17.1%} {ve:+17.1%} {ve - be:+11.1%}")


def main():
    N = 2000
    base_config = load_config()

    style_sets = {
        3: ["balanced", "aggressive", "sniper"],
        4: ["balanced", "aggressive", "sniper", "hoarder"],
        5: ["balanced", "aggressive", "sniper", "hoarder", "spread"],
    }

    hf3_config = make_config(base_config, 3)
    hf0_config = make_config(base_config, 0)

    print("=" * 80)
    print("  HOME FIELD REMOVAL TEST: HF=3 vs HF=0")
    print(f"  {N} games per scenario")
    print("=" * 80)

    for np in [3, 4, 5]:
        styles = style_sets[np]

        print(f"\n{'='*80}")
        print(f"  {np} PLAYERS")
        print(f"{'='*80}")

        print(f"  Running HF=3 baseline...", end="", flush=True)
        baseline = run_scenario("HF=3", N, np, styles, hf3_config)
        print(" done")

        print(f"  Running HF=0...", end="", flush=True)
        variant = run_scenario("HF=0", N, np, styles, hf0_config)
        print(" done")

        print(f"  Running skill tests...", end="", flush=True)
        b_skill = run_skill_test("HF=3 skill", N, np, hf3_config)
        v_skill = run_skill_test("HF=0 skill", N, np, hf0_config)
        print(" done")

        print_comparison(baseline, variant, b_skill, v_skill, np)

    # ── Also test HF=1 as a middle ground ──
    print(f"\n{'='*80}")
    print(f"  MIDDLE GROUND: HF=1 at 4P")
    print(f"{'='*80}")

    hf1_config = make_config(base_config, 1)
    np = 4
    styles = style_sets[np]

    print(f"  Running HF=1...", end="", flush=True)
    hf1 = run_scenario("HF=1", N, np, styles, hf1_config)
    hf1_skill = run_skill_test("HF=1 skill", N, np, hf1_config)
    print(" done")

    baseline_4p = run_scenario("HF=3", N, np, styles, hf3_config)
    b4_skill = run_skill_test("HF=3 skill", N, np, hf3_config)

    print(f"\n  {'Metric':<28} {'HF=3':>14} {'HF=1':>14} {'HF=0':>14}")
    print(f"  {'-'*70}")

    hf0_4p = run_scenario("HF=0", N, np, styles, hf0_config)
    hf0_4p_skill = run_skill_test("HF=0 skill", N, np, hf0_config)

    for data, sk in [(baseline_4p, b4_skill), (hf1, hf1_skill), (hf0_4p, hf0_4p_skill)]:
        pass  # we'll print inline

    print(f"  {'Style gap':<28} {baseline_4p['style_gap']:13.1%} {hf1['style_gap']:13.1%} {hf0_4p['style_gap']:13.1%}")
    print(f"  {'Winner VP':<28} {baseline_4p['avg_winner_score']:13.1f} {hf1['avg_winner_score']:13.1f} {hf0_4p['avg_winner_score']:13.1f}")
    print(f"  {'Score spread':<28} {baseline_4p['avg_spread']:13.1f} {hf1['avg_spread']:13.1f} {hf0_4p['avg_spread']:13.1f}")
    print(f"  {'Tie rate':<28} {baseline_4p['tie_rate']:13.1%} {hf1['tie_rate']:13.1%} {hf0_4p['tie_rate']:13.1%}")
    print(f"  {'Zones per player':<28} {baseline_4p['avg_zones_per_player']:13.2f} {hf1['avg_zones_per_player']:13.2f} {hf0_4p['avg_zones_per_player']:13.2f}")
    print(f"  {'Colors per zone':<28} {baseline_4p['avg_color_diversity']:13.2f} {hf1['avg_color_diversity']:13.2f} {hf0_4p['avg_color_diversity']:13.2f}")
    print(f"  {'Skill edge':<28} {b4_skill['skill_edge']:+13.1%} {hf1_skill['skill_edge']:+13.1%} {hf0_4p_skill['skill_edge']:+13.1%}")

    # Win rates
    for s in sorted(style_sets[4]):
        b = baseline_4p['win_rates'].get(s, 0)
        h1 = hf1['win_rates'].get(s, 0)
        h0 = hf0_4p['win_rates'].get(s, 0)
        print(f"  {s + ' win%':<28} {b:13.1%} {h1:13.1%} {h0:13.1%}")

    print(f"\n{'='*80}")
    print("  INTERPRETATION")
    print(f"{'='*80}")
    print("""
  What to look for:
  - Style gap: Does removing HF favor one style over others?
  - Tie rate: Without HF's +3 differentiator, do more zones tie?
  - Zones per player: Do players spread more when no color pulls them?
  - Colors per zone: Do players mix colors more freely without HF?
  - Skill edge: Does HF=0 reward or punish good play?
  - Score spread: Tighter = more coin-flip; wider = more differentiation

  If HF=0 creates tighter spreads, more ties, and flatter skill edge,
  then HF was actually ADDING meaningful decisions (play on-color vs off-color).
  If HF=0 opens up spreads and skill edge, then HF was CONSTRAINING decisions.
""")


if __name__ == "__main__":
    main()
