"""
Game state machine for Tailgate Turf War v2.0.

Implements the full 3-round, 5-phase game loop:
  Phase 1: Deployment (simultaneous card placement)
  Phase 2: Reveal
  Phase 3: Mishaps (ROYGBP order)
  Phase 4: Hype Calculation (Headliner system)
  Phase 5: Scoring (zone control + bonuses)
"""

import math
import random
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional, Callable
from collections import defaultdict

from cards import Card, Deck, FACTIONS, FACTION_ORDER, build_full_deck


# ---------------------------------------------------------------------------
# Player state
# ---------------------------------------------------------------------------

@dataclass
class Player:
    id: int
    hand: List[Card] = field(default_factory=list)
    score: int = 0
    # Cards that MUST be played face-up next round (Purple mishap)
    forced_faceup: List[Card] = field(default_factory=list)

    # Per-round tracking
    zones_won_this_round: int = 0
    total_zones_won: int = 0

    # Lifetime stats
    cards_played_total: int = 0
    underdog_bonuses: int = 0
    sweep_bonuses: int = 0

    def __repr__(self):
        return f"P{self.id}(VP:{self.score} Hand:{len(self.hand)})"


# ---------------------------------------------------------------------------
# Zone state (per round — rebuilt each round)
# ---------------------------------------------------------------------------

@dataclass
class ZonePlacement:
    """One player's cards at one zone."""
    player_id: int
    cards: List[Card] = field(default_factory=list)
    # After mishap resolution
    bonus_value: int = 0        # e.g. Red mishap +2
    stolen_cards: List[Card] = field(default_factory=list)  # Orange mishap
    swapped: bool = False       # Blue mishap applied
    green_taunted: bool = False # Green taunt revealed


@dataclass
class Zone:
    """A single tailgate zone."""
    faction: str
    placements: Dict[int, ZonePlacement] = field(default_factory=dict)

    def get_placement(self, player_id: int) -> ZonePlacement:
        if player_id not in self.placements:
            self.placements[player_id] = ZonePlacement(player_id=player_id)
        return self.placements[player_id]

    @property
    def active_players(self) -> List[int]:
        return [pid for pid, zp in self.placements.items() if zp.cards]


# ---------------------------------------------------------------------------
# Main game state
# ---------------------------------------------------------------------------

class GameState:
    def __init__(self, config: dict, num_players: int, seed: int = 42):
        self.config = config
        self.rules = config["game_rules"]
        self.num_players = num_players
        self.rng = random.Random(seed)
        self.seed = seed
        self.pkey = f"{num_players}_player"

        # Build and shuffle deck
        all_cards = build_full_deck()
        self.rng.shuffle(all_cards)

        # Deal hands
        hand_size = self.rules["hand_sizes"][self.pkey]
        self.players: List[Player] = []
        idx = 0
        for i in range(num_players):
            hand = all_cards[idx:idx + hand_size]
            self.players.append(Player(id=i, hand=hand))
            idx += hand_size

        # Remaining cards are unused (not drawn during game)
        self.unused_cards = all_cards[idx:]

        # Round tracking
        self.current_round = 0   # 0-indexed; incremented at start of each round
        self.game_over = False

        # Zones (rebuilt each round)
        self.zones: List[Zone] = []

        # Logging
        self.log: List[str] = []

        # Stats collection
        self.stats = {
            "rounds": [],
            "zone_wins": defaultdict(lambda: defaultdict(int)),  # player -> faction -> count
            "hype_values": [],       # all hype values computed
            "cards_per_zone": [],    # how many cards each player placed
            "mishap_triggers": defaultdict(int),  # faction -> count
            "underdog_count": 0,
            "sweep_count": 0,
        }

    # ------------------------------------------------------------------
    # Top-level game loop
    # ------------------------------------------------------------------

    def play_game(self, deployment_fn: Callable) -> dict:
        """
        Play a full 3-round game.

        deployment_fn(player, game_state, round_num) -> dict[str, List[Card]]
            Returns {faction: [cards]} mapping zones to cards to play there.
        """
        for round_num in range(self.rules["num_rounds"]):
            self.current_round = round_num
            round_stats = self._play_round(round_num, deployment_fn)
            self.stats["rounds"].append(round_stats)

        # Die-Hard Fan bonus
        self._resolve_diehard_bonus()
        self.game_over = True
        return self._compile_final_stats()

    # ------------------------------------------------------------------
    # Round logic
    # ------------------------------------------------------------------

    def _play_round(self, round_num: int, deployment_fn: Callable) -> dict:
        """Execute all 5 phases for one round."""
        vp_per_zone = self.rules["zone_vp_by_round"][round_num]
        self._log(f"\n{'='*50}")
        self._log(f"ROUND {round_num + 1} (VP per zone: {vp_per_zone})")
        self._log(f"{'='*50}")

        # Reset per-round counters
        for p in self.players:
            p.zones_won_this_round = 0

        # Build fresh zones
        self.zones = [Zone(faction=f) for f in FACTIONS]

        # --- PHASE 1: DEPLOYMENT ---
        all_deployments = {}
        for player in self.players:
            deploy = deployment_fn(player, self, round_num)
            all_deployments[player.id] = deploy
            self._execute_deployment(player, deploy, round_num)

        # --- PHASE 2: REVEAL ---
        self._log("\n--- REVEAL ---")
        for zone in self.zones:
            for pid in zone.active_players:
                zp = zone.get_placement(pid)
                self._log(f"  {zone.faction} Zone: P{pid} played {zp.cards}")

        # --- PHASE 3: MISHAPS ---
        self._resolve_mishaps(round_num)

        # --- PHASE 4: HYPE CALCULATION ---
        zone_hype = self._calculate_all_hype()

        # --- PHASE 5: SCORING ---
        round_stats = self._score_round(zone_hype, vp_per_zone)

        self._log(f"\nScores after Round {round_num + 1}: " +
                  ", ".join(f"P{p.id}={p.score}" for p in self.players))

        return round_stats

    # ------------------------------------------------------------------
    # Phase 1: Deployment
    # ------------------------------------------------------------------

    def _execute_deployment(self, player: Player, deploy: Dict[str, List[Card]],
                            round_num: int):
        """Place cards from hand to zones."""
        for faction, cards in deploy.items():
            if not cards:
                continue
            zone = self._get_zone(faction)
            zp = zone.get_placement(player.id)

            for card in cards:
                if card not in player.hand:
                    self._log(f"  WARNING: P{player.id} tried to play {card} not in hand")
                    continue
                player.hand.remove(card)
                zp.cards.append(card)
                player.cards_played_total += 1

            # Green taunt: if playing a Green card to Green zone, reveal face-up
            if faction == "GREEN":
                green_naturals = [c for c in zp.cards
                                  if c.faction == "GREEN" and c.is_natural]
                if green_naturals:
                    zp.green_taunted = True

            self.stats["cards_per_zone"].append(len(zp.cards))

    # ------------------------------------------------------------------
    # Phase 3: Mishaps
    # ------------------------------------------------------------------

    def _resolve_mishaps(self, round_num: int):
        """Resolve mishaps in ROYGBP order."""
        self._log("\n--- MISHAPS ---")
        for faction in FACTIONS:
            zone = self._get_zone(faction)
            for pid in zone.active_players:
                zp = zone.get_placement(pid)
                # Check if player has a natural card matching zone faction
                has_natural = any(c.faction == faction and c.is_natural
                                  for c in zp.cards)
                if not has_natural:
                    continue

                self.stats["mishap_triggers"][faction] += 1

                if faction == "RED":
                    self._mishap_red(zone, zp)
                elif faction == "ORANGE":
                    self._mishap_orange(zone, zp)
                elif faction == "YELLOW":
                    self._mishap_yellow(zone, zp)
                elif faction == "GREEN":
                    self._mishap_green(zone, zp)
                elif faction == "BLUE":
                    self._mishap_blue(zone, zp)
                elif faction == "PURPLE":
                    self._mishap_purple(zone, zp, pid)

    def _mishap_red(self, zone: Zone, zp: ZonePlacement):
        """Red natural cards gain +2 to base value."""
        bonus = self.rules["mishaps"]["red_bonus"]
        red_naturals = [c for c in zp.cards
                        if c.faction == "RED" and c.is_natural]
        total_bonus = bonus * len(red_naturals)
        zp.bonus_value += total_bonus
        self._log(f"  RED Mishap: P{zp.player_id} red naturals gain +{total_bonus}")

    def _mishap_orange(self, zone: Zone, zp: ZonePlacement):
        """Claim the lowest-value opponent card here as Crew."""
        # Find lowest-value opponent card (natural 1-9 only for fairness)
        lowest_card = None
        lowest_owner = None
        for other_pid in zone.active_players:
            if other_pid == zp.player_id:
                continue
            other_zp = zone.get_placement(other_pid)
            for c in other_zp.cards:
                if lowest_card is None or c.rank < lowest_card.rank:
                    lowest_card = c
                    lowest_owner = other_pid

        if lowest_card and lowest_owner is not None:
            # Remove from opponent and add to this player's placement as crew
            other_zp = zone.get_placement(lowest_owner)
            other_zp.cards.remove(lowest_card)
            zp.stolen_cards.append(lowest_card)
            self._log(f"  ORANGE Mishap: P{zp.player_id} stole {lowest_card} from P{lowest_owner}")

    def _mishap_yellow(self, zone: Zone, zp: ZonePlacement):
        """Yellow Crew cards here provide +4 Hype instead of +2."""
        # This is handled in hype calculation — just flag it
        self._log(f"  YELLOW Mishap: P{zp.player_id} yellow crew cards get +4")

    def _mishap_green(self, zone: Zone, zp: ZonePlacement):
        """Already handled in deployment (taunt). Log only."""
        if zp.green_taunted:
            self._log(f"  GREEN Mishap: P{zp.player_id} taunted (already revealed)")

    def _mishap_blue(self, zone: Zone, zp: ZonePlacement):
        """Swap Blue card's base value with one opponent's natural card."""
        blue_cards = [c for c in zp.cards
                      if c.faction == "BLUE" and c.is_natural]
        if not blue_cards:
            return

        # Find highest opponent natural card to swap with
        best_target = None
        best_owner = None
        for other_pid in zone.active_players:
            if other_pid == zp.player_id:
                continue
            other_zp = zone.get_placement(other_pid)
            for c in other_zp.cards:
                if c.is_natural:
                    if best_target is None or c.rank > best_target.rank:
                        best_target = c
                        best_owner = other_pid

        if best_target and best_owner is not None:
            # Swap ranks of our blue card and their card
            my_blue = max(blue_cards, key=lambda c: c.rank)
            old_my = my_blue.rank
            old_their = best_target.rank
            # We model this as a value swap via bonus tracking
            # Since Cards are shared objects, we track the delta as bonus
            zp.bonus_value += (old_their - old_my)
            zone.get_placement(best_owner).bonus_value += (old_my - old_their)
            zp.swapped = True
            self._log(f"  BLUE Mishap: P{zp.player_id} swapped {my_blue}(val {old_my}) "
                       f"with P{best_owner}'s {best_target}(val {old_their})")

    def _mishap_purple(self, zone: Zone, zp: ZonePlacement, player_id: int):
        """Return Purple card to hand. Must play face-up next round."""
        purple_cards = [c for c in zp.cards
                        if c.faction == "PURPLE" and c.is_natural]
        if not purple_cards:
            return

        # Return the purple natural card to hand
        card = purple_cards[0]  # Return first one
        zp.cards.remove(card)
        player = self.players[player_id]
        player.hand.append(card)
        player.forced_faceup.append(card)
        self._log(f"  PURPLE Mishap: P{player_id} returns {card} to hand (must play face-up next round)")

    # ------------------------------------------------------------------
    # Phase 4: Hype Calculation
    # ------------------------------------------------------------------

    def _calculate_all_hype(self) -> Dict[str, Dict[int, float]]:
        """Calculate hype for every player at every zone.

        Returns {faction: {player_id: hype_value}}.
        """
        self._log("\n--- HYPE CALCULATION ---")
        zone_hype: Dict[str, Dict[int, float]] = {}

        for zone in self.zones:
            zone_hype[zone.faction] = {}
            for pid in zone.active_players:
                zp = zone.get_placement(pid)
                all_cards = zp.cards + zp.stolen_cards
                if not all_cards:
                    zone_hype[zone.faction][pid] = 0
                    continue

                hype = self._calculate_hype(all_cards, zone.faction, zp)
                zone_hype[zone.faction][pid] = hype
                self.stats["hype_values"].append(hype)
                self._log(f"  {zone.faction}: P{pid} → {hype} Hype "
                          f"({len(all_cards)} cards)")

        return zone_hype

    def _calculate_hype(self, cards: List[Card], zone_faction: str,
                        zp: ZonePlacement) -> float:
        """Calculate hype for a set of cards at a zone."""
        if not cards:
            return 0

        total_cards = len(cards)

        # --- Identify Headliner ---
        # Superstar (10) automatically becomes headliner
        superstars = [c for c in cards if c.is_superstar]
        mascots = [c for c in cards if c.is_mascot]
        naturals = [c for c in cards if c.is_natural]

        if superstars:
            headliner_value = self.rules["superstar_hype"]  # 12
            crew_cards = [c for c in cards if c is not superstars[0]]
        elif naturals:
            # Highest natural is headliner
            best_natural = max(naturals, key=lambda c: c.rank)
            headliner_value = best_natural.rank

            # Apply Red mishap bonus to headliner if it's a red natural at red zone
            if zp.bonus_value > 0 and best_natural.faction == "RED" and zone_faction == "RED":
                headliner_value += self.rules["mishaps"]["red_bonus"]

            # Mascot doubles natural headliner
            if mascots and not superstars:
                headliner_value *= 2

            crew_cards = [c for c in cards if c is not best_natural]
            # Remove one mascot from crew if it was used for doubling
            if mascots and not superstars:
                for i, c in enumerate(crew_cards):
                    if c.is_mascot:
                        crew_cards.pop(i)
                        break
        elif mascots:
            # Only mascots, no naturals or superstars
            headliner_value = 0
            crew_cards = cards[1:]  # First mascot is "headliner" at 0
        else:
            headliner_value = 0
            crew_cards = cards[1:]

        # --- Calculate Crew bonus ---
        crew_bonus = 0
        normal_crew_bonus = self.rules["crew_bonus"]  # 2
        yellow_crew_bonus = self.rules["yellow_crew_bonus"]  # 4

        # Check if Yellow mishap is active (player has yellow natural at yellow zone)
        yellow_mishap_active = (zone_faction == "YELLOW" and
                                any(c.faction == "YELLOW" and c.is_natural
                                    for c in zp.cards))

        for c in crew_cards:
            if yellow_mishap_active and c.faction == "YELLOW":
                crew_bonus += yellow_crew_bonus
            else:
                crew_bonus += normal_crew_bonus

        # --- Apply bonus from Blue mishap swap ---
        # bonus_value tracks net change from blue swap and red bonus
        # Red bonus already applied to headliner above for red naturals
        # For blue swap, the bonus_value was set as a delta
        blue_bonus = 0
        if zp.swapped:
            blue_bonus = zp.bonus_value
            # Don't double-count red bonus
            if zone_faction == "RED":
                red_naturals = [c for c in zp.cards if c.faction == "RED" and c.is_natural]
                blue_bonus -= self.rules["mishaps"]["red_bonus"] * len(red_naturals)

        base_hype = headliner_value + crew_bonus + blue_bonus

        # --- Apply multiplier ---
        multiplier = self._get_multiplier(total_cards)
        final_hype = math.ceil(base_hype * multiplier)

        return max(0, final_hype)

    def _get_multiplier(self, card_count: int) -> float:
        """Get hype multiplier based on card count at zone."""
        mults = self.rules["hype_multipliers"]
        if card_count <= 0:
            return 0
        elif card_count == 1:
            return mults["1"]
        elif card_count == 2:
            return mults["2"]
        elif card_count == 3:
            return mults["3"]
        else:
            return mults["4+"]

    # ------------------------------------------------------------------
    # Phase 5: Scoring
    # ------------------------------------------------------------------

    def _score_round(self, zone_hype: Dict[str, Dict[int, float]],
                     vp_per_zone: int) -> dict:
        """Award VP for zone control and bonuses."""
        self._log("\n--- SCORING ---")
        round_stats = {
            "zone_winners": {},
            "vp_awarded": defaultdict(int),
            "hype_by_zone": zone_hype,
        }

        for faction in FACTIONS:
            hype_map = zone_hype.get(faction, {})
            if not hype_map:
                self._log(f"  {faction}: No contestants")
                round_stats["zone_winners"][faction] = None
                continue

            max_hype = max(hype_map.values())
            min_threshold = self.rules.get("min_hype_threshold", 0)
            if max_hype <= 0 or max_hype < min_threshold:
                self._log(f"  {faction}: No one meets hype threshold ({max_hype} < {min_threshold})")
                round_stats["zone_winners"][faction] = None
                continue

            # Filter out players below the threshold
            if min_threshold > 0:
                hype_map = {pid: h for pid, h in hype_map.items()
                            if h >= min_threshold}

            winners = [pid for pid, h in hype_map.items() if h == max_hype]

            if len(winners) == 1:
                winner = winners[0]
                vp = vp_per_zone
                self.players[winner].score += vp
                self.players[winner].zones_won_this_round += 1
                self.players[winner].total_zones_won += 1
                round_stats["vp_awarded"][winner] += vp
                round_stats["zone_winners"][faction] = [winner]
                self.stats["zone_wins"][winner][faction] += 1
                self._log(f"  {faction}: P{winner} wins ({max_hype} Hype) → +{vp} VP")

                # Underdog bonus: win with exactly 1 card vs opponent with 2+
                zone = self._get_zone(faction)
                my_cards = len(zone.get_placement(winner).cards) + len(zone.get_placement(winner).stolen_cards)
                opponent_has_more = any(
                    len(zone.get_placement(pid).cards) + len(zone.get_placement(pid).stolen_cards) >= 2
                    for pid in zone.active_players if pid != winner
                )
                if my_cards == 1 and opponent_has_more:
                    underdog_vp = self.rules["bonuses"]["underdog_vp"]
                    self.players[winner].score += underdog_vp
                    self.players[winner].underdog_bonuses += 1
                    round_stats["vp_awarded"][winner] += underdog_vp
                    self.stats["underdog_count"] += 1
                    self._log(f"    UNDERDOG! P{winner} +{underdog_vp} VP")

                # Green taunt bonus
                if faction == "GREEN":
                    zp = zone.get_placement(winner)
                    if zp.green_taunted:
                        taunt_vp = self.rules["bonuses"]["green_taunt_vp"]
                        self.players[winner].score += taunt_vp
                        round_stats["vp_awarded"][winner] += taunt_vp
                        self._log(f"    GREEN TAUNT! P{winner} +{taunt_vp} VP")

            else:
                # Tie — split VP (round up)
                split_vp = math.ceil(vp_per_zone / len(winners))
                round_stats["zone_winners"][faction] = winners
                for w in winners:
                    self.players[w].score += split_vp
                    self.players[w].zones_won_this_round += 1
                    self.players[w].total_zones_won += 1
                    round_stats["vp_awarded"][w] += split_vp
                    self.stats["zone_wins"][w][faction] += 1
                self._log(f"  {faction}: TIE between {['P'+str(w) for w in winners]} "
                          f"({max_hype} Hype) → +{split_vp} VP each")

        # Sweep bonus: win 3+ zones in a single round
        sweep_threshold = self.rules["bonuses"]["sweep_threshold"]
        sweep_vp = self.rules["bonuses"]["sweep_vp"]
        for player in self.players:
            if player.zones_won_this_round >= sweep_threshold:
                player.score += sweep_vp
                player.sweep_bonuses += 1
                round_stats["vp_awarded"][player.id] += sweep_vp
                self.stats["sweep_count"] += 1
                self._log(f"  SWEEP! P{player.id} won {player.zones_won_this_round} zones → +{sweep_vp} VP")

        return round_stats

    # ------------------------------------------------------------------
    # End game: Die-Hard Fan bonus
    # ------------------------------------------------------------------

    def _resolve_diehard_bonus(self):
        """Player with highest total value of unused cards gets +5 VP."""
        self._log("\n--- DIE-HARD FAN BONUS ---")
        hand_values = {}
        for p in self.players:
            total = sum(c.rank for c in p.hand)
            hand_values[p.id] = total
            self._log(f"  P{p.id}: {len(p.hand)} cards, total value = {total}")

        if not hand_values:
            return

        max_val = max(hand_values.values())
        if max_val == 0:
            self._log("  No one has cards left — no bonus awarded")
            return

        winners = [pid for pid, v in hand_values.items() if v == max_val]
        diehard_vp = self.rules["bonuses"]["diehard_fan_vp"]

        if len(winners) == 1:
            self.players[winners[0]].score += diehard_vp
            self._log(f"  P{winners[0]} wins Die-Hard Fan bonus → +{diehard_vp} VP")
        else:
            # Tie: split (round up)
            split = math.ceil(diehard_vp / len(winners))
            for w in winners:
                self.players[w].score += split
            self._log(f"  TIE for Die-Hard Fan: {['P'+str(w) for w in winners]} → +{split} VP each")

    # ------------------------------------------------------------------
    # Final stats compilation
    # ------------------------------------------------------------------

    def _compile_final_stats(self) -> dict:
        """Compile end-of-game statistics."""
        scores = {p.id: p.score for p in self.players}
        max_score = max(scores.values())
        winners = [pid for pid, s in scores.items() if s == max_score]

        # Tiebreaker: most zones won
        if len(winners) > 1:
            max_zones = max(self.players[w].total_zones_won for w in winners)
            winners = [w for w in winners if self.players[w].total_zones_won == max_zones]

        self._log(f"\n{'='*50}")
        self._log(f"FINAL SCORES: " + ", ".join(f"P{p.id}={p.score}" for p in self.players))
        if len(winners) == 1:
            self._log(f"WINNER: P{winners[0]}!")
        else:
            self._log(f"TIE: {['P'+str(w) for w in winners]}")

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
            "underdog_bonuses": {p.id: p.underdog_bonuses for p in self.players},
            "sweep_bonuses": {p.id: p.sweep_bonuses for p in self.players},
            "mishap_triggers": dict(self.stats["mishap_triggers"]),
            "zone_wins_by_faction": {pid: dict(fw)
                                     for pid, fw in self.stats["zone_wins"].items()},
            "hype_values": self.stats["hype_values"],
            "cards_per_zone_play": self.stats["cards_per_zone"],
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_zone(self, faction: str) -> Zone:
        idx = FACTION_ORDER[faction]
        return self.zones[idx]

    def _log(self, msg: str):
        self.log.append(msg)

    def get_hand_summary(self, player: Player) -> dict:
        """Summarize a player's hand by faction and rank."""
        summary = defaultdict(list)
        for c in player.hand:
            summary[c.faction].append(c.rank)
        return {f: sorted(ranks, reverse=True) for f, ranks in summary.items()}
