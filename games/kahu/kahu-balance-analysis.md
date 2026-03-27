# Kahu Balance Analysis

*Based on 500+ AI-vs-AI simulations at each player count. Data collected March 2026.*

---

## Overall Fun Audit: Grade A

Kahu scores well across all seven fun dimensions. The core loop — build your deck, buy Pua, complete Offerings — produces engaging games with high decision density, strong comeback potential, and virtually zero dead turns. The issues below are refinements to an already solid design.

| Dimension | Grade | Summary |
|---|---|---|
| Decision Density | A | 87% of turns offer 2+ meaningful choice categories |
| Comeback Potential | A | Early leader loses 55% of games; 6.6 lead changes per game |
| Dead Turns | A | 0.0% dead turn rate across 500 games |
| Blowout Rate | A | Only 4% of games are 2x blowouts; 50% decided by ≤3 VP |
| Tension Curve | B | VP accelerates into final third (46%) but not consistently ascending |
| Power Fantasy | A | 100% of games produce wow moments (~9 per game) |
| Interaction Rate | A | 61% of turns involve player interaction |

---

## Issue 1: First-Player Advantage

**Severity: High — this is the biggest balance issue in the game.**

The first player wins significantly more than expected, and the advantage scales with player count:

| Players | P0 Win% | P1 Win% | P2 Win% | P3 Win% | Expected |
|---|---|---|---|---|---|
| 2 | 53% | 47% | — | — | 50% |
| 3 | 44% | 32% | 25% | — | 33% |
| 4 | 38% | 27% | 20% | 15% | 25% |

At 4 players, Player 0 wins 2.5× as often as Player 3. The "finish the round" rule prevents a literal turn-count imbalance but does not address the economy advantage. Going first means first access to the Pua market at lower prices, first pick of the market row, and first crack at 4-VP Offering tokens. That advantage compounds over 12 rounds.

### Recommended Fixes

**Option A — Asymmetric starting resources.** Give later-seat players a small bonus: one free Pua token of their choice (P1 gets 1, P2 gets 1, P3 gets 2 in a 4-player game). This is the lightest-touch fix and easy to playtest. The cost is minimal — one Pua is worth roughly 3–5 influence, or about half a turn's economy.

**Option B — Rotating first player.** First player rotates each round. This is a more structural change and fully eliminates positional advantage, but it adds bookkeeping and changes the game feel (players can no longer plan based on a predictable turn order).

**Option C — Starting hand size bump.** Later-seat players start with 6 cards instead of 5. This gives them more influence and a higher chance of drawing a Pua icon on turn 1, addressing both the economy gap and the icon bottleneck.

---

## Issue 2: Rush Strategy Is Non-Viable

**Severity: Medium — affects strategic depth.**

In a styles matchup (balanced vs. rush vs. economy), the rush player wins only 8% of games despite collecting the most VP tokens (10.0 avg, vs. 7.2 for balanced). Meanwhile the economy player wins 45% from the worst seat position.

The cause: card VP dominates final scoring. Rush players end the game with 8.1 card VP; economy players accumulate 24.6. The Offering tokens (worth 1–4 VP each) are nearly irrelevant compared to the card VP engine a patient player builds.

This means completing Offerings quickly is actively bad strategy — it ends the game before your deck engine pays off. Players are incentivized to delay their 3rd Offering as long as possible, which runs counter to the thematic urgency of the volcano.

| Style | Card VP | Token VP | Bonus VP | Total | Win% |
|---|---|---|---|---|---|
| Balanced (Seat 0) | 17.3 | 7.2 | 6.5 | 31.0 | 47% |
| Rush (Seat 1) | 8.1 | 10.0 | 6.1 | 24.2 | 8% |
| Economy (Seat 2) | 24.6 | 2.7 | 3.9 | 31.2 | 45% |

### Recommended Fixes

**Option A — Increase VP token values.** Change the token set from 4/3/2/1 to 6/5/4/3. This makes the race to complete Offerings first worth roughly double, without changing any other mechanic. Quick wins become genuinely rewarding rather than symbolic.

**Option B — Endgame trigger bonus.** Award +3 VP to the player who triggers the endgame (completes their 3rd Offering first). This directly rewards the rush strategy and creates a dramatic decision point: do you rush to trigger the end, or hold off and build?

**Option C — Reduce base VP on market cards.** If most market cards gave 1 VP instead of 2, the relative importance of tokens and Offering bonuses would increase. This is a broader change and would require retesting the full economy.

---

## Issue 3: 4-Pua Offerings Underperform

**Severity: Medium — affects Offering diversity.**

The four Offerings that cost 4 Pua (Islanders RBYY, Items RBYY, Wildlife RBBY, Removed Cards RRBY) get completed roughly half as often as the four that cost 3 Pua:

| Cost Tier | Examples | Completions/Game (3P) |
|---|---|---|
| 3 Pua (RBY) | Card Types, Flowers, Surfs, Tikis | 1.7–2.4 |
| 4 Pua (RBYY, RBBY, RRBY) | Islanders, Items, Wildlife, Removed Cards | 0.7–0.9 |

That extra Pua costs an additional turn and 3–5 influence — a large tempo hit. In games where the active Offerings are mostly 4-Pua, players fall behind because the Pua grind takes longer, giving opponents more time to build engines.

### Recommended Fixes

**Option A — Reduce all 4-Pua Offerings to 3 Pua.** The simplest fix. If every Offering costs 3 Pua (with different color distributions), the completion rates should equalize. The color distribution (RBY vs. RRB vs. RYY) already creates meaningful asymmetry.

**Option B — Increase the bonus multiplier on 4-Pua Offerings.** If "1 VP per Islander" became "2 VP per Islander," the higher upfront cost would be justified by a larger endgame payoff. This preserves the cost asymmetry as a meaningful strategic choice: cheap Offerings for speed, expensive ones for late-game scaling.

**Option C — Add a Pua rebate.** When completing a 4-Pua Offering, return 1 Pua of the player's choice to their supply. This effectively makes 4-Pua Offerings cost 3 net Pua while keeping the icon-gating of needing all four at once.

---

## Issue 4: Islander Cards Are Over-Represented in Purchases

**Severity: Low — may be intentional design.**

Islander cards are purchased 4× more often than any other card type:

| Card | Purchases/Game |
|---|---|
| Islander (18 unique cards) | 6.5–7.5 |
| Sea Turtle | 1.5–1.8 |
| Pig | 1.4–1.6 |
| Pua Kalaunu | 1.4–1.6 |
| All other cards | 1.0–1.6 |

This is partly because there are 18 unique Islanders in the market deck (vs. 3 copies each of other named cards), so they appear more often. But several Islander effects are also very strong for their cost: free Pua gain, free cards from the market, and draw-2 are all high-impact effects at 5 influence cost.

### Implications

This isn't necessarily a problem if Islanders are meant to be the versatile "workhorse" type. But it does mean:

- The "1 VP per Islander" Offering is easier to cash in than it looks (players will naturally accumulate 4–6 Islanders).
- The "Card Types" Offering (1 VP per unique type, max 6) is trivially easy to complete because players diversify naturally.
- If an Offering set includes both "Islanders" and "Card Types," both will be completed quickly, potentially making those games shorter and less interesting.

### Recommended Fix

Consider bumping the cost of the strongest Islanders (free Pua gain, free market card, draw-2) from 5 to 6 influence. This preserves their power while making them harder to acquire casually.

---

## Issue 5: Lava Eruption Is Rare

**Severity: Low — functions well as tension device even if rare.**

The lava eruption end condition triggers in only 2–8% of games depending on player count. The lava track serves primarily as an escalation timer that creates interesting events (Second Lava at 15, Tiki Lockout at 12, Market Wipe at 10) rather than as a genuine alternate ending.

This is fine thematically — the *threat* of eruption adds tension even when it rarely occurs. But if the design intent is for eruption to be a real strategic consideration (e.g., a player deliberately letting lava advance to end the game before opponents complete Offerings), the starting position would need to be lower or the lava would need to advance faster.

### Optional Fix

If more eruption games are desired, reduce the starting lava position by 2–3 spaces at each player count. This would roughly double the eruption rate without changing the escalation event thresholds.

---

## Issue 6: Tension Curve (B Grade)

**Severity: Low — already good, room to be great.**

VP accelerates into the final third of the game (46% of VP scored late), which is the right shape for competitive games. However, only 43% of games have a strictly ascending tension curve. The issue: the first Offering completion often comes in rounds 3–5, creating a VP spike before the mid-game engine-building phase.

This would likely improve naturally if Issues 2 and 3 are addressed. Higher VP token values make the endgame race for first-completion more dramatic, and evening out Offering costs removes the "easy first Offering, hard second" pattern that front-loads scoring.
