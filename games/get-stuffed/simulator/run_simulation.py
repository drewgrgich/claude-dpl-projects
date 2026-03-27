"""
Batch simulation runner for Get Stuffed.

Runs N AI-vs-AI games, collects per-game stats, and prints an
aggregate report highlighting balance issues.

Usage:
    python run_simulation.py -n 500 -p 4
    python run_simulation.py -n 200 -p 3 --preset styles --json results.json
"""

import argparse
import json
import os
import sys
import statistics
from collections import defaultdict
from typing import List, Dict, Optional

from cards import build_deck, Card
from game_state import GameState
from ai_player import HeuristicAI, STYLE_PROFILES


# ─── Single Game ──────────────────────────────────────

def run_single_game(config: dict, num_players: int, seed: int,
                    max_turns: int = 300,
                    player_configs: Optional[List[dict]] = None) -> dict:
    """Run one complete game and return stats."""

    game = GameState(config, num_players, seed=seed)

    # Create AIs
    ais: List[HeuristicAI] = []
    for i in range(num_players):
        pc = {}
        if player_configs and i < len(player_configs):
            pc = player_configs[i]
        ais.append(HeuristicAI(
            player_id=i,
            skill=pc.get("skill", 1.0),
            style=pc.get("style", "balanced"),
            aggression=pc.get("aggression", 0.5),
            rng_seed=seed + i * 1000,
        ))

    # Setup with P0 bonus discard if enabled
    p0_discard_fn = None
    if game.rules["setup"].get("p0_bonus_card", False) and len(ais) > 0:
        p0_discard_fn = lambda p, g: ais[0].choose_p0_discard(p, g)
    game.setup(p0_discard_fn=p0_discard_fn)

    turn_count = 0
    forced_scavenge_active = False

    while not game.game_over and turn_count < max_turns:
        player = game.current_player
        ai = ais[player.id]
        turn_count += 1
        game.turn_number = turn_count

        # Check for forced scavenge (Dib It)
        if forced_scavenge_active:
            forced_scavenge_active = False
            scav_result = game.scavenge(player,
                                         mercy_decision_fn=ai.decide_mercy)
            if scav_result.get("game_over"):
                break

            # Sugar Crash: even after scavenge, get a free dump
            if game.sugar_crash and player.hand_size > 0:
                dump_card = ai.choose_sugar_crash_dump(player, game)
                if dump_card:
                    player.remove_card(dump_card)
                    game.pit.append(dump_card)
                    game.stats["per_player"][player.id]["sugar_crash_free_dumps"] += 1
                    game._log(f"  Sugar Crash free dump: P{player.id} dumps {dump_card}")
                    if player.hand_size == 0:
                        game.game_over = True
                        game.winner = player.id
                        break

            game.advance_turn()
            continue

        # Normal turn: try to play a card
        card, decl = ai.choose_card_to_play(player, game)

        if card is not None:
            # Play the card with AI power decisions
            power_decisions = ai.get_power_decisions(player, game)
            result = game.play_card(player, card, declared_faction=decl,
                                    power_decision_fn=power_decisions)

            if result.get("game_over"):
                break

            # Check for Dib It flag
            if game.forced_scavenge_player is not None:
                forced_scavenge_active = True
                # Override next player to be the forced scavenge target
                game.current_player_idx = game.forced_scavenge_player
                game.forced_scavenge_player = None
                continue

            # Sugar Crash: play a second card (free dump)
            if game.sugar_crash and player.hand_size > 0:
                dump_card = ai.choose_sugar_crash_dump(player, game)
                if dump_card:
                    player.remove_card(dump_card)
                    game.pit.append(dump_card)
                    game.stats["per_player"][player.id]["sugar_crash_free_dumps"] += 1
                    game._log(f"  Sugar Crash free dump: P{player.id} dumps {dump_card}")
                    if player.hand_size == 0:
                        game.game_over = True
                        game.winner = player.id
                        break

        else:
            # Can't play — Scavenge
            scav_result = game.scavenge(player,
                                         mercy_decision_fn=ai.decide_mercy)
            if scav_result.get("game_over"):
                break

            # Sugar Crash: even after scavenge, get a free dump
            if game.sugar_crash and player.hand_size > 0:
                dump_card = ai.choose_sugar_crash_dump(player, game)
                if dump_card:
                    player.remove_card(dump_card)
                    game.pit.append(dump_card)
                    game.stats["per_player"][player.id]["sugar_crash_free_dumps"] += 1
                    game._log(f"  Sugar Crash free dump: P{player.id} dumps {dump_card}")
                    if player.hand_size == 0:
                        game.game_over = True
                        game.winner = player.id
                        break

            # Check for Dib It flag from scavenge power
            if game.forced_scavenge_player is not None:
                forced_scavenge_active = True
                game.current_player_idx = game.forced_scavenge_player
                game.forced_scavenge_player = None
                continue

        game.advance_turn()

    # Compile stats
    return compile_game_stats(game, turn_count, max_turns, player_configs)


def compile_game_stats(game: GameState, turn_count: int,
                       max_turns: int,
                       player_configs: Optional[List[dict]] = None) -> dict:
    """Extract all interesting stats from a completed game."""
    stats = {
        "seed": game.seed,
        "num_players": game.num_players,
        "winner": game.winner,
        "turns": turn_count,
        "timed_out": turn_count >= max_turns,
        "sugar_crash_activated": game.sugar_crash,
        "sugar_crash_turn": game.stats["sugar_crash_turn"],
        "reshuffles": game.stats["reshuffles"],
        "total_scavenges": game.stats["scavenges"],
        "total_mercy_saves": game.stats["mercy_saves"],
        "total_cards_played": game.stats["cards_played"],
        "total_cards_drawn": game.stats["cards_drawn_total"],
        "scavenge_penalties": game.stats["scavenge_penalties"],
        "powers_triggered": dict(game.stats["powers_triggered"]),
        "final_hand_sizes": {p.id: p.hand_size for p in game.players},
        "per_player": dict(game.stats["per_player"]),
    }

    if player_configs:
        stats["player_configs"] = player_configs

    return stats


# ─── Batch Runner ─────────────────────────────────────

def run_batch(config: dict, num_games: int, num_players: int,
              start_seed: int = 1, max_turns: int = 300,
              player_configs: Optional[List[dict]] = None,
              verbose: bool = False) -> dict:
    """Run N games and aggregate statistics."""
    all_stats = []

    for i in range(num_games):
        seed = start_seed + i
        stats = run_single_game(config, num_players, seed, max_turns, player_configs)
        all_stats.append(stats)

        if verbose and (i + 1) % 50 == 0:
            print(f"  Completed {i + 1}/{num_games} games...")

    return aggregate_stats(all_stats, num_players)


def aggregate_stats(all_stats: List[dict], num_players: int) -> dict:
    """Aggregate per-game stats into summary statistics."""
    n = len(all_stats)

    # Basic
    turns = [s["turns"] for s in all_stats]
    timed_out = sum(1 for s in all_stats if s["timed_out"])
    sugar_crash_games = sum(1 for s in all_stats if s["sugar_crash_activated"])
    sugar_crash_turns = [s["sugar_crash_turn"] for s in all_stats
                         if s["sugar_crash_turn"] is not None]

    # Win rates
    win_counts = defaultdict(int)
    for s in all_stats:
        if s["winner"] is not None:
            win_counts[s["winner"]] += 1

    decided_games = sum(1 for s in all_stats if s["winner"] is not None)
    win_rates = {}
    for pid in range(num_players):
        win_rates[pid] = win_counts[pid] / decided_games if decided_games > 0 else 0

    # Scavenging
    total_scavenges = [s["total_scavenges"] for s in all_stats]
    total_mercy = [s["total_mercy_saves"] for s in all_stats]
    all_penalties = []
    for s in all_stats:
        all_penalties.extend(s["scavenge_penalties"])

    # Powers
    power_totals = defaultdict(int)
    for s in all_stats:
        for faction, count in s["powers_triggered"].items():
            power_totals[faction] += count

    # Per-player aggregation
    per_player_agg = {}
    for pid in range(num_players):
        cards_played = [s["per_player"][pid]["cards_played"] for s in all_stats]
        cards_drawn = [s["per_player"][pid]["cards_drawn"] for s in all_stats]
        scavenges = [s["per_player"][pid]["scavenges"] for s in all_stats]
        max_hands = [s["per_player"][pid]["max_hand_size"] for s in all_stats]
        final_hands = [s["final_hand_sizes"][pid] for s in all_stats]

        per_player_agg[pid] = {
            "avg_cards_played": statistics.mean(cards_played),
            "avg_cards_drawn": statistics.mean(cards_drawn),
            "avg_scavenges": statistics.mean(scavenges),
            "avg_max_hand": statistics.mean(max_hands),
            "avg_final_hand": statistics.mean(final_hands),
        }

    # First-player advantage
    first_player_wins = sum(1 for s in all_stats if s["winner"] == 0)
    first_player_rate = first_player_wins / decided_games if decided_games > 0 else 0

    agg = {
        "num_games": n,
        "num_players": num_players,
        "decided_games": decided_games,
        "timed_out": timed_out,
        "timeout_rate": timed_out / n,

        "avg_turns": statistics.mean(turns),
        "median_turns": statistics.median(turns),
        "stdev_turns": statistics.stdev(turns) if n > 1 else 0,
        "min_turns": min(turns),
        "max_turns": max(turns),
        "turns_p10": sorted(turns)[n // 10] if n >= 10 else min(turns),
        "turns_p90": sorted(turns)[9 * n // 10] if n >= 10 else max(turns),

        "win_rates": win_rates,
        "first_player_advantage": first_player_rate,
        "first_player_expected": 1.0 / num_players,

        "sugar_crash_rate": sugar_crash_games / n,
        "avg_sugar_crash_turn": (statistics.mean(sugar_crash_turns)
                                  if sugar_crash_turns else None),

        "avg_scavenges_per_game": statistics.mean(total_scavenges),
        "avg_mercy_saves_per_game": statistics.mean(total_mercy),
        "mercy_rate": (sum(total_mercy) / sum(total_scavenges)
                       if sum(total_scavenges) > 0 else 0),
        "avg_penalty_draw": (statistics.mean(all_penalties)
                              if all_penalties else 0),
        "max_penalty_draw": max(all_penalties) if all_penalties else 0,
        "penalty_distribution": _histogram(all_penalties, bins=[0,1,2,3,4,5,6,7,8,9,10]),

        "power_totals": dict(power_totals),
        "power_per_game": {f: c / n for f, c in power_totals.items()},

        "per_player": per_player_agg,

        "reshuffles_per_game": statistics.mean(
            [s["reshuffles"] for s in all_stats]),
    }

    return agg


def _histogram(values: list, bins: list) -> dict:
    """Count values falling into each bin."""
    hist = {b: 0 for b in bins}
    for v in values:
        for b in sorted(bins, reverse=True):
            if v >= b:
                hist[b] += 1
                break
    return hist


# ─── Report ───────────────────────────────────────────

def print_report(agg: dict):
    """Print a human-readable simulation report."""
    n = agg["num_games"]
    np = agg["num_players"]

    print(f"\n{'='*65}")
    print(f"  GET STUFFED SIMULATION REPORT")
    print(f"  {n} games | {np} players")
    print(f"{'='*65}")

    # Game Length
    print(f"\n--- Game Length ---")
    print(f"  Average:  {agg['avg_turns']:.1f} turns  (median: {agg['median_turns']:.0f})")
    print(f"  Range:    {agg['min_turns']}–{agg['max_turns']} turns")
    print(f"  P10/P90:  {agg['turns_p10']}–{agg['turns_p90']} turns")
    print(f"  Std Dev:  {agg['stdev_turns']:.1f}")
    if agg["timed_out"] > 0:
        print(f"  ⚠️  TIMED OUT: {agg['timed_out']}/{n} games "
              f"({agg['timeout_rate']:.1%}) hit turn limit!")

    # Win Rates
    print(f"\n--- Win Rates (by seat position) ---")
    expected = agg["first_player_expected"]
    for pid, rate in sorted(agg["win_rates"].items()):
        bar = "█" * int(rate * 50)
        flag = ""
        if abs(rate - expected) > 0.05:
            flag = " ⚠️" if rate > expected + 0.05 else " ⚠️"
        print(f"  P{pid}: {rate:6.1%} {bar}{flag}")
    print(f"  Expected (fair): {expected:.1%} each")
    fpa = agg["first_player_advantage"]
    if abs(fpa - expected) > 0.05:
        print(f"  ⚠️  First-player advantage: {fpa:.1%} vs expected {expected:.1%}")

    # Sugar Crash
    print(f"\n--- Sugar Crash ---")
    print(f"  Triggered: {agg['sugar_crash_rate']:.1%} of games")
    if agg["avg_sugar_crash_turn"]:
        print(f"  Avg onset:  turn {agg['avg_sugar_crash_turn']:.0f}")

    # Scavenging
    print(f"\n--- Scavenging ---")
    print(f"  Avg scavenges/game:  {agg['avg_scavenges_per_game']:.1f}")
    print(f"  Mercy save rate:     {agg['mercy_rate']:.1%}")
    print(f"  Avg penalty draw:    {agg['avg_penalty_draw']:.1f} cards")
    print(f"  Max penalty draw:    {agg['max_penalty_draw']} cards")
    if agg["avg_penalty_draw"] > 6:
        print(f"  ⚠️  High average penalty — scavenging may be too punishing!")

    # Penalty distribution
    print(f"\n  Penalty size distribution:")
    pd = agg["penalty_distribution"]
    total_pen = sum(pd.values())
    if total_pen > 0:
        for rank in sorted(pd.keys()):
            pct = pd[rank] / total_pen
            bar = "█" * int(pct * 40)
            print(f"    {rank:2d}+ cards: {pd[rank]:5d} ({pct:5.1%}) {bar}")

    # Faction Powers
    print(f"\n--- Faction Powers (total triggers across all games) ---")
    faction_names = {
        "RED": "🔴 Hot Potato",
        "ORANGE": "🟠 Dib It",
        "YELLOW": "🟡 Re-Tinker",
        "GREEN": "🟢 I Foresaw This",
        "BLUE": "🔵 Magicians",
        "PURPLE": "🟣 Time Warp",
    }
    for faction in ["RED", "ORANGE", "YELLOW", "GREEN", "BLUE", "PURPLE"]:
        total = agg["power_totals"].get(faction, 0)
        per_game = agg["power_per_game"].get(faction, 0)
        print(f"  {faction_names[faction]:25s}: {total:5d} total  ({per_game:.1f}/game)")

    # Per-player
    print(f"\n--- Per-Player Averages ---")
    print(f"  {'':4s} {'Played':>8s} {'Drawn':>8s} {'Scav':>6s} {'MaxHand':>8s} {'FinalHand':>10s}")
    for pid in range(np):
        pp = agg["per_player"][pid]
        print(f"  P{pid}:  {pp['avg_cards_played']:7.1f} {pp['avg_cards_drawn']:7.1f} "
              f"{pp['avg_scavenges']:5.1f} {pp['avg_max_hand']:7.1f} {pp['avg_final_hand']:9.1f}")

    # Reshuffles
    print(f"\n--- Reshuffles ---")
    print(f"  Average per game: {agg['reshuffles_per_game']:.2f}")

    # Warnings summary
    print(f"\n{'='*65}")
    print(f"  ISSUES & WARNINGS")
    print(f"{'='*65}")
    issues = []

    if agg["timeout_rate"] > 0.05:
        issues.append(f"HIGH TIMEOUT RATE ({agg['timeout_rate']:.1%}): "
                      f"Games are stalling. Consider adjusting scavenge penalties or Sugar Crash timing.")

    fpa_dev = abs(agg["first_player_advantage"] - expected)
    if fpa_dev > 0.05:
        issues.append(f"SEAT IMBALANCE: P0 wins {agg['first_player_advantage']:.1%} "
                      f"(expected {expected:.1%}). {fpa_dev:.1%} deviation.")

    max_wr = max(agg["win_rates"].values())
    min_wr = min(agg["win_rates"].values())
    if max_wr - min_wr > 0.10:
        issues.append(f"WIN RATE SPREAD: {max_wr - min_wr:.1%} gap between best and worst seat. "
                      f"May indicate positional advantage.")

    if agg["avg_penalty_draw"] > 6:
        issues.append(f"PUNISHING SCAVENGE: Avg penalty is {agg['avg_penalty_draw']:.1f} cards. "
                      f"Players who can't play face massive hand bloat.")

    if agg["sugar_crash_rate"] > 0.3:
        issues.append(f"FREQUENT SUGAR CRASH ({agg['sugar_crash_rate']:.1%}): "
                      f"Many games need the turbo finish. Deck may be too large or shedding too slow.")

    if agg["mercy_rate"] < 0.1:
        issues.append(f"LOW MERCY RATE ({agg['mercy_rate']:.1%}): "
                      f"Mercy Clause rarely helps. Scavenge penalty feels inescapable.")

    if agg["avg_turns"] > 80:
        issues.append(f"LONG GAMES ({agg['avg_turns']:.0f} avg turns): "
                      f"Games run longer than the target 10-15 minute window.")

    if agg["avg_turns"] < 15:
        issues.append(f"SHORT GAMES ({agg['avg_turns']:.0f} avg turns): "
                      f"Games may end too quickly for powers to matter.")

    # Check power frequency balance
    power_per_game = agg["power_per_game"]
    non_purple_powers = {f: v for f, v in power_per_game.items() if f != "PURPLE"}
    if non_purple_powers:
        max_power = max(non_purple_powers.values())
        min_power = min(non_purple_powers.values())
        if max_power > 0 and min_power / max_power < 0.3:
            least = min(non_purple_powers, key=non_purple_powers.get)
            most = max(non_purple_powers, key=non_purple_powers.get)
            issues.append(f"POWER IMBALANCE: {faction_names[most]} fires {max_power:.1f}/game "
                          f"vs {faction_names[least]} at {min_power:.1f}/game.")

    if not issues:
        print("  ✅ No major issues detected!")
    else:
        for i, issue in enumerate(issues, 1):
            print(f"  {i}. {issue}")

    print(f"\n{'='*65}\n")


# ─── CLI ──────────────────────────────────────────────

def load_config(config_path: Optional[str] = None) -> dict:
    """Load config.json, auto-detecting location."""
    if config_path:
        with open(config_path) as f:
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

    raise FileNotFoundError("config.json not found!")


def build_player_configs(args, num_players: int) -> Optional[List[dict]]:
    """Build per-player AI configurations from CLI args."""
    configs = None

    if args.preset:
        if args.preset == "experts":
            configs = [{"skill": 1.0, "style": "balanced", "aggression": 0.5}
                       for _ in range(num_players)]
        elif args.preset == "beginners":
            configs = [{"skill": 0.3, "style": "balanced", "aggression": 0.5}
                       for _ in range(num_players)]
        elif args.preset == "mixed":
            configs = [{"skill": 1.0, "style": "balanced", "aggression": 0.5}]
            configs += [{"skill": 0.3, "style": "balanced", "aggression": 0.5}
                        for _ in range(num_players - 1)]
        elif args.preset == "styles":
            style_list = ["balanced", "aggressive_shed", "disruptive", "hoarder"]
            configs = [{"skill": 1.0, "style": style_list[i % len(style_list)],
                         "aggression": 0.5}
                       for i in range(num_players)]

    if args.skill:
        if configs is None:
            configs = [{"skill": 1.0, "style": "balanced", "aggression": 0.5}
                       for _ in range(num_players)]
        skills = [float(s) for s in args.skill.split(",")]
        for i, s in enumerate(skills):
            if i < len(configs):
                configs[i]["skill"] = s

    if args.styles:
        if configs is None:
            configs = [{"skill": 1.0, "style": "balanced", "aggression": 0.5}
                       for _ in range(num_players)]
        styles = args.styles.split(",")
        for i, s in enumerate(styles):
            if i < len(configs):
                configs[i]["style"] = s.strip()

    return configs


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Run batch simulation of Get Stuffed")
    parser.add_argument("-n", "--num-games", type=int, default=100,
                        help="Number of games to simulate")
    parser.add_argument("-p", "--players", type=int, default=4,
                        help="Number of players (2-6)")
    parser.add_argument("-s", "--seed", type=int, default=1,
                        help="Starting random seed")
    parser.add_argument("--max-turns", type=int, default=300,
                        help="Max turns before game is aborted")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Print progress during simulation")
    parser.add_argument("--config", type=str, default=None,
                        help="Path to config.json")
    parser.add_argument("--json", type=str, default=None,
                        help="Export results to JSON file")

    # Player configuration
    parser.add_argument("--skill", type=str, default=None,
                        help="Comma-separated skill levels: '1.0,0.5,0.3'")
    parser.add_argument("--styles", type=str, default=None,
                        help="Comma-separated styles: 'balanced,disruptive'")
    parser.add_argument("--preset", type=str, default=None,
                        choices=["experts", "beginners", "mixed", "styles"],
                        help="Preset player configurations")

    # Rule variants
    parser.add_argument("--p0-bonus", action="store_true",
                        help="Enable P0 bonus card rule (deal+1, discard 1 after seeing pit)")
    parser.add_argument("--p0-fewer", type=int, default=None,
                        help="P0 starts with N fewer cards (e.g. --p0-fewer 1)")

    args = parser.parse_args()

    config = load_config(args.config)

    # Apply rule overrides
    if args.p0_bonus:
        config["game_rules"]["setup"]["p0_bonus_card"] = True
    if args.p0_fewer is not None:
        config["game_rules"]["setup"]["p0_fewer_cards"] = args.p0_fewer
    player_configs = build_player_configs(args, args.players)

    print(f"Running {args.num_games} games with {args.players} players "
          f"(seed {args.seed})...")
    if player_configs:
        for i, pc in enumerate(player_configs):
            print(f"  P{i}: skill={pc.get('skill', 1.0):.1f} "
                  f"style={pc.get('style', 'balanced')} "
                  f"aggression={pc.get('aggression', 0.5):.1f}")

    agg = run_batch(config, args.num_games, args.players,
                    start_seed=args.seed, max_turns=args.max_turns,
                    player_configs=player_configs, verbose=args.verbose)

    print_report(agg)

    if args.json:
        # Convert any non-serializable keys
        serializable = json.loads(json.dumps(agg, default=str))
        with open(args.json, 'w') as f:
            json.dump(serializable, f, indent=2)
        print(f"Results saved to {args.json}")
