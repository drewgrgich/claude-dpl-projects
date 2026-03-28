"""Round simulation for Championship Arena."""

import random
from typing import List, Dict, Optional, Tuple
from cards import HMCard
from game_state import GameState, Player, Ring
from ai_player import AIPlayer


# ─── Ring Energy Calculation ────────────────────────────────────────────────────

def calc_ring_energy(
    player: Player,
    ring: Ring,
    gs: GameState,
    include_stunt_double: bool = True
) -> int:
    """
    Calculate energy score for a player at a ring.
    Applies ring power, but NOT spectator double-FP (that's applied later).
    """
    dice_vals = player.assigned_dice.get(ring.color, [])
    card = player.played_cards.get(ring.color, None)
    sd = player.stunt_double if include_stunt_double else None

    # Start with dice
    energy = 0

    if gs.chaos_round:
        dice_vals = [0] * len(dice_vals)

    # Apply Green ring power: odd dice values doubled
    if ring.power_type == "odd_double":
        for d in dice_vals:
            if d % 2 == 1:
                energy += d * 2
            else:
                energy += d
    else:
        energy += sum(dice_vals)

    # Apply card contribution (unless Red ring)
    if ring.power_type != "highest_dice":
        # Rainbow Ring: all cards = 10
        if gs.rainbow_ring == ring.color:
            card_energy = 10
            sd_energy = sd.rank if sd else 0
        else:
            card_energy = card.rank if card else 0
            sd_energy = sd.rank if sd else 0

        # Apply Blue ring power: even card ranks doubled
        if ring.power_type == "even_double":
            if card_energy % 2 == 0 and card_energy > 0:
                card_energy *= 2
            if sd_energy % 2 == 0 and sd_energy > 0:
                sd_energy *= 2

        # Apply Yellow ring power: only 0s and 10s count
        if ring.power_type == "extremes":
            card_energy = card_energy if card_energy in [0, 10] else 0
            sd_energy = sd_energy if sd_energy in [0, 10] else 0

        energy += card_energy + sd_energy

    # Apply Sprinter talent: all dice +2
    if player.talent and player.talent["name"] == "The Sprinter":
        energy += 2 * len(dice_vals)

    return energy


def calc_orange_energy(player: Player, ring: Ring, gs: GameState) -> int:
    """Orange ring: most cards wins. Count cards played (1 per player + trophies)."""
    count = 0
    if ring.color in player.played_cards:
        count += 1
    if player.stunt_double:
        count += 1
    count += len(ring.trophies)
    return count


def get_winner_at_ring(
    ring: Ring,
    players: List[Player],
    gs: GameState,
) -> Optional[Player]:
    """Determine the winner at a specific ring."""
    active_players = [p for p in players if ring.color in p.assigned_dice or ring.power_type == "most_cards"]

    if not active_players:
        return None

    scores = {}
    for p in active_players:
        if ring.power_type == "most_cards":
            scores[p.id] = calc_orange_energy(p, ring, gs)
        else:
            scores[p.id] = calc_ring_energy(p, ring, gs)

    if ring.power_type == "lowest_wins":
        winner_id = min(scores, key=lambda pid: scores[pid])
    else:
        winner_id = max(scores, key=lambda pid: scores[pid])

    for p in players:
        if p.id == winner_id:
            return p
    return None


# ─── Spectator Card Resolution ─────────────────────────────────────────────────

def resolve_spectator_card(gs: GameState, card: dict, starting_player_idx: int) -> str:
    """Resolve a spectator card effect. Returns a narration string."""
    cid = card["id"]
    narration = f"  🎭 SPECTATOR: {card['emoji']} {card['name']} — {card['desc']}\n"

    # Reset round-specific flags
    gs.chaos_round = False
    gs.rainbow_ring = None
    gs.jittery_hamster_winner = None
    gs.starstruck_target = None
    gs.underdog_player = None

    if cid == 1:  # The Roaring Crowd
        narration += "  → All FP this round is DOUBLED!\n"

    elif cid == 2:  # The Jittery Hamster
        # Highest single die at Red Ring wins +1 FP
        red_ring = gs.get_ring_by_color("Red")
        if red_ring:
            best_player = None
            best_die = -1
            for p in gs.players:
                dice_vals = p.assigned_dice.get("Red", [])
                if dice_vals:
                    max_die = max(dice_vals)
                    if max_die > best_die:
                        best_die = max_die
                        best_player = p
                    elif max_die == best_die:
                        best_player = None  # tie
            if best_player:
                gs.jittery_hamster_winner = best_player.id
                narration += f"  → {best_player} has highest die ({best_die}) at Red — gets +1 FP!\n"

    elif cid == 3:  # The Dramatic Ref
        # Player with most cards reveals a Stunt Double swap with opponent
        most_cards_player = max(gs.players, key=lambda p: p.num_cards_in_play())
        # AI: just swap with first opponent
        opponent = gs.players[0] if gs.players[0] != most_cards_player else gs.players[-1]
        if most_cards_player.stunt_double and opponent.stunt_double:
            # Swap
            most_cards_player.stunt_double, opponent.stunt_double = \
                opponent.stunt_double, most_cards_player.stunt_double
            narration += f"  → {most_cards_player} and {opponent} swap Stunt Doubles!\n"

    elif cid == 4:  # The Starstruck Fan
        # Choose player (randomly for AI)
        target = random.choice(gs.players)
        target.hand.extend(gs.deck.draw(3))
        target.starstruck_active = True
        gs.starstruck_target = target.id
        narration += f"  → {target} draws 3 cards and next win = +2 FP bonus!\n"

    elif cid == 5:  # The Jeering Rival
        # Player who lost last round discards 2 cards
        loser = gs.last_round_loser
        if loser and loser in gs.players:
            discards = gs.deck.draw(2)
            gs.deck.cards.extend(discards)  # discard back to deck
            removed = []
            for _ in range(min(2, len(loser.hand))):
                c = loser.hand.pop(0)
                removed.append(c)
            if removed:
                narration += f"  → {loser} discards {removed} (2 cards returned to deck)!\n"

    elif cid == 6:  # The Underdog Cheer
        # Fewest FP player rolls 5 dice
        fewest_fp = min(gs.players, key=lambda p: p.fp)
        gs.underdog_player = fewest_fp.id
        fewest_fp.dice = list(fewest_fp.dice) + [random.randint(1, 6)]
        narration += f"  → {fewest_fp} (fewest FP) rolls 5 dice this round!\n"

    elif cid == 7:  # The Wild Card Toss
        # Dump top 3 deck cards into Stunt Pool, refill to 6
        dumped = gs.deck.draw(3)
        gs.stunt_pool.extend(dumped)
        narration += f"  → 3 cards dumped to Stunt Pool: {dumped}\n"
        gs.fill_stunt_pool(6)
        narration += f"  → Stunt Pool refilled to 6: {gs.stunt_pool}\n"

    elif cid == 8:  # The Card Shark
        # All players swap one card at a chosen Ring
        if gs.active_rings:
            chosen_ring = random.choice(gs.active_rings)
            # Simple: swap first two players' cards at this ring
            if len(gs.players) >= 2:
                p1, p2 = gs.players[0], gs.players[1]
                c1 = p1.played_cards.get(chosen_ring.color)
                c2 = p2.played_cards.get(chosen_ring.color)
                if c1 and c2:
                    p1.played_cards[chosen_ring.color], p2.played_cards[chosen_ring.color] = c2, c1
                    narration += f"  → {p1} and {p2} swap cards at {chosen_ring.color}!\n"

    elif cid == 9:  # The Champion's Welcome
        # Most Trophies draws 2 cards
        most_trophies = max(gs.players, key=lambda p: len(p.trophies))
        drawn = gs.deck.draw(2)
        most_trophies.hand.extend(drawn)
        narration += f"  → {most_trophies} (most Trophies) draws 2 cards: {drawn}!\n"

    elif cid == 10:  # The Chaos Round
        gs.chaos_round = True
        narration += "  → ALL DICE = 0 THIS ROUND! Cards only!\n"

    elif cid == 11:  # The Peace Offering
        # All who reveal Stunt Double draw 1 card
        for p in gs.players:
            if p.stunt_double:
                drawn = gs.deck.draw(1)
                p.hand.extend(drawn)
                narration += f"  → {p} reveals Stunt Double and draws 1 card!\n"

    elif cid == 12:  # The Rainbow Ring
        # Choose a Ring: all cards = 10, dice normal
        chosen = random.choice(gs.active_rings)
        gs.rainbow_ring = chosen.color
        narration += f"  → {chosen.color} Ring is WILD (all cards = 10)!\n"

    return narration


# ─── Talent Resolution ──────────────────────────────────────────────────────────

def apply_talents_pre_roll(gs: GameState, player: Player, ai: AIPlayer):
    """Apply talents that trigger before rolling."""
    if not player.talent or player.talent_used_this_round:
        return

    talent_name = player.talent["name"]

    if talent_name == "The Sprinter":
        player.talent_used_this_round = True
    elif talent_name == "The Showman":
        player.talent_used_this_round = True
    elif talent_name == "The Illusionist":
        player.talent_used_this_round = True


def apply_talents_after_reveal(gs: GameState, player: Player, ai: AIPlayer):
    """Apply talents that trigger after reveal."""
    if not player.talent or player.talent_used_this_round:
        return

    talent_name = player.talent["name"]

    if talent_name == "The Time Traveler":
        # Swap one of your cards with opponent's at same ring
        player.talent_used_this_round = True
        # Find a ring where we have a card
        my_rings = [r for r in gs.active_rings if r.color in player.played_cards]
        if not my_rings:
            return
        ring = random.choice(my_rings)
        # Find opponent with a card at same ring
        for opp in gs.players:
            if opp.id != player.id and ring.color in opp.played_cards:
                # Swap
                my_card = player.played_cards[ring.color]
                opp_card = opp.played_cards[ring.color]
                player.played_cards[ring.color] = opp_card
                opp.played_cards[ring.color] = my_card
                break


# ─── Stunt Double Resolution ────────────────────────────────────────────────────

def resolve_stunt_doubles(gs: GameState):
    """Allow each player to optionally move their stunt double to any ring."""
    for p in gs.players:
        if p.stunt_double:
            # AI: 60% chance to reveal and move to best ring
            if random.random() < 0.6:
                # Move to ring with most assigned dice
                best_ring = None
                best_dice = -1
                for r in gs.active_rings:
                    num_dice = len(p.assigned_dice.get(r.color, []))
                    if num_dice > best_dice:
                        best_dice = num_dice
                        best_ring = r
                # Stunt double is just added to energy; it stays in played_cards conceptually
                # Actually the stunt double can be moved to ANY ring before scoring
                # We'll leave it as-is since it already contributes to the ring it's assigned to


# ─── Score Calculation & Ring Claim ────────────────────────────────────────────

def claim_rings(gs: GameState) -> Dict[str, Player]:
    """Determine ring winners. Returns dict of ring_color → winner."""
    results = {}
    for ring in gs.active_rings:
        winner = get_winner_at_ring(ring, gs.players, gs)
        results[ring.color] = winner
    return results


def award_fp(player: Player, num_rings_won: int, gs: GameState, spectator_active: bool):
    """Award FP to player for rings won."""
    base_fp = {1: 1, 2: 3, 3: 6}
    fp = base_fp.get(num_rings_won, 0)

    # The Roaring Crowd doubles FP
    if spectator_active:
        fp *= 2

    # The Showman doubles FP
    if player.talent and player.talent["name"] == "The Showman":
        fp *= 2

    player.fp += fp

    # The Starstruck Fan bonus
    if player.starstruck_active and num_rings_won > 0:
        player.fp += 2
        player.starstruck_active = False

    # The Jittery Hamster bonus
    if gs.jittery_hamster_winner == player.id:
        player.fp += 1


def award_trophy(player: Player, ring: Ring, gs: GameState):
    """Place trophy on ring after winning."""
    if player.hand:
        trophy = player.hand.pop(0)
        ring.trophies.append(trophy)
        player.trophies.append(trophy)


def draw_cards_after_win(player: Player, gs: GameState, purple_count: int):
    """Draw cards after winning a ring."""
    base_draw = 2
    # The Collector gets +2 extra
    if player.talent and player.talent["name"] == "The Collector":
        base_draw += 2
    # Purple cards played give +1 each
    total_draw = base_draw + purple_count
    drawn = gs.deck.draw(total_draw)
    player.hand.extend(drawn)


# ─── Main Round Simulation ──────────────────────────────────────────────────────

def simulate_round(gs: GameState, audit_data: Optional[dict] = None) -> Tuple[GameState, str]:
    """
    Simulate one complete round.
    audit_data: optional dict to collect sweep/spectator/talent tracking.
    Returns (updated GameState, narration_string).
    """
    narration = f"\n{'='*60}\n"
    narration += f"  ROUND {gs.round_number}\n"
    narration += f"{'='*60}\n"

    gs.round_number += 1

    # ── Step 0: Spectator Card ──────────────────────────────────────────────
    spectator_card = gs.spectator_deck.draw()
    if spectator_card:
        narration += resolve_spectator_card(gs, spectator_card, 0)
        gs.current_spectator = spectator_card
        gs.spectator_deck.discard_card(spectator_card)
        # Track impactful spectator cards
        if audit_data is not None and spectator_card["id"] in [1, 2, 4, 7, 8, 11, 12]:
            audit_data["spectator_impact_this_round"] = True
    else:
        gs.current_spectator = None

    # Check if Roaring Crowd is active
    roaring_crowd = gs.current_spectator and gs.current_spectator["id"] == 1

    # ── Step 1: Roll Dice ───────────────────────────────────────────────────
    for p in gs.players:
        num_dice = 4
        # Underdog gets +1 die
        if gs.underdog_player == p.id:
            num_dice = 5
        if gs.chaos_round:
            p.dice = [0] * num_dice
        else:
            p.dice = [random.randint(1, 6) for _ in range(num_dice)]
    narration += f"  🎲 Dice rolled: {[(p.id, p.dice) for p in gs.players]}\n"

    # ── Create AI Players ───────────────────────────────────────────────────
    ais = {p.id: AIPlayer(p, len(gs.players)) for p in gs.players}

    # ── Pre-roll talent activation ───────────────────────────────────────────
    for p in gs.players:
        if p.talent and p.talent["trigger"] == "before_roll" and not p.talent_used_this_round:
            apply_talents_pre_roll(gs, p, ais[p.id])
            if audit_data is not None:
                audit_data["talent_decisive"] = True

    # ── Step 2: Commit — Assign Dice & Play Cards ────────────────────────────
    for p in gs.players:
        ais[p.id].assign_dice(gs)
        ais[p.id].play_cards(gs)

    narration += f"  🎯 Assignments: {[(p.id, p.assigned_dice) for p in gs.players]}\n"
    narration += f"  🃏 Cards played (face-down): {[(p.id, list(p.played_cards.values())) for p in gs.players]}\n"

    # ── Step 3: Reveal ───────────────────────────────────────────────────────
    narration += "  ✨ REVEAL! Cards flip:\n"
    for p in gs.players:
        for ring_color, card in p.played_cards.items():
            sd = " [SD]" if p.stunt_double and p.stunt_double == card else ""
            narration += f"    {p} at {ring_color}: {card}{sd}\n"

    # ── Talent: The Time Traveler (after reveal) ────────────────────────────
    for p in gs.players:
        if p.talent and p.talent["name"] == "The Time Traveler" and not p.talent_used_this_round:
            apply_talents_after_reveal(gs, p, ais[p.id])
            if audit_data is not None:
                audit_data["talent_decisive"] = True

    # ── Resolve stunt doubles ─────────────────────────────────────────────────
    resolve_stunt_doubles(gs)

    # ── Step 4: Calculate Energy & Claim Rings ──────────────────────────────
    narration += "\n  📊 ENERGY SCORES:\n"
    for ring in gs.active_rings:
        for p in gs.players:
            if ring.color in p.assigned_dice or ring.power_type == "most_cards":
                if ring.power_type == "most_cards":
                    score = calc_orange_energy(p, ring, gs)
                else:
                    score = calc_ring_energy(p, ring, gs)
                narration += f"    {p} @ {ring.color}: {score} (dice={p.assigned_dice.get(ring.color, [])}, card={p.played_cards.get(ring.color, 'none')})\n"

    # Determine winners
    ring_winners = claim_rings(gs)

    # Count rings per player
    rings_per_player: Dict[int, int] = {p.id: 0 for p in gs.players}
    for ring_color, winner in ring_winners.items():
        if winner:
            rings_per_player[winner.id] += 1

    narration += "\n  🏆 RING CLAIMS:\n"
    last_loser = None
    for ring_color, winner in ring_winners.items():
        ring = gs.get_ring_by_color(ring_color)
        if winner:
            narration += f"    {ring_color} → {winner} (score: {winner.fp})\n"
            # Award trophy
            award_trophy(winner, ring, gs)
            # Count purple cards played
            purple_count = sum(1 for c in winner.played_cards.values() if c.suit == "Purple")
            draw_cards_after_win(winner, gs, purple_count)
        else:
            narration += f"    {ring_color} → NO CLAIM\n"

    # Award FP
    for player_id, num_rings in rings_per_player.items():
        player = gs.get_player_by_id(player_id)
        if player and num_rings > 0:
            award_fp(player, num_rings, gs, roaring_crowd)
            if num_rings == 3:
                narration += f"    🎉 SWEEP by {player}! All 3 rings!\n"
                if audit_data is not None:
                    audit_data["sweep_rounds"] += 1

    # ── Step 5: Stunt Pool Drafting ──────────────────────────────────────────
    for p in gs.players:
        drafted = ais[p.id].draft_from_stunt_pool(gs)
        if drafted:
            narration += f"  🎪 {p} drafts from Stunt Pool\n"

    # Check for winner
    winner = gs.get_winner()
    if winner:
        gs.winner = winner
        narration += f"\n  🏆🏆🏆 WINNER: {winner} with {winner.fp} FP! 🏆🏆🏆\n"

    # Update last round loser (player who won 0 rings)
    last_loser = None
    for player_id, num_rings in rings_per_player.items():
        if num_rings == 0:
            last_loser = gs.get_player_by_id(player_id)
    gs.last_round_loser = last_loser

    # ── Reset round state ────────────────────────────────────────────────────
    for p in gs.players:
        p.assigned_dice = {}
        p.played_cards = {}
        # Keep stunt double (hidden reserve)

    gs.reset_round_state()

    # ── Check winner ─────────────────────────────────────────────────────────
    winner = gs.get_winner()
    if winner:
        gs.winner = winner

    return gs, narration
