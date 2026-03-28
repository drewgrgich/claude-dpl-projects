"""Simulate a complete Championship Arena game."""

import random
import json
from typing import List, Tuple, Optional
from cards import HMCard, Deck
from game_state import GameState, Player, SpectatorDeck, TALENTS
from simulate_round import simulate_round
from ai_player import create_ai_player


def setup_game(num_players: int, config: dict) -> GameState:
    """Set up a new game."""
    # Create deck
    deck = Deck(config["suits"], config["ranks"]["min"], config["ranks"]["max"])

    # Create spectator deck
    spec_deck = SpectatorDeck()
    spec_deck.reset()

    # Create players
    players = []
    for i in range(num_players):
        hand = deck.draw(config["hand_size"])
        talent = random.choice(TALENTS)
        p = Player(
            id=i,
            hand=hand,
            talent=talent,
            fp=0,
            score=0,
        )
        players.append(p)

    # Create game state
    gs = GameState(
        deck=deck,
        spectator_deck=spec_deck,
        players=players,
        round_number=0,
    )

    # Pick initial active rings
    gs.pick_active_rings(config["rings_per_round"])

    # Fill stunt pool
    gs.fill_stunt_pool(6)

    return gs


def simulate_game(
    num_players: int,
    config: dict,
    verbose: bool = False
) -> Tuple[Optional[Player], int, List[Player]]:
    """
    Simulate a complete game.
    Returns (winner, total_rounds, all_players).
    """
    gs = setup_game(num_players, config)
    max_rounds = 50  # safety valve

    for _ in range(max_rounds):
        gs, _ = simulate_round(gs)
        if gs.winner:
            break

    return gs.winner, gs.round_number, gs.players


def run_narrated_game(num_players: int, config: dict) -> Tuple[GameState, str]:
    """Run a game with full narration."""
    gs = setup_game(num_players, config)
    full_narration = ""
    max_rounds = 50

    full_narration += f"\n{'#'*60}\n"
    full_narration += f"#  CHAMPIONSHIP ARENA — {num_players} PLAYERS\n"
    full_narration += f"{'#'*60}\n"
    full_narration += f"\n🎭 Welcome to the Arena!\n\n"
    full_narration += f"RINGS: {[r.color for r in gs.active_rings]}\n"
    full_narration += f"STUNT POOL: {gs.stunt_pool}\n"
    full_narration += f"TALENTS:\n"
    for p in gs.players:
        full_narration += f"  {p}: {p.talent['name']} — {p.talent['desc']}\n"

    for p in gs.players:
        full_narration += f"\n{p}'s hand: {p.hand}\n"

    for _ in range(max_rounds):
        gs, round_text = simulate_round(gs)
        full_narration += round_text

        if gs.winner:
            full_narration += f"\n{'='*60}\n"
            full_narration += f"FINAL SCORES:\n"
            for p in sorted(gs.players, key=lambda x: x.fp, reverse=True):
                full_narration += f"  {p}: {p.fp} FP\n"
            full_narration += f"\n🏆 CHAMPION: {gs.winner} with {gs.winner.fp} FP!\n"
            break

    return gs, full_narration


if __name__ == "__main__":
    with open("config.json") as f:
        cfg = json.load(f)
    gs, text = run_narrated_game(3, cfg)
    print(text)
