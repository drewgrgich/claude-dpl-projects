# Kahu v2.0 — Balance Patch

*This document contains the recommended rule changes from the Designer Corps*
*balance analysis. Apply these changes to kahu-rules-v1.0.md for a more*
*balanced gameplay experience.*

---

## CHANGE 1: Lava Track Starting Values

**Problem**: In 2-player games, lava rarely threatens the village before
Offerings end the game. Lava becomes irrelevant.

**Fix**: Adjust starting lava for 2-player games.

| Players | v1.0 | v2.0 |
|---------|------|------|
| 4 | 22 | 22 (no change) |
| 3 | 20 | 20 (no change) |
| 2 | 16 | **12** |

**Rationale**: Lower starting lava in 2-player creates genuine time pressure.
With fewer players triggering lava, the track needs a head start to matter.

---

## CHANGE 2: Offering VP Tokens

**Problem**: VP tokens from Offerings (4/3/2/1) are overwhelming compared to
card economy. This creates a "rush Offerings or lose" meta where the
optimal strategy is obvious.

**Fix**: Reduce the first Offering's VP value.

| Order Completed | v1.0 | v2.0 |
|-----------------|------|------|
| 1st | 4 VP | **3 VP** |
| 2nd | 3 VP | 2 VP |
| 3rd | 2 VP | 1 VP |
| 4th | 1 VP | 1 VP |

**Rationale**: First-offerings are still rewarding but no longer dominant.
Card economy and Offering bonuses become comparatively more valuable.

---

## CHANGE 3: Offering Completion Cooldown

**Problem**: A player who completes their first Offering early can often
complete a second and third before opponents can react. This creates a
"runaway leader" problem.

**Fix**: Add a mandatory wait between Offering completions.

**New Rule (insert after "Complete an Offering" in Spend Influence step):**

> **Offering Cooldown**: Once you complete an Offering, you must wait
> until every other player has taken at least one turn before you may
> complete another Offering. This "round gap" is mandatory regardless of
> how much Pua you have accumulated.

**Exception**: If the Lava Tracker reaches space 5 or below, the cooldown
is waived — the race to the finish is on.

**Rationale**: Prevents one player from chaining Offerings. Gives opponents
a real catch-up window. The waiver at space 5 preserves the dramatic
"sprint to the finish" when lava is threatening.

---

## CHANGE 4: Tiki Cost Reduction

**Problem**: Tikis cost 1 Red + 1 Blue + 1 Yellow Pua (3 resources) but
only block a single Lava Flow trigger. The cost-to-benefit ratio is poor,
making Tikis a trap purchase.

**Fix**: Reduce Tiki cost by one color.

| | v1.0 | v2.0 |
|-|------|------|
| Tiki cost | 1 Red + 1 Blue + 1 Yellow | **1 Red + 1 Blue** |

Yellow Pua is still useful for Offerings but Yellow Tikis are too niche.

**Rationale**: Tikis become a genuine tactical option — a worthwhile
purchase when lava is at space 8 or lower, not just a sunk cost.

---

## CHANGE 5: Surf Card VP

**Problem**: Surf cards (cost 2, influence 2, VP 0) are pure "dumps" with
no VP value. Players who buy Surf feel like they're wasting their turn.

**Fix**: Give each Surf card 1 VP.

| | v1.0 | v2.0 |
|-|------|------|
| Surf VP | 0 | **1** |

**Rationale**: Surf becomes a "break even" purchase (spend 2, get 2
influence + 1 VP) rather than a pure loss. Surf strategies become
marginally viable.

---

## CHANGE 6: Starting Pua (House Rule for 2-Player)

**Problem**: In 2-player games, the Pua economy can deadlock early as
players struggle to acquire matching icons for buying Pua.

**Fix (Optional — for 2-player games only):**

> At the start of the game, each player receives 1 Pua token of each
> color (Red, Blue, Yellow) from the village store as a blessing.
> This represents the village's contribution to your offering fund.

**Rationale**: Prevents economic deadlock in 2-player. The village
contribution is thematically appropriate and speeds up the game to a
more exciting pace.

---

## Summary of All Changes

| Change | Impact |
|--------|--------|
| Lava start = 12 (2-player) | Lava is threatening in 2-player games |
| Offering tokens = 3/2/1/1 | Card economy more valuable |
| Offering cooldown | Prevents runaway leaders |
| Tiki cost = 1R+1B | Tikis are tactically relevant |
| Surf = 1 VP | Surf不再是陷阱 |
| Starting Pua (2P) | 防止经济死锁 |

---

*These changes are the result of Monte Carlo simulation (500 games per*
*iteration, 3 iterations). They address the most critical balance issues*
*identified: lava irrelevance, offering dominance, and Tiki/Surf trap cards.*

*For the full simulation data, see ITERATION-01-analysis.md,*
*ITERATION-02-analysis.md, and ITERATION-03-analysis.md in this directory.*
