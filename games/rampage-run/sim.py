#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import random
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from enum import Enum
from statistics import mean
from typing import Dict, List, Optional, Tuple

FACTIONS = list("ABCDEF")
HAND_SIZE = 5
WIN_SCORE = 50


class Strategy(str, Enum):
    SAFE = "SAFE"
    AGGRESSIVE = "AGGRESSIVE"
    CALCULATED = "CALCULATED"
    GAMBLER = "GAMBLER"
    MIXED = "MIXED"


@dataclass(frozen=True)
class Card:
    rank: int
    faction: str

    @property
    def points(self) -> int:
        return self.rank


@dataclass
class Player:
    idx: int
    strategy: Strategy
    hand: List[Card] = field(default_factory=list)
    banked: int = 0
    crash_shield: bool = True
    crashes: int = 0
    folds: int = 0
    plays: int = 0
    post_play_folds: int = 0
    bonuses: int = 0


@dataclass
class GameResult:
    winner: int
    scores: List[int]
    turns: int
    crash_count: int
    fold_count: int
    post_play_folds: int
    average_streak_banked: float
    highest_streak: int
    winner_strategy: str
    crashed_out_without_bonus: int
    bonuses_awarded: int
    deck_exhausted: bool


class RampageRunGame:
    def __init__(self, strategies: List[Strategy], seed: Optional[int] = None):
        self.random = random.Random(seed)
        self.players = [Player(idx=i, strategy=s) for i, s in enumerate(strategies)]
        self.draw_pile = [Card(rank, faction) for faction in FACTIONS for rank in range(11)]
        self.random.shuffle(self.draw_pile)
        for _ in range(HAND_SIZE):
            for p in self.players:
                p.hand.append(self.draw_pile.pop())
        self.streak_pile: List[Tuple[int, Card, int]] = []  # (effective_rank, card, player_idx)
        self.streak_total = 0
        self.current_target = 0
        self.last_player_to_play: Optional[int] = None
        self.turns = 0
        self.crash_count = 0
        self.fold_count = 0
        self.post_play_fold_count = 0
        self.banked_streaks: List[int] = []
        self.highest_streak = 0
        self.bonuses_awarded = 0
        self.crashed_out_without_bonus = 0
        self.deck_exhausted = False
        self.start_new_streak(force=True)
        self.current_player = self.find_starting_player()
        self.rounds_after_exhaustion_remaining: Optional[int] = None

    def find_starting_player(self) -> int:
        lows = []
        for p in self.players:
            min_rank = min(card.rank for card in p.hand)
            lows.append((min_rank, p.idx))
        lows.sort()
        return lows[0][1]

    def playable_cards(self, player: Player) -> List[Tuple[int, Card]]:
        out = []
        for c in player.hand:
            if c.rank == 0:
                out.append((max(self.current_target, 1), c))
            elif c.rank >= self.current_target:
                out.append((c.rank, c))
        return out

    def draw_to_five(self, player: Player):
        while len(player.hand) < HAND_SIZE and self.draw_pile:
            player.hand.append(self.draw_pile.pop())
        if not self.draw_pile:
            self.deck_exhausted = True

    def start_new_streak(self, force: bool = False):
        if self.draw_pile:
            c = self.draw_pile.pop()
            effective = max(c.rank, 1) if c.rank == 0 else c.rank
            self.streak_pile = [(effective, c, -1)]
            self.current_target = effective
            self.streak_total = c.points
            self.highest_streak = max(self.highest_streak, self.streak_total)
            if not self.draw_pile:
                self.deck_exhausted = True
        elif force:
            raise RuntimeError("Cannot start streak without cards")
        else:
            # empty-deck rule: streak continues as-is
            self.deck_exhausted = True

    def should_post_play_fold(self, player: Player, played_rank: int) -> bool:
        playable_after = self.playable_cards(player)
        hand_pressure = sum(1 for c in player.hand if c.rank >= self.current_target or c.rank == 0)
        risk = self.current_target / 10
        total = self.streak_total
        s = player.strategy
        if s == Strategy.SAFE:
            return total >= 14 or risk >= 0.8 or hand_pressure <= 1
        if s == Strategy.AGGRESSIVE:
            return total >= 25 and (risk >= 0.9 or hand_pressure == 0)
        if s == Strategy.GAMBLER:
            return total >= 30 and self.random.random() < 0.2
        if s == Strategy.CALCULATED:
            continue_value = len(playable_after) * 2.3 + max(0, 8 - self.current_target)
            bank_value = total * (0.65 + 0.05 * (player.banked / 10))
            return bank_value >= continue_value + 3
        # MIXED
        if player.banked >= 35:
            return total >= 12
        if player.banked <= 10:
            return total >= 18 and risk >= 0.7
        return total >= 16 and (risk >= 0.8 or hand_pressure <= 1)

    def choose_action(self, player: Player):
        playable = self.playable_cards(player)
        total = self.streak_total
        risk = self.current_target / 10
        if playable:
            s = player.strategy
            crash_bias = 0.0
            if len(self.players) == 2 or (not self.draw_pile and self.deck_exhausted):
                crash_bias = -1.0
            elif s == Strategy.SAFE:
                crash_bias = 0.02 if total >= 20 else 0.0
            elif s == Strategy.AGGRESSIVE:
                crash_bias = 0.14 if total >= 18 else 0.05
            elif s == Strategy.GAMBLER:
                crash_bias = 0.22 if total >= 14 else 0.08
            elif s == Strategy.CALCULATED:
                expected_bonus = total * (0.45 if len(self.players) > 2 else 0.0)
                expected_bank = total * 0.9
                crash_bias = 0.18 if expected_bonus > expected_bank and risk >= 0.7 else 0.01
            else:  # MIXED
                crash_bias = 0.18 if total >= 22 else (0.03 if player.banked >= 25 else 0.08)

            fold_threshold = {
                Strategy.SAFE: 13,
                Strategy.AGGRESSIVE: 22,
                Strategy.GAMBLER: 26,
                Strategy.CALCULATED: 16,
                Strategy.MIXED: 17,
            }[s]
            if player.banked >= 35:
                fold_threshold -= 4
            if total >= fold_threshold and self.random.random() > crash_bias:
                return ("fold", None)
            if self.random.random() < crash_bias and self.last_player_to_play is not None:
                return ("crash", None)
            playable.sort(key=lambda x: (x[0], x[1].rank))
            if s == Strategy.SAFE:
                choice = playable[0]
            elif s == Strategy.AGGRESSIVE:
                choice = playable[-1]
            elif s == Strategy.GAMBLER:
                choice = playable[-1] if self.random.random() < 0.7 else self.random.choice(playable)
            elif s == Strategy.CALCULATED:
                choice = min(playable, key=lambda t: (t[0] + (0 if t[1].rank == 0 else 0.4 * t[1].rank), -t[1].rank))
            else:
                if total <= 10:
                    choice = playable[-1]
                elif risk >= 0.8:
                    choice = playable[0]
                else:
                    choice = playable[len(playable) // 2]
            return ("play", choice)
        return ("fold", None)

    def execute_play(self, player: Player, choice: Tuple[int, Card]):
        effective_rank, card = choice
        player.hand.remove(card)
        self.streak_pile.append((effective_rank, card, player.idx))
        self.current_target = effective_rank
        self.streak_total += card.points
        self.highest_streak = max(self.highest_streak, self.streak_total)
        self.last_player_to_play = player.idx
        player.plays += 1

    def execute_fold(self, player: Player, post_play: bool = False):
        player.banked += self.streak_total
        player.folds += 1
        self.fold_count += 1
        self.banked_streaks.append(self.streak_total)
        if post_play:
            player.post_play_folds += 1
            self.post_play_fold_count += 1
        self.streak_pile = []
        self.last_player_to_play = None
        self.draw_to_five(player)
        self.start_new_streak(force=False)

    def execute_crash(self, player: Player):
        player.crashes += 1
        self.crash_count += 1
        streak = self.streak_total
        if player.crash_shield:
            player.crash_shield = False
            self.crashed_out_without_bonus += 1
        else:
            prev = self.last_player_to_play
            no_bonus = len(self.players) == 2 or (not self.draw_pile and self.deck_exhausted) or prev is None
            if not no_bonus:
                self.players[prev].banked += streak
                self.players[prev].bonuses += 1
                self.bonuses_awarded += 1
        self.streak_pile = []
        self.last_player_to_play = None
        self.draw_to_five(player)
        self.start_new_streak(force=False)

    def maybe_trigger_endgame(self):
        if self.rounds_after_exhaustion_remaining is None and self.deck_exhausted:
            self.rounds_after_exhaustion_remaining = len(self.players)

    def is_over(self) -> bool:
        if any(p.banked >= WIN_SCORE for p in self.players):
            return True
        if self.rounds_after_exhaustion_remaining is not None and self.rounds_after_exhaustion_remaining <= 0:
            return True
        return False

    def play(self) -> GameResult:
        while not self.is_over() and self.turns < 1000:
            player = self.players[self.current_player]
            self.turns += 1
            action, payload = self.choose_action(player)
            if action == "play":
                self.execute_play(player, payload)
                if self.should_post_play_fold(player, payload[0]):
                    self.execute_fold(player, post_play=True)
            elif action == "fold":
                self.execute_fold(player)
            else:
                self.execute_crash(player)

            self.maybe_trigger_endgame()
            if self.rounds_after_exhaustion_remaining is not None:
                self.rounds_after_exhaustion_remaining -= 1
            if any(p.banked >= WIN_SCORE for p in self.players):
                break
            self.current_player = (self.current_player + 1) % len(self.players)

        scores = [p.banked for p in self.players]
        max_score = max(scores)
        contenders = [i for i, s in enumerate(scores) if s == max_score]
        if len(contenders) > 1:
            hand_counts = [(len(self.players[i].hand), i) for i in contenders]
            min_hand = min(v for v, _ in hand_counts)
            contenders = [i for v, i in hand_counts if v == min_hand]
        if len(contenders) > 1:
            crash_counts = [(self.players[i].crashes, i) for i in contenders]
            min_crash = min(v for v, _ in crash_counts)
            contenders = [i for v, i in crash_counts if v == min_crash]
        winner = contenders[0]
        return GameResult(
            winner=winner,
            scores=scores,
            turns=self.turns,
            crash_count=self.crash_count,
            fold_count=self.fold_count,
            post_play_folds=self.post_play_fold_count,
            average_streak_banked=mean(self.banked_streaks) if self.banked_streaks else 0.0,
            highest_streak=self.highest_streak,
            winner_strategy=self.players[winner].strategy.value,
            crashed_out_without_bonus=self.crashed_out_without_bonus,
            bonuses_awarded=self.bonuses_awarded,
            deck_exhausted=self.deck_exhausted,
        )


def run_games(num_games: int = 250, num_players: int = 4, seed: int = 7) -> Dict:
    rng = random.Random(seed)
    strategy_cycle = [Strategy.SAFE, Strategy.AGGRESSIVE, Strategy.CALCULATED, Strategy.GAMBLER, Strategy.MIXED]
    results: List[GameResult] = []
    strategy_wins = Counter()
    for game_idx in range(num_games):
        strategies = [strategy_cycle[(game_idx + i) % len(strategy_cycle)] for i in range(num_players)]
        rng.shuffle(strategies)
        game = RampageRunGame(strategies, seed=rng.randint(1, 10_000_000))
        result = game.play()
        results.append(result)
        strategy_wins[result.winner_strategy] += 1

    avg_scores = [mean([r.scores[i] for r in results]) for i in range(num_players)]
    summary = {
        "games": num_games,
        "players": num_players,
        "avg_turns": round(mean(r.turns for r in results), 2),
        "avg_crashes": round(mean(r.crash_count for r in results), 2),
        "avg_folds": round(mean(r.fold_count for r in results), 2),
        "avg_post_play_folds": round(mean(r.post_play_folds for r in results), 2),
        "avg_banked_streak": round(mean(r.average_streak_banked for r in results), 2),
        "avg_highest_streak": round(mean(r.highest_streak for r in results), 2),
        "avg_final_scores_by_seat": [round(x, 2) for x in avg_scores],
        "strategy_wins": dict(strategy_wins),
        "deck_exhaustion_rate": round(sum(1 for r in results if r.deck_exhausted) / num_games, 3),
        "avg_shield_crashes": round(mean(r.crashed_out_without_bonus for r in results), 2),
        "avg_bonuses_awarded": round(mean(r.bonuses_awarded for r in results), 2),
        "sample_scores": results[0].scores if results else [],
    }
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--games", type=int, default=250)
    parser.add_argument("--players", type=int, default=4)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    summary = run_games(num_games=args.games, num_players=args.players, seed=args.seed)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
