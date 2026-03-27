#!/usr/bin/env python3
"""Narration engine for The Merch Stand Mob.

Plays a single game with full AI thinking exposed, producing a
Markdown play-by-play that reads like commentary.
"""

import argparse
import os
import sys
from typing import List, Dict, Optional

from cards import Card, FACTION_COLORS, FACTIONS, FACTION_ABILITIES
from game_state import GameState, Bid, Player, load_config
from ai_player import HeuristicAI, STYLE_PROFILES


class NarratedGame:
    """Plays one game with full narration of AI decisions."""

    def __init__(self, config: dict, num_players: int, seed: int,
                 player_configs: List[dict] = None):
        self.config = config
        self.num_players = num_players
        self.seed = seed
        self.game = GameState(config, num_players, seed=seed)
        self.narrative: List[str] = []

        # Create AIs
        self.ais = []
        for i in range(num_players):
            pc = player_configs[i] if player_configs and i < len(player_configs) else {}
            self.ais.append(HeuristicAI(
                player_id=i,
                skill=pc.get("skill", 1.0),
                style=pc.get("style", "balanced"),
                aggression=pc.get("aggression", 0.5),
                rng_seed=seed + i * 1000,
            ))

    def play(self) -> str:
        """Play a full game with narration. Returns Markdown string."""
        self.game.setup()
        self._narrate_setup()

        while not self.game.game_over and self.game.round_number < self.game.rules["max_rounds"]:
            self._narrate_round()

        self._narrate_final_scores()
        return "\n\n".join(self.narrative)

    def _narrate_setup(self):
        """Narrate the game setup."""
        self.narrative.append(f"# The Merch Stand Mob — Narrated Game")
        self.narrative.append(f"**Seed:** {self.seed} | "
                             f"**Players:** {self.num_players} | "
                             f"**Hand size:** {self.game.rules['hand_size'][self.game.pkey]}")

        # Player info
        lines = ["## Players"]
        for i, ai in enumerate(self.ais):
            p = self.game.players[i]
            hand_str = ", ".join(str(c) for c in sorted(p.hand, key=lambda c: (c.faction, c.rank)))
            lines.append(f"- **P{i}** ({ai.style}, skill={ai.skill:.1f}, "
                        f"aggr={ai.aggression:.1f}): {hand_str}")
        self.narrative.append("\n".join(lines))

        # Stand
        stand_str = ", ".join(str(c) for c in self.game.stand)
        self.narrative.append(f"**Starting Stand:** {stand_str}")

    def _narrate_round(self):
        """Narrate one full round."""
        rnum = self.game.round_number + 1  # Will become this round number

        # Header with game state
        lines = [f"---\n## Round {rnum}"]

        # Show Stand
        stand_str = ", ".join(f"{c}" for c in self.game.stand) if self.game.stand else "(empty)"
        lines.append(f"**Stand:** {stand_str}")

        # Mosh Pit status
        pit_parts = []
        for f in FACTION_COLORS:
            count = self.game.get_mosh_pit_faction_count(f)
            if count > 0:
                threshold = self.game.rules["trample_threshold"][self.game.pkey]
                danger = " ⚠" if count >= threshold - 1 else ""
                pit_parts.append(f"{f}:{count}{danger}")
        pit_str = " | ".join(pit_parts) if pit_parts else "(empty)"
        lines.append(f"**Mosh Pit:** {pit_str}")

        # Player states
        for p in self.game.players:
            vp = p.vp
            colors = p.unique_colors
            lines.append(f"**P{p.id}:** VP:{vp} | Hand:{p.hand_size} | "
                        f"Scored:{p.score_pile_count} ({colors} colors)")

        self.narrative.append("\n".join(lines))

        # ── Bidding Phase ──
        bid_lines = ["### The Commit"]
        bids = []

        for i, player in enumerate(self.game.players):
            if not player.hand:
                continue

            ai = self.ais[i]
            bid, reasoning = ai.choose_bid_with_reasoning(player, self.game)

            # Remove bid cards from hand
            player.hand.remove(bid.primary)
            if bid.anchor and bid.anchor in player.hand:
                player.hand.remove(bid.anchor)
            bids.append(bid)

            # Narrate the thinking
            bid_lines.append(f"\n**P{i}** considers their hand:")
            bid_lines.append(f"> {reasoning.replace(chr(10), chr(10) + '> ')}")

            if bid.anchor:
                bid_lines.append(f"P{i} places **{bid.primary}** + **{bid.anchor}** face-down.")
            else:
                bid_lines.append(f"P{i} places **{bid.primary}** face-down.")

        self.narrative.append("\n".join(bid_lines))

        if not bids:
            return

        # ── Execute Round ──
        def make_callback(ai_list):
            def callback(player, ability_type, gs, context):
                return ai_list[player.id].ability_callback(player, ability_type, gs, context)
            return callback

        result = self.game.play_round(bids, ability_callback=make_callback(self.ais))

        # Update AI sneak history
        sneak_occurred = result["sneaks"]["attempts"] > 0
        for ai in self.ais:
            ai.update_sneak_history(sneak_occurred)

        # ── Narrate the Reveal ──
        reveal_lines = ["### The Reveal"]

        # Sneak results
        if result["sneaks"]["attempts"] > 0:
            if result["sneaks"]["successes"] == 1:
                sneak_pid = [b for b in result["bids"] if b["is_sneak"] and b["has_valid_anchor"]]
                if sneak_pid:
                    reveal_lines.append(f"**Sneak succeeds!** P{sneak_pid[0]['player_id']} "
                                       f"slips through the crowd unnoticed.")
            else:
                reveal_lines.append(f"**{result['sneaks']['attempts']} Sneaks collide!** "
                                   f"All cancelled. Nobody gets through cleanly.")

        # Claims
        if result["claims"]:
            reveal_lines.append("\n**Claim order:**")
            for claim in result["claims"]:
                pid = claim["player_id"]
                claimed = claim.get("claimed")
                ctype = claim["type"]

                if claimed:
                    faction = claimed.faction
                    ability_name = FACTION_ABILITIES.get(faction, "")
                    reveal_lines.append(
                        f"- P{pid} ({ctype}, rank {claim['bid_rank']}) → "
                        f"claims **{claimed}** "
                        f"*(triggers {ability_name})*")
                else:
                    reveal_lines.append(
                        f"- P{pid} ({ctype}, rank {claim['bid_rank']}) → "
                        f"finds empty shelves")

        self.narrative.append("\n".join(reveal_lines))

        # ── Abilities ──
        if result["abilities"]:
            ability_lines = ["### Abilities"]
            for ab in result["abilities"]:
                ability = ab["ability"]
                pid = ab["player"]

                if ability == "stadium_sweep":
                    removed = ab.get("removed")
                    from_f = ab.get("from_faction")
                    ability_lines.append(
                        f"🔴 P{pid} **Stadium Sweep**: Removes {removed} from {from_f} Pit.")

                elif ability == "keen_eye":
                    if ab.get("swapped"):
                        ability_lines.append(
                            f"🟠 P{pid} **Keen Eye**: Peeks {ab['supply_card']}, "
                            f"swaps it onto the Stand for {ab.get('stand_card')}.")
                    else:
                        ability_lines.append(
                            f"🟠 P{pid} **Keen Eye**: Peeks at supply... decides not to swap.")

                elif ability == "quick_hands":
                    drawn = ab.get("drawn")
                    ability_lines.append(
                        f"🟡 P{pid} **Quick Hands**: Grabs {drawn} from the supply! "
                        f"({'Nice!' if drawn.rank >= 7 else 'Ouch.' if drawn.rank <= 2 else 'Fine.'})")

                elif ability == "small_prophecies":
                    kept = ab.get("kept")
                    seen = ab.get("seen", [])
                    seen_str = ", ".join(str(c) for c in seen)
                    if kept:
                        ability_lines.append(
                            f"🟢 P{pid} **Small Prophecies**: Sees [{seen_str}], "
                            f"keeps {kept}. Reorders the rest.")
                    else:
                        ability_lines.append(
                            f"🟢 P{pid} **Small Prophecies**: Sees [{seen_str}]. "
                            f"Nothing keepable. Reorders supply.")

                elif ability == "sleight_of_paw":
                    ability_lines.append(
                        f"🔵 P{pid} **Sleight of Paw**: Moves {ab.get('card')} "
                        f"from {ab.get('from')} → {ab.get('to')}")
                    if ab.get("triggered_trample"):
                        ability_lines.append(f"   **This triggers a TRAMPLE!**")

                elif ability == "temporal_recall":
                    ability_lines.append(
                        f"🟣 P{pid} **Temporal Recall**: Retrieves {ab.get('retrieved')} "
                        f"from Pit, discards {ab.get('discarded')} in its place.")
                    if ab.get("triggered_trample"):
                        ability_lines.append(f"   **This triggers a TRAMPLE!**")

            self.narrative.append("\n".join(ability_lines))

        # ── Trample ──
        if result["tramples"]:
            trample_lines = ["### TRAMPLE!"]
            for trample in result["tramples"]:
                faction = trample["faction"]
                trample_lines.append(
                    f"**{faction} ({FACTIONS[faction]}) TRAMPLES!** "
                    f"({trample['pit_count']} cards in Pit)")
                for pid, cards in trample.get("casualties", {}).items():
                    card_str = ", ".join(str(c) for c in cards)
                    vp_lost = sum(c.vp for c in cards)
                    trample_lines.append(f"  - P{pid} loses {card_str} ({vp_lost} VP crushed)")
            self.narrative.append("\n".join(trample_lines))

        # ── Scores after round ──
        score_parts = [f"P{p.id}:{p.vp}" for p in self.game.players]
        self.narrative.append(f"**Scores:** {' | '.join(score_parts)}")

    def _narrate_final_scores(self):
        """Narrate the final scores and winner."""
        lines = ["---\n## Final Scores"]
        lines.append(f"*Game ended: {self.game.end_reason}*\n")

        scores = self.game.get_final_scores()
        for s in scores:
            pid = s["player_id"]
            ai = self.ais[pid]
            medal = "🥇" if s["finish_position"] == 1 else \
                    "🥈" if s["finish_position"] == 2 else \
                    "🥉" if s["finish_position"] == 3 else "  "

            lines.append(
                f"{medal} **P{pid}** ({ai.style}): **{s['total_vp']} VP** "
                f"(cards: {s['card_vp']}, sets: {s['set_bonus']}, "
                f"{s['unique_colors']} colors)")
            lines.append(f"   Score pile: {', '.join(s['score_pile'])}")

        # Game stats
        lines.append(f"\n**Game Stats:**")
        lines.append(f"- Rounds: {self.game.round_number}")
        lines.append(f"- Sneaks: {self.game.stats['sneak_attempts']} attempted, "
                    f"{self.game.stats['sneak_successes']} successful")
        lines.append(f"- Shoves: {self.game.stats['shove_count']}")
        lines.append(f"- Tramples: {len(self.game.stats['tramples'])}")
        lines.append(f"- Ties: {self.game.stats['ties']}")

        self.narrative.append("\n".join(lines))


def main():
    parser = argparse.ArgumentParser(
        description="The Merch Stand Mob — Narrated Single Game"
    )
    parser.add_argument("-s", "--seed", type=int, default=42,
                       help="Random seed (default: 42)")
    parser.add_argument("-p", "--players", type=int, default=4,
                       help="Number of players (3-5, default: 4)")
    parser.add_argument("-o", "--output", type=str, default=None,
                       help="Output Markdown file (default: stdout)")
    parser.add_argument("--config", type=str, default=None,
                       help="Path to config.json")
    parser.add_argument("--preset", type=str, default=None,
                       choices=["experts", "beginners", "mixed", "styles"])
    parser.add_argument("--skill", type=str, default=None)
    parser.add_argument("--styles", type=str, default=None)

    args = parser.parse_args()

    config = load_config(args.config)

    # Build player configs
    num_players = args.players
    player_configs = [{"skill": 1.0, "style": "balanced", "aggression": 0.5}
                     for _ in range(num_players)]

    if args.preset == "styles":
        style_list = list(STYLE_PROFILES.keys())
        player_configs = [{"skill": 1.0, "style": style_list[i % len(style_list)],
                          "aggression": 0.5}
                         for i in range(num_players)]
    elif args.preset == "mixed":
        player_configs[0] = {"skill": 1.0, "style": "balanced", "aggression": 0.5}
        for i in range(1, num_players):
            player_configs[i] = {"skill": 0.3, "style": "balanced", "aggression": 0.5}

    if args.skill:
        skills = [float(s) for s in args.skill.split(",")]
        for i, s in enumerate(skills):
            if i < len(player_configs):
                player_configs[i]["skill"] = s

    if args.styles:
        styles = args.styles.split(",")
        for i, s in enumerate(styles):
            if i < len(player_configs):
                player_configs[i]["style"] = s.strip()

    narrated = NarratedGame(config, num_players, args.seed, player_configs)
    markdown = narrated.play()

    if args.output:
        with open(args.output, 'w') as f:
            f.write(markdown)
        print(f"Narrated game saved to {args.output}")
    else:
        print(markdown)


if __name__ == "__main__":
    main()
