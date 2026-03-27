#!/usr/bin/env python3
"""
Compare balance fix candidates for sniper-at-3P and spread-at-5P.

Scenarios tested:
  A. BASELINE      — current v0.1.3 rules, rotating styles
  B. SELF-CORRECT  — all-sniper at 3P (does sniper counter itself?)
  C. 3 ZONES @ 3P  — reduce zones from 4→3 at 3 players
  D. 2ND-PLACE VP  — 1 VP for runner-up at each zone
  E. PRESENCE VP   — 1 VP per zone you have any cards at

Each scenario runs 2000 games at the relevant player count(s).
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

from cards_v4 import Card
from game_state_v4 import GameStateV4, Zone
from ai_player_v4 import AIPlayerV4, STYLE_PROFILES


# ─── PATCHED GAME STATE ────────────────────────────────────────────────────

class PatchedGameStateV4(GameStateV4):
    """
    Extended game state that supports experimental scoring rules.
    """

    def __init__(self, num_players, seed=42, config=None,
                 second_place_vp=0, presence_vp=0, num_zones_override=None):
        # If overriding zone count, patch config before super().__init__
        if num_zones_override and config:
            config = copy.deepcopy(config)
            colors = config["game_rules"]["colors"][:num_zones_override]
            config["game_rules"]["colors"] = colors
            config["game_rules"]["num_zones"] = num_zones_override

        super().__init__(num_players, seed=seed, config=config)
        self.second_place_vp = second_place_vp
        self.presence_vp = presence_vp

    def _score_round(self, zone_strengths):
        """Override scoring to add second-place and presence VP."""
        # Run base scoring first
        round_stats = super()._score_round(zone_strengths)

        # ── SECOND-PLACE VP ──
        if self.second_place_vp > 0:
            for zone in self.zones:
                strength_map = zone_strengths.get(zone.color, {})
                if len(strength_map) < 2:
                    continue

                # Find winner(s) and runner-up(s)
                sorted_strengths = sorted(strength_map.values(), reverse=True)
                top = sorted_strengths[0]
                winners = [pid for pid, s in strength_map.items() if s == top]

                # If it's a tie for first, no second place
                if len(winners) > 1:
                    continue

                # Second-best strength
                second = sorted_strengths[1]
                if second <= 0:
                    continue

                runners_up = [pid for pid, s in strength_map.items()
                              if s == second and pid not in winners]
                for pid in runners_up:
                    self.players[pid].score += self.second_place_vp
                    round_stats["vp_awarded"][pid] += self.second_place_vp

        # ── PRESENCE VP ──
        if self.presence_vp > 0:
            for player in self.players:
                zones_present = 0
                for zone in self.zones:
                    zp = zone.get_placement(player.id)
                    if zp.cards:
                        zones_present += 1
                bonus = zones_present * self.presence_vp
                if bonus > 0:
                    player.score += bonus
                    round_stats["vp_awarded"][player.id] += bonus

        return round_stats


# ─── SIMULATION HELPERS ────────────────────────────────────────────────────

def load_config():
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "config_v4.json")
    with open(config_path) as f:
        return json.load(f)


def run_games(num_games, num_players, styles, config,
              second_place_vp=0, presence_vp=0, num_zones_override=None):
    """Run batch of games with optional experimental rules."""
    style_wins = defaultdict(float)
    style_scores = defaultdict(list)
    style_zones_won = defaultdict(list)
    style_games = defaultdict(int)
    all_winner_scores = []
    all_spreads = []
    per_round_vp = defaultdict(lambda: defaultdict(list))  # style -> round -> [vp]

    for i in range(num_games):
        seed = 5000 + i
        game_styles = [styles[(i + j) % len(styles)] for j in range(num_players)]

        game = PatchedGameStateV4(
            num_players, seed=seed, config=config,
            second_place_vp=second_place_vp,
            presence_vp=presence_vp,
            num_zones_override=num_zones_override,
        )

        ais = [AIPlayerV4(pid, skill=1.0, style=game_styles[pid],
                           rng_seed=seed * 100 + pid)
               for pid in range(num_players)]

        def deployment_fn(player, gs, round_num):
            return ais[player.id].choose_deployment(player, gs, round_num)

        def pass_fn(player, gs, pass_count):
            return ais[player.id].choose_pass(player, gs, pass_count)

        result = game.play_game(deployment_fn, pass_fn)
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
            style_zones_won[game_styles[pid]].append(result["zones_won"][pid])
            style_games[game_styles[pid]] += 1

    return {
        "win_rates": {s: style_wins[s] / style_games[s]
                      if style_games[s] > 0 else 0
                      for s in set(styles)},
        "avg_vp": {s: statistics.mean(style_scores[s])
                   if style_scores[s] else 0
                   for s in set(styles)},
        "avg_zones": {s: statistics.mean(style_zones_won[s])
                      if style_zones_won[s] else 0
                      for s in set(styles)},
        "avg_winner_score": statistics.mean(all_winner_scores),
        "avg_spread": statistics.mean(all_spreads),
        "total_games": num_games,
    }


def print_scenario(label, desc, data, expected_wr, player_count):
    print(f"\n{'─'*60}")
    print(f"  {label}: {desc}")
    print(f"  {data['total_games']} games × {player_count}P")
    print(f"{'─'*60}")

    styles_sorted = sorted(data["win_rates"].keys(),
                           key=lambda s: -data["win_rates"][s])
    fair = 1.0 / player_count

    print(f"  {'Style':<12} {'Win%':>7} {'Δ':>7} {'Avg VP':>8} {'Zones':>7}")
    for s in styles_sorted:
        wr = data["win_rates"][s]
        delta = wr - fair
        vp = data["avg_vp"][s]
        zones = data["avg_zones"][s]
        flag = " ⚠️" if abs(delta) > 0.08 else ""
        print(f"  {s:<12} {wr:6.1%} {delta:+6.1%} {vp:7.1f} {zones:6.1f}{flag}")

    max_wr = max(data["win_rates"].values())
    min_wr = min(data["win_rates"].values())
    gap = max_wr - min_wr
    print(f"\n  Style gap: {gap:.1%}  |  Avg winner: {data['avg_winner_score']:.1f} VP  |  Spread: {data['avg_spread']:.1f}")

    return gap


# ─── MAIN ──────────────────────────────────────────────────────────────────

def main():
    N = 2000
    config = load_config()

    print("=" * 60)
    print("  BALANCE FIX COMPARISON — Sniper@3P & Spread@5P")
    print(f"  {N} games per scenario")
    print("=" * 60)

    results = {}

    # ── A: BASELINE 3P ──
    print("\n▶ Running A: Baseline 3P...", end="", flush=True)
    styles_3p = ["balanced", "aggressive", "sniper"]
    data = run_games(N, 3, styles_3p, config)
    print(" done")
    gap = print_scenario("A", "BASELINE 3P (current rules)", data, 0.333, 3)
    results["A_baseline_3p"] = {"gap": gap, "data": data}

    # ── B: SELF-CORRECTION (all sniper 3P) ──
    print("\n▶ Running B: All-Sniper 3P...", end="", flush=True)
    styles_all_sniper = ["sniper", "sniper", "sniper"]
    data = run_games(N, 3, styles_all_sniper, config)
    print(" done")
    gap = print_scenario("B", "ALL-SNIPER 3P (self-correction test)", data, 0.333, 3)
    results["B_self_correct"] = {"gap": gap, "data": data}

    # ── C: 3 ZONES AT 3P ──
    print("\n▶ Running C: 3 Zones at 3P...", end="", flush=True)
    data = run_games(N, 3, styles_3p, config, num_zones_override=3)
    print(" done")
    gap = print_scenario("C", "3 ZONES @ 3P (fewer uncontested zones)", data, 0.333, 3)
    results["C_3zones_3p"] = {"gap": gap, "data": data}

    # ── D: BASELINE 5P ──
    print("\n▶ Running D: Baseline 5P...", end="", flush=True)
    styles_5p = ["balanced", "aggressive", "sniper", "hoarder", "spread"]
    data = run_games(N, 5, styles_5p, config)
    print(" done")
    gap = print_scenario("D", "BASELINE 5P (current rules)", data, 0.200, 5)
    results["D_baseline_5p"] = {"gap": gap, "data": data}

    # ── E: 2ND-PLACE VP at 5P ──
    print("\n▶ Running E: 2nd-Place VP at 5P...", end="", flush=True)
    data = run_games(N, 5, styles_5p, config, second_place_vp=1)
    print(" done")
    gap = print_scenario("E", "2ND-PLACE VP (1 VP for runner-up) @ 5P", data, 0.200, 5)
    results["E_2nd_place_5p"] = {"gap": gap, "data": data}

    # ── F: PRESENCE VP at 5P ──
    print("\n▶ Running F: Presence VP at 5P...", end="", flush=True)
    data = run_games(N, 5, styles_5p, config, presence_vp=1)
    print(" done")
    gap = print_scenario("F", "PRESENCE VP (1 VP per zone present) @ 5P", data, 0.200, 5)
    results["F_presence_5p"] = {"gap": gap, "data": data}

    # ── G: 2ND-PLACE VP at 3P (does it hurt sniper?) ──
    print("\n▶ Running G: 2nd-Place VP at 3P...", end="", flush=True)
    data = run_games(N, 3, styles_3p, config, second_place_vp=1)
    print(" done")
    gap = print_scenario("G", "2ND-PLACE VP (1 VP for runner-up) @ 3P", data, 0.333, 3)
    results["G_2nd_place_3p"] = {"gap": gap, "data": data}

    # ── H: PRESENCE VP at 3P ──
    print("\n▶ Running H: Presence VP at 3P...", end="", flush=True)
    data = run_games(N, 3, styles_3p, config, presence_vp=1)
    print(" done")
    gap = print_scenario("H", "PRESENCE VP (1 VP per zone present) @ 3P", data, 0.333, 3)
    results["H_presence_3p"] = {"gap": gap, "data": data}

    # ── I: 3 ZONES + 2ND-PLACE VP at 3P (combo) ──
    print("\n▶ Running I: 3 Zones + 2nd-Place VP at 3P...", end="", flush=True)
    data = run_games(N, 3, styles_3p, config,
                     second_place_vp=1, num_zones_override=3)
    print(" done")
    gap = print_scenario("I", "3 ZONES + 2ND-PLACE VP @ 3P (combo)", data, 0.333, 3)
    results["I_combo_3p"] = {"gap": gap, "data": data}

    # ── J: CROSS-CHECK — does the 5P fix break 3P? ──
    # Test best 5P fix at 3P, and best 3P fix at 5P
    print("\n▶ Running J: 3 Zones at 5P (cross-check)...", end="", flush=True)
    # 3 zones at 5P would be very crowded — skip if silly
    # Instead: check if 2nd-place VP at 4P stays balanced
    styles_4p = ["balanced", "aggressive", "sniper", "hoarder"]
    data = run_games(N, 4, styles_4p, config, second_place_vp=1)
    print(" done")
    gap = print_scenario("J", "2ND-PLACE VP @ 4P (cross-check)", data, 0.250, 4)
    results["J_2nd_place_4p"] = {"gap": gap, "data": data}

    # ─── SUMMARY ───────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  SUMMARY — Style Gap by Scenario")
    print("=" * 60)
    print(f"  {'Scenario':<42} {'Gap':>7} {'Verdict':>10}")
    print(f"  {'─'*42} {'─'*7} {'─'*10}")

    for key, val in sorted(results.items()):
        gap = val["gap"]
        # Determine verdict
        if gap <= 0.08:
            verdict = "✅ GREAT"
        elif gap <= 0.12:
            verdict = "👍 GOOD"
        elif gap <= 0.20:
            verdict = "⚠️  MEH"
        else:
            verdict = "❌ BAD"

        label = key.split("_", 1)[1].replace("_", " ").title()
        print(f"  {key}: {label:<38} {gap:6.1%} {verdict}")


if __name__ == "__main__":
    main()
