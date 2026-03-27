#!/usr/bin/env python3
"""
Yomi test: Does reading opponents actually help?

Builds an "adaptive" AI that tracks opponent history and adjusts deployment:
  - Tracks which zones each opponent contested in prior rounds
  - Tracks which colors each opponent has shown strength in
  - Estimates how many cards each opponent has left
  - Avoids zones where strong opponents are likely to deploy
  - Targets zones opponents have historically ignored

If adaptive AI outperforms static styles, reading opponents matters
and the game has meaningful Yomi. If it doesn't, the game is closer
to multiplayer solitaire.

Test matrix:
  1. Adaptive vs 2 balanced (3P) — does reading help at all?
  2. Adaptive vs balanced+aggressive (3P) — mixed opponents
  3. Adaptive vs balanced+aggressive+sniper (4P) — full field
  4. 3× adaptive (3P) — does Yomi self-cancel?
  5. Static baseline for comparison at each player count
"""

import json
import math
import os
import statistics
import sys
from collections import defaultdict
from typing import List, Dict, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cards_v4 import (
    Card, COLORS, COLOR_ORDER,
    CARD_TYPE_NUMBER, CARD_TYPE_MASCOT, CARD_TYPE_ACTION, CARD_TYPE_DUD,
    ACTION_SHIELD, ACTION_BOMB, ACTION_SWAP, ACTION_BOUNTY,
)
from game_state_v4 import GameStateV4
from ai_player_v4 import AIPlayerV4, STYLE_PROFILES


# ─── ADAPTIVE AI ───────────────────────────────────────────────────────────

class AdaptiveAI(AIPlayerV4):
    """
    AI that reads opponent history and adapts deployment.

    Uses base 'balanced' style as foundation, then adjusts zone targeting
    based on what it's observed in prior rounds.
    """

    def __init__(self, player_id, skill=1.0, rng_seed=42):
        super().__init__(player_id, skill=skill, style="balanced", rng_seed=rng_seed)
        self.style_name = "adaptive"

        # Opponent tracking
        self.opponent_zone_history = defaultdict(lambda: defaultdict(int))  # pid -> zone_color -> times_contested
        self.opponent_strength_history = defaultdict(lambda: defaultdict(list))  # pid -> zone_color -> [strengths]
        self.opponent_color_history = defaultdict(lambda: defaultdict(int))  # pid -> card_color -> times_played
        self.opponent_cards_played = defaultdict(int)  # pid -> total cards played
        self.round_history = []  # list of round results

        # Cards we received in pass (tells us about right neighbor)
        self.received_colors = defaultdict(int)

    def observe_pass(self, received_cards: List[Card], from_pid: int):
        """Record what we received in the pass phase."""
        for card in received_cards:
            if card.color:
                self.received_colors[card.color] += 1

    def observe_round(self, game_state, round_num: int):
        """After a round resolves, observe what opponents did."""
        for zone in game_state.zones:
            for pid in zone.active_players:
                if pid == self.player_id:
                    continue
                zp = zone.get_placement(pid)
                if zp.cards:
                    self.opponent_zone_history[pid][zone.color] += 1
                    self.opponent_cards_played[pid] += len(zp.cards)

                    for card in zp.cards:
                        if card.color:
                            self.opponent_color_history[pid][card.color] += 1

    def _score_card_at_zone(self, card, zone_color, vp, zone_counts):
        """Override scoring to factor in opponent history."""
        base_score = super()._score_card_at_zone(card, zone_color, vp, zone_counts)

        if not self.opponent_zone_history:
            return base_score  # No history yet (round 1)

        # ── AVOIDANCE: Penalize zones where strong opponents cluster ──
        opponent_pressure = 0
        for pid, zone_hist in self.opponent_zone_history.items():
            times_at_zone = zone_hist.get(zone_color, 0)
            total_rounds = sum(zone_hist.values()) / max(1, len(zone_hist))
            if total_rounds > 0:
                affinity = times_at_zone / max(1, sum(zone_hist.values()))
                opponent_pressure += affinity

        # ── OPPORTUNITY: Bonus for zones opponents have ignored ──
        total_opponents = len(self.opponent_zone_history)
        if total_opponents > 0:
            avg_pressure = opponent_pressure / total_opponents
            # Low pressure = opportunity, high pressure = danger
            adjustment = (0.5 - avg_pressure) * 6.0  # ±3 points swing
            base_score += adjustment

        # ── COLOR READS: If opponents have been playing a color heavily,
        # they likely have more of it. Avoid zones where their color matches ──
        for pid, color_hist in self.opponent_color_history.items():
            # If opponent plays a lot of one color, they'll likely contest that zone
            total_color_plays = sum(color_hist.values())
            if total_color_plays > 0:
                zone_color_affinity = color_hist.get(zone_color, 0) / total_color_plays
                # Strong color affinity for this zone = they'll probably be here
                if zone_color_affinity > 0.4:
                    base_score -= 1.5

        # ── HAND SIZE READS: If opponent has played a lot of cards,
        # they're thinner for later rounds ──
        current_round = len(self.round_history)
        if current_round >= 2:
            for pid, cards_played in self.opponent_cards_played.items():
                avg_per_round = cards_played / current_round
                # Heavy spender = weaker in future rounds at their typical zones
                if avg_per_round > 3.5:
                    # They've been spending heavily — their contested zones get weaker
                    for zc, times in self.opponent_zone_history[pid].items():
                        if zc == zone_color and times >= 2:
                            base_score += 0.8  # They'll be thinner here

        # ── PASS READS: Colors passed to us suggest right neighbor is weak there ──
        # (less useful since we can't see left neighbor's passes, but still a signal)
        if self.received_colors.get(zone_color, 0) >= 2:
            # Right neighbor gave us this color — they're probably not contesting it
            base_score += 0.5

        return base_score


# ─── GAME RUNNER WITH OBSERVATION ──────────────────────────────────────────

def run_game_with_observation(num_players, seed, ais, config):
    """Run a game where adaptive AIs get to observe each round."""
    game = GameStateV4(num_players, seed=seed, config=config)

    def deployment_fn(player, gs, round_num):
        return ais[player.id].choose_deployment(player, gs, round_num)

    def pass_fn(player, gs, pass_count):
        return ais[player.id].choose_pass(player, gs, pass_count)

    # Card passing — let adaptive AIs observe what they received
    game.execute_pass(pass_fn)

    # Play rounds with observation
    for round_num in range(game.num_rounds):
        game.current_round = round_num

        # Draw condition
        if game.condition_deck:
            game.active_condition = game.condition_deck.pop(0)
            game.stats["condition_cards_drawn"].append(game.active_condition.name)
        else:
            game.active_condition = None

        # Reset round tracking
        for p in game.players:
            p.zones_won_this_round = 0

        # Create fresh zones
        game.zones = [GameStateV4.__dict__  # we need Zone
                      for _ in range(len(game.colors))]
        # Actually, let's use the proper internal method
        # We need to call _play_round but with observation hooks

        # Simpler approach: just run the full round, then observe
        game.zones = []
        for i, c in enumerate(game.colors):
            from game_state_v4 import Zone
            game.zones.append(Zone(color=c, index=i))

        # Deploy
        for player in game.players:
            deploy = deployment_fn(player, game, round_num)
            game._execute_deployment(player, deploy)

        # Resolve actions
        game._resolve_actions()

        # Let adaptive AIs observe BEFORE scoring (they see the board)
        for ai in ais:
            if isinstance(ai, AdaptiveAI):
                ai.observe_round(game, round_num)
                ai.round_history.append(round_num)

        # Score
        zone_strengths = game._calculate_all_strength()
        game.stats["rounds"].append(game._score_round(zone_strengths))

        game.active_condition = None

    game.game_over = True
    return game._compile_final_stats()


# ─── BATCH RUNNER ──────────────────────────────────────────────────────────

def run_scenario(name, num_games, num_players, ai_factory, config):
    """Run a scenario and return style-level win rates."""
    style_wins = defaultdict(float)
    style_games = defaultdict(int)
    style_scores = defaultdict(list)

    for i in range(num_games):
        seed = 1 + i
        ais = ai_factory(seed, num_players)

        result = run_game_with_observation(num_players, seed, ais, config)
        winner = result["winner"]

        styles = [ai.style_name for ai in ais]

        if isinstance(winner, list):
            for w in winner:
                style_wins[styles[w]] += 1.0 / len(winner)
        else:
            style_wins[styles[winner]] += 1

        for pid in range(num_players):
            style_scores[styles[pid]].append(result["scores"][pid])
            style_games[styles[pid]] += 1

    return {
        "win_rates": {s: style_wins[s] / style_games[s]
                      if style_games[s] > 0 else 0
                      for s in style_games},
        "avg_vp": {s: statistics.mean(style_scores[s])
                   if style_scores[s] else 0
                   for s in style_games},
        "total_games": num_games,
    }


def print_scenario(label, desc, data, num_players):
    print(f"\n{'─'*60}")
    print(f"  {label}: {desc}")
    print(f"  {data['total_games']} games × {num_players}P")
    print(f"{'─'*60}")

    fair = 1.0 / num_players
    styles = sorted(data["win_rates"].keys(), key=lambda s: -data["win_rates"][s])

    print(f"  {'Style':<14} {'Win%':>7} {'Δ':>7} {'Avg VP':>8}")
    for s in styles:
        wr = data["win_rates"][s]
        delta = wr - fair
        vp = data["avg_vp"][s]
        flag = " ⚠️" if s == "adaptive" and delta > 0.03 else ""
        flag = " 🎯" if s == "adaptive" and delta > 0.05 else flag
        print(f"  {s:<14} {wr:6.1%} {delta:+6.1%} {vp:7.1f}{flag}")

    return data["win_rates"].get("adaptive", 0)


# ─── MAIN ──────────────────────────────────────────────────────────────────

def main():
    N = 2000
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config_v4.json")
    with open(config_path) as f:
        config = json.load(f)

    print("=" * 60)
    print("  YOMI TEST — Does Reading Opponents Help?")
    print(f"  {N} games per scenario")
    print("=" * 60)

    results = {}

    # ── 1: Baseline 3P (no adaptive) ──
    print("\n▶ Running: Baseline 3P (balanced × 3)...", end="", flush=True)
    data = run_scenario("baseline_3p", N, 3,
        lambda seed, np: [AIPlayerV4(pid, skill=1.0, style="balanced",
                                      rng_seed=seed*100+pid) for pid in range(np)],
        config)
    print(" done")
    print_scenario("1", "BASELINE 3P (balanced × 3)", data, 3)
    results["baseline_3p"] = data

    # ── 2: Adaptive vs 2 balanced (3P) ──
    print("\n▶ Running: Adaptive vs 2 balanced (3P)...", end="", flush=True)
    data = run_scenario("adapt_vs_bal_3p", N, 3,
        lambda seed, np: [AdaptiveAI(0, rng_seed=seed*100),
                          AIPlayerV4(1, skill=1.0, style="balanced", rng_seed=seed*100+1),
                          AIPlayerV4(2, skill=1.0, style="balanced", rng_seed=seed*100+2)],
        config)
    print(" done")
    wr2 = print_scenario("2", "ADAPTIVE vs balanced × 2 (3P)", data, 3)
    results["adapt_vs_bal"] = data

    # ── 3: Adaptive vs balanced + aggressive (3P) ──
    print("\n▶ Running: Adaptive vs balanced + aggressive (3P)...", end="", flush=True)
    data = run_scenario("adapt_vs_mix_3p", N, 3,
        lambda seed, np: [AdaptiveAI(0, rng_seed=seed*100),
                          AIPlayerV4(1, skill=1.0, style="balanced", rng_seed=seed*100+1),
                          AIPlayerV4(2, skill=1.0, style="aggressive", rng_seed=seed*100+2)],
        config)
    print(" done")
    wr3 = print_scenario("3", "ADAPTIVE vs balanced + aggressive (3P)", data, 3)
    results["adapt_vs_mix"] = data

    # ── 4: Adaptive vs balanced + sniper (3P) — hardest opponents ──
    print("\n▶ Running: Adaptive vs balanced + sniper (3P)...", end="", flush=True)
    data = run_scenario("adapt_vs_sniper_3p", N, 3,
        lambda seed, np: [AdaptiveAI(0, rng_seed=seed*100),
                          AIPlayerV4(1, skill=1.0, style="balanced", rng_seed=seed*100+1),
                          AIPlayerV4(2, skill=1.0, style="sniper", rng_seed=seed*100+2)],
        config)
    print(" done")
    wr4 = print_scenario("4", "ADAPTIVE vs balanced + sniper (3P)", data, 3)
    results["adapt_vs_sniper"] = data

    # ── 5: Adaptive vs 3 others (4P) ──
    print("\n▶ Running: Adaptive vs bal+agg+sniper (4P)...", end="", flush=True)
    data = run_scenario("adapt_4p", N, 4,
        lambda seed, np: [AdaptiveAI(0, rng_seed=seed*100),
                          AIPlayerV4(1, skill=1.0, style="balanced", rng_seed=seed*100+1),
                          AIPlayerV4(2, skill=1.0, style="aggressive", rng_seed=seed*100+2),
                          AIPlayerV4(3, skill=1.0, style="sniper", rng_seed=seed*100+3)],
        config)
    print(" done")
    wr5 = print_scenario("5", "ADAPTIVE vs bal+agg+sniper (4P)", data, 4)
    results["adapt_4p"] = data

    # ── 6: All adaptive (3P) — does Yomi cancel out? ──
    print("\n▶ Running: All adaptive × 3 (3P)...", end="", flush=True)
    data = run_scenario("all_adapt_3p", N, 3,
        lambda seed, np: [AdaptiveAI(pid, rng_seed=seed*100+pid) for pid in range(np)],
        config)
    print(" done")
    print_scenario("6", "ALL ADAPTIVE × 3 (self-cancellation test)", data, 3)
    results["all_adapt"] = data

    # ── 7: Adaptive vs 4 others (5P) ──
    print("\n▶ Running: Adaptive vs 4 others (5P)...", end="", flush=True)
    data = run_scenario("adapt_5p", N, 5,
        lambda seed, np: [AdaptiveAI(0, rng_seed=seed*100),
                          AIPlayerV4(1, skill=1.0, style="balanced", rng_seed=seed*100+1),
                          AIPlayerV4(2, skill=1.0, style="aggressive", rng_seed=seed*100+2),
                          AIPlayerV4(3, skill=1.0, style="sniper", rng_seed=seed*100+3),
                          AIPlayerV4(4, skill=1.0, style="hoarder", rng_seed=seed*100+4)],
        config)
    print(" done")
    wr7 = print_scenario("7", "ADAPTIVE vs bal+agg+sniper+hoarder (5P)", data, 5)
    results["adapt_5p"] = data

    # ─── VERDICT ───────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("  VERDICT: DOES YOMI MATTER?")
    print(f"{'='*60}")

    adaptive_wrs = []
    comparisons = [
        ("vs balanced×2 (3P)", wr2, 1/3),
        ("vs bal+agg (3P)", wr3, 1/3),
        ("vs bal+sniper (3P)", wr4, 1/3),
        ("vs bal+agg+sniper (4P)", wr5, 1/4),
        ("vs 4 styles (5P)", wr7, 1/5),
    ]

    print(f"\n  {'Matchup':<30} {'Adaptive':>9} {'Fair':>6} {'Edge':>7}")
    for label, wr, fair in comparisons:
        edge = wr - fair
        marker = "🎯" if edge > 0.05 else ("✅" if edge > 0.02 else "—")
        print(f"  {label:<30} {wr:>8.1%} {fair:>5.1%} {edge:>+6.1%} {marker}")
        adaptive_wrs.append(wr - fair)

    avg_edge = statistics.mean(adaptive_wrs)
    print(f"\n  Average adaptive edge: {avg_edge:+.1%}")

    if avg_edge > 0.05:
        print("  📊 STRONG YOMI: Reading opponents provides a clear advantage.")
        print("     The game rewards paying attention to what others do.")
    elif avg_edge > 0.02:
        print("  📊 MODERATE YOMI: Reading opponents helps, but isn't dominant.")
        print("     The game rewards attention but doesn't punish casual play severely.")
    elif avg_edge > 0.00:
        print("  📊 WEAK YOMI: Marginal benefit to reading opponents.")
        print("     Information is there but hard to exploit meaningfully.")
    else:
        print("  📊 NO YOMI: Reading opponents doesn't help.")
        print("     The game is effectively multiplayer solitaire.")


if __name__ == "__main__":
    main()
