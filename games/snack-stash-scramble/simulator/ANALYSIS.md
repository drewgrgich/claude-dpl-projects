# Snack Stash Scramble v1.4 — Simulation Analysis

**Methodology:** 500 AI-vs-AI games per player count (2P, 3P, 4P), plus 500 games with mixed AI styles (rush/balanced/hoarder/aggressive). All players at expert skill level. Seeded RNG for reproducibility.

---

## Executive Summary

The core rummy loop is solid — games finish reliably in 37-43 turns with no stalls, and the halftime reshuffle mechanic works exactly as designed. However, the simulation reveals **six areas worth attention**, ranging from a meaningful seat-position imbalance to several mechanics that aren't pulling their weight in practice.

---

## 1. Seat Position Balance

| Player Count | Seat 1 | Seat 2 | Seat 3 | Seat 4 | Expected |
|:---:|:---:|:---:|:---:|:---:|:---:|
| 2P | **53.4%** | 46.6% | — | — | 50.0% |
| 3P | **36.4%** | 32.4% | 31.2% | — | 33.3% |
| 4P | **30.2%** | 28.2% | 23.8% | **17.8%** | 25.0% |

**Finding:** First-player advantage is mild at 2P but grows with player count. At 4P, Seat 4 wins only 17.8% — nearly half the expected rate. This is the single biggest balance issue.

**Why it happens:** The first player gets the first shot at the litter box card (which was flipped at random), takes the first draw before the deck thins, and banks first. In a 66-card deck split 4 ways, being one turn behind compounds — by the time Seat 4 acts, 3-4 cards are already gone from the feeder.

**Suggested fix:** Consider asymmetric starting hand sizes (e.g., Seat 1 gets 6 cards, Seat 4 gets 8) or a first-round draw skip for Seat 1. The simulator can test these with `--starting-hand` overrides.

---

## 2. Faction Power Imbalance

Usage per game (3-player baseline):

| Faction | Triggers/Game | Assessment |
|:---:|:---:|:---|
| ORANGE | 3.04 | **Overused.** Free card with no risk — pure upside. |
| PURPLE | 2.07 | Healthy. Extends game clock strategically. |
| BLUE | 1.83 | Healthy. Card swap is situationally strong. |
| YELLOW | 1.34 | Slightly low. Poisoned Peanut is fun but hard to execute. |
| RED | 0.76 | **Underused.** Protection rarely matters in practice. |
| GREEN | 0.73 | **Underused.** Peeking at 3 cards has limited impact. |

**Why ORANGE dominates:** It's the only power with zero cost and guaranteed value — you always get a free card. Every other power is situational.

**Why RED is weak:** The "protect from opponent extensions" scenario almost never arises naturally. Players rarely extend opponents' sets except via the Yellow power (Poisoned Peanut), which itself only fires ~0.4 times per game. RED is defending against a threat that barely exists.

**Why GREEN is weak:** Seeing the top 3 cards of a ~30-card deck is marginal information advantage. By the time you draw again, the card ordering may have been disrupted by other players' actions.

**Suggested fixes:**
- **RED:** Make it also grant +2 or +3 bonus points to the protected set — gives it stand-alone value beyond blocking.
- **GREEN:** Increase the peek to 5 cards, or let the player take one of the peeked cards into hand (making it a mini-draft).
- **ORANGE:** Consider adding a small cost (e.g., must discard a card first) to balance its auto-include status.

---

## 3. Wild Card Risk/Reward

| Metric | Value |
|:---:|:---:|
| Wilds banked per game | 8.5–9.0 (out of 12 in deck) |
| Wilds discarded per game | **0.00** |
| Wilds stuck in hand at game end | **0.00** |

**Finding:** The Jawbreaker Hazard (-10 penalty for wilds in hand) is a *paper tiger*. In 2,000 simulated games across all player counts, **zero wilds were ever caught in anyone's hand at game end.** The AI always finds a way to bank them.

**Why:** Wilds (Rank 0 and 10) fit into literally any group or run. With 6 factions and 11 ranks creating abundant set opportunities, wilds are the easiest cards in the deck to bank. The -10 penalty is scary in theory but never actually materializes.

**This means:** The design tension of "wilds are powerful but risky" doesn't actually exist. They're powerful *and* safe. The Jawbreaker Hazard is flavor text, not a real game mechanic.

**Suggested fixes:**
- **Reduce wild flexibility:** Wilds can only substitute within the same color (require Anchor Rule for *groups* too, not just faction power triggers). This makes them harder to dump into any random set.
- **Add a banking penalty:** Banked wilds are worth 0 points regardless of rank (Rank 10 wilds currently score 10 points when banked — that's reward with no real risk).
- **Increase the hand penalty:** Make it -15 instead of -10.
- **Restrict banking timing:** Wilds can only be banked in sets of 4+ (not 3), requiring more natural cards alongside them.

---

## 4. Pacing & Stagnation

| Metric | 2P | 3P | 4P |
|:---:|:---:|:---:|:---:|
| Avg game length | 43.4 turns | 41.2 turns | 37.9 turns |
| Avg stagnation streak | 3.7 turns | 5.2 turns | 5.6 turns |
| Games with 5+ stagnation | 34% | 51% | **61%** |
| Snack Floor triggers/game | 16.6 | 13.4 | 10.5 |

**Finding:** Stagnation (turns where a player can't bank anything) is common, especially at 4P where 61% of games have at least one player going 5+ turns without banking. The Snack Floor mechanic fires frequently (10-16 times per game), confirming that players regularly drain their hands below 2 cards.

**The stagnation loop:** Player banks everything they can → hand empties to 1-2 cards → Snack Floor draws 3 → those 3 random cards rarely form a set → discard one, hand drops to 2 again → repeat.

**Suggested fixes:**
- **Increase Snack Floor draw to 4 cards** (testable with `--snack-floor-draw 4`). More cards = more set potential.
- **Add a "scavenge" action:** If you can't bank anything, draw an extra card instead of discarding. Breaks the stagnation loop.
- **Reduce min set size to 2 for extensions:** Let players extend banked sets with just 1 matching card (already allowed in rules, but AI rarely does it because hands are too small).

---

## 5. Litter Box Is Nearly Dead

| Metric | Value |
|:---:|:---:|
| Draws from Litter Box per game | **0.85** |
| Draws from Feeder per game | 27–31 |
| Litter Box draw rate | ~3% of all draws |

**Finding:** Players almost never take from the Litter Box. 97% of draws are blind from the Feeder.

**Why:** The Stale Snack Rule blocks the most common scenario (taking what the previous player just discarded), and the visible card is usually whatever the previous player didn't want — which often isn't what you want either. The only time the Litter Box is useful is when you coincidentally need that specific card, which is rare.

**Impact:** This makes the discard decision nearly meaningless — it doesn't matter what you discard because no one takes it anyway. The Litter Box is just a temporary holding pen before the Halftime Sweep shuffles it back in.

**Suggested fixes:**
- **Remove the Stale Snack Rule** and see if it speeds up the game (testable by modifying the `_is_stale_snack` method).
- **Litter Box fan:** Show the top 3 cards of the Litter Box face-up, not just the top 1. More visible options = more reason to look.
- **Litter Box discount:** Drawing from the Litter Box lets you draw 2 cards (pick one, put one back), making it strictly better than a blind draw.

---

## 6. Strategy Differentiation

When running 4 different AI styles against each other (rush/balanced/hoarder/aggressive):

| Style | Win Rate | Avg Score |
|:---:|:---:|:---:|
| Rush (P0) | 27.6% | +42.0 |
| Balanced (P1) | 26.4% | +39.4 |
| Hoarder (P2) | 26.4% | +38.3 |
| Aggressive (P3) | 19.6% | +35.4 |

**Finding:** Rush, Balanced, and Hoarder are nearly indistinguishable in win rate (within noise). Aggressive is slightly weaker, likely due to the seat-4 penalty more than its strategy.

**What this means:** The game doesn't strongly reward different strategic approaches. Whether you bank fast (rush) or accumulate big sets (hoarder), the outcome is roughly the same. This suggests the game is more luck-driven than strategy-driven at its current tuning.

**Note:** When we control for the seat-4 disadvantage, even Aggressive performs comparably. The game's strategy space may be shallow — "bank when you can, draw when you can't" is always correct.

---

## How to Use the Simulator

All files are in `simulator/`. Everything runs with Python 3, no dependencies.

**Quick batch test:**
```bash
python3 run_simulation.py -n 500 -p 3
```

**Test a rule change (e.g., Snack Floor draws 4 instead of 3):**
```bash
python3 run_simulation.py -n 500 -p 4 --snack-floor-draw 4
```

**Compare strategies:**
```bash
python3 run_simulation.py -n 500 -p 4 --preset styles
```

**Watch a single game play out:**
```bash
python3 narrate_game.py -s 42 -p 3 -o game_replay.md
```

**Test beginner vs expert:**
```bash
python3 run_simulation.py -n 500 -p 3 --preset mixed
```

**Override specific config values:**
```bash
python3 run_simulation.py -n 500 -p 4 --wild-penalty 15 --starting-hand 8
```
