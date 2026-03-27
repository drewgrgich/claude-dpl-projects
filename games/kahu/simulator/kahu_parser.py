"""CSV parser for Kahu card data."""

import csv
import os
from typing import List
from cards import Card


# Map card names to machine-readable effect IDs
EFFECT_MAP = {
    "orchid": "orchid_scry",
    "pua kalaunu": "pua_kalaunu_thin",
    "plumeria": "plumeria_topdeck",
    "ginger": "ginger_retrieve_flower",
    "bird of paradise": "bird_retrieve_wildlife",
    "hibiscus": "hibiscus_retrieve_item",
    "pineapple": "pineapple_draw2",
    "ukulele": "ukulele_recycle",
    "surfboard": "surfboard_synergy",
    "sugar cane": "sugar_cane_cycle",
    "sea shell": "sea_shell_remove",
    "lei": "lei_islander_synergy",
    "outrigger": "outrigger_draw3",  # v3: surf synergy handled in game_state
    "grass hut": "grass_hut_islander_synergy",
    "plate lunch": "plate_lunch_free_pua",
    "sea turtle": "sea_turtle_flower_draw",
    "chicken": "chicken_steal",
    "nene goose": "nene_goose_copy",
    "dolphin": "dolphin_remove",
    "pig": "pig_exchange_pua",
    "fish": "fish_surf_pua",
    "surf": "surf",
}

# Islander cards have unique effects — map by effect text keywords
ISLANDER_EFFECTS = {
    "discard pile is empty": "islander_empty_discard",
    "wildlife cards cost 1 less": "islander_wildlife_discount",
    "tiki in play": "islander_tiki_bonus",
    "gain a surf card": "islander_free_surf",
    "play it again": "islander_replay",
    "gain any item": "islander_free_item",
    "draw two cards": "islander_draw2",
    "gain red pua": "islander_gain_red",
    "gain blue pua": "islander_gain_blue",
    "gain yellow": "islander_gain_yellow",
    "use any card from the market": "islander_market_borrow",
    "another islander": "islander_islander_synergy",
    "purchase this card": "islander_self_topdeck",
    "played with a surf": "islander_surf_synergy",
    "top card of your discard pile to your hand": "islander_discard_retrieve",
    "both of you may draw": "islander_mutual_draw",
    "both of you may gain the same": "islander_mutual_pua",
    "gain any flower": "islander_free_flower",
}


def classify_islander_effect(effect_text: str) -> str:
    """Classify an Islander's unique effect by keyword matching."""
    lower = effect_text.lower()
    for keyword, effect_id in ISLANDER_EFFECTS.items():
        if keyword in lower:
            return effect_id
    return "islander_generic"


def load_market_cards(filepath: str) -> List[Card]:
    """Load market cards from CSV file."""
    cards = []
    with open(filepath, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row["Card Name"].strip()
            card_type = row["Card Type"].strip()
            icon = row.get("Icon", "").strip()
            cost = int(row["Cost"]) if row["Cost"].strip() else 0
            influence = int(row["Influence"]) if row["Influence"].strip() else 0
            vp = int(row["VP"]) if row["VP"].strip() else 0
            effect_text = row.get("Card Effect", "").strip()

            # Determine effect_id
            name_lower = name.lower().strip()
            if card_type.lower() == "islander":
                effect_id = classify_islander_effect(effect_text)
            elif name_lower in EFFECT_MAP:
                effect_id = EFFECT_MAP[name_lower]
            else:
                effect_id = name_lower.replace(" ", "_")

            card = Card(
                name=name,
                card_type=card_type,
                cost=cost,
                influence=influence,
                vp=vp,
                icon=icon,
                effect_text=effect_text,
                effect_id=effect_id,
            )
            cards.append(card)
    return cards


def find_csv(pattern: str = "kahu-cards") -> str:
    """Auto-detect the card CSV file."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    search_dirs = [
        script_dir,
        os.path.join(script_dir, ".."),
        os.path.join(script_dir, "..", ".."),
    ]
    for d in search_dirs:
        if not os.path.isdir(d):
            continue
        for f in os.listdir(d):
            if pattern.lower() in f.lower() and f.endswith(".csv"):
                return os.path.join(d, f)
    return None


if __name__ == "__main__":
    path = find_csv()
    if path:
        cards = load_market_cards(path)
        print(f"Loaded {len(cards)} cards from {path}")
        by_type = {}
        for c in cards:
            by_type.setdefault(c.card_type, []).append(c)
        for t, cl in sorted(by_type.items()):
            print(f"  {t}: {len(cl)} cards")
    else:
        print("No CSV found")
