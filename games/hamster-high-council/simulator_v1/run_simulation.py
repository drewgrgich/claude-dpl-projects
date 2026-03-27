"""
Hamster High Council v1.0 — Batch Simulation Runner.

Metrics: game health, seat balance, stash economy, Wobbly exploitation,
council seat impact, talent frequency, Final Bell stats.

Usage:
    python run_simulation.py -n 500
    python run_simulation.py -n 500 --vp-target 40 --num-players 3
"""

import argparse
import json
import os
import sys
import time
from collections import defaultdict
from typing import List, Dict, Optional

from cards import Card, FACTIONS, FACTION_SYMBOLS, FACTION_NAMES
from game_state import GameState, Player
from ai_player import HeuristicAI, STYLE_PROFILES


def run_single_game(config: dict, seed: int, max_rounds: int = 20,
                    player_configs: Optional[List[dict]] = None) -> dict:
    """Run one complete v1 game, return stats dict."""
    game = GameState(config, seed=seed)
    num_players = game.num_players

    ais = []
    for i in range(num_players):
        pc = player_configs[i] if player_configs and i < len(player_configs) else {}
        ais.append(HeuristicAI(
            player_id=i,
            skill=pc.get("skill", 1.0),
            style=pc.get("style", "balanced"),
            rng_seed=seed * 100 + i
        ))

    tricks_per_round = []
    round_count = 0

    def choose_card_fn(player, gs, led_faction):
        return ais[player.id].choose_card(player, gs, led_faction)

    def choose_talent_fn(player, gs, faction):
        return ais[player.id].choose_talent(player, gs, faction)

    def make_talent_callbacks(ai_list):
        return {
            "orange": lambda w, p, g: ai_list[w.id].choose_orange_keep(w, p, g),
            "yellow": lambda w, t, g: ai_list[w.id].choose_yellow_swap(w, t, g),
            "green": lambda w, d, g: ai_list[w.id].choose_green_return(w, d, g),
            "blue": lambda w, o, g: ai_list[w.id].choose_blue_action(w, o, g),
            "purple": lambda w, g: ai_list[w.id].choose_purple_action(w, g),
        }

    talent_cbs = make_talent_callbacks(ais)

    while not game.game_over and round_count < max_rounds:
        game.setup_new_round()
        round_count += 1
        tricks_this_round = 0
        final_bell_done = False

        while not game.game_over:
            # Check if someone emptied their hand
            emptied = game.player_emptied_hand()
            if emptied is not None and not final_bell_done:
                # Finish current trick already happened via play_trick
                # Now do the Final Bell
                if game.rules["final_bell"]["enabled"]:
                    # Player to left of emptied player leads one final trick
                    final_leader = (emptied + 1) % num_players
                    # Only if there are players with cards
                    players_with_cards = [p for p in game.players if len(p.hand) > 0]
                    if len(players_with_cards) >= 2:
                        game.leader_id = final_leader
                        result = game.play_trick(
                            choose_card_fn=choose_card_fn,
                            choose_talent_fn=choose_talent_fn,
                            talent_callbacks=talent_cbs,
                            is_final_bell=True
                        )
                        tricks_this_round += 1
                final_bell_done = True
                break

            result = game.play_trick(
                choose_card_fn=choose_card_fn,
                choose_talent_fn=choose_talent_fn,
                talent_callbacks=talent_cbs,
            )
            tricks_this_round += 1

            if tricks_this_round > config["game_rules"]["max_tricks_per_round"]:
                break

        if not game.game_over:
            game.end_round()
        tricks_per_round.append(tricks_this_round)

    # Compile stats
    stats = {
        "seed": seed,
        "winner_id": game.winner_id,
        "rounds": round_count,
        "total_tricks": game.total_tricks,
        "tied_tricks": game.total_tied_tricks,
        "tricks_per_round": tricks_per_round,
        "final_vps": [p.vp for p in game.players],
        "stash_sizes": [p.vp for p in game.players],
        "tricks_won": [p.total_tricks_won for p in game.players],
        "wobbly_tricks": game.wobbly_tricks,
        "trump_tricks": game.trump_tricks,
        "standard_tricks": game.standard_tricks,
        "talent_activations": dict(game.talent_activations),
        "intern_draws": game.intern_draws,
        "final_bell_tricks": game.final_bell_tricks,
        "cards_banked_by_purple": game.cards_banked_by_purple,
        "council_balance_discards": game.council_balance_cards_discarded,
        "timed_out": game.winner_id is None,
    }

    # R1 leader tracking
    if round_count >= 1:
        r1_vps = [p.vp for p in game.players]  # This is cumulative, not R1-only
        # Approximate: after round 1, check who was ahead
        # We'll track via trick counts in round 1
        stats["r1_leader"] = None
        stats["r1_leader_won"] = False

    return stats


def run_batch(config: dict, num_games: int, start_seed: int = 1,
              max_rounds: int = 20,
              player_configs: Optional[List[dict]] = None,
              verbose: bool = False) -> dict:
    all_stats = []
    num_players = config["game_rules"]["num_players"]

    for i in range(num_games):
        seed = start_seed + i
        stats = run_single_game(config, seed, max_rounds, player_configs)
        all_stats.append(stats)
        if verbose and (i + 1) % 100 == 0:
            print(f"  ... {i + 1}/{num_games} games complete")

    return aggregate_stats(all_stats, num_players)


def aggregate_stats(all_stats: List[dict], num_players: int) -> dict:
    n = len(all_stats)
    if n == 0:
        return {}

    agg = {"num_games": n, "num_players": num_players}

    # Game Health
    rounds = [s["rounds"] for s in all_stats]
    agg["avg_rounds"] = sum(rounds) / n
    agg["median_rounds"] = sorted(rounds)[n // 2]
    agg["min_rounds"] = min(rounds)
    agg["max_rounds"] = max(rounds)
    agg["round_distribution"] = {}
    for r in range(1, max(rounds) + 1):
        count = rounds.count(r)
        if count > 0:
            agg["round_distribution"][r] = count

    total_tricks = [s["total_tricks"] for s in all_stats]
    agg["avg_tricks"] = sum(total_tricks) / n
    agg["avg_tricks_per_round"] = sum(total_tricks) / sum(rounds) if sum(rounds) > 0 else 0

    timed_out = sum(1 for s in all_stats if s["timed_out"])
    agg["timeout_rate"] = timed_out / n

    # Seat Balance
    win_counts = [0] * num_players
    for s in all_stats:
        if s["winner_id"] is not None:
            win_counts[s["winner_id"]] += 1
    games_won = sum(win_counts)
    agg["win_rates"] = {i: win_counts[i] / games_won if games_won > 0 else 0
                        for i in range(num_players)}
    agg["win_counts"] = {i: win_counts[i] for i in range(num_players)}

    all_final_vps = [s["final_vps"] for s in all_stats]
    agg["avg_final_vp"] = [sum(vps[i] for vps in all_final_vps) / n
                           for i in range(num_players)]
    agg["avg_vp_per_player"] = sum(agg["avg_final_vp"]) / num_players

    total_vp_all = sum(sum(s["final_vps"]) for s in all_stats)
    total_rounds_all = sum(s["rounds"] for s in all_stats)
    agg["avg_vp_per_player_per_round"] = (total_vp_all / num_players / total_rounds_all
                                           if total_rounds_all > 0 else 0)

    # Trick Type Distribution
    total_wobbly = sum(s["wobbly_tricks"] for s in all_stats)
    total_trump = sum(s["trump_tricks"] for s in all_stats)
    total_standard = sum(s["standard_tricks"] for s in all_stats)
    total_all_tricks = sum(total_tricks)

    agg["wobbly_tricks_per_game"] = total_wobbly / n
    agg["trump_tricks_per_game"] = total_trump / n
    agg["standard_tricks_per_game"] = total_standard / n
    agg["trick_type_share"] = {
        "trump": total_trump / total_all_tricks if total_all_tricks > 0 else 0,
        "wobbly": total_wobbly / total_all_tricks if total_all_tricks > 0 else 0,
        "standard": total_standard / total_all_tricks if total_all_tricks > 0 else 0,
    }

    # VP from trick types (approximate: cards_per_trick * tricks)
    # In v1, every trick gives same VP (card count) regardless of type
    # But wobbly/trump tricks may have different card counts due to timing
    agg["avg_cards_per_trick"] = total_vp_all / total_all_tricks if total_all_tricks > 0 else 0

    # Talents
    total_talents = {f: 0 for f in FACTIONS}
    for s in all_stats:
        for f in FACTIONS:
            total_talents[f] += s["talent_activations"].get(f, 0)

    agg["talent_activations_total"] = dict(total_talents)
    agg["talent_activations_per_game"] = {f: total_talents[f] / n for f in FACTIONS}
    grand_talents = sum(total_talents.values())
    agg["talent_share"] = {f: total_talents[f] / grand_talents if grand_talents > 0 else 0
                           for f in FACTIONS}
    agg["total_talents_per_game"] = grand_talents / n

    # Purple banking
    total_banked = sum(s["cards_banked_by_purple"] for s in all_stats)
    agg["purple_banks_per_game"] = total_banked / n

    # Stagnation
    tied = [s["tied_tricks"] for s in all_stats]
    agg["avg_tied_tricks"] = sum(tied) / n
    agg["tied_trick_rate"] = sum(tied) / sum(total_tricks) if sum(total_tricks) > 0 else 0

    # Intern draws
    agg["avg_intern_draws"] = sum(s["intern_draws"] for s in all_stats) / n

    # Final Bell
    total_fb = sum(s["final_bell_tricks"] for s in all_stats)
    agg["final_bell_tricks_per_game"] = total_fb / n
    agg["final_bell_share"] = total_fb / total_all_tricks if total_all_tricks > 0 else 0

    return agg


def print_report(agg: dict, config: dict):
    n = agg["num_games"]
    np_ = agg["num_players"]
    rules = config["game_rules"]

    print(f"\n{'='*65}")
    print(f"  HAMSTER HIGH COUNCIL v1.0 — SIMULATION REPORT")
    print(f"  {n} games · {np_} players · VP target: {rules['vp_target']}")
    print(f"  Council: Trump + Elite + Wobbly (3 seats)")
    print(f"  Scoring: Stash-based (1 card = 1 VP)")
    print(f"{'='*65}")

    print(f"\n--- GAME HEALTH ---")
    print(f"  Average rounds:        {agg['avg_rounds']:.1f} (median {agg['median_rounds']})")
    print(f"  Round range:           {agg['min_rounds']}–{agg['max_rounds']}")
    print(f"  Round distribution:    ", end="")
    for r, count in sorted(agg["round_distribution"].items()):
        print(f"R{r}={count/n:.0%}  ", end="")
    print()
    print(f"  Avg tricks/game:       {agg['avg_tricks']:.1f}")
    print(f"  Avg tricks/round:      {agg['avg_tricks_per_round']:.1f}")
    print(f"  Avg cards/trick:       {agg['avg_cards_per_trick']:.1f}")
    print(f"  Timeout rate:          {agg['timeout_rate']:.1%}")

    print(f"\n--- SEAT BALANCE ---")
    for i in range(np_):
        wr = agg["win_rates"][i]
        bar = "█" * int(wr * 40)
        flag = " ⚠️" if wr > 0.30 or wr < 0.20 else ""
        print(f"  P{i}: {wr:6.1%} ({agg['win_counts'][i]:>4} wins) {bar}{flag}")
    print(f"  Avg final VP/player:   {agg['avg_vp_per_player']:.1f}")
    print(f"  VP/player/round:       {agg['avg_vp_per_player_per_round']:.1f}")

    print(f"\n--- TRICK TYPE DISTRIBUTION ---")
    tts = agg["trick_type_share"]
    for ttype, label in [("trump", "Trump (Big Cheese)"), ("wobbly", "Wobbly (Low wins)"),
                          ("standard", "Standard (High wins)")]:
        share = tts[ttype]
        per_game = agg[f"{ttype}_tricks_per_game"]
        bar = "█" * int(share * 30)
        print(f"  {label:25s}: {share:5.1%} ({per_game:.1f}/game) {bar}")

    print(f"\n--- FACTION TALENTS ---")
    print(f"  Total talents/game:    {agg['total_talents_per_game']:.1f}")
    for f in FACTIONS:
        per_game = agg["talent_activations_per_game"][f]
        share = agg["talent_share"][f]
        name = rules["talents"]["talent_list"][f]["name"]
        sym = FACTION_SYMBOLS[f]
        flag = ""
        if per_game < 0.3:
            flag = " ⚠️ rare"
        elif per_game > 3.0:
            flag = " ⚠️ frequent"
        print(f"  {sym} {f:7s} {name:25s}: {per_game:4.1f}/game ({share:4.1%}){flag}")
    print(f"  Purple VP banked/game: {agg['purple_banks_per_game']:.1f}")

    print(f"\n--- STAGNATION ---")
    print(f"  Avg tied tricks/game:  {agg['avg_tied_tricks']:.1f}")
    print(f"  Tied trick rate:       {agg['tied_trick_rate']:.1%}")

    print(f"\n--- SPECIAL MECHANICS ---")
    print(f"  Intern draws/game:     {agg['avg_intern_draws']:.1f}")
    print(f"  Final Bell tricks/game:{agg['final_bell_tricks_per_game']:.1f}")

    # Flags
    flags = []
    if agg["timeout_rate"] > 0.05:
        flags.append(f"High timeout rate ({agg['timeout_rate']:.0%})")
    for i in range(np_):
        if agg["win_rates"][i] > 0.30:
            flags.append(f"P{i} win rate too high ({agg['win_rates'][i]:.0%})")
        if agg["win_rates"][i] < 0.20:
            flags.append(f"P{i} win rate too low ({agg['win_rates'][i]:.0%})")
    if tts["wobbly"] < 0.05:
        flags.append(f"Wobbly tricks too rare ({tts['wobbly']:.0%})")
    if agg["purple_banks_per_game"] > 4:
        flags.append(f"Purple banking too frequent ({agg['purple_banks_per_game']:.1f}/game)")

    if flags:
        print(f"\n{'!'*65}")
        print(f"  ⚠️  BALANCE FLAGS:")
        for flag in flags:
            print(f"    • {flag}")
        print(f"{'!'*65}")
    else:
        print(f"\n  ✅ No balance flags detected.")

    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Hamster High Council v1.0 — Batch Simulation Runner")
    parser.add_argument("-n", "--num-games", type=int, default=500)
    parser.add_argument("-s", "--seed", type=int, default=1)
    parser.add_argument("--max-rounds", type=int, default=20)
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--config", type=str, default=None)
    parser.add_argument("--json", type=str, default=None)

    # Rule overrides
    parser.add_argument("--vp-target", type=int, default=None)
    parser.add_argument("--num-players", type=int, default=None)
    parser.add_argument("--talents-off", action="store_true")
    parser.add_argument("--final-bell-off", action="store_true")

    # Player configs
    parser.add_argument("--preset", type=str, default="experts",
                       choices=["experts", "beginners", "mixed", "styles"])
    parser.add_argument("--skill", type=str, default=None)
    parser.add_argument("--styles", type=str, default=None)

    args = parser.parse_args()

    config = GameState.load_config(args.config)

    if args.vp_target is not None:
        config["game_rules"]["vp_target"] = args.vp_target
    if args.num_players is not None:
        config["game_rules"]["num_players"] = args.num_players
    if args.talents_off:
        config["game_rules"]["talents"]["enabled"] = False
    if args.final_bell_off:
        config["game_rules"]["final_bell"]["enabled"] = False

    num_players = config["game_rules"]["num_players"]
    player_configs = [{"skill": 1.0, "style": "balanced"} for _ in range(num_players)]

    if args.preset == "styles":
        style_list = ["balanced", "aggressive", "wobbly_hunter", "hoarder"]
        for i in range(num_players):
            player_configs[i]["style"] = style_list[i % len(style_list)]
    elif args.preset == "beginners":
        player_configs = [{"skill": 0.3, "style": "balanced"} for _ in range(num_players)]
    elif args.preset == "mixed":
        player_configs[0] = {"skill": 1.0, "style": "balanced"}
        for i in range(1, num_players):
            player_configs[i] = {"skill": 0.3, "style": "balanced"}

    if args.skill:
        skills = [float(s) for s in args.skill.split(",")]
        for i, s in enumerate(skills):
            if i < len(player_configs):
                player_configs[i]["skill"] = s

    if args.styles:
        styles = args.styles.split(",")
        for i, s in enumerate(styles):
            if i < len(player_configs):
                player_configs[i]["style"] = s.strip()

    print(f"\nHamster High Council v1.0 Simulator")
    print(f"Running {args.num_games} games ({num_players} players, seed {args.seed})...")
    for i, pc in enumerate(player_configs):
        print(f"  P{i}: skill={pc['skill']:.1f}, style={pc['style']}")

    start_time = time.time()
    agg = run_batch(config, args.num_games, start_seed=args.seed,
                    max_rounds=args.max_rounds,
                    player_configs=player_configs,
                    verbose=args.verbose)
    elapsed = time.time() - start_time

    print(f"\nCompleted in {elapsed:.1f}s ({args.num_games / elapsed:.0f} games/sec)")
    print_report(agg, config)

    if args.json:
        with open(args.json, 'w') as f:
            json.dump(agg, f, indent=2, default=str)
        print(f"Stats exported to {args.json}")
