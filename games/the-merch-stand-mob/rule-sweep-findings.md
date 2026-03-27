# The Merch Stand Mob — Rule Sweep Findings

**Date:** March 15, 2026
**Method:** 500 AI-vs-AI games per configuration, seeded for reproducibility
**Simulator:** v1.0, all 6 faction abilities active, 4 AI play styles

---

## Sweep 1: Trample Threshold at 3 Players

**Question:** The 3-player Trample threshold (3 cards) is lower than 4-5 player (4 cards). Should it be raised?

| Metric | Threshold=3 (current) | Threshold=4 | Threshold=5 |
|--------|----------------------|-------------|-------------|
| Avg Tramples/game | 4.87 | 2.85 | 1.49 |
| Zero-Trample games | 0.0% | 1.6% | 14.0% |
| Avg cards lost/game | 5.2 | 3.6 | 1.9 |
| Avg VP | 17.3 | 20.5 | 23.8 |
| 1st set completion | 42.6% | 51.9% | 62.5% |
| VP spread (winner-last) | 21.5 | 24.5 | 28.3 |
| Win rate spread | 3.2% | 8.4% | 4.0% |
| Game length | 6.7 rounds | 6.6 rounds | 6.6 rounds |

### Analysis

**Threshold=3 (current)** is brutal. Nearly 5 Tramples per game, zero games without one. Players lose an average of 5.2 cards to Trample — in a game where you only claim about 3.5 cards total. That means Trample destroys more than a full game's worth of collected merch. The saving grace: VP spread is the tightest (21.5), meaning everyone gets crushed roughly equally.

**Threshold=4** is the sweet spot. Tramples drop to 2.85/game — still a meaningful threat (only 1.6% of games avoid it entirely) but no longer a certainty every round. Average VP rises 18% from 17.3 to 20.5, meaning players actually get to keep some of their merch. Set completion jumps to 51.9%. The downside: win rate spread doubles from 3.2% to 8.4%, suggesting slightly less competitive randomness, but 8.4% is still well within acceptable range for a 3-player game.

**Threshold=5** goes too far. Tramples become rare events (14% of games have none), scores inflate to 23.8 avg VP, and 62.5% of players complete a color set. The Mosh Pit loses its teeth. VP spread balloons to 28.3, meaning the leader pulls far ahead unchecked.

**Recommendation: Raise 3-player Trample threshold to 4.** Unifies the rule across all player counts (no "special 3-player exception" to remember), preserves Trample as a real threat without making it oppressive, and improves the set collection experience meaningfully.

---

## Sweep 2: Set Bonus Progression

**Question:** The 2nd set bonus (6 colors = 8VP) almost never fires (0.2%). Should we add intermediate bonuses or lower the bar?

| Metric | Baseline (3=5, 6=8) | +Mid (3=5, 4=3, 6=8) | Lower 2nd (3=5, 5=8) | Both (3=5, 4=3, 5=8) |
|--------|---------------------|----------------------|-----------------------|----------------------|
| Avg VP | 16.9 | 17.3 | 17.0 | 17.4 |
| Avg set bonus | 2.0 | 2.4 | 2.1 | 2.5 |
| 2nd set rate | 0.2% | 0.2% | 0.2% | 0.2% |
| VP spread | 22.8 | 23.7 | 23.1 | 24.0 |
| Win rate spread | 6.2% | 7.6% | 5.4% | 7.0% |

### Analysis

**The color distribution doesn't change.** This is the key finding. All four configurations produce identical color distributions (5.5% at 0, 21.4% at 1, 32.8% at 2, etc.). The bonus structure doesn't influence player behavior enough to change how many colors they actually collect — because the Trample pressure and short game length are the binding constraints, not the reward structure.

Even lowering the 2nd set to 5 colors doesn't help: only 1.2% of players reach 5 colors regardless of the reward. The 2nd set bonus remains decorative in all variants.

The mid-set bonus (4 colors = 3VP) adds 0.4 VP on average — marginal. It slightly increases VP spread and win rate spread without meaningfully changing the game.

**Recommendation: This isn't where the lever is.** The reason the 2nd set never fires isn't that 6 colors is too many — it's that Trample destroys collected colors too aggressively and games end too quickly for broad collection. If Sweep 1's recommendation is adopted (raising 3-player threshold to 4), the set bonus picture may improve naturally. Re-run this sweep after the Trample change before adding bonus complexity.

If you do want to add a bonus, the cleanest option is **4 colors = 3VP** as an intermediate step. It's a small reward (not game-warping) that gives collectors a meaningful partial payoff. But the priority is fixing Trample first.

---

## Sweep 3: Sneak Cancellation at 5 Players

**Question:** Sneak success rate at 5 players is only 23%. Should Sneaks cancel at 3+ instead of 2+?

| Metric | Cancel at 2+ (current) | Cancel at 3+ |
|--------|----------------------|-------------|
| Sneak success rate | 22.9% | 55.9% |
| Sneak attempts/game | 3.7 | 3.7 |
| Sneak successes/game | 0.8 | 2.1 |
| Shoves/game | 4.5 | 4.5 |
| Avg VP | 12.8 | 12.9 |
| VP spread | 21.7 | 21.8 |
| Win rate spread | 2.8% | 2.4% |
| Tramples/game | 4.70 | 4.71 |
| Game length | 5.0 rounds | 5.0 rounds |

### Analysis

**The Sneak success rate more than doubles** from 23% to 56%, restoring the Sneak/Shove tension that defines the game. Players attempt Sneaks at the same rate (3.7/game) but succeed far more often (2.1 vs 0.8 successes/game).

**Everything else stays remarkably stable.** Same VP, same game length, same Trample rate, near-identical VP spread. The win rate spread actually improves slightly (2.4% vs 2.8%). This tells us the change is surgical: it fixes the Sneak viability problem without creating new imbalances.

The reason Trample doesn't change is elegant: successful Sneaks avoid the Pit entirely, so more successful Sneaks = fewer cards entering the Pit. But the same number of Sneaks are attempted either way (the AI considers Sneaks similarly attractive at both thresholds), so the total cards committed per round stays similar.

**Recommendation: At 5 players, cancel Sneaks at 3+ instead of 2+.** This is the cleanest change in the entire sweep — large improvement to one specific metric (Sneak viability at 5p), zero collateral effects. It makes the 5-player game feel more like the 3-4 player game where the Sneak/Shove decision actually matters.

---

## Priority Summary

| Priority | Change | Confidence | Impact |
|----------|--------|-----------|--------|
| 1 | Raise 3p Trample threshold from 3 → 4 | High | Reduces oppressive Trample, improves scoring |
| 2 | Cancel Sneaks at 3+ (5p only) | High | Restores core tension, zero side effects |
| 3 | Add 4-color=3VP mid-set bonus | Low | Marginal impact; revisit after Trample fix |
| — | Lower 2nd set to 5 colors | Not recommended | Doesn't change behavior, adds rule complexity |
