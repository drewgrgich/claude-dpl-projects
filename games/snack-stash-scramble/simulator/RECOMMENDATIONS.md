# Snack Stash Scramble — Rule Change Recommendations

**Based on:** 4,500 AI-vs-AI simulated games across 9 configurations (baseline + 7 individual variants + 1 combined fix), all at 4 players where issues are most pronounced.

---

## The Three Changes Worth Making

### 1. Add the Scavenge Rule (stagnation fix)

**The rule:** If a player couldn't bank anything on their previous turn, they draw 2 cards from the Feeder instead of 1 on their next draw phase. (This doesn't stack with Snack Floor — if hand ≤2, Snack Floor still triggers normally.)

**What it does:**

| Metric | Baseline | With Scavenge | Change |
|:---|:---:|:---:|:---|
| Stagnation (5+ turns without banking) | 61% | **8%** | Crushed |
| Avg worst stagnation streak | 5.6 turns | **2.6 turns** | Cut in half |
| Seat win-rate spread | 12.4% | **6.3%** | Nearly halved |
| Seat 4 win rate | 17.8% | **22.4%** | +4.6% |

**Why it works:** The stagnation loop in v1.4 is: bank everything → hand drops to 1-2 cards → Snack Floor draws 3 random cards → can't form a set → discard, hand drops again → repeat. Scavenge breaks this by giving stuck players an extra card. One additional card dramatically increases set-forming probability, so players escape stagnation within 1-2 turns instead of 5+.

**Why this is the right version of the fix:** We also tested Snack Floor draws 4 (modest improvement, 61%→53%) and Snack Floor threshold ≤3 (42% but worsened score spread). Scavenge is more targeted — it only helps players who are actually stuck, rather than accelerating everyone. It doesn't shorten the game nearly as much either.

**Flavor suggestion:** *"Desperate Sniffing — When your last turn came up empty, you sniff around harder and draw 2 cards instead of 1."*

---

### 2. Remove the Stale Snack Rule (Litter Box fix)

**The current rule:** You can't take the top card of the Litter Box if the previous player just discarded it.

**Recommendation:** Delete this rule entirely.

**What it does:**

| Metric | Baseline | No Stale Snack | Change |
|:---|:---:|:---:|:---|
| Litter Box draws per game | 0.84 | **17.84** | 21x increase |
| Stagnation 5+ rate | 61% | **48%** | -13% |
| Seat win-rate spread | 12.4% | **9.2%** | -3.2% |
| Score spread (best-worst player) | 6.9 pts | **4.5 pts** | Tighter |
| Avg final score | 39.1 | **46.0** | Higher scoring |

**Why it works:** The Stale Snack Rule was meant to prevent "take-back" plays, but in practice it kills the entire Litter Box mechanic. With the rule in place, the Litter Box is basically a graveyard — nobody draws from it, so the discard decision is meaningless. Remove the rule, and suddenly the discard becomes *the most interesting decision in the game*: "Do I discard this card knowing the next player might want it?"

**A secondary benefit:** Litter Box draws give players *targeted* cards instead of blind draws. This is directly anti-stagnation — if you need a RED 7 and someone just discarded one, you can take it. More targeted draws = more set completion = less stagnation.

**What about abuse?** Two players could theoretically pass cards back and forth. In practice this doesn't happen because it costs you a turn each time and the rest of the table advances. The simulation shows no degenerate patterns.

---

### 3. Asymmetric Starting Hands (seat balance fix)

**The rule:** Instead of everyone starting with 7 cards, deal based on turn order. In a 4-player game: Seat 1 gets 6 cards, Seats 2-3 get 7, Seat 4 gets 8.

**What it does:**

| Metric | Baseline | 6/7/7/8 | Change |
|:---|:---:|:---:|:---|
| Seat 1 win rate | 30.2% | 19.0% | Reduced advantage |
| Seat 4 win rate | 17.8% | **29.0%** | Huge improvement |
| Seat win-rate spread | 12.4% | **9.6%** | Tighter |

**Calibration note:** The 6/7/7/8 split slightly overcorrects — Seat 1 becomes the weakest seat. The ideal split for 4P is probably **6/7/7/7** or **7/7/7/8**. For 3P, try **6/7/7**. For 2P, no adjustment needed (the 53/47 split is within normal range).

**Flavor suggestion:** *"Late arrivals to the snack pile get first pickings — Seat 4 was closest to the pantry and grabbed an extra snack before sitting down."*

---

## Changes We Tested But Don't Recommend

### Banked Wilds Worth 0 Points — Rejected

We tested making wild cards score 0 when banked (Rank 10 wilds currently score 10 points). The result: identical gameplay with scores just shifted down by ~15 points. The AI banked wilds at the exact same rate because the -10 hand penalty still makes banking them a no-brainer. The problem isn't that wilds score too many points — it's that they're trivially easy to bank into any set. Reducing their bank value doesn't fix this.

To actually create wild card tension, you'd need to restrict *where* they can be played (e.g., "wilds can only be used in runs, not groups"), which is a bigger design change than a number tweak.

### Snack Floor Draws 4 — Superseded by Scavenge

Drawing 4 instead of 3 on Snack Floor does reduce stagnation (61%→53%), but it's a blunt instrument — it accelerates ALL players equally, including those who aren't stuck. It also shortens games by 5 turns, which means less play time. Scavenge is strictly better because it targets only stuck players.

### Snack Floor Threshold ≤3 — Mixed Results

Triggering Snack Floor at ≤3 cards instead of ≤2 drops stagnation (61%→42%) but worsens the score spread between best and worst players (+2 points wider). It also shortens games by 7 turns. Not recommended as a standalone change.

### Buffed RED (+3 bonus) & GREEN (peek 5, take 1) — Too Subtle

Adding +3 bonus points to RED-protected sets and letting GREEN take 1 of 5 peeked cards produced only marginal improvements. The AI's behavior barely changed because the relative power ranking stayed the same — ORANGE is still the best power by far. To truly fix faction balance, ORANGE probably needs a cost (e.g., "discard one card first") rather than buffing the others up.

---

## The Combined Fix

When we applied Scavenge + No Stale Snack + Asymmetric Hands + Buffed RED/GREEN all together:

| Metric | Baseline | Combined | Change |
|:---|:---:|:---:|:---|
| Stagnation 5+ rate | **61%** | **23%** | -38% |
| Seat 4 win rate | **17.8%** | **29%** | +11.2% |
| Seat win-rate spread | **12.4%** | **10%** | -2.4% |
| Litter Box draws/game | **0.84** | **20.4** | Litter Box lives! |
| Avg final score | **39.1** | **46.0** | Higher scoring |
| Game length | **37.9** | **42.0** | Slightly longer |

The combined fix addresses stagnation, seat balance, and the dead Litter Box simultaneously. The slight increase in game length (+4 turns) comes from the Litter Box being used — more draws = more play, which is a good kind of longer. Games are richer, not padded.

---

## Priority Order

If you want to make changes incrementally:

1. **Scavenge first** — biggest single-mechanic impact, easy to add, and easy to explain to players
2. **Remove Stale Snack Rule second** — zero rules to add (it's a deletion), resurrects a dead mechanic
3. **Asymmetric hands third** — needs some playtesting to calibrate the exact numbers per player count

---

## How to Re-test

All variants are testable with the simulator. Edit `config.json` or run `test_variants.py` to tweak parameters:

```bash
# Run all variants vs baseline
python3 test_variants.py

# Test a specific combo
python3 run_simulation.py -n 500 -p 4  # Then edit config.json

# Watch a game with the combined fix
python3 narrate_game.py -s 42 -p 4 -o game_v2.md
```
