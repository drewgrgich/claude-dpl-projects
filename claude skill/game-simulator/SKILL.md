---
name: game-simulator
description: >
  Build a complete Python simulation engine for tabletop games (card games, board games, dice games)
  to playtest and balance rules through AI-vs-AI batch simulation. Use this skill whenever someone
  wants to simulate, playtest, balance, or analyze a tabletop game — even if they just say things like
  "help me balance my game", "test these rules", "which cards should I cut", "is this mechanic fair",
  "run some playtests", or "build a simulator". Also trigger when someone has an existing game
  simulator and wants to add features like AI skill levels, play style profiles, narrated games,
  or card auditing tools. If the conversation involves tabletop game design and quantitative analysis,
  this skill applies.
---

# Game Simulator Skill

Build Python simulation engines that let tabletop game designers answer balance questions with data instead of guesswork. The simulator plays hundreds of AI-vs-AI games, collects metrics, and surfaces the numbers that matter: win rate spreads, game length distributions, stagnation detection, action frequency, and component-level impact analysis.

This skill encodes a proven architecture developed through extensive iteration on a card game simulator. The patterns generalize to card games, board games, dice games, and hybrid designs.

## When to Read Reference Files

This skill has two reference files in the `references/` directory:

- **`architecture.md`** — The full module breakdown, file-by-file responsibilities, and code patterns. **Read this first** when starting a new simulator from scratch or when you need to understand how the pieces fit together.
- **`ai-design.md`** — How to build heuristic AI players with tunable skill levels, play style profiles, and aggression axes. **Read this** when building or extending the AI player, or when the user asks about modeling different player types or skill levels.

You don't need to read both for every task. If someone just wants to add a new action to an existing simulator, `architecture.md` is enough. If they want to test "does an expert beat beginners?", `ai-design.md` is what you need.

## Core Philosophy

**Config-driven rules.** Every tunable number lives in `config.json`, not in code. When the user says "what if the wipe costs 3 instead of 5?", they can change one number and re-run — or use a CLI flag to override it without editing the file at all. This is the single most important design decision in the whole system. Hard-coding rule values into game logic makes iteration painful; externalizing them makes it effortless.

**CSV-based card data.** Card definitions (stats, requirements, costs, rewards) live in CSV files that the user can edit in any spreadsheet tool. The simulator loads them at startup. This separation means game designers can tweak card values without touching Python, and programmers can improve the engine without breaking card data.

**Seeded randomness everywhere.** Every random decision flows through a seeded `random.Random` instance. Same seed = same game, always. This makes debugging possible (reproduce a weird game by re-running its seed), enables fair A/B comparisons (same seeds across two rule configs), and lets narrated games be replayed exactly.

**Heuristic AI, not random play.** The AI should make reasonable decisions that resemble how a human would play. Random play produces meaningless balance data. The AI doesn't need to be optimal — it needs to be good enough that when the simulation says "this card is never completed," you can trust that it's actually too hard, not just that the AI is too dumb to find it.

**Comprehensive metrics collection.** The batch runner doesn't just report who won. It tracks everything: per-action frequency, per-component completion rates, economy flow (resources earned vs spent), stagnation (turns where no progress is possible), game length distributions, and win rate spreads across player positions. More data means more questions you can answer without re-running.

## The Build Process

When a user describes their game, follow this sequence. Don't try to build everything at once — each phase should be working and testable before moving to the next.

### Phase 1: Understand the Game

Interview the user about their game. You need to understand:

1. **Components** — What types of cards/pieces/tokens exist? What properties does each have? (e.g., "cards have a faction, a rank 0-10, and some are special")
2. **Setup** — How does a game begin? What gets dealt/placed/distributed?
3. **Turn structure** — What can a player do on their turn? List every possible action.
4. **Win condition** — How does the game end? How is the winner determined?
5. **Economy** — What resources exist? How are they earned and spent?
6. **Market/public state** — Is there a shared market, board, or display that changes during play?

If the user already has a ruleset document, read it carefully and extract these answers. Ask about anything ambiguous — the simulator needs precise rules, not fuzzy descriptions.

### Phase 2: Data Layer

Build the card/component definitions and data loading first.

**`cards.py`** — Dataclasses for every component type. Keep them simple: just the properties each component has, plus convenience methods (like `is_free_agent` or `total_cost`). Include `__hash__` and `__eq__` if components need to be compared or stored in sets.

**`Deck` class** — A generic container that supports shuffle (with seeded RNG), draw, peek, add-to-bottom, and add-to-top. Reuse this for every deck/pile/bag in the game.

**CSV parser** — Load card data from CSVs. Keep the CSV format human-friendly (column names match the game's terminology). The parser converts free-text fields (like "3x Magicians + Sum >= 12") into structured dicts the engine can evaluate programmatically. This parsing step is game-specific and often the trickiest part — invest time getting it right because every other module depends on it.

**`config.json`** — All numeric rules in one file. Organize by category (victory conditions, economy, action costs, market sizes). Include per-player-count variants where rules differ (e.g., 2-player vs 4-player starting resources). Add a `description` field to complex rule groups so the user remembers what they do.

### Phase 3: Game Engine

**`game_state.py`** — The full state machine. This is the largest file and the heart of the simulator.

Structure it as:
- A `Player` dataclass tracking each player's state (hand, resources, score, etc.)
- A `GameState` class that owns all shared state (decks, market, turn counter, flags)
- A `setup()` method that initializes the game from config
- One `action_*()` method per possible player action, each returning a result dict with `success: bool` and relevant details
- An `end_turn()` method handling cleanup (hand limits, triggered effects, win checks)
- A logging system (list of strings) for debugging and narration

Key patterns:
- Actions validate preconditions before executing (can the player afford it? do they have the right cards?)
- Actions return result dicts, never raise exceptions for illegal moves — the AI needs to handle failure gracefully
- State changes are explicit (no hidden side effects — if an action grants resources, it's visible in the result)
- The game state never makes decisions — it only executes what it's told. All decision-making lives in the AI.

### Phase 4: AI Player

**`ai_player.py`** — A heuristic AI that makes reasonable decisions.

Read `references/ai-design.md` for the full design, but the key ideas are:

- **Priority-based action selection**: evaluate all legal actions, pick the best one. Don't use a decision tree — use a scoring system where each action gets a numeric score and the highest wins.
- **Three tunable axes**: skill (mistake frequency), style (strategic preferences), aggression (spending tendency). These produce meaningfully different play patterns that help validate the game works for different player types.
- **Action-specific evaluation methods**: each action type gets its own scoring function that considers the current game state. For example, "should I draft this card?" considers card value + resource bonus - cost + "does this card help me complete an available objective?"

### Phase 5: Batch Runner

**`run_simulation.py`** — Run N games and aggregate statistics.

Structure:
- `run_single_game()` — plays one complete game, returns a stats dict
- `run_batch()` — loops over seeds, calls `run_single_game()`, aggregates results
- `print_report()` — formats the aggregated stats into a readable console report
- CLI with argparse — flags for game count, player count, seed, max turns, config overrides, and JSON export

The stats dict from each game should capture everything interesting: winner, per-player VP breakdown, action counts, component completion rates, game length, stagnation metrics, economy metrics, and any game-specific data points.

CLI override flags are important. The user should be able to test "what if this costs 4 instead of 5?" without editing config.json — just pass `--some-cost 4` on the command line. This makes parameter sweeps trivial:
```bash
for cost in 3 4 5 6; do
  python run_simulation.py -n 200 --wipe-cost $cost --json results_cost_${cost}.json
done
```

### Phase 6: Narration Engine

**`narrate_game.py`** — Generate a detailed Markdown file of a single game session.

This plays one game with full AI thinking exposed: what options were considered, how each was scored, why the winning action was chosen. The output reads like a play-by-play commentary. It's invaluable for:
- Catching bugs (the AI did something obviously wrong)
- Validating feel (does the game flow naturally? are there awkward moments?)
- Explaining decisions to the game designer ("here's why the AI never uses that action")

Use blockquotes (`>`) for AI thinking to visually separate it from game events.

### Phase 7: Analysis Tools (As Needed)

Build these when the user needs them, not upfront:

**Card/component audit tool** — Rank every card by game impact using three analyses:
1. Per-card statistics (completion rate, average timing, which player types use it)
2. Redundancy clustering (which cards fill the same role?)
3. Leave-one-out testing (remove each card, measure impact on game quality)

Combine into a composite score with keep/cut recommendations.

**Parameter sweep scripts** — Automate testing multiple values of a rule parameter and comparing results.

**Comparison reports** — Side-by-side stats from two configurations highlighting meaningful differences.

## Output Standards

- All Python files use type hints and docstrings
- No external dependencies — standard library only (the user shouldn't need to install anything)
- Every file is independently runnable where it makes sense (batch runner has a `__main__` block, narration engine has a `__main__` block)
- CLI flags use argparse with clear help text
- JSON export available for any tool that produces data
- Config auto-detection: tools look for config.json and CSV files relative to their own location, so the user doesn't have to specify paths for the common case

## Metrics That Matter

When reporting simulation results, focus on these categories:

**Game Health**: average game length, turn limit abort rate, standing ovation / natural ending rate
**Balance**: win rate spread across player positions, VP standard deviation, first-player advantage
**Pacing**: turns to first score, stagnation turns and worst streak, action frequency distribution
**Economy**: resource flow (earned vs spent per player), market draft distribution by slot/price
**Components**: per-card completion rates, never-used components, most/least popular items
**AI Behavior**: action type distribution per style, event completion by tier per style, resource management patterns

Always highlight anything that looks like a problem: a card that's never completed, a player position that wins 40%+ in a 4-player game, stagnation streaks above 10 turns, or an action type that's used less than 2% of the time.

## Common Pitfalls

**Don't over-engineer the AI.** A heuristic AI that makes reasonable moves is more valuable than a perfect optimizer. The goal is to approximate human play well enough that balance data is trustworthy — not to solve the game.

**Don't skip the requirement parser.** If the game has cards with text-based requirements (like "3 cards from the same faction with sum >= 12"), invest in a solid parser. A buggy parser produces buggy simulation data, and the bugs are hard to spot because the numbers look plausible.

**Don't hardcode rule values.** If you find yourself writing `if shinies >= 5:` instead of `if shinies >= config["wipe_cost"]:`, stop and fix it. Every hardcoded number is a parameter the user can't tune.

**Don't forget seeded RNG.** If any random call uses `random.random()` instead of `self.rng.random()`, reproducibility breaks silently. Use the seeded instance everywhere.

**Don't collect too few metrics.** It's cheap to track extra counters during simulation and expensive to re-run hundreds of games because you forgot to measure something. When in doubt, track it.
