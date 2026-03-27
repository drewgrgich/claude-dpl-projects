#!/usr/bin/env python3
"""
Narration engine for Tailgate Turf War v0.1.5.

Plays a single game with full play-by-play:
  - Per-round passing (2 cards/round at 3-4P, 1 at 5P)
  - New condition cards (12 from v0.1.5 overhaul)
  - New default action cards: Shield, Heist, Contaminate, Bounty
  - Full strength breakdowns with condition modifiers

Usage:
  python narrate_game_v015.py --seed 42 -p 4
  python narrate_game_v015.py --seed 7 -p 4 --styles balanced,aggressive,sniper,hoarder
"""

import argparse
import math
import os
import random as rng_mod
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cards_v4 import (
    Card, COLORS, COLOR_ORDER,
    CARD_TYPE_NUMBER, CARD_TYPE_MASCOT, CARD_TYPE_ACTION, CARD_TYPE_DUD,
    ACTION_SHIELD, ACTION_BOMB, ACTION_SWAP, ACTION_BOUNTY,
)
from game_state_v4 import GameStateV4, Zone, ConditionCard
from ai_player_v4 import AIPlayerV4, STYLE_PROFILES
from test_new_conditions import CANDIDATE_CONDITIONS, ConditionTestGame, ConditionAI


# ── Constants ─────────────────────────────────────────────────────────

ACTION_HEIST = "heist"
ACTION_CONTAMINATE = "contaminate"
ACTION_AMBUSH = "ambush"

V015_CONDITIONS = [
    ("Inversion", "lowest_wins"),
    ("Neutral Ground", "no_home_field"),
    ("Color Tax", "color_tax"),
    ("Ceiling", "ceiling_5"),
    ("Mirror", "mirror_ranks"),
    ("Spread Out", "min_2_zones"),
    ("Lone Wolf", "lone_wolf_max1"),
    ("Double Stakes", "double_vp"),
    ("Sudden Death", "ties_lose"),
    ("Diminishing Returns", "diminishing_returns"),
    ("Grudge Match", "grudge_match"),
    ("Second Wave", "second_wave"),
]

CONDITION_DESCRIPTIONS = {
    "lowest_wins":          "Lowest Strength wins each zone! Your 10s are worthless.",
    "no_home_field":        "No Home Field Bonus this round. Pure rank optimization.",
    "color_tax":            "Home Field is -2 penalty instead of +3! Matching color hurts.",
    "ceiling_5":            "All card ranks capped at 5. A 10 counts as 5.",
    "mirror_ranks":         "Rank = 10 minus printed rank. Your 0s become 10s!",
    "min_2_zones":          "Must play cards at 2+ different zones this round.",
    "lone_wolf_max1":       "Max 1 card per zone this round.",
    "double_vp":            "Each zone is worth 10 VP instead of 5!",
    "ties_lose":            "Ties score zero — nobody wins a tied zone.",
    "diminishing_returns":  "VP per zone won: 1st=7, 2nd=5, 3rd=3, 4th=1.",
    "grudge_match":         "Last round's loser(s) get +3 Strength everywhere.",
    "second_wave":          "After reveal, deploy 1 more card (face-up).",
}

COLOR_EMOJI = {"red": "🔴", "blue": "🔵", "green": "🟢", "yellow": "🟡"}

ACTION_EMOJI = {
    ACTION_SHIELD: "🛡️", ACTION_BOMB: "💣", ACTION_SWAP: "🔄",
    ACTION_BOUNTY: "💰", ACTION_HEIST: "🏴‍☠️", ACTION_CONTAMINATE: "☣️",
    ACTION_AMBUSH: "🎯",
}

DEFAULT_ACTIONS = [ACTION_SHIELD, ACTION_HEIST, ACTION_CONTAMINATE, ACTION_BOUNTY]

STYLE_INTROS = {
    "balanced":   "a well-rounded strategist",
    "aggressive": "a high-volume player who floods every zone",
    "sniper":     "a precision player hunting mascot combos",
    "hoarder":    "a patient operator saving for later rounds",
    "spread":     "a zone-coverage maximizer",
}


# ── Helpers ───────────────────────────────────────────────────────────

def card_name(c: Card) -> str:
    if c.is_mascot:
        return f"{c.color.capitalize()} Mascot"
    if c.is_action:
        emoji = ACTION_EMOJI.get(c.action_type, "⚡")
        return f"{emoji}{c.action_type.capitalize()} ({c.color.capitalize()})"
    if c.is_dud:
        return f"Dud ({c.color.capitalize()}, plays as 5)"
    return f"{c.color.capitalize()} {c.rank}"


def card_list_str(cards: list) -> str:
    if not cards:
        return "*nothing*"
    return ", ".join(card_name(c) for c in cards)


def hand_summary(hand: list) -> str:
    by_color = {}
    specials = []
    for c in sorted(hand, key=lambda x: (COLOR_ORDER.get(x.color, 99), x.effective_rank)):
        if c.is_action:
            specials.append(f"{ACTION_EMOJI.get(c.action_type, '⚡')}{c.action_type.capitalize()}")
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


def calc_strength_narrated(cards, zone_color, cond_effect):
    """Calculate strength with condition modifiers and return (total, breakdown_str)."""
    if not cards:
        return 0, "0 (empty)"

    ranked_cards = [c for c in cards if c.has_rank]
    mascots = [c for c in cards if c.is_mascot]

    if not ranked_cards:
        if mascots:
            return 0, "0 (Mascot alone — no rank to double)"
        return 0, "0 (only action cards)"

    # Apply rank modifications
    effective = []
    for c in ranked_cards:
        r = c.effective_rank
        if cond_effect == "mirror_ranks":
            r = 10 - r
        elif cond_effect == "ceiling_5":
            r = min(r, 5)
        elif cond_effect == "peasant_revolt" and c.effective_rank <= 3:
            r = c.effective_rank + 5
        effective.append((c, r))

    best_card, best_rank = max(effective, key=lambda x: x[1])
    parts = []

    if mascots:
        parts.append(f"{best_rank}x2={best_rank*2} (Mascot doubles {card_name(best_card)})")
        best_rank *= 2
        extra = len(ranked_cards) - 1
    else:
        if cond_effect == "mirror_ranks":
            parts.append(f"{best_rank} ({card_name(best_card)}, mirrored from {best_card.effective_rank})")
        elif cond_effect == "ceiling_5" and best_card.effective_rank > 5:
            parts.append(f"{best_rank} ({card_name(best_card)}, capped from {best_card.effective_rank})")
        else:
            parts.append(f"{best_rank} ({card_name(best_card)})")
        extra = len(ranked_cards) - 1

    if extra > 0:
        parts.append(f"+{extra*2} ({extra} extra x 2)")

    # Home Field
    hf = 0
    if cond_effect == "no_home_field":
        parts.append("no HF (Neutral Ground)")
    elif cond_effect == "color_tax":
        has_matching = any(c.color == zone_color and c.is_natural for c in cards)
        if has_matching:
            hf = -2
            anchor = next(c for c in cards if c.color == zone_color and c.is_natural)
            parts.append(f"-2 (Color Tax! {card_name(anchor)} matches)")
    elif cond_effect == "lowest_wins":
        has_matching = any(c.color == zone_color and c.is_natural for c in cards)
        if has_matching:
            hf = 3
            parts.append(f"+3 HF (hurts under Inversion!)")
    else:
        has_matching = any(c.color == zone_color and c.is_natural for c in cards)
        if has_matching:
            hf = 3
            anchor = next(c for c in cards if c.color == zone_color and c.is_natural)
            parts.append(f"+3 HF ({card_name(anchor)})")

    total = max(0, best_rank + max(0, extra) * 2 + hf)
    return total, f"{' '.join(parts)} = **{total}**"


# ── Narrated Game ─────────────────────────────────────────────────────

class NarratedGame(ConditionTestGame):
    """v0.1.5 game with full narration capture."""

    def __init__(self, num_players, seed=42, config=None):
        pass_per_round = 2 if num_players <= 4 else 1
        super().__init__(num_players, seed=seed, config=config,
                         pass_per_round=pass_per_round, test_condition=None)
        # Build v0.1.5 condition deck (shuffled)
        rng = rng_mod.Random(seed + 999)
        pool = list(V015_CONDITIONS)
        rng.shuffle(pool)
        self.condition_deck = [
            ConditionCard(name, "v015", effect)
            for name, effect in pool[:self.num_rounds]
        ]
        # Replace action cards with default v0.1.5 set
        self._patch_actions()

    def _patch_actions(self):
        """Replace Bomb/Swap with Heist/Contaminate in all hands."""
        replacements = {
            ACTION_BOMB: ACTION_HEIST,
            ACTION_SWAP: ACTION_CONTAMINATE,
        }
        for player in self.players:
            new_hand = []
            for card in player.hand:
                if card.is_action and card.action_type in replacements:
                    new_card = Card(
                        color=card.color,
                        card_type=CARD_TYPE_ACTION,
                        rank=0,
                        action_type=replacements[card.action_type]
                    )
                    new_hand.append(new_card)
                else:
                    new_hand.append(card)
            player.hand = new_hand

        new_unused = []
        for card in self.unused_cards:
            if card.is_action and card.action_type in replacements:
                new_card = Card(
                    color=card.color,
                    card_type=CARD_TYPE_ACTION,
                    rank=0,
                    action_type=replacements[card.action_type]
                )
                new_unused.append(new_card)
            else:
                new_unused.append(card)
        self.unused_cards = new_unused


def narrate_game(num_players, seed, player_configs=None):
    """Play one v0.1.5 game and return Markdown narrative."""
    import json
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config_v4.json")
    with open(config_path) as f:
        config = json.load(f)

    game = NarratedGame(num_players, seed=seed, config=config)
    lines = []

    # Create AIs
    ais = []
    for i in range(num_players):
        pc = player_configs[i] if player_configs and i < len(player_configs) else {}
        ai = ConditionAI(
            player_id=i,
            skill=pc.get("skill", 1.0),
            style=pc.get("style", "balanced"),
            rng_seed=seed * 100 + i,
        )
        ai._game_ref = game
        ais.append(ai)

    # ── Title ──
    lines.append("# Tailgate Turf War v0.1.5 — Narrated Game")
    lines.append("")
    lines.append(f"**Seed:** {seed} · **Players:** {num_players} · "
                 f"**Rounds:** {game.num_rounds} · **VP/Zone:** {game.base_vp}")
    lines.append("")
    conditions_drawn = [c.name for c in game.condition_deck]
    lines.append(f"> *Four zones. {game.num_rounds} rounds. Per-round passing. "
                 "Every round is a new puzzle.*")
    lines.append("")

    # ── Setup ──
    lines.append("---")
    lines.append("## Setup")
    lines.append("")
    lines.append("Four zone cards: "
                 + " · ".join(f"{COLOR_EMOJI.get(c, '')} {c.capitalize()}" for c in COLORS))
    lines.append("")
    lines.append(f"Each player is dealt **{len(game.players[0].hand)} cards** for the entire game.")
    lines.append("")

    for i, ai in enumerate(ais):
        hand = list(game.players[i].hand)
        lines.append(f"**Player {i}** — *{ai.style_name.capitalize()}* "
                     f"({STYLE_INTROS.get(ai.style_name, '')})")
        lines.append(f"> Hand ({len(hand)}): {hand_summary(hand)}")
        lines.append("")

    lines.append(f"**Action cards this game:** Shield, Heist, Contaminate, Bounty")
    lines.append(f"**Conditions in deck:** {', '.join(conditions_drawn)}")
    lines.append("")

    # ── Rounds ──
    zones_won_last_round = defaultdict(int)

    for round_num in range(game.num_rounds):
        game.current_round = round_num

        lines.append("---")
        lines.append(f"## Round {round_num + 1}")
        lines.append("")

        # ── Phase 1: Pass ──
        pass_count = game.pass_per_round
        if num_players == 2 and round_num > 0:
            pass_count = 0

        if pass_count > 0:
            lines.append("### Pass Phase")
            lines.append("")
            lines.append(f"Each player passes **{pass_count}** card{'s' if pass_count != 1 else ''} left.")
            lines.append("")

            pass_selections = {}
            for player in game.players:
                ai = ais[player.id]
                actual_pass = min(pass_count, max(0, len(player.hand) - 1))
                if actual_pass > 0:
                    to_pass = ai.choose_pass(player, game, actual_pass)
                else:
                    to_pass = []
                pass_selections[player.id] = to_pass

            for pid, passed in pass_selections.items():
                target = (pid + 1) % num_players
                if passed:
                    lines.append(f"- **P{pid}** → P{target}: {card_list_str(passed)}")
                else:
                    lines.append(f"- **P{pid}** → P{target}: *nothing (hand too small)*")

            # Execute pass
            for player in game.players:
                for card in pass_selections[player.id]:
                    if card in player.hand:
                        player.hand.remove(card)
                right_id = (player.id - 1) % num_players
                player.hand.extend(pass_selections[right_id])

            lines.append("")

        # ── Phase 2: Condition ──
        if game.condition_deck:
            cond = game.condition_deck.pop(0)
            game.active_condition = cond
            game.test_condition_effect = cond.effect
            game.stats["condition_cards_drawn"].append(cond.name)
        else:
            cond = None
            game.active_condition = None
            game.test_condition_effect = None

        cond_effect = game.test_condition_effect

        if cond:
            desc = CONDITION_DESCRIPTIONS.get(cond.effect, cond.effect)
            lines.append(f"### Condition: {cond.name}")
            lines.append(f"> *{desc}*")
            lines.append("")

        # Grudge Match bonus
        grudge_players = set()
        if cond_effect == "grudge_match" and round_num > 0:
            min_zones = min(zones_won_last_round.get(pid, 0) for pid in range(num_players))
            grudge_players = {pid for pid in range(num_players)
                             if zones_won_last_round.get(pid, 0) == min_zones}
            gp_str = ", ".join(f"P{pid}" for pid in sorted(grudge_players))
            lines.append(f"*Grudge Match: {gp_str} won fewest zones last round → +3 Strength everywhere!*")
            lines.append("")

        # Show hands before deploy
        lines.append("**Hands before deployment:**")
        lines.append("")
        for i in range(num_players):
            lines.append(f"- P{i} ({len(game.players[i].hand)} cards): {hand_summary(game.players[i].hand)}")
        lines.append("")

        # ── Phase 3: Deploy ──
        lines.append("### Deploy")
        lines.append("")

        game.zones = [Zone(color=c, index=i) for i, c in enumerate(COLORS)]

        all_deployments = {}
        for player in game.players:
            ai = ais[player.id]
            ai._game_ref = game
            deploy = ai.choose_deployment(player, game, round_num)

            # Apply deployment conditions
            if cond_effect == "lone_wolf_max1":
                deploy = game._apply_lone_wolf(deploy)
            elif cond_effect == "min_2_zones":
                # AI should already handle this, but ensure compliance
                pass

            all_deployments[player.id] = deploy

            total_cards = sum(len(cards) for cards in deploy.values())
            zones_targeted = [c for c, cards in deploy.items() if cards]

            lines.append(f"**P{player.id}** ({ai.style_name}) — "
                         f"{total_cards} cards → {len(zones_targeted)} zone{'s' if len(zones_targeted) != 1 else ''}:")

            for color in COLORS:
                cards = deploy.get(color, [])
                if cards:
                    emoji = COLOR_EMOJI.get(color, "")
                    lines.append(f"  - {emoji} {color.capitalize()}: {card_list_str(cards)}")

            remaining = len(player.hand) - total_cards
            lines.append(f"  - *{remaining} cards held back*")
            lines.append("")

            game._execute_deployment(player, deploy)

        # Second Wave: extra deployment after reveal
        if cond_effect == "second_wave":
            lines.append("### Second Wave")
            lines.append("*After reveal, each player deploys 1 more card face-up.*")
            lines.append("")
            for player in game.players:
                if player.hand:
                    best_card = max(
                        [c for c in player.hand if c.has_rank],
                        key=lambda c: c.effective_rank, default=None)
                    if best_card:
                        best_zone = None
                        best_str = -1
                        for zone in game.zones:
                            zp = zone.get_placement(player.id)
                            if zp.cards:
                                s = sum(c.effective_rank for c in zp.cards if c.has_rank)
                                if s > best_str:
                                    best_str = s
                                    best_zone = zone
                        if best_zone:
                            player.hand.remove(best_card)
                            best_zone.get_placement(player.id).cards.append(best_card)
                            player.cards_played_total += 1
                            lines.append(f"- P{player.id} adds {card_name(best_card)} to {COLOR_EMOJI.get(best_zone.color, '')} {best_zone.color.capitalize()}")
            lines.append("")

        # ── Reveal Table ──
        lines.append("### Reveal")
        lines.append("")
        lines.append("| Zone | Player | Cards |")
        lines.append("|------|--------|-------|")

        for zone in game.zones:
            emoji = COLOR_EMOJI.get(zone.color, "")
            if not zone.active_players:
                lines.append(f"| {emoji} {zone.color.capitalize()} | — | *empty* |")
                continue
            for pid in zone.active_players:
                zp = zone.get_placement(pid)
                lines.append(f"| {emoji} {zone.color.capitalize()} | P{pid} | {card_list_str(zp.cards)} |")
        lines.append("")

        # ── Action Resolution ──
        has_actions = any(
            any(c.is_action for c in zone.get_placement(pid).cards)
            for zone in game.zones
            for pid in zone.active_players
        )

        if has_actions:
            lines.append("### Action Resolution")
            lines.append("")
            lines.append("*Shield → Heist → Contaminate → Bounty*")
            lines.append("")

        game._resolve_actions()

        # ── Strength & Scoring ──
        lines.append("### Strength & Scoring")
        lines.append("")

        inversion = cond_effect == "lowest_wins"
        contaminate_inversion = False  # TODO: if Contaminate played at zone

        vp = game.base_vp
        if cond_effect == "double_vp":
            vp = 10
            lines.append("*Double Stakes! Each zone worth **10 VP**.*")
            lines.append("")

        if inversion:
            lines.append("*Inversion! **Lowest** strength wins.*")
            lines.append("")

        round_vp = defaultdict(int)
        zones_won_this_round = defaultdict(int)

        for zone in game.zones:
            color = zone.color
            emoji = COLOR_EMOJI.get(color, "")
            players_here = zone.active_players

            if not players_here:
                lines.append(f"**{emoji} {color.capitalize()}** — Empty.")
                lines.append("")
                continue

            lines.append(f"**{emoji} {color.capitalize()} Zone:**")
            lines.append("")

            # Calculate strengths
            strength_map = {}
            for pid in players_here:
                zp = zone.get_placement(pid)
                total, breakdown = calc_strength_narrated(zp.cards, color, cond_effect)
                # Grudge Match bonus
                if cond_effect == "grudge_match" and pid in grudge_players:
                    total += 3
                    breakdown = breakdown.replace(f"= **{total-3}**", f"+3 (Grudge) = **{total}**")
                strength_map[pid] = total
                lines.append(f"- P{pid}: {breakdown}")

            # Determine winner
            if not strength_map or max(strength_map.values()) <= 0:
                lines.append(f"- *No valid strength — zone unclaimed.*")
                lines.append("")
                continue

            if inversion:
                target = min(strength_map.values())
            else:
                target = max(strength_map.values())

            winners = [pid for pid, s in strength_map.items() if s == target]

            # Score
            if cond_effect == "ties_lose" and len(winners) > 1:
                lines.append(f"- **Sudden Death: Tie at {target} — nobody scores!**")
            elif len(winners) == 1:
                w = winners[0]

                # Diminishing Returns
                if cond_effect == "diminishing_returns":
                    dim_vp = [7, 5, 3, 1]
                    player_vp = dim_vp[min(zones_won_this_round[w], 3)]
                else:
                    player_vp = vp

                # Bounty check
                has_bounty = any(c.is_action and c.action_type == ACTION_BOUNTY
                                for c in zone.get_placement(w).cards)
                if has_bounty:
                    player_vp *= 2
                    lines.append(f"- 💰 **P{w} wins with Bounty! → +{player_vp} VP**")
                elif len(players_here) == 1:
                    lines.append(f"- **P{w} wins uncontested → +{player_vp} VP**")
                else:
                    losers = [pid for pid in players_here if pid != w]
                    loser_parts = [f"P{pid}={strength_map.get(pid, 0)}" for pid in losers]
                    lines.append(f"- **P{w} wins** ({target} vs {', '.join(loser_parts)}) → **+{player_vp} VP**")

                round_vp[w] += player_vp
                zones_won_this_round[w] += 1

                # Shield consolation for losers
                for loser in [pid for pid in players_here if pid != w]:
                    zp = zone.get_placement(loser)
                    has_shield = any(c.is_action and c.action_type == ACTION_SHIELD for c in zp.cards)
                    has_bounty_loss = any(c.is_action and c.action_type == ACTION_BOUNTY for c in zp.cards)
                    if has_shield and not has_bounty_loss:
                        lines.append(f"  - 🛡️ P{loser} Shield consolation → +2 VP")
                        round_vp[loser] += 2
                    if has_bounty_loss:
                        lines.append(f"  - 💰 P{loser} Bounty bust — 0 VP")

                # 2nd-place VP
                if len(players_here) >= 2:
                    sorted_str = sorted(strength_map.values(), reverse=(not inversion))
                    second_best = sorted_str[1] if len(sorted_str) > 1 else 0
                    if second_best > 0:
                        runners = [pid for pid in players_here
                                   if strength_map.get(pid, 0) == second_best and pid not in winners]
                        for pid in runners:
                            lines.append(f"  - P{pid} 2nd place → +1 VP")
                            round_vp[pid] += 1
            else:
                # Tie
                if cond_effect == "diminishing_returns":
                    dim_vp = [7, 5, 3, 1]
                    base = dim_vp[min(zones_won_this_round.get(winners[0], 0), 3)]
                else:
                    base = vp
                split = math.floor(base / len(winners))
                tied = " & ".join(f"P{w}" for w in winners)
                lines.append(f"- **Tie: {tied}** (both {target}) → **+{split} VP each**")
                for w in winners:
                    round_vp[w] += split
                    zones_won_this_round[w] += 1

            lines.append("")

        # Apply VP to game state
        for pid, vp_earned in round_vp.items():
            game.players[pid].score += vp_earned

        # Track zones for grudge match
        zones_won_last_round = dict(zones_won_this_round)

        # Scoreboard
        lines.append("#### Scoreboard")
        lines.append("")
        lines.append("| Player | Style | Round VP | Total VP | Cards Left |")
        lines.append("|--------|-------|----------|----------|------------|")
        for p in game.players:
            lines.append(f"| P{p.id} | {ais[p.id].style_name} | "
                         f"+{round_vp.get(p.id, 0)} | **{p.score}** | {len(p.hand)} |")
        lines.append("")

        game.active_condition = None
        game.test_condition_effect = None

    # ── Final Results ──
    lines.append("---")
    lines.append("## Final Results")
    lines.append("")

    scores = {p.id: p.score for p in game.players}
    max_score = max(scores.values())

    lines.append("| Player | Style | Final VP |")
    lines.append("|--------|-------|----------|")
    for pid in range(num_players):
        medal = " 🏆" if scores[pid] == max_score else ""
        lines.append(f"| P{pid}{medal} | {ais[pid].style_name} | **{scores[pid]}** |")
    lines.append("")

    winners = [pid for pid, s in scores.items() if s == max_score]
    if len(winners) > 1:
        tied = " & ".join(f"P{w} ({ais[w].style_name})" for w in winners)
        lines.append(f"> **Tie game: {tied}!**")
    else:
        w = winners[0]
        sorted_scores = sorted(scores.values(), reverse=True)
        margin = sorted_scores[0] - sorted_scores[1]
        lines.append(f"> **Player {w} ({ais[w].style_name}) wins by {margin} VP!**")
        closings = {
            "sniper":     "Surgical precision — the Mascot combo is a thing of beauty.",
            "aggressive": "Overwhelming force across the board. Volume wins wars.",
            "hoarder":    "Patience rewarded. Saving cards for the right moment paid off.",
            "spread":     "Coverage everywhere. Uncontested zones add up fast.",
            "balanced":   "Adaptable, measured, and always in the right place.",
        }
        lines.append(f">\n> *{closings.get(ais[w].style_name, 'Well played.')}*")

    lines.append("")
    lines.append("---")
    lines.append(f"*Generated by the Tailgate Turf War v0.1.5 simulation engine.*")

    return "\n".join(lines)


# ── CLI ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Tailgate Turf War v0.1.5 — Narrated Game")
    parser.add_argument("-s", "--seed", type=int, default=42)
    parser.add_argument("-p", "--players", type=int, default=4)
    parser.add_argument("-o", "--output", type=str, default=None)
    parser.add_argument("--styles", type=str, default=None,
                        help="Comma-separated styles (e.g. 'balanced,aggressive,sniper,hoarder')")
    args = parser.parse_args()

    player_configs = None
    if args.styles:
        styles = [s.strip() for s in args.styles.split(",")]
        player_configs = [{"skill": 1.0, "style": s} for s in styles]
    else:
        style_list = list(STYLE_PROFILES.keys())
        player_configs = [{"skill": 1.0, "style": style_list[i % len(style_list)]}
                          for i in range(args.players)]

    narrative = narrate_game(args.players, args.seed, player_configs)

    if args.output:
        with open(args.output, 'w') as f:
            f.write(narrative)
        print(f"Written to {args.output}")
    else:
        print(narrative)


if __name__ == "__main__":
    main()
