#!/usr/bin/env python3
"""
Deep analysis for designer questions — v0.1.4.

Morgan's questions:
  M1. Action card activation rates
  M2. Mascot impact on win rate
  M3. Home Field frequency in winning plays
  M4. VP distribution by round

Jordan's question:
  J1. Close games vs blowouts, final-round winner changes

Casey's question:
  C1. Condition card impact on VP spreads / blowouts
"""

import json
import math
import os
import statistics
import sys
from collections import defaultdict
from typing import List, Dict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cards_v4 import (
    Card, COLORS,
    CARD_TYPE_NUMBER, CARD_TYPE_MASCOT, CARD_TYPE_ACTION, CARD_TYPE_DUD,
    ACTION_SHIELD, ACTION_BOMB, ACTION_SWAP, ACTION_BOUNTY,
)
from game_state_v4 import GameStateV4, Zone
from ai_player_v4 import AIPlayerV4, STYLE_PROFILES


# ─── INSTRUMENTED GAME ─────────────────────────────────────────────────────

class InstrumentedGame(GameStateV4):
    """Extended game state that tracks per-round VP and per-zone details."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.round_vp = defaultdict(lambda: defaultdict(int))  # round -> pid -> vp
        self.round_winners = {}  # round -> {zone_color: [winner_pids]}
        self.zone_details = []  # list of per-zone-per-round dicts
        self.mascot_holders = set()  # pids who were dealt a mascot
        self.mascot_zone_wins = 0  # zones won where mascot was in the stack
        self.total_zone_wins = 0
        self.hf_in_winning_plays = 0
        self.no_hf_in_winning_plays = 0
        self._pre_round_scores = {}

        # Track who holds mascots at game start
        for p in self.players:
            for c in p.hand:
                if c.is_mascot:
                    self.mascot_holders.add(p.id)

    def _play_round(self, round_num, deployment_fn):
        # Snapshot scores before round
        self._pre_round_scores = {p.id: p.score for p in self.players}
        result = super()._play_round(round_num, deployment_fn)

        # Compute per-round VP
        for p in self.players:
            gained = p.score - self._pre_round_scores[p.id]
            self.round_vp[round_num][p.id] = gained

        return result

    def _score_round(self, zone_strengths):
        """Override to capture zone-level winning details."""
        # Before scoring, snapshot zone compositions for analysis
        cond = self.active_condition

        for zone in self.zones:
            strength_map = zone_strengths.get(zone.color, {})
            if not strength_map:
                continue

            # Determine winner(s)
            inversion = cond and cond.effect == "lowest_wins"
            target = min(strength_map.values()) if inversion else max(strength_map.values())
            if target <= 0:
                continue

            winners = [pid for pid, s in strength_map.items() if s == target]

            # Check tie handling
            if len(winners) > 1:
                if cond and cond.effect == "ties_lose":
                    continue
                if cond and cond.effect == "fewer_cards_wins_ties":
                    min_cards = min(len(zone.get_placement(w).cards) for w in winners)
                    winners = [w for w in winners
                               if len(zone.get_placement(w).cards) == min_cards]

            for w in winners:
                self.total_zone_wins += 1
                zp = zone.get_placement(w)

                # Mascot in winning stack?
                has_mascot = any(c.is_mascot for c in zp.cards)
                if has_mascot:
                    self.mascot_zone_wins += 1

                # Home field in winning stack?
                no_hf = cond and cond.effect == "no_home_field"
                if not no_hf:
                    has_hf = any(c.color == zone.color and c.is_natural for c in zp.cards)
                    if has_hf:
                        self.hf_in_winning_plays += 1
                    else:
                        self.no_hf_in_winning_plays += 1
                else:
                    self.no_hf_in_winning_plays += 1

        return super()._score_round(zone_strengths)


# ─── RUN GAMES ─────────────────────────────────────────────────────────────

def load_config():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config_v4.json")
    with open(path) as f:
        return json.load(f)


def run_analysis(num_games, num_players, styles, config):
    """Run instrumented games and collect detailed metrics."""

    # Accumulators
    action_games_played = defaultdict(int)  # action_type -> games where it was played
    action_activations = defaultdict(int)    # action_type -> times it actually fired
    total_action_plays = defaultdict(int)

    mascot_holder_wins = 0
    mascot_holder_games = 0
    non_mascot_holder_wins = 0
    non_mascot_holder_games = 0

    hf_in_wins = 0
    no_hf_in_wins = 0
    mascot_zone_wins = 0
    total_zone_wins = 0

    round_vp_totals = defaultdict(lambda: defaultdict(list))  # round -> pid_style -> [vp]
    round_vp_all = defaultdict(list)  # round -> [total_vp_awarded]

    score_gaps = []
    final_round_flips = 0
    total_games = 0

    condition_spreads = defaultdict(list)  # condition_name -> [score_spread]
    condition_games = defaultdict(int)

    # Per-game accumulators for action tracking
    for i in range(num_games):
        seed = 1 + i
        game_styles = [styles[(i + j) % len(styles)] for j in range(num_players)]

        game = InstrumentedGame(num_players, seed=seed, config=config)
        ais = [AIPlayerV4(pid, skill=1.0, style=game_styles[pid],
                           rng_seed=seed * 100 + pid) for pid in range(num_players)]

        def dfn(p, gs, rn):
            return ais[p.id].choose_deployment(p, gs, rn)

        def pfn(p, gs, pc):
            return ais[p.id].choose_pass(p, gs, pc)

        result = game.play_game(dfn, pfn)
        total_games += 1

        # ── ACTION CARDS (M1) ──
        for action_type, count in result.get("action_plays", {}).items():
            total_action_plays[action_type] += count
            if count > 0:
                action_games_played[action_type] += 1

        # Shield saves = games where shield prevented bomb damage
        if result.get("shield_saves", 0) > 0:
            action_activations[ACTION_SHIELD] += result["shield_saves"]
        if result.get("bomb_kills", 0) > 0:
            action_activations[ACTION_BOMB] += result["bomb_kills"]
        if result.get("swap_uses", 0) > 0:
            action_activations[ACTION_SWAP] += result["swap_uses"]
        bounty_wins = result.get("bounty_wins", 0)
        bounty_fails = result.get("bounty_fails", 0)
        if bounty_wins > 0 or bounty_fails > 0:
            action_activations[ACTION_BOUNTY] += bounty_wins  # "activated successfully"

        # ── MASCOT IMPACT (M2) ──
        winner = result["winner"]
        winner_set = set(winner) if isinstance(winner, list) else {winner}

        for pid in range(num_players):
            if pid in game.mascot_holders:
                mascot_holder_games += 1
                if pid in winner_set:
                    mascot_holder_wins += (1.0 / len(winner_set))
            else:
                non_mascot_holder_games += 1
                if pid in winner_set:
                    non_mascot_holder_wins += (1.0 / len(winner_set))

        # ── HOME FIELD (M3) ──
        hf_in_wins += game.hf_in_winning_plays
        no_hf_in_wins += game.no_hf_in_winning_plays
        mascot_zone_wins += game.mascot_zone_wins
        total_zone_wins += game.total_zone_wins

        # ── VP BY ROUND (M4) ──
        num_rounds = game.num_rounds
        for rnd in range(num_rounds):
            round_total = sum(game.round_vp[rnd].values())
            round_vp_all[rnd].append(round_total)
            for pid in range(num_players):
                vp = game.round_vp[rnd].get(pid, 0)
                round_vp_totals[rnd][game_styles[pid]].append(vp)

        # ── CLOSE GAMES / BLOWOUTS (J1) ──
        scores = result["scores"]
        sorted_scores = sorted(scores.values(), reverse=True)
        gap_1st_2nd = sorted_scores[0] - sorted_scores[1]
        score_gaps.append(gap_1st_2nd)

        # Did the final round change the winner?
        pre_final = game._pre_round_scores
        pre_final_leader = max(pre_final, key=pre_final.get)
        final_winner = result["winner"]
        if isinstance(final_winner, list):
            if pre_final_leader not in final_winner:
                final_round_flips += 1
        else:
            if pre_final_leader != final_winner:
                final_round_flips += 1

        # ── CONDITION IMPACT (C1) ──
        conditions_this_game = result.get("condition_cards", [])
        final_spread = sorted_scores[0] - sorted_scores[-1]
        for cond_name in conditions_this_game:
            condition_spreads[cond_name].append(final_spread)
            condition_games[cond_name] += 1

    return {
        "total_games": total_games,
        "num_players": num_players,
        "num_rounds": config["game_rules"]["num_rounds"],

        # M1
        "total_action_plays": dict(total_action_plays),
        "action_games_played": dict(action_games_played),
        "action_activations": dict(action_activations),

        # M2
        "mascot_holder_wins": mascot_holder_wins,
        "mascot_holder_games": mascot_holder_games,
        "non_mascot_holder_wins": non_mascot_holder_wins,
        "non_mascot_holder_games": non_mascot_holder_games,

        # M3
        "hf_in_wins": hf_in_wins,
        "no_hf_in_wins": no_hf_in_wins,
        "mascot_zone_wins": mascot_zone_wins,
        "total_zone_wins": total_zone_wins,

        # M4
        "round_vp_all": {r: v for r, v in round_vp_all.items()},

        # J1
        "score_gaps": score_gaps,
        "final_round_flips": final_round_flips,

        # C1
        "condition_spreads": dict(condition_spreads),
        "condition_games": dict(condition_games),
    }


# ─── REPORTING ─────────────────────────────────────────────────────────────

def print_report(data, player_label):
    N = data["total_games"]
    np = data["num_players"]
    nr = data["num_rounds"]

    print(f"\n{'='*65}")
    print(f"  DEEP ANALYSIS — {player_label} ({N} games)")
    print(f"{'='*65}")

    # ── M1: ACTION CARD ACTIVATION ──
    print(f"\n── M1: ACTION CARD ACTIVATION RATES ──")
    print(f"  {'Action':<10} {'Played':>8} {'Play%':>7} {'Fired':>8} {'Fire%':>7} {'Fire/Play':>10}")

    action_names = {ACTION_SHIELD: "Shield", ACTION_BOMB: "Bomb",
                    ACTION_SWAP: "Swap", ACTION_BOUNTY: "Bounty"}

    for action_type in [ACTION_SHIELD, ACTION_BOMB, ACTION_SWAP, ACTION_BOUNTY]:
        name = action_names[action_type]
        played = data["total_action_plays"].get(action_type, 0)
        games_with = data["action_games_played"].get(action_type, 0)
        fired = data["action_activations"].get(action_type, 0)
        play_pct = games_with / N if N > 0 else 0
        fire_pct = games_with and fired > 0
        fire_per_play = fired / played if played > 0 else 0
        fire_per_game = fired / N

        print(f"  {name:<10} {played:>7.0f} {play_pct:>6.0%} {fired:>8.0f} "
              f"{fire_per_game:>6.1%} {fire_per_play:>9.0%}")

    print(f"\n  Note: 'Played' = total times deployed. 'Play%' = % of games where it appeared.")
    print(f"        'Fired' = times it had a meaningful effect. 'Fire/Play' = activation rate per play.")

    # ── M2: MASCOT IMPACT ──
    print(f"\n── M2: MASCOT IMPACT ON WIN RATE ──")
    mh_wr = data["mascot_holder_wins"] / data["mascot_holder_games"] if data["mascot_holder_games"] > 0 else 0
    nmh_wr = data["non_mascot_holder_wins"] / data["non_mascot_holder_games"] if data["non_mascot_holder_games"] > 0 else 0
    fair = 1.0 / np
    mz_pct = data["mascot_zone_wins"] / data["total_zone_wins"] if data["total_zone_wins"] > 0 else 0

    print(f"  Mascot holders:     {mh_wr:.1%} win rate ({data['mascot_holder_games']} appearances)")
    print(f"  Non-mascot holders: {nmh_wr:.1%} win rate ({data['non_mascot_holder_games']} appearances)")
    print(f"  Expected (fair):    {fair:.1%}")
    print(f"  Mascot advantage:   {mh_wr - nmh_wr:+.1%}")
    print(f"  Zones won with mascot in stack: {mz_pct:.1%} of all zone wins")

    if abs(mh_wr - nmh_wr) > 0.10:
        print(f"  ⚠️  Mascot advantage is significant (>{10}%)")
    else:
        print(f"  ✅ Mascot advantage is within acceptable range")

    # ── M3: HOME FIELD ──
    print(f"\n── M3: HOME FIELD IN WINNING PLAYS ──")
    total_win_plays = data["hf_in_wins"] + data["no_hf_in_wins"]
    hf_pct = data["hf_in_wins"] / total_win_plays if total_win_plays > 0 else 0
    print(f"  Winning plays with Home Field:    {data['hf_in_wins']:>5} ({hf_pct:.1%})")
    print(f"  Winning plays without Home Field: {data['no_hf_in_wins']:>5} ({1 - hf_pct:.1%})")

    if hf_pct > 0.90:
        print(f"  ⚠️  Off-color plays almost never win — Home Field feels mandatory")
    elif hf_pct > 0.60:
        print(f"  ⚠️  Home Field is strong but not mandatory")
    else:
        print(f"  ✅ Both HF and off-color wins are viable")

    # ── M4: VP BY ROUND ──
    print(f"\n── M4: VP DISTRIBUTION BY ROUND ──")
    total_vp_all_rounds = sum(statistics.mean(v) for v in data["round_vp_all"].values())

    print(f"  {'Round':<8} {'Avg VP':>8} {'% Total':>9} {'Min':>6} {'Max':>6}")
    for rnd in range(nr):
        vp_list = data["round_vp_all"][rnd]
        avg = statistics.mean(vp_list)
        pct = avg / total_vp_all_rounds if total_vp_all_rounds > 0 else 0
        mn = min(vp_list)
        mx = max(vp_list)
        print(f"  R{rnd+1:<6} {avg:>7.1f} {pct:>8.1%} {mn:>6} {mx:>6}")

    r4_pct = statistics.mean(data["round_vp_all"][nr - 1]) / total_vp_all_rounds if total_vp_all_rounds > 0 else 0
    if r4_pct > 0.40:
        print(f"\n  ⚠️  Final round accounts for {r4_pct:.0%} of total VP — early rounds may feel low-stakes")
    else:
        print(f"\n  ✅ VP spread across rounds is healthy (final round = {r4_pct:.0%})")

    # ── J1: CLOSE GAMES VS BLOWOUTS ──
    print(f"\n── J1: CLOSE GAMES VS BLOWOUTS ──")
    gaps = data["score_gaps"]
    avg_gap = statistics.mean(gaps)
    med_gap = statistics.median(gaps)
    p10 = sorted(gaps)[len(gaps) // 10]
    p90 = sorted(gaps)[9 * len(gaps) // 10]

    close_games = sum(1 for g in gaps if g <= 3)  # within 3 VP
    blowouts = sum(1 for g in gaps if g >= 15)
    flip_rate = data["final_round_flips"] / N

    print(f"  1st-to-2nd VP gap:  avg {avg_gap:.1f}, median {med_gap:.1f}")
    print(f"  10th-90th range:    {p10} – {p90}")
    print(f"  Close games (≤3 VP gap):    {close_games:>4} ({close_games/N:.1%})")
    print(f"  Blowouts (≥15 VP gap):      {blowouts:>4} ({blowouts/N:.1%})")
    print(f"  Final round flipped winner:  {data['final_round_flips']:>4} ({flip_rate:.1%})")

    if flip_rate < 0.10:
        print(f"  ⚠️  Final round rarely matters — game decided early")
    elif flip_rate > 0.50:
        print(f"  ⚠️  Final round too swingy — early rounds feel irrelevant")
    else:
        print(f"  ✅ Healthy flip rate — final round matters but doesn't dominate")

    # ── C1: CONDITION CARD IMPACT ──
    print(f"\n── C1: CONDITION CARD IMPACT ON VP SPREADS ──")
    print(f"  {'Condition':<22} {'Games':>6} {'Avg Spread':>11} {'Tight(<5)':>10} {'Blow(>15)':>10}")

    cond_stats = []
    for cond_name, spreads in sorted(data["condition_spreads"].items()):
        if not spreads:
            continue
        avg_sp = statistics.mean(spreads)
        tight = sum(1 for s in spreads if s <= 5)
        blow = sum(1 for s in spreads if s >= 15)
        n_c = len(spreads)
        cond_stats.append((cond_name, n_c, avg_sp, tight / n_c, blow / n_c))

    # Sort by avg spread (tightest first)
    cond_stats.sort(key=lambda x: x[2])
    for name, count, avg_sp, tight_pct, blow_pct in cond_stats:
        print(f"  {name:<22} {count:>5} {avg_sp:>10.1f} {tight_pct:>9.0%} {blow_pct:>9.0%}")

    # Highlight extremes
    tightest = cond_stats[0]
    widest = cond_stats[-1]
    print(f"\n  Tightest: {tightest[0]} (avg spread {tightest[2]:.1f})")
    print(f"  Widest:   {widest[0]} (avg spread {widest[2]:.1f})")


# ─── MAIN ──────────────────────────────────────────────────────────────────

def main():
    N = 2000
    config = load_config()

    style_sets = {
        3: ["balanced", "aggressive", "sniper"],
        4: ["balanced", "aggressive", "sniper", "hoarder"],
        5: ["balanced", "aggressive", "sniper", "hoarder", "spread"],
    }

    print("=" * 65)
    print("  DESIGNER DEEP ANALYSIS — v0.1.4")
    print(f"  {N} games per player count")
    print("=" * 65)

    for np in [3, 4, 5]:
        print(f"\n▶ Running {np}P analysis...", end="", flush=True)
        data = run_analysis(N, np, style_sets[np], config)
        print(" done")
        print_report(data, f"{np}P")

    print(f"\n{'='*65}")


if __name__ == "__main__":
    main()
