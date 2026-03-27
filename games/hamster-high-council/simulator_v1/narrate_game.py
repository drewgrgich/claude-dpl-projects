"""
Hamster High Council v1.0 — Single Game Narration Engine.

Usage:
    python narrate_game.py --seed 42
    python narrate_game.py --seed 42 -o game_log.md
"""

import argparse
from typing import List, Optional

from cards import FACTIONS, FACTION_SYMBOLS, FACTION_NAMES
from game_state import GameState, Player
from ai_player import HeuristicAI


class NarratedGame:
    def __init__(self, config: dict, seed: int,
                 player_configs: Optional[List[dict]] = None):
        self.config = config
        self.seed = seed
        self.game = GameState(config, seed=seed)
        self.num_players = self.game.num_players

        self.ais = []
        for i in range(self.num_players):
            pc = player_configs[i] if player_configs and i < len(player_configs) else {}
            self.ais.append(HeuristicAI(
                player_id=i,
                skill=pc.get("skill", 1.0),
                style=pc.get("style", "balanced"),
                rng_seed=seed * 100 + i
            ))
        self.narrative: List[str] = []

    def play(self) -> str:
        self._header()
        round_count = 0
        max_rounds = self.config["game_rules"].get("max_rounds", 20)

        while not self.game.game_over and round_count < max_rounds:
            round_count += 1
            self.game.setup_new_round()
            self._narrate_round_start()

            trick_count = 0
            final_bell_done = False
            while not self.game.game_over:
                emptied = self.game.player_emptied_hand()
                if emptied is not None and not final_bell_done:
                    if self.config["game_rules"]["final_bell"]["enabled"]:
                        self._add(f"\n**🔔 FINAL BELL!** P{emptied} emptied their hand.")
                        final_leader = (emptied + 1) % self.num_players
                        players_with_cards = [p for p in self.game.players if len(p.hand) > 0]
                        if len(players_with_cards) >= 2:
                            self.game.leader_id = final_leader
                            trick_count += 1
                            self._narrate_trick(trick_count, is_final_bell=True)
                    final_bell_done = True
                    break

                trick_count += 1
                self._narrate_trick(trick_count)
                if trick_count > 50:
                    break

            if not self.game.game_over:
                self.game.end_round()
                self._narrate_round_end()

        self._narrate_final()
        return "\n\n".join(self.narrative)

    def _header(self):
        self._add(f"# 🏛️ Hamster High Council v1.0 — Narrated Game")
        self._add(f"**Seed:** {self.seed} · **Players:** {self.num_players} · "
                  f"**VP Target:** {self.config['game_rules']['vp_target']}")
        player_info = [f"P{i}: {ai.style_name} (skill={ai.skill:.1f})"
                       for i, ai in enumerate(self.ais)]
        self._add("**Players:** " + " · ".join(player_info))
        self._add("---")

    def _narrate_round_start(self):
        g = self.game
        self._add(f"## Round {g.round_number}")
        self._add(f"**Trump:** {FACTION_SYMBOLS[g.trump_faction]} {g.trump_faction} · "
                  f"**Elite:** {FACTION_SYMBOLS[g.elite_faction]} {g.elite_faction} · "
                  f"**Wobbly:** {FACTION_SYMBOLS[g.wobbly_faction]} {g.wobbly_faction} "
                  f"(low wins when led!)")
        self._add(f"**Dealer:** P{g.dealer_id} · **Leader:** P{g.leader_id} · "
                  f"**Vault:** {g.vault.size} cards")

        hand_lines = []
        for p in g.players:
            sorted_hand = sorted(p.hand)
            hand_str = " ".join(c.short() for c in sorted_hand)
            hand_lines.append(f"P{p.id} ({p.vp} VP): {hand_str}")
        self._add("**Hands:**\n" + "\n".join(f"- {h}" for h in hand_lines))

    def _narrate_trick(self, trick_num: int, is_final_bell: bool = False):
        g = self.game
        fb = " [FINAL BELL]" if is_final_bell else ""
        self._add(f"### Trick {trick_num}{fb}")

        def choose_card(player, gs, led_faction):
            card = self.ais[player.id].choose_card(player, gs, led_faction)
            for line in self.ais[player.id].last_reasoning:
                self._add(f"> {line}")
            return card

        def choose_talent(player, gs, faction):
            use = self.ais[player.id].choose_talent(player, gs, faction)
            for line in self.ais[player.id].last_reasoning:
                self._add(f"> {line}")
            return use

        talent_cbs = {
            "orange": lambda w, p, gs: self.ais[w.id].choose_orange_keep(w, p, gs),
            "yellow": lambda w, t, gs: self.ais[w.id].choose_yellow_swap(w, t, gs),
            "green": lambda w, d, gs: self.ais[w.id].choose_green_return(w, d, gs),
            "blue": lambda w, o, gs: self.ais[w.id].choose_blue_action(w, o, gs),
            "purple": lambda w, gs: self.ais[w.id].choose_purple_action(w, gs),
        }

        result = g.play_trick(
            choose_card_fn=choose_card,
            choose_talent_fn=choose_talent,
            talent_callbacks=talent_cbs,
            is_final_bell=is_final_bell,
        )

        plays_str = " · ".join(f"P{pid}: {card.short()}" for pid, card in result.plays)
        self._add(f"**Plays:** {plays_str}")

        if result.tied_no_winner:
            self._add(f"**Result:** 🔄 TIE — cards to Crate.")
        else:
            extra = ""
            if result.trump_won:
                extra += " (TRUMP!)"
            if result.wobbly_won:
                extra += " (WOBBLY — low wins!)"
            if result.elite_broke_tie:
                extra += " (Elite tiebreak)"
            self._add(f"**Result:** P{result.winner_id} wins with "
                      f"{result.winning_card.short()}{extra} → "
                      f"**{result.cards_in_trick} cards to stash**")

        scores = " · ".join(f"P{p.id}={p.vp}" for p in g.players)
        self._add(f"*Scores: {scores}*")

        if g.game_over:
            self._add(f"\n**🏆 P{g.winner_id} WINS THE GAME!**")
        self._add("")

    def _narrate_round_end(self):
        g = self.game
        scores = " · ".join(f"P{p.id}={p.vp}" for p in g.players)
        self._add(f"**End of Round {g.round_number}:** {scores}")
        self._add("---")

    def _narrate_final(self):
        g = self.game
        self._add("## Final Results")
        self._add(f"**Rounds played:** {g.round_number}")
        self._add(f"**Total tricks:** {g.total_tricks}")

        self._add("\n**Final Scores:**")
        for p in sorted(g.players, key=lambda p: p.vp, reverse=True):
            crown = " 👑" if p.id == g.winner_id else ""
            self._add(f"- **P{p.id}: {p.vp} VP**{crown} "
                      f"({p.total_tricks_won} tricks, "
                      f"{p.trump_tricks_won} trump, {p.wobbly_tricks_won} wobbly)")

        self._add(f"\n**Talent Usage:**")
        for f in FACTIONS:
            count = g.talent_activations[f]
            if count > 0:
                name = self.config["game_rules"]["talents"]["talent_list"][f]["name"]
                self._add(f"- {FACTION_SYMBOLS[f]} {name}: {count}×")

    def _add(self, text: str):
        self.narrative.append(text)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Hamster High Council v1.0 — Narrated Game")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("-o", "--output", type=str, default=None)
    parser.add_argument("--config", type=str, default=None)
    parser.add_argument("--preset", type=str, default="experts",
                       choices=["experts", "beginners", "mixed", "styles"])

    args = parser.parse_args()
    config = GameState.load_config(args.config)

    num_players = config["game_rules"]["num_players"]
    player_configs = [{"skill": 1.0, "style": "balanced"} for _ in range(num_players)]
    if args.preset == "styles":
        for i, s in enumerate(["balanced", "aggressive", "wobbly_hunter", "hoarder"]):
            if i < num_players:
                player_configs[i]["style"] = s

    narrated = NarratedGame(config, seed=args.seed, player_configs=player_configs)
    markdown = narrated.play()

    if args.output:
        with open(args.output, 'w') as f:
            f.write(markdown)
        print(f"Narration written to {args.output}")
    else:
        print(markdown)
