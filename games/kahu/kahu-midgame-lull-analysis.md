# Kahu Mid-Game Lull Analysis

*Round-by-round tempo analysis based on 500 AI-vs-AI games at 3 players.*

---

## The Question

Does Kahu have a mid-game lull? The fun audit gave the game strong marks across the board, with virtually zero dead turns. But the tension curve earned a B rather than an A, and playtesting intuition suggested something flattens out in the middle rounds. This analysis digs into exactly what happens, when, and why.

---

## What the Data Shows

### Offering Completion Timing

Players complete their Offerings at predictable intervals:

| Offering | Avg Round | Median | Range |
|---|---|---|---|
| 1st | 4.2 | 4 | 1–17 |
| 2nd | 8.3 | 8 | 4–18 |
| 3rd | 11.6 | 11 | 6–18 |

The gap between the 1st and 2nd Offering — the period most likely to feel like a lull — averages 4.4 rounds with a median of 4. That's roughly a third of the total game spent grinding toward the next milestone after the first one lands.

The distribution of that gap tells the story:

```
Gap (rounds)  Frequency
    1         ▓▓ 3%
    2         ▓▓▓▓▓▓ 11%
    3         ▓▓▓▓▓▓▓▓▓▓▓▓▓ 24%
    4         ▓▓▓▓▓▓▓▓▓▓▓▓ 22%
    5         ▓▓▓▓▓▓▓▓ 15%
    6         ▓▓▓▓▓ 10%
    7         ▓▓▓ 5%
    8+        ▓▓▓ 6%
```

The most common experience is a 3–5 round gap (61% of all players). That's 3–5 consecutive rounds where you already completed something and haven't completed anything new yet. You're active — buying cards, buying Pua — but you're not crossing any finish lines.

### Round-by-Round Tempo

The offering completion rate per round tells us exactly where the dip occurs:

| Round | Offerings/Round | Pua Bought/Turn | Cards Bought/Turn | Influence Available |
|---|---|---|---|---|
| 0 | 0.00 | 0.43 | 1.27 | 5.5 |
| 1 | 0.01 | 0.73 | 0.87 | 5.5 |
| 2 | 0.47 | 0.60 | 1.20 | 5.9 |
| 3 | 0.76 | 0.73 | 1.07 | 5.9 |
| 4 | 0.75 | 0.73 | 1.13 | 6.3 |
| **5** | **0.53** | **0.73** | **1.17** | **6.7** |
| **6** | **0.69** | **0.73** | **1.10** | **6.8** |
| **7** | **0.58** | **0.67** | **1.20** | **7.1** |
| **8** | **0.61** | **0.67** | **1.17** | **7.2** |
| **9** | **0.56** | **0.63** | **1.20** | **7.1** |
| 10 | 0.63 | 0.63 | 1.27 | 7.4 |
| 11 | 0.58 | 0.57 | 1.33 | 7.6 |
| 12 | 0.70 | 0.60 | 1.33 | 7.9 |

Rounds 5–9 are the lull zone. Offering completions drop from 0.75 per round (rounds 3–4) to 0.53–0.61. Influence keeps climbing — players have bigger engines — but it doesn't translate into proportionally more Offerings. The engine is growing, but progress toward the win condition plateaus.

### Phase Summary

| Phase | Offerings/Round | Pua/Turn | Cards/Turn | Influence/Turn | Dead Turn Rate |
|---|---|---|---|---|---|
| Early (R1–6) | 1.26 | 0.66 | 1.12 | 6.0 | 0.0% |
| Mid (R7–12) | 1.82 | 0.66 | 1.20 | 7.2 | 0.0% |
| Late (R13+) | 2.22 | 0.60 | 1.32 | 8.1 | 0.2% |

The mid-game buys the same amount of Pua as the early game (0.66/turn) despite having 20% more influence. That's the bottleneck showing up — influence is available, but it can't always be converted into Pua.

---

## Root Cause: The Pua Icon Bottleneck

The mid-game lull isn't caused by dead turns. Players are always buying something. The problem is that **on roughly 50% of all turns, a player wants to buy a Pua token but doesn't have the matching icon in their hand.**

| Round | Avg Wasted Influence | Pua Icon Miss Rate |
|---|---|---|
| 0 | 0.4 | 50% |
| 3 | 0.4 | 49% |
| 6 | 0.7 | 52% |
| 9 | 0.9 | 47% |
| 12 | 1.0 | 42% |
| 14+ | 1.1 | 37% |

Half the game is spent holding enough influence to buy Pua but lacking the right color icon in the play area. So players buy market cards instead — perfectly reasonable, but it dilutes the deck further, which makes future icon draws *less* likely, which extends the Pua grind.

This creates a self-reinforcing cycle:

```
Can't buy Pua (no icon)
    → Buy market cards instead
        → Deck grows, icon density drops
            → Even harder to draw icons next turn
                → More turns grinding for Pua
```

The icon miss rate actually *improves* in the late game (dropping from 50% to 37%) because players have acquired more Flower cards with icons and some Wild-icon cards by then. But in rounds 5–9, they're in the worst spot: decks are diluted from early purchases but haven't accumulated enough icon-bearing cards to compensate.

### Why It Doesn't Feel Like a Dead Turn

The fun audit doesn't flag this as a problem because players are still making meaningful choices — which market card to buy, whether to buy Surf, when to use deck-thinning effects. The choices are real. The issue is psychological: the *goal* (complete the next Offering) doesn't advance, even though the *engine* is improving. It's progress without a payoff.

---

## Recommendations

### Fix 1: More Pua Icons in the Starter Deck

**Impact: High. Complexity: Low.**

The starter deck has 3 icon cards out of 11 total (27%). After drawing 5, you'll often get 0–1 icons. Replace one of the six plain 1-Influence starter cards with another colored 1-Influence card (picking a random color). This changes the icon density from 3/11 (27%) to 4/11 (36%) and meaningfully increases the chance of drawing at least one icon per hand.

Expected effect: faster early Pua acquisition, shorter gap between 1st and 2nd Offering, reduced mid-game grind. The economy impact is minimal — it's still a 1-Influence card.

### Fix 2: Wild Pua Purchase at a Premium

**Impact: High. Complexity: Low.**

Add a rule: "You may pay 2 extra Influence to buy a Pua without a matching icon." A player with 7 influence but no Red icon could pay 5 (Red's current price) + 2 = 7 to buy Red Pua anyway.

This creates a genuine decision on every turn where icons are missing: overpay now and stay on track, or buy a card and hope for icons next turn. The 2-Influence premium is steep enough to keep icons valuable but affordable enough to prevent multi-round stalls.

Expected effect: eliminates the worst-case lull turns where a player has 6+ influence and nothing productive to spend it on. The premium means icons remain the preferred path.

### Fix 3: More Wild Icons in the Market Deck

**Impact: Medium. Complexity: Low.**

Currently only Orchid and Pua Kalaunu have Wild icons (6 cards of 72 in the market deck, about 8%). Adding Wild icons to a few more cards — particularly cheaper ones like Sea Turtle (cost 2) or one of the Plumeria variants — would naturally ease the icon bottleneck as players build their decks.

This fix has a gradual effect: it doesn't help in rounds 1–3 (before market purchases enter the deck), but it significantly smooths rounds 5–9 as Wild-icon cards cycle through players' hands.

### Fix 4: Pua Icon on Surf Cards

**Impact: Medium. Complexity: Very Low.**

Surf cards are already a popular purchase (2 Influence for 2 cost, clean economy). Adding a Wild Pua icon to Surf would give them a secondary purpose and create an interesting tension: Surf cards already synergize with Surfboard, Fish, and some Islanders, and adding icon utility would make them even more versatile without making them overpowered (they still have 0 VP).

This is the lowest-effort change that could meaningfully address the lull. Players already buy Surf regularly; giving it icon utility means those purchases double as lull prevention.

---

## Which Fix to Try First

If testing only one change: **Fix 2 (Wild purchase at +2 cost).** It's the most elegant because it doesn't change any card data — just adds one rule — and it directly addresses the root cause (influence available but unconvertible). It also adds a meaningful decision to every affected turn rather than removing the constraint entirely.

If testing a pair: Fix 2 + Fix 1 (extra starter icon). This attacks the problem from both ends — the starter icon helps in rounds 0–4, and the wild purchase premium smooths rounds 5–9.

Avoid stacking all four fixes simultaneously. The icon bottleneck creates some of the game's tension (choosing which color to pursue, timing your Pua purchases around icon draws). Removing it entirely could make Offerings too easy to complete, shortening the game and reducing strategic depth.
