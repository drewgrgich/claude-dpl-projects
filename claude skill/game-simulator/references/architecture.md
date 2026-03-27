# Simulator Architecture Reference

This document details the file-by-file structure and code patterns for building a tabletop game simulator. All patterns are drawn from a production card game simulator that has been extensively tested and iterated.

## Table of Contents

1. [File Structure](#file-structure)
2. [cards.py — Component Definitions](#cardspy)
3. [CSV Parser — Card Data Loading](#csv-parser)
4. [Requirement Checker — Validation Engine](#requirement-checker)
5. [config.json — Rule Parameters](#configjson)
6. [game_state.py — State Machine](#game_statepy)
7. [run_simulation.py — Batch Runner](#run_simulationpy)
8. [narrate_game.py — Narration Engine](#narrate_gamepy)
9. [card_audit.py — Component Analysis](#card_auditpy)
10. [CLI Design Patterns](#cli-design-patterns)

---

## File Structure

```
game-name/
├── simulator/
│   ├── config.json          # All tunable game rules
│   ├── cards.py             # Component dataclasses and Deck class
│   ├── <game>_parser.py     # CSV loaders and text-to-struct parsing
│   ├── <game>_checker.py    # Requirement/condition validation
│   ├── game_state.py        # Full game state machine
│   ├── ai_player.py         # Heuristic AI with skill/style/aggression
│   ├── run_simulation.py    # Batch runner with stats collection
│   ├── narrate_game.py      # Single-game narration to Markdown
│   └── card_audit.py        # Component ranking and culling analysis
├── <game>-cards.csv         # Card definitions (editable in spreadsheet)
├── <game>-rules.md          # Ruleset document
└── README.md                # Simulator documentation
```

CSV files live in the parent directory so they're easy to find and edit. The simulator auto-detects them relative to its own location.

---

## cards.py

Define one dataclass per component type. Keep them minimal — just the data properties the component has, plus convenience computed properties.

### Pattern: Component Dataclass

```python
from dataclasses import dataclass, field
from typing import List, Optional

@dataclass
class Card:
    """A single game card."""
    name: str
    card_type: str      # e.g., "creature", "spell", "resource"
    cost: int
    power: int = 0

    @property
    def is_free(self) -> bool:
        return self.cost == 0

    @property
    def id(self) -> str:
        return f"{self.card_type}-{self.name}"

    def __hash__(self):
        return hash(self.id)

    def __eq__(self, other):
        if not isinstance(other, Card):
            return False
        return self.id == other.id

    def __repr__(self):
        return f"{self.name}({self.cost}cost/{self.power}pow)"
```

Important details:
- `__hash__` and `__eq__` are needed if cards go into sets or get compared
- `__repr__` should be short and informative — you'll see it in logs thousands of times
- Use `@property` for derived values, not stored state

### Pattern: Deck Class

A generic container for any pile of components:

```python
import random

class Deck:
    def __init__(self, cards: list = None):
        self.cards: list = list(cards) if cards else []

    def shuffle(self, rng: random.Random = None):
        """Shuffle using provided RNG for reproducibility."""
        if rng:
            rng.shuffle(self.cards)
        else:
            random.shuffle(self.cards)

    def draw(self, n: int = 1) -> list:
        drawn = self.cards[:n]
        self.cards = self.cards[n:]
        return drawn

    def draw_one(self):
        return self.cards.pop(0) if self.cards else None

    def add_to_bottom(self, cards):
        if isinstance(cards, list):
            self.cards.extend(cards)
        else:
            self.cards.append(cards)

    def add_to_top(self, cards):
        if isinstance(cards, list):
            self.cards = cards + self.cards
        else:
            self.cards.insert(0, cards)

    def peek(self, n: int = 1) -> list:
        return self.cards[:n]

    @property
    def size(self) -> int:
        return len(self.cards)

    @property
    def empty(self) -> bool:
        return len(self.cards) == 0
```

This single class handles draw piles, discard piles, hands, markets — anything that holds an ordered collection of components.

### Pattern: Build Function

A factory that creates all components from config:

```python
def build_deck(config: dict) -> List[Card]:
    """Build all cards from configuration."""
    cards = []
    for card_type in config["card_types"]:
        for rank in range(config["rank_range"][0], config["rank_range"][1] + 1):
            cards.append(Card(name=f"{card_type}-{rank}",
                            card_type=card_type, cost=rank))
    return cards
```

---

## CSV Parser

Load card definitions from CSV files. The parser bridges human-readable card descriptions and the structured dicts the engine needs.

### Pattern: CSV Loader

```python
import csv
import os

def load_cards_csv(filepath: str) -> list:
    """Load cards from CSV, parsing text requirements into structured dicts."""
    cards = []
    with open(filepath, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            req = parse_requirement_text(row["Requirements"])
            cards.append(EventCard(
                name=row["Name"].strip(),
                tier=int(row["Tier"].replace("Tier ", "")),
                vp=int(row["VP"]),
                requirements=req,
                reward=row.get("Reward", "").strip(),
                raw_requirements=row["Requirements"].strip()
            ))
    return cards
```

### Pattern: Auto-Detection

Find CSV files relative to the script's location:

```python
def find_data_file(filename_pattern: str) -> str:
    """Search for a data file in common locations."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    search_dirs = [
        script_dir,                        # Same directory as script
        os.path.join(script_dir, ".."),     # Parent directory
        os.path.join(script_dir, "data"),   # data/ subdirectory
    ]
    for d in search_dirs:
        for f in os.listdir(d):
            if filename_pattern.lower() in f.lower():
                return os.path.join(d, f)
    return None
```

### Pattern: Requirement Parser

This is game-specific and often the most complex parsing code. Use regex for structured patterns, fallbacks for free text:

```python
import re

def parse_requirement_text(text: str) -> dict:
    """Parse free-text requirement into structured dict."""
    req = {}
    text_lower = text.lower().strip()

    # Example: "3x Warriors" -> {"factions": {"WAR": 3}}
    faction_pattern = r'(\d+)x?\s*(warriors?|mages?|rogues?)'
    factions = {}
    for match in re.finditer(faction_pattern, text_lower):
        count = int(match.group(1))
        faction_name = match.group(2).strip()
        factions[normalize_faction(faction_name)] = count
    if factions:
        req["factions"] = factions

    # Example: "Sum >= 12" -> {"sum_min": 12}
    sum_match = re.search(r'sum\s*[>≥]=?\s*(\d+)', text_lower)
    if sum_match:
        req["sum_min"] = int(sum_match.group(1))

    # ... more patterns as needed for the specific game

    return req
```

Invest time here. A buggy parser produces subtly wrong simulation data that's hard to detect.

---

## Requirement Checker

Validates whether a set of components meets a requirement. This module is pure logic — no state, no side effects.

### Pattern: Check Function

```python
def check_requirements(cards: list, requirements: dict) -> bool:
    """Check if cards satisfy all requirements. Returns True/False."""

    if "card_count" in requirements:
        if len(cards) != requirements["card_count"]:
            return False

    if "factions" in requirements:
        if not _check_factions(cards, requirements["factions"]):
            return False

    if "sum_min" in requirements:
        if sum(c.rank for c in cards) < requirements["sum_min"]:
            return False

    # ... more checks

    return True
```

### Pattern: Best Combo Finder

For AI use — find the optimal set of cards to meet a requirement:

```python
from itertools import combinations

def find_best_combo(hand: list, requirements: dict) -> list:
    """Find the card combination that meets requirements using fewest/weakest cards."""
    card_count = requirements.get("card_count", len(hand))

    for combo in combinations(hand, card_count):
        if check_requirements(list(combo), requirements):
            return list(combo)
    return None
```

### Pattern: Completable Scan

Check all available objectives against a player's hand:

```python
def find_completable(hand: list, objectives: list) -> list:
    """Return list of (objective, best_cards) for everything the hand can complete."""
    results = []
    for obj in objectives:
        combo = find_best_combo(hand, obj.requirements)
        if combo:
            results.append((obj, combo))
    return results
```

---

## config.json

Organize all tunable parameters by category. Include per-player-count variants where rules differ.

### Pattern: Config Structure

```json
{
  "game_rules": {
    "victory_threshold": {
      "2_player": 25,
      "3_player": 30,
      "4_player": 30
    },
    "starting_resources": {
      "2_player": [3, 4],
      "3_player": [3, 4, 4],
      "4_player": [3, 4, 4, 5]
    },
    "hand_limit": 8,
    "market_size": 4,
    "action_costs": {
      "basic_action": 0,
      "special_action": 5,
      "premium_action": 3
    }
  },
  "component_types": {
    "TYPE_A": "Display Name A",
    "TYPE_B": "Display Name B"
  }
}
```

### Pattern: Config Access in Game State

Use a player-count key for lookups:

```python
class GameState:
    def __init__(self, config, num_players, ...):
        self.config = config
        self.rules = config["game_rules"]
        self.pkey = f"{num_players}_player"  # "3_player"

    def get_starting_resources(self, seat):
        return self.rules["starting_resources"][self.pkey][seat]
```

### Pattern: CLI Override

Let command-line flags override config values without editing the file:

```python
if args.wipe_cost is not None:
    config["game_rules"]["wipe_jumbotron"]["cost"] = args.wipe_cost
```

---

## game_state.py

The largest and most important file. Every game action is a method that validates preconditions, mutates state, and returns a result dict.

### Pattern: Player Dataclass

```python
@dataclass
class Player:
    id: int
    hand: List = field(default_factory=list)
    resources: int = 0
    score: int = 0
    completed: List = field(default_factory=list)

    @property
    def total_score(self) -> int:
        return self.score + self.bonus_score

    def __repr__(self):
        return f"P{self.id}(Score:{self.score} Hand:{len(self.hand)} Res:{self.resources})"
```

### Pattern: GameState Constructor

```python
class GameState:
    def __init__(self, config, num_players, seed=None,
                 cards=None, use_optional_deck=True):
        self.config = config
        self.rules = config["game_rules"]
        self.num_players = num_players
        self.rng = random.Random(seed)   # SEEDED RNG — critical
        self.seed = seed
        self.pkey = f"{num_players}_player"

        # Build and shuffle decks
        self.main_deck = Deck(build_deck(config))
        self.main_deck.shuffle(self.rng)

        # Board state
        self.market: List = []
        self.display: List = []

        # Players
        self.players: List[Player] = []
        self.current_player_idx: int = 0
        self.turn_number: int = 0

        # Game flags
        self.game_over: bool = False
        self.endgame_triggered: bool = False

        # Logging
        self.log: List[str] = []
```

### Pattern: Action Method

Every action follows the same structure:

```python
def action_draft(self, player: Player, slot_index: int) -> dict:
    """Draft a card from the market."""
    # 1. Validate preconditions
    if slot_index >= len(self.market):
        return {"success": False, "error": "Invalid slot"}

    cost = self.rules["slot_pricing"][slot_index]
    if player.resources < cost:
        return {"success": False, "error": f"Need {cost} resources"}

    # 2. Execute state changes
    card = self.market[slot_index]
    bonus = self.market_bonuses[slot_index]

    player.resources -= cost
    player.resources += bonus
    player.hand.append(card)

    # 3. Resolve side effects (market refill, etc.)
    self._refill_market(slot_index)

    # 4. Log and return result
    self._log(f"P{player.id} drafted {card} from slot {slot_index} for {cost}")
    return {
        "success": True,
        "action": "draft",
        "card": card,
        "cost": cost,
        "bonus_collected": bonus,
        "slot": slot_index
    }
```

### Pattern: Setup with AI Choices

Some games have draft-style setup where players make choices. Support this with callback functions:

```python
def setup_with_choices(self, keep_fn=None, draft_fn=None):
    """Setup with AI-driven initial choices."""
    # Create players
    for i in range(self.num_players):
        p = Player(id=i, resources=self.get_starting_resources(i))
        self.players.append(p)

    # Deal starting hands with choice
    for player in self.players:
        dealt = self.main_deck.draw(self.rules["starting_deal"])
        if keep_fn:
            keep, discard = keep_fn(player, dealt, self)
        else:
            keep = dealt[:self.rules["starting_keep"]]
            discard = dealt[self.rules["starting_keep"]:]
        player.hand = list(keep)
        self.main_deck.add_to_bottom(discard)
```

### Pattern: End of Turn

Handle cleanup, triggered effects, and win condition checks:

```python
def end_turn(self, player: Player) -> dict:
    """End-of-turn cleanup: hand limit, triggered effects, win check."""
    results = {"discards": [], "triggered": None, "game_ending": False}

    # Hand limit enforcement
    limit = self.rules["hand_limit"]
    while len(player.hand) > limit:
        # Discard weakest card (AI decides elsewhere, this is fallback)
        weakest = min(player.hand, key=lambda c: c.power)
        player.hand.remove(weakest)
        results["discards"].append(weakest)

    # Win condition check
    threshold = self.rules["victory_threshold"][self.pkey]
    if player.score >= threshold and not self.endgame_triggered:
        self.endgame_triggered = True
        self.endgame_trigger_player = player.id
        results["game_ending"] = True

    # Advance turn
    self.current_player_idx = (self.current_player_idx + 1) % self.num_players
    self.turn_number += 1

    return results
```

---

## run_simulation.py

### Pattern: Single Game Runner

```python
def run_single_game(config, cards, num_players, seed, max_turns=200,
                    player_configs=None) -> dict:
    """Run one game, return stats dict."""
    game = GameState(config, num_players, seed=seed, cards=cards)

    # Create AIs
    ais = []
    for i in range(num_players):
        if player_configs and i < len(player_configs):
            pc = player_configs[i]
            ais.append(HeuristicAI(skill=pc.get("skill", 1.0),
                                   style=pc.get("style", "balanced"),
                                   aggression=pc.get("aggression", 0.5)))
        else:
            ais.append(HeuristicAI(rng_seed=seed + i * 1000))

    game.setup_with_choices(
        keep_fn=lambda p, d, g: ais[p.id].choose_starting_hand(p, d, g),
    )

    # Tracking
    action_counts = defaultdict(lambda: defaultdict(int))
    stagnation_turns = 0
    turn_count = 0

    while not game.game_over and turn_count < max_turns:
        player = game.get_current_player()
        ai = ais[player.id]
        action = ai.choose_action(player, game)

        # Execute and track...
        action_counts[player.id][action["type"]] += 1
        result = execute_action(game, player, action)

        # Track stagnation, completion, etc.
        game.end_turn(player)
        turn_count += 1

    return compile_game_stats(game, action_counts, turn_count, ...)
```

### Pattern: Batch Runner

```python
def run_batch(config, cards, num_games, num_players, start_seed=1,
              max_turns=200, player_configs=None) -> dict:
    """Run N games and aggregate statistics."""
    all_stats = []
    for i in range(num_games):
        stats = run_single_game(config, cards, num_players,
                               seed=start_seed + i, max_turns=max_turns,
                               player_configs=player_configs)
        all_stats.append(stats)

    return aggregate_stats(all_stats)
```

### Pattern: Report Printer

Organize output into clear sections:

```python
def print_report(agg, num_games, num_players):
    print(f"\n{'='*60}")
    print(f"SIMULATION REPORT: {num_games} games, {num_players} players")
    print(f"{'='*60}")

    print(f"\n--- Game Length ---")
    print(f"Average: {agg['avg_turns']:.1f} turns")
    print(f"Range: {agg['min_turns']}–{agg['max_turns']}")

    print(f"\n--- Win Rates ---")
    for pid, rate in agg['win_rates'].items():
        print(f"  Player {pid}: {rate:.1%}")

    # ... more sections
```

### Pattern: CLI

```python
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run batch simulation")
    parser.add_argument("-n", "--num-games", type=int, default=100)
    parser.add_argument("-p", "--players", type=int, default=3)
    parser.add_argument("-s", "--seed", type=int, default=1)
    parser.add_argument("--max-turns", type=int, default=200)
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--config", type=str, default=None)
    parser.add_argument("--json", type=str, default=None)

    # Rule overrides
    parser.add_argument("--some-cost", type=int, default=None)

    # Player configuration
    parser.add_argument("--skill", type=str, default=None,
                       help="Comma-separated skill levels per player")
    parser.add_argument("--styles", type=str, default=None,
                       help="Comma-separated play styles per player")
    parser.add_argument("--preset", type=str, default=None,
                       choices=["experts", "beginners", "mixed", "styles"])

    args = parser.parse_args()
```

---

## narrate_game.py

### Pattern: Narrated Game Wrapper

Wrap the game state to capture AI thinking alongside actions:

```python
class NarratedGame:
    def __init__(self, config, num_players, seed, cards, player_configs=None):
        self.game = GameState(config, num_players, seed=seed, cards=cards)
        self.ais = [...]  # Create AIs
        self.narrative = []  # List of narrative blocks

    def play(self):
        """Play the full game, collecting narrative."""
        self._narrate_setup()

        while not self.game.game_over:
            player = self.game.get_current_player()
            ai = self.ais[player.id]

            self._narrate_turn_header(player)

            # Get AI decision with reasoning
            action, reasoning = ai.choose_action_with_reasoning(player, self.game)
            self._narrate_thinking(reasoning)

            # Execute
            result = self.execute(player, action)
            self._narrate_result(action, result)

            self.game.end_turn(player)

        self._narrate_final_scores()

    def to_markdown(self) -> str:
        return "\n\n".join(self.narrative)
```

### Pattern: AI Thinking Display

```markdown
**Turn 15 — Player 1** (VP: 12 | Hand: 6 | Resources: 4)

> **Considering actions...**
> - Complete "Dragon's Hoard": Need 3 Warriors, have 2. Missing 1. SKIP
> - Complete "Market Day": Need 2 Merchants + Sum >= 8. Have MER-5, MER-3 (sum=8). COMPLETABLE for 6 VP!
> - Draft Slot 1: WAR-7 (free, strong warrior). Score: 4.2
> - Draft Slot 3: MER-10 (cost 2, but enables Dragon's Hoard next turn). Score: 5.1
> **Decision: Complete "Market Day" for 6 VP (best available)**

Commits MER-5 and MER-3 to complete Market Day. +6 VP, +2 resources reward.
Score: P1: 18 VP | P2: 14 VP | P3: 11 VP
```

---

## card_audit.py

### Pattern: Three-Phase Analysis

```python
def run_full_audit(config, cards, games, players, target_keep):
    # Phase 1: Per-card statistics
    report = run_per_card_report(config, cards, games, players)

    # Phase 2: Redundancy clustering
    redundancy = analyze_redundancy(cards)

    # Phase 3: Leave-one-out impact
    loo = run_leave_one_out(config, cards, games, players)

    # Combine into composite ranking
    rankings = compute_composite_rank(report, redundancy, loo, target_keep)
    return rankings
```

Key metrics per card:
- **Completion rate**: How often is this card used/completed across all games?
- **Pressure valve rate**: How often was this the *only* available option? (High = critical for preventing stagnation)
- **Leave-one-out delta**: Does removing this card make the game better or worse?
- **Redundancy group**: Is this card doing the same job as another card?

---

## CLI Design Patterns

### Preset Configurations

Save users from typing long flag lists:

```python
parser.add_argument("--preset", choices=["experts", "beginners", "mixed", "styles"])

# In main():
if args.preset == "experts":
    player_configs = [{"skill": 1.0, "style": "balanced"} for _ in range(num_players)]
elif args.preset == "mixed":
    player_configs = [{"skill": 1.0, "style": "balanced"}]
    player_configs += [{"skill": 0.3, "style": "balanced"} for _ in range(num_players - 1)]
```

### JSON Export

Every tool that produces data should have a `--json` flag:

```python
if args.json:
    with open(args.json, 'w') as f:
        json.dump(stats, f, indent=2, default=str)
    print(f"Stats saved to {args.json}")
```

### Auto-Detect Data Files

```python
def find_config():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(script_dir, "config.json"),
        os.path.join(script_dir, "..", "config.json"),
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return None
```
