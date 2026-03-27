# Contests of Chaos — Playtest Simulator

A modular Python simulation engine for playtesting and balancing the card game **Contests of Chaos**. Run hundreds of AI-vs-AI games to analyze balance metrics, or generate narrated single-game sessions with full decision-tree analysis.

## Architecture

```
simulator/
├── config.json         # All tunable game rules
├── cards.py            # Card dataclasses (Recruit, Event, Playbook) and Deck
├── event_parser.py     # CSV loaders for Events and Playbooks
├── event_checker.py    # Event requirement validation and card matching
├── game_state.py       # Full game state machine with all 6 actions
├── ai_player.py        # Heuristic AI with configurable aggression
├── run_simulation.py   # Batch game runner with stats and reporting
├── narrate_game.py     # Single-game narration engine (Markdown output)
└── card_audit.py       # Card culling tool — rank events/playbooks by game impact
```

The simulator also expects two CSV data files in the parent directory:

- `contests-of-chaos-events copy.csv` — 37 Event Cards (Tiers 1–6)
- `contests-of-chaos-playbooks copy.csv` — 24 Playbook Cards

These are auto-detected. You can also point to custom CSVs with CLI flags.

---

## Quick Start

All commands are run from the `simulator/` directory.

### Run a 100-game batch simulation

```bash
python run_simulation.py
```

### Generate a narrated game session

```bash
python narrate_game.py -s 42 -o ../narrated_game.md
```

---

## Batch Simulation (`run_simulation.py`)

Runs multiple AI-vs-AI games and produces a balance report covering win rates, VP distributions, action frequency, event completion by tier, stagnation metrics, and more.

### Usage

```bash
python run_simulation.py [options]
```

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `-n`, `--num-games` | 100 | Number of games to simulate |
| `-p`, `--players` | 3 | Number of players (2–4) |
| `-s`, `--seed` | 1 | Starting random seed |
| `--max-turns` | 200 | Max turns per game before aborting |
| `-v`, `--verbose` | off | Print each game's summary |
| `--config` | auto | Path to `config.json` |
| `--events` | auto | Path to events CSV |
| `--playbooks` | auto | Path to playbooks CSV |
| `--no-wipe` | — | Disable Jumbotron wipe entirely |
| `--wipe-cost` | (from config) | Override wipe Shiny cost |
| `--min-hand` | (from config) | Override minimum hand size for wipe (0 to disable) |
| `--post-wipe-cost` | (from config) | Override post-wipe event completion surcharge (0 to disable) |
| `--no-playbooks` | — | Disable the Playbook deck |
| `--json` | — | Save raw stats to a JSON file |

### Examples

**Standard 200-game run with 3 players:**
```bash
python run_simulation.py -n 200 -p 3
```

**Compare wipe costs (run each, save JSON for later analysis):**
```bash
python run_simulation.py -n 200 --wipe-cost 3 --json ../wipe_cost_3.json
python run_simulation.py -n 200 --wipe-cost 4 --json ../wipe_cost_4.json
python run_simulation.py -n 200 --wipe-cost 5 --json ../wipe_cost_5.json
python run_simulation.py -n 200 --wipe-cost 6 --json ../wipe_cost_6.json
```

**Test wipe with hand minimum and surcharge:**
```bash
python run_simulation.py -n 200 --wipe-cost 4 --min-hand 5 --post-wipe-cost 2 --json ../wipe_balanced.json
```

**Playbooks on vs. off:**
```bash
python run_simulation.py -n 200 --json ../playbooks_on.json
python run_simulation.py -n 200 --no-playbooks --json ../playbooks_off.json
```

**2-player mode (uses different VP threshold and starting Shinies):**
```bash
python run_simulation.py -n 200 -p 2
```

**Verbose single-game debugging:**
```bash
python run_simulation.py -n 1 -s 42 -v
```

### Report Output

The batch report includes:

- **Game Length** — mean, min, max, median turns; aborted game count
- **Win Rates** — per-player win percentage
- **VP Averages** — total, event, playbook, and events-completed per player
- **Action Frequency** — how often each action type is used per game
- **Events by Tier** — completion rate by tier (are high-tier events reachable?)
- **Top/Bottom Events** — most and least completed events; never-completed events
- **Jumbotron Wipes** — total, per-game average, max in a single game
- **Stagnation** — turns where no player can complete any event; worst streak
- **First Event Turn** — how quickly the first event gets completed
- **Lineup Draft Distribution** — which slots get drafted most (pricing balance)
- **Standing Ovation Rate** — how often the VP threshold triggers the endgame

---

## Narrated Game (`narrate_game.py`)

Generates a detailed Markdown file of a single game session with full AI thinking shown. Useful for reading through a "play session" to see how the game flows, identify awkward turns, and validate that the AI is making reasonable decisions.

### Usage

```bash
python narrate_game.py [options]
```

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `-s`, `--seed` | 42 | Random seed (same seed = same game) |
| `-p`, `--players` | 3 | Number of players (2–4) |
| `-o`, `--output` | stdout | Output Markdown file path |
| `--max-turns` | 200 | Max turns before aborting |
| `--config` | auto | Path to `config.json` |
| `--events` | auto | Path to events CSV |
| `--playbooks` | auto | Path to playbooks CSV |
| `--wipe-cost` | (from config) | Override wipe cost |
| `--no-playbooks` | — | Disable playbooks |

### Examples

**Generate a narrated game and save it:**
```bash
python narrate_game.py -s 7 -p 3 -o ../narrated_playtest_seed7.md
```

**Try different seeds to find interesting games:**
```bash
for seed in 1 7 13 42 99; do
  python narrate_game.py -s $seed -o ../narrated_seed${seed}.md
done
```

**Narrated game without playbooks:**
```bash
python narrate_game.py -s 42 --no-playbooks -o ../narrated_no_playbooks.md
```

### What the Narration Shows

Each turn includes:

- **Player status** — VP, Shinies, hand contents, playbook
- **AI thinking** (in `> blockquote` format) with full decision analysis:
  - **Event completion:** card-by-card matching, multi-event comparison, playbook synergy alerts
  - **Draft evaluation:** per-slot breakdown with card value, Shiny bonus, cost penalty, and whether drafting enables an event completion
  - **Wipe analysis:** cost check, hand size check, stagnation counter, post-wipe scan results
  - **Scramble/Timeout reasoning:** when and why the AI falls back to these options
- **Action result** — what happened, rewards resolved
- **Score line** — running score after each turn

The setup phase shows card-by-card evaluation for the starting hand draft and playbook selection with scoring adjustments explained.

---

## Tuning the Game (`config.json`)

All game rules are driven by `config.json`. Edit values there to test rule changes without touching code.

### Key Parameters

**Victory and Setup:**
| Parameter | Description |
|-----------|-------------|
| `victory_threshold.3_player` | Event VP needed to trigger Standing Ovation (30) |
| `starting_shinies.3_player` | Starting Shinies per seat position ([3, 4, 4]) |
| `hand_limit` | Maximum hand size (8) |
| `starting_deal` / `starting_keep` | Cards dealt and kept during setup (5 / 3) |

**Economy:**
| Parameter | Description |
|-----------|-------------|
| `slot_pricing` | Cost per Lineup slot ([0, 1, 2, 3]) |
| `scramble_cost.3_player` | Shiny cost to Scramble (2) |
| `timeout_shiny_gain` | Shinies gained on Timeout (1) |
| `shiny_bonus_rate` | Shinies-per-VP conversion at game end (3:1) |
| `shiny_bonus_max` | Max VP from Shiny bonus (3) |

**Jumbotron Wipe:**
| Parameter | Description |
|-----------|-------------|
| `wipe_jumbotron.enabled` | Toggle wipe on/off (true) |
| `wipe_jumbotron.cost` | Shiny cost to wipe (5) |
| `wipe_jumbotron.min_hand_size` | Minimum cards in hand to wipe (5) |
| `wipe_jumbotron.post_wipe_event_cost` | Extra Shiny cost to complete an event the same turn as a wipe (2) |

### Example: Testing a Cheaper Wipe

Edit `config.json`:
```json
"wipe_jumbotron": {
    "enabled": true,
    "cost": 3,
    "min_hand_size": 5,
    "post_wipe_event_cost": 2
}
```

Or override from the command line without editing the file:
```bash
python run_simulation.py -n 200 --wipe-cost 3
```

---

## Updating Card Data

Event and Playbook decks are loaded from CSV files. To change the card pool, edit the CSVs directly.

### Events CSV Format

```
Tier,Name,Requirements,VP,Reward
Tier 1,Scouting Report,"2 of any 1 faction",3,"Take 2 Shinies from the bank."
```

Columns: `Tier`, `Name`, `Requirements` (free text parsed by `event_parser.py`), `VP`, `Reward`

### Playbooks CSV Format

```
Category,Playbook,VP,Trigger,Timing,Flavor
Composition,The Rookie,3,Complete an Event using only Ranks 1-5,Combo,"Who needs experience..."
```

Columns: `Category`, `Playbook`, `VP`, `Trigger`, `Timing` (Combo/Finish/Immediate), `Flavor`

### Adding New Events or Playbooks

1. Add rows to the appropriate CSV
2. For events: ensure the `Requirements` text follows patterns the parser recognizes (faction counts, sums, runs, same-number sets)
3. For playbooks: the trigger text is matched in `game_state.py`'s `_check_playbook_condition()` — new trigger types may need code additions
4. Run a batch simulation to verify the new cards are being completed/scored

---

## Common Comparison Workflows

### Wipe Cost Sweep

Test wipe costs from 3 to 6 with consistent settings:

```bash
for cost in 3 4 5 6; do
  python run_simulation.py -n 200 \
    --wipe-cost $cost --min-hand 5 --post-wipe-cost 2 \
    --json ../wipe_cost_${cost}_tuned.json
done
```

Look at the JSON outputs for: game length, win rate spread, wipe frequency, and stagnation metrics.

### Playbook Impact

```bash
python run_simulation.py -n 200 --json ../with_playbooks.json
python run_simulation.py -n 200 --no-playbooks --json ../without_playbooks.json
```

Compare `vp_averages` — playbooks typically add ~2.4 VP per player (~9% of total) without distorting core strategy.

### Player Count Comparison

```bash
python run_simulation.py -n 200 -p 2 --json ../2player.json
python run_simulation.py -n 200 -p 3 --json ../3player.json
python run_simulation.py -n 200 -p 4 --json ../4player.json
```

### Finding Problematic Events

In the batch report, check:
- **Never-completed events** — requirements may be too hard or too niche
- **Top 10 most completed** — if one event dominates, it may be too easy
- **Events by tier** — Tier 5–6 events should be rare but not impossible

---

## Card Audit (`card_audit.py`)

Ranks every Event and Playbook by game impact to help you decide what to keep when culling the deck down to a target card count. Combines three analyses into a single composite score.

### Usage

```bash
python card_audit.py [options]
```

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--games` | 100 | Games per batch (more = tighter stats, slower) |
| `-p`, `--players` | 3 | Number of players |
| `-s`, `--seed` | 1 | Starting seed |
| `--mode` | full | `full`, `report`, `redundancy`, or `leave-one-out` |
| `--target-events` | — | Number of events to keep (marks rest as CUT) |
| `--target-playbooks` | — | Number of playbooks to keep (marks rest as CUT) |
| `--config` | auto | Path to `config.json` |
| `--events` | auto | Path to events CSV |
| `--playbooks` | auto | Path to playbooks CSV |
| `--json` | — | Save full results to JSON |

### Three Analysis Phases

**Phase 1: Per-Card Report** (`--mode report`) — runs a batch of games and tracks per-card stats: how often each event is completed, average completion turn, which player types favor it, and "pressure valve" rate (how often it was the *only* completable event, meaning it prevented stagnation). For playbooks: draft rate, score rate, and effectiveness when drafted.

**Phase 2: Redundancy Analysis** (`--mode redundancy`) — clusters events by their faction requirements. If multiple events demand the same faction combo, they're flagged as a redundancy group. Within each group, the lower-VP or lower-completion entries are natural cut candidates.

**Phase 3: Leave-One-Out** (`--mode leave-one-out`) — removes each card one at a time, re-runs the batch, and measures the delta on game length, stagnation, win spread, and average VP. Cards whose removal has zero or positive impact are safe cuts. This is the slowest phase (runs N+1 batches).

### Examples

**Quick report to see which cards are dead weight:**
```bash
python card_audit.py --mode report --games 50
```

**Full audit with keep/cut line — keep 30 events and 20 playbooks:**
```bash
python card_audit.py --games 200 --target-events 30 --target-playbooks 20
```

**Just redundancy (instant, no simulation needed):**
```bash
python card_audit.py --mode redundancy
```

**Deep leave-one-out analysis (slow but thorough):**
```bash
python card_audit.py --mode leave-one-out --games 100 --json ../card_audit_loo.json
```

### Reading the Output

The report produces a ranked table for events and playbooks:

- **Comp%** — completion rate across all games (higher = more relevant to gameplay)
- **PV%** — "pressure valve" rate (how often it was the only completable event — high PV% cards prevent stagnation)
- **LOO** — leave-one-out impact (positive = removing hurts the game; negative = removing helps)
- **Score** — composite ranking combining all signals
- **If Drafted** (playbooks) — scoring rate when a player actually chose this playbook

Cards at the bottom of the rankings with 0% completion, negative LOO, or high redundancy are your strongest cut candidates. Cards near the top with high PV% are critical to keep even if their VP seems low.

---

## AI Player Details

The `HeuristicAI` uses a priority-based decision system:

1. **Complete an event** if possible (highest VP first, modified by style)
2. **Wipe Jumbotron** if stuck (patience varies by style), can afford it, meets hand size requirement
3. **Draft from Lineup** — evaluates each slot by card value + Shiny bonus - cost penalty, with a large bonus if drafting enables an event completion
4. **Scramble** if the Lineup is weak (threshold varies by style) and resources allow
5. **Timeout** as fallback — gains 1 Shiny, optionally discards weak cards and flushes Jumbotron Slot 1

### Three Configuration Axes

**Skill** (0.0–1.0): Controls how many mistakes the AI makes. At 1.0 (expert), play is optimal. Lower values introduce realistic beginner mistakes: missing completable events (up to 40% miss rate at skill=0.0), misjudging card value (noise on all scores), fixating on one faction, undervaluing Free Agents, and making bad wipe timing decisions.

**Style** (balanced, rush, economy, control): Determines strategic priorities:

- **Balanced** — well-rounded default play
- **Rush** — speed strategy; prioritizes Tier 1–2 events, uses fewer cards per event, drafts more aggressively, wipes after just 2 turns stuck
- **Economy** — resource hoarder; waits for Tier 4–6 payoffs, reluctant to spend on wipes or scrambles, holds cards longer
- **Control** — disruptive; wipes early and often (including to deny opponents high-VP events), scrambles aggressively, flushes Jumbotron events worth 7+ VP on timeout

**Aggression** (0.0–1.0): Spending tendency, layered on top of style. Higher = more willing to pay for expensive Lineup slots.

### CLI Flags

Both `run_simulation.py` and `narrate_game.py` accept:

| Flag | Description |
|------|-------------|
| `--preset experts` | All players at skill=1.0, balanced style |
| `--preset beginners` | All players at skill=0.3, balanced style |
| `--preset mixed` | P0 expert, rest beginners |
| `--preset styles` | All expert, P0=rush, P1=economy, P2=control |
| `--skill 1.0,0.5,0.3` | Set skill per player (comma-separated) |
| `--styles rush,economy,balanced` | Set style per player (comma-separated) |

Flags can be combined: `--skill 1.0,0.3,0.3 --styles balanced,rush,economy`

### Example Scenarios

**Does an experienced player dominate beginners?**
```bash
python run_simulation.py -n 200 --preset mixed
```

**Which play style wins most often?**
```bash
python run_simulation.py -n 200 --preset styles
```

**Is the game still fun for a table of new players?**
```bash
python run_simulation.py -n 200 --preset beginners
```

**One expert rusher vs two intermediate economy players:**
```bash
python run_simulation.py -n 200 --skill "1.0,0.6,0.6" --styles "rush,economy,economy"
```

**Narrate a game with personality:**
```bash
python narrate_game.py -s 42 --preset styles -o ../narrated_styles.md
```

---

## Requirements

- Python 3.8+
- No external dependencies (standard library only)
