"""Narration engine for Kahu — generates a detailed Markdown play-by-play."""

import sys
import os
import copy
from typing import List, Dict, Optional
from collections import defaultdict

from cards import Card, Offering
from kahu_parser import load_market_cards, find_csv
from game_state import GameState, Player, load_config
from ai_player import KahuAI


PLAYER_NAMES = ["Kai", "Leilani", "Makoa", "Naia"]
PLAYER_EMOJI = ["🔴", "🔵", "🟡", "🟢"]


def pua_str(pua: dict) -> str:
    parts = []
    if pua.get("Red", 0): parts.append(f"{pua['Red']}R")
    if pua.get("Blue", 0): parts.append(f"{pua['Blue']}B")
    if pua.get("Yellow", 0): parts.append(f"{pua['Yellow']}Y")
    return " ".join(parts) if parts else "none"


def market_str(game: GameState) -> str:
    slots = []
    for i, card in enumerate(game.market_row):
        if card is None:
            slots.append("(empty)")
        else:
            cost = game._get_market_cost(i)
            discount = " 💰" if i == len(game.market_row) - 1 else ""
            slots.append(f"{card.name}({cost}){discount}")
    return " | ".join(slots)


def score_snapshot(game: GameState) -> str:
    parts = []
    for p in game.players:
        cards = p.all_cards
        card_vp = sum(c.vp for c in cards)
        token_vp = sum(p.vp_tokens)
        parts.append(f"{PLAYER_NAMES[p.id]}: {card_vp + token_vp}vp ({p.num_vp_tokens} tokens, {pua_str(p.pua)} pua)")
    return " | ".join(parts)


def offering_status(game: GameState) -> str:
    parts = []
    for off in game.offerings:
        cost_str = "".join(c[0] * n for c, n in off.pua_cost.items())
        top = off.top_vp_token
        taken = len(off.completed_by)
        parts.append(f"{off.name}[{cost_str}] next:{top}vp ({taken} claimed)")
    return " | ".join(parts)


class NarratedGame:
    """Play a full game with detailed narration."""

    def __init__(self, config, market_cards, num_players, seed):
        self.game = GameState(config, num_players, seed=seed,
                              market_cards=list(market_cards))
        self.ais = [
            KahuAI(skill=1.0, style="balanced", aggression=0.5,
                   rng_seed=seed + i * 10000)
            for i in range(num_players)
        ]
        self.narrative: List[str] = []
        self.seed = seed

    def _add(self, text: str):
        self.narrative.append(text)

    def play(self) -> dict:
        """Play the full game, collecting narrative."""
        game = self.game

        # Setup narration
        self._narrate_setup()

        turn = 0
        while not game.game_over and turn < 200:
            player = game.get_current_player()
            ai = self.ais[player.id]
            round_num = turn // game.num_players + 1
            turn_in_round = turn % game.num_players + 1
            name = PLAYER_NAMES[player.id]
            emoji = PLAYER_EMOJI[player.id]

            if turn_in_round == 1:
                self._add(f"\n---\n\n## Round {round_num}\n")
                self._add(f"*Lava tracker: {game.lava_position} | "
                          f"Pua prices: R={game.pua_prices['Red']} B={game.pua_prices['Blue']} Y={game.pua_prices['Yellow']}*\n")

            self._add(f"\n### {emoji} {name}'s Turn\n")

            # Show hand
            hand_cards = [f"{c.name}({c.influence}i)" for c in player.hand]
            self._add(f"**Hand:** {', '.join(hand_cards)}")

            # Step 1: Play hand
            lava_before = game.lava_position
            play_result = game.play_hand(player, ai_callback=ai.effect_callback)

            # v3: Hula remove narration
            if play_result.get("hula_removed"):
                removed_card = play_result["hula_removed"]
                self._add(f"\n> 💃 **Hula!** {name} removes **{removed_card.name}** from their hand permanently.")

            if play_result["lava_triggered"]:
                if play_result["tiki_used"]:
                    self._add(f"\n> ⚡ **Lava Flow!** {name}'s Tiki absorbs the eruption. The Tiki crumbles to the discard pile.")
                elif play_result["lava_advanced"]:
                    self._add(f"\n> 🌋 **Lava Flow!** No Tiki to protect {name}. Lava advances to **{game.lava_position}**.")
                    if game.lava_position != lava_before - 1:
                        # Multiple advances (two lava cards)
                        pass
                    # Check for escalation
                    # Read escalation thresholds from config
                    esc = game.rules.get("escalation_events", {})
                    esc_labels = {
                        "second_lava": "Second Lava — every player receives another Lava Flow card!",
                        "tiki_lockout": "Tiki Lockout — no more Tikis can be claimed!",
                        "market_wipe_shrink": "Market Wipe + Shrink — market cleared and reduced to 4 slots!",
                        "pua_price_increase": "Pua Price Increase — all Pua prices rise by 1!",
                        "market_wipe": "Market Wipe — market cleared and refilled!",
                    }
                    for threshold, event in [(int(k), esc_labels.get(v, v)) for k, v in esc.items()]:
                        if game.lava_position <= threshold < lava_before:
                            self._add(f"> 🚨 **ESCALATION at {threshold}: {event}**")

            # Step 1b: Effects
            effect_result = game.resolve_card_effects(player, ai.effect_callback)

            effect_notes = []
            if effect_result.get("cards_drawn", 0) > 0:
                effect_notes.append(f"drew {effect_result['cards_drawn']} extra cards")
            if effect_result.get("cards_removed", 0) > 0:
                effect_notes.append(f"removed {effect_result['cards_removed']} cards from the game")
            if effect_result.get("pua_gained"):
                colors = effect_result["pua_gained"]
                effect_notes.append(f"gained {', '.join(colors)} Pua from card effects")
            if effect_notes:
                self._add(f"\n*Card effects: {'; '.join(effect_notes)}*")

            self._add(f"\n**Influence available: {player.influence_this_turn}**")

            # Step 2: Spending
            spending_actions = ai.plan_spending(player, game)

            if spending_actions:
                self._add("")  # blank line
                for act in spending_actions:
                    atype = act.get("type", "unknown")
                    if atype == "complete_offering":
                        off_name = act.get("offering", "?")
                        vp = act.get("vp", 0)
                        self._add(f"> 🏆 **Completes the {off_name} offering!** Takes the **{vp} VP** token. "
                                  f"({name} now has {player.num_vp_tokens} VP tokens)")
                        if player.num_vp_tokens >= 3:
                            self._add(f">\n> 🎉 **{name} has collected 3 VP tokens — ENDGAME TRIGGERED!** "
                                      f"Finish the round, then final scoring.")
                    elif atype == "buy_pua":
                        color = act.get("color", "?")
                        cost = act.get("cost", 0)
                        self._add(f"- Buys **{color} Pua** for {cost} influence "
                                  f"(now holding: {pua_str(player.pua)})")
                    elif atype == "buy_market":
                        card = act.get("card")
                        cost = act.get("cost", 0)
                        card_name = card.name if card else "?"
                        self._add(f"- Buys **{card_name}** from the market for {cost} influence")
                    elif atype == "buy_surf":
                        cost = act.get("cost", 0)
                        self._add(f"- Buys a **Surf** card for {cost} influence")
                    elif atype == "claim_tiki":
                        self._add(f"> 🗿 **Claims a Tiki!** Spends 1R + 1B + 1Y Pua for lava protection.")
            else:
                self._add(f"\n*{name} saves their influence — nothing worth buying this turn.*")

            if player.influence_this_turn > 0:
                self._add(f"\n*{player.influence_this_turn} influence unspent (lost)*")

            # Steps 3-4
            game.refresh_market()
            game.cleanup_and_draw(player)
            game.advance_turn()
            turn += 1

        # Final scoring
        self._narrate_finale()

        final_scores = game.calculate_final_scores()
        winner = max(final_scores.keys(), key=lambda pid: (
            final_scores[pid]["total"], final_scores[pid]["pua_remaining"]))

        return {
            "seed": self.seed,
            "winner": winner,
            "winner_name": PLAYER_NAMES[winner],
            "turns": turn,
            "rounds": game.round_number,
            "final_scores": final_scores,
            "narrative": "\n".join(self.narrative),
        }

    def _narrate_setup(self):
        game = self.game
        self._add(f"# Kahu — Narrated Game\n")
        self._add(f"*Seed: {self.seed} | {game.num_players} players | "
                  f"Lava starts at {game.lava_position}*\n")

        self._add(f"## Setup\n")
        self._add(f"**Active Offerings:**\n")
        for off in game.offerings:
            cost_str = "".join(c[0] * n for c, n in off.pua_cost.items())
            self._add(f"- **{off.name}** ({cost_str}) — {off.bonus_text}")

        self._add(f"\n**Starting Pua Prices:** Red={game.pua_prices['Red']}, "
                  f"Blue={game.pua_prices['Blue']}, Yellow={game.pua_prices['Yellow']}")
        self._add(f"\n**Opening Market:** {market_str(game)}")

        self._add(f"\n**Players:** {', '.join(PLAYER_NAMES[:game.num_players])}")
        for p in game.players:
            hand_cards = [f"{c.name}({c.influence}i)" for c in p.hand]
            self._add(f"- {PLAYER_NAMES[p.id]} opening hand: {', '.join(hand_cards)}")

    def _narrate_finale(self):
        game = self.game
        final_scores = game.calculate_final_scores()
        winner = max(final_scores.keys(), key=lambda pid: (
            final_scores[pid]["total"], final_scores[pid]["pua_remaining"]))

        self._add(f"\n---\n\n## Final Scoring\n")
        self._add(f"*The round is complete. All players tally their scores.*\n")

        # Sort by total descending
        ranked = sorted(final_scores.items(), key=lambda x: x[1]["total"], reverse=True)

        self._add(f"| Player | Card VP | Token VP | Offering Bonus | **Total** |")
        self._add(f"|---|---|---|---|---|")
        for pid, sc in ranked:
            name = PLAYER_NAMES[pid]
            marker = " 👑" if pid == winner else ""
            bonus_detail = ""
            if sc["bonus_details"]:
                bonus_detail = " (" + ", ".join(f"{k}: +{v}" for k, v in sc["bonus_details"].items()) + ")"
            self._add(f"| {name}{marker} | {sc['card_vp']} | {sc['token_vp']} | "
                      f"{sc['offering_bonus']}{bonus_detail} | **{sc['total']}** |")

        margin = ranked[0][1]["total"] - ranked[1][1]["total"]
        winner_name = PLAYER_NAMES[winner]

        self._add(f"\n**{winner_name} is crowned Kahu!**")
        if margin <= 3:
            self._add(f"A nail-biter — winning by just {margin} VP!")
        elif margin <= 6:
            self._add(f"A solid victory by {margin} VP.")
        else:
            self._add(f"A commanding win by {margin} VP.")

        self._add(f"\n*Final lava position: {game.lava_position} | "
                  f"Tikis used: {game.tikis_used} | "
                  f"Game lasted {game.round_number} rounds*")


def find_exciting_game(config, market_cards, num_players=3,
                       search_range=500, start_seed=1) -> int:
    """Search for a game with exciting properties: close finish, lead changes, wow moments."""
    from fun_audit import run_game_with_fun_tracking

    best_seed = start_seed
    best_score = -999

    for seed in range(start_seed, start_seed + search_range):
        r = run_game_with_fun_tracking(config, market_cards, num_players, seed)

        # Score excitement
        excitement = 0

        # Close finish (margin <= 3 is great)
        if r["margin"] <= 2:
            excitement += 10
        elif r["margin"] <= 4:
            excitement += 5
        elif r["margin"] <= 6:
            excitement += 2

        # Lead changes
        excitement += min(r["lead_changes"], 10) * 1.5

        # Comeback (last place at half finishes top 2)
        if r["last_to_top2"]:
            excitement += 8

        # Early leader doesn't win
        if not r["early_leader_won"]:
            excitement += 4

        # Wow moments
        excitement += min(r["wow_turns"], 12) * 0.5

        # Prefer games that end by offerings (not max turns or lava)
        turns = r["turns"]
        if 30 <= turns <= 45:
            excitement += 3
        if r["lava_final"] <= 5:
            excitement += 2  # Lava was close — dramatic

        # Ascending tension
        if r["ascending"]:
            excitement += 3

        if excitement > best_score:
            best_score = excitement
            best_seed = seed

    return best_seed, best_score


if __name__ == "__main__":
    rules_version = "v1"
    num_players = 3
    output_path = None
    search = True
    seed = None

    if len(sys.argv) > 1:
        for arg in sys.argv[1:]:
            if arg.startswith("--seed="):
                seed = int(arg.split("=")[1])
                search = False
            elif arg.startswith("--players="):
                num_players = int(arg.split("=")[1])
            elif arg.startswith("--output="):
                output_path = arg.split("=")[1]
            elif arg.startswith("--rules="):
                rules_version = arg.split("=")[1]

    config = load_config(rules_version)
    if rules_version == "v3":
        csv_path = find_csv("kahu-cards-v3")
        if not csv_path:
            csv_path = find_csv()
    else:
        csv_path = find_csv()
    if not csv_path:
        print("ERROR: Cannot find kahu-cards CSV")
        sys.exit(1)
    market_cards = load_market_cards(csv_path)
    print(f"Using rules: {rules_version}, CSV: {csv_path}")

    if search and seed is None:
        print("Searching for an exciting game...")
        seed, score = find_exciting_game(config, market_cards, num_players,
                                          search_range=500)
        print(f"Found seed {seed} (excitement score: {score:.1f})")

    print(f"Narrating game with seed {seed}, {num_players} players...")
    narrated = NarratedGame(config, market_cards, num_players, seed)
    result = narrated.play()

    md = result["narrative"]

    if output_path:
        with open(output_path, 'w') as f:
            f.write(md)
        print(f"Narration saved to {output_path}")
    else:
        print(md)

    ranked = sorted(result['final_scores'].values(), key=lambda x: x['total'], reverse=True)
    margin = ranked[0]['total'] - ranked[1]['total']
    print(f"\nWinner: {result['winner_name']} | Margin: {margin} VP | Rounds: {result['rounds']}")
