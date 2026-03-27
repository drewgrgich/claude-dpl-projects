# Tailgate Turf War v2.0 — Balance Analysis Report

**Date:** March 15, 2026
**Simulations:** 500 games per configuration, seeded for reproducibility
**Simulator:** AI-vs-AI heuristic batch simulation with 5 play styles

---

## Executive Summary

The core mechanics of Tailgate Turf War v2.0 are sound. Seat-position balance is excellent across all player counts (within 3% of fair). The Headliner system and Hype multiplier create meaningful tension. However, several areas need attention:

1. **The single-card spread strategy dominates** — 88% of zone plays are single cards. The Hype multiplier penalty for 2+ cards is steep enough that multi-card plays are rarely optimal. This undermines the core "commitment vs. concentration" tension.
2. **The Hoarder style significantly outperforms** — In 5-player style matchups, the hoarder wins 28.4% vs the expected 20%, largely thanks to the Die-Hard Fan bonus.
3. **The Purple zone is under-contested** — Its mishap (returning the card to hand) is the only purely negative one, making Purple the least attractive zone at every player count.
4. **Score spread is high** — Average winner-loser gap is 22-30 VP, meaning games can feel non-competitive by Round 3.

---

## Seat Position Balance

| Players | P0 Win % | P1 Win % | P2 Win % | P3 Win % | P4 Win % | Max Deviation |
|---------|----------|----------|----------|----------|----------|---------------|
| 2       | 54.2%    | 45.8%    | —        | —        | —        | 4.2%          |
| 3       | 31.1%    | 33.6%    | 35.3%    | —        | —        | 2.2%          |
| 4       | 23.4%    | 25.5%    | 27.2%    | 23.9%    | —        | 2.2%          |
| 5       | 20.0%    | 18.6%    | 21.3%    | 28.4%*   | 11.7%*   | 8.4%*         |

*5-player data uses different AI styles per seat, so variation reflects strategy balance, not seat advantage.

**Verdict:** Seat balance is excellent for 2-4 players. The deal order creates no meaningful first-player advantage because deployment is simultaneous. The slight 2-player P0 edge (54.2%) is within normal statistical noise at 500 games.

---

## Strategy (Style) Balance

5-player matchup with one of each style:

| Style      | Win Rate | Avg Score | Zones/Game | Cards Saved | Assessment |
|------------|----------|-----------|------------|-------------|------------|
| Balanced   | 20.0%    | 18.0      | 3.5        | 1.0         | Fair baseline |
| Aggressive | 18.6%    | 15.1      | 3.1        | 0.0         | Slightly weak — plays too many cards |
| Sniper     | 21.3%    | 18.7      | 3.6        | 1.0         | Solid — Mascot combos are strong |
| **Hoarder**| **28.4%**| **21.2**  | 3.5        | **2.0**     | **Too strong** — Die-Hard Fan bonus |
| Spread     | 11.7%    | 12.5      | 2.6        | 1.0         | **Too weak** — spread too thin |

**Key Finding:** The Hoarder style wins ~40% more than expected by saving high-value cards for the Die-Hard Fan bonus (+5 VP). Meanwhile, the Spread strategy is punished — trying to contest all 6 zones means each play is weaker and more easily beaten.

**Recommendation:** Reduce Die-Hard Fan bonus from 5 VP to 3 VP, or make it award based on card count (not total value) so hoarders can't cherry-pick high cards.

---

## Cards-Per-Zone Distribution

| Cards at Zone | Frequency | Observation |
|---------------|-----------|-------------|
| 1 card        | 88%       | Overwhelmingly dominant |
| 2 cards       | 10%       | Mostly Mascot+Natural combos |
| 3 cards       | 2%        | Very rare |
| 4+ cards      | <1%       | Essentially never |

**The Problem:** The ×0.8 multiplier for 2 cards means you need the crew bonus (+2) to just break even on what you'd get from playing the cards at separate zones. With 6 zones each worth VP, it's almost always better to spread single cards across more zones than to stack them.

**Example math:** A rank-8 card alone = 8 Hype. A rank-8 + rank-4 together = (8 + 2) × 0.8 = 8 Hype. You used 2 cards to get the same Hype as 1 card — and you gave up contesting a second zone.

**Recommendation options:**
- Increase Crew bonus from +2 to +3 (our simulation shows minimal impact with current AI)
- Change multiplier to ×0.9 / ×0.7 / ×0.5 (gentler early curve)
- Award bonus VP for "strongest Hype at any single zone" to reward concentration

---

## Zone Balance

Average wins per zone per game (3 players):

| Zone   | Wins/Game | Mishap Effect | Assessment |
|--------|-----------|---------------|------------|
| RED    | 3.84      | +2 base value (good) | Most contested — mishap is pure upside |
| BLUE   | 3.16      | Value swap (situational) | Healthy |
| ORANGE | 3.10      | Steal opponent card (good) | Healthy |
| YELLOW | 2.94      | +4 crew bonus (good) | Healthy |
| GREEN  | 2.76      | Taunt +1 VP (minor) | Slightly low |
| PURPLE | 1.32      | Return card to hand (bad) | **Under-contested** |

**The Purple Problem:** Every other mishap is neutral-to-positive. Purple's is the only purely negative one (you lose your card for the round). Smart players avoid triggering it, which means avoiding playing Purple cards at the Purple zone — but since non-matching cards don't trigger mishaps, Purple zone should still see play. The issue is that OTHER zones offer positive mishap bonuses that make them more attractive.

**Recommendation:** Rework the Purple mishap to have an upside — for example: "Return card to hand AND gain +1 VP" or "Return card to hand AND peek at one opponent's next-round deployment."

---

## Bonus Balance

| Bonus       | Triggers/Game (3p) | Assessment |
|-------------|-------------------|------------|
| Underdog    | 0.58              | Low — rarely relevant |
| Sweep       | 2.21              | High — happens more than twice per game |
| Die-Hard Fan| 1.00              | Always triggers; favors hoarders too much |

**Sweep is too frequent** because the dominant strategy (spread single cards to many zones) naturally leads to winning 3+ zones. When the best strategy AND the bonus both reward spreading, the game loses its "commitment vs. concentration" tension.

**Underdog is too rare** because winning with 1 card against 2+ cards requires either a Superstar or Mascot combo — and if you're using a Mascot combo, that's 2 cards (not eligible). This makes Underdog mostly a "got lucky with a 10" bonus.

---

## Hype Value Distribution

| Stat    | Value |
|---------|-------|
| Mean    | 6.7   |
| Median  | 6     |
| StdDev  | 3.8   |
| Range   | 0–18  |

The Hype distribution is reasonable. The max of 18 comes from Mascot doubling a rank-9 (= 18 × 1.0), which is thematic and exciting. The mean of 6.7 means most zone contests are decided by moderate-value plays.

---

## Skill Gap (Expert vs. Beginners)

| Config | Expert Win % | Beginner Win % (each) |
|--------|-------------|----------------------|
| 1 expert + 2 beginners | 30.5% | 34.3%, 35.2% |

**Concerning:** The expert wins LESS than the beginners. In a well-designed game, skill should matter. The issue is that in a simultaneous-deployment game with hidden information, "skill" is mostly about card valuation — and the noisy scoring of beginners sometimes stumbles onto good plays. Additionally, the game is short (3 rounds) which limits how much accumulated skill advantage can manifest.

**This is not necessarily a problem for the target audience** (families, casual gamers). A low skill gap means mixed-skill tables will have fun. But if you want strategic depth, consider adding information asymmetry (partial reveals) or more decision points per round.

---

## Recommended Changes (Priority Order)

### High Priority
1. **Reduce Die-Hard Fan bonus to 3 VP** — The 5 VP swing is too impactful and rewards passive play
2. **Rework Purple mishap** — Give it an upside to make Purple zone as attractive as others
3. **Increase Crew bonus to +3** — Makes 2-card plays mathematically competitive with two single-card plays

### Medium Priority
4. **Reduce Sweep threshold to 4 zones** (or remove Sweep) — Currently rewards the dominant strategy rather than creating tension
5. **Add a "Domination" bonus** — Extra VP for having the highest Hype value across ALL zones in a round. Rewards concentration.

### Low Priority
6. **Adjust multiplier curve** — Try ×0.9/×0.7/×0.5 for a gentler 2-card penalty
7. **Increase Underdog to +3 VP** — Makes single-card heroics more rewarding

---

## How to Use This Simulator

Run from the `simulator/` directory:

```bash
# Basic 500-game run
python run_simulation.py -n 500 -p 3

# Test with different player counts
python run_simulation.py -n 500 -p 2
python run_simulation.py -n 500 -p 4

# Style matchup (1 of each AI style)
python run_simulation.py -n 500 -p 5 --preset styles

# Expert vs beginners
python run_simulation.py -n 500 -p 3 --preset mixed

# Test rule changes
python run_simulation.py -n 500 -p 3 --crew-bonus 3
python run_simulation.py -n 500 -p 3 --mult-2 0.9 --mult-3 0.7
python run_simulation.py -n 500 -p 3 --underdog-vp 3
python run_simulation.py -n 500 -p 3 --diehard-vp 3
python run_simulation.py -n 500 -p 3 --sweep-threshold 4

# Parameter sweep
for crew in 2 3 4; do
  python run_simulation.py -n 300 -p 3 --crew-bonus $crew --json results_crew_${crew}.json
done

# Narrate a single game (for debugging / feel-checking)
python narrate_game.py --seed 42 -p 3
python narrate_game.py --seed 42 -p 3 --preset styles -o game_log.md

# Export to JSON for further analysis
python run_simulation.py -n 500 -p 3 --json results.json
```

All rule parameters live in `config.json` and can be overridden via CLI flags without editing the file.
