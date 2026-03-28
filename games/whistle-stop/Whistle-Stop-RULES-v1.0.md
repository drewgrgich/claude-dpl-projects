# 🐹 Whistle Stop v1.0

**A Route-Building Racing Card Game for 2–4 Players**
*Part of the Hamsters & Monsters Collection*

---

## The One-Sentence Pitch

Build the rails, time your departure, and race to the station — but early trains get less steam.

---

## What You Need

- **The Deck:** 66 cards
  - **44 faction cards:** 4 factions × 11 ranks (0–10)
  - **22 wild cards:** 11 wild 0s + 11 wild 10s (factionless)
  - Factions: 🔴 Red, 🔵 Blue, 🟢 Green, 🟡 Yellow

**No tokens. No dice. No board. Just cards.**

---

## Setup

1. **Shuffle** the deck.
2. **Deal 3 cards** to each player, face-down.
3. **Place the Depot:** Flip the top deck card face-up — this is the **Depot** (start of the route).
4. **Each player marks their train** at the Depot (remember it — you're at position 0).

> Cards are drawn back to 3 at the end of each round.

---

## How to Play — Round by Round

Each round has **5 phases**:

### Phase 1: Choose Secretly
Everyone **chooses 1 card** from hand and holds it face-down.

### Phase 2: Reveal (Low → High)
Reveal all cards **lowest rank first, highest last**. Ties reveal simultaneously.

### Phase 3: Place Your Card
Starting with the lowest revealed, each player **places their card** at the end of the route.

- Cards go **end-to-end** — the route is a straight line growing from the Depot.
- The route extends by **1 card per player per round**.
- Cards played earlier build the route; cards played later ride what was built.

### Phase 4: Move Your Train
After placing, **move your train forward** along the route:

- Move up to **[your card's rank + faction bonus]** steps.
- You **cannot move past the last placed card** in the route.
- You may move fewer steps than allowed.

**Faction Bonus:** When your card's faction matches yours, you get **+1 extra step**:
- 🔴 Red, 🔵 Blue, 🟢 Green, 🟡 Yellow: all get +1 step

### Phase 5: Score!
**Each card you pass through** = **½ VP** (rounded). Red cards passed through = **1 VP each**.

**The card you land on** = **½ × its rank** VP. Red cards landed on = **rank VP**.

**Wild 10:** Your entire round score is **doubled** (×2).

---

## Scoring Example

You play a **Green 7** (and you're Green). You move 8 steps (7 + 1 bonus):

- Pass through 3 cards: 3 × ½ = **1½ VP**
- Land on a **Blue 8**: 8 × ½ = **4 VP**
- **Total: 5½ VP**

If the landed card were **Red 8** (Red doubles your landed VP): 8 × 1 = **8 VP** + 1½ = **9½ VP**

---

## End Condition

The game ends when the **20th card** is placed in the route (the **Station**).

That player gets **+10 VP** bonus.

**The Station itself** (the 20th card) is worth **0 VP** — it's the finish line!

**Highest VP wins!**

---

## Special Cards

### 0s — Jokers
- **Rank 0:** Move 0 steps (but you DID build the route!)
- **Wild 0s:** Can be declared as any rank (1–9) and any faction when revealed
  - Declared rank = movement steps
  - Declared faction = grants faction bonus
  - Actually scoring uses the card's real rank (0) = **0 VP landed**

### 10s — Express
- **Rank 10:** Move up to 10 steps
- **Wild 10s:** Rank 10, factionless, **doubles your entire round score**

---

## Factions

| Faction | Bonus | Strategy |
|---------|-------|---------|
| 🔴 Red | +1 step + Red cards score 2× | Aggressive — high risk, high reward |
| 🔵 Blue | +1 step | Balanced — reliable movement |
| 🟢 Green | +1 step | Flexible — matches any card |
| 🟡 Yellow | +1 step | Flexible — matches any card |

> Green and Yellow are **flexible** — their +1 applies to whichever card they play, even if the card's faction is different.

---

## 2-Player Variant

Same rules, but with a twist:

- Route can **branch** — extend from any card, not just the end.
- **Strategic blocking:** Place cards to cut off your opponent's route.
- First to the Station still wins, but the route is a maze.

---

## Solo Mode (vs AI)

Play against the AI using the same rules. The AI:

1. Picks the highest-movement card from its hand
2. Extends from the route end
3. Moves its full movement value

**Solo Challenge:** Beat the AI's VP. First to 50 VP (or highest after the same number of rounds) wins!

---

## Quick Reference

```
WHISTLE STOP — QUICK RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

SETUP: 3 cards each. Depot starts route.

EACH ROUND:
  1. Choose 1 card secretly
  2. Reveal low → high
  3. Place card at route end
  4. Move train (rank + faction bonus steps)
  5. Score: passed = ½ VP each, landed = ½ × rank VP

SCORING:
  • Passed through = ½ VP (Red = 1 VP)
  • Landed on = ½ × rank (Red = rank VP)
  • Wild 10 = round score × 2
  • Station placed = +10 VP bonus
  • Comeback bonus = 1 VP per step behind leader

END: 20 cards in route = Station → most VP wins

FACTION BONUS: All factions get +1 step when matching

SPECIAL:
  0 = 0 movement (but builds route)
  Wild 0 = declare rank + faction when revealed
  Wild 10 = rank 10, ×2 score this round
  Red cards = all Red VP doubled
```

---

## Design Notes

*Whistle Stop is the first racing/route-building game in Hamsters & Monsters. The core tension — "do I build early with low cards or ride high with powerful moves?" — creates genuine decision-making without cognitive overload. The shared route means every player affects every other player. The simultaneous reveal means everyone commits before knowing what others did.*

*The comeback mechanic (1 VP per step behind) ensures trailing players always have a shot at victory, keeping every round exciting.*

*— Morgan, Jordan & Casey (The Designer Corps)*
