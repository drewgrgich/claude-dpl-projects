"""Validate whether a set of cards meets event requirements."""

from typing import List, Tuple, Optional, Set
from itertools import combinations
from cards import RecruitCard, EventCard


def check_event_requirements(cards: List[RecruitCard], event: EventCard) -> bool:
    """Check if a set of cards satisfies an event's requirements.

    Implements full validation including:
    - Faction counts with Free Agent substitution
    - Buddy System (each claimed faction needs at least 1 signed player)
    - Sum requirements (min, max, exact)
    - Run requirements (consecutive ranks)
    - Set requirements (same rank)
    - Card count requirements
    - Free Agent count/max restrictions
    """
    req = event.requirements

    # Card count check
    if "card_count" in req and len(cards) != req["card_count"]:
        return False

    # Required rank check (e.g., Sprinkler Ambush: 3 cards of number 0)
    if "required_rank" in req:
        matching = [c for c in cards if c.rank == req["required_rank"]]
        if len(matching) < req.get("card_count", len(cards)):
            return False

    # Free agent count requirements
    free_agents_in_hand = [c for c in cards if c.is_free_agent]

    if "free_agent_count" in req:
        # Events that specifically need free agents
        if len(free_agents_in_hand) < req["free_agent_count"]:
            return False

        # If the event ONLY needs free agents (like Secret Playbook), no Buddy needed
        if not req.get("factions") and not req.get("any_factions"):
            return _check_sum(cards, req) and _check_run(cards, req) and _check_set(cards, req)

    # Max free agent restriction
    if "free_agent_max" in req:
        if len(free_agents_in_hand) > req["free_agent_max"]:
            return False

    # "N different factions" (like Group Photo or Opening Ceremony)
    if "any_factions" in req:
        return _check_any_factions(cards, req)

    # Faction-specific requirements
    if "factions" in req:
        if not _check_faction_requirements(cards, req):
            return False

    # Pairs check (e.g., "2 Pairs of numbers")
    if "pairs_count" in req:
        return _check_pairs(cards, req)

    # Same number (set) check
    if "same_number" in req:
        return _check_same_number(cards, req)

    # Same faction run (e.g., Rivalry Week: same faction + consecutive ranks)
    if "same_faction_run" in req:
        return _check_same_faction_run(cards, req)

    # Run check
    if "run_length" in req:
        return _check_run(cards, req)

    # Sum check (applied after other checks)
    if not _check_sum(cards, req):
        return False

    return True


def _check_sum(cards: List[RecruitCard], req: dict) -> bool:
    """Check sum requirements."""
    total = sum(c.rank for c in cards)

    if "sum_min" in req and total < req["sum_min"]:
        return False
    if "sum_max" in req and total > req["sum_max"]:
        return False
    if "sum_exact" in req and total != req["sum_exact"]:
        return False

    return True


def _check_run(cards: List[RecruitCard], req: dict) -> bool:
    """Check if cards form a consecutive run of required length."""
    if "run_length" not in req:
        return True

    needed = req["run_length"]
    if len(cards) < needed:
        return False

    ranks = sorted(set(c.rank for c in cards))

    # Find consecutive sequences
    for i in range(len(ranks) - needed + 1):
        consecutive = True
        for j in range(1, needed):
            if ranks[i + j] != ranks[i] + j:
                consecutive = False
                break
        if consecutive:
            return _check_sum(cards, req)

    return False


def _check_same_number(cards: List[RecruitCard], req: dict) -> bool:
    """Check if N cards share the same rank."""
    needed = req["same_number"]
    if len(cards) < needed:
        return False

    from collections import Counter
    rank_counts = Counter(c.rank for c in cards)

    for rank, count in rank_counts.items():
        if count >= needed:
            return _check_sum(cards, req)

    return False


def _check_set(cards: List[RecruitCard], req: dict) -> bool:
    """Check set requirements."""
    if "same_number" in req:
        return _check_same_number(cards, req)
    return True


def _check_pairs(cards: List[RecruitCard], req: dict) -> bool:
    """Check if cards contain N distinct pairs of matching ranks.

    E.g., 2 Pairs: two 4s and two 7s (4 cards, 2 distinct pairs).
    """
    needed_pairs = req["pairs_count"]
    if len(cards) < needed_pairs * 2:
        return False

    from collections import Counter
    rank_counts = Counter(c.rank for c in cards)
    pairs_found = sum(1 for count in rank_counts.values() if count >= 2)

    if pairs_found < needed_pairs:
        return False

    return _check_sum(cards, req)


def _check_same_faction_run(cards: List[RecruitCard], req: dict) -> bool:
    """Check if cards are all the same faction AND form a consecutive run.

    E.g., Rivalry Week: 2 cards from same faction with consecutive ranks.
    Free Agents (rank 0, 10) can count as any faction (with buddy).
    """
    run_length = req.get("run_length", len(cards))
    if len(cards) < run_length:
        return False

    # Separate signed and free agents
    signed = [c for c in cards if not c.is_free_agent]
    free_agents = [c for c in cards if c.is_free_agent]

    if not signed:
        return False  # Need at least one buddy

    # Try each faction that has a signed card
    signed_factions = set(c.faction for c in signed)
    for faction in signed_factions:
        # Cards that count as this faction: signed of this faction + all FAs
        faction_cards = [c for c in signed if c.faction == faction] + free_agents
        if len(faction_cards) < run_length:
            continue

        # Check if any subset forms a run
        ranks = sorted(c.rank for c in faction_cards)
        for i in range(len(ranks) - run_length + 1):
            is_run = True
            for j in range(1, run_length):
                if ranks[i + j] != ranks[i] + j:
                    is_run = False
                    break
            if is_run:
                return _check_sum(cards, req)

    return False


def _check_any_factions(cards: List[RecruitCard], req: dict) -> bool:
    """Check N-different-factions requirement with Free Agent substitution and Buddy System."""
    needed_factions = req["any_factions"]

    # Get signed factions (ranks 1-9)
    signed_factions = set()
    for c in cards:
        if not c.is_free_agent:
            signed_factions.add(c.faction)

    # Free agents can fill in for missing factions
    free_agents = [c for c in cards if c.is_free_agent]

    # Each free agent can represent one additional faction, BUT needs a buddy
    # For "any_factions" events, we need at least 1 signed player per claimed faction
    # Free agents can represent factions where we have a buddy OR where the FA itself
    # provides the faction (but then needs another signed card as buddy).

    # Actually for Group Photo / Opening Ceremony style events:
    # Each card represents its own faction (or a FA represents any faction)
    # But Buddy System: each claimed faction needs at least 1 signed player

    # Strategy: signed cards claim their own faction. Free agents fill remaining slots.
    # But each FA-claimed faction still needs a buddy. Since FAs have their OWN printed
    # faction, if we use a FA as its own faction, it IS a signed member of that faction? No.
    # FAs are rank 0 or 10 - they are NOT signed (ranks 1-9).

    # A FA used as its OWN faction still needs a buddy of that faction (a rank 1-9 card).
    # A FA used as ANOTHER faction needs a buddy of that other faction.

    # So: the only factions we can claim are those where we have at least one rank 1-9 card.
    # FAs fill in ADDITIONAL slots for factions that already have a buddy.

    # For Group Photo (6 factions, 6 cards):
    # We need 6 factions. Each faction must have a buddy. We have at most 6 cards.
    # So we need at least 1 signed card per faction we claim.
    # FAs can fill the 6th slot if we have 5 signed factions + 1 FA with a buddy somewhere.

    # Simplified approach: factions we can represent = signed factions + number of FAs
    # (each FA can represent one additional faction, limited by buddy requirement)

    # But a FA can only represent a faction that has a buddy OR if it's its own faction
    # and there's a buddy for that faction. Since FAs are NOT signed...

    # The clean interpretation: signed_factions are covered. Each FA can add one MORE
    # faction IF there's at least one signed card that could buddy for it. But for
    # "any different factions" events, the FA needs a buddy for the faction it claims.
    # Since we typically don't have a buddy for the FA's CLAIMED faction (that's why
    # we're using the FA), we can't use FAs to add new factions without buddies.

    # WAIT - re-reading the rules more carefully:
    # "For each faction you're claiming, at least one card must be a signed player
    # (ranks 1–9) of that faction."
    # So to claim Magician faction, you need at least one Magician rank 1-9.
    # A Tinkerer-0 counting as Magician still needs a real Magician buddy.

    # For Group Photo (1 of each of 6 factions):
    # You need 6 different factions. Each needs a signed buddy.
    # With 6 cards, you need 6 signed cards from 6 different factions (no FAs possible!)
    # OR you need signed buddies for each faction you claim, and FAs fill extra slots.

    # Example from playtest: YLW-2, RED-3, ORG-7, GRN-2, BLU-6, PUR-1 - all signed. Works.

    # So for any_factions: count signed factions. FAs can claim factions that already
    # have a signed buddy, but that doesn't ADD new factions. FAs only add new factions
    # if the event doesn't require the buddy... but it always does.

    # Actually, re-reading again: "Free Agents can count as any faction when completing
    # events. Need three Magicians but only have two? That Tinkerer-0 can put on a top hat."
    # The buddy is needed for the FACTION being claimed, and 1 buddy covers all FAs
    # claiming that faction. So for "3 Magicians": BLU-7 (buddy) + BLU-0 (FA as Mag,
    # has buddy BLU-7) + YLW-0 (FA as Mag, has buddy BLU-7). That works.

    # For "different factions" events: a FA can claim a faction that already has a signed
    # buddy. But that's redundant - that faction is already counted.
    # A FA CANNOT claim a brand new faction with no buddy present.

    # So: achievable factions = number of distinct signed factions (rank 1-9).
    # FAs don't help with "different factions" events unless the FA's OWN printed
    # faction has a buddy. But the FA itself isn't a buddy (ranks 0,10 not signed).

    total_possible = len(signed_factions)

    # Wait - what about a FA counting as its OWN faction? E.g., BLU-0 counts as Magician.
    # It needs a Magician buddy (rank 1-9). If we don't have one, BLU-0 can't claim Magician.
    # So FAs truly cannot add factions beyond what signed cards provide.

    # HOWEVER: consider this edge case for Group Photo:
    # 5 signed factions + 1 FA whose printed faction is the 6th. The FA can count as
    # its own faction, but needs a buddy. No buddy available -> can't claim it.
    # So you genuinely need 6 signed factions for Group Photo. Unless...
    # You have a signed card of faction X and an FA of faction X. The FA is redundant
    # for faction X but could count as faction Y (with buddy requirement for Y).

    # Final answer: achievable different factions = len(signed_factions)
    # FAs can only add diversity if they claim a faction that already has a buddy,
    # which by definition is already counted. So FAs don't increase faction diversity
    # for "N different factions" events.

    if total_possible < needed_factions:
        return False

    # Also check sum if needed
    return _check_sum(cards, req)


def _check_faction_requirements(cards: List[RecruitCard], req: dict) -> bool:
    """Check faction-count requirements with Free Agent substitution and Buddy System.

    For requirements like "3x Magicians + 1x Finders-Keepers":
    - Each faction needs at least 1 signed player (ranks 1-9) as buddy
    - Free Agents can fill remaining slots for any faction that has a buddy
    """
    required_factions = req["factions"]  # e.g., {"BLU": 3, "ORG": 1}

    # Separate signed cards and free agents
    signed = [c for c in cards if not c.is_free_agent]
    free_agents = [c for c in cards if c.is_free_agent]

    # Check buddy requirement: each required faction needs at least 1 signed card
    for faction, count in required_factions.items():
        has_buddy = any(c.faction == faction for c in signed)
        if not has_buddy:
            return False

    # Count signed cards per required faction
    signed_per_faction = {}
    used_signed = set()
    for faction, needed in required_factions.items():
        matching = [i for i, c in enumerate(signed)
                    if c.faction == faction and i not in used_signed]
        take = min(len(matching), needed)
        signed_per_faction[faction] = take
        for i in matching[:take]:
            used_signed.add(i)

    # Calculate remaining needs
    total_remaining = 0
    for faction, needed in required_factions.items():
        remaining = needed - signed_per_faction.get(faction, 0)
        total_remaining += remaining

    # Free agents fill the remaining slots (any faction with a buddy)
    # Also handle additional free agent requirements from the event
    fa_for_factions = min(len(free_agents), total_remaining)

    # Check free agent max restriction
    if "free_agent_max" in req:
        fa_for_factions = min(fa_for_factions, req["free_agent_max"])

    if fa_for_factions < total_remaining:
        return False

    # Additional free agent count requirement (e.g., "3x TT + 2 Free Agents")
    if "free_agent_count" in req:
        fa_used_for_factions = fa_for_factions
        fa_remaining = len(free_agents) - fa_used_for_factions
        if fa_remaining < req["free_agent_count"]:
            return False

    return _check_sum(cards, req)


def find_completable_events(hand: List[RecruitCard], jumbotron: List[EventCard]) -> List[Tuple[EventCard, List[RecruitCard]]]:
    """Find all events that can be completed with the current hand.

    Returns list of (event, cards_to_use) tuples.
    """
    completable = []

    for event in jumbotron:
        best_combo = find_best_card_combo(hand, event)
        if best_combo is not None:
            completable.append((event, best_combo))

    return completable


def find_best_card_combo(hand: List[RecruitCard], event: EventCard) -> Optional[List[RecruitCard]]:
    """Find the best (smallest) set of cards from hand that completes an event.

    Returns None if the event cannot be completed.
    """
    req = event.requirements

    # Determine how many cards to try
    min_cards = _estimate_min_cards(req)
    max_cards = min(len(hand), 8)  # never need more than 8

    if "card_count" in req:
        # Fixed card count - only try that size
        min_cards = req["card_count"]
        max_cards = req["card_count"]

    for size in range(min_cards, max_cards + 1):
        for combo in combinations(hand, size):
            if check_event_requirements(list(combo), event):
                return list(combo)

    return None


def _estimate_min_cards(req: dict) -> int:
    """Estimate minimum cards needed based on requirements."""
    estimates = [1]

    if "card_count" in req:
        return req["card_count"]

    if "factions" in req:
        estimates.append(sum(req["factions"].values()))
        if "free_agent_count" in req:
            estimates[-1] += req["free_agent_count"]

    if "any_factions" in req:
        estimates.append(req["any_factions"])

    if "run_length" in req:
        estimates.append(req["run_length"])

    if "same_number" in req:
        estimates.append(req["same_number"])

    if "pairs_count" in req:
        estimates.append(req["pairs_count"] * 2)

    if "same_faction_run" in req and "run_length" in req:
        estimates.append(req["run_length"])

    if "free_agent_count" in req and "factions" not in req:
        estimates.append(req["free_agent_count"])

    return max(estimates)
