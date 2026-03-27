#!/usr/bin/env python3
"""
Narration engine for The Tunnel Brawl v2.0.

Plays a single game with detailed AI-thinking commentary,
outputting a Markdown play-by-play report.
"""

import argparse
import json
import os
import sys
from typing import List

from cards import Card
from game_state import GameState
from ai_player import HeuristicAI, STYLE_PROFILES


class NarratedGame:
    """Plays one game with full narration of AI decisions."""

    def __init__(self, config: dict, num_players: int, seed: int,
                 player_configs: List[dict] = None, max_rounds: int = 50):
        self.config = config
        self.num_players = num_players
        self.seed = seed
        self.max_rounds = max_rounds
        self.game = GameState(config, num_players, seed=seed)

        # Create AIs
        self.ais = []
        for i in range(num_players):
            pc = player_configs[i] if player_configs and i < len(player_configs) else {}
            self.ais.append(HeuristicAI(
                player_id=i,
                skill=pc.get("skill", 1.0),
                style=pc.get("style", "balanced"),
                aggression=pc.get("aggression", 0.5),
                rng_seed=seed * 100 + i,
            ))

        self.narrative: List[str] = []

    def play(self) -> str:
        """Play the full game and return Markdown narration."""
        self.game.setup()
        self._narrate_setup()

        while not self.game.game_over and self.game.round_number < self.max_rounds:
            self._play_round()
            self.game.check_game_end()
            if self.num_players == 3:
                self.game.rotate_defender()
            self.game.deployments.clear()

        self._narrate_final()
        return "\n\n".join(self.narrative)

    def _play_round(self):
        """Play and narrate one full round."""
        round_num = self.game.round_number + 1
        self._add(f"## Round {round_num}")

        scores = " | ".join(f"P{p.id}: {p.victory_points} VP"
                            for p in self.game.players)
        self._add(f"**Scores:** {scores}")

        if self.num_players == 3:
            defender = [p for p in self.game.players if p.is_defender][0]
            self._add(f"**Defender:** P{defender.id}")

        # Deployment phase
        self._add("### Deployment Phase")
        for i, player in enumerate(self.game.players):
            forced = player.forced_card
            if forced and forced not in player.hand:
                forced = None
                player.forced_card = None

            hand_str = ", ".join(str(c) for c in sorted(player.hand, key=lambda c: (c.faction, c.rank)))
            self._add(f"**P{i}** hand ({len(player.hand)} cards): [{hand_str}]")

            if len(player.hand) < 2:
                self._add(f"> P{i} doesn't have enough cards to deploy!")
                continue

            home, away = self.ais[i].choose_deployment(player.hand, self.game, forced)

            # Narrate thinking
            thinking = []
            if forced:
                thinking.append(f"Forced to play {forced} (Green talent)")

            # Check Wild considerations
            if home.is_wild:
                if not away.is_wild and away.faction == home.faction:
                    thinking.append(f"Playing Wild {home} in Home with {away} anchor in Away — will activate!")
                else:
                    thinking.append(f"Playing Wild {home} in Home — will trip (no matching anchor)")
            if away.is_wild:
                if not home.is_wild and home.faction == away.faction:
                    thinking.append(f"Playing Wild {away} in Away with {home} anchor in Home — will activate!")
                else:
                    thinking.append(f"Playing Wild {away} in Away — will trip")

            style = self.ais[i].style
            thinking.append(f"Style: {style} | Aggression: {self.ais[i].aggression}")

            if thinking:
                self._add("> " + "\n> ".join(thinking))

            self._add(f"→ **P{i} deploys:** Home = {home}, Away = {away}")

            result = self.game.set_deployment(i, home, away)
            if not result["success"]:
                home, away = player.hand[0], player.hand[1]
                self.game.set_deployment(i, home, away)
                self._add(f"  *(fallback: {home}, {away})*")

            player.forced_card = None

        if len(self.game.deployments) < self.num_players:
            self._add("⚠ Not all players deployed — round skipped")
            return

        # Resolution
        self._add("### Brawl Resolution")

        def clash_chooser(pid, gs, cr):
            card = self.ais[pid].choose_clash_card(pid, gs, cr)
            self._add(f"> P{pid} plays {card} for CLASH! round {cr}")
            return card

        round_data = self.game.resolve_round(clash_chooser)

        # Narrate each brawl
        for br in round_data["brawl_results"]:
            if br.clash_round > 0:
                continue  # Already narrated inline
            label = f"P{br.attacker_id} ({br.attacker_card}[eff:{br.attacker_effective_rank}]) vs P{br.defender_id} ({br.defender_card}[eff:{br.defender_effective_rank}])"
            if br.winner_id is not None:
                self._add(f"⚔ {label} → **P{br.winner_id} wins!** +{br.vp_awarded} VP")
            elif br.is_clash:
                self._add(f"⚔ {label} → **CLASH!** (tied at rank {br.attacker_effective_rank})")

        # Talents
        self._add("### Talent Phase")
        talent_triggered = False
        for i, player in enumerate(self.game.players):
            if self.game.can_trigger_talent(i):
                winning_cards = self.game.round_winning_cards.get(i, [])
                doubled = self.game.has_double_talent(i)
                faction = self.ais[i].choose_talent_faction(winning_cards, doubled, self.game)
                if faction:
                    double_str = " (DOUBLED!)" if doubled else ""
                    self._add(f"✨ P{i} triggers **{faction}** talent{double_str}")

                    def green_chooser(my_id, target_id, target_hand, gs):
                        card = self.ais[my_id].choose_green_target(my_id, target_id, target_hand, gs)
                        self._add(f"> Green: P{my_id} forces P{target_id} to play {card}")
                        return card

                    self.game.apply_talent(i, faction, doubled, green_chooser)
                    talent_triggered = True

        if not talent_triggered:
            self._add("*No talents triggered this round.*")

        # Draw phase
        self.game.draw_phase()
        self._add("### Draw Phase")
        for p in self.game.players:
            self._add(f"P{p.id}: now has {len(p.hand)} cards, {p.victory_points} VP")

        self._add("---")

    def _narrate_setup(self):
        """Narrate the game setup."""
        self._add(f"# The Tunnel Brawl v2.0 — Narrated Game")
        self._add(f"**Players:** {self.num_players} | **Seed:** {self.seed} | "
                  f"**Victory Target:** {self.config['game_rules']['victory_threshold'][f'{self.num_players}_player']} VP")

        for i, ai in enumerate(self.ais):
            self._add(f"- **P{i}:** skill={ai.skill}, style={ai.style}, aggression={ai.aggression}")

        hand_size = self.config["game_rules"]["starting_hand_size"][f"{self.num_players}_player"]
        self._add(f"\n*Each player dealt {hand_size} cards from the shuffled 66-card deck.*")

        if self.num_players == 3:
            defender = [p for p in self.game.players if p.is_defender][0]
            self._add(f"*P{defender.id} is the starting Defender.*")

        self._add("---")

    def _narrate_final(self):
        """Narrate the game conclusion."""
        self._add(f"## Game Over!")
        self._add(f"**Rounds played:** {self.game.round_number}")

        if self.game.winner_id is not None:
            winner = self.game.players[self.game.winner_id]
            self._add(f"**Winner: P{winner.id}** with **{winner.victory_points} VP!**")
        else:
            self._add("**No winner (max rounds reached)**")

        self._add("### Final Standings")
        sorted_players = sorted(self.game.players, key=lambda p: p.victory_points, reverse=True)
        for rank, p in enumerate(sorted_players, 1):
            self._add(f"{rank}. P{p.id}: {p.victory_points} VP | "
                      f"Brawls W/L: {p.brawls_won}/{p.brawls_lost} | "
                      f"CLASH! W/L: {p.clashes_won}/{p.clashes_lost} | "
                      f"Wilds: {p.wilds_activated} activated, {p.wilds_tripped} tripped | "
                      f"Talents: {p.talents_triggered}")

    def _add(self, text: str):
        """Add a line to the narrative."""
        self.narrative.append(text)


# ─── CLI ─────────────────────────────────────────────────────────

def load_config(config_path: str = None) -> dict:
    if config_path:
        with open(config_path, 'r') as f:
            return json.load(f)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    for c in [os.path.join(script_dir, "config.json"),
              os.path.join(script_dir, "..", "config.json")]:
        if os.path.exists(c):
            with open(c, 'r') as f:
                return json.load(f)
    print("ERROR: config.json not found.", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="The Tunnel Brawl v2.0 — Narrated Game Engine"
    )
    parser.add_argument("-p", "--players", type=int, default=4,
                        help="Number of players (2-5, default: 4)")
    parser.add_argument("-s", "--seed", type=int, default=42,
                        help="Random seed (default: 42)")
    parser.add_argument("--max-rounds", type=int, default=50,
                        help="Max rounds (default: 50)")
    parser.add_argument("--config", type=str, default=None)
    parser.add_argument("-o", "--output", type=str, default=None,
                        help="Output file (default: stdout)")
    parser.add_argument("--preset", type=str, default=None,
                        choices=["experts", "beginners", "mixed", "styles"])
    parser.add_argument("--skill", type=str, default=None)
    parser.add_argument("--styles", type=str, default=None)

    args = parser.parse_args()

    config = load_config(args.config)

    # Build player configs
    num_p = args.players
    player_configs = [{"skill": 1.0, "style": "balanced", "aggression": 0.5}
                      for _ in range(num_p)]
    if args.preset == "styles":
        style_list = list(STYLE_PROFILES.keys())
        player_configs = [{"skill": 1.0, "style": style_list[i % len(style_list)], "aggression": 0.5}
                          for i in range(num_p)]
    elif args.preset == "mixed":
        player_configs = [{"skill": 1.0, "style": "balanced", "aggression": 0.5}]
        player_configs += [{"skill": 0.3, "style": "balanced", "aggression": 0.5}
                           for _ in range(num_p - 1)]

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

    narrated = NarratedGame(config, num_p, args.seed, player_configs, args.max_rounds)
    md = narrated.play()

    if args.output:
        with open(args.output, 'w') as f:
            f.write(md)
        print(f"Narration saved to {args.output}", file=sys.stderr)
    else:
        print(md)
