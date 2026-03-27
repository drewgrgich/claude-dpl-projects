#!/usr/bin/env python3
"""
Test candidate Condition cards for viability with 4 colors.

For each candidate condition, simulates thousands of dealt hands and measures:
  - stuck_rate: player has fewer than 2 playable cards (bad experience)
  - zero_rate: player has 0 playable cards (unacceptable)
  - avg_playable: average number of playable cards (should be meaningful but constraining)
  - restriction_bite: what fraction of hand gets eliminated (want 20-60%)

Target thresholds:
  - stuck_rate < 15% (at most 1 in 7 times does it feel bad)
  - zero_rate < 3% (almost never completely locked out)
  - restriction_bite between 20-60% (enough to matter, not enough to cripple)

Uses 4 colors, flat 0-10 distribution (44 cards) as baseline.
Tests across 2, 3, 4, 5 player counts.

Usage:
  python test_conditions.py
"""

import random
import statistics
from collections import defaultdict, Counter
from typing import List, Callable, Dict

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cards import Card, build_full_deck

# ─── DECK CONFIG ──────────────────────────────────────────────────────────────

FACTIONS = ["RED", "BLUE", "YELLOW", "GREEN"]
RANKS = list(range(0, 11))  # 0-10
TOTAL_CARDS = len(FACTIONS) * len(RANKS)  # 44

HAND_SIZES = {2: 15, 3: 10, 4: 7, 5: 6}

# Cards per round (approximate: hand / 3)
def cards_per_round(hand_size):
    return max(3, hand_size // 3)


# ─── CANDIDATE CONDITIONS ────────────────────────────────────────────────────
# Each condition is a dict with:
#   name: display name
#   description: what it does (for the card)
#   filter_fn: given a list of Cards, return the playable subset
#   category: "card_restriction", "placement", or "scoring_twist"
#
# Note: placement and scoring conditions don't restrict WHICH cards are playable,
# they restrict WHERE or HOW. We test those differently.

def build_candidates():
    candidates = []

    # ─── CARD RESTRICTION CONDITIONS ──────────────────────────────────────
    # These limit which cards from your hand you may play.

    candidates.append({
        "name": "Only Even",
        "desc": "Play only even-ranked cards (0, 2, 4, 6, 8, 10)",
        "category": "card",
        "filter": lambda cards: [c for c in cards if c.rank % 2 == 0],
    })

    candidates.append({
        "name": "Only Odd",
        "desc": "Play only odd-ranked cards (1, 3, 5, 7, 9)",
        "category": "card",
        "filter": lambda cards: [c for c in cards if c.rank % 2 == 1],
    })

    candidates.append({
        "name": "Low Cards Only (≤5)",
        "desc": "Play only cards ranked 5 or below",
        "category": "card",
        "filter": lambda cards: [c for c in cards if c.rank <= 5],
    })

    candidates.append({
        "name": "High Cards Only (≥5)",
        "desc": "Play only cards ranked 5 or above",
        "category": "card",
        "filter": lambda cards: [c for c in cards if c.rank >= 5],
    })

    candidates.append({
        "name": "Low Cards Only (≤6)",
        "desc": "Play only cards ranked 6 or below",
        "category": "card",
        "filter": lambda cards: [c for c in cards if c.rank <= 6],
    })

    candidates.append({
        "name": "High Cards Only (≥4)",
        "desc": "Play only cards ranked 4 or above",
        "category": "card",
        "filter": lambda cards: [c for c in cards if c.rank >= 4],
    })

    candidates.append({
        "name": "No Red",
        "desc": "You may not play Red cards this round",
        "category": "card",
        "filter": lambda cards: [c for c in cards if c.faction != "RED"],
    })

    candidates.append({
        "name": "No Blue",
        "desc": "You may not play Blue cards this round",
        "category": "card",
        "filter": lambda cards: [c for c in cards if c.faction != "BLUE"],
    })

    candidates.append({
        "name": "No Yellow",
        "desc": "You may not play Yellow cards this round",
        "category": "card",
        "filter": lambda cards: [c for c in cards if c.faction != "YELLOW"],
    })

    candidates.append({
        "name": "No Green",
        "desc": "You may not play Green cards this round",
        "category": "card",
        "filter": lambda cards: [c for c in cards if c.faction != "GREEN"],
    })

    candidates.append({
        "name": "No Wildcards",
        "desc": "You may not play Mascots (0) or highest rank (10)",
        "category": "card",
        "filter": lambda cards: [c for c in cards if c.rank not in (0, 10)],
    })

    candidates.append({
        "name": "Naturals Only",
        "desc": "Play only natural cards (ranks 1-9)",
        "category": "card",
        "filter": lambda cards: [c for c in cards if 1 <= c.rank <= 9],
    })

    candidates.append({
        "name": "Max 3 Cards",
        "desc": "Play at most 3 cards this round",
        "category": "card",
        "filter": lambda cards: cards,  # All playable, but capped at 3
        "cap": 3,
    })

    candidates.append({
        "name": "Max 4 Cards",
        "desc": "Play at most 4 cards this round",
        "category": "card",
        "filter": lambda cards: cards,
        "cap": 4,
    })

    candidates.append({
        "name": "Max 5 Cards",
        "desc": "Play at most 5 cards this round",
        "category": "card",
        "filter": lambda cards: cards,
        "cap": 5,
    })

    candidates.append({
        "name": "Min 4 Cards",
        "desc": "You must play at least 4 cards this round",
        "category": "card",
        "filter": lambda cards: cards,  # All playable
        "min_play": 4,
    })

    # Two-color restrictions
    candidates.append({
        "name": "Only Red/Blue",
        "desc": "Play only Red or Blue cards",
        "category": "card",
        "filter": lambda cards: [c for c in cards if c.faction in ("RED", "BLUE")],
    })

    candidates.append({
        "name": "Only Yellow/Green",
        "desc": "Play only Yellow or Green cards",
        "category": "card",
        "filter": lambda cards: [c for c in cards if c.faction in ("YELLOW", "GREEN")],
    })

    candidates.append({
        "name": "Only Red/Green",
        "desc": "Play only Red or Green cards",
        "category": "card",
        "filter": lambda cards: [c for c in cards if c.faction in ("RED", "GREEN")],
    })

    candidates.append({
        "name": "Only Blue/Yellow",
        "desc": "Play only Blue or Yellow cards",
        "category": "card",
        "filter": lambda cards: [c for c in cards if c.faction in ("BLUE", "YELLOW")],
    })

    candidates.append({
        "name": "No Duplicates",
        "desc": "No two cards you play may share a rank",
        "category": "card",
        "filter": lambda cards: cards,  # Can't pre-filter; tested separately
        "special": "no_dup_rank",
    })

    candidates.append({
        "name": "No Matching Colors",
        "desc": "No two cards you play may share a color",
        "category": "card",
        "filter": lambda cards: cards,
        "special": "no_dup_color",
    })

    # ─── PLACEMENT CONDITIONS ─────────────────────────────────────────────
    # These don't restrict which cards, but where you put them.

    candidates.append({
        "name": "All In (1-2 zones)",
        "desc": "All your cards must go to at most 2 zones",
        "category": "placement",
        "max_zones": 2,
    })

    candidates.append({
        "name": "Spread Out (3+ zones)",
        "desc": "You must play at 3 or more different zones",
        "category": "placement",
        "min_zones": 3,
    })

    candidates.append({
        "name": "Full Coverage (all 4)",
        "desc": "You must play at least 1 card at every zone",
        "category": "placement",
        "min_zones": 4,
    })

    # ─── SCORING TWIST CONDITIONS ─────────────────────────────────────────
    # These change how scoring works, not what you can play.

    candidates.append({
        "name": "Inversion",
        "desc": "Lowest strength wins each zone this round",
        "category": "scoring",
    })

    candidates.append({
        "name": "Double VP",
        "desc": "Each zone is worth 10 VP instead of 5 this round",
        "category": "scoring",
    })

    candidates.append({
        "name": "No Home Field",
        "desc": "Home Field Advantage does not apply this round",
        "category": "scoring",
    })

    candidates.append({
        "name": "Ties Lose",
        "desc": "If two or more players tie at a zone, nobody scores",
        "category": "scoring",
    })

    candidates.append({
        "name": "Fewest Cards Wins Ties",
        "desc": "Ties broken by whoever played fewer cards at that zone",
        "category": "scoring",
    })

    candidates.append({
        "name": "Bonus: Lone Wolf",
        "desc": "+3 VP for each zone where you're the only player",
        "category": "scoring",
    })

    candidates.append({
        "name": "Bonus: Big Stack",
        "desc": "+2 VP for each zone where you play 3+ cards",
        "category": "scoring",
    })

    return candidates


# ─── SIMULATION ───────────────────────────────────────────────────────────────

def test_card_conditions(candidates, num_trials=5000, seed=42):
    """Test card-restriction conditions across all player counts."""
    rng = random.Random(seed)
    results = {}

    card_candidates = [c for c in candidates if c["category"] == "card"]

    for num_players in [2, 3, 4, 5]:
        hand_size = HAND_SIZES[num_players]
        round_cards = cards_per_round(hand_size)

        for cond in card_candidates:
            key = f"{cond['name']}|{num_players}P"
            stuck = 0
            zero = 0
            playable_counts = []
            bite_rates = []
            total = 0

            for t in range(num_trials):
                deck = build_full_deck(factions=FACTIONS, ranks_per_faction=RANKS)
                rng.shuffle(deck)

                for p in range(num_players):
                    hand = deck[p * hand_size:(p + 1) * hand_size]
                    # Simulate round hand (first third of cards roughly)
                    round_hand = hand[:round_cards]
                    total += 1

                    if cond.get("special") == "no_dup_rank":
                        # For "no duplicates" — count unique ranks available
                        rank_counts = Counter(c.rank for c in round_hand)
                        playable = len(rank_counts)  # max cards you could play
                    elif cond.get("special") == "no_dup_color":
                        color_counts = Counter(c.faction for c in round_hand)
                        playable = len(color_counts)  # max 4
                    else:
                        filtered = cond["filter"](round_hand)
                        cap = cond.get("cap")
                        if cap:
                            playable = min(len(filtered), cap)
                        else:
                            playable = len(filtered)

                    min_play = cond.get("min_play", 0)
                    if min_play and len(round_hand) < min_play:
                        stuck += 1
                        if len(round_hand) == 0:
                            zero += 1
                    elif playable < 2:
                        stuck += 1
                        if playable == 0:
                            zero += 1

                    playable_counts.append(playable)
                    bite = 1.0 - (playable / len(round_hand)) if round_hand else 0
                    bite_rates.append(bite)

            results[key] = {
                "name": cond["name"],
                "players": num_players,
                "hand_size": hand_size,
                "round_cards": round_cards,
                "stuck_rate": stuck / total,
                "zero_rate": zero / total,
                "avg_playable": statistics.mean(playable_counts),
                "bite": statistics.mean(bite_rates),
            }

    return results


def test_placement_conditions(candidates, num_trials=5000, seed=42):
    """Test placement conditions — can players meet them with their hand?"""
    rng = random.Random(seed)
    results = {}

    place_candidates = [c for c in candidates if c["category"] == "placement"]

    for num_players in [2, 3, 4, 5]:
        hand_size = HAND_SIZES[num_players]
        round_cards = cards_per_round(hand_size)

        for cond in place_candidates:
            key = f"{cond['name']}|{num_players}P"
            impossible = 0
            total = 0

            for t in range(num_trials):
                deck = build_full_deck(factions=FACTIONS, ranks_per_faction=RANKS)
                rng.shuffle(deck)

                for p in range(num_players):
                    hand = deck[p * hand_size:(p + 1) * hand_size]
                    round_hand = hand[:round_cards]
                    total += 1

                    unique_colors = len(set(c.faction for c in round_hand))
                    min_zones = cond.get("min_zones", 0)
                    max_zones = cond.get("max_zones", 99)

                    # Can they meet the zone requirement?
                    if min_zones and unique_colors < min_zones:
                        # They don't have enough colors to spread to min_zones
                        # But they could play any card at any zone, so they
                        # always CAN play at N zones if they have N cards
                        if round_cards < min_zones:
                            impossible += 1

            results[key] = {
                "name": cond["name"],
                "players": num_players,
                "impossible_rate": impossible / total if total else 0,
            }

    return results


# ─── REPORTING ───────────────────────────────────────────────────────────────

def print_results(card_results, placement_results, candidates):
    print(f"\n{'='*95}")
    print(f"  CONDITION CARD VIABILITY — 4 COLORS × [0-10] (44 cards)")
    print(f"{'='*95}")

    # Card restriction conditions
    card_conds = sorted(set(r["name"] for r in card_results.values()))

    print(f"\n--- CARD RESTRICTION CONDITIONS ---")
    print(f"  Thresholds: stuck < 15%, zero < 3%, bite 20-60%")
    print()

    header = f"{'Condition':<25} {'P':>1}"
    header += f" {'Hand':>4} {'Rnd':>3} {'Stuck':>6} {'Zero':>5} {'Avg#':>5} {'Bite':>5} {'OK?':>4}"
    print(header)
    print("-" * 65)

    for cond_name in card_conds:
        for np in [2, 3, 4, 5]:
            key = f"{cond_name}|{np}P"
            if key not in card_results:
                continue
            r = card_results[key]
            stuck_ok = r["stuck_rate"] < 0.15
            zero_ok = r["zero_rate"] < 0.03
            bite_ok = 0.15 <= r["bite"] <= 0.65
            all_ok = stuck_ok and zero_ok and bite_ok

            flag = "✅" if all_ok else "⚠️" if (stuck_ok and zero_ok) else "❌"

            name = cond_name if np == 2 else ""
            print(f"{name:<25} {np:>1}  {r['hand_size']:>4} {r['round_cards']:>3}"
                  f"  {r['stuck_rate']:>5.0%} {r['zero_rate']:>4.0%}"
                  f"  {r['avg_playable']:>4.1f} {r['bite']:>4.0%}  {flag}")
        print()

    # Placement conditions
    print(f"\n--- PLACEMENT CONDITIONS ---")
    place_conds = [c for c in candidates if c["category"] == "placement"]
    for cond in place_conds:
        print(f"\n  {cond['name']}: \"{cond['desc']}\"")
        for np in [2, 3, 4, 5]:
            key = f"{cond['name']}|{np}P"
            if key in placement_results:
                r = placement_results[key]
                imp = r["impossible_rate"]
                flag = "✅" if imp < 0.05 else "❌"
                print(f"    {np}P: impossible {imp:.0%} {flag}")

    # Scoring conditions — always viable (no card restrictions)
    print(f"\n--- SCORING TWIST CONDITIONS ---")
    scoring = [c for c in candidates if c["category"] == "scoring"]
    for c in scoring:
        print(f"  ✅ {c['name']}: \"{c['desc']}\" — always viable (no card restriction)")

    # Summary: which conditions pass at ALL player counts?
    print(f"\n{'='*95}")
    print(f"  SUMMARY — CONDITIONS THAT PASS ALL PLAYER COUNTS")
    print(f"{'='*95}")

    for cond_name in card_conds:
        all_pass = True
        for np in [2, 3, 4, 5]:
            key = f"{cond_name}|{np}P"
            if key in card_results:
                r = card_results[key]
                if r["stuck_rate"] >= 0.15 or r["zero_rate"] >= 0.03:
                    all_pass = False
                    break
        flag = "✅ PASS" if all_pass else "❌ FAIL"
        print(f"  {flag}  {cond_name}")

    for cond in place_conds:
        all_pass = True
        for np in [2, 3, 4, 5]:
            key = f"{cond['name']}|{np}P"
            if key in placement_results:
                if placement_results[key]["impossible_rate"] >= 0.05:
                    all_pass = False
        flag = "✅ PASS" if all_pass else "❌ FAIL"
        print(f"  {flag}  {cond['name']}")

    for c in scoring:
        print(f"  ✅ PASS  {c['name']}")

    print()


# ─── MAIN ────────────────────────────────────────────────────────────────────

def main():
    candidates = build_candidates()
    print(f"Testing {len(candidates)} candidate conditions...")
    print(f"Deck: 4 colors × [0-10] = 44 cards")
    print(f"Hand sizes: {HAND_SIZES}")
    print(f"Cards per round: {', '.join(f'{p}P={cards_per_round(h)}' for p, h in HAND_SIZES.items())}")

    card_results = test_card_conditions(candidates)
    placement_results = test_placement_conditions(candidates)
    print_results(card_results, placement_results, candidates)


if __name__ == "__main__":
    main()
