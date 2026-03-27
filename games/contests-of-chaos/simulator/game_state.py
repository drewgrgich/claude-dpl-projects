"""Core game state and action execution for Contests of Chaos."""

import json
import random
from dataclasses import dataclass, field
from typing import List, Optional, Tuple, Dict
from cards import RecruitCard, EventCard, PlaybookCard, Deck, build_recruit_deck
from event_checker import check_event_requirements, find_completable_events, find_best_card_combo


@dataclass
class Player:
    """Tracks a single player's state."""
    id: int
    hand: List[RecruitCard] = field(default_factory=list)
    shinies: int = 0
    scored_events: List[EventCard] = field(default_factory=list)
    event_vp: int = 0
    playbooks: List[PlaybookCard] = field(default_factory=list)
    scored_playbooks: List[PlaybookCard] = field(default_factory=list)
    playbook_vp: int = 0

    @property
    def total_vp(self) -> int:
        shiny_bonus = min(self.shinies // 3, 3)
        return self.event_vp + self.playbook_vp + shiny_bonus

    @property
    def shiny_bonus(self) -> int:
        return min(self.shinies // 3, 3)

    def __repr__(self):
        return (f"P{self.id}(VP:{self.event_vp}e+{self.playbook_vp}pb+{self.shiny_bonus}s"
                f"={self.total_vp} | Hand:{len(self.hand)} | S:{self.shinies})")


@dataclass
class LineupSlot:
    """A single slot in the Lineup with a card and accumulated Shinies."""
    card: Optional[RecruitCard] = None
    shinies: int = 0


class GameState:
    """Full game state for Contests of Chaos."""

    def __init__(self, config: dict, num_players: int, seed: int = None,
                 events: List[EventCard] = None, playbooks: List[PlaybookCard] = None,
                 use_playbooks: bool = True):
        self.config = config
        self.rules = config["game_rules"]
        self.num_players = num_players
        self.use_playbooks = use_playbooks
        self.rng = random.Random(seed)
        self.seed = seed

        # Player key for config lookups
        self.pkey = f"{num_players}_player"

        # Build decks
        recruit_cards = build_recruit_deck(config)
        self.recruit_deck = Deck(recruit_cards)
        self.recruit_deck.shuffle(self.rng)

        self.event_deck = Deck(list(events)) if events else Deck()
        self.event_deck.shuffle(self.rng)

        self.playbook_deck = Deck(list(playbooks)) if playbooks else Deck()
        if self.use_playbooks:
            self.playbook_deck.shuffle(self.rng)

        # Board
        self.lineup: List[LineupSlot] = []
        self.jumbotron: List[EventCard] = []
        self.stands = Deck()  # discard pile

        # Players
        self.players: List[Player] = []
        self.current_player_idx: int = 0
        self.turn_number: int = 0

        # Game state flags
        self.standing_ovation_triggered: bool = False
        self.standing_ovation_trigger_player: int = -1
        self.game_over: bool = False

        # Turn state tracking
        self.wiped_this_turn: bool = False
        self.turn_context: dict = {}  # Tracks what happened this turn for playbook scoring

        # Logging
        self.log: List[str] = []
        self.turn_log: List[dict] = []

    def setup(self):
        """Run full game setup."""
        # Deal Lineup
        for _ in range(self.rules["lineup_size"]):
            card = self.recruit_deck.draw_one()
            self.lineup.append(LineupSlot(card=card, shinies=0))

        # Deal Jumbotron
        for _ in range(self.rules["jumbotron_size"]):
            card = self.event_deck.draw_one()
            if card:
                self.jumbotron.append(card)

        # Create players and deal starting hands
        starting_shinies = self.rules["starting_shinies"][self.pkey]
        for i in range(self.num_players):
            player = Player(id=i, shinies=starting_shinies[i])
            # Deal 5, keep 3
            dealt = self.recruit_deck.draw(self.rules["starting_deal"])
            # AI will choose which to keep - for now, keep first 3 (AI overrides this)
            player.hand = dealt[:self.rules["starting_keep"]]
            discards = dealt[self.rules["starting_keep"]:]
            for c in discards:
                self.stands.add_to_bottom(c)
            self.players.append(player)

        # Deal playbooks
        if self.use_playbooks and self.playbook_deck.size >= self.num_players * 2:
            for player in self.players:
                dealt = self.playbook_deck.draw(2)
                # Keep first, discard second (AI overrides this)
                player.playbooks = [dealt[0]]
                self.playbook_deck.add_to_bottom(dealt[1])

        self._log(f"Game setup complete. {self.num_players} players, seed={self.seed}")

    def setup_with_choices(self, keep_fn=None, playbook_fn=None):
        """Setup with AI-driven draft and playbook choices."""
        # Deal Lineup
        for _ in range(self.rules["lineup_size"]):
            card = self.recruit_deck.draw_one()
            self.lineup.append(LineupSlot(card=card, shinies=0))

        # Deal Jumbotron
        for _ in range(self.rules["jumbotron_size"]):
            card = self.event_deck.draw_one()
            if card:
                self.jumbotron.append(card)

        # Create players
        starting_shinies = self.rules["starting_shinies"][self.pkey]
        for i in range(self.num_players):
            player = Player(id=i, shinies=starting_shinies[i])
            dealt = self.recruit_deck.draw(self.rules["starting_deal"])

            if keep_fn:
                kept, discarded = keep_fn(player, dealt, self)
            else:
                kept = dealt[:self.rules["starting_keep"]]
                discarded = dealt[self.rules["starting_keep"]:]

            player.hand = list(kept)
            for c in discarded:
                self.stands.add_to_bottom(c)
            self.players.append(player)

        # Deal playbooks with choices
        if self.use_playbooks and self.playbook_deck.size >= self.num_players * 2:
            for player in self.players:
                dealt = self.playbook_deck.draw(2)
                if playbook_fn:
                    keep, discard = playbook_fn(player, dealt, self)
                else:
                    keep, discard = dealt[0], dealt[1]
                player.playbooks = [keep]
                self.playbook_deck.add_to_bottom(discard)

        self._log(f"Game setup complete. {self.num_players} players, seed={self.seed}")

    # ── Actions ──────────────────────────────────────────────────────────

    def action_recruit_lineup(self, player: Player, slot_index: int) -> dict:
        """Draft a card from the Lineup at the given slot (0-indexed).

        Returns dict with action result details.
        """
        if slot_index < 0 or slot_index >= len(self.lineup):
            return {"success": False, "error": "Invalid slot index"}

        slot = self.lineup[slot_index]
        if slot.card is None:
            return {"success": False, "error": "Empty slot"}

        # Calculate cost
        cost = self.rules["slot_pricing"][slot_index]
        if player.shinies < cost:
            return {"success": False, "error": f"Need {cost} Shinies, have {player.shinies}"}

        # Pay cost: place 1 Shiny on each card to the left
        for i in range(slot_index):
            if self.lineup[i].card is not None:
                self.lineup[i].shinies += 1
        player.shinies -= cost

        # Collect Shinies from the drafted card
        collected = slot.shinies
        player.shinies += collected

        # Take the card
        drafted_card = slot.card
        player.hand.append(drafted_card)

        # Slide lineup left and refill
        self.lineup.pop(slot_index)
        new_card = self.recruit_deck.draw_one()
        if new_card is None:
            self._reshuffle_stands()
            new_card = self.recruit_deck.draw_one()
        self.lineup.append(LineupSlot(card=new_card, shinies=0))

        # Record turn context for playbook scoring
        self.turn_context["drafted_slot"] = slot_index
        self.turn_context["drafted_card"] = drafted_card
        self.turn_context["drafted_shinies_on_card"] = collected

        result = {
            "success": True,
            "action": "recruit_lineup",
            "card": drafted_card,
            "slot": slot_index,
            "cost": cost,
            "collected_shinies": collected,
        }
        self._log(f"P{player.id} drafted {drafted_card} from Slot {slot_index+1}, "
                  f"paid {cost}S, collected {collected}S")
        return result

    def action_scramble(self, player: Player) -> dict:
        """Perform a Scramble action."""
        cost = self.rules["scramble_cost"][self.pkey]
        if player.shinies < cost:
            return {"success": False, "error": f"Need {cost} Shinies for Scramble"}

        # Discard Slot 1 (index 0)
        discarded = self.lineup[0]
        if discarded.card:
            self.stands.add_to_bottom(discarded.card)
        slot1_shinies = discarded.shinies

        # Slide left
        self.lineup.pop(0)

        # Deal new card to Slot 4
        new_card = self.recruit_deck.draw_one()
        if new_card is None:
            self._reshuffle_stands()
            new_card = self.recruit_deck.draw_one()

        # Shinies from payment + Slot 1's Shinies go onto new Slot 4
        new_slot_shinies = cost + slot1_shinies
        self.lineup.append(LineupSlot(card=new_card, shinies=new_slot_shinies))

        player.shinies -= cost

        # Draw mystery card
        mystery = self.recruit_deck.draw_one()
        if mystery is None:
            self._reshuffle_stands()
            mystery = self.recruit_deck.draw_one()
        if mystery:
            player.hand.append(mystery)

        result = {
            "success": True,
            "action": "scramble",
            "discarded": discarded.card,
            "mystery_card": mystery,
            "cost": cost,
        }
        self._log(f"P{player.id} Scrambled. Discarded {discarded.card}, drew mystery {mystery}")
        return result

    def action_timeout(self, player: Player, discard_indices: List[int] = None,
                       flush_jumbotron: bool = False) -> dict:
        """Perform a Timeout action."""
        # Gain 1 Shiny
        player.shinies += self.rules["timeout_shiny_gain"]

        # Optional: discard up to 2 cards
        discarded = []
        if discard_indices:
            # Sort descending to avoid index shifting
            for idx in sorted(discard_indices, reverse=True):
                if 0 <= idx < len(player.hand):
                    card = player.hand.pop(idx)
                    self.stands.add_to_bottom(card)
                    discarded.append(card)

        # Optional: flush Jumbotron Slot 1
        flushed_event = None
        if flush_jumbotron and self.jumbotron:
            flushed_event = self.jumbotron.pop(0)
            self.turn_context["flushed_event_vp"] = flushed_event.vp
            self.event_deck.add_to_bottom(flushed_event)
            # Refill
            new_event = self.event_deck.draw_one()
            if new_event:
                self.jumbotron.append(new_event)

        # 2-player Coach's Toll
        if self.num_players == 2 and self.rules.get("coachs_toll", {}).get("enabled_2p"):
            toll = self.rules["coachs_toll"]["shiny_on_slot1"]
            if self.lineup:
                self.lineup[0].shinies += toll

        result = {
            "success": True,
            "action": "timeout",
            "shinies_gained": self.rules["timeout_shiny_gain"],
            "discarded": discarded,
            "flushed_event": flushed_event,
        }
        self._log(f"P{player.id} Timeout. +1S, discarded {len(discarded)} cards"
                  f"{', flushed ' + str(flushed_event) if flushed_event else ''}")
        return result

    def action_complete_event(self, player: Player, event_index: int,
                               card_indices: List[int]) -> dict:
        """Complete an event from the Jumbotron."""
        if event_index < 0 or event_index >= len(self.jumbotron):
            return {"success": False, "error": "Invalid event index"}

        event = self.jumbotron[event_index]
        cards = [player.hand[i] for i in card_indices]

        # Validate
        if not check_event_requirements(cards, event):
            return {"success": False, "error": f"Cards don't meet requirements for {event.name}"}

        # Post-wipe surcharge: if player wiped Jumbotron this turn, completing costs extra
        post_wipe_cost = 0
        if self.wiped_this_turn:
            wipe_config = self.rules.get("wipe_jumbotron", {})
            post_wipe_cost = wipe_config.get("post_wipe_event_cost", 0)
            if post_wipe_cost > 0 and player.shinies < post_wipe_cost:
                return {"success": False,
                        "error": f"Need {post_wipe_cost} Shinies to complete event after wipe"}
            if post_wipe_cost > 0:
                player.shinies -= post_wipe_cost
                self._log(f"P{player.id} paid {post_wipe_cost}S post-wipe surcharge")

        # Discard used cards to stands
        for idx in sorted(card_indices, reverse=True):
            card = player.hand.pop(idx)
            self.stands.add_to_bottom(card)

        # Score the event
        player.scored_events.append(event)
        player.event_vp += event.vp

        # Remove from Jumbotron and refill
        self.jumbotron.pop(event_index)
        new_event = self.event_deck.draw_one()
        if new_event:
            self.jumbotron.append(new_event)

        # Resolve reward (simplified - rewards are handled by AI/caller)
        result = {
            "success": True,
            "action": "complete_event",
            "event": event,
            "cards_used": cards,
            "vp_gained": event.vp,
            "reward": event.reward,
            "post_wipe_cost": post_wipe_cost,
        }
        # Record turn context for playbook scoring
        self.turn_context["completed_event"] = True
        self.turn_context["event_name"] = event.name
        self.turn_context["event_vp"] = event.vp
        self.turn_context["event_reward"] = event.reward
        self.turn_context["cards_used"] = cards
        self.turn_context["cards_used_count"] = len(cards)
        self.turn_context["cards_used_ranks"] = [c.rank for c in cards]
        self.turn_context["cards_used_factions"] = [c.faction for c in cards]
        self.turn_context["cards_used_free_agents"] = [c for c in cards if c.is_free_agent]
        self.turn_context["events_completed_total"] = len(player.scored_events)
        self.turn_context["hand_size_after_event"] = len(player.hand)
        self.turn_context["event_has_sum_req"] = any(
            k in event.requirements for k in ["sum_min", "sum_max", "sum_exact"]
        )

        self._log(f"P{player.id} completed {event.name} for {event.vp}VP "
                  f"using {cards}"
                  f"{f' (paid {post_wipe_cost}S surcharge)' if post_wipe_cost else ''}")

        # Check Standing Ovation
        threshold = self.rules["victory_threshold"][self.pkey]
        if player.event_vp >= threshold and not self.standing_ovation_triggered:
            self.standing_ovation_triggered = True
            self.standing_ovation_trigger_player = player.id
            self._log(f"*** STANDING OVATION triggered by P{player.id} "
                      f"at {player.event_vp} Event VP! ***")

        return result

    def action_agent(self, player: Player) -> dict:
        """Hire The Agent to get a new Playbook."""
        if not self.use_playbooks:
            return {"success": False, "error": "Playbooks not enabled"}

        cost = self.rules["agent_cost"]
        if player.shinies < cost:
            return {"success": False, "error": f"Need {cost} Shinies for The Agent"}

        if self.playbook_deck.size < self.rules["agent_draw"]:
            return {"success": False, "error": "Not enough Playbooks in deck"}

        player.shinies -= cost
        dealt = self.playbook_deck.draw(self.rules["agent_draw"])

        # Keep 1, return 1 (AI decides which)
        # For now keep first
        keep = dealt[0]
        discard = dealt[1]

        if len(player.playbooks) < self.rules["playbook_limit"]:
            player.playbooks.append(keep)
        else:
            # At limit - must discard one
            self.playbook_deck.add_to_bottom(keep)
            keep = None

        self.playbook_deck.add_to_bottom(discard)

        result = {
            "success": True,
            "action": "agent",
            "cost": cost,
            "kept": keep,
            "returned": discard,
        }
        self._log(f"P{player.id} hired The Agent for {cost}S, kept {keep}")
        return result

    def action_wipe_jumbotron(self, player: Player, target_indices: List[int] = None) -> dict:
        """Wipe some or all Jumbotron events.

        target_indices: list of Jumbotron slot indices to remove (0-based).
                        If None, wipe all (full wipe — legacy behavior).

        Cost is determined by wipe_jumbotron config:
          - If 'tiered_cost' is present: {1: cost1, 2: cost2, 4: cost4}
          - Otherwise: flat 'cost' for full wipe only
        """
        wipe_config = self.rules.get("wipe_jumbotron", {})
        if not wipe_config.get("enabled", False):
            return {"success": False, "error": "Jumbotron wipe not enabled"}

        # Determine how many to wipe and the cost
        tiered = wipe_config.get("tiered_cost", None)

        if target_indices is not None:
            num_targets = len(target_indices)
            # Validate indices
            valid_indices = [i for i in target_indices if 0 <= i < len(self.jumbotron)]
            if len(valid_indices) != num_targets:
                return {"success": False, "error": "Invalid Jumbotron slot index"}
            num_targets = len(valid_indices)
        else:
            # Full wipe
            num_targets = len(self.jumbotron)
            valid_indices = list(range(num_targets))

        if num_targets == 0:
            return {"success": False, "error": "No events to wipe"}

        # Calculate cost
        if tiered:
            # Look up cost by number of events targeted
            cost = tiered.get(str(num_targets), tiered.get(num_targets))
            if cost is None:
                # Find nearest valid tier
                valid_tiers = sorted(int(k) for k in tiered.keys())
                for t in valid_tiers:
                    if t >= num_targets:
                        cost = tiered.get(str(t), tiered.get(t))
                        break
                if cost is None:
                    cost = tiered.get(str(valid_tiers[-1]), tiered.get(valid_tiers[-1]))
        else:
            # Flat cost — only full wipe allowed
            if num_targets < len(self.jumbotron):
                return {"success": False, "error": "Targeted wipe not enabled (no tiered_cost in config)"}
            cost = wipe_config["cost"]

        if player.shinies < cost:
            return {"success": False, "error": f"Need {cost} Shinies to wipe {num_targets} event(s)"}

        # Hand size check (applies to all wipe types)
        min_hand = wipe_config.get("min_hand_size", 0)
        if min_hand > 0 and len(player.hand) < min_hand:
            return {"success": False, "error": f"Need {min_hand} cards in hand to wipe Jumbotron"}

        player.shinies -= cost

        # Remove targeted events (in reverse order to preserve indices)
        wiped = []
        for idx in sorted(valid_indices, reverse=True):
            event = self.jumbotron.pop(idx)
            self.event_deck.add_to_bottom(event)
            wiped.append(event)
        wiped.reverse()  # Restore original order

        # Refill Jumbotron to full size
        new_events = []
        while len(self.jumbotron) < self.rules["jumbotron_size"]:
            new_event = self.event_deck.draw_one()
            if new_event:
                self.jumbotron.append(new_event)
                new_events.append(new_event)
            else:
                break

        result = {
            "success": True,
            "action": "wipe_jumbotron",
            "cost": cost,
            "num_wiped": len(wiped),
            "wiped_events": wiped,
            "new_events": new_events,
            "full_wipe": num_targets == self.rules["jumbotron_size"],
        }
        self.wiped_this_turn = True
        self._log(f"P{player.id} WIPED {len(wiped)} Jumbotron event(s) for {cost}S! "
                  f"Removed: {wiped} → New: {new_events}")
        return result

    # ── End of Turn ──────────────────────────────────────────────────────

    def end_of_turn(self, player: Player) -> dict:
        """Handle end-of-turn checks: hand limit, playbook scoring, victory check."""
        results = {"discards": [], "playbook_scored": None, "game_triggered": False}

        # Hand limit
        limit = self.rules["hand_limit"]
        while len(player.hand) > limit:
            # Discard worst card (AI should handle this, but default to lowest rank non-FA)
            worst_idx = self._find_worst_card_index(player)
            card = player.hand.pop(worst_idx)
            self.stands.add_to_bottom(card)
            results["discards"].append(card)

        # Playbook check (simplified - AI handles scoring decisions)
        # For now, auto-score completed playbooks
        if self.use_playbooks and player.playbooks:
            for pb in list(player.playbooks):
                if self._check_playbook_condition(player, pb):
                    player.playbooks.remove(pb)
                    player.scored_playbooks.append(pb)
                    player.playbook_vp += pb.vp
                    results["playbook_scored"] = pb
                    self._log(f"P{player.id} scored Playbook: {pb.name} for {pb.vp}VP")
                    break  # Max 1 per turn

        # Victory check
        threshold = self.rules["victory_threshold"][self.pkey]
        if player.event_vp >= threshold and not self.standing_ovation_triggered:
            self.standing_ovation_triggered = True
            self.standing_ovation_trigger_player = player.id
            results["game_triggered"] = True

        return results

    def _check_playbook_condition(self, player: Player, playbook: PlaybookCard) -> bool:
        """Check if a playbook's trigger condition was met this turn.

        Uses self.turn_context to know what happened.
        """
        trigger = playbook.trigger.lower()
        ctx = self.turn_context
        did_event = ctx.get("completed_event", False)

        # ── Finish-type (end of turn state checks) ──

        # The Salary Cap: "End of turn: Have exactly 0 Shinies"
        if "exactly 0 shinies" in trigger:
            return player.shinies == 0

        # The Windfall: "End of turn: Have 8+ Shinies"
        if "8+ shinies" in trigger or "8 or more shinies" in trigger:
            return player.shinies >= 8

        # The Buzzer Beater: "Leader has 4+ completed Events and you are not the leader"
        if "leader has 4+" in trigger and "not the leader" in trigger:
            leader_events = max(len(p.scored_events) for p in self.players)
            my_events = len(player.scored_events)
            return leader_events >= 4 and my_events < leader_events

        # Leave It On The Field: "2 or fewer cards in hand and you completed an Event"
        if "2 or fewer cards" in trigger and "completed an event" in trigger:
            return did_event and len(player.hand) <= 2

        # ── Combo-type (checked when completing an event) ──

        if not did_event:
            # All remaining playbooks require an event completion this turn
            # Exception: draft-based and timeout-based ones handled below
            pass

        # The Rookie: "Complete an Event using only Ranks 1-5"
        if "only ranks 1-5" in trigger or "only rank" in trigger and "1-5" in trigger:
            if did_event:
                ranks = ctx.get("cards_used_ranks", [])
                return all(1 <= r <= 5 for r in ranks)

        # The Speed Run: "Complete an Event using 3 or fewer cards"
        if "3 or fewer cards" in trigger and "complete" in trigger:
            if did_event:
                return ctx.get("cards_used_count", 99) <= 3

        # The Perfect 10: "at least one Rank 10 card"
        if "rank 10" in trigger and "at least one" in trigger:
            if did_event:
                return 10 in ctx.get("cards_used_ranks", [])

        # The Big Game: "Complete an Event worth 9 VP or more"
        if "9 vp or more" in trigger or "worth 9" in trigger:
            if did_event:
                return ctx.get("event_vp", 0) >= 9

        # Goldilocks: "Complete an Event using exactly 4 cards"
        if "exactly 4 cards" in trigger:
            if did_event:
                return ctx.get("cards_used_count", 0) == 4

        # The Precision: "Complete an Event with any Sum requirement"
        if "sum requirement" in trigger:
            if did_event:
                return ctx.get("event_has_sum_req", False)

        # The Full Court Press: "Complete an Event from a hand of 7+ cards"
        if "hand of 7+" in trigger or "7+ cards" in trigger:
            if did_event:
                # Hand size before playing cards = after + cards used
                hand_before = ctx.get("hand_size_after_event", 0) + ctx.get("cards_used_count", 0)
                return hand_before >= 7

        # The Franchise Player: "only cards from a single faction with no Free Agents"
        if "single faction" in trigger and "no free agent" in trigger:
            if did_event:
                fas = ctx.get("cards_used_free_agents", [])
                factions = ctx.get("cards_used_factions", [])
                return len(fas) == 0 and len(set(factions)) == 1

        # The Underdog Story: "2+ fewer completed Events than the leader"
        if "2+ fewer" in trigger and "leader" in trigger:
            if did_event:
                leader_events = max(len(p.scored_events) for p in self.players)
                # -1 because we already scored this one
                my_events_before = len(player.scored_events) - 1
                return leader_events - my_events_before >= 2

        # The Knockout: "Complete Photo Finish or Sudden Death"
        if "photo finish" in trigger or "sudden death" in trigger:
            if did_event:
                name = ctx.get("event_name", "").lower()
                return "photo finish" in name or "sudden death" in name

        # The Marathon Runner: "Complete your 4th event"
        if "4th event" in trigger:
            if did_event:
                return ctx.get("events_completed_total", 0) == 4

        # The Hail Mary: "Complete your 5th Event with 2 or fewer cards in hand after"
        if "5th event" in trigger:
            if did_event:
                return (ctx.get("events_completed_total", 0) == 5 and
                        ctx.get("hand_size_after_event", 99) <= 2)

        # The Curveball: "reward causes an opponent to lose a card or Shiny"
        if "opponent to lose" in trigger or "causes an opponent" in trigger:
            if did_event:
                reward = ctx.get("event_reward", "").lower()
                return ("take" in reward and ("shiny" in reward or "shinies" in reward or
                        "card" in reward or "discard" in reward))

        # The Sponsorship Deal: "pay 5 Shinies immediately after scoring"
        # This is an optional pay - AI should choose. For sim, auto-trigger if affordable
        if "pay 5 shinies" in trigger and "after scoring" in trigger:
            if did_event and player.shinies >= 5:
                player.shinies -= 5
                return True

        # ── Draft-based combos ──

        # The High Roller: "Recruit a card from Lineup Slot 4"
        if "slot 4" in trigger and "recruit" in trigger:
            return ctx.get("drafted_slot") == 3  # 0-indexed

        # The Scavenger: "Draft a card that has 3+ Shinies sitting on it"
        if "3+ shinies" in trigger and "draft" in trigger:
            return ctx.get("drafted_shinies_on_card", 0) >= 3

        # Walk-On, Transfer, Ringer: "Recruit from Slot X and then Complete an Event"
        if "recruit from lineup slot 1" in trigger and "complete an event" in trigger:
            return ctx.get("drafted_slot") == 0 and did_event
        if "recruit from lineup slot 2" in trigger and "complete an event" in trigger:
            return ctx.get("drafted_slot") == 1 and did_event
        if ("slot 3 or 4" in trigger or "slot 3 or slot 4" in trigger) and "complete an event" in trigger:
            return ctx.get("drafted_slot") in (2, 3) and did_event

        # The Gatekeeper: "flush a Jumbotron event worth 8+ VP"
        if "flush" in trigger and "8+ vp" in trigger:
            return ctx.get("flushed_event_vp", 0) >= 8

        return False

    def _find_worst_card_index(self, player: Player) -> int:
        """Find index of least valuable card to discard for hand limit."""
        best_idx = 0
        best_score = float('inf')
        for i, card in enumerate(player.hand):
            # Simple heuristic: low-rank non-FAs are worst
            score = card.rank
            if card.is_free_agent:
                score += 20  # FAs are valuable, keep them
            if score < best_score:
                best_score = score
                best_idx = i
        return best_idx

    # ── Game Flow ────────────────────────────────────────────────────────

    def is_round_complete(self) -> bool:
        """Check if current round is complete (all players have had a turn)."""
        return self.current_player_idx == 0 and self.turn_number > 0

    def check_game_over(self) -> bool:
        """Check if the game should end."""
        if self.standing_ovation_triggered:
            # Game ends when we complete the round (back to player 0)
            if self.current_player_idx == 0 and self.turn_number > 0:
                # Check if all players after the trigger player have had their turn
                return True

        # Event deck exhaustion
        if self.event_deck.empty and len(self.jumbotron) == 0:
            return True

        return False

    def get_current_player(self) -> Player:
        return self.players[self.current_player_idx]

    def advance_turn(self):
        """Move to next player."""
        self.wiped_this_turn = False
        self.turn_context = {}
        self.current_player_idx = (self.current_player_idx + 1) % self.num_players
        if self.current_player_idx == 0:
            self.turn_number += 1

    def get_winner(self) -> Tuple[Player, List[dict]]:
        """Determine winner after game ends. Returns (winner, standings)."""
        standings = []
        for p in self.players:
            standings.append({
                "player": p.id,
                "event_vp": p.event_vp,
                "playbook_vp": p.playbook_vp,
                "shiny_bonus": p.shiny_bonus,
                "total_vp": p.total_vp,
                "events_9plus": sum(1 for e in p.scored_events if e.vp >= 9),
                "shinies": p.shinies,
            })

        # Sort by total VP, then by events worth 9+ (tiebreaker)
        standings.sort(key=lambda x: (-x["total_vp"], -x["events_9plus"]))
        winner = self.players[standings[0]["player"]]
        return winner, standings

    # ── Helpers ───────────────────────────────────────────────────────────

    def _reshuffle_stands(self):
        """Shuffle The Stands to form a new Recruit Deck."""
        if self.stands.size > 0:
            self._log("Reshuffling The Stands into Recruit Deck")
            self.recruit_deck.cards.extend(self.stands.cards)
            self.stands.cards.clear()
            self.recruit_deck.shuffle(self.rng)

    def _log(self, msg: str):
        self.log.append(f"T{self.turn_number}.P{self.current_player_idx}: {msg}")

    def get_state_summary(self) -> dict:
        """Return a summary of current game state for AI decision-making."""
        return {
            "turn": self.turn_number,
            "current_player": self.current_player_idx,
            "lineup": [(s.card, s.shinies) for s in self.lineup],
            "jumbotron": list(self.jumbotron),
            "players": [{
                "id": p.id,
                "hand": list(p.hand),
                "shinies": p.shinies,
                "event_vp": p.event_vp,
                "playbook_vp": p.playbook_vp,
                "total_vp": p.total_vp,
                "events_completed": len(p.scored_events),
                "hand_size": len(p.hand),
            } for p in self.players],
            "recruit_deck_size": self.recruit_deck.size,
            "event_deck_size": self.event_deck.size,
            "stands_size": self.stands.size,
            "standing_ovation": self.standing_ovation_triggered,
        }

    def resolve_reward_scramble(self, player: Player):
        """Resolve a 'free Scramble' reward."""
        if not self.lineup:
            return
        # Discard Slot 1
        discarded = self.lineup[0]
        if discarded.card:
            self.stands.add_to_bottom(discarded.card)
        slot1_shinies = discarded.shinies
        self.lineup.pop(0)

        # New card at Slot 4 with Slot 1's Shinies
        new_card = self.recruit_deck.draw_one()
        if new_card is None:
            self._reshuffle_stands()
            new_card = self.recruit_deck.draw_one()
        self.lineup.append(LineupSlot(card=new_card, shinies=slot1_shinies))

        # Draw mystery card
        mystery = self.recruit_deck.draw_one()
        if mystery is None:
            self._reshuffle_stands()
            mystery = self.recruit_deck.draw_one()
        if mystery:
            player.hand.append(mystery)
        self._log(f"P{player.id} free Scramble reward: drew {mystery}")

    def resolve_reward_shinies(self, player: Player, amount: int):
        """Give player Shinies as reward."""
        player.shinies += amount
        self._log(f"P{player.id} gained {amount}S from reward")

    def resolve_reward_draw(self, player: Player, draw: int, keep: int):
        """Draw N cards from Recruit Deck, keep M."""
        drawn = []
        for _ in range(draw):
            card = self.recruit_deck.draw_one()
            if card is None:
                self._reshuffle_stands()
                card = self.recruit_deck.draw_one()
            if card:
                drawn.append(card)

        # Keep first M (AI should choose, but default)
        kept = drawn[:keep]
        returned = drawn[keep:]
        player.hand.extend(kept)
        for c in returned:
            self.stands.add_to_bottom(c)
        self._log(f"P{player.id} drew {draw}, kept {keep}: {kept}")

    def resolve_reward_free_lineup_draft(self, player: Player, slot: int):
        """Free draft from a specific Lineup slot (0-indexed)."""
        if 0 <= slot < len(self.lineup) and self.lineup[slot].card:
            card = self.lineup[slot].card
            collected = self.lineup[slot].shinies
            player.hand.append(card)
            player.shinies += collected
            self.lineup.pop(slot)
            new_card = self.recruit_deck.draw_one()
            if new_card is None:
                self._reshuffle_stands()
                new_card = self.recruit_deck.draw_one()
            self.lineup.append(LineupSlot(card=new_card, shinies=0))
            self._log(f"P{player.id} free draft from Slot {slot+1}: {card} (+{collected}S)")
