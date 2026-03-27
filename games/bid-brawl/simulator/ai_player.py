from __future__ import annotations

import random
from typing import List, Tuple

from cards import Card

STYLE_PROFILES = {
    "balanced": {"risk": 0.0, "feed_fear": 1.0, "heart_bias": 0.6, "diamond_bias": 0.4},
    "shark": {"risk": 1.0, "feed_fear": 0.7, "heart_bias": 0.7, "diamond_bias": 0.2},
    "sandbagger": {"risk": -0.6, "feed_fear": 1.3, "heart_bias": 0.3, "diamond_bias": 0.8},
    "spoiler": {"risk": 0.2, "feed_fear": 0.9, "heart_bias": 0.4, "diamond_bias": 0.7},
}


class BidBrawlAI:
    def __init__(self, skill: float = 0.6, style: str = "balanced", rng_seed: int = 1):
        self.skill = max(0.05, min(1.0, skill))
        self.style = style
        self.profile = STYLE_PROFILES.get(style, STYLE_PROFILES["balanced"])
        self.rng = random.Random(rng_seed)

    def choose_bid(self, player, market: List[Card], score_snapshot, num_players: int) -> Tuple[Card, float]:
        options = player.bid_options()
        scored = []
        market_points = sorted((card.points for card in market), reverse=True)
        best_prize = market_points[0] if market_points else 0
        worst_prize = market_points[-1] if market_points else 0
        my_score = score_snapshot[player.pid]
        max_score = max(score_snapshot.values()) if score_snapshot else 0
        trailing = my_score < max_score

        for card in options:
            value = 0.0
            rank = card.bid_rank
            expected_finish = self._estimate_finish(rank, options, num_players)
            value += max(0, best_prize - abs(expected_finish - 1) * 2.2)
            value += (rank - 7) * 0.45 * self.profile["risk"]
            value -= rank * 0.22 * self.profile["feed_fear"]
            if card.suit == "Hearts":
                value += self.profile["heart_bias"] * 1.4
                if rank >= 10:
                    value += 1.3
            if card.suit == "Diamonds":
                value += self.profile["diamond_bias"] * (1.1 if expected_finish > 1 else 0.2)
            if card.suit == "Spades":
                value += 0.8
            if trailing and rank >= 10:
                value += 1.8
            if not trailing and rank <= 6:
                value += 1.0
            if worst_prize >= 10 and rank <= 5:
                value += 0.8
            noise = self.rng.uniform(-2.5, 2.5) * (1.0 - self.skill)
            scored.append((value + noise, card))

        scored.sort(key=lambda x: (-x[0], x[1].bid_rank, x[1].tie_priority))
        chosen_score, chosen_card = scored[0]
        predicted = chosen_score + chosen_card.bid_rank * 0.2 + (0.4 if chosen_card.suit == "Spades" else 0)
        return chosen_card, predicted

    def _estimate_finish(self, rank: int, options: List[Card], num_players: int) -> int:
        stronger = sum(1 for card in options if card.bid_rank > rank)
        if rank >= 12:
            return 1
        if rank >= 9:
            return min(2, num_players)
        if rank >= 6:
            return min(3, num_players)
        return min(num_players, 4 + min(stronger, 1))
