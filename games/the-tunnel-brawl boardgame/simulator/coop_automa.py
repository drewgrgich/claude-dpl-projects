#!/usr/bin/env python3
"""
The Tunnel Brawl v2.0 — Siege Mode (Co-op Automa)

2 human players cooperate against a Boss automa pushing through the tunnels.
Each round: Player 1 fights the Boss in the Home tunnel, Player 2 fights in Away.
Players share a VP pool and race to a threshold before the Boss does.

Boss mechanics:
  - Draws from a shuffled threat deck (the same 66-card game deck)
  - Gets a cumulative rank bonus that escalates each round (+1 per 3 rounds)
  - Boss deploys 2 cards per round (one per tunnel), no intelligence needed
  - Boss VP comes from winning brawls against players

Player mechanics:
  - Both players see each other's hands and can coordinate
  - Each player deploys 1 card to their assigned tunnel
  - Players alternate Home/Away assignment each round
  - Standard faction talents activate on wins (adapted for co-op)
  - Wilds use cross-body rule: your Wild activates if your partner's card
    matches faction (thematic: teamwork activates Wild powers)

Talent adaptations for co-op:
  - RED (disrupt): Boss discards top card from threat deck
  - ORANGE (scavenge): Draw from discard pile
  - YELLOW (draw): Draw extra cards (standard)
  - GREEN (force): Look at Boss's next 2 cards, reorder them
  - BLUE (chaos): Shuffle Boss's threat deck
  - PURPLE (recycle): Return card to draw pile (standard)

Win conditions:
  - Players win: reach combined VP threshold (default 20)
  - Boss wins: reaches VP threshold (default 15), OR round limit hit
"""

import argparse
import json
import os
import sys
import random
from collections import defaultdict
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Tuple

from cards import Card, Deck, build_deck


# ─── Co-op Game State ────────────────────────────────────────────

@dataclass
class CoopPlayer:
    """A human player in co-op mode."""
    id: int
    hand: List[Card] = field(default_factory=list)
    tunnel: str = "home"  # alternates each round
    brawls_won: int = 0
    brawls_lost: int = 0
    wilds_activated: int = 0
    wilds_tripped: int = 0
    talents_triggered: int = 0
    cards_drawn: int = 0


@dataclass
class CoopBrawlResult:
    """Result of a player vs Boss brawl."""
    player_id: int
    player_card: Card
    boss_card: Card
    player_effective_rank: int
    boss_effective_rank: int
    player_wild_activated: bool = False
    player_won: bool = False
    is_clash: bool = False
    vp_awarded: int = 0


class SiegeGame:
    """Co-op game state for Siege Mode."""

    def __init__(self, config: dict, seed: int = None):
        self.config = config
        self.rules = config.get("siege_rules", {})
        self.rng = random.Random(seed)
        self.seed = seed

        # Defaults (tuned for ~50% win rate sweet spot)
        self.team_vp_threshold = self.rules.get("team_vp_threshold", 18)
        self.boss_vp_threshold = self.rules.get("boss_vp_threshold", 12)
        self.max_rounds = self.rules.get("max_rounds", 12)
        self.starting_hand = self.rules.get("starting_hand", 7)
        self.hand_limit = self.rules.get("hand_limit", 7)
        self.draw_per_turn = self.rules.get("draw_per_turn", 2)
        self.boss_escalation_interval = self.rules.get("boss_escalation_interval", 2)
        self.clash_reward = config["game_rules"].get("clash_base_reward", 2)
        self.power_play_rank = config["game_rules"].get("power_play_min_rank", 7)
        self.power_play_bonus = config["game_rules"].get("power_play_bonus_vp", 1)
        self.wild_strict = config["game_rules"].get("wild_strict_mode", False)

        # Build two separate decks: player deck and boss threat deck
        all_cards = build_deck(config)
        self.rng.shuffle(all_cards)
        mid = len(all_cards) // 2
        self.player_draw = Deck(all_cards[:mid])
        self.player_draw.shuffle(self.rng)
        self.boss_draw = Deck(all_cards[mid:])
        self.boss_draw.shuffle(self.rng)
        self.player_discard = Deck()
        self.boss_discard = Deck()

        # Players
        self.players = [CoopPlayer(id=0), CoopPlayer(id=1)]
        self.team_vp = 0
        self.boss_vp = 0
        self.round_number = 0
        self.game_over = False
        self.team_won = False

        # Stats
        self.log: List[str] = []
        self.round_team_vp = []
        self.round_boss_vp = []
        self.boss_rank_bonus = 0
        self.total_brawls = 0
        self.clashes = 0

    def setup(self):
        """Deal starting hands."""
        for player in self.players:
            self._draw_player_cards(player, self.starting_hand)
        self.players[0].tunnel = "home"
        self.players[1].tunnel = "away"
        self._log(f"=== SIEGE MODE: 2 Players vs Boss ===")
        self._log(f"Team needs {self.team_vp_threshold} VP | Boss needs {self.boss_vp_threshold} VP | {self.max_rounds} rounds")

    def _log(self, msg):
        self.log.append(msg)

    def _draw_player_cards(self, player, n):
        for _ in range(n):
            if self.player_draw.empty:
                if self.player_discard.empty:
                    return
                self.player_draw = Deck(list(self.player_discard.cards))
                self.player_discard = Deck()
                self.player_draw.shuffle(self.rng)
            card = self.player_draw.draw_one()
            if card:
                player.hand.append(card)
                player.cards_drawn += 1

    def _draw_boss_cards(self, n):
        cards = []
        for _ in range(n):
            if self.boss_draw.empty:
                if self.boss_discard.empty:
                    return cards
                self.boss_draw = Deck(list(self.boss_discard.cards))
                self.boss_discard = Deck()
                self.boss_draw.shuffle(self.rng)
            card = self.boss_draw.draw_one()
            if card:
                cards.append(card)
        return cards

    def boss_escalation_bonus(self):
        """Boss gets +1 rank per escalation interval."""
        return self.round_number // self.boss_escalation_interval

    def resolve_wild(self, wild_card, partner_card):
        """Co-op Wild rule: activates if partner's card matches faction."""
        if partner_card is None or partner_card.is_wild:
            return 0, False
        if partner_card.faction == wild_card.faction:
            if self.wild_strict and partner_card.rank > 5:
                return 0, False
            return wild_card.rank, True
        return 0, False

    def resolve_brawl(self, player_card, partner_card, boss_card, player_id):
        """Resolve a single player-vs-Boss brawl."""
        self.total_brawls += 1

        # Player effective rank
        if player_card.is_wild:
            p_rank, p_wild_active = self.resolve_wild(player_card, partner_card)
        else:
            p_rank = player_card.rank
            p_wild_active = False

        # Boss effective rank (base rank + escalation bonus)
        bonus = self.boss_escalation_bonus()
        b_rank = boss_card.rank + bonus

        result = CoopBrawlResult(
            player_id=player_id,
            player_card=player_card,
            boss_card=boss_card,
            player_effective_rank=p_rank,
            boss_effective_rank=b_rank,
            player_wild_activated=p_wild_active,
        )

        if p_rank > b_rank:
            result.player_won = True
            result.vp_awarded = 1
            # Power Play
            if self.power_play_rank > 0 and p_rank >= self.power_play_rank:
                result.vp_awarded += self.power_play_bonus
            self.players[player_id].brawls_won += 1
        elif p_rank == b_rank:
            # CLASH! — goes to the Boss (defender advantage)
            result.is_clash = True
            result.player_won = False
            result.vp_awarded = self.clash_reward  # Boss gets CLASH VP
            self.clashes += 1
            self.players[player_id].brawls_lost += 1
        else:
            result.player_won = False
            result.vp_awarded = 1  # Boss gets 1 VP for normal win
            self.players[player_id].brawls_lost += 1

        if p_wild_active:
            self.players[player_id].wilds_activated += 1
        elif player_card.is_wild:
            self.players[player_id].wilds_tripped += 1

        return result

    def apply_talent(self, player_id, faction):
        """Apply a faction talent in co-op mode."""
        player = self.players[player_id]
        player.talents_triggered += 1

        if faction == "RED":
            # Disrupt: Boss discards top card
            cards = self._draw_boss_cards(1)
            if cards:
                self.boss_discard.add_to_bottom(cards[0])
                self._log(f"  RED talent: Boss discards {cards[0]}")

        elif faction == "ORANGE":
            # Scavenge: Draw from player discard
            if not self.player_discard.empty:
                card = self.player_discard.cards.pop()
                player.hand.append(card)
                self._log(f"  ORANGE talent: P{player_id} scavenges {card}")

        elif faction == "YELLOW":
            # Draw: extra card draw
            self._draw_player_cards(player, 1)
            self._log(f"  YELLOW talent: P{player_id} draws extra card")

        elif faction == "GREEN":
            # Scout: look at Boss's next 2 cards, put worst on top
            if self.boss_draw.size >= 2:
                top2 = [self.boss_draw.draw_one(), self.boss_draw.draw_one()]
                # Put highest rank on top (worst for players = deepest in deck)
                top2.sort(key=lambda c: c.rank)
                # Weakest goes on top (best for players)
                for c in reversed(top2):
                    self.boss_draw.add_to_top(c)
                self._log(f"  GREEN talent: P{player_id} scouts Boss deck, reorders")

        elif faction == "BLUE":
            # Chaos: shuffle Boss's threat deck
            self.boss_draw.shuffle(self.rng)
            self._log(f"  BLUE talent: Boss deck shuffled!")

        elif faction == "PURPLE":
            # Recycle: return a card from discard to player draw pile
            if not self.player_discard.empty:
                card = self.player_discard.cards.pop()
                pos = self.rng.randint(0, max(self.player_draw.size, 0))
                self.player_draw.cards.insert(pos, card)
                self._log(f"  PURPLE talent: {card} recycled to draw pile")

    def draw_phase(self):
        """Draw cards for both players."""
        for player in self.players:
            self._draw_player_cards(player, self.draw_per_turn)
            # Hand limit
            while len(player.hand) > self.hand_limit:
                weakest = min(player.hand, key=lambda c: c.rank)
                player.hand.remove(weakest)
                self.player_discard.add_to_bottom(weakest)

    def check_game_end(self):
        """Check victory conditions."""
        if self.team_vp >= self.team_vp_threshold:
            self.game_over = True
            self.team_won = True
            self._log(f"\n*** TEAM WINS with {self.team_vp} VP! (Boss had {self.boss_vp}) ***")
            return True
        if self.boss_vp >= self.boss_vp_threshold:
            self.game_over = True
            self.team_won = False
            self._log(f"\n*** BOSS WINS with {self.boss_vp} VP! (Team had {self.team_vp}) ***")
            return True
        if self.round_number >= self.max_rounds:
            self.game_over = True
            self.team_won = self.team_vp >= self.team_vp_threshold
            if not self.team_won:
                self._log(f"\n*** TIME'S UP! Boss wins. Team: {self.team_vp} / Boss: {self.boss_vp} ***")
            return True
        return False

    def swap_tunnels(self):
        """Players alternate tunnels each round."""
        for p in self.players:
            p.tunnel = "away" if p.tunnel == "home" else "home"


# ─── Co-op AI (plays both human players) ────────────────────────

class CoopAI:
    """Heuristic AI that plays cooperatively for both players."""

    def __init__(self, skill=1.0, rng_seed=42):
        self.skill = skill
        self.rng = random.Random(rng_seed)

    def choose_cards(self, game: SiegeGame):
        """Choose 1 card for each player to deploy.

        Strategy: coordinate to maximize total expected wins.
        Player with the stronger hand covers the harder tunnel.
        """
        p0, p1 = game.players
        if not p0.hand or not p1.hand:
            return None, None

        boss_bonus = game.boss_escalation_bonus()

        best_score = -999
        best_pair = (None, None)

        # Try all combinations of (P0 card, P1 card)
        for c0 in p0.hand:
            for c1 in p1.hand:
                score = self._score_pair(c0, c1, p0, p1, game, boss_bonus)
                if score > best_score:
                    best_score = score
                    best_pair = (c0, c1)

        return best_pair

    def _effective_rank(self, card, partner_card, game):
        if not card.is_wild:
            return card.rank
        if partner_card and not partner_card.is_wild and partner_card.faction == card.faction:
            if game.wild_strict and partner_card.rank > 5:
                return 0
            return card.rank
        return 0

    def _score_pair(self, c0, c1, p0, p1, game, boss_bonus):
        """Score a (P0 card, P1 card) pair."""
        # Effective ranks — cross-body: each player's Wild checks partner's card
        r0 = self._effective_rank(c0, c1, game)
        r1 = self._effective_rank(c1, c0, game)

        # Expected Boss rank: ~5 + bonus (average of 0-10 uniform)
        expected_boss = 5 + boss_bonus

        score = 0
        # Each card that beats expected Boss is good
        for r in [r0, r1]:
            if r > expected_boss:
                score += 2 + (r - expected_boss) * 0.5
            elif r == expected_boss:
                score -= 1  # CLASH is bad (Boss wins ties)
            else:
                score -= 1

        # Prefer Power Play ranks
        for r in [r0, r1]:
            if r >= game.power_play_rank:
                score += 1.5

        # Prefer spreading factions (for talent variety)
        if c0.faction != c1.faction:
            score += 0.5

        # Prefer keeping strong cards in hand
        avg_hand_0 = sum(c.rank for c in p0.hand) / max(len(p0.hand), 1)
        avg_hand_1 = sum(c.rank for c in p1.hand) / max(len(p1.hand), 1)

        # Penalty for playing your best card unnecessarily
        if c0.rank == max(c.rank for c in p0.hand) and r0 > expected_boss + 3:
            score -= 0.5
        if c1.rank == max(c.rank for c in p1.hand) and r1 > expected_boss + 3:
            score -= 0.5

        # Noise for skill < 1.0
        if self.skill < 1.0:
            score += self.rng.gauss(0, (1 - self.skill) * 4)

        return score

    def choose_talent(self, player_id, winning_card, game):
        """Choose which talent to activate."""
        faction = winning_card.faction
        # Simple: always activate the winning card's faction talent
        return faction


# ─── Game Runner ─────────────────────────────────────────────────

def run_coop_game(config, seed=1, skill=1.0, verbose=False):
    """Run one co-op Siege Mode game."""
    game = SiegeGame(config, seed=seed)
    game.setup()
    ai = CoopAI(skill=skill, rng_seed=seed * 100)

    # Per-round tracking
    team_vp_per_round = []
    boss_vp_per_round = []
    choices_per_round = []
    wow_events = []
    dead_rounds = {0: 0, 1: 0}  # zero-agency turns
    costly_failures = {0: 0, 1: 0}  # lost brawl but had agency

    while not game.game_over and game.round_number < game.max_rounds:
        game.round_number += 1
        round_num = game.round_number
        bonus = game.boss_escalation_bonus()

        game._log(f"\n--- Round {round_num} (Boss bonus: +{bonus}) ---")
        game._log(f"  Team VP: {game.team_vp} | Boss VP: {game.boss_vp}")

        # Count choices: how many distinct card pairs are available?
        n_choices = len(game.players[0].hand) * len(game.players[1].hand)
        choices_per_round.append(n_choices)

        team_vp_before = game.team_vp
        boss_vp_before = game.boss_vp

        # Players choose cards
        c0, c1 = ai.choose_cards(game)
        if c0 is None or c1 is None:
            break

        # Boss draws 2 cards
        boss_cards = game._draw_boss_cards(2)
        if len(boss_cards) < 2:
            # Not enough Boss cards — reshuffle
            boss_cards.extend(game._draw_boss_cards(2 - len(boss_cards)))
        if len(boss_cards) < 2:
            break  # Completely out

        # Remove player cards from hands
        game.players[0].hand.remove(c0)
        game.players[1].hand.remove(c1)

        game._log(f"  P0 plays {c0} ({game.players[0].tunnel})")
        game._log(f"  P1 plays {c1} ({game.players[1].tunnel})")
        game._log(f"  Boss plays {boss_cards[0]} / {boss_cards[1]} (bonus +{bonus})")

        # Resolve brawls
        # P0's card vs Boss card 0, P1's card vs Boss card 1
        # Cross-body Wild: P0's Wild checks P1's card as partner
        r0 = game.resolve_brawl(c0, c1, boss_cards[0], 0)
        r1 = game.resolve_brawl(c1, c0, boss_cards[1], 1)

        round_team_vp = 0
        round_boss_vp = 0
        talents_won = []

        for result in [r0, r1]:
            if result.player_won:
                game.team_vp += result.vp_awarded
                round_team_vp += result.vp_awarded
                game._log(f"  P{result.player_id} WINS! ({result.player_effective_rank} vs {result.boss_effective_rank}) +{result.vp_awarded} team VP")
                talents_won.append((result.player_id, result.player_card))
            elif result.is_clash:
                game.boss_vp += result.vp_awarded
                round_boss_vp += result.vp_awarded
                game._log(f"  CLASH! ({result.player_effective_rank} vs {result.boss_effective_rank}) Boss +{result.vp_awarded} VP")
            else:
                game.boss_vp += result.vp_awarded
                round_boss_vp += result.vp_awarded
                game._log(f"  P{result.player_id} loses ({result.player_effective_rank} vs {result.boss_effective_rank}) Boss +{result.vp_awarded} VP")

        # Faction talents for winners
        for pid, winning_card in talents_won:
            faction = ai.choose_talent(pid, winning_card, game)
            game.apply_talent(pid, faction)

        # Track per-player dead rounds (co-op: zero-agency = no cards to play)
        # Losing a brawl is a COSTLY FAILURE (Boss gains VP), not a dead turn
        for pid in [0, 1]:
            if len(game.players[pid].hand) == 0:
                dead_rounds[pid] += 1
            else:
                result = r0 if pid == 0 else r1
                if not result.player_won:
                    costly_failures[pid] += 1

        # Wow moments
        round_wows = []
        if round_team_vp >= 3:
            round_wows.append("big_team_round")
        if any(r.player_won and r.player_effective_rank >= game.power_play_rank for r in [r0, r1]):
            round_wows.append("power_play")
        if any(r.player_wild_activated and r.player_won for r in [r0, r1]):
            round_wows.append("wild_win")
        if r0.player_won and r1.player_won:
            round_wows.append("double_win")
        if round_wows:
            wow_events.append((round_num, round_wows))

        team_vp_per_round.append(round_team_vp)
        boss_vp_per_round.append(round_boss_vp)

        # Discard played cards
        game.player_discard.add_to_bottom(c0)
        game.player_discard.add_to_bottom(c1)
        for bc in boss_cards:
            game.boss_discard.add_to_bottom(bc)

        # Draw phase
        game.draw_phase()

        # Swap tunnels
        game.swap_tunnels()

        # Check end
        game.check_game_end()

    if verbose:
        for line in game.log:
            print(line)

    # Compile stats
    rounds_played = game.round_number
    total_turns = rounds_played * 2

    # Threat level per round (normalized Boss VP / threshold)
    threat_per_round = []
    cumulative_boss = 0
    for bvp in boss_vp_per_round:
        cumulative_boss += bvp
        threat_per_round.append(cumulative_boss / game.boss_vp_threshold)

    # Crisis detection: Boss VP >= 60% of threshold
    crisis_entered = any(t >= 0.6 for t in threat_per_round)
    near_loss = any(t >= 0.85 for t in threat_per_round)

    # Contribution equity
    p0_contribution = game.players[0].brawls_won
    p1_contribution = game.players[1].brawls_won
    total_contrib = p0_contribution + p1_contribution
    if total_contrib > 0:
        shares = [p0_contribution / total_contrib, p1_contribution / total_contrib]
        ideal = 0.5
        deviations = [abs(s - ideal) for s in shares]
        equity = 1.0 - sum(deviations)
    else:
        equity = 1.0

    return {
        "seed": seed,
        "rounds": rounds_played,
        "team_won": game.team_won,
        "team_vp": game.team_vp,
        "boss_vp": game.boss_vp,
        "team_vp_per_round": team_vp_per_round,
        "boss_vp_per_round": boss_vp_per_round,
        "threat_per_round": threat_per_round,
        "choices_per_round": choices_per_round,
        "dead_rounds": dict(dead_rounds),
        "costly_failures": dict(costly_failures),
        "wow_events": wow_events,
        "crisis_entered": crisis_entered,
        "near_loss": near_loss,
        "equity": equity,
        "total_brawls": game.total_brawls,
        "clashes": game.clashes,
        "per_player": {
            pid: {
                "brawls_won": game.players[pid].brawls_won,
                "brawls_lost": game.players[pid].brawls_lost,
                "wilds_activated": game.players[pid].wilds_activated,
                "wilds_tripped": game.players[pid].wilds_tripped,
                "talents_triggered": game.players[pid].talents_triggered,
            }
            for pid in [0, 1]
        },
    }


# ─── Batch Runner & Report ───────────────────────────────────────

def run_coop_batch(config, num_games, start_seed=1, skill=1.0, verbose=False):
    """Run N co-op games and aggregate."""
    results = []
    for i in range(num_games):
        r = run_coop_game(config, seed=start_seed + i, skill=skill, verbose=verbose)
        results.append(r)
        if (i + 1) % 100 == 0:
            print(f"  ... completed {i + 1}/{num_games} games", file=sys.stderr)
    return aggregate_coop(results)


def aggregate_coop(results):
    n = len(results)

    win_rate = sum(1 for r in results if r["team_won"]) / n
    avg_rounds = sum(r["rounds"] for r in results) / n
    avg_team_vp = sum(r["team_vp"] for r in results) / n
    avg_boss_vp = sum(r["boss_vp"] for r in results) / n

    # Decision density
    avg_choices = sum(
        sum(r["choices_per_round"]) / max(len(r["choices_per_round"]), 1)
        for r in results
    ) / n
    pct_high_choice = sum(
        sum(1 for c in r["choices_per_round"] if c >= 6) / max(len(r["choices_per_round"]), 1)
        for r in results
    ) / n

    # Crisis recovery
    games_with_crisis = sum(1 for r in results if r["crisis_entered"])
    crisis_rate = games_with_crisis / n
    crisis_recoveries = sum(1 for r in results if r["crisis_entered"] and r["team_won"])
    recovery_rate = crisis_recoveries / max(games_with_crisis, 1)

    # Dead turns (zero-agency: no cards in hand) vs costly failures (lost with agency)
    total_player_rounds = sum(r["rounds"] * 2 for r in results)
    total_dead = sum(r["dead_rounds"][0] + r["dead_rounds"][1] for r in results)
    dead_rate = total_dead / max(total_player_rounds, 1)
    total_costly = sum(r["costly_failures"][0] + r["costly_failures"][1] for r in results)
    costly_rate = total_costly / max(total_player_rounds, 1)

    # Threat escalation
    threat_ascending = 0
    for r in results:
        t = r["threat_per_round"]
        if len(t) >= 4:
            q1 = sum(t[:len(t)//4]) / max(len(t)//4, 1)
            q4 = sum(t[3*len(t)//4:]) / max(len(t) - 3*len(t)//4, 1)
            if q4 > q1:
                threat_ascending += 1
    threat_ascending_rate = threat_ascending / n

    near_loss_rate = sum(1 for r in results if r["near_loss"]) / n

    # Power fantasy
    total_wow = sum(len(r["wow_events"]) for r in results)
    avg_wow = total_wow / n
    pct_with_wow = sum(1 for r in results if r["wow_events"]) / n
    wow_types = defaultdict(int)
    for r in results:
        for _, types in r["wow_events"]:
            for t in types:
                wow_types[t] += 1

    # Contribution equity
    avg_equity = sum(r["equity"] for r in results) / n

    return {
        "num_games": n,
        "win_rate": win_rate,
        "avg_rounds": avg_rounds,
        "avg_team_vp": avg_team_vp,
        "avg_boss_vp": avg_boss_vp,
        "decision_density": {
            "avg_choices": avg_choices,
            "pct_high_choice": pct_high_choice,
        },
        "crisis_recovery": {
            "crisis_rate": crisis_rate,
            "recovery_rate": recovery_rate,
        },
        "dead_turns": {
            "avg_rate": dead_rate,
            "costly_failure_rate": costly_rate,
        },
        "difficulty": {
            "win_rate": win_rate,
        },
        "threat_escalation": {
            "ascending_rate": threat_ascending_rate,
            "near_loss_rate": near_loss_rate,
        },
        "power_fantasy": {
            "avg_wow": avg_wow,
            "pct_with_wow": pct_with_wow,
            "wow_types": dict(wow_types),
        },
        "contribution_equity": {
            "avg_equity": avg_equity,
        },
    }


# ─── Grading (cooperative lens) ─────────────────────────────────

def grade_coop(agg):
    grades = {}

    # 1. Decision Density (using pct_high_choice as proxy for 2+ meaningful options)
    v = agg["decision_density"]["pct_high_choice"]
    if v >= 0.85: grades["Decision Density"] = "A"
    elif v >= 0.70: grades["Decision Density"] = "B"
    elif v >= 0.50: grades["Decision Density"] = "C"
    elif v >= 0.30: grades["Decision Density"] = "D"
    else: grades["Decision Density"] = "F"

    # 2. Crisis Recovery
    cr = agg["crisis_recovery"]
    if cr["crisis_rate"] < 0.50:
        # Too few crises — cap at B
        if cr["recovery_rate"] >= 0.40: grades["Crisis Recovery"] = "B"
        elif cr["recovery_rate"] >= 0.30: grades["Crisis Recovery"] = "C"
        else: grades["Crisis Recovery"] = "D"
    else:
        if cr["recovery_rate"] >= 0.40: grades["Crisis Recovery"] = "A"
        elif cr["recovery_rate"] >= 0.30: grades["Crisis Recovery"] = "B"
        elif cr["recovery_rate"] >= 0.20: grades["Crisis Recovery"] = "C"
        elif cr["recovery_rate"] >= 0.10: grades["Crisis Recovery"] = "D"
        else: grades["Crisis Recovery"] = "F"

    # 3. Dead Turns
    v = agg["dead_turns"]["avg_rate"]
    if v < 0.05: grades["Dead Turns"] = "A"
    elif v < 0.10: grades["Dead Turns"] = "B"
    elif v < 0.20: grades["Dead Turns"] = "C"
    elif v < 0.35: grades["Dead Turns"] = "D"
    else: grades["Dead Turns"] = "F"

    # 4. Difficulty Balance
    wr = agg["difficulty"]["win_rate"]
    if 0.35 <= wr <= 0.55: grades["Difficulty Balance"] = "A"
    elif 0.25 <= wr <= 0.65: grades["Difficulty Balance"] = "B"
    elif 0.15 <= wr <= 0.75: grades["Difficulty Balance"] = "C"
    elif 0.08 <= wr <= 0.85: grades["Difficulty Balance"] = "D"
    else: grades["Difficulty Balance"] = "F"

    # 5. Threat Escalation
    te = agg["threat_escalation"]
    asc = te["ascending_rate"] >= 0.50
    near = te["near_loss_rate"]
    if asc and near >= 0.50: grades["Threat Escalation"] = "A"
    elif asc and near >= 0.40: grades["Threat Escalation"] = "B"
    elif asc or near >= 0.30: grades["Threat Escalation"] = "C"
    elif near >= 0.10: grades["Threat Escalation"] = "D"
    else: grades["Threat Escalation"] = "F"

    # 6. Power Fantasy
    v = agg["power_fantasy"]["pct_with_wow"]
    if v >= 0.70: grades["Power Fantasy"] = "A"
    elif v >= 0.50: grades["Power Fantasy"] = "B"
    elif v >= 0.30: grades["Power Fantasy"] = "C"
    elif v >= 0.15: grades["Power Fantasy"] = "D"
    else: grades["Power Fantasy"] = "F"

    # 7. Contribution Equity
    v = agg["contribution_equity"]["avg_equity"]
    if v >= 0.85: grades["Contribution Equity"] = "A"
    elif v >= 0.70: grades["Contribution Equity"] = "B"
    elif v >= 0.55: grades["Contribution Equity"] = "C"
    elif v >= 0.40: grades["Contribution Equity"] = "D"
    else: grades["Contribution Equity"] = "F"

    return grades


GRADE_MAP = {"A": 4, "B": 3, "C": 2, "D": 1, "F": 0}
GRADE_COLORS = {
    "A": "\033[92m", "B": "\033[94m", "C": "\033[93m",
    "D": "\033[91m", "F": "\033[91m",
}
RESET = "\033[0m"


def print_coop_report(agg):
    n = agg["num_games"]
    grades = grade_coop(agg)

    print(f"\n{'═' * 65}")
    print(f"  THE TUNNEL BRAWL v2.0 — SIEGE MODE FUN AUDIT")
    print(f"  {n} games · 2 players co-op vs Boss · cooperative lens")
    print(f"  Average game length: {agg['avg_rounds']:.1f} rounds")
    print(f"{'═' * 65}")

    # Overview
    print(f"\n{'─' * 65}")
    print(f"  GAME OVERVIEW")
    print(f"{'─' * 65}")
    print(f"  Team win rate:    {agg['win_rate']:.1%}")
    print(f"  Avg team VP:      {agg['avg_team_vp']:.1f}")
    print(f"  Avg Boss VP:      {agg['avg_boss_vp']:.1f}")

    dim_order = [
        "Decision Density", "Crisis Recovery", "Dead Turns",
        "Difficulty Balance", "Threat Escalation", "Power Fantasy",
        "Contribution Equity",
    ]

    details = {
        "Decision Density": [
            f"Avg card pair options per round: {agg['decision_density']['avg_choices']:.0f}",
            f"Rounds with 6+ options:          {agg['decision_density']['pct_high_choice']:.1%}",
        ],
        "Crisis Recovery": [
            f"Games entering crisis (Boss ≥60%): {agg['crisis_recovery']['crisis_rate']:.1%}",
            f"Recovery rate (win after crisis):   {agg['crisis_recovery']['recovery_rate']:.1%}",
        ],
        "Dead Turns": [
            f"Zero-agency rate (no cards):    {agg['dead_turns']['avg_rate']:.1%}",
            f"Costly failure rate (lost w/ cards): {agg['dead_turns']['costly_failure_rate']:.1%}",
            f"(Graded on zero-agency only — costly failures are dramatic, not boring)",
        ],
        "Difficulty Balance": [
            f"Team win rate: {agg['difficulty']['win_rate']:.1%} (sweet spot: 35-55%)",
        ],
        "Threat Escalation": [
            f"Games with ascending threat: {agg['threat_escalation']['ascending_rate']:.1%}",
            f"Near-loss rate (Boss ≥85%):  {agg['threat_escalation']['near_loss_rate']:.1%}",
        ],
        "Power Fantasy": [
            f"Games with wow moment: {agg['power_fantasy']['pct_with_wow']:.1%}",
            f"Avg wow per game:      {agg['power_fantasy']['avg_wow']:.1f}",
        ],
        "Contribution Equity": [
            f"Equity score: {agg['contribution_equity']['avg_equity']:.2f} (1.0 = perfectly equal)",
        ],
    }

    for i, dim in enumerate(dim_order, 1):
        g = grades[dim]
        color = GRADE_COLORS.get(g, "")
        print(f"\n{'─' * 65}")
        print(f"  {i}. {dim.upper():40s}     {color}[{g}]{RESET}")
        print(f"{'─' * 65}")
        for line in details.get(dim, []):
            print(f"  {line}")
        if dim in ("Power Fantasy",) and agg["power_fantasy"]["wow_types"]:
            for t, c in sorted(agg["power_fantasy"]["wow_types"].items(), key=lambda x: -x[1]):
                label = {"big_team_round": "Big team round (3+ VP)", "power_play": "Power Play",
                         "wild_win": "Wild activation win", "double_win": "Both players win"}.get(t, t)
                print(f"    {label}: {c:,}")

    # Overall
    grade_values = [GRADE_MAP[g] for g in grades.values()]
    gpa = sum(grade_values) / len(grade_values)
    if gpa >= 3.5: overall = "A"
    elif gpa >= 2.5: overall = "B"
    elif gpa >= 1.5: overall = "C"
    else: overall = "D"

    color = GRADE_COLORS.get(overall, "")
    print(f"\n{'═' * 65}")
    print(f"  OVERALL FUN GRADE                                 {color}[{overall}]{RESET}")
    print(f"{'═' * 65}")
    print(f"  GPA: {gpa:.2f} / 4.00")
    print(f"  Grades: {' '.join(f'{dim[0]}={g}' for dim, g in grades.items())}")

    strengths = [d for d, g in grades.items() if g == "A"]
    weaknesses = [d for d, g in grades.items() if g in ("D", "F")]
    if strengths:
        print(f"  Strengths: {', '.join(strengths)}")
    if weaknesses:
        print(f"  Weaknesses: {', '.join(weaknesses)}")

    print(f"\n{'═' * 65}\n")
    return grades, overall, gpa


# ─── CLI ─────────────────────────────────────────────────────────

def load_config(config_path=None):
    if config_path:
        with open(config_path, 'r') as f:
            return json.load(f)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    for c in [os.path.join(script_dir, "config.json"),
              os.path.join(script_dir, "..", "config.json")]:
        if os.path.exists(c):
            with open(c, 'r') as f:
                return json.load(f)
    print("ERROR: config.json not found.", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="The Tunnel Brawl v2.0 — Siege Mode (Co-op)"
    )
    parser.add_argument("-n", "--num-games", type=int, default=500)
    parser.add_argument("-s", "--seed", type=int, default=1)
    parser.add_argument("--skill", type=float, default=1.0)
    parser.add_argument("--config", type=str, default=None)
    parser.add_argument("--json", type=str, default=None)
    parser.add_argument("-v", "--verbose", action="store_true")

    # Siege-specific overrides
    parser.add_argument("--team-vp", type=int, default=None)
    parser.add_argument("--boss-vp", type=int, default=None)
    parser.add_argument("--max-rounds", type=int, default=None)
    parser.add_argument("--escalation", type=int, default=None,
                        help="Boss rank bonus interval in rounds (default: 3)")

    args = parser.parse_args()

    config = load_config(args.config)

    # Ensure siege_rules section exists
    if "siege_rules" not in config:
        config["siege_rules"] = {}

    if args.team_vp:
        config["siege_rules"]["team_vp_threshold"] = args.team_vp
    if args.boss_vp:
        config["siege_rules"]["boss_vp_threshold"] = args.boss_vp
    if args.max_rounds:
        config["siege_rules"]["max_rounds"] = args.max_rounds
    if args.escalation:
        config["siege_rules"]["boss_escalation_interval"] = args.escalation

    print(f"Running Siege Mode: {args.num_games} games (seed={args.seed}, skill={args.skill})...",
          file=sys.stderr)

    agg = run_coop_batch(config, args.num_games, start_seed=args.seed, skill=args.skill)
    print_coop_report(agg)

    if args.json:
        with open(args.json, 'w') as f:
            json.dump(agg, f, indent=2, default=str)
