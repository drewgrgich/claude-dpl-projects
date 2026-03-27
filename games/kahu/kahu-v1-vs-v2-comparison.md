# Kahu Rules Comparison — v1.0 (RAW) vs v2.0 (OpenClaw)

*500 AI-vs-AI simulations per player count per version. Expert-level heuristic AI. March 2026.*

---

## What Changed in v2.0

OpenClaw proposed six rule modifications to address balance issues identified in v1.0:

1. **Surf VP bonus** — Surf cards now award 1 VP each (was 0). Gives Surf an endgame role beyond influence generation.
2. **Cheaper Tikis** — Tiki cost reduced from 1R+1B+1Y (3 Pua) to 1R+1B (2 Pua). Removes Yellow from the cost, making Tikis more accessible.
3. **Reduced VP tokens** — Offering VP tokens changed from [4, 3, 2, 1] to [3, 2, 1, 1]. First-completion advantage drops by 1 VP.
4. **Shorter 2P lava track** — 2-player lava start reduced from 16 to 12. Adds urgency to the 2P game.
5. **Offering cooldown** — After completing an Offering, a player must wait one full round before completing another. Cooldown is waived when lava reaches position 5 or below.
6. **Starting Pua (2P only)** — Each player begins with 1R+1B+1Y Pua in 2-player games. Jumpstarts the Pua economy.

---

## Overall Grades

| Players | v1.0 | v2.0 | Change |
|---|---|---|---|
| **2** | **A** | **A** | Held (with tradeoffs) |
| **3** | **A** | **A** | Held (tension improved) |
| **4** | **B** | **A** | **Upgraded** |

The headline: v2.0 lifts 4-player from B to A. The 3-player game stays strong with a notable tension curve improvement. The 2-player game holds at A overall but introduces a new tension curve problem.

---

## Dimension-by-Dimension Comparison

### Decision Density

| Players | v1.0 | v2.0 |
|---|---|---|
| 2P | A (87%, 2.4/turn) | A (92%, 2.8/turn) |
| 3P | A (87%, 2.4/turn) | A (87%, 2.3/turn) |
| 4P | A (87%, 2.3/turn) | A (86%, 2.3/turn) |

No meaningful change at 3P or 4P. The 2P game actually *improves* — starting Pua plus cheaper Tikis give players more viable options on early turns, pushing decision density from 87% to 92%.

### Comeback Potential

| Players | v1.0 | v2.0 |
|---|---|---|
| 2P | A (45% comeback, 5.0 LC) | B (38% comeback, 3.9 LC) |
| 3P | A (55% comeback, 6.6 LC) | A (55% comeback, 6.7 LC) |
| 4P | A (60% comeback, 7.2 LC) | A (62% comeback, 7.4 LC) |

Comeback potential is unchanged at 3P and 4P. The 2P game drops slightly to B — with starting Pua, Player 0's first-mover advantage is amplified (both players have resources, but P0 spends first). Lead changes fall from 5.0 to 3.9 per game. The offering cooldown, intended to slow snowballing, doesn't fully compensate because the 2P game is shorter (11.6 rounds vs 14.3).

### Dead Turn Rate

| Players | v1.0 | v2.0 |
|---|---|---|
| 2P | A (0.0%) | A (0.0%) |
| 3P | A (0.0%) | A (0.0%) |
| 4P | A (0.1%) | A (0.1%) |

No change. Dead turns remain essentially zero across all counts.

### Blowout Rate

| Players | v1.0 | v2.0 |
|---|---|---|
| 2P | A (0% 2×, 6.4 margin) | A (3% 2×, 7.4 margin) |
| 3P | A (4% 2×, 4.5 margin) | B (9% 2×, 5.6 margin) |
| 4P | C (11% 2×, 3.6 margin) | C (16% 2×, 4.3 margin) |

This is the most concerning regression. Blowout rates *increased* across all player counts. Average margins widened by 0.7–1.1 VP. At 3P the grade drops from A to B.

The culprit appears to be the reduced VP tokens ([3,2,1,1] instead of [4,3,2,1]). In v1.0, the first player to complete an Offering gets 4 VP — a big lead. But the 4→3→2→1 spacing means later completions are still meaningful (3 VP is close to 4). In v2.0, the 3→2→1→1 spacing means the first completer gets 3 VP while the third and fourth get only 1 VP each. This compresses late-arriving players more harshly, paradoxically *increasing* score spread despite reducing the top token.

The Surf VP bonus also contributes — players who build Surf-heavy engines get +5 to +8 VP from Surf cards alone, creating a new axis of divergence.

### Tension Curve

| Players | v1.0 | v2.0 |
|---|---|---|
| 2P | B (43% ascending, 47% final third) | C (1% ascending, 34% final third) |
| 3P | B (43% ascending, 46% final third) | A (51% ascending, 48% final third) |
| 4P | C (35% ascending, 44% final third) | B (49% ascending, 47% final third) |

The most dramatic shifts. At 3P and 4P, v2.0 improves the tension curve substantially — ascending games jump from 43%→51% at 3P and 35%→49% at 4P. The offering cooldown forces players to space out their completions, preventing a mid-game spike where multiple players complete offerings in the same round.

However, the 2P game collapses to C. Only 1% of 2P games show an ascending curve, and the final third accounts for just 34% of VP. The starting Pua causes an early scoring burst — players can complete their first Offering by round 2–3 instead of round 4–5 — front-loading VP and flattening the arc. The shorter lava track (12 instead of 16) also compresses the game, giving less time for late-game acceleration.

### Power Fantasy

| Players | v1.0 | v2.0 |
|---|---|---|
| 2P | A (7.8/game) | A (7.5/game) |
| 3P | A (9.0/game) | A (8.9/game) |
| 4P | A (10.3/game) | A (10.1/game) |

No meaningful change. Wow moments remain universal and consistent.

### Interaction Rate

| Players | v1.0 | v2.0 |
|---|---|---|
| 2P | A (57%, 15.9/game) | A (59%, 13.3/game) |
| 3P | A (61%, 22.6/game) | A (61%, 23.7/game) |
| 4P | A (63%, 29.4/game) | A (63%, 31.3/game) |

No meaningful change. Interaction is stable across all counts.

---

## Game Health Metrics

| Metric | v1.0 2P | v2.0 2P | v1.0 3P | v2.0 3P | v1.0 4P | v2.0 4P |
|---|---|---|---|---|---|---|
| Avg turns | 28.6 | 23.2 | 37.4 | 38.9 | 47.4 | 49.7 |
| Avg rounds | 14.3 | 11.6 | 12.5 | 13.0 | 11.8 | 12.4 |
| End by Offerings | 94.4% | 100% | 97.6% | 98.4% | 90.8% | 95.6% |
| End by lava | 5.6% | 0% | 2.4% | 1.6% | 9.2% | 4.4% |
| Avg lava final pos | 4.9 | 7.8 | 8.0 | 9.4 | 7.3 | 8.8 |
| Avg influence/turn | 7.0 | 7.0 | 6.7 | 6.7 | 6.5 | 6.6 |

Notable shifts:

The 2P game is **5 rounds shorter** in v2.0 (11.6 vs 14.3). Starting Pua accelerates early Offering completions dramatically. Lava eruptions disappear entirely — the shorter track starts at 12 but the faster game means fewer lava advances (4.2 in v2 vs 11.1 in v1). This is counterintuitive: OpenClaw shortened the track to add urgency, but the starting Pua accelerates the game so much that lava never becomes a threat.

The 3P and 4P games are slightly *longer* in v2.0 (+0.5 rounds each). The offering cooldown prevents players from chaining back-to-back Offering completions, extending the game by a round or so. Lava eruptions are less frequent at 4P (4.4% vs 9.2%), which is a clear improvement — fewer games end by runaway lava.

---

## Win Rates by Seat

| Seat | v1.0 2P | v2.0 2P | v1.0 3P | v2.0 3P | v1.0 4P | v2.0 4P |
|---|---|---|---|---|---|---|
| P0 | 59.4% | 58.8% | 42.4% | 42.4% | 37.0% | 40.6% |
| P1 | 40.6% | 41.2% | 32.4% | 33.8% | 27.6% | 25.0% |
| P2 | — | — | 25.2% | 23.8% | 19.4% | 18.4% |
| P3 | — | — | — | — | 16.0% | 16.0% |

First-player advantage is essentially unchanged. At 2P it remains ~59/41. At 3P, P0 stays at 42.4%. At 4P, P0 actually *worsens* from 37% to 40.6%. None of the v2.0 changes directly address the first-player advantage — they target other aspects of balance.

---

## Score Composition

| Component | v1.0 3P | v2.0 3P | Delta |
|---|---|---|---|
| Card VP | 16.7 | 20.1 | +3.4 |
| VP Tokens | 7.5 | 5.2 | −2.3 |
| Offering Bonuses | 6.6 | 6.5 | −0.1 |
| **Total** | **30.8** | **31.7** | **+0.9** |

VP tokens contribute less (by design — the [3,2,1,1] scale reduces the pool). Card VP increases to compensate, partly from Surf cards now being worth 1 VP each. Total scores are slightly higher across the board. The shift toward card VP reinforces deck-building as the dominant strategy.

---

## Assessment of Each v2.0 Change

### 1. Surf VP Bonus — Mixed

Surf cards contributing 1 VP each is thematically nice and makes them more interesting to buy. However, it adds a new source of score divergence. Players who buy 6+ Surf cards get a substantial VP bonus that wasn't available in v1.0. This contributes to wider margins.

**Verdict:** Keep, but monitor. If blowouts remain a concern, consider reducing to 0.5 VP (via a conditional — e.g., "1 VP if you have 3+ Surf cards, 0 otherwise").

### 2. Cheaper Tikis — Positive

Removing Yellow from the Tiki cost makes them significantly easier to claim, which is good — in v1.0 Tikis were often too expensive relative to their defensive value. The data shows lava eruptions are less frequent in v2.0, suggesting Tikis are more accessible and providing their intended protection.

**Verdict:** Clear improvement. Keep.

### 3. Reduced VP Tokens — Negative

The intention was to reduce first-completer advantage, but the flattened distribution [3,2,1,1] actually widens score spreads. The third and fourth players to complete an Offering get only 1 VP, making late completions feel unrewarding. This harms comeback potential and increases blowout rate.

**Verdict:** Revert to [4,3,2,1] or try [3,2,2,1] to keep the late-arrival tokens more meaningful.

### 4. Shorter 2P Lava Track — Ineffective

Reducing lava start from 16 to 12 was meant to add urgency, but the starting Pua (change #6) accelerates the game so much that the shorter track doesn't matter. Zero lava eruptions occurred in 500 v2.0 2P games. The net effect is just a shorter game.

**Verdict:** If keeping starting Pua, revert lava to 16 (or 14 as a compromise). If removing starting Pua, 12 is fine.

### 5. Offering Cooldown — Positive

The cooldown is the strongest improvement in v2.0. It directly addresses the mid-game Offering rush, forces players to diversify their turn-by-turn strategy, and produces measurably better tension curves at 3P (+8% ascending) and 4P (+14% ascending). The lava waiver at position 5 is well-calibrated — it creates a natural "panic mode" when lava is critical.

**Verdict:** Clear improvement. Keep.

### 6. Starting Pua (2P) — Negative

Starting with 1R+1B+1Y is too strong at 2 players. It eliminates the early-game Pua acquisition phase, enables round-2 Offering completions, front-loads scoring, and collapses the tension curve. The 2P game goes from B tension to C tension. Lead changes drop by 22% and comebacks become less likely.

**Verdict:** Remove, or reduce to 1 Pua of a random color. The 2P game was already the strongest in v1.0 and didn't need acceleration.

---

## Summary

| Change | Impact on 2P | Impact on 3P | Impact on 4P | Recommendation |
|---|---|---|---|---|
| Surf VP +1 | Neutral | Slight negative (wider margin) | Slight negative | Keep with caution |
| Cheaper Tikis | Positive | Positive | Positive | **Keep** |
| VP Tokens [3,2,1,1] | Negative | Negative | Negative | **Revert or adjust** |
| 2P Lava 16→12 | Ineffective | — | — | Revert if keeping #6 |
| Offering Cooldown | N/A (too short) | **Very positive** | **Very positive** | **Keep** |
| Starting Pua (2P) | Negative | — | — | **Remove** |

The best v2.0 package would be: keep the offering cooldown and cheaper Tikis, revert the VP tokens and starting Pua, and make Surf VP conditional or keep it at 1 VP while monitoring blowout rates. This combination would preserve the v1.0 strengths while fixing the tension curve at 3P and 4P.
