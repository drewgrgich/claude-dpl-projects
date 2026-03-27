"""
Game state machine for Tailgate Turf War v3.0 (Streamlined Edition).

Simplified rules:
  - Strength = highest card + 2 per extra card + 3 if best card matches zone color
  - Mascot (0) doubles best paired card's rank
  - No mishaps, no multipliers, no bonus VP conditions
  - 3 rounds, VP per zone: 3/5/7
"""

import math
import random
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional, Callable
from collections import defaultdict

from cards import Card, Deck, FACTIONS, FACTION_ORDER, build_full_deck


@dataclass
class DeckConfig:
    """Configuration for a custom deck distribution."""
    factions: List[str] = field(default_factory=lambda: list(FACTIONS))
    ranks_per_faction: List[int] = field(default_factory=lambda: list(range(0, 11)))
    hand_sizes: Dict[int, int] = field(default_factory=dict)
    label: str = "default"

    @property
    def total_cards(self) -> int:
        return len(self.factions) * len(self.ranks_per_faction)

    @property
    def max_rank(self) -> int:
        return max(self.ranks_per_faction) if self.ranks_per_faction else 10

    @property
    def has_mascot(self) -> bool:
        return 0 in self.ranks_per_faction


@dataclass
class Player:
    id: int
    hand: List[Card] = field(default_factory=list)
    score: int = 0
    zones_won_this_round: int = 0
    total_zones_won: int = 0
    cards_played_total: int = 0

    def __repr__(self):
        return f"P{self.id}(VP:{self.score} Hand:{len(self.hand)})"


@dataclass
class ZonePlacement:
    player_id: int
    cards: List[Card] = field(default_factory=list)


@dataclass
class Zone:
    faction: str
    placements: Dict[int, ZonePlacement] = field(default_factory=dict)

    def get_placement(self, player_id: int) -> ZonePlacement:
        if player_id not in self.placements:
            self.placements[player_id] = ZonePlacement(player_id=player_id)
        return self.placements[player_id]

    @property
    def active_players(self) -> List[int]:
        return [pid for pid, zp in self.placements.items() if zp.cards]


class GameStateV3:
    def __init__(self, num_players: int, seed: int = 42,
                 hand_sizes: dict = None, zone_vp: list = None,
                 home_field_bonus: int = 3, extra_card_bonus: int = 2,
                 deck_config: 'DeckConfig' = None):
        self.num_players = num_players
        self.rng = random.Random(seed)
        self.seed = seed

        # Deck configuration
        self.deck_config = deck_config or DeckConfig()
        self.factions = self.deck_config.factions
        self.faction_order = {f: i for i, f in enumerate(self.factions)}

        # Tunable parameters
        self.home_field_bonus = home_field_bonus
        self.extra_card_bonus = extra_card_bonus
        self.num_rounds = 3
        self.zone_vp = zone_vp or [5, 5, 5]

        # Hand sizes — compute from deck size if not provided
        total_cards = self.deck_config.total_cards
        default_hand_sizes = {2: 18, 3: 15, 4: 13, 5: 11}
        # Auto-scale hand sizes for non-standard decks
        if total_cards != 66:
            for p in range(2, 6):
                # Deal ~70% of deck, split evenly
                default_hand_sizes[p] = int(total_cards * 0.70 / p)
        if self.deck_config.hand_sizes:
            default_hand_sizes.update(self.deck_config.hand_sizes)
        if hand_sizes:
            default_hand_sizes.update(hand_sizes)
        hand_size = default_hand_sizes[num_players]

        # Build and shuffle deck
        all_cards = build_full_deck(
            factions=self.deck_config.factions,
            ranks_per_faction=self.deck_config.ranks_per_faction
        )
        self.rng.shuffle(all_cards)

        # Deal hands
        self.players: List[Player] = []
        idx = 0
        for i in range(num_players):
            hand = all_cards[idx:idx + hand_size]
            self.players.append(Player(id=i, hand=hand))
            idx += hand_size

        self.unused_cards = all_cards[idx:]
        self.current_round = 0
        self.game_over = False
        self.zones: List[Zone] = []
        self.log: List[str] = []

        # Stats
        self.stats = {
            "rounds": [],
            "zone_wins": defaultdict(lambda: defaultdict(int)),
            "strength_values": [],
            "cards_per_zone": [],
            "home_field_triggers": 0,
            "mascot_combos": 0,
        }

    def play_game(self, deployment_fn: Callable) -> dict:
        for round_num in range(self.num_rounds):
            self.current_round = round_num
            round_stats = self._play_round(round_num, deployment_fn)
            self.stats["rounds"].append(round_stats)

        self.game_over = True
        return self._compile_final_stats()

    def _play_round(self, round_num: int, deployment_fn: Callable) -> dict:
        vp_per_zone = self.zone_vp[round_num]
        self._log(f"\n{'='*50}")
        self._log(f"ROUND {round_num + 1} (VP per zone: {vp_per_zone})")

        for p in self.players:
            p.zones_won_this_round = 0

        self.zones = [Zone(faction=f) for f in self.factions]

        # DEPLOY
        for player in self.players:
            deploy = deployment_fn(player, self, round_num)
            self._execute_deployment(player, deploy)

        # REVEAL
        self._log("\n--- REVEAL ---")
        for zone in self.zones:
            for pid in zone.active_players:
                zp = zone.get_placement(pid)
                self._log(f"  {zone.faction}: P{pid} played {zp.cards}")

        # SCORE
        zone_strengths = self._calculate_all_strength()
        round_stats = self._score_round(zone_strengths, vp_per_zone)

        self._log(f"\nScores after Round {round_num + 1}: " +
                  ", ".join(f"P{p.id}={p.score}" for p in self.players))
        return round_stats

    def _execute_deployment(self, player: Player, deploy: Dict[str, List[Card]]):
        for faction, cards in deploy.items():
            if not cards:
                continue
            zone = self._get_zone(faction)
            zp = zone.get_placement(player.id)
            for card in cards:
                if card not in player.hand:
                    continue
                player.hand.remove(card)
                zp.cards.append(card)
                player.cards_played_total += 1
            self.stats["cards_per_zone"].append(len(zp.cards))

    def _calculate_all_strength(self) -> Dict[str, Dict[int, float]]:
        self._log("\n--- STRENGTH CALCULATION ---")
        zone_strengths: Dict[str, Dict[int, float]] = {}

        for zone in self.zones:
            zone_strengths[zone.faction] = {}
            for pid in zone.active_players:
                zp = zone.get_placement(pid)
                if not zp.cards:
                    zone_strengths[zone.faction][pid] = 0
                    continue

                strength = self._calculate_strength(zp.cards, zone.faction)
                zone_strengths[zone.faction][pid] = strength
                self.stats["strength_values"].append(strength)
                self._log(f"  {zone.faction}: P{pid} → {strength} Strength "
                          f"({len(zp.cards)} cards)")

        return zone_strengths

    def _calculate_strength(self, cards: List[Card], zone_faction: str) -> int:
        """
        Strength = highest card rank + 2 per extra card + 3 if best matches zone.
        Mascot (0): doubles best paired card's rank.
        """
        if not cards:
            return 0

        mascots = [c for c in cards if c.is_mascot]
        non_mascots = [c for c in cards if not c.is_mascot]

        if not non_mascots:
            # All mascots — worth 0
            return 0

        best_card = max(non_mascots, key=lambda c: c.rank)
        best_rank = best_card.rank

        # Mascot doubling
        if mascots:
            best_rank *= 2
            self.stats["mascot_combos"] += 1
            # The mascot's contribution is the doubling — it doesn't add +2
            extra_cards = len(cards) - 2  # subtract best card and mascot
        else:
            extra_cards = len(cards) - 1  # subtract best card

        extra_bonus = max(0, extra_cards) * self.extra_card_bonus

        # Home Field Advantage (Anchor Rule):
        # Requires at least one NATURAL card (ranks 1-9) matching the zone color.
        # Mascots (0) and Superstars (10) don't count as anchors.
        home_field = 0
        has_matching_natural = any(
            c.faction == zone_faction and c.is_natural
            for c in cards
        )
        if has_matching_natural:
            home_field = self.home_field_bonus
            self.stats["home_field_triggers"] += 1

        return best_rank + extra_bonus + home_field

    def _score_round(self, zone_strengths: Dict[str, Dict[int, float]],
                     vp_per_zone: int) -> dict:
        self._log("\n--- SCORING ---")
        round_stats = {
            "zone_winners": {},
            "vp_awarded": defaultdict(int),
            "strength_by_zone": zone_strengths,
        }

        for faction in self.factions:
            strength_map = zone_strengths.get(faction, {})
            if not strength_map:
                round_stats["zone_winners"][faction] = None
                continue

            max_strength = max(strength_map.values())
            if max_strength <= 0:
                round_stats["zone_winners"][faction] = None
                continue

            winners = [pid for pid, s in strength_map.items() if s == max_strength]

            if len(winners) == 1:
                winner = winners[0]
                self.players[winner].score += vp_per_zone
                self.players[winner].zones_won_this_round += 1
                self.players[winner].total_zones_won += 1
                round_stats["vp_awarded"][winner] += vp_per_zone
                round_stats["zone_winners"][faction] = [winner]
                self.stats["zone_wins"][winner][faction] += 1
                self._log(f"  {faction}: P{winner} wins ({max_strength}) → +{vp_per_zone} VP")
            else:
                split_vp = math.ceil(vp_per_zone / len(winners))
                round_stats["zone_winners"][faction] = winners
                for w in winners:
                    self.players[w].score += split_vp
                    self.players[w].zones_won_this_round += 1
                    self.players[w].total_zones_won += 1
                    round_stats["vp_awarded"][w] += split_vp
                    self.stats["zone_wins"][w][faction] += 1
                self._log(f"  {faction}: TIE {['P'+str(w) for w in winners]} "
                          f"({max_strength}) → +{split_vp} VP each")

        return round_stats

    def _compile_final_stats(self) -> dict:
        scores = {p.id: p.score for p in self.players}
        max_score = max(scores.values())
        winners = [pid for pid, s in scores.items() if s == max_score]

        if len(winners) > 1:
            max_zones = max(self.players[w].total_zones_won for w in winners)
            winners = [w for w in winners if self.players[w].total_zones_won == max_zones]

        self._log(f"\n{'='*50}")
        self._log(f"FINAL: " + ", ".join(f"P{p.id}={p.score}" for p in self.players))

        return {
            "seed": self.seed,
            "num_players": self.num_players,
            "winner": winners[0] if len(winners) == 1 else winners,
            "scores": scores,
            "zones_won": {p.id: p.total_zones_won for p in self.players},
            "cards_played": {p.id: p.cards_played_total for p in self.players},
            "cards_remaining": {p.id: len(p.hand) for p in self.players},
            "hand_value_remaining": {p.id: sum(c.rank for c in p.hand)
                                     for p in self.players},
            "strength_values": self.stats["strength_values"],
            "cards_per_zone_play": self.stats["cards_per_zone"],
            "home_field_triggers": self.stats["home_field_triggers"],
            "mascot_combos": self.stats["mascot_combos"],
            "zone_wins_by_faction": {pid: dict(fw)
                                     for pid, fw in self.stats["zone_wins"].items()},
        }

    def _get_zone(self, faction: str) -> Zone:
        return self.zones[self.faction_order[faction]]

    def _log(self, msg: str):
        self.log.append(msg)
