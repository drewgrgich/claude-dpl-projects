# Kahu Balance Analysis — Iteration 02

## Changes Applied from Iteration 01

### Iteration 01 Problems:
1. Lava was mathematically inert (eruptions = 0)
2. Pua economy deadlocked (Offerings impossible to complete)
3. Rush strategy dominated (95-100% win rates)
4. Engine strategy was non-viable (0% vs balanced)

### Iteration 02 Fixes Applied:

**Fix 1: Lava Acceleration**
- Start lava higher: 20 for 2-player (was 16)
- Give each player 3 Lava Flow cards in discard from turn 1 (simulates space 15 escalation)
- Expected: lava reaches 0 in ~15-20 turns in 2-player games

**Fix 2: Pua Economy Fix**
- Starting Pua prices reduced from 3/4/5 to 2/3/4
- Each player starts with 1 Pua of each color (village contribution, prevents deadlock)
- Influence banking added (unspent influence carries over, cap 5)
- Expected: Pua economy flows, Offerings completable in 15-25 turns

**Fix 3: Strategy Tweaks**
- Rush: aggressive Pua buying + offering completion
- Balanced: mix of market cards and Pua
- Engine: market cards first, then Pua

---

## Iteration 02 Simulation Results (500 games, 2-player)

### Strategy Win Rates

| Matchup | P1 Win% | P2 Win% | Avg Turns | Lava Eruptions |
|---------|--------|---------|-----------|----------------|
| balanced vs balanced | 53.2% | 46.8% | 47.6 | 0 |
| rush vs rush | 54.8% | 45.2% | 32.1 | 0 |
| engine vs engine | 44.2% | 55.8% | 60.0 | 0 |
| rush vs balanced | 19.0% | **81.0%** | 38.1 | 0 |
| engine vs balanced | **100.0%** | 0.0% | 48.2 | 0 |
| rush vs engine | 0.0% | **100.0%** | 41.3 | 0 |

### New Analysis:

**Positive findings:**
- First-player advantage is well-balanced (44-55% range) ✓
- Winner scores are reasonable (13-20 VP) ✓
- Games end faster (32-60 turns) ✓
- Balanced vs balanced is 53/47 - near perfect ✓

**Remaining problems:**

1. **Lava is STILL inert**: 0 eruptions across ALL games. The 3 Lava Flow cards per player still don't create enough pressure. Games end through the VP race before lava threatens.

2. **Rock-Paper-Scissors balance is inverted**: The intended balance should be Engine > Balanced > Rush > Engine (roughly). Instead we see:
   - Balanced crushes Rush (81%) ← too dominant
   - Engine loses to Balanced (0%) ← Engine is the "loser" strategy
   - Rush loses to Engine (0%) ← Rush can't catch up
   - This means: Engine < Rush < Balanced, with Balanced being nearly unbeatable

3. **The "winning" strategy (balanced) is boring**: It buys 2 market cards per turn + completes Offerings. This is the safest, most consistent path but lacks strategic tension.

4. **Engine is completely non-viable**: Waiting to complete Offerings until you have 2 tokens = you lose. Engine never catches up.

---

## Root Cause Analysis

### Why is Lava Still Inert?

With 3 Lava Flow cards per player, the probability per turn of drawing at least one:
- Turn 1-5: Very low (LF cards in discard, slowly entering deck)
- Turn 6+: ~37.5% per player per turn (3 LF in ~12 card deck, 5 cards drawn)
- Both players combined: ~63% per turn
- BUT: Tiki can block (very rare in sim since Tikis are expensive)
- Expected lava decrease: ~0.63 spaces/turn
- In 50 turns: ~31.5 spaces decrease (20 → would reach 0!)

**But eruptions are 0!** This means games are ending BEFORE lava reaches 0 — through the VP condition (3 Offerings completed).

The VP condition ends games at ~30-50 turns. By then, lava has only decreased to space 5-10. The lava NEVER reaches 0.

### Why Does "Balanced" Dominate?

The simulation's "balanced" strategy buys 2 market cards per turn while also completing Offerings. This creates a positive feedback loop:
- More market cards → more influence → more Offerings completed
- More Offerings → faster VP → game ends sooner
- The market card advantage compounds over time

Rush focuses only on Offerings but doesn't build the engine to sustain it.
Engine focuses on market cards but waits too long on Offerings.

### The Core Design Flaw

**The Offering completion is TOO rewarding relative to card economy.**

VP token values (4+3+2 = 9 for first 3 Offerings) are overwhelming compared to card VP (which averages 2-5 per card, but you need 10-15 cards to match one Offering).

The Offering bonuses then ADD 5-10 more VP on top.

**This creates a pure "rush Offerings" meta where the optimal play is: focus entirely on Offerings.**

The balanced AI in my sim isn't "balanced" — it's actually the best rush because it also buys market cards while rushing.

---

## Iteration 03 Proposed Fixes

### Fix A: Make Lava Truly Threatening (CRITICAL)
- **Add 2 more Lava Flow cards to each player's discard** (5 LF total per player)
- OR: Start lava at space 12 for 2-player (dramatically reduces margin)
- OR: Make lava advance 2 spaces per trigger (doubling pressure)
- **Goal**: Make lava eruptions happen in 30-40% of games

### Fix B: Reduce Offering Token VP
- Change from 4/3/2/1 to 3/2/1/1
- This makes card economy more valuable relative to Offerings
- Engine strategy becomes more competitive

### Fix C: Add Market Card VP Bonus
- Cards with VP values (2-3 VP) should be worth pursuing
- The Surf card (2 influence for 0 VP) is currently a trap — lower Surf VP to make it neutral

### Fix D: Accelerate Game End Through Lava
- When lava reaches space 5, ALL players score a "survival bonus" of 3 VP
- This creates a "sprint to the finish" when lava is threatening
- Makes lava interesting even if it doesn't reach 0

---

## Recommendation

**Proceed to Iteration 03** with:
1. Lava acceleration (5 LF per player, lava starts at 15 for 2-player)
2. Offering token reduction (3/2/1/1 instead of 4/3/2/1)
3. Test whether the balance shifts

If after these changes lava still doesn't erupt, accept that the lava track is a "bonus tension" mechanism rather than a primary end condition in 2-player games.
