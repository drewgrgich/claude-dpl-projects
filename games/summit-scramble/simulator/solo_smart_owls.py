#!/usr/bin/env python3
"""
Summit Scramble Solo Mode — Smart Owls Variant (Option B).

Each Night Owl holds a small face-up hand (3-4 cards) drawn from its deck.
Owls play optimally from their visible hand, including multi-card formations.
After each trick, owls refill their hand from the deck.

Player can SEE owl hands — creating real strategic planning.
Turn order: Player → Owl A → Owl B (single turn per cycle).
"""

import argparse
import json
import random
from typing import List, Dict, Optional, Tuple
from collections import defaultdict
from dataclasses import dataclass, field

from cards import (
    Card, Deck, build_full_deck, FACTIONS, FACTION_RANK,
    FACTION_ABILITIES, FACTION_NAMES,
)
from game_state import Formation, FormationType, classify_formation, formation_beats


# ---------------------------------------------------------------------------
# Smart Owl
# ---------------------------------------------------------------------------

@dataclass
class SmartOwl:
    name: str
    deck: Deck = field(default_factory=Deck)
    hand: List[Card] = field(default_factory=list)
    hand_size_limit: int = 3
    skip_next: bool = False

    @property
    def exhausted(self) -> bool:
        return len(self.hand) == 0 and self.deck.empty

    @property
    def active_cards(self) -> int:
        return len(self.hand)

    def refill(self):
        """Draw from deck to fill hand up to limit."""
        while len(self.hand) < self.hand_size_limit and not self.deck.empty:
            c = self.deck.draw_one()
            if c:
                self.hand.append(c)

    def remove_cards(self, cards: List[Card]):
        for c in cards:
            if c in self.hand:
                self.hand.remove(c)

    def get_all_formations(self) -> List[Formation]:
        """Get all valid formations from owl hand."""
        formations = []
        by_rank = defaultdict(list)
        for c in self.hand:
            by_rank[c.rank].append(c)

        # Solos
        for c in self.hand:
            formations.append(Formation(
                ftype=FormationType.SOLO, cards=[c],
                rank=c.rank, length=1, faction=c.faction))

        # Surges (2-3 of kind)
        for rank, cards in by_rank.items():
            if len(cards) >= 2:
                formations.append(Formation(
                    ftype=FormationType.SURGE, cards=cards[:2],
                    rank=rank, length=2))
            if len(cards) >= 3:
                formations.append(Formation(
                    ftype=FormationType.SURGE, cards=cards[:3],
                    rank=rank, length=3))

        # Daisy Chains (3+ consecutive)
        sorted_ranks = sorted(by_rank.keys())
        for start_idx in range(len(sorted_ranks)):
            chain_ranks = [sorted_ranks[start_idx]]
            for next_idx in range(start_idx + 1, len(sorted_ranks)):
                if sorted_ranks[next_idx] == chain_ranks[-1] + 1:
                    chain_ranks.append(sorted_ranks[next_idx])
                    if len(chain_ranks) >= 3:
                        chain_cards = [by_rank[r][0] for r in chain_ranks]
                        formations.append(Formation(
                            ftype=FormationType.DAISY_CHAIN,
                            cards=chain_cards, rank=chain_ranks[-1],
                            length=len(chain_ranks)))
                else:
                    break

        return formations

    def choose_lead(self) -> Optional[Formation]:
        """Lead with lowest solo card (conserve high cards for defense)."""
        if not self.hand:
            return None

        formations = self.get_all_formations()
        if not formations:
            return None

        # Prefer multi-card formations (sheds more cards from hand = refill faster)
        # But weight toward lower ranks
        best = None
        best_score = -999

        for f in formations:
            avg_rank = sum(c.rank for c in f.cards) / len(f.cards)
            # Multi-card bonus + low rank preference
            score = len(f.cards) * 2.0 - avg_rank * 1.5
            if score > best_score:
                best_score = score
                best = f

        return best

    def choose_follow(self, current: Formation) -> Optional[Formation]:
        """Beat current formation with cheapest option, or None to pass."""
        formations = self.get_all_formations()

        beaters = [f for f in formations
                   if f.ftype == current.ftype and formation_beats(f, current)]

        if not beaters:
            # Also check: if current is SOLO, owl can only beat with SOLO
            # Trip-Up: if owl has a 0 and current is solo 10
            if (current.ftype == FormationType.SOLO and current.rank == 10):
                zeros = [c for c in self.hand if c.rank == 0]
                if zeros:
                    return Formation(
                        ftype=FormationType.TRIP_UP,
                        cards=[zeros[0]], rank=0, length=1, faction=zeros[0].faction)
            return None

        # Pick cheapest beater (lowest rank)
        beaters.sort(key=lambda f: (f.rank, sum(FACTION_RANK.get(c.faction, 0) for c in f.cards)))
        return beaters[0]


# ---------------------------------------------------------------------------
# Smart Owl Solo Player (same as original)
# ---------------------------------------------------------------------------

@dataclass
class SoloPlayer:
    hand: List[Card] = field(default_factory=list)
    finished: bool = False

    @property
    def hand_size(self) -> int:
        return len(self.hand)

    def remove_cards(self, cards: List[Card]):
        for c in cards:
            self.hand.remove(c)


# ---------------------------------------------------------------------------
# Smart Owl Game State
# ---------------------------------------------------------------------------

class SmartOwlGame:
    """Solo game with smart owls that have visible hands."""

    def __init__(self, seed: int = 42, owl_hand_size: int = 3,
                 player_hand_size: int = 12):
        self.rng = random.Random(seed)
        self.seed = seed
        self.owl_hand_limit = owl_hand_size

        # Build and shuffle deck
        all_cards = build_full_deck()
        deck = Deck(all_cards)
        deck.shuffle(self.rng)

        # Deal player hand
        self.player = SoloPlayer(hand=deck.draw(player_hand_size))

        # Split remaining between owls
        remaining = deck.cards
        mid = len(remaining) // 2
        self.owl_a = SmartOwl(name="Owl A", deck=Deck(remaining[:mid]),
                              hand_size_limit=owl_hand_size)
        self.owl_b = SmartOwl(name="Owl B", deck=Deck(remaining[mid:]),
                              hand_size_limit=owl_hand_size)

        # Owls draw initial hands
        self.owl_a.refill()
        self.owl_b.refill()

        self.base_camp = Deck()
        self.trail = Deck()

        # Trick state
        self.current_formation: Optional[Formation] = None
        self.current_leader: Optional[str] = None
        self.trick_cards: List[Card] = []
        self.passed: set = set()  # who has passed this trick

        # Turn order: Player → Owl A → Owl B
        self.turn_sequence = ["player", "owl_a", "owl_b"]
        self.turn_idx = 0

        # Game state
        self.game_over = False
        self.player_won = False
        self.turn_count = 0

        # Stats
        self.tricks_won_by_player = 0
        self.tricks_won_by_owls = 0
        self.abilities_triggered: Dict[str, int] = defaultdict(int)
        self.trip_ups = 0
        self.strategic_conserves = 0
        self.owl_multi_card_plays = 0
        self.owl_formations_played: Dict[str, int] = defaultdict(int)

        self.log: List[str] = []

    def _log(self, msg: str):
        self.log.append(msg)

    def _ensure_trail(self, needed: int = 1):
        if self.trail.size < needed and self.base_camp.size > 0:
            reshuffled = self.base_camp.cards[:]
            self.base_camp.cards.clear()
            self.trail.add_to_bottom(reshuffled)
            self.trail.shuffle(self.rng)

    # -------------------------------------------------------------------
    # Game loop
    # -------------------------------------------------------------------

    def play_game(self) -> dict:
        self._log(f"=== SMART OWLS (seed {self.seed}, owl hand={self.owl_hand_limit}) ===")
        self._log(f"Player hand: {self.player.hand_size} cards")
        self._log(f"Owl A: {self.owl_a.active_cards} hand + {self.owl_a.deck.size} deck")
        self._log(f"Owl B: {self.owl_b.active_cards} hand + {self.owl_b.deck.size} deck")

        max_iter = 500

        while not self.game_over and max_iter > 0:
            max_iter -= 1
            self.turn_count += 1

            who = self.turn_sequence[self.turn_idx % len(self.turn_sequence)]

            # Skip checks
            if who == "owl_a" and self.owl_a.skip_next:
                self.owl_a.skip_next = False
                self._log(f"Owl A skips (Substitution)")
                self._advance_turn()
                continue
            if who == "owl_b" and self.owl_b.skip_next:
                self.owl_b.skip_next = False
                self._log(f"Owl B skips (Substitution)")
                self._advance_turn()
                continue

            # Skip exhausted entities
            if who == "player" and self.player.finished:
                self._advance_turn()
                continue
            if who == "owl_a" and self.owl_a.exhausted:
                if self.current_formation is not None:
                    self.passed.add("owl_a")
                self._advance_turn()
                self._check_trick_over()
                continue
            if who == "owl_b" and self.owl_b.exhausted:
                if self.current_formation is not None:
                    self.passed.add("owl_b")
                self._advance_turn()
                self._check_trick_over()
                continue

            # If already passed this trick, skip
            if who in self.passed:
                self._advance_turn()
                self._check_trick_over()
                continue

            if self.current_formation is None:
                self._lead(who)
            else:
                self._follow(who)

            self._check_game_over()

        return self._compile_stats()

    def _advance_turn(self):
        self.turn_idx += 1

    def _get_owl(self, who: str) -> SmartOwl:
        return self.owl_a if who == "owl_a" else self.owl_b

    # -------------------------------------------------------------------
    # Leading
    # -------------------------------------------------------------------

    def _lead(self, who: str):
        if who == "player":
            self._player_leads()
        else:
            self._owl_leads(who)

    def _player_leads(self):
        formation = self._choose_player_lead(self.player.hand)
        if formation is None:
            return

        self.player.remove_cards(formation.cards)
        self.current_formation = formation
        self.current_leader = "player"
        self.trick_cards.extend(formation.cards)
        self.passed = set()

        self._log(f"Player leads: {formation}")

        if self.player.hand_size == 0:
            self._player_wins()
            return

        self._advance_turn()

    def _owl_leads(self, who: str):
        owl = self._get_owl(who)
        formation = owl.choose_lead()
        if formation is None:
            self._advance_turn()
            return

        owl.remove_cards(formation.cards)
        self.current_formation = formation
        self.current_leader = who
        self.trick_cards.extend(formation.cards)
        self.passed = set()

        if len(formation.cards) > 1:
            self.owl_multi_card_plays += 1
        self.owl_formations_played[formation.ftype] += 1

        self._log(f"{owl.name} leads: {formation}")
        self._advance_turn()

    # -------------------------------------------------------------------
    # Following
    # -------------------------------------------------------------------

    def _follow(self, who: str):
        if who == "player":
            self._player_follows()
        else:
            self._owl_follows(who)

    def _player_follows(self):
        player = self.player

        # Trip-Up check
        if (self.current_formation.ftype == FormationType.SOLO and
                self.current_formation.rank == 10):
            zeros = [c for c in player.hand if c.rank == 0]
            if zeros and self._should_trip_up():
                z = zeros[0]
                player.hand.remove(z)
                trip_f = Formation(ftype=FormationType.TRIP_UP,
                                   cards=[z], rank=0, length=1, faction=z.faction)
                self.trick_cards.append(z)
                self.trip_ups += 1
                self.current_formation = trip_f
                self.current_leader = "player"
                self._log(f"Player TRIP-UP with {z}!")
                if player.hand_size == 0:
                    self._player_wins()
                    return
                self._advance_turn()
                return

        # Strategic Conserve
        if player.hand_size <= 3 and self.current_leader != "player":
            if self._should_conserve():
                self.strategic_conserves += 1
                self.passed.add("player")
                self._log(f"Player conserves ({player.hand_size} cards)")
                self._advance_turn()
                self._check_trick_over()
                return

        # Try to beat
        play = self._choose_player_follow()
        if play is None:
            self.passed.add("player")
            self._log(f"Player passes")
            self._advance_turn()
            self._check_trick_over()
        else:
            player.remove_cards(play.cards)
            self.trick_cards.extend(play.cards)
            self.current_formation = play
            self.current_leader = "player"
            # Clear passes — new high play means others get another chance
            self.passed = set()
            self._log(f"Player beats with: {play}")

            if player.hand_size == 0:
                self._player_wins()
                return

            self._advance_turn()

    def _owl_follows(self, who: str):
        owl = self._get_owl(who)
        play = owl.choose_follow(self.current_formation)

        if play is None:
            self.passed.add(who)
            self._log(f"{owl.name} passes")
            self._advance_turn()
            self._check_trick_over()
        else:
            owl.remove_cards(play.cards)
            self.trick_cards.extend(play.cards)
            self.current_formation = play
            self.current_leader = who
            self.passed = set()

            if len(play.cards) > 1:
                self.owl_multi_card_plays += 1
            self.owl_formations_played[play.ftype] += 1

            self._log(f"{owl.name} beats with: {play}")
            self._advance_turn()

    # -------------------------------------------------------------------
    # Trick resolution
    # -------------------------------------------------------------------

    def _check_trick_over(self):
        """Check if all non-leader entities have passed."""
        if self.current_formation is None:
            return

        entities = ["player", "owl_a", "owl_b"]
        non_leaders = [e for e in entities if e != self.current_leader]

        all_passed = all(
            e in self.passed or
            (e == "owl_a" and self.owl_a.exhausted) or
            (e == "owl_b" and self.owl_b.exhausted) or
            (e == "player" and self.player.finished)
            for e in non_leaders
        )

        if all_passed:
            self._resolve_trick(self.current_leader, self.current_formation)

    def _resolve_trick(self, winner: str, formation: Formation):
        for c in self.trick_cards:
            self.base_camp.add_to_bottom(c)

        if winner == "player":
            self.tricks_won_by_player += 1
            self._log(f"→ Player wins trick")

            if formation.triggers_power and not self.player.finished:
                ability = self._get_solo_ability(formation)
                if ability:
                    self._execute_solo_ability(ability, formation)
        else:
            self.tricks_won_by_owls += 1
            self._log(f"→ {self._get_owl(winner).name} wins trick")

        # Reset trick
        self.trick_cards = []
        self.current_formation = None
        self.current_leader = None
        self.passed = set()

        # Owls refill their hands
        self.owl_a.refill()
        self.owl_b.refill()

        # Winner leads next
        if winner == "player":
            self.turn_idx = 0
        elif winner == "owl_a":
            self.turn_idx = 1
        elif winner == "owl_b":
            self.turn_idx = 2

    def _player_wins(self):
        self.player.finished = True
        self.player_won = True
        self.game_over = True
        self._log(f"PLAYER REACHES THE SUMMIT!")
        for c in self.trick_cards:
            self.base_camp.add_to_bottom(c)
        self.trick_cards = []
        self.current_formation = None

    # -------------------------------------------------------------------
    # Player AI
    # -------------------------------------------------------------------

    def _choose_player_lead(self, hand: List[Card]) -> Optional[Formation]:
        formations = self._get_all_formations(hand)
        if not formations:
            return None

        # Consider what owls can beat — visible hands!
        owl_a_max = max((c.rank for c in self.owl_a.hand), default=0)
        owl_b_max = max((c.rank for c in self.owl_b.hand), default=0)
        owl_max_rank = max(owl_a_max, owl_b_max)

        scored = []
        for f in formations:
            score = self._score_lead(f, owl_max_rank)
            scored.append((f, score))

        scored.sort(key=lambda x: -x[1])
        return scored[0][0]

    def _score_lead(self, f: Formation, owl_max_rank: int) -> float:
        score = 0.0
        hand_after = self.player.hand_size - len(f.cards)

        if hand_after == 0:
            return 1000.0

        # Multi-card formations: owls CAN counter these now,
        # but it's still good to shed cards
        score += len(f.cards) * 2.5

        # If formation type can't be matched by owls, bonus
        # Check if either owl could form this type
        can_be_beaten = False
        for owl in [self.owl_a, self.owl_b]:
            for of in owl.get_all_formations():
                if of.ftype == f.ftype and formation_beats(of, f):
                    can_be_beaten = True
                    break
            if can_be_beaten:
                break

        if not can_be_beaten:
            score += 8.0  # free trick!

        # Lead LOW cards
        avg_rank = sum(c.rank for c in f.cards) / len(f.cards)
        score -= avg_rank * 1.2

        # Don't lead 0s
        if any(c.rank == 0 for c in f.cards):
            score -= 8.0

        # Lead above owl max if possible (unbeatable solo)
        if f.ftype == FormationType.SOLO and f.rank > owl_max_rank:
            score += 6.0

        # Ability triggers
        if f.triggers_power:
            ability = self._get_solo_ability(f)
            if ability == "streamline":
                score += 5.0
            elif ability == "recalibrate":
                score += 4.0
            elif ability == "rotation":
                score += 2.0

        return score

    def _choose_player_follow(self) -> Optional[Formation]:
        if self.current_formation is None:
            return None

        hand = self.player.hand
        current = self.current_formation

        all_f = self._get_all_formations(hand)
        beaters = [f for f in all_f
                   if f.ftype == current.ftype and formation_beats(f, current)]

        if not beaters:
            return None

        # Pick cheapest beater
        beaters.sort(key=lambda f: (f.rank, sum(FACTION_RANK.get(c.faction, 0) for c in f.cards)))

        hand_after = self.player.hand_size - len(beaters[0].cards)
        if hand_after == 0:
            return beaters[0]

        # Don't waste 0 cards
        non_zero = [f for f in beaters if not any(c.rank == 0 for c in f.cards)]
        if non_zero:
            return non_zero[0]
        return beaters[0]

    def _should_trip_up(self) -> bool:
        return True  # almost always worth it

    def _should_conserve(self) -> bool:
        if self.player.hand_size > 3:
            return False
        if self.owl_a.exhausted and self.owl_b.exhausted:
            return False
        if self.owl_a.exhausted or self.owl_b.exhausted:
            return False  # only one owl, no racing benefit
        if self.current_formation and self.current_formation.rank >= 7:
            return True
        return self.player.hand_size <= 2

    # -------------------------------------------------------------------
    # Formation helpers
    # -------------------------------------------------------------------

    def _get_all_formations(self, hand: List[Card]) -> List[Formation]:
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
        for start_idx in range(len(sorted_ranks)):
            chain_ranks = [sorted_ranks[start_idx]]
            for next_idx in range(start_idx + 1, len(sorted_ranks)):
                if sorted_ranks[next_idx] == chain_ranks[-1] + 1:
                    chain_ranks.append(sorted_ranks[next_idx])
                    if len(chain_ranks) >= 3:
                        chain_cards = [by_rank[r][0] for r in chain_ranks]
                        formations.append(Formation(
                            ftype=FormationType.DAISY_CHAIN,
                            cards=chain_cards, rank=chain_ranks[-1],
                            length=len(chain_ranks)))
                else:
                    break

        return formations

    # -------------------------------------------------------------------
    # Abilities (same as original solo)
    # -------------------------------------------------------------------

    def _get_solo_ability(self, formation: Formation) -> Optional[str]:
        if formation.ftype == FormationType.SOLO:
            return FACTION_ABILITIES.get(formation.faction)
        elif formation.ftype == FormationType.TRIP_UP:
            return None
        elif formation.ftype in (FormationType.SURGE, FormationType.CONFETTI_CANNON):
            best = None
            best_score = -1
            for c in formation.cards:
                ability = FACTION_ABILITIES[c.faction]
                score = {"streamline": 5, "recalibrate": 4, "rotation": 3,
                         "scout": 2, "reclaim": 2, "revelation": 1}.get(ability, 0)
                if score > best_score:
                    best_score = score
                    best = ability
            return best
        elif formation.ftype == FormationType.DAISY_CHAIN:
            top = max(formation.cards, key=lambda c: c.rank)
            return FACTION_ABILITIES.get(top.faction)
        return None

    def _execute_solo_ability(self, ability: str, formation: Formation):
        self.abilities_triggered[ability] += 1

        if ability == "rotation":
            if self.owl_a.active_cards >= self.owl_b.active_cards and not self.owl_a.exhausted:
                self.owl_a.skip_next = True
                self._log(f"  SUBSTITUTION: Owl A skips next turn")
            elif not self.owl_b.exhausted:
                self.owl_b.skip_next = True
                self._log(f"  SUBSTITUTION: Owl B skips next turn")

        elif ability == "scout":
            self._ensure_trail(2)
            if self.trail.size >= 1:
                top = self.trail.peek(min(2, self.trail.size))
                if self.player.hand:
                    worst = min(self.player.hand, key=lambda c: c.rank * 10 + FACTION_RANK[c.faction])
                    best_trail = max(top, key=lambda c: c.rank)
                    if best_trail.rank > worst.rank:
                        self.player.hand.remove(worst)
                        self.trail.remove(best_trail)
                        self.player.hand.append(best_trail)
                        self.trail.add_to_top(worst)
                        self._log(f"  SCOUT: Swap {worst} for {best_trail}")

        elif ability == "streamline":
            if self.player.hand:
                non_zeros = [c for c in self.player.hand if c.rank != 0]
                target = min(non_zeros, key=lambda c: c.rank * 10 + FACTION_RANK[c.faction]) if non_zeros else min(self.player.hand, key=lambda c: c.rank)
                self.player.hand.remove(target)
                self.base_camp.add_to_bottom(target)
                self._log(f"  STREAMLINE: Discard {target}")
                if self.player.hand_size == 0:
                    self._player_wins()

        elif ability == "recalibrate":
            self._ensure_trail(1)
            drawn = self.trail.draw(min(1, self.trail.size))
            if drawn:
                self.player.hand.extend(drawn)
                self._log(f"  RECALIBRATE: Draw {drawn[0]}")
            for _ in range(2):
                if self.player.hand:
                    non_zeros = [c for c in self.player.hand if c.rank != 0]
                    pool = non_zeros if non_zeros else self.player.hand
                    worst = min(pool, key=lambda c: c.rank * 10 + FACTION_RANK[c.faction])
                    self.player.hand.remove(worst)
                    self.base_camp.add_to_bottom(worst)
                    self._log(f"  RECALIBRATE: Discard {worst}")
            if self.player.hand_size == 0:
                self._player_wins()

        elif ability == "revelation":
            # Forecast: peek top of owl decks, may swap
            top_a = self.owl_a.deck.peek(1) if not self.owl_a.deck.empty else []
            top_b = self.owl_b.deck.peek(1) if not self.owl_b.deck.empty else []
            if top_a and top_b:
                a_card, b_card = top_a[0], top_b[0]
                self._log(f"  FORECAST: Owl A deck top={a_card}, Owl B deck top={b_card}")
                if b_card.rank < a_card.rank:
                    self.owl_a.deck.cards[0] = b_card
                    self.owl_b.deck.cards[0] = a_card
                    self._log(f"  FORECAST: Swapped!")

        elif ability == "reclaim":
            if self.player.hand and self.base_camp.cards:
                best_camp = max(self.base_camp.cards,
                               key=lambda c: c.rank * 10 + (5 - FACTION_RANK[c.faction]))
                non_zeros = [c for c in self.player.hand if c.rank != 0]
                worst_hand = min(non_zeros, key=lambda c: c.rank * 10 + FACTION_RANK[c.faction]) if non_zeros else min(self.player.hand, key=lambda c: c.rank)
                if best_camp.rank > worst_hand.rank:
                    self.base_camp.remove(best_camp)
                    self.player.hand.append(best_camp)
                    self.player.hand.remove(worst_hand)
                    self.base_camp.add_to_bottom(worst_hand)
                    self._log(f"  RECLAIM: Take {best_camp}, give {worst_hand}")

    # -------------------------------------------------------------------
    # End conditions
    # -------------------------------------------------------------------

    def _check_game_over(self):
        if self.player.finished:
            self.game_over = True
            self.player_won = True
            return

        if self.owl_a.exhausted and self.owl_b.exhausted:
            if self.current_formation is None:
                self.game_over = True
                self.player_won = False
                self._log(f"Both owls exhausted. Player loses with {self.player.hand_size} cards.")

    # -------------------------------------------------------------------
    # Stats
    # -------------------------------------------------------------------

    def _compile_stats(self) -> dict:
        return {
            "seed": self.seed,
            "owl_hand_size": self.owl_hand_limit,
            "player_won": self.player_won,
            "player_cards_remaining": self.player.hand_size,
            "turns": self.turn_count,
            "tricks_player": self.tricks_won_by_player,
            "tricks_owls": self.tricks_won_by_owls,
            "abilities": dict(self.abilities_triggered),
            "trip_ups": self.trip_ups,
            "conserves": self.strategic_conserves,
            "owl_multi_card_plays": self.owl_multi_card_plays,
            "owl_formations": dict(self.owl_formations_played),
        }


# ---------------------------------------------------------------------------
# Batch runner
# ---------------------------------------------------------------------------

def run_batch(num_games: int, seed_start: int = 1,
              owl_hand_size: int = 3, player_hand_size: int = 12) -> dict:
    all_stats = []
    for i in range(num_games):
        g = SmartOwlGame(seed=seed_start + i, owl_hand_size=owl_hand_size,
                         player_hand_size=player_hand_size)
        stats = g.play_game()
        all_stats.append(stats)

    wins = sum(1 for s in all_stats if s["player_won"])
    n = len(all_stats)

    turns = [s["turns"] for s in all_stats]
    cards_left = [s["player_cards_remaining"] for s in all_stats if not s["player_won"]]
    tricks_p = [s["tricks_player"] for s in all_stats]
    tricks_o = [s["tricks_owls"] for s in all_stats]
    trip_ups = [s["trip_ups"] for s in all_stats]
    conserves = [s["conserves"] for s in all_stats]
    multi = [s["owl_multi_card_plays"] for s in all_stats]

    total_abilities = defaultdict(int)
    total_owl_f = defaultdict(int)
    for s in all_stats:
        for k, v in s["abilities"].items():
            total_abilities[k] += v
        for k, v in s["owl_formations"].items():
            total_owl_f[k] += v

    return {
        "n": n,
        "owl_hand_size": owl_hand_size,
        "player_hand_size": player_hand_size,
        "win_rate": wins / n,
        "wins": wins,
        "avg_turns": sum(turns) / n,
        "min_turns": min(turns),
        "max_turns": max(turns),
        "avg_cards_left": sum(cards_left) / len(cards_left) if cards_left else 0,
        "avg_tricks_player": sum(tricks_p) / n,
        "avg_tricks_owls": sum(tricks_o) / n,
        "avg_trip_ups": sum(trip_ups) / n,
        "avg_conserves": sum(conserves) / n,
        "avg_owl_multi": sum(multi) / n,
        "owl_formations": dict(total_owl_f),
        "abilities": dict(sorted(total_abilities.items())),
    }


def print_report(agg: dict):
    print(f"\n{'='*60}")
    print(f"  SMART OWLS — hand={agg['owl_hand_size']}, player={agg['player_hand_size']} cards")
    print(f"  {agg['n']} games")
    print(f"{'='*60}")

    print(f"\n--- WIN RATE ---")
    print(f"  Player wins: {agg['win_rate']:.1%} ({agg['wins']}/{agg['n']})")
    bar = "█" * int(agg["win_rate"] * 50)
    print(f"  {bar}")

    print(f"\n--- GAME LENGTH ---")
    print(f"  Avg turns: {agg['avg_turns']:.1f} (range: {agg['min_turns']}–{agg['max_turns']})")

    print(f"\n--- TRICKS ---")
    print(f"  Player avg: {agg['avg_tricks_player']:.1f}")
    print(f"  Owls avg:   {agg['avg_tricks_owls']:.1f}")

    if agg["avg_cards_left"] > 0:
        print(f"\n--- ON LOSS ---")
        print(f"  Avg cards remaining: {agg['avg_cards_left']:.1f}")

    print(f"\n--- OWL PLAY QUALITY ---")
    print(f"  Multi-card plays: {agg['avg_owl_multi']:.1f}/game")
    for ftype, count in sorted(agg["owl_formations"].items()):
        print(f"    {ftype:20s}: {count:5d} ({count/agg['n']:.1f}/game)")

    print(f"\n--- PLAYER SPECIAL ---")
    print(f"  Trip-Ups: {agg['avg_trip_ups']:.2f}/game")
    print(f"  Conserves: {agg['avg_conserves']:.2f}/game")

    print(f"\n--- ABILITIES ---")
    for ab, count in agg["abilities"].items():
        print(f"  {ab:15s}: {count/agg['n']:.1f}/game")

    # Assessment
    wr = agg["win_rate"]
    print(f"\n--- ASSESSMENT ---")
    if 0.30 <= wr <= 0.50:
        print(f"  ✓ Win rate {wr:.0%} is in the sweet spot for a solo challenge.")
    elif wr < 0.30:
        print(f"  ✗ Win rate {wr:.0%} may be frustratingly hard.")
    elif wr > 0.70:
        print(f"  ✗ Win rate {wr:.0%} is too easy for a challenge mode.")
    else:
        print(f"  ~ Win rate {wr:.0%} is reasonable but could be tighter.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Smart Owls Solo Variant")
    parser.add_argument("-n", "--num-games", type=int, default=1000)
    parser.add_argument("--owl-hand", type=int, default=3,
                        help="Owl hand size (3 or 4)")
    parser.add_argument("--player-hand", type=int, default=12,
                        help="Player starting hand size")
    parser.add_argument("--narrate", action="store_true",
                        help="Print narration for first game")
    args = parser.parse_args()

    if args.narrate:
        g = SmartOwlGame(seed=42, owl_hand_size=args.owl_hand,
                         player_hand_size=args.player_hand)
        stats = g.play_game()
        for line in g.log:
            print(line)
        print(f"\nResult: {'WIN' if stats['player_won'] else 'LOSS'}")
        print(f"Turns: {stats['turns']}")
    else:
        agg = run_batch(args.num_games, owl_hand_size=args.owl_hand,
                        player_hand_size=args.player_hand)
        print_report(agg)
