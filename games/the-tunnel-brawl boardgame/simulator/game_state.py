"""
Game state machine for The Tunnel Brawl v2.0.

Handles simultaneous deployment, brawl resolution, CLASH! mechanic,
Wild activation (cross-body rule), faction talents, and draw phase.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Tuple, Callable
import random

from cards import Card, Deck, build_deck


@dataclass
class Deployment:
    """A player's card placement for one round."""
    home_card: Optional[Card] = None
    away_card: Optional[Card] = None


@dataclass
class BrawlResult:
    """Result of a single brawl between two cards."""
    attacker_id: int
    defender_id: int
    attacker_card: Card
    defender_card: Card
    attacker_effective_rank: int
    defender_effective_rank: int
    attacker_wild_activated: bool = False
    defender_wild_activated: bool = False
    winner_id: Optional[int] = None  # None = tie
    is_clash: bool = False
    vp_awarded: int = 0
    clash_round: int = 0


@dataclass
class Player:
    """A single player's state."""
    id: int
    hand: List[Card] = field(default_factory=list)
    victory_points: int = 0
    is_defender: bool = False
    forced_card: Optional[Card] = None  # Green talent: forced next deployment

    # Stats tracking
    brawls_won: int = 0
    brawls_lost: int = 0
    clashes_won: int = 0
    clashes_lost: int = 0
    wilds_activated: int = 0
    wilds_tripped: int = 0
    talents_triggered: int = 0
    cards_drawn: int = 0
    dominations: int = 0

    def __repr__(self):
        return f"P{self.id}(VP:{self.victory_points} Hand:{len(self.hand)})"


class GameState:
    """Full state machine for The Tunnel Brawl."""

    def __init__(self, config: dict, num_players: int, seed: int = None):
        self.config = config
        self.rules = config["game_rules"]
        self.num_players = num_players
        self.rng = random.Random(seed)
        self.seed = seed
        self.pkey = f"{num_players}_player"

        # Build and shuffle deck
        all_cards = build_deck(config)
        self.draw_pile = Deck(all_cards)
        self.draw_pile.shuffle(self.rng)
        self.discard_pile = Deck()

        # Players
        self.players: List[Player] = []
        self.round_number: int = 0
        self.defender_idx: int = 0  # For 3-player rotation

        # Game state
        self.game_over: bool = False
        self.winner_id: Optional[int] = None
        self.deployments: Dict[int, Deployment] = {}

        # Round tracking
        self.round_results: List[dict] = []
        self.log: List[str] = []

        # Per-round stats for talents
        self.round_winners: Dict[int, List[str]] = {}  # pid -> list of tunnel types won
        self.round_winning_cards: Dict[int, List[Card]] = {}  # pid -> winning cards
        self.round_losing_opponents: Dict[int, List[int]] = {}  # pid -> list of opponent ids beaten

    def setup(self):
        """Initialize the game: create players, deal hands."""
        hand_size = self.rules["starting_hand_size"][self.pkey]

        for i in range(self.num_players):
            p = Player(id=i)
            p.hand = self.draw_pile.draw(hand_size)
            p.cards_drawn = hand_size
            self.players.append(p)

        # 3-player: assign initial defender
        if self.num_players == 3:
            self.defender_idx = self.rng.randint(0, 2)
            self.players[self.defender_idx].is_defender = True

        self._log(f"Game started: {self.num_players} players, seed={self.seed}")
        self._log(f"Each player dealt {hand_size} cards")
        if self.num_players == 3:
            self._log(f"P{self.defender_idx} is the initial Defender")

    def get_left_neighbor(self, player_id: int) -> int:
        """Get the player ID of the left neighbor."""
        return (player_id - 1) % self.num_players

    def get_right_neighbor(self, player_id: int) -> int:
        """Get the player ID of the right neighbor."""
        return (player_id + 1) % self.num_players

    def set_deployment(self, player_id: int, home_card: Card, away_card: Card) -> dict:
        """Player deploys cards to Home and Away tunnels."""
        player = self.players[player_id]

        if home_card not in player.hand:
            return {"success": False, "error": f"Home card {home_card} not in hand"}
        if away_card not in player.hand:
            return {"success": False, "error": f"Away card {away_card} not in hand"}
        if home_card == away_card and player.hand.count(home_card) < 2:
            return {"success": False, "error": "Cannot deploy same card to both tunnels"}

        self.deployments[player_id] = Deployment(home_card=home_card, away_card=away_card)
        player.hand.remove(home_card)
        player.hand.remove(away_card)

        return {"success": True}

    def resolve_wild(self, wild_card: Card, other_card: Card) -> Tuple[int, bool]:
        """
        Determine effective rank and activation status of a Wild card.
        Returns (effective_rank, activated).

        In strict mode, the anchor card must also be rank 1-5 (low half),
        making Wild activation harder and more of a real trade-off.
        """
        if not wild_card.is_wild:
            return wild_card.rank, False

        strict = self.rules.get("wild_strict_mode", False)

        # Wild activates if other tunnel has matching faction, non-wild
        if other_card is not None and not other_card.is_wild and other_card.faction == wild_card.faction:
            # In strict mode, anchor must be rank 1-5
            if strict and other_card.rank > 5:
                return 0, False
            return wild_card.rank, True  # 0 stays 0, 10 stays 10
        else:
            return 0, False  # Trips: counts as rank 0, no faction

    def resolve_brawl(self, p1_id: int, p1_card: Card, p1_other_card: Card,
                      p2_id: int, p2_card: Card, p2_other_card: Card,
                      tunnel_label: str = "") -> BrawlResult:
        """
        Resolve a single brawl between two cards.
        p1_other_card / p2_other_card are the cards in the player's OTHER tunnel
        (needed for Wild activation check).
        """
        # Resolve Wilds
        p1_rank, p1_wild_activated = self.resolve_wild(p1_card, p1_other_card)
        p2_rank, p2_wild_activated = self.resolve_wild(p2_card, p2_other_card)

        # Wild Surge: draw a card if Wild activated
        if p1_card.is_wild and p1_wild_activated:
            self._draw_cards(self.players[p1_id], self.rules["wild_surge_draw"])
            self.players[p1_id].wilds_activated += 1
            self._log(f"  P{p1_id} Wild Surge! {p1_card} activated, draws {self.rules['wild_surge_draw']}")
        elif p1_card.is_wild:
            self.players[p1_id].wilds_tripped += 1
            self._log(f"  P{p1_id} Wild tripped! {p1_card} counts as 0")

        if p2_card.is_wild and p2_wild_activated:
            self._draw_cards(self.players[p2_id], self.rules["wild_surge_draw"])
            self.players[p2_id].wilds_activated += 1
            self._log(f"  P{p2_id} Wild Surge! {p2_card} activated, draws {self.rules['wild_surge_draw']}")
        elif p2_card.is_wild:
            self.players[p2_id].wilds_tripped += 1
            self._log(f"  P{p2_id} Wild tripped! {p2_card} counts as 0")

        result = BrawlResult(
            attacker_id=p1_id, defender_id=p2_id,
            attacker_card=p1_card, defender_card=p2_card,
            attacker_effective_rank=p1_rank, defender_effective_rank=p2_rank,
            attacker_wild_activated=p1_wild_activated,
            defender_wild_activated=p2_wild_activated,
        )

        # Determine winner
        if p1_rank > p2_rank:
            result.winner_id = p1_id
            result.vp_awarded = self.rules["normal_win_reward"]
        elif p2_rank > p1_rank:
            result.winner_id = p2_id
            result.vp_awarded = self.rules["normal_win_reward"]
        else:
            # Tie — check 3-player defender wins ties
            if self.num_players == 3 and self.config["three_player"]["defender_wins_ties"]:
                if self.players[p1_id].is_defender:
                    result.winner_id = p1_id
                    result.vp_awarded = self.rules["normal_win_reward"]
                    self._log(f"  Tie at rank {p1_rank} — Defender P{p1_id} wins!")
                elif self.players[p2_id].is_defender:
                    result.winner_id = p2_id
                    result.vp_awarded = self.rules["normal_win_reward"]
                    self._log(f"  Tie at rank {p2_rank} — Defender P{p2_id} wins!")
                else:
                    result.is_clash = True
                    self._log(f"  Tie at rank {p1_rank} — CLASH! (neither is Defender)")
            else:
                result.is_clash = True
                self._log(f"  Tie at rank {p1_rank} — CLASH!")

        # Discard played cards
        self.discard_pile.add_to_bottom(p1_card)
        self.discard_pile.add_to_bottom(p2_card)

        if result.winner_id is not None and not result.is_clash:
            # Old domination bonus (rank difference based, disabled by default)
            dom_diff = self.rules.get("domination_rank_diff", 0)
            dom_bonus = self.rules.get("domination_bonus_vp", 0)
            rank_diff = abs(p1_rank - p2_rank)
            if dom_diff > 0 and dom_bonus > 0 and rank_diff >= dom_diff:
                result.vp_awarded += dom_bonus

            # Power Play bonus: extra VP for winning with a high-rank card (8, 9, 10)
            pp_min = self.rules.get("power_play_min_rank", 0)
            pp_bonus = self.rules.get("power_play_bonus_vp", 0)
            winner_rank = p1_rank if result.winner_id == p1_id else p2_rank
            is_power_play = pp_min > 0 and pp_bonus > 0 and winner_rank >= pp_min
            if is_power_play:
                result.vp_awarded += pp_bonus

            self.players[result.winner_id].victory_points += result.vp_awarded
            bonus_str = ""
            if dom_diff > 0 and dom_bonus > 0 and rank_diff >= dom_diff:
                bonus_str = f" (DOMINATION! +{dom_bonus})"
            if is_power_play:
                bonus_str = f" (POWER PLAY! +{pp_bonus})"
            self._log(f"  {tunnel_label}: P{result.winner_id} wins! ({p1_card}[{p1_rank}] vs {p2_card}[{p2_rank}]) +{result.vp_awarded} VP{bonus_str}")

            # Track winner stats
            winner = self.players[result.winner_id]
            loser_id = p2_id if result.winner_id == p1_id else p1_id
            winner.brawls_won += 1
            self.players[loser_id].brawls_lost += 1
            if (dom_diff > 0 and dom_bonus > 0 and rank_diff >= dom_diff) or is_power_play:
                winner.dominations += 1

        return result

    def resolve_clash(self, p1_id: int, p2_id: int, clash_round: int,
                      choose_card_fn: Callable) -> BrawlResult:
        """
        Resolve a CLASH! by having both players select new cards.
        choose_card_fn(player_id, game_state, clash_round) -> Card
        Returns the BrawlResult for this CLASH! round.
        """
        p1 = self.players[p1_id]
        p2 = self.players[p2_id]

        # Both players must have cards to CLASH!
        if len(p1.hand) == 0 or len(p2.hand) == 0:
            # Can't CLASH!, no winner
            self._log(f"  CLASH! round {clash_round}: A player has no cards. No winner.")
            return BrawlResult(
                attacker_id=p1_id, defender_id=p2_id,
                attacker_card=Card("NONE", 0), defender_card=Card("NONE", 0),
                attacker_effective_rank=0, defender_effective_rank=0,
                clash_round=clash_round
            )

        c1 = choose_card_fn(p1_id, self, clash_round)
        c2 = choose_card_fn(p2_id, self, clash_round)

        p1.hand.remove(c1)
        p2.hand.remove(c2)

        # In CLASH!, Wilds count at face value (no cross-body check — no "other tunnel")
        r1 = c1.rank
        r2 = c2.rank

        vp_reward = self.rules["clash_base_reward"] + (clash_round - 1)

        result = BrawlResult(
            attacker_id=p1_id, defender_id=p2_id,
            attacker_card=c1, defender_card=c2,
            attacker_effective_rank=r1, defender_effective_rank=r2,
            clash_round=clash_round
        )

        if r1 > r2:
            result.winner_id = p1_id
            result.vp_awarded = vp_reward
        elif r2 > r1:
            result.winner_id = p2_id
            result.vp_awarded = vp_reward
        else:
            result.is_clash = True  # Another tie — CLASH! again

        self.discard_pile.add_to_bottom(c1)
        self.discard_pile.add_to_bottom(c2)

        if result.winner_id is not None:
            self.players[result.winner_id].victory_points += result.vp_awarded
            self.players[result.winner_id].clashes_won += 1
            loser_id = p2_id if result.winner_id == p1_id else p1_id
            self.players[loser_id].clashes_lost += 1
            self._log(f"  CLASH! round {clash_round}: P{result.winner_id} wins! "
                       f"({c1}[{r1}] vs {c2}[{r2}]) +{vp_reward} VP")
        else:
            self._log(f"  CLASH! round {clash_round}: Tie again at rank {r1}! Another CLASH!")

        return result

    def resolve_round(self, choose_clash_card_fn: Callable) -> dict:
        """
        Resolve all brawls for the current round after deployments are set.
        Returns a dict with all brawl results.
        """
        self.round_number += 1
        self._log(f"\n=== Round {self.round_number} ===")

        # Reset per-round tracking
        self.round_winners = {p.id: [] for p in self.players}
        self.round_winning_cards = {p.id: [] for p in self.players}
        self.round_losing_opponents = {p.id: [] for p in self.players}

        all_brawl_results = []

        # Each player's Home tunnel fights left neighbor's Away tunnel
        for player in self.players:
            pid = player.id
            left_id = self.get_left_neighbor(pid)

            dep_home = self.deployments[pid]
            dep_away = self.deployments[left_id]

            home_card = dep_home.home_card
            away_card = dep_away.away_card

            self._log(f"  Brawl: P{pid} Home ({home_card}) vs P{left_id} Away ({away_card})")

            result = self.resolve_brawl(
                p1_id=pid, p1_card=home_card, p1_other_card=dep_home.away_card,
                p2_id=left_id, p2_card=away_card, p2_other_card=dep_away.home_card,
                tunnel_label=f"P{pid}Home vs P{left_id}Away"
            )
            all_brawl_results.append(result)

            # Handle CLASH! chain
            if result.is_clash:
                clash_round = 1
                clash_result = result
                while clash_result.is_clash and clash_round <= 5:  # Cap at 5 to prevent infinite
                    clash_result = self.resolve_clash(
                        pid, left_id, clash_round, choose_clash_card_fn
                    )
                    all_brawl_results.append(clash_result)
                    clash_round += 1

                if clash_result.winner_id is not None:
                    result = clash_result  # Use final CLASH! result for talent tracking

            # Track who won for talent purposes
            if result.winner_id is not None:
                winner = result.winner_id
                loser = pid if winner == left_id else left_id

                if winner == pid:
                    self.round_winners[pid].append("home")
                    self.round_winning_cards[pid].append(home_card)
                    self.round_losing_opponents[pid].append(left_id)
                else:
                    self.round_winners[left_id].append("away")
                    self.round_winning_cards[left_id].append(away_card)
                    self.round_losing_opponents[left_id].append(pid)

        round_data = {
            "round": self.round_number,
            "brawl_results": all_brawl_results,
            "deployments": dict(self.deployments),
        }
        self.round_results.append(round_data)
        return round_data

    def can_trigger_talent(self, player_id: int) -> bool:
        """Check if a player can trigger their faction talent this round."""
        wins = self.round_winners.get(player_id, [])
        if not wins:
            return False

        if self.num_players == 3:
            player = self.players[player_id]
            if player.is_defender:
                # Defender needs both Home and Away wins
                return "home" in wins and "away" in wins
            else:
                # Attacker only needs 1 win
                return len(wins) >= 1
        else:
            return len(wins) >= 1

    def has_double_talent(self, player_id: int) -> bool:
        """Check if player won BOTH brawls (Talent Combo Bonus)."""
        if not self.rules.get("double_talent_enabled", True):
            return False
        wins = self.round_winners.get(player_id, [])
        return "home" in wins and "away" in wins

    def apply_talent_red(self, player_id: int, doubled: bool):
        """Red: Force loser(s) to discard random card(s), draw replacement(s)."""
        losers = self.round_losing_opponents.get(player_id, [])
        discard_count = 2 if doubled else 1
        for loser_id in losers:
            loser = self.players[loser_id]
            for _ in range(discard_count):
                if loser.hand:
                    card = self.rng.choice(loser.hand)
                    loser.hand.remove(card)
                    self.discard_pile.add_to_bottom(card)
                    self._draw_cards(loser, 1)
                    self._log(f"  Red talent: P{loser_id} forced to discard {card}, draws replacement")
        self.players[player_id].talents_triggered += 1

    def apply_talent_orange(self, player_id: int, doubled: bool):
        """Orange: Take top card(s) of discard pile. If Wild, draw extra."""
        player = self.players[player_id]
        take_count = 2 if doubled else 1
        for _ in range(take_count):
            if not self.discard_pile.empty:
                card = self.discard_pile.cards.pop()  # Take from top
                player.hand.append(card)
                self._log(f"  Orange talent: P{player_id} takes {card} from discard")
                if card.is_wild:
                    self._draw_cards(player, 1)
                    self._log(f"    Bonus! It's a Wild — draws extra card")
        self.players[player_id].talents_triggered += 1

    def apply_talent_yellow(self, player_id: int, doubled: bool):
        """Yellow: Draw 2 (or 4) cards."""
        draw_count = 4 if doubled else 2
        self._draw_cards(self.players[player_id], draw_count)
        self._log(f"  Yellow talent: P{player_id} draws {draw_count} cards")
        self.players[player_id].talents_triggered += 1

    def apply_talent_green(self, player_id: int, doubled: bool, choose_target_fn: Callable = None):
        """Green: Look at opponent's hand, force them to play a card next turn."""
        # In simulation, AI picks a target and forces their worst card
        losers = self.round_losing_opponents.get(player_id, [])
        targets = losers if losers else [p.id for p in self.players if p.id != player_id]
        force_count = 2 if doubled else 1

        for i in range(min(force_count, len(targets))):
            target_id = targets[i]
            target = self.players[target_id]
            if target.hand and choose_target_fn:
                forced_card = choose_target_fn(player_id, target_id, target.hand, self)
                target.forced_card = forced_card
                self._log(f"  Green talent: P{player_id} forces P{target_id} to play {forced_card} next round")
        self.players[player_id].talents_triggered += 1

    def apply_talent_blue(self, player_id: int, doubled: bool):
        """Blue: All players pass 1 (or 2) random card(s) to the left."""
        pass_count = 2 if doubled else 1
        # Collect cards to pass
        passing = {}
        for p in self.players:
            cards_to_pass = []
            for _ in range(pass_count):
                if p.hand:
                    card = self.rng.choice(p.hand)
                    p.hand.remove(card)
                    cards_to_pass.append(card)
            passing[p.id] = cards_to_pass

        # Distribute to left neighbors
        for p in self.players:
            left_id = self.get_left_neighbor(p.id)
            received = passing.get(p.id, [])
            self.players[left_id].hand.extend(received)
            if received:
                self._log(f"  Blue talent: P{p.id} passes {received} to P{left_id}")

        self.players[player_id].talents_triggered += 1

    def apply_talent_purple(self, player_id: int, doubled: bool):
        """Purple: Return winning card(s) to hand OR to draw pile (configurable)."""
        player = self.players[player_id]
        winning_cards = self.round_winning_cards.get(player_id, [])
        return_count = 2 if doubled else 1
        vp_cost = self.rules.get("purple_return_vp_cost", 0)
        return_to_deck = self.rules.get("purple_return_to_deck", False)

        for i in range(min(return_count, len(winning_cards))):
            card = winning_cards[i]
            # Check if player can afford the VP cost
            if vp_cost > 0 and player.victory_points < vp_cost:
                self._log(f"  Purple talent: P{player_id} can't afford {vp_cost} VP cost to return {card}")
                continue
            # Remove from discard
            if card in self.discard_pile.cards:
                self.discard_pile.cards.remove(card)
                if vp_cost > 0:
                    player.victory_points -= vp_cost

                if return_to_deck:
                    # Shuffle card into draw pile (not directly to hand)
                    pos = self.rng.randint(0, max(self.draw_pile.size, 0))
                    self.draw_pile.cards.insert(pos, card)
                    self._log(f"  Purple talent: P{player_id} shuffles {card} back into draw pile (keep VP)")
                else:
                    player.hand.append(card)
                    cost_str = f" (costs {vp_cost} VP)" if vp_cost > 0 else ""
                    self._log(f"  Purple talent: P{player_id} returns {card} to hand{cost_str}")
        self.players[player_id].talents_triggered += 1

    def apply_talent(self, player_id: int, faction: str, doubled: bool,
                     choose_green_target_fn: Callable = None):
        """Apply a faction talent for the given player."""
        if faction == "RED":
            self.apply_talent_red(player_id, doubled)
        elif faction == "ORANGE":
            self.apply_talent_orange(player_id, doubled)
        elif faction == "YELLOW":
            self.apply_talent_yellow(player_id, doubled)
        elif faction == "GREEN":
            self.apply_talent_green(player_id, doubled, choose_green_target_fn)
        elif faction == "BLUE":
            self.apply_talent_blue(player_id, doubled)
        elif faction == "PURPLE":
            self.apply_talent_purple(player_id, doubled)

    def draw_phase(self):
        """Step 5: Everyone draws cards, enforce hand limit."""
        hand_limit = self.rules["hand_limit"][self.pkey]

        # 2p variant: underdog draw bonus
        underdog_draw = self.rules.get("underdog_draw_bonus", 0)

        for player in self.players:
            draw_count = self.rules["draw_per_turn"]
            if self.num_players == 3 and player.is_defender:
                draw_count = self.rules["defender_draw_per_turn"]

            # Underdog bonus: trailing player draws extra cards
            if underdog_draw > 0 and self.num_players == 2:
                other = [p for p in self.players if p.id != player.id][0]
                if player.victory_points < other.victory_points:
                    draw_count += underdog_draw
                    self._log(f"  P{player.id} draws +{underdog_draw} (underdog bonus)")

            self._draw_cards(player, draw_count)

            # If still below hand limit, draw up to it
            while len(player.hand) < hand_limit and not self.draw_pile.empty:
                self._draw_cards(player, 1)

            # Enforce hand limit (discard excess — weakest cards)
            while len(player.hand) > hand_limit:
                # Discard lowest rank card
                weakest = min(player.hand, key=lambda c: c.rank)
                player.hand.remove(weakest)
                self.discard_pile.add_to_bottom(weakest)

    def check_game_end(self) -> bool:
        """Check if any player has reached the victory threshold."""
        # Fixed-round mode: play exactly N rounds, highest VP wins
        fixed_rounds = self.rules.get("fixed_rounds", {}).get(self.pkey, 0)
        if fixed_rounds > 0:
            if self.round_number >= fixed_rounds:
                self.game_over = True
                max_vp = max(p.victory_points for p in self.players)
                winners = [p for p in self.players if p.victory_points == max_vp]
                if len(winners) == 1:
                    self.winner_id = winners[0].id
                else:
                    max_hand = max(len(w.hand) for w in winners)
                    hand_winners = [w for w in winners if len(w.hand) == max_hand]
                    self.winner_id = hand_winners[0].id
                self._log(f"\n*** Round {fixed_rounds} complete! P{self.winner_id} wins with {max_vp} VP! ***")
                return True
            return False

        threshold = self.rules["victory_threshold"][self.pkey]
        for player in self.players:
            if player.victory_points >= threshold:
                self.game_over = True
                # Winner is player with most VP
                max_vp = max(p.victory_points for p in self.players)
                winners = [p for p in self.players if p.victory_points == max_vp]
                if len(winners) == 1:
                    self.winner_id = winners[0].id
                else:
                    # Tiebreaker: most cards in hand
                    max_hand = max(len(w.hand) for w in winners)
                    hand_winners = [w for w in winners if len(w.hand) == max_hand]
                    self.winner_id = hand_winners[0].id  # Shared victory → pick first
                self._log(f"\n*** GAME OVER! P{self.winner_id} wins with {max_vp} VP! ***")
                return True

        # Check max rounds
        if self.round_number >= self.rules["max_rounds"]:
            self.game_over = True
            max_vp = max(p.victory_points for p in self.players)
            winners = [p for p in self.players if p.victory_points == max_vp]
            self.winner_id = winners[0].id
            self._log(f"\n*** Max rounds reached. P{self.winner_id} wins with {max_vp} VP ***")
            return True

        return False

    def rotate_defender(self):
        """3-player only: rotate the Defender token clockwise."""
        if self.num_players != 3:
            return
        self.players[self.defender_idx].is_defender = False
        self.defender_idx = (self.defender_idx + 1) % 3
        self.players[self.defender_idx].is_defender = True

    def _draw_cards(self, player: Player, n: int):
        """Draw n cards for a player, reshuffling discard if needed."""
        for _ in range(n):
            if self.draw_pile.empty:
                if self.discard_pile.empty:
                    return  # No cards anywhere
                # Reshuffle discard into draw pile
                self.draw_pile = Deck(list(self.discard_pile.cards))
                self.discard_pile = Deck()
                self.draw_pile.shuffle(self.rng)
                self._log("  Draw pile empty — reshuffled discard pile")

            card = self.draw_pile.draw_one()
            if card:
                player.hand.append(card)
                player.cards_drawn += 1

    def _log(self, message: str):
        """Append a log message."""
        self.log.append(message)

    def get_scores(self) -> Dict[int, int]:
        """Get current VP totals."""
        return {p.id: p.victory_points for p in self.players}

    def get_state_summary(self) -> dict:
        """Get a summary of the current game state."""
        return {
            "round": self.round_number,
            "scores": self.get_scores(),
            "hands": {p.id: len(p.hand) for p in self.players},
            "draw_pile": self.draw_pile.size,
            "discard_pile": self.discard_pile.size,
            "game_over": self.game_over,
            "winner": self.winner_id,
        }
