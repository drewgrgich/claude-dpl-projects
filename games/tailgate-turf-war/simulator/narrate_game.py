#!/usr/bin/env python3
"""
Narration engine for Tailgate Turf War.

Plays a single game with full AI reasoning exposed, outputting a
detailed Markdown play-by-play.

Usage:
  python narrate_game.py --seed 42 -p 3
  python narrate_game.py --seed 42 -p 3 -o game_report.md
"""

import argparse
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cards import Card, FACTIONS
from game_state import GameState
from ai_player import AIPlayer, STYLE_PROFILES


def narrate_game(config: dict, num_players: int, seed: int,
                 player_configs=None) -> str:
    """Play one game and return a Markdown narrative."""
    lines = []

    game = GameState(config, num_players, seed=seed)

    # Create AIs
    ais = []
    for i in range(num_players):
        pc = player_configs[i] if player_configs and i < len(player_configs) else {}
        ai = AIPlayer(
            player_id=i,
            skill=pc.get("skill", 1.0),
            style=pc.get("style", "balanced"),
            aggression=pc.get("aggression", 0.5),
            rng_seed=seed * 100 + i
        )
        ais.append(ai)

    # Header
    lines.append(f"# Tailgate Turf War — Game Narrative")
    lines.append(f"**Seed:** {seed} | **Players:** {num_players}")
    lines.append("")
    for i, ai in enumerate(ais):
        hand = sorted(game.players[i].hand)
        lines.append(f"**P{i}** — {ai.style_name} (skill={ai.skill:.1f}, "
                     f"aggression={ai.aggression:.1f})")
        lines.append(f"- Starting hand ({len(hand)} cards): {hand}")
    lines.append("")

    # Play with reasoning
    def deployment_fn(player, gs, round_num):
        ai = ais[player.id]
        deploy, reasoning = ai.choose_deployment_with_reasoning(player, gs, round_num)

        lines.append(f"\n#### P{player.id} ({ai.style_name}) — Deployment")
        for r in reasoning:
            lines.append(f"> {r}")
        lines.append("")

        return deploy

    # Run each round manually to inject narrative
    for round_num in range(config["game_rules"]["num_rounds"]):
        vp = config["game_rules"]["zone_vp_by_round"][round_num]
        lines.append(f"\n---\n## Round {round_num + 1} (VP per zone: {vp})\n")

        game.current_round = round_num
        for p in game.players:
            p.zones_won_this_round = 0
        game.zones = [__import__('game_state').Zone(faction=f) for f in FACTIONS]

        # Phase 1: Deployment with reasoning
        lines.append("### Phase 1: Deployment\n")
        for player in game.players:
            deploy = deployment_fn(player, game, round_num)
            game._execute_deployment(player, deploy, round_num)

        # Phase 2: Reveal
        lines.append("### Phase 2: Reveal\n")
        for zone in game.zones:
            for pid in zone.active_players:
                zp = zone.get_placement(pid)
                lines.append(f"- **{zone.faction}** Zone: P{pid} → {zp.cards}")
        lines.append("")

        # Phase 3: Mishaps
        lines.append("### Phase 3: Mishaps\n")
        old_log_len = len(game.log)
        game._resolve_mishaps(round_num)
        new_logs = game.log[old_log_len:]
        if any("Mishap" in l for l in new_logs):
            for l in new_logs:
                if "Mishap" in l:
                    lines.append(f"- {l.strip()}")
        else:
            lines.append("- No mishaps triggered")
        lines.append("")

        # Phase 4: Hype
        lines.append("### Phase 4: Hype Calculation\n")
        zone_hype = game._calculate_all_hype()
        for faction in FACTIONS:
            hype_map = zone_hype.get(faction, {})
            if hype_map:
                entries = ", ".join(f"P{pid}={h}" for pid, h in hype_map.items())
                lines.append(f"- **{faction}**: {entries}")
        lines.append("")

        # Phase 5: Scoring
        lines.append("### Phase 5: Scoring\n")
        old_log_len = len(game.log)
        game._score_round(zone_hype, vp)
        new_logs = game.log[old_log_len:]
        for l in new_logs:
            if l.strip():
                lines.append(f"- {l.strip()}")
        lines.append("")

        # Scoreboard
        lines.append("**Scoreboard:**")
        for p in game.players:
            lines.append(f"- P{p.id}: {p.score} VP ({len(p.hand)} cards in hand)")
        lines.append("")

    # Die-Hard Fan
    lines.append("\n---\n## Final: Die-Hard Fan Bonus\n")
    old_log_len = len(game.log)
    game._resolve_diehard_bonus()
    game.game_over = True
    new_logs = game.log[old_log_len:]
    for l in new_logs:
        if l.strip():
            lines.append(f"- {l.strip()}")
    lines.append("")

    # Final
    final = game._compile_final_stats()
    lines.append("## Final Results\n")
    lines.append("| Player | VP | Zones Won | Cards Played | Cards Saved |")
    lines.append("|--------|-----|-----------|-------------|-------------|")
    for pid in range(num_players):
        lines.append(f"| P{pid} ({ais[pid].style_name}) | "
                     f"{final['scores'][pid]} | "
                     f"{final['zones_won'][pid]} | "
                     f"{final['cards_played'][pid]} | "
                     f"{final['cards_remaining'][pid]} |")

    winner = final["winner"]
    if isinstance(winner, list):
        lines.append(f"\n**TIE between {['P'+str(w) for w in winner]}!**")
    else:
        lines.append(f"\n**Winner: P{winner} ({ais[winner].style_name})!**")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Tailgate Turf War — Single Game Narration"
    )
    parser.add_argument("-s", "--seed", type=int, default=42)
    parser.add_argument("-p", "--players", type=int, default=3)
    parser.add_argument("-o", "--output", type=str, default=None,
                        help="Output Markdown file")
    parser.add_argument("--config", type=str, default=None)
    parser.add_argument("--preset", type=str, default=None,
                        choices=["experts", "beginners", "mixed", "styles"])

    args = parser.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = args.config or os.path.join(script_dir, "config.json")
    with open(config_path) as f:
        config = json.load(f)

    player_configs = None
    if args.preset == "styles":
        style_list = list(STYLE_PROFILES.keys())
        player_configs = [{"skill": 1.0, "style": style_list[i % len(style_list)]}
                          for i in range(args.players)]

    narrative = narrate_game(config, args.players, args.seed, player_configs)

    if args.output:
        with open(args.output, 'w') as f:
            f.write(narrative)
        print(f"Narrative written to {args.output}")
    else:
        print(narrative)


if __name__ == "__main__":
    main()
