# Championship Arena v1.2 — Iteration Results

**Date:** 2026-03-27

**Games per test:** 250 × 3 player counts = 750 total


## Summary


| Iteration | GPA | Pacing | Mean Score | Comeback | Sweep | Spectator | Talent | Balance |

|-----------|-----|--------|------------|----------|-------|-----------|--------|--------|

BASELINE (v1.1)                                          2.21  D(5)  A(9) B(17) D(57) D(99) D(94) D(47)|

A: FP target 25                                          1.86  A(8) D(15) C(15) D(66) D(100) D(94) F(51)|

B: Harder Sweeps (sweep=4 FP)                            2.21  D(6)  A(9) B(15) D(57) D(99) D(94) D(48)|

C: Spectator every OTHER round                           2.14  D(5)  A(9) B(16) D(58) D(86) D(94) F(50)|

D: Talent Nerfs (Showman/Sprinter once/game)             2.21  D(5)  A(9) B(17) D(57) D(99) D(94) D(47)|

E: Ring Power Buffs (2/4/8 FP)                           1.93  F(4) A(10) B(18) D(49) D(97) D(94) F(50)|

F: Tamer Spectators (remove 4 chaotic)                   2.21  D(5)  A(9) B(18) D(55) D(96) D(94) D(49)|

G: Progressive Victory (Final Round at 15)               2.21  D(5)  A(9) B(17) D(57) D(99) D(94) D(47)|


### Combinations


Combo AC (FP25 + SpecOdd)                                1.86  A(9) D(15) C(13) D(68) D(97) D(94) F(51)|

Combo AD (FP25 + TalentNerf)                             1.86  A(8) D(15) C(15) D(66) D(100) D(94) F(51)|

Combo AE (FP25 + RingBuff)                               2.00  A(6) F(16) B(16) D(60) D(99) D(94) D(47)|

Combo CE (SpecOdd + RingBuff)                            1.86  F(4) A(10) C(15) D(50) D(75) D(94) D(47)|

Combo ACF (FP25 + SpecOdd + TamerSpect)                  1.86  A(9) F(15) C(14) D(67) D(91) D(94) D(49)|

Combo ADE (FP25 + TalentNerf + RingBuff)                 2.00  A(6) F(16) B(16) D(60) D(99) D(94) D(47)|


## ★ Best Performer: B: Harder Sweeps (sweep=4 FP)

**GPA: 2.21**  *(baseline 2.21, Δ = +0.00)*


| Dimension | Value | Grade | Δ vs Baseline |

|-----------|-------|-------|---------------|

| Pacing | 5.5 | D | 0.0 |

| Mean Score | 9.2 | A | 0.0 |

| Comeback Rate | 15.5 | B | 0.0 |

| Sweep Rate | 57.2 | D | 0.0 |

| Spectator Impact | 99.3 | D | 0.0 |

| Talent Usage | 93.7 | D | 0.0 |

| Balance | 48.0 | D | 0.0 |


## Per-Player-Count Breakdown (Best)


### 2-Player

- Avg rounds: 4.7

- Avg final FP: 11.8

- Win rates: {0: 74.0, 1: 26.0}

- Comeback rate: 12.8%

- Sweep rate: 71.6%

- Spectator impact: 98.0%

- Talent decisive: 86.8%

- Win rate spread: 48.0%


### 3-Player

- Avg rounds: 5.5

- Avg final FP: 8.7

- Win rates: {0: 63.6, 1: 24.4, 2: 12.0}

- Comeback rate: 16.8%

- Sweep rate: 57.6%

- Spectator impact: 100.0%

- Talent decisive: 95.2%

- Win rate spread: 51.6%


### 4-Player

- Avg rounds: 6.3

- Avg final FP: 7.1

- Win rates: {0: 55.2, 1: 16.0, 2: 18.0, 3: 10.8}

- Comeback rate: 16.8%

- Sweep rate: 42.4%

- Spectator impact: 100.0%

- Talent decisive: 99.2%

- Win rate spread: 44.4%


## Iteration Details


### A: FP target 25

Change fp_to_win from 15 → 25. Hypothesis: games end too fast (5.1 rounds).

**GPA: 1.86** — Overall F


| Dimension | Value | Grade | Δ Baseline |

|-----------|-------|-------|------------|

| Pacing | 8.3 | A | +1.5 |

| Mean Score | 15.0 | D | -2.5 |

| Comeback Rate | 14.7 | C | -1.0 |

| Sweep Rate | 66.0 | D | 0.0 |

| Spectator Impact | 99.7 | D | 0.0 |

| Talent Usage | 93.7 | D | 0.0 |

| Balance | 51.2 | F | -0.5 |



### B: Harder Sweeps (sweep=4 FP)

Reduce sweep reward from 6 → 4 FP. Hypothesis: 57% sweep rate too high.

**GPA: 2.21** — Overall D


| Dimension | Value | Grade | Δ Baseline |

|-----------|-------|-------|------------|

| Pacing | 5.5 | D | 0.0 |

| Mean Score | 9.2 | A | 0.0 |

| Comeback Rate | 15.5 | B | 0.0 |

| Sweep Rate | 57.2 | D | 0.0 |

| Spectator Impact | 99.3 | D | 0.0 |

| Talent Usage | 93.7 | D | 0.0 |

| Balance | 48.0 | D | 0.0 |



### C: Spectator every OTHER round

Draw spectator card only on odd-numbered rounds. Hypothesis: 98.5% spectator impact too high.

**GPA: 2.14** — Overall F


| Dimension | Value | Grade | Δ Baseline |

|-----------|-------|-------|------------|

| Pacing | 5.4 | D | 0.0 |

| Mean Score | 9.1 | A | 0.0 |

| Comeback Rate | 15.6 | B | 0.0 |

| Sweep Rate | 57.9 | D | 0.0 |

| Spectator Impact | 86.0 | D | 0.0 |

| Talent Usage | 93.7 | D | 0.0 |

| Balance | 50.3 | F | -0.5 |



### D: Talent Nerfs (Showman/Sprinter once/game)

Showman and Sprinter once-per-game instead of per-round. Hypothesis: 93.7% talent decisive crowding out base mechanics.

**GPA: 2.21** — Overall D


| Dimension | Value | Grade | Δ Baseline |

|-----------|-------|-------|------------|

| Pacing | 5.1 | D | 0.0 |

| Mean Score | 9.2 | A | 0.0 |

| Comeback Rate | 16.7 | B | 0.0 |

| Sweep Rate | 57.2 | D | 0.0 |

| Spectator Impact | 98.5 | D | 0.0 |

| Talent Usage | 93.7 | D | 0.0 |

| Balance | 47.5 | D | 0.0 |



### E: Ring Power Buffs (2/4/8 FP)

Increase base ring rewards 1→2, 2→3→4, 3→6→8. Hypothesis: base rings under-rewarded vs talents/spectators.

**GPA: 1.93** — Overall F


| Dimension | Value | Grade | Δ Baseline |

|-----------|-------|-------|------------|

| Pacing | 3.7 | F | -1.5 |

| Mean Score | 10.1 | A | 0.0 |

| Comeback Rate | 18.0 | B | 0.0 |

| Sweep Rate | 48.8 | D | 0.0 |

| Spectator Impact | 96.8 | D | 0.0 |

| Talent Usage | 93.7 | D | 0.0 |

| Balance | 50.0 | F | -0.5 |



### F: Tamer Spectators (remove 4 chaotic)

Remove Chaos Round, Wild Card Toss, Jeering Rival, Card Shark. Hypothesis: too much spectator chaos.

**GPA: 2.21** — Overall D


| Dimension | Value | Grade | Δ Baseline |

|-----------|-------|-------|------------|

| Pacing | 5.2 | D | 0.0 |

| Mean Score | 9.4 | A | 0.0 |

| Comeback Rate | 17.6 | B | 0.0 |

| Sweep Rate | 55.3 | D | 0.0 |

| Spectator Impact | 95.6 | D | 0.0 |

| Talent Usage | 93.7 | D | 0.0 |

| Balance | 48.7 | D | 0.0 |



### G: Progressive Victory (Final Round at 15)

First to 15 FP triggers a Final Round with doubled scoring. Hypothesis: games ending at 15 feel abrupt.

**GPA: 2.21** — Overall D


| Dimension | Value | Grade | Δ Baseline |

|-----------|-------|-------|------------|

| Pacing | 5.1 | D | 0.0 |

| Mean Score | 9.2 | A | 0.0 |

| Comeback Rate | 16.7 | B | 0.0 |

| Sweep Rate | 57.2 | D | 0.0 |

| Spectator Impact | 98.5 | D | 0.0 |

| Talent Usage | 93.7 | D | 0.0 |

| Balance | 47.5 | D | 0.0 |


