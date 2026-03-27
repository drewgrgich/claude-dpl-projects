"""
Hamster High Council — Batch Simulation Runner.

Runs N AI-vs-AI games and reports comprehensive metrics:
game health, seat balance, VP economy, dial statistics,
faction talent impact, Castle's Blessing effectiveness.

Usage:
    python run_simulation.py -n 500
    python run_simulation.py -n 1000 --vp-target 70 --right-multiplier 3
    python run_simulation.py -n 200 --preset styles --json results.json
"""

import argparse
import json
import os
import sys
import time
from collections import defaultdict
from typing import List, Dict, Optional

from cards import Card, FACTIONS, FACTION_SYMBOLS, FACTION_NAMES
from game_state import GameState, Player, DIAL_POSITIONS, DIAL_MULTIPLIER
from ai_player import HeuristicAI, STYLE_PROFILES


# ── Single Game Runner ─────────────────────────────────────────────

def run_single_game(config: dict, seed: int, max_rounds: int = 20,
                    player_configs: Optional[List[dict]] = None) -> dict:
    """Run one complete game, return stats dict."""
    game = GameState(config, seed=seed)
    num_players = game.num_players

    # Create AIs
    ais = []
    for i in range(num_players):
        pc = player_configs[i] if player_configs and i < len(player_configs) else {}
        ais.append(HeuristicAI(
            player_id=i,
            skill=pc.get("skill", 1.0),
            style=pc.get("style", "balanced"),
            aggression=pc.get("aggression", 0.5),
            rng_seed=seed * 100 + i
        ))

    # Tracking
    tricks_per_round = []
    stagnation_streaks = []  # consecutive tied tricks
    current_stagnation = 0
    vp_snapshots = []  # VP after each round
    round_count = 0

    # Blessing tracking
    blessing_recipients = defaultdict(list)  # player_id -> [round_nums]

    def choose_card_fn(player, gs, led_faction):
        return ais[player.id].choose_card(player, gs, led_faction)

    def choose_talent_fn(player, gs, faction):
        return ais[player.id].choose_talent(player, gs, faction)

    def choose_quick_fix_fn(player, gs):
        return ais[player.id].choose_quick_fix_cards(player, gs)

    def choose_orange_fn(player, gs):
        return ais[player.id].choose_orange_swap(player, gs)

    def choose_green_fn(player, peeked, gs):
        return ais[player.id].choose_green_keep(player, peeked, gs)

    def choose_blue_fn(player, opponents, gs):
        return ais[player.id].choose_blue_targets(player, opponents, gs)

    def blessing_keep_fn(player, all_cards, gs):
        return ais[player.id].choose_blessing_keep(player, all_cards, gs)

    # Play rounds until someone wins or max rounds
    while not game.game_over and round_count < max_rounds:
        game.setup_new_round(keep_fn=blessing_keep_fn)
        round_count += 1
        tricks_this_round = 0

        while not game.game_over and not game.is_round_over():
            result = game.play_trick(
                choose_card_fn=choose_card_fn,
                choose_talent_fn=choose_talent_fn,
                choose_quick_fix_cards_fn=choose_quick_fix_fn,
                choose_orange_swap_fn=choose_orange_fn,
                choose_green_keep_fn=choose_green_fn,
                choose_blue_targets_fn=choose_blue_fn,
            )
            tricks_this_round += 1

            if result.tied_no_winner:
                current_stagnation += 1
            else:
                if current_stagnation > 0:
                    stagnation_streaks.append(current_stagnation)
                current_stagnation = 0

            # Safety valve
            if tricks_this_round > config["game_rules"]["max_tricks_per_round"]:
                break

        if not game.game_over:
            game.end_round()

        tricks_per_round.append(tricks_this_round)
        vp_snapshots.append([p.vp for p in game.players])

    if current_stagnation > 0:
        stagnation_streaks.append(current_stagnation)

    # Compile stats
    winner_id = game.winner_id
    stats = {
        "seed": seed,
        "winner_id": winner_id,
        "rounds": round_count,
        "total_tricks": game.total_tricks,
        "tied_tricks": game.total_tied_tricks,
        "tricks_per_round": tricks_per_round,
        "final_vps": [p.vp for p in game.players],
        "vp_from_right": [p.vp_from_right for p in game.players],
        "tricks_won": [p.total_tricks_won for p in game.players],
        "tricks_by_dial": dict(game.tricks_by_dial),
        "vp_by_dial": dict(game.vp_by_dial),
        "talent_activations": dict(game.talent_activations),
        "player_talents": [dict(p.total_talents_used) for p in game.players],
        "intern_draws": game.intern_draws,
        "game_ending_dial": game.game_ending_dial,
        "stagnation_streaks": stagnation_streaks,
        "max_stagnation": max(stagnation_streaks) if stagnation_streaks else 0,
        "timed_out": winner_id is None,
        "council_balance_discards": game.council_balance_cards_discarded,
        "blessing_cards_drawn": game.blessing_cards_drawn,
    }

    # R1 leader tracking
    if len(vp_snapshots) >= 1:
        r1_vps = vp_snapshots[0]
        r1_leader = r1_vps.index(max(r1_vps))
        stats["r1_leader"] = r1_leader
        stats["r1_leader_won"] = (winner_id == r1_leader)
        r1_last = r1_vps.index(min(r1_vps))
        stats["r1_last"] = r1_last
        stats["r1_last_won"] = (winner_id == r1_last)

    return stats


# ── Batch Runner ───────────────────────────────────────────────────

def run_batch(config: dict, num_games: int, start_seed: int = 1,
              max_rounds: int = 20,
              player_configs: Optional[List[dict]] = None,
              verbose: bool = False) -> dict:
    """Run N games and aggregate statistics."""
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
    """Aggregate per-game stats into summary metrics."""
    n = len(all_stats)
    if n == 0:
        return {}

    agg = {"num_games": n, "num_players": num_players}

    # ── Game Health ────────────────────────────────────────────
    rounds = [s["rounds"] for s in all_stats]
    agg["avg_rounds"] = sum(rounds) / n
    agg["min_rounds"] = min(rounds)
    agg["max_rounds"] = max(rounds)
    agg["median_rounds"] = sorted(rounds)[n // 2]
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

    # ── Seat Balance ───────────────────────────────────────────
    win_counts = [0] * num_players
    for s in all_stats:
        if s["winner_id"] is not None:
            win_counts[s["winner_id"]] += 1
    games_with_winner = sum(win_counts)
    agg["win_rates"] = {i: win_counts[i] / games_with_winner if games_with_winner > 0 else 0
                        for i in range(num_players)}
    agg["win_counts"] = {i: win_counts[i] for i in range(num_players)}

    # VP statistics
    all_final_vps = [s["final_vps"] for s in all_stats]
    agg["avg_final_vp"] = [sum(vps[i] for vps in all_final_vps) / n
                           for i in range(num_players)]
    agg["avg_vp_per_player"] = sum(agg["avg_final_vp"]) / num_players

    # VP per round per player
    total_vp_all = sum(sum(s["final_vps"]) for s in all_stats)
    total_rounds_all = sum(s["rounds"] for s in all_stats)
    agg["avg_vp_per_player_per_round"] = (total_vp_all / num_players / total_rounds_all
                                           if total_rounds_all > 0 else 0)

    # ── Dial & VP Economy ──────────────────────────────────────
    total_vp_by_dial = {"CROSS": 0, "LEFT": 0, "RIGHT": 0}
    total_tricks_by_dial = {"CROSS": 0, "LEFT": 0, "RIGHT": 0}
    for s in all_stats:
        for pos in DIAL_POSITIONS:
            total_vp_by_dial[pos] += s["vp_by_dial"].get(pos, 0)
            total_tricks_by_dial[pos] += s["tricks_by_dial"].get(pos, 0)

    grand_total_vp = sum(total_vp_by_dial.values())
    agg["vp_share_by_dial"] = {pos: total_vp_by_dial[pos] / grand_total_vp
                                if grand_total_vp > 0 else 0
                                for pos in DIAL_POSITIONS}
    agg["tricks_share_by_dial"] = {
        pos: total_tricks_by_dial[pos] / sum(total_tricks_by_dial.values())
        if sum(total_tricks_by_dial.values()) > 0 else 0
        for pos in DIAL_POSITIONS
    }

    avg_vp_per_trick_by_dial = {}
    for pos in DIAL_POSITIONS:
        if total_tricks_by_dial[pos] > 0:
            avg_vp_per_trick_by_dial[pos] = total_vp_by_dial[pos] / total_tricks_by_dial[pos]
        else:
            avg_vp_per_trick_by_dial[pos] = 0
    agg["avg_vp_per_trick_by_dial"] = avg_vp_per_trick_by_dial

    # Game-ending dial position
    ending_dials = defaultdict(int)
    for s in all_stats:
        if s["game_ending_dial"]:
            ending_dials[s["game_ending_dial"]] += 1
    games_ended = sum(ending_dials.values())
    agg["game_ending_dial"] = {pos: ending_dials[pos] / games_ended
                                if games_ended > 0 else 0
                                for pos in DIAL_POSITIONS}

    # RIGHT VP share per player
    right_vp = [sum(s["vp_from_right"][i] for s in all_stats) for i in range(num_players)]
    total_player_vp = [sum(s["final_vps"][i] for s in all_stats) for i in range(num_players)]
    agg["right_vp_share_per_player"] = {
        i: right_vp[i] / total_player_vp[i] if total_player_vp[i] > 0 else 0
        for i in range(num_players)
    }

    # ── Faction Talents ────────────────────────────────────────
    total_talents = {f: 0 for f in FACTIONS}
    for s in all_stats:
        for f in FACTIONS:
            total_talents[f] += s["talent_activations"].get(f, 0)

    agg["talent_activations_total"] = dict(total_talents)
    agg["talent_activations_per_game"] = {f: total_talents[f] / n for f in FACTIONS}
    grand_total_talents = sum(total_talents.values())
    agg["talent_share"] = {f: total_talents[f] / grand_total_talents
                            if grand_total_talents > 0 else 0
                            for f in FACTIONS}
    agg["total_talents_per_game"] = grand_total_talents / n

    # ── Stagnation ─────────────────────────────────────────────
    tied_tricks = [s["tied_tricks"] for s in all_stats]
    agg["avg_tied_tricks"] = sum(tied_tricks) / n
    agg["tied_trick_rate"] = sum(tied_tricks) / sum(total_tricks) if sum(total_tricks) > 0 else 0
    max_stags = [s["max_stagnation"] for s in all_stats]
    agg["avg_max_stagnation"] = sum(max_stags) / n
    agg["worst_stagnation"] = max(max_stags) if max_stags else 0

    # ── Intern Draws ───────────────────────────────────────────
    intern_draws = [s["intern_draws"] for s in all_stats]
    agg["avg_intern_draws"] = sum(intern_draws) / n

    # ── R1 Leader Analysis (Castle's Blessing) ─────────────────
    r1_leader_wins = sum(1 for s in all_stats if s.get("r1_leader_won", False))
    r1_last_wins = sum(1 for s in all_stats if s.get("r1_last_won", False))
    games_with_r1 = sum(1 for s in all_stats if "r1_leader" in s)
    if games_with_r1 > 0:
        agg["r1_leader_win_rate"] = r1_leader_wins / games_with_r1
        agg["r1_last_win_rate"] = r1_last_wins / games_with_r1
    else:
        agg["r1_leader_win_rate"] = 0
        agg["r1_last_win_rate"] = 0

    return agg


# ── Report Printer ─────────────────────────────────────────────────

def print_report(agg: dict, config: dict):
    """Print formatted simulation report."""
    n = agg["num_games"]
    np_ = agg["num_players"]
    rules = config["game_rules"]

    print(f"\n{'='*65}")
    print(f"  HAMSTER HIGH COUNCIL — SIMULATION REPORT")
    print(f"  {n} games · {np_} players · VP target: {rules['vp_target']}")
    print(f"  RIGHT multiplier: ×{rules['alliance_dial']['multipliers']['RIGHT']}")
    print(f"  Castle's Blessing: {'ON' if rules['castles_blessing']['enabled'] else 'OFF'}")
    print(f"{'='*65}")

    # ── Game Health ────────────────────────────────────────────
    print(f"\n--- GAME HEALTH ---")
    print(f"  Average rounds:        {agg['avg_rounds']:.1f} (median {agg['median_rounds']})")
    print(f"  Round range:           {agg['min_rounds']}–{agg['max_rounds']}")
    print(f"  Round distribution:    ", end="")
    for r, count in sorted(agg["round_distribution"].items()):
        print(f"R{r}={count/n:.0%}  ", end="")
    print()
    print(f"  Avg tricks/game:       {agg['avg_tricks']:.1f}")
    print(f"  Avg tricks/round:      {agg['avg_tricks_per_round']:.1f}")
    print(f"  Timeout rate:          {agg['timeout_rate']:.1%}")

    # ── Seat Balance ───────────────────────────────────────────
    print(f"\n--- SEAT BALANCE ---")
    for i in range(np_):
        wr = agg["win_rates"][i]
        bar = "█" * int(wr * 40)
        flag = " ⚠️" if wr > 0.30 or wr < 0.20 else ""
        print(f"  P{i}: {wr:6.1%} ({agg['win_counts'][i]:>4} wins) {bar}{flag}")
    print(f"  Avg final VP/player:   {agg['avg_vp_per_player']:.1f}")
    print(f"  VP/player/round:       {agg['avg_vp_per_player_per_round']:.1f}")

    # ── VP Economy & Dial ──────────────────────────────────────
    print(f"\n--- VP ECONOMY & DIAL ---")
    for pos in DIAL_POSITIONS:
        share = agg["vp_share_by_dial"][pos]
        trick_share = agg["tricks_share_by_dial"][pos]
        avg_vp = agg["avg_vp_per_trick_by_dial"][pos]
        mult = rules["alliance_dial"]["multipliers"][pos]
        low = " (low wins)" if pos in rules["alliance_dial"]["low_wins"] else ""
        print(f"  {pos:6s}: {share:5.1%} of VP, "
              f"{trick_share:5.1%} of tricks, "
              f"avg {avg_vp:.1f} VP/trick (×{mult}{low})")

    total_right = agg["vp_share_by_dial"]["RIGHT"]
    flag = " ⚠️ high" if total_right > 0.45 else " ⚠️ low" if total_right < 0.25 else ""
    print(f"  RIGHT VP share:        {total_right:.1%}{flag}")

    print(f"\n  Game-ending dial position:")
    for pos in DIAL_POSITIONS:
        rate = agg["game_ending_dial"][pos]
        bar = "█" * int(rate * 30)
        print(f"    {pos:6s}: {rate:5.1%} {bar}")

    # ── Faction Talents ────────────────────────────────────────
    print(f"\n--- FACTION TALENTS ---")
    print(f"  Total talents/game:    {agg['total_talents_per_game']:.1f}")
    for f in FACTIONS:
        per_game = agg["talent_activations_per_game"][f]
        share = agg["talent_share"][f]
        name = FACTION_NAMES[f]
        sym = FACTION_SYMBOLS[f]
        talent_name = rules["talents"]["talent_list"][f]["name"]
        flag = ""
        if per_game < 0.3:
            flag = " ⚠️ rare"
        elif per_game > 3.0:
            flag = " ⚠️ frequent"
        print(f"  {sym} {f:7s} {talent_name:20s}: "
              f"{per_game:4.1f}/game ({share:4.1%}){flag}")

    # ── Stagnation ─────────────────────────────────────────────
    print(f"\n--- STAGNATION ---")
    print(f"  Avg tied tricks/game:  {agg['avg_tied_tricks']:.1f}")
    print(f"  Tied trick rate:       {agg['tied_trick_rate']:.1%}")
    print(f"  Avg worst streak:      {agg['avg_max_stagnation']:.1f}")
    worst = agg["worst_stagnation"]
    flag = " ⚠️ concern" if worst > 5 else ""
    print(f"  Global worst streak:   {worst}{flag}")

    # ── Intern & Blessing ──────────────────────────────────────
    print(f"\n--- SPECIAL MECHANICS ---")
    print(f"  Intern draws/game:     {agg['avg_intern_draws']:.1f}")
    print(f"  R1 leader win rate:    {agg['r1_leader_win_rate']:.1%}"
          f"{' ⚠️ high' if agg['r1_leader_win_rate'] > 0.35 else ''}")
    print(f"  R1 last-place win rate:{agg['r1_last_win_rate']:.1%}"
          f"{' ⚠️ low' if agg['r1_last_win_rate'] < 0.15 else ''}")

    # ── Flags Summary ──────────────────────────────────────────
    flags = []
    if agg["timeout_rate"] > 0.05:
        flags.append(f"High timeout rate ({agg['timeout_rate']:.0%})")
    for i in range(np_):
        if agg["win_rates"][i] > 0.30:
            flags.append(f"P{i} win rate too high ({agg['win_rates'][i]:.0%})")
        if agg["win_rates"][i] < 0.20:
            flags.append(f"P{i} win rate too low ({agg['win_rates'][i]:.0%})")
    if total_right > 0.45:
        flags.append(f"RIGHT VP share too high ({total_right:.0%})")
    if agg["worst_stagnation"] > 5:
        flags.append(f"Stagnation streak of {agg['worst_stagnation']} tied tricks")
    if agg["r1_leader_win_rate"] > 0.35:
        flags.append(f"R1 leader advantage ({agg['r1_leader_win_rate']:.0%})")

    if flags:
        print(f"\n{'!'*65}")
        print(f"  ⚠️  BALANCE FLAGS:")
        for flag in flags:
            print(f"    • {flag}")
        print(f"{'!'*65}")
    else:
        print(f"\n  ✅ No balance flags detected.")

    print()


# ── CLI ────────────────────────────────────────────────────────────

def build_player_configs(args, num_players: int) -> List[dict]:
    """Build player configs from CLI args."""
    configs = [{"skill": 1.0, "style": "balanced", "aggression": 0.5}
               for _ in range(num_players)]

    if args.preset == "experts":
        pass  # Default is already experts
    elif args.preset == "beginners":
        configs = [{"skill": 0.3, "style": "balanced", "aggression": 0.5}
                   for _ in range(num_players)]
    elif args.preset == "mixed":
        configs[0] = {"skill": 1.0, "style": "balanced", "aggression": 0.5}
        for i in range(1, num_players):
            configs[i] = {"skill": 0.3, "style": "balanced", "aggression": 0.5}
    elif args.preset == "styles":
        style_list = ["balanced", "aggressive", "tactical", "cooperative"]
        for i in range(num_players):
            configs[i] = {"skill": 1.0, "style": style_list[i % len(style_list)],
                         "aggression": 0.5}

    # Override with explicit flags
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

    if args.aggression:
        aggs = [float(a) for a in args.aggression.split(",")]
        for i, a in enumerate(aggs):
            if i < len(configs):
                configs[i]["aggression"] = a

    return configs


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Hamster High Council — Batch Simulation Runner")
    parser.add_argument("-n", "--num-games", type=int, default=500,
                       help="Number of games to simulate (default: 500)")
    parser.add_argument("-s", "--seed", type=int, default=1,
                       help="Starting random seed (default: 1)")
    parser.add_argument("--max-rounds", type=int, default=20,
                       help="Max rounds per game before timeout (default: 20)")
    parser.add_argument("-v", "--verbose", action="store_true",
                       help="Print progress every 100 games")
    parser.add_argument("--config", type=str, default=None,
                       help="Path to config.json")
    parser.add_argument("--json", type=str, default=None,
                       help="Export full stats to JSON file")

    # Rule overrides
    parser.add_argument("--vp-target", type=int, default=None,
                       help="Override VP target (default: from config)")
    parser.add_argument("--right-multiplier", type=int, default=None,
                       help="Override RIGHT multiplier (default: from config)")
    parser.add_argument("--blessing-off", action="store_true",
                       help="Disable Castle's Blessing")
    parser.add_argument("--talents-off", action="store_true",
                       help="Disable all faction talents")
    parser.add_argument("--compression-off", action="store_true",
                       help="Disable VP compression for leader on RIGHT")
    parser.add_argument("--compression-on", action="store_true",
                       help="Enable VP compression for leader on RIGHT")

    # Player configs
    parser.add_argument("--preset", type=str, default="experts",
                       choices=["experts", "beginners", "mixed", "styles"],
                       help="Player config preset (default: experts)")
    parser.add_argument("--skill", type=str, default=None,
                       help="Comma-separated skill levels: '1.0,0.5,0.3,0.3'")
    parser.add_argument("--styles", type=str, default=None,
                       help="Comma-separated styles: 'balanced,aggressive,tactical,cooperative'")
    parser.add_argument("--aggression", type=str, default=None,
                       help="Comma-separated aggression: '0.5,0.8,0.2,0.5'")

    args = parser.parse_args()

    # Load config
    config = GameState.load_config(args.config)

    # Apply overrides
    if args.vp_target is not None:
        config["game_rules"]["vp_target"] = args.vp_target
    if args.right_multiplier is not None:
        config["game_rules"]["alliance_dial"]["multipliers"]["RIGHT"] = args.right_multiplier
    if args.blessing_off:
        config["game_rules"]["castles_blessing"]["enabled"] = False
    if args.talents_off:
        config["game_rules"]["talents"]["enabled"] = False
    if args.compression_off:
        config["game_rules"]["scoring"]["vp_compression"] = False
    if args.compression_on:
        config["game_rules"]["scoring"]["vp_compression"] = True

    player_configs = build_player_configs(args, config["game_rules"]["num_players"])

    # Print setup
    print(f"\nHamster High Council Simulator")
    print(f"Running {args.num_games} games with seed {args.seed}...")
    if args.preset != "experts":
        print(f"Preset: {args.preset}")
    for i, pc in enumerate(player_configs):
        print(f"  P{i}: skill={pc['skill']:.1f}, style={pc['style']}, "
              f"aggression={pc['aggression']:.1f}")

    start_time = time.time()
    agg = run_batch(config, args.num_games, start_seed=args.seed,
                    max_rounds=args.max_rounds,
                    player_configs=player_configs,
                    verbose=args.verbose)
    elapsed = time.time() - start_time

    print(f"\nCompleted in {elapsed:.1f}s ({args.num_games / elapsed:.0f} games/sec)")

    print_report(agg, config)

    if args.json:
        # Make stats JSON-serializable
        with open(args.json, 'w') as f:
            json.dump(agg, f, indent=2, default=str)
        print(f"Stats exported to {args.json}")
