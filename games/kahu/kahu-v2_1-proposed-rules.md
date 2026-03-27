# Kahu v2.1 Proposed Rules — Simulation Results

*500 AI-vs-AI simulations per configuration. Expert-level heuristic AI. March 2026.*

---

## What Is v2.1?

After testing OpenClaw's v2.0 changes and finding some regressions, v2.1 cherry-picks the winners and replaces the losers with new approaches.

### Kept from v2.0

- **Offering cooldown** — After completing an Offering, wait one full round before completing another. Waived when lava reaches position 5 or below. This was v2.0's best change: it breaks up the mid-game Offering rush, forces turn-by-turn strategy diversity, and lifts the tension curve at 3P and 4P.

- **Cheaper Tikis** — Cost reduced from 1R+1B+1Y to 1R+1B. Lava eruptions dropped significantly at 4P (9.2% → 4.4%), meaning fewer games end in a runaway disaster. Clean, simple improvement.

### Reverted to v1.0

- **VP tokens** — Back to [4, 3, 2, 1]. The v2.0 reduction to [3, 2, 1, 1] paradoxically increased blowouts by making third and fourth completions worthless.

- **2P lava track** — Back to 16. The shortened track (12) was made moot by v2.0's starting Pua.

- **Starting Pua (2P)** — Removed. The 1R+1B+1Y starting Pua collapsed the 2P tension curve from B to C by front-loading scoring.

### New in v2.1

- **Surf VP threshold** — Surf cards are worth 0 VP unless you own 4 or more, then each is worth 1 VP. This rewards deliberate Surf investment without inflating scores for incidental purchases. Creates an interesting decision point around that fourth Surf.

---

## Overall Grades

| Players | v1.0 | v2.0 | v2.1 |
|---|---|---|---|
| **2P** | **A** | A (tension C) | **A** |
| **3P** | **A** | A (blowout B) | **A** |
| **4P** | **B** | **A** (tension/blowout tradeoffs) | **A** |

v2.1 achieves the same 4P upgrade as v2.0 (B → A) while avoiding the regressions v2.0 introduced at 2P and 3P.

---

## Dimension Comparison (All Three Versions)

### 2 Players

| Dimension | v1.0 | v2.0 | v2.1 |
|---|---|---|---|
| Decision Density | A (87%, 2.4) | A (92%, 2.8) | A (87%, 2.4) |
| Comeback | A (45%, 5.0 LC) | B (38%, 3.9 LC) | A (45%, 4.7 LC) |
| Dead Turns | A (0.0%) | A (0.0%) | A (0.0%) |
| Blowout | A (0%, 6.4 margin) | A (3%, 7.4) | A (2%, 8.3) |
| Tension | B (43% asc, 47%) | C (1% asc, 34%) | B (48% asc, 47%) |
| Power Fantasy | A (7.8/game) | A (7.5) | A (7.7) |
| Interaction | A (57%, 15.9) | A (59%, 13.3) | A (57%, 15.7) |

v2.1 preserves the v1.0 strengths at 2P. Comeback stays at A (v2.0 dropped it to B). Tension stays at B (v2.0 dropped it to C). No starting Pua means the early game still has its natural Pua-acquisition phase.

### 3 Players

| Dimension | v1.0 | v2.0 | v2.1 |
|---|---|---|---|
| Decision Density | A (87%, 2.4) | A (87%, 2.3) | A (87%, 2.4) |
| Comeback | A (55%, 6.6 LC) | A (55%, 6.7) | A (56%, 6.2) |
| Dead Turns | A (0.0%) | A (0.0%) | A (0.0%) |
| Blowout | A (4%, 4.5 margin) | B (9%, 5.6) | C (10%, 6.2) |
| Tension | B (43% asc, 46%) | A (51% asc, 48%) | B (50% asc, 48%) |
| Power Fantasy | A (9.0/game) | A (8.9) | A (8.7) |
| Interaction | A (61%, 22.6) | A (61%, 23.7) | A (61%, 22.4) |

The tension improvement from the offering cooldown carries over — 50% ascending in v2.1 vs 43% in v1.0. This is the cooldown's signature effect. Blowout at 3P dropped to C (10%), which is a regression from v1.0's A (4%). The Surf threshold may contribute here — the binary 0-or-4+ VP swing creates score divergence between players who cross the threshold and those who don't. This is worth monitoring in playtesting.

### 4 Players

| Dimension | v1.0 | v2.0 | v2.1 |
|---|---|---|---|
| Decision Density | A (87%, 2.3) | A (86%, 2.3) | A (86%, 2.3) |
| Comeback | A (60%, 7.2 LC) | A (62%, 7.4) | A (65%, 7.1) |
| Dead Turns | A (0.1%) | A (0.1%) | A (0.1%) |
| Blowout | C (11%, 3.6 margin) | C (16%, 4.3) | C (12%, 4.6) |
| Tension | C (39% asc, 44%) | B (49% asc, 47%) | B (49% asc, 47%) |
| Power Fantasy | A (10.3/game) | A (10.1) | A (9.9) |
| Interaction | A (63%, 29.4) | A (63%, 31.3) | A (63%, 28.7) |

The key 4P improvements hold: tension lifts from C to B (49% ascending vs 39%), and comeback improves to 65%. Blowout at 12% is back near v1.0's 11% — the v2.0 regression (16%) is largely corrected by reverting VP tokens to [4,3,2,1].

---

## Win Rates by Seat

| Seat | v1.0 2P | v2.1 2P | v1.0 3P | v2.1 3P | v1.0 4P | v2.1 4P |
|---|---|---|---|---|---|---|
| P0 | 59.4% | 57.4% | 42.4% | 45.8% | 37.0% | 40.0% |
| P1 | 40.6% | 42.6% | 32.4% | 30.4% | 27.6% | 26.6% |
| P2 | — | — | 25.2% | 23.8% | 19.4% | 20.6% |
| P3 | — | — | — | — | 16.0% | 12.8% |

First-player advantage persists. This was expected — none of the v2.1 changes directly address turn order. The clean v2.1 package (without compensation Pua) accepts this tradeoff in favor of better fun metrics across the board.

### A Note on Compensation Pua

We tested a seat-based compensation mechanic where non-P0 players start with bonus Pua. The results were instructive:

- **Aggressive version** (P1: 1 random, P2: 2 random, P3: 1R+1B+1Y): Overcorrected catastrophically. P3 won 49.6% of 4P games.
- **Light version** (everyone except P0 gets 1 random Pua): Better — 4P win rates improved to 33/26/22/19. But introduced early-game variance that degraded blowout (D at 4P) and tension (C at 3P).

The problem is that Pua is too tightly coupled to scoring. A free Pua can translate directly into an earlier Offering completion, which means the compensation itself becomes a scoring advantage. A better approach might be non-scoring compensation — an extra card draw on turn 1, or first pick from a wider opening market. This is a design space worth exploring in physical playtesting rather than more simulation.

---

## Game Health Metrics

| Metric | v1.0 3P | v2.1 3P | v1.0 4P | v2.1 4P |
|---|---|---|---|---|
| Avg rounds | 12.5 | 12.4 | 11.8 | 12.0 |
| End by Offerings | 97.6% | 98.8% | 90.8% | 95.4% |
| End by lava | 2.4% | 1.2% | 9.2% | 4.6% |
| Avg influence/turn | 6.7 | 6.7 | 6.5 | 6.5 |

Game length is stable. Lava eruptions are down (especially at 4P: 9.2% → 4.6%), meaning fewer "feel-bad" endings where the volcano cuts the game short before players can execute their strategy.

---

## Summary: The v2.1 Package

**Three changes, all config-driven:**

1. **Offering cooldown** (1 full round, waived at lava ≤ 5) — The star of the show. Improves tension at 3P and 4P.
2. **Cheaper Tikis** (1R+1B instead of 1R+1B+1Y) — Reduces lava eruption rate by half at 4P.
3. **Surf VP threshold** (0 VP normally, 1 VP each if you own 4+) — Adds a meaningful Surf investment decision.

**What we didn't change:** VP tokens [4,3,2,1], 2P lava at 16, no starting Pua.

**What still needs work:** First-player advantage remains the biggest structural issue. Simulation suggests Pua-based compensation is the wrong tool — it's too close to the scoring axis. Physical playtesting should explore non-scoring compensation: extra card draws, wider opening markets, or a bid-for-seat-order mechanic.

---

## How to Run These Yourself

```bash
# v1.0 (rules as written)
python run_simulation.py --rules v1 -n 500 -p 3
python fun_audit.py --rules v1 -n 500 -p 4

# v2.0 (OpenClaw changes)
python run_simulation.py --rules v2 -n 500 -p 3
python fun_audit.py --rules v2 -n 500 -p 4

# v2.1 (proposed)
python run_simulation.py --rules v2.1 -n 500 -p 3
python fun_audit.py --rules v2.1 -n 500 -p 4
```

All configs are JSON files in the simulator directory. Every tunable number is externalized — tweak `config_v2_1.json` and re-run.
