"""Generate a narrated play session with AI thinking shown, output as Markdown."""

import json
import os
import re
import sys
import argparse
from typing import List, Optional
from collections import Counter

from cards import RecruitCard, EventCard, PlaybookCard, Deck, build_recruit_deck
from event_parser import load_events_csv, load_playbooks_csv
from event_checker import find_completable_events, find_best_card_combo
from game_state import GameState, Player, LineupSlot
from ai_player import HeuristicAI


class NarratedGame:
    """Runs a single game and produces a detailed Markdown narrative."""

    def __init__(self, config: dict, events: List[EventCard],
                 playbooks: List[PlaybookCard], num_players: int,
                 seed: int, max_turns: int = 200,
                 player_configs: list = None):
        self.config = config
        self.events = events
        self.playbooks = playbooks
        self.num_players = num_players
        self.seed = seed
        self.max_turns = max_turns
        self.player_configs = player_configs or []
        self.lines: List[str] = []

    def run(self) -> str:
        """Run the game and return Markdown text."""
        game = GameState(self.config, self.num_players, seed=self.seed,
                         events=self.events, playbooks=self.playbooks,
                         use_playbooks=len(self.playbooks) > 0)

        ais = []
        personas = self._build_personas()
        for i in range(self.num_players):
            if self.player_configs and i < len(self.player_configs):
                pc = self.player_configs[i]
                ais.append(HeuristicAI(
                    aggression=pc.get("aggression", 0.3 + i * 0.2),
                    skill=pc.get("skill", 1.0),
                    style=pc.get("style", "balanced"),
                    rng_seed=self.seed + i * 1000,
                ))
            else:
                aggression = 0.3 + (i * 0.2)
                ais.append(HeuristicAI(aggression=min(aggression, 0.9),
                                       rng_seed=self.seed + i * 1000))

        # ── Header ──
        self._h1("Contests of Chaos — Simulated Playtest")
        self._p(f"**Seed:** {self.seed} | **Players:** {self.num_players} | "
                f"**Wipe Cost:** {game.rules.get('wipe_jumbotron', {}).get('cost', 'N/A')} | "
                f"**Min Hand for Wipe:** {game.rules.get('wipe_jumbotron', {}).get('min_hand_size', 'N/A')} | "
                f"**Post-Wipe Surcharge:** {game.rules.get('wipe_jumbotron', {}).get('post_wipe_event_cost', 0)}")
        self._p(f"**Victory Threshold:** {game.rules['victory_threshold'][game.pkey]} Event VP | "
                f"**Hand Limit:** {game.rules['hand_limit']}")

        # Show player profiles
        self._p("\n**Player Profiles:**\n")
        for i in range(self.num_players):
            ai = ais[i]
            skill_label = "Expert" if ai.skill >= 0.9 else "Intermediate" if ai.skill >= 0.5 else "Beginner"
            self._p(f"- **{personas[i]}** (P{i}): {ai.style.title()} style, "
                    f"{skill_label} skill ({ai.skill:.1f}), "
                    f"aggression {ai.aggression:.1f}")

        self._hr()

        # ── Setup ──
        self._h2("Game Setup")

        # Setup with narrated choices
        def keep_fn(player, dealt, gs):
            ai = ais[player.id]
            kept, discarded = ai.choose_starting_hand(player, dealt, gs)
            self._narrate_starting_hand(player, dealt, kept, discarded, ai, gs, personas)
            return kept, discarded

        def playbook_fn(player, options, gs):
            ai = ais[player.id]
            keep, discard = ai.choose_playbook(player, options, gs)
            self._narrate_playbook_choice(player, options, keep, discard, ai, gs, personas)
            return keep, discard

        game.setup_with_choices(keep_fn=keep_fn, playbook_fn=playbook_fn)

        # Show initial board
        self._h3("Initial Board State")
        self._show_board(game)

        # ── Game Loop ──
        self._h2("Play-by-Play")
        turn_count = 0
        last_round = -1

        while not game.game_over and turn_count < self.max_turns:
            player = game.get_current_player()
            ai = ais[player.id]
            name = personas[player.id]
            round_num = game.turn_number + 1

            if game.turn_number != last_round:
                last_round = game.turn_number
                self._h3(f"Round {round_num}")
                self._show_board_compact(game)

            self._h4(f"Turn {turn_count + 1} — {name} (P{player.id})")
            self._show_player_status(player, game, personas)

            # Show full decision analysis
            self._narrate_full_decision(player, ai, game, personas)

            # Get and execute action
            action = ai.choose_action(player, game)
            action_type = action["type"]

            result = {"success": False}

            if action_type == "complete_event":
                result = game.action_complete_event(
                    player, action["event_index"], action["card_indices"]
                )
                if result["success"]:
                    self._narrate_event_completion(player, result, game, personas)
                    _resolve_reward_narrated(self, game, player, result["event"].reward)

            elif action_type == "recruit_lineup":
                slot = action["slot"]
                result = game.action_recruit_lineup(player, slot)
                if result["success"]:
                    self._narrate_draft_result(player, result, game, personas)

            elif action_type == "scramble":
                result = game.action_scramble(player)
                if result["success"]:
                    self._narrate_scramble(player, result, game, personas)

            elif action_type == "wipe_jumbotron":
                result = game.action_wipe_jumbotron(player,
                                                    target_indices=action.get("target_indices"))
                if result["success"]:
                    self._narrate_wipe(player, result, game, personas)

                    # Post-wipe event completion attempt
                    post_wipe_cost = game.rules.get("wipe_jumbotron", {}).get("post_wipe_event_cost", 0)
                    completable = find_completable_events(player.hand, game.jumbotron)
                    if completable and player.shinies >= post_wipe_cost:
                        completable.sort(key=lambda x: -x[0].vp)
                        event, cards = completable[0]
                        event_idx = game.jumbotron.index(event)
                        card_indices = [player.hand.index(c) for c in cards]

                        cost_note = f" I'll pay the {post_wipe_cost}S surcharge — worth it for {event.vp}VP." if post_wipe_cost else ""
                        self._thinking(
                            f"**Post-Wipe Scan:** The new Jumbotron has something!\n"
                            f"I can complete **{event.name}** ({event.vp}VP) with: "
                            f"{', '.join(str(c) for c in cards)}.{cost_note}"
                        )

                        ev_result = game.action_complete_event(player, event_idx, card_indices)
                        if ev_result["success"]:
                            self._narrate_event_completion(player, ev_result, game, personas)
                            _resolve_reward_narrated(self, game, player, ev_result["event"].reward)
                        else:
                            self._p(f"  ❌ Couldn't complete: {ev_result.get('error')}")
                    elif completable:
                        ev = completable[0][0]
                        self._thinking(
                            f"**Post-Wipe Scan:** I could complete **{ev.name}** ({ev.vp}VP), "
                            f"but I can't afford the {post_wipe_cost}S surcharge (only have {player.shinies}S). "
                            f"Frustrating — I'll need to come back for it."
                        )
                    else:
                        self._thinking(
                            f"**Post-Wipe Scan:** Nothing I can complete immediately. "
                            f"Let me see what's here now:\n"
                            + "\n".join(
                                f"  - **{ev.name}** ({ev.vp}VP): {ev.raw_requirements}"
                                for ev in game.jumbotron
                            )
                            + "\n\nSome of these look reachable in a turn or two."
                        )

            elif action_type == "timeout":
                result = game.action_timeout(
                    player,
                    discard_indices=action.get("discard_indices"),
                    flush_jumbotron=action.get("flush_jumbotron", False)
                )
                if result["success"]:
                    self._narrate_timeout(player, result, action, game, personas)

            # Fallback
            if not result.get("success"):
                result = game.action_timeout(player)
                self._thinking("Nothing worked as planned — taking a Timeout to regroup.")
                self._p(f"  ⏸️ **Timeout** (fallback). Gained 1 Shiny.")

            # End of turn
            eot = game.end_of_turn(player)
            if eot.get("discards"):
                discarded_cards = ", ".join(str(c) for c in eot["discards"])
                self._p(f"  📋 Hand limit reached — discarded: {discarded_cards}")
            if eot.get("playbook_scored"):
                pb = eot["playbook_scored"]
                self._p(f"\n  🏆 **PLAYBOOK SCORED: {pb.name}** (+{pb.vp}VP)!")
                self._p(f"  *Trigger: \"{pb.trigger}\"*")

            # Standing Ovation check
            if game.standing_ovation_triggered and game.standing_ovation_trigger_player == player.id:
                self._p(f"\n  🎆 **STANDING OVATION!** {name} has reached "
                        f"{player.event_vp} Event VP! "
                        f"All other players get one final turn.")

            self._show_score_line(game, personas)

            game.advance_turn()
            turn_count += 1

            if game.check_game_over():
                game.game_over = True

        # ── Final Results ──
        self._hr()
        self._h2("Final Results")

        if turn_count >= self.max_turns:
            self._p(f"⚠️ Game aborted after {self.max_turns} turns (max reached).")

        winner, standings = game.get_winner()

        self._p(f"**Game ended after {turn_count} turns ({game.turn_number + 1} rounds).**\n")

        # Standings table
        self._line("| Place | Player | Event VP | Playbook VP | Shiny Bonus | **Total VP** | Events |")
        self._line("|-------|--------|----------|-------------|-------------|--------------|--------|")
        for i, s in enumerate(standings):
            pid = s["player"]
            medal = ["🥇", "🥈", "🥉"][i] if i < 3 else f"#{i+1}"
            self._line(f"| {medal} | {personas[pid]} (P{pid}) | {s['event_vp']} | "
                       f"{s['playbook_vp']} | {s['shiny_bonus']} | **{s['total_vp']}** | "
                       f"{len(game.players[pid].scored_events)} |")

        self._line("")

        # Events completed summary
        self._h3("Events Completed")
        for p in game.players:
            pname = personas[p.id]
            if p.scored_events:
                ev_list = ", ".join(f"{e.name} ({e.vp}VP)" for e in p.scored_events)
                self._p(f"**{pname}:** {ev_list}")
            else:
                self._p(f"**{pname}:** None")

        # Playbooks scored
        if any(p.scored_playbooks for p in game.players):
            self._h3("Playbooks Scored")
            for p in game.players:
                pname = personas[p.id]
                if p.scored_playbooks:
                    pb_list = ", ".join(f"{pb.name} ({pb.vp}VP)" for pb in p.scored_playbooks)
                    self._p(f"**{pname}:** {pb_list}")

        return "\n".join(self.lines)

    # ── Narration: Setup ─────────────────────────────────────────────

    def _narrate_starting_hand(self, player, dealt, kept, discarded, ai, game, personas):
        name = personas[player.id]
        self._h4(f"{name} (P{player.id}) — Starting Hand Draft")
        self._p(f"Dealt 5 cards: {', '.join(str(c) for c in dealt)}\n")

        # Build detailed evaluation
        lines = ["**Evaluating each card against the Jumbotron:**\n"]
        for c in dealt:
            val = ai._card_value(c, game)
            reasons = []
            if c.is_free_agent:
                reasons.append("Free Agent — fits any faction with a Buddy")
            if 3 <= c.rank <= 7:
                reasons.append("mid-rank, versatile for sum requirements")
            elif c.rank >= 8:
                reasons.append("high-rank, good for sum requirements")
            elif c.rank <= 2 and not c.is_free_agent:
                reasons.append("low-rank, useful for Limbo-type events")

            # Check Jumbotron relevance
            jumbotron_hits = []
            for ev in game.jumbotron:
                if "factions" in ev.requirements and c.faction in ev.requirements["factions"]:
                    jumbotron_hits.append(ev.name)
            if jumbotron_hits:
                reasons.append(f"matches Jumbotron: {', '.join(jumbotron_hits)}")

            fa_star = " ⭐" if c.is_free_agent else ""
            reason_str = "; ".join(reasons) if reasons else "limited synergy with current board"
            lines.append(f"| **{c}**{fa_star} | Score: **{val:.1f}** | {reason_str} |")

        self._thinking("\n".join(lines))

        kept_total = sum(ai._card_value(c, game) for c in kept)
        disc_total = sum(ai._card_value(c, game) for c in discarded)
        self._thinking(
            f"**Decision:** Keep the top 3 by score (combined value: {kept_total:.1f}) "
            f"over the bottom 2 ({disc_total:.1f})."
        )
        self._p(f"**Keeps:** {', '.join(str(c) for c in kept)}")
        self._p(f"**Discards:** {', '.join(str(c) for c in discarded)}")

    def _narrate_playbook_choice(self, player, options, keep, discard, ai, game, personas):
        name = personas[player.id]
        self._p(f"\n**{name}'s Playbook Draft:**\n")

        lines = ["**Evaluating playbook options:**\n"]
        for pb in options:
            score = pb.vp
            trigger = pb.trigger.lower()
            adjustments = []
            if "5th event" in trigger:
                score -= 3
                adjustments.append("-3 (very hard to reach 5th event)")
            if "slot 4" in trigger or "slot 3" in trigger:
                score += 1
                adjustments.append("+1 (achievable through normal drafting)")
            if "3 or fewer cards" in trigger:
                score += 1
                adjustments.append("+1 (Tier 1 events use 3 cards, very common)")
            if "exactly 0 shinies" in trigger:
                score -= 1
                adjustments.append("-1 (awkward — locks out spending flexibility)")
            if "4th event" in trigger:
                adjustments.append("(reachable if game goes well)")
            if "9 vp or more" in trigger:
                adjustments.append("(need Tier 4+ events)")
            if "rank 10" in trigger:
                adjustments.append("(need to draft a Rank 10)")
            if "8+ shinies" in trigger:
                adjustments.append("(requires hoarding)")
            if "leader has 4+" in trigger:
                adjustments.append("(situational — need to be behind)")
            if "single faction" in trigger:
                adjustments.append("(need faction-pure hand, no FA)")

            adj_str = " ".join(adjustments) if adjustments else "(base VP, no adjustments)"
            lines.append(
                f"| **{pb.name}** ({pb.vp}VP) | Adjusted score: **{score}** | "
                f"{adj_str} |"
            )
            lines.append(f"|   *Trigger:* \"{pb.trigger}\" ||")

        self._thinking("\n".join(lines))
        self._thinking(
            f"**Decision:** Keeping **{keep.name}** ({keep.vp}VP) — "
            f"higher adjusted score. Returning {discard.name}."
        )
        self._p(f"**Keeps:** {keep.name} | **Returns:** {discard.name}")

    # ── Narration: Turn Decision ─────────────────────────────────────

    def _narrate_full_decision(self, player, ai, game, personas):
        """Show the complete decision tree with all options weighed."""
        name = personas[player.id]
        completable = find_completable_events(player.hand, game.jumbotron)

        # ── Option 1: Complete an event ──
        if completable:
            self._narrate_event_options(player, ai, game, completable, personas)
            return

        # No events completable — show full option analysis
        thoughts = ["**Situation Assessment:** No events completable right now.\n"]

        # Analyze each Jumbotron event — how close are we?
        thoughts.append("**Jumbotron Closeness Analysis:**")
        for ev in game.jumbotron:
            closeness_detail = self._analyze_closeness(player.hand, ev)
            thoughts.append(f"  - **{ev.name}** ({ev.vp}VP): {closeness_detail}")
        thoughts.append("")

        # ── Option A: Wipe Jumbotron ──
        wipe_config = game.rules.get("wipe_jumbotron", {})
        wipe_available = False
        if wipe_config.get("enabled"):
            cost = wipe_config["cost"]
            min_hand = wipe_config.get("min_hand_size", 0)
            can_afford = player.shinies >= cost
            has_hand = len(player.hand) >= min_hand if min_hand else True
            stuck_turns = ai.turns_without_completable

            thoughts.append(f"**Option: Wipe Jumbotron** (cost: {cost}S, need {min_hand}+ cards)")
            if can_afford and has_hand:
                if stuck_turns >= 3:
                    thoughts.append(
                        f"  ✅ CAN WIPE. Been stuck {stuck_turns} turns. "
                        f"Have {player.shinies}S and {len(player.hand)} cards. "
                        f"**This is my best move — resetting the board.**"
                    )
                    wipe_available = True
                else:
                    thoughts.append(
                        f"  ⏳ Could wipe (have {player.shinies}S, {len(player.hand)} cards) "
                        f"but only stuck {stuck_turns} turn(s). "
                        f"Threshold is 3 — still worth trying to draft toward an event."
                    )
            elif not can_afford and not has_hand:
                thoughts.append(
                    f"  ❌ Can't wipe: need {cost}S (have {player.shinies}S) "
                    f"AND {min_hand} cards (have {len(player.hand)})."
                )
            elif not can_afford:
                thoughts.append(
                    f"  ❌ Can't afford: need {cost}S, have {player.shinies}S. "
                    f"Short by {cost - player.shinies}S."
                )
            else:
                thoughts.append(
                    f"  ❌ Not enough cards: need {min_hand}, have {len(player.hand)}."
                )
            thoughts.append("")

        # If we're going to wipe, show that and stop
        if wipe_available and ai.turns_without_completable >= 3:
            self._thinking("\n".join(thoughts))
            return

        # ── Option B: Draft from Lineup ──
        thoughts.append("**Option: Draft from Lineup**")
        draft_evals = []
        for i, slot in enumerate(game.lineup):
            if slot.card is None:
                continue
            cost = game.rules["slot_pricing"][i]
            affordable = player.shinies >= cost

            card_val = ai._card_value(slot.card, game)
            shiny_val = slot.shinies * 1.5
            cost_penalty = cost * 2.0
            net_base = card_val + shiny_val - cost_penalty

            # Check if this card enables event completion
            enables_event = None
            event_bonus = 0
            if affordable:
                hypothetical = player.hand + [slot.card]
                can_complete = find_completable_events(hypothetical, game.jumbotron)
                if can_complete:
                    best = max(can_complete, key=lambda x: x[0].vp)
                    enables_event = best[0]
                    event_bonus = enables_event.vp * 2.0

            net_total = net_base + event_bonus

            # Build readable breakdown
            parts = [f"Card value: {card_val:.1f}"]
            if slot.shinies > 0:
                parts.append(f"Shinies bonus: +{shiny_val:.1f}")
            if cost > 0:
                parts.append(f"Cost penalty: -{cost_penalty:.1f}")
            if enables_event:
                parts.append(f"Enables **{enables_event.name}** ({enables_event.vp}VP): +{event_bonus:.1f}")

            status = "✅" if affordable else f"❌ need {cost}S"
            breakdown = ", ".join(parts)
            entry = (
                f"  Slot {i+1}: **{slot.card}** (+{slot.shinies}S on card, cost {cost}S) "
                f"[{status}]\n"
                f"    Breakdown: {breakdown}\n"
                f"    **Net score: {net_total:.1f}**"
            )
            thoughts.append(entry)
            draft_evals.append((net_total, i, slot, enables_event, affordable))

        thoughts.append("")

        # ── Option C: Scramble ──
        scramble_cost = game.rules["scramble_cost"][game.pkey]
        can_scramble = player.shinies >= scramble_cost
        lineup_value = sum(ai._card_value(s.card, game) for s in game.lineup if s.card)
        avg_lineup = lineup_value / max(len(game.lineup), 1)

        thoughts.append(f"**Option: Scramble** (cost: {scramble_cost}S)")
        if can_scramble:
            if avg_lineup < 2.0 and player.shinies >= scramble_cost + 2:
                thoughts.append(
                    f"  ⚠️ Lineup average value is low ({avg_lineup:.1f}). "
                    f"Scramble would clear Slot 1 and give a mystery draw. "
                    f"Considering it."
                )
            else:
                thoughts.append(
                    f"  Lineup average value: {avg_lineup:.1f}. "
                    f"Not bad enough to justify spending {scramble_cost}S + losing tempo."
                )
        else:
            thoughts.append(
                f"  ❌ Can't afford ({scramble_cost}S needed, have {player.shinies}S)."
            )
        thoughts.append("")

        # ── Option D: Timeout ──
        thoughts.append("**Option: Timeout** (+1 Shiny, discard up to 2, optional Jumbotron flush)")
        timeout_reasons = []
        if player.shinies < 2:
            timeout_reasons.append("low on Shinies — could use the income")
        if len(player.hand) >= 6:
            # Find worst cards
            card_scores = [(ai._card_value(c, game), c) for c in player.hand]
            card_scores.sort(key=lambda x: x[0])
            worst = card_scores[:2]
            worst_strs = [f"{c} (val {v:.1f})" for v, c in worst]
            timeout_reasons.append(f"hand is full ({len(player.hand)} cards) — could shed dead weight: {', '.join(worst_strs)}")
        if ai.turns_without_completable >= 2:
            timeout_reasons.append("could flush Jumbotron Slot 1 to cycle events")
        if not timeout_reasons:
            timeout_reasons.append("fallback if nothing else is appealing")
        thoughts.append("  " + "; ".join(timeout_reasons).capitalize())
        thoughts.append("")

        # ── Final Decision ──
        # Determine what the AI will actually do
        best_draft = None
        if draft_evals:
            affordable_drafts = [(s, i, sl, ev, af) for s, i, sl, ev, af in draft_evals if af]
            if affordable_drafts:
                best_draft = max(affordable_drafts, key=lambda x: x[0])

        thoughts.append("**DECISION:**")
        if wipe_available and ai.turns_without_completable >= 3:
            thoughts.append(f"  ➡️ **Wipe Jumbotron.** Stuck too long — time to reset.")
        elif best_draft and best_draft[0] > 2.0:
            slot_idx = best_draft[1]
            slot = best_draft[2]
            if best_draft[3]:
                thoughts.append(
                    f"  ➡️ **Draft from Slot {slot_idx+1}** ({slot.card}) — "
                    f"this enables completing {best_draft[3].name}! Score: {best_draft[0]:.1f}"
                )
            else:
                thoughts.append(
                    f"  ➡️ **Draft from Slot {slot_idx+1}** ({slot.card}) — "
                    f"best value at score {best_draft[0]:.1f}"
                )
        elif can_scramble and avg_lineup < 2.0 and player.shinies >= scramble_cost + 2:
            thoughts.append(f"  ➡️ **Scramble.** Lineup is weak, rolling the dice.")
        else:
            thoughts.append(f"  ➡️ **Timeout.** Building resources and cycling the board.")

        self._thinking("\n".join(thoughts))

    def _narrate_event_options(self, player, ai, game, completable, personas):
        """Show detailed analysis when events are completable."""
        completable_sorted = sorted(completable, key=lambda x: -x[0].vp)

        if len(completable_sorted) == 1:
            ev, cards = completable_sorted[0]
            card_str = ", ".join(str(c) for c in cards)
            self._thinking(
                f"**I can complete an event!**\n\n"
                f"**{ev.name}** (Tier {ev.tier}, {ev.vp}VP)\n"
                f"  Requirements: *{ev.raw_requirements}*\n"
                f"  My cards: {card_str}\n"
                f"  Reward: *{ev.reward}*\n\n"
                f"Only one option — taking it."
            )
        else:
            lines = [f"**Multiple events completable!** Evaluating {len(completable_sorted)} options:\n"]
            for i, (ev, cards) in enumerate(completable_sorted):
                card_str = ", ".join(str(c) for c in cards)
                cards_remaining = len(player.hand) - len(cards)
                lines.append(
                    f"  **Option {i+1}: {ev.name}** (Tier {ev.tier}, **{ev.vp}VP**)\n"
                    f"    Cards needed: {card_str} ({len(cards)} cards)\n"
                    f"    Cards remaining after: {cards_remaining}\n"
                    f"    Reward: *{ev.reward}*"
                )

            best_ev = completable_sorted[0][0]
            lines.append(
                f"\n**Decision:** Completing **{best_ev.name}** — highest VP at {best_ev.vp}."
            )

            # Check if there's a strategic reason to pick a lower-VP event
            if len(completable_sorted) > 1:
                second = completable_sorted[1]
                if len(second[1]) < len(completable_sorted[0][1]):
                    lines.append(
                        f"  (Note: {second[0].name} uses fewer cards ({len(second[1])} vs "
                        f"{len(completable_sorted[0][1])}), but the VP difference "
                        f"({best_ev.vp} vs {second[0].vp}) makes the bigger event worth it.)"
                    )

            self._thinking("\n".join(lines))

        # Check playbook synergy
        if player.playbooks:
            for pb in player.playbooks:
                trigger = pb.trigger.lower()
                ev, cards = completable_sorted[0]
                synergy = None
                if "3 or fewer cards" in trigger and len(cards) <= 3:
                    synergy = f"completing with {len(cards)} cards triggers **{pb.name}** ({pb.vp}VP)!"
                elif "rank 10" in trigger and any(c.rank == 10 for c in cards):
                    synergy = f"using a Rank 10 triggers **{pb.name}** ({pb.vp}VP)!"
                elif "9 vp or more" in trigger and ev.vp >= 9:
                    synergy = f"this {ev.vp}VP event triggers **{pb.name}** ({pb.vp}VP)!"
                elif "exactly 4 cards" in trigger and len(cards) == 4:
                    synergy = f"using exactly 4 cards triggers **{pb.name}** ({pb.vp}VP)!"
                elif "4th event" in trigger and len(player.scored_events) == 3:
                    synergy = f"this is my 4th event — triggers **{pb.name}** ({pb.vp}VP)!"
                elif "single faction" in trigger and len(set(c.faction for c in cards)) == 1 and not any(c.is_free_agent for c in cards):
                    synergy = f"all same faction, no FAs — triggers **{pb.name}** ({pb.vp}VP)!"
                if synergy:
                    self._thinking(f"**Playbook Alert:** {synergy}")

    # ── Narration: Actions ───────────────────────────────────────────

    def _narrate_event_completion(self, player, result, game, personas):
        ev = result["event"]
        cards = result["cards_used"]
        surcharge = result.get("post_wipe_cost", 0)
        self._p(f"\n  🎯 **EVENT COMPLETE: {ev.name}** (+{ev.vp}VP)")
        self._p(f"  Cards committed: {', '.join(str(c) for c in cards)}")
        if surcharge:
            self._p(f"  Paid {surcharge}S post-wipe surcharge.")
        if ev.reward and ev.reward.lower() != "none.":
            self._p(f"  Reward: *{ev.reward}*")
        self._p(f"  {personas[player.id]} now at **{player.event_vp} Event VP** "
                f"({len(player.scored_events)} events completed)")

    def _narrate_draft_result(self, player, result, game, personas):
        card = result["card"]
        slot = result["slot"]
        cost = result["cost"]
        collected = result["collected_shinies"]
        self._p(f"\n  📥 **DRAFTED: {card}** from Slot {slot+1}")
        if cost > 0 or collected > 0:
            parts = []
            if cost > 0:
                parts.append(f"paid {cost}S")
            if collected > 0:
                parts.append(f"collected {collected}S from card")
            self._p(f"  {', '.join(parts).capitalize()}. "
                    f"Shinies: {player.shinies}S. Hand size: {len(player.hand)}")
        else:
            self._p(f"  Free pickup. Hand size: {len(player.hand)}")

    def _narrate_scramble(self, player, result, game, personas):
        self._p(f"\n  🔀 **SCRAMBLE!**")
        self._p(f"  Discarded {result['discarded']} from Slot 1.")
        self._p(f"  Drew mystery card: **{result['mystery_card']}**")
        self._p(f"  Shinies: {player.shinies}S. Hand size: {len(player.hand)}")

    def _narrate_wipe(self, player, result, game, personas):
        name = personas[player.id]
        cost = result["cost"]
        self._p(f"\n  💥 **JUMBOTRON WIPE!** {name} pays {cost}S to clear the entire board!")
        self._p(f"  Removed:")
        for ev in result["wiped_events"]:
            self._p(f"    ~~{ev.name} ({ev.vp}VP)~~")
        self._p(f"  New Jumbotron:")
        for ev in result["new_events"]:
            self._p(f"    **{ev.name}** (Tier {ev.tier}, {ev.vp}VP) — *{ev.raw_requirements}*")
        self._p(f"  Shinies remaining: {player.shinies}S")

    def _narrate_timeout(self, player, result, action, game, personas):
        self._p(f"\n  ⏸️ **TIMEOUT.** +1 Shiny (now {player.shinies}S).")
        if result.get("discarded"):
            for c in result["discarded"]:
                self._p(f"    Discarded: {c}")
        if result.get("flushed_event"):
            self._p(f"    Flushed from Jumbotron Slot 1: *{result['flushed_event']}*")
            if game.jumbotron:
                new_ev = game.jumbotron[-1]
                self._p(f"    New event in Slot 4: **{new_ev.name}** "
                        f"({new_ev.vp}VP) — *{new_ev.raw_requirements}*")

    # ── Analysis Helpers ─────────────────────────────────────────────

    def _analyze_closeness(self, hand: List[RecruitCard], event: EventCard) -> str:
        """Return a human-readable closeness description for an event."""
        req = event.requirements
        parts = []

        if "factions" in req:
            for faction, needed in req["factions"].items():
                signed = sum(1 for c in hand if c.faction == faction and not c.is_free_agent)
                fas = sum(1 for c in hand if c.is_free_agent)
                # FAs only count if we have a signed buddy
                usable_fas = min(fas, needed - signed) if signed > 0 else 0
                total = signed + usable_fas
                parts.append(f"{faction}: {total}/{needed}")
                if total < needed:
                    gap = needed - total
                    parts[-1] += f" (need {gap} more)"
                else:
                    parts[-1] += " ✓"

        if "free_agent_count" in req:
            fas = sum(1 for c in hand if c.is_free_agent)
            needed = req["free_agent_count"]
            parts.append(f"Free Agents: {fas}/{needed}" + (" ✓" if fas >= needed else f" (need {needed - fas} more)"))

        if "sum_min" in req:
            relevant = hand  # simplified
            current_sum = sum(c.rank for c in relevant[:req.get("card_count", len(relevant))])
            parts.append(f"Sum: {current_sum} (need ≥{req['sum_min']})")

        if "run_length" in req:
            ranks = sorted(set(c.rank for c in hand))
            max_run = 1
            current = 1
            for j in range(1, len(ranks)):
                if ranks[j] == ranks[j-1] + 1:
                    current += 1
                    max_run = max(max_run, current)
                else:
                    current = 1
            needed = req["run_length"]
            parts.append(f"Run: {max_run}/{needed}")

        if "same_number" in req:
            rank_counts = Counter(c.rank for c in hand)
            best = max(rank_counts.values()) if rank_counts else 0
            needed = req["same_number"]
            parts.append(f"Same-number: {best}/{needed}")

        if "card_count" in req and "sum_max" in req:
            # Limbo-type: need N cards with low sum
            n = req["card_count"]
            max_sum = req["sum_max"]
            low_cards = sorted(hand, key=lambda c: c.rank)[:n]
            actual_sum = sum(c.rank for c in low_cards)
            parts.append(f"Low-sum ({n} cards ≤{max_sum}): best sum={actual_sum}")

        if not parts:
            parts.append(f"*{event.raw_requirements}*")

        return " | ".join(parts)

    # ── Board Display ────────────────────────────────────────────────

    def _show_board(self, game):
        self._p("**Lineup:**\n")
        self._line("| Slot | Card | Shinies | Cost |")
        self._line("|------|------|---------|------|")
        for i, slot in enumerate(game.lineup):
            cost = game.rules["slot_pricing"][i]
            fa = " ⭐" if slot.card and slot.card.is_free_agent else ""
            self._line(f"| {i+1} | {slot.card}{fa} | {slot.shinies}S | {cost}S |")

        self._p("\n**Jumbotron:**\n")
        self._line("| Slot | Event | Tier | VP | Requirements |")
        self._line("|------|-------|------|----|-------------|")
        for i, ev in enumerate(game.jumbotron):
            self._line(f"| {i+1} | {ev.name} | {ev.tier} | {ev.vp} | {ev.raw_requirements} |")

    def _show_board_compact(self, game):
        """Compact board state at start of each round."""
        lineup_str = " | ".join(
            f"[{i+1}] {s.card}" + (f" +{s.shinies}S" if s.shinies else "")
            for i, s in enumerate(game.lineup) if s.card
        )
        jumbotron_str = " | ".join(
            f"[{i+1}] {ev.name} ({ev.vp}VP)"
            for i, ev in enumerate(game.jumbotron)
        )
        self._p(f"**Lineup:** {lineup_str}")
        self._p(f"**Jumbotron:** {jumbotron_str}\n")

    def _show_player_status(self, player, game, personas):
        name = personas[player.id]
        hand_str = ", ".join(str(c) for c in player.hand)
        pb_str = ""
        if player.playbooks:
            pb_names = ", ".join(f"{pb.name} ({pb.vp}VP)" for pb in player.playbooks)
            pb_str = f" | Playbooks: {pb_names}"

        self._p(f"  **{name}:** {player.event_vp}eVP + {player.playbook_vp}pbVP "
                f"+ {player.shiny_bonus}sVP = **{player.total_vp}VP** | "
                f"Shinies: {player.shinies} | Hand ({len(player.hand)}): {hand_str}{pb_str}")

    def _show_score_line(self, game, personas):
        parts = []
        for p in game.players:
            parts.append(f"{personas[p.id]}: {p.total_vp}VP ({len(p.scored_events)}ev)")
        self._p(f"\n  📊 *Score: {' | '.join(parts)}*")

    # ── Markdown Helpers ─────────────────────────────────────────────

    def _h1(self, text):
        self.lines.append(f"# {text}\n")

    def _h2(self, text):
        self.lines.append(f"\n## {text}\n")

    def _h3(self, text):
        self.lines.append(f"\n### {text}\n")

    def _h4(self, text):
        self.lines.append(f"\n#### {text}\n")

    def _p(self, text):
        self.lines.append(text)

    def _line(self, text):
        self.lines.append(text)

    def _hr(self):
        self.lines.append("\n---\n")

    def _thinking(self, text):
        """Render AI thinking as a blockquote block."""
        self.lines.append("")
        for line in text.split("\n"):
            self.lines.append(f"> 🧠 {line}")
        self.lines.append("")

    def _build_personas(self):
        names = ["Coach Red", "Coach Blue", "Coach Green", "Coach Gold"]
        return names[:self.num_players]


def _resolve_reward_narrated(narrator, game, player, reward_text):
    """Resolve reward and narrate it."""
    reward = reward_text.lower()

    if "shini" in reward:
        match = re.search(r'(\d+)\s*shini', reward)
        if match:
            amount = int(match.group(1))
            if "from the bank" in reward or "take" in reward:
                game.resolve_reward_shinies(player, amount)
                narrator._p(f"  💰 Reward: +{amount} Shinies (now {player.shinies}S)")

    if "free scramble" in reward or "perform one free scramble" in reward:
        game.resolve_reward_scramble(player)
        narrator._p(f"  🔀 Reward: Free Scramble! Drew a mystery card. Hand: {len(player.hand)}")

    if "draw" in reward and "recruit" in reward:
        draw_match = re.search(r'draw\s*(?:top\s*)?(\d+)', reward)
        keep_match = re.search(r'keep\s*(\d+)', reward)
        if draw_match and keep_match:
            d, k = int(draw_match.group(1)), int(keep_match.group(1))
            game.resolve_reward_draw(player, d, k)
            narrator._p(f"  🃏 Reward: Drew {d}, kept {k}. Hand: {len(player.hand)}")

    if "draft lineup slot 2" in reward:
        if len(game.lineup) > 1 and game.lineup[1].card:
            narrator._p(f"  📥 Reward: Free draft from Slot 2: **{game.lineup[1].card}**")
        game.resolve_reward_free_lineup_draft(player, 1)

    if "look" in reward and "stands" in reward:
        if game.stands.size > 0:
            card = game.stands.cards[0]
            game.stands.cards.pop(0)
            player.hand.append(card)
            narrator._p(f"  🔍 Reward: Searched The Stands, took **{card}**")


# ── CLI ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Narrate a Contests of Chaos game session")
    parser.add_argument("-s", "--seed", type=int, default=42,
                        help="Random seed (default: 42)")
    parser.add_argument("-p", "--players", type=int, default=3,
                        help="Number of players (2-4, default: 3)")
    parser.add_argument("-o", "--output", type=str, default=None,
                        help="Output MD file path (default: stdout)")
    parser.add_argument("--max-turns", type=int, default=200,
                        help="Max turns (default: 200)")
    parser.add_argument("--config", type=str, default=None,
                        help="Path to config.json")
    parser.add_argument("--events", type=str, default=None,
                        help="Path to events CSV")
    parser.add_argument("--playbooks", type=str, default=None,
                        help="Path to playbooks CSV")
    parser.add_argument("--wipe-cost", type=int, default=None,
                        help="Override wipe cost")
    parser.add_argument("--no-playbooks", action="store_true",
                        help="Disable playbooks")
    parser.add_argument("--skill", type=str, default=None,
                        help="Skill levels per player, comma-separated (e.g. '1.0,0.5,0.3')")
    parser.add_argument("--styles", type=str, default=None,
                        help="Play styles per player, comma-separated (e.g. 'rush,economy,control')")
    parser.add_argument("--preset", type=str, default=None,
                        choices=["experts", "beginners", "mixed", "styles"],
                        help="Quick preset: experts, beginners, mixed, styles")

    args = parser.parse_args()

    sim_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(sim_dir)

    config_path = args.config or os.path.join(sim_dir, "config.json")
    with open(config_path, 'r') as f:
        config = json.load(f)

    if args.wipe_cost is not None:
        config["game_rules"]["wipe_jumbotron"]["cost"] = args.wipe_cost

    events_path = args.events
    if not events_path:
        for c in [os.path.join(parent_dir, "contests-of-chaos-events copy.csv"),
                  os.path.join(parent_dir, "contests-of-chaos-events.csv")]:
            if os.path.exists(c):
                events_path = c
                break

    playbooks_path = args.playbooks
    if not playbooks_path and not args.no_playbooks:
        for c in [os.path.join(parent_dir, "contests-of-chaos-playbooks copy.csv"),
                  os.path.join(parent_dir, "contests-of-chaos-playbooks.csv")]:
            if os.path.exists(c):
                playbooks_path = c
                break

    events = load_events_csv(events_path) if events_path else []
    playbooks = load_playbooks_csv(playbooks_path) if playbooks_path and not args.no_playbooks else []

    # Build player configs
    player_configs = None
    np = args.players

    if args.preset:
        if args.preset == "experts":
            player_configs = [{"skill": 1.0, "style": "balanced"} for _ in range(np)]
        elif args.preset == "beginners":
            player_configs = [{"skill": 0.3, "style": "balanced"} for _ in range(np)]
        elif args.preset == "mixed":
            player_configs = [{"skill": 1.0, "style": "balanced"}]
            player_configs += [{"skill": 0.3, "style": "balanced"} for _ in range(np - 1)]
        elif args.preset == "styles":
            style_cycle = ["rush", "economy", "control", "balanced"]
            player_configs = [{"skill": 1.0, "style": style_cycle[i % 4]} for i in range(np)]

    if args.skill or args.styles:
        if player_configs is None:
            player_configs = [{} for _ in range(np)]
        if args.skill:
            skills = [float(s) for s in args.skill.split(",")]
            for i in range(min(len(skills), np)):
                player_configs[i]["skill"] = skills[i]
        if args.styles:
            styles = [s.strip() for s in args.styles.split(",")]
            for i in range(min(len(styles), np)):
                player_configs[i]["style"] = styles[i]

    print(f"Generating narrated game (seed={args.seed}, {args.players}p)...", file=sys.stderr)

    narrator = NarratedGame(config, events, playbooks, args.players,
                            seed=args.seed, max_turns=args.max_turns,
                            player_configs=player_configs)
    md_text = narrator.run()

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(md_text)
        print(f"Saved to: {args.output}", file=sys.stderr)
    else:
        print(md_text)


if __name__ == "__main__":
    main()
