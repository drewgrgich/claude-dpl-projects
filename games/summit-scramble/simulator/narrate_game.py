#!/usr/bin/env python3
"""
Summit Scramble Narration Engine.

Plays a single game with full AI thinking exposed, producing a
detailed Markdown play-by-play for debugging and feel validation.
"""

import argparse
import json
import os
import sys
from typing import List, Optional

from cards import Card, build_full_deck, FACTIONS, FACTION_ABILITIES, FACTION_NAMES
from game_state import (
    GameState, Player, Formation, FormationType,
    classify_formation, formation_beats,
)
from ai_player import HeuristicAI, STYLE_PROFILES


class NarratedGame:
    """Wrapper that plays a game and collects narrative blocks."""

    def __init__(self, config: dict, num_players: int, seed: int,
                 player_configs: List[dict] = None,
                 use_stored_surge: bool = False):
        self.config = config
        self.game = GameState(config, num_players, seed=seed,
                              use_stored_surge=use_stored_surge)
        self.game.setup()

        self.ais = []
        for i in range(num_players):
            pc = player_configs[i] if player_configs else {}
            self.ais.append(HeuristicAI(
                skill=pc.get("skill", 1.0),
                style=pc.get("style", "balanced"),
                aggression=pc.get("aggression", 0.5),
                rng_seed=seed + i * 1000,
            ))

        self.narrative: List[str] = []
        self.trick_num = 0

    def play(self) -> str:
        """Play full game, return Markdown narrative."""
        self._narrate_setup()

        turn = 0
        max_turns = self.config["game_rules"].get("max_turns_per_round", 300)

        while not self.game.round_over and turn < max_turns:
            turn += 1

            if self.game.check_round_over():
                break

            leader_idx = self.game.current_leader_idx
            leader = self.game.players[leader_idx]

            if leader.finished:
                self.game.current_leader_idx = self.game._next_active_player(leader_idx)
                continue

            self.trick_num += 1
            ai_leader = self.ais[leader_idx]

            # --- LEAD ---
            self._add(f"\n### Trick {self.trick_num}")
            self._add(self._player_status_line())

            lead = ai_leader.choose_lead(leader, self.game)
            if lead is None:
                self._add(f"**P{leader.pid}** has no valid lead — skipping.")
                self.game.current_leader_idx = self.game._next_active_player(leader_idx)
                continue

            self._add(f"\n**P{leader.pid} leads** with {self._fmt_formation(lead)}")
            self._narrate_lead_thinking(ai_leader, leader, lead)

            result = self.game.play_formation(leader, lead)
            if result.get("went_out"):
                self._add(f"\n🏔️ **P{leader.pid} REACHES THE SUMMIT!** "
                          f"(Position {result['finish_position']})")
                self._handle_trick_end_narrated(result)
                if self.game.check_round_over():
                    break
                continue

            # --- FOLLOW ---
            trick_ended = False
            follower_idx = self.game._next_active_player(leader_idx)
            players_acted = {leader_idx}

            while not trick_ended:
                if follower_idx in players_acted:
                    break

                follower = self.game.players[follower_idx]
                ai_follower = self.ais[follower_idx]

                if follower.finished or follower.pid in self.game.passed_players:
                    players_acted.add(follower_idx)
                    follower_idx = self.game._next_active_player(follower_idx)
                    continue

                # Check interrupts
                for p in self.game.get_active_players():
                    if p.pid == self.game.trick_winner_idx:
                        continue
                    ai = self.ais[p.pid]
                    interrupt = ai.choose_interrupt(p, self.game)
                    if interrupt:
                        self._add(f"\n💥 **P{p.pid} INTERRUPTS** with "
                                  f"{self._fmt_formation(interrupt)}!")
                        int_result = self.game.play_interrupt(p, interrupt)
                        if int_result.get("went_out"):
                            self._add(f"\n🏔️ **P{p.pid} REACHES THE SUMMIT!**")
                            self._handle_trick_end_narrated(int_result)
                            trick_ended = True
                        else:
                            trick_ended = True
                        break

                if trick_ended:
                    break

                follow_play = ai_follower.choose_follow(follower, self.game)
                if follow_play is None:
                    self._add(f"P{follower.pid} passes.")
                    self.game.player_passes(follower)
                else:
                    self._add(f"**P{follower.pid}** plays {self._fmt_formation(follow_play)}")
                    f_result = self.game.play_formation(follower, follow_play)
                    if f_result.get("went_out"):
                        self._add(f"\n🏔️ **P{follower.pid} REACHES THE SUMMIT!**")
                        self._handle_trick_end_narrated(f_result)
                        trick_ended = True
                        break

                players_acted.add(follower_idx)

                active_pids = self.game.get_active_pids()
                non_passed = [pid for pid in active_pids
                             if pid not in self.game.passed_players
                             and pid != self.game.trick_winner_idx]
                if not non_passed:
                    break

                follower_idx = self.game._next_active_player(follower_idx)

            # --- RESOLVE ---
            if not self.game.round_over and not trick_ended:
                trick_result = self.game.resolve_trick()
                winner_pid = trick_result["winner"]
                self._add(f"\n✓ **P{winner_pid} wins the trick.**")

                if trick_result["power_triggered"] and trick_result["ability"]:
                    winner = self.game.players[winner_pid]
                    if not winner.finished:
                        ability = trick_result["ability"]
                        ai_winner = self.ais[winner_pid]

                        if ability == "choose":
                            winning_f = trick_result["formation"]
                            ability = ai_winner.choose_ability_faction(
                                winning_f, winner, self.game)

                        if ability:
                            choices = ai_winner.make_ability_choices(
                                ability, winner, self.game)
                            ab_result = self.game.execute_ability(
                                winner, ability, choices)
                            self._narrate_ability(winner_pid, ability, ab_result)

                if self.game.check_round_over():
                    break
            elif not self.game.round_over and trick_ended:
                # Trick ended by interrupt or going out — resolve
                if self.game.current_formation is not None:
                    trick_result = self.game.resolve_trick()
                    winner_pid = trick_result["winner"]
                    self._add(f"\n✓ **P{winner_pid} wins the trick.**")

                    if trick_result["power_triggered"] and trick_result["ability"]:
                        winner = self.game.players[winner_pid]
                        if not winner.finished:
                            ability = trick_result["ability"]
                            ai_winner = self.ais[winner_pid]
                            if ability == "choose":
                                winning_f = trick_result["formation"]
                                ability = ai_winner.choose_ability_faction(
                                    winning_f, winner, self.game)
                            if ability:
                                choices = ai_winner.make_ability_choices(
                                    ability, winner, self.game)
                                ab_result = self.game.execute_ability(
                                    winner, ability, choices)
                                self._narrate_ability(winner_pid, ability, ab_result)

                if self.game.check_round_over():
                    break

        self._narrate_final()
        return "\n".join(self.narrative)

    # -------------------------------------------------------------------
    # Narrative helpers
    # -------------------------------------------------------------------

    def _add(self, text: str):
        self.narrative.append(text)

    def _narrate_setup(self):
        game = self.game
        self._add(f"# Summit Scramble — Narrated Game")
        self._add(f"\n**Seed:** {game.seed} | **Players:** {game.num_players} | "
                  f"**Cards each:** {self.config['game_rules']['starting_hand'][game.pkey]}")
        self._add(f"**Trail:** {game.trail.size} cards | **Base Camp:** empty")

        for i, p in enumerate(game.players):
            ai = self.ais[i]
            hand_str = ", ".join(str(c) for c in sorted(p.hand, key=lambda c: (c.rank, c.faction)))
            self._add(f"\n**Player {p.pid}** (style: {ai.style_name}, "
                      f"skill: {ai.skill}, aggression: {ai.aggression})")
            self._add(f"> Hand ({p.hand_size}): {hand_str}")

        self._add(f"\n---\n")

    def _player_status_line(self) -> str:
        parts = []
        for p in self.game.players:
            status = "🏔️" if p.finished else f"{p.hand_size}cards"
            parts.append(f"P{p.pid}:{status}")
        return f"*[{' | '.join(parts)} | Trail:{self.game.trail.size} | Camp:{self.game.base_camp.size}]*"

    def _fmt_formation(self, f: Formation) -> str:
        cards = " ".join(str(c) for c in f.cards)
        names = {
            FormationType.SOLO: "Solo Sprint",
            FormationType.SURGE: f"Surge ({f.length})",
            FormationType.DAISY_CHAIN: f"Daisy Chain ({f.length})",
            FormationType.CONFETTI_CANNON: "Confetti Cannon",
            FormationType.TRIP_UP: "Trip-Up",
        }
        return f"**{names.get(f.ftype, f.ftype)}** [{cards}]"

    def _narrate_lead_thinking(self, ai: HeuristicAI, player: Player,
                               chosen: Formation):
        options = self.game.get_legal_formations(player)
        if len(options) <= 3:
            return  # not much to think about

        # Show top 3 alternatives
        scored = []
        for f in options[:20]:  # limit for performance
            score = ai._score_lead(f, player, self.game)
            scored.append((f, score))
        scored.sort(key=lambda x: -x[1])

        lines = ["> **Considering leads...**"]
        for f, score in scored[:4]:
            marker = " ← CHOSEN" if f.cards == chosen.cards else ""
            lines.append(f"> - {self._fmt_formation(f)}: score {score:.1f}{marker}")
        self._add("\n".join(lines))

    def _narrate_ability(self, pid: int, ability: str, result: dict):
        ability_names = {
            "rotation": "The Rotation",
            "scout": "Scout",
            "streamline": "Streamline",
            "recalibrate": "Recalibrate",
            "revelation": "The Revelation",
            "reclaim": "Reclaim",
        }
        name = ability_names.get(ability, ability)
        self._add(f"\n⚡ **P{pid} triggers {name}!**")

        if ability == "rotation" and "direction" in result:
            self._add(f"> Direction: {result['direction']}")
        elif ability == "recalibrate":
            if result.get("drawn"):
                self._add(f"> Drew: {result['drawn'][0]}")
            if result.get("discarded"):
                self._add(f"> Discarded: {', '.join(str(c) for c in result['discarded'])}")
        elif ability == "revelation" and "target" in result:
            self._add(f"> Target: P{result['target']}")

    def _handle_trick_end_narrated(self, result: dict):
        for card_list in self.game.current_trick_cards:
            for c in card_list:
                self.game.base_camp.add_to_bottom(c)
        self.game.current_trick_cards = []
        self.game.current_formation = None
        self.game.passed_players.clear()
        self.game.trick_count += 1

    def _narrate_final(self):
        self._add(f"\n---\n")
        self._add(f"## Final Results")
        self._add(f"\n**Tricks played:** {self.trick_num}")

        fatigue = self.game.calculate_fatigue()
        self._add(f"\n| Player | Position | Cards Left | Fatigue |")
        self._add(f"|--------|----------|------------|---------|")
        for p in self.game.players:
            pos = p.finish_position if p.finish_position > 0 else "DNF"
            self._add(f"| P{p.pid} | {pos} | {p.hand_size} | "
                      f"{fatigue.get(p.pid, '?')} Zzz's |")


def main():
    parser = argparse.ArgumentParser(
        description="Narrate a single Summit Scramble game")
    parser.add_argument("-p", "--players", type=int, default=4)
    parser.add_argument("-s", "--seed", type=int, default=42)
    parser.add_argument("-o", "--output", type=str, default=None)
    parser.add_argument("--stored-surge", action="store_true")
    parser.add_argument("--skill", type=str, default=None)
    parser.add_argument("--styles", type=str, default=None)
    args = parser.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(script_dir, "config.json")) as f:
        config = json.load(f)

    player_configs = [{"skill": 1.0, "style": "balanced", "aggression": 0.5}
                      for _ in range(args.players)]
    if args.skill:
        for i, s in enumerate(args.skill.split(",")):
            if i < len(player_configs):
                player_configs[i]["skill"] = float(s)
    if args.styles:
        for i, s in enumerate(args.styles.split(",")):
            if i < len(player_configs):
                player_configs[i]["style"] = s.strip()

    narrated = NarratedGame(config, args.players, args.seed,
                            player_configs=player_configs,
                            use_stored_surge=args.stored_surge)
    md = narrated.play()

    if args.output:
        with open(args.output, 'w') as f:
            f.write(md)
        print(f"Narrative saved to {args.output}")
    else:
        print(md)


if __name__ == "__main__":
    main()
