# Kahu v3 (JJ's Revised Rules) — Simulation Report

*500 AI-vs-AI simulations per player count. Expert-level heuristic AI. March 2026.*

---

## What Changed in v3

JJ's revised rulebook makes several significant changes from what we previously tested in v2.1:

**Scoring & Offerings**
- VP tokens increased to [5, 4, 3, 2] (was [4, 3, 2, 1]) — first-to-complete bonus is now larger
- Offerings drawn from two stacks: 2 cheap (RBY = 3 Pua) + 2 expensive (4 Pua, varied colors)
- Offering cooldown removed (was present in v2.1)

**Starter Deck & Cards**
- Starter deck now includes 1× Wild icon card (replaces one plain 1-Influence)
- Hula card reworked: no longer gives 2 Influence — instead removes a non-Lava card from hand before playing (built-in deck thinning every cycle)
- Tiki cards now worth 2 VP each (was 0)
- Wildlife cards reduced to 2 copies each (was 3) — smaller market card pool
- Outrigger gains Surf synergy: keep all 3 drawn cards if played with a Surf card

**Lava Track & Tikis**
- Tiki cost reverted to 1R+1B+1Y (was 1R+1B in v2.1)
- Tiki lockout moved to space 13 (was 12)

**Turn-Order Compensation**
- Later players get 2 bonus Influence on their first turn (not Pua) — 3P: Player 3 only; 4P: Players 3 and 4

---

## Simulation Results

### 2 Players

| Metric | v2.1 | v3 |
|---|---|---|
| Avg rounds | 13.4 | 13.5 |
| End by offerings | 97.2% | **45.6%** |
| End by lava | 2.8% | **54.4%** |
| P0 win rate | 57.4% | 61.0% |
| P1 win rate | 42.6% | 39.0% |
| Avg total score | ~31 | P0: 32.1, P1: 30.3 |
| Avg winner margin | ~6.4 | 6.9 |
| Avg influence/turn | 6.7 | 5.5 |
| Avg lava advances | ~13 | 14.7 |

**⚠ Major concern: 54.4% lava eruption rate at 2P.** This is a dramatic regression from v2.1's 2.8%. The likely causes are compounding:

1. **Second Lava triggers immediately.** With lava starting at 16 and the second_lava escalation at space 15, it takes just one unblocked Lava Flow to add a second lava card to every player's deck. This doubles the lava pressure from round 2–3 onward.
2. **Tikis cost more.** Reverting to 1R+1B+1Y means players need 3 Pua colors to block lava, which is harder to afford when the game is also demanding Pua for offerings.
3. **No offering cooldown.** Without the pacing brake, players rush offerings and neglect Tiki investment.
4. **Hula gives 0 Influence.** The deck thinning is valuable long-term but reduces average hand influence from ~6.7 to 5.5, meaning less purchasing power per turn.

### 3 Players

| Metric | v2.1 | v3 |
|---|---|---|
| Avg rounds | 12.4 | 12.0 |
| End by offerings | 98.8% | **56.4%** |
| End by lava | 1.2% | **43.6%** |
| P0 win rate | 45.8% | 43.4% |
| P1 win rate | 30.4% | 27.4% |
| P2 win rate | 23.8% | 29.2% |
| Avg winner margin | ~5.0 | 5.0 |
| Avg influence/turn | 6.7 | 5.3 |
| Avg lava advances | ~17 | 17.5 |

**⚠ 43.6% lava eruption at 3P** — same pattern as 2P. The influence-based seat compensation helps P2 slightly (29.2% vs 23.8% in v2.1), narrowing the gap with P0. But the high eruption rate means many games end before players can execute their strategies.

### 4 Players

| Metric | v2.1 | v3 |
|---|---|---|
| Avg rounds | 12.0 | 11.2 |
| End by offerings | 95.4% | **36.0%** |
| End by lava | 4.6% | **64.0%** |
| P0 win rate | 40.0% | 35.2% |
| P1 win rate | 26.6% | **15.2%** |
| P2 win rate | 20.6% | **29.2%** |
| P3 win rate | 12.8% | 20.4% |
| Avg winner margin | ~4.6 | 3.7 |
| Avg influence/turn | 6.5 | 5.1 |
| Avg lava advances | ~19 | 21.1 |

**⚠ 64% lava eruption at 4P** — two-thirds of games end by volcano. The compensation system has a notable imbalance: P2 and P3 get bonus influence and outperform P1, who gets nothing but still goes after P0. P1's 15.2% win rate is the lowest across all seats in any version we've tested.

---

## Key Issues to Flag for JJ

### 1. Lava Eruption Rate Is the Headline Problem

| Players | v1.0 | v2.1 | v3 |
|---|---|---|---|
| 2P | 2.6% | 2.8% | **54.4%** |
| 3P | 2.4% | 1.2% | **43.6%** |
| 4P | 9.2% | 4.6% | **64.0%** |

The game's intended win condition (3 offerings completed) is no longer the primary outcome. At 4P, nearly two-thirds of games end by lava eruption. This fundamentally changes the game's identity — instead of a strategic deckbuilder with a ticking clock, it becomes a survival game where the clock usually wins.

**Root cause analysis:** The combination of (a) Hula losing its 2 Influence, (b) more expensive Tikis, (c) no offering cooldown, and (d) the early second_lava trigger creates a situation where players can't generate enough economy to both buy Tikis AND complete offerings before the lava track runs out.

### 2. Hula's New Role Reduces Economy

The Hula rework is thematically interesting — built-in deck thinning every cycle is a compelling design. But losing 2 Influence from the starter hand is significant. Average influence per turn dropped from ~6.7 to ~5.3. That's roughly one fewer Pua purchase per turn, which slows everything down.

**Possible fix:** Give Hula 1 Influence in addition to its remove ability. This softens the economy hit while preserving the thinning mechanic.

### 3. Seat Compensation Creates a P1 Dead Zone

The influence-based compensation helps P2 and P3 but leaves P1 (second seat) with nothing. At 4P, P1 wins only 15.2% of games — less than half the expected 25%. The compensation skips P1 entirely, creating a "worst seat" problem.

**Possible fix:** Give P1 a smaller bonus (1 bonus Influence?) to smooth the curve.

### 4. Offering Stacks Are Well-Designed

The two-stack system (2 cheap + 2 expensive offerings) is a good change. The 3-Pua offerings (Card Types, Flowers, Tikis, Surfs) show healthy completion rates across all player counts, while the 4-Pua offerings (Removed Cards, Islanders, Items, Wildlife) create meaningful reach goals. This is one of the cleanest changes in v3.

### 5. VP Token Increase Raises Scores

The [5, 4, 3, 2] tokens mean more VP flowing through offerings. Combined with Tiki VP (2 each), total scores are higher. The winner margin is tight (3.7–6.9 VP), suggesting competitive games when they do reach a natural conclusion.

---

## Offering Completion Rates

| Offering | 2P | 3P | 4P | Stack |
|---|---|---|---|---|
| Card Types | 1.89 | 2.67 | 3.36 | 3-Pua |
| Surfs | 1.78 | 2.58 | 3.11 | 3-Pua |
| Flowers | 1.76 | 2.41 | 3.12 | 3-Pua |
| Tikis | 1.65 | 2.38 | 2.96 | 3-Pua |
| Removed Cards | 0.61 | 0.94 | 1.04 | 4-Pua |
| Items | 0.50 | 0.76 | 0.80 | 4-Pua |
| Wildlife | 0.42 | 0.72 | 0.94 | 4-Pua |
| Islanders | 0.31 | 0.62 | 0.77 | 4-Pua |

The 3-Pua stack offerings are completed at 2–3× the rate of 4-Pua stack offerings, which is exactly the intended asymmetry. The gap between the cheapest (Card Types) and most expensive (Islanders) is meaningful but not so extreme that 4-Pua offerings feel impossible.

---

## Most Purchased Cards (4P, per game)

| Card | Purchases/Game |
|---|---|
| Islander (various) | 3.5 |
| Pua Kalaunu | 1.2 |
| Orchid | 1.1 |
| Ginger | 1.0 |
| Hibiscus | 1.0 |
| Plumeria | 0.9 |
| Sea Turtle | 0.9 |
| Pig | 0.9 |
| Plate Lunch | 0.9 |
| Bird of Paradise | 0.9 |

Flowers and Islanders dominate purchasing, which makes sense given their Pua icons and synergy effects. The wildlife reduction to 2 copies is reflected in slightly lower purchase rates vs. previous versions.

---

## Recommendations

1. **Address lava eruption rate first.** This is the critical issue. Options include:
   - Reduce Tiki cost back to 1R+1B (the v2.1 change that halved 4P eruptions)
   - Move second_lava trigger from space 15 to space 12 or 13 to give players more runway
   - Give Hula 1 Influence to restore some economy
   - Restore offering cooldown to slow the Pua drain

2. **Fix P1 compensation.** Give the second player 1 bonus Influence token to prevent the dead-zone win rate.

3. **Consider the Hula economy trade-off.** The remove-from-hand mechanic is great design, but the 0 Influence creates a cascading weakness. Even 1 Influence would maintain the thinning identity while keeping average hand power closer to 6.

---

## How to Run

```bash
# v3 simulations
cd simulator
python run_simulation.py --rules v3 -n 500 -p 2 --json v3_sim_2p.json
python run_simulation.py --rules v3 -n 500 -p 3 --json v3_sim_3p.json
python run_simulation.py --rules v3 -n 500 -p 4 --json v3_sim_4p.json

# Fun audit (also updated for v3)
python fun_audit.py --rules v3 -n 500 -p 3
```

All v3 files: `config_v3.json`, `kahu-cards-v3.csv`. Previous versions remain untouched.
