"""
ai_player.py — AI player logic for Whistle Stop
Greedy AI: picks highest movement, aims for high-value landings.
"""

import random
from typing import Optional, List, Tuple, Dict
from cards import HMCard
from game_state import GameState, Player, STATION_POS, ROUTE_CARDS_BEFORE_STATION


class AIPlayer:
    """Simple AI for Whistle Stop."""

    def __init__(self, player: Player, difficulty: str = "normal"):
        self.player = player
        self.difficulty = difficulty

    def choose_card(self, gs: GameState) -> Tuple[HMCard, Optional[int], Optional[str]]:
        """
        Choose the best card from hand.
        Strategy: maximize movement toward station, prefer own-faction for bonus steps.
        """
        hand = self.player.hand
        if not hand:
            raise ValueError("AI has no cards in hand!")

        best_card = None
        best_steps = -1
        best_dec_rank = None
        best_dec_faction = None

        for card in hand:
            if card.is_wild and card.rank == 0:
                # Wild 0: declare as rank 8 + own faction for 9 total steps
                for dec_rank in [8, 7, 6, 9]:
                    for dec_faction in [self.player.faction, None]:
                        steps = dec_rank + (1 if dec_faction == self.player.faction else 0)
                        if steps > best_steps:
                            best_steps = steps
                            best_card = card
                            best_dec_rank = dec_rank
                            best_dec_faction = dec_faction
            elif card.is_wild and card.rank == 10:
                # Wild 10: doubles score, 10 steps, no faction bonus
                if 10 > best_steps:
                    best_steps = 10
                    best_card = card
                    best_dec_rank = None
                    best_dec_faction = None
            else:
                steps = card.rank
                if card.faction == self.player.faction:
                    steps += 1
                if steps > best_steps:
                    best_steps = steps
                    best_card = card
                    best_dec_rank = None
                    best_dec_faction = None

        if best_card is None:
            best_card = random.choice(hand)

        return best_card, best_dec_rank, best_dec_faction


def run_ai_turns(
    gs: GameState,
    ai_player_ids: List[int],
    difficulty: str = "normal"
) -> Tuple[Dict[int, HMCard], Dict[int, int], Dict[int, str]]:
    """All AI players choose cards."""
    chosen = {}
    dec_ranks = {}
    dec_factions = {}

    for pid in ai_player_ids:
        player = gs.player_by_id(pid)
        ai = AIPlayer(player, difficulty=difficulty)
        card, dec_r, dec_f = ai.choose_card(gs)
        chosen[pid] = card
        if dec_r is not None:
            dec_ranks[pid] = dec_r
        if dec_f is not None:
            dec_factions[pid] = dec_f

    return chosen, dec_ranks, dec_factions
