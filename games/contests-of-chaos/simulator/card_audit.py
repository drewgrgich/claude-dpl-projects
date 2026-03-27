"""Card Audit Tool — rank every Event and Playbook by game impact to guide deck culling.

Three analysis modes:
  1. Per-card report:  completion rates, avg turn, faction demand, "pressure valve" frequency
  2. Redundancy:       cluster events by faction requirements, flag overlapping groups
  3. Leave-one-out:    remove each card, re-run batch, measure delta on game quality metrics

Usage:
  python card_audit.py                          # full audit, 100 games per test
  python card_audit.py --games 200              # more games for tighter stats
  python card_audit.py --mode report            # per-card report only (fast)
  python card_audit.py --mode redundancy        # redundancy analysis only (instant)
  python card_audit.py --mode leave-one-out     # leave-one-out only (slow)
  python card_audit.py --target-events 30       # rank events with a keep/cut line at 30
  python card_audit.py --target-playbooks 20    # rank playbooks with a keep/cut line at 20
  python card_audit.py --json card_audit.json   # save full results as JSON
"""

import argparse
import json
import os
import sys
import time
from collections import Counter, defaultdict
from typing import List, Dict, Tuple, Optional

from cards import RecruitCard, EventCard, PlaybookCard, Deck, build_recruit_deck
from event_parser import load_events_csv, load_playbooks_csv
from event_checker import find_completable_events
from game_state import GameState, Player
from ai_player import HeuristicAI
from run_simulation import run_single_game


# ── Per-Card Report ──────────────────────────────────────────────────

def run_per_card_report(config: dict, events: List[EventCard],
                        playbooks: List[PlaybookCard], num_games: int,
                        num_players: int, seed: int = 1) -> dict:
    """Run a batch of games and collect granular per-card statistics."""

    event_stats = {e.name: {
        "name": e.name,
        "tier": e.tier,
        "vp": e.vp,
        "raw_requirements": e.raw_requirements,
        "reward": e.reward,
        "times_completed": 0,
        "completion_turns": [],       # which turn number it was completed
        "completed_by_player": Counter(),
        "times_on_jumbotron": 0,      # how many games it appeared on the Jumbotron
        "times_only_option": 0,       # completed when it was the ONLY completable event
        "factions_demanded": set(),
    } for e in events}

    # Pre-compute faction demand
    for e in events:
        req = e.requirements
        if "factions" in req:
            for f in req["factions"]:
                event_stats[e.name]["factions_demanded"].add(f)
        if "any_factions" in req:
            event_stats[e.name]["factions_demanded"] = {"ANY"}

    playbook_stats = {pb.name: {
        "name": pb.name,
        "category": pb.category,
        "vp": pb.vp,
        "trigger": pb.trigger,
        "timing": pb.timing,
        "times_drafted": 0,
        "times_scored": 0,
        "total_vp_contributed": 0,
    } for pb in playbooks}

    start = time.time()
    for i in range(num_games):
        _run_tracked_game(config, events, playbooks, num_players,
                          seed + i, event_stats, playbook_stats)
        if (i + 1) % 25 == 0:
            elapsed = time.time() - start
            print(f"  ... {i+1}/{num_games} games ({elapsed:.1f}s)")

    elapsed = time.time() - start
    print(f"Per-card report: {num_games} games in {elapsed:.1f}s\n")

    # Compute derived metrics
    for name, s in event_stats.items():
        s["completion_rate"] = s["times_completed"] / num_games
        s["avg_completion_turn"] = (
            sum(s["completion_turns"]) / len(s["completion_turns"])
            if s["completion_turns"] else None
        )
        s["pressure_valve_rate"] = (
            s["times_only_option"] / s["times_completed"]
            if s["times_completed"] > 0 else 0
        )
        # Convert set to list for JSON
        s["factions_demanded"] = sorted(s["factions_demanded"])
        # Remove raw turn list from output (can be huge)
        del s["completion_turns"]
        # Convert Counter to dict
        s["completed_by_player"] = dict(s["completed_by_player"])

    for name, s in playbook_stats.items():
        s["draft_rate"] = s["times_drafted"] / num_games
        s["score_rate"] = s["times_scored"] / num_games
        s["score_given_draft"] = (
            s["times_scored"] / s["times_drafted"]
            if s["times_drafted"] > 0 else 0
        )

    return {"events": event_stats, "playbooks": playbook_stats}


def _run_tracked_game(config, events, playbooks, num_players, seed,
                      event_stats, playbook_stats):
    """Run one game with detailed per-card tracking."""
    game = GameState(config, num_players, seed=seed,
                     events=events, playbooks=playbooks,
                     use_playbooks=len(playbooks) > 0)

    ais = []
    for i in range(num_players):
        aggression = 0.3 + (i * 0.2)
        ais.append(HeuristicAI(aggression=min(aggression, 0.9)))

    def keep_fn(player, dealt, gs):
        return ais[player.id].choose_starting_hand(player, dealt, gs)

    def playbook_fn(player, options, gs):
        chosen_keep, chosen_disc = ais[player.id].choose_playbook(player, options, gs)
        # Track drafts
        if chosen_keep.name in playbook_stats:
            playbook_stats[chosen_keep.name]["times_drafted"] += 1
        return chosen_keep, chosen_disc

    game.setup_with_choices(keep_fn=keep_fn, playbook_fn=playbook_fn)

    turn_count = 0
    max_turns = 200

    while not game.game_over and turn_count < max_turns:
        player = game.get_current_player()
        ai = ais[player.id]

        action = ai.choose_action(player, game)
        action_type = action["type"]
        result = {"success": False}

        if action_type == "complete_event":
            # Check if this was the only completable event
            completable = find_completable_events(player.hand, game.jumbotron)
            only_option = len(completable) == 1

            result = game.action_complete_event(
                player, action["event_index"], action["card_indices"])

            if result["success"]:
                ev = result["event"]
                if ev.name in event_stats:
                    event_stats[ev.name]["times_completed"] += 1
                    event_stats[ev.name]["completion_turns"].append(turn_count)
                    event_stats[ev.name]["completed_by_player"][player.id] += 1
                    if only_option:
                        event_stats[ev.name]["times_only_option"] += 1
                _resolve_reward_simple(game, player, ev.reward)

        elif action_type == "recruit_lineup":
            result = game.action_recruit_lineup(player, action["slot"])

        elif action_type == "scramble":
            result = game.action_scramble(player)

        elif action_type == "wipe_jumbotron":
            result = game.action_wipe_jumbotron(player,
                                                target_indices=action.get("target_indices"))
            if result["success"]:
                post_wipe_cost = game.rules.get("wipe_jumbotron", {}).get("post_wipe_event_cost", 0)
                completable = find_completable_events(player.hand, game.jumbotron)
                if completable and player.shinies >= post_wipe_cost:
                    completable.sort(key=lambda x: -x[0].vp)
                    event, cards = completable[0]
                    event_idx = game.jumbotron.index(event)
                    card_indices = [player.hand.index(c) for c in cards]
                    ev_result = game.action_complete_event(player, event_idx, card_indices)
                    if ev_result["success"]:
                        ev = ev_result["event"]
                        if ev.name in event_stats:
                            event_stats[ev.name]["times_completed"] += 1
                            event_stats[ev.name]["completion_turns"].append(turn_count)
                            event_stats[ev.name]["completed_by_player"][player.id] += 1
                        _resolve_reward_simple(game, player, ev.reward)

        elif action_type == "timeout":
            result = game.action_timeout(
                player,
                discard_indices=action.get("discard_indices"),
                flush_jumbotron=action.get("flush_jumbotron", False))

        if not result.get("success"):
            game.action_timeout(player)

        eot = game.end_of_turn(player)

        # Track playbook scoring
        if eot.get("playbook_scored"):
            pb = eot["playbook_scored"]
            if pb.name in playbook_stats:
                playbook_stats[pb.name]["times_scored"] += 1
                playbook_stats[pb.name]["total_vp_contributed"] += pb.vp

        game.advance_turn()
        turn_count += 1
        if game.check_game_over():
            game.game_over = True


def _resolve_reward_simple(game, player, reward_text):
    """Minimal reward resolution (mirrors run_simulation.py)."""
    import re
    reward = reward_text.lower()
    if "shini" in reward:
        match = re.search(r'(\d+)\s*shini', reward)
        if match:
            amount = int(match.group(1))
            if "from the bank" in reward or "take" in reward:
                game.resolve_reward_shinies(player, amount)
    if "free scramble" in reward or "perform one free scramble" in reward:
        game.resolve_reward_scramble(player)
    if "draw" in reward and "recruit" in reward:
        draw_match = re.search(r'draw\s*(?:top\s*)?(\d+)', reward)
        keep_match = re.search(r'keep\s*(\d+)', reward)
        if draw_match and keep_match:
            game.resolve_reward_draw(player, int(draw_match.group(1)), int(keep_match.group(1)))
    if "draft lineup slot 2" in reward:
        game.resolve_reward_free_lineup_draft(player, 1)
    if "look" in reward and "stands" in reward:
        if game.stands.size > 0:
            card = game.stands.cards[0]
            game.stands.cards.pop(0)
            player.hand.append(card)


# ── Redundancy Analysis ──────────────────────────────────────────────

def analyze_redundancy(events: List[EventCard]) -> dict:
    """Cluster events by their faction requirements and flag redundant groups."""

    # Build a signature for each event based on what it demands
    clusters = defaultdict(list)
    for e in events:
        sig = _faction_signature(e)
        clusters[sig].append(e)

    redundancy_groups = {}
    group_id = 0
    for sig, group in sorted(clusters.items(), key=lambda x: -len(x[1])):
        if len(group) >= 2:
            redundancy_groups[f"group_{group_id}"] = {
                "signature": sig,
                "count": len(group),
                "events": [
                    {"name": e.name, "tier": e.tier, "vp": e.vp,
                     "requirements": e.raw_requirements}
                    for e in sorted(group, key=lambda e: (e.tier, e.vp))
                ],
                "note": _redundancy_note(group),
            }
            group_id += 1

    # Also find events with unique signatures (no overlap)
    unique_events = []
    for sig, group in clusters.items():
        if len(group) == 1:
            e = group[0]
            unique_events.append({
                "name": e.name, "tier": e.tier, "vp": e.vp,
                "signature": sig
            })

    return {
        "redundancy_groups": redundancy_groups,
        "unique_events": sorted(unique_events, key=lambda x: x["tier"]),
        "total_groups": len(redundancy_groups),
        "total_unique": len(unique_events),
    }


def _faction_signature(event: EventCard) -> str:
    """Build a string signature describing what an event demands."""
    req = event.requirements
    parts = []

    if "factions" in req:
        for f, c in sorted(req["factions"].items()):
            parts.append(f"{c}x{f}")

    if "any_factions" in req:
        parts.append(f"{req['any_factions']}diff")

    if "free_agent_count" in req:
        parts.append(f"{req['free_agent_count']}FA")

    if "run_length" in req:
        parts.append(f"run{req['run_length']}")

    if "same_number" in req:
        parts.append(f"set{req['same_number']}")

    if "sum_min" in req:
        parts.append(f"sum>={req['sum_min']}")

    if "sum_max" in req:
        parts.append(f"sum<={req['sum_max']}")

    if "card_count" in req and not any(k in req for k in ["factions", "any_factions", "run_length", "same_number"]):
        parts.append(f"{req['card_count']}cards")

    return "+".join(parts) if parts else "unknown"


def _redundancy_note(group: List[EventCard]) -> str:
    """Generate a human-readable note about a redundancy group."""
    tiers = [e.tier for e in group]
    vps = [e.vp for e in group]

    if len(set(tiers)) == 1:
        return (f"All Tier {tiers[0]}. Same faction demand, VP range {min(vps)}-{max(vps)}. "
                f"Consider cutting the lower-VP card if completion rates are similar.")
    else:
        return (f"Tiers {min(tiers)}-{max(tiers)}, VP {min(vps)}-{max(vps)}. "
                f"Provides natural progression within this faction combo. "
                f"Cut candidates are low-VP entries with similar completion rates to higher ones.")


# ── Leave-One-Out Analysis ───────────────────────────────────────────

def run_leave_one_out(config: dict, events: List[EventCard],
                      playbooks: List[PlaybookCard], num_games: int,
                      num_players: int, seed: int = 1) -> dict:
    """Remove each event/playbook one at a time and measure game quality delta."""

    print("Running baseline batch...")
    baseline = _run_quality_batch(config, events, playbooks, num_games, num_players, seed)
    print(f"  Baseline: {baseline['avg_turns']:.1f} turns, "
          f"{baseline['avg_stagnation']:.1f} stag, "
          f"{baseline['win_spread']:.3f} spread, "
          f"{baseline['avg_total_vp']:.1f} VP\n")

    event_deltas = {}
    total_events = len(events)

    print(f"Testing {total_events} events (leave-one-out)...")
    for i, event in enumerate(events):
        reduced = [e for e in events if e.name != event.name]
        result = _run_quality_batch(config, reduced, playbooks, num_games, num_players, seed)
        delta = _compute_delta(baseline, result)
        event_deltas[event.name] = {
            "tier": event.tier,
            "vp": event.vp,
            "requirements": event.raw_requirements,
            "delta_turns": delta["delta_turns"],
            "delta_stagnation": delta["delta_stagnation"],
            "delta_win_spread": delta["delta_win_spread"],
            "delta_total_vp": delta["delta_total_vp"],
            "impact_score": delta["impact_score"],
            "verdict": delta["verdict"],
        }
        if (i + 1) % 5 == 0:
            print(f"  ... {i+1}/{total_events} events tested")

    playbook_deltas = {}
    total_pb = len(playbooks)

    if total_pb > 0:
        print(f"\nTesting {total_pb} playbooks (leave-one-out)...")
        for i, pb in enumerate(playbooks):
            reduced = [p for p in playbooks if p.name != pb.name]
            result = _run_quality_batch(config, events, reduced, num_games, num_players, seed)
            delta = _compute_delta(baseline, result)
            playbook_deltas[pb.name] = {
                "vp": pb.vp,
                "trigger": pb.trigger,
                "timing": pb.timing,
                "delta_turns": delta["delta_turns"],
                "delta_stagnation": delta["delta_stagnation"],
                "delta_win_spread": delta["delta_win_spread"],
                "delta_total_vp": delta["delta_total_vp"],
                "impact_score": delta["impact_score"],
                "verdict": delta["verdict"],
            }
            if (i + 1) % 5 == 0:
                print(f"  ... {i+1}/{total_pb} playbooks tested")

    return {
        "baseline": baseline,
        "event_deltas": event_deltas,
        "playbook_deltas": playbook_deltas,
    }


def _run_quality_batch(config, events, playbooks, num_games, num_players, seed) -> dict:
    """Run a batch and extract key quality metrics."""
    turns_list = []
    stag_list = []
    win_counter = Counter()
    vp_totals = []

    for i in range(num_games):
        stats = run_single_game(config, events, playbooks, num_players,
                                seed=seed + i, max_turns=200, verbose=False)
        turns_list.append(stats["turns"])
        stag_list.append(stats["stagnation_turns"])
        win_counter[stats["winner"]] += 1
        for pd in stats["player_details"]:
            vp_totals.append(pd["total_vp"])

    n = num_games
    win_rates = [win_counter.get(i, 0) / n for i in range(num_players)]
    win_spread = max(win_rates) - min(win_rates)

    return {
        "avg_turns": sum(turns_list) / n,
        "avg_stagnation": sum(stag_list) / n,
        "win_spread": win_spread,
        "avg_total_vp": sum(vp_totals) / len(vp_totals) if vp_totals else 0,
        "aborted": sum(1 for t in turns_list if t >= 200),
    }


def _compute_delta(baseline: dict, result: dict) -> dict:
    """Compute quality delta between baseline and a leave-one-out run."""
    dt = result["avg_turns"] - baseline["avg_turns"]
    ds = result["avg_stagnation"] - baseline["avg_stagnation"]
    dw = result["win_spread"] - baseline["win_spread"]
    dv = result["avg_total_vp"] - baseline["avg_total_vp"]

    # Impact score: positive = removing this card HURT the game (card is valuable)
    #               negative = removing this card HELPED (card is a cut candidate)
    # Weights: stagnation increase is bad, longer games mildly bad, wider spread bad
    impact = -(ds * 3.0 + dt * 0.5 + dw * 10.0)

    if impact > 2.0:
        verdict = "KEEP — removal hurts game quality"
    elif impact > 0.5:
        verdict = "LEAN KEEP — slight negative impact if removed"
    elif impact > -0.5:
        verdict = "NEUTRAL — minimal impact either way"
    elif impact > -2.0:
        verdict = "LEAN CUT — slight improvement if removed"
    else:
        verdict = "CUT — removal improves game quality"

    return {
        "delta_turns": round(dt, 2),
        "delta_stagnation": round(ds, 2),
        "delta_win_spread": round(dw, 4),
        "delta_total_vp": round(dv, 2),
        "impact_score": round(impact, 2),
        "verdict": verdict,
    }


# ── Composite Ranking ────────────────────────────────────────────────

def compute_composite_rank(report_data: dict, loo_data: dict,
                           redundancy_data: dict,
                           target_events: Optional[int] = None,
                           target_playbooks: Optional[int] = None) -> dict:
    """Combine all analyses into a single ranked keep/cut recommendation."""

    # Build redundancy penalty map: events in large groups get a penalty
    redundancy_penalty = {}
    for gid, group in redundancy_data.get("redundancy_groups", {}).items():
        size = group["count"]
        for ev in group["events"]:
            # Larger groups = more redundancy = higher penalty
            redundancy_penalty[ev["name"]] = (size - 1) * 1.5

    # Score each event
    event_rankings = []
    for name, stats in report_data.get("events", {}).items():
        score = 0

        # Completion rate is the strongest signal (0–1 range, scaled to 0–10)
        score += stats["completion_rate"] * 10.0

        # Pressure valve bonus: events that are often the only option are critical
        score += stats["pressure_valve_rate"] * 3.0

        # Tier diversity bonus: higher tiers are rarer and more important
        score += stats["tier"] * 0.5

        # VP weighting: higher VP events carry more game impact
        score += stats["vp"] * 0.3

        # Leave-one-out impact (if available)
        if loo_data and name in loo_data.get("event_deltas", {}):
            impact = loo_data["event_deltas"][name]["impact_score"]
            score += impact * 1.0

        # Redundancy penalty
        score -= redundancy_penalty.get(name, 0)

        # Never-completed penalty
        if stats["times_completed"] == 0:
            score -= 5.0

        event_rankings.append({
            "name": name,
            "tier": stats["tier"],
            "vp": stats["vp"],
            "completion_rate": round(stats["completion_rate"], 3),
            "pressure_valve": round(stats["pressure_valve_rate"], 3),
            "redundancy_penalty": redundancy_penalty.get(name, 0),
            "loo_impact": (loo_data["event_deltas"][name]["impact_score"]
                           if loo_data and name in loo_data.get("event_deltas", {}) else None),
            "composite_score": round(score, 2),
        })

    event_rankings.sort(key=lambda x: -x["composite_score"])

    # Apply keep/cut line
    if target_events:
        for i, e in enumerate(event_rankings):
            e["recommendation"] = "KEEP" if i < target_events else "CUT"

    # Score each playbook
    playbook_rankings = []
    for name, stats in report_data.get("playbooks", {}).items():
        score = 0

        # Score rate is the primary signal
        score += stats["score_rate"] * 10.0

        # Score-given-draft: does this playbook actually fire when chosen?
        score += stats["score_given_draft"] * 5.0

        # VP value
        score += stats["vp"] * 0.4

        # Draft popularity
        score += stats["draft_rate"] * 2.0

        # LOO impact
        if loo_data and name in loo_data.get("playbook_deltas", {}):
            impact = loo_data["playbook_deltas"][name]["impact_score"]
            score += impact * 1.0

        # Never-scored penalty
        if stats["times_scored"] == 0:
            score -= 5.0

        playbook_rankings.append({
            "name": name,
            "vp": stats["vp"],
            "trigger": stats["trigger"],
            "draft_rate": round(stats["draft_rate"], 3),
            "score_rate": round(stats["score_rate"], 3),
            "score_given_draft": round(stats["score_given_draft"], 3),
            "loo_impact": (loo_data["playbook_deltas"][name]["impact_score"]
                           if loo_data and name in loo_data.get("playbook_deltas", {}) else None),
            "composite_score": round(score, 2),
        })

    playbook_rankings.sort(key=lambda x: -x["composite_score"])

    if target_playbooks:
        for i, pb in enumerate(playbook_rankings):
            pb["recommendation"] = "KEEP" if i < target_playbooks else "CUT"

    return {
        "event_rankings": event_rankings,
        "playbook_rankings": playbook_rankings,
    }


# ── Report Printer ───────────────────────────────────────────────────

def print_report(report_data: dict, redundancy_data: dict,
                 loo_data: dict, rankings: dict,
                 target_events: Optional[int], target_playbooks: Optional[int]):
    """Print a comprehensive human-readable audit report."""

    print("\n" + "=" * 78)
    print("  CONTESTS OF CHAOS — CARD AUDIT REPORT")
    print("=" * 78)

    # ── Event Rankings ──
    print(f"\n{'EVENT RANKINGS':─<78}")
    if target_events:
        print(f"  Target: keep {target_events} events out of {len(rankings['event_rankings'])}\n")

    header = f"  {'Rank':>4}  {'Event':<30} {'Tier':>4} {'VP':>3} {'Comp%':>6} {'PV%':>5} {'LOO':>6} {'Score':>6}"
    if target_events:
        header += f"  {'Rec':>4}"
    print(header)
    print("  " + "─" * (len(header) - 2))

    for i, e in enumerate(rankings["event_rankings"]):
        loo_str = f"{e['loo_impact']:+.1f}" if e["loo_impact"] is not None else "  n/a"
        line = (f"  {i+1:>4}  {e['name']:<30} {e['tier']:>4} {e['vp']:>3} "
                f"{e['completion_rate']:>5.1%} {e['pressure_valve']:>5.1%} "
                f"{loo_str:>6} {e['composite_score']:>6.1f}")
        if target_events:
            rec = e.get("recommendation", "")
            marker = " ✅" if rec == "KEEP" else " ❌" if rec == "CUT" else ""
            line += f"  {marker}"
        print(line)

    # ── Playbook Rankings ──
    print(f"\n{'PLAYBOOK RANKINGS':─<78}")
    if target_playbooks:
        print(f"  Target: keep {target_playbooks} playbooks out of {len(rankings['playbook_rankings'])}\n")

    header = f"  {'Rank':>4}  {'Playbook':<28} {'VP':>3} {'Draft%':>6} {'Score%':>7} {'If Drafted':>10} {'LOO':>6} {'Score':>6}"
    if target_playbooks:
        header += f"  {'Rec':>4}"
    print(header)
    print("  " + "─" * (len(header) - 2))

    for i, pb in enumerate(rankings["playbook_rankings"]):
        loo_str = f"{pb['loo_impact']:+.1f}" if pb["loo_impact"] is not None else "  n/a"
        line = (f"  {i+1:>4}  {pb['name']:<28} {pb['vp']:>3} "
                f"{pb['draft_rate']:>5.1%} {pb['score_rate']:>6.1%} "
                f"{pb['score_given_draft']:>9.1%} "
                f"{loo_str:>6} {pb['composite_score']:>6.1f}")
        if target_playbooks:
            rec = pb.get("recommendation", "")
            marker = " ✅" if rec == "KEEP" else " ❌" if rec == "CUT" else ""
            line += f"  {marker}"
        print(line)

    # ── Redundancy Groups ──
    if redundancy_data["total_groups"] > 0:
        print(f"\n{'FACTION REDUNDANCY GROUPS':─<78}")
        print(f"  {redundancy_data['total_groups']} groups found, "
              f"{redundancy_data['total_unique']} unique events\n")

        for gid, group in redundancy_data["redundancy_groups"].items():
            print(f"  [{group['signature']}] — {group['count']} events")
            for ev in group["events"]:
                # Find ranking for this event
                rank_info = next((r for r in rankings["event_rankings"]
                                  if r["name"] == ev["name"]), None)
                rank_str = ""
                if rank_info:
                    rank_num = rankings["event_rankings"].index(rank_info) + 1
                    rank_str = f" (ranked #{rank_num}, score {rank_info['composite_score']:.1f})"
                print(f"    • {ev['name']} (T{ev['tier']}, {ev['vp']}VP){rank_str}")
            print(f"    Note: {group['note']}")
            print()

    # ── Cut List Summary ──
    if target_events or target_playbooks:
        print(f"\n{'CUT LIST SUMMARY':─<78}")

        if target_events:
            cuts = [e for e in rankings["event_rankings"] if e.get("recommendation") == "CUT"]
            if cuts:
                print(f"\n  Events to cut ({len(cuts)}):")
                for e in cuts:
                    print(f"    ❌ {e['name']} (T{e['tier']}, {e['vp']}VP) — "
                          f"score {e['composite_score']:.1f}, completed {e['completion_rate']:.1%}")

        if target_playbooks:
            cuts = [pb for pb in rankings["playbook_rankings"] if pb.get("recommendation") == "CUT"]
            if cuts:
                print(f"\n  Playbooks to cut ({len(cuts)}):")
                for pb in cuts:
                    print(f"    ❌ {pb['name']} ({pb['vp']}VP) — "
                          f"score {pb['composite_score']:.1f}, scored {pb['score_rate']:.1%}")

        # Keep list
        if target_events:
            keeps = [e for e in rankings["event_rankings"] if e.get("recommendation") == "KEEP"]
            print(f"\n  Events to keep ({len(keeps)}):")
            for e in keeps:
                print(f"    ✅ {e['name']} (T{e['tier']}, {e['vp']}VP) — "
                      f"score {e['composite_score']:.1f}")

        if target_playbooks:
            keeps = [pb for pb in rankings["playbook_rankings"] if pb.get("recommendation") == "KEEP"]
            print(f"\n  Playbooks to keep ({len(keeps)}):")
            for pb in keeps:
                print(f"    ✅ {pb['name']} ({pb['vp']}VP) — "
                      f"score {pb['composite_score']:.1f}")

    print("\n" + "=" * 78)

    # ── Legend ──
    print("\nLEGEND:")
    print("  Comp%  = How often this event is completed across all games")
    print("  PV%    = Pressure Valve rate — how often it was the ONLY completable event")
    print("  LOO    = Leave-One-Out impact — positive means removing it hurts the game")
    print("  Score  = Composite ranking score (higher = more important to keep)")
    print("  Draft% = How often AIs chose this playbook during setup")
    print("  Score% = How often this playbook scored across all games")
    print("  If Drafted = Scoring rate when actually drafted (effectiveness)")
    print()


# ── CLI ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Card Audit — rank Events and Playbooks for deck culling")
    parser.add_argument("--games", type=int, default=100,
                        help="Games per batch (default: 100)")
    parser.add_argument("-p", "--players", type=int, default=3,
                        help="Number of players (default: 3)")
    parser.add_argument("-s", "--seed", type=int, default=1,
                        help="Starting seed (default: 1)")
    parser.add_argument("--mode", choices=["full", "report", "redundancy", "leave-one-out"],
                        default="full",
                        help="Analysis mode (default: full)")
    parser.add_argument("--target-events", type=int, default=None,
                        help="Number of events to keep (marks rest as CUT)")
    parser.add_argument("--target-playbooks", type=int, default=None,
                        help="Number of playbooks to keep (marks rest as CUT)")
    parser.add_argument("--config", type=str, default=None,
                        help="Path to config.json")
    parser.add_argument("--events", type=str, default=None,
                        help="Path to events CSV")
    parser.add_argument("--playbooks", type=str, default=None,
                        help="Path to playbooks CSV")
    parser.add_argument("--json", type=str, default=None,
                        help="Save full results to JSON")

    args = parser.parse_args()

    # File resolution (same logic as run_simulation.py)
    sim_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(sim_dir)

    config_path = args.config or os.path.join(sim_dir, "config.json")
    with open(config_path, 'r') as f:
        config = json.load(f)

    events_path = args.events
    if not events_path:
        for c in [os.path.join(parent_dir, "contests-of-chaos-events copy.csv"),
                  os.path.join(parent_dir, "contests-of-chaos-events.csv")]:
            if os.path.exists(c):
                events_path = c
                break

    playbooks_path = args.playbooks
    if not playbooks_path:
        for c in [os.path.join(parent_dir, "contests-of-chaos-playbooks copy.csv"),
                  os.path.join(parent_dir, "contests-of-chaos-playbooks.csv")]:
            if os.path.exists(c):
                playbooks_path = c
                break

    events = load_events_csv(events_path) if events_path else []
    playbooks = load_playbooks_csv(playbooks_path) if playbooks_path and os.path.exists(playbooks_path) else []

    print(f"Loaded {len(events)} events, {len(playbooks)} playbooks")
    print(f"Mode: {args.mode} | Games: {args.games} | Players: {args.players}\n")

    # ── Run analyses ──
    report_data = {}
    redundancy_data = {"redundancy_groups": {}, "unique_events": [], "total_groups": 0, "total_unique": 0}
    loo_data = {}

    if args.mode in ("full", "report"):
        print("─" * 40)
        print("PHASE 1: Per-Card Report")
        print("─" * 40)
        report_data = run_per_card_report(
            config, events, playbooks, args.games, args.players, args.seed)

    if args.mode in ("full", "redundancy"):
        print("─" * 40)
        print("PHASE 2: Redundancy Analysis")
        print("─" * 40)
        redundancy_data = analyze_redundancy(events)
        print(f"  Found {redundancy_data['total_groups']} redundancy groups, "
              f"{redundancy_data['total_unique']} unique events\n")

    if args.mode in ("full", "leave-one-out"):
        print("─" * 40)
        print("PHASE 3: Leave-One-Out Testing")
        print("─" * 40)
        loo_data = run_leave_one_out(
            config, events, playbooks, args.games, args.players, args.seed)

    # ── Composite Ranking ──
    rankings = compute_composite_rank(
        report_data, loo_data, redundancy_data,
        target_events=args.target_events,
        target_playbooks=args.target_playbooks)

    # ── Print Report ──
    print_report(report_data, redundancy_data, loo_data, rankings,
                 args.target_events, args.target_playbooks)

    # ── Save JSON ──
    if args.json:
        output = {
            "config": {
                "games": args.games,
                "players": args.players,
                "seed": args.seed,
                "mode": args.mode,
                "target_events": args.target_events,
                "target_playbooks": args.target_playbooks,
            },
            "report": report_data,
            "redundancy": redundancy_data,
            "leave_one_out": loo_data,
            "rankings": rankings,
        }
        # Make JSON-serializable
        json_str = json.dumps(output, default=str, indent=2)
        output_path = args.json
        if not os.path.isabs(output_path):
            output_path = os.path.join(parent_dir, output_path)
        with open(output_path, 'w') as f:
            f.write(json_str)
        print(f"Full results saved to: {output_path}")


if __name__ == "__main__":
    main()
