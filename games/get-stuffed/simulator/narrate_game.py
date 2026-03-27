"""
Narration engine for Get Stuffed.

Plays a single game with full AI reasoning exposed, outputting a
Markdown play-by-play. Invaluable for verifying the engine and
understanding game flow.

Usage:
    python narrate_game.py --seed 42 -p 4
    python narrate_game.py --seed 42 -p 3 -o game_narration.md
"""

import argparse
import json
import os
import sys
from typing import List, Optional

from cards import Card, FACTION_NAMES, FACTION_SYMBOLS
from game_state import GameState
from ai_player import HeuristicAI


def narrate_game(config: dict, num_players: int, seed: int,
                 max_turns: int = 300,
                 player_configs: Optional[List[dict]] = None) -> str:
    """Play one game and return Markdown narration."""
    lines = []

    def emit(text: str = ""):
        lines.append(text)

    game = GameState(config, num_players, seed=seed)

    # Create AIs
    ais: List[HeuristicAI] = []
    for i in range(num_players):
        pc = {}
        if player_configs and i < len(player_configs):
            pc = player_configs[i]
        ais.append(HeuristicAI(
            player_id=i,
            skill=pc.get("skill", 1.0),
            style=pc.get("style", "balanced"),
            aggression=pc.get("aggression", 0.5),
            rng_seed=seed + i * 1000,
        ))

    game.setup()

    # Header
    emit(f"# Get Stuffed — Narrated Game")
    emit(f"")
    emit(f"**Seed:** {seed} | **Players:** {num_players} | **Max Turns:** {max_turns}")
    emit(f"")

    # Player info
    for i, ai in enumerate(ais):
        emit(f"- **P{i}**: skill={ai.skill:.1f}, style={ai.style_name}, aggression={ai.aggression:.1f}")
    emit(f"")

    # Starting state
    emit(f"## Setup")
    emit(f"")
    emit(f"Starting pit: **{game.pit_top}** ({game.pit_top})")
    emit(f"")
    for p in game.players:
        hand_str = ", ".join(str(c) for c in sorted(p.hand, key=lambda c: (c.faction, c.rank)))
        emit(f"**P{p.id} hand** ({p.hand_size} cards): {hand_str}")
    emit(f"")
    emit(f"---")

    turn_count = 0
    forced_scavenge_active = False

    while not game.game_over and turn_count < max_turns:
        player = game.current_player
        ai = ais[player.id]
        turn_count += 1
        game.turn_number = turn_count

        emit(f"")
        emit(f"### Turn {turn_count} — P{player.id} "
             f"(hand: {player.hand_size} | pit: {game.pit_top}"
             f"{' [declared: ' + game.declared_faction + ']' if game.declared_faction else ''})")
        emit(f"")

        # Show hand
        hand_str = ", ".join(repr(c) for c in sorted(player.hand, key=lambda c: (c.faction, c.rank)))
        emit(f"Hand: [{hand_str}]")
        emit(f"")

        if forced_scavenge_active:
            forced_scavenge_active = False
            emit(f"**FORCED SCAVENGE** (Dib It! target)")
            emit(f"")
            scav_result = game.scavenge(player, mercy_decision_fn=ai.decide_mercy)
            _narrate_scavenge(emit, scav_result, player)

            if scav_result.get("game_over"):
                break

            if game.sugar_crash and player.hand_size > 0:
                dump = ai.choose_sugar_crash_dump(player, game)
                if dump:
                    player.remove_card(dump)
                    game.pit.append(dump)
                    emit(f"")
                    emit(f"**Sugar Crash free dump:** plays {dump}")
                    if player.hand_size == 0:
                        game.game_over = True
                        game.winner = player.id
                        emit(f"")
                        emit(f"**P{player.id} WINS!** (Sugar Crash dump was last card)")
                        break

            game.advance_turn()
            continue

        # AI thinking
        playable = player.get_playable(game.pit_top, game.declared_faction)
        emit(f"> **Playable cards:** {len(playable)} — "
             f"{', '.join(repr(c) for c in playable) if playable else 'NONE'}")

        card, decl = ai.choose_card_to_play(player, game)

        if card is not None:
            emit(f"> **Decision:** Play {card}"
                 + (f" (declare {decl})" if decl else ""))
            emit(f"")

            power_decisions = ai.get_power_decisions(player, game)
            result = game.play_card(player, card, declared_faction=decl,
                                    power_decision_fn=power_decisions)

            if result.get("game_over"):
                emit(f"")
                emit(f"## 🎉 P{player.id} WINS! Last card played!")
                break

            if result.get("power_triggered"):
                emit(f"")
                emit(f"**Power: {result['power_triggered']}**")
                if result.get("power_result"):
                    _narrate_power(emit, result["power_result"], player, game)

            # Check Dib It
            if game.forced_scavenge_player is not None:
                forced_scavenge_active = True
                game.current_player_idx = game.forced_scavenge_player
                game.forced_scavenge_player = None
                continue

            # Sugar Crash
            if game.sugar_crash and player.hand_size > 0:
                dump = ai.choose_sugar_crash_dump(player, game)
                if dump:
                    player.remove_card(dump)
                    game.pit.append(dump)
                    emit(f"")
                    emit(f"**Sugar Crash free dump:** plays {dump}")
                    if player.hand_size == 0:
                        game.game_over = True
                        game.winner = player.id
                        emit(f"")
                        emit(f"## 🎉 P{player.id} WINS! (Sugar Crash dump)")
                        break

        else:
            emit(f"> **Decision:** Can't play — must Scavenge!")
            emit(f"")
            scav_result = game.scavenge(player, mercy_decision_fn=ai.decide_mercy)
            _narrate_scavenge(emit, scav_result, player)

            if scav_result.get("game_over"):
                break

            if game.sugar_crash and player.hand_size > 0:
                dump = ai.choose_sugar_crash_dump(player, game)
                if dump:
                    player.remove_card(dump)
                    game.pit.append(dump)
                    emit(f"")
                    emit(f"**Sugar Crash free dump:** plays {dump}")
                    if player.hand_size == 0:
                        game.game_over = True
                        game.winner = player.id
                        emit(f"")
                        emit(f"## 🎉 P{player.id} WINS! (Sugar Crash dump)")
                        break

            # Check Dib It from scavenge power
            if game.forced_scavenge_player is not None:
                forced_scavenge_active = True
                game.current_player_idx = game.forced_scavenge_player
                game.forced_scavenge_player = None
                continue

        # Status line
        emit(f"")
        status = " | ".join(f"P{p.id}:{p.hand_size}" for p in game.players)
        emit(f"*Hands: {status} | Direction: {'→' if game.play_direction == 1 else '←'}"
             f"{' | 🍬 SUGAR CRASH' if game.sugar_crash else ''}*")

        game.advance_turn()

    if turn_count >= max_turns and not game.game_over:
        emit(f"")
        emit(f"## ⏰ GAME TIMED OUT after {max_turns} turns!")
        emit(f"")
        for p in game.players:
            emit(f"P{p.id}: {p.hand_size} cards remaining")

    # Final summary
    emit(f"")
    emit(f"---")
    emit(f"")
    emit(f"## Game Summary")
    emit(f"")
    emit(f"- **Winner:** {'P' + str(game.winner) if game.winner is not None else 'None (timed out)'}")
    emit(f"- **Turns:** {turn_count}")
    emit(f"- **Reshuffles:** {game.reshuffle_count}")
    emit(f"- **Sugar Crash:** {'Yes (turn ' + str(game.stats['sugar_crash_turn']) + ')' if game.sugar_crash else 'No'}")
    emit(f"- **Total scavenges:** {game.stats['scavenges']}")
    emit(f"- **Mercy saves:** {game.stats['mercy_saves']}")
    emit(f"")
    emit(f"### Power Triggers")
    emit(f"")
    for faction in ["RED", "ORANGE", "YELLOW", "GREEN", "BLUE", "PURPLE"]:
        name = FACTION_SYMBOLS[faction] + " " + FACTION_NAMES[faction]
        count = game.stats["powers_triggered"][faction]
        emit(f"- {name}: {count}")

    return "\n".join(lines)


def _narrate_scavenge(emit, result: dict, player):
    """Add scavenge narration."""
    if result["flipped_card"]:
        emit(f"Flips: **{result['flipped_card']}**")
        if result["flipped_matched"]:
            emit(f"✅ Matches the pit! Played directly.")
            if result.get("power_triggered"):
                emit(f"Power triggers: **{result['power_triggered']}**")
        else:
            emit(f"❌ No match. Added to hand. Penalty: **{result['penalty_amount']}** cards.")
            if result["mercy_save"]:
                emit(f"🙏 **MERCY!** Drew {result['mercy_card']} on card #{result['cards_drawn']} — matches pit!")
                if result.get("power_triggered"):
                    emit(f"Power triggers: **{result['power_triggered']}**")
            else:
                emit(f"Drew {result['cards_drawn']} penalty cards. "
                     f"P{player.id} now has **{player.hand_size}** cards.")


def _narrate_power(emit, power_result: dict, player, game):
    """Add power resolution narration."""
    power = power_result.get("power", "")

    if power == "Hot Potato!":
        if power_result.get("fizzled"):
            emit(f"Fizzles — P{player.id} has no cards to give!")
        elif power_result.get("gave_card"):
            emit(f"P{player.id} gives {power_result['card']} to P{power_result['target']}")

    elif power == "Dib It!":
        emit(f"P{power_result['target']} must Scavenge on their next turn!")

    elif power == "Re-Tinker!":
        if power_result["choice"] == "reverse":
            emit(f"Play direction REVERSED!")
        else:
            emit(f"P{player.id} takes an EXTRA TURN!")

    elif power == "I Foresaw This!":
        if power_result.get("took_card"):
            emit(f"Peeked and took: {power_result['took_card']}")
        if power_result.get("played_card"):
            emit(f"Follow-up play: {power_result['played_card']}")
            if power_result.get("play_result", {}).get("game_over"):
                emit(f"")
                emit(f"## 🎉 P{player.id} WINS! (Foresaw follow-up was last card)")

    elif power == "Sleight of Paw":
        emit(f"Blind swap with P{power_result.get('target', '?')}: "
             f"gave {power_result.get('gave', '?')}, got {power_result.get('received', '?')}")

    elif power == "VANISH!":
        if power_result.get("swapped"):
            emit(f"Swaps entire hand with P{power_result['target']}! "
                 f"P{player.id} now has {power_result['my_new_size']}, "
                 f"P{power_result['target']} has {power_result['their_new_size']}")
        else:
            emit(f"Chooses NOT to swap hands.")

    elif power == "Time Warp":
        emit(f"Wild played — faction declared for next player.")


# ─── CLI ──────────────────────────────────────────────

def load_config(config_path: Optional[str] = None) -> dict:
    if config_path:
        with open(config_path) as f:
            return json.load(f)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    for c in [os.path.join(script_dir, "config.json"),
              os.path.join(script_dir, "..", "config.json")]:
        if os.path.exists(c):
            with open(c) as f:
                return json.load(f)
    raise FileNotFoundError("config.json not found!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Narrate a single Get Stuffed game")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("-p", "--players", type=int, default=4)
    parser.add_argument("--max-turns", type=int, default=300)
    parser.add_argument("-o", "--output", type=str, default=None,
                        help="Output file (default: stdout)")
    parser.add_argument("--config", type=str, default=None)

    # Player config
    parser.add_argument("--skill", type=str, default=None)
    parser.add_argument("--styles", type=str, default=None)

    args = parser.parse_args()
    config = load_config(args.config)

    player_configs = None
    if args.skill:
        skills = [float(s) for s in args.skill.split(",")]
        player_configs = [{"skill": s, "style": "balanced"} for s in skills]
    if args.styles:
        styles = args.styles.split(",")
        if player_configs is None:
            player_configs = [{"skill": 1.0, "style": s.strip()} for s in styles]
        else:
            for i, s in enumerate(styles):
                if i < len(player_configs):
                    player_configs[i]["style"] = s.strip()

    md = narrate_game(config, args.players, args.seed, args.max_turns, player_configs)

    if args.output:
        with open(args.output, 'w') as f:
            f.write(md)
        print(f"Narration saved to {args.output}")
    else:
        print(md)
