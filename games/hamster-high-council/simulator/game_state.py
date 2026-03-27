"""
Hamster High Council — Full game state machine.

Handles: setup, Council Balance, Castle's Blessing, trick play,
trick resolution (Trump/Elite/dial), faction talents, scoring,
alliance dial rotation, round management, and victory detection.
"""

import json
import os
import random
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict, Callable

from cards import Card, Deck, build_full_deck, FACTIONS, FACTION_SYMBOLS


# ── Alliance Dial ──────────────────────────────────────────────────

DIAL_POSITIONS = ["CROSS", "LEFT", "RIGHT"]
DIAL_MULTIPLIER = {"CROSS": 1, "LEFT": 1, "RIGHT": 2}
LOW_WINS_POSITIONS = {"RIGHT"}


def next_dial(position: str) -> str:
    """Rotate clockwise: CROSS → LEFT → RIGHT → CROSS."""
    idx = DIAL_POSITIONS.index(position)
    return DIAL_POSITIONS[(idx + 1) % 3]


def prev_dial(position: str) -> str:
    """Rotate counter-clockwise (Red talent)."""
    idx = DIAL_POSITIONS.index(position)
    return DIAL_POSITIONS[(idx - 1) % 3]


# ── Player ─────────────────────────────────────────────────────────

@dataclass
class Player:
    """A single player's state."""
    id: int
    hand: List[Card] = field(default_factory=list)
    vp: int = 0

    # Per-round stats (reset each round)
    tricks_won_this_round: int = 0
    talents_used_this_round: Dict[str, int] = field(default_factory=dict)

    # Lifetime stats
    total_tricks_won: int = 0
    total_talents_used: Dict[str, int] = field(default_factory=dict)
    vp_from_right: int = 0
    tricks_won_at: Dict[str, int] = field(default_factory=dict)  # by dial position

    def cards_of_faction(self, faction: str) -> List[Card]:
        return [c for c in self.hand if c.faction == faction]

    def has_faction(self, faction: str) -> bool:
        return any(c.faction == faction for c in self.hand)

    def reset_round_stats(self):
        self.tricks_won_this_round = 0
        self.talents_used_this_round = {}

    def __repr__(self):
        return f"P{self.id}(VP:{self.vp} Hand:{len(self.hand)})"


# ── Trick Result ───────────────────────────────────────────────────

@dataclass
class TrickResult:
    """Outcome of a single trick."""
    winner_id: Optional[int]  # None if tied / no winner
    winning_card: Optional[Card]
    vp_scored: int
    cards_in_trick: int
    dial_position: str
    multiplier: int
    led_faction: str
    trump_won: bool
    elite_broke_tie: bool
    tied_no_winner: bool
    plays: List[Tuple[int, Card]]  # (player_id, card) in play order
    talent_available: Optional[str]  # faction of winning card, if talent possible
    vp_compressed: bool = False  # True if leader's RIGHT VP was reduced by compression


# ── Game State ─────────────────────────────────────────────────────

class GameState:
    """Complete state machine for Hamster High Council."""

    def __init__(self, config: dict, seed: int = 42):
        self.config = config
        self.rules = config["game_rules"]
        self.rng = random.Random(seed)
        self.seed = seed

        self.num_players = self.rules["num_players"]
        self.vp_target = self.rules["vp_target"]

        # Players
        self.players: List[Player] = [Player(id=i) for i in range(self.num_players)]

        # Decks
        self.vault = Deck()       # draw pile (Snack Vault)
        self.crate = Deck()       # discard pile (Discard Crate)

        # Round state
        self.round_number: int = 0
        self.dial_position: str = "CROSS"
        self.trump_faction: Optional[str] = None
        self.elite_faction: Optional[str] = None
        self.dealer_id: int = self.rng.randint(0, self.num_players - 1)
        self.leader_id: int = 0   # who leads current trick
        self.trick_number: int = 0  # within round

        # Quick Fix state (Yellow talent)
        self.quick_fix_active: bool = False
        self.quick_fix_player_id: Optional[int] = None

        # Game flags
        self.game_over: bool = False
        self.winner_id: Optional[int] = None

        # Logging
        self.log: List[str] = []

        # Metrics
        self.total_tricks: int = 0
        self.total_tied_tricks: int = 0
        self.tricks_by_dial: Dict[str, int] = {"CROSS": 0, "LEFT": 0, "RIGHT": 0}
        self.vp_by_dial: Dict[str, int] = {"CROSS": 0, "LEFT": 0, "RIGHT": 0}
        self.talent_activations: Dict[str, int] = {f: 0 for f in FACTIONS}
        self.intern_draws: int = 0
        self.council_balance_cards_discarded: int = 0
        self.blessing_cards_drawn: int = 0
        self.game_ending_dial: Optional[str] = None

    # ── Setup ──────────────────────────────────────────────────────

    def setup_new_round(self, blessing_fn: Optional[Callable] = None,
                        keep_fn: Optional[Callable] = None):
        """Set up a new round: shuffle, deal, Council Balance, Blessing."""
        self.round_number += 1
        self.trick_number = 0
        self.quick_fix_active = False
        self.quick_fix_player_id = None

        # Reset per-round stats
        for p in self.players:
            p.reset_round_stats()

        # Combine all cards, shuffle
        all_cards = build_full_deck()
        self.vault = Deck(all_cards)
        self.vault.shuffle(self.rng)
        self.crate = Deck()

        # Reset dial
        self.dial_position = "CROSS"

        # Dealer: round 1 = random (already set), round 2+ = lowest VP
        if self.round_number > 1:
            min_vp = min(p.vp for p in self.players)
            lowest = [p for p in self.players if p.vp == min_vp]
            if len(lowest) == 1:
                self.dealer_id = lowest[0].id
            else:
                # Tied: rotate from previous dealer
                self.dealer_id = (self.dealer_id + 1) % self.num_players

        # Council Balance
        self._council_balance()

        # Deal 8 cards
        for p in self.players:
            p.hand = self.vault.draw(self.rules["hand_size"])

        # Castle's Blessing (round 2+)
        if self.round_number > 1 and self.rules["castles_blessing"]["enabled"]:
            self._castles_blessing(blessing_fn, keep_fn)

        # Leader: player left of dealer
        self.leader_id = (self.dealer_id + 1) % self.num_players

        self._log(f"=== ROUND {self.round_number} === "
                  f"Trump: {self.trump_faction} | Elite: {self.elite_faction} | "
                  f"Dealer: P{self.dealer_id} | Leader: P{self.leader_id} | "
                  f"Vault: {self.vault.size} cards")

    def _council_balance(self):
        """Reveal cards to establish Trump and Elite factions."""
        revealed = []
        first_faction = None
        second_faction = None
        attempts = 0

        while True:
            attempts += 1
            revealed = []
            first_faction = None
            second_faction = None

            for _ in range(self.rules["council_balance"]["safety_cap"]):
                card = self.vault.draw_one()
                if card is None:
                    break
                revealed.append(card)

                if first_faction is None:
                    first_faction = card.faction
                elif card.faction != first_faction and second_faction is None:
                    second_faction = card.faction
                    break

            if second_faction is not None:
                break

            # Safety cap hit without second faction — reshuffle and retry
            self.vault.add_to_bottom(revealed)
            self.vault.shuffle(self.rng)
            if attempts > 10:
                # Fallback: pick two random factions
                factions = self.rng.sample(FACTIONS, 2)
                first_faction, second_faction = factions
                revealed = []
                break

        self.trump_faction = first_faction
        self.elite_faction = second_faction

        # Discard revealed cards
        for card in revealed:
            self.crate.add_to_bottom(card)
        self.council_balance_cards_discarded += len(revealed)

        self._log(f"Council Balance: Trump={self.trump_faction}, "
                  f"Elite={self.elite_faction}, discarded {len(revealed)} cards")

    def _castles_blessing(self, blessing_fn=None, keep_fn=None):
        """Trailing players draw extra cards, keep best 8."""
        bl = self.rules["castles_blessing"]
        scores = [(p.vp, p.id) for p in self.players]
        scores.sort()

        min_vp = scores[0][0]
        second_min = None
        for vp, pid in scores:
            if vp > min_vp:
                second_min = vp
                break

        # Last place players
        last_place = [self.players[pid] for vp, pid in scores if vp == min_vp]
        # Second-to-last players (only if different from last place)
        second_to_last = []
        if second_min is not None:
            second_to_last = [self.players[pid] for vp, pid in scores if vp == second_min]

        for p in last_place:
            extra = self.vault.draw(bl["last_place_draw"])
            self.blessing_cards_drawn += len(extra)
            all_cards = p.hand + extra
            if keep_fn:
                kept, returned = keep_fn(p, all_cards, self)
            else:
                # Default: keep highest-ranked cards
                all_cards.sort(key=lambda c: c.rank, reverse=True)
                kept = all_cards[:bl["keep_count"]]
                returned = all_cards[bl["keep_count"]:]
            p.hand = kept
            for c in returned:
                self.vault.add_to_bottom(c)
            self.vault.shuffle(self.rng)
            self._log(f"Blessing: P{p.id} (last place, VP={p.vp}) drew {len(extra)}, "
                      f"kept best {len(kept)}")

        for p in second_to_last:
            extra = self.vault.draw(bl["second_to_last_draw"])
            self.blessing_cards_drawn += len(extra)
            all_cards = p.hand + extra
            if keep_fn:
                kept, returned = keep_fn(p, all_cards, self)
            else:
                all_cards.sort(key=lambda c: c.rank, reverse=True)
                kept = all_cards[:bl["keep_count"]]
                returned = all_cards[bl["keep_count"]:]
            p.hand = kept
            for c in returned:
                self.vault.add_to_bottom(c)
            self.vault.shuffle(self.rng)
            self._log(f"Blessing: P{p.id} (2nd-to-last, VP={p.vp}) drew {len(extra)}, "
                      f"kept best {len(kept)}")

    # ── Trick Play ─────────────────────────────────────────────────

    def play_trick(self, choose_card_fn: Callable,
                   choose_talent_fn: Optional[Callable] = None,
                   choose_quick_fix_cards_fn: Optional[Callable] = None,
                   choose_orange_swap_fn: Optional[Callable] = None,
                   choose_green_keep_fn: Optional[Callable] = None,
                   choose_blue_targets_fn: Optional[Callable] = None) -> TrickResult:
        """
        Play a full trick.

        choose_card_fn(player, game_state, led_faction) -> Card
            Called for each player to choose which card to play.
            led_faction is None for the leader.

        choose_talent_fn(player, game_state, faction) -> bool
            Called when winner can use a talent. Return True to use it.

        Returns a TrickResult with all details.
        """
        self.trick_number += 1
        plays: List[Tuple[int, Card]] = []
        led_faction = None
        intern_draws = 0

        # Determine play order starting from leader
        play_order = [(self.leader_id + i) % self.num_players
                      for i in range(self.num_players)]

        for i, pid in enumerate(play_order):
            player = self.players[pid]

            if i == 0:
                # Leader plays
                if self.quick_fix_active and self.quick_fix_player_id == pid:
                    # Quick Fix: leader plays 2 cards of same faction
                    self.quick_fix_active = False
                    self.quick_fix_player_id = None
                    if choose_quick_fix_cards_fn:
                        card1, card2 = choose_quick_fix_cards_fn(player, self)
                    else:
                        # Default: pick any pair of same faction
                        card1, card2 = self._default_quick_fix(player)

                    if card1 is not None and card2 is not None:
                        led_faction = card1.faction
                        player.hand.remove(card1)
                        player.hand.remove(card2)
                        plays.append((pid, card1))
                        plays.append((pid, card2))
                        # Intern draws for each rank-0
                        for c in [card1, card2]:
                            if c.is_intern and not self.vault.empty:
                                drawn = self.vault.draw_one()
                                if drawn:
                                    player.hand.append(drawn)
                                    intern_draws += 1
                                    self.intern_draws += 1
                        self._log(f"P{pid} leads QUICK FIX: {card1} + {card2} (faction={led_faction})")
                    else:
                        # Quick fix fizzled — play normally
                        card = choose_card_fn(player, self, None)
                        led_faction = card.faction
                        player.hand.remove(card)
                        plays.append((pid, card))
                        if card.is_intern and not self.vault.empty:
                            drawn = self.vault.draw_one()
                            if drawn:
                                player.hand.append(drawn)
                                intern_draws += 1
                                self.intern_draws += 1
                        self._log(f"P{pid} leads: {card} (Quick Fix fizzled)")
                else:
                    card = choose_card_fn(player, self, None)
                    led_faction = card.faction
                    player.hand.remove(card)
                    plays.append((pid, card))
                    if card.is_intern and not self.vault.empty:
                        drawn = self.vault.draw_one()
                        if drawn:
                            player.hand.append(drawn)
                            intern_draws += 1
                            self.intern_draws += 1
                    self._log(f"P{pid} leads: {card} (faction={led_faction})")
            else:
                # Followers
                card = choose_card_fn(player, self, led_faction)
                player.hand.remove(card)
                plays.append((pid, card))
                if card.is_intern and not self.vault.empty:
                    drawn = self.vault.draw_one()
                    if drawn:
                        player.hand.append(drawn)
                        intern_draws += 1
                        self.intern_draws += 1
                self._log(f"P{pid} plays: {card}")

        # ── Resolve the trick ──────────────────────────────────────
        result = self._resolve_trick(plays, led_faction)

        if not result.tied_no_winner:
            winner = self.players[result.winner_id]

            # 1. Score VP (with optional compression)
            actual_vp = result.vp_scored
            vp_compressed = False
            if (self.rules.get("scoring", {}).get("vp_compression", False)
                and self.dial_position == "RIGHT"):
                # Leader scores x1 instead of x2
                max_vp_others = max(
                    (p.vp for p in self.players if p.id != result.winner_id),
                    default=0)
                if winner.vp > max_vp_others:
                    actual_vp = result.cards_in_trick  # x1 instead of x2
                    vp_compressed = True

            result.vp_compressed = vp_compressed
            if vp_compressed:
                result.vp_scored = actual_vp  # update result to reflect actual VP
            winner.vp += actual_vp
            winner.total_tricks_won += 1
            winner.tricks_won_this_round += 1
            winner.tricks_won_at[self.dial_position] = winner.tricks_won_at.get(self.dial_position, 0) + 1
            if self.dial_position == "RIGHT":
                winner.vp_from_right += actual_vp

            self.vp_by_dial[self.dial_position] += actual_vp
            self.tricks_by_dial[self.dial_position] += 1
            self.total_tricks += 1

            self._log(f"P{result.winner_id} WINS with {result.winning_card} → "
                      f"{result.vp_scored} VP (dial={self.dial_position}, "
                      f"×{result.multiplier}, {result.cards_in_trick} cards). "
                      f"Total VP: {winner.vp}")

            # 2. Discard trick cards to Crate
            # (Purple Time Loop card will be retrieved after this)
            trick_cards = [card for _, card in plays]
            for card in trick_cards:
                self.crate.add_to_bottom(card)

            # 3. Rotate dial clockwise
            old_dial = self.dial_position
            self.dial_position = next_dial(self.dial_position)

            # 4. Check victory
            if winner.vp >= self.vp_target:
                self.game_over = True
                self.winner_id = winner.id
                self.game_ending_dial = old_dial
                self._log(f"*** P{winner.id} WINS THE GAME with {winner.vp} VP! ***")
                return result

            # 5. Faction Talent (optional)
            if self.rules["talents"]["enabled"] and choose_talent_fn:
                winning_faction = result.winning_card.faction
                use_talent = choose_talent_fn(winner, self, winning_faction)
                if use_talent:
                    self._execute_talent(winner, winning_faction, result,
                                        choose_orange_swap_fn,
                                        choose_green_keep_fn,
                                        choose_blue_targets_fn)

            # 6. Leader = winner
            self.leader_id = result.winner_id

        else:
            # Tie — no winner
            self.total_tied_tricks += 1
            self.total_tricks += 1
            self.tricks_by_dial[self.dial_position] += 1

            # All cards to Crate
            for _, card in plays:
                self.crate.add_to_bottom(card)

            self._log(f"TIED trick — no winner. Cards to Crate. Same leader.")
            # Leader stays the same, dial does not rotate

        return result

    def _resolve_trick(self, plays: List[Tuple[int, Card]],
                       led_faction: str) -> TrickResult:
        """Resolve who wins the trick."""
        dial = self.dial_position
        multiplier = DIAL_MULTIPLIER[dial]
        cards_in_trick = len(plays)
        trump_won = False
        elite_broke_tie = False
        tied_no_winner = False

        # Step 1: Trump check
        trump_plays = [(pid, c) for pid, c in plays if c.faction == self.trump_faction]
        if trump_plays:
            # Highest Trump wins
            trump_plays.sort(key=lambda x: x[1].rank, reverse=True)
            max_rank = trump_plays[0][1].rank
            top_trump = [(pid, c) for pid, c in trump_plays if c.rank == max_rank]

            if len(top_trump) == 1:
                winner_id, winning_card = top_trump[0]
                return TrickResult(
                    winner_id=winner_id, winning_card=winning_card,
                    vp_scored=cards_in_trick * multiplier,
                    cards_in_trick=cards_in_trick, dial_position=dial,
                    multiplier=multiplier, led_faction=led_faction,
                    trump_won=True, elite_broke_tie=False,
                    tied_no_winner=False, plays=plays,
                    talent_available=winning_card.faction
                )
            else:
                # Tied Trump — check Elite
                elite_trump = [(pid, c) for pid, c in top_trump
                               if c.faction == self.elite_faction]
                if len(elite_trump) == 1:
                    winner_id, winning_card = elite_trump[0]
                    return TrickResult(
                        winner_id=winner_id, winning_card=winning_card,
                        vp_scored=cards_in_trick * multiplier,
                        cards_in_trick=cards_in_trick, dial_position=dial,
                        multiplier=multiplier, led_faction=led_faction,
                        trump_won=True, elite_broke_tie=True,
                        tied_no_winner=False, plays=plays,
                        talent_available=winning_card.faction
                    )
                else:
                    # Still tied — no winner
                    return TrickResult(
                        winner_id=None, winning_card=None, vp_scored=0,
                        cards_in_trick=cards_in_trick, dial_position=dial,
                        multiplier=multiplier, led_faction=led_faction,
                        trump_won=True, elite_broke_tie=False,
                        tied_no_winner=True, plays=plays,
                        talent_available=None
                    )

        # Step 2: Alliance Resolution — only led-faction cards can win
        led_plays = [(pid, c) for pid, c in plays if c.faction == led_faction]
        if not led_plays:
            # This shouldn't happen (leader always plays led faction)
            # but handle gracefully
            return TrickResult(
                winner_id=None, winning_card=None, vp_scored=0,
                cards_in_trick=cards_in_trick, dial_position=dial,
                multiplier=multiplier, led_faction=led_faction,
                trump_won=False, elite_broke_tie=False,
                tied_no_winner=True, plays=plays,
                talent_available=None
            )

        if dial in LOW_WINS_POSITIONS:
            # Lowest of led faction wins
            led_plays.sort(key=lambda x: x[1].rank)
        else:
            # Highest of led faction wins
            led_plays.sort(key=lambda x: x[1].rank, reverse=True)

        winning_rank = led_plays[0][1].rank
        candidates = [(pid, c) for pid, c in led_plays if c.rank == winning_rank]

        if len(candidates) == 1:
            winner_id, winning_card = candidates[0]
            return TrickResult(
                winner_id=winner_id, winning_card=winning_card,
                vp_scored=cards_in_trick * multiplier,
                cards_in_trick=cards_in_trick, dial_position=dial,
                multiplier=multiplier, led_faction=led_faction,
                trump_won=False, elite_broke_tie=False,
                tied_no_winner=False, plays=plays,
                talent_available=winning_card.faction
            )

        # Step 3: Tiebreak — Elite
        elite_candidates = [(pid, c) for pid, c in candidates
                            if c.faction == self.elite_faction]
        if len(elite_candidates) == 1:
            winner_id, winning_card = elite_candidates[0]
            return TrickResult(
                winner_id=winner_id, winning_card=winning_card,
                vp_scored=cards_in_trick * multiplier,
                cards_in_trick=cards_in_trick, dial_position=dial,
                multiplier=multiplier, led_faction=led_faction,
                trump_won=False, elite_broke_tie=True,
                tied_no_winner=False, plays=plays,
                talent_available=winning_card.faction
            )

        # Still tied — no winner
        return TrickResult(
            winner_id=None, winning_card=None, vp_scored=0,
            cards_in_trick=cards_in_trick, dial_position=dial,
            multiplier=multiplier, led_faction=led_faction,
            trump_won=False, elite_broke_tie=False,
            tied_no_winner=True, plays=plays,
            talent_available=None
        )

    # ── Talents ────────────────────────────────────────────────────

    def _execute_talent(self, winner: Player, faction: str,
                        trick_result: TrickResult,
                        choose_orange_swap_fn=None,
                        choose_green_keep_fn=None,
                        choose_blue_targets_fn=None):
        """Execute a faction talent after winning a trick."""
        self.talent_activations[faction] += 1
        winner.talents_used_this_round[faction] = winner.talents_used_this_round.get(faction, 0) + 1
        winner.total_talents_used[faction] = winner.total_talents_used.get(faction, 0) + 1

        if faction == "RED":
            # Rally the Dupes: rotate dial back (counter-clockwise)
            self.dial_position = prev_dial(self.dial_position)
            self._log(f"  🔴 TALENT: Rally the Dupes — dial back to {self.dial_position}")

        elif faction == "ORANGE":
            # Finders Keepers: swap 1 hand card with any crate card
            if self.crate.size > 0 and len(winner.hand) > 0:
                if choose_orange_swap_fn:
                    hand_card, crate_card = choose_orange_swap_fn(winner, self)
                else:
                    hand_card, crate_card = self._default_orange(winner)

                if hand_card and crate_card:
                    winner.hand.remove(hand_card)
                    self.crate.remove(crate_card)
                    winner.hand.append(crate_card)
                    self.crate.add_to_bottom(hand_card)
                    self._log(f"  🟠 TALENT: Finders Keepers — swapped {hand_card} for {crate_card}")

        elif faction == "YELLOW":
            # Quick Fix: next trick, leader plays 2 cards of same faction
            # Check if the winner has 2 cards of same faction
            has_pair = False
            for f in FACTIONS:
                if len(winner.cards_of_faction(f)) >= 2:
                    has_pair = True
                    break
            if has_pair:
                self.quick_fix_active = True
                self.quick_fix_player_id = winner.id
                self._log(f"  🟡 TALENT: Quick Fix — P{winner.id} will lead 2 cards next trick")
            else:
                self._log(f"  🟡 TALENT: Quick Fix FIZZLED — no same-faction pair in hand")

        elif faction == "GREEN":
            # Saw It Coming: peek top 3 of vault, keep 1, reorder 2
            if self.vault.size > 0:
                peek_count = min(3, self.vault.size)
                peeked = self.vault.draw(peek_count)
                if choose_green_keep_fn:
                    keep_card, reorder = choose_green_keep_fn(winner, peeked, self)
                else:
                    keep_card, reorder = self._default_green(winner, peeked)

                winner.hand.append(keep_card)
                # Put remaining back on top in chosen order
                self.vault.add_to_top(reorder)
                self._log(f"  🟢 TALENT: Saw It Coming — kept {keep_card}, "
                          f"reordered {len(reorder)} on top")

        elif faction == "BLUE":
            # Sleight of Paw: choose 2 opponents, they swap 1 random card each
            opponents = [p for p in self.players if p.id != winner.id and len(p.hand) > 0]
            if len(opponents) >= 2:
                if choose_blue_targets_fn:
                    target1, target2 = choose_blue_targets_fn(winner, opponents, self)
                else:
                    target1, target2 = self._default_blue(winner, opponents)

                if len(target1.hand) > 0 and len(target2.hand) > 0:
                    card1 = self.rng.choice(target1.hand)
                    card2 = self.rng.choice(target2.hand)
                    target1.hand.remove(card1)
                    target2.hand.remove(card2)
                    target1.hand.append(card2)
                    target2.hand.append(card1)
                    self._log(f"  🔵 TALENT: Sleight of Paw — P{target1.id} and P{target2.id} "
                              f"swapped cards")
            else:
                self._log(f"  🔵 TALENT: Sleight of Paw FIZZLED — not enough opponents with cards")

        elif faction == "PURPLE":
            # Pocket the Past: bank 1 card from hand for 1 VP, draw 1, discard 1
            if len(winner.hand) < 2:
                self._log(f"  🟣 TALENT: Pocket the Past FIZZLED — not enough cards")
                return
            # Bank least valuable card (all worth 1 VP in bank)
            bank_card = min(winner.hand, key=lambda c: c.rank)
            winner.hand.remove(bank_card)
            winner.vp += 1
            self.crate.add_to_bottom(bank_card)
            self._log(f"  🟣 TALENT: Pocket the Past — banked {bank_card} for 1 VP")
            # Draw 1
            if not self.vault.empty:
                drawn = self.vault.draw_one()
                if drawn:
                    winner.hand.append(drawn)
            # Discard 1
            if winner.hand:
                discard_card = min(winner.hand, key=lambda c: c.rank)
                winner.hand.remove(discard_card)
                self.crate.add_to_bottom(discard_card)
            # Check victory
            if winner.vp >= self.vp_target:
                self.game_over = True
                self.winner_id = winner.id
                self._log(f"*** P{winner.id} WINS via Purple bank! {winner.vp} VP ***")

    def _default_quick_fix(self, player: Player) -> Tuple[Optional[Card], Optional[Card]]:
        """Default Quick Fix: pick highest-ranked pair of same faction."""
        best_pair = None
        best_rank = -1
        for f in FACTIONS:
            cards = sorted(player.cards_of_faction(f), key=lambda c: c.rank, reverse=True)
            if len(cards) >= 2:
                pair_rank = cards[0].rank + cards[1].rank
                if pair_rank > best_rank:
                    best_rank = pair_rank
                    best_pair = (cards[0], cards[1])
        return best_pair if best_pair else (None, None)

    def _default_orange(self, winner: Player) -> Tuple[Optional[Card], Optional[Card]]:
        """Default Orange talent: swap weakest hand card for strongest crate card."""
        if not winner.hand or self.crate.empty:
            return None, None
        weakest = min(winner.hand, key=lambda c: c.rank)
        strongest = max(self.crate.cards, key=lambda c: c.rank)
        if strongest.rank > weakest.rank:
            return weakest, strongest
        return None, None

    def _default_green(self, winner: Player, peeked: List[Card]):
        """Default Green talent: keep highest-ranked card."""
        peeked.sort(key=lambda c: c.rank, reverse=True)
        return peeked[0], peeked[1:]

    def _default_blue(self, winner: Player, opponents: List[Player]):
        """Default Blue talent: pick 2 opponents randomly."""
        chosen = self.rng.sample(opponents, 2)
        return chosen[0], chosen[1]

    # ── Round Management ───────────────────────────────────────────

    def is_round_over(self) -> bool:
        """Round ends when any player plays their last card."""
        return any(len(p.hand) == 0 for p in self.players)

    def end_round(self):
        """Clean up after a round — discard remaining hands."""
        for p in self.players:
            for card in p.hand:
                self.crate.add_to_bottom(card)
            p.hand = []
        self._log(f"Round {self.round_number} ended. "
                  f"Scores: {', '.join(f'P{p.id}={p.vp}' for p in self.players)}")

    # ── Utility ────────────────────────────────────────────────────

    def get_partner_id(self, player_id: int) -> Optional[int]:
        """Who is this player's partner at the current dial position?"""
        if self.dial_position == "CROSS":
            return (player_id + 2) % self.num_players
        elif self.dial_position == "LEFT":
            return (player_id + 1) % self.num_players  # player to your left
        elif self.dial_position == "RIGHT":
            return (player_id - 1) % self.num_players  # player to your right
        return None

    def get_legal_plays(self, player: Player, led_faction: Optional[str]) -> List[Card]:
        """What cards can this player legally play?"""
        if led_faction is None:
            # Leader can play anything
            return list(player.hand)
        # Must follow led faction if possible
        on_suit = player.cards_of_faction(led_faction)
        if on_suit:
            return on_suit
        # Off-suit: can play anything
        return list(player.hand)

    def _log(self, msg: str):
        self.log.append(msg)

    # ── Config Loading ─────────────────────────────────────────────

    @staticmethod
    def load_config(config_path: Optional[str] = None) -> dict:
        """Load config.json from default or specified path."""
        if config_path is None:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            config_path = os.path.join(script_dir, "config.json")
        with open(config_path, 'r') as f:
            return json.load(f)
