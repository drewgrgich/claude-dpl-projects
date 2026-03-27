#!/usr/bin/env python3
"""
Late-Round Condition Experience Analyzer

Answers: "How often do rounds 3 and 4 produce poor player experiences
because of the condition card drawn?"

Approach:
  1. Run thousands of natural games (random condition order each game)
  2. Track per-round, per-condition metrics:
     - stuck_rate: player had cards but played 0 (condition blocked them)
     - zero_vp_rate: player scored 0 VP this round
     - avg_cards_played: how many cards deployed
     - avg_hand_size: how many cards were available at round start
     - frustration_index: composite of stuck + zero + low-play
  3. Compare R1/R2 vs R3/R4 for each condition
  4. Identify specific condition × round combos that feel bad
  5. Check whether certain condition SEQUENCES compound the problem
"""

import json
import os
import statistics
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cards_v4 import COLORS, build_deck
from game_state_v4 import GameStateV4, Zone, ConditionCard
from ai_player_v4 import AIPlayerV4, STYLE_PROFILES

GAMES = 3000
PLAYER_COUNTS = [2, 3, 4, 5]


def run_analysis(num_players, num_games=GAMES):
    """Run natural games tracking per-round, per-condition metrics."""

    config_path = os.path.join(os.path.dirname(__file__), "config_v4.json")
    with open(config_path) as f:
        config = json.load(f)

    num_rounds = config["game_rules"]["num_rounds"]
    styles = list(STYLE_PROFILES.keys())

    # Per (round, condition_effect) metrics
    # Key: (round_num, condition_effect_or_None)
    round_cond_data = defaultdict(lambda: {
        "stuck": 0,
        "zero_vp": 0,
        "cards_played": [],
        "hand_sizes": [],
        "vp_earned": [],
        "player_rounds": 0,
        "low_play": 0,  # played <= 1 card despite having 3+
    })

    # Track condition sequences: what conditions appeared in R1-R2 before this R3/R4
    sequence_data = defaultdict(lambda: {
        "stuck": 0, "zero_vp": 0, "player_rounds": 0,
        "cards_played": [], "vp_earned": [],
    })

    # Per-round aggregate (regardless of condition)
    round_agg = defaultdict(lambda: {
        "stuck": 0, "zero_vp": 0, "cards_played": [],
        "hand_sizes": [], "vp_earned": [], "player_rounds": 0,
    })

    for game_idx in range(num_games):
        seed = game_idx + 1
        game = GameStateV4(num_players, seed=seed, config=config)

        ais = [AIPlayerV4(pid, skill=1.0,
                           style=styles[pid % len(styles)],
                           rng_seed=seed * 100 + pid)
               for pid in range(num_players)]

        # Card passing
        pass_selections = {}
        for player in game.players:
            ai = ais[player.id]
            to_pass = ai.choose_pass(player, game,
                                      game.rules["pass_count"][game.pkey])
            pass_selections[player.id] = to_pass

        def pass_fn(player, gs, count):
            return pass_selections[player.id]
        game.execute_pass(pass_fn)

        # Track conditions drawn each round for sequence analysis
        conditions_this_game = []

        for round_num in range(num_rounds):
            game.current_round = round_num
            for p in game.players:
                p.zones_won_this_round = 0

            # Draw condition naturally
            if game.condition_deck:
                game.active_condition = game.condition_deck.pop(0)
                game.stats["condition_cards_drawn"].append(game.active_condition.name)
            else:
                game.active_condition = None

            cond_effect = game.active_condition.effect if game.active_condition else None
            cond_name = game.active_condition.name if game.active_condition else "None"
            conditions_this_game.append(cond_effect)

            game.zones = [Zone(color=c, index=i)
                          for i, c in enumerate(COLORS)]

            scores_before = {p.id: p.score for p in game.players}

            for player in game.players:
                ai = ais[player.id]
                hand_size = len(player.hand)

                deploy = ai.choose_deployment(player, game, round_num)
                all_cards = [c for cards in deploy.values() for c in cards]
                num_played = len(all_cards)

                is_stuck = (num_played == 0 and hand_size > 0)
                is_low_play = (num_played <= 1 and hand_size >= 3)

                # Record per (round, condition)
                key = (round_num, cond_effect)
                d = round_cond_data[key]
                d["player_rounds"] += 1
                d["hand_sizes"].append(hand_size)
                d["cards_played"].append(num_played)
                if is_stuck:
                    d["stuck"] += 1
                if is_low_play:
                    d["low_play"] += 1

                # Record per round aggregate
                ra = round_agg[round_num]
                ra["player_rounds"] += 1
                ra["hand_sizes"].append(hand_size)
                ra["cards_played"].append(num_played)
                if is_stuck:
                    ra["stuck"] += 1

                game._execute_deployment(player, deploy)

            game._resolve_actions()
            zone_strengths = game._calculate_all_strength()
            game._score_round(zone_strengths)

            # Record VP outcomes
            for player in game.players:
                vp_gained = player.score - scores_before[player.id]
                key = (round_num, cond_effect)
                round_cond_data[key]["vp_earned"].append(vp_gained)
                if vp_gained == 0:
                    round_cond_data[key]["zero_vp"] += 1

                round_agg[round_num]["vp_earned"].append(vp_gained)
                if vp_gained == 0:
                    round_agg[round_num]["zero_vp"] += 1

            # Sequence tracking for R3 and R4
            if round_num >= 2:
                prev_conditions = tuple(conditions_this_game[:round_num])
                seq_key = (round_num, cond_effect, prev_conditions)
                for player in game.players:
                    vp_gained = player.score - scores_before[player.id]
                    sd = sequence_data[seq_key]
                    sd["player_rounds"] += 1
                    sd["vp_earned"].append(vp_gained)
                    if vp_gained == 0:
                        sd["zero_vp"] += 1

            game.active_condition = None

    return round_cond_data, round_agg, sequence_data, num_rounds


def compute_metrics(data):
    """Compute summary metrics from a data bucket."""
    pr = data["player_rounds"]
    if pr == 0:
        return None
    return {
        "stuck_rate": data["stuck"] / pr,
        "zero_vp_rate": data["zero_vp"] / pr,
        "avg_cards": statistics.mean(data["cards_played"]) if data["cards_played"] else 0,
        "avg_hand": statistics.mean(data["hand_sizes"]) if data["hand_sizes"] else 0,
        "avg_vp": statistics.mean(data["vp_earned"]) if data["vp_earned"] else 0,
        "low_play_rate": data.get("low_play", 0) / pr,
        "n": pr,
    }


# Condition effect -> friendly name
COND_NAMES = {
    None: "No Condition",
    "no_mascots": "Naturals Only",
    "unique_colors_per_zone": "Rainbow",
    "max_cards_4": "Light Touch",
    "max_2_zones": "All In",
    "min_2_zones": "Spread Out",
    "lowest_wins": "Inversion",
    "double_vp": "Double Stakes",
    "no_home_field": "Neutral Ground",
    "ties_lose": "Sudden Death",
    "fewer_cards_wins_ties": "Efficiency",
    "lone_wolf_bonus": "Lone Wolf",
    "big_stack_bonus": "Fortify",
}

# Restrictive conditions (ones that limit what you can play)
RESTRICTIVE = {"no_mascots", "unique_colors_per_zone", "max_cards_4", "max_2_zones", "min_2_zones"}


def print_report(np, round_cond_data, round_agg, sequence_data, num_rounds):
    """Print analysis for one player count."""
    print(f"\n{'='*90}")
    print(f"  LATE-ROUND CONDITION EXPERIENCE — {np} PLAYERS — {GAMES} games")
    print(f"{'='*90}")

    # ── SECTION 1: Round-by-round baseline ──
    print(f"\n── ROUND-BY-ROUND BASELINE (all conditions pooled) ──")
    print(f"  {'Round':<8} {'Hand':>6} {'Cards':>6} {'Stuck%':>7} {'Zero%':>7} {'VP':>6}")
    print(f"  {'-'*42}")
    for rn in range(num_rounds):
        m = compute_metrics(round_agg[rn])
        if m:
            print(f"  R{rn+1:<6} {m['avg_hand']:>6.1f} {m['avg_cards']:>6.1f} "
                  f"{m['stuck_rate']:>7.1%} {m['zero_vp_rate']:>7.1%} {m['avg_vp']:>6.1f}")

    # ── SECTION 2: Each condition by round ──
    print(f"\n── CONDITION × ROUND MATRIX ──")
    print(f"  Shows: stuck% / zero_vp% / avg_cards")
    print()

    # Collect all conditions that appeared
    all_conds = sorted(set(ce for (_, ce) in round_cond_data.keys()),
                       key=lambda x: (x is not None, str(x)))

    header = f"  {'Condition':<22}"
    for rn in range(num_rounds):
        header += f" {'R'+str(rn+1):>18}"
    header += f"  {'R3-R4 Δ':>10}"
    print(header)
    print(f"  {'-'*(22 + 19*num_rounds + 12)}")

    flagged_combos = []

    for ce in all_conds:
        name = COND_NAMES.get(ce, str(ce))
        line = f"  {name:<22}"
        round_metrics = []
        for rn in range(num_rounds):
            key = (rn, ce)
            m = compute_metrics(round_cond_data.get(key, {
                "stuck": 0, "zero_vp": 0, "cards_played": [], "hand_sizes": [],
                "vp_earned": [], "player_rounds": 0, "low_play": 0
            }))
            round_metrics.append(m)
            if m and m["n"] > 10:
                cell = f"{m['stuck_rate']:.0%}/{m['zero_vp_rate']:.0%}/{m['avg_cards']:.1f}"
                line += f" {cell:>18}"
            else:
                line += f" {'(few samples)':>18}"

        # Compute R3-R4 vs R1-R2 deterioration
        early = [round_metrics[i] for i in range(min(2, num_rounds)) if round_metrics[i]]
        late = [round_metrics[i] for i in range(2, num_rounds) if round_metrics[i]]

        delta_str = ""
        if early and late:
            early_zero = statistics.mean([m["zero_vp_rate"] for m in early])
            late_zero = statistics.mean([m["zero_vp_rate"] for m in late])
            delta = late_zero - early_zero
            delta_str = f"{delta:>+.0%}"

            # Flag concerning combos
            for rn in range(2, num_rounds):
                m = round_metrics[rn]
                if m and m["n"] > 10:
                    if m["stuck_rate"] > 0.10:
                        flagged_combos.append((name, rn, "STUCK", m["stuck_rate"]))
                    if m["zero_vp_rate"] > 0.55:
                        flagged_combos.append((name, rn, "HIGH_ZERO", m["zero_vp_rate"]))
                    if m["avg_cards"] < 1.5 and ce in RESTRICTIVE:
                        flagged_combos.append((name, rn, "LOW_PLAY", m["avg_cards"]))

        line += f"  {delta_str:>10}"
        print(line)

    # ── SECTION 3: Frustration Index ──
    print(f"\n── FRUSTRATION INDEX (R3+R4 only, restrictive conditions) ──")
    print(f"  Frustration = stuck_rate + zero_vp_rate + low_play_rate (lower = better)")
    print()
    print(f"  {'Condition':<22} {'Stuck%':>7} {'Zero%':>7} {'LowPlay%':>9} {'Frust':>7} {'Verdict':>10}")
    print(f"  {'-'*64}")

    for ce in all_conds:
        if ce not in RESTRICTIVE and ce is not None:
            continue
        name = COND_NAMES.get(ce, str(ce))

        # Pool R3+R4 data
        pooled = {"stuck": 0, "zero_vp": 0, "cards_played": [], "hand_sizes": [],
                  "vp_earned": [], "player_rounds": 0, "low_play": 0}
        for rn in range(2, num_rounds):
            key = (rn, ce)
            d = round_cond_data.get(key)
            if d:
                pooled["stuck"] += d["stuck"]
                pooled["zero_vp"] += d["zero_vp"]
                pooled["cards_played"].extend(d["cards_played"])
                pooled["hand_sizes"].extend(d["hand_sizes"])
                pooled["vp_earned"].extend(d["vp_earned"])
                pooled["player_rounds"] += d["player_rounds"]
                pooled["low_play"] += d.get("low_play", 0)

        m = compute_metrics(pooled)
        if not m or m["n"] < 20:
            continue

        frust = m["stuck_rate"] + m["zero_vp_rate"] + m["low_play_rate"]
        if frust > 0.80:
            verdict = "CONCERN"
        elif frust > 0.60:
            verdict = "WATCH"
        else:
            verdict = "OK"

        marker = "⚠️ " if verdict != "OK" else "✅"
        print(f"  {marker}{name:<20} {m['stuck_rate']:>7.1%} {m['zero_vp_rate']:>7.1%} "
              f"{m['low_play_rate']:>9.1%} {frust:>7.2f} {verdict:>10}")

    # ── SECTION 4: Scoring conditions that feel bad late ──
    print(f"\n── SCORING CONDITIONS IN LATE ROUNDS ──")
    print(f"  {'Condition':<22} {'R1-R2 VP':>9} {'R3-R4 VP':>9} {'Δ':>6} {'R3-R4 Zero%':>12}")
    print(f"  {'-'*60}")

    for ce in all_conds:
        if ce in RESTRICTIVE:
            continue
        name = COND_NAMES.get(ce, str(ce))

        early_vp = []
        late_vp = []
        late_zero = 0
        late_pr = 0

        for rn in range(num_rounds):
            key = (rn, ce)
            d = round_cond_data.get(key)
            if d and d["player_rounds"] > 0:
                if rn < 2:
                    early_vp.extend(d["vp_earned"])
                else:
                    late_vp.extend(d["vp_earned"])
                    late_zero += d["zero_vp"]
                    late_pr += d["player_rounds"]

        if not early_vp or not late_vp or late_pr < 20:
            continue

        e_avg = statistics.mean(early_vp)
        l_avg = statistics.mean(late_vp)
        delta = l_avg - e_avg
        lz_rate = late_zero / late_pr

        flag = " ⚠️" if lz_rate > 0.50 else ""
        print(f"  {name:<22} {e_avg:>9.1f} {l_avg:>9.1f} {delta:>+6.1f} {lz_rate:>12.1%}{flag}")

    # ── SECTION 5: Flagged combos ──
    if flagged_combos:
        print(f"\n── FLAGGED CONDITION × ROUND COMBOS ──")
        for name, rn, issue, val in sorted(flagged_combos, key=lambda x: -x[3]):
            print(f"  ⚠️  {name} at R{rn+1}: {issue} ({val:.1%})")

    # ── SECTION 6: Hand depletion context ──
    print(f"\n── HAND DEPLETION CONTEXT ──")
    print(f"  {'Round':<8} {'Avg Hand':>9} {'Min Hand (p5)':>14} {'Max Hand (p95)':>15}")
    print(f"  {'-'*48}")
    for rn in range(num_rounds):
        d = round_agg[rn]
        if d["hand_sizes"]:
            hs = sorted(d["hand_sizes"])
            avg = statistics.mean(hs)
            p5 = hs[len(hs)//20]
            p95 = hs[19*len(hs)//20]
            print(f"  R{rn+1:<6} {avg:>9.1f} {p5:>14} {p95:>15}")

    # ── SECTION 7: Worst sequence pairs ──
    print(f"\n── CONDITION SEQUENCE EFFECTS (does prior round condition make R3/R4 worse?) ──")
    print(f"  Comparing: same R3/R4 condition, different R1-R2 history")

    # Group by (round, current_condition), compare across prior sequences
    from itertools import groupby

    for target_round in [2, 3]:  # R3 and R4
        print(f"\n  --- Round {target_round + 1} ---")

        # Group sequences by current condition
        by_current = defaultdict(list)
        for (rn, ce, prev), sd in sequence_data.items():
            if rn == target_round and sd["player_rounds"] >= 10:
                by_current[ce].append((prev, sd))

        for ce in sorted(by_current.keys(), key=lambda x: str(x)):
            name = COND_NAMES.get(ce, str(ce))
            entries = by_current[ce]
            if len(entries) < 2:
                continue

            # Find best and worst prior sequences
            scored = []
            for prev, sd in entries:
                zr = sd["zero_vp"] / sd["player_rounds"]
                avg_vp = statistics.mean(sd["vp_earned"]) if sd["vp_earned"] else 0
                scored.append((prev, zr, avg_vp, sd["player_rounds"]))

            scored.sort(key=lambda x: x[1])  # sort by zero rate
            best = scored[0]
            worst = scored[-1]

            if worst[1] - best[1] > 0.10:  # meaningful difference
                prev_best = " → ".join(COND_NAMES.get(c, "?")[:8] for c in best[0])
                prev_worst = " → ".join(COND_NAMES.get(c, "?")[:8] for c in worst[0])
                print(f"    {name:<20} zero_vp range: {best[1]:.0%}–{worst[1]:.0%}")
                print(f"      Best after:  [{prev_best}] (n={best[3]})")
                print(f"      Worst after: [{prev_worst}] (n={worst[3]})")


def main():
    print("Late-Round Condition Experience Analyzer")
    print(f"Running {GAMES} games per player count...\n")

    for np in PLAYER_COUNTS:
        print(f"Simulating {np}P...", end="", flush=True)
        round_cond_data, round_agg, sequence_data, num_rounds = run_analysis(np, GAMES)
        print(" done.")
        print_report(np, round_cond_data, round_agg, sequence_data, num_rounds)

    # ── FINAL VERDICT ──
    print(f"\n{'='*90}")
    print("  OVERALL ASSESSMENT")
    print(f"{'='*90}")
    print("""
  Key questions answered:

  1. HAND DEPLETION: Do players have enough cards in R3/R4?
     → Check "Hand Depletion Context" section for each player count.

  2. RESTRICTIVE CONDITIONS IN LATE ROUNDS: Do they create stuck/frustrated players?
     → Check "Frustration Index" — any CONCERN flags need design attention.

  3. SCORING CONDITIONS IN LATE ROUNDS: Do they feel different late vs early?
     → Check "Scoring Conditions" — large VP drops or high zero rates are flags.

  4. COMPOUNDING SEQUENCES: Do bad R1-R2 conditions make R3-R4 worse?
     → Check "Sequence Effects" — large zero_vp ranges suggest interaction effects.
""")


if __name__ == "__main__":
    main()
