# Championship Arena v1.2 — Corpus-Informed Iteration

**Date:** 2026-03-27

**Games simulated:** 250 × 3 player counts = 750 total


## Lessons from the H&M Iteration Corpus


## Lessons from the H&M Iteration Corpus

### Monster Mixer (Iterations 5-6)
- GPA ceiling was 2.86 due to structural shared-lineup design
- Bouncer penalty -5 → -3 improved GPA +0.15 (from 2.14 → 2.29)
- Dead turns was F → A by reducing forced-isolated rate
- Structural ceiling: shared-row single-placement can't go higher without design change

### Kahu (GPA ~A, 3.5+)
- 0% dead turns (A) — market always has something to buy
- 55% comeback rate (A) — engine-building naturally creates catch-up
- 46% final-third VP (B) — tension curve was the only B, not a blocker
- Balance: reduced offering tokens from 4/3/2/1 to 3/2/1/1 to reduce rush dominance
- Balance: reduced Tiki cost and buffed Surf to 1 VP to make more strategies viable

### Bid Brawl (GPA 3.04, B)
- Underdog Push mechanic boosted comeback pressure
- Replayability was strongest at 4.5/5
- Surprise Factor was weakest at 2.9/5

### Key Pacing Insight
- Monster Mixer: games too fast in 2-player single-round variant
- Kahu: 12.5 rounds avg worked well with 21-60 turn range
- Championship Arena v1.1: 5.1 rounds avg too fast (target 6-10)
- FP to win raise from 15 → 25 should push games from 5.1 → 8-10 rounds

### Key Spectator Insight
- Kahu interaction rate: 61% (A) — but came from Pua market, not external chaos
- Championship Arena spectator impact: 98.5% (D) — every round felt chaotic
- Fix: draw spectator only every OTHER round → impact should drop to ~50% (B range)

### Key Talent Insight
- Talents should amplify strategy, not dominate outcomes
- Kahu: talents didn't determine games — engine-building did
- Championship Arena: 93.7% talent decisive → too much
- Fix: Showman/Sprinter once-per-game instead of per-round

### Key Balance Insight
- Kahu had RPS lock (Balanced > Rush > Engine) — fixed with token changes
- Bid Brawl: Underdog Push fixed comeback issues
- Championship Arena: 47.5% win rate spread → P1 dominates
- Fix: longer games + reduced talent dominance = more even competition


## Changes Applied (Based on Corpus)


### Change 1: FP to Win 15 → 25

- **Corpus rationale:** Monster Mixer and Kahu showed that longer games (more rounds) produce better GPA.

- Kahu succeeded with 12.5 rounds avg; Championship Arena v1.1 was too fast at 5.1 rounds.

- Raising FP target extends game length and reduces sweep dominance.


### Change 2: Spectator Every OTHER Round

- **Corpus rationale:** Kahu's interaction came from the Pua market (61%, A). Championship Arena's 98.5% spectator impact means every round is chaotic.

- Drawing spectator only on odd-numbered rounds cuts impact roughly in half.


### Change 3: Showman/Sprinter Once-Per-Game

- **Corpus rationale:** Kahu talents didn't dominate outcomes. Championship Arena talents fire 93.7% of games — too dominant.

- Limiting to once-per-game preserves the power fantasy while preventing lockout.


## Results Comparison


| Dimension | v1.1 Grade | v1.1 Value | v1.2 Grade | v1.2 Value | Δ Grade | Target |

|-----------|-----------|-----------|-----------|-----------|---------|-------|

| Pacing | D | 5.7 | D | 5.8 | 0.0 | 6-10 rounds |

| Mean Score | A | 9.0 | A | 8.9 | 0.0 | avg 8-12 FP |

| Comeback Rate | B | 16.8 | B | 16.1 | 0.0 | 25-45% |

| Sweep Rate | D | 57.7 | D | 58.4 | 0.0 | 8-20% |

| Spectator Impact | D | 94.3 | D | 95.1 | 0.0 | 30-50% |

| Talent Usage | D | 93.7 | D | 93.7 | 0.0 | 40-70% |

| Balance | F | 52.5 | F | 52.4 | 0.0 | <30% spread |


**Overall GPA: 2.14 → 2.14  Δ = +0.00**

Letter grade: F → F


## Per-Player-Count Breakdown (v1.2)


### 2-Player Games

- Avg rounds: 4.6

- Avg final FP: 11.1

- Win rates: {0: 75.2, 1: 24.8}

- Comeback rate: 11.6%

- Sweep rate: 74.4%

- Spectator impact: 92.8%

- Talent decisive: 86.8%

- Win rate spread: 50.4%


### 3-Player Games

- Avg rounds: 5.8

- Avg final FP: 8.5

- Win rates: {0: 71.2, 1: 18.8, 2: 10.0}

- Comeback rate: 18.0%

- Sweep rate: 58.4%

- Spectator impact: 94.8%

- Talent decisive: 95.2%

- Win rate spread: 61.2%


### 4-Player Games

- Avg rounds: 7.1

- Avg final FP: 7.2

- Win rates: {0: 56.8, 1: 18.8, 2: 13.200000000000001, 3: 11.200000000000001}

- Comeback rate: 18.8%

- Sweep rate: 42.4%

- Spectator impact: 97.6%

- Talent decisive: 99.2%

- Win rate spread: 45.6%


## Per-Player-Count Breakdown (v1.1 Baseline)


### 2-Player Games

- Avg rounds: 4.4

- Avg final FP: 11.2

- Win rates: {0: 76.0, 1: 24.0}

- Comeback rate: 13.2%

- Sweep rate: 74.4%

- Spectator impact: 92.0%

- Talent decisive: 86.8%

- Win rate spread: 52.0%


### 3-Player Games

- Avg rounds: 5.6

- Avg final FP: 8.5

- Win rates: {0: 70.0, 1: 19.6, 2: 10.4}

- Comeback rate: 16.4%

- Sweep rate: 57.2%

- Spectator impact: 93.6%

- Talent decisive: 95.2%

- Win rate spread: 59.6%


### 4-Player Games

- Avg rounds: 7.0

- Avg final FP: 7.3

- Win rates: {0: 56.8, 1: 18.8, 2: 13.600000000000001, 3: 10.8}

- Comeback rate: 20.8%

- Sweep rate: 41.6%

- Spectator impact: 97.2%

- Talent decisive: 99.2%

- Win rate spread: 46.0%

