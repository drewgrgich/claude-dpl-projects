#!/usr/bin/env python3
"""
Mystery Mascots — Deep Analysis for the Design Team.

Answers 11 specific questions from Morgan, Jordan, and Casey
with targeted simulations and data extraction.
"""

import json
import os
import sys
from collections import defaultdict
from typing import List, Dict
import random
import math

from cards import Card, Deck, FACTIONS, FACTION_NAMES, build_full_deck, WILD_RANKS
from game_state import GameState, Player, Placement
from ai_player import HeuristicAI, STYLE_PROFILES
from run_simulation import run_draft, execute_action, load_config


# ═══════════════════════════════════════════════════════════════════
# Instrumented game runner with deep tracking
# ═══════════════════════════════════════════════════════════════════

def run_deep_game(config, num_players, seed, max_turns=200,
                  player_configs=None) -> dict:
    """Run one game with maximum instrumentation."""
    game = GameState(config, num_players, seed=seed)

    ais = []
    for i in range(num_players):
        pc = player_configs[i] if player_configs and i < len(player_configs) else {}
        ais.append(HeuristicAI(
            skill=pc.get("skill", 1.0),
            style=pc.get("style", "balanced"),
            aggression=pc.get("aggression", 0.5),
            rng_seed=seed + i * 10000,
        ))

    game.setup(draft_fn=lambda players, hands, g: run_draft(players, hands, ais, g))

    # Patch resolution for wilds
    original_resolve = game._resolve_room
    def resolve_with_wilds(room_idx, wild_fn=None):
        def ai_wild_fn(player, card, ri, g):
            return ais[player.pid].declare_wild(player, card, ri, g)
        return original_resolve(room_idx, wild_fn=ai_wild_fn)
    game._resolve_room = resolve_with_wilds

    # ── Deep tracking ──────────────────────────────────────────────
    # Q2: Track which ranks are played and their outcomes
    rank_placements = []  # (rank, player_faction, room_won, points_contributed)

    # Q5: "Oh no" moments — exposure at worst time
    oh_no_moments = []  # dicts of dramatic exposures

    # Q7: Resolution drama tracking
    resolution_dramas = []

    # Per-turn choice tracking for Q6
    choice_counts_per_turn = []

    # Wild declaration tracking for Q2
    wild_declarations = []  # (rank, declared_as_own_faction, room_scored)

    # Draft tracking
    drafted_own_faction = [0] * num_players
    drafted_total = [0] * num_players
    for i, p in enumerate(game.players):
        for c in p.hand:
            drafted_total[i] += 1
            if c.faction == p.faction:
                drafted_own_faction[i] += 1

    # Exposure timing
    exposure_turns = []
    pre_exposure_scores = []

    turn_count = 0
    consecutive_passes = 0
    actions_by_style = defaultdict(lambda: defaultdict(int))

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

        # Q6: Track choices available
        from fun_audit import count_meaningful_choices
        choices = count_meaningful_choices(player, game)
        total_choices = sum(1 for v in choices.values() if v > 0)
        choice_counts_per_turn.append(total_choices)

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

        # Track action by style
        style = ai.style_name
        actions_by_style[style][action["type"]] += 1

        # Pre-action state for "oh no" tracking
        was_hidden = not player.exposed
        faction_score_before = game.faction_scores.get(player.faction, 0)

        result = execute_action(game, player, action, ai)

        # Q2: Track card ranks played
        if action.get("type") == "place":
            card = action["card"]
            rank_placements.append({
                "rank": card.rank,
                "is_wild": card.is_wild,
                "player_faction": player.faction,
                "card_faction": card.faction,
                "triggered_res": result.get("triggered_resolution", False),
            })

        # Q5: "Oh no" moments — did this player just get exposed unexpectedly?
        if was_hidden and player.exposed:
            faction_score_after = game.faction_scores.get(player.faction, 0)
            # Was this a bad time to get exposed?
            progress = game.total_resolutions / max(game.target_resolutions, 1)
            cards_left = len(player.hand)
            oh_no = {
                "turn": turn_count,
                "player": player.pid,
                "faction": player.faction,
                "progress": progress,
                "cards_left": cards_left,
                "was_winning": faction_score_before > 0,
            }
            # Drama score: worse if early, if player had many cards left, if faction was winning
            oh_no["drama_score"] = (
                (1.0 - progress) * 3.0 +  # earlier = worse
                cards_left * 1.0 +  # more cards left = more impact
                (2.0 if oh_no["was_winning"] else 0.0)
            )
            oh_no_moments.append(oh_no)
            exposure_turns.append(turn_count)
            pre_exposure_scores.append(faction_score_before)

        # Q7: Track resolution drama
        if result.get("triggered_resolution"):
            res = result.get("resolution", {})
            if res:
                drama = {
                    "scored": res.get("scored", False),
                    "score": res.get("score", 0),
                    "bust": res.get("bust", False),
                    "faction_counts": res.get("faction_counts", {}),
                    "num_factions": len(res.get("faction_counts", {})),
                    "was_close": False,
                }
                # Was it close? (2 factions with equal count = bust)
                counts = list(res.get("faction_counts", {}).values())
                if len(counts) >= 2:
                    counts.sort(reverse=True)
                    drama["was_close"] = (counts[0] - counts[1]) <= 0
                    drama["margin"] = counts[0] - (counts[1] if len(counts) > 1 else 0)

                # High-value resolution?
                if res.get("score", 0) >= 15:
                    drama["high_value"] = True
                else:
                    drama["high_value"] = False

                resolution_dramas.append(drama)

        game.advance_turn()
        turn_count += 1

    # ── Compile results ────────────────────────────────────────────
    final_scores = game.compute_final_scores()

    return {
        "seed": seed,
        "num_players": num_players,
        "turns": turn_count,
        "completed": game.total_resolutions >= game.target_resolutions,
        "final_scores": final_scores,
        "faction_scores": dict(game.faction_scores),
        "rank_placements": rank_placements,
        "oh_no_moments": oh_no_moments,
        "resolution_dramas": resolution_dramas,
        "choice_counts": choice_counts_per_turn,
        "wild_declarations": wild_declarations,
        "drafted_own_faction": drafted_own_faction,
        "drafted_total": drafted_total,
        "exposure_turns": exposure_turns,
        "exposure_count": sum(1 for p in game.players if p.exposed),
        "actions_by_style": {k: dict(v) for k, v in actions_by_style.items()},
        "accusations": [
            {
                "player": p.pid,
                "faction": p.faction,
                "made": len(p.accusations_made),
                "correct": sum(1 for a in p.accusations_made if a["correct"]),
            }
            for p in game.players
        ],
        "resolution_log": game.resolution_log,
        "bust_count": sum(1 for r in game.resolution_log if r["bust"]),
        "player_styles": [ais[i].style_name for i in range(num_players)],
    }


# ═══════════════════════════════════════════════════════════════════
# Run all targeted simulation batches
# ═══════════════════════════════════════════════════════════════════

def run_all_analyses(config, n_games=500, verbose=True):
    """Run every analysis needed for the 11 questions."""
    results = {}

    def vprint(msg):
        if verbose:
            print(f"  {msg}", file=sys.stderr)

    # ── Batch 1: Standard 4-player (deep tracked) ─────────────────
    vprint("Batch 1: Deep-tracked 4-player games...")
    deep_4p = []
    for i in range(n_games):
        if verbose and (i+1) % 100 == 0:
            vprint(f"  4p game {i+1}/{n_games}")
        r = run_deep_game(config, 4, seed=1000 + i)
        deep_4p.append(r)
    results["deep_4p"] = deep_4p

    # ── Batch 2: 3-player ─────────────────────────────────────────
    vprint("Batch 2: 3-player games...")
    deep_3p = []
    for i in range(n_games):
        if verbose and (i+1) % 100 == 0:
            vprint(f"  3p game {i+1}/{n_games}")
        r = run_deep_game(config, 3, seed=2000 + i)
        deep_3p.append(r)
    results["deep_3p"] = deep_3p

    # ── Batch 3: 5-player ─────────────────────────────────────────
    vprint("Batch 3: 5-player games...")
    deep_5p = []
    for i in range(n_games):
        if verbose and (i+1) % 100 == 0:
            vprint(f"  5p game {i+1}/{n_games}")
        r = run_deep_game(config, 5, seed=3000 + i)
        deep_5p.append(r)
    results["deep_5p"] = deep_5p

    # ── Batch 4: Style matchups (Q2, Q11) ─────────────────────────
    vprint("Batch 4: Style matchup games...")
    style_games = []
    styles = ["sneaky", "bold", "balanced", "disruptive"]
    for i in range(n_games):
        if verbose and (i+1) % 100 == 0:
            vprint(f"  style game {i+1}/{n_games}")
        configs_list = [
            {"skill": 1.0, "style": styles[j % len(styles)]}
            for j in range(4)
        ]
        r = run_deep_game(config, 4, seed=4000 + i, player_configs=configs_list)
        style_games.append(r)
    results["style_games"] = style_games

    # ── Batch 5: Skill gap (Q6, Q10) ─────────────────────────────
    vprint("Batch 5: Expert vs Beginner games...")
    skill_gap = []
    for i in range(n_games):
        if verbose and (i+1) % 100 == 0:
            vprint(f"  skill gap game {i+1}/{n_games}")
        configs_list = [
            {"skill": 1.0, "style": "balanced"},  # expert
            {"skill": 0.3, "style": "balanced"},   # beginner
            {"skill": 0.3, "style": "balanced"},   # beginner
            {"skill": 0.3, "style": "balanced"},   # beginner
        ]
        r = run_deep_game(config, 4, seed=5000 + i, player_configs=configs_list)
        skill_gap.append(r)
    results["skill_gap"] = skill_gap

    # ── Batch 6: All beginners (Q10 learning curve baseline) ─────
    vprint("Batch 6: All-beginner games...")
    beginners = []
    for i in range(n_games):
        if verbose and (i+1) % 100 == 0:
            vprint(f"  beginner game {i+1}/{n_games}")
        configs_list = [{"skill": 0.3, "style": "balanced"} for _ in range(4)]
        r = run_deep_game(config, 4, seed=6000 + i, player_configs=configs_list)
        beginners.append(r)
    results["beginners"] = beginners

    return results


# ═══════════════════════════════════════════════════════════════════
# Answer each question from the data
# ═══════════════════════════════════════════════════════════════════

def answer_questions(results: dict) -> dict:
    """Extract answers to all 11 questions."""
    answers = {}

    # ── Q1: Win rate by faction ────────────────────────────────────
    def faction_win_rates(games):
        faction_wins = defaultdict(int)
        faction_appearances = defaultdict(int)
        total = len(games)
        for g in games:
            # Track which factions appear
            seen = set()
            for s in g["final_scores"]:
                seen.add(s["faction"])
            for f in seen:
                faction_appearances[f] += 1
            # Winner
            if g["final_scores"]:
                faction_wins[g["final_scores"][0]["faction"]] += 1
        return {
            f: {
                "wins": faction_wins.get(f, 0),
                "appearances": faction_appearances.get(f, 0),
                "win_rate_raw": faction_wins.get(f, 0) / max(total, 1),
                "win_rate_adjusted": (
                    faction_wins.get(f, 0) / max(faction_appearances.get(f, 0), 1)
                ),
            }
            for f in FACTIONS
        }

    answers["q1_faction_balance"] = {
        "4p": faction_win_rates(results["deep_4p"]),
        "3p": faction_win_rates(results["deep_3p"]),
        "5p": faction_win_rates(results["deep_5p"]),
    }

    # Avg faction scores
    def avg_faction_scores(games):
        totals = defaultdict(list)
        for g in games:
            for f, s in g["faction_scores"].items():
                totals[f].append(s)
        return {f: sum(v)/len(v) if v else 0 for f, v in totals.items()}

    answers["q1_avg_scores"] = {
        "4p": avg_faction_scores(results["deep_4p"]),
        "3p": avg_faction_scores(results["deep_3p"]),
        "5p": avg_faction_scores(results["deep_5p"]),
    }

    # ── Q2: Sneak vs Shove (0/10 wild strategy) ───────────────────
    # Track how wilds (0s and 10s) perform
    wild_stats = {"0": {"placed": 0, "in_winning_rooms": 0, "total_pts_contributed": 0},
                  "10": {"placed": 0, "in_winning_rooms": 0, "total_pts_contributed": 0},
                  "mid": {"placed": 0, "in_winning_rooms": 0}}
    for g in results["deep_4p"]:
        for rp in g["rank_placements"]:
            if rp["rank"] == 0:
                wild_stats["0"]["placed"] += 1
            elif rp["rank"] == 10:
                wild_stats["10"]["placed"] += 1
            else:
                wild_stats["mid"]["placed"] += 1

        # Check resolution outcomes
        for res in g["resolution_log"]:
            if res["scored"]:
                for card_str, pid, eff_faction in res["cards"]:
                    # Parse rank from card string
                    parts = card_str.split("-")
                    if len(parts) == 2:
                        try:
                            rank = int(parts[1])
                            if eff_faction == res["winning_faction"]:
                                if rank == 0:
                                    wild_stats["0"]["in_winning_rooms"] += 1
                                elif rank == 10:
                                    wild_stats["10"]["in_winning_rooms"] += 1
                                    wild_stats["10"]["total_pts_contributed"] += 10
                                else:
                                    wild_stats["mid"]["in_winning_rooms"] += 1
                        except ValueError:
                            pass

    answers["q2_sneak_vs_shove"] = wild_stats

    # Style win rates
    style_wins = defaultdict(int)
    style_games_count = defaultdict(int)
    for g in results["style_games"]:
        for i, style in enumerate(g["player_styles"]):
            style_games_count[style] += 1
        if g["final_scores"]:
            winner_idx = g["final_scores"][0]["pid"]
            winner_style = g["player_styles"][winner_idx]
            style_wins[winner_style] += 1

    answers["q2_style_win_rates"] = {
        s: style_wins.get(s, 0) / max(style_games_count.get(s, 0), 1)
        for s in STYLE_PROFILES
    }

    # ── Q3: Accusation / deduction accuracy ────────────────────────
    total_accusations = 0
    correct_accusations = 0
    accusations_vs_exposed = 0
    accusations_vs_hidden = 0
    correct_vs_hidden = 0
    for g in results["deep_4p"]:
        for acc in g["accusations"]:
            total_accusations += acc["made"]
            correct_accusations += acc["correct"]

    answers["q3_deduction"] = {
        "total_accusations": total_accusations,
        "correct": correct_accusations,
        "accuracy": correct_accusations / max(total_accusations, 1),
        "avg_per_game": total_accusations / max(len(results["deep_4p"]), 1),
    }

    # How many players get exposed per game?
    exposure_counts = [g["exposure_count"] for g in results["deep_4p"]]
    answers["q3_exposure"] = {
        "avg_exposed": sum(exposure_counts) / len(exposure_counts),
        "all_exposed_pct": sum(1 for e in exposure_counts if e >= 4) / len(exposure_counts),
        "none_exposed_pct": sum(1 for e in exposure_counts if e == 0) / len(exposure_counts),
    }

    # ── Q4: Game length distribution ──────────────────────────────
    for label, games in [("4p", results["deep_4p"]), ("3p", results["deep_3p"]),
                          ("5p", results["deep_5p"])]:
        turns = [g["turns"] for g in games]
        answers[f"q4_length_{label}"] = {
            "avg": sum(turns) / len(turns),
            "min": min(turns),
            "max": max(turns),
            "median": sorted(turns)[len(turns)//2],
            "std": math.sqrt(sum((t - sum(turns)/len(turns))**2 for t in turns) / len(turns)),
            "completion_rate": sum(1 for g in games if g["completed"]) / len(games),
            "distribution": {
                f"{lo}-{hi}": sum(1 for t in turns if lo <= t < hi) / len(turns)
                for lo, hi in [(15, 20), (20, 25), (25, 30), (30, 35), (35, 50)]
            },
        }

    # ── Q5: "Oh no!" moments ──────────────────────────────────────
    all_oh_nos = []
    for g in results["deep_4p"]:
        all_oh_nos.extend(g["oh_no_moments"])

    n_games_4p = len(results["deep_4p"])
    high_drama = [o for o in all_oh_nos if o["drama_score"] >= 5.0]
    answers["q5_oh_no"] = {
        "total_exposures": len(all_oh_nos),
        "avg_per_game": len(all_oh_nos) / n_games_4p,
        "high_drama_count": len(high_drama),
        "high_drama_per_game": len(high_drama) / n_games_4p,
        "pct_games_with_drama": sum(
            1 for g in results["deep_4p"]
            if any(o["drama_score"] >= 5.0 for o in g["oh_no_moments"])
        ) / n_games_4p,
        "avg_drama_score": sum(o["drama_score"] for o in all_oh_nos) / max(len(all_oh_nos), 1),
        "exposure_while_winning": sum(1 for o in all_oh_nos if o["was_winning"]) / max(len(all_oh_nos), 1),
        "early_exposure_pct": sum(1 for o in all_oh_nos if o["progress"] < 0.3) / max(len(all_oh_nos), 1),
    }

    # ── Q6: Agency vs Luck (skill gap analysis) ───────────────────
    expert_wins = 0
    expert_avg_score = []
    beginner_avg_score = []
    for g in results["skill_gap"]:
        if g["final_scores"]:
            # P0 is expert, P1-3 are beginners
            if g["final_scores"][0]["pid"] == 0:
                expert_wins += 1
            for s in g["final_scores"]:
                if s["pid"] == 0:
                    expert_avg_score.append(s["total"])
                else:
                    beginner_avg_score.append(s["total"])

    n_skill = len(results["skill_gap"])
    answers["q6_agency"] = {
        "expert_win_rate": expert_wins / n_skill,
        "expected_random_win_rate": 0.25,
        "skill_multiplier": (expert_wins / n_skill) / 0.25,
        "expert_avg_score": sum(expert_avg_score) / max(len(expert_avg_score), 1),
        "beginner_avg_score": sum(beginner_avg_score) / max(len(beginner_avg_score), 1),
        "score_advantage": (
            sum(expert_avg_score) / max(len(expert_avg_score), 1) -
            sum(beginner_avg_score) / max(len(beginner_avg_score), 1)
        ),
    }

    # Choice variety
    all_choices = []
    for g in results["deep_4p"]:
        all_choices.extend(g["choice_counts"])
    answers["q6_choices"] = {
        "avg_choices_per_turn": sum(all_choices) / max(len(all_choices), 1),
        "pct_1_choice": sum(1 for c in all_choices if c == 1) / max(len(all_choices), 1),
        "pct_2_choices": sum(1 for c in all_choices if c == 2) / max(len(all_choices), 1),
        "pct_3_choices": sum(1 for c in all_choices if c == 3) / max(len(all_choices), 1),
    }

    # ── Q7: Resolution drama ──────────────────────────────────────
    all_dramas = []
    for g in results["deep_4p"]:
        all_dramas.extend(g["resolution_dramas"])

    total_res = len(all_dramas)
    answers["q7_drama"] = {
        "total_resolutions": total_res,
        "bust_rate": sum(1 for d in all_dramas if d["bust"]) / max(total_res, 1),
        "high_value_rate": sum(1 for d in all_dramas if d["high_value"]) / max(total_res, 1),
        "close_rate": sum(1 for d in all_dramas if d["was_close"]) / max(total_res, 1),
        "avg_factions_per_room": sum(d["num_factions"] for d in all_dramas) / max(total_res, 1),
        "score_when_scored": (
            sum(d["score"] for d in all_dramas if d["scored"]) /
            max(sum(1 for d in all_dramas if d["scored"]), 1)
        ),
        "pct_3_faction_rooms": sum(1 for d in all_dramas if d["num_factions"] >= 3) / max(total_res, 1),
    }

    # ── Q8: Scaling comparison ─────────────────────────────────────
    def scaling_stats(games, n_players):
        turns = [g["turns"] for g in games]
        busts = sum(g["bust_count"] for g in games)
        total_res = sum(len(g["resolution_log"]) for g in games)
        exposures = [g["exposure_count"] for g in games]

        # Seat balance
        seat_wins = defaultdict(int)
        for g in games:
            if g["final_scores"]:
                seat_wins[g["final_scores"][0]["pid"]] += 1
        seat_rates = {i: seat_wins.get(i, 0) / len(games) for i in range(n_players)}
        max_seat = max(seat_rates.values())
        min_seat = min(seat_rates.values())

        return {
            "avg_turns": sum(turns) / len(turns),
            "completion_rate": sum(1 for g in games if g["completed"]) / len(games),
            "bust_rate": busts / max(total_res, 1),
            "avg_exposures": sum(exposures) / len(exposures),
            "seat_imbalance": max_seat - min_seat,
            "seat_rates": seat_rates,
            "avg_winner_score": sum(
                g["final_scores"][0]["total"] for g in games if g["final_scores"]
            ) / len(games),
        }

    answers["q8_scaling"] = {
        "3p": scaling_stats(results["deep_3p"], 3),
        "4p": scaling_stats(results["deep_4p"], 4),
        "5p": scaling_stats(results["deep_5p"], 5),
    }

    # ── Q9: Play time distribution ─────────────────────────────────
    # Estimate minutes from turns (assume ~20 seconds per turn in real play)
    SEC_PER_TURN = 20
    for label, games in [("4p", results["deep_4p"]), ("3p", results["deep_3p"]),
                          ("5p", results["deep_5p"])]:
        turns = [g["turns"] for g in games]
        minutes = [t * SEC_PER_TURN / 60 for t in turns]
        answers[f"q9_playtime_{label}"] = {
            "avg_minutes": sum(minutes) / len(minutes),
            "min_minutes": min(minutes),
            "max_minutes": max(minutes),
            "pct_under_15": sum(1 for m in minutes if m <= 15) / len(minutes),
            "pct_under_20": sum(1 for m in minutes if m <= 20) / len(minutes),
            "pct_over_25": sum(1 for m in minutes if m > 25) / len(minutes),
        }

    # ── Q10: Learning curve ────────────────────────────────────────
    # Compare expert vs beginner score distributions
    beginner_wins_total = 0
    for g in results["beginners"]:
        if g["final_scores"]:
            beginner_wins_total += 1  # just counting total games

    # Bucket beginner games into windows to see if win rates "stabilize"
    window = 50
    beginner_turns = results["beginners"]
    beginner_windows = []
    for start in range(0, len(beginner_turns), window):
        chunk = beginner_turns[start:start+window]
        if not chunk:
            break
        avg_score = sum(
            g["final_scores"][0]["total"] for g in chunk if g["final_scores"]
        ) / len(chunk)
        avg_turns = sum(g["turns"] for g in chunk) / len(chunk)
        beginner_windows.append({
            "games": f"{start+1}-{start+len(chunk)}",
            "avg_winner_score": avg_score,
            "avg_turns": avg_turns,
        })

    answers["q10_learning"] = {
        "expert_vs_beginner_win_rate": answers["q6_agency"]["expert_win_rate"],
        "skill_advantage": answers["q6_agency"]["score_advantage"],
        "beginner_windows": beginner_windows,
    }

    # ── Q11: Dominant strategy ─────────────────────────────────────
    answers["q11_dominant"] = {
        "style_win_rates": answers["q2_style_win_rates"],
        "best_style": max(answers["q2_style_win_rates"], key=answers["q2_style_win_rates"].get),
        "worst_style": min(answers["q2_style_win_rates"], key=answers["q2_style_win_rates"].get),
        "spread": (
            max(answers["q2_style_win_rates"].values()) -
            min(answers["q2_style_win_rates"].values())
        ),
    }

    # Is there a dominant first action?
    # Track what the winners did differently
    winner_action_dist = defaultdict(int)
    loser_action_dist = defaultdict(int)
    for g in results["style_games"]:
        for pid_str, actions in g["actions_by_style"].items():
            for action, count in actions.items():
                # This is by style, not by win/loss — let's use deep_4p instead
                pass

    for g in results["deep_4p"]:
        if g["final_scores"]:
            winner_pid = g["final_scores"][0]["pid"]
            for i, drafted in enumerate(g["drafted_own_faction"]):
                total = g["drafted_total"][i]
                if i == winner_pid:
                    answers.setdefault("q11_draft", {}).setdefault("winner_own_pct", []).append(
                        drafted / max(total, 1)
                    )
                else:
                    answers.setdefault("q11_draft", {}).setdefault("loser_own_pct", []).append(
                        drafted / max(total, 1)
                    )

    if "q11_draft" in answers:
        w = answers["q11_draft"]["winner_own_pct"]
        l = answers["q11_draft"]["loser_own_pct"]
        answers["q11_draft"]["avg_winner_own_faction_pct"] = sum(w) / max(len(w), 1)
        answers["q11_draft"]["avg_loser_own_faction_pct"] = sum(l) / max(len(l), 1)
        del answers["q11_draft"]["winner_own_pct"]
        del answers["q11_draft"]["loser_own_pct"]

    return answers


# ═══════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Deep Analysis for Mystery Mascots")
    parser.add_argument("-n", "--num-games", type=int, default=500)
    parser.add_argument("--config", type=str, default=None)
    parser.add_argument("--json", type=str, default=None)
    args = parser.parse_args()

    config = load_config(args.config)

    print("Running deep analysis (6 batches)...", file=sys.stderr)
    results = run_all_analyses(config, n_games=args.num_games, verbose=True)

    print("Analyzing results...", file=sys.stderr)
    answers = answer_questions(results)

    if args.json:
        with open(args.json, 'w') as f:
            json.dump(answers, f, indent=2, default=str)
        print(f"Answers saved to {args.json}")
    else:
        print(json.dumps(answers, indent=2, default=str))
