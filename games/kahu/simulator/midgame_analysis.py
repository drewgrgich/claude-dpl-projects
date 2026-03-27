"""Mid-game lull detector — round-by-round analysis of game tempo."""

import sys
import os
from collections import defaultdict
from typing import List, Dict

from cards import Card
from kahu_parser import load_market_cards, find_csv
from game_state import GameState, Player, load_config
from ai_player import KahuAI
from fun_audit import count_meaningful_choices


def run_tempo_game(config: dict, market_cards: List[Card],
                   num_players: int, seed: int, max_turns: int = 200) -> dict:
    """Run one game tracking per-round tempo metrics."""
    game = GameState(config, num_players, seed=seed, market_cards=list(market_cards))
    ais = [KahuAI(skill=1.0, style="balanced", aggression=0.5,
                   rng_seed=seed + i * 10000)
           for i in range(num_players)]

    # Per-round tracking
    round_data = defaultdict(lambda: {
        "offerings_completed": 0,
        "pua_bought": 0,
        "cards_bought": 0,
        "influence_spent": 0,
        "influence_available": 0,
        "choices_available": 0,
        "lava_advances": 0,
        "tiki_claims": 0,
        "cards_removed": 0,
        "cards_drawn_extra": 0,
        "dead_turns": 0,
        "total_turns": 0,
        "offerings_completable_but_skipped": 0,
        "pua_total_held": 0,
        "pua_needed_for_cheapest": 0,
    })

    turn = 0
    while not game.game_over and turn < max_turns:
        player = game.get_current_player()
        ai = ais[player.id]
        round_idx = turn // num_players

        rd = round_data[round_idx]
        rd["total_turns"] += 1

        # Step 1: Play hand
        lava_before = game.lava_position
        play_result = game.play_hand(player)
        lava_after = game.lava_position
        if lava_before > lava_after:
            rd["lava_advances"] += (lava_before - lava_after)

        # Effects
        effect_result = game.resolve_card_effects(player, ai.effect_callback)
        rd["cards_drawn_extra"] += effect_result.get("cards_drawn", 0)
        rd["cards_removed"] += effect_result.get("cards_removed", 0)

        # Measure choices
        choices = count_meaningful_choices(player, game)
        rd["choices_available"] += choices["raw_total"]
        rd["influence_available"] += player.influence_this_turn

        # Track pua state before spending
        total_pua = sum(player.pua.values())
        rd["pua_total_held"] += total_pua

        # Cheapest incomplete offering cost
        cheapest_remaining = 99
        for off in game.offerings:
            if off.name not in player.completed_offerings and off.available:
                needed = sum(max(0, v - player.pua.get(c, 0))
                             for c, v in off.pua_cost.items())
                cheapest_remaining = min(cheapest_remaining, needed)
        rd["pua_needed_for_cheapest"] += cheapest_remaining if cheapest_remaining < 99 else 0

        # Check if any offering is completable
        completable = 0
        for off in game.offerings:
            if off.name in player.completed_offerings or not off.available:
                continue
            can = all(player.pua.get(c, 0) >= n for c, n in off.pua_cost.items())
            if can:
                completable += 1

        # Spending
        spending_actions = ai.plan_spending(player, game)

        completed_this_turn = False
        for act in spending_actions:
            atype = act.get("type", "")
            if atype == "complete_offering":
                rd["offerings_completed"] += 1
                completed_this_turn = True
            elif atype == "buy_pua":
                rd["pua_bought"] += 1
                rd["influence_spent"] += act.get("cost", 0)
            elif atype in ("buy_market", "buy_surf"):
                rd["cards_bought"] += 1
                rd["influence_spent"] += act.get("cost", 0)
            elif atype == "claim_tiki":
                rd["tiki_claims"] += 1

        if completable > 0 and not completed_this_turn:
            rd["offerings_completable_but_skipped"] += 1

        if not spending_actions:
            rd["dead_turns"] += 1

        game.refresh_market()
        game.cleanup_and_draw(player)
        game.advance_turn()
        turn += 1

    total_rounds = max(1, game.round_number)
    return {
        "total_rounds": total_rounds,
        "round_data": dict(round_data),
        "lava_final": game.lava_position,
    }


def run_tempo_batch(config, market_cards, num_games, num_players, start_seed=1):
    """Aggregate round-by-round data across many games."""
    # Normalize to max_rounds and aggregate
    all_round_data = defaultdict(lambda: defaultdict(list))

    for i in range(num_games):
        result = run_tempo_game(config, market_cards, num_players, start_seed + i)
        total_rounds = result["total_rounds"]

        for round_idx, rd in result["round_data"].items():
            # Store as fraction of total game
            pct = round_idx / max(1, total_rounds - 1)
            # Also store by absolute round
            for key, val in rd.items():
                all_round_data[round_idx][key].append(val)

    return all_round_data


def print_tempo_report(all_round_data, num_games, num_players):
    """Print round-by-round tempo analysis."""
    max_round = max(all_round_data.keys())

    print(f"\n{'='*90}")
    print(f"  KAHU MID-GAME TEMPO ANALYSIS: {num_games} games, {num_players} players")
    print(f"{'='*90}")
    print()
    print(f"  {'Round':>5}  {'Offerings':>9}  {'Pua Bought':>10}  {'Cards':>7}  {'Inf Avail':>9}  "
          f"{'Inf Spent':>9}  {'Choices':>7}  {'Dead%':>6}  {'Pua Gap':>7}")
    print(f"  {'─'*80}")

    for r in range(max_round + 1):
        if r not in all_round_data:
            continue
        rd = all_round_data[r]
        n = len(rd["total_turns"])
        if n < num_games * 0.3:  # Skip rounds with few data points
            continue

        off = sum(rd["offerings_completed"]) / n
        pua = sum(rd["pua_bought"]) / n
        cards = sum(rd["cards_bought"]) / n
        inf_avail = sum(rd["influence_available"]) / max(1, sum(rd["total_turns"]))
        inf_spent = sum(rd["influence_spent"]) / max(1, sum(rd["total_turns"]))
        choices = sum(rd["choices_available"]) / max(1, sum(rd["total_turns"]))
        dead_pct = sum(rd["dead_turns"]) / max(1, sum(rd["total_turns"]))
        pua_gap = sum(rd["pua_needed_for_cheapest"]) / max(1, sum(rd["total_turns"]))

        # Flag lull indicators
        flag = ""
        if off < 0.1 and pua < 1.0 and dead_pct > 0.02:
            flag = " ← LULL"
        elif off < 0.05 and choices < 2.0:
            flag = " ← low action"
        elif pua_gap > 2.5:
            flag = " ← grinding"

        print(f"  {r:>5}  {off:>9.2f}  {pua:>10.1f}  {cards:>7.1f}  {inf_avail:>9.1f}  "
              f"{inf_spent:>9.1f}  {choices:>7.1f}  {dead_pct:>5.0%}  {pua_gap:>7.1f}{flag}")

    # Summary by game phase
    print(f"\n  {'─'*80}")
    print(f"\n  PHASE SUMMARY (normalized to early/mid/late thirds):")

    third = max(1, (max_round + 1) // 3)
    phases = {
        "Early (1-{})".format(third): range(0, third),
        "Mid ({}-{})".format(third + 1, 2 * third): range(third, 2 * third),
        "Late ({}-{})".format(2 * third + 1, max_round + 1): range(2 * third, max_round + 1),
    }

    for phase_name, rounds in phases.items():
        total_off = 0
        total_pua = 0
        total_cards = 0
        total_dead = 0
        total_turns = 0
        total_inf_avail = 0
        total_inf_spent = 0
        total_choices = 0
        total_pua_gap = 0
        count = 0

        for r in rounds:
            if r not in all_round_data:
                continue
            rd = all_round_data[r]
            n = len(rd["total_turns"])
            total_off += sum(rd["offerings_completed"])
            total_pua += sum(rd["pua_bought"])
            total_cards += sum(rd["cards_bought"])
            total_dead += sum(rd["dead_turns"])
            total_turns += sum(rd["total_turns"])
            total_inf_avail += sum(rd["influence_available"])
            total_inf_spent += sum(rd["influence_spent"])
            total_choices += sum(rd["choices_available"])
            total_pua_gap += sum(rd["pua_needed_for_cheapest"])
            count += n

        if total_turns == 0:
            continue

        print(f"\n  {phase_name}:")
        print(f"    Offerings completed:  {total_off / count * num_players:.2f} / round")
        print(f"    Pua purchased:        {total_pua / total_turns:.2f} / turn")
        print(f"    Cards purchased:      {total_cards / total_turns:.2f} / turn")
        print(f"    Influence available:   {total_inf_avail / total_turns:.1f} / turn")
        print(f"    Influence spent:       {total_inf_spent / total_turns:.1f} / turn")
        print(f"    Avg choices:           {total_choices / total_turns:.1f} / turn")
        print(f"    Dead turn rate:        {total_dead / total_turns:.1%}")
        print(f"    Avg Pua gap:           {total_pua_gap / total_turns:.1f} (to cheapest offering)")

    # Lull detection
    print(f"\n  {'─'*80}")
    print(f"\n  LULL DETECTION:")

    # Find consecutive rounds with below-average action
    avg_off_per_round = sum(
        sum(all_round_data[r]["offerings_completed"])
        for r in all_round_data
    ) / max(1, sum(
        len(all_round_data[r]["total_turns"])
        for r in all_round_data
    ))

    lull_rounds = []
    for r in range(max_round + 1):
        if r not in all_round_data:
            continue
        rd = all_round_data[r]
        n = len(rd["total_turns"])
        if n < num_games * 0.3:
            continue
        off = sum(rd["offerings_completed"]) / n
        pua = sum(rd["pua_bought"]) / max(1, sum(rd["total_turns"]))
        pua_gap = sum(rd["pua_needed_for_cheapest"]) / max(1, sum(rd["total_turns"]))
        if off < 0.1 and pua_gap > 2.0:
            lull_rounds.append(r)

    if lull_rounds:
        # Find consecutive stretches
        stretches = []
        current = [lull_rounds[0]]
        for r in lull_rounds[1:]:
            if r == current[-1] + 1:
                current.append(r)
            else:
                stretches.append(current)
                current = [r]
        stretches.append(current)

        for stretch in stretches:
            if len(stretch) >= 2:
                print(f"    Rounds {stretch[0]}-{stretch[-1]}: {len(stretch)}-round lull "
                      f"(no offerings, still grinding Pua)")
            else:
                print(f"    Round {stretch[0]}: minor stall")
    else:
        print(f"    No significant lull detected.")

    print(f"\n{'='*90}")


if __name__ == "__main__":
    config = load_config()
    csv_path = find_csv()
    if not csv_path:
        print("ERROR: Cannot find kahu-cards.csv")
        sys.exit(1)
    market_cards = load_market_cards(csv_path)

    num_games = 500
    num_players = 3

    if len(sys.argv) > 1:
        num_players = int(sys.argv[1])
    if len(sys.argv) > 2:
        num_games = int(sys.argv[2])

    print(f"Analyzing round-by-round tempo: {num_games} games, {num_players} players...")
    data = run_tempo_batch(config, market_cards, num_games, num_players)
    print_tempo_report(data, num_games, num_players)
