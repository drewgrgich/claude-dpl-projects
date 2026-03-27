# Monster Mixer Iteration Notes (Iteration 5)

## Goal
Raise fun-audit GPA above 3.0 without changing the core shared-lineup identity.

## Change Set (v1.0 -> v1.1)
- **Bouncer penalty reduced** from -5 to **-3**.
  - Rationale: make completing a run of 3 feel less punishing, encourage more bouncer triggers, and reduce conservative play.

## Simulation Notes
- Simulator updated to track **forced isolated** turns (isolated plays where no matching suit was available).
- Audit framework updated to use forced isolated rate for dead-turn scoring and per-turn scoring for scaling.

## Results (250 games per player count)
- **v1.0 GPA:** 2.14
- **v1.1 GPA:** 2.29

### Key Issues Persisting
- **Dead Turns:** Still failing due to high forced-isolated frequency in the shared-lineup structure.
- **Scaling:** Score-per-turn varies meaningfully across player counts due to fixed hand sizes and round counts.

## Decision
Stop iteration due to **structural weakness**: the shared-lineup, single-placement turn loop produces a stable forced-isolated rate that resists tuning without altering core identity (e.g., adding multi-placement, hand cycling, or insertion rules). Further changes would likely shift the game away from the simple shared-row tension.
