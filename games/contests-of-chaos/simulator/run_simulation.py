"""Run multiple Contests of Chaos games and collect balance statistics."""

import json
import os
import sys
import time
import argparse
from collections import Counter, defaultdict
from typing import List, Dict

from cards import RecruitCard, EventCard, PlaybookCard, Deck, build_recruit_deck
from event_parser import load_events_csv, load_playbooks_csv
from event_checker import find_completable_events
from game_state import GameState, Player
from ai_player import HeuristicAI


# ── Single Game Runner ────────────────────────────────────────────────

def run_single_game(config: dict, events: List[EventCard], playbooks: List[PlaybookCard],
                    num_players: int, seed: int, max_turns: int = 200,
                    verbose: bool = False,
                    player_configs: list = None) -> dict:
    """Run one complete game and return statistics.

    Returns a dict with per-game stats including winner, VP scores,
    action counts, event completions, game length, and stagnation data.
    """
    game = GameState(config, num_players, seed=seed,
                     events=events, playbooks=playbooks,
                     use_playbooks=len(playbooks) > 0)

    # Create AI players
    ais = []
    for i in range(num_players):
        if player_configs and i < len(player_configs):
            pc = player_configs[i]
            ais.append(HeuristicAI(
                aggression=pc.get("aggression", 0.3 + i * 0.2),
                skill=pc.get("skill", 1.0),
                style=pc.get("style", "balanced"),
                rng_seed=seed + i * 1000,
            ))
        else:
            aggression = 0.3 + (i * 0.2)
            ais.append(HeuristicAI(aggression=min(aggression, 0.9),
                                   rng_seed=seed + i * 1000))

    # Setup with AI choices
    def keep_fn(player, dealt, gs):
        return ais[player.id].choose_starting_hand(player, dealt, gs)

    def playbook_fn(player, options, gs):
        return ais[player.id].choose_playbook(player, options, gs)

    game.setup_with_choices(keep_fn=keep_fn, playbook_fn=playbook_fn)

    # Tracking
    action_counts = defaultdict(lambda: defaultdict(int))  # player -> action -> count
    events_completed_by_tier = defaultdict(int)
    events_completed_by_name = Counter()
    wipe_count = 0
    stagnation_turns = 0  # turns where no one can complete anything
    max_stagnation_streak = 0
    current_stagnation = 0
    turns_to_first_event = None
    total_shinies_spent = defaultdict(int)
    total_shinies_earned = defaultdict(int)
    lineup_drafts_by_slot = Counter()

    turn_count = 0
    game_aborted = False

    while not game.game_over and turn_count < max_turns:
        player = game.get_current_player()
        ai = ais[player.id]

        # Get AI decision
        action = ai.choose_action(player, game)
        action_type = action["type"]
        action_counts[player.id][action_type] += 1

        # Execute action
        result = {"success": False}

        if action_type == "complete_event":
            result = game.action_complete_event(
                player, action["event_index"], action["card_indices"]
            )
            if result["success"]:
                ev = result["event"]
                events_completed_by_tier[ev.tier] += 1
                events_completed_by_name[ev.name] += 1
                if turns_to_first_event is None:
                    turns_to_first_event = turn_count
                current_stagnation = 0

                # Resolve rewards (simplified)
                _resolve_reward(game, player, ev.reward)

        elif action_type == "recruit_lineup":
            slot = action["slot"]
            result = game.action_recruit_lineup(player, slot)
            if result["success"]:
                lineup_drafts_by_slot[slot] += 1
                total_shinies_spent[player.id] += result["cost"]
                total_shinies_earned[player.id] += result["collected_shinies"]

        elif action_type == "scramble":
            result = game.action_scramble(player)
            if result["success"]:
                cost = game.rules["scramble_cost"][game.pkey]
                total_shinies_spent[player.id] += cost

        elif action_type == "wipe_jumbotron":
            result = game.action_wipe_jumbotron(player,
                                                target_indices=action.get("target_indices"))
            if result["success"]:
                wipe_count += 1
                total_shinies_spent[player.id] += result["cost"]

                # After wipe, AI may attempt to complete a new event (paying surcharge)
                post_wipe_cost = game.rules.get("wipe_jumbotron", {}).get("post_wipe_event_cost", 0)
                completable = find_completable_events(player.hand, game.jumbotron)
                if completable and player.shinies >= post_wipe_cost:
                    # Pick highest VP event
                    completable.sort(key=lambda x: -x[0].vp)
                    event, cards = completable[0]
                    event_idx = game.jumbotron.index(event)
                    card_indices = [player.hand.index(c) for c in cards]
                    ev_result = game.action_complete_event(
                        player, event_idx, card_indices
                    )
                    if ev_result["success"]:
                        action_counts[player.id]["post_wipe_complete"] += 1
                        ev = ev_result["event"]
                        events_completed_by_tier[ev.tier] += 1
                        events_completed_by_name[ev.name] += 1
                        if turns_to_first_event is None:
                            turns_to_first_event = turn_count
                        current_stagnation = 0
                        total_shinies_spent[player.id] += post_wipe_cost
                        _resolve_reward(game, player, ev.reward)

        elif action_type == "timeout":
            result = game.action_timeout(
                player,
                discard_indices=action.get("discard_indices"),
                flush_jumbotron=action.get("flush_jumbotron", False)
            )
            if result["success"]:
                total_shinies_earned[player.id] += game.rules["timeout_shiny_gain"]

        # If action failed, take timeout as fallback
        if not result.get("success"):
            result = game.action_timeout(player)
            action_counts[player.id]["timeout_fallback"] += 1
            total_shinies_earned[player.id] += game.rules["timeout_shiny_gain"]

        # End of turn
        eot = game.end_of_turn(player)

        # Track stagnation
        any_completable = False
        for p in game.players:
            if find_completable_events(p.hand, game.jumbotron):
                any_completable = True
                break
        if not any_completable:
            current_stagnation += 1
            stagnation_turns += 1
            max_stagnation_streak = max(max_stagnation_streak, current_stagnation)
        else:
            current_stagnation = 0

        # Advance
        game.advance_turn()
        turn_count += 1

        # Check game over
        if game.check_game_over():
            game.game_over = True

    if turn_count >= max_turns:
        game_aborted = True

    # Final results
    winner, standings = game.get_winner()

    # Build stats dict
    stats = {
        "seed": seed,
        "num_players": num_players,
        "turns": turn_count,
        "aborted": game_aborted,
        "winner": winner.id,
        "standings": standings,
        "action_counts": {pid: dict(ac) for pid, ac in action_counts.items()},
        "events_by_tier": dict(events_completed_by_tier),
        "events_by_name": dict(events_completed_by_name),
        "wipe_count": wipe_count,
        "stagnation_turns": stagnation_turns,
        "max_stagnation_streak": max_stagnation_streak,
        "turns_to_first_event": turns_to_first_event,
        "lineup_drafts_by_slot": dict(lineup_drafts_by_slot),
        "shinies_spent": dict(total_shinies_spent),
        "shinies_earned": dict(total_shinies_earned),
        "standing_ovation": game.standing_ovation_triggered,
        "player_details": [],
    }

    for p in game.players:
        stats["player_details"].append({
            "id": p.id,
            "event_vp": p.event_vp,
            "playbook_vp": p.playbook_vp,
            "shiny_bonus": p.shiny_bonus,
            "total_vp": p.total_vp,
            "events_completed": len(p.scored_events),
            "shinies_remaining": p.shinies,
            "hand_size": len(p.hand),
            "playbooks_scored": len(p.scored_playbooks),
        })

    if verbose:
        _print_game_summary(stats)

    return stats


def _resolve_reward(game: GameState, player: Player, reward_text: str):
    """Simplified reward resolution based on reward text."""
    reward = reward_text.lower()

    if "shini" in reward:
        # Extract number of shinies
        import re
        match = re.search(r'(\d+)\s*shini', reward)
        if match:
            amount = int(match.group(1))
            if "from the bank" in reward or "take" in reward:
                game.resolve_reward_shinies(player, amount)

    if "free scramble" in reward or "perform one free scramble" in reward:
        game.resolve_reward_scramble(player)

    if "draw" in reward and "recruit" in reward:
        import re
        draw_match = re.search(r'draw\s*(?:top\s*)?(\d+)', reward)
        keep_match = re.search(r'keep\s*(\d+)', reward)
        if draw_match and keep_match:
            game.resolve_reward_draw(player, int(draw_match.group(1)), int(keep_match.group(1)))

    if "draft lineup slot 2" in reward:
        game.resolve_reward_free_lineup_draft(player, 1)  # 0-indexed

    if "look" in reward and "stands" in reward:
        # Look at top 5 of Stands, take 1-2 — simplified: draw 1 from stands
        if game.stands.size > 0:
            card = game.stands.cards[0]
            game.stands.cards.pop(0)
            player.hand.append(card)


# ── Multi-Game Runner ─────────────────────────────────────────────────

def run_batch(config: dict, events: List[EventCard], playbooks: List[PlaybookCard],
              num_games: int, num_players: int, start_seed: int = 1,
              max_turns: int = 200, verbose: bool = False,
              player_configs: list = None) -> dict:
    """Run a batch of games and aggregate statistics."""
    all_stats = []
    start_time = time.time()

    for i in range(num_games):
        seed = start_seed + i
        stats = run_single_game(config, events, playbooks, num_players,
                                seed=seed, max_turns=max_turns, verbose=verbose,
                                player_configs=player_configs)
        all_stats.append(stats)

        if (i + 1) % 25 == 0:
            elapsed = time.time() - start_time
            print(f"  ... {i+1}/{num_games} games complete ({elapsed:.1f}s)")

    elapsed = time.time() - start_time
    print(f"\nCompleted {num_games} games in {elapsed:.1f}s")

    return aggregate_stats(all_stats, num_players)


def aggregate_stats(all_stats: List[dict], num_players: int) -> dict:
    """Aggregate per-game stats into a batch summary."""
    n = len(all_stats)
    if n == 0:
        return {}

    # Game length
    turns = [s["turns"] for s in all_stats]
    aborted = sum(1 for s in all_stats if s["aborted"])

    # Wins
    win_counts = Counter(s["winner"] for s in all_stats)

    # VP distributions
    vp_by_player = defaultdict(list)
    event_vp_by_player = defaultdict(list)
    playbook_vp_by_player = defaultdict(list)
    events_completed_by_player = defaultdict(list)

    for s in all_stats:
        for pd in s["player_details"]:
            pid = pd["id"]
            vp_by_player[pid].append(pd["total_vp"])
            event_vp_by_player[pid].append(pd["event_vp"])
            playbook_vp_by_player[pid].append(pd["playbook_vp"])
            events_completed_by_player[pid].append(pd["events_completed"])

    # Action frequency
    total_actions = defaultdict(lambda: defaultdict(int))
    for s in all_stats:
        for pid_str, actions in s["action_counts"].items():
            pid = int(pid_str) if isinstance(pid_str, str) else pid_str
            for action, count in actions.items():
                total_actions[pid][action] += count

    # Events by tier
    tier_totals = defaultdict(int)
    for s in all_stats:
        for tier, count in s["events_by_tier"].items():
            tier_totals[tier] += count

    # Events by name
    name_totals = Counter()
    for s in all_stats:
        for name, count in s["events_by_name"].items():
            name_totals[name] += count

    # Wipe stats
    wipe_counts = [s["wipe_count"] for s in all_stats]

    # Stagnation
    stag_turns = [s["stagnation_turns"] for s in all_stats]
    max_stag = [s["max_stagnation_streak"] for s in all_stats]

    # First event
    first_event_turns = [s["turns_to_first_event"] for s in all_stats
                         if s["turns_to_first_event"] is not None]

    # Lineup draft distribution
    slot_totals = Counter()
    for s in all_stats:
        for slot, count in s["lineup_drafts_by_slot"].items():
            slot_totals[slot] += count

    # Standing Ovation rate
    so_count = sum(1 for s in all_stats if s["standing_ovation"])

    summary = {
        "num_games": n,
        "num_players": num_players,
        "game_length": {
            "mean": sum(turns) / n,
            "min": min(turns),
            "max": max(turns),
            "median": sorted(turns)[n // 2],
            "aborted": aborted,
        },
        "wins": {i: win_counts.get(i, 0) for i in range(num_players)},
        "win_rates": {i: win_counts.get(i, 0) / n for i in range(num_players)},
        "vp_averages": {
            pid: {
                "total": sum(vps) / n,
                "event": sum(event_vp_by_player[pid]) / n,
                "playbook": sum(playbook_vp_by_player[pid]) / n,
                "events_completed": sum(events_completed_by_player[pid]) / n,
            }
            for pid, vps in vp_by_player.items()
        },
        "action_distribution": {
            pid: {a: c / n for a, c in actions.items()}
            for pid, actions in total_actions.items()
        },
        "events_by_tier": {
            t: {"total": c, "per_game": c / n}
            for t, c in sorted(tier_totals.items())
        },
        "most_completed_events": name_totals.most_common(10),
        "least_completed_events": name_totals.most_common()[-10:] if len(name_totals) >= 10 else [],
        "never_completed_events": [],  # Filled below
        "wipes": {
            "total": sum(wipe_counts),
            "per_game": sum(wipe_counts) / n,
            "games_with_wipe": sum(1 for w in wipe_counts if w > 0),
            "max_in_game": max(wipe_counts) if wipe_counts else 0,
        },
        "stagnation": {
            "avg_stagnation_turns": sum(stag_turns) / n,
            "avg_max_streak": sum(max_stag) / n,
            "worst_streak": max(max_stag) if max_stag else 0,
        },
        "first_event_turn": {
            "mean": sum(first_event_turns) / len(first_event_turns) if first_event_turns else None,
            "min": min(first_event_turns) if first_event_turns else None,
            "max": max(first_event_turns) if first_event_turns else None,
        },
        "lineup_draft_slots": dict(slot_totals),
        "standing_ovation_rate": so_count / n,
        "all_event_completions": dict(name_totals),
    }

    # Find events that were never completed
    all_event_names = set()
    for s in all_stats:
        all_event_names.update(s["events_by_name"].keys())
    # We'd need the full event list to find never-completed ones
    # For now, leave as the event names with 0 completions in name_totals
    # (This gets filled in the report)

    return summary


# ── Report Output ─────────────────────────────────────────────────────

def print_report(summary: dict, events: List[EventCard] = None):
    """Print a human-readable balance report."""
    print("\n" + "=" * 70)
    print("  CONTESTS OF CHAOS — PLAYTEST SIMULATION REPORT")
    print("=" * 70)

    gl = summary["game_length"]
    print(f"\n{'GAME LENGTH':─<40}")
    print(f"  Games played:    {summary['num_games']}")
    print(f"  Players/game:    {summary['num_players']}")
    print(f"  Avg turns:       {gl['mean']:.1f}")
    print(f"  Min / Max:       {gl['min']} / {gl['max']}")
    print(f"  Median:          {gl['median']}")
    print(f"  Aborted (hit max): {gl['aborted']}")

    print(f"\n{'WIN RATES':─<40}")
    for pid, rate in summary["win_rates"].items():
        wins = summary["wins"][pid]
        print(f"  Player {pid}: {rate:.1%}  ({wins}/{summary['num_games']})")

    print(f"\n{'VP AVERAGES PER PLAYER':─<40}")
    for pid, vp in sorted(summary["vp_averages"].items()):
        print(f"  P{pid}: Total={vp['total']:.1f}  Event={vp['event']:.1f}  "
              f"Playbook={vp['playbook']:.1f}  Events completed={vp['events_completed']:.1f}")

    print(f"\n{'ACTION FREQUENCY (per game avg)':─<40}")
    for pid, actions in sorted(summary["action_distribution"].items()):
        parts = ", ".join(f"{a}={c:.1f}" for a, c in sorted(actions.items()))
        print(f"  P{pid}: {parts}")

    print(f"\n{'EVENTS BY TIER (per game avg)':─<40}")
    for tier, data in sorted(summary["events_by_tier"].items()):
        print(f"  Tier {tier}: {data['per_game']:.2f}/game  ({data['total']} total)")

    print(f"\n{'TOP 10 MOST COMPLETED EVENTS':─<40}")
    for name, count in summary["most_completed_events"]:
        pg = count / summary["num_games"]
        print(f"  {name}: {count} ({pg:.2f}/game)")

    if summary["least_completed_events"]:
        print(f"\n{'BOTTOM 10 LEAST COMPLETED EVENTS':─<40}")
        for name, count in reversed(summary["least_completed_events"]):
            pg = count / summary["num_games"]
            print(f"  {name}: {count} ({pg:.2f}/game)")

    # Check for never-completed events
    if events:
        # Build full set of completed event names from the counter
        all_completed = set()
        for name, count in summary["most_completed_events"]:
            all_completed.add(name)
        for name, count in summary.get("least_completed_events", []):
            all_completed.add(name)
        # Also add any in-between that aren't in top/bottom 10
        if "all_event_completions" in summary:
            all_completed = set(summary["all_event_completions"].keys())

        never = [e.name for e in events if e.name not in all_completed]
        if never:
            print(f"\n{'NEVER COMPLETED EVENTS':─<40}")
            for name in never:
                print(f"  ⚠ {name}")

    print(f"\n{'JUMBOTRON WIPES':─<40}")
    w = summary["wipes"]
    print(f"  Total wipes:       {w['total']}")
    print(f"  Per game avg:      {w['per_game']:.2f}")
    print(f"  Games with ≥1 wipe: {w['games_with_wipe']}/{summary['num_games']}")
    print(f"  Max in single game: {w['max_in_game']}")

    print(f"\n{'STAGNATION (turns with no completable events for anyone)':─<40}")
    s = summary["stagnation"]
    print(f"  Avg stagnation turns/game: {s['avg_stagnation_turns']:.1f}")
    print(f"  Avg max streak/game:       {s['avg_max_streak']:.1f}")
    print(f"  Worst streak seen:         {s['worst_streak']}")

    fe = summary["first_event_turn"]
    if fe["mean"] is not None:
        print(f"\n{'FIRST EVENT COMPLETION':─<40}")
        print(f"  Avg turn:  {fe['mean']:.1f}")
        print(f"  Min / Max: {fe['min']} / {fe['max']}")

    print(f"\n{'LINEUP DRAFT DISTRIBUTION':─<40}")
    total_drafts = sum(summary["lineup_draft_slots"].values())
    for slot in range(4):
        count = summary["lineup_draft_slots"].get(slot, 0)
        pct = count / total_drafts * 100 if total_drafts else 0
        print(f"  Slot {slot+1}: {count} ({pct:.1f}%)")

    print(f"\n{'OTHER':─<40}")
    print(f"  Standing Ovation rate: {summary['standing_ovation_rate']:.1%}")

    print("\n" + "=" * 70)


def _print_game_summary(stats: dict):
    """Print summary of a single game."""
    print(f"\n--- Game (seed={stats['seed']}) ---")
    print(f"  Turns: {stats['turns']}  |  Aborted: {stats['aborted']}")
    print(f"  Winner: P{stats['winner']}")
    for pd in stats["player_details"]:
        print(f"  P{pd['id']}: {pd['total_vp']}VP "
              f"(E:{pd['event_vp']} PB:{pd['playbook_vp']} S:{pd['shiny_bonus']}) "
              f"Events:{pd['events_completed']}")
    print(f"  Wipes: {stats['wipe_count']}  |  Stagnation: {stats['stagnation_turns']}t "
          f"(max streak {stats['max_stagnation_streak']})")


# ── CLI Entry Point ───────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Contests of Chaos Playtest Simulator")
    parser.add_argument("-n", "--num-games", type=int, default=100,
                        help="Number of games to simulate (default: 100)")
    parser.add_argument("-p", "--players", type=int, default=3,
                        help="Number of players (2-4, default: 3)")
    parser.add_argument("-s", "--seed", type=int, default=1,
                        help="Starting random seed (default: 1)")
    parser.add_argument("--max-turns", type=int, default=200,
                        help="Max turns per game before aborting (default: 200)")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Print each game's summary")
    parser.add_argument("--config", type=str, default=None,
                        help="Path to config.json (default: auto-detect)")
    parser.add_argument("--events", type=str, default=None,
                        help="Path to events CSV")
    parser.add_argument("--playbooks", type=str, default=None,
                        help="Path to playbooks CSV")
    parser.add_argument("--no-wipe", action="store_true",
                        help="Disable Jumbotron wipe to compare")
    parser.add_argument("--wipe-cost", type=int, default=None,
                        help="Override wipe cost for testing")
    parser.add_argument("--min-hand", type=int, default=None,
                        help="Override min hand size for wipe (0 to disable)")
    parser.add_argument("--post-wipe-cost", type=int, default=None,
                        help="Override post-wipe event completion surcharge (0 to disable)")
    parser.add_argument("--no-playbooks", action="store_true",
                        help="Disable playbook deck entirely")
    parser.add_argument("--tiered-wipe", type=str, default=None,
                        help="Enable tiered wipe with costs: '1:1,2:3,4:5' means "
                             "1 event=1S, 2 events=3S, 4 events=5S")
    parser.add_argument("--json", type=str, default=None,
                        help="Output raw stats to JSON file")
    parser.add_argument("--skill", type=str, default=None,
                        help="Skill levels per player, comma-separated (e.g. '1.0,0.5,0.3')")
    parser.add_argument("--styles", type=str, default=None,
                        help="Play styles per player, comma-separated (e.g. 'rush,economy,balanced')")
    parser.add_argument("--preset", type=str, default=None,
                        choices=["experts", "beginners", "mixed", "styles"],
                        help="Quick preset: experts, beginners, mixed (1 expert + beginners), "
                             "styles (rush+economy+control)")

    args = parser.parse_args()

    # Find files
    sim_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(sim_dir)

    config_path = args.config or os.path.join(sim_dir, "config.json")
    events_path = args.events
    playbooks_path = args.playbooks

    # Auto-detect CSV files
    if not events_path:
        for candidate in [
            os.path.join(parent_dir, "contests-of-chaos-events copy.csv"),
            os.path.join(parent_dir, "contests-of-chaos-events.csv"),
            os.path.join(sim_dir, "events.csv"),
        ]:
            if os.path.exists(candidate):
                events_path = candidate
                break

    if not playbooks_path:
        for candidate in [
            os.path.join(parent_dir, "contests-of-chaos-playbooks copy.csv"),
            os.path.join(parent_dir, "contests-of-chaos-playbooks.csv"),
            os.path.join(sim_dir, "playbooks.csv"),
        ]:
            if os.path.exists(candidate):
                playbooks_path = candidate
                break

    # Load config
    print(f"Loading config from: {config_path}")
    with open(config_path, 'r') as f:
        config = json.load(f)

    # Apply overrides
    if args.no_wipe:
        config["game_rules"]["wipe_jumbotron"]["enabled"] = False
        print("  ⚠ Jumbotron wipe DISABLED")
    if args.wipe_cost is not None:
        config["game_rules"]["wipe_jumbotron"]["cost"] = args.wipe_cost
        print(f"  ⚠ Wipe cost overridden to {args.wipe_cost}")
    if args.min_hand is not None:
        config["game_rules"]["wipe_jumbotron"]["min_hand_size"] = args.min_hand
        print(f"  ⚠ Min hand size for wipe overridden to {args.min_hand}")
    if args.post_wipe_cost is not None:
        config["game_rules"]["wipe_jumbotron"]["post_wipe_event_cost"] = args.post_wipe_cost
        print(f"  ⚠ Post-wipe event surcharge overridden to {args.post_wipe_cost}")
    if args.tiered_wipe:
        tiered = {}
        for pair in args.tiered_wipe.split(","):
            n, cost = pair.strip().split(":")
            tiered[str(int(n))] = int(cost)
        config["game_rules"]["wipe_jumbotron"]["tiered_cost"] = tiered
        config["game_rules"]["wipe_jumbotron"]["enabled"] = True
        tier_desc = ", ".join(f"{n} event(s)={c}S" for n, c in sorted(tiered.items()))
        print(f"  ⚠ Tiered wipe enabled: {tier_desc}")

    # Load events
    events = []
    if events_path and os.path.exists(events_path):
        print(f"Loading events from: {events_path}")
        events = load_events_csv(events_path)
        print(f"  Loaded {len(events)} events")
    else:
        print("⚠ No events CSV found. Using empty event deck.")

    # Load playbooks
    playbooks = []
    if args.no_playbooks:
        print("  ⚠ Playbooks DISABLED")
    elif playbooks_path and os.path.exists(playbooks_path):
        print(f"Loading playbooks from: {playbooks_path}")
        playbooks = load_playbooks_csv(playbooks_path)
        print(f"  Loaded {len(playbooks)} playbooks")
    else:
        print("⚠ No playbooks CSV found. Running without playbooks.")

    # Validate
    if args.players < 2 or args.players > 4:
        print("Error: players must be 2-4")
        sys.exit(1)

    # Build player configs
    player_configs = None
    np = args.players

    if args.preset:
        if args.preset == "experts":
            player_configs = [{"skill": 1.0, "style": "balanced"} for _ in range(np)]
        elif args.preset == "beginners":
            player_configs = [{"skill": 0.3, "style": "balanced"} for _ in range(np)]
        elif args.preset == "mixed":
            player_configs = [{"skill": 1.0, "style": "balanced"}]
            player_configs += [{"skill": 0.3, "style": "balanced"} for _ in range(np - 1)]
        elif args.preset == "styles":
            style_cycle = ["rush", "economy", "control", "balanced"]
            player_configs = [{"skill": 1.0, "style": style_cycle[i % 4]} for i in range(np)]
        print(f"  ⚠ Preset: {args.preset}")
        for i, pc in enumerate(player_configs):
            print(f"    P{i}: skill={pc.get('skill', 1.0)}, style={pc.get('style', 'balanced')}")

    if args.skill or args.styles:
        if player_configs is None:
            player_configs = [{} for _ in range(np)]

        if args.skill:
            skills = [float(s) for s in args.skill.split(",")]
            for i in range(min(len(skills), np)):
                player_configs[i]["skill"] = skills[i]

        if args.styles:
            styles = [s.strip() for s in args.styles.split(",")]
            for i in range(min(len(styles), np)):
                player_configs[i]["style"] = styles[i]

        print(f"  ⚠ Custom player configs:")
        for i, pc in enumerate(player_configs):
            print(f"    P{i}: skill={pc.get('skill', 1.0)}, style={pc.get('style', 'balanced')}")

    print(f"\nRunning {args.num_games} games with {args.players} players "
          f"(seeds {args.seed}-{args.seed + args.num_games - 1})...")

    # Run
    summary = run_batch(config, events, playbooks, args.num_games,
                        args.players, start_seed=args.seed,
                        max_turns=args.max_turns, verbose=args.verbose,
                        player_configs=player_configs)

    # Print report
    print_report(summary, events)

    # Optional JSON output
    if args.json:
        # Make JSON serializable
        json_summary = json.loads(json.dumps(summary, default=str))
        with open(args.json, 'w') as f:
            json.dump(json_summary, f, indent=2)
        print(f"\nRaw stats saved to: {args.json}")

    return summary


if __name__ == "__main__":
    main()
