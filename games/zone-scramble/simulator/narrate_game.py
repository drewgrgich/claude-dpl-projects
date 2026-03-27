#!/usr/bin/env python3
"""
Zone Scramble — Single-game narration engine.

Plays one game with full AI reasoning exposed and writes a Markdown file
that reads like play-by-play commentary.
"""

from __future__ import annotations
import argparse
import json
import os
from typing import List, Optional

from cards import Card
from game_state import GameState
from ai_player import HeuristicAI


def narrate_game(config: dict, seed: int,
                 player_configs: Optional[List[dict]] = None,
                 max_turns: int = 200) -> str:
    """Play one game and return Markdown narration."""

    game = GameState(config, seed=seed)
    lines: List[str] = []

    def emit(text: str):
        lines.append(text)

    # Create AIs
    ais = []
    for i in range(2):
        pc = player_configs[i] if player_configs and i < len(player_configs) else {}
        ais.append(HeuristicAI(
            skill=pc.get("skill", 1.0),
            style=pc.get("style", "balanced"),
            aggression=pc.get("aggression", 0.5),
            rng_seed=seed * 100 + i,
        ))

    # Setup
    def draft_fn(pid, available, num_to_pick, gs):
        return ais[pid].choose_factions(pid, available, num_to_pick, gs)

    game.full_setup(draft_fn=draft_fn)

    emit(f"# Zone Scramble — Narrated Game (Seed {seed})")
    emit("")
    emit(f"**P0 factions:** {', '.join(game.players[0].command_factions)}  ")
    emit(f"**P1 factions:** {', '.join(game.players[1].command_factions)}  ")
    emit(f"**P0 style:** {ais[0].style_name} (skill={ais[0].skill}, aggression={ais[0].aggression})  ")
    emit(f"**P1 style:** {ais[1].style_name} (skill={ais[1].skill}, aggression={ais[1].aggression})  ")
    emit("")
    emit("---")
    emit("")

    turn_count = 0
    current_round_display = 1

    while not game.game_over and turn_count < max_turns:
        player = game.get_current_player()
        ai = ais[player.id]
        pid = player.id

        # Round header
        round_display = game.current_round + 1
        if round_display != current_round_display:
            current_round_display = round_display
            emit(f"\n## Round {round_display}\n")

        turn_in_round = game.current_turn_in_round // 2 + 1

        # Arena state
        arena_state = []
        for a in game.arenas:
            monsters = ", ".join(f"{s.card}(P{s.owner})" for s in a.slots)
            turf = a.turf_color or "none"
            arena_state.append(f"{a.name}[turf={turf}]: {monsters or 'empty'}")

        emit(f"### Turn {turn_in_round} — P{pid} "
             f"(VP: {player.total_vp} | Hand: {len(player.hand)} cards)")
        arena_display = " | ".join(arena_state)
        emit(f"*Arenas: {arena_display}*")
        emit(f"*Hand: {player.hand}*")
        emit("")

        # Green peek
        if player.has_faction("GREEN") and not game.draw_pile.empty:
            top = game.draw_pile.peek(1)[0]
            should_discard = ai.decide_green_peek(player, top, game)
            game.action_green_peek(player, should_discard)
            if should_discard:
                emit(f"> GREEN Peek: sees {top} — discards it")
            else:
                emit(f"> GREEN Peek: sees {top} — keeps it on top")
            emit("")

        # Choose action with reasoning
        action, reasoning = ai.choose_action_with_reasoning(player, game)
        action_type = action["type"]

        emit(f"> **Thinking...**")
        for line in reasoning.split("\n"):
            emit(f"> {line}")
        emit("")

        if action_type == "play_monster":
            card = action["card"]
            arena_name = action["arena"]

            result = game.action_play_monster(
                player, card, arena_name,
                chameleon_turf_choice=action.get("chameleon_turf_choice"),
            )

            if result["success"]:
                emit(f"**Plays {card} to {arena_name}.**")
                if result.get("drew"):
                    emit(f"Draws {result['drew']}.")

                # Blue bounce
                if card.faction == "BLUE" and player.has_faction("BLUE"):
                    bounce = ai.choose_blue_bounce(player, game, arena_name, card)
                    if bounce:
                        game.action_blue_bounce(player, arena_name, bounce)
                        emit(f"BLUE Misdirection: bounces {bounce} back to hand.")

                # Signature
                sig = ai.choose_signature(player, game, card, arena_name)
                if sig:
                    sig_type = sig["type"]
                    if sig_type == "sig_red":
                        r = game.sig_red_heroic_intervention(
                            player, sig["source_arena"],
                            sig["target_arena"], sig["monster"])
                        if r["success"]:
                            emit(f"RED Heroic Intervention: moves {sig['monster']} "
                                 f"from {sig['source_arena']} to {sig['target_arena']}.")
                    elif sig_type == "sig_yellow":
                        r = game.sig_yellow_double_install(
                            player, sig["arena"], sig["card"],
                            sig.get("chameleon_turf_choice"))
                        if r["success"]:
                            emit(f"YELLOW Double-Install: plays {sig['card']} to {sig['arena']}.")
                    elif sig_type == "sig_green":
                        r = game.sig_green_scheduled_outcome(player)
                        if r["success"] and len(r["drawn"]) == 2:
                            drawn = r["drawn"]
                            keep = max(drawn, key=lambda c: c.rank)
                            discard = [c for c in drawn if c != keep][0]
                            game.sig_green_keep_choice(player, keep, discard)
                            emit(f"GREEN Scheduled Outcome: draws {drawn}, keeps {keep}.")
                        elif r["success"] and len(r["drawn"]) == 1:
                            player.hand.append(r["drawn"][0])
                            emit(f"GREEN Scheduled Outcome: draws {r['drawn'][0]}.")
                    elif sig_type == "sig_blue":
                        r = game.sig_blue_swap(
                            player, sig["arena"],
                            sig["my_card"], sig["their_card"])
                        if r["success"]:
                            emit(f"BLUE Swap: exchanges {sig['my_card']} for {sig['their_card']}.")
                    elif sig_type == "sig_purple":
                        r = game.sig_purple_rewind(player)
                        if r["success"]:
                            emit(f"PURPLE Rewind: takes {r['card']} from discard.")

                if result.get("roar"):
                    roar = result["roar"]
                    emit(f"\n**🎉 CROWD ROARS in {roar['arena']}!** "
                         f"P0: {roar['totals'][0]} vs P1: {roar['totals'][1]}")
                    if roar["winner"] is not None:
                        emit(f"**P{roar['winner']} wins {roar['arena']}!** (+{roar['vp_awarded']} VP)")
                    else:
                        emit(f"**Tie — nobody scores.**")
            else:
                emit(f"*Play failed: {result.get('error')}*")

        elif action_type == "fumble":
            game.action_fumble(player, action["discard"])
            emit(f"**Fumbles the Bag:** discards {action['discard']}.")

        elif action_type == "bench":
            if action.get("discard") and action["discard"] in player.hand:
                game.action_bench(player, action["discard"])
            emit(f"**Takes The Bench** (no legal plays, fumbles exhausted).")

        emit("")

        # End turn
        end_result = game.end_turn()

        if end_result.get("round_ended"):
            emit(f"\n---\n**End of Round {game.current_round}**")
            for arena_res in end_result.get("arena_scores", []):
                emit(f"  Arena {arena_res['arena']}: P0={arena_res['totals'][0]} vs "
                     f"P1={arena_res['totals'][1]} → "
                     f"{'P' + str(arena_res['winner']) + ' wins' if arena_res['winner'] is not None else 'Tie'}")
            for pid_m, got in end_result.get("momentum", {}).items():
                if got:
                    emit(f"  P{pid_m} earns **Momentum** (+1 VP)!")
            emit(f"\nScoreboard: P0={game.players[0].total_vp} VP | "
                 f"P1={game.players[1].total_vp} VP")
            emit("---\n")

        turn_count += 1

    # Final
    emit(f"\n## Final Result\n")
    for p in game.players:
        emit(f"**P{p.id}:** {p.total_vp} VP "
             f"(base: {p.vp}, trophies: {len(p.trophy_pile)})")
    emit("")
    if game.winner is not None:
        emit(f"**🏆 P{game.winner} wins!**")
    else:
        emit(f"**Draw!**")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def load_config(path: str = None) -> dict:
    if path is None:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        path = os.path.join(script_dir, "config.json")
    with open(path) as f:
        return json.load(f)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Narrate a single Zone Scramble game"
    )
    parser.add_argument("-s", "--seed", type=int, default=42,
                        help="Random seed for the game")
    parser.add_argument("-o", "--output", type=str, default=None,
                        help="Output Markdown file (default: stdout)")
    parser.add_argument("--config", type=str, default=None)
    parser.add_argument("--p0-style", type=str, default="balanced")
    parser.add_argument("--p1-style", type=str, default="balanced")
    parser.add_argument("--p0-skill", type=float, default=1.0)
    parser.add_argument("--p1-skill", type=float, default=1.0)

    args = parser.parse_args()
    config = load_config(args.config)

    player_configs = [
        {"skill": args.p0_skill, "style": args.p0_style},
        {"skill": args.p1_skill, "style": args.p1_style},
    ]

    md = narrate_game(config, seed=args.seed, player_configs=player_configs)

    if args.output:
        with open(args.output, 'w') as f:
            f.write(md)
        print(f"Narration saved to {args.output}")
    else:
        print(md)
