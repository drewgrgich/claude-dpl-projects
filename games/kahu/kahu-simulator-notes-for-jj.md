# Kahu Simulator — Implementation Notes

*Notes from building a Kahu AI-vs-AI simulator. These are the tricky spots, edge cases, and rule ambiguities that bit us during development. Sharing so you don't have to rediscover them.*

---

## 1. Lava Flow Resolution Order Is Critical

The Lava Flow card must resolve **before** any other card abilities fire and **before** influence is counted. This sounds simple but creates cascading complications:

- If a card effect causes a mid-turn draw (Pineapple, Outrigger, Islander draw-2) and a Lava Flow is among the drawn cards, it fires **immediately** — in the middle of resolving other effects. Your simulator needs to handle Lava interrupts at any point during the effect resolution phase, not just at the start of the turn.

- If a player has two Lava Flow cards in hand (after the Second Lava escalation event), both must resolve before anything else. If the first one consumes the Tiki, the second one advances the lava tracker — and that second advance can itself trigger an escalation event mid-resolution.

- Make sure you handle the chain: Lava Flow drawn mid-turn → Tiki check → possible lava advance → possible escalation event → escalation event side effects (Second Lava adds *another* Lava card to all discard piles) → then resume the original card effect. If you don't structure this as a recursive or stack-based resolution, you'll get subtle ordering bugs.

---

## 2. Three Cards Safely Discard Lava Flow — Nothing Else Does

Pineapple, Outrigger, and Chicken can route a Lava Flow to the discard pile without triggering it. **Every other draw effect triggers Lava immediately.** This distinction is easy to get wrong because the effects look similar:

| Card | What it does | Lava safe? |
|---|---|---|
| Pineapple | Draw 2, may keep or discard each | Yes — you may choose to discard Lava |
| Outrigger | Draw 3, discard 1 | Yes — you may choose Lava as the discard |
| Chicken | Reveal/discard top of any player's deck, may play it | Yes — you may choose not to play Lava |
| Islander (draw 2) | Draw 2 cards | **No** — Lava fires immediately |
| Sugar Cane | Discard 4, draw 4 | **No** — Lava fires from drawn cards |
| Sea Turtle | Reveal top card | **No** (but it only adds Flowers to hand, so Lava gets discarded — treat this case carefully) |

If your simulator doesn't distinguish these, you'll either over-trigger Lava (making the game harder than it is) or under-trigger it (making Tikis seem useless).

---

## 3. The Pua Price Shift Mechanic Has a Ceiling Rule

When you buy Pua at the 3 or 4 price (normal range), that color goes up by 1 and the color already at the new price drops by 1. But **buying at the highest price (5 normal, 6 after escalation) does not shift prices.** This is easy to miss and it matters a lot for simulation accuracy.

The mechanic works like a three-position sliding scale. At any time, the three prices are always three consecutive integers (3/4/5 or 4/5/6 after the Pua Price Increase escalation). Buying cheap pushes up; buying expensive holds steady. If you implement this as a general +1/-1 without the ceiling check, you'll get prices drifting outside the valid range.

Here's the state machine:

```
Before: Red=3, Blue=4, Yellow=5
Buy Red (price 3): Red→4, Blue→3 (Blue drops to fill the gap), Yellow=5
After:  Red=4, Blue=3, Yellow=5

Before: Red=4, Blue=3, Yellow=5
Buy Yellow (price 5): No change — bought at ceiling
After:  Red=4, Blue=3, Yellow=5
```

Also note: after the Pua Price Increase escalation at lava position 7, **all three prices go up by 1 simultaneously** and the range shifts to 4/5/6. The shift mechanic continues working within the new range. Don't forget to update the ceiling.

---

## 4. The Market Slide Is Not a Simple Left-Shift

When cards are purchased from the market, the remaining cards **slide right** (toward the discount slot), and empty slots refill **from the left** (from the market deck). This is the opposite of what most people assume on first read.

The discount always applies to the **rightmost occupied slot**, not a fixed position. After the Market Shrink at lava position 10, the market goes from 5 slots to 4, but the rightmost of those 4 still gets the discount.

If you implement this as "fill from right, slide left" you'll get a subtly different market economy — cards will age toward the expensive end instead of the cheap end, making the discount less impactful.

---

## 5. Tiki Placement and Lifecycle

Tikis have an unusual lifecycle that doesn't match any other card type:

- Tikis go directly into the **play area**, not the discard pile. They sit in front of the player permanently.
- Tikis are **not discarded** during the Cleanup & Draw phase. They survive across turns.
- When a Tiki absorbs a Lava Flow, **it goes to the discard pile** (not removed from game). It will eventually cycle back through the deck, but it's just a 0-influence, 0-VP card at that point.
- Tiki use is **mandatory**. If you have a Tiki and draw Lava Flow, you must use the Tiki. You cannot choose to advance lava instead.
- A player can only have **one Tiki in play at a time**. They can buy another after the first absorbs a Lava Flow.
- After Tiki Lockout (lava position 12), no new Tikis can be claimed, but existing ones remain active.

In our implementation, the Tiki is stored on the Player object separately from the play area, hand, and deck. It's a single optional card, not part of the deck cycle. For final scoring, any Tiki still in play counts toward the player's card collection (relevant for the "3 VP per Tiki" Offering bonus).

---

## 6. Endgame Trigger vs. Game Over Are Two Separate Events

The endgame triggers when a player collects their 3rd VP token **or** lava reaches 0. But the game doesn't end immediately — it finishes the current round so all players have taken the same number of turns.

This means:

- Endgame can trigger on Player 0's turn, and Players 1–3 still get their turns in that round.
- Those final turns are real turns. Players can complete Offerings, buy cards, and score VP. A trailing player can absolutely overtake the trigger player in those final turns.
- If lava reaches 0 mid-round, play continues to the end of the round. Nothing special happens at position 0 — there's no "eruption penalty."

Track `endgame_triggered` and `game_over` as separate flags. Set `endgame_triggered = True` when the condition is met, then set `game_over = True` at the end of the round (when the turn counter wraps back to Player 0).

---

## 7. The Escalation Events Can Chain

Lava advancing by 1 can trigger an escalation event, which has side effects that matter for the rest of the current turn. But lava only advances by 1 per Lava Flow card — escalation events don't advance it further. The important chains are:

- **Second Lava (position 15)** adds a Lava Flow to every player's discard pile. These new Lavas don't do anything immediately — they'll show up in future hands. But if a player is about to reshuffle their discard pile into their draw pile this turn, the new Lava is now in the mix.

- **Market Wipe + Shrink (position 10)** discards all market cards and refills with new ones, then permanently removes the 5th slot. If this triggers mid-turn (during a Lava resolution before the player has spent influence), the player is now shopping from a completely new market. Any cards they were planning to buy are gone.

- **Pua Price Increase (position 7)** raises all prices by 1 immediately. If this triggers mid-turn, the player's Pua purchase plans just got more expensive. This can matter if the player had exactly enough influence to buy a Pua at the old price.

In our implementation, escalation events fire inside `advance_lava()` before control returns to the turn sequence. This means the player experiences the escalation effect on their own turn, which matches the rules ("resolve immediately before the current player continues their turn").

---

## 8. Card Effect Ambiguities We Had to Decide

The CSV card data uses free-text effect descriptions. Several effects are ambiguous enough that a simulator has to make a ruling:

**Sugar Cane ("Discard 4 cards to draw 4")** — Discard from where? Our reading: discard 4 cards from your play area (the cards you played this turn), then draw 4 from your draw pile. This is a powerful cycle effect but requires having 4 other cards in play worth sacrificing. We simplified this to a no-op in simulation because the AI decision tree for "which 4 of my 5 play-area cards should I sacrifice" is complex and the effect is relatively rare.

**Islander "Choose a card you already played this turn and play it again"** — Does "play it again" mean you get its influence again? Does the effect trigger again? We treated this as: add the card's influence to the total a second time, and resolve its effect a second time. This makes the card very strong (effectively doubles another card).

**Islander "Use any card from the market as if you own it, then put it at the bottom of the market pile"** — We interpreted this as: resolve the market card's effect and add its influence for this turn, then the card goes to the bottom of the market deck (not back to the market row). The card is not "purchased" — it's borrowed.

**Chicken "reveal and discard the top card of their deck; you may play that card as if it were your own"** — If the revealed card is Lava Flow, you may choose NOT to play it, and it goes to the discard pile without triggering. This is one of the three safe-discard exceptions. If you do choose to play a non-Lava card, it goes to your play area for this turn only, then to the **opponent's** discard pile during cleanup (we chose to send it to the active player's discard pile instead for simplicity — worth deciding which way you want to rule).

**Nene Goose "play the top card of any single player's discard pile as if it was your own"** — Same ownership question as Chicken. We played it as: the card's effect and influence apply to you this turn, but the card stays in (or returns to) the opponent's discard pile.

Document your rulings for each of these. The effects are edge-case-heavy and different rulings will produce different simulation data.

---

## 9. The CSV Has Duplicate Rows — It's Intentional

The card CSV has what look like duplicate rows (e.g., three copies of Orchid, three copies of Sea Turtle). These aren't data errors — the game has multiple copies of each card in the market deck. Each row is one physical card. Load all rows, not just unique names.

Also note: the first column in the CSV is an unlabeled count column that always contains "1". Ignore it or account for it when parsing.

---

## 10. Islander Cards Are 18 Unique Effects, Not a Uniform Type

Unlike Flower, Item, and Wildlife cards (which have 2–3 copies of each named card), the 18 Islander cards are **all unique**. Each has a different cost and a different effect. The CSV lists them all as "Islander" in the Card Name column, distinguishable only by their Cost and Card Effect fields.

This means you need to parse each Islander individually. We used keyword matching on the effect text to assign machine-readable effect IDs. A few keywords that reliably distinguish them:

| Keyword in effect text | Effect |
|---|---|
| "discard pile is empty" | +2 influence bonus |
| "wildlife cards cost 1 less" | Wildlife discount this turn |
| "tiki in play" | +3 influence bonus |
| "gain a surf card" | Free Surf from supply |
| "play it again" | Replay another card |
| "gain any item" | Free Item from market |
| "draw two cards" | Draw 2 (Lava-unsafe) |
| "gain red pua" | Free Red Pua |
| "gain blue pua" | Free Blue Pua |
| "gain yellow" | Free Yellow Pua |
| "use any card from the market" | Borrow market card |
| "another islander" | +2 influence if paired |
| "purchase this card" | Self-topdecks on purchase |
| "played with a surf" | +2 influence if Surf in play |
| "top card of your discard pile to your hand" | Retrieve from discard |
| "both of you may draw" | Mutual draw |
| "both of you may gain the same" | Mutual Pua gain |
| "gain any flower" | Free Flower from market |

If you use a different parsing approach, double-check that all 18 are classified correctly. A misclassified Islander (e.g., treating "gain Red Pua" as a generic no-op) will skew the economy data.

---

## 11. Offering Bonus Scoring Happens at Game End, Not on Completion

When a player completes an Offering, they take a VP token immediately. But the Offering's bonus (e.g., "1 VP per Wildlife card you own") is calculated **during final scoring**, not at the moment of completion. This matters because the player will likely acquire more cards between completing the Offering and the game ending.

A common simulator bug is to calculate the bonus at completion time and lock it in. This undervalues engine-building Offerings and overvalues rush strategies.

---

## 12. Card Identity — Use Instance Identity, Not Name Equality

Each physical card is a unique object, even if two cards share the same name (e.g., two copies of "Dolphin"). Use instance identity (`is` / object ID), not name-based equality, when tracking which card is where. If you use name equality, operations like "remove this specific Dolphin from the discard pile" will ambiguously match any Dolphin.

This is especially important for Lava Flow cards. After the Second Lava escalation, each player has two Lava Flows in their deck. They're functionally identical but need to be tracked as separate objects.

---

## 13. Draw Pile Exhaustion and Reshuffle Timing

When a player needs to draw but their draw pile is empty, they shuffle their discard pile into a new draw pile and continue drawing. This can happen multiple times in a single turn (e.g., Outrigger draws 3 cards, emptying the draw pile after 1, triggering a reshuffle for the remaining 2).

Handle this **per card drawn**, not per draw effect. The draw loop should be:

```
for each card to draw:
    if draw pile empty:
        if discard pile empty: stop (can't draw more)
        shuffle discard into draw pile
    draw one card
```

If you reshuffle once at the start of a draw-3 effect, you might miss the case where the reshuffle itself doesn't provide enough cards (very small deck late in game).

---

## 14. Seeded Randomness — Use One RNG Instance

All random decisions (deck shuffles, Pua price assignment, Offering selection, market deck order) must flow through a single seeded RNG instance. If any call uses the global `random` module instead of your seeded instance, reproducibility breaks silently — you won't get errors, just non-reproducible results.

The most common leaks: shuffling a deck without passing the RNG, using `random.choice()` instead of `rng.choice()`, or creating a new `random.Random()` in a helper function that forgets to use the game's seed.

---

## 15. Our Simulation Results — Reference Benchmarks

If your simulator is working correctly, these numbers should be in the right ballpark for 3-player expert-level play (500 games):

| Metric | Our result |
|---|---|
| Avg game length | ~37 turns (~12.5 rounds) |
| End by Offerings / lava | ~98% / ~2% |
| P0 / P1 / P2 win rates | ~43% / 32% / 25% |
| Avg total score | ~30 VP |
| Avg influence per turn | ~6.7 |
| Most purchased card | Islander (~6.5/game) |
| 3-Pua Offering completions/game | 1.7–2.4 |
| 4-Pua Offering completions/game | 0.7–0.9 |
| Avg lava final position | ~8 |

If your numbers are wildly different — especially if games are much shorter/longer, lava advances are much higher/lower, or scores are dramatically off — check the Pua price shift logic, the Lava Flow resolution order, and the market slide direction first. Those are the three most likely sources of divergence.
