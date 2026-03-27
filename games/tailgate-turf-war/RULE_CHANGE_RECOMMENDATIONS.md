# Tailgate Turf War v2.0 — Rule Change Recommendations

Based on 500-game simulations across 2–5 player counts, five play styles, and multiple parameter sweeps.

---

## Recommendation 1: Raise Sweep Threshold to 4 Zones

**Problem:** Sweep triggers 2.2× per game at 3 players and 3.2× at 2 players. The dominant strategy (spread single cards to many zones) naturally achieves 3+ zone wins without trying. Sweep currently rewards the strategy that's *already* best, instead of creating tension.

**Change:** Win **4 or more** zones in a single round to earn the Sweep bonus (was 3).

**Simulation evidence:**

| Metric (3-player) | Before (3 zones) | After (4 zones) |
|--------------------|-------------------|------------------|
| Sweep frequency | 2.21/game | 0.81/game |
| Score spread | 29.7 | 26.2 |
| Sweep still feels achievable? | Trivially easy | Challenging but realistic |

This is the single highest-impact change. Sweep becomes a meaningful achievement rather than a participation trophy.

---

## Recommendation 2: Reduce Die-Hard Fan Bonus to 3 VP

**Problem:** The Hoarder strategy wins 28.4% of 5-player games (expected: 20%) almost entirely because of the Die-Hard Fan bonus. Saving two high-value cards (average saved value: 3.7) for a guaranteed +5 VP swing is too efficient compared to playing those cards.

**Change:** Die-Hard Fan awards **3 VP** (was 5).

**Simulation evidence (5-player style matchup):**

| Style | Baseline (5 VP) | Die-Hard 3 VP | Die-Hard 2 VP |
|-----------|-----------------|---------------|---------------|
| Balanced | 20.0% | 21.1% | 21.3% |
| Aggressive | 18.6% | 18.6% | 19.0% |
| Sniper | 21.3% | 22.5% | 23.5% |
| **Hoarder** | **28.4%** | **25.8%** | **23.8%** |
| Spread | 11.7% | 12.0% | 12.6% |

At 3 VP, the Hoarder advantage shrinks from +8.4% over fair to +5.8%. At 2 VP it's nearly balanced. We recommend 3 VP as the sweet spot — the bonus still matters but doesn't dominate.

**Alternative:** Change Die-Hard Fan to award based on **number of saved cards** (e.g., 1 VP per card) instead of total value. This prevents cherry-picking high cards while still rewarding hand management.

---

## Recommendation 3: Remove the 2-Card Hype Multiplier Penalty

**Problem:** 88% of all zone plays are single cards. The ×0.8 multiplier for 2 cards means a Crew bonus of +2 barely breaks even. Example: A rank-8 alone = 8 Hype. A rank-8 + rank-4 together = (8 + 2) × 0.8 = 8.0 Hype — the same result using two cards instead of one, and you forfeited contesting a second zone.

**Change:** Set the 2-card multiplier to **×1.0** (no penalty). Keep ×0.6 for 3 cards and ×0.5 for 4+.

**Why this works:** With ×1.0, a rank-8 + rank-4 = (8 + 2) × 1.0 = 10 Hype at one zone, versus 8 + 4 = 12 across two zones. Splitting is still slightly better for raw Hype, but the higher concentration at one zone makes you harder to beat there — creating the intended tension between "concentrate to dominate one zone" vs. "spread to contest many."

**Pair with Crew bonus +3** (next recommendation) to make the math clearly favor pairing low cards with high ones.

---

## Recommendation 4: Increase Crew Bonus to +3

**Problem:** At +2 per Crew member, multi-card plays are almost never worth the multiplier penalty. The Crew bonus needs to offset the opportunity cost of not splitting cards across zones.

**Change:** Each Crew card adds **+3 Hype** (was +2).

**Combined with ×1.0 for 2 cards, the new math becomes:**
- Rank-8 alone: 8 Hype
- Rank-8 + Rank-3 together: (8 + 3) × 1.0 = **11 Hype** — clearly better than 8 + 3 = 11 split across two zones, with the bonus of being harder to beat at that single zone
- Mascot + Rank-7: (14 + 0) × 1.0 = **14 Hype** — devastating power combo

This makes the "do I pair cards or split them?" decision genuinely interesting rather than a no-brainer.

---

## Recommendation 5: Rework the Purple Mishap

**Problem:** Purple zone averages 0–1.3 wins per game across all player counts. Every other mishap is neutral-to-positive (Red: +2 value, Orange: steal a card, Yellow: enhanced crew, Green: taunt bonus, Blue: value swap). Purple's mishap is the only purely negative one — your card is returned to your hand. Rational players avoid triggering it, which means avoiding Purple natural cards at the Purple zone.

**Suggested rework options (pick one):**

1. **"The Extra Lap — with Souvenirs"**: Return the Purple card to hand, but gain +2 VP immediately. This makes it a conscious trade: lose zone presence now for guaranteed points.

2. **"The Extra Lap — Scouting Report"**: Return the Purple card to hand, and the player may look at one opponent's deployment for the next round. Information advantage compensates for the lost card.

3. **"Purple Passion"**: Instead of returning to hand, the Purple card stays and its rank is doubled (like a self-Mascot). This makes Purple naturals powerful at the Purple zone rather than punished.

All three options give players a reason to play Purple naturals at the Purple zone, solving the under-contestation problem.

---

## Recommendation 6 (Optional): Add a Catch-Up Mechanism

**Problem:** The average score spread (winner minus loser) is 21–30 VP depending on player count. That's a large gap in a game where total scores average 20–50 VP. Games can feel decided by Round 2.

**Suggested option — "Rivalry Bonus":** The player(s) with the lowest score at the start of Round 2 and Round 3 draws one extra card from the unused pool. This helps trailing players without punishing leaders.

---

## Summary: Recommended v2.1 Rule Changes

| Parameter | v2.0 | v2.1 (Recommended) |
|-----------|------|---------------------|
| Sweep threshold | 3 zones | **4 zones** |
| Die-Hard Fan VP | 5 VP | **3 VP** |
| 2-card multiplier | ×0.8 | **×1.0** |
| Crew bonus | +2 | **+3** |
| Purple mishap | Return card (negative) | **Return card + gain 2 VP** |
| Yellow Crew bonus | +4 | +4 (unchanged) |

**How to test this exact package in the simulator:**

```bash
python run_simulation.py -n 500 -p 3 \
  --sweep-threshold 4 \
  --diehard-vp 3 \
  --mult-2 1.0 \
  --crew-bonus 3

# For style matchup:
python run_simulation.py -n 500 -p 5 --preset styles \
  --sweep-threshold 4 \
  --diehard-vp 3 \
  --mult-2 1.0 \
  --crew-bonus 3
```

The Purple mishap rework and catch-up mechanism require code changes — they're design-level recommendations rather than number tweaks.
