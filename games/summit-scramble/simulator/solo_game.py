#!/usr/bin/env python3
"""
Summit Scramble Solo Mode — The Night Shift.

Player vs. Two Night Owls (automated flip decks).
Turn order: Player → Owl A → Player → Owl B.

Win condition: Player empties their hand before both Owls exhaust their decks.
Loss condition: Both Owl decks are empty and player still has cards.
"""

import argparse
import json
import os
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
# Solo-specific structures
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


@dataclass
class NightOwl:
    name: str
    deck: Deck = field(default_factory=Deck)
    skip_next: bool = False  # Red ability: The Substitution

    @property
    def exhausted(self) -> bool:
        return self.deck.empty

    def flip(self) -> Optional[Card]:
        return self.deck.draw_one()


# ---------------------------------------------------------------------------
# Solo Game State
# ---------------------------------------------------------------------------

class SoloGameState:
    """State machine for solo Night Shift mode."""

    def __init__(self, seed: int = 42, iron_climb: bool = False):
        self.rng = random.Random(seed)
        self.seed = seed
        self.iron_climb = iron_climb

        # Build and shuffle deck
        all_cards = build_full_deck()
        deck = Deck(all_cards)
        deck.shuffle(self.rng)

        # Deal: player gets 12, rest split between owls
        self.player = SoloPlayer(hand=deck.draw(12))
        remaining = deck.cards
        mid = len(remaining) // 2
        self.owl_a = NightOwl(name="Owl A", deck=Deck(remaining[:mid]))
        self.owl_b = NightOwl(name="Owl B", deck=Deck(remaining[mid:]))

        self.base_camp = Deck()
        self.trail = Deck()  # not used much in solo, but abilities reference it

        # Trick state
        self.current_formation: Optional[Formation] = None
        self.current_leader: Optional[str] = None  # "player", "owl_a", "owl_b"
        self.trick_cards: List[Card] = []

        # Turn order: Player, Owl A, Player, Owl B (repeating)
        self.turn_sequence = ["player", "owl_a", "player", "owl_b"]
        self.turn_idx = 0  # who leads first trick

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
        self.cards_played_by_player = 0
        self.owl_cards_flipped = 0

        # Logging
        self.log: List[str] = []

    def _log(self, msg: str):
        self.log.append(msg)

    # -------------------------------------------------------------------
    # Trail / Base Camp
    # -------------------------------------------------------------------

    def _ensure_trail(self, needed: int = 1):
        """Reshuffle base camp into trail if needed."""
        if self.trail.size < needed and self.base_camp.size > 0:
            reshuffled = self.base_camp.cards[:]
            self.base_camp.cards.clear()
            self.trail.add_to_bottom(reshuffled)
            self.trail.shuffle(self.rng)
            self._log(f"Reshuffled {len(reshuffled)} cards from Base Camp into Trail.")

    # -------------------------------------------------------------------
    # Game loop
    # -------------------------------------------------------------------

    def play_game(self) -> dict:
        """Run the complete solo game. Returns stats."""
        self._log(f"=== NIGHT SHIFT (seed {self.seed}) ===")
        self._log(f"Player hand: {len(self.player.hand)} cards")
        self._log(f"Owl A deck: {self.owl_a.deck.size} | Owl B deck: {self.owl_b.deck.size}")

        max_iterations = 500  # safety valve

        while not self.game_over and max_iterations > 0:
            max_iterations -= 1
            self.turn_count += 1

            who = self._current_turn()

            # Skip check for owls (Red ability: The Substitution)
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

            # Check if current entity can act
            if who == "player" and self.player.finished:
                self._advance_turn()
                continue
            if who == "owl_a" and self.owl_a.exhausted:
                self._advance_turn()
                continue
            if who == "owl_b" and self.owl_b.exhausted:
                self._advance_turn()
                continue

            # No trick in progress? Current entity leads.
            if self.current_formation is None:
                self._lead(who)
            else:
                self._follow(who)

            # Check end conditions
            self._check_game_over()

        return self._compile_stats()

    def _current_turn(self) -> str:
        return self.turn_sequence[self.turn_idx % 4]

    def _advance_turn(self):
        self.turn_idx += 1

    def _get_owl(self, who: str) -> NightOwl:
        return self.owl_a if who == "owl_a" else self.owl_b

    def _other_owl(self, who: str) -> NightOwl:
        return self.owl_b if who == "owl_a" else self.owl_a

    # -------------------------------------------------------------------
    # Leading
    # -------------------------------------------------------------------

    def _lead(self, who: str):
        """Entity leads a new trick."""
        if who == "player":
            self._player_leads()
        else:
            self._owl_leads(who)

    def _player_leads(self):
        """Player chooses a formation to lead with."""
        player = self.player
        hand = player.hand

        # Strategy: lead with lowest possible card/formation to conserve
        # high cards for beating owls

        # Strategic Conserve: when 3 or fewer cards, consider passing
        # (but player MUST lead if it's their turn to lead — they can't pass a lead)
        # Actually, re-reading rules: Strategic Conserve only applies to following, not leading.
        # Player must lead if it's their turn.

        formation = self._choose_player_lead(hand)
        if formation is None:
            # Edge case: empty hand (shouldn't happen if we check correctly)
            return

        player.remove_cards(formation.cards)
        self.current_formation = formation
        self.current_leader = "player"
        self.trick_cards.extend(formation.cards)
        self.cards_played_by_player += len(formation.cards)

        self._log(f"Player leads: {formation}")

        # Check if player went out
        if player.hand_size == 0:
            self._player_wins_going_out()
            return

        self._advance_turn()

    def _owl_leads(self, who: str):
        """Owl flips its top card as lead."""
        owl = self._get_owl(who)
        card = owl.flip()
        if card is None:
            self._advance_turn()
            return

        self.owl_cards_flipped += 1
        formation = Formation(
            ftype=FormationType.SOLO,
            cards=[card], rank=card.rank, length=1, faction=card.faction,
        )
        self.current_formation = formation
        self.current_leader = who
        self.trick_cards.append(card)

        self._log(f"{owl.name} leads: {card}")
        self._advance_turn()

    # -------------------------------------------------------------------
    # Following
    # -------------------------------------------------------------------

    def _follow(self, who: str):
        """Entity follows on current trick."""
        if who == "player":
            self._player_follows()
        else:
            self._owl_follows(who)

    def _player_follows(self):
        """Player decides to beat current formation or pass."""
        player = self.player

        # Trip-Up check: if current is solo 10, player can play a 0
        if (self.current_formation.ftype == FormationType.SOLO and
            self.current_formation.rank == 10):
            zeros = [c for c in player.hand if c.rank == 0]
            if zeros:
                # Use Trip-Up if it's strategically good
                if self._should_trip_up():
                    z = zeros[0]
                    player.hand.remove(z)
                    trip_formation = Formation(
                        ftype=FormationType.TRIP_UP,
                        cards=[z], rank=0, length=1, faction=z.faction,
                    )
                    self.trick_cards.append(z)
                    self.cards_played_by_player += 1
                    self.trip_ups += 1
                    self._log(f"Player TRIP-UP with {z}!")
                    self._resolve_trick("player", trip_formation)
                    return

        # Strategic Conserve: 3 or fewer cards, pass to let owls burn each other
        if player.hand_size <= 3 and self.current_leader != "player":
            # Only conserve if there's a real benefit — owls will fight each other
            if self._should_conserve():
                self.strategic_conserves += 1
                self._log(f"Player conserves (Strategic Conserve, {player.hand_size} cards)")
                self._advance_turn()
                return

        # Try to beat current formation
        play = self._choose_player_follow()
        if play is None:
            # Pass
            self._log(f"Player passes")
            self._player_passes()
        else:
            player.remove_cards(play.cards)
            self.trick_cards.extend(play.cards)
            self.cards_played_by_player += len(play.cards)
            self.current_formation = play
            self.current_leader = "player"
            self._log(f"Player beats with: {play}")

            if player.hand_size == 0:
                self._player_wins_going_out()
                return

            self._advance_turn()

    def _player_passes(self):
        """Player passes on trick. Check if trick resolves."""
        # If player passes and an owl is leading, the owl wins the trick
        # But the other owl might still follow...
        # Actually, the turn structure is: Player → Owl A → Player → Owl B
        # If player passes, the trick continues to the next entity
        self._advance_turn()

        # Run remaining followers in this trick
        self._resolve_remaining_followers()

    def _owl_follows(self, who: str):
        """Owl flips and tries to beat current formation."""
        owl = self._get_owl(who)

        if owl.exhausted:
            self._advance_turn()
            return

        if self.iron_climb:
            # Iron Climb: owl keeps flipping until it wins or exhausts
            self._owl_iron_climb_follow(owl, who)
        else:
            # Normal: owl flips one card
            card = owl.flip()
            if card is None:
                self._advance_turn()
                return

            self.owl_cards_flipped += 1

            # Check if this card beats current
            if card.rank > self.current_formation.rank:
                # Owl takes the lead
                new_formation = Formation(
                    ftype=FormationType.SOLO,
                    cards=[card], rank=card.rank, length=1, faction=card.faction,
                )
                self.current_formation = new_formation
                self.current_leader = who
                self.trick_cards.append(card)
                self._log(f"{owl.name} beats with {card}")
            elif (card.rank == self.current_formation.rank and
                  self.current_formation.ftype == FormationType.SOLO and
                  FACTION_RANK[card.faction] < FACTION_RANK.get(self.current_formation.faction, 99)):
                # Tie-break by faction
                new_formation = Formation(
                    ftype=FormationType.SOLO,
                    cards=[card], rank=card.rank, length=1, faction=card.faction,
                )
                self.current_formation = new_formation
                self.current_leader = who
                self.trick_cards.append(card)
                self._log(f"{owl.name} beats with {card} (faction tie-break)")
            else:
                # Owl rests — card goes to base camp
                self.base_camp.add_to_bottom(card)
                self._log(f"{owl.name} rests ({card} → Base Camp)")

            self._advance_turn()

    def _owl_iron_climb_follow(self, owl: NightOwl, who: str):
        """Iron Climb: owl keeps flipping until it wins or exhausts."""
        while not owl.exhausted:
            card = owl.flip()
            if card is None:
                break
            self.owl_cards_flipped += 1

            if card.rank > self.current_formation.rank:
                new_formation = Formation(
                    ftype=FormationType.SOLO,
                    cards=[card], rank=card.rank, length=1, faction=card.faction,
                )
                self.current_formation = new_formation
                self.current_leader = who
                self.trick_cards.append(card)
                self._log(f"{owl.name} beats with {card} (Iron Climb)")
                self._advance_turn()
                return
            elif (card.rank == self.current_formation.rank and
                  self.current_formation.ftype == FormationType.SOLO and
                  FACTION_RANK[card.faction] < FACTION_RANK.get(self.current_formation.faction, 99)):
                new_formation = Formation(
                    ftype=FormationType.SOLO,
                    cards=[card], rank=card.rank, length=1, faction=card.faction,
                )
                self.current_formation = new_formation
                self.current_leader = who
                self.trick_cards.append(card)
                self._log(f"{owl.name} beats with {card} (faction, Iron Climb)")
                self._advance_turn()
                return
            else:
                self.base_camp.add_to_bottom(card)
                self._log(f"{owl.name} flips {card}, can't beat — continues (Iron Climb)")

        # Exhausted without winning
        self._log(f"{owl.name} exhausted during Iron Climb")
        self._advance_turn()

    # -------------------------------------------------------------------
    # Trick resolution
    # -------------------------------------------------------------------

    def _resolve_remaining_followers(self):
        """After player passes, let remaining entities follow."""
        # Run through remaining turns in the cycle for this trick
        safety = 20
        while safety > 0:
            safety -= 1
            who = self._current_turn()

            # Skip checks
            if who == "owl_a" and self.owl_a.skip_next:
                self.owl_a.skip_next = False
                self._advance_turn()
                continue
            if who == "owl_b" and self.owl_b.skip_next:
                self.owl_b.skip_next = False
                self._advance_turn()
                continue

            if who == "player":
                # Back to player's turn — if player already passed this trick,
                # and an owl is leading, trick is over
                if self.current_leader != "player":
                    # Check if player wants to Trip-Up
                    if (self.current_formation.ftype == FormationType.SOLO and
                        self.current_formation.rank == 10):
                        zeros = [c for c in self.player.hand if c.rank == 0]
                        if zeros and self._should_trip_up():
                            z = zeros[0]
                            self.player.hand.remove(z)
                            trip_f = Formation(
                                ftype=FormationType.TRIP_UP,
                                cards=[z], rank=0, length=1, faction=z.faction,
                            )
                            self.trick_cards.append(z)
                            self.cards_played_by_player += 1
                            self.trip_ups += 1
                            self._log(f"Player TRIP-UP with {z}!")
                            self._resolve_trick("player", trip_f)
                            return

                    # Check if player wants to beat it now (second chance)
                    if self.player.hand_size <= 3 and self._should_conserve():
                        # Still conserving
                        self._resolve_trick(self.current_leader, self.current_formation)
                        return
                    else:
                        # Try to beat
                        play = self._choose_player_follow()
                        if play:
                            self.player.remove_cards(play.cards)
                            self.trick_cards.extend(play.cards)
                            self.cards_played_by_player += len(play.cards)
                            self.current_formation = play
                            self.current_leader = "player"
                            self._log(f"Player beats with: {play}")
                            if self.player.hand_size == 0:
                                self._player_wins_going_out()
                                return
                            self._advance_turn()
                            continue
                        else:
                            # Can't beat — owl wins trick
                            self._resolve_trick(self.current_leader, self.current_formation)
                            return
                else:
                    # Player is leading — trick resolved
                    self._resolve_trick("player", self.current_formation)
                    return

            elif who in ("owl_a", "owl_b"):
                owl = self._get_owl(who)
                if owl.exhausted:
                    self._advance_turn()
                    # If both owls exhausted and player hasn't won, resolve
                    if self.owl_a.exhausted and self.owl_b.exhausted:
                        self._resolve_trick(self.current_leader, self.current_formation)
                        return
                    continue

                if who == self.current_leader:
                    # This owl is already winning — no one left to beat it
                    # Check if the other owl still needs to act
                    other_who = "owl_b" if who == "owl_a" else "owl_a"
                    other_owl = self._get_owl(other_who)
                    if other_owl.exhausted:
                        self._resolve_trick(who, self.current_formation)
                        return
                    self._advance_turn()
                    continue

                self._owl_follows(who)
                continue

        # Safety valve
        self._resolve_trick(self.current_leader, self.current_formation)

    def _resolve_trick(self, winner: str, formation: Formation):
        """Resolve a completed trick."""
        # All trick cards to base camp
        for c in self.trick_cards:
            self.base_camp.add_to_bottom(c)

        if winner == "player":
            self.tricks_won_by_player += 1
            self._log(f"→ Player wins trick")

            # Power check (rank 6+)
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

        # Winner leads next — adjust turn index
        if winner == "player":
            # Player leads next
            self.turn_idx = 0
        elif winner == "owl_a":
            self.turn_idx = 1
        elif winner == "owl_b":
            self.turn_idx = 3

    def _player_wins_going_out(self):
        """Player empties hand — wins!"""
        self.player.finished = True
        self.player_won = True
        self.game_over = True
        self._log(f"PLAYER REACHES THE SUMMIT!")
        # Clean up trick cards
        for c in self.trick_cards:
            self.base_camp.add_to_bottom(c)
        self.trick_cards = []
        self.current_formation = None

    # -------------------------------------------------------------------
    # Player AI (heuristic)
    # -------------------------------------------------------------------

    def _choose_player_lead(self, hand: List[Card]) -> Optional[Formation]:
        """Choose formation to lead with. Strategy: lead low, save high."""
        # Prefer multi-card formations to shed faster
        formations = self._get_all_formations(hand)
        if not formations:
            return None

        scored = []
        for f in formations:
            score = self._score_lead(f)
            scored.append((f, score))

        scored.sort(key=lambda x: -x[1])
        return scored[0][0]

    def _score_lead(self, f: Formation) -> float:
        """Score a formation for leading in solo."""
        score = 0.0
        hand_after = self.player.hand_size - len(f.cards)

        # Going out = always
        if hand_after == 0:
            return 1000.0

        # Multi-card formations shed more
        score += len(f.cards) * 3.0

        # Lead LOW cards (save high for beating owls)
        avg_rank = sum(c.rank for c in f.cards) / len(f.cards)
        score -= avg_rank * 1.5

        # Don't lead with 0s (save for Trip-Up)
        if any(c.rank == 0 for c in f.cards):
            score -= 8.0

        # Ability triggers are valuable
        if f.triggers_power:
            ability = self._get_solo_ability(f)
            if ability == "streamline":
                score += 5.0  # extra card shed
            elif ability == "recalibrate":
                score += 4.0  # net -1
            elif ability == "rotation":
                score += 2.0  # substitution in solo
            elif ability == "scout":
                score += 1.0

        # Surges and chains are hard for owls to beat
        if f.ftype in (FormationType.SURGE, FormationType.DAISY_CHAIN):
            score += 4.0

        # Cannon = shed 4 cards!
        if f.ftype == FormationType.CONFETTI_CANNON:
            score += 12.0
            if hand_after <= 3:
                score += 8.0

        return score

    def _choose_player_follow(self) -> Optional[Formation]:
        """Choose formation to beat current trick, or None to pass."""
        if self.current_formation is None:
            return None

        hand = self.player.hand
        current = self.current_formation

        # For solo, owls only play solos — so we usually need a higher solo
        # But player could also lead chains/surges, so check type
        if current.ftype == FormationType.SOLO:
            # Find cheapest card that beats it
            beaters = []
            for c in hand:
                f = Formation(ftype=FormationType.SOLO, cards=[c],
                              rank=c.rank, length=1, faction=c.faction)
                if formation_beats(f, current):
                    beaters.append((c, f))

            if not beaters:
                return None

            # Pick cheapest beater (lowest rank that still wins)
            beaters.sort(key=lambda x: (x[0].rank, FACTION_RANK[x[0].faction]))

            hand_after = self.player.hand_size - 1
            # Going out = always do it
            if hand_after == 0:
                return beaters[0][1]

            # Don't waste 0 cards on following (save for Trip-Up)
            non_zero = [(c, f) for c, f in beaters if c.rank != 0]
            if non_zero:
                return non_zero[0][1]
            return beaters[0][1]

        elif current.ftype in (FormationType.SURGE, FormationType.DAISY_CHAIN,
                                FormationType.CONFETTI_CANNON):
            # These would only happen if player led these types
            # Find matching formations that beat
            all_f = self._get_all_formations(hand)
            matching = [f for f in all_f
                       if f.ftype == current.ftype and formation_beats(f, current)]
            if matching:
                # Pick lowest
                matching.sort(key=lambda f: f.rank)
                return matching[0]

        return None

    def _should_trip_up(self) -> bool:
        """Should player use Trip-Up on a solo 10?"""
        # Almost always yes in solo — seize initiative
        # Unless we're very close to going out and need to conserve the card
        if self.player.hand_size <= 2:
            # Holding a 0 when you have 2 cards — Trip-Up seizes lead AND sheds a card
            return True
        if self.player.hand_size <= 5:
            return True  # worth it for initiative
        # With larger hands, still usually worth it
        return True

    def _should_conserve(self) -> bool:
        """Should player use Strategic Conserve?"""
        if self.player.hand_size > 3:
            return False
        # Conserve if both owls have cards left to burn each other
        if self.owl_a.exhausted or self.owl_b.exhausted:
            return False  # only one owl left, conserving doesn't help
        # Conserve if the leading formation is hard to beat cheaply
        if self.current_formation and self.current_formation.rank >= 7:
            return True  # don't waste high cards
        return self.player.hand_size <= 2  # always conserve at 1-2 cards

    # -------------------------------------------------------------------
    # Formation helpers
    # -------------------------------------------------------------------

    def _get_all_formations(self, hand: List[Card]) -> List[Formation]:
        """Get all valid formations from hand."""
        formations = []
        by_rank = defaultdict(list)
        for c in hand:
            by_rank[c.rank].append(c)

        # Solos
        for c in hand:
            formations.append(Formation(
                ftype=FormationType.SOLO, cards=[c],
                rank=c.rank, length=1, faction=c.faction))

        # Surges
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

        # Daisy Chains
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
    # Solo faction abilities
    # -------------------------------------------------------------------

    def _get_solo_ability(self, formation: Formation) -> Optional[str]:
        """Get ability name, with solo variants for Red and Blue."""
        if formation.ftype == FormationType.SOLO:
            return FACTION_ABILITIES.get(formation.faction)
        elif formation.ftype == FormationType.TRIP_UP:
            return None
        elif formation.ftype in (FormationType.SURGE, FormationType.CONFETTI_CANNON):
            # Choose best ability from factions in formation
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
        """Execute a faction ability in solo mode."""
        self.abilities_triggered[ability] += 1

        if ability == "rotation":
            # Solo variant: The Substitution — skip one owl's next turn
            # Pick the owl with more cards (bigger threat)
            if self.owl_a.deck.size >= self.owl_b.deck.size and not self.owl_a.exhausted:
                self.owl_a.skip_next = True
                self._log(f"  SUBSTITUTION: Owl A skips next turn")
            elif not self.owl_b.exhausted:
                self.owl_b.skip_next = True
                self._log(f"  SUBSTITUTION: Owl B skips next turn")

        elif ability == "scout":
            # Look at top 2 of trail, swap 1
            self._ensure_trail(2)
            if self.trail.size >= 1:
                top = self.trail.peek(min(2, self.trail.size))
                # Swap worst hand card for best trail card
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
            # Discard 1 card
            if self.player.hand:
                worst = min(self.player.hand, key=lambda c: c.rank * 10 + FACTION_RANK[c.faction])
                # Don't discard 0s (Trip-Up value)
                non_zeros = [c for c in self.player.hand if c.rank != 0]
                if non_zeros:
                    worst = min(non_zeros, key=lambda c: c.rank * 10 + FACTION_RANK[c.faction])
                self.player.hand.remove(worst)
                self.base_camp.add_to_bottom(worst)
                self._log(f"  STREAMLINE: Discard {worst}")
                # Check ability finish
                if self.player.hand_size == 0:
                    self._player_wins_going_out()

        elif ability == "recalibrate":
            # Draw 1 from trail, discard 2
            self._ensure_trail(1)
            drawn = self.trail.draw(min(1, self.trail.size))
            if drawn:
                self.player.hand.extend(drawn)
                self._log(f"  RECALIBRATE: Draw {drawn[0]}")
            # Discard 2 worst
            for _ in range(2):
                if self.player.hand:
                    non_zeros = [c for c in self.player.hand if c.rank != 0]
                    pool = non_zeros if non_zeros else self.player.hand
                    worst = min(pool, key=lambda c: c.rank * 10 + FACTION_RANK[c.faction])
                    self.player.hand.remove(worst)
                    self.base_camp.add_to_bottom(worst)
                    self._log(f"  RECALIBRATE: Discard {worst}")
            if self.player.hand_size == 0:
                self._player_wins_going_out()

        elif ability == "revelation":
            # Solo variant: The Forecast — peek top of each owl deck, may swap
            top_a = self.owl_a.deck.peek(1) if not self.owl_a.exhausted else []
            top_b = self.owl_b.deck.peek(1) if not self.owl_b.exhausted else []
            if top_a and top_b:
                a_card = top_a[0]
                b_card = top_b[0]
                # Swap if it helps: put high card on the owl that acts sooner
                # (so we face it when we have better cards)
                # Actually, put LOW card on next-to-act owl so it's easier to beat
                self._log(f"  FORECAST: Owl A top={a_card}, Owl B top={b_card}")
                # Simple heuristic: swap if B's card is lower (put easier card first)
                if b_card.rank < a_card.rank:
                    self.owl_a.deck.cards[0] = b_card
                    self.owl_b.deck.cards[0] = a_card
                    self._log(f"  FORECAST: Swapped!")

        elif ability == "reclaim":
            # Swap 1 from hand with base camp
            if self.player.hand and self.base_camp.cards:
                best_camp = max(self.base_camp.cards,
                               key=lambda c: c.rank * 10 + (5 - FACTION_RANK[c.faction]))
                worst_hand = min(self.player.hand,
                                key=lambda c: c.rank * 10 + FACTION_RANK[c.faction])
                # Don't swap 0s away
                non_zeros = [c for c in self.player.hand if c.rank != 0]
                if non_zeros:
                    worst_hand = min(non_zeros, key=lambda c: c.rank * 10 + FACTION_RANK[c.faction])
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
        """Check if game is over."""
        if self.player.finished:
            self.game_over = True
            self.player_won = True
            return

        # If both owls exhausted and player still has cards
        if self.owl_a.exhausted and self.owl_b.exhausted:
            # Player loses — but finish current trick first
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
            "iron_climb": self.iron_climb,
            "player_won": self.player_won,
            "player_cards_remaining": self.player.hand_size,
            "turns": self.turn_count,
            "tricks_won_player": self.tricks_won_by_player,
            "tricks_won_owls": self.tricks_won_by_owls,
            "abilities_triggered": dict(self.abilities_triggered),
            "trip_ups": self.trip_ups,
            "strategic_conserves": self.strategic_conserves,
            "cards_played_by_player": self.cards_played_by_player,
            "owl_cards_flipped": self.owl_cards_flipped,
            "owl_a_remaining": self.owl_a.deck.size,
            "owl_b_remaining": self.owl_b.deck.size,
        }


# ---------------------------------------------------------------------------
# Batch runner
# ---------------------------------------------------------------------------

def run_solo_batch(num_games: int, seed_start: int = 1,
                   iron_climb: bool = False) -> dict:
    """Run N solo games and aggregate."""
    all_stats = []
    for i in range(num_games):
        game = SoloGameState(seed=seed_start + i, iron_climb=iron_climb)
        stats = game.play_game()
        all_stats.append(stats)

    # Aggregate
    wins = sum(1 for s in all_stats if s["player_won"])
    n = len(all_stats)

    turns = [s["turns"] for s in all_stats]
    cards_remaining = [s["player_cards_remaining"] for s in all_stats if not s["player_won"]]
    trip_ups = [s["trip_ups"] for s in all_stats]
    conserves = [s["strategic_conserves"] for s in all_stats]
    tricks_player = [s["tricks_won_player"] for s in all_stats]
    tricks_owls = [s["tricks_won_owls"] for s in all_stats]

    total_abilities = defaultdict(int)
    for s in all_stats:
        for ab, count in s["abilities_triggered"].items():
            total_abilities[ab] += count

    # Win stats by presence of 0 in opening hand
    # (rules claim: "Drawing one in your opening hand significantly increases your win probability")
    # We can check this by looking at trip_up usage as a proxy

    return {
        "num_games": n,
        "iron_climb": iron_climb,
        "win_rate": wins / n,
        "wins": wins,
        "losses": n - wins,
        "avg_turns": sum(turns) / n,
        "min_turns": min(turns),
        "max_turns": max(turns),
        "avg_cards_remaining_on_loss": sum(cards_remaining) / len(cards_remaining) if cards_remaining else 0,
        "max_cards_remaining_on_loss": max(cards_remaining) if cards_remaining else 0,
        "avg_trip_ups": sum(trip_ups) / n,
        "games_with_trip_up": sum(1 for t in trip_ups if t > 0) / n * 100,
        "avg_strategic_conserves": sum(conserves) / n,
        "avg_tricks_player": sum(tricks_player) / n,
        "avg_tricks_owls": sum(tricks_owls) / n,
        "ability_usage": dict(sorted(total_abilities.items())),
    }


def print_solo_report(agg: dict):
    """Print solo mode report."""
    mode = "IRON CLIMB" if agg["iron_climb"] else "STANDARD"
    n = agg["num_games"]

    print(f"\n{'='*60}")
    print(f"  SOLO MODE: THE NIGHT SHIFT ({mode})")
    print(f"  {n} games")
    print(f"{'='*60}")

    print(f"\n--- WIN RATE ---")
    print(f"  Player wins: {agg['win_rate']:.1%} ({agg['wins']}/{n})")
    bar = "█" * int(agg["win_rate"] * 50)
    print(f"  {bar}")

    print(f"\n--- GAME LENGTH ---")
    print(f"  Avg turns: {agg['avg_turns']:.1f} (range: {agg['min_turns']}–{agg['max_turns']})")

    print(f"\n--- TRICKS ---")
    print(f"  Player avg: {agg['avg_tricks_player']:.1f}")
    print(f"  Owls avg:   {agg['avg_tricks_owls']:.1f}")

    if agg["avg_cards_remaining_on_loss"] > 0:
        print(f"\n--- ON LOSS ---")
        print(f"  Avg cards remaining: {agg['avg_cards_remaining_on_loss']:.1f}")
        print(f"  Max cards remaining: {agg['max_cards_remaining_on_loss']}")

    print(f"\n--- SPECIAL PLAYS ---")
    print(f"  Trip-Ups: {agg['avg_trip_ups']:.2f}/game (in {agg['games_with_trip_up']:.1f}% of games)")
    print(f"  Strategic Conserves: {agg['avg_strategic_conserves']:.2f}/game")

    print(f"\n--- ABILITIES ---")
    for ability, count in agg["ability_usage"].items():
        avg = count / n
        print(f"  {ability:15s}: {count:5d} total ({avg:.1f}/game)")

    # Flag issues
    issues = []
    if not agg["iron_climb"] and agg["win_rate"] < 0.15:
        issues.append(f"WIN RATE TOO LOW: {agg['win_rate']:.1%} — solo may be frustratingly hard")
    if not agg["iron_climb"] and agg["win_rate"] > 0.70:
        issues.append(f"WIN RATE TOO HIGH: {agg['win_rate']:.1%} — solo may be too easy")
    if agg["iron_climb"] and agg["win_rate"] > 0.05:
        issues.append(f"IRON CLIMB WIN RATE: {agg['win_rate']:.1%} — rules claim <5%")
    if agg["avg_turns"] > 200:
        issues.append(f"GAME TOO LONG: avg {agg['avg_turns']:.0f} turns")

    if issues:
        print(f"\n{'!'*60}")
        print(f"  POTENTIAL ISSUES")
        print(f"{'!'*60}")
        for i, issue in enumerate(issues, 1):
            print(f"  {i}. {issue}")
    else:
        print(f"\n  ✓ No major issues detected")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Solo Night Shift Simulator")
    parser.add_argument("-n", "--num-games", type=int, default=1000)
    parser.add_argument("-s", "--seed", type=int, default=1)
    parser.add_argument("--iron-climb", action="store_true")
    parser.add_argument("--json", type=str, default=None)
    args = parser.parse_args()

    agg = run_solo_batch(args.num_games, args.seed, args.iron_climb)
    print_solo_report(agg)

    if args.json:
        with open(args.json, "w") as f:
            json.dump(agg, f, indent=2)
        print(f"\nSaved to {args.json}")
