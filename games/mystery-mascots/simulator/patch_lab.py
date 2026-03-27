#!/usr/bin/env python3
"""
Mystery Mascots — Patch Lab.

Tests proposed rule changes against the baseline to measure impact.
Each patch modifies config or game behavior, runs a batch, and compares.
"""

import json
import copy
import sys
import os
from collections import defaultdict

from cards import FACTIONS
from game_state import GameState, Player
from ai_player import HeuristicAI
from run_simulation import run_draft, execute_action, load_config
from fun_audit import run_game_with_fun_tracking, aggregate_fun_metrics


# ═══════════════════════════════════════════════════════════════════
# Patched game runner — supports rule overrides
# ═══════════════════════════════════════════════════════════════════

def run_patched_game(config, num_players, seed, max_turns=200,
                     bust_partial_scoring=False):
    """Run one game with optional rule patches applied."""
    game = GameState(config, num_players, seed=seed)

    ais = [HeuristicAI(skill=1.0, style="balanced", rng_seed=seed + i * 10000)
           for i in range(num_players)]

    game.setup(draft_fn=lambda players, hands, g: run_draft(players, hands, ais, g))

    # Patch resolution for wilds + optional bust scoring
    original_resolve = game._resolve_room

    def patched_resolve(room_idx, wild_fn=None):
        def ai_wild_fn(player, card, ri, g):
            return ais[player.pid].declare_wild(player, card, ri, g)

        result = original_resolve(room_idx, wild_fn=ai_wild_fn)

        # PATCH: partial scoring on busts
        if bust_partial_scoring and result.get("bust"):
            # Each faction in the bust scores half its rank sum (rounded down)
            for faction, count in result.get("faction_counts", {}).items():
                # Find the rank sum for this faction from the cards
                faction_rank_sum = 0
                for card_str, pid, eff_faction in result.get("cards", []):
                    if eff_faction == faction:
                        parts = card_str.split("-")
                        if len(parts) == 2:
                            try:
                                faction_rank_sum += int(parts[1])
                            except ValueError:
                                pass
                partial = faction_rank_sum // 2
                if partial > 0:
                    game.faction_scores[faction] += partial
                    result["bust_partial_scores"] = result.get("bust_partial_scores", {})
                    result["bust_partial_scores"][faction] = partial

        return result

    game._resolve_room = patched_resolve

    # Standard game loop
    turn_count = 0
    consecutive_passes = 0
    actions = defaultdict(int)

    while not game.game_over and turn_count < max_turns:
        player = game.get_current_player()
        ai = ais[player.pid]

        if not game.can_player_act(player):
            consecutive_passes += 1
            if consecutive_passes >= num_players:
                game.game_over = True
                break
            game.advance_turn()
            turn_count += 1
            continue

        action = ai.choose_action(player, game)

        if action.get("type") == "pass":
            consecutive_passes += 1
            if consecutive_passes >= num_players * 2:
                game.game_over = True
                break
            game.advance_turn()
            turn_count += 1
            continue

        consecutive_passes = 0
        result = execute_action(game, player, action, ai)
        actions[action.get("type", "pass")] += 1
        game.advance_turn()
        turn_count += 1

    scores = game.compute_final_scores()

    # Track key metrics
    busts = sum(1 for r in game.resolution_log if r["bust"])
    total_res = len(game.resolution_log)

    # Seat wins
    winner_pid = scores[0]["pid"] if scores else -1

    # Wow turns
    wow = 0
    for s in scores:
        if s["faction_points"] >= 10:
            wow += 1

    return {
        "seed": seed,
        "turns": turn_count,
        "completed": game.total_resolutions >= game.target_resolutions,
        "resolutions": game.total_resolutions,
        "busts": busts,
        "bust_rate": busts / max(total_res, 1),
        "winner_pid": winner_pid,
        "winner_score": scores[0]["total"] if scores else 0,
        "winner_faction": scores[0]["faction"] if scores else "NONE",
        "score_spread": scores[0]["total"] - scores[-1]["total"] if len(scores) > 1 else 0,
        "scores": scores,
        "faction_scores": dict(game.faction_scores),
        "exposure_count": sum(1 for p in game.players if p.exposed),
        "actions": dict(actions),
    }


def run_batch_patched(config, n_games, num_players, seed_start=1,
                      bust_partial_scoring=False, verbose=False):
    """Run a batch of patched games."""
    results = []
    for i in range(n_games):
        if verbose and (i + 1) % 100 == 0:
            print(f"    game {i+1}/{n_games}", file=sys.stderr)
        r = run_patched_game(config, num_players, seed=seed_start + i,
                             bust_partial_scoring=bust_partial_scoring)
        results.append(r)
    return results


def summarize_batch(results, label, num_players):
    """Summarize a batch of results."""
    n = len(results)
    turns = [r["turns"] for r in results]
    completion = sum(1 for r in results if r["completed"]) / n
    busts = sum(r["busts"] for r in results)
    total_res = sum(r["resolutions"] for r in results)
    bust_rate = busts / max(total_res, 1)

    # Seat balance
    seat_wins = defaultdict(int)
    for r in results:
        seat_wins[r["winner_pid"]] += 1
    seat_rates = {i: seat_wins.get(i, 0) / n for i in range(num_players)}
    max_seat = max(seat_rates.values())
    min_seat = min(seat_rates.values())

    # Faction balance
    faction_wins = defaultdict(int)
    for r in results:
        faction_wins[r["winner_faction"]] += 1

    # Scores
    winner_scores = [r["winner_score"] for r in results]
    all_player_scores = [s["total"] for r in results for s in r["scores"]]
    spreads = [r["score_spread"] for r in results]

    # Faction scores
    faction_totals = defaultdict(list)
    for r in results:
        for f, s in r["faction_scores"].items():
            faction_totals[f].append(s)

    # Exposure
    exposures = [r["exposure_count"] for r in results]

    summary = {
        "label": label,
        "num_games": n,
        "num_players": num_players,
        "avg_turns": sum(turns) / n,
        "turn_range": f"{min(turns)}-{max(turns)}",
        "completion_rate": completion,
        "bust_rate": bust_rate,
        "avg_busts_per_game": busts / n,
        "seat_imbalance": max_seat - min_seat,
        "seat_rates": {str(k): round(v, 3) for k, v in sorted(seat_rates.items())},
        "avg_winner_score": sum(winner_scores) / n,
        "avg_player_score": sum(all_player_scores) / len(all_player_scores) if all_player_scores else 0,
        "avg_score_spread": sum(spreads) / n,
        "avg_exposures": sum(exposures) / n,
        "faction_win_rates": {f: faction_wins.get(f, 0) / n for f in FACTIONS},
        "avg_faction_scores": {f: sum(v)/len(v) for f, v in faction_totals.items()},
    }
    return summary


def print_comparison(summaries):
    """Print side-by-side comparison of multiple batches."""
    print(f"\n{'='*80}")
    print(f"  PATCH LAB — RULE VARIANT COMPARISON")
    print(f"{'='*80}")

    # Column headers
    labels = [s["label"] for s in summaries]
    col_w = 18
    header = f"  {'Metric':<25s}" + "".join(f"{l:>{col_w}s}" for l in labels)
    print(f"\n{header}")
    print("  " + "-" * (25 + col_w * len(labels)))

    def row(metric, key, fmt=".1f"):
        vals = []
        for s in summaries:
            v = s.get(key, 0)
            if fmt == ".1%":
                vals.append(f"{v:.1%}")
            elif fmt == ".1f":
                vals.append(f"{v:.1f}")
            elif fmt == "s":
                vals.append(str(v))
            else:
                vals.append(str(v))
        line = f"  {metric:<25s}" + "".join(f"{v:>{col_w}s}" for v in vals)
        print(line)

    row("Avg turns", "avg_turns", ".1f")
    row("Turn range", "turn_range", "s")
    row("Completion rate", "completion_rate", ".1%")
    row("Bust rate", "bust_rate", ".1%")
    row("Avg busts/game", "avg_busts_per_game", ".1f")
    row("Seat imbalance", "seat_imbalance", ".1%")
    row("Avg winner score", "avg_winner_score", ".1f")
    row("Avg player score", "avg_player_score", ".1f")
    row("Avg score spread", "avg_score_spread", ".1f")
    row("Avg exposures", "avg_exposures", ".1f")

    # Seat rates
    print(f"\n  {'Seat win rates:':<25s}")
    for s in summaries:
        seats_str = ", ".join(f"S{k}:{v:.0%}" for k, v in sorted(s["seat_rates"].items()))
        print(f"    {s['label']}: {seats_str}")

    # Faction scores
    print(f"\n  {'Avg faction scores:':<25s}")
    for s in summaries:
        scores_str = ", ".join(
            f"{f[:3]}:{v:.1f}" for f, v in sorted(s["avg_faction_scores"].items(), key=lambda x: -x[1])
        )
        print(f"    {s['label']}: {scores_str}")

    print(f"\n{'='*80}")


# ═══════════════════════════════════════════════════════════════════
# Main — Run all patches
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Patch Lab")
    parser.add_argument("-n", "--num-games", type=int, default=500)
    parser.add_argument("--config", type=str, default=None)
    parser.add_argument("--json", type=str, default=None)
    args = parser.parse_args()

    config = load_config(args.config)
    N = args.num_games
    all_summaries = []

    # ── PATCH A: 3-player baseline ─────────────────────────────────
    print("  Patch A: 3p baseline (5 rooms)...", file=sys.stderr)
    batch_a = run_batch_patched(config, N, 3, seed_start=10000, verbose=True)
    sum_a = summarize_batch(batch_a, "3p-baseline", 3)
    all_summaries.append(sum_a)

    # ── PATCH B: 3-player with 4 rooms ─────────────────────────────
    print("  Patch B: 3p with 4 rooms...", file=sys.stderr)
    config_b = copy.deepcopy(config)
    config_b["game_rules"]["locker_rooms"]["3_player"] = 4
    batch_b = run_batch_patched(config_b, N, 3, seed_start=20000, verbose=True)
    sum_b = summarize_batch(batch_b, "3p-4rooms", 3)
    all_summaries.append(sum_b)

    # ── PATCH C: 4-player baseline ─────────────────────────────────
    print("  Patch C: 4p baseline...", file=sys.stderr)
    batch_c = run_batch_patched(config, N, 4, seed_start=30000, verbose=True)
    sum_c = summarize_batch(batch_c, "4p-baseline", 4)
    all_summaries.append(sum_c)

    # ── PATCH D: 4-player with partial bust scoring ────────────────
    print("  Patch D: 4p with partial bust scoring...", file=sys.stderr)
    batch_d = run_batch_patched(config, N, 4, seed_start=40000,
                                bust_partial_scoring=True, verbose=True)
    sum_d = summarize_batch(batch_d, "4p-bust-fix", 4)
    all_summaries.append(sum_d)

    # ── PATCH E: 3-player with 4 rooms + partial bust scoring ──────
    print("  Patch E: 3p with 4 rooms + partial bust scoring...", file=sys.stderr)
    batch_e = run_batch_patched(config_b, N, 3, seed_start=50000,
                                bust_partial_scoring=True, verbose=True)
    sum_e = summarize_batch(batch_e, "3p-both-fix", 3)
    all_summaries.append(sum_e)

    print_comparison(all_summaries)

    if args.json:
        with open(args.json, 'w') as f:
            json.dump(all_summaries, f, indent=2, default=str)
        print(f"\nResults saved to {args.json}")
