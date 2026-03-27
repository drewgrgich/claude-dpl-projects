#!/usr/bin/env python3
"""
Summit Scramble Co-op Solo Modes — 2 Players vs Night Owls.

Option 1: Shared Mountain — 2 players, 2 owls, shared trick limit.
Option 2: Tag Team — 2 players, 1 owl, shared hand, alternating active player.

Both use the "Ascent" redesign: smart owls with hands, trick-limit loss condition,
bottomless owl deck (reshuffle base camp).
"""

import argparse
import random
from typing import List, Dict, Optional
from collections import defaultdict
from dataclasses import dataclass, field

from cards import (
    Card, Deck, build_full_deck, FACTIONS, FACTION_RANK,
    FACTION_ABILITIES, FACTION_NAMES,
)
from game_state import Formation, FormationType, formation_beats


# ---------------------------------------------------------------------------
# Shared components
# ---------------------------------------------------------------------------

def get_all_formations(hand: List[Card]) -> List[Formation]:
    """Get all valid formations from a hand of cards."""
    formations = []
    by_rank = defaultdict(list)
    for c in hand:
        by_rank[c.rank].append(c)

    for c in hand:
        formations.append(Formation(
            ftype=FormationType.SOLO, cards=[c],
            rank=c.rank, length=1, faction=c.faction))

    for rank, cards in by_rank.items():
        if len(cards) >= 2:
            formations.append(Formation(
                ftype=FormationType.SURGE, cards=cards[:2],
                rank=rank, length=2))
        if len(cards) >= 3:
            formations.append(Formation(
                ftype=FormationType.SURGE, cards=cards[:3],
                rank=rank, length=3))
        if len(cards) >= 4:
            formations.append(Formation(
                ftype=FormationType.CONFETTI_CANNON, cards=cards[:4],
                rank=rank, length=4))

    sorted_ranks = sorted(by_rank.keys())
    for si in range(len(sorted_ranks)):
        cr = [sorted_ranks[si]]
        for ni in range(si + 1, len(sorted_ranks)):
            if sorted_ranks[ni] == cr[-1] + 1:
                cr.append(sorted_ranks[ni])
                if len(cr) >= 3:
                    formations.append(Formation(
                        ftype=FormationType.DAISY_CHAIN,
                        cards=[by_rank[r][0] for r in cr],
                        rank=cr[-1], length=len(cr)))
            else:
                break
    return formations


@dataclass
class SmartOwl:
    name: str
    hand: List[Card] = field(default_factory=list)
    hand_limit: int = 8
    skip_next: bool = False

    @property
    def active(self) -> bool:
        return len(self.hand) > 0

    def refill(self, deck: Deck, base_camp: List[Card], rng: random.Random):
        """Refill hand to limit. Reshuffle base camp if deck empty."""
        while len(self.hand) < self.hand_limit:
            if deck.empty:
                if base_camp:
                    deck.cards = list(base_camp)
                    base_camp.clear()
                    deck.shuffle(rng)
                else:
                    break
            c = deck.draw_one()
            if c:
                self.hand.append(c)
            else:
                break

    def choose_lead(self) -> Optional[Formation]:
        """Lead with strongest formation (high rank, prefer multi-card)."""
        fs = get_all_formations(self.hand)
        if not fs:
            return None
        scored = []
        for f in fs:
            s = f.rank * 2.0 + len(f.cards) * 3.0
            if f.ftype in (FormationType.SURGE, FormationType.DAISY_CHAIN):
                s += 5.0  # multi-card = harder for players to match
            scored.append((f, s))
        scored.sort(key=lambda x: -x[1])
        return scored[0][0]

    def choose_follow(self, current: Formation) -> Optional[Formation]:
        """Beat current with cheapest option."""
        fs = get_all_formations(self.hand)
        beaters = [f for f in fs
                   if f.ftype == current.ftype and formation_beats(f, current)]
        if not beaters:
            # Trip-Up check
            if current.ftype == FormationType.SOLO and current.rank == 10:
                zeros = [c for c in self.hand if c.rank == 0]
                if zeros:
                    return Formation(ftype=FormationType.TRIP_UP,
                                    cards=[zeros[0]], rank=0, length=1,
                                    faction=zeros[0].faction)
            return None
        beaters.sort(key=lambda f: (f.rank, sum(FACTION_RANK.get(c.faction, 0) for c in f.cards)))
        return beaters[0]

    def remove_cards(self, cards: List[Card]):
        for c in cards:
            if c in self.hand:
                self.hand.remove(c)


def player_choose_lead(hand: List[Card]) -> Optional[Formation]:
    """AI: lead with best formation (multi-card, high rank for unbeatable)."""
    fs = get_all_formations(hand)
    if not fs:
        return None
    scored = []
    for f in fs:
        s = len(f.cards) * 3.5
        avg_r = sum(c.rank for c in f.cards) / len(f.cards)
        s += avg_r * 0.5  # lead high = harder to beat
        if any(c.rank == 0 for c in f.cards):
            s -= 10
        if f.ftype in (FormationType.SURGE, FormationType.DAISY_CHAIN):
            s += 4.0
        if f.rank >= 9:
            s += 3.0
        if len(hand) - len(f.cards) == 0:
            s = 9999
        scored.append((f, s))
    scored.sort(key=lambda x: -x[1])
    return scored[0][0]


def player_choose_follow(hand: List[Card], current: Formation) -> Optional[Formation]:
    """AI: beat current with cheapest option."""
    fs = get_all_formations(hand)
    beaters = [f for f in fs
               if f.ftype == current.ftype and formation_beats(f, current)]
    if not beaters:
        if current.ftype == FormationType.SOLO and current.rank == 10:
            zeros = [c for c in hand if c.rank == 0]
            if zeros:
                return Formation(ftype=FormationType.TRIP_UP,
                                cards=[zeros[0]], rank=0, length=1,
                                faction=zeros[0].faction)
        return None
    beaters.sort(key=lambda f: (f.rank, sum(FACTION_RANK.get(c.faction, 0) for c in f.cards)))
    # Going out = always
    for b in beaters:
        if len(hand) - len(b.cards) == 0:
            return b
    # Don't waste 0s
    non_zero = [f for f in beaters if not any(c.rank == 0 for c in f.cards)]
    return non_zero[0] if non_zero else beaters[0]


# ---------------------------------------------------------------------------
# Option 1: Shared Mountain — 2 players, 2 owls
# ---------------------------------------------------------------------------

class SharedMountain:
    """
    2 players, 2 owls, shared trick limit.
    Turn order: P1 → Owl A → P2 → Owl B (each leads in sequence).
    Trick: leader plays, all others follow in order. Highest wins.
    """

    def __init__(self, seed=42, p1_cards=8, p2_cards=8,
                 owl_hand=8, trick_limit=12):
        self.rng = random.Random(seed)
        self.seed = seed

        all_cards = build_full_deck()
        deck = Deck(all_cards)
        deck.shuffle(self.rng)

        self.p1_hand = deck.draw(p1_cards)
        self.p2_hand = deck.draw(p2_cards)

        owl_a_cards = deck.draw(owl_hand)
        owl_b_cards = deck.draw(owl_hand)

        self.owl_a = SmartOwl(name="Owl A", hand=owl_a_cards, hand_limit=owl_hand)
        self.owl_b = SmartOwl(name="Owl B", hand=owl_b_cards, hand_limit=owl_hand)

        self.owl_deck = deck
        self.base_camp: List[Card] = []
        self.trick_limit = trick_limit
        self.tricks = 0

        # Turn order for leading
        self.lead_order = ["p1", "owl_a", "p2", "owl_b"]
        self.lead_idx = 0

        self.player_won = False
        self.log: List[str] = []

    def _log(self, msg):
        self.log.append(msg)

    def play(self) -> dict:
        self._log(f"=== SHARED MOUNTAIN (seed {self.seed}) ===")
        self._log(f"P1: {len(self.p1_hand)} cards, P2: {len(self.p2_hand)} cards")
        self._log(f"Owl A: {len(self.owl_a.hand)}, Owl B: {len(self.owl_b.hand)}")

        while self.tricks < self.trick_limit:
            leader_id = self.lead_order[self.lead_idx % 4]

            # Get leader's formation
            lead_f = self._get_lead(leader_id)
            if lead_f is None:
                self.lead_idx += 1
                continue

            self._remove(leader_id, lead_f.cards)
            self._log(f"T{self.tricks+1}: {leader_id} leads {lead_f}")

            # Check going out
            if self._check_player_out(leader_id):
                return self._stats()

            # Others follow in order
            follow_order = [x for x in self.lead_order if x != leader_id]
            # Reorder so next-in-sequence goes first
            start = (self.lead_order.index(leader_id) + 1) % 4
            follow_order = []
            for i in range(1, 4):
                follow_order.append(self.lead_order[(self.lead_order.index(leader_id) + i) % 4])

            current_best = lead_f
            current_winner = leader_id
            trick_cards = list(lead_f.cards)

            for fid in follow_order:
                resp = self._get_follow(fid, current_best)
                if resp is not None:
                    self._remove(fid, resp.cards)
                    trick_cards.extend(resp.cards)
                    current_best = resp
                    current_winner = fid
                    self._log(f"  {fid} beats with {resp}")

                    if self._check_player_out(fid):
                        return self._stats()
                else:
                    self._log(f"  {fid} passes")

            self._log(f"  → {current_winner} wins trick")
            self.base_camp.extend(trick_cards)
            self.tricks += 1

            # Refill owls
            self.owl_a.refill(self.owl_deck, self.base_camp, self.rng)
            self.owl_b.refill(self.owl_deck, self.base_camp, self.rng)

            # Winner leads next
            self.lead_idx = self.lead_order.index(current_winner)

        # Trick limit reached
        self._log(f"Trick limit reached. P1: {len(self.p1_hand)}, P2: {len(self.p2_hand)}")
        return self._stats()

    def _get_lead(self, who):
        if who == "p1":
            return player_choose_lead(self.p1_hand)
        elif who == "p2":
            return player_choose_lead(self.p2_hand)
        elif who == "owl_a":
            return self.owl_a.choose_lead()
        elif who == "owl_b":
            return self.owl_b.choose_lead()

    def _get_follow(self, who, current):
        if who == "p1":
            return player_choose_follow(self.p1_hand, current)
        elif who == "p2":
            return player_choose_follow(self.p2_hand, current)
        elif who == "owl_a":
            return self.owl_a.choose_follow(current)
        elif who == "owl_b":
            return self.owl_b.choose_follow(current)

    def _remove(self, who, cards):
        if who == "p1":
            for c in cards:
                self.p1_hand.remove(c)
        elif who == "p2":
            for c in cards:
                self.p2_hand.remove(c)
        elif who == "owl_a":
            self.owl_a.remove_cards(cards)
        elif who == "owl_b":
            self.owl_b.remove_cards(cards)

    def _check_player_out(self, who):
        """Check if both players have emptied their hands."""
        p1_out = len(self.p1_hand) == 0
        p2_out = len(self.p2_hand) == 0
        if p1_out and p2_out:
            self.player_won = True
            self._log(f"BOTH PLAYERS SUMMIT!")
            return True
        if p1_out or p2_out:
            who_out = "P1" if p1_out else "P2"
            self._log(f"  {who_out} reaches the summit! Partner continues.")
        return False

    def _stats(self):
        return {
            "won": self.player_won,
            "tricks": self.tricks,
            "p1_left": len(self.p1_hand),
            "p2_left": len(self.p2_hand),
            "total_left": len(self.p1_hand) + len(self.p2_hand),
        }


# ---------------------------------------------------------------------------
# Option 2: Tag Team — 2 players, 1 owl, shared hand
# ---------------------------------------------------------------------------

class TagTeam:
    """
    2 players share one pool of cards but alternate who acts.
    Each player has their OWN hand. On your turn you play from YOUR hand.
    Players can see each other's hands (cooperative).
    One owl opponent.
    Turn order: Active Player → Owl → Other Player → Owl...
    """

    def __init__(self, seed=42, p1_cards=7, p2_cards=7,
                 owl_hand=8, trick_limit=12):
        self.rng = random.Random(seed)
        self.seed = seed

        all_cards = build_full_deck()
        deck = Deck(all_cards)
        deck.shuffle(self.rng)

        self.p1_hand = deck.draw(p1_cards)
        self.p2_hand = deck.draw(p2_cards)

        owl_cards = deck.draw(owl_hand)
        self.owl = SmartOwl(name="Night Owl", hand=owl_cards, hand_limit=owl_hand)

        self.owl_deck = deck
        self.base_camp: List[Card] = []
        self.trick_limit = trick_limit
        self.tricks = 0

        # Alternating: p1, owl, p2, owl
        self.lead_order = ["p1", "owl", "p2", "owl"]
        self.lead_idx = 0

        self.player_won = False
        self.log: List[str] = []

    def _log(self, msg):
        self.log.append(msg)

    def play(self) -> dict:
        self._log(f"=== TAG TEAM (seed {self.seed}) ===")
        self._log(f"P1: {len(self.p1_hand)}, P2: {len(self.p2_hand)}")

        while self.tricks < self.trick_limit:
            leader_id = self.lead_order[self.lead_idx % 4]

            lead_f = self._get_lead(leader_id)
            if lead_f is None:
                self.lead_idx += 1
                continue

            self._remove(leader_id, lead_f.cards)
            self._log(f"T{self.tricks+1}: {leader_id} leads {lead_f}")

            if self._check_win():
                return self._stats()

            # Follower: if player led, owl follows. If owl led, next player follows.
            if leader_id in ("p1", "p2"):
                follower = "owl"
            else:
                # Find which player follows (the one whose turn it is)
                if self.lead_idx % 4 == 1:  # owl after p1
                    follower = "p2"  # p2 gets chance to beat
                else:  # owl after p2
                    follower = "p1"

            resp = self._get_follow(follower, lead_f)
            trick_cards = list(lead_f.cards)
            winner = leader_id

            if resp:
                self._remove(follower, resp.cards)
                trick_cards.extend(resp.cards)
                winner = follower
                self._log(f"  {follower} beats with {resp}")

                if self._check_win():
                    return self._stats()
            else:
                self._log(f"  {follower} passes")

            self._log(f"  → {winner} wins trick")
            self.base_camp.extend(trick_cards)
            self.tricks += 1

            # Refill owl
            self.owl.refill(self.owl_deck, self.base_camp, self.rng)

            # Winner leads next (map to lead_order index)
            if winner == "p1":
                self.lead_idx = 0
            elif winner == "p2":
                self.lead_idx = 2
            else:
                # Owl won — next player in sequence leads... actually owl leads again
                self.lead_idx = self.lead_order.index(leader_id)

        self._log(f"Trick limit. P1: {len(self.p1_hand)}, P2: {len(self.p2_hand)}")
        return self._stats()

    def _get_lead(self, who):
        if who == "p1":
            return player_choose_lead(self.p1_hand) if self.p1_hand else None
        elif who == "p2":
            return player_choose_lead(self.p2_hand) if self.p2_hand else None
        elif who == "owl":
            return self.owl.choose_lead()

    def _get_follow(self, who, current):
        if who == "p1":
            return player_choose_follow(self.p1_hand, current) if self.p1_hand else None
        elif who == "p2":
            return player_choose_follow(self.p2_hand, current) if self.p2_hand else None
        elif who == "owl":
            return self.owl.choose_follow(current)

    def _remove(self, who, cards):
        if who == "p1":
            for c in cards:
                self.p1_hand.remove(c)
        elif who == "p2":
            for c in cards:
                self.p2_hand.remove(c)
        elif who == "owl":
            self.owl.remove_cards(cards)

    def _check_win(self):
        if len(self.p1_hand) == 0 and len(self.p2_hand) == 0:
            self.player_won = True
            self._log("BOTH PLAYERS SUMMIT!")
            return True
        return False

    def _stats(self):
        return {
            "won": self.player_won,
            "tricks": self.tricks,
            "p1_left": len(self.p1_hand),
            "p2_left": len(self.p2_hand),
            "total_left": len(self.p1_hand) + len(self.p2_hand),
        }


# ---------------------------------------------------------------------------
# Batch runners
# ---------------------------------------------------------------------------

def run_shared_mountain(n=1000, seed_start=1, p1_cards=8, p2_cards=8,
                        owl_hand=8, trick_limit=12):
    results = []
    for i in range(n):
        g = SharedMountain(seed=seed_start + i, p1_cards=p1_cards,
                           p2_cards=p2_cards, owl_hand=owl_hand,
                           trick_limit=trick_limit)
        results.append(g.play())
    return _aggregate(results, n, f"Shared Mountain (P:{p1_cards}+{p2_cards}, Owl:{owl_hand}, T≤{trick_limit})")


def run_tag_team(n=1000, seed_start=1, p1_cards=7, p2_cards=7,
                 owl_hand=8, trick_limit=12):
    results = []
    for i in range(n):
        g = TagTeam(seed=seed_start + i, p1_cards=p1_cards,
                    p2_cards=p2_cards, owl_hand=owl_hand,
                    trick_limit=trick_limit)
        results.append(g.play())
    return _aggregate(results, n, f"Tag Team (P:{p1_cards}+{p2_cards}, Owl:{owl_hand}, T≤{trick_limit})")


def _aggregate(results, n, label):
    wins = sum(1 for r in results if r["won"])
    tricks = [r["tricks"] for r in results]
    left = [r["total_left"] for r in results if not r["won"]]
    return {
        "label": label,
        "n": n,
        "wins": wins,
        "win_rate": wins / n,
        "avg_tricks": sum(tricks) / n,
        "avg_left_on_loss": sum(left) / len(left) if left else 0,
    }


def print_result(agg):
    wr = agg["win_rate"]
    marker = "✓" if 0.25 <= wr <= 0.50 else "~" if 0.20 <= wr <= 0.55 else "✗"
    print(f"  {marker} {agg['label']}: {wr:.1%} "
          f"(avg {agg['avg_tricks']:.0f} tricks, "
          f"{agg['avg_left_on_loss']:.1f} cards left on loss)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-n", "--num", type=int, default=1000)
    parser.add_argument("--narrate", type=str, default=None,
                        help="'mountain' or 'tag' to narrate one game")
    args = parser.parse_args()

    if args.narrate == "mountain":
        g = SharedMountain(seed=42)
        stats = g.play()
        for line in g.log:
            print(line)
        print(f"\nResult: {'WIN' if stats['won'] else 'LOSS'}")
    elif args.narrate == "tag":
        g = TagTeam(seed=42)
        stats = g.play()
        for line in g.log:
            print(line)
        print(f"\nResult: {'WIN' if stats['won'] else 'LOSS'}")
    else:
        N = args.num
        print(f"\n{'='*65}")
        print(f"  CO-OP SOLO SIMULATION — {N} games per config")
        print(f"{'='*65}")

        print(f"\n--- SHARED MOUNTAIN (2 players, 2 owls) ---")
        for p_cards in [8]:
            for owl_h in [8, 10]:
                for tl in [10, 12, 14, 16]:
                    agg = run_shared_mountain(N, p1_cards=p_cards, p2_cards=p_cards,
                                              owl_hand=owl_h, trick_limit=tl)
                    print_result(agg)

        print(f"\n--- TAG TEAM (2 players, 1 owl) ---")
        for p_cards in [7]:
            for owl_h in [8, 10]:
                for tl in [10, 12, 14, 16]:
                    agg = run_tag_team(N, p1_cards=p_cards, p2_cards=p_cards,
                                       owl_hand=owl_h, trick_limit=tl)
                    print_result(agg)
