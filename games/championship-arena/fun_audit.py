#!/usr/bin/env python3
"""
Fun Audit for Championship Arena v1.1
Runs 250 games × 4 player counts (2, 3, 4) = 1000 total games
Grading dimensions:
  - Pacing: Avg rounds per game (target 6-10)
  - Mean Score: Average final FP of all players
  - Comeback Rate: % of games where winner was not leading at midpoint
  - Sweep Rate: % of rounds with a Sweep (3 rings)
  - Spectator Impact: % of rounds where Spectator card changed the outcome
  - Talent Usage: % of games where at least one Talent was decisive
  - Balance: Win rate spread across player positions
"""

import json
import random
import os
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from simulate_game import simulate_game, setup_game
from simulate_round import simulate_round
from game_state import GameState


# ─── Grading Helper ────────────────────────────────────────────────────────────

def grade_pacing(avg_rounds: float) -> Tuple[float, str]:
    """Grade pacing: target 6-10 rounds. Returns (grade 0-4, letter)."""
    if 6 <= avg_rounds <= 10:
        return 4.0, "A"
    elif avg_rounds < 4:
        return 1.0, "F"
    elif avg_rounds < 6:
        return 2.5, "D"
    elif avg_rounds < 12:
        return 3.5, "B"
    elif avg_rounds < 15:
        return 2.5, "D"
    else:
        return 1.5, "F"


def grade_mean_score(avg_fp: float, fp_to_win: int = 15) -> Tuple[float, str]:
    """Grade mean score: should be meaningful but not reach cap too often."""
    # If average is close to 15, games end prematurely (bad)
    # If average is very low, games drag (bad)
    if 8 <= avg_fp <= 12:
        return 4.0, "A"
    elif 6 <= avg_fp < 8:
        return 3.0, "B"
    elif 12 < avg_fp < 14:
        return 3.0, "B"
    elif 4 <= avg_fp < 6:
        return 2.0, "C"
    elif 14 <= avg_fp < 15:
        return 1.5, "D"
    else:
        return 1.0, "F"


def grade_comeback_rate(rate: float) -> Tuple[float, str]:
    """Grade comeback rate: target 25-45%."""
    if 25 <= rate <= 45:
        return 4.0, "A"
    elif 15 <= rate < 25:
        return 3.0, "B"
    elif 45 < rate <= 60:
        return 3.0, "B"
    elif 5 <= rate < 15:
        return 2.0, "C"
    elif rate < 5:
        return 1.0, "F"
    else:
        return 1.5, "D"


def grade_sweep_rate(rate: float) -> Tuple[float, str]:
    """Grade sweep rate: target 8-20%."""
    if 8 <= rate <= 20:
        return 4.0, "A"
    elif 4 <= rate < 8:
        return 3.0, "B"
    elif 20 < rate <= 35:
        return 3.0, "B"
    elif 1 <= rate < 4:
        return 2.0, "C"
    elif rate < 1:
        return 1.0, "F"
    else:
        return 1.5, "D"


def grade_spectator_impact(rate: float) -> Tuple[float, str]:
    """Grade spectator impact: target 30-50%."""
    if 30 <= rate <= 50:
        return 4.0, "A"
    elif 15 <= rate < 30:
        return 3.0, "B"
    elif 50 < rate <= 65:
        return 3.0, "B"
    elif 5 <= rate < 15:
        return 2.0, "C"
    elif rate < 5:
        return 1.0, "F"
    else:
        return 1.5, "D"


def grade_talent_usage(rate: float) -> Tuple[float, str]:
    """Grade talent usage: target 40-70%."""
    if 40 <= rate <= 70:
        return 4.0, "A"
    elif 20 <= rate < 40:
        return 3.0, "B"
    elif 70 < rate <= 85:
        return 3.0, "B"
    elif 5 <= rate < 20:
        return 2.0, "C"
    elif rate < 5:
        return 1.0, "F"
    else:
        return 1.5, "D"


def grade_balance(win_spread: float) -> Tuple[float, str]:
    """Grade balance: win rate spread (lower is better, target <20%)."""
    if win_spread < 10:
        return 4.0, "A"
    elif win_spread < 20:
        return 3.5, "B"
    elif win_spread < 30:
        return 3.0, "B"
    elif win_spread < 40:
        return 2.0, "C"
    elif win_spread < 50:
        return 1.5, "D"
    else:
        return 1.0, "F"


# ─── Extended Game Simulation for Audit ───────────────────────────────────────

@dataclass
class GameAuditData:
    winner_id: int
    final_scores: List[int]
    total_rounds: int
    was_comeback: bool
    sweep_rounds: int
    total_rounds_simulated: int
    spectator_impact: bool
    talent_decisive: bool


def simulate_game_for_audit(
    num_players: int,
    config: dict,
    seed: int
) -> GameAuditData:
    """Simulate a game and collect audit data."""
    random.seed(seed)
    gs = setup_game(num_players, config)

    max_rounds = 50
    round_number = 0
    leader_at_midpoint = None
    sweep_rounds = 0
    spectator_impact = False
    talent_decisive = False
    fp_history = []  # track FP after each round

    # Per-round audit data passed to simulate_round
    audit_data = {
        "sweep_rounds": 0,
        "spectator_impact_this_round": False,
        "talent_decisive": False,
    }

    for _ in range(max_rounds):
        audit_data["spectator_impact_this_round"] = False
        audit_data["talent_decisive"] = False
        audit_data["sweep_rounds"] = 0

        gs, _ = simulate_round(gs, audit_data)
        round_number += 1

        if audit_data["spectator_impact_this_round"]:
            spectator_impact = True
        if audit_data["talent_decisive"]:
            talent_decisive = True
        sweep_rounds += audit_data["sweep_rounds"]

        # Track leader at midpoint (50% of actual game length, round up)
        fp_history.append({p.id: p.fp for p in gs.players})
        midpoint = (round_number + 1) // 2  # midpoint of rounds played so far
        if len(fp_history) >= midpoint:
            midpoint_idx = midpoint - 1
            mid_fp = fp_history[midpoint_idx]
            leader_at_midpoint = max(mid_fp, key=lambda pid: mid_fp[pid])

        if gs.winner:
            break

    winner = gs.winner
    final_scores = [p.fp for p in gs.players]

    # Comeback detection: winner was not leading at midpoint
    was_comeback = False
    if round_number >= 2 and leader_at_midpoint is not None and winner:
        if leader_at_midpoint != winner.id:
            was_comeback = True

    return GameAuditData(
        winner_id=winner.id if winner else -1,
        final_scores=final_scores,
        total_rounds=round_number,
        was_comeback=was_comeback,
        sweep_rounds=sweep_rounds,
        total_rounds_simulated=round_number,
        spectator_impact=spectator_impact,
        talent_decisive=talent_decisive,
    )


# ─── Main Fun Audit ────────────────────────────────────────────────────────────

def run_fun_audit(num_games: int = 250) -> Dict:
    """Run the full fun audit."""
    with open(os.path.join(os.path.dirname(__file__), "config.json")) as f:
        config = json.load(f)

    results_by_players = {}

    for num_players in [2, 3, 4]:
        print(f"  Running {num_games} {num_players}-player games...", flush=True)

        all_rounds = []
        all_final_fp = []
        comeback_count = 0
        sweep_count = 0
        spectator_impact_count = 0
        talent_decisive_count = 0
        wins = defaultdict(int)
        total_games = 0

        for i in range(num_games):
            seed = i * 1000 + num_players
            audit = simulate_game_for_audit(num_players, config, seed)

            all_rounds.append(audit.total_rounds)
            all_final_fp.extend(audit.final_scores)
            wins[audit.winner_id] += 1
            total_games += 1

            if audit.was_comeback:
                comeback_count += 1
            if audit.sweep_rounds > 0:
                sweep_count += 1
            if audit.spectator_impact:
                spectator_impact_count += 1
            if audit.talent_decisive:
                talent_decisive_count += 1

        avg_rounds = sum(all_rounds) / len(all_rounds) if all_rounds else 0
        avg_fp = sum(all_final_fp) / len(all_final_fp) if all_final_fp else 0
        comeback_rate = comeback_count / total_games * 100 if total_games else 0
        sweep_rate = sweep_count / total_games * 100 if total_games else 0
        spectator_rate = spectator_impact_count / total_games * 100 if total_games else 0
        talent_rate = talent_decisive_count / total_games * 100 if total_games else 0

        # Win rate spread (max - min win rate)
        win_rates = {pid: count / total_games * 100 for pid, count in wins.items()}
        win_spread = max(win_rates.values()) - min(win_rates.values()) if win_rates else 0

        results_by_players[num_players] = {
            "avg_rounds": avg_rounds,
            "avg_fp": avg_fp,
            "comeback_rate": comeback_rate,
            "sweep_rate": sweep_rate,
            "spectator_rate": spectator_rate,
            "talent_rate": talent_rate,
            "win_spread": win_spread,
            "win_rates": win_rates,
            "wins": dict(wins),
        }

    # ── Compute grades ────────────────────────────────────────────────────────
    all_grades = []

    # Pool across all player counts for overall grades
    pool_avg_rounds = sum(r["avg_rounds"] for r in results_by_players.values()) / 3
    pool_avg_fp = sum(r["avg_fp"] for r in results_by_players.values()) / 3
    pool_comeback = sum(r["comeback_rate"] for r in results_by_players.values()) / 3
    pool_sweep = sum(r["sweep_rate"] for r in results_by_players.values()) / 3
    pool_spectator = sum(r["spectator_rate"] for r in results_by_players.values()) / 3
    pool_talent = sum(r["talent_rate"] for r in results_by_players.values()) / 3
    pool_balance = sum(r["win_spread"] for r in results_by_players.values()) / 3

    pacing_grade, pacing_letter = grade_pacing(pool_avg_rounds)
    score_grade, score_letter = grade_mean_score(pool_avg_fp)
    comeback_grade, comeback_letter = grade_comeback_rate(pool_comeback)
    sweep_grade, sweep_letter = grade_sweep_rate(pool_sweep)
    spectator_grade, spectator_letter = grade_spectator_impact(pool_spectator)
    talent_grade, talent_letter = grade_talent_usage(pool_talent)
    balance_grade, balance_letter = grade_balance(pool_balance)

    all_grades = [
        pacing_grade, score_grade, comeback_grade, sweep_grade,
        spectator_grade, talent_grade, balance_grade
    ]
    gpa = sum(all_grades) / len(all_grades)

    # Letter grade
    if gpa >= 3.7: letter = "A"
    elif gpa >= 3.0: letter = "B"
    elif gpa >= 2.0: letter = "C"
    elif gpa >= 1.0: letter = "D"
    else: letter = "F"

    # ── Build report ──────────────────────────────────────────────────────────
    report = []
    report.append("=" * 70)
    report.append("  CHAMPIONSHIP ARENA v1.1 — FUN AUDIT REPORT")
    report.append("=" * 70)
    report.append(f"\n  Games simulated: {num_games} × 3 player counts = {num_games * 3} total")
    report.append(f"  Date: 2026-03-27\n")

    report.append("-" * 70)
    report.append("  DIMENSION GRADES")
    report.append("-" * 70)

    dims = [
        ("Pacing", pool_avg_rounds, pacing_grade, pacing_letter,
         f"target 6-10 rounds, got {pool_avg_rounds:.1f}"),
        ("Mean Score", pool_avg_fp, score_grade, score_letter,
         f"avg final FP {pool_avg_fp:.1f} / 15"),
        ("Comeback Rate", pool_comeback, comeback_grade, comeback_letter,
         f"target 25-45%, got {pool_comeback:.1f}%"),
        ("Sweep Rate", pool_sweep, sweep_grade, sweep_letter,
         f"target 8-20%, got {pool_sweep:.1f}%"),
        ("Spectator Impact", pool_spectator, spectator_grade, spectator_letter,
         f"target 30-50%, got {pool_spectator:.1f}%"),
        ("Talent Usage", pool_talent, talent_grade, talent_letter,
         f"target 40-70%, got {pool_talent:.1f}%"),
        ("Balance", pool_balance, balance_grade, balance_letter,
         f"win rate spread {pool_balance:.1f}%"),
    ]

    for name, value, grade, letter, note in dims:
        bar = "█" * int(grade) + "░" * (4 - int(grade))
        report.append(f"  {name:<20} [{bar}] {letter}  ({grade:.1f}/4.0)  {note}")

    report.append("")
    report.append(f"  ╔══════════════════════════════════════════╗")
    report.append(f"  ║  OVERALL GPA:  {gpa:.2f} / 4.00  →  Letter: {letter}   ║")
    report.append(f"  ╚══════════════════════════════════════════╝")

    report.append("\n" + "-" * 70)
    report.append("  PER-PLAYER-COUNT BREAKDOWN")
    report.append("-" * 70)

    for num_players, r in sorted(results_by_players.items()):
        report.append(f"\n  {num_players}-Player Games:")
        report.append(f"    Avg rounds: {r['avg_rounds']:.1f}")
        report.append(f"    Avg final FP: {r['avg_fp']:.1f}")
        report.append(f"    Win rates: {dict(sorted(r['win_rates'].items()))}")
        report.append(f"    Comeback rate: {r['comeback_rate']:.1f}%")
        report.append(f"    Sweep rate: {r['sweep_rate']:.1f}%")
        report.append(f"    Spectator impact: {r['spectator_rate']:.1f}%")
        report.append(f"    Talent decisive: {r['talent_rate']:.1f}%")
        report.append(f"    Win rate spread: {r['win_spread']:.1f}%")

    report.append("\n" + "=" * 70)
    report.append("  END OF FUN AUDIT")
    report.append("=" * 70)

    return {
        "results_by_players": results_by_players,
        "dimensions": {
            "Pacing": {"value": pool_avg_rounds, "grade": pacing_grade, "letter": pacing_letter},
            "Mean Score": {"value": pool_avg_fp, "grade": score_grade, "letter": score_letter},
            "Comeback Rate": {"value": pool_comeback, "grade": comeback_grade, "letter": comeback_letter},
            "Sweep Rate": {"value": pool_sweep, "grade": sweep_grade, "letter": sweep_letter},
            "Spectator Impact": {"value": pool_spectator, "grade": spectator_grade, "letter": spectator_letter},
            "Talent Usage": {"value": pool_talent, "grade": talent_grade, "letter": talent_letter},
            "Balance": {"value": pool_balance, "grade": balance_grade, "letter": balance_letter},
        },
        "gpa": gpa,
        "letter": letter,
        "report": report,
    }


def main():
    print("CHAMPIONSHIP ARENA v1.1 — FUN AUDIT")
    print("Running 250 games × 3 player counts (2, 3, 4)...\n")

    audit = run_fun_audit(250)

    report_text = "\n".join(audit["report"])
    print("\n" + report_text)

    # Save results
    output_dir = os.path.dirname(os.path.abspath(__file__))
    report_path = os.path.join(output_dir, "FUN-AUDIT-RESULTS.md")
    with open(report_path, "w") as f:
        f.write("# Championship Arena v1.1 — Fun Audit Results\n\n")
        f.write(f"**Date:** 2026-03-27\n")
        f.write(f"**Games simulated:** 250 × 3 player counts = 750 total\n\n")
        f.write(report_text)

    print(f"\n[Fun audit saved to: {report_path}]")


if __name__ == "__main__":
    main()
