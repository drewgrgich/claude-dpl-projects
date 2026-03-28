# Whistle Stop — Fun Audit Report

**Date:** 2026-03-27
**Simulator:** 500 games per variant, 4 players, expert AI (skill=1.0)
**Framework:** 7-dimension competitive fun audit with Racing Tension

---

## Executive Summary

Whistle Stop scores a **B (3.4/4.0)** under current rules and jumps to **A (3.6/4.0)** with one change: extending the route from 10 to 15 cards. The game's core loop is strong — every turn has meaningful decisions, the shared route creates natural interaction, and comebacks happen in half of all games. Two issues were identified and one was resolved through tuning.

---

## The Scorecard

| Dimension | Current (route=10) | Recommended (route=15) | Change |
|---|---|---|---|
| Decision Density | A (100%) | A (100%) | — |
| Comeback Potential | A (51%) | A (52%) | — |
| Dead Turn Rate | A (2.7%) | A (2.0%) | Improved |
| Blowout Rate | **D (26%)** | **C (11%)** | Fixed |
| Racing Tension | B (40%) | B (37%) | — |
| Power Fantasy | A (83%) | A (91%) | Improved |
| Interaction Rate | A (119%) | A (125%) | Improved |
| **Overall** | **B (3.4)** | **A (3.6)** | **Upgraded** |

---

## What's Working (Don't Touch These)

### Decision Density: A

Every single turn across 500 games had 2+ meaningful choice categories. Players always face real decisions: which card to play, where to place it, and how far to move. The simultaneous selection mechanic means you're committing before seeing what others do. This is the game's strongest design element.

### Comeback Potential: A

The early leader loses 51% of the time. In a 4-player game, that's near-perfect — it means being ahead matters but doesn't lock in the win. The simultaneous reveal is the hero here: you can't see what's coming and react to it, so leads are fragile.

### Interaction Rate: A

119% interaction-per-turn (meaning more than one interaction event per turn on average). The shared route is doing exactly what it should — every card you place becomes terrain others traverse. You're constantly scoring off cards opponents placed and they're scoring off yours. This is "interaction through shared infrastructure" and it works beautifully.

---

## What Was Fixed

### Blowout Rate: D → C

**The problem:** 26% of 4-player games had a 2x blowout (winner's VP >= double the worst player's VP). Root cause: with only 3 rounds at 4 players, one high-value turn dominates the entire game. A player who plays a Red 10 on a long route in round 3 can score 40+ VP in a single turn — nearly the entire game's output.

**The fix:** Extend the route from 10 to 15 cards. This gives 4-player games 4 rounds instead of 3, adding one full decision cycle. Effects:

- Blowout rate drops from 26% to 11%
- Each player gets 4 turns instead of 3 (33% more decisions)
- The extra round dilutes the impact of any single explosive turn
- Dead turn rate also improves (2.7% → 2.0%) because more route = more movement options

**Why not also remove Red ×2?** Tested it (Variant C). Removing Red's scoring bonus cuts average winner margin from 12.2 to 8.9 VP, but doesn't meaningfully change the blowout rate (11% vs 12%). Red ×2 adds flavor and excitement without being the blowout driver — it's the short game length that causes blowouts, not the multiplier. Keep Red ×2.

### Power Fantasy: F → A (measurement fix)

**The problem:** The framework's default wow threshold (3x average VP per turn) was calibrated for games with unbounded scoring variance. Whistle Stop has bounded scoring — the theoretical max is ~54 VP/turn. The 3x threshold (47 VP) landed at P99 of the actual distribution, meaning only 1% of turns could ever qualify.

**The real picture:** Whistle Stop DOES produce exciting turns. The VP distribution across 3,600 analyzed turns:

- P75: 20 VP
- P90: 30 VP (a great turn)
- P95: 42 VP (an exceptional turn)
- Max: 54 VP

At the corrected threshold (2x avg ≈ 31 VP), 83–91% of games produce at least one wow moment — turns where a player traverses most of the route with a high-rank card, stacking the ×2 from a 10 and passing through Red cards. These are genuinely exciting moments.

**This wasn't a game design problem — it was a measurement problem.** No rule change needed.

---

## What Remains (B-Grade Items)

### Racing Tension: B

Photo finish rate is 37–40% (threshold for A is 50%). Players cluster near the end of the route but not quite tightly enough for consistent nail-biter finishes. The avg late-game spread is 3.4–4.1 steps.

**Potential levers (untested):**
- A catch-up mechanic that gives trailing players +1 movement
- A "draft" phase where players pick from a shared pool, creating more information about what's coming
- Increase station bonus from 5 to 10 VP, making the race to place it more intense

This is a B, not a problem. The game finishes with reasonable tension in most games.

---

## Summary of Recommended Changes

### Must-Do

| Change | Rule | From | To | Impact |
|---|---|---|---|---|
| Extend route | `route_length_to_end` | 10 | 15 | Blowout D→C, more decisions, more interaction |

### Keep As-Is

| Rule | Current | Rationale |
|---|---|---|
| Red ×2 scoring | 2x | Adds excitement; removing it doesn't fix blowout |
| Hand size | 5 | Tested 7; no measurable improvement |
| Station bonus | 5 VP | Tested 10; no improvement, slightly more blowout |
| 10-card ×2 multiplier | 2x | Creates the game's biggest wow moments |

---

## Reproducing These Results

```bash
# Baseline (current rules)
python fun_audit.py -n 500 -p 4

# Recommended variant (route 15)
python run_simulation.py -n 500 -p 4 --route-length 15

# Compare specific tweaks
python run_simulation.py -n 500 -p 4 --route-length 15 --red-multiplier 1
python run_simulation.py -n 500 -p 4 --route-length 15 --station-bonus 10
```

---

*Design Play Labs — Whistle Stop Simulation Report*
*Generated by Whistle Stop Simulator v1.1*
