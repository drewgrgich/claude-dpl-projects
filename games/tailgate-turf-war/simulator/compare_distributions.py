#!/usr/bin/env python3
"""
Compare different card rank distributions for Tailgate Turf War.

Runs full game simulations under each candidate distribution and produces
a side-by-side comparison of gameplay-relevant metrics:
  - Win rate balance (seat fairness)
  - Score spread (blowout vs. close games)
  - Strength distribution (granularity of zone contests)
  - Home Field trigger rate
  - Mascot combo rate & ceiling
  - Strategy diversity (does any style dominate?)
  - Cards-per-zone distribution (stacking behavior)

Usage:
  python compare_distributions.py
  python compare_distributions.py -n 2000
  python compare_distributions.py -n 1000 --players 4
"""

import argparse
import statistics
import sys
import os
from collections import defaultdict
from typing import List, Dict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cards import Card, FACTIONS, build_full_deck
from game_state_v3 import GameStateV3, DeckConfig
from ai_player_v3 import AIPlayerV3, STYLE_PROFILES

# ─── CANDIDATE DISTRIBUTIONS ─────────────────────────────────────────────────

DISTRIBUTIONS = {
    "A_current": DeckConfig(
        label="Current (6×[0-10], 66 cards)",
        factions=list(FACTIONS),
        ranks_per_faction=list(range(0, 11)),
    ),

    "B_compressed": DeckConfig(
        label="Compressed (6×[0-8], 54 cards)",
        factions=list(FACTIONS),
        ranks_per_faction=[0, 1, 2, 3, 4, 5, 6, 7, 8],
    ),

    "C_triangle": DeckConfig(
        label="Triangle (6×[1,1,2,2,3,3,4,5,6,7,0], 66 cards)",
        factions=list(FACTIONS),
        ranks_per_faction=[0, 1, 1, 2, 2, 3, 3, 4, 5, 6, 7],
    ),

    "D_power5": DeckConfig(
        label="Power-5 (5×[0,1,1,2,2,3,3,4,4,5,6,7,8], 65 cards)",
        factions=["RED", "ORANGE", "YELLOW", "GREEN", "BLUE"],
        ranks_per_faction=[0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 6, 7, 8],
    ),

    "E_steep": DeckConfig(
        label="Steep (6×[0,1,1,1,2,2,3,4,5,9], 60 cards)",
        factions=list(FACTIONS),
        ranks_per_faction=[0, 1, 1, 1, 2, 2, 3, 4, 5, 9],
    ),

    "F_bellcurve6": DeckConfig(
        label="Bell Curve (6×[0,2,3,4,4,5,5,6,6,7,8], 66 cards)",
        factions=list(FACTIONS),
        ranks_per_faction=[0, 2, 3, 4, 4, 5, 5, 6, 6, 7, 8],
    ),
}


# ─── SIMULATION ENGINE ───────────────────────────────────────────────────────

def run_games(deck_config: DeckConfig, num_games: int, num_players: int,
              player_styles: List[str], start_seed: int = 1) -> Dict:
    """Run a batch of games and collect detailed stats."""
    all_results = []

    for i in range(num_games):
        seed = start_seed + i
        game = GameStateV3(
            num_players, seed=seed, deck_config=deck_config
        )

        ais = []
        for pid in range(num_players):
            style = player_styles[pid % len(player_styles)]
            ais.append(AIPlayerV3(
                player_id=pid, skill=1.0, style=style,
                rng_seed=seed * 100 + pid
            ))

        def deployment_fn(player, gs, round_num):
            return ais[player.id].choose_deployment(player, gs, round_num)

        result = game.play_game(deployment_fn)
        all_results.append(result)

    return aggregate(all_results, num_players, deck_config)


def aggregate(results: List[dict], num_players: int, deck_config: DeckConfig) -> Dict:
    """Aggregate game results into summary statistics."""
    n = len(results)
    wins = defaultdict(float)
    all_scores = defaultdict(list)
    score_spreads = []
    all_strength = []
    all_cpz = []
    total_hf = 0
    total_mascot = 0
    zone_wins = defaultdict(int)
    ties = 0

    for r in results:
        winner = r["winner"]
        if isinstance(winner, list):
            ties += 1
            for w in winner:
                wins[w] += 1.0 / len(winner)
        else:
            wins[winner] += 1

        scores = list(r["scores"].values())
        for pid, s in r["scores"].items():
            all_scores[pid].append(s)
        score_spreads.append(max(scores) - min(scores))

        all_strength.extend(r.get("strength_values", []))
        all_cpz.extend(r.get("cards_per_zone_play", []))
        total_hf += r.get("home_field_triggers", 0)
        total_mascot += r.get("mascot_combos", 0)
        for pid, zw in r["zones_won"].items():
            zone_wins[pid] += zw

    # Calculate theoretical max mascot combo
    max_rank = deck_config.max_rank
    has_mascot = deck_config.has_mascot
    mascot_ceiling = max_rank * 2 if has_mascot else max_rank

    # Strength percentiles
    sorted_str = sorted(all_strength) if all_strength else [0]
    p25 = sorted_str[len(sorted_str) // 4] if all_strength else 0
    p75 = sorted_str[3 * len(sorted_str) // 4] if all_strength else 0

    fair = 1.0 / num_players
    win_rates = {pid: wins[pid] / n for pid in range(num_players)}
    max_seat_dev = max(abs(wr - fair) for wr in win_rates.values())

    return {
        "label": deck_config.label,
        "total_cards": deck_config.total_cards,
        "num_factions": len(deck_config.factions),
        "max_rank": max_rank,
        "mascot_ceiling": mascot_ceiling,
        "hand_size": int(deck_config.total_cards * 0.70 / num_players)
            if deck_config.total_cards != 66
            else {2: 18, 3: 15, 4: 13, 5: 11}[num_players],
        "num_games": n,
        "win_rates": win_rates,
        "max_seat_deviation": max_seat_dev,
        "tie_rate": ties / n,
        "avg_score": statistics.mean([s for scores in all_scores.values() for s in scores]),
        "avg_winner_score": statistics.mean([max(r["scores"].values()) for r in results]),
        "avg_score_spread": statistics.mean(score_spreads),
        "score_spread_std": statistics.stdev(score_spreads) if len(score_spreads) > 1 else 0,
        "strength_mean": statistics.mean(all_strength) if all_strength else 0,
        "strength_median": statistics.median(all_strength) if all_strength else 0,
        "strength_std": statistics.stdev(all_strength) if len(all_strength) > 1 else 0,
        "strength_p25": p25,
        "strength_p75": p75,
        "strength_max": max(all_strength) if all_strength else 0,
        "strength_min": min(all_strength) if all_strength else 0,
        "cpz_mean": statistics.mean(all_cpz) if all_cpz else 0,
        "hf_per_game": total_hf / n,
        "mascot_per_game": total_mascot / n,
        "avg_zone_wins": {pid: zone_wins[pid] / n for pid in range(num_players)},
    }


# ─── STYLE MATCHUP TEST ─────────────────────────────────────────────────────

def run_style_matchup(deck_config: DeckConfig, num_games: int,
                      num_players: int, start_seed: int = 10001) -> Dict:
    """Run games with all 5 styles and check for dominant strategies."""
    styles = list(STYLE_PROFILES.keys())
    style_wins = defaultdict(float)
    total_games = 0

    # For 3+ players, rotate through style combos
    for i in range(num_games):
        seed = start_seed + i
        # Rotate styles so each gets equal representation
        game_styles = [styles[(i + j) % len(styles)] for j in range(num_players)]

        game = GameStateV3(num_players, seed=seed, deck_config=deck_config)
        ais = [AIPlayerV3(pid, skill=1.0, style=game_styles[pid],
                          rng_seed=seed * 100 + pid)
               for pid in range(num_players)]

        def deployment_fn(player, gs, round_num):
            return ais[player.id].choose_deployment(player, gs, round_num)

        result = game.play_game(deployment_fn)
        winner = result["winner"]

        if isinstance(winner, list):
            for w in winner:
                style_wins[game_styles[w]] += 1.0 / len(winner)
        else:
            style_wins[game_styles[winner]] += 1

        total_games += 1

    return {s: style_wins[s] / total_games for s in styles}


# ─── REPORTING ───────────────────────────────────────────────────────────────

def print_comparison(all_agg: List[Dict], style_matchups: Dict[str, Dict]):
    """Print a side-by-side comparison table."""
    print()
    print("=" * 90)
    print("  TAILGATE TURF WAR — DISTRIBUTION COMPARISON")
    print("=" * 90)

    # Summary table
    header = f"{'Metric':<30}"
    for a in all_agg:
        # Use short key name
        short = a["label"][:20]
        header += f"  {short:>14}"
    print(f"\n{header}")
    print("-" * (30 + 16 * len(all_agg)))

    def row(label, key, fmt=".1f"):
        line = f"{label:<30}"
        for a in all_agg:
            val = a[key]
            line += f"  {val:>14{fmt}}"
        print(line)

    def row_custom(label, values):
        line = f"{label:<30}"
        for v in values:
            line += f"  {v:>14}"
        print(line)

    row_custom("Deck size", [str(a["total_cards"]) for a in all_agg])
    row_custom("Factions", [str(a["num_factions"]) for a in all_agg])
    row_custom("Max rank", [str(a["max_rank"]) for a in all_agg])
    row_custom("Mascot combo ceiling", [str(a["mascot_ceiling"]) for a in all_agg])
    row_custom("Hand size (3P)", [str(a["hand_size"]) for a in all_agg])
    print()

    print("--- BALANCE ---")
    row("Max seat deviation", "max_seat_deviation", ".1%")
    row("Tie rate", "tie_rate", ".1%")
    print()

    print("--- SCORES ---")
    row("Avg score (all players)", "avg_score", ".1f")
    row("Avg winner score", "avg_winner_score", ".1f")
    row("Avg score spread", "avg_score_spread", ".1f")
    row("Score spread std", "score_spread_std", ".1f")
    print()

    print("--- STRENGTH ---")
    row("Mean strength", "strength_mean", ".1f")
    row("Median strength", "strength_median", ".0f")
    row("Std dev", "strength_std", ".1f")
    row("25th percentile", "strength_p25", ".0f")
    row("75th percentile", "strength_p75", ".0f")
    row("Max observed", "strength_max", ".0f")
    row("Min observed", "strength_min", ".0f")
    print()

    print("--- FEATURES ---")
    row("Home Field triggers/game", "hf_per_game", ".1f")
    row("Mascot combos/game", "mascot_per_game", ".1f")
    row("Avg cards per zone play", "cpz_mean", ".2f")
    print()

    # Style matchup
    print("--- STRATEGY DOMINANCE (style win rates) ---")
    styles = list(STYLE_PROFILES.keys())
    style_header = f"{'Style':<15}"
    for a in all_agg:
        short = a["label"][:20]
        style_header += f"  {short:>14}"
    print(style_header)
    print("-" * (15 + 16 * len(all_agg)))

    for style in styles:
        line = f"{style:<15}"
        for key in style_matchups:
            rate = style_matchups[key].get(style, 0)
            line += f"  {rate:>13.1%}"
        print(line)

    # Check for dominant strategy
    print()
    fair_style = 1.0 / len(styles)
    for key, matchup in style_matchups.items():
        max_style = max(matchup, key=matchup.get)
        max_rate = matchup[max_style]
        min_style = min(matchup, key=matchup.get)
        min_rate = matchup[min_style]
        spread = max_rate - min_rate
        if spread > 0.10:
            print(f"  ⚠️  {key}: {max_style} dominates ({max_rate:.1%}) "
                  f"while {min_style} struggles ({min_rate:.1%})")
        else:
            print(f"  ✅ {key}: style spread {spread:.1%} (balanced)")

    print(f"\n{'=' * 90}")

    # Recommendation
    print("\n--- ANALYSIS ---")
    for a in all_agg:
        label = a["label"]
        issues = []
        strengths = []

        if a["max_seat_deviation"] > 0.05:
            issues.append(f"seat imbalance ({a['max_seat_deviation']:.1%})")
        else:
            strengths.append("fair seating")

        if a["avg_score_spread"] > 20:
            issues.append(f"blowouts (spread {a['avg_score_spread']:.1f})")
        elif a["avg_score_spread"] < 5:
            issues.append(f"too close (spread {a['avg_score_spread']:.1f})")
        else:
            strengths.append(f"good score spread ({a['avg_score_spread']:.1f})")

        if a["strength_std"] < 2.5:
            issues.append("low strength variance (decisions feel similar)")
        elif a["strength_std"] > 6:
            strengths.append("high strength variance (dramatic swings)")
        else:
            strengths.append(f"healthy strength spread (σ={a['strength_std']:.1f})")

        if a["hf_per_game"] < 2:
            issues.append(f"home field rare ({a['hf_per_game']:.1f}/game)")
        elif a["hf_per_game"] > 15:
            issues.append(f"home field too common ({a['hf_per_game']:.1f}/game)")
        else:
            strengths.append(f"home field meaningful ({a['hf_per_game']:.1f}/game)")

        if a["mascot_per_game"] < 0.5:
            issues.append(f"mascot combos rare ({a['mascot_per_game']:.1f}/game)")
        else:
            strengths.append(f"mascot combos active ({a['mascot_per_game']:.1f}/game)")

        print(f"\n  {label}:")
        for s in strengths:
            print(f"    ✅ {s}")
        for i in issues:
            print(f"    ⚠️  {i}")

    print()


# ─── MAIN ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Compare TTW distributions")
    parser.add_argument("-n", "--num-games", type=int, default=1000,
                        help="Games per distribution (default: 1000)")
    parser.add_argument("-p", "--players", type=int, default=3,
                        help="Player count (default: 3)")
    parser.add_argument("--style-games", type=int, default=500,
                        help="Games for style matchup test (default: 500)")
    args = parser.parse_args()

    print(f"Testing {len(DISTRIBUTIONS)} distributions × {args.num_games} games "
          f"× {args.players} players...")
    print(f"Plus {args.style_games} style matchup games per distribution.\n")

    all_agg = []
    style_matchups = {}
    base_styles = ["balanced", "balanced", "balanced", "balanced", "balanced"][:args.players]

    for key, dc in sorted(DISTRIBUTIONS.items()):
        print(f"  Running {key} ({dc.label})...", end="", flush=True)
        agg = run_games(dc, args.num_games, args.players, base_styles)
        all_agg.append(agg)
        print(f" scores avg={agg['avg_score']:.1f}, spread={agg['avg_score_spread']:.1f}")

        print(f"    Style matchup...", end="", flush=True)
        sm = run_style_matchup(dc, args.style_games, args.players)
        style_matchups[key] = sm
        dominant = max(sm, key=sm.get)
        print(f" top={dominant} ({sm[dominant]:.1%})")

    print_comparison(all_agg, style_matchups)


if __name__ == "__main__":
    main()
