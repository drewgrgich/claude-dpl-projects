#!/usr/bin/env python3
"""
Batch simulation runner for The Tunnel Brawl v2.0.

Runs N AI-vs-AI games and collects comprehensive metrics on game balance,
pacing, faction usage, Wild mechanics, CLASH! frequency, and more.
"""

import argparse
import json
import os
import sys
from collections import defaultdict
from typing import List, Dict, Optional

from cards import Card, build_deck
from game_state import GameState
from ai_player import HeuristicAI, STYLE_PROFILES


# ─── Single Game Runner ──────────────────────────────────────────

def run_single_game(config: dict, num_players: int, seed: int,
                    max_rounds: int = 50, player_configs: List[dict] = None,
                    verbose: bool = False) -> dict:
    """Run one complete game and return a stats dict."""
    game = GameState(config, num_players, seed=seed)
    game.setup()

    # Create AIs
    ais = []
    for i in range(num_players):
        pc = player_configs[i] if player_configs and i < len(player_configs) else {}
        ais.append(HeuristicAI(
            player_id=i,
            skill=pc.get("skill", 1.0),
            style=pc.get("style", "balanced"),
            aggression=pc.get("aggression", 0.5),
            rng_seed=seed * 100 + i,
        ))

    # Tracking
    faction_wins = defaultdict(int)
    faction_plays = defaultdict(int)
    clash_count = 0
    clash_chain_lengths = []
    wild_plays = 0
    wild_activations = 0
    wild_trips = 0
    talent_triggers = defaultdict(int)
    vp_per_round = {i: [] for i in range(num_players)}
    rounds_with_clash = 0

    # Play the game
    while not game.game_over and game.round_number < max_rounds:
        # Step 1: Simultaneous deployment
        for i, player in enumerate(game.players):
            forced = player.forced_card
            if forced and forced not in player.hand:
                forced = None
                player.forced_card = None

            if len(player.hand) < 2:
                # Not enough cards — skip this player's deployment
                # Give them a "pass" round
                if player.hand:
                    home = player.hand[0]
                    away = player.hand[0]  # Will fail, handle gracefully
                else:
                    continue
            else:
                home, away = ais[i].choose_deployment(player.hand, game, forced)

            result = game.set_deployment(i, home, away)
            if not result["success"] and len(player.hand) >= 2:
                # Fallback: play first two cards
                home, away = player.hand[0], player.hand[1]
                game.set_deployment(i, home, away)

            # Track faction plays
            faction_plays[home.faction] += 1
            faction_plays[away.faction] += 1
            if home.is_wild:
                wild_plays += 1
            if away.is_wild:
                wild_plays += 1

            player.forced_card = None

        # Verify all players deployed
        if len(game.deployments) < num_players:
            break

        # Step 2 & 3: Reveal and resolve brawls
        def clash_card_chooser(pid, gs, cr):
            return ais[pid].choose_clash_card(pid, gs, cr)

        round_data = game.resolve_round(clash_card_chooser)

        # Track brawl results
        round_had_clash = False
        for br in round_data["brawl_results"]:
            if br.winner_id is not None:
                # Track which faction won
                winner_card = br.attacker_card if br.winner_id == br.attacker_id else br.defender_card
                faction_wins[winner_card.faction] += 1

            if br.is_clash or br.clash_round > 0:
                if br.clash_round > 0:
                    clash_count += 1
                round_had_clash = True

            if br.attacker_wild_activated:
                wild_activations += 1
            if br.defender_wild_activated:
                wild_activations += 1

        if round_had_clash:
            rounds_with_clash += 1

        # Step 4: Faction talents
        for i, player in enumerate(game.players):
            if game.can_trigger_talent(i):
                winning_cards = game.round_winning_cards.get(i, [])
                doubled = game.has_double_talent(i)
                faction = ais[i].choose_talent_faction(winning_cards, doubled, game)
                if faction:
                    def green_chooser(my_id, target_id, target_hand, gs):
                        return ais[my_id].choose_green_target(my_id, target_id, target_hand, gs)

                    game.apply_talent(i, faction, doubled, green_chooser)
                    talent_triggers[faction] += 1

        # Step 5: Draw phase
        game.draw_phase()

        # Track VP progression
        for p in game.players:
            vp_per_round[p.id].append(p.victory_points)

        # Check game end
        game.check_game_end()

        # 3-player: rotate defender
        if num_players == 3:
            game.rotate_defender()

        # Clear deployments for next round
        game.deployments.clear()

    # Compile stats
    stats = {
        "seed": seed,
        "num_players": num_players,
        "rounds": game.round_number,
        "winner": game.winner_id,
        "reached_max_rounds": game.round_number >= max_rounds and not game.game_over,
        "final_scores": {p.id: p.victory_points for p in game.players},
        "per_player": {},
        "clash_count": clash_count,
        "rounds_with_clash": rounds_with_clash,
        "clash_rate": rounds_with_clash / max(game.round_number, 1),
        "wild_plays": wild_plays,
        "wild_activations": wild_activations,
        "wild_trips": wild_plays - wild_activations,
        "wild_activation_rate": wild_activations / max(wild_plays, 1),
        "faction_wins": dict(faction_wins),
        "faction_plays": dict(faction_plays),
        "talent_triggers": dict(talent_triggers),
        "vp_per_round": {k: v for k, v in vp_per_round.items()},
    }

    for p in game.players:
        stats["per_player"][p.id] = {
            "vp": p.victory_points,
            "brawls_won": p.brawls_won,
            "brawls_lost": p.brawls_lost,
            "clashes_won": p.clashes_won,
            "clashes_lost": p.clashes_lost,
            "wilds_activated": p.wilds_activated,
            "wilds_tripped": p.wilds_tripped,
            "talents_triggered": p.talents_triggered,
            "cards_drawn": p.cards_drawn,
            "final_hand": len(p.hand),
            "dominations": p.dominations,
        }

    if verbose:
        for line in game.log:
            print(line)

    return stats


# ─── Batch Runner ────────────────────────────────────────────────

def run_batch(config: dict, num_games: int, num_players: int,
              start_seed: int = 1, max_rounds: int = 50,
              player_configs: List[dict] = None,
              verbose: bool = False) -> dict:
    """Run N games and aggregate statistics."""
    all_stats = []
    for i in range(num_games):
        stats = run_single_game(
            config, num_players, seed=start_seed + i,
            max_rounds=max_rounds, player_configs=player_configs,
            verbose=verbose,
        )
        all_stats.append(stats)
        if (i + 1) % 100 == 0:
            print(f"  ... completed {i + 1}/{num_games} games", file=sys.stderr)

    return aggregate_stats(all_stats, num_players)


def aggregate_stats(all_stats: List[dict], num_players: int) -> dict:
    """Aggregate stats from multiple games into a summary report."""
    n = len(all_stats)

    # Win rates
    wins = defaultdict(int)
    for s in all_stats:
        if s["winner"] is not None:
            wins[s["winner"]] += 1
    win_rates = {pid: wins[pid] / n for pid in range(num_players)}

    # Game length
    rounds = [s["rounds"] for s in all_stats]
    avg_rounds = sum(rounds) / n
    min_rounds = min(rounds)
    max_rounds_val = max(rounds)
    timeout_rate = sum(1 for s in all_stats if s["reached_max_rounds"]) / n

    # VP stats
    final_vps = {pid: [s["final_scores"][pid] for s in all_stats] for pid in range(num_players)}
    avg_vp = {pid: sum(vps) / n for pid, vps in final_vps.items()}
    vp_std = {}
    for pid, vps in final_vps.items():
        mean = avg_vp[pid]
        vp_std[pid] = (sum((v - mean) ** 2 for v in vps) / n) ** 0.5

    # CLASH! stats
    total_clashes = sum(s["clash_count"] for s in all_stats)
    avg_clashes = total_clashes / n
    avg_clash_rate = sum(s["clash_rate"] for s in all_stats) / n

    # Wild stats
    total_wild_plays = sum(s["wild_plays"] for s in all_stats)
    total_wild_activations = sum(s["wild_activations"] for s in all_stats)
    wild_activation_rate = total_wild_activations / max(total_wild_plays, 1)

    # Faction win rates
    faction_wins = defaultdict(int)
    faction_plays = defaultdict(int)
    for s in all_stats:
        for f, count in s["faction_wins"].items():
            faction_wins[f] += count
        for f, count in s["faction_plays"].items():
            faction_plays[f] += count
    faction_win_rates = {}
    for f in faction_plays:
        faction_win_rates[f] = faction_wins.get(f, 0) / max(faction_plays[f], 1)

    # Talent triggers
    total_talents = defaultdict(int)
    for s in all_stats:
        for f, count in s["talent_triggers"].items():
            total_talents[f] += count
    avg_talents = {f: total_talents[f] / n for f in total_talents}

    # Per-player aggregates
    per_player_agg = {}
    for pid in range(num_players):
        per_player_agg[pid] = {
            "avg_vp": avg_vp[pid],
            "vp_std": vp_std[pid],
            "win_rate": win_rates[pid],
            "avg_brawls_won": sum(s["per_player"][pid]["brawls_won"] for s in all_stats) / n,
            "avg_brawls_lost": sum(s["per_player"][pid]["brawls_lost"] for s in all_stats) / n,
            "avg_clashes_won": sum(s["per_player"][pid]["clashes_won"] for s in all_stats) / n,
            "avg_wilds_activated": sum(s["per_player"][pid]["wilds_activated"] for s in all_stats) / n,
            "avg_wilds_tripped": sum(s["per_player"][pid]["wilds_tripped"] for s in all_stats) / n,
            "avg_talents_triggered": sum(s["per_player"][pid]["talents_triggered"] for s in all_stats) / n,
            "avg_cards_drawn": sum(s["per_player"][pid]["cards_drawn"] for s in all_stats) / n,
            "avg_dominations": sum(s["per_player"][pid]["dominations"] for s in all_stats) / n,
        }

    return {
        "num_games": n,
        "num_players": num_players,
        "win_rates": win_rates,
        "avg_rounds": avg_rounds,
        "min_rounds": min_rounds,
        "max_rounds": max_rounds_val,
        "timeout_rate": timeout_rate,
        "avg_vp": avg_vp,
        "vp_std": vp_std,
        "avg_clashes_per_game": avg_clashes,
        "avg_clash_rate": avg_clash_rate,
        "total_wild_plays": total_wild_plays,
        "wild_activation_rate": wild_activation_rate,
        "faction_win_rates": faction_win_rates,
        "faction_play_counts": dict(faction_plays),
        "avg_talent_triggers": dict(avg_talents),
        "per_player": per_player_agg,
    }


# ─── Report Printer ─────────────────────────────────────────────

def print_report(agg: dict):
    """Print a formatted simulation report."""
    n = agg["num_games"]
    p = agg["num_players"]

    print(f"\n{'=' * 65}")
    print(f"  THE TUNNEL BRAWL v2.0 — SIMULATION REPORT")
    print(f"  {n} games · {p} players")
    print(f"{'=' * 65}")

    # Game Length
    print(f"\n--- Game Length ---")
    print(f"  Average: {agg['avg_rounds']:.1f} rounds")
    print(f"  Range:   {agg['min_rounds']}–{agg['max_rounds']} rounds")
    print(f"  Timeout rate: {agg['timeout_rate']:.1%}")

    # Win Rates
    print(f"\n--- Win Rates by Seat Position ---")
    for pid in range(p):
        pp = agg["per_player"][pid]
        bar = "█" * int(pp["win_rate"] * 50)
        print(f"  Player {pid}: {pp['win_rate']:6.1%}  {bar}")
    expected = 1.0 / p
    max_wr = max(agg["win_rates"].values())
    min_wr = min(agg["win_rates"].values())
    spread = max_wr - min_wr
    print(f"  Expected: {expected:.1%} | Spread: {spread:.1%}")
    if spread > 0.10:
        print(f"  ⚠ WARNING: Seat position spread > 10% — possible first-player advantage")

    # VP Distribution
    print(f"\n--- Victory Points ---")
    for pid in range(p):
        pp = agg["per_player"][pid]
        print(f"  Player {pid}: avg {pp['avg_vp']:.1f} VP (σ = {pp['vp_std']:.1f})")

    # CLASH! Stats
    print(f"\n--- CLASH! Mechanics ---")
    print(f"  Average CLASH!es per game: {agg['avg_clashes_per_game']:.1f}")
    print(f"  Rounds with at least one CLASH!: {agg['avg_clash_rate']:.1%}")

    # Wild Stats
    print(f"\n--- Wild Card (Sugar Rush) Mechanics ---")
    avg_wilds = agg["total_wild_plays"] / n
    print(f"  Average Wild plays per game: {avg_wilds:.1f}")
    print(f"  Wild activation rate: {agg['wild_activation_rate']:.1%}")
    total_wild_activations = int(agg["wild_activation_rate"] * agg["total_wild_plays"])
    print(f"  Total activations: {total_wild_activations} / {agg['total_wild_plays']} Wild plays")
    if agg["wild_activation_rate"] < 0.25:
        print(f"  ⚠ WARNING: Wild activation rate below 25% — cross-body rule may be too restrictive")
    elif agg["wild_activation_rate"] > 0.85:
        print(f"  ⚠ WARNING: Wild activation rate above 85% — cross-body rule may be too easy")

    # Faction Performance
    print(f"\n--- Faction Win Rates (when played) ---")
    factions = sorted(agg["faction_win_rates"].keys())
    for f in factions:
        wr = agg["faction_win_rates"][f]
        plays = agg["faction_play_counts"].get(f, 0)
        bar = "█" * int(wr * 40)
        print(f"  {f:8s}: {wr:5.1%} (played {plays:,} times)  {bar}")

    # Talent Triggers
    print(f"\n--- Faction Talent Triggers (avg per game) ---")
    talents = agg["avg_talent_triggers"]
    for f in sorted(talents.keys()):
        print(f"  {f:8s}: {talents[f]:.1f}")
    total_talents = sum(talents.values())
    print(f"  TOTAL:    {total_talents:.1f} per game")

    # Power Play / Domination Stats
    total_doms = sum(agg["per_player"][pid]["avg_dominations"] for pid in range(p))
    if total_doms > 0:
        print(f"\n--- Power Play / Domination Bonus ---")
        print(f"  Average bonus wins per game: {total_doms:.1f}")
        for pid in range(p):
            print(f"  Player {pid}: {agg['per_player'][pid]['avg_dominations']:.1f} per game")

    # Per-Player Combat Stats
    print(f"\n--- Per-Player Combat Averages ---")
    print(f"  {'':10s} {'Brawls Won':>10s} {'Brawls Lost':>11s} {'CLASH Won':>10s} {'Wilds Act':>10s} {'Wilds Trip':>10s} {'Talents':>8s} {'Domin':>6s}")
    for pid in range(p):
        pp = agg["per_player"][pid]
        print(f"  Player {pid}: {pp['avg_brawls_won']:10.1f} {pp['avg_brawls_lost']:11.1f} "
              f"{pp['avg_clashes_won']:10.1f} {pp['avg_wilds_activated']:10.1f} "
              f"{pp['avg_wilds_tripped']:10.1f} {pp['avg_talents_triggered']:8.1f} "
              f"{pp['avg_dominations']:6.1f}")

    # Health Summary
    print(f"\n--- Game Health Summary ---")
    issues = []
    if agg["timeout_rate"] > 0.05:
        issues.append(f"High timeout rate ({agg['timeout_rate']:.1%}) — games may drag")
    if spread > 0.10:
        issues.append(f"Seat position spread {spread:.1%} — possible balance issue")
    if agg["avg_rounds"] < 5:
        issues.append(f"Very short games ({agg['avg_rounds']:.1f} rounds) — might feel rushed")
    if agg["avg_rounds"] > 25:
        issues.append(f"Long games ({agg['avg_rounds']:.1f} rounds) — might drag")
    if agg["avg_clashes_per_game"] < 0.5:
        issues.append("Very few CLASH!es — tie mechanic rarely activates")
    if agg["wild_activation_rate"] < 0.25:
        issues.append("Low Wild activation — cross-body rule too restrictive?")

    if issues:
        for issue in issues:
            print(f"  ⚠ {issue}")
    else:
        print(f"  ✓ No major issues detected!")

    print(f"\n{'=' * 65}\n")


# ─── Player Config Builder ──────────────────────────────────────

def build_player_configs(args, num_players: int) -> List[dict]:
    """Build player configs from CLI args."""
    configs = [{"skill": 1.0, "style": "balanced", "aggression": 0.5}
               for _ in range(num_players)]

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
        style_list = list(STYLE_PROFILES.keys())
        configs = [{"skill": 1.0, "style": style_list[i % len(style_list)], "aggression": 0.5}
                   for i in range(num_players)]
    elif args.preset == "aggression":
        agg_levels = [0.2, 0.5, 0.8, 1.0, 0.0]
        configs = [{"skill": 1.0, "style": "balanced",
                    "aggression": agg_levels[i % len(agg_levels)]}
                   for i in range(num_players)]

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

    if args.aggression_levels:
        aggs = [float(a) for a in args.aggression_levels.split(",")]
        for i, a in enumerate(aggs):
            if i < len(configs):
                configs[i]["aggression"] = a

    return configs


# ─── CLI ─────────────────────────────────────────────────────────

def load_config(config_path: str = None) -> dict:
    """Load config from file, auto-detecting if not specified."""
    if config_path:
        with open(config_path, 'r') as f:
            return json.load(f)

    # Auto-detect
    script_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(script_dir, "config.json"),
        os.path.join(script_dir, "..", "config.json"),
    ]
    for c in candidates:
        if os.path.exists(c):
            with open(c, 'r') as f:
                return json.load(f)

    print("ERROR: config.json not found. Specify with --config.", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="The Tunnel Brawl v2.0 — Batch Simulation Runner"
    )
    parser.add_argument("-n", "--num-games", type=int, default=200,
                        help="Number of games to simulate (default: 200)")
    parser.add_argument("-p", "--players", type=int, default=4,
                        help="Number of players (2-5, default: 4)")
    parser.add_argument("-s", "--seed", type=int, default=1,
                        help="Starting random seed (default: 1)")
    parser.add_argument("--max-rounds", type=int, default=50,
                        help="Max rounds per game before timeout (default: 50)")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Print detailed game logs")
    parser.add_argument("--config", type=str, default=None,
                        help="Path to config.json")
    parser.add_argument("--json", type=str, default=None,
                        help="Export stats to JSON file")

    # Player configuration
    parser.add_argument("--skill", type=str, default=None,
                        help="Comma-separated skill levels: '1.0,0.5,0.3'")
    parser.add_argument("--styles", type=str, default=None,
                        help="Comma-separated play styles: 'aggressive,defensive,balanced'")
    parser.add_argument("--aggression-levels", type=str, default=None,
                        help="Comma-separated aggression levels: '0.2,0.5,0.8'")
    parser.add_argument("--preset", type=str, default=None,
                        choices=["experts", "beginners", "mixed", "styles", "aggression"],
                        help="Preset player configuration")

    # Rule overrides
    parser.add_argument("--victory-threshold", type=int, default=None,
                        help="Override victory point threshold")
    parser.add_argument("--clash-reward", type=int, default=None,
                        help="Override base CLASH! reward")
    parser.add_argument("--wild-surge-draw", type=int, default=None,
                        help="Override Wild Surge draw count")
    parser.add_argument("--draw-per-turn", type=int, default=None,
                        help="Override cards drawn per turn")
    parser.add_argument("--purple-vp-cost", type=int, default=None,
                        help="VP cost for Purple's return-card talent (default: 0)")
    parser.add_argument("--wild-strict", action="store_true",
                        help="Strict Wild mode: anchor must be rank 1-5")
    parser.add_argument("--purple-to-deck", action="store_true",
                        help="Purple returns cards to draw pile instead of hand")
    parser.add_argument("--domination-diff", type=int, default=None,
                        help="Rank difference for domination bonus (default: 0=off)")
    parser.add_argument("--domination-bonus", type=int, default=None,
                        help="VP bonus for domination win (default: 0)")
    parser.add_argument("--power-play-rank", type=int, default=None,
                        help="Min rank for Power Play bonus (default: 8)")
    parser.add_argument("--power-play-bonus", type=int, default=None,
                        help="VP bonus for Power Play win (default: 1)")

    args = parser.parse_args()

    # Validate
    if args.players < 2 or args.players > 5:
        print("ERROR: Player count must be 2-5.", file=sys.stderr)
        sys.exit(1)

    # Load config
    config = load_config(args.config)

    # Apply overrides
    pkey = f"{args.players}_player"
    if args.victory_threshold is not None:
        config["game_rules"]["victory_threshold"][pkey] = args.victory_threshold
    if args.clash_reward is not None:
        config["game_rules"]["clash_base_reward"] = args.clash_reward
    if args.wild_surge_draw is not None:
        config["game_rules"]["wild_surge_draw"] = args.wild_surge_draw
    if args.draw_per_turn is not None:
        config["game_rules"]["draw_per_turn"] = args.draw_per_turn
    if args.purple_vp_cost is not None:
        config["game_rules"]["purple_return_vp_cost"] = args.purple_vp_cost
    if args.wild_strict:
        config["game_rules"]["wild_strict_mode"] = True
    if args.purple_to_deck:
        config["game_rules"]["purple_return_to_deck"] = True
    if args.domination_diff is not None:
        config["game_rules"]["domination_rank_diff"] = args.domination_diff
    if args.domination_bonus is not None:
        config["game_rules"]["domination_bonus_vp"] = args.domination_bonus
    if args.power_play_rank is not None:
        config["game_rules"]["power_play_min_rank"] = args.power_play_rank
    if args.power_play_bonus is not None:
        config["game_rules"]["power_play_bonus_vp"] = args.power_play_bonus

    # Build player configs
    player_configs = build_player_configs(args, args.players)

    print(f"Running {args.num_games} games with {args.players} players (seed={args.seed})...",
          file=sys.stderr)
    if args.preset:
        print(f"Preset: {args.preset}", file=sys.stderr)
    for i, pc in enumerate(player_configs):
        print(f"  P{i}: skill={pc['skill']}, style={pc['style']}, aggression={pc['aggression']}",
              file=sys.stderr)

    # Run batch
    agg = run_batch(config, args.num_games, args.players,
                    start_seed=args.seed, max_rounds=args.max_rounds,
                    player_configs=player_configs, verbose=args.verbose)

    # Print report
    print_report(agg)

    # Export JSON
    if args.json:
        with open(args.json, 'w') as f:
            json.dump(agg, f, indent=2, default=str)
        print(f"Stats exported to {args.json}", file=sys.stderr)
