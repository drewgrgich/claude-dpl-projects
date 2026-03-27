"""
Hamster High Council — Single Game Narration Engine.

Plays one game with full AI thinking exposed, generating a Markdown
play-by-play. Invaluable for catching bugs, validating game feel,
and understanding AI decisions.

Usage:
    python narrate_game.py --seed 42
    python narrate_game.py --seed 42 -o game_log.md
"""

import argparse
import os
import sys
from typing import List, Optional

from cards import Card, FACTIONS, FACTION_SYMBOLS, FACTION_NAMES
from game_state import GameState, Player, DIAL_POSITIONS, DIAL_MULTIPLIER, LOW_WINS_POSITIONS
from ai_player import HeuristicAI


class NarratedGame:
    """Play a single game with full narration and AI reasoning."""

    def __init__(self, config: dict, seed: int,
                 player_configs: Optional[List[dict]] = None):
        self.config = config
        self.seed = seed
        self.game = GameState(config, seed=seed)
        self.num_players = self.game.num_players

        # Create AIs
        self.ais = []
        for i in range(self.num_players):
            pc = player_configs[i] if player_configs and i < len(player_configs) else {}
            self.ais.append(HeuristicAI(
                player_id=i,
                skill=pc.get("skill", 1.0),
                style=pc.get("style", "balanced"),
                aggression=pc.get("aggression", 0.5),
                rng_seed=seed * 100 + i
            ))

        self.narrative: List[str] = []

    def play(self) -> str:
        """Play the full game and return Markdown narration."""
        self._header()

        round_count = 0
        max_rounds = self.config["game_rules"].get("max_rounds", 20)

        while not self.game.game_over and round_count < max_rounds:
            round_count += 1

            def keep_fn(player, all_cards, gs):
                return self.ais[player.id].choose_blessing_keep(player, all_cards, gs)

            self.game.setup_new_round(keep_fn=keep_fn)
            self._narrate_round_start()

            trick_count = 0
            while not self.game.game_over and not self.game.is_round_over():
                trick_count += 1
                self._narrate_trick(trick_count)

                if trick_count > 50:
                    self._add("**⚠️ Safety limit: too many tricks in round.**")
                    break

            if not self.game.game_over:
                self.game.end_round()
                self._narrate_round_end()

        self._narrate_final()
        return "\n\n".join(self.narrative)

    def _header(self):
        """Opening header."""
        self._add(f"# 🏛️ Hamster High Council — Narrated Game")
        self._add(f"**Seed:** {self.seed} · **Players:** {self.num_players} · "
                  f"**VP Target:** {self.config['game_rules']['vp_target']}")

        player_info = []
        for i, ai in enumerate(self.ais):
            player_info.append(
                f"P{i}: {ai.style_name} (skill={ai.skill:.1f}, agg={ai.aggression:.1f})")
        self._add("**Players:** " + " · ".join(player_info))
        self._add("---")

    def _narrate_round_start(self):
        """Narrate the start of a round."""
        g = self.game
        self._add(f"## Round {g.round_number}")
        self._add(f"**Trump:** {FACTION_SYMBOLS[g.trump_faction]} {g.trump_faction} "
                  f"({FACTION_NAMES[g.trump_faction]}) · "
                  f"**Elite:** {FACTION_SYMBOLS[g.elite_faction]} {g.elite_faction} "
                  f"({FACTION_NAMES[g.elite_faction]})")
        self._add(f"**Dealer:** P{g.dealer_id} · **Leader:** P{g.leader_id} · "
                  f"**Vault:** {g.vault.size} cards")

        # Show hands
        hand_lines = []
        for p in g.players:
            sorted_hand = sorted(p.hand)
            hand_str = " ".join(c.short() for c in sorted_hand)
            hand_lines.append(f"P{p.id} ({p.vp} VP): {hand_str}")
        self._add("**Hands:**\n" + "\n".join(f"- {h}" for h in hand_lines))
        self._add("")

    def _narrate_trick(self, trick_num: int):
        """Play and narrate one trick."""
        g = self.game
        dial = g.dial_position
        mult = DIAL_MULTIPLIER[dial]
        low_wins = dial in LOW_WINS_POSITIONS

        self._add(f"### Trick {trick_num} — Dial: **{dial}** "
                  f"({'low wins' if low_wins else 'high wins'}, ×{mult})")

        # Show partnerships
        partnerships = []
        for i in range(self.num_players):
            partner_id = g.get_partner_id(i)
            partnerships.append(f"P{i}↔P{partner_id}")
        self._add(f"*Partnerships: {' · '.join(partnerships)}*")

        # Play the trick with narration
        def choose_card(player, gs, led_faction):
            card = self.ais[player.id].choose_card(player, gs, led_faction)
            reasoning = self.ais[player.id].last_reasoning
            if reasoning:
                self._add(f"> **P{player.id} thinks:**")
                for line in reasoning:
                    self._add(f"> {line}")
            return card

        def choose_talent(player, gs, faction):
            use = self.ais[player.id].choose_talent(player, gs, faction)
            reasoning = self.ais[player.id].last_reasoning
            if reasoning:
                for line in reasoning:
                    self._add(f"> {line}")
            return use

        def choose_qf(player, gs):
            result = self.ais[player.id].choose_quick_fix_cards(player, gs)
            reasoning = self.ais[player.id].last_reasoning
            if reasoning:
                for line in reasoning:
                    self._add(f"> {line}")
            return result

        def choose_orange(player, gs):
            result = self.ais[player.id].choose_orange_swap(player, gs)
            reasoning = self.ais[player.id].last_reasoning
            if reasoning:
                for line in reasoning:
                    self._add(f"> {line}")
            return result

        def choose_green(player, peeked, gs):
            result = self.ais[player.id].choose_green_keep(player, peeked, gs)
            reasoning = self.ais[player.id].last_reasoning
            if reasoning:
                for line in reasoning:
                    self._add(f"> {line}")
            return result

        def choose_blue(player, opponents, gs):
            result = self.ais[player.id].choose_blue_targets(player, opponents, gs)
            reasoning = self.ais[player.id].last_reasoning
            if reasoning:
                for line in reasoning:
                    self._add(f"> {line}")
            return result

        result = g.play_trick(
            choose_card_fn=choose_card,
            choose_talent_fn=choose_talent,
            choose_quick_fix_cards_fn=choose_qf,
            choose_orange_swap_fn=choose_orange,
            choose_green_keep_fn=choose_green,
            choose_blue_targets_fn=choose_blue,
        )

        # Summarize result
        plays_str = " · ".join(f"P{pid}: {card.short()}" for pid, card in result.plays)
        self._add(f"**Plays:** {plays_str}")

        if result.tied_no_winner:
            self._add(f"**Result:** 🔄 TIE — no winner. Cards to Crate. Same leader.")
        else:
            extra = ""
            if result.trump_won:
                extra += " (Trump!)"
            if result.elite_broke_tie:
                extra += " (Elite tiebreak)"
            compression_note = ""
            if getattr(result, 'vp_compressed', False):
                compression_note = " ⚖️ **VP Compressed** (leader scores ×1)"
            self._add(f"**Result:** P{result.winner_id} wins with "
                      f"{result.winning_card.short()}{extra} → "
                      f"**{result.vp_scored} VP** "
                      f"({result.cards_in_trick} cards × "
                      f"{'1 compressed' if getattr(result, 'vp_compressed', False) else str(result.multiplier)})"
                      f"{compression_note}")

        # Score summary
        scores = " · ".join(f"P{p.id}={p.vp}" for p in g.players)
        self._add(f"*Scores: {scores} · Dial → {g.dial_position}*")

        if g.game_over:
            self._add(f"\n**🏆 P{g.winner_id} WINS THE GAME!**")

        self._add("")

    def _narrate_round_end(self):
        """Narrate end of round."""
        g = self.game
        scores = " · ".join(f"P{p.id}={p.vp}" for p in g.players)
        self._add(f"**End of Round {g.round_number}:** {scores}")
        self._add("---")

    def _narrate_final(self):
        """Final summary."""
        g = self.game
        self._add("## Final Results")
        self._add(f"**Rounds played:** {g.round_number}")
        self._add(f"**Total tricks:** {g.total_tricks} "
                  f"({g.total_tied_tricks} tied)")

        self._add("\n**Final Scores:**")
        for p in sorted(g.players, key=lambda p: p.vp, reverse=True):
            crown = " 👑" if p.id == g.winner_id else ""
            right_pct = (p.vp_from_right / p.vp * 100) if p.vp > 0 else 0
            self._add(f"- **P{p.id}: {p.vp} VP**{crown} "
                      f"({p.total_tricks_won} tricks won, "
                      f"{right_pct:.0f}% from RIGHT)")

        self._add(f"\n**Talent Usage:**")
        for f in FACTIONS:
            count = g.talent_activations[f]
            if count > 0:
                name = self.config["game_rules"]["talents"]["talent_list"][f]["name"]
                self._add(f"- {FACTION_SYMBOLS[f]} {name}: {count}×")

        self._add(f"\n**Dial Distribution:**")
        for pos in DIAL_POSITIONS:
            tricks = g.tricks_by_dial[pos]
            vp = g.vp_by_dial[pos]
            self._add(f"- {pos}: {tricks} tricks, {vp} VP")

    def _add(self, text: str):
        self.narrative.append(text)


# ── CLI ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Hamster High Council — Narrated Game")
    parser.add_argument("--seed", type=int, default=42,
                       help="Random seed (default: 42)")
    parser.add_argument("-o", "--output", type=str, default=None,
                       help="Output file (default: stdout)")
    parser.add_argument("--config", type=str, default=None,
                       help="Path to config.json")

    # Player configs
    parser.add_argument("--preset", type=str, default="experts",
                       choices=["experts", "beginners", "mixed", "styles"])
    parser.add_argument("--skill", type=str, default=None)
    parser.add_argument("--styles", type=str, default=None)

    args = parser.parse_args()

    config = GameState.load_config(args.config)

    # Build player configs
    num_players = config["game_rules"]["num_players"]
    player_configs = [{"skill": 1.0, "style": "balanced", "aggression": 0.5}
                      for _ in range(num_players)]
    if args.preset == "styles":
        style_list = ["balanced", "aggressive", "tactical", "cooperative"]
        for i in range(num_players):
            player_configs[i]["style"] = style_list[i % len(style_list)]

    narrated = NarratedGame(config, seed=args.seed, player_configs=player_configs)
    markdown = narrated.play()

    if args.output:
        with open(args.output, 'w') as f:
            f.write(markdown)
        print(f"Narration written to {args.output}")
    else:
        print(markdown)
