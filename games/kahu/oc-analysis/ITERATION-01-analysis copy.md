# Kahu Balance Analysis — Iteration 01

## Phase 1: Designer Corps Analysis

### Morgan (A) — Mathematical/Balance Analysis

**Finding 1: Lava is practically inert in 2-player games**
- With 1 Lava Flow card per player cycling through a 10-card deck, probability of drawing it on any given turn is ~12.5%
- Expected lava advancement: ~1 space per 8 turns
- With lava starting at space 16, eruption expected at ~128 turns (way beyond reasonable game length)
- **Result**: Lava track never ends games in 2-player. The main escalation (space 15: second Lava Flow) barely matters.
- The second Lava Flow at space 15 should double lava pressure, but space 15 is reached after ~120 turns — too late.

**Finding 2: Rush strategy dominates wildly**
- Simulation shows rush vs balanced = 95.2% win rate, rush vs engine = 100%
- The VP race is the ONLY viable path to victory since lava never ends the game
- Players who rush Offerings (aggressive Pua buying + offering completion) completely shut out engine builders
- Engine builders invest in cards but can't complete Offerings fast enough to compete

**Finding 3: Pua economy is dangerously tight**
- Each player starts with exactly 3 colored Pua icons (R, B, Y) and 1 Wild
- To buy 1 Pua of a color, you need a matching icon in your play area
- To complete RRBY (cheapest Offering), you need 2R+1B+1Y = 4 Pua
- Even with 8 influence on Turn 1 (6 basic + Hula), after buying 3 Pua (3+4+5 = 12), you can't afford all 4 Pua for RRBY
- This means Offerings can't be completed on Turn 1, which is probably intentional — but the margin is very thin

**Finding 4: Surf cards are a trap**
- Surf costs 2, gives 2 influence. Net gain = 0.
- Surfboard (4 cost) needs Surf to be worth playing (5 vs 4 cost). Net gain = 1.
- Only 10 Surf cards exist total. Any strategy relying on Surf is non-viable.
- The Surf market is effectively a "dump 2 influence for nothing" in most cases.

---

### Jordan (B) — Player Experience Analysis

**Finding 1: Game length is unpredictable and often too long**
- With 2 players, games run 47-60 turns on average (well beyond the 30-45 minute target)
- Players can't tell when the game will end — neither lava nor VP condition provides clear signals
- The game feels like it's "running away" without player agency

**Finding 2: Pua icon requirement creates frustrating dead states**
- If you play a card with a Blue icon, you MUST use that icon to buy Pua (or lose it)
- But icons cycle slowly — you might have a Blue icon but no Blue Pua affordable, and the icon just expires at cleanup
- Players can find themselves "locked out" of buying Pua despite having cards with icons because the math doesn't work out

**Finding 3: The Offering bonus system is opaque**
- "1 VP per card type you own" is unclear until end game — players can't easily track
- The "cards removed from game" bonus is especially confusing — how do cards get removed?
- These feel like they belong in a more advanced game; they're too complex for a deck-builder's first play

**Finding 4: Tiki use feels bad**
- When you have a Tiki and draw Lava Flow, the Tiki is MANDATORY — no choice
- Players can't "save" a Tiki for a more dangerous moment
- After Tiki Lockout (space 12), Tikis become unclaimable, but any existing Tikis remain — creates confusing state

**Finding 5: Second Lava card at space 15 arrives too late to matter**
- By space 15, the game is often already decided through Offerings
- The "escalation" fires but has no meaningful impact on most game outcomes

---

### Casey (C) — Explanation/Marketing Analysis

**Finding 1: "Build your deck" + "Pua market" is two games stapled together**
- Deck-builders (Dominion) and commodity markets (Puerto Rico) are both complex systems
- Kahu combines them, doubling the cognitive load: not just "what cards do I buy?" but also "which Pua color do I buy, and how will it affect prices?"
- The Pua market has real economic depth (price shifting, color dependencies) that conflicts with the casual image of a "tropical deck-builder"

**Finding 2: Lava Flow is a brilliant but confusing mechanic**
- The concept of a "danger card" that must be resolved each turn is compelling
- BUT: the rules exceptions (Pineapple, Outrigger, Chicken can dodge it) create a complex web
- A new player asks: "Why CAN'T I discard Lava Flow like other cards?" — the answer is thematic but mechanically opaque

**Finding 3: The Tiki is marketed as a shield but feels like a resource sink**
- "Protect yourself with sacred Tikis!" sounds compelling
- But Tikis cost 1R+1B+1Y Pua (expensive!) and only block ONE lava trigger
- The cost-benefit is hard to evaluate quickly

**Finding 4: Offering bonuses are "endgame scoring tricks" that feel disconnected from play**
- "1 VP per card type in your deck" — players can't easily track this during play
- It encourages hoarding cards of each type rather than building a focused strategy
- Compare to Ticket to Ride: scoring is visible and trackable throughout

**Finding 5: The game needs a clear "elevator pitch" that it's currently missing**
- "Deck-builder + Pua market + lava track" = too many hooks
- The core identity is unclear: Is it a resource management game? A race game? A deck-builder?
- Risk: players bounce off before understanding the depth

---

## Phase 2: Simulation Results (v1.0, 2-player, 500 games each)

### Strategy Win Rates

| Matchup | P1 Win% | P2 Win% | Avg Turns | Lava Eruptions |
|---------|--------|---------|-----------|----------------|
| balanced vs balanced | 49.8% | 50.2% | 59.4 | 0 |
| rush vs rush | 46.6% | 53.4% | 47.4 | 0 |
| engine vs engine | 46.6% | 53.4% | 60.0 | 0 |
| rush vs balanced | **95.2%** | 4.8% | 52.8 | 0 |
| engine vs balanced | 6.6% | **93.4%** | 59.5 | 0 |
| rush vs engine | **100.0%** | 0.0% | 53.7 | 0 |

### Key Problems Identified

1. **Rush dominates**: 95-100% win rate vs other strategies. Engine is non-viable.
2. **Lava eruptions = 0**: The lava track is completely irrelevant in 2-player games.
3. **Games are too long**: 47-60 turns average, most exceed 50 turns.
4. **Engine strategy is broken**: 0% win rate vs rush. Engine builders can't finish Offerings before being outpaced.
5. **First-player advantage slightly elevated** in rush-heavy matchups (95%+ = ~52% raw FP advantage adjusted for strategy matchup).

---

## Phase 3: Proposed Fixes (for Iteration 02)

### Fix 1: Accelerate Lava Track
- **Problem**: Lava advances too slowly to create pressure
- **Fix**: Start lava tracker higher (24 for 4p, 22 for 3p, 18 for 2p) AND add a second Lava Flow card to EACH player's starting discard
- **Rationale**: More Lava Flow triggers = more lava pressure = lava becomes relevant

### Fix 2: Nerf Rush Strategy
- **Problem**: Rushing Offerings is overwhelmingly dominant
- **Fix**: Increase the Pua costs of the cheapest Offerings, OR add a "cool down" on completing Offerings (can't complete two Offerings in a row without a round in between)
- **Alternative**: Make Pua icons slightly more scarce in early game (start with 2 of each color token instead of cards with icons)

### Fix 3: Buff Engine Strategy
- **Problem**: Engine builders can't complete Offerings fast enough
- **Fix**: Add 1-2 cards to starting deck that generate Pua icons or provide draw power to cycle faster
- **Alternative**: Reduce the cost of "economy" cards (Islander, Item) to make engine building faster

### Fix 4: Reduce Game Length
- **Problem**: Games exceed 50 turns
- **Fix**: The lava acceleration (Fix 1) should naturally shorten games by creating real pressure
- **Alternative**: Lower the turn cap and accept more lava eruptions as the ending condition

### Fix 5: Clarify Offering Bonuses
- **Problem**: Offering bonuses are too complex to track
- **Fix**: Simplify to 2-3 clear bonus types, remove "cards removed" and "card types" from base game

---

## Recommended Priority

1. **MUST FIX**: Lava acceleration (Fix 1) — lava is currently a dead mechanic
2. **SHOULD FIX**: Rush dominance (Fix 2) — threatens game diversity
3. **CONSIDER**: Engine buff (Fix 3) — only needed if Fix 2 doesn't balance enough
4. **NICE TO HAVE**: Simplify Offering bonuses (Fix 5) — improves new-player experience

**Proceed to Iteration 02**: Implement Fix 1 (lava acceleration) and Fix 2 (rush balancing).
