#!/usr/bin/env python3
"""
Moment analysis — measuring structural proxies for dopamine, agency, and replayability.

DOPAMINE PEAKS: How often do exciting/dramatic moments happen?
  - Close wins (won by ≤2 strength)
  - Blowout wins (won by ≥10 strength)
  - Bomb kills on high cards (rank 7+)
  - Bounty payoffs (double VP)
  - Bounty busts (gambled and lost)
  - Mascot combo big plays (strength 15+)
  - Comeback victories (trailing after round 2, won the game)
  - Last-round swing zones (a zone that changed the game winner)
  - Shield saves that earned consolation while losing

PLAYER AGENCY: Do decisions matter more than luck?
  - Win rate by style (wider spread = more strategic)
  - Correlation between cards played and winning
  - Condition card impact (how much does the condition change outcomes?)
  - Home Field utilization (did players who sought HF do better?)
  - Pass impact (how much did the draft change hand quality?)

REPLAYABILITY: How different is each game?
  - Score variance game-to-game
  - Winner diversity (how often does each seat win?)
  - Condition sequence variety
  - Hand composition variance
  - Strategic path diversity (do games feel different?)

Runs 2000 games at 3P, collecting detailed per-game and per-zone data.
"""

import json
import math
import os
import statistics
import sys
from collections import defaultdict, Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cards_v4 import (
    Card, COLORS, COLOR_ORDER, build_deck,
    CARD_TYPE_NUMBER, CARD_TYPE_MASCOT, CARD_TYPE_ACTION, CARD_TYPE_DUD,
    ACTION_SHIELD, ACTION_BOMB, ACTION_SWAP, ACTION_BOUNTY,
)
from game_state_v4 import GameStateV4, Zone
from ai_player_v4 import AIPlayerV4, STYLE_PROFILES

import random

NUM_GAMES = 2000
NUM_PLAYERS = 3


def run_moment_analysis():
    """Run games with detailed moment tracking."""

    # ── Dopamine counters ──
    close_wins = 0        # zone won by ≤2 strength margin
    blowout_wins = 0      # zone won by ≥10 strength margin
    bomb_kills_high = 0   # bomb destroyed a rank 7+ card
    bounty_payoffs = 0    # bounty doubled VP
    bounty_busts = 0      # bounty got 0
    mascot_big_plays = 0  # mascot combo yielded 15+ strength
    shield_consolations = 0
    comebacks = 0         # was losing after round 2, won the game
    lead_changes = 0      # per game, how often does the leader change
    uncontested_steals = 0  # won a zone nobody else contested

    # Per-game tracking for aggregation
    all_close_per_game = []
    all_blowout_per_game = []
    all_lead_changes_per_game = []
    all_moments_per_game = []  # total "exciting moments" per game

    # ── Agency counters ──
    condition_win_shifts = 0  # times the condition likely changed who won a zone
    hf_decisive = 0           # home field was the margin of victory
    total_zones_scored = 0
    pass_quality_delta = []   # how much did passing improve hand quality?

    # ── Replayability counters ──
    all_final_scores = []
    all_winner_ids = []
    condition_sequences = []
    winning_margins = []
    zone_win_patterns = []  # which zones each winner won

    config_path = os.path.join(os.path.dirname(__file__), "config_v4.json")
    with open(config_path) as f:
        config = json.load(f)

    for game_idx in range(NUM_GAMES):
        seed = game_idx + 1
        game = GameStateV4(NUM_PLAYERS, seed=seed, config=config)

        ais = []
        styles_this_game = list(STYLE_PROFILES.keys())
        style_rng = random.Random(seed)
        style_rng.shuffle(styles_this_game)
        for pid in range(NUM_PLAYERS):
            style = styles_this_game[pid % len(styles_this_game)]
            ais.append(AIPlayerV4(pid, skill=1.0, style=style,
                                   rng_seed=seed * 100 + pid))

        # ── Measure pass quality ──
        pre_pass_quality = []
        for p in game.players:
            q = sum(c.effective_rank for c in p.hand if c.has_rank) / max(1, len(p.hand))
            pre_pass_quality.append(q)

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

        post_pass_quality = []
        for p in game.players:
            q = sum(c.effective_rank for c in p.hand if c.has_rank) / max(1, len(p.hand))
            post_pass_quality.append(q)

        for i in range(NUM_PLAYERS):
            pass_quality_delta.append(post_pass_quality[i] - pre_pass_quality[i])

        # ── Play rounds with moment tracking ──
        game_close = 0
        game_blowout = 0
        game_moments = 0
        game_lead_changes = 0
        score_after_round = {pid: 0 for pid in range(NUM_PLAYERS)}
        leader_after_round = []
        game_conditions = []

        for round_num in range(game.num_rounds):
            game.current_round = round_num
            for p in game.players:
                p.zones_won_this_round = 0

            # Condition
            if game.condition_deck:
                game.active_condition = game.condition_deck.pop(0)
                game.stats["condition_cards_drawn"].append(game.active_condition.name)
                game_conditions.append(game.active_condition.name)
            else:
                game.active_condition = None

            game.zones = [Zone(color=c, index=i) for i, c in enumerate(COLORS)]

            # Deploy
            for player in game.players:
                ai = ais[player.id]
                deploy = ai.choose_deployment(player, game, round_num)
                game._execute_deployment(player, deploy)

            # Resolve actions — track bomb kills on high cards
            bomb_kills_before = game.stats["bomb_kills"]
            # We need to check what gets bombed
            for zone in game.zones:
                for pid in zone.active_players:
                    zp = zone.get_placement(pid)
                    for card in zp.cards:
                        if card.is_action and card.action_type == ACTION_BOMB:
                            # Find what it would kill
                            for other_pid in zone.active_players:
                                ozp = zone.get_placement(other_pid)
                                for c in ozp.cards:
                                    if c.has_rank and c.effective_rank >= 7:
                                        # This is a potential high-value bomb target
                                        pass  # tracked after resolution

            game._resolve_actions()
            new_kills = game.stats["bomb_kills"] - bomb_kills_before

            # Calculate strength
            zone_strengths = game._calculate_all_strength()

            # ── Analyze each zone for moments BEFORE scoring ──
            cond = game.active_condition
            inversion = cond and cond.effect == "lowest_wins"

            for zone in game.zones:
                color = zone.color
                sm = zone_strengths.get(color, {})
                players_here = zone.active_players

                if len(players_here) == 0:
                    continue

                total_zones_scored += 1

                if len(players_here) == 1:
                    uncontested_steals += 1
                    continue

                values = sorted(sm.values(), reverse=not inversion)
                if len(values) >= 2:
                    margin = abs(values[0] - values[1])

                    if margin <= 2:
                        close_wins += 1
                        game_close += 1
                        game_moments += 1

                    if margin >= 10:
                        blowout_wins += 1
                        game_blowout += 1

                    # Home field decisive?
                    if margin <= 3 and margin > 0:
                        # Check if winner had home field
                        if inversion:
                            winner_str = min(sm.values())
                        else:
                            winner_str = max(sm.values())
                        winners = [pid for pid, s in sm.items() if s == winner_str]
                        if len(winners) == 1:
                            w = winners[0]
                            zp = zone.get_placement(w)
                            has_hf = any(c.color == color and c.is_natural
                                        for c in zp.cards)
                            if has_hf and not (cond and cond.effect == "no_home_field"):
                                hf_decisive += 1

                # Mascot big plays
                for pid in players_here:
                    s = sm.get(pid, 0)
                    zp = zone.get_placement(pid)
                    has_mascot = any(c.is_mascot for c in zp.cards)
                    if has_mascot and s >= 15:
                        mascot_big_plays += 1
                        game_moments += 1

                # Bounty outcomes
                for pid in players_here:
                    zp = zone.get_placement(pid)
                    has_bounty = any(c.is_action and c.action_type == ACTION_BOUNTY
                                    for c in zp.cards)
                    if has_bounty:
                        if inversion:
                            target = min(sm.values())
                        else:
                            target = max(sm.values())
                        winners = [p for p, s in sm.items() if s == target]
                        if pid in winners and len(winners) == 1:
                            bounty_payoffs += 1
                            game_moments += 1
                        else:
                            bounty_busts += 1
                            game_moments += 1  # busts are exciting too!

                # Shield consolation
                if len(players_here) > 1:
                    if inversion:
                        target = min(sm.values())
                    else:
                        target = max(sm.values())
                    winners = [p for p, s in sm.items() if s == target]
                    for pid in players_here:
                        if pid not in winners:
                            zp = zone.get_placement(pid)
                            if any(c.is_action and c.action_type == ACTION_SHIELD
                                   for c in zp.cards):
                                shield_consolations += 1
                                game_moments += 1

            # Score the round
            game._score_round(zone_strengths)

            # Track leader after this round
            for p in game.players:
                score_after_round[p.id] = p.score
            current_leader = max(score_after_round, key=score_after_round.get)
            leader_after_round.append(current_leader)

            game.active_condition = None

        # ── Post-game analysis ──

        # Lead changes
        for i in range(1, len(leader_after_round)):
            if leader_after_round[i] != leader_after_round[i-1]:
                game_lead_changes += 1
                lead_changes += 1

        # Comeback detection
        if len(leader_after_round) >= 3:
            # Who was leading after round 2?
            leader_r2 = leader_after_round[1]  # index 1 = after round 2
            final_scores = {p.id: p.score for p in game.players}
            final_winner = max(final_scores, key=final_scores.get)
            # Check for tie
            max_score = max(final_scores.values())
            all_winners = [pid for pid, s in final_scores.items() if s == max_score]
            if len(all_winners) == 1 and final_winner != leader_r2:
                comebacks += 1
                game_moments += 1

        all_close_per_game.append(game_close)
        all_blowout_per_game.append(game_blowout)
        all_lead_changes_per_game.append(game_lead_changes)
        all_moments_per_game.append(game_moments)

        # Replayability tracking
        final_scores = {p.id: p.score for p in game.players}
        all_final_scores.append(list(final_scores.values()))
        max_score = max(final_scores.values())
        winner = max(final_scores, key=final_scores.get)
        all_winner_ids.append(winner)
        sorted_scores = sorted(final_scores.values(), reverse=True)
        winning_margins.append(sorted_scores[0] - sorted_scores[1])
        condition_sequences.append(tuple(game_conditions))

        # Zone win pattern
        pattern = tuple(game.players[winner].total_zones_won for _ in [0])
        zone_win_patterns.append(game.players[winner].total_zones_won)

    # ══════════════════════════════════════════════════════════════════
    #  REPORT
    # ══════════════════════════════════════════════════════════════════

    n = NUM_GAMES
    total_zones = total_zones_scored

    print()
    print("=" * 75)
    print("  MOMENT ANALYSIS — Dopamine, Agency, & Replayability")
    print(f"  {n} games × {NUM_PLAYERS} players (Bookends 56-card / 4 rounds)")
    print("=" * 75)

    # ── DOPAMINE ──
    print()
    print("━" * 75)
    print("  🎯 DOPAMINE PEAKS")
    print("━" * 75)
    print()
    print("  These are the moments players will remember and talk about.")
    print()

    print(f"  Close wins (margin ≤2):        {close_wins/n:.1f}/game  "
          f"({close_wins/max(1,total_zones):.0%} of contested zones)")
    verdict = "✅ Frequent tension" if close_wins/n > 2 else "⚠️  Too rare" if close_wins/n < 0.5 else "✅ Good"
    print(f"    → {verdict}")

    print(f"  Blowout wins (margin ≥10):     {blowout_wins/n:.1f}/game  "
          f"({blowout_wins/max(1,total_zones):.0%} of contested zones)")
    verdict = "✅ Satisfying power plays" if 0.5 < blowout_wins/n < 3 else "⚠️  Check balance"
    print(f"    → {verdict}")

    print(f"  Bounty payoffs (double VP):    {bounty_payoffs/n:.2f}/game")
    print(f"  Bounty busts (got 0):          {bounty_busts/n:.2f}/game")
    total_bounty = bounty_payoffs + bounty_busts
    if total_bounty > 0:
        print(f"    → Risk ratio: {bounty_payoffs/total_bounty:.0%} success. ", end="")
        if 0.35 <= bounty_payoffs/total_bounty <= 0.65:
            print("✅ Exciting gamble")
        elif bounty_payoffs/total_bounty > 0.65:
            print("⚠️  Too safe — needs more risk")
        else:
            print("⚠️  Too punishing — players will stop using it")

    print(f"  Mascot mega-combos (15+ str):  {mascot_big_plays/n:.2f}/game")
    verdict = "✅ Wow moments" if mascot_big_plays/n > 0.5 else "⚠️  Too rare"
    print(f"    → {verdict}")

    print(f"  Shield consolation saves:      {shield_consolations/n:.2f}/game")
    print(f"    → {'✅ Softens losses' if shield_consolations/n > 0.1 else '⚠️  Rarely relevant'}")

    print(f"  Bomb kills:                    {game.stats['bomb_kills']/max(1,n):.2f}/game")

    print(f"  Uncontested zone steals:       {uncontested_steals/n:.1f}/game  "
          f"({uncontested_steals/max(1,total_zones):.0%} of zones)")
    verdict = "✅ Positioning rewarded" if 1 < uncontested_steals/n < 5 else "⚠️  Check"
    print(f"    → {verdict}")

    print(f"\n  Comebacks (trailing R2, won):  {comebacks/n:.1%} of games")
    verdict = "✅ Games stay alive" if comebacks/n > 0.10 else "⚠️  Front-runner wins too often"
    print(f"    → {verdict}")

    print(f"  Lead changes per game:         {statistics.mean(all_lead_changes_per_game):.1f} avg")
    verdict = "✅ Narrative arc" if statistics.mean(all_lead_changes_per_game) > 0.5 else "⚠️  Static"
    print(f"    → {verdict}")

    avg_moments = statistics.mean(all_moments_per_game)
    print(f"\n  Total 'moments' per game:      {avg_moments:.1f} avg "
          f"(min={min(all_moments_per_game)}, max={max(all_moments_per_game)})")
    if avg_moments >= 4:
        print(f"    → ✅ High drama — plenty of table talk triggers")
    elif avg_moments >= 2:
        print(f"    → ✅ Solid — at least a couple of memorable moments per game")
    else:
        print(f"    → ⚠️  Low drama — game may feel flat")

    # ── AGENCY ──
    print()
    print("━" * 75)
    print("  🧠 PLAYER AGENCY")
    print("━" * 75)
    print()
    print("  Does skill matter? Can players meaningfully influence outcomes?")
    print()

    print(f"  Home Field decisive wins:      {hf_decisive/n:.1f}/game  "
          f"({hf_decisive/max(1,total_zones):.0%} of zones)")
    print(f"    → {'✅ Positioning rewarded' if hf_decisive/n > 1 else '⚠️  HF rarely decides outcomes'}")

    avg_delta = statistics.mean(pass_quality_delta)
    print(f"  Draft quality change:          {avg_delta:+.2f} avg rank improvement")
    if abs(avg_delta) > 0.3:
        print(f"    → ✅ Passing meaningfully shapes hands")
    else:
        print(f"    → Draft impact is subtle (which is fine for a family game)")

    # Win rate by seat (proxy for luck vs skill)
    seat_wins = Counter(all_winner_ids)
    fair = n / NUM_PLAYERS
    seat_deviation = max(abs(seat_wins[pid] - fair) / fair for pid in range(NUM_PLAYERS))
    print(f"  Seat balance deviation:        {seat_deviation:.1%}")
    print(f"    → {'✅ No seat advantage' if seat_deviation < 0.08 else '⚠️  Seat matters too much'}")

    # Close games = more agency-feeling (your last decision mattered)
    close_game_pct = sum(1 for m in winning_margins if m <= 5) / n
    print(f"  Close games (margin ≤5 VP):    {close_game_pct:.0%}")
    print(f"    → {'✅ Decisions feel decisive' if close_game_pct > 0.25 else '⚠️  Outcomes too predetermined'}")

    blowout_game_pct = sum(1 for m in winning_margins if m >= 20) / n
    print(f"  Blowout games (margin ≥20):    {blowout_game_pct:.0%}")
    print(f"    → {'✅ Rare enough to not frustrate' if blowout_game_pct < 0.25 else '⚠️  Too many non-games'}")

    # ── REPLAYABILITY ──
    print()
    print("━" * 75)
    print("  🔄 REPLAYABILITY")
    print("━" * 75)
    print()
    print("  Does each game feel different? Will players want to play again?")
    print()

    # Score variance
    all_winning_scores = [max(scores) for scores in all_final_scores]
    score_cv = statistics.stdev(all_winning_scores) / statistics.mean(all_winning_scores)
    print(f"  Winner score variance:         CV={score_cv:.2f}  "
          f"(mean={statistics.mean(all_winning_scores):.0f}, "
          f"σ={statistics.stdev(all_winning_scores):.0f})")
    print(f"    → {'✅ High variability — games feel different' if score_cv > 0.20 else '⚠️  Games converge to similar scores'}")

    # Margin distribution
    tight = sum(1 for m in winning_margins if m <= 5)
    medium = sum(1 for m in winning_margins if 5 < m <= 15)
    wide = sum(1 for m in winning_margins if m > 15)
    print(f"  Win margin spread:             tight(≤5)={tight/n:.0%}  "
          f"med(6-15)={medium/n:.0%}  wide(15+)={wide/n:.0%}")
    if tight/n > 0.25 and wide/n > 0.10:
        print(f"    → ✅ Mix of nail-biters and runaways — varied drama")
    else:
        print(f"    → Margin distribution is narrow")

    # Condition sequence diversity
    unique_sequences = len(set(condition_sequences))
    print(f"  Unique condition sequences:     {unique_sequences}/{n} games "
          f"({unique_sequences/n:.0%} unique)")
    print(f"    → {'✅ Almost every game has a unique condition combo' if unique_sequences/n > 0.90 else 'Some repetition'}")

    # Winner diversity
    winner_entropy = 0
    for pid in range(NUM_PLAYERS):
        p = seat_wins.get(pid, 0) / n
        if p > 0:
            winner_entropy -= p * math.log2(p)
    max_entropy = math.log2(NUM_PLAYERS)
    print(f"  Winner entropy:                {winner_entropy:.2f} / {max_entropy:.2f} max")
    print(f"    → {'✅ Anyone can win' if winner_entropy > max_entropy * 0.95 else '⚠️  Predictable winners'}")

    # Zone win distribution for winners
    zwp_counter = Counter(zone_win_patterns)
    print(f"  Winner zone-win patterns:      {len(zwp_counter)} distinct patterns")
    for zones_won, count in sorted(zwp_counter.items()):
        print(f"    Won {zones_won} zones: {count/n:.0%} of games")

    # ── OVERALL VERDICT ──
    print()
    print("━" * 75)
    print("  📊 OVERALL GAME FEEL ASSESSMENT")
    print("━" * 75)
    print()

    dop_score = 0
    dop_max = 7
    if close_wins/n > 1.5: dop_score += 1
    if 0.5 < blowout_wins/n < 3: dop_score += 1
    if total_bounty > 0 and 0.35 <= bounty_payoffs/total_bounty <= 0.65: dop_score += 1
    if mascot_big_plays/n > 0.5: dop_score += 1
    if comebacks/n > 0.10: dop_score += 1
    if statistics.mean(all_lead_changes_per_game) > 0.5: dop_score += 1
    if avg_moments >= 3: dop_score += 1

    agency_score = 0
    agency_max = 5
    if hf_decisive/n > 1: agency_score += 1
    if seat_deviation < 0.08: agency_score += 1
    if close_game_pct > 0.25: agency_score += 1
    if blowout_game_pct < 0.25: agency_score += 1
    if abs(avg_delta) > 0.1: agency_score += 1

    replay_score = 0
    replay_max = 4
    if score_cv > 0.20: replay_score += 1
    if tight/n > 0.25 and wide/n > 0.10: replay_score += 1
    if unique_sequences/n > 0.90: replay_score += 1
    if winner_entropy > max_entropy * 0.95: replay_score += 1

    bars = lambda score, mx: "█" * score + "░" * (mx - score)

    print(f"  Dopamine:      [{bars(dop_score, dop_max)}]  {dop_score}/{dop_max}")
    print(f"  Agency:        [{bars(agency_score, agency_max)}]  {agency_score}/{agency_max}")
    print(f"  Replayability: [{bars(replay_score, replay_max)}]  {replay_score}/{replay_max}")
    print()

    total = dop_score + agency_score + replay_score
    total_max = dop_max + agency_max + replay_max
    if total >= total_max * 0.85:
        print(f"  🏆 EXCELLENT — This game has strong fundamentals across all three axes.")
    elif total >= total_max * 0.70:
        print(f"  ✅ GOOD — Solid foundation with room to refine specific areas.")
    elif total >= total_max * 0.50:
        print(f"  ⚠️  FAIR — Some mechanics need attention before playtesting.")
    else:
        print(f"  ❌ NEEDS WORK — Core loop may not sustain player interest.")

    print()
    print("=" * 75)


if __name__ == "__main__":
    run_moment_analysis()
