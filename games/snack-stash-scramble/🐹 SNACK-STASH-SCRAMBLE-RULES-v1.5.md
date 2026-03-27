# 🐹 SNACK STASH SCRAMBLE (v1.5 - Balance Patch)

### A High-Speed Action-Rummy Game for 2–4 Players

**System:** Hamsters & Monsters Core Deck (66 cards) | **Time:** 15–20 Min

### ARCHITECT'S NOTE: WHAT IS THIS GAME?

Welcome to the Cheek-Pouch Challenge. *Snack Stash Scramble* is a game of aggressive set collection. You are a hamster frantically hoarding treats before the feeder runs out.

Do not get attached to your hand. The deck moves fast, and if the whistle blows while you are holding a mouthful of giant snacks, you will choke on the penalty. **Stop optimizing. Start converting.**

### v1.5 CHANGELOG

Five targeted balance changes based on 18,500 simulated games (three rounds of testing):

1. **NEW — Desperate Sniffing (anti-stagnation rule).** Players who couldn't bank anything last turn draw 2 cards instead of 1. Stagnation rate dropped from 61% to 22% in 4P testing.
2. **REPLACED — Stale Snack Rule → Pantry Restock.** The old Stale Snack Rule made the Litter Box a dead mechanic (~1 draw/game). Now, anyone can draw from the Litter Box, but the top card of the Feeder automatically flips to replace it. The game clock keeps ticking and the discard pile stays interesting (~12 draws/game at 4P).
3. **NEW — Late to the Pantry (seat balance).** Later seats start with more cards to offset first-mover advantage. Seat 4 win rate improved from 17.8% to 28% at 4P.
4. **REWORKED — Poisoned Peanut (Yellow power now bites).** In v1.4, placing a card on an opponent's set accidentally *helped* them (free points). Now, opponent-placed cards are turned sideways and **subtract** their face value at scoring. Yellow triggers nearly tripled (1.2 → 3.1/game), RED protection doubled (0.7 → 2.4/game), and the attack/defend tension gives both factions a real role.
5. All changes stress-tested across 28 configurations including Poisoned Peanut A/B tests at all player counts. Zero games stalled. No significant seat imbalance from poison exposure (P1 takes more poison but seat spread *narrowed* from 5.2% to 3.6%).

------

## ⚙️ BASE PRINCIPLES: THE DECK PHYSICS

The deck has 66 cards across 6 Factions (Colors). Each Faction has cards ranked **0 through 10**.

**THE WILD GAP:**

- **Ranks 0 and 10 are WILD.** They can substitute for any number or Faction to complete a set.
- **The Anchor Rule (Critical):** Wilds *do not* have an innate Faction. They are just blank snacks. If you want to use a Wild to trigger a Faction Power (see below), it **must be anchored** by a Natural Card (Ranks 1–9) of that Faction in the exact same set.

------

## 🏁 SETUP

1. **Shuffle** the 66-card deck.
2. **Deal starting hands by seat order (Late to the Pantry rule):**

| Players | Seat 1 | Seat 2 | Seat 3 | Seat 4 |
|:---:|:---:|:---:|:---:|:---:|
| 2 Players | 7 cards | 7 cards | — | — |
| 3 Players | 6 cards | 7 cards | 7 cards | — |
| 4 Players | 6 cards | 7 cards | 7 cards | 8 cards |

*The last hamster to the table was closest to the pantry and snagged an extra treat.*

3. Place the remaining deck in the center. This is **The Feeder**.
4. Flip the top card of The Feeder face-up next to it. This starts **The Litter Box** (Discard Pile).

------

## 🏃 HOW TO PLAY: THE TURN LOOP

On your turn, you must complete three steps in order:

### 1. DRAW (Restock)

Count your hand size to determine your draw action:

- **The Snack Floor:** If you begin your turn with **2 or fewer cards** in your hand, your cheeks are too empty! Instead of drawing 1 card, you must immediately draw exactly **3 cards** directly from The Feeder.
- **Standard Draw:** If you begin your turn with **3 or more cards**, take the top card of The Feeder (blind) OR the top card of The Litter Box (visible) and add it to your hand.
- **🔄 Pantry Restock:** Whenever you draw from the Litter Box, immediately flip the top card of The Feeder face-up onto the Litter Box to replace it. *(The pantry keeps cycling — you got your snack, but a new one falls off the shelf.)*
- **🐽 Desperate Sniffing:** If you **could not bank any set on your previous turn**, you sniff around harder — draw **2 cards** from The Feeder instead of 1. *(This replaces your Standard Draw. You may still choose the Litter Box instead of Desperate Sniffing if you prefer the visible card.)*

*Note: Desperate Sniffing does not stack with The Snack Floor. If your hand is at 2 or fewer, Snack Floor always takes priority.*

### 2. BANK & FIRE (The Action Phase)

*Optional.* You may play valid sets from your hand onto the table in front of you. This is your **Cheek Stash**. A valid set is either:

- **A Group:** 3 or more cards of the *same number* (e.g., three 4s).
- **A Run:** 3 or more cards of the *same Faction in numerical sequence* (e.g., Red 5, Red 6, Red 7).

**The Dopamine Trigger (Firing):** Whenever you bank a *new* set of 3+ cards, you don't just score points—you trigger a combo. You must point to **exactly one Natural Card (Ranks 1–9)** in that set and declare its Faction Power (see "The Distractions" below).

- *Note: You can also extend previously banked sets by adding cards to them later. Extending a set does NOT trigger a power.*

### 3. DISCARD (End Turn)

You must end your turn by placing one card from your hand face-up onto The Litter Box. (If you managed to play every single card in your hand and have zero left, your turn simply ends). Play passes clockwise.

------

## 💥 THE DISTRACTIONS (Faction Powers)

When you **Fire** a Faction by banking a new set, resolve its effect immediately:

- 🔴 **RED (Super-Dupes) — *"I'll Guard It!"*** Target one of your banked sets. Opponents cannot add cards to this set for the rest of the game. *(This permanently blocks opponents from slipping Poisoned Peanuts into your stash! Guard your best sets!)*
- 🟠 **ORANGE (Finders-Keepers) — *"Dibs!"*** Immediately draw the top card of the Litter Box into your hand. *(Efficiency. You dropped this, I'll take it.)*
- 🟡 **YELLOW (Tinkerers) — *"Look What I Did!"*** Instantly play a single valid card from your hand to extend ANY player's banked set on the table. **The Poisoned Peanut:** When you place a card on an *opponent's* set, turn it sideways (horizontal) to mark it as poisoned. At final scoring, **sideways cards subtract their face value** from the set owner's score instead of adding to it. *(Sneaking a rotten peanut into someone else's stash. The higher the card, the nastier the surprise!)*
- 🟢 **GREEN (Prognosticationers) — *"Just As Planned."*** Look at the top 3 cards of the Feeder. Put them back in any order. *(Checking the pantry for the good seeds.)*
- 🔵 **BLUE (Magicians) — *"Is This Your Card?"*** Take a random card from an opponent's hand. Give them one card of your choice from your hand in return. **(Empty Pockets Contingency: If all opponents have 0 cards in hand, just draw 1 card from The Feeder instead).**
- 🟣 **PURPLE (Time Travelers) — *"Nap Time."*** Take any 1 card from the Litter Box and slide it to the bottom of the Feeder. *(Extending the game clock. We haven't eaten that one yet!)*

------

## 🚨 THE HALFTIME SWEEP

When **The Feeder** empties for the *first time*, pause the game. Take the entire Litter Box (except the top card), shuffle it, and place it face-down to create a fresh Feeder. The game resumes immediately.

------

## 💥 ENDGAME: THE GREEDY CHEEKS CHECK

The game ends **instantly** the exact moment The Feeder empties for the *second time*. No one gets a final turn.

**🚨 THE MID-BITE WHISTLE (Choking Hazard):** If the Feeder empties for the second time while you are in the middle of drawing multiple cards for The Snack Floor, the game ends INSTANTLY the moment the last card is pulled. You do not get to finish your draw, you do not get to play any sets, and you are immediately scored with whatever is currently in your hand.

**SCORING:**

1. **Count Your Stash:** Add up the mathematical face value of every card you successfully banked on the table. (A banked 8 is worth 8 points. 1s are worth 1).
2. **The Poisoned Peanut Tax:** Any sideways (horizontal) cards in your banked sets were placed by opponents. **Subtract their face value from your score** instead of adding it. *(That "free" card they gave you? It was rotten.)*
3. **The Greedy Cheeks Penalty:** Reveal your hand. You tried to stuff too much in your cheeks and tipped over. **Subtract the face value of every card left in your hand from your score.**
4. **The Jawbreaker Hazard:** Rank 0 and Rank 10 cards are massive hazards. They are incredible wildcards for building sets, but if you get caught with a 0 or a 10 in your hand when the game ends, you choke. **Any Rank 0 or Rank 10 caught in your hand is worth -10 points.** **The player with the highest final score is the Champion of the Snacks.**
