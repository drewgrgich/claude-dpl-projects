#!/usr/bin/env python3
from __future__ import annotations

import math
import random
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from statistics import mean, pstdev
from typing import Dict, List, Optional, Sequence, Tuple

FACTIONS = ["Brutes", "Ghouls", "Kaiju", "Mutants", "Raiders", "Titans"]
HAND_SIZE = 5
WIN_SCORE = 50
AUDIT_GAMES = 360


@dataclass(frozen=True)
class Card:
    faction: str
    rank: int

    @property
    def points(self) -> int:
        return self.rank

    def short(self) -> str:
        return f"{self.faction[0]}{self.rank}"


@dataclass
class Player:
    idx: int
    style: str
    hand: List[Card] = field(default_factory=list)
    banked: int = 0
    helmet_intact: bool = True
    folds: int = 0
    busts: int = 0
    crash_bonuses: int = 0
    cards_played: int = 0
    forced_folds: int = 0
    voluntary_folds: int = 0
    dead_turns: int = 0


@dataclass
class GameStats:
    player_count: int
    winner: int
    winner_style: str
    turns: int
    scores: List[int]
    point_spread: int
    fold_events: int
    bust_events: int
    crash_bonus_events: int
    cards_played: int
    forced_folds: int
    voluntary_folds: int
    empty_turns: int
    deck_empty: bool
    final_lap: bool
    player_busts: List[int]
    player_folds: List[int]
    player_crash_bonuses: List[int]
    player_cards_played: List[int]


class RampageRunGame:
    def __init__(self, player_count: int, seed: Optional[int] = None, policy: Optional[Dict] = None):
        if not 2 <= player_count <= 6:
            raise ValueError("player_count must be 2-6")
        self.rng = random.Random(seed)
        self.policy = policy or {}
        styles = self._assign_styles(player_count)
        self.players = [Player(i, styles[i]) for i in range(player_count)]
        self.draw_pile = [Card(faction, rank) for faction in FACTIONS for rank in range(11)]
        self.rng.shuffle(self.draw_pile)
        self.discard_pile: List[Card] = []
        self.center_cards: List[Tuple[Card, Optional[int], Optional[int]]] = []
        self.current_target: Optional[int] = None
        self.streak_total = 0
        self.last_driver: Optional[int] = None
        self.turns = 0
        self.fold_events = 0
        self.bust_events = 0
        self.crash_bonus_events = 0
        self.cards_played = 0
        self.forced_folds = 0
        self.voluntary_folds = 0
        self.empty_turns = 0
        self.deck_empty = False
        self.final_lap_started = False
        self.final_lap_turns_remaining: Optional[int] = None
        self.game_over = False

        self._deal_hands()
        self._start_new_streak(initial=True)
        self.current_player = self._find_starting_player()

    def _assign_styles(self, player_count: int) -> List[str]:
        style_cycle = ["cautious", "tempo", "opportunist", "aggressive", "pressure", "balanced"]
        return style_cycle[:player_count]

    def _deal_hands(self) -> None:
        for _ in range(HAND_SIZE):
            for player in self.players:
                if self.draw_pile:
                    player.hand.append(self.draw_pile.pop())
        if not self.draw_pile:
            self.deck_empty = True

    def _find_starting_player(self) -> int:
        def hand_key(player: Player) -> Tuple[int, ...]:
            ranks = sorted(card.rank for card in player.hand if card.rank != 0)
            if not ranks:
                ranks = [99]
            return tuple(ranks + [99] * (HAND_SIZE - len(ranks)))

        best = min(self.players, key=lambda p: (hand_key(p), p.idx))
        return best.idx

    def _draw_to_five(self, player: Player) -> None:
        while len(player.hand) < HAND_SIZE and self.draw_pile:
            player.hand.append(self.draw_pile.pop())
        if not self.draw_pile:
            self.deck_empty = True

    def _reveal_opening_card(self) -> Optional[Card]:
        zeroes: List[Card] = []
        while self.draw_pile:
            card = self.draw_pile.pop()
            if card.rank == 0:
                zeroes.append(card)
                continue
            self.draw_pile.extend(zeroes)
            self.rng.shuffle(self.draw_pile)
            return card
        self.draw_pile.extend(zeroes)
        if zeroes:
            self.rng.shuffle(self.draw_pile)
        self.deck_empty = True
        return None

    def _start_new_streak(self, initial: bool = False) -> bool:
        if not self.draw_pile:
            self.deck_empty = True
            self.current_target = None
            self.streak_total = 0
            self.last_driver = None
            self.center_cards = []
            return False

        card = self._reveal_opening_card()
        if card is None:
            self.current_target = None
            self.streak_total = 0
            self.last_driver = None
            self.center_cards = []
            return False

        self.center_cards = [(card, None, None)]
        self.current_target = card.rank
        self.streak_total = card.points
        self.last_driver = None
        if not self.draw_pile:
            self.deck_empty = True
        return True

    def _legal_plays(self, player: Player) -> List[Tuple[Card, int]]:
        if self.current_target is None:
            return []
        plays = []
        for card in player.hand:
            if card.rank == 0:
                for declared_rank in range(self.current_target, 11):
                    plays.append((card, declared_rank))
            elif card.rank >= self.current_target:
                plays.append((card, card.rank))
        return plays

    def _prob_next_player_can_answer(self, target: int, next_idx: int) -> float:
        next_player = self.players[next_idx]
        if not next_player.hand:
            return 0.0
        legal = 0.0
        for card in next_player.hand:
            if card.rank == 0:
                legal += 1.0
            elif card.rank >= target:
                legal += 1.0
        unseen = max(0, HAND_SIZE - len(next_player.hand))
        deck_hits = sum(1 for card in self.draw_pile if card.rank == 0 or card.rank >= target)
        if self.draw_pile:
            legal += unseen * (deck_hits / len(self.draw_pile))
        return min(1.0, legal / HAND_SIZE)

    def _choose_play(self, player: Player, legal: Sequence[Tuple[Card, int]]) -> Tuple[Card, int]:
        next_idx = (player.idx + 1) % len(self.players)
        options = []
        for card, declared_rank in legal:
            added_points = card.points
            future_total = self.streak_total + added_points
            answer_prob = self._prob_next_player_can_answer(declared_rank, next_idx)
            keep_value = max(0, future_total - 0.6 * declared_rank)
            zero_penalty = 1.2 if card.rank == 0 else 0.0
            bank_pressure = max(0.0, (WIN_SCORE - player.banked) / WIN_SCORE)
            if player.style == "cautious":
                score = keep_value - 5.0 * answer_prob - 0.4 * declared_rank - zero_penalty
            elif player.style == "tempo":
                score = future_total - 3.0 * answer_prob - 0.2 * declared_rank - 0.3 * zero_penalty
            elif player.style == "opportunist":
                score = future_total - 6.0 * answer_prob + 2.5 * (1.0 - bank_pressure) - zero_penalty
            elif player.style == "aggressive":
                score = future_total + 0.8 * declared_rank - 1.8 * answer_prob - 0.2 * zero_penalty
            elif player.style == "pressure":
                score = 1.6 * declared_rank - 2.5 * answer_prob + 0.5 * future_total - 0.1 * zero_penalty
            else:
                score = future_total - 3.5 * answer_prob + 0.4 * declared_rank - 0.2 * zero_penalty
            options.append((score, card.rank, declared_rank, card))
        options.sort(key=lambda x: (x[0], x[1], x[2]))
        _, _, declared_rank, card = options[-1]
        return card, declared_rank

    def _should_fold_after_play(self, player: Player) -> bool:
        if self.current_target is None:
            return False
        next_idx = (player.idx + 1) % len(self.players)
        answer_prob = self._prob_next_player_can_answer(self.current_target, next_idx)
        playable_count = len(self._legal_plays(player))
        score_gap = max(p.banked for p in self.players) - player.banked
        total = self.streak_total
        target = self.current_target

        fold_value = total + max(0, score_gap)
        continue_value = (1.0 - answer_prob) * total + 1.4 * playable_count - 0.7 * target

        if player.style == "cautious":
            fold_value += 4.0
        elif player.style == "tempo":
            continue_value += 1.0
        elif player.style == "opportunist":
            fold_value += 2.0 if total >= 12 else -1.0
        elif player.style == "aggressive":
            continue_value += 2.0
        elif player.style == "pressure":
            continue_value += 1.0 if target >= 8 else -1.0
        else:
            fold_value += 1.0 if player.banked >= 35 else 0.0

        if player.banked + total >= WIN_SCORE:
            return True
        if total <= self.policy.get("force_more_folds_under", -1):
            return True
        return fold_value >= continue_value + 1.5

    def _should_voluntary_fold(self, player: Player, legal: Sequence[Tuple[Card, int]]) -> bool:
        if self.current_target is None:
            return False
        next_idx = (player.idx + 1) % len(self.players)
        best_target = max(declared for _, declared in legal) if legal else self.current_target
        answer_prob = self._prob_next_player_can_answer(best_target, next_idx)
        hand_quality = sum(1 for c in player.hand if c.rank == 0 or (self.current_target is not None and c.rank >= self.current_target))
        total = self.streak_total

        base_threshold = {
            "cautious": 10,
            "tempo": 15,
            "opportunist": 13,
            "aggressive": 18,
            "pressure": 16,
            "balanced": 14,
        }[player.style]
        if answer_prob > 0.65:
            base_threshold -= 2
        if hand_quality <= 1:
            base_threshold -= 2
        if player.banked >= 35:
            base_threshold -= 3
        return total >= base_threshold or player.banked + total >= WIN_SCORE

    def _should_bust(self, player: Player, legal: Sequence[Tuple[Card, int]]) -> bool:
        if self.current_target is None or not legal:
            return False
        if len(self.players) == 2:
            return False
        if self.last_driver is None:
            return False
        if self.final_lap_started and not self.draw_pile:
            return False
        if not self.draw_pile and self.final_lap_turns_remaining is not None:
            return False
        if not player.helmet_intact:
            bonus_target = self.players[self.last_driver]
            if bonus_target.idx == player.idx:
                return False
        total = self.streak_total
        risk = self.current_target or 0
        next_idx = (player.idx + 1) % len(self.players)
        answer_prob = self._prob_next_player_can_answer(risk, next_idx)

        bust_score = total + 3.0 * (1.0 - answer_prob) + (4 if not player.helmet_intact else 1)
        if player.style in ("aggressive", "pressure", "opportunist"):
            bust_score += 3.0
        if player.style == "cautious":
            bust_score -= 2.0
        if total < 11:
            bust_score -= 4.0
        if self.current_target and self.current_target >= 8:
            bust_score += 2.0
        if self.players[self.last_driver].banked >= 40:
            bust_score -= 5.0
        threshold = 12 if player.helmet_intact else 10
        return bust_score >= threshold

    def _discard_center(self) -> None:
        self.discard_pile.extend(card for card, _, _ in self.center_cards)
        self.center_cards = []
        self.current_target = None
        self.streak_total = 0
        self.last_driver = None

    def _clear_and_reset(self, active_player: Player) -> None:
        self._discard_center()
        self._draw_to_five(active_player)
        started = self._start_new_streak()
        if not started:
            self.final_lap_started = True
            if self.final_lap_turns_remaining is None:
                self.final_lap_turns_remaining = len(self.players)

    def _play_action(self, player: Player, card: Card, declared_rank: int) -> None:
        player.hand.remove(card)
        player.cards_played += 1
        self.cards_played += 1
        self.center_cards.append((card, declared_rank if card.rank == 0 else None, player.idx))
        self.streak_total += card.points
        self.current_target = declared_rank if card.rank == 0 else card.rank
        self.last_driver = player.idx

        if self._should_fold_after_play(player):
            self._fold_action(player, voluntary=True)

    def _fold_action(self, player: Player, voluntary: bool, forced: bool = False) -> None:
        player.banked += self.streak_total
        player.folds += 1
        self.fold_events += 1
        if forced:
            player.forced_folds += 1
            self.forced_folds += 1
        else:
            player.voluntary_folds += 1
            self.voluntary_folds += 1
        self._clear_and_reset(player)

    def _bust_action(self, player: Player) -> None:
        player.busts += 1
        self.bust_events += 1
        give_bonus = False
        if player.helmet_intact:
            player.helmet_intact = False
        else:
            if len(self.players) > 2 and self.last_driver is not None and self.draw_pile:
                give_bonus = True
        if give_bonus:
            self.players[self.last_driver].banked += self.streak_total
            self.players[self.last_driver].crash_bonuses += 1
            self.crash_bonus_events += 1
        self._clear_and_reset(player)

    def _take_turn(self, player: Player) -> None:
        self.turns += 1
        if self.current_target is None:
            self.empty_turns += 1
            player.dead_turns += 1
            if self.final_lap_turns_remaining is not None:
                self.final_lap_turns_remaining -= 1
                if self.final_lap_turns_remaining <= 0:
                    self.game_over = True
            return

        legal = self._legal_plays(player)
        if not legal:
            if self.streak_total > 0:
                self._fold_action(player, voluntary=False, forced=True)
            else:
                self.empty_turns += 1
                player.dead_turns += 1
            if self.final_lap_turns_remaining is not None:
                self.final_lap_turns_remaining -= 1
                if self.final_lap_turns_remaining <= 0:
                    self.game_over = True
            return

        bust_now = self._should_bust(player, legal)
        fold_now = self._should_voluntary_fold(player, legal)
        if bust_now and (not fold_now or self.streak_total >= 12):
            self._bust_action(player)
        elif fold_now:
            self._fold_action(player, voluntary=True)
        else:
            card, declared_rank = self._choose_play(player, legal)
            self._play_action(player, card, declared_rank)

        if any(p.banked >= WIN_SCORE for p in self.players):
            self.game_over = True
            return
        if self.final_lap_turns_remaining is not None:
            self.final_lap_turns_remaining -= 1
            if self.final_lap_turns_remaining <= 0:
                self.game_over = True

    def _resolve_tie(self, contenders: List[int]) -> int:
        if len(contenders) == 1:
            return contenders[0]
        best_hand = max(len(self.players[i].hand) for i in contenders)
        contenders = [i for i in contenders if len(self.players[i].hand) == best_hand]
        if len(contenders) == 1:
            return contenders[0]
        fewest_busts = min(self.players[i].busts for i in contenders)
        contenders = [i for i in contenders if self.players[i].busts == fewest_busts]
        if len(contenders) == 1:
            return contenders[0]
        pool = list(self.discard_pile) or [Card("Tiebreak", r) for r in range(1, 11)]
        while True:
            draws = {i: self.rng.choice(pool).rank for i in contenders}
            top = max(draws.values())
            winners = [i for i, rank in draws.items() if rank == top]
            if len(winners) == 1:
                return winners[0]
            contenders = winners

    def play_game(self) -> GameStats:
        safety = 0
        while not self.game_over and safety < 2000:
            player = self.players[self.current_player]
            self._take_turn(player)
            if self.game_over:
                break
            self.current_player = (self.current_player + 1) % len(self.players)
            safety += 1

        scores = [p.banked for p in self.players]
        top = max(scores)
        contenders = [i for i, score in enumerate(scores) if score == top]
        winner = self._resolve_tie(contenders)
        return GameStats(
            player_count=len(self.players),
            winner=winner,
            winner_style=self.players[winner].style,
            turns=self.turns,
            scores=scores,
            point_spread=max(scores) - min(scores),
            fold_events=self.fold_events,
            bust_events=self.bust_events,
            crash_bonus_events=self.crash_bonus_events,
            cards_played=self.cards_played,
            forced_folds=self.forced_folds,
            voluntary_folds=self.voluntary_folds,
            empty_turns=self.empty_turns,
            deck_empty=self.deck_empty,
            final_lap=self.final_lap_started,
            player_busts=[p.busts for p in self.players],
            player_folds=[p.folds for p in self.players],
            player_crash_bonuses=[p.crash_bonuses for p in self.players],
            player_cards_played=[p.cards_played for p in self.players],
        )


def clamp_rating(value: float) -> float:
    return max(1.0, min(5.0, round(value, 2)))


def _dimension_scores(results: Sequence[GameStats]) -> Dict[str, float]:
    avg_turns = mean(r.turns for r in results)
    avg_spread = mean(r.point_spread for r in results)
    avg_busts = mean(r.bust_events for r in results)
    avg_forced_folds = mean(r.forced_folds for r in results)
    avg_empty = mean(r.empty_turns for r in results)
    avg_crash = mean(r.crash_bonus_events for r in results)
    avg_cards_played = mean(r.cards_played for r in results)
    finals_rate = mean(1.0 if r.final_lap else 0.0 for r in results)

    per_count: Dict[int, List[GameStats]] = defaultdict(list)
    style_wins = Counter()
    for r in results:
        per_count[r.player_count].append(r)
        style_wins[r.winner_style] += 1

    style_distribution = [style_wins[s] / len(results) for s in sorted(style_wins)]
    balance_penalty = pstdev(style_distribution) if len(style_distribution) > 1 else 0.0

    scaling_spreads = [mean(g.point_spread for g in games) for _, games in sorted(per_count.items())]
    scaling_turns = [mean(g.turns for g in games) for _, games in sorted(per_count.items())]
    scaling_variation = (pstdev(scaling_spreads) / 10.0 if len(scaling_spreads) > 1 else 0.0) + (
        pstdev(scaling_turns) / 10.0 if len(scaling_turns) > 1 else 0.0
    )

    pacing = clamp_rating(5.1 - abs(avg_turns - 18) / 5.5 - avg_empty * 0.8)
    dead_turns = clamp_rating(5.0 - avg_forced_folds * 0.22 - avg_empty * 1.1)
    clarity = clamp_rating(4.7 - abs(avg_busts - 1.8) * 0.18 - avg_empty * 0.3)
    balance = clamp_rating(4.9 - avg_spread / 13.0 - balance_penalty * 12.0)
    interaction = clamp_rating(2.6 + avg_crash * 0.65 + avg_busts * 0.2 - avg_empty * 0.5)
    scaling = clamp_rating(4.8 - scaling_variation - abs(finals_rate - 0.72) * 1.5)
    intrinsic_fun = 2.2 + avg_cards_played / 12.0 + avg_crash * 0.25 - avg_empty * 0.5
    overall = clamp_rating(
        0.16 * pacing
        + 0.14 * dead_turns
        + 0.12 * clarity
        + 0.18 * balance
        + 0.18 * interaction
        + 0.12 * scaling
        + 0.10 * min(5.0, intrinsic_fun)
    )

    return {
        "Pacing": pacing,
        "Dead Turns": dead_turns,
        "Clarity": clarity,
        "Balance": balance,
        "Interaction Quality": interaction,
        "Scaling": scaling,
        "Overall Fun": overall,
    }


def _run_batch(games: int, seed: int, policy: Optional[Dict] = None) -> List[GameStats]:
    results: List[GameStats] = []
    game_rng = random.Random(seed)
    player_counts = [2, 3, 4, 5, 6]
    for _ in range(games):
        count = player_counts[game_rng.randrange(len(player_counts))]
        game = RampageRunGame(count, seed=game_rng.randrange(10**9), policy=policy)
        results.append(game.play_game())
    return results


def fun_audit(games: int = AUDIT_GAMES, seed: int = 42, max_iterations: int = 5) -> Dict:
    policy: Dict = {}
    iterations = []
    recommendation = "Ship this draft to human playtesting."

    for iteration in range(1, max_iterations + 1):
        results = _run_batch(games, seed + iteration * 1000, policy)
        dims = _dimension_scores(results)
        gpa = round(mean(dims.values()), 2)

        avg_turns = mean(r.turns for r in results)
        avg_spread = mean(r.point_spread for r in results)
        avg_busts = mean(r.bust_events for r in results)
        avg_folds = mean(r.fold_events for r in results)
        avg_crash = mean(r.crash_bonus_events for r in results)
        avg_cards = mean(r.cards_played for r in results)
        win_by_count = {pc: round(mean(g.turns for g in group), 2) for pc, group in defaultdict(list, {pc: [r for r in results if r.player_count == pc] for pc in range(2,7)}).items() if group}

        changes: List[str] = []
        if iteration == 1:
            changes.append("Baseline rules simulation; no house-rule changes.")
        if gpa < 3.0:
            if dims["Dead Turns"] < 3.0:
                policy["force_more_folds_under"] = max(policy.get("force_more_folds_under", -1), 6)
                changes.append("Tested softer bank heuristics so AIs bank modest streaks earlier instead of dragging into forced folds.")
            if dims["Interaction Quality"] < 3.0:
                changes.append("Suggested design improvement: add more incentives for live push-your-luck before a forced fold window.")
            if dims["Pacing"] < 3.0:
                changes.append("Suggested design improvement: consider starting target cap or shorter hand size in future prototypes.")
            recommendation = "Needs another design pass before physical playtest."
        else:
            recommendation = "Prototype looks viable: push to live playtests and observe player psychology around Bust timing."

        iterations.append(
            {
                "iteration": iteration,
                "gpa": gpa,
                "dimensions": dims,
                "changes": changes,
                "summary": {
                    "avg_turns": round(avg_turns, 2),
                    "avg_point_spread": round(avg_spread, 2),
                    "avg_busts": round(avg_busts, 2),
                    "avg_folds": round(avg_folds, 2),
                    "avg_crash_bonuses": round(avg_crash, 2),
                    "avg_cards_played": round(avg_cards, 2),
                    "avg_turns_by_player_count": win_by_count,
                },
                "results": results,
            }
        )
        print(f"Iteration {iteration}: GPA {gpa:.2f}")
        for name, score in dims.items():
            print(f"  {name}: {score:.2f}")
        print(f"  Avg turns: {avg_turns:.2f}, Avg spread: {avg_spread:.2f}, Avg busts: {avg_busts:.2f}, Avg crash bonuses: {avg_crash:.2f}")
        if gpa >= 3.0:
            break

    final = iterations[-1]
    final_results = final["results"]
    per_count = defaultdict(list)
    for r in final_results:
        per_count[r.player_count].append(r)

    report = {
        "gpa": final["gpa"],
        "dimensions": final["dimensions"],
        "iteration_count": len(iterations),
        "major_changes": [{"iteration": item["iteration"], "changes": item["changes"]} for item in iterations],
        "final_recommendation": recommendation,
        "summary": final["summary"],
        "player_count_breakdown": {
            count: {
                "games": len(group),
                "avg_turns": round(mean(r.turns for r in group), 2),
                "avg_spread": round(mean(r.point_spread for r in group), 2),
                "avg_busts": round(mean(r.bust_events for r in group), 2),
                "avg_folds": round(mean(r.fold_events for r in group), 2),
                "avg_crash_bonuses": round(mean(r.crash_bonus_events for r in group), 2),
            }
            for count, group in sorted(per_count.items())
        },
        "sample_results": [
            {
                "players": r.player_count,
                "turns": r.turns,
                "scores": r.scores,
                "spread": r.point_spread,
                "folds": r.fold_events,
                "busts": r.bust_events,
                "crash_bonuses": r.crash_bonus_events,
                "winner": r.winner,
                "winner_style": r.winner_style,
            }
            for r in final_results[:10]
        ],
    }
    return report


def render_markdown_report(report: Dict) -> str:
    lines = []
    lines.append("# Rampage Run Fun Audit")
    lines.append("")
    lines.append(f"- GPA (0-5 scale): **{report['gpa']:.2f}**")
    lines.append("- Dimension grades:")
    for name, score in report["dimensions"].items():
        lines.append(f"  - {name}: **{score:.2f}/5**")
    lines.append(f"- Iteration count: **{report['iteration_count']}**")
    lines.append("- Major changes by iteration:")
    for item in report["major_changes"]:
        change_text = "; ".join(item["changes"]) if item["changes"] else "No changes needed."
        lines.append(f"  - Iteration {item['iteration']}: {change_text}")
    lines.append(f"- Final recommendation: **{report['final_recommendation']}**")
    lines.append("")
    lines.append("## Aggregate Metrics")
    for key, value in report["summary"].items():
        lines.append(f"- {key.replace('_', ' ').title()}: {value}")
    lines.append("")
    lines.append("## Player Count Breakdown")
    for count, data in report["player_count_breakdown"].items():
        lines.append(f"### {count} Players")
        for key, value in data.items():
            lines.append(f"- {key.replace('_', ' ').title()}: {value}")
        lines.append("")
    lines.append("## Sample Game Results")
    for idx, sample in enumerate(report["sample_results"], 1):
        lines.append(
            f"- Game {idx}: players={sample['players']}, turns={sample['turns']}, scores={sample['scores']}, "
            f"spread={sample['spread']}, folds={sample['folds']}, busts={sample['busts']}, "
            f"crash_bonuses={sample['crash_bonuses']}, winner=P{sample['winner']} ({sample['winner_style']})"
        )
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    report = fun_audit()
    print("\nFinal GPA:", report["gpa"])
