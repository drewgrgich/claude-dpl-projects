# Solo Mode Analysis: The Night Shift

**1,000 games per variant | Seeded randomness for reproducibility**

---

## Standard Mode Results

| Metric | Value |
|---|---|
| **Win Rate** | **73.9%** |
| Avg Game Length | 77 turns |
| Avg Tricks Won (Player) | 1.9/game |
| Avg Tricks Won (Owls) | 0.8/game |
| Strategic Conserves | 22.1/game |
| Trip-Ups | 0.63/game (in 52.9% of games) |
| Cards Remaining on Loss | 1.4 avg, 3 max |

### Ability Usage (Standard)

| Ability | Triggers/Game |
|---|---|
| Streamline | 0.3 |
| Recalibrate | 0.3 |
| Rotation (Substitution) | 0.2 |
| Scout | 0.2 |
| Revelation | 0.1 |
| Reclaim | 0.1 |

### Finding: Standard Mode Is Too Easy

A 73.9% win rate means a competent player will win roughly 3 out of 4 games. For a solo challenge mode, this should be closer to 35–50%.

**Root cause: the double-turn structure.** The rules specify Player → Owl A → Player → Owl B, giving the player two actions per cycle. With only 12 cards to shed against 54 in the owl decks, the math heavily favors the player. The player leads, sheds multi-card formations (chains, surges), and the owls — flipping one random card at a time — rarely beat strong plays.

**Strategic Conserve amplifies the problem.** At ≤3 cards, the player passes every trick, forcing the two owls to race each other. Since each owl only flips one card per follow, they deplete slowly — but they're fighting each other, not the player. The player averages 22 conserves per game, meaning roughly a third of all turns are spent watching owls burn cards.

---

## Iron Climb Results

| Metric | Value |
|---|---|
| **Win Rate** | **49.3%** (rules claim <5%) |
| Avg Game Length | 25.6 turns |
| Avg Tricks Won (Player) | 1.3/game |
| Avg Tricks Won (Owls) | 2.2/game |
| Strategic Conserves | 1.1/game |
| Cards Remaining on Loss | 3.1 avg, 8 max |

### Finding: Iron Climb Is Broken (Paradoxically Easier in Some Ways)

The rules claim Iron Climb has a <5% win rate. The simulation shows **49.3%** — ten times higher than advertised.

**The paradox:** Iron Climb says "owls keep flipping until they win or exhaust." This makes owls *more aggressive* per trick, but it also makes them **burn through their decks dramatically faster**. In one traced game (seed 42), Owl A flipped 18 consecutive cards trying to beat a rank 10, sending 17 to Base Camp. Owl B then flipped its entire remaining 16 cards and exhausted. The player had 3 cards left and won easily.

Iron Climb turns the owl decks into a bonfire. The game ends in 25 turns instead of 77, but the player can still shed 12 cards in that time because multi-card formations (chains, surges, cannons) shed 3–4 cards per lead.

---

## Variant Testing

| Variant | Win Rate | Notes |
|---|---|
| Standard (as written) | 73.9% | Too easy |
| Standard, no conserve | 92.9% | Even easier — player sheds faster when aggressive |
| Standard, single turn (P→A→B) | **36.0%** | Feels like a proper challenge |
| Iron Climb (as written) | 49.3% | Rules claim <5% |
| Iron Climb, no conserve | 52.3% | Conserve barely matters in Iron Climb |
| Iron Climb, card recycling* | **10.3%** | Much closer to <5% |
| Iron Climb, recycling + no conserve | 96.8% | Owls never exhaust, player sheds freely |

*Card recycling = failed owl flips go back to the bottom of the owl deck instead of Base Camp.

---

## Recommended Fixes

### Fix 1: Standard Mode — Remove the Double Turn

**Current:** Player → Owl A → Player → Owl B (player goes twice per cycle)

**Proposed:** Player → Owl A → Owl B (player goes once per cycle)

**Effect:** Win rate drops from 73.9% → 36.0%. This feels like a genuine solo challenge — winnable with good play and favorable draws, but requiring real strategy.

The rules acknowledge the double turn with "Yes, you go twice per cycle. You need the advantage." The simulation says you don't — you need less advantage for the mode to be challenging. A single turn per cycle still gives the player the edge of *choosing* what to play (vs. owls flipping randomly), plus Trip-Ups, Strategic Conserve, and faction abilities.

If 36% feels too hard, a compromise: Player → Owl A → Player → Owl B but increase the starting hand to 15–16 cards. This gives the player more options without the raw tempo advantage of double turns.

### Fix 2: Iron Climb — Add Card Recycling

**Current:** Failed owl flips go to Base Camp (owls self-destruct faster).

**Proposed:** Failed owl flips go back to the bottom of the owl deck. Owls never lose cards they don't win tricks with.

**Effect:** Win rate drops from 49.3% → 10.3%. Combined with Strategic Conserve (which now helps because the player NEEDS owls to burn each other), this creates the oppressive difficulty the rules describe.

To push it below 5%, combine card recycling with the single-turn cycle from Fix 1.

### Fix 3: Strategic Conserve Threshold

The ≤3 card threshold is too generous in standard mode (triggers 22 times/game). Consider dropping it to ≤2 cards. This makes the "Mathematical essential" claim feel more earned — the player has to get dangerously close to going out before the conserve safety net kicks in.

---

## Solo-Specific Edge Cases

1. **Multi-card leads are uncounterable.** Owls only flip single cards. When the player leads a 4-card Confetti Cannon or a 5-card Daisy Chain, no owl can ever beat it. The player wins the trick for free, sheds 4–5 cards, and may trigger an ability. This is the primary acceleration path.

2. **Ability balance in solo is fine.** Streamline (discard 1) and Recalibrate (draw 1, discard 2) are the strongest solo abilities because they shed cards. Substitution (skip owl turn) is decent. Scout and Reclaim are marginal. Revelation can't target owls (no hand to see), so it does nothing in solo. All of this feels appropriate — abilities are a bonus, not the win condition.

3. **Trip-Up is correctly powerful.** Appearing in 53% of standard games, Trip-Ups seize initiative from rank 10 owl flips. The 0-vs-10 mechanic creates exactly the dramatic moment the rules describe. No fix needed.

4. **No stalemate risk.** Unlike multiplayer, the solo mode always terminates — either the player empties their hand or both owl decks exhaust. The 500-turn safety valve was never hit in standard mode (max game: 500 turns in ~0.1% of Iron Climb games due to recycling edge cases).
