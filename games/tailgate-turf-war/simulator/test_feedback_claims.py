#!/usr/bin/env python3
"""
Test the 5 playtester feedback claims with simulation data.

1. Swap is too situational (fires near-zero)
2. Reveal phase cognitive load (not directly testable — measure complexity proxy)
3. 5P spectator problem (zero-card rounds)
4. Tie-breaker VP inflation from rounding up
5. Spread style is a trap

Run: python test_feedback_claims.py
"""

import json
import math
import os
import statistics
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cards_v4 import COLORS, ACTION_SWAP, ACTION_BOUNTY, ACTION_SHIELD, ACTION_BOMB
from game_state_v4 import GameStateV4, Zone
from ai_player_v4 import AIPlayerV4, STYLE_PROFILES

GAMES = 2000


def run_games(num_players, num_games=GAMES):
    """Run games and collect data for all 5 claims."""
    config_path = os.path.join(os.path.dirname(__file__), "config_v4.json")
    with open(config_path) as f:
        config = json.load(f)

    styles = list(STYLE_PROFILES.keys())
    data = {
        # Claim 1: Swap
        "swap_in_hand": 0,
        "swap_played": 0,
        "swap_beneficial": 0,
        "swap_no_effect": 0,

        # Claim 3: 5P spectator
        "zero_card_rounds": 0,
        "one_card_rounds": 0,
        "total_player_rounds": 0,
        "cards_per_player_round": [],
        "zero_card_by_round": defaultdict(int),
        "player_rounds_by_round": defaultdict(int),

        # Claim 4: Tie VP inflation
        "tie_events": 0,
        "tie_vp_awarded": 0,
        "tie_vp_fair": 0,  # what would be awarded with floor
        "total_zones_scored": 0,
        "total_vp_awarded": 0,

        # Claim 5: Spread viability
        "style_wins": defaultdict(int),
        "style_games": defaultdict(int),
        "style_vp": defaultdict(list),
        "style_zones_won": defaultdict(list),

        # Claim 2: Complexity proxy
        "stacks_per_reveal": [],
        "unique_strengths_per_reveal": [],
        "actions_per_round": [],
    }

    for seed in range(1, num_games + 1):
        game = GameStateV4(num_players, seed=seed, config=config)
        ais = [AIPlayerV4(pid, skill=1.0,
                           style=styles[pid % len(styles)],
                           rng_seed=seed * 100 + pid)
               for pid in range(num_players)]

        # Track styles assigned
        for pid in range(num_players):
            data["style_games"][styles[pid % len(styles)]] += 1

        # Check who has swap in hand
        for p in game.players:
            if any(c.is_action and c.action_type == ACTION_SWAP for c in p.hand):
                data["swap_in_hand"] += 1

        # Card passing
        pass_sel = {}
        for p in game.players:
            pass_sel[p.id] = ais[p.id].choose_pass(p, game,
                                                     game.rules["pass_count"][game.pkey])
        game.execute_pass(lambda p, gs, c: pass_sel[p.id])

        for rn in range(game.num_rounds):
            game.current_round = rn
            for p in game.players:
                p.zones_won_this_round = 0

            if game.condition_deck:
                game.active_condition = game.condition_deck.pop(0)
            else:
                game.active_condition = None

            game.zones = [Zone(color=c, index=i) for i, c in enumerate(COLORS)]
            scores_before = {p.id: p.score for p in game.players}

            round_action_count = 0

            for p in game.players:
                deploy = ais[p.id].choose_deployment(p, game, rn)
                all_cards = [c for cards in deploy.values() for c in cards]
                num_cards = len(all_cards)

                data["total_player_rounds"] += 1
                data["cards_per_player_round"].append(num_cards)
                data["player_rounds_by_round"][rn] += 1

                if num_cards == 0:
                    data["zero_card_rounds"] += 1
                    data["zero_card_by_round"][rn] += 1
                elif num_cards == 1:
                    data["one_card_rounds"] += 1

                # Track swap plays
                for zone_color, cards in deploy.items():
                    for c in cards:
                        if c.is_action and c.action_type == ACTION_SWAP:
                            data["swap_played"] += 1
                        if c.is_action:
                            round_action_count += 1

                game._execute_deployment(p, deploy)

            data["actions_per_round"].append(round_action_count)

            # Complexity proxy: count stacks on the board
            stacks = 0
            for zone in game.zones:
                stacks += len(zone.active_players)
            data["stacks_per_reveal"].append(stacks)

            # Resolve actions and track swap outcomes
            log_before = len(game.log)
            game._resolve_actions()
            action_log = game.log[log_before:]
            for msg in action_log:
                if "Swap" in msg and "no beneficial" in msg:
                    data["swap_no_effect"] += 1
                elif "Swap" in msg and ("swaps" in msg.lower() or "swap —" in msg.lower()):
                    if "no beneficial" not in msg:
                        data["swap_beneficial"] += 1

            # Score round
            zone_strengths = game._calculate_all_strength()

            # Track ties BEFORE scoring
            cond = game.active_condition
            vp = game.base_vp
            if cond and cond.effect == "double_vp":
                vp *= 2

            for zone in game.zones:
                sm = zone_strengths.get(zone.color, {})
                if not sm:
                    continue

                data["total_zones_scored"] += 1

                inversion = cond and cond.effect == "lowest_wins"
                target = min(sm.values()) if inversion else max(sm.values())
                if target <= 0:
                    continue

                winners = [pid for pid, s in sm.items() if s == target]

                if len(winners) > 1:
                    # It's a tie
                    if cond and cond.effect == "ties_lose":
                        continue  # sudden death, no VP
                    if cond and cond.effect == "fewer_cards_wins_ties":
                        min_cards = min(len(zone.get_placement(w).cards) for w in winners)
                        winners = [w for w in winners if len(zone.get_placement(w).cards) == min_cards]

                    if len(winners) > 1:
                        data["tie_events"] += 1
                        ceil_vp = math.ceil(vp / len(winners))
                        floor_vp = math.floor(vp / len(winners))
                        data["tie_vp_awarded"] += ceil_vp * len(winners)
                        data["tie_vp_fair"] += floor_vp * len(winners)

                data["total_vp_awarded"] += vp  # base VP at stake

            game._score_round(zone_strengths)
            game.active_condition = None

        # Final results
        final = game._compile_final_stats()
        scores = final["scores"]
        max_score = max(scores.values())
        winner_ids = [pid for pid, s in scores.items() if s == max_score]

        for pid in range(num_players):
            style = styles[pid % len(styles)]
            data["style_vp"][style].append(scores[pid])
            data["style_zones_won"][style].append(final["zones_won"][pid])
            if pid in winner_ids:
                data["style_wins"][style] += 1

    return data


def print_report(np, data):
    styles = list(STYLE_PROFILES.keys())

    print(f"\n{'='*80}")
    print(f"  FEEDBACK CLAIMS TEST — {np} PLAYERS — {GAMES} games")
    print(f"{'='*80}")

    # ── CLAIM 1: Swap ──
    print(f"\n── CLAIM 1: Swap is too situational ──")
    print(f"  Players dealt Swap:    {data['swap_in_hand']}")
    print(f"  Swap cards played:     {data['swap_played']}")
    print(f"  Beneficial swaps:      {data['swap_beneficial']}")
    print(f"  No-effect swaps:       {data['swap_no_effect']}")
    if data['swap_played'] > 0:
        success = data['swap_beneficial'] / data['swap_played']
        print(f"  Success rate:          {success:.0%}")
    if data['swap_in_hand'] > 0:
        play_rate = data['swap_played'] / data['swap_in_hand']
        print(f"  Play rate (of held):   {play_rate:.0%}")
    verdict = "CONFIRMED" if data['swap_beneficial'] < data['swap_played'] * 0.15 else "MIXED"
    print(f"  Verdict: {verdict}")

    # ── CLAIM 2: Cognitive load ──
    print(f"\n── CLAIM 2: Reveal phase complexity ──")
    avg_stacks = statistics.mean(data["stacks_per_reveal"])
    max_stacks = max(data["stacks_per_reveal"])
    avg_actions = statistics.mean(data["actions_per_round"])
    print(f"  Avg stacks to evaluate:  {avg_stacks:.1f} per reveal")
    print(f"  Max stacks in a reveal:  {max_stacks}")
    print(f"  Avg action cards/round:  {avg_actions:.1f}")
    # Each stack needs: best card + extras*2 + home field check = ~3 mental ops
    mental_ops = avg_stacks * 3 + avg_actions * 2
    print(f"  Est. mental operations:  {mental_ops:.0f} per reveal")
    if mental_ops > 30:
        print(f"  Verdict: CONFIRMED — {mental_ops:.0f} ops is a lot for a party game")
    else:
        print(f"  Verdict: MANAGEABLE — zone-by-zone resolution should help")

    # ── CLAIM 3: 5P spectator ──
    print(f"\n── CLAIM 3: Zero-card 'spectator' rounds ──")
    total = data["total_player_rounds"]
    zc = data["zero_card_rounds"]
    oc = data["one_card_rounds"]
    print(f"  Total player-rounds:   {total}")
    print(f"  Zero-card rounds:      {zc} ({zc/total:.1%})")
    print(f"  One-card rounds:       {oc} ({oc/total:.1%})")
    print(f"  Avg cards/player/round: {statistics.mean(data['cards_per_player_round']):.1f}")

    print(f"\n  By round:")
    for rn in sorted(data["player_rounds_by_round"].keys()):
        pr = data["player_rounds_by_round"][rn]
        zr = data["zero_card_by_round"][rn]
        print(f"    R{rn+1}: {zr}/{pr} zero-card ({zr/pr:.1%})")

    if zc / total > 0.05:
        print(f"  Verdict: CONFIRMED — {zc/total:.0%} of player-rounds are spectator turns")
    else:
        print(f"  Verdict: NOT AN ISSUE — only {zc/total:.1%} spectator turns")

    # ── CLAIM 4: Tie VP inflation ──
    print(f"\n── CLAIM 4: Tie VP inflation from ceil() ──")
    print(f"  Total zones scored:    {data['total_zones_scored']}")
    print(f"  Tie events:            {data['tie_events']} ({data['tie_events']/max(1,data['total_zones_scored']):.1%} of zones)")
    print(f"  VP with ceil (current): {data['tie_vp_awarded']}")
    print(f"  VP with floor (alt):    {data['tie_vp_fair']}")
    inflation = data['tie_vp_awarded'] - data['tie_vp_fair']
    games_inflation = inflation / GAMES
    per_zone = inflation / max(1, data['tie_events'])
    print(f"  Total inflation:       {inflation} VP across {GAMES} games")
    print(f"  Per game:              {games_inflation:.1f} VP")
    print(f"  Per tie event:         {per_zone:.1f} VP")
    if games_inflation > 2:
        print(f"  Verdict: WORTH FIXING — {games_inflation:.1f} VP/game distorts scoring")
    elif games_inflation > 0.5:
        print(f"  Verdict: MINOR — {games_inflation:.1f} VP/game, noticeable but not breaking")
    else:
        print(f"  Verdict: NEGLIGIBLE")

    # ── CLAIM 5: Spread is a trap ──
    print(f"\n── CLAIM 5: Spread style is a trap ──")
    print(f"  {'Style':<12} {'Games':>6} {'Wins':>6} {'Win%':>6} {'Avg VP':>7} {'Avg Zones':>10}")
    print(f"  {'-'*48}")

    for s in styles:
        games = data["style_games"].get(s, 0)
        wins = data["style_wins"].get(s, 0)
        vp_list = data["style_vp"].get(s, [])
        zones_list = data["style_zones_won"].get(s, [])
        if not vp_list:
            continue
        wr = wins / max(1, games)
        avg_vp = statistics.mean(vp_list)
        avg_zones = statistics.mean(zones_list)
        marker = " ⚠️" if s == "spread" else ""
        print(f"  {s:<12} {games:>6} {wins:>6} {wr:>6.0%} {avg_vp:>7.1f} {avg_zones:>10.1f}{marker}")

    # Check if spread is significantly worse
    spread_vp = data["style_vp"].get("spread", [])
    best_style = max(styles, key=lambda s: statistics.mean(data["style_vp"].get(s, [0])))
    best_vp = data["style_vp"].get(best_style, [])
    if spread_vp and best_vp:
        gap = statistics.mean(best_vp) - statistics.mean(spread_vp)
        print(f"\n  VP gap (best vs spread): {gap:.1f}")
        if gap > 5:
            print(f"  Verdict: CONFIRMED — spread trails by {gap:.1f} VP, needs help or a warning")
        elif gap > 2:
            print(f"  Verdict: SOFT CONFIRM — {gap:.1f} VP gap is noticeable but not crippling")
        else:
            print(f"  Verdict: NOT AN ISSUE — spread is competitive")


def main():
    print("Testing 5 Feedback Claims")
    print(f"Running {GAMES} games per player count...\n")

    for np in [2, 3, 4, 5]:
        print(f"Simulating {np}P...", end="", flush=True)
        data = run_games(np, GAMES)
        print(" done.")
        print_report(np, data)

    print(f"\n{'='*80}")
    print("  SUMMARY")
    print(f"{'='*80}")
    print("""
  Claim 1 (Swap):       Check success rate — if < 15%, consider expanding targeting
  Claim 2 (Complexity): Check mental ops — zone-by-zone resolution recommended
  Claim 3 (Spectator):  Check 5P zero-card rate — if > 5%, consider 3-round 5P variant
  Claim 4 (Inflation):  Check VP/game inflation — switch to floor() if > 2 VP/game
  Claim 5 (Spread):     Check VP gap — if > 5 VP, add strategy tips or rebalance
""")


if __name__ == "__main__":
    main()
