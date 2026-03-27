# Tailgate Turf War — Project Context

## What This Is
A standalone card game: zone-control with simultaneous blind deployment. 2-5 players, ~15 minutes. Tailgate/sports theme. Designed by Drew.

## Current Version: v0.1.5-candidate

### Core Mechanics
- **56-card deck**: 44 number cards (11 per color × 4 colors), 4 mascots, 4 action cards, 4 duds
- **4 colored zones** — players deploy cards simultaneously and blindly each round
- **4 rounds** per game
- **Per-round passing**: pass 2 cards left EACH round at 2-4P, 1 at 5P — condition is revealed AFTER passing
- **Strength formula**: best card rank + 2 per extra card + 3 Home Field (card color matches zone color)
- **Mascot**: doubles the strength of one card at that zone (doesn't count as extra card, can't anchor Home Field)
- **Duds**: look like action cards from the back, play as rank 5 of their color, CAN anchor Home Field

### Rank Distribution ("Bookends")
`[0, 0, 1, 1, 3, 5, 7, 9, 9, 10, 10]` per color — doubled extremes, thin middle. Chosen over 6 alternatives for best seat balance, tightest style gap, and highest strength variance.

### Action Cards — Default 4 (resolve in order: Shield → Heist → Contaminate → Bounty)
- **Shield**: protects your stack from Heist/Bomb, 2 VP consolation if you lose the zone
- **Heist**: steal opponent's highest-ranked card at this zone, add to your stack
- **Contaminate**: this zone scores inverted (lowest strength wins) this round
- **Bounty**: double VP if you win the zone, 0 VP if you lose

### Variant Action Cards (Spice Option: randomize 4 from pool of 7)
- **Bomb**: destroys the highest-ranked card at that zone (from any unshielded player)
- **Swap**: exchange your top card here with your top card at any other zone you occupy
- **Ambush**: +5 Strength if you're the only player at this zone

### Scoring
- **Winner**: 5 VP per zone won (split on ties, rounded down)
- **2nd Place**: 1 VP for runner-up at each zone (requires clear winner, no ties)

### Condition Cards (12 total, 1 revealed per round after passing)
- **HF Disruptors (3)**: Inversion (lowest wins), Neutral Ground (no HF), Color Tax (HF = -2 penalty)
- **Rank Disruptors (2)**: Ceiling (all cards capped at rank 5), Mirror (rank = 10 - printed rank)
- **Deployment Constraints (2)**: Spread Out (must use 2+ zones), Lone Wolf (max 1 card per zone)
- **Scoring Twists (3)**: Double Stakes (10 VP zones), Sudden Death (ties = 0), Diminishing Returns (7/5/3/1 VP)
- **Momentum & Interaction (2)**: Grudge Match (+3 to last round's loser), Second Wave (deploy 1 more after reveal)

## Key Design Decisions & Why

| Decision | Alternatives Tested | Why This Won |
|----------|-------------------|--------------|
| 56 cards / 4 rounds | 48/3, 52/3, 52/4, 56/3, 60/4 | Best card density (4.0/round at 3P), more hand management tension |
| Bookends distribution | Flat, bell, steep, topheavy, pyramid, valley | Best seat balance (0.5%), tightest style gap (3.8%), highest σ |
| Pass left only | Bidirectional (alternating L/R) | Bidirectional creates ping-pong where junk bounces between same players |
| Per-round passing (2/round) | Single pass at start | Per-round: 3P sniper 41%→36%, 4P tightest gap (0.9%), hand shifts create fresh puzzle each round |
| Pass 2 cards/round (3-4P) | Pass 1 or 3 | Pass 1: too little churn (12-18%). Pass 3: breaks at 5P (51% churn, skill edge negative). Pass 2: 34% churn, best 4P balance |
| Condition after pass | Condition before pass | Passing blind adds hedging tension; can't game the pass |
| Rainbow (unique colors/zone) | No Matching Colors (all unique) | Old version: 91% stuck at 2P with Bookends' duplicate ranks |
| Light Touch (max 4) | Max 3 Cards | Max 3 was a no-op at 4-5P (baseline play already < 3) |
| Spread Out (2+ zones) | Min 3 Zones | Min 3: 78.5% stuck at 5P (only ~2.2 cards/round) |
| Swap targets any zone | Adjacent zones only | Adjacent-only + blind deployment = 0% beneficial swaps; any-zone = 22-26% |
| Tie rounding: floor | Ceiling | ceil() inflated VP by 2-3/game; floor keeps total VP honest |
| Min 3 cards/round | No minimum | Hoarder style exploited save-and-dump (39% win rate at 4P → 30% with fix) |
| 2nd-place VP (1) | Presence VP, no consolation | Presence VP bloats scores (+7 VP/game); 2nd-place is surgical — helps spread at 5P (12%→20%), tightens 4P to 1.8% gap |
| Sniper self-corrects at 3P | 3 zones at 3P, contested bonus | All-sniper test: 33.3% each. Problem is metagame, not rules. Don't add rules to fix adaptation |
| Condition card overhaul | 50 concepts → 20 tested → 12 selected | 3 HF disruptors (make HF bad/neutral), 2 rank disruptors, 2 deployment, 3 scoring, 2 momentum/interaction |
| Cut Exile condition | Keep it | Negative skill edge at ALL player counts (-14% to -21%). Punishes good play. |
| Cut Peasant Revolt | Keep it | 24.5% style gap at 3P — worst balance of any candidate |
| Cut Mercenary condition | Keep it | 94% HF hit rate — doesn't feel different enough from baseline |
| Keep Color Tax over Exile | Either as HF disruptor | Color Tax: HF=-2 (reshapes decisions), 2.2% gap at 4P, +34% skill edge. Exile: 0% HF but -21% skill. |
| Mirror over Peasant Revolt | Either as rank disruptor | Mirror: +45% skill at 3P (highest of any condition), genuinely flips optimization puzzle |

## Simulator Architecture
All code in `simulator/`. Config-driven via `config_v4.json`.

- `config_v4.json` — central config for all game parameters
- `cards_v4.py` — card definitions and deck builder
- `game_state_v4.py` — full game engine with scoring and action resolution
- `ai_player_v4.py` — heuristic AI with 5 play styles (balanced, aggressive, sniper, hoarder, spread)
- `run_simulation_v4.py` — batch runner with stats, style matchups, player count sweep
- `narrate_game_v4.py` — play-by-play markdown narration engine
- `analyze_moments.py` — dopamine/agency/replayability proxy analysis
- `compare_rounds_deck.py` — round count / deck size comparison tool
- `compare_distributions_56.py` — rank distribution comparison tool
- `test_conditions_bookends.py` — condition card stress tester
- `analyze_late_round_conditions.py` — per-round condition experience analyzer
- `test_feedback_claims.py` — playtester feedback claim validator (5 claims × 4 player counts)
- `compare_balance_fixes.py` — sniper/spread fix comparison (10 scenarios, 2000 games each)
- `validate_v014.py` — v0.1.4 (2nd-place VP) validation runner
- `deep_analysis.py` — designer deep dive (action rates, mascot impact, HF, VP by round, conditions)
- `test_yomi.py` — adaptive AI opponent-reading test (result: -1.9% edge, reading doesn't help)
- `test_home_field_variants.py` — HF variant comparison (baseline, require_2, scaling, wild_field)
- `test_action_pool.py` — new action cards (Heist, Contaminate, Ambush) + Spice Option pool system
- `test_per_round_pass.py` — per-round passing vs single-pass baseline
- `test_no_home_field.py` — HF=0 vs HF=3 comparison
- `test_hf0_perround.py` — 2×2 matrix: HF × pass timing
- `test_random_hf.py` — randomized HF color (flip before/after deploy)
- `test_hf_tuning.py` — flip-before at HF=1/2/3
- `test_kimi_mechanics.py` — Debt Cards + Rotating Exile
- `test_debt_variants.py` — debt timing: lump sum vs per-round bleed
- `test_pass_volume.py` — pass 1 vs 2 vs 3 cards/round
- `test_new_conditions.py` — 20 candidate condition cards tested in isolation at 4P
- `test_conditions_cross_np.py` — top 12 conditions validated at 3P/4P/5P + mixed set test

## Latest Analysis Results (v0.1.4, 2000 games)

### Post-Fix Win Rates
| Player Count | Balanced | Aggressive | Sniper | Hoarder | Spread | Style Gap |
|-------------|----------|------------|--------|---------|--------|-----------|
| 3P | 30% | 30% | 41% | — | — | 11.1% |
| 4P | 25% | 24% | 26% | 25% | — | 1.8% |
| 5P | 19% | 18% | 20% | 22% | 21% | 4.2% |

### Key Metrics
- **2nd-place awards**: ~10-11 per game across all player counts
- **4P**: Near-perfect balance (1.8% style gap)
- **5P**: Spread recovered from 12% → 21% (now viable)
- **3P sniper**: Still elevated (41%) but confirmed self-correcting (all-sniper → 33.3% each)

### Balance Fix History
| Version | Fix | Before | After |
|---------|-----|--------|-------|
| v0.1.3 | Swap any-zone | 0% success | 22-26% |
| v0.1.3 | Tie floor rounding | +3 VP/game inflation | 0 |
| v0.1.3 | Min 3 cards/round | Hoarder 39% at 4P | 25% |
| v0.1.3 | AI deployment reorder | 12.1% naked modifiers | 4.1% |
| v0.1.4 | 2nd-place VP (1) | Spread 12% at 5P | 21% |

## Action Card Pool Analysis (v0.1.5 candidate)

### New Actions Tested
| Card | Effect | Fire Rate | Success | Balance Impact |
|------|--------|-----------|---------|----------------|
| **Heist** | Steal opponent's best card at zone | 0.60-0.65/game | N/A | Tightened 4P gap to 1.5% |
| **Contaminate** | Zone scores inverted | 0.82-0.86/game | N/A | Neutral — same VP/spread |
| **Ambush** | +5 Strength if alone at zone | 0.13-0.24/game | 17-30% | Slightly favors sniper at 3P |

### Recommended Default 4
Shield / Heist / Contaminate / Bounty — one defensive, one theft, one zone-warp, one gamble.

### Spice Option (Randomized Pool)
Pick 4 from pool of 7 (original 4 + Heist, Contaminate, Ambush) at game setup. Tested: style gaps within normal range, uniform pool appearances, healthy game-to-game variance (σ=6.2-7.5).

### Key Findings
- Heist > Bomb for interaction (two-way decision vs one-directional disruption)
- Contaminate > Swap for Yomi (forces opponent guessing vs self-improvement)
- Ambush fires too rarely at 4P (17%) to be satisfying — better as variant card
- "ALL NEW" set (Shield/Heist/Contaminate/Ambush) produced tightest 4P balance (1.3% gap)
- No VP inflation across any scenario

### Yomi & Interaction Investigation
- **Adaptive AI test**: Reading opponents provides -1.9% edge (WORSE than static). HF (+3) is so dominant that hand composition determines lanes, not opponent behavior.
- **Home Field variants**: Tested require_2, scaling, wild_field. None reduced HF dominance (87-91% across all variants). HF is the game's backbone.
- **Interaction levers**: Draft (pass phase) is the real PvP. New action cards add deployment-phase interaction without breaking the HF economy.

## Condition Card Overhaul (v0.1.5)

### Process
50 concepts brainstormed → 20 tested in isolation (2000 games each at 4P) → 12 validated at 3P/4P/5P → final 12 confirmed as mixed set.

### Final 12 Condition Cards

| # | Name | Effect | Category | 4P Gap | HF% | Why Selected |
|---|------|--------|----------|--------|-----|-------------|
| 1 | **Inversion** | Lowest strength wins | HF disruptor | 3.1% | 8% | Flips HF from asset to liability; +11% skill edge |
| 2 | **Neutral Ground** | No Home Field | HF disruptor | 2.6% | 0% | Pure rank optimization; eliminates color matching |
| 3 | **Color Tax** | HF = -2 penalty | HF disruptor | 2.2% | 8% | Reshapes decisions; +34% skill edge (highest) |
| 4 | **Ceiling** | All cards capped at rank 5 | Rank disruptor | 4.1% | 96% | Compresses scores; 7% close games (2× baseline) |
| 5 | **Mirror** | Rank = 10 - printed | Rank disruptor | 3.2% | 95% | +45% skill edge at 3P; genuine puzzle flip |
| 6 | **Spread Out** | Must use 2+ zones | Deployment | 1.6% | 89% | Counters sniper; forces resource splitting |
| 7 | **Lone Wolf** | Max 1 card per zone | Deployment | 1.7% | 95% | Forces spread; 0.8% gap (tightest of any condition) |
| 8 | **Double Stakes** | Zones worth 10 VP | Scoring | 2.1% | 96% | High drama; rounds feel different |
| 9 | **Sudden Death** | Ties score 0 | Scoring | 3.2% | 96% | Punishes copycat play; forces differentiation |
| 10 | **Diminishing Returns** | 7/5/3/1 VP per zone | Scoring | 3.0% | 96% | Rewards focus over spread |
| 11 | **Grudge Match** | +3 to last round's loser | Momentum | 1.6% | 96% | 9% close games (3× baseline); comeback feel |
| 12 | **Second Wave** | Deploy 1 more after reveal | Interaction | 3.7% | 94% | Information advantage; post-reveal reaction |

### Mixed Set Results (all 12 as random pool, 2000 games)
| Player Count | Style Gap | Winner VP | Spread | Blowouts | Close Games |
|-------------|-----------|-----------|--------|----------|-------------|
| 3P | 10.2% | 39.5 | 18.1 | 24% | 7% |
| 4P | 2.9% | 31.4 | 17.9 | 19% | 3% |
| 5P | 1.6% | 26.4 | 18.1 | 18% | 1% |

### What Each Condition Does to the Game
- **HF disruptors (3)**: 1 in 4 rounds will disrupt HF. Players can't autopilot "match colors." Inversion makes your 10s worthless and 0s powerful. Color Tax makes matching actively bad. Neutral Ground levels the field.
- **Rank disruptors (2)**: Ceiling makes all number cards roughly equal (0-5 range), emphasizing quantity over quality. Mirror turns the optimization puzzle upside down.
- **Deployment constraints (2)**: Spread Out and Lone Wolf force resource splitting. Counters sniper strategy, creates distributed conflicts.
- **Scoring twists (3)**: Double Stakes raises drama. Sudden Death punishes ties. Diminishing Returns rewards zone focus.
- **Momentum/interaction (2)**: Grudge Match helps the trailing player. Second Wave gives information advantage (see what others deployed, then react).

### Rejected Condition Candidates
| Condition | 4P Gap | Why Cut |
|-----------|--------|---------|
| Exile (can't play at matching zone) | 5.8% | Negative skill edge at ALL player counts (-14% to -21%) |
| Peasant Revolt (low cards +5) | 3.7% | 24.5% style gap at 3P — worst of any candidate |
| Consolation Prize (losers get 2 VP) | 12.2% | Way too high style gap; warps incentives |
| Mercenary (off-color +1 each) | 2.6% | 94% HF hit rate — doesn't feel different from baseline |
| Foreign Exchange (HF on non-matching) | 2.5% | 92% HF hit rate — reverses logic but still all about color matching |
| Charity (2nd place gets 3 VP) | 4.7% | Higher gap than alternatives; too generous to losers |
| Overkill (play all cards) | 1.6% | Balance is fine but not interesting — just accelerates baseline play |
| Minimalist (max 2 cards) | 0.8% | Ultra-safe but boring — limits play without creating new decisions |

## Rejected Variants (tested, data-driven rejection)
| Variant | Why Rejected |
|---------|-------------|
| Remove Home Field (HF=0) | Round 4 VP dropped 20%, raw rank more deterministic, skill edge flat |
| Random HF — flip after deploy | Pure noise, blowouts +19%, skill edge went negative |
| Random HF — flip before deploy | Amplified hand luck, sniper to 47%, +24% style gap |
| Reduced HF with flip (HF=1,2) | Didn't fix sniper spike, just dampened slightly |
| Rotating Exile | Anti-sniper but over-rewarded aggressive (+6.7% gap), punished good play |
| Debt Cards (-3 lump or -1/round bleed) | Good score compression (halved blowouts) but adds complexity; tabled for now |
| Pass 3/round | Breaks at 5P (51% churn), skill edge negative, diminishing returns |
| Roulette Zones | Same problems as random HF (noise if after deploy, convergence if before) |
| Comeback Card | Band-aid, only helps 1 player, requires mid-game scoring pause |
| Auction Deployment | Fundamentally changes core simultaneous-blind mechanic |

## Rules Document
`GAME-RULES-v0.1.5.md` — complete rules + Print & Play guide. **Markdown is the only written format needed** (no PDF/docx).

## Open Design Questions
- **Condition cards overhauled**: 12 new conditions tested and validated. 3 HF disruptors ensure ~25% of rounds disrupt the dominant strategy. Ready for playtesting.
- **Sniper at 3P (39% with new conditions)**: Condition mix slightly elevated sniper from 36% to 39%. Still self-correcting in metagame. HF disruptor conditions help (Inversion, Color Tax punish sniper's color-matching strategy).
- **Seat balance**: Pass-left gives slight positional advantage. Acceptable for a 15-min game.
- **Action card pool**: Ready for playtesting. Ship core 4 (Shield/Heist/Contaminate/Bounty), include Bomb/Swap/Ambush as variant cards.
- **Next steps**: Physical prototype and playtesting. All major balance work is simulation-validated.

## Changelog

### v0.1.5-candidate (2026-03-16) — Per-Round Passing, Action Pool, Condition Overhaul
- **Per-round passing**: Pass 2 cards left EACH round (1 at 5P) instead of single pass at start
  - 3P sniper: 41% → 36% | 4P style gap: tightest ever at 0.9% | Hand churn: 34%/round
- **3 new action cards**: Heist (steal opponent's best card), Contaminate (zone scores inverted), Ambush (+5 if alone)
- **Spice Option**: Randomize 4 from pool of 7 at game setup — tested safe across all player counts
- **Recommended default 4**: Shield / Heist / Contaminate / Bounty
- **Resolution order**: Shield(1) → Heist(2) → Bomb(3) → Swap(4) → Contaminate(5) → Bounty(6) → Ambush(7)
- **Condition card overhaul**: 50 concepts → 20 tested → 12 selected. 3 HF disruptors, 2 rank disruptors, 2 deployment, 3 scoring, 2 momentum/interaction. Mixed set: 4P gap 2.9%, 5P gap 1.6%.
- **New conditions**: Color Tax (HF=-2), Ceiling (cap at 5), Mirror (10-rank), Lone Wolf (max 1/zone), Diminishing Returns (7/5/3/1), Grudge Match (+3 comeback), Second Wave (deploy after reveal)
- **Yomi investigation**: Adaptive AI proves reading opponents doesn't help (-1.9%); HF variants don't reduce HF dominance
- **Rejected variants**: HF=0, random HF (both timings), Rotating Exile, Debt Cards, Auction, Comeback Card, Exile condition, Peasant Revolt condition (see rejected tables)

### v0.1.4 (2026-03-16) — 2nd-Place VP & Balance Investigation
- **2nd-place VP**: 1 VP for runner-up at each zone (clear winner required, no ties)
- **Sniper investigation**: Tested 10 scenarios (3 zones, presence VP, contested bonus, combos). Proved sniper self-corrects via all-sniper test.
- **Alternatives rejected**: Presence VP (score bloat), 3 zones at 3P (unnecessary — sniper self-corrects), escalating zones (players sit out early rounds)

### v0.1.3 (2026-03-16) — Playtester Feedback Fixes
- **Swap**: removed adjacency restriction, now targets any zone you occupy
- **Tie scoring**: switched from `ceil()` to `floor()` rounding
- **Anti-hoarding**: added `min_cards_per_round` config parameter (3 at 2-4P, 2 at 5P)
- **AI overhaul**: deployment priority reorder (numbers before actions), anchor validation, Bounty strength threshold

### v0.1.2 — Bookends Distribution & 4-Round Structure
- Settled on 56-card Bookends distribution after testing 7 alternatives
- Moved to 4 rounds (from 3) for better card density
- Condition cards rebalanced for new structure

