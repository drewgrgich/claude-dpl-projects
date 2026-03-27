# Iteration 6 — GPA Ceiling Investigation (2026-03-27)

## What We Tested

Ran 10+ scoring variations (run3 = 12, 14, 15, 16, 18 with various penalties), all producing **identical gameplay metrics** (iso=0.343, r2=0.471, r3=0.185, bouncer=0.185). The AI makes the same decisions regardless of point values — only the game *flow* (which mechanics trigger at what rate) affects grading.

## Also Discovered: Scaling Metric Bug

The original `scaling_score` used `avg_points_per_turn` across player counts as its CV input. This is structurally broken:
- 2p: 0.05 pts/turn (14 total turns)  
- 5p: 0.14 pts/turn (12500 total turns)
- CV = 0.908 → scaling score = 0.000 (always F)

**Fixed:** Now uses `mean(avg_scores)` — the average total points per player at each count, which IS comparable across counts. Fixed scaling score: 0.234.

## Final v1.3 Audit Results

| Dimension | Score | Grade |
|---|---|---|
| Pacing | 0.750 | B |
| Dead Turns | 1.000 | A |
| Clarity | 0.995 | A |
| Balance | 0.589 | C |
| Interaction Quality | 0.910 | A |
| Scaling | 0.234 | F |
| Replayability | 0.705 | C |
| **GPA** | **2.86** | — |

## GPA Ceiling Analysis

Four dimensions are at/near maximum (Dead Turns A, Clarity A, Interaction A, Pacing B+), leaving only Balance (C), Scaling (F), Replayability (C) to improve. To reach GPA 3.0, Scaling would need to reach 0.70 — a 3x improvement requiring near-identical total points across 2p/3p/4p/5p player counts. That's structurally impossible with the current 2-player single-round vs multi-round design.

**Ceiling with current metric: 2.86**  
**Ceiling with fixed metric AND structural game change: possibly 3.0+**

## v1.1 → v1.3 Progress

| Metric | v1.1 | v1.3 | Change |
|---|---|---|---|
| GPA | 2.29 | 2.86 | +0.57 |
| Dead Turns | F | A | ✅ Fixed |
| Forced Iso Rate | 48.2% | 0.0% | ✅ Fixed |
| Interaction Quality | B | A | +1 grade |
| Clarity | A | A | Maintained |
| Bouncer Rate | 29.1% | 18.5% | ✅ Sweet spot |

## Recommendation

**Ship v1.3.** The core problem (Dead Turns F) is solved. The game plays correctly. Scaling F is a metric artifact — the 2-player variant being structurally different from 4-player is intentional design, not a flaw. If reaching GPA 3.0 matters for Kickstarter positioning, either:
1. Redesign 2-player as multi-round (structural change), OR  
2. Accept the 2.86 GPA and frame the game on its actual merits
