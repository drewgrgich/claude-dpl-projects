"""Parse event requirements from CSV text into structured format."""

import csv
import re
from typing import List, Dict, Optional
from cards import EventCard, PlaybookCard


def parse_requirement_text(text: str) -> dict:
    """Parse a requirement string into a structured dict.

    Returns a dict with possible keys:
    - factions: dict of {faction: count} required
    - sum_min: minimum sum of ranks
    - sum_exact: exact sum required
    - sum_max: maximum sum allowed
    - run_length: consecutive rank run needed
    - set_size: N cards of same rank
    - card_count: total cards needed
    - free_agent_count: number of free agents needed
    - free_agent_max: maximum free agents allowed
    - any_factions: number of different factions needed
    - same_number: N cards with same rank (any factions)
    - free_agent_rank: specific rank for free agents (e.g., 0 for Sprinkler Ambush)
    """
    req = {}
    text_lower = text.lower().strip()

    # Faction-count patterns: "3x Super-Dupes" or "4x Time Travelers"
    faction_map = {
        "super-dupes": "RED", "super dupes": "RED",
        "finders-keepers": "RED", "finders keepers": "ORG", "finders-keepers": "ORG",
        "tinkerers": "YLW", "tinkerer": "YLW",
        "prognosticationers": "GRN", "prognosticationer": "GRN",
        "magicians": "BLU", "magician": "BLU",
        "time travelers": "PUR", "time traveler": "PUR",
    }

    factions = {}
    # Match patterns like "3x Super-Dupes" or "4x Time Travelers"
    faction_pattern = r'(\d+)x?\s*(super[- ]dupes|finders[- ]keepers|tinkerers?|prognosticationers?|magicians?|time travelers?)'
    for match in re.finditer(faction_pattern, text_lower):
        count = int(match.group(1))
        faction_name = match.group(2).strip()
        # Normalize faction name
        for key, code in faction_map.items():
            if faction_name.startswith(key[:4]):
                factions[code] = count
                break

    if factions:
        req["factions"] = factions

    # "N different factions" or "N different faction" or "one card showing each of the six faction symbols"
    diff_match = re.search(r'(\d+)\s+different\s+faction', text_lower)
    if diff_match:
        req["any_factions"] = int(diff_match.group(1))

    # "one card showing each of the six faction symbols" -> Group Photo
    if "each of the six" in text_lower or "one card showing each" in text_lower:
        req["any_factions"] = 6
        req["card_count"] = 6

    # Sum requirements
    sum_min = re.search(r'sum\s*[≥>=]+\s*(\d+)', text_lower)
    if sum_min:
        req["sum_min"] = int(sum_min.group(1))

    sum_exact = re.search(r'sum\s+exactly\s+(\d+)', text_lower)
    if sum_exact:
        req["sum_exact"] = int(sum_exact.group(1))

    sum_max = re.search(r'sum\s*[≤<=]+\s*(\d+)', text_lower)
    if sum_max:
        req["sum_max"] = int(sum_max.group(1))

    # Run requirements
    run_match = re.search(r'(\d+)-card\s+run', text_lower)
    if run_match:
        req["run_length"] = int(run_match.group(1))

    # Consecutive ranks
    if "consecutive ranks" in text_lower and "run_length" not in req:
        count_match = re.search(r'(\d+)-card', text_lower)
        if count_match:
            req["run_length"] = int(count_match.group(1))

    # Set requirements (N cards of same rank)
    set_match = re.search(r'(\d+)\s+cards?\s+(?:with\s+)?(?:the\s+)?same\s+(?:number|rank)', text_lower)
    if set_match:
        req["same_number"] = int(set_match.group(1))

    # Card count
    count_match = re.search(r'^(\d+)\s+cards?\b', text_lower)
    if count_match and "same" not in text_lower[:30]:
        req["card_count"] = int(count_match.group(1))

    # "N cards with Sum" pattern
    cards_sum = re.search(r'(\d+)\s+cards?\s+with\s+sum', text_lower)
    if cards_sum:
        req["card_count"] = int(cards_sum.group(1))

    # Free agent requirements
    fa_count = re.search(r'(\d+)\s+free\s+agents?', text_lower)
    if fa_count:
        req["free_agent_count"] = int(fa_count.group(1))

    # Max free agents
    fa_max = re.search(r'max\.?\s*(\d+)\s+free\s+agent', text_lower)
    if fa_max:
        req["free_agent_max"] = int(fa_max.group(1))

    # Free agent rank specification (e.g., "3 cards of number 0")
    fa_rank = re.search(r'(\d+)\s+cards?\s+of\s+number\s+(\d+)', text_lower)
    if fa_rank:
        req["card_count"] = int(fa_rank.group(1))
        req["required_rank"] = int(fa_rank.group(2))

    # "4x Free Agents (any mix of 0 and/or 10)"
    if "free agents" in text_lower and ("any mix" in text_lower or "4x free" in text_lower):
        fa_n = re.search(r'(\d+)x?\s+free\s+agents?', text_lower)
        if fa_n:
            req["free_agent_count"] = int(fa_n.group(1))

    # "3 cards from 3 different factions"
    diff_faction_cards = re.search(r'(\d+)\s+cards?\s+from\s+(\d+)\s+different\s+factions?', text_lower)
    if diff_faction_cards:
        req["card_count"] = int(diff_faction_cards.group(1))
        req["any_factions"] = int(diff_faction_cards.group(2))

    # Pairs: "2 Pairs of numbers" or "N pairs"
    pairs_match = re.search(r'(\d+)\s+pairs?\s+of\s+(?:numbers?|ranks?)', text_lower)
    if pairs_match:
        req["pairs_count"] = int(pairs_match.group(1))
        # "4 cards total" or infer: 2 pairs = 4 cards
        total_match = re.search(r'(\d+)\s+cards?\s+total', text_lower)
        if total_match:
            req["card_count"] = int(total_match.group(1))
        elif "card_count" not in req:
            req["card_count"] = req["pairs_count"] * 2

    # 3-of-a-kind: "3-of-a-kind (same number)" or "N-of-a-kind"
    kind_match = re.search(r'(\d+)-of-a-kind', text_lower)
    if kind_match:
        req["same_number"] = int(kind_match.group(1))
        # Infer card count from "N cards:" prefix
        card_prefix = re.search(r'^(\d+)\s+cards?:', text_lower)
        if card_prefix and "card_count" not in req:
            req["card_count"] = int(card_prefix.group(1))

    # "Same faction + consecutive ranks" (e.g., Rivalry Week)
    if "same faction" in text_lower and "consecutive rank" in text_lower:
        req["same_faction_run"] = True
        card_prefix = re.search(r'^(\d+)\s+cards?:', text_lower)
        if card_prefix:
            run_len = int(card_prefix.group(1))
            req["run_length"] = run_len
            if "card_count" not in req:
                req["card_count"] = run_len

    return req


def load_events_csv(filepath: str) -> List[EventCard]:
    """Load event cards from CSV file."""
    events = []
    with open(filepath, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Handle various column name formats
            tier_raw = row.get('Tier', row.get('tier', '0'))
            # Handle "Tier 1" format or plain "1"
            tier_str = str(tier_raw).strip()
            if tier_str.lower().startswith('tier'):
                tier_str = tier_str.split()[-1]
            tier = int(tier_str) if tier_str.isdigit() else 0
            name = row.get('Event Name', row.get('event_name', row.get('Name', row.get('name', ''))))
            vp = int(row.get('VP', row.get('vp', 0)))
            req_text = row.get('Requirements', row.get('requirements', ''))
            reward = row.get('Reward', row.get('reward', ''))

            requirements = parse_requirement_text(req_text)

            events.append(EventCard(
                name=name.strip(),
                tier=tier,
                vp=vp,
                requirements=requirements,
                reward=reward.strip(),
                raw_requirements=req_text.strip()
            ))
    return events


def load_playbooks_csv(filepath: str) -> List[PlaybookCard]:
    """Load playbook cards from CSV file."""
    playbooks = []
    with open(filepath, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row.get('Playbook', row.get('playbook', row.get('Name', row.get('name', ''))))
            category = row.get('Category', row.get('category', ''))
            vp = int(row.get('VP', row.get('vp', 0)))
            trigger = row.get('Trigger', row.get('trigger', ''))
            timing = row.get('Timing', row.get('timing', ''))

            playbooks.append(PlaybookCard(
                name=name.strip(),
                category=category.strip(),
                vp=vp,
                trigger=trigger.strip(),
                timing=timing.strip()
            ))
    return playbooks
