#!/usr/bin/env python3
"""
Compare different color counts (3-6) for the family game version.

Measures things that matter for a family game:
  1. Zone contestation — how many zones have 2+ players competing?
  2. Condition card viability — if we restrict "no red" or "only even",
     does a player get stuck with nothing playable?
  3. Scoring complexity — how many comparisons per round?
  4. Hand composition — how many cards per color do you typically hold?
  5. Balance — seat fairness and score spreads.

Usage:
  python compare_colors.py
  python compare_colors.py -n 1000
"""

import argparse
import statistics
import sys
import os
from collections import defaultdict, Counter
from typing import List, Dict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cards import Card, build_full_deck
from game_state_v3 import GameStateV3, DeckConfig
from ai_player_v3 import AIPlayerV3, STYLE_PROFILES

# ─── COLOR PALETTES ──────────────────────────────────────────────────────────

PALETTES = {
    3: ["RED", "BLUE", "YELLOW"],
    4: ["RED", "BLUE", "YELLOW", "GREEN"],
    5: ["RED", "BLUE", "YELLOW", "GREEN", "PURPLE"],
    6: ["RED", "ORANGE", "YELLOW", "GREEN", "BLUE", "PURPLE"],
}

# ─── CANDIDATE CONFIGURATIONS ────────────────────────────────────────────────
# For each color count, test 2 rank distributions:
#   "flat" = one of each rank (like current game)
#   "tuned" = a distribution designed for that color count

def build_configs():
    configs = {}

    # 3 colors
    # Flat: 3 × [0-10] = 33 cards (too few for 4-5P)
    # Tuned: 3 × 15 cards each = 45 cards
    configs["3c_flat"] = DeckConfig(
        label="3 colors × 0-10 (33)",
        factions=PALETTES[3],
        ranks_per_faction=list(range(0, 11)),
    )
    configs["3c_tuned"] = DeckConfig(
        label="3 colors × 15 (45)",
        factions=PALETTES[3],
        ranks_per_faction=[0, 1, 1, 2, 2, 3, 3, 4, 5, 5, 6, 7, 7, 8, 9],
    )

    # 4 colors
    # Flat: 4 × [0-10] = 44 cards
    # Tuned: 4 × [0-9] = 40, or 4 × 12 = 48
    configs["4c_flat"] = DeckConfig(
        label="4 colors × 0-10 (44)",
        factions=PALETTES[4],
        ranks_per_faction=list(range(0, 11)),
    )
    configs["4c_tuned"] = DeckConfig(
        label="4 colors × 12 (48)",
        factions=PALETTES[4],
        ranks_per_faction=[0, 1, 2, 3, 3, 4, 5, 5, 6, 7, 8, 9],
    )

    # 5 colors
    configs["5c_flat"] = DeckConfig(
        label="5 colors × 0-10 (55)",
        factions=PALETTES[5],
        ranks_per_faction=list(range(0, 11)),
    )
    configs["5c_tuned"] = DeckConfig(
        label="5 colors × 11 (55)",
        factions=PALETTES[5],
        ranks_per_faction=[0, 1, 2, 3, 4, 4, 5, 6, 7, 8, 9],
    )

    # 6 colors (current)
    configs["6c_flat"] = DeckConfig(
        label="6 colors × 0-10 (66)",
        factions=PALETTES[6],
        ranks_per_faction=list(range(0, 11)),
    )

    return configs


# ─── CONDITION CARD VIABILITY ─────────────────────────────────────────────────

def simulate_condition_viability(deck_config: DeckConfig, num_players: int,
                                  num_trials: int = 2000, seed: int = 1):
    """
    Simulate dealing hands and check what fraction of the time
    various condition restrictions leave a player with <2 playable cards.

    Conditions tested:
      - "No [color]" for each color
      - "Only even ranks"
      - "Only odd ranks"
      - "Max rank 5" (only cards rank ≤ 5)
      - "Min rank 4" (only cards rank ≥ 4)
    """
    import random
    rng = random.Random(seed)

    factions = deck_config.factions
    ranks = deck_config.ranks_per_faction
    total = deck_config.total_cards

    # Hand size
    if total != 66:
        hand_size = int(total * 0.70 / num_players)
    else:
        hand_size = {2: 18, 3: 15, 4: 13, 5: 11}[num_players]

    # Per-round hand size (rough: hand / 3 rounds)
    per_round = max(3, hand_size // 3)

    conditions = {}

    # Color lockout conditions
    for f in factions:
        conditions[f"no_{f.lower()}"] = lambda cards, f=f: [c for c in cards if c.faction != f]

    # Even/odd
    conditions["only_even"] = lambda cards: [c for c in cards if c.rank % 2 == 0]
    conditions["only_odd"] = lambda cards: [c for c in cards if c.rank % 2 == 1]

    # Rank caps
    max_rank = max(ranks)
    mid = max_rank // 2
    conditions[f"max_rank_{mid}"] = lambda cards, m=mid: [c for c in cards if c.rank <= m]
    conditions[f"min_rank_{mid}"] = lambda cards, m=mid: [c for c in cards if c.rank >= m]

    # Track: fraction of times a player has < 2 playable cards for each condition
    stuck_counts = {name: 0 for name in conditions}
    severely_stuck = {name: 0 for name in conditions}  # 0 playable cards
    total_checks = 0

    for t in range(num_trials):
        deck = build_full_deck(factions=factions, ranks_per_faction=ranks)
        rng.shuffle(deck)
        for p in range(num_players):
            hand = deck[p * hand_size:(p + 1) * hand_size]
            # Simulate having ~per_round cards available in a given round
            round_hand = hand[:per_round]
            total_checks += 1

            for name, filter_fn in conditions.items():
                playable = filter_fn(round_hand)
                if len(playable) < 2:
                    stuck_counts[name] += 1
                if len(playable) == 0:
                    severely_stuck[name] += 1

    return {
        name: {
            "stuck_rate": stuck_counts[name] / total_checks,
            "zero_rate": severely_stuck[name] / total_checks,
        }
        for name in conditions
    }


# ─── ZONE CONTESTATION ───────────────────────────────────────────────────────

def run_games_with_contestation(deck_config: DeckConfig, num_games: int,
                                 num_players: int, start_seed: int = 1):
    """Run games and measure zone contestation and other family-game metrics."""
    contested_zones = []  # per round: how many zones had 2+ players
    empty_zones = []      # per round: how many zones had 0 players
    solo_zones = []       # per round: how many zones had exactly 1 player (free VP)
    all_scores = defaultdict(list)
    score_spreads = []
    wins = defaultdict(float)
    total_comparisons = []  # how many strength comparisons per round
    hf_total = 0
    mascot_total = 0
    hand_color_counts = []  # how many cards per color in starting hand

    styles = ["balanced"] * num_players

    for i in range(num_games):
        seed = start_seed + i
        game = GameStateV3(num_players, seed=seed, deck_config=deck_config)

        # Record hand composition for first game set
        if i < 200:
            for p in game.players:
                color_counts = Counter(c.faction for c in p.hand)
                for f in deck_config.factions:
                    hand_color_counts.append(color_counts.get(f, 0))

        ais = [AIPlayerV3(pid, skill=1.0, style="balanced", rng_seed=seed * 100 + pid)
               for pid in range(num_players)]

        def deployment_fn(player, gs, round_num):
            return ais[player.id].choose_deployment(player, gs, round_num)

        result = game.play_game(deployment_fn)

        # Analyze rounds for contestation
        for round_stats in game.stats["rounds"]:
            sz = round_stats["strength_by_zone"]
            contested = 0
            empty = 0
            solo = 0
            comparisons = 0
            for faction, strength_map in sz.items():
                n_players = len([s for s in strength_map.values() if s > 0])
                if n_players >= 2:
                    contested += 1
                    comparisons += n_players
                elif n_players == 1:
                    solo += 1
                    comparisons += 1
                else:
                    empty += 1
            contested_zones.append(contested)
            empty_zones.append(empty)
            solo_zones.append(solo)
            total_comparisons.append(comparisons)

        # Standard metrics
        winner = result["winner"]
        if isinstance(winner, list):
            for w in winner:
                wins[w] += 1.0 / len(winner)
        else:
            wins[winner] += 1

        scores = list(result["scores"].values())
        for pid, s in result["scores"].items():
            all_scores[pid].append(s)
        score_spreads.append(max(scores) - min(scores))

        hf_total += result.get("home_field_triggers", 0)
        mascot_total += result.get("mascot_combos", 0)

    n = num_games
    fair = 1.0 / num_players
    win_rates = {pid: wins[pid] / n for pid in range(num_players)}

    return {
        "label": deck_config.label,
        "num_colors": len(deck_config.factions),
        "total_cards": deck_config.total_cards,
        "hand_size": int(deck_config.total_cards * 0.70 / num_players)
            if deck_config.total_cards != 66
            else {2: 18, 3: 15, 4: 13, 5: 11}[num_players],
        "cards_per_color_avg": statistics.mean(hand_color_counts) if hand_color_counts else 0,
        "cards_per_color_std": statistics.stdev(hand_color_counts) if len(hand_color_counts) > 1 else 0,
        "contested_zones_avg": statistics.mean(contested_zones),
        "empty_zones_avg": statistics.mean(empty_zones),
        "solo_zones_avg": statistics.mean(solo_zones),
        "comparisons_per_round": statistics.mean(total_comparisons),
        "max_seat_deviation": max(abs(wr - fair) for wr in win_rates.values()),
        "avg_score": statistics.mean([s for scores in all_scores.values() for s in scores]),
        "avg_score_spread": statistics.mean(score_spreads),
        "hf_per_game": hf_total / n,
        "mascot_per_game": mascot_total / n,
    }


# ─── REPORTING ───────────────────────────────────────────────────────────────

def print_report(all_results: Dict[int, List[Dict]], condition_results: Dict):
    """Print results organized by player count."""

    for num_players in sorted(all_results.keys()):
        results = all_results[num_players]
        print(f"\n{'='*85}")
        print(f"  {num_players} PLAYERS")
        print(f"{'='*85}")

        header = f"{'Metric':<30}"
        for r in results:
            short = f"{r['num_colors']}c"
            if "tuned" in r.get("tag", ""):
                short += "(t)"
            else:
                short += "(f)"
            header += f"  {short:>10}"
        print(f"\n{header}")
        print("-" * (30 + 12 * len(results)))

        def row(label, key, fmt=".1f"):
            line = f"{label:<30}"
            for r in results:
                val = r[key]
                line += f"  {val:>10{fmt}}"
            print(line)

        def row_custom(label, values):
            line = f"{label:<30}"
            for v in values:
                line += f"  {v:>10}"
            print(line)

        row_custom("Deck size", [str(r["total_cards"]) for r in results])
        row_custom("Hand size", [str(r["hand_size"]) for r in results])
        row("Cards per color (avg)", "cards_per_color_avg", ".1f")
        row("Cards per color (std)", "cards_per_color_std", ".1f")
        print()

        print("--- ZONE ACTIVITY (per round) ---")
        row("Contested zones (2+ players)", "contested_zones_avg", ".1f")
        row("Solo zones (free VP)", "solo_zones_avg", ".1f")
        row("Empty zones", "empty_zones_avg", ".1f")
        row("Scoring comparisons", "comparisons_per_round", ".1f")
        print()

        print("--- BALANCE ---")
        row("Max seat deviation", "max_seat_deviation", ".1%")
        row("Avg score spread", "avg_score_spread", ".1f")
        print()

        print("--- FEATURES ---")
        row("Home Field / game", "hf_per_game", ".1f")
        row("Mascot combos / game", "mascot_per_game", ".1f")

    # Condition viability (3P only for readability)
    print(f"\n{'='*85}")
    print(f"  CONDITION CARD VIABILITY (3 players)")
    print(f"  'stuck' = fewer than 2 playable cards, 'zero' = no playable cards")
    print(f"{'='*85}")

    # Get all condition names from first result
    all_conditions = set()
    for key, conds in condition_results.items():
        all_conditions.update(conds.keys())

    sorted_conds = sorted(all_conditions)
    config_keys = sorted(condition_results.keys())

    header = f"{'Condition':<25}"
    for key in config_keys:
        header += f"  {key:>12}"
    print(f"\n{header}")
    print("-" * (25 + 14 * len(config_keys)))

    for cond in sorted_conds:
        line = f"{cond:<25}"
        for key in config_keys:
            data = condition_results[key].get(cond, {})
            stuck = data.get("stuck_rate", 0)
            zero = data.get("zero_rate", 0)
            line += f"  {stuck:>5.0%}/{zero:<5.0%}"
        print(line)

    print("\n  (format: stuck_rate / zero_rate)")
    print(f"  Target: stuck < 20%, zero < 5% for any condition")


# ─── MAIN ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Compare color counts for TTW")
    parser.add_argument("-n", "--num-games", type=int, default=1000,
                        help="Games per configuration (default: 1000)")
    args = parser.parse_args()

    configs = build_configs()
    player_counts = [2, 3, 4, 5]

    all_results = {p: [] for p in player_counts}
    condition_results = {}

    print(f"Testing {len(configs)} configurations × {len(player_counts)} player counts "
          f"× {args.num_games} games each...\n")

    for key in sorted(configs.keys()):
        dc = configs[key]
        print(f"  {key}: {dc.label}")

        for num_players in player_counts:
            # Skip configs that can't support this player count
            max_possible_hand = dc.total_cards // num_players
            if max_possible_hand < 6:
                print(f"    {num_players}P: skipped (deck too small)")
                r = {
                    "label": dc.label, "tag": key,
                    "num_colors": len(dc.factions),
                    "total_cards": dc.total_cards,
                    "hand_size": 0, "cards_per_color_avg": 0,
                    "cards_per_color_std": 0,
                    "contested_zones_avg": 0, "empty_zones_avg": 0,
                    "solo_zones_avg": 0, "comparisons_per_round": 0,
                    "max_seat_deviation": 0, "avg_score": 0,
                    "avg_score_spread": 0, "hf_per_game": 0,
                    "mascot_per_game": 0,
                }
                all_results[num_players].append(r)
                continue

            r = run_games_with_contestation(dc, args.num_games, num_players)
            r["tag"] = key
            all_results[num_players].append(r)
            print(f"    {num_players}P: contested={r['contested_zones_avg']:.1f}/"
                  f"{len(dc.factions)} zones, spread={r['avg_score_spread']:.1f}")

        # Condition viability at 3P
        print(f"    Condition viability...", end="", flush=True)
        cv = simulate_condition_viability(dc, num_players=3)
        condition_results[key] = cv
        worst = max(cv.values(), key=lambda x: x["stuck_rate"])
        print(f" worst stuck rate: {worst['stuck_rate']:.0%}")

    print_report(all_results, condition_results)


if __name__ == "__main__":
    main()
