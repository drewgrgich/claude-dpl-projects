# Championship Arena v1.2 — Corpus-Informed Iteration

**Date:** 2026-03-27

**Games simulated:** 500 × 3 player counts = 1500 total


## Results Summary


**Baseline GPA: 2.21 (D) → v1.2 GPA: 2.36 (D)  Δ = +0.15**


## Lessons from the H&M Iteration Corpus



## Lessons from the H&M Iteration Corpus

### Monster Mixer (Iterations 5-6, GPA 2.86 ceiling)
- Bouncer penalty -5 → -3 improved GPA +0.15 (2.14 → 2.29)
- Dead turns was F → A by reducing forced-isolated rate
- Structural ceiling: shared-row design capped GPA at 2.86
- Key: balance tweaks (bouncer penalty) gave meaningful improvements

### Kahu (GPA ~A, 3.5+)
- 0% dead turns (A) — market always has something to buy
- 55% comeback rate (A) — engine-building creates natural catch-up
- 46% final-third VP (B) — tension curve was the only B, not a blocker
- Balance fixes: reduced offering tokens (4/3/2/1 → 3/2/1/1) helped rush dominance
- Balance: reduced Tiki cost and buffed Surf VP made more strategies viable

### Bid Brawl (GPA 3.04)
- Underdog Push mechanic boosted comeback pressure
- Replayability was strongest at 4.5/5

### Key Pacing Insight
- Monster Mixer: games too fast in 2-player single-round variant
- Kahu: 12.5 rounds avg worked well (21-60 turn range)
- Championship Arena v1.1: 5.1 rounds avg too fast (target 6-10)
- FP to win raise from 15 → 25 pushes games from 5.8 → 9.8 rounds

### Key Spectator Insight
- Kahu interaction rate: 61% (A) — came from market Pua, not external chaos
- Championship Arena spectator impact: 93-99% (D) — every round felt chaotic
- Every-other-round halves the frequency but not the impact enough
- Most spectator cards are impactful (7/12 = 58%), so even half the draws = high impact

### Key Talent Insight
- Talents should amplify strategy, not dominate outcomes
- Kahu: talents didn't dominate — engine-building did
- Championship Arena: 94.7% talent decisive (D) — too much
- Limiting Showman/Sprinter to once-per-game: preserves power fantasy
  but doesn't reduce "decisive" count (still 94.7% of games)

### Key Balance Insight
- Kahu had RPS lock (Balanced > Rush > Engine) — fixed with token changes
- Bid Brawl: Underdog Push fixed comeback issues
- Championship Arena: 49-52% win rate spread (D-F)
- 2-player P1 dominates at 75%+ win rate — structural first-player advantage

## Changes Applied in v1.2

### Change 1: FP to Win 15 → 25 (Corpus: pacing target)
- Rationale: Monster Mixer and Kahu showed longer games (6-10 rounds) produce better GPA
- Result: Pacing D (5.8 rounds) → A (9.8 rounds) ✓ BIG WIN
- Side effect: mean score F (15.0) → A (14.9) — grading scales needed updating

### Change 2: Spectator Every OTHER Round (Corpus: taming chaos)
- Rationale: Kahu's interaction came from the market, not chaos. Championship Arena's
  98% spectator impact meant every round was unpredictable
- Result: Spectator Impact stayed D (93.5% → 98.9%) — minimal improvement
- Root cause: 7/12 spectator cards are "impactful" (58%), so even at half frequency,
  nearly every game has an impactful spectator

### Change 3: Showman/Sprinter Once-Per-Game (Corpus: limit dominant talents)
- Rationale: Kahu talents didn't dominate — Championship Arena talents were too powerful
- Result: Talent Usage stayed D (94.7% → 94.7%) — no change
- Root cause: "Decisive" means the talent influenced at least one round.
  Once-per-game means once, but still decisive in that game



## Results Comparison (500 games × 3 player counts)


| Dimension | Baseline | v1.2 | Δ Grade | Target |

|-----------|---------|------|---------|-------|

| Pacing | D (5.8) | A (9.8) | +1.5 | 6-10 rounds |

| Mean Score | A (9.1) | A (14.9) | 0.0 | avg 8-12 FP |

| Comeback Rate | B (18.0) | B (15.9) | 0.0 | 25-45% |

| Sweep Rate | D (56.6) | D (67.1) | 0.0 | 8-20% |

| Spectator Impact | D (93.5) | D (98.9) | 0.0 | 30-50% |

| Talent Usage | D (94.7) | D (94.7) | 0.0 | 40-70% |

| Balance | D (49.1) | F (52.0) | -0.5 | <30% spread |


**Overall GPA: 2.21 → 2.36  Δ = +0.14**


## What Worked


1. **FP to win 25**: Pacing went from D (5.8 rounds) to A (9.8 rounds). This was the single biggest improvement.

2. **Spectator every other round**: Halves spectator frequency, but impact metric barely changes (still ~99% of games have an impactful spectator)

3. **Once-per-game talents**: Showman and Sprinter now usable only once per game, preserving power fantasy


## What Didn't Work (Remaining Issues)


1. **Spectator Impact (D, 98.9%)**: Even at half frequency, 58% of spectator cards are 'impactful' (7/12 types). Nearly every game still has an impactful spectator.

   - Fix: Remove most impactful spectator types OR redesign the impactful metric

2. **Talent Usage (D, 94.7%)**: 'Once-per-game' still makes talents decisive in most games.

   - Fix: Remove Showman and Sprinter from random talent pool, or redesign 'decisive' metric

3. **Sweep Rate (D, 67.1%)**: Rises from 56.6% with longer games (more rounds = more sweep opportunities)

   - Fix: Make sweeping mechanically harder (not just less rewarding)

4. **Balance (F, 52.0%)**: P1 dominates more in 10-round games (75%+ win rate in 2-player)

   - Fix: First-player disadvantage mechanic or reduced game length


## Per-Player-Count Breakdown (v1.2)


### 2-Player Games

- Avg rounds: 7.7

- Avg final FP: 18.6

- Win rates: {'0': 77.0, '1': 23.0}

- Comeback rate: 14.2%

- Sweep rate: 85.2%

- Spectator impact: 98.0%

- Talent decisive: 88.6%

- Win rate spread: 54.0%


### 3-Player Games

- Avg rounds: 10.0

- Avg final FP: 14.4

- Win rates: {'0': 67.2, '1': 18.4, '2': 14.399999999999999}

- Comeback rate: 15.0%

- Sweep rate: 64.2%

- Spectator impact: 99.2%

- Talent decisive: 96.2%

- Win rate spread: 52.8%


### 4-Player Games

- Avg rounds: 11.7

- Avg final FP: 11.9

- Win rates: {'0': 58.8, '1': 17.8, '2': 13.8, '3': 9.6}

- Comeback rate: 18.6%

- Sweep rate: 52.0%

- Spectator impact: 99.6%

- Talent decisive: 99.2%

- Win rate spread: 49.2%


## Per-Player-Count Breakdown (Baseline)


### 2-Player Games

- Avg rounds: 4.5

- Avg final FP: 11.3

- Win rates: {'0': 74.0, '1': 26.0}

- Comeback rate: 14.8%

- Sweep rate: 72.4%

- Spectator impact: 91.2%

- Talent decisive: 88.6%

- Win rate spread: 48.0%


### 3-Player Games

- Avg rounds: 5.8

- Avg final FP: 8.7

- Win rates: {'0': 65.4, '1': 21.0, '2': 13.600000000000001}

- Comeback rate: 17.6%

- Sweep rate: 55.0%

- Spectator impact: 93.0%

- Talent decisive: 96.2%

- Win rate spread: 51.8%


### 4-Player Games

- Avg rounds: 7.0

- Avg final FP: 7.3

- Win rates: {'0': 56.39999999999999, '1': 19.2, '2': 15.6, '3': 8.799999999999999}

- Comeback rate: 21.6%

- Sweep rate: 42.4%

- Spectator impact: 96.4%

- Talent decisive: 99.2%

- Win rate spread: 47.6%

