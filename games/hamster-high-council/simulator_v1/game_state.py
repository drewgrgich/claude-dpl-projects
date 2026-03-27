"""
Hamster High Council v1.0 — Game State Machine.

Key differences from v2.1:
  - Three Council seats: Trump, Elite, Wobbly (low wins when Wobbly is LED)
  - No Alliance Dial, no partnerships, no multipliers
  - Stash scoring: won trick cards → player's stash, 1 card = 1 VP
  - Final Bell: extra trick when someone empties their hand
  - Different faction talents (hand manipulation focus)
  - 3-5 player support with variable hand sizes
"""

import json
import os
import random
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict, Callable

from cards import Card, Deck, build_full_deck, FACTIONS, FACTION_SYMBOLS


@dataclass
class Player:
    """A single player's state."""
    id: int
    hand: List[Card] = field(default_factory=list)
    vp: int = 0  # tracked as number; cards return to deck each round

    # Stats
    tricks_won_this_round: int = 0
    total_tricks_won: int = 0
    talents_used: Dict[str, int] = field(default_factory=dict)
    wobbly_tricks_won: int = 0
    trump_tricks_won: int = 0

    def cards_of_faction(self, faction: str) -> List[Card]:
        return [c for c in self.hand if c.faction == faction]

    def has_faction(self, faction: str) -> bool:
        return any(c.faction == faction for c in self.hand)

    def reset_round_stats(self):
        self.tricks_won_this_round = 0

    def __repr__(self):
        return f"P{self.id}(VP:{self.vp} Hand:{len(self.hand)})"


@dataclass
class TrickResult:
    """Outcome of a single trick."""
    winner_id: Optional[int]
    winning_card: Optional[Card]
    cards_in_trick: int
    led_faction: str
    trump_won: bool
    wobbly_won: bool       # won via Wobbly inversion
    elite_broke_tie: bool
    tied_no_winner: bool
    plays: List[Tuple[int, Card]]
    is_final_bell: bool = False


class GameState:
    """Complete state machine for Hamster High Council v1.0."""

    def __init__(self, config: dict, seed: int = 42):
        self.config = config
        self.rules = config["game_rules"]
        self.rng = random.Random(seed)
        self.seed = seed

        self.num_players = self.rules["num_players"]
        self.hand_size = self.rules["hand_sizes"][str(self.num_players)]
        self.vp_target = self.rules["vp_target"]

        self.players: List[Player] = [Player(id=i) for i in range(self.num_players)]

        self.vault = Deck()
        self.crate = Deck()

        # Round state
        self.round_number: int = 0
        self.trump_faction: Optional[str] = None
        self.elite_faction: Optional[str] = None
        self.wobbly_faction: Optional[str] = None  # v1 exclusive
        self.dealer_id: int = self.rng.randint(0, self.num_players - 1)
        self.leader_id: int = 0
        self.trick_number: int = 0

        # Game flags
        self.game_over: bool = False
        self.winner_id: Optional[int] = None

        # Logging
        self.log: List[str] = []

        # Metrics
        self.total_tricks: int = 0
        self.total_tied_tricks: int = 0
        self.wobbly_tricks: int = 0
        self.trump_tricks: int = 0
        self.standard_tricks: int = 0
        self.talent_activations: Dict[str, int] = {f: 0 for f in FACTIONS}
        self.intern_draws: int = 0
        self.council_balance_cards_discarded: int = 0
        self.final_bell_tricks: int = 0
        self.cards_banked_by_purple: int = 0

    # ── Setup ──────────────────────────────────────────────────────

    def setup_new_round(self):
        """Set up a new round: shuffle, deal, Council Balance."""
        self.round_number += 1
        self.trick_number = 0

        for p in self.players:
            p.reset_round_stats()

        # "Shuffle everything" — full 66-card deck reshuffled each round.
        # Stash VP is tracked as a number; cards return to deck.
        all_cards = build_full_deck()
        self.vault = Deck(all_cards)
        self.vault.shuffle(self.rng)
        self.crate = Deck()

        # Dealer rotation
        if self.round_number > 1:
            self.dealer_id = (self.dealer_id + 1) % self.num_players

        # Council Balance — 3 seats
        self._council_balance()

        # Deal
        for p in self.players:
            p.hand = self.vault.draw(self.hand_size)

        # Leader: round 1 = left of dealer; round 2+ = lowest score
        if self.round_number == 1:
            self.leader_id = (self.dealer_id + 1) % self.num_players
        else:
            min_vp = min(p.vp for p in self.players)
            lowest = [p for p in self.players if p.vp == min_vp]
            self.leader_id = lowest[0].id

        self._log(f"=== ROUND {self.round_number} === "
                  f"Trump: {self.trump_faction} | Elite: {self.elite_faction} | "
                  f"Wobbly: {self.wobbly_faction} | "
                  f"Dealer: P{self.dealer_id} | Leader: P{self.leader_id} | "
                  f"Vault: {self.vault.size} cards")

    def _council_balance(self):
        """Reveal cards until 3 different factions appear."""
        revealed = []
        factions_found = []

        while len(factions_found) < 3:
            card = self.vault.draw_one()
            if card is None:
                break
            revealed.append(card)
            if card.faction not in factions_found:
                factions_found.append(card.faction)

        if len(factions_found) < 3:
            # Fallback
            all_f = list(FACTIONS)
            self.rng.shuffle(all_f)
            while len(factions_found) < 3:
                for f in all_f:
                    if f not in factions_found:
                        factions_found.append(f)
                        if len(factions_found) == 3:
                            break

        self.trump_faction = factions_found[0]
        self.elite_faction = factions_found[1]
        self.wobbly_faction = factions_found[2]

        # Discard all revealed cards to crate
        for card in revealed:
            self.crate.add_to_bottom(card)
        self.council_balance_cards_discarded += len(revealed)

        self._log(f"Council Balance: Trump={self.trump_faction}, "
                  f"Elite={self.elite_faction}, Wobbly={self.wobbly_faction}, "
                  f"discarded {len(revealed)} cards")

    # ── Trick Play ─────────────────────────────────────────────────

    def play_trick(self, choose_card_fn: Callable,
                   choose_talent_fn: Optional[Callable] = None,
                   talent_callbacks: Optional[dict] = None,
                   is_final_bell: bool = False) -> TrickResult:
        """Play a single trick."""
        self.trick_number += 1
        if talent_callbacks is None:
            talent_callbacks = {}

        plays: List[Tuple[int, Card]] = []
        led_faction = None

        play_order = [(self.leader_id + i) % self.num_players
                      for i in range(self.num_players)]

        for i, pid in enumerate(play_order):
            player = self.players[pid]
            if not player.hand:
                continue  # skip players with no cards

            if i == 0:
                card = choose_card_fn(player, self, None)
                led_faction = card.faction
                player.hand.remove(card)
                plays.append((pid, card))
                if card.is_intern and not self.vault.empty:
                    drawn = self.vault.draw_one()
                    if drawn:
                        player.hand.append(drawn)
                        self.intern_draws += 1
                self._log(f"P{pid} leads: {card} (faction={led_faction})")
            else:
                card = choose_card_fn(player, self, led_faction)
                player.hand.remove(card)
                plays.append((pid, card))
                if card.is_intern and not self.vault.empty:
                    drawn = self.vault.draw_one()
                    if drawn:
                        player.hand.append(drawn)
                        self.intern_draws += 1
                self._log(f"P{pid} plays: {card}")

        # Resolve
        result = self._resolve_trick(plays, led_faction, is_final_bell)

        if not result.tied_no_winner and result.winner_id is not None:
            winner = self.players[result.winner_id]

            # Score VP (1 card = 1 VP). Cards go to crate (reshuffled next round).
            winner.vp += len(plays)
            for _, card in plays:
                self.crate.add_to_bottom(card)

            winner.total_tricks_won += 1
            winner.tricks_won_this_round += 1
            self.total_tricks += 1

            if result.trump_won:
                self.trump_tricks += 1
                winner.trump_tricks_won += 1
            elif result.wobbly_won:
                self.wobbly_tricks += 1
                winner.wobbly_tricks_won += 1
            else:
                self.standard_tricks += 1

            if is_final_bell:
                self.final_bell_tricks += 1

            self._log(f"P{result.winner_id} WINS with {result.winning_card} → "
                      f"{result.cards_in_trick} cards to stash. "
                      f"Total VP: {winner.vp}"
                      f"{' (TRUMP)' if result.trump_won else ''}"
                      f"{' (WOBBLY)' if result.wobbly_won else ''}"
                      f"{' [FINAL BELL]' if is_final_bell else ''}")

            # Check victory
            if winner.vp >= self.vp_target:
                self.game_over = True
                self.winner_id = winner.id
                self._log(f"*** P{winner.id} WINS THE GAME with {winner.vp} VP! ***")
                return result

            # Talent
            if self.rules["talents"]["enabled"] and choose_talent_fn:
                faction = result.winning_card.faction
                use = choose_talent_fn(winner, self, faction)
                if use:
                    self._execute_talent(winner, faction, talent_callbacks)

            # Leader = winner
            self.leader_id = result.winner_id
        else:
            # Tied — cards to crate
            self.total_tied_tricks += 1
            self.total_tricks += 1
            for _, card in plays:
                self.crate.add_to_bottom(card)
            self._log(f"TIED trick — no winner. Cards to Crate.")

        return result

    def _resolve_trick(self, plays: List[Tuple[int, Card]],
                       led_faction: str,
                       is_final_bell: bool = False) -> TrickResult:
        """Resolve who wins the trick."""
        cards_in_trick = len(plays)
        trump_won = False
        wobbly_won = False
        elite_broke_tie = False

        # Step 1: Trump check
        trump_plays = [(pid, c) for pid, c in plays if c.faction == self.trump_faction]
        if trump_plays:
            trump_plays.sort(key=lambda x: x[1].rank, reverse=True)
            max_rank = trump_plays[0][1].rank
            top = [(pid, c) for pid, c in trump_plays if c.rank == max_rank]

            if len(top) == 1:
                return TrickResult(
                    winner_id=top[0][0], winning_card=top[0][1],
                    cards_in_trick=cards_in_trick, led_faction=led_faction,
                    trump_won=True, wobbly_won=False, elite_broke_tie=False,
                    tied_no_winner=False, plays=plays, is_final_bell=is_final_bell
                )
            # Tied trump — Elite breaks tie
            elite = [(pid, c) for pid, c in top if c.faction == self.elite_faction]
            if len(elite) == 1:
                return TrickResult(
                    winner_id=elite[0][0], winning_card=elite[0][1],
                    cards_in_trick=cards_in_trick, led_faction=led_faction,
                    trump_won=True, wobbly_won=False, elite_broke_tie=True,
                    tied_no_winner=False, plays=plays, is_final_bell=is_final_bell
                )
            # Still tied
            return TrickResult(
                winner_id=None, winning_card=None,
                cards_in_trick=cards_in_trick, led_faction=led_faction,
                trump_won=True, wobbly_won=False, elite_broke_tie=False,
                tied_no_winner=True, plays=plays, is_final_bell=is_final_bell
            )

        # Step 2: Wobbly check — was the Wobbly faction LED?
        if led_faction == self.wobbly_faction:
            wobbly_plays = [(pid, c) for pid, c in plays if c.faction == self.wobbly_faction]
            if wobbly_plays:
                # LOWEST rank of wobbly faction wins
                wobbly_plays.sort(key=lambda x: x[1].rank)
                min_rank = wobbly_plays[0][1].rank
                bottom = [(pid, c) for pid, c in wobbly_plays if c.rank == min_rank]

                if len(bottom) == 1:
                    return TrickResult(
                        winner_id=bottom[0][0], winning_card=bottom[0][1],
                        cards_in_trick=cards_in_trick, led_faction=led_faction,
                        trump_won=False, wobbly_won=True, elite_broke_tie=False,
                        tied_no_winner=False, plays=plays, is_final_bell=is_final_bell
                    )
                # Tied wobbly — Elite breaks tie
                elite = [(pid, c) for pid, c in bottom if c.faction == self.elite_faction]
                if len(elite) == 1:
                    return TrickResult(
                        winner_id=elite[0][0], winning_card=elite[0][1],
                        cards_in_trick=cards_in_trick, led_faction=led_faction,
                        trump_won=False, wobbly_won=True, elite_broke_tie=True,
                        tied_no_winner=False, plays=plays, is_final_bell=is_final_bell
                    )
                return TrickResult(
                    winner_id=None, winning_card=None,
                    cards_in_trick=cards_in_trick, led_faction=led_faction,
                    trump_won=False, wobbly_won=True, elite_broke_tie=False,
                    tied_no_winner=True, plays=plays, is_final_bell=is_final_bell
                )

        # Step 3: Standard — highest of led faction wins
        led_plays = [(pid, c) for pid, c in plays if c.faction == led_faction]
        if not led_plays:
            return TrickResult(
                winner_id=None, winning_card=None,
                cards_in_trick=cards_in_trick, led_faction=led_faction,
                trump_won=False, wobbly_won=False, elite_broke_tie=False,
                tied_no_winner=True, plays=plays, is_final_bell=is_final_bell
            )

        led_plays.sort(key=lambda x: x[1].rank, reverse=True)
        max_rank = led_plays[0][1].rank
        top = [(pid, c) for pid, c in led_plays if c.rank == max_rank]

        if len(top) == 1:
            return TrickResult(
                winner_id=top[0][0], winning_card=top[0][1],
                cards_in_trick=cards_in_trick, led_faction=led_faction,
                trump_won=False, wobbly_won=False, elite_broke_tie=False,
                tied_no_winner=False, plays=plays, is_final_bell=is_final_bell
            )
        # Tied — Elite
        elite = [(pid, c) for pid, c in top if c.faction == self.elite_faction]
        if len(elite) == 1:
            return TrickResult(
                winner_id=elite[0][0], winning_card=elite[0][1],
                cards_in_trick=cards_in_trick, led_faction=led_faction,
                trump_won=False, wobbly_won=False, elite_broke_tie=True,
                tied_no_winner=False, plays=plays, is_final_bell=is_final_bell
            )
        return TrickResult(
            winner_id=None, winning_card=None,
            cards_in_trick=cards_in_trick, led_faction=led_faction,
            trump_won=False, wobbly_won=False, elite_broke_tie=False,
            tied_no_winner=True, plays=plays, is_final_bell=is_final_bell
        )

    # ── Talents ────────────────────────────────────────────────────

    def _execute_talent(self, winner: Player, faction: str,
                        callbacks: dict):
        """Execute a v1 faction talent."""
        self.talent_activations[faction] += 1
        winner.talents_used[faction] = winner.talents_used.get(faction, 0) + 1

        if faction == "RED":
            # Borrow Aggressively: reveal 1 random from opponent,
            # optionally discard 1 from hand to force them to discard revealed.
            opponents = [p for p in self.players
                         if p.id != winner.id and len(p.hand) > 0]
            if not opponents:
                return

            cb = callbacks.get("red")
            if cb:
                target, do_discard = cb(winner, opponents, self)
            else:
                target = self.rng.choice(opponents)
                do_discard = len(winner.hand) > 2  # default heuristic

            revealed = self.rng.choice(target.hand)
            self._log(f"  🔴 TALENT: Borrow Aggressively — revealed P{target.id}'s {revealed}")

            if do_discard and len(winner.hand) > 0:
                # Discard worst card from hand to force opponent discard
                if cb:
                    discard_card = cb.__self__.choose_red_discard(winner, revealed, self) if hasattr(cb, '__self__') else min(winner.hand, key=lambda c: c.rank)
                else:
                    discard_card = min(winner.hand, key=lambda c: c.rank)
                winner.hand.remove(discard_card)
                self.crate.add_to_bottom(discard_card)
                target.hand.remove(revealed)
                self.crate.add_to_bottom(revealed)
                self._log(f"    Discarded {discard_card} to force P{target.id} to discard {revealed}")

        elif faction == "ORANGE":
            # Snack Forecast: top 3 of vault, keep 1, put 2 on bottom
            if self.vault.empty:
                return
            peek_count = min(3, self.vault.size)
            peeked = self.vault.draw(peek_count)

            cb = callbacks.get("orange")
            if cb:
                keep, rest = cb(winner, peeked, self)
            else:
                peeked.sort(key=lambda c: c.rank, reverse=True)
                keep = peeked[0]
                rest = peeked[1:]

            winner.hand.append(keep)
            for c in rest:
                self.vault.add_to_bottom(c)
            self._log(f"  🟠 TALENT: Snack Forecast — kept {keep}")

        elif faction == "YELLOW":
            # Quick Adjustment: look at top card, may swap 1 from hand
            if self.vault.empty:
                return
            top_card = self.vault.draw_one()

            cb = callbacks.get("yellow")
            if cb:
                do_swap, hand_card = cb(winner, top_card, self)
            else:
                worst = min(winner.hand, key=lambda c: c.rank)
                do_swap = top_card.rank > worst.rank
                hand_card = worst

            if do_swap and hand_card:
                winner.hand.remove(hand_card)
                winner.hand.append(top_card)
                self.vault.add_to_top(hand_card)
                self._log(f"  🟡 TALENT: Quick Adjustment — swapped {hand_card} for {top_card}")
            else:
                self.vault.add_to_top(top_card)
                self._log(f"  🟡 TALENT: Quick Adjustment — kept hand (top was {top_card})")

        elif faction == "GREEN":
            # Flow Correction: draw 2, put 1 from hand on bottom of vault
            drawn = self.vault.draw(min(2, self.vault.size))
            for c in drawn:
                winner.hand.append(c)

            cb = callbacks.get("green")
            if cb:
                return_card = cb(winner, drawn, self)
            else:
                return_card = min(winner.hand, key=lambda c: c.rank)

            if return_card and return_card in winner.hand:
                winner.hand.remove(return_card)
                self.vault.add_to_bottom(return_card)
            self._log(f"  🟢 TALENT: Flow Correction — drew {len(drawn)}, returned {return_card}")

        elif faction == "BLUE":
            # Fair Trade: take 1 random from opponent, give 1 from hand
            opponents = [p for p in self.players
                         if p.id != winner.id and len(p.hand) > 0]
            if not opponents or not winner.hand:
                return

            cb = callbacks.get("blue")
            if cb:
                target, give_card = cb(winner, opponents, self)
            else:
                target = self.rng.choice(opponents)
                give_card = min(winner.hand, key=lambda c: c.rank)

            taken = self.rng.choice(target.hand)
            target.hand.remove(taken)
            winner.hand.append(taken)

            if give_card in winner.hand:
                winner.hand.remove(give_card)
                target.hand.append(give_card)
            self._log(f"  🔵 TALENT: Fair Trade — took {taken} from P{target.id}, "
                      f"gave {give_card}")

        elif faction == "PURPLE":
            # Pocket the Past: bank 1 from hand to stash, draw 1, discard 1
            if not winner.hand:
                return

            cb = callbacks.get("purple")
            if cb:
                bank_card, discard_card = cb(winner, self)
            else:
                # Bank highest card
                bank_card = max(winner.hand, key=lambda c: c.rank)
                discard_card = None

            if bank_card and bank_card in winner.hand:
                winner.hand.remove(bank_card)
                winner.vp += 1  # Free VP! Card goes to crate.
                self.crate.add_to_bottom(bank_card)
                self.cards_banked_by_purple += 1
                self._log(f"  🟣 TALENT: Pocket the Past — banked {bank_card} (VP!)")

                # Draw 1
                if not self.vault.empty:
                    drawn = self.vault.draw_one()
                    if drawn:
                        winner.hand.append(drawn)

                # Discard 1
                if winner.hand:
                    if discard_card is None or discard_card not in winner.hand:
                        discard_card = min(winner.hand, key=lambda c: c.rank)
                    if discard_card in winner.hand:
                        winner.hand.remove(discard_card)
                        self.crate.add_to_bottom(discard_card)

                # Check if banking pushed VP over target
                if winner.vp >= self.vp_target:
                    self.game_over = True
                    self.winner_id = winner.id
                    self._log(f"*** P{winner.id} WINS via Purple bank! {winner.vp} VP ***")

    # ── Round Management ───────────────────────────────────────────

    def player_emptied_hand(self) -> Optional[int]:
        """Return id of first player with empty hand, or None."""
        for p in self.players:
            if len(p.hand) == 0:
                return p.id
        return None

    def end_round(self):
        """Discard all remaining hands."""
        for p in self.players:
            for card in p.hand:
                self.crate.add_to_bottom(card)
            p.hand = []
        self._log(f"Round {self.round_number} ended. "
                  f"Scores: {', '.join(f'P{p.id}={p.vp}' for p in self.players)}")

    def get_legal_plays(self, player: Player, led_faction: Optional[str]) -> List[Card]:
        if led_faction is None:
            return list(player.hand)
        on_suit = player.cards_of_faction(led_faction)
        return on_suit if on_suit else list(player.hand)

    def _log(self, msg: str):
        self.log.append(msg)

    @staticmethod
    def load_config(config_path: Optional[str] = None) -> dict:
        if config_path is None:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            config_path = os.path.join(script_dir, "config.json")
        with open(config_path, 'r') as f:
            return json.load(f)
