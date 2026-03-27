#!/usr/bin/env python3
"""
Narration engine for the v0.1 custom-deck zone-control game.

Plays a single game with full play-by-play: card passing, condition cards,
simultaneous deployment, action card resolution, strength breakdowns, and
scoring — all in readable Markdown.

Usage:
  python narrate_game_v4.py --seed 42 -p 3
  python narrate_game_v4.py --seed 7 -p 3 --preset styles -o sample_game.md
"""

import argparse
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cards_v4 import (
    Card, COLORS, COLOR_ORDER,
    CARD_TYPE_NUMBER, CARD_TYPE_MASCOT, CARD_TYPE_ACTION, CARD_TYPE_DUD,
    ACTION_SHIELD, ACTION_BOMB, ACTION_SWAP, ACTION_BOUNTY, ACTION_RESOLUTION,
)
from game_state_v4 import GameStateV4, Zone, ConditionCard
from ai_player_v4 import AIPlayerV4, STYLE_PROFILES


# ── Flavor ─────────────────────────────────────────────────────────────

COLOR_EMOJI = {
    "red": "🔴", "blue": "🔵", "green": "🟢", "yellow": "🟡",
}

ACTION_EMOJI = {
    ACTION_SHIELD: "🛡️",
    ACTION_BOMB:   "💣",
    ACTION_SWAP:   "🔄",
    ACTION_BOUNTY: "💰",
}

STYLE_INTROS = {
    "balanced":   "a well-rounded strategist",
    "aggressive": "a high-volume player who floods every zone",
    "sniper":     "a precision player hunting mascot combos",
    "hoarder":    "a patient operator saving for later rounds",
    "spread":     "a zone-coverage maximizer",
}

CONDITION_DESCRIPTIONS = {
    "no_mascots":     "Mascots cannot be played this round.",
    "unique_colors":  "Each card you play must be a different color.",
    "max_cards_3":    "You may play at most 3 cards this round.",
    "max_2_zones":    "You may only play to 2 zones this round.",
    "min_3_zones":    "You must spread across at least 3 zones.",
    "lowest_wins":    "Lowest strength wins each zone!",
    "double_vp":      "Each zone is worth double VP this round.",
    "no_home_field":  "Home Field Advantage is disabled.",
    "ties_lose":      "Tied zones score zero — nobody wins.",
    "fewer_cards_wins_ties": "Ties broken by fewest cards.",
    "lone_wolf_bonus":"Uncontested zones give +3 bonus VP.",
    "big_stack_bonus":"3+ cards at a zone gives +2 bonus VP.",
}


def card_name(c: Card) -> str:
    """Human-readable card name."""
    if c.is_mascot:
        return f"{c.color.capitalize()} Mascot"
    if c.is_action:
        emoji = ACTION_EMOJI.get(c.action_type, "")
        return f"{emoji}{c.action_type.capitalize()} ({c.color.capitalize()})"
    if c.is_dud:
        return f"Dud ({c.color.capitalize()}, plays as 5)"
    return f"{c.color.capitalize()} {c.rank}"


def card_list_str(cards: list) -> str:
    if not cards:
        return "*nothing*"
    return ", ".join(card_name(c) for c in cards)


def hand_summary(hand: list) -> str:
    """Group hand by color for compact display."""
    by_color = {}
    specials = []
    for c in sorted(hand, key=lambda x: (COLOR_ORDER.get(x.color, 99), x.effective_rank)):
        if c.is_action:
            specials.append(f"{ACTION_EMOJI.get(c.action_type, '')}{c.action_type.capitalize()}")
        elif c.is_mascot:
            by_color.setdefault(c.color, []).append("M")
        elif c.is_dud:
            by_color.setdefault(c.color, []).append("D(5)")
        else:
            by_color.setdefault(c.color, []).append(str(c.rank))

    parts = []
    for color in COLORS:
        if color in by_color:
            emoji = COLOR_EMOJI.get(color, "")
            parts.append(f"{emoji} {', '.join(by_color[color])}")
    if specials:
        parts.append("⚡ " + ", ".join(specials))
    return " · ".join(parts)


def strength_breakdown(cards: list, zone_color: str, has_home_field: bool = True) -> str:
    """Return a human-readable strength calculation string."""
    if not cards:
        return "0 (empty)"

    ranked_cards = [c for c in cards if c.has_rank]
    mascots = [c for c in cards if c.is_mascot]
    action_cards = [c for c in cards if c.is_action]

    if not ranked_cards:
        if action_cards:
            return "0 (only action cards — no rank)"
        if mascots:
            return "0 (Mascot alone — no rank to double)"
        return "0"

    best = max(ranked_cards, key=lambda c: c.effective_rank)
    best_rank = best.effective_rank
    parts = []

    if mascots:
        parts.append(f"{best_rank}×2={best_rank*2} (Mascot doubles {card_name(best)})")
        best_rank *= 2
        extra = len(ranked_cards) - 1  # mascot doesn't count as extra
    else:
        parts.append(f"{best_rank} ({card_name(best)})")
        extra = len(ranked_cards) - 1

    if extra > 0:
        parts.append(f"+{extra*2} ({extra} extra × 2)")

    # Home field
    if has_home_field:
        matching_natural = any(c.color == zone_color and c.is_natural for c in cards)
        if matching_natural:
            anchor = next(c for c in cards if c.color == zone_color and c.is_natural)
            parts.append(f"+3 (Home Field — {card_name(anchor)})")
        else:
            # Check for matching dud or mascot that doesn't anchor
            matching_dud = any(c.color == zone_color and c.is_dud for c in cards)
            if matching_dud:
                parts.append("+3 (Home Field — Dud is natural rank 5)")
    else:
        parts.append("no Home Field (Neutral Ground)")

    total_extra = max(0, extra) * 2
    hf = 0
    if has_home_field:
        has_nat = any(c.color == zone_color and c.is_natural for c in cards)
        if has_nat:
            hf = 3

    total = best_rank + total_extra + hf
    return f"{' '.join(parts)} = **{total}**"


# ── Narration ──────────────────────────────────────────────────────────

def narrate_game(num_players: int, seed: int, player_configs=None) -> str:
    """Play one v0.1 game and return a Markdown narrative."""
    lines = []
    game = GameStateV4(num_players, seed=seed)

    # Create AIs
    ais = []
    for i in range(num_players):
        pc = player_configs[i] if player_configs and i < len(player_configs) else {}
        ai = AIPlayerV4(
            player_id=i,
            skill=pc.get("skill", 1.0),
            style=pc.get("style", "balanced"),
            rng_seed=seed * 100 + i
        )
        ais.append(ai)

    # ── Title ──
    lines.append("# Zone Control v0.1 — Narrated Game")
    lines.append("")
    lines.append(f"**Seed:** {seed} · **Players:** {num_players} · "
                 f"**Rounds:** {game.num_rounds} · **VP/Zone:** {game.base_vp}")
    lines.append("")
    total_cards = sum(len(p.hand) for p in game.players) + len(game.unused_cards)
    lines.append(f"> *Four zones. {game.num_rounds} rounds. {total_cards} cards. "
                 "Every deployment is a blind bet.*")
    lines.append("")

    # ── Setup ──
    lines.append("---")
    lines.append("## Setup")
    lines.append("")
    lines.append("Four zone cards are laid out: "
                 + " · ".join(f"{COLOR_EMOJI.get(c, '')} {c.capitalize()}" for c in COLORS)
                 + ".")
    lines.append("")

    hand_size = len(game.players[0].hand)
    lines.append(f"Each player is dealt **{hand_size} cards** for the entire game.")
    lines.append("")

    # Show initial hands
    for i, ai in enumerate(ais):
        hand = list(game.players[i].hand)
        lines.append(f"**Player {i}** — *{ai.style_name.capitalize()}* "
                     f"({STYLE_INTROS.get(ai.style_name, '')})")
        lines.append(f"> Hand ({len(hand)}): {hand_summary(hand)}")
        lines.append("")

    # ── Card Passing ──
    lines.append("---")
    lines.append("## Card Passing")
    lines.append("")
    pass_count = game.rules["pass_count"][game.pkey]
    lines.append(f"Each player selects **{pass_count}** card{'s' if pass_count != 1 else ''} "
                 f"to pass to the player on their left.")
    lines.append("")

    # Capture what gets passed
    pass_selections = {}
    for player in game.players:
        ai = ais[player.id]
        to_pass = ai.choose_pass(player, game, pass_count)
        pass_selections[player.id] = to_pass

    for pid, passed in pass_selections.items():
        target = (pid + 1) % num_players
        lines.append(f"- **P{pid}** passes to P{target}: {card_list_str(passed)}")

    lines.append("")

    # Execute the pass
    def pass_fn(player, gs, count):
        return pass_selections[player.id]
    game.execute_pass(pass_fn)

    # Show post-pass hands
    lines.append("**After passing:**")
    lines.append("")
    for i in range(num_players):
        hand = list(game.players[i].hand)
        lines.append(f"- P{i}: {hand_summary(hand)}")
    lines.append("")

    # ── Rounds ──
    for round_num in range(game.num_rounds):
        game.current_round = round_num
        for p in game.players:
            p.zones_won_this_round = 0

        # Draw condition
        if game.condition_deck:
            game.active_condition = game.condition_deck.pop(0)
            game.stats["condition_cards_drawn"].append(game.active_condition.name)
        else:
            game.active_condition = None

        game.zones = [Zone(color=c, index=i) for i, c in enumerate(COLORS)]

        lines.append("---")
        lines.append(f"## Round {round_num + 1}")
        lines.append("")

        if game.active_condition:
            cond = game.active_condition
            desc = CONDITION_DESCRIPTIONS.get(cond.effect, cond.effect)
            lines.append(f"**Condition Card: {cond.name}** ({cond.category})")
            lines.append(f"> *{desc}*")
            lines.append("")

        # ── Phase 1: Deploy ──
        lines.append("### Deploy")
        lines.append("")
        lines.append("*All players simultaneously place cards face-down on their boards.*")
        lines.append("")

        all_deployments = {}
        for player in game.players:
            ai = ais[player.id]
            deploy = ai.choose_deployment(player, game, round_num)
            all_deployments[player.id] = deploy

            # Narrate what they played
            total_cards = sum(len(cards) for cards in deploy.values())
            zones_targeted = [c for c, cards in deploy.items() if cards]

            lines.append(f"**P{player.id}** ({ai.style_name}) — "
                         f"plays {total_cards} cards to {len(zones_targeted)} zone{'s' if len(zones_targeted) != 1 else ''}:")

            for color in COLORS:
                cards = deploy.get(color, [])
                if cards:
                    emoji = COLOR_EMOJI.get(color, "")
                    lines.append(f"  - {emoji} {color.capitalize()}: {card_list_str(cards)}")

            remaining = len(player.hand) - total_cards
            lines.append(f"  - *{remaining} cards held back*")
            lines.append("")

            game._execute_deployment(player, deploy)

        # ── Phase 2: Reveal ──
        lines.append("### Reveal")
        lines.append("")

        lines.append("| Zone | Player | Cards |")
        lines.append("|------|--------|-------|")

        for zone in game.zones:
            players_here = zone.active_players
            emoji = COLOR_EMOJI.get(zone.color, "")
            if not players_here:
                lines.append(f"| {emoji} {zone.color.capitalize()} | — | *empty* |")
                continue
            for pid in players_here:
                zp = zone.get_placement(pid)
                lines.append(f"| {emoji} {zone.color.capitalize()} "
                             f"| P{pid} | {card_list_str(zp.cards)} |")
        lines.append("")

        # ── Phase 3: Action Resolution ──
        has_actions = False
        for zone in game.zones:
            for pid in zone.active_players:
                zp = zone.get_placement(pid)
                if any(c.is_action for c in zp.cards):
                    has_actions = True
                    break
            if has_actions:
                break

        if has_actions:
            lines.append("### Action Resolution")
            lines.append("")
            lines.append("*Actions resolve in fixed order: Shield → Bomb → Swap → Bounty*")
            lines.append("")

        # Run action resolution and capture the game log for it
        log_before = len(game.log)
        game._resolve_actions()
        action_log = game.log[log_before:]

        # Parse action log into readable narration
        for msg in action_log:
            msg = msg.strip()
            if not msg or msg.startswith("---") or msg.startswith("==="):
                continue
            if "Shield active" in msg:
                lines.append(f"- 🛡️ {msg.strip()}")
            elif "Bomb destroys" in msg:
                lines.append(f"- 💣 {msg.strip()}")
            elif "Bomb —" in msg:
                lines.append(f"- 💣 {msg.strip()}")
            elif "Swap" in msg:
                lines.append(f"- 🔄 {msg.strip()}")
            elif "Bounty active" in msg:
                lines.append(f"- 💰 {msg.strip()}")
            elif msg.strip():
                lines.append(f"- {msg.strip()}")

        if has_actions:
            lines.append("")

        # ── Phase 4: Strength & Scoring ──
        lines.append("### Strength & Scoring")
        lines.append("")

        cond = game.active_condition
        has_hf = not (cond and cond.effect == "no_home_field")
        inversion = cond and cond.effect == "lowest_wins"
        vp = game.base_vp
        if cond and cond.effect == "double_vp":
            vp *= 2
            lines.append(f"*Double Stakes! Each zone worth **{vp} VP** this round.*")
            lines.append("")

        if inversion:
            lines.append("*Inversion! **Lowest** strength wins each zone.*")
            lines.append("")

        zone_strengths = game._calculate_all_strength()

        for zone in game.zones:
            color = zone.color
            emoji = COLOR_EMOJI.get(color, "")
            strength_map = zone_strengths.get(color, {})
            players_here = zone.active_players

            if not players_here:
                lines.append(f"**{emoji} {color.capitalize()}** — Empty. "
                             f"{vp} VP unclaimed.")
                lines.append("")
                continue

            lines.append(f"**{emoji} {color.capitalize()} Zone:**")
            lines.append("")

            for pid in players_here:
                zp = zone.get_placement(pid)
                bd = strength_breakdown(zp.cards, color, has_hf)
                lines.append(f"- P{pid}: {bd}")

            # Determine outcome
            if not strength_map or max(strength_map.values()) <= 0:
                lines.append(f"- *No valid strength — zone unclaimed.*")
                lines.append("")
                continue

            if inversion:
                target = min(strength_map.values())
            else:
                target = max(strength_map.values())

            winners = [pid for pid, s in strength_map.items() if s == target]

            if cond and cond.effect == "ties_lose" and len(winners) > 1:
                lines.append(f"- ⚡ **Sudden Death: Tie at {target} — nobody scores!**")
            elif cond and cond.effect == "fewer_cards_wins_ties" and len(winners) > 1:
                min_cards = min(len(zone.get_placement(w).cards) for w in winners)
                tiebreak_winners = [w for w in winners
                                    if len(zone.get_placement(w).cards) == min_cards]
                if len(tiebreak_winners) == 1:
                    w = tiebreak_winners[0]
                    lines.append(f"- 🎯 **Efficiency tiebreak: P{w} wins** "
                                 f"(fewest cards) → **+{vp} VP**")
                else:
                    split = math.floor(vp / len(tiebreak_winners))
                    tied = " & ".join(f"P{w}" for w in tiebreak_winners)
                    lines.append(f"- **Still tied after Efficiency: {tied}** → "
                                 f"**+{split} VP each**")
            elif len(winners) == 1:
                w = winners[0]
                # Check for bounty
                has_bounty = any(c.is_action and c.action_type == ACTION_BOUNTY
                                for c in zone.get_placement(w).cards)
                if has_bounty:
                    lines.append(f"- 💰 **P{w} wins with Bounty! "
                                 f"Double VP → +{vp * 2} VP**")
                elif len(players_here) == 1:
                    lines.append(f"- **P{w} wins uncontested → +{vp} VP**")
                else:
                    losers = [pid for pid in players_here if pid != w]
                    loser_parts = [f"P{pid}={strength_map.get(pid, 0)}" for pid in losers]
                    lines.append(f"- **P{w} wins** ({target} vs {', '.join(loser_parts)}) "
                                 f"→ **+{vp} VP**")

                # Check for shield consolation among losers
                for loser in [pid for pid in players_here if pid != w]:
                    zp = zone.get_placement(loser)
                    has_shield = any(c.is_action and c.action_type == ACTION_SHIELD
                                    for c in zp.cards)
                    has_bounty_loss = any(c.is_action and c.action_type == ACTION_BOUNTY
                                         for c in zp.cards)
                    if has_shield and not has_bounty_loss:
                        consolation = game.rules["action_cards"]["shield"]["consolation_vp"]
                        lines.append(f"  - 🛡️ P{loser} Shield consolation → +{consolation} VP")
                    if has_bounty_loss:
                        lines.append(f"  - 💰 P{loser} Bounty bust — 0 VP")

                # 2nd-place VP
                second_vp = game.rules.get("second_place_vp", 0)
                if second_vp > 0 and len(players_here) >= 2:
                    sorted_str = sorted(strength_map.values(), reverse=True)
                    second_best = sorted_str[1] if len(sorted_str) > 1 else 0
                    if second_best > 0:
                        runners = [pid for pid in players_here
                                   if strength_map.get(pid, 0) == second_best
                                   and pid not in winners]
                        for pid in runners:
                            lines.append(f"  - P{pid} 2nd place → +{second_vp} VP")
            else:
                split = math.floor(vp / len(winners))
                tied = " & ".join(f"P{w}" for w in winners)
                lines.append(f"- **Tie: {tied}** (both {target}) → **+{split} VP each**")

            lines.append("")

        # Actually score in the game state
        round_stats = game._score_round(zone_strengths)

        # Lone Wolf / Fortify bonuses
        if cond and cond.effect == "lone_wolf_bonus":
            lines.append("*Lone Wolf: +3 bonus VP for uncontested zones.*")
            lines.append("")
        if cond and cond.effect == "big_stack_bonus":
            lines.append("*Fortify: +2 bonus VP for 3+ cards at a zone.*")
            lines.append("")

        # Scoreboard
        lines.append("#### Scoreboard")
        lines.append("")
        lines.append("| Player | Style | VP | Cards Left |")
        lines.append("|--------|-------|----|------------|")
        for p in game.players:
            lines.append(f"| P{p.id} | {ais[p.id].style_name} | "
                         f"**{p.score}** | {len(p.hand)} |")
        lines.append("")

        game.active_condition = None

    # ── Final Results ──
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
        tied = " & ".join(f"P{w} ({ais[w].style_name})" for w in winner)
        lines.append(f"> **Tie game: {tied}!**")
    else:
        sorted_scores = sorted(scores.values(), reverse=True)
        margin = sorted_scores[0] - sorted_scores[1]
        lines.append(f"> **Player {winner} ({ais[winner].style_name}) "
                     f"wins by {margin} VP!**")

        style = ais[winner].style_name
        closings = {
            "sniper":     "Surgical precision — the Mascot combo is a thing of beauty.",
            "aggressive": "Overwhelming force across the board. Volume wins wars.",
            "hoarder":    "Patience rewarded. Saving cards for the right moment paid off.",
            "spread":     "Coverage everywhere. Uncontested zones add up fast.",
            "balanced":   "Adaptable, measured, and always in the right place.",
        }
        lines.append(f">\n> *{closings.get(style, 'Well played.')}*")

    lines.append("")

    # ── Game Stats ──
    lines.append("---")
    lines.append("### Game Statistics")
    lines.append("")
    lines.append(f"- Home Field triggers: {final['home_field_triggers']}")
    lines.append(f"- Mascot combos: {final['mascot_combos']}")
    lines.append(f"- Bomb kills: {final['bomb_kills']}")
    lines.append(f"- Shield saves: {final['shield_saves']}")
    lines.append(f"- Swap uses: {final['swap_uses']}")
    lines.append(f"- Bounty wins: {final['bounty_wins']}, "
                 f"fails: {final['bounty_fails']}")
    lines.append(f"- Dud plays: {final['dud_plays']}")
    lines.append(f"- Conditions: {', '.join(final['condition_cards'])}")
    lines.append("")
    lines.append("---")
    lines.append("*Generated by the v0.1 simulation engine.*")

    return "\n".join(lines)


# ── CLI ────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Zone Control v0.1 — Narrated Game"
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
