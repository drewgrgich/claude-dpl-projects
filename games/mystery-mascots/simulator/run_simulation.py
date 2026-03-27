#!/usr/bin/env python3
"""
Mystery Mascots — Batch Simulation Runner.

Runs N AI-vs-AI games and aggregates balance / game-health statistics.
"""

import argparse
import json
import os
import sys
from collections import defaultdict
from typing import List, Dict, Optional

from cards import Card, Deck, FACTIONS, build_full_deck
from game_state import GameState, Player
from ai_player import HeuristicAI, STYLE_PROFILES


# ── Draft Orchestrator ─────────────────────────────────────────────
def run_draft(players: List[Player], hands: List[List[Card]],
              ais: List[HeuristicAI], game: GameState) -> List[List[Card]]:
    """
    Run the Tailgate Draft: deal 7, pick 1, pass clockwise, keep 5.
    """
    n = len(players)
    keep_count = game.rules["setup"]["keep_size"]
    packs = [list(h) for h in hands]
    kept = [[] for _ in range(n)]

    for round_num in range(keep_count):
        # Each player picks one card
        for i in range(n):
            if packs[i]:
                pick = ais[i].choose_one_draft_pick(players[i], packs[i], kept[i], game)
                packs[i].remove(pick)
                kept[i].append(pick)

        # Pass packs clockwise: player i gets pack from player i-1
        packs = [packs[(i - 1) % n] for i in range(n)]

    return kept


# ── Execute action ─────────────────────────────────────────────────
def execute_action(game: GameState, player: Player, action: dict,
                   ai: HeuristicAI) -> dict:
    """Execute an AI action on the game state."""
    t = action.get("type", "pass")

    if t == "place":
        result = game.action_place_card(player, action["card"], action["room"])
        # If resolution was triggered and there are wilds, declare them
        # (wilds are declared during _resolve_room via wild_fn callback)
        return result

    elif t == "power_red":
        return game.action_power_red(player, action["room"], action["placement_idx"])

    elif t == "power_orange":
        result = game.action_power_orange(player, action["room"], action["placement_idx"])
        if result["success"]:
            # AI learns from the peek
            peeked_card = result["peeked"]
            ai.known_allegiances.setdefault(result["player_of_card"], None)
        return result

    elif t == "power_yellow":
        return game.action_power_yellow(player, action["room"],
                                         action["placement_idx"], action["new_rank"])

    elif t == "power_green":
        result = game.action_power_green(player, action["target"])
        if result["success"]:
            ai.known_allegiances[action["target"]] = result["your_peek"]
        return result

    elif t == "power_blue":
        return game.action_power_blue(player, action["from_room"],
                                       action["from_idx"], action["to_room"])

    elif t == "power_purple":
        return game.action_power_purple(player, action["from_room"],
                                         action["from_idx"], action["to_room"],
                                         wild_fn=lambda p, c, r, g: ai.declare_wild(p, c, r, g))

    elif t == "accuse":
        return game.action_accuse(player, action["target"], action["faction"])

    elif t == "pass":
        return {"success": True, "action": "pass"}

    return {"success": False, "error": f"Unknown action type: {t}"}


# ── Single game runner ─────────────────────────────────────────────
def run_single_game(config: dict, num_players: int, seed: int,
                    max_turns: int = 200,
                    player_configs: List[Dict] = None) -> dict:
    """Run one complete game and return stats."""
    game = GameState(config, num_players, seed=seed)

    # Create AIs
    ais = []
    for i in range(num_players):
        pc = player_configs[i] if player_configs and i < len(player_configs) else {}
        ais.append(HeuristicAI(
            skill=pc.get("skill", 1.0),
            style=pc.get("style", "balanced"),
            aggression=pc.get("aggression", 0.5),
            rng_seed=seed + i * 10000,
        ))

    # Setup with AI draft
    game.setup(draft_fn=lambda players, hands, g: run_draft(players, hands, ais, g))

    # Register wild declaration callback for resolutions
    original_resolve = game._resolve_room

    def resolve_with_wilds(room_idx, wild_fn=None):
        def ai_wild_fn(player, card, ri, g):
            ai = ais[player.pid]
            return ai.declare_wild(player, card, ri, g)
        return original_resolve(room_idx, wild_fn=ai_wild_fn)

    game._resolve_room = resolve_with_wilds

    # Tracking
    action_counts = defaultdict(lambda: defaultdict(int))
    cards_placed = 0
    powers_used = 0
    accusations_made = 0
    pass_count = 0
    turn_count = 0
    consecutive_passes = 0

    # Play the game
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

        # If AI returns pass but player could act, count it
        if action.get("type") == "pass":
            consecutive_passes += 1
            if consecutive_passes >= num_players * 2:
                game.game_over = True
                break
            pass_count += 1
            action_counts[player.pid]["pass"] += 1
            game.advance_turn()
            turn_count += 1
            continue

        consecutive_passes = 0  # reset on real action
        result = execute_action(game, player, action, ai)

        t = action.get("type", "pass")
        action_counts[player.pid][t] += 1

        if t == "place":
            cards_placed += 1
        elif t.startswith("power_"):
            powers_used += 1
        elif t == "accuse":
            accusations_made += 1

        game.advance_turn()
        turn_count += 1

    # Final scores
    scores = game.compute_final_scores()

    # Compile stats
    stats = {
        "seed": seed,
        "num_players": num_players,
        "turns": turn_count,
        "resolutions": game.total_resolutions,
        "target_resolutions": game.target_resolutions,
        "completed_naturally": game.total_resolutions >= game.target_resolutions,
        "cards_placed": cards_placed,
        "powers_used": powers_used,
        "accusations_made": accusations_made,
        "passes": pass_count,
        "scores": scores,
        "winner_pid": scores[0]["pid"] if scores else -1,
        "winner_faction": scores[0]["faction"] if scores else "NONE",
        "winner_score": scores[0]["total"] if scores else 0,
        "score_spread": scores[0]["total"] - scores[-1]["total"] if len(scores) > 1 else 0,
        "faction_scores": dict(game.faction_scores),
        "action_counts": {str(k): dict(v) for k, v in action_counts.items()},
        "exposure_count": sum(1 for p in game.players if p.exposed),
        "resolution_log": game.resolution_log,
        "bust_count": sum(1 for r in game.resolution_log if r["bust"]),
        "per_player": [
            {
                "pid": s["pid"],
                "faction": s["faction"],
                "total": s["total"],
                "faction_pts": s["faction_points"],
                "acc_bonus": s["accusation_bonus"],
                "exposed": s["exposed"],
                "correct_accusations": s["correct_accusations"],
                "accusations_made": s["accusations_made"],
            }
            for s in scores
        ],
    }

    return stats


# ── Batch runner ───────────────────────────────────────────────────
def run_batch(config: dict, num_games: int, num_players: int,
              start_seed: int = 1, max_turns: int = 200,
              player_configs: List[Dict] = None,
              verbose: bool = False) -> dict:
    """Run N games and aggregate statistics."""
    all_stats = []

    for i in range(num_games):
        if verbose and (i + 1) % 50 == 0:
            print(f"  Game {i + 1}/{num_games}...", file=sys.stderr)

        stats = run_single_game(config, num_players,
                                seed=start_seed + i,
                                max_turns=max_turns,
                                player_configs=player_configs)
        all_stats.append(stats)

    return aggregate_stats(all_stats, num_players)


def aggregate_stats(all_stats: List[dict], num_players: int) -> dict:
    """Aggregate stats across multiple games."""
    n = len(all_stats)
    if n == 0:
        return {}

    agg = {
        "num_games": n,
        "num_players": num_players,
    }

    # Game length
    turns = [s["turns"] for s in all_stats]
    agg["avg_turns"] = sum(turns) / n
    agg["min_turns"] = min(turns)
    agg["max_turns"] = max(turns)

    # Completion rate
    completed = sum(1 for s in all_stats if s["completed_naturally"])
    agg["completion_rate"] = completed / n

    # Resolutions
    resolutions = [s["resolutions"] for s in all_stats]
    agg["avg_resolutions"] = sum(resolutions) / n

    # Bust rate
    total_resolutions = sum(resolutions)
    total_busts = sum(s["bust_count"] for s in all_stats)
    agg["bust_rate"] = total_busts / max(total_resolutions, 1)
    agg["avg_busts_per_game"] = total_busts / n

    # Win rates by player position (seat)
    seat_wins = defaultdict(int)
    for s in all_stats:
        seat_wins[s["winner_pid"]] += 1
    agg["win_rate_by_seat"] = {str(k): v / n for k, v in sorted(seat_wins.items())}

    # Win rates by faction
    faction_wins = defaultdict(int)
    for s in all_stats:
        faction_wins[s["winner_faction"]] += 1
    agg["win_rate_by_faction"] = {k: v / n for k, v in sorted(faction_wins.items())}

    # Score distribution
    winner_scores = [s["winner_score"] for s in all_stats]
    agg["avg_winner_score"] = sum(winner_scores) / n
    agg["avg_score_spread"] = sum(s["score_spread"] for s in all_stats) / n

    all_scores = [p["total"] for s in all_stats for p in s["per_player"]]
    agg["avg_player_score"] = sum(all_scores) / len(all_scores) if all_scores else 0

    # Faction score distribution
    faction_totals = defaultdict(list)
    for s in all_stats:
        for f, sc in s["faction_scores"].items():
            faction_totals[f].append(sc)
    agg["avg_faction_scores"] = {f: sum(v) / len(v) for f, v in faction_totals.items()}

    # Exposure stats
    exposure_counts = [s["exposure_count"] for s in all_stats]
    agg["avg_exposures"] = sum(exposure_counts) / n

    # Action distribution
    total_actions = defaultdict(int)
    for s in all_stats:
        for pid, actions in s["action_counts"].items():
            for action_type, count in actions.items():
                total_actions[action_type] += count
    grand_total = sum(total_actions.values())
    agg["action_distribution"] = {k: v / max(grand_total, 1) for k, v in total_actions.items()}
    agg["action_totals"] = dict(total_actions)

    # Accusation stats
    total_accusations = sum(s["accusations_made"] for s in all_stats)
    correct_accusations = sum(
        p["correct_accusations"] for s in all_stats for p in s["per_player"]
    )
    agg["avg_accusations_per_game"] = total_accusations / n
    agg["accusation_accuracy"] = correct_accusations / max(total_accusations, 1)

    # Powers used
    agg["avg_powers_per_game"] = sum(s["powers_used"] for s in all_stats) / n

    return agg


# ── Report printer ─────────────────────────────────────────────────
def print_report(agg: dict):
    """Print formatted simulation report."""
    print(f"\n{'=' * 65}")
    print(f"  MYSTERY MASCOTS SIMULATION REPORT")
    print(f"  {agg['num_games']} games, {agg['num_players']} players")
    print(f"{'=' * 65}")

    print(f"\n--- Game Health ---")
    print(f"  Avg game length:    {agg['avg_turns']:.1f} turns")
    print(f"  Turn range:         {agg['min_turns']}–{agg['max_turns']}")
    print(f"  Natural completion: {agg['completion_rate']:.1%}")
    print(f"  Avg resolutions:    {agg['avg_resolutions']:.1f}")

    print(f"\n--- Scoring ---")
    print(f"  Avg winner score:   {agg['avg_winner_score']:.1f}")
    print(f"  Avg player score:   {agg['avg_player_score']:.1f}")
    print(f"  Avg score spread:   {agg['avg_score_spread']:.1f}")
    print(f"  Bust rate:          {agg['bust_rate']:.1%} ({agg['avg_busts_per_game']:.1f}/game)")

    print(f"\n--- Balance: Win Rate by Seat ---")
    for seat, rate in agg["win_rate_by_seat"].items():
        bar = "#" * int(rate * 50)
        print(f"  Seat {seat}: {rate:.1%}  {bar}")

    print(f"\n--- Balance: Win Rate by Faction ---")
    for faction, rate in sorted(agg["win_rate_by_faction"].items(), key=lambda x: -x[1]):
        bar = "#" * int(rate * 50)
        print(f"  {faction:8s}: {rate:.1%}  {bar}")

    print(f"\n--- Avg Faction Scores ---")
    for faction, score in sorted(agg["avg_faction_scores"].items(), key=lambda x: -x[1]):
        print(f"  {faction:8s}: {score:.1f}")

    print(f"\n--- Exposure ---")
    print(f"  Avg exposures/game: {agg['avg_exposures']:.1f}")

    print(f"\n--- Actions ---")
    for action, pct in sorted(agg["action_distribution"].items(), key=lambda x: -x[1]):
        total = agg["action_totals"].get(action, 0)
        print(f"  {action:15s}: {pct:.1%} ({total} total)")

    print(f"\n--- Accusations ---")
    print(f"  Avg per game:       {agg['avg_accusations_per_game']:.1f}")
    print(f"  Accuracy:           {agg['accusation_accuracy']:.1%}")

    print(f"\n--- Powers ---")
    print(f"  Avg used per game:  {agg['avg_powers_per_game']:.1f}")

    print(f"\n{'=' * 65}")


# ── CLI ────────────────────────────────────────────────────────────
def load_config(path: str = None) -> dict:
    """Load config.json from specified path or auto-detect."""
    if path:
        with open(path) as f:
            return json.load(f)

    script_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(script_dir, "config.json"),
        os.path.join(script_dir, "..", "config.json"),
    ]
    for c in candidates:
        if os.path.exists(c):
            with open(c) as f:
                return json.load(f)

    raise FileNotFoundError("Could not find config.json")


def build_player_configs(args, num_players: int) -> List[Dict]:
    """Build player configs from CLI args."""
    configs = [{"skill": 1.0, "style": "balanced", "aggression": 0.5}
               for _ in range(num_players)]

    if args.preset == "experts":
        configs = [{"skill": 1.0, "style": "balanced"} for _ in range(num_players)]
    elif args.preset == "beginners":
        configs = [{"skill": 0.3, "style": "balanced"} for _ in range(num_players)]
    elif args.preset == "mixed":
        configs = [{"skill": 1.0, "style": "balanced"}]
        configs += [{"skill": 0.3, "style": "balanced"} for _ in range(num_players - 1)]
    elif args.preset == "styles":
        style_list = list(STYLE_PROFILES.keys())
        configs = [{"skill": 1.0, "style": style_list[i % len(style_list)]}
                   for i in range(num_players)]

    if args.skill:
        skills = [float(s) for s in args.skill.split(",")]
        for i, s in enumerate(skills):
            if i < len(configs):
                configs[i]["skill"] = s

    if args.styles:
        styles = args.styles.split(",")
        for i, s in enumerate(styles):
            if i < len(configs):
                configs[i]["style"] = s.strip()

    return configs


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Mystery Mascots Batch Simulation")
    parser.add_argument("-n", "--num-games", type=int, default=200)
    parser.add_argument("-p", "--players", type=int, default=4)
    parser.add_argument("-s", "--seed", type=int, default=1)
    parser.add_argument("--max-turns", type=int, default=200)
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--config", type=str, default=None)
    parser.add_argument("--json", type=str, default=None)

    # Player configuration
    parser.add_argument("--skill", type=str, default=None,
                        help="Comma-separated skills: '1.0,0.5,0.3'")
    parser.add_argument("--styles", type=str, default=None,
                        help="Comma-separated styles: 'sneaky,bold,balanced'")
    parser.add_argument("--preset", type=str, default=None,
                        choices=["experts", "beginners", "mixed", "styles"])

    args = parser.parse_args()

    config = load_config(args.config)
    player_configs = build_player_configs(args, args.players)

    print(f"Running {args.num_games} games with {args.players} players (seed={args.seed})...")
    if args.preset:
        print(f"Preset: {args.preset}")

    agg = run_batch(config, args.num_games, args.players,
                    start_seed=args.seed, max_turns=args.max_turns,
                    player_configs=player_configs, verbose=args.verbose)

    print_report(agg)

    if args.json:
        with open(args.json, 'w') as f:
            json.dump(agg, f, indent=2, default=str)
        print(f"\nStats saved to {args.json}")
