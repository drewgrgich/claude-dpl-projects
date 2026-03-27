# The Burrow - Fun Audit Results

## Summary
| Metric | Value |
| --- | --- |
| **Final GPA** | 4.45 |
| **Grade** | A |
| **Competitive Threshold (3.0)** | ✓ MET |
| **Games Audited** | 500 × 4-player games |

## Dimension Scores
| Dimension | Score | Grade | Weight |
| --- | --- | --- | --- |
| Competitive Balance | 4.3 | B | 25% |
| Strategic Depth | 4.8 | A | 20% |
| Player Interaction | 5.0 | A | 20% |
| Accessibility | 3.4 | C | 15% |
| Pacing & Momentum | 4.7 | A | 10% |
| Replayability | 3.7 | B | 5% |
| Fun Factor | 5.0 | A | 5% |

**GPA = 4.45 (A)** — Exceeds 3.0 threshold ✓

## Simulation Summary
- Average rounds played: 9.0
- Average column doublings per game: 1.47
- Column doubling rate: 12%
- Average win spread: 12.6 points
- Average lead changes: 2.91 per game
- Come-from-behind wins: 303/500 (60.6%)
- Deck exhaustion rate: 0%
- Winner diversity: 4 unique winners
- Close game rate (<5pt margin): 27%

## Iteration History
- **Iteration 1**: Initial simulation with 3×3 grid, 3 passes per round
  - Game completed in 3 rounds (structural issue: 3×3 grid + 3 cards/round = 3 rows filled)
  - Revised to 9-column grid (1 pass/round) → 9 rounds achieved
- **Iteration 2**: Tuned AI strategies, strict 1-card-per-column placement
  - GPA: 4.45, avg_rounds: 9.0, doubling_rate: 12%
- **Iteration 3**: Final validation (500 games)
  - GPA: 4.45 (stable), no weak dimensions

## Key Design Findings

### What Works Well
1. **Wheel draft creates genuine tension** — avg 2.91 lead changes per game; players actively disrupt each other
2. **Suit doubling is rare and meaningful** — 12% of columns double; when it happens, it's a significant swing
3. **9-round pacing is tight** — no deck exhaustion; games always complete the full length
4. **Comeback mechanism** — 60% of wins come from behind; no runaway leader problem
5. **Strategic diversity** — 5 AI strategies all achieve meaningful wins; no dominant strategy

### Areas of Concern
1. **Accessibility (3.4)**: Split-suit cards add mental overhead; scoring reference card essential
2. **Replayability (3.7)**: Could be higher; the 12% doubling rate is fixed by deck composition
3. **Win spread (12.6pt)**: Moderate — not all games are close, but 27% are very close

## Important Note on Rules vs. Simulation

The rules specify "9 rounds, 3 passes per round" with a "3-column burrow." This creates a structural inconsistency: with 3 passes/round and 3 cards placed per round into a 3×3 grid, the game naturally completes in 3 rounds — not 9.

**The simulation implements a corrected structure:**
- 9 rounds × 1 pass per round × 1 card per pass = 9 cards per player
- 3 columns × 3 rows = 9 slots per Burrow
- 1 card per column per round (one row filled per round)

This preserves the wheel draft mechanic while achieving the intended 9-round length. The suit-doubling tension is maintained (12% rate makes doublings feel special).

## Design Recommendations

### For Rule Refinement
1. **Grid sizing**: The 3×3 grid with 3 passes/round mathematically completes in 3 rounds. Consider either:
   - Expanding to 9 columns × 3 rows (requires 9 passes/round — different mechanic)
   - Using 1 pass/round with 3×3 grid (as simulated) — cleaner but changes the draft feel
2. **Column B center bonus**: Well-balanced; the +5 reliably makes column B contested
3. **Split-suit cards**: Add important flexibility but increase cognitive load

### For Playtesting
- Test with 2-player (simpler, faster) and 5-player (more chaotic) variants
- The Draft-Attack variant (stealing from completed columns) could significantly boost Player Interaction
- Consider adding a "column reveal" where suit-doubled columns get a special marker

## Final Recommendation

**APPROVED** — GPA 4.45 ≥ 3.0 threshold

The Burrow demonstrates strong competitive balance, excellent player interaction through the wheel draft, and meaningful strategic depth around suit-doubling. The core game loop (draft → place → score) is tight and satisfying.

**Priority for next iteration**: Resolve the rules/simulation discrepancy (3 passes vs. 1 pass) before physical prototype testing. The game mechanics are sound; only the grid/pace calibration needs finalizing.

---

*Simulation: 500 games × 4 players, seed=42*
*Generated: Phase 3 Game Simulation Audit*
