#!/usr/bin/env python3
"""
Cross-player-count validation of the top 12 condition cards.
Tests each condition at 3P, 4P, and 5P (2000 games each).
Then tests the full set of 12 as a mixed deck.
"""

import json
import os
import statistics
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_new_conditions import (
    CANDIDATE_CONDITIONS, ConditionTestGame, ConditionAI,
)
from game_state_v4 import ConditionCard
from ai_player_v4 import AIPlayerV4


TOP_12 = [
    # HF Disruptors (3)
    ("Inversion", "lowest_wins"),         # lowest wins → HF becomes liability
    ("Neutral Ground", "no_home_field"),   # no HF at all
    ("Color Tax", "color_tax"),            # HF = -2 penalty
    # Rank Disruptors (2)
    ("Ceiling", "ceiling_5"),              # all cards capped at 5
    ("Mirror", "mirror_ranks"),            # rank = 10 - printed
    # Deployment Constraints (2)
    ("Spread Out", "min_2_zones"),         # must use 2+ zones
    ("Lone Wolf", "lone_wolf_max1"),       # max 1 card per zone
    # Scoring Twists (3)
    ("Double Stakes", "double_vp"),        # zones worth 10 VP
    ("Sudden Death", "ties_lose"),         # ties score 0
    ("Diminishing Returns", "diminishing_returns"),  # 7/5/3/1 VP
    # Momentum & Interaction (2)
    ("Grudge Match", "grudge_match"),      # +3 to last round's loser
    ("Second Wave", "second_wave"),        # deploy 1 more after reveal
]


def load_config():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config_v4.json")
    with open(path) as f:
        return json.load(f)


def test_condition(cond_name, cond_effect, N, np, styles, config):
    style_wins = defaultdict(float)
    style_games = defaultdict(int)
    all_winner = []
    all_spread = []
    total_hf_hit = 0
    total_hf_check = 0

    for i in range(N):
        seed = 1 + i
        gs = [styles[(i + j) % len(styles)] for j in range(np)]
        game = ConditionTestGame(np, seed=seed, config=config,
                                  pass_per_round=2 if np <= 4 else 1,
                                  test_condition=cond_effect)
        ais = [ConditionAI(pid, skill=1.0, style=gs[pid], rng_seed=seed*100+pid)
               for pid in range(np)]
        for ai in ais:
            ai._game_ref = game

        def dfn(p, g, rn):
            ais[p.id]._game_ref = g
            return ais[p.id].choose_deployment(p, g, rn)
        def pfn(p, g, pc):
            return ais[p.id].choose_pass(p, g, pc)

        result = game.play_game(dfn, pfn)
        w = result["winner"]
        if isinstance(w, list):
            for x in w: style_wins[gs[x]] += 1.0/len(w)
        else:
            style_wins[gs[w]] += 1

        scores = list(result["scores"].values())
        all_winner.append(max(scores))
        all_spread.append(max(scores) - min(scores))
        for pid, sc in result["scores"].items():
            style_games[gs[pid]] += 1

        total_hf_hit += game._hf_hits
        total_hf_check += game._hf_checks

    wr = {s: style_wins[s]/style_games[s] if style_games[s] > 0 else 0
          for s in set(styles)}
    return {
        "name": cond_name,
        "effect": cond_effect,
        "gap": max(wr.values()) - min(wr.values()),
        "win_rates": wr,
        "avg_winner": statistics.mean(all_winner),
        "avg_spread": statistics.mean(all_spread),
        "blowout_pct": sum(1 for s in all_spread if s >= 25) / N,
        "close_pct": sum(1 for s in all_spread if s <= 5) / N,
        "hf_pct": total_hf_hit / total_hf_check if total_hf_check > 0 else 0,
    }


def run_skill_test(cond_effect, N, np, config):
    """Expert vs novice skill expression test."""
    expert_wins = 0
    for i in range(N):
        seed = 1 + i
        game = ConditionTestGame(np, seed=seed, config=config,
                                  pass_per_round=2 if np <= 4 else 1,
                                  test_condition=cond_effect)
        expert = ConditionAI(0, skill=1.0, style="balanced", rng_seed=seed*100)
        expert._game_ref = game
        novices = [AIPlayerV4(pid, skill=0.3, style="balanced", rng_seed=seed*100+pid)
                   for pid in range(1, np)]
        all_ai = [expert] + novices

        def dfn(p, g, rn):
            if hasattr(all_ai[p.id], '_game_ref'):
                all_ai[p.id]._game_ref = g
            return all_ai[p.id].choose_deployment(p, g, rn)
        def pfn(p, g, pc):
            return all_ai[p.id].choose_pass(p, g, pc)

        result = game.play_game(dfn, pfn)
        w = result["winner"]
        if isinstance(w, int) and w == 0: expert_wins += 1
        elif isinstance(w, list) and 0 in w: expert_wins += 1.0/len(w)

    fair = 1.0 / np
    actual = expert_wins / N
    return {"expert_wr": actual, "edge": actual - fair}


class MixedConditionGame(ConditionTestGame):
    """Game that draws from a mixed pool of 12 conditions."""
    def __init__(self, num_players, seed=42, config=None, pass_per_round=2,
                 condition_pool=None):
        # Don't pass test_condition — we'll set it per-round
        super().__init__(num_players, seed=seed, config=config,
                         pass_per_round=pass_per_round, test_condition=None)
        self.condition_pool = condition_pool or []
        import random as rnd
        self._pool_rng = rnd.Random(seed)
        # Build condition deck from pool
        self.condition_deck = []
        for _ in range(self.num_rounds):
            name, effect = self._pool_rng.choice(self.condition_pool)
            self.condition_deck.append(ConditionCard(name, "pool", effect))

    def _play_round_with_condition(self, round_num, deployment_fn):
        # Set test_condition_effect from the drawn condition
        if self.condition_deck:
            cond = self.condition_deck.pop(0)
            self.active_condition = cond
            self.test_condition_effect = cond.effect
            self.stats["condition_cards_drawn"].append(cond.name)
        else:
            self.active_condition = None
            self.test_condition_effect = None

        for p in self.players:
            p.zones_won_this_round = 0
        from game_state_v4 import Zone
        self.zones = [Zone(color=c, index=i) for i, c in enumerate(self.colors)]

        for player in self.players:
            deploy = deployment_fn(player, self, round_num)
            cond = self.test_condition_effect
            if cond == "exile":
                deploy = self._apply_exile(deploy)
            elif cond == "minimalist":
                deploy = self._apply_minimalist(deploy, 2)
            elif cond == "lone_wolf_max1":
                deploy = self._apply_lone_wolf(deploy)
            self._execute_deployment(player, deploy)

        if self.test_condition_effect == "second_wave":
            for player in self.players:
                if player.hand:
                    best_card = max(
                        [c for c in player.hand if c.has_rank],
                        key=lambda c: c.effective_rank, default=None)
                    if best_card:
                        best_zone = None
                        best_str = -1
                        for zone in self.zones:
                            zp = zone.get_placement(player.id)
                            if zp.cards:
                                s = sum(c.effective_rank for c in zp.cards if c.has_rank)
                                if s > best_str:
                                    best_str = s
                                    best_zone = zone
                        if best_zone:
                            player.hand.remove(best_card)
                            best_zone.get_placement(player.id).cards.append(best_card)
                            player.cards_played_total += 1

        self._resolve_actions()
        zone_strengths = self._calculate_all_strength_custom()
        round_stats = self._score_round_custom(zone_strengths)

        # Track zones for grudge match
        self._zones_won_last_round = defaultdict(int)
        for zone_color, winners in round_stats["zone_winners"].items():
            if winners and isinstance(winners, list):
                for w in winners:
                    self._zones_won_last_round[w] += 1

        self.active_condition = None
        self.test_condition_effect = None
        return round_stats


def test_mixed_set(N, np, styles, config, pool):
    """Test the full set of conditions as a mixed deck."""
    style_wins = defaultdict(float)
    style_games = defaultdict(int)
    all_winner = []
    all_spread = []
    lead_changes = 0
    cond_counts = defaultdict(int)

    for i in range(N):
        seed = 1 + i
        gs = [styles[(i + j) % len(styles)] for j in range(np)]
        game = MixedConditionGame(np, seed=seed, config=config,
                                   pass_per_round=2 if np <= 4 else 1,
                                   condition_pool=pool)
        ais = [ConditionAI(pid, skill=1.0, style=gs[pid], rng_seed=seed*100+pid)
               for pid in range(np)]

        def dfn(p, g, rn):
            ais[p.id]._game_ref = g
            return ais[p.id].choose_deployment(p, g, rn)
        def pfn(p, g, pc):
            return ais[p.id].choose_pass(p, g, pc)

        result = game.play_game(dfn, pfn)
        w = result["winner"]
        if isinstance(w, list):
            for x in w: style_wins[gs[x]] += 1.0/len(w)
        else:
            style_wins[gs[w]] += 1

        scores = list(result["scores"].values())
        all_winner.append(max(scores))
        all_spread.append(max(scores) - min(scores))
        for pid, sc in result["scores"].items():
            style_games[gs[pid]] += 1

        for cname in result.get("condition_cards_drawn", []):
            cond_counts[cname] += 1

    wr = {s: style_wins[s]/style_games[s] if style_games[s] > 0 else 0
          for s in set(styles)}
    return {
        "gap": max(wr.values()) - min(wr.values()),
        "win_rates": wr,
        "avg_winner": statistics.mean(all_winner),
        "winner_stdev": statistics.stdev(all_winner),
        "avg_spread": statistics.mean(all_spread),
        "blowout_pct": sum(1 for s in all_spread if s >= 25) / N,
        "close_pct": sum(1 for s in all_spread if s <= 5) / N,
        "cond_counts": dict(cond_counts),
    }


def main():
    N = 2000
    config = load_config()
    style_sets = {
        3: ["balanced", "aggressive", "sniper"],
        4: ["balanced", "aggressive", "sniper", "hoarder"],
        5: ["balanced", "aggressive", "sniper", "hoarder", "spread"],
    }

    print("=" * 90)
    print("  TOP 12 CONDITIONS — CROSS-PLAYER-COUNT VALIDATION")
    print(f"  {N} games per condition per player count")
    print("=" * 90)

    # ─── Per-condition at 3P, 4P, 5P ───
    all_results = {}  # {(cond_name, np): result}
    all_skill = {}

    for np in [3, 4, 5]:
        styles = style_sets[np]
        print(f"\n{'='*90}")
        print(f"  {np} PLAYERS")
        print(f"{'='*90}")

        for cname, ceffect in TOP_12:
            print(f"  {cname:<20} ...", end="", flush=True)
            r = test_condition(cname, ceffect, N, np, styles, config)
            s = run_skill_test(ceffect, N, np, config)
            all_results[(cname, np)] = r
            all_skill[(cname, np)] = s
            print(f" gap={r['gap']:.1%} HF={r['hf_pct']:.0%} spread={r['avg_spread']:.1f}"
                  f" close={r['close_pct']:.0%} skill={s['edge']:+.1%}")

    # ─── Summary table ───
    print(f"\n{'='*90}")
    print("  SUMMARY: Style Gap by Player Count")
    print(f"{'='*90}")
    cw = 12
    print(f"  {'Condition':<20}", end="")
    for np in [3, 4, 5]:
        print(f" {'%dP gap' % np:>{cw}} {'%dP skill' % np:>{cw}}", end="")
    print(f" {'Avg gap':>{cw}} {'Flag':>{cw}}")
    print(f"  {'-'*20}" + f" {'-'*cw}" * 7)

    flagged = []
    for cname, ceffect in TOP_12:
        gaps = []
        print(f"  {cname:<20}", end="")
        for np in [3, 4, 5]:
            r = all_results[(cname, np)]
            s = all_skill[(cname, np)]
            gaps.append(r["gap"])
            print(f" {r['gap']:>{cw}.1%} {s['edge']:>+{cw}.1%}", end="")
        avg_gap = statistics.mean(gaps)
        flag = ""
        if max(gaps) > 8:
            flag = "HIGH GAP"
            flagged.append(cname)
        elif any(s["edge"] < -0.02 for np2 in [3,4,5]
                 for s in [all_skill[(cname, np2)]]):
            flag = "NEG SKILL"
            flagged.append(cname)
        print(f" {avg_gap:>{cw}.1%} {flag:>{cw}}")

    if flagged:
        print(f"\n  ⚠ Flagged conditions: {', '.join(flagged)}")
    else:
        print(f"\n  ✅ All conditions pass balance checks across player counts")

    # ─── Blowout/Close summary ───
    print(f"\n{'='*90}")
    print("  BLOWOUT & CLOSE GAME RATES")
    print(f"{'='*90}")
    print(f"  {'Condition':<20}", end="")
    for np in [3, 4, 5]:
        print(f" {'%dP blow' % np:>{cw}} {'%dP close' % np:>{cw}}", end="")
    print()
    print(f"  {'-'*20}" + f" {'-'*cw}" * 6)
    for cname, ceffect in TOP_12:
        print(f"  {cname:<20}", end="")
        for np in [3, 4, 5]:
            r = all_results[(cname, np)]
            print(f" {r['blowout_pct']:>{cw}.0%} {r['close_pct']:>{cw}.0%}", end="")
        print()

    # ─── Mixed set test ───
    print(f"\n{'='*90}")
    print("  MIXED SET TEST: All 12 conditions as random pool")
    print(f"{'='*90}")

    pool = [(cname, ceffect) for cname, ceffect in TOP_12]

    for np in [3, 4, 5]:
        styles = style_sets[np]
        print(f"\n  {np}P mixed set...", end="", flush=True)
        mr = test_mixed_set(N, np, styles, config, pool)
        print(f" done")
        print(f"    Style gap: {mr['gap']:.1%}")
        wr_strs = [f"{s}={mr['win_rates'][s]:.0%}" for s in sorted(mr['win_rates'])]
        print(f"    Win rates: {', '.join(wr_strs)}")
        print(f"    Winner VP: {mr['avg_winner']:.1f} (σ={mr['winner_stdev']:.1f})")
        print(f"    Spread: {mr['avg_spread']:.1f}  Blowouts: {mr['blowout_pct']:.0%}  Close: {mr['close_pct']:.0%}")
        conds_drawn = mr["cond_counts"]
        total_drawn = sum(conds_drawn.values())
        print(f"    Conditions drawn ({total_drawn} total):")
        for cn in sorted(conds_drawn, key=conds_drawn.get, reverse=True):
            print(f"      {cn:<20} {conds_drawn[cn]:>4} ({conds_drawn[cn]/total_drawn:.0%})")


if __name__ == "__main__":
    main()
