"""
simulate_game.py — Game loop for Whistle Stop
"""

import random
from typing import List, Optional, Tuple, Dict
from cards import Deck, HMCard
from game_state import GameState, Player, Route, ROUTE_CARDS_BEFORE_STATION
from simulate_round import simulate_round, RoundResult
from ai_player import AIPlayer


FACTION_NAMES = ["red", "blue", "green", "yellow"]


def create_game(
    num_players: int,
    player_names: Optional[List[str]] = None,
    factions: Optional[List[str]] = None,
    seed: Optional[int] = None
) -> GameState:
    if player_names is None:
        player_names = [f"Player {i+1}" for i in range(num_players)]
    if factions is None:
        factions = [FACTION_NAMES[i % 4] for i in range(num_players)]

    deck = Deck(seed=seed)
    players = [
        Player(player_id=i, name=player_names[i], faction=factions[i])
        for i in range(num_players)
    ]
    gs = GameState(players=players, deck=deck)
    gs.setup()
    return gs


def play_game(
    num_players: int,
    ai_player_ids: Optional[List[int]] = None,
    human_choices: Optional[Dict[int, Tuple[HMCard, Optional[int], Optional[str]]]] = None,
    factions: Optional[List[str]] = None,
    seed: Optional[int] = None,
    verbose: bool = False,
    max_rounds: int = 50
) -> Tuple[GameState, List[RoundResult]]:
    ai_player_ids = ai_player_ids if ai_player_ids is not None else list(range(num_players))
    human_choices = human_choices or {}

    gs = create_game(num_players=num_players, factions=factions, seed=seed)

    if verbose:
        print(f"\n{'='*50}")
        print(f"WHISTLE STOP — {num_players} players")
        print(f"{'='*50}")
        print(f"Depot: {gs.route.cards[0].card}")
        print()

    round_results = []

    while not gs.is_game_over and gs.round_number < max_rounds:
        chosen_cards = {}
        dec_ranks = {}
        dec_factions = {}

        for pid in range(num_players):
            player = gs.player_by_id(pid)
            if pid in ai_player_ids:
                ai = AIPlayer(player, difficulty="normal")
                card, dec_r, dec_f = ai.choose_card(gs)
            else:
                if pid in human_choices:
                    card, dec_r, dec_f = human_choices[pid]
                else:
                    card = max(player.hand, key=lambda c: c.rank if not c.is_wild else 10)
                    dec_r, dec_f = None, None
            chosen_cards[pid] = card
            if dec_r is not None:
                dec_ranks[pid] = dec_r
            if dec_f is not None:
                dec_factions[pid] = dec_f

        result = simulate_round(
            gs, chosen_cards,
            declared_ranks=dec_ranks,
            declared_factions=dec_factions,
            verbose=verbose
        )
        round_results.append(result)

        if verbose:
            scores = ", ".join([f"P{p.player_id}:{p.score:.0f}" for p in gs.players])
            print(f"Round {result.round_number} | Scores: {scores} | "
                  f"Route: {gs.route.route_card_count()}/{ROUTE_CARDS_BEFORE_STATION}")

    if verbose:
        winner = gs.player_by_id(gs.winner_id)
        print(f"\n{'='*50}")
        print(f"GAME OVER — {gs.round_number} rounds")
        print(f"Winner: {winner.name} ({winner.score:.0f} VP)")
        print("Final Scores:")
        for p in sorted(gs.players, key=lambda x: x.score, reverse=True):
            star = " ⭐" if gs.station_placer_id == p.player_id else ""
            print(f"  {p.name}: {p.score:.0f} VP{star}")
        print(f"{'='*50}\n")

    return gs, round_results
