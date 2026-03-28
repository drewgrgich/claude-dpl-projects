#!/usr/bin/env python3
"""
narrated_game.py — Human-readable narrated game of Whistle Stop
"""

import random
from simulate_game import play_game, create_game
from game_state import GameState, Player, STATION_POS, ROUTE_CARDS_BEFORE_STATION
from ai_player import AIPlayer
from cards import HMCard


def narrate_game(num_players: int = 3, seed: int = 42, difficulty: str = "normal"):
    """Play and narrate a complete game."""
    random.seed(seed)

    print(f"\n{'🎬' * 20}")
    print(f"WHISTLE STOP — A Narrated Game")
    print(f"{'🎬' * 20}")
    print(f"\n🎯 {num_players} players  |  Seed: {seed}  |  {difficulty.title()}")
    print()

    gs = create_game(num_players=num_players, seed=seed)

    print(f"📋 SETUP")
    print(f"   Depot: {gs.route.cards[0].card}")
    for p in gs.players:
        print(f"   {p.name} [{p.faction.upper()}] — {', '.join(str(c) for c in p.hand)}")
    print()

    round_num = 0
    while not gs.is_game_over and round_num < 30:
        round_num += 1
        print(f"{'━' * 50}")
        print(f"🎴 ROUND {round_num}")
        print(f"{'━' * 50}")

        chosen_cards = {}
        dec_ranks = {}
        dec_factions = {}

        for pid in range(num_players):
            player = gs.player_by_id(pid)
            ai = AIPlayer(player, difficulty=difficulty)
            card, dec_r, dec_f = ai.choose_card(gs)
            chosen_cards[pid] = card
            if dec_r is not None:
                dec_ranks[pid] = dec_r
            if dec_f is not None:
                dec_factions[pid] = dec_f

        print("   🫣 Secret choices made...")
        for pid in range(num_players):
            player = gs.player_by_id(pid)
            card = chosen_cards[pid]
            dec_r = dec_ranks.get(pid)
            dec_f = dec_factions.get(pid)
            eff_rank = dec_r if dec_r is not None else card.rank
            eff_faction = dec_f if dec_f else (card.faction or "wild")
            print(f"   {player.name}: {card} → [{eff_faction} {eff_rank}]")

        def sort_key(pid):
            c = chosen_cards[pid]
            r = dec_ranks.get(pid)
            return r if r is not None else c.rank

        order = sorted(range(num_players), key=sort_key)
        names = [gs.player_by_id(p).name for p in order]
        print(f"\n   📣 Reveal: {' → '.join(names)}")

        from simulate_round import simulate_round
        result = simulate_round(
            gs, chosen_cards,
            declared_ranks=dec_ranks,
            declared_factions=dec_factions,
            verbose=True
        )

        print(f"\n   📊 After Round {round_num}:")
        for p in gs.players:
            star = " 🏁" if gs.station_placer_id == p.player_id else ""
            route_count = gs.route.route_card_count()
            print(f"   {p.name}: {p.score:.0f} VP | pos {p.position}/{STATION_POS} | "
                  f"route {route_count}/{ROUTE_CARDS_BEFORE_STATION}{star}")

        if gs.is_game_over:
            break
        print()

    print(f"\n{'🏆' * 20}")
    print(f"GAME OVER!")
    print(f"{'🏆' * 20}")
    print(f"\n📊 FINAL SCORES:")
    sorted_p = sorted(gs.players, key=lambda p: p.score, reverse=True)
    medals = ["🥇", "🥈", "🥉", "  "]
    for i, p in enumerate(sorted_p):
        m = medals[i] if i < 3 else "  "
        star = " ⭐ Station placed!" if gs.station_placer_id == p.player_id else ""
        print(f"   {m} {p.name}: {p.score:.0f} VP{star}")

    winner = sorted_p[0]
    print(f"\n⏱️ {gs.round_number} rounds")
    print(f"🎉 Winner: {winner.name} with {winner.score:.0f} VP!")

    return gs


if __name__ == "__main__":
    import sys
    num_players = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else random.randint(1, 9999)
    difficulty = sys.argv[3] if len(sys.argv) > 3 else "normal"
    narrate_game(num_players=num_players, seed=seed, difficulty=difficulty)
