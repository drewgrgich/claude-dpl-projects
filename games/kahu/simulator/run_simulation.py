"""Batch simulation runner for Kahu."""

import argparse
import json
import os
import sys
from collections import defaultdict
from typing import List, Dict, Optional

from cards import Card
from kahu_parser import load_market_cards, find_csv
from game_state import GameState, load_config
from ai_player import KahuAI


def run_single_game(config: dict, market_cards: List[Card], num_players: int,
                    seed: int, max_turns: int = 200,
                    player_configs: List[dict] = None) -> dict:
    """Run one complete game of Kahu, return stats dict."""
    game = GameState(config, num_players, seed=seed, market_cards=list(market_cards))

    # Create AIs
    ais = []
    for i in range(num_players):
        pc = (player_configs[i] if player_configs and i < len(player_configs)
              else {"skill": 1.0, "style": "balanced", "aggression": 0.5})
        ais.append(KahuAI(
            skill=pc.get("skill", 1.0),
            style=pc.get("style", "balanced"),
            aggression=pc.get("aggression", 0.5),
            rng_seed=seed + i * 10000,
        ))

    # Tracking
    action_counts = defaultdict(lambda: defaultdict(int))
    pua_bought = defaultdict(lambda: defaultdict(int))
    offerings_completed_turn = []
    cards_purchased = defaultdict(int)
    turns_per_player = defaultdict(int)
    influence_per_turn = []
    lava_at_turn = []

    turn = 0
    while not game.game_over and turn < max_turns:
        player = game.get_current_player()
        ai = ais[player.id]
        turns_per_player[player.id] += 1

        # Step 1: Play hand (v3: pass AI callback for Hula remove)
        play_result = game.play_hand(player, ai_callback=ai.effect_callback)
        lava_at_turn.append(game.lava_position)

        if play_result["lava_triggered"]:
            action_counts[player.id]["lava_triggered"] += 1
        if play_result["tiki_used"]:
            action_counts[player.id]["tiki_used"] += 1

        # Step 1b: Resolve card effects
        effect_result = game.resolve_card_effects(player, ai.effect_callback)

        influence_per_turn.append(player.influence_this_turn)

        # Step 2: Spend Influence
        spending_actions = ai.plan_spending(player, game)

        for act in spending_actions:
            atype = act.get("type", "unknown")
            action_counts[player.id][atype] += 1
            if atype == "buy_pua":
                pua_bought[player.id][act.get("color", "?")] += 1
            elif atype == "buy_market":
                card = act.get("card")
                if card:
                    cards_purchased[card.name] += 1
            elif atype == "complete_offering":
                offerings_completed_turn.append(turn)

        # Step 3: Refresh market
        game.refresh_market()

        # Step 4: Cleanup & draw
        game.cleanup_and_draw(player)

        # Advance
        game.advance_turn()
        turn += 1

    # Final scores
    final_scores = game.calculate_final_scores()
    winner = max(final_scores.keys(), key=lambda pid: (
        final_scores[pid]["total"], final_scores[pid]["pua_remaining"]))

    # Determine end condition
    end_condition = "max_turns"
    if game.lava_position <= 0:
        end_condition = "lava_eruption"
    elif any(p.num_vp_tokens >= 3 for p in game.players):
        end_condition = "offerings_complete"

    return {
        "seed": seed,
        "num_players": num_players,
        "turns": turn,
        "rounds": game.round_number,
        "winner": winner,
        "end_condition": end_condition,
        "final_scores": final_scores,
        "lava_final": game.lava_position,
        "lava_advances": game.lava_advances,
        "tikis_used": game.tikis_used,
        "action_counts": dict(action_counts),
        "pua_bought": dict(pua_bought),
        "cards_purchased": dict(cards_purchased),
        "offerings_completed_turn": offerings_completed_turn,
        "influence_per_turn": influence_per_turn,
        "lava_at_turn": lava_at_turn,
        "offerings_active": [o.name for o in game.offerings],
        "offerings_completion_counts": {
            o.name: len(o.completed_by) for o in game.offerings
        },
    }


def run_batch(config: dict, market_cards: List[Card], num_games: int,
              num_players: int, start_seed: int = 1, max_turns: int = 200,
              player_configs: List[dict] = None, verbose: bool = False) -> dict:
    """Run N games and aggregate statistics."""
    all_stats = []
    for i in range(num_games):
        if verbose and (i + 1) % 50 == 0:
            print(f"  Running game {i + 1}/{num_games}...")
        stats = run_single_game(config, market_cards, num_players,
                                seed=start_seed + i, max_turns=max_turns,
                                player_configs=player_configs)
        all_stats.append(stats)

    return aggregate_stats(all_stats, num_players)


def aggregate_stats(all_stats: List[dict], num_players: int) -> dict:
    """Aggregate stats across all games."""
    n = len(all_stats)
    if n == 0:
        return {}

    # Game length
    turns = [s["turns"] for s in all_stats]
    rounds = [s["rounds"] for s in all_stats]

    # Win rates
    wins = defaultdict(int)
    for s in all_stats:
        wins[s["winner"]] += 1
    win_rates = {pid: wins[pid] / n for pid in range(num_players)}

    # End conditions
    end_conditions = defaultdict(int)
    for s in all_stats:
        end_conditions[s["end_condition"]] += 1

    # Scores
    all_totals = defaultdict(list)
    all_card_vp = defaultdict(list)
    all_token_vp = defaultdict(list)
    all_bonus_vp = defaultdict(list)
    for s in all_stats:
        for pid, sc in s["final_scores"].items():
            all_totals[pid].append(sc["total"])
            all_card_vp[pid].append(sc["card_vp"])
            all_token_vp[pid].append(sc["token_vp"])
            all_bonus_vp[pid].append(sc["offering_bonus"])

    # Lava stats
    lava_finals = [s["lava_final"] for s in all_stats]
    lava_advances = [s["lava_advances"] for s in all_stats]

    # Action frequency
    total_actions = defaultdict(lambda: defaultdict(int))
    for s in all_stats:
        for pid_str, acts in s["action_counts"].items():
            pid = int(pid_str) if isinstance(pid_str, str) else pid_str
            for act, count in acts.items():
                total_actions[pid][act] += count

    # Offerings
    off_completions = defaultdict(int)
    off_appearances = defaultdict(int)
    for s in all_stats:
        for name in s["offerings_active"]:
            off_appearances[name] += 1
        for name, count in s["offerings_completion_counts"].items():
            off_completions[name] += count

    # Card popularity
    card_buys = defaultdict(int)
    for s in all_stats:
        for name, count in s["cards_purchased"].items():
            card_buys[name] += count

    # Influence per turn
    all_inf = []
    for s in all_stats:
        all_inf.extend(s["influence_per_turn"])

    # Score margins
    margins = []
    for s in all_stats:
        scores = sorted(s["final_scores"].values(), key=lambda x: x["total"], reverse=True)
        if len(scores) >= 2:
            margins.append(scores[0]["total"] - scores[1]["total"])

    return {
        "num_games": n,
        "num_players": num_players,
        "avg_turns": sum(turns) / n,
        "min_turns": min(turns),
        "max_turns": max(turns),
        "avg_rounds": sum(rounds) / n,
        "win_rates": win_rates,
        "end_conditions": dict(end_conditions),
        "avg_scores": {pid: sum(v) / n for pid, v in all_totals.items()},
        "avg_card_vp": {pid: sum(v) / n for pid, v in all_card_vp.items()},
        "avg_token_vp": {pid: sum(v) / n for pid, v in all_token_vp.items()},
        "avg_bonus_vp": {pid: sum(v) / n for pid, v in all_bonus_vp.items()},
        "avg_lava_final": sum(lava_finals) / n,
        "avg_lava_advances": sum(lava_advances) / n,
        "action_frequency": dict(total_actions),
        "offering_stats": {
            name: {
                "appearances": off_appearances[name],
                "completions": off_completions[name],
                "completion_rate": off_completions[name] / max(1, off_appearances[name]),
            }
            for name in set(list(off_appearances.keys()) + list(off_completions.keys()))
        },
        "top_cards": dict(sorted(card_buys.items(), key=lambda x: x[1], reverse=True)[:15]),
        "avg_influence_per_turn": sum(all_inf) / max(1, len(all_inf)),
        "avg_winner_margin": sum(margins) / max(1, len(margins)),
        "score_margins": margins,
    }


def print_report(agg: dict):
    """Print a formatted simulation report."""
    n = agg["num_games"]
    np = agg["num_players"]
    print(f"\n{'='*65}")
    print(f"  KAHU SIMULATION REPORT: {n} games, {np} players")
    print(f"{'='*65}")

    print(f"\n--- Game Length ---")
    print(f"  Average: {agg['avg_turns']:.1f} turns ({agg['avg_rounds']:.1f} rounds)")
    print(f"  Range: {agg['min_turns']}–{agg['max_turns']} turns")

    print(f"\n--- End Conditions ---")
    for cond, count in sorted(agg["end_conditions"].items(), key=lambda x: -x[1]):
        print(f"  {cond}: {count} ({count/n:.1%})")

    print(f"\n--- Win Rates ---")
    for pid in sorted(agg["win_rates"].keys()):
        rate = agg["win_rates"][pid]
        flag = " ⚠" if rate > 0.35 else ""
        print(f"  Player {pid}: {rate:.1%}{flag}")

    print(f"\n--- Average Scores ---")
    for pid in sorted(agg["avg_scores"].keys()):
        total = agg["avg_scores"][pid]
        card = agg["avg_card_vp"][pid]
        token = agg["avg_token_vp"][pid]
        bonus = agg["avg_bonus_vp"][pid]
        print(f"  P{pid}: {total:.1f} total (Cards: {card:.1f} + Tokens: {token:.1f} + Bonus: {bonus:.1f})")

    print(f"\n--- Score Spread ---")
    print(f"  Avg winner margin: {agg['avg_winner_margin']:.1f} VP")

    print(f"\n--- Lava Track ---")
    print(f"  Avg final position: {agg['avg_lava_final']:.1f}")
    print(f"  Avg lava advances: {agg['avg_lava_advances']:.1f}")

    print(f"\n--- Average Influence per Turn ---")
    print(f"  {agg['avg_influence_per_turn']:.1f}")

    print(f"\n--- Offering Completion Rates ---")
    for name, data in sorted(agg["offering_stats"].items(),
                              key=lambda x: -x[1]["completion_rate"]):
        rate = data["completion_rate"]
        apps = data["appearances"]
        print(f"  {name}: {rate:.2f} completions/game (in {apps} games)")

    print(f"\n--- Most Purchased Cards ---")
    for name, count in list(agg["top_cards"].items())[:10]:
        print(f"  {name}: {count} ({count/n:.1f}/game)")

    print(f"\n{'='*65}")


def build_player_configs(args, num_players: int) -> List[dict]:
    """Build player configs from CLI args."""
    configs = [{"skill": 1.0, "style": "balanced", "aggression": 0.5}
               for _ in range(num_players)]

    if args.preset == "experts":
        pass  # Already default
    elif args.preset == "beginners":
        configs = [{"skill": 0.3, "style": "balanced", "aggression": 0.5}
                   for _ in range(num_players)]
    elif args.preset == "mixed":
        configs[0] = {"skill": 1.0, "style": "balanced", "aggression": 0.5}
        for i in range(1, num_players):
            configs[i] = {"skill": 0.3, "style": "balanced", "aggression": 0.5}
    elif args.preset == "styles":
        style_list = ["balanced", "rush", "economy", "defensive"]
        for i in range(num_players):
            configs[i] = {"skill": 1.0, "style": style_list[i % len(style_list)],
                          "aggression": 0.5}

    if args.styles:
        for i, s in enumerate(args.styles.split(",")):
            if i < len(configs):
                configs[i]["style"] = s.strip()

    return configs


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Kahu batch simulation")
    parser.add_argument("-n", "--num-games", type=int, default=200)
    parser.add_argument("-p", "--players", type=int, default=3)
    parser.add_argument("-s", "--seed", type=int, default=1)
    parser.add_argument("--max-turns", type=int, default=200)
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--json", type=str, default=None)
    parser.add_argument("--preset", type=str, default="experts",
                        choices=["experts", "beginners", "mixed", "styles"])
    parser.add_argument("--styles", type=str, default=None)
    parser.add_argument("--rules", type=str, default="v1",
                        help="Rules version: 'v1', 'v2', 'v2.1', 'v3', or config path")
    parser.add_argument("--csv", type=str, default=None,
                        help="Override CSV card file path")

    args = parser.parse_args()

    config = load_config(args.rules)
    if args.csv:
        csv_path = args.csv
    elif args.rules == "v3":
        csv_path = find_csv("kahu-cards-v3")
        if not csv_path:
            csv_path = find_csv()
    else:
        csv_path = find_csv()
    if not csv_path:
        print("ERROR: Cannot find kahu-cards CSV")
        sys.exit(1)
    market_cards = load_market_cards(csv_path)
    print(f"Using CSV: {csv_path}")

    player_configs = build_player_configs(args, args.players)

    print(f"Running {args.num_games} games with {args.players} players (seed={args.seed})...")
    if args.verbose:
        print(f"Player configs: {player_configs}")

    agg = run_batch(config, market_cards, args.num_games, args.players,
                    start_seed=args.seed, max_turns=args.max_turns,
                    player_configs=player_configs, verbose=args.verbose)

    print_report(agg)

    if args.json:
        # Convert non-serializable keys
        export = {}
        for k, v in agg.items():
            if isinstance(v, dict):
                export[k] = {str(kk): vv for kk, vv in v.items()}
            else:
                export[k] = v
        with open(args.json, 'w') as f:
            json.dump(export, f, indent=2, default=str)
        print(f"\nStats exported to {args.json}")
