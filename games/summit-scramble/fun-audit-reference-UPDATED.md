# Fun Audit — Measuring Subjective Fun Through Simulation Data

A framework for quantifying how "fun" a tabletop game feels by measuring 7+ dimensions that correlate with player engagement. This isn't a replacement for playtesting with real humans — it's a way to catch fun-killers (dead turns, blowouts, no decisions) before you put the game in front of people.

## Table of Contents

1. [When to Use This](#when-to-use-this)
2. [The 7 Fun Dimensions](#the-7-fun-dimensions)
3. [Genre-Specific Tension Metrics](#genre-specific-tension-metrics)
4. [Implementation Pattern](#implementation-pattern)
5. [Grading System](#grading-system)
6. [Interpreting Results & Recommendations](#interpreting-results--recommendations)
7. [Adapting to Different Game Types](#adapting-to-different-game-types)

---

## When to Use This

Build a fun audit when:
- The simulator is already working and producing valid game data (Phases 1–5 from the main skill are done)
- The user asks about "fun", "engagement", "player experience", "feel", or "is this game interesting?"
- Balance metrics look fine but you suspect the game might still be boring
- The user wants to compare two rule variants on subjective feel, not just win rates

Don't build it as the first thing — get the game engine and batch runner working first. Fun metrics depend on having a solid, bug-free simulation to measure.

---

## The 7 Fun Dimensions

### 1. Decision Density

**What it measures:** How many meaningful choices a player faces each turn.

**Why it matters:** A game where every turn is automatic ("there's only one good move") feels like watching, not playing. Players need at least 2 meaningfully different options most of the time to feel engaged.

**How to measure:**
Before each turn, count the distinct action categories available to the current player. What counts as "meaningful" is game-specific, but the pattern is:

```
choices = {
    "move_options":    count of distinct legal moves/placements,
    "action_options":  count of distinct action types available,
    "score_options":   count of different scoring plays available,
    "power_options":   count of usable special abilities,
    "trade_options":   1 if trading is possible, 0 if not,
}
total = sum(min(v, 1) for v in choices.values())  # binary per category
```

The binary-per-category approach prevents "8 face-down cards to flip" from inflating the count — what matters is that flipping is an option, not how many positions exist. But also track the raw counts for the detailed breakdown.

**Key metrics:**
- `avg_meaningful_choices`: mean total choices per turn across all games
- `pct_turns_with_2plus_choices`: fraction of turns where total >= 2
- `avg_by_type`: breakdown by choice category

### 2. Comeback Potential

**What it measures:** Whether trailing players can still win.

**Why it matters:** If the leader after the first round always wins, trailing players check out mentally. The game needs enough variance and catch-up opportunities that being behind doesn't mean the game is over.

**How to measure:**
- Track the leader after the first major phase (shift/round/epoch)
- Check whether that leader ends up winning
- Track lead changes throughout the game
- Track whether the last-place player at the midpoint can recover to top 2

**Key metrics:**
- `comeback_rate`: fraction of games where the early leader loses
- `avg_lead_changes`: mean lead changes per game
- `last_to_top2_rate`: fraction of games where last-at-halftime finishes in top 2

### 3. Dead Turn Rate

**What it measures:** How often a player's turn produces zero progress.

**Why it matters:** A dead turn is a turn where the player gained no VP, collected no resources, scored no objectives, and performed no meaningful actions. It's the game saying "you wasted your time." Occasional dead turns create tension; frequent ones kill engagement.

**How to measure:**
Define "dead" for your game. A reasonable default: no VP gained AND no resources collected AND no objectives scored AND no special abilities used AND no interaction with other players. The exact criteria depend on the game — in some games, drawing a card IS progress; in others, it's filler.

**Key metrics:**
- `avg_dead_turn_rate`: fraction of turns that are dead, averaged across games
- `max_dead_turn_rate`: worst single game
- `pct_games_with_zero_dead`: fraction of games with no dead turns at all

### 4. Blowout Rate

**What it measures:** How often the final scores are lopsided.

**Why it matters:** Close games are more fun than stomps. If the winner regularly doubles the loser's score, trailing players knew they'd lost long before the game ended.

**How to measure:**
- Winner's margin over second place
- Ratio of highest to lowest score (the "blowout ratio")
- Fraction of games where the blowout ratio exceeds 2.0x

**Key metrics:**
- `avg_winner_margin`: mean VP gap between 1st and 2nd
- `blowout_rate_2x`: fraction of games where best score >= 2x worst score
- `close_game_rate`: fraction of games where margin <= some threshold (e.g., 3 VP)

### 5. Tension Curve

**What it measures:** Whether excitement builds toward the end of the game.

**Why it matters:** The best games build to a climax. If 75% of scoring happens in the first round and the last round is a formality, the ending feels flat. Ideally, VP per round should be ascending — more happens as the game progresses.

**How to measure:**
- Track total VP scored per round/shift/phase
- Compute average VP per player per round
- Check if the curve is ascending (each round >= previous)
- Calculate what percentage of total VP comes from the final round

**Key metrics:**
- `shift_N_avg_vp`: average VP per player in each round
- `ascending`: boolean — does VP increase each round?
- `final_shift_pct_of_total`: what % of total VP comes from the last round

**Target:** Final round should account for 33%+ of total VP in a 3-round game (even split would be 33%). Ascending curve with final round at 38%+ earns an A.

> **Genre Warning:** This volume-based metric is structurally misleading for shedding/racing games. See [Genre-Specific Tension Metrics](#genre-specific-tension-metrics) below.

### 6. Power Fantasy Moments

**What it measures:** How often a player has a "wow" turn — a big scoring moment that feels exciting.

**Why it matters:** Players remember the highs. A game where every turn scores 2-3 VP is balanced but forgettable. A game where most turns score 1-2 VP but occasionally you land a 12-VP combo is memorable and exciting. These "power fantasy" moments are what players talk about after the game.

**How to measure:**
Define a VP threshold for a "wow" turn. A reasonable default: 10+ VP in a single turn, or completing the game's most difficult objective. The threshold should be roughly 3x the average VP-per-turn.

**Key metrics:**
- `avg_wow_turns_per_game`: mean count of wow turns per game
- `pct_games_with_wow`: fraction of games that have at least one
- `avg_wow_rate`: wow turns as a fraction of all turns

### 7. Interaction Rate

**What it measures:** How much players affect each other during the game.

**Why it matters:** A game where players just optimize in parallel is a puzzle, not a social game. Interaction — trading, stealing, blocking, competing for shared resources — is what makes multiplayer games feel multiplayer.

**How to measure:**
Count events where one player directly affects another: trades, targeted abilities (steal/swap), blocking moves, shared resource competition. The exact events depend on the game's mechanics.

**Key metrics:**
- `avg_interactions_per_game`: mean count of interaction events
- `avg_interaction_rate`: interactions per turn
- `pct_games_with_interaction`: fraction of games where any interaction occurs

---

## Genre-Specific Tension Metrics

The default tension curve (dimension 5) measures *volume* of progress per game phase. This works well for scoring games, engine builders, and area control — any game where the amount of stuff happening can genuinely increase over time.

**But it fails for an entire class of games** where the "resource" being spent is finite and depleting. This section documents the problem, the fix, and how to choose the right metric.

### The Problem: Depleting-Resource Games

In a hand-shedding game (Big Two, President, Tichu), players start with N cards and the game ends when someone empties their hand. Progress = cards removed from hand. The total cards that *can* be shed decreases every turn — you can't shed more cards than you have left. A volume-based tension curve will *always* show a mid-game peak and a declining final third, because the pool of remaining progress is shrinking. This is a mathematical certainty, not a design flaw.

The same problem applies to:
- **Race games** (Parcheesi, racing card games) — pieces can only move forward, remaining distance shrinks
- **Auction/spending games** — if the resource being spent is non-renewable
- **Countdown/timer games** — anything where a finite counter ticks toward zero

Grading these games on volume-based tension will always produce a C or worse, creating a misleading signal that the endgame is flat. In practice, shedding-game endgames can be the most exciting part — the question is whether the players are bunched together near the finish, not whether they're shedding a lot of cards.

### The Fix: Racing Tension (Finish Proximity)

For depleting-resource games, supplement or replace the volume curve with **Racing Tension**, which measures what actually creates endgame excitement: *how close are multiple players to finishing at the same time?*

**How to measure:**

Track two things during the final 40% of the game (measured by overall progress toward the win condition):

1. **Late-game spread:** Each turn, compute the gap between the largest and smallest "remaining distance" among active players (hand size, distance to goal, tokens left). Lower spread = tighter race.

2. **Photo finish rate:** What fraction of late-game turns have 2+ players simultaneously within a threshold of finishing? For hand-shedding games, "within 3 cards of going out" is a good threshold. For race games, "within 2-3 moves of the goal."

**Key metrics:**
- `avg_late_game_spread`: mean spread among active players when progress >= 60%
- `avg_photo_finish_rate`: fraction of late-game turns with 2+ players near finish
- `avg_near_finish_turns`: mean count of photo-finish turns per game
- `pct_games_with_photo_finish`: fraction of games with at least one photo finish moment

**Grading thresholds:**

| Grade | Criteria |
|-------|----------|
| A | Photo finish rate >= 50% AND avg late spread <= 3 |
| B | Photo finish rate >= 35% OR avg late spread <= 3 |
| C | Photo finish rate >= 20% OR avg late spread <= 5 |
| D | Photo finish rate >= 10% |
| F | Photo finish rate < 10% |

### How to Choose the Right Metric

**Use volume-based tension curve (default dimension 5) when:**
- The game has a scoring system (VP, gold, prestige) that accumulates
- Progress can increase or decrease between phases
- There's no structural ceiling on how much can happen per turn in late game
- Examples: engine builders, set collection, area majority, auction games

**Use Racing Tension when:**
- The primary win condition is resource depletion (empty hand, reach finish, spend all tokens)
- Total possible progress per turn is bounded by remaining resources
- The "pool" of remaining stuff-to-do shrinks as the game progresses
- Examples: climbing/shedding games, race-to-the-end games, countdown games

**Use both (report both, pick one for scoring) when:**
- The game mixes scoring with racing (e.g., a race with VP scoring along the way)
- You're unsure which better captures the game's feel
- Use the one matching the *primary* win condition for the overall grade; keep the other as a reference annotation

### Implementation Pattern for Racing Tension

Add this to the per-turn tracking in the instrumented game loop:

```python
# After computing scores/progress for the turn:
active_remaining = [remaining_for_player(p) for p in active_players]
if len(active_remaining) >= 2:
    spread = max(active_remaining) - min(active_remaining)
    finish_proximity_snapshots.append((progress_pct, spread))

    near_finish = sum(1 for r in active_remaining if r <= THRESHOLD)
    if near_finish >= 2:
        simultaneous_near_finish += 1
```

Then aggregate after the game:
```python
late_spreads = [s for pct, s in snapshots if pct >= 0.6]
avg_late_spread = mean(late_spreads)
photo_finish_rate = simultaneous_near_finish / len(late_spreads)
```

For the overall score calculation, swap Racing Tension into the slot that Tension Curve normally occupies. Keep the volume curve in the report as context (annotated as "reference only — not included in overall score").

---

## Implementation Pattern

The fun audit is a standalone script that wraps the existing game engine and AI. It does NOT modify the engine — it instruments a game loop and collects extra data.

### Architecture

```
fun_audit.py
├── count_meaningful_choices(player, game)  → dict of choice counts
├── snapshot_scores(game)                   → {player_id: score}
├── run_game_with_fun_tracking(config, num_players, seed)  → per-game metrics dict
├── run_fun_audit(config, num_games, num_players)           → aggregated metrics
├── aggregate_fun_metrics(results, num_players)             → aggregated dict
├── print_fun_report(agg)                                   → console output with grades
└── main()                                                  → CLI entry point
```

### The Instrumented Game Loop

The core pattern is a modified game loop that captures state before and after each turn:

```python
def run_game_with_fun_tracking(config, num_players, seed):
    game = GameState(config, num_players, seed=seed)
    ais = [HeuristicAI(skill=1.0, rng_seed=seed + i * 10000)
           for i in range(num_players)]

    turn_data = []
    # ... tracking structures ...

    while not game.game_over and turn_count < max_turns:
        player = game.get_current_player()

        # Pre-turn snapshot
        vp_before = player.score

        # Play the turn (using existing AI)
        turn_stats = ais[player.id].play_turn(player, game)

        # Post-turn analysis
        vp_gained = player.score - vp_before

        # Dead turn detection (game-specific criteria)
        is_dead = (vp_gained == 0 and
                   turn_stats["collected"] == 0 and
                   turn_stats["deals_scored"] == 0 and ...)

        # Lead change detection
        scores = snapshot_scores(game)
        new_leader = max(scores, key=lambda pid: scores[pid])
        if new_leader != current_leader:
            lead_changes += 1

        # Decision density for next player
        next_player = game.players[(idx + 1) % num_players]
        next_choices = count_meaningful_choices(next_player, game)

        turn_data.append({...})
        game.advance_turn()

    return {per-game metrics computed from turn_data}
```

### Key Design Decisions

**Measure choices for the NEXT player, not the current one.** The current player's choices were already resolved by the AI. What matters for fun is whether the game state *after* a turn leaves the next player with interesting decisions. This measures the game's ability to generate decision points, not the AI's ability to find them.

**Use max-skill AI (skill=1.0) for fun audits.** Lower-skill AI makes suboptimal moves that can artificially inflate or deflate metrics (e.g., a bad AI might never complete hard combos, making "power fantasy" look worse than it is). Measure the game at its best to understand its ceiling.

**Track per-turn data, aggregate later.** Store everything per-turn in a list of dicts. Aggregation happens after the game, not during. This keeps the game loop clean and makes it easy to add new metrics without re-running.

**Separate the instrumented loop from the batch runner.** The fun audit has its own `run_fun_audit()` function that wraps the per-game tracker. Don't try to bolt fun tracking onto the existing `run_simulation.py` — it's a different tool with different output.

**Choose the right tension metric upfront.** Before building the fun audit, identify whether the game's win condition is accumulation-based (use volume tension) or depletion-based (use racing tension). Getting this wrong produces a misleading grade that sends the designer chasing a problem that doesn't exist. When in doubt, implement both and present the more relevant one as the scored dimension.

---

## Grading System

Each dimension gets a letter grade (A through F) based on thresholds. The thresholds are subjective but calibrated against known-good and known-bad game states. Adjust them for your game's genre — a party game might need higher interaction thresholds than a strategy game.

### Default Thresholds

| Dimension | A | B | C | D | F |
|-----------|---|---|---|---|---|
| Decision Density (% turns with 2+ choices) | 85-100% | 70-85% | 50-70% | 30-50% | <30% |
| Comeback Potential (leader-loses rate) | 40-100% | 30-40% | 20-30% | 10-20% | <10% |
| Dead Turn Rate (avg dead %) | <5% | 5-10% | 10-20% | 20-35% | >35% |
| Blowout Rate (2x blowout %) | <5% | 5-10% | 10-20% | 20-35% | >35% |
| Tension Curve (volume) | ascending + final >= 38% | ascending | final >= 30% | flat/declining | — |
| Racing Tension (proximity) | photo >= 50% + spread <= 3 | photo >= 35% or spread <= 3 | photo >= 20% or spread <= 5 | photo >= 10% | photo < 10% |
| Power Fantasy (% games with wow) | 70-100% | 50-70% | 30-50% | 15-30% | <15% |
| Interaction Rate (per turn) | >15% | 10-15% | 5-10% | 2-5% | <2% |

> **Note:** Only one tension metric (volume OR proximity) should feed into the overall score. Choose based on win condition type. Report both if helpful, but annotate which is scored.

### Overall Score

Convert letter grades to numbers (A=4, B=3, C=2, D=1, F=0), average them, and map back:
- 3.5+ = A
- 2.5-3.5 = B
- 1.5-2.5 = C
- <1.5 = D

---

## Interpreting Results & Recommendations

The report should surface not just grades but actionable recommendations. Each low-scoring dimension maps to specific design levers:

| Low Grade | Likely Cause | Design Levers |
|-----------|-------------|---------------|
| Decision Density D/F | Too few actions, forced moves | Add action types, increase hand sizes, add optional actions |
| Comeback D/F | Runaway leader, snowballing | Add catch-up mechanics, increase late-game variance, reduce early scoring |
| Dead Turns D/F | Resource starvation, nothing to do | Guarantee minimum progress per turn, add free actions, shorten rounds |
| Blowout D/F | Skill/luck amplification | Add VP caps per round, diminishing returns, rubber-banding |
| Tension (volume) D/F | Front-loaded scoring | Make later rounds worth more, add end-game bonuses, progressive unlocks |
| Racing Tension D/F | Players spread out / no close finishes | Add catch-up mechanics, reduce snowball effects, tighten the race with rubber-banding |
| Power Fantasy D/F | No big combos possible | Add high-risk/high-reward options, combo multipliers, jackpot events |
| Interaction D/F | Parallel solitaire | Make trading rewarding, add shared objectives, targeted abilities |

### Common Patterns

**"Everything is B except Tension is D"** — The game is solid but front-loaded. This is very common in games where early access to resources means early scoring. Fix by making later phases more rewarding (escalating bonuses, end-game objectives, progressive multipliers).

**"Everything is B except Tension (volume) is C in a racing game"** — This is probably fine. Check Racing Tension before diagnosing a problem. If Racing Tension is B or A, the endgame is exciting — the volume curve is just measuring the wrong thing. Don't chase a tension curve grade in a shedding game.

**"Decision A, Interaction F"** — Lots of choices but they're all solo optimization. The game is a puzzle disguised as a multiplayer game. Add mechanics that force players to consider each other (shared markets, trading incentives, blocking).

**"Comeback F, Blowout F"** — Snowball problem. Early advantages compound. Add catch-up mechanics or diminishing returns on repeated strategies.

**"Racing Tension F, Blowout B"** — Players finish at different times but final scores are close. This means the game has good balance but the race itself is non-competitive (one player sprints ahead, others catch up on points). Consider mechanics that make the physical race tighter even if scoring is balanced.

---

## Adapting to Different Game Types

The 7 dimensions are universal, but the measurement details change per game type.

### Card Games
- **Decision density**: hand cards playable + market cards draftable + special actions
- **Dead turns**: no cards played AND no cards drawn (beyond mandatory draw)
- **Power fantasy**: completing the hardest objective, playing a huge combo
- **Interaction**: trading, card stealing, market blocking

### Climbing / Shedding Games (Big Two, President, Tichu family)
- **Decision density**: formation types playable (solo, pair, run, etc.) + pass option. Note that this naturally decreases as hands shrink — at 5 players it can drop a full grade vs 3 players due to more opponents driving up the rank bar before your turn arrives. This is inherent to the genre, not a design flaw.
- **Dead turns**: typically 0% in well-designed climbing games — the trick structure guarantees you either play or strategically pass. If this isn't near-zero, the engine likely has a bug.
- **Tension**: **Use Racing Tension, not volume curve.** Volume will always show a mid-game peak. Racing Tension captures whether players are neck-and-neck in the final stretch.
- **Power fantasy**: shedding 3+ cards in one formation, firing a 4-of-a-kind, successful interrupt plays
- **Interaction**: targeted abilities (steal, reveal), card passing, interrupt mechanics. Note that every trick is inherently interactive (competing to win it), but the audit only counts *direct* player-affecting events. The true interaction level is higher than the numbers suggest. This is a conservative measurement by design.

### Board Games
- **Decision density**: legal moves + build options + trade offers
- **Dead turns**: no movement AND no building AND no resource gain
- **Power fantasy**: capturing a key territory, completing a route, triggering a chain
- **Interaction**: blocking paths, competing for spaces, negotiation

### Dice Games
- **Decision density**: which dice to keep + when to stop + side bets
- **Dead turns**: busting (rolling nothing useful)
- **Power fantasy**: rolling the perfect combo, long hot streaks
- **Interaction**: stealing points, targeted challenges

### Engine-Building Games
- **Decision density**: careful here — late-game turns may have many choices but the "right" one is obvious. Weight by game phase.
- **Dead turns**: rare in engine builders, but watch for turns where the engine produces nothing
- **Power fantasy**: the moment the engine "clicks" and produces massive output
- **Tension curve**: engine builders naturally have ascending curves (good!) but can have blowout problems (the best engine runs away)

### Race Games (non-card)
- **Tension**: **Use Racing Tension.** Same logic as shedding games — remaining distance is finite and shrinking.
- **Dead turns**: turns where no movement occurs (blocked, bad roll)
- **Power fantasy**: passing multiple opponents in one move, using a shortcut, chain effects

### Cooperative Games
- **Replace Blowout with Win Rate variance**: instead of measuring score gaps between players, measure how often the team wins vs loses. Too easy (>80%) and too hard (<20%) are both unfun.
- **Replace Comeback with Crisis Recovery**: how often the team recovers from a losing position
- **Interaction is inherent**: focus instead on whether all players contribute equally (quarterbacking detection)

---

## CLI Pattern

The fun audit should follow the same CLI conventions as the batch runner:

```
python fun_audit.py -n 500 -p 4
python fun_audit.py -n 200 -p 3 --json fun_results.json
python fun_audit.py -n 1000 -p 4 -s 42 --verbose
python fun_audit.py -n 500 -p 4 --stored-surge   # game-specific variant flags
```

Standard flags:
- `-n` / `--num-games`: game count (default 500)
- `-p` / `--players`: player count
- `-s` / `--seed`: starting seed for reproducibility
- `-v` / `--verbose`: progress updates
- `--json`: export aggregated results (omit per-turn data — it's too large)
- `--config`: path to config file

Game-specific variant flags (e.g., `--stored-surge`, `--advanced-rules`) allow testing optional mechanics without editing config files. The fun audit should pass these through to the game state constructor.

The script imports from the existing game engine modules — it doesn't duplicate any game logic.
