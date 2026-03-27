from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from cards import Card, Deck, SUIT_PRIORITY, build_bid_brawl_deck


@dataclass
class BidPlay:
    player_id: int
    card: Card
    rerolled: bool = False
    predicted_strength: float = 0.0
    effective_rank: float = 0.0
    actual_position: int = 0
    expected_position: int = 0
    prize_taken: Optional[Card] = None
    fed_to: Optional[int] = None
    heart_draw: Optional[Card] = None
    diamond_peek: Optional[Card] = None
    flair_gained: int = 0


@dataclass
class PlayerState:
    pid: int
    hand: List[Card] = field(default_factory=list)
    prize_cards: List[Card] = field(default_factory=list)
    discard_pile: List[Card] = field(default_factory=list)
    clubs_public: bool = False
    reroll_used: bool = False
    style_name: str = "balanced"
    skill: float = 0.5
    flair: int = 0

    @property
    def score(self) -> int:
        return sum(card.points for card in self.prize_cards) + min(3, self.flair)

    def bid_options(self) -> List[Card]:
        return [card for card in self.hand if card.can_bid]

    def remove_card(self, card: Card):
        self.hand.remove(card)


class GameState:
    def __init__(self, config: dict, num_players: int, seed: int = 1):
        self.config = config
        self.num_players = num_players
        self.seed = seed
        self.rng = random.Random(seed)
        self.deck = Deck(build_bid_brawl_deck())
        self.deck.shuffle(self.rng)
        self.global_discard: List[Card] = []
        self.players: List[PlayerState] = []
        self.round_history: List[dict] = []
        self.final_round_triggered = False
        self.game_over = False
        self.market_size = config["market_size"][str(num_players)]
        self.max_rounds = config.get("max_rounds_2p", 8) if num_players == 2 else 99
        self.setup()

    def setup(self):
        for pid in range(self.num_players):
            hand = self.deck.draw(self.config["hand_size"])
            self.players.append(PlayerState(pid=pid, hand=hand, clubs_public=True))

    def assign_profiles(self, profiles: List[dict]):
        for player, profile in zip(self.players, profiles):
            player.style_name = profile.get("style", "balanced")
            player.skill = profile.get("skill", 0.5)

    def draw_cards(self, n: int) -> List[Card]:
        if self.deck.size < n and self.num_players >= 3 and self.global_discard:
            self.deck.add_to_bottom(self.global_discard)
            self.global_discard = []
            self.deck.shuffle(self.rng)
        return self.deck.draw(n)

    def reveal_market(self) -> List[Card]:
        return self.draw_cards(self.market_size)

    def reveal_spike_prize(self) -> Optional[Card]:
        extra = self.draw_cards(1)
        return extra[0] if extra else None

    def rank_bids(self, plays: List[BidPlay]) -> List[BidPlay]:
        return sorted(
            plays,
            key=lambda play: (-play.effective_rank, SUIT_PRIORITY.get(play.card.suit, 99), -play.predicted_strength, play.player_id),
        )

    def underdog_push_player(self) -> Optional[int]:
        scores = [p.score for p in self.players]
        lowest = min(scores)
        lows = [p.pid for p in self.players if p.score == lowest]
        return lows[0] if len(lows) == 1 else None

    def choose_reroll_player(self, plays: List[BidPlay]) -> Optional[PlayerState]:
        eligible = [p for p in self.players if not p.reroll_used]
        if not eligible:
            return None
        lowest_score = min(p.score for p in self.players)
        lowest = [p for p in eligible if p.score == lowest_score]
        if len(lowest) != 1:
            return None
        target = lowest[0]
        play = next((pl for pl in plays if pl.player_id == target.pid), None)
        if not play or play.card.bid_rank >= 10:
            return None
        market_values = sorted((c.points for c in self.reveal_cache), reverse=True)
        if market_values and market_values[-1] >= play.card.points + 2:
            return target
        return None

    def maybe_mark_final_round(self) -> bool:
        total_needed = sum(max(0, self.config["hand_size"] - len(p.hand)) for p in self.players)
        if self.num_players == 2:
            return False
        if total_needed > self.deck.size + len(self.global_discard):
            self.final_round_triggered = True
            return True
        return False

    def replenish_hands(self):
        for player in self.players:
            need = max(0, self.config["hand_size"] - len(player.hand))
            if need:
                player.hand.extend(self.draw_cards(need))

    def play_round(self, ais: List[object]) -> dict:
        if self.game_over:
            raise RuntimeError("game already over")
        market = self.reveal_market()
        spike_prize = self.reveal_spike_prize()
        self.reveal_cache = market[:]
        if not market:
            self.game_over = True
            return {"market": [], "plays": [], "scores": [p.score for p in self.players]}

        underdog_pid = self.underdog_push_player()
        plays: List[BidPlay] = []
        score_snapshot = {p.pid: p.score for p in self.players}
        for player, ai in zip(self.players, ais):
            card, predicted = ai.choose_bid(player, market[:] + ([spike_prize] if spike_prize else []), score_snapshot, self.num_players)
            player.remove_card(card)
            effective_rank = card.bid_rank + 1 if player.pid == underdog_pid and card.bid_rank <= 9 else card.bid_rank
            plays.append(BidPlay(player_id=player.pid, card=card, predicted_strength=predicted, effective_rank=effective_rank))

        ranked_initial = self.rank_bids(plays)
        for idx, play in enumerate(sorted(plays, key=lambda p: p.predicted_strength, reverse=True), start=1):
            play.expected_position = idx

        reroll_player = None
        if self.config.get("underdog_reroll") and self.num_players >= 3:
            reroll_player = self.choose_reroll_player(plays)
        if reroll_player is not None:
            reroll_player.reroll_used = True
            reroll_play = next(play for play in plays if play.player_id == reroll_player.pid)
            reroll_play.rerolled = True
            self.global_discard.append(reroll_play.card)
            ranked = [play for play in ranked_initial if play.player_id != reroll_player.pid]
        else:
            ranked = ranked_initial

        available_prizes = sorted(market, key=lambda c: c.points, reverse=True)
        for pos, play in enumerate(ranked, start=1):
            play.actual_position = pos
            if not available_prizes:
                continue
            if pos == 1 and spike_prize is not None:
                best_normal = available_prizes[0]
                prize = spike_prize if spike_prize.points >= best_normal.points else available_prizes.pop(0)
            else:
                prize = available_prizes.pop(0)
            play.prize_taken = prize
            self.players[play.player_id].prize_cards.append(prize)

        if reroll_player is not None and available_prizes:
            reroll_play = next(play for play in plays if play.player_id == reroll_player.pid)
            reroll_play.prize_taken = available_prizes.pop(0)
            self.players[reroll_player.pid].prize_cards.append(reroll_play.prize_taken)
        elif reroll_player is not None and spike_prize is not None and all(p.prize_taken != spike_prize for p in plays):
            self.global_discard.append(spike_prize)

        if reroll_player is None and spike_prize is not None and all(p.prize_taken != spike_prize for p in plays):
            self.global_discard.append(spike_prize)

        if self.num_players == 2:
            p0, p1 = ranked_initial
            self.players[p1.player_id].discard_pile.append(p0.card)
            self.players[p0.player_id].discard_pile.append(p1.card)
            p0.fed_to = p1.player_id
            p1.fed_to = p0.player_id
        else:
            for idx, play in enumerate(ranked):
                winner_pid = play.player_id
                self.players[winner_pid].discard_pile.append(play.card)
                play.fed_to = winner_pid
                if idx + 1 < len(ranked):
                    losing_play = ranked[idx + 1]
                    self.players[winner_pid].discard_pile.append(losing_play.card)
                    losing_play.fed_to = winner_pid
            if reroll_player is not None:
                reroll_play = next(play for play in plays if play.player_id == reroll_player.pid)
                reroll_play.fed_to = None

        for play in plays:
            if play.fed_to is not None and play.fed_to != play.player_id and play.card.bid_rank >= 11:
                self.players[play.player_id].flair = min(3, self.players[play.player_id].flair + 1)
                play.flair_gained = 1

        for play in ranked:
            if play.card.suit == "Hearts" and play.actual_position == 1:
                drawn = self.draw_cards(1)
                if drawn:
                    self.players[play.player_id].hand.extend(drawn)
                    play.heart_draw = drawn[0]

        for play in plays:
            if play.card.suit == "Diamonds" and (play.actual_position == 0 or play.actual_position > 1):
                peek = self.deck.peek(1)
                if peek:
                    play.diamond_peek = peek[0]

        pre_replenish_final = self.maybe_mark_final_round()
        self.replenish_hands()

        round_record = {
            "round": len(self.round_history) + 1,
            "market": market,
            "spike_prize": spike_prize,
            "underdog_push": underdog_pid,
            "plays": plays,
            "scores_after": {p.pid: p.score for p in self.players},
            "leader": max(self.players, key=lambda p: (p.score, -p.pid)).pid,
            "final_round_triggered": pre_replenish_final,
        }
        self.round_history.append(round_record)

        if self.num_players == 2 and len(self.round_history) >= self.max_rounds:
            self.game_over = True
        elif self.final_round_triggered:
            self.game_over = True
        elif any(not p.bid_options() for p in self.players):
            self.game_over = True

        return round_record

    def final_scores(self) -> Dict[int, int]:
        return {p.pid: p.score for p in self.players}
