"""
Heist Heat — Game State Machine

Full game state including vault grid, Heat track, faction powers,
chain reactions, getaway mechanic, and pattern-based scoring.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict, Set
from collections import Counter
from itertools import combinations
import random
import json
import os

from cards import Card, Deck, VaultGrid, build_full_deck


@dataclass
class Player:
    """A single player's state within a round."""
    id: int
    hand: List[Card] = field(default_factory=list)
    stash: List[Card] = field(default_factory=list)        # Claimed loot this round
    secured_stash: List[Card] = field(default_factory=list) # Secured after getaway
    got_away: bool = False
    busted: bool = False
    faction_powers_used: Set[str] = field(default_factory=set)  # Factions used this round
    round_scores: List[int] = field(default_factory=list)

    @property
    def total_score(self) -> int:
        return sum(self.round_scores)

    @property
    def active(self) -> bool:
        """Can still take actions this round."""
        return not self.got_away and not self.busted

    @property
    def hand_size(self) -> int:
        return len(self.hand)

    def reset_for_round(self):
        """Reset per-round state."""
        self.stash = []
        self.secured_stash = []
        self.got_away = False
        self.busted = False
        self.faction_powers_used = set()

    def __repr__(self):
        status = "SAFE" if self.got_away else ("BUST" if self.busted else "IN")
        return (f"P{self.id}[{status} Score:{self.total_score} "
                f"Hand:{len(self.hand)} Stash:{len(self.stash)}]")


class GameState:
    """
    Full Heist Heat game state.

    A game consists of multiple rounds. Each round:
    - Vault is dealt, Heat starts at 0
    - Players take turns cracking or getting away
    - Round ends when Heat >= heat_end or vault is empty
    - Busted players lose stash; safe players score
    """

    def __init__(self, config: dict, num_players: int, seed: int = None):
        self.config = config
        self.rules = config["game_rules"]
        self.num_players = num_players
        self.rng = random.Random(seed)
        self.seed = seed
        self.pkey = f"{num_players}_player"

        # Game-level state
        self.players: List[Player] = [Player(id=i) for i in range(num_players)]
        self.current_round: int = 0
        self.total_rounds: int = self.rules["rounds_per_game"]
        self.game_over: bool = False

        # Round-level state (set in setup_round)
        self.vault: Optional[VaultGrid] = None
        self.heat: int = 0
        self.heat_end: int = self.rules["heat_end"]
        self.heat_getaway: int = self.rules["heat_getaway"][self.pkey]
        self.current_player_idx: int = 0
        self.round_over: bool = False
        self.discard_pile: List[Card] = []

        # Full deck
        self.full_deck: List[Card] = build_full_deck()

        # Logging
        self.log: List[str] = []

        # Metrics
        self.metrics: Dict = {
            "cracks_attempted": [0] * num_players,
            "cracks_succeeded": [0] * num_players,
            "cracks_failed": [0] * num_players,
            "chains_triggered": [0] * num_players,
            "chain_lengths": [],
            "cards_claimed": [0] * num_players,
            "getaways": [0] * num_players,
            "busts": [0] * num_players,
            "faction_powers_used": [Counter() for _ in range(num_players)],
            "heat_per_round": [],
            "round_lengths": [],
            "alarms_hit": 0,
            "vault_empty_ends": 0,
            "heat_cap_ends": 0,
        }

    def _log(self, msg: str):
        self.log.append(msg)

    # ── Setup ───────────────────────────────────────────────────────

    def setup_round(self):
        """Set up a new round: shuffle, deal vault and hands."""
        self.current_round += 1
        self.heat = 0
        self.round_over = False
        self.discard_pile = []

        # Rotate starting player each round
        if self.rules.get("rotate_start_player", False):
            self.current_player_idx = (self.current_round - 1) % self.num_players
        else:
            self.current_player_idx = 0

        # Reset player round state
        for p in self.players:
            p.reset_for_round()

        # Shuffle full deck
        deck = Deck(list(self.full_deck))
        deck.shuffle(self.rng)

        # Deal vault grid
        grid_dims = self.rules["vault_grid"][self.pkey]
        rows, cols = grid_dims[0], grid_dims[1]
        vault_cards = deck.draw(rows * cols)
        self.vault = VaultGrid(rows, cols)
        self.vault.place(vault_cards)

        # Deal hands
        hand_size = self.rules["hand_size"][self.pkey]
        for p in self.players:
            p.hand = deck.draw(hand_size)

        # Remaining cards not used this round (used for Purple draw)
        self._remaining_deck = deck

        self._log(f"=== Round {self.current_round} Start (P{self.current_player_idx} leads) ===")
        self._log(f"Vault: {rows}x{cols} ({rows * cols} cards), "
                  f"Hands: {hand_size} cards each")

    # ── Core Actions ────────────────────────────────────────────────

    def get_current_player(self) -> Player:
        return self.players[self.current_player_idx]

    def get_active_players(self) -> List[Player]:
        """Players who can still act this round."""
        return [p for p in self.players if p.active]

    def action_crack(self, player: Player, target_row: int, target_col: int,
                     hand_card_idx: int, use_faction_power: bool = False) -> dict:
        """
        Attempt to crack a vault card.

        Returns dict with success, cards_claimed, heat_added, chain info, etc.
        """
        # Validate
        if not player.active:
            return {"success": False, "error": "Player not active"}
        if hand_card_idx >= len(player.hand):
            return {"success": False, "error": "Invalid hand card index"}
        if self.vault.get(target_row, target_col) is None:
            return {"success": False, "error": "No card at that position"}

        played_card = player.hand[hand_card_idx]
        self.metrics["cracks_attempted"][player.id] += 1

        # Handle faction power (before reveal)
        power_used = None
        effective_rank = played_card.rank

        if use_faction_power and played_card.faction not in player.faction_powers_used:
            power_used = played_card.faction
            player.faction_powers_used.add(played_card.faction)
            self.metrics["faction_powers_used"][player.id][played_card.faction] += 1

            if played_card.faction == "GREEN":
                # Inside Man: peek at up to 3 face-down cards
                face_down = self.vault.face_down_positions()
                peek_count = min(self.rules["green_peek_count"], len(face_down))
                peek_positions = self.rng.sample(face_down, peek_count) if face_down else []
                peek_cards = [(r, c, self.vault.get(r, c)) for r, c in peek_positions]
                # Return peek info — AI will use this to possibly change target
                return {
                    "success": True,
                    "action": "green_peek",
                    "power_used": "GREEN",
                    "peek_results": peek_cards,
                    "played_card": played_card,
                    "hand_card_idx": hand_card_idx,
                }

            elif played_card.faction == "ORANGE":
                # Lucky Guess: peek at target before committing
                vault_card = self.vault.get(target_row, target_col)
                return {
                    "success": True,
                    "action": "orange_peek",
                    "power_used": "ORANGE",
                    "target_card": vault_card,
                    "target_pos": (target_row, target_col),
                    "played_card": played_card,
                    "hand_card_idx": hand_card_idx,
                }

            elif played_card.faction == "BLUE":
                # Sleight of Hand: steal from opponent instead of cracking
                return self._action_blue_steal(player, played_card, hand_card_idx)

            elif played_card.faction == "RED":
                # Power Through: +2 rank
                effective_rank = played_card.rank + self.rules["red_power_bonus"]

            elif played_card.faction == "PURPLE":
                # Time Rewind handled on failure below
                pass

            elif played_card.faction == "YELLOW":
                # Perfect Fit handled on exact match below
                pass

        # Reveal the vault card
        vault_card = self.vault.reveal(target_row, target_col)

        # Compare ranks
        if effective_rank >= vault_card.rank:
            # SUCCESS
            return self._resolve_crack_success(
                player, played_card, hand_card_idx, vault_card,
                target_row, target_col, effective_rank, power_used
            )
        else:
            # FAILURE
            return self._resolve_crack_failure(
                player, played_card, hand_card_idx, vault_card,
                target_row, target_col, power_used
            )

    def _resolve_crack_success(self, player: Player, played_card: Card,
                                hand_card_idx: int, vault_card: Card,
                                row: int, col: int, effective_rank: int,
                                power_used: Optional[str]) -> dict:
        """Handle a successful crack including chain reactions."""
        # Remove played card from hand
        player.hand.pop(hand_card_idx)
        self.discard_pile.append(played_card)

        # Claim the target card
        self.vault.remove(row, col)
        claimed = [vault_card]
        alarm_hit = vault_card.is_alarm

        # Chain reaction
        yellow_tolerance = self.rules.get("yellow_rank_tolerance", 0)
        yellow_perfect_fit = (power_used == "YELLOW" and
                              abs(played_card.rank - vault_card.rank) <= yellow_tolerance)

        chain_claimed = self._chain_reaction(
            row, col, effective_rank, yellow_perfect_fit
        )
        claimed.extend(chain_claimed)

        # Check for alarms in chain
        for c in chain_claimed:
            if c.is_alarm:
                alarm_hit = True

        # Add to stash
        player.stash.extend(claimed)
        self.metrics["cracks_succeeded"][player.id] += 1
        self.metrics["cards_claimed"][player.id] += len(claimed)
        if len(claimed) > 1:
            self.metrics["chains_triggered"][player.id] += 1
            self.metrics["chain_lengths"].append(len(claimed))

        # Calculate heat from highest claimed card
        highest_rank = max(c.rank for c in claimed)
        heat_added = self._heat_for_rank(highest_rank)

        # Alarm extra heat (already included in heat_for_rank for rank 0,
        # but alarms revealed during chain also add heat)
        alarm_count = sum(1 for c in claimed if c.is_alarm)
        if alarm_count > 0:
            self.metrics["alarms_hit"] += alarm_count
            # The highest_rank heat already covers one alarm if it's rank 0
            # Additional alarms in chain add +3 each
            if highest_rank != 0 and alarm_count > 0:
                heat_added += self.rules["alarm_extra_heat"] * alarm_count
            elif alarm_count > 1:
                heat_added += self.rules["alarm_extra_heat"] * (alarm_count - 1)

        self.heat += heat_added

        self._log(f"P{player.id} CRACKS {vault_card!r} at ({row},{col}) "
                  f"with {played_card!r} (eff.rank={effective_rank})")
        self._log(f"  Claimed {len(claimed)} cards, Heat +{heat_added} "
                  f"(now {self.heat})")

        # Check round end conditions
        if self.heat >= self.heat_end:
            self.round_over = True
            self.metrics["heat_cap_ends"] += 1
        if self.vault.empty:
            self.round_over = True
            self.metrics["vault_empty_ends"] += 1

        return {
            "success": True,
            "action": "crack",
            "cracked": True,
            "played_card": played_card,
            "vault_card": vault_card,
            "claimed": claimed,
            "chain_length": len(claimed),
            "heat_added": heat_added,
            "total_heat": self.heat,
            "power_used": power_used,
            "round_over": self.round_over,
            "alarm_hit": alarm_hit,
        }

    def _chain_reaction(self, start_row: int, start_col: int,
                        effective_rank: int, ignore_rank: bool) -> List[Card]:
        """
        Chain reaction: claim orthogonally adjacent cards with rank <= effective_rank.
        Alarms stop chains. Chain cap limits total chained cards.
        Returns list of chained cards (not including the original).
        """
        chain_cap = self.rules.get("chain_cap", 999)  # Default: no cap
        claimed = []
        visited = {(start_row, start_col)}
        frontier = [(start_row, start_col)]

        while frontier:
            if len(claimed) >= chain_cap:
                break
            next_frontier = []
            for r, c in frontier:
                if len(claimed) >= chain_cap:
                    break
                for nr, nc in self.vault.orthogonal_neighbors(r, c):
                    if len(claimed) >= chain_cap:
                        break
                    if (nr, nc) in visited:
                        continue
                    visited.add((nr, nc))

                    card = self.vault.get(nr, nc)
                    if card is None:
                        continue

                    # Reveal the card (flip face-up)
                    self.vault.reveal(nr, nc)

                    if ignore_rank or card.rank <= effective_rank:
                        # Claim it
                        if card.is_alarm:
                            # Alarms are claimed but DON'T chain further
                            self.vault.remove(nr, nc)
                            claimed.append(card)
                            # Don't add to frontier — alarms stop chains
                        else:
                            self.vault.remove(nr, nc)
                            claimed.append(card)
                            next_frontier.append((nr, nc))
                    # If card rank > effective_rank, it stays (now face-up)
            frontier = next_frontier

        return claimed

    def _resolve_crack_failure(self, player: Player, played_card: Card,
                                hand_card_idx: int, vault_card: Card,
                                row: int, col: int,
                                power_used: Optional[str]) -> dict:
        """Handle a failed crack."""
        self.metrics["cracks_failed"][player.id] += 1

        # Purple Time Rewind: get card back + draw a card
        if power_used == "PURPLE":
            drawn_card = None
            if self.rules.get("purple_draw_on_rewind", False):
                if not self._remaining_deck.empty:
                    drawn_card = self._remaining_deck.draw_one()
                    player.hand.append(drawn_card)
            self._log(f"P{player.id} FAILS crack at ({row},{col}) but "
                      f"Purple TIME REWIND saves {played_card!r}"
                      + (f" and draws {drawn_card!r}" if drawn_card else ""))
            return {
                "success": True,
                "action": "crack",
                "cracked": False,
                "purple_rewind": True,
                "purple_drew": drawn_card,
                "played_card": played_card,
                "vault_card": vault_card,
                "heat_added": 0,
                "total_heat": self.heat,
                "power_used": "PURPLE",
                "round_over": self.round_over,
            }

        # Normal failure: discard played card
        player.hand.pop(hand_card_idx)
        self.discard_pile.append(played_card)

        # Vault card stays face-up
        # Faction penalty: if played card rank 8+, add +1 Heat
        heat_added = 0
        if played_card.rank >= self.rules["fail_high_card_heat_threshold"]:
            heat_added = self.rules["fail_high_card_heat_penalty"]
            self.heat += heat_added

        self._log(f"P{player.id} FAILS crack at ({row},{col}): "
                  f"{played_card!r} < {vault_card!r}"
                  + (f" (+{heat_added} Heat penalty)" if heat_added else ""))

        if self.heat >= self.heat_end:
            self.round_over = True
            self.metrics["heat_cap_ends"] += 1

        return {
            "success": True,
            "action": "crack",
            "cracked": False,
            "played_card": played_card,
            "vault_card": vault_card,
            "heat_added": heat_added,
            "total_heat": self.heat,
            "power_used": power_used,
            "round_over": self.round_over,
        }

    def _action_blue_steal(self, player: Player, played_card: Card,
                            hand_card_idx: int) -> dict:
        """Blue Sleight of Hand: steal 1 random card from an opponent's stash."""
        # Find valid targets (opponents with 2+ stash cards)
        targets = [p for p in self.players
                   if p.id != player.id and len(p.stash) >= self.rules["blue_steal_min_stash"]]

        if not targets:
            # No valid targets; power is wasted but card is still played
            player.hand.pop(hand_card_idx)
            self.discard_pile.append(played_card)
            self._log(f"P{player.id} uses Blue STEAL but no valid targets")
            return {
                "success": True,
                "action": "blue_steal",
                "stolen": False,
                "played_card": played_card,
                "power_used": "BLUE",
                "heat_added": 0,
                "total_heat": self.heat,
                "round_over": self.round_over,
            }

        # Pick a random target and steal
        target = self.rng.choice(targets)
        stolen_idx = self.rng.randrange(len(target.stash))
        stolen_card = target.stash.pop(stolen_idx)
        player.stash.append(stolen_card)

        player.hand.pop(hand_card_idx)
        self.discard_pile.append(played_card)

        self._log(f"P{player.id} uses Blue STEAL on P{target.id}: "
                  f"took {stolen_card!r}")

        return {
            "success": True,
            "action": "blue_steal",
            "stolen": True,
            "stolen_card": stolen_card,
            "target_player": target.id,
            "played_card": played_card,
            "power_used": "BLUE",
            "heat_added": 0,
            "total_heat": self.heat,
            "round_over": self.round_over,
        }

    def action_getaway(self, player: Player) -> dict:
        """Player escapes with their stash."""
        if not player.active:
            return {"success": False, "error": "Player not active"}
        if self.heat < self.heat_getaway:
            return {"success": False, "error": f"Heat {self.heat} < {self.heat_getaway}"}

        player.got_away = True
        player.secured_stash = list(player.stash)
        self.metrics["getaways"][player.id] += 1

        self._log(f"P{player.id} GETAWAY with {len(player.stash)} cards!")

        # Check if all players have gotten away or busted
        if not self.get_active_players():
            self.round_over = True

        return {
            "success": True,
            "action": "getaway",
            "stash_size": len(player.secured_stash),
            "heat": self.heat,
        }

    # ── Heat Helpers ────────────────────────────────────────────────

    def _heat_for_rank(self, rank: int) -> int:
        return self.rules["heat_by_rank"].get(str(rank), 2)

    # ── Turn Management ─────────────────────────────────────────────

    def advance_turn(self):
        """Move to the next active player."""
        for _ in range(self.num_players):
            self.current_player_idx = (
                (self.current_player_idx + 1) % self.num_players
            )
            if self.players[self.current_player_idx].active:
                return
        # No active players left
        self.round_over = True

    def can_player_act(self, player: Player) -> bool:
        """Can this player take any action?"""
        if not player.active:
            return False
        if player.hand_size == 0 and self.heat < self.heat_getaway:
            return False  # No cards and can't getaway
        return True

    # ── Round End ───────────────────────────────────────────────────

    def end_round(self) -> dict:
        """Resolve end of round: bust players, score safe players.

        Per rules: if vault is empty, NO ONE is busted — all stashes score.
        If heat hit 10, anyone who didn't getaway is busted.
        """
        vault_empty = self.vault.empty
        round_results = {
            "round": self.current_round,
            "final_heat": self.heat,
            "vault_empty": vault_empty,
            "player_results": [],
        }

        # Final round scoring multiplier
        multipliers = self.rules.get("round_score_multipliers", None)
        multiplier = 1.0
        if multipliers and self.current_round <= len(multipliers):
            multiplier = multipliers[self.current_round - 1]

        for p in self.players:
            if p.got_away:
                # Already secured via getaway
                raw_score = self.score_stash(p.secured_stash)
                score = int(raw_score * multiplier)
                p.round_scores.append(score)
                round_results["player_results"].append({
                    "player": p.id,
                    "status": "safe",
                    "stash_size": len(p.secured_stash),
                    "score": score,
                })
                self._log(f"P{p.id} SAFE (getaway) — scored {score} points "
                          f"from {len(p.secured_stash)} cards"
                          + (f" (x{multiplier})" if multiplier != 1.0 else ""))
            elif vault_empty:
                # Vault emptied — everyone still inside scores their stash
                raw_score = self.score_stash(p.stash)
                score = int(raw_score * multiplier)
                p.round_scores.append(score)
                round_results["player_results"].append({
                    "player": p.id,
                    "status": "safe_vault_empty",
                    "stash_size": len(p.stash),
                    "score": score,
                })
                self._log(f"P{p.id} SAFE (vault empty) — scored {score} points "
                          f"from {len(p.stash)} cards"
                          + (f" (x{multiplier})" if multiplier != 1.0 else ""))
            else:
                # Heat cap — busted!
                p.busted = True
                p.round_scores.append(0)
                self.metrics["busts"][p.id] += 1
                round_results["player_results"].append({
                    "player": p.id,
                    "status": "busted",
                    "stash_size": len(p.stash),
                    "score": 0,
                })
                self._log(f"P{p.id} BUSTED — lost {len(p.stash)} cards!")

        self.metrics["heat_per_round"].append(self.heat)

        return round_results

    # ── Scoring ─────────────────────────────────────────────────────

    @staticmethod
    def score_stash(stash: List[Card]) -> int:
        """
        Score a stash using pattern matching.
        Each card can only count toward one pattern.

        Alarm penalty (per rules example): score patterns normally with all
        non-alarm cards, but the highest-rank card loses its high-card bonus.
        """
        if not stash:
            return 0

        non_alarm = [c for c in stash if not c.is_alarm]
        has_alarm = any(c.is_alarm for c in stash)

        if not non_alarm:
            return 0

        # Score patterns on all non-alarm cards
        # The alarm penalty cancels the high-card bonus for the highest card
        penalized_card_rank = -1
        if has_alarm and non_alarm:
            penalized_card_rank = max(c.rank for c in non_alarm)

        return GameState._best_pattern_score(non_alarm, penalized_card_rank)

    @staticmethod
    def _best_pattern_score(cards: List[Card], penalized_rank: int = -1) -> int:
        """Find the highest-scoring assignment of cards to patterns."""
        if not cards:
            return 0

        return GameState._greedy_score(cards, penalized_rank)

    @staticmethod
    def _greedy_score(cards: List[Card], penalized_rank: int = -1) -> int:
        """Greedy scoring: try patterns from most valuable down.

        penalized_rank: if >= 0, ONE card at this rank loses high-card bonus
        (alarm penalty).
        """
        used = [False] * len(cards)
        total = 0

        # 1. Try Rainbow (5 different factions) — 10 points
        total += GameState._try_rainbows(cards, used)

        # 2. Try Triple Rank (3 same rank) — 7 points
        total += GameState._try_triple_rank(cards, used)

        # 3. Try Sequence (3 consecutive ranks) — 6 points
        total += GameState._try_sequences(cards, used)

        # 4. Try Triple Faction (3 same faction) — 5 points
        total += GameState._try_triple_faction(cards, used)

        # 5. Try Pairs (2 same faction) — 2 points
        total += GameState._try_pairs(cards, used)

        # 6. High card bonus: each rank 8+ card gets +1 (regardless of pattern use)
        #    Alarm penalty: one card at penalized_rank loses this bonus
        penalty_applied = False
        for i, c in enumerate(cards):
            if c.rank >= 8:
                if penalized_rank >= 0 and c.rank == penalized_rank and not penalty_applied:
                    penalty_applied = True  # Skip this card's bonus
                else:
                    total += 1

        return total

    @staticmethod
    def _try_rainbows(cards: List[Card], used: List[bool]) -> int:
        """Find sets of 5 cards with all different factions."""
        score = 0
        available = [(i, c) for i, c in enumerate(cards) if not used[i]]

        # Group by faction
        by_faction: Dict[str, List[Tuple[int, Card]]] = {}
        for i, c in available:
            by_faction.setdefault(c.faction, []).append((i, c))

        factions_available = [f for f in by_faction if len(by_faction[f]) > 0]
        if len(factions_available) >= 5:
            # Pick one card per faction (prefer lower rank to save high cards)
            for combo_factions in combinations(factions_available, 5):
                indices = []
                for f in combo_factions:
                    candidates = [(i, c) for i, c in by_faction[f] if not used[i]]
                    if not candidates:
                        break
                    # Pick lowest rank
                    best = min(candidates, key=lambda x: x[1].rank)
                    indices.append(best[0])
                else:
                    for idx in indices:
                        used[idx] = True
                    score += 10
                    break  # Only score one rainbow per attempt

        return score

    @staticmethod
    def _try_triple_rank(cards: List[Card], used: List[bool]) -> int:
        score = 0
        by_rank: Dict[int, List[int]] = {}
        for i, c in enumerate(cards):
            if not used[i]:
                by_rank.setdefault(c.rank, []).append(i)

        for rank in sorted(by_rank, reverse=True):
            indices = [i for i in by_rank[rank] if not used[i]]
            while len(indices) >= 3:
                for idx in indices[:3]:
                    used[idx] = True
                score += 7
                indices = indices[3:]

        return score

    @staticmethod
    def _try_sequences(cards: List[Card], used: List[bool]) -> int:
        score = 0
        available = [(i, c) for i, c in enumerate(cards) if not used[i]]
        if len(available) < 3:
            return 0

        # Sort by rank
        available.sort(key=lambda x: x[1].rank)
        ranks_present = sorted(set(c.rank for _, c in available))

        # Find consecutive runs of 3+
        for start_idx in range(len(ranks_present) - 2):
            r1, r2, r3 = ranks_present[start_idx], ranks_present[start_idx + 1], ranks_present[start_idx + 2]
            if r2 == r1 + 1 and r3 == r2 + 1:
                # Find unused cards for each rank
                idx1 = next((i for i, c in enumerate(cards) if not used[i] and c.rank == r1), None)
                idx2 = next((i for i, c in enumerate(cards) if not used[i] and c.rank == r2), None)
                idx3 = next((i for i, c in enumerate(cards) if not used[i] and c.rank == r3), None)
                if idx1 is not None and idx2 is not None and idx3 is not None:
                    used[idx1] = True
                    used[idx2] = True
                    used[idx3] = True
                    score += 6

        return score

    @staticmethod
    def _try_triple_faction(cards: List[Card], used: List[bool]) -> int:
        score = 0
        by_faction: Dict[str, List[int]] = {}
        for i, c in enumerate(cards):
            if not used[i]:
                by_faction.setdefault(c.faction, []).append(i)

        for faction in by_faction:
            indices = [i for i in by_faction[faction] if not used[i]]
            while len(indices) >= 3:
                for idx in indices[:3]:
                    used[idx] = True
                score += 5
                indices = indices[3:]

        return score

    @staticmethod
    def _try_pairs(cards: List[Card], used: List[bool]) -> int:
        score = 0
        by_faction: Dict[str, List[int]] = {}
        for i, c in enumerate(cards):
            if not used[i]:
                by_faction.setdefault(c.faction, []).append(i)

        for faction in by_faction:
            indices = [i for i in by_faction[faction] if not used[i]]
            while len(indices) >= 2:
                for idx in indices[:2]:
                    used[idx] = True
                score += 2
                indices = indices[2:]

        return score

    # ── Full Game Loop (for external use) ───────────────────────────

    def is_game_over(self) -> bool:
        return self.game_over

    def finish_game(self):
        """Mark game as finished."""
        self.game_over = True

    def get_winner(self) -> Tuple[int, int]:
        """Return (winner_id, score). Tiebreak by getaways, then cards."""
        best = max(
            self.players,
            key=lambda p: (
                p.total_score,
                self.metrics["getaways"][p.id],
                self.metrics["cards_claimed"][p.id],
            )
        )
        return best.id, best.total_score

    def get_scores(self) -> List[int]:
        return [p.total_score for p in self.players]
