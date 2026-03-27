#!/usr/bin/env python3
"""
Narration engine for Tailgate Turf War v3.0 (Streamlined Edition).

Plays a single game with full AI reasoning exposed, outputting a
detailed Markdown play-by-play that doubles as a rules walkthrough.

Usage:
  python narrate_game_v3.py --seed 42 -p 3
  python narrate_game_v3.py --seed 7 -p 3 --preset styles -o sample_game_v3.md
"""

import argparse
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cards import Card, FACTIONS, FACTION_ORDER
from game_state_v3 import GameStateV3, Zone
from ai_player_v3 import AIPlayerV3, STYLE_PROFILES


# ── Flavor ────────────────────────────────────────────────────────────

FACTION_EMOJI = {
    "RED": "🔴", "ORANGE": "🟠", "YELLOW": "🟡",
    "GREEN": "🟢", "BLUE": "🔵", "PURPLE": "🟣",
}

RANK_NAMES = {0: "Mascot", 10: "Superstar"}

STYLE_INTROS = {
    "balanced": "a well-rounded strategist who spreads and concentrates in equal measure",
    "aggressive": "a high-volume player who floods the lot with bodies",
    "sniper": "a precision player who lives for the Mascot combo kill-shot",
    "hoarder": "a patient operator saving firepower for the high-VP rounds",
    "spread": "a zone-coverage maximizer who drops one card everywhere",
}


def card_name(c: Card) -> str:
    rank_str = RANK_NAMES.get(c.rank, str(c.rank))
    return f"{c.faction.capitalize()} {rank_str}"


def card_list_str(cards: list) -> str:
    return ", ".join(card_name(c) for c in cards)


def strength_breakdown(cards: list, zone_faction: str) -> str:
    """Return a human-readable strength calculation string."""
    if not cards:
        return "0 (empty)"

    mascots = [c for c in cards if c.is_mascot]
    non_mascots = [c for c in cards if not c.is_mascot]

    if not non_mascots:
        return "0 (Mascot alone — worthless!)"

    best = max(non_mascots, key=lambda c: c.rank)
    best_rank = best.rank
    parts = []

    if mascots:
        parts.append(f"{best.rank}×2={best.rank*2} (Mascot doubles {card_name(best)})")
        best_rank *= 2
        extra = len(cards) - 2
    else:
        parts.append(f"{best.rank} ({card_name(best)})")
        extra = len(cards) - 1

    if extra > 0:
        parts.append(f"+{extra*2} ({extra} extra card{'s' if extra > 1 else ''} × 2)")

    has_anchor = any(c.faction == zone_faction and c.is_natural for c in cards)
    if has_anchor:
        anchor_card = next(c for c in cards if c.faction == zone_faction and c.is_natural)
        parts.append(f"+3 (Home Field — {card_name(anchor_card)} anchors)")
    else:
        # Explain WHY no home field if they have a matching non-natural
        matching_wilds = [c for c in cards
                          if c.faction == zone_faction and not c.is_natural]
        if matching_wilds:
            w = matching_wilds[0]
            parts.append(f"no Home Field ({card_name(w)} is rank {w.rank}, "
                         f"not a natural 1–9)")

    total = best_rank + max(0, extra) * 2 + (3 if has_anchor else 0)
    return f"{' '.join(parts)} = **{total}**"


# ── Narration ─────────────────────────────────────────────────────────

def narrate_game(num_players: int, seed: int,
                 player_configs=None) -> str:
    """Play one v3.0 game and return a Markdown narrative."""
    lines = []

    game = GameStateV3(num_players, seed=seed)

    # Create AIs
    ais = []
    for i in range(num_players):
        pc = player_configs[i] if player_configs and i < len(player_configs) else {}
        ai = AIPlayerV3(
            player_id=i,
            skill=pc.get("skill", 1.0),
            style=pc.get("style", "balanced"),
            rng_seed=seed * 100 + i
        )
        ais.append(ai)

    # ── Title ──
    lines.append("# Tailgate Turf War v3.0 — Narrated Game")
    lines.append("")
    lines.append(f"**Seed:** {seed} · **Players:** {num_players} · "
                 f"**Rules:** Streamlined Edition (Anchor Rule)")
    lines.append("")
    lines.append("> *The stadium doors won't open for another hour. "
                 "The parking lot is your battlefield. "
                 "Six zones. Three rounds. Every card counts.*")
    lines.append("")

    # ── Setup ──
    lines.append("---")
    lines.append("## Setup")
    lines.append("")
    lines.append("Six zone cards are laid out in a row: "
                 + " ".join(f"{FACTION_EMOJI[f]} {f.capitalize()}" for f in FACTIONS)
                 + ".")
    lines.append("")

    hand_size = len(game.players[0].hand)
    lines.append(f"Each player is dealt **{hand_size} cards** for the entire game — "
                 f"no re-draws across all three rounds.")
    lines.append("")

    for i, ai in enumerate(ais):
        hand = sorted(game.players[i].hand)
        by_faction = {}
        for c in hand:
            by_faction.setdefault(c.faction, []).append(c.rank)
        hand_str = " · ".join(
            f"{FACTION_EMOJI[f]} {', '.join(RANK_NAMES.get(r, str(r)) for r in ranks)}"
            for f, ranks in by_faction.items()
        )
        lines.append(f"**Player {i}** — *{ai.style_name.capitalize()}* "
                     f"({STYLE_INTROS.get(ai.style_name, '')})")
        lines.append(f"> Hand: {hand_str}")
        lines.append("")

    # ── Rounds ──
    for round_num in range(game.num_rounds):
        vp = game.zone_vp[round_num]
        game.current_round = round_num
        for p in game.players:
            p.zones_won_this_round = 0
        game.zones = [Zone(faction=f) for f in FACTIONS]

        lines.append("---")
        lines.append(f"## Round {round_num + 1} — {vp} VP per Zone")
        lines.append("")

        if round_num == 0:
            lines.append("> *The grill smoke hasn't even cleared yet and the "
                         "jockeying for position begins.*")
        elif round_num == 1:
            lines.append("> *Stakes are climbing. Cards are thinning. "
                         "Every deployment is a commitment.*")
        else:
            lines.append("> *Final round. 7 VP per zone. "
                         "Whatever you've been saving — this is the moment.*")
        lines.append("")

        # ── Step 1: Deploy ──
        lines.append("### Step 1: Deploy")
        lines.append("")
        lines.append("*All players simultaneously choose cards and place them "
                     "face-down on their Player Boards.*")
        lines.append("")

        all_deployments = {}
        for player in game.players:
            ai = ais[player.id]
            deploy, reasoning = ai.choose_deployment_with_reasoning(
                player, game, round_num
            )
            all_deployments[player.id] = deploy

            lines.append(f"**Player {player.id}** ({ai.style_name}):")
            for r in reasoning:
                lines.append(f"> {r}")
            lines.append("")

            game._execute_deployment(player, deploy)

        # ── Step 2: Reveal ──
        lines.append("### Step 2: Reveal")
        lines.append("")
        lines.append("*All cards flip face-up simultaneously.*")
        lines.append("")

        # Build a zone-by-zone reveal table
        lines.append("| Zone | Player | Cards | Count |")
        lines.append("|------|--------|-------|-------|")
        any_contest = False
        for zone in game.zones:
            players_here = zone.active_players
            if not players_here:
                lines.append(f"| {FACTION_EMOJI[zone.faction]} {zone.faction} "
                             f"| — | *uncontested* | 0 |")
                continue
            for pid in players_here:
                zp = zone.get_placement(pid)
                lines.append(f"| {FACTION_EMOJI[zone.faction]} {zone.faction} "
                             f"| P{pid} | {card_list_str(zp.cards)} "
                             f"| {len(zp.cards)} |")
            if len(players_here) > 1:
                any_contest = True
        lines.append("")

        # ── Step 3: Score ──
        lines.append("### Step 3: Score")
        lines.append("")

        zone_strengths = game._calculate_all_strength()

        # Show detailed strength breakdowns
        for zone in game.zones:
            faction = zone.faction
            strength_map = zone_strengths.get(faction, {})
            players_here = zone.active_players

            if not players_here:
                lines.append(f"**{FACTION_EMOJI[faction]} {faction}** — No one showed up. "
                             f"({vp} VP left on the table.)")
                lines.append("")
                continue

            lines.append(f"**{FACTION_EMOJI[faction]} {faction} Zone:**")
            lines.append("")

            for pid in players_here:
                zp = zone.get_placement(pid)
                bd = strength_breakdown(zp.cards, faction)
                lines.append(f"- P{pid}: {bd}")

            # Determine winner
            max_str = max(strength_map.values())
            winners = [pid for pid, s in strength_map.items() if s == max_str]

            if len(winners) == 1:
                w = winners[0]
                # Check if uncontested
                if len(players_here) == 1:
                    lines.append(f"- **P{w} wins uncontested → +{vp} VP** (free points!)")
                else:
                    losers = [pid for pid in players_here if pid != w]
                    loser_strs = [f"P{pid}={strength_map[pid]}" for pid in losers]
                    lines.append(f"- **P{w} wins** ({max_str} vs {', '.join(loser_strs)}) "
                                 f"**→ +{vp} VP**")
            else:
                split = math.ceil(vp / len(winners))
                tied = " and ".join(f"P{w}" for w in winners)
                lines.append(f"- **Tie between {tied}** (both {max_str}) "
                             f"**→ +{split} VP each**")
            lines.append("")

        # Actually score in the game state
        round_stats = game._score_round(zone_strengths, vp)

        # Scoreboard
        lines.append("#### Scoreboard")
        lines.append("")
        lines.append("| Player | Style | VP | Cards Left |")
        lines.append("|--------|-------|----|------------|")
        for p in game.players:
            lines.append(f"| P{p.id} | {ais[p.id].style_name} | "
                         f"**{p.score}** | {len(p.hand)} |")
        lines.append("")

    # ── Final ──
    lines.append("---")
    lines.append("## Final Results")
    lines.append("")

    final = game._compile_final_stats()
    scores = final["scores"]
    max_score = max(scores.values())

    lines.append("| Player | Style | Final VP | Zones Won | Cards Played |")
    lines.append("|--------|-------|----------|-----------|--------------|")
    for pid in range(num_players):
        medal = " 🏆" if scores[pid] == max_score else ""
        lines.append(f"| P{pid}{medal} | {ais[pid].style_name} | "
                     f"**{scores[pid]}** | "
                     f"{final['zones_won'][pid]} | "
                     f"{final['cards_played'][pid]} |")
    lines.append("")

    winner = final["winner"]
    if isinstance(winner, list):
        tied = " and ".join(f"P{w} ({ais[w].style_name})" for w in winner)
        lines.append(f"> **Tie game between {tied}!** "
                     f"Both claimed {final['zones_won'][winner[0]]} zones.")
    else:
        margin = max_score - sorted(scores.values())[-2]
        lines.append(f"> **Player {winner} ({ais[winner].style_name}) "
                     f"wins by {margin} VP!**")

        # Flavor closing
        style = ais[winner].style_name
        if style == "sniper":
            lines.append(f">\n> *The Mascot combo strikes again. "
                         f"Surgical precision beats brute force.*")
        elif style == "aggressive":
            lines.append(f">\n> *Sometimes showing up everywhere is enough. "
                         f"Volume has its own kind of dominance.*")
        elif style == "hoarder":
            lines.append(f">\n> *Patience pays. Saving the big guns for Round 3 "
                         f"proved decisive.*")
        elif style == "spread":
            lines.append(f">\n> *A card in every zone. Free points add up fast "
                         f"when no one's covering the margins.*")
        else:
            lines.append(f">\n> *Adaptable, measured, and always in the right place. "
                         f"The balanced approach takes the tailgate.*")

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("*Generated by the Tailgate Turf War v3.0 simulation engine.*")

    return "\n".join(lines)


# ── CLI ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Tailgate Turf War v3.0 — Narrated Game"
    )
    parser.add_argument("-s", "--seed", type=int, default=42)
    parser.add_argument("-p", "--players", type=int, default=3)
    parser.add_argument("-o", "--output", type=str, default=None)
    parser.add_argument("--preset", type=str, default=None,
                        choices=["experts", "styles", "mixed"])
    parser.add_argument("--styles", type=str, default=None,
                        help="Comma-separated styles (e.g. 'sniper,balanced,hoarder')")

    args = parser.parse_args()

    player_configs = None
    if args.preset:
        style_list = list(STYLE_PROFILES.keys())
        if args.preset == "experts":
            player_configs = [{"skill": 1.0, "style": "balanced"}
                              for _ in range(args.players)]
        elif args.preset == "styles":
            player_configs = [{"skill": 1.0, "style": style_list[i % len(style_list)]}
                              for i in range(args.players)]
        elif args.preset == "mixed":
            player_configs = [{"skill": 1.0, "style": "balanced"}]
            player_configs += [{"skill": 0.5, "style": "balanced"}
                               for _ in range(args.players - 1)]

    if args.styles:
        styles = [s.strip() for s in args.styles.split(",")]
        player_configs = [{"skill": 1.0, "style": s} for s in styles]

    narrative = narrate_game(args.players, args.seed, player_configs)

    if args.output:
        with open(args.output, 'w') as f:
            f.write(narrative)
        print(f"Narrative written to {args.output}")
    else:
        print(narrative)


if __name__ == "__main__":
    main()
