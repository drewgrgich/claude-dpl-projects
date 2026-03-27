# The Merch Stand Mob — Project Context

## What This Is

A simultaneous-bidding card game (3–5 players, 15–20 min) using the Hamsters & Monsters 66-card deck. Players bid cards face-down to claim merch from a Stand. Bid cards enter a shared Mosh Pit; when a faction's Pit fills past a threshold, it Tramples and everyone loses scored cards of that color. Six factions with unique abilities. VP from card ranks + color-set bonuses. Game ends when any player empties their hand or supply runs dry.

## Folder Layout

- `the-merch-stand-mob-RULES-v4.7.md` — Current rules (canonical)
- `simulator/` — Python simulation engine (AI-vs-AI playtesting)
  - `config.json` — All tunable parameters (hand size, trample threshold, set bonuses, sneak cancel, etc.)
  - `game_state.py` — Core game loop and state machine
  - `ai_player.py` — Heuristic AI with skill levels and play styles
  - `cards.py` — Card/deck definitions
  - `run_simulation.py` — Batch runner with stat aggregation
  - `sweep_rules.py` — Parameter sweep tool (vary one knob, compare outcomes)
  - `fun_audit.py` — 7-dimension fun audit (decision density, comeback, dead turns, blowout, tension, power fantasy, interaction)
  - `narrate_game.py` — Human-readable game narration
- `rule-sweep-findings.md` — Results from prior parameter sweeps

## Current Design Status

Rules are at v4.7. The simulator is stable and covers all core mechanics including faction abilities, Sneaks/Shoves, and The Drop (championship variant).

### Already Tuned (from rule sweeps)
- 3-player Trample threshold raised from 3 → 4 (unifies with 4/5-player)
- 5-player Sneak cancellation changed from 2+ → 3+ (restores Sneak viability)
- Set bonus structure left as-is for now (behavior doesn't change with bonus tweaks; Trample pressure is the binding constraint)

### Known Issues — Fun Audit (March 2026)

The fun audit (500 games, 4 players) shows a split profile: **four A's, three F's**.

**Healthy (all grade A):** Decision density, comeback potential, power fantasy, interaction rate. The core bid system, Trample equalizer, and faction abilities are working well.

**Needs work:**

1. **Blowout Rate (F)** — Avg winner margin is ~9 VP over 2nd place. 91% of games have a 2x+ ratio between 1st and last. Only ~27% of games finish within 3 VP. The scoring system amplifies early advantages.

2. **Tension Curve (F)** — VP distribution is roughly 45/41/14% across early/mid/late phases. The final third of the game produces very little scoring because hands are nearly empty and the supply is thinning. Endgames feel like a formality rather than a climax.

3. **Dead Turn Rate (F, but by design)** — 37% of player-rounds yield zero progress. ~25% of this is structural (N players, N-1 Stand slots). The remaining 12% comes from tied bids and failed Sneaks. Drew considers this acceptable as part of the game's competitive squeeze.

**Root cause connecting blowout + tension:** As hands shrink, options narrow. Fewer cards → more forced bids → more collisions → more dead rounds → trailing players fall further behind → no dramatic finish. The late-game starvation drives both problems.

## Next Tuning Experiments

These are untested ideas for addressing blowout and tension. Run them through `fun_audit.py` and `sweep_rules.py` to see what moves the needle.

### Tension Curve Fixes (try these first — tension likely improves blowout too)

- **Late-game Stand escalation:** After round N/2, restock the Stand from the bottom of the supply (where higher-rank cards tend to settle after shuffling) or from a reserved "premium" pool. Makes the final rounds worth fighting for.
- **End-game scoring event:** A final bonus round after hand depletion — reveal top 3 supply cards, all players simultaneously bid one scored card to claim one. Creates a dramatic last decision.
- **Progressive Trample pressure:** Lower the Trample threshold by 1 in the final third of the game. Makes late-game bids riskier and increases the tension of "do I push or protect."

### Blowout Fixes

- **Consolation draw:** Players who fail to claim from the Stand draw 1 card from supply to hand (not to score pile). Keeps trailing players in the game longer without inflating VP directly.
- **Diminishing claims:** If a player has claimed 2+ rounds in a row, their next bid resolves at -1 effective rank. Soft cap on runaway leaders.
- **Trample immunity for trailing players:** The player with the lowest VP keeps their cards when a Trample fires. Rubber-banding without adding rules complexity.

### How to Test

```bash
cd simulator

# Fun audit with current rules
python fun_audit.py -n 500 -p 4

# Compare player counts
python fun_audit.py -n 500 -p 3
python fun_audit.py -n 500 -p 5

# Test a rule variant (trample threshold example)
python fun_audit.py -n 500 -p 4 --trample-threshold 3

# Parameter sweep
python sweep_rules.py
```

Any rule variant that requires code changes (consolation draw, diminishing claims, etc.) will need modifications to `game_state.py`. The fun audit and sweep tools will work automatically once the game loop is updated.

## Style Notes

- Drew is the designer. The game's tone is irreverent and chaotic — "stadium energy."
- Rules docs use casual voice with flavor text. Simulator code is straightforward Python, no external dependencies beyond the standard library.
- When updating rules, always create a new version file (v4.8, etc.) rather than overwriting.
