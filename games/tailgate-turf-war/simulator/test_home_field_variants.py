#!/usr/bin/env python3
"""
Test Home Field variants to find one that opens up deployment decisions.

Current: +3 if any natural card matches zone color (90% of wins have HF)

Variants:
  A. BASELINE  — current rules (+3 for 1+ matching natural)
  B. REQUIRE 2 — +3 only if 2+ matching naturals at that zone
  C. SCALING   — +1 for 1 matching natural, +3 for 2+
  D. WILD FIELD — +3 on-color (unchanged), +1 if NO cards match zone color

Metrics we care about:
  - HF frequency in winning plays (want < 90%)
  - Off-color win rate (want > 10%)
  - Style balance (don't break what works)
  - VP distribution (no inflation)
  - Does it increase Yomi? (re-test adaptive AI with best variant)
"""

import copy
import json
import math
import os
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
from game_state_v4 import GameStateV4
from ai_player_v4 import AIPlayerV4, STYLE_PROFILES


# ─── PATCHED GAME STATES ──────────────────────────────────────────────────

class HFVariantGame(GameStateV4):
    """Game state with configurable Home Field variant."""

    def __init__(self, num_players, seed=42, config=None, hf_mode="baseline"):
        super().__init__(num_players, seed=seed, config=config)
        self.hf_mode = hf_mode
        self.hf_in_wins = 0
        self.no_hf_in_wins = 0

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

        # Home Field — varies by mode
        home_field = 0
        no_hf = (self.active_condition and
                 self.active_condition.effect == "no_home_field")

        if not no_hf:
            matching_naturals = sum(
                1 for c in cards
                if c.color == zone_color and c.is_natural
            )

            if self.hf_mode == "baseline":
                # Current: +3 for any matching natural
                if matching_naturals >= 1:
                    home_field = 3
                    self.stats["home_field_triggers"] += 1

            elif self.hf_mode == "require_2":
                # +3 only if 2+ matching naturals
                if matching_naturals >= 2:
                    home_field = 3
                    self.stats["home_field_triggers"] += 1

            elif self.hf_mode == "scaling":
                # +1 for 1 matching, +3 for 2+
                if matching_naturals >= 2:
                    home_field = 3
                    self.stats["home_field_triggers"] += 1
                elif matching_naturals == 1:
                    home_field = 1
                    self.stats["home_field_triggers"] += 1

            elif self.hf_mode == "wild_field":
                # +3 on-color (as before), +1 if NO cards match zone
                if matching_naturals >= 1:
                    home_field = 3
                    self.stats["home_field_triggers"] += 1
                else:
                    # Wild Field: bonus for going fully off-color
                    home_field = 1

        return best_rank + extra_bonus + home_field


# ─── ANALYSIS RUNNER ───────────────────────────────────────────────────────

def load_config():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config_v4.json")
    with open(path) as f:
        return json.load(f)


def run_variant(num_games, num_players, styles, config, hf_mode):
    """Run games with a specific HF variant and collect metrics."""
    style_wins = defaultdict(float)
    style_games = defaultdict(int)
    style_scores = defaultdict(list)
    hf_in_wins = 0
    no_hf_in_wins = 0
    total_zone_wins = 0
    all_spreads = []
    all_winner_scores = []

    for i in range(num_games):
        seed = 1 + i
        game_styles = [styles[(i + j) % len(styles)] for j in range(num_players)]

        game = HFVariantGame(num_players, seed=seed, config=config, hf_mode=hf_mode)
        ais = [AIPlayerV4(pid, skill=1.0, style=game_styles[pid],
                           rng_seed=seed * 100 + pid) for pid in range(num_players)]

        def dfn(p, gs, rn):
            return ais[p.id].choose_deployment(p, gs, rn)

        def pfn(p, gs, pc):
            return ais[p.id].choose_pass(p, gs, pc)

        # We need to track HF in winning plays manually
        # Override: hook into scoring by running game normally, then analyze
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
        "win_rates": {s: style_wins[s] / style_games[s]
                      if style_games[s] > 0 else 0
                      for s in set(styles)},
        "avg_vp": {s: statistics.mean(style_scores[s])
                   if style_scores[s] else 0
                   for s in set(styles)},
        "avg_winner_score": statistics.mean(all_winner_scores),
        "avg_spread": statistics.mean(all_spreads),
    }


def run_hf_tracking(num_games, num_players, styles, config, hf_mode):
    """Run games and track HF in winning plays."""
    hf_in_wins = 0
    no_hf_in_wins = 0

    for i in range(num_games):
        seed = 1 + i
        game_styles = [styles[(i + j) % len(styles)] for j in range(num_players)]

        game = HFVariantGame(num_players, seed=seed, config=config, hf_mode=hf_mode)
        ais = [AIPlayerV4(pid, skill=1.0, style=game_styles[pid],
                           rng_seed=seed * 100 + pid) for pid in range(num_players)]

        def dfn(p, gs, rn):
            return ais[p.id].choose_deployment(p, gs, rn)

        def pfn(p, gs, pc):
            return ais[p.id].choose_pass(p, gs, pc)

        # Run the game round by round to capture zone-level data
        game.execute_pass(pfn)

        for round_num in range(game.num_rounds):
            game.current_round = round_num

            if game.condition_deck:
                game.active_condition = game.condition_deck.pop(0)
                game.stats["condition_cards_drawn"].append(game.active_condition.name)
            else:
                game.active_condition = None

            for p in game.players:
                p.zones_won_this_round = 0

            from game_state_v4 import Zone
            game.zones = [Zone(color=c, index=i) for i, c in enumerate(game.colors)]

            for player in game.players:
                deploy = dfn(player, game, round_num)
                game._execute_deployment(player, deploy)

            game._resolve_actions()
            zone_strengths = game._calculate_all_strength()

            # Analyze winning plays before scoring
            cond = game.active_condition
            for zone in game.zones:
                strength_map = zone_strengths.get(zone.color, {})
                if len(strength_map) < 1:
                    continue

                inversion = cond and cond.effect == "lowest_wins"
                target = min(strength_map.values()) if inversion else max(strength_map.values())
                if target <= 0:
                    continue

                winners = [pid for pid, s in strength_map.items() if s == target]
                if len(winners) > 1 and cond and cond.effect == "ties_lose":
                    continue

                for w in winners:
                    zp = zone.get_placement(w)
                    no_hf_cond = cond and cond.effect == "no_home_field"
                    if not no_hf_cond:
                        has_match = any(c.color == zone.color and c.is_natural for c in zp.cards)
                        if has_match:
                            hf_in_wins += 1
                        else:
                            no_hf_in_wins += 1
                    else:
                        no_hf_in_wins += 1

            game.stats["rounds"].append(game._score_round(zone_strengths))
            game.active_condition = None

    total = hf_in_wins + no_hf_in_wins
    return hf_in_wins / total if total > 0 else 0, total


# ─── MAIN ──────────────────────────────────────────────────────────────────

def main():
    N = 2000
    config = load_config()

    variants = [
        ("baseline", "BASELINE (+3 for 1+ matching)"),
        ("require_2", "REQUIRE 2 (+3 only for 2+ matching)"),
        ("scaling", "SCALING (+1 for 1, +3 for 2+)"),
        ("wild_field", "WILD FIELD (+3 on-color, +1 off-color)"),
    ]

    style_sets = {
        3: ["balanced", "aggressive", "sniper"],
        4: ["balanced", "aggressive", "sniper", "hoarder"],
    }

    print("=" * 65)
    print("  HOME FIELD VARIANT COMPARISON")
    print(f"  {N} games per variant per player count")
    print("=" * 65)

    for np in [3, 4]:
        styles = style_sets[np]
        fair = 1.0 / np

        print(f"\n{'='*65}")
        print(f"  {np} PLAYERS")
        print(f"{'='*65}")

        for mode, desc in variants:
            print(f"\n▶ {mode}...", end="", flush=True)

            data = run_variant(N, np, styles, config, mode)
            hf_pct, total_wins = run_hf_tracking(N, np, styles, config, mode)

            print(f" done")
            print(f"\n  ── {desc} ──")

            # Style balance
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

            print(f"\n  HF in wins: {hf_pct:.1%}  |  Off-color wins: {1-hf_pct:.1%}")
            print(f"  Style gap: {gap:.1%}  |  Winner VP: {data['avg_winner_score']:.1f}  |  Spread: {data['avg_spread']:.1f}")

            # Grade
            if hf_pct > 0.85:
                hf_grade = "⚠️ HF dominant"
            elif hf_pct > 0.70:
                hf_grade = "👍 HF strong but not mandatory"
            elif hf_pct > 0.50:
                hf_grade = "✅ Balanced HF/off-color"
            else:
                hf_grade = "⚠️ HF too weak"

            if gap <= 0.08:
                bal_grade = "✅ balanced"
            elif gap <= 0.15:
                bal_grade = "👍 acceptable"
            else:
                bal_grade = "⚠️ imbalanced"

            print(f"  Verdict: {hf_grade} / {bal_grade}")

    # ─── SUMMARY ───────────────────────────────────────────────────────
    print(f"\n{'='*65}")
    print("  RECOMMENDATION")
    print(f"{'='*65}")
    print("  Compare HF win% and style gap across variants above.")
    print("  Best variant: lowest HF dominance + tightest style gap.")


if __name__ == "__main__":
    main()
