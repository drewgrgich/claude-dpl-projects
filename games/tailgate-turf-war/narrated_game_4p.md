# Zone Control v0.1 — Narrated Game

**Seed:** 77 · **Players:** 4 · **Rounds:** 4 · **VP/Zone:** 5

> *Four zones. 4 rounds. 56 cards. Every deployment is a blind bet.*

---
## Setup

Four zone cards are laid out:  Red ·  Yellow ·  Green ·  Blue.

Each player is dealt **12 cards** for the entire game.

**Player 0** — *Sniper* (a precision player hunting mascot combos)
> Hand (12):  3, 5, D(5) ·  9, 10 ·  0, 0, 7, 10 ·  M, 1 · ⚡ 💰Bounty

**Player 1** — *Aggressive* (a high-volume player who floods every zone)
> Hand (12):  7 ·  M, 0, 5, D(5), 9 ·  9 ·  0, 1, 7, 9 · ⚡ 💣Bomb

**Player 2** — *Hoarder* (a patient operator saving for later rounds)
> Hand (12):  M, 1, 1, 9, 10 ·  10 ·  5, D(5), 10 ·  0, 5, 9

**Player 3** — *Spread* (a zone-coverage maximizer)
> Hand (12):  0, 0, 10 ·  1 ·  M, 1, 1, 3, 9 ·  3, D(5) · ⚡ 🔄Swap

---
## Card Passing

Each player selects **2** cards to pass to the player on their left.

- **P0** passes to P1: Blue 1, Green 0
- **P1** passes to P2: Blue 0, Yellow 0
- **P2** passes to P3: Blue 0, Red 1
- **P3** passes to P0: Yellow 1, Red 0

**After passing:**

- P0:  0, 3, 5, D(5) ·  1, 9, 10 ·  0, 7, 10 ·  M · ⚡ 💰Bounty
- P1:  7 ·  M, 5, D(5), 9 ·  0, 9 ·  1, 1, 7, 9 · ⚡ 💣Bomb
- P2:  M, 1, 9, 10 ·  0, 10 ·  5, D(5), 10 ·  0, 5, 9
- P3:  0, 1, 10 ·  M, 1, 1, 3, 9 ·  0, 3, D(5) · ⚡ 🔄Swap

---
## Round 1

**Condition Card: Light Touch** (card_restriction)
> *max_cards_4*

### Deploy

*All players simultaneously place cards face-down on their boards.*

**P0** (sniper) — plays 3 cards to 1 zone:
  -  Yellow: Blue Mascot, Yellow 10, 💰Bounty (Blue)
  - *9 cards held back*

**P1** (aggressive) — plays 3 cards to 1 zone:
  -  Green: Yellow Mascot, Green 9, 💣Bomb (Yellow)
  - *9 cards held back*

**P2** (hoarder) — plays 2 cards to 1 zone:
  -  Green: Red Mascot, Green 10
  - *10 cards held back*

**P3** (spread) — plays 3 cards to 1 zone:
  -  Red: Green Mascot, Red 10, 🔄Swap (Green)
  - *9 cards held back*

### Reveal

| Zone | Player | Cards |
|------|--------|-------|
|  Red | P3 | Green Mascot, Red 10, 🔄Swap (Green) |
|  Yellow | P0 | Blue Mascot, Yellow 10, 💰Bounty (Blue) |
|  Green | P1 | Yellow Mascot, Green 9, 💣Bomb (Yellow) |
|  Green | P2 | Red Mascot, Green 10 |
|  Blue | — | *empty* |

### Action Resolution

*Actions resolve in fixed order: Shield → Bomb → Swap → Bounty*

- 🔄 RED: P3 Swap — no beneficial swap
- 💰 YELLOW: P0 Bounty active
- 💣 GREEN: P1 Bomb destroys GRE-10 (P2)

### Strength & Scoring

** Red Zone:**

- P3: 10×2=20 (Mascot doubles Red 10) +3 (Home Field — Red 10) = **23**
- **P3 wins uncontested → +5 VP**

** Yellow Zone:**

- P0: 10×2=20 (Mascot doubles Yellow 10) +3 (Home Field — Yellow 10) = **23**
- 💰 **P0 wins with Bounty! Double VP → +10 VP**

** Green Zone:**

- P1: 9×2=18 (Mascot doubles Green 9) +3 (Home Field — Green 9) = **21**
- P2: 0 (Mascot alone — no rank to double)
- **P1 wins** (21 vs P2=0) → **+5 VP**

** Blue** — Empty. 5 VP unclaimed.

#### Scoreboard

| Player | Style | VP | Cards Left |
|--------|-------|----|------------|
| P0 | sniper | **10** | 9 |
| P1 | aggressive | **5** | 9 |
| P2 | hoarder | **0** | 10 |
| P3 | spread | **5** | 9 |

---
## Round 2

**Condition Card: Double Stakes** (scoring)
> *Each zone is worth double VP this round.*

### Deploy

*All players simultaneously place cards face-down on their boards.*

**P0** (sniper) — plays 3 cards to 3 zones:
  -  Red: Red 5
  -  Yellow: Yellow 9
  -  Green: Green 10
  - *6 cards held back*

**P1** (aggressive) — plays 3 cards to 3 zones:
  -  Red: Red 7
  -  Yellow: Yellow 9
  -  Blue: Blue 9
  - *6 cards held back*

**P2** (hoarder) — plays 3 cards to 3 zones:
  -  Red: Red 10
  -  Yellow: Yellow 10
  -  Blue: Blue 9
  - *7 cards held back*

**P3** (spread) — plays 3 cards to 3 zones:
  -  Red: Red 1
  -  Green: Green 9
  -  Blue: Dud (Blue, plays as 5)
  - *6 cards held back*

### Reveal

| Zone | Player | Cards |
|------|--------|-------|
|  Red | P0 | Red 5 |
|  Red | P1 | Red 7 |
|  Red | P2 | Red 10 |
|  Red | P3 | Red 1 |
|  Yellow | P0 | Yellow 9 |
|  Yellow | P1 | Yellow 9 |
|  Yellow | P2 | Yellow 10 |
|  Green | P0 | Green 10 |
|  Green | P3 | Green 9 |
|  Blue | P1 | Blue 9 |
|  Blue | P2 | Blue 9 |
|  Blue | P3 | Dud (Blue, plays as 5) |

### Strength & Scoring

*Double Stakes! Each zone worth **10 VP** this round.*

** Red Zone:**

- P0: 5 (Red 5) +3 (Home Field — Red 5) = **8**
- P1: 7 (Red 7) +3 (Home Field — Red 7) = **10**
- P2: 10 (Red 10) +3 (Home Field — Red 10) = **13**
- P3: 1 (Red 1) +3 (Home Field — Red 1) = **4**
- **P2 wins** (13 vs P0=8, P1=10, P3=4) → **+10 VP**

** Yellow Zone:**

- P0: 9 (Yellow 9) +3 (Home Field — Yellow 9) = **12**
- P1: 9 (Yellow 9) +3 (Home Field — Yellow 9) = **12**
- P2: 10 (Yellow 10) +3 (Home Field — Yellow 10) = **13**
- **P2 wins** (13 vs P0=12, P1=12) → **+10 VP**

** Green Zone:**

- P0: 10 (Green 10) +3 (Home Field — Green 10) = **13**
- P3: 9 (Green 9) +3 (Home Field — Green 9) = **12**
- **P0 wins** (13 vs P3=12) → **+10 VP**

** Blue Zone:**

- P1: 9 (Blue 9) +3 (Home Field — Blue 9) = **12**
- P2: 9 (Blue 9) +3 (Home Field — Blue 9) = **12**
- P3: 5 (Dud (Blue, plays as 5)) +3 (Home Field — Dud (Blue, plays as 5)) = **8**
- **Tie: P1 & P2** (both 12) → **+5 VP each**

#### Scoreboard

| Player | Style | VP | Cards Left |
|--------|-------|----|------------|
| P0 | sniper | **20** | 6 |
| P1 | aggressive | **10** | 6 |
| P2 | hoarder | **25** | 7 |
| P3 | spread | **5** | 6 |

---
## Round 3

**Condition Card: Lone Wolf** (scoring)
> *Uncontested zones give +3 bonus VP.*

### Deploy

*All players simultaneously place cards face-down on their boards.*

**P0** (sniper) — plays 3 cards to 2 zones:
  -  Red: Dud (Red, plays as 5), Red 3
  -  Green: Green 7
  - *3 cards held back*

**P1** (aggressive) — plays 3 cards to 3 zones:
  -  Red: Dud (Yellow, plays as 5)
  -  Yellow: Yellow 5
  -  Blue: Blue 7
  - *3 cards held back*

**P2** (hoarder) — plays 3 cards to 3 zones:
  -  Red: Red 9
  -  Green: Green 5
  -  Blue: Blue 5
  - *4 cards held back*

**P3** (spread) — plays 3 cards to 3 zones:
  -  Red: Red 0
  -  Green: Green 3
  -  Blue: Blue 3
  - *3 cards held back*

### Reveal

| Zone | Player | Cards |
|------|--------|-------|
|  Red | P0 | Dud (Red, plays as 5), Red 3 |
|  Red | P1 | Dud (Yellow, plays as 5) |
|  Red | P2 | Red 9 |
|  Red | P3 | Red 0 |
|  Yellow | P1 | Yellow 5 |
|  Green | P0 | Green 7 |
|  Green | P2 | Green 5 |
|  Green | P3 | Green 3 |
|  Blue | P1 | Blue 7 |
|  Blue | P2 | Blue 5 |
|  Blue | P3 | Blue 3 |

### Strength & Scoring

** Red Zone:**

- P0: 5 (Dud (Red, plays as 5)) +2 (1 extra × 2) +3 (Home Field — Dud (Red, plays as 5)) = **10**
- P1: 5 (Dud (Yellow, plays as 5)) = **5**
- P2: 9 (Red 9) +3 (Home Field — Red 9) = **12**
- P3: 0 (Red 0) +3 (Home Field — Red 0) = **3**
- **P2 wins** (12 vs P0=10, P1=5, P3=3) → **+5 VP**

** Yellow Zone:**

- P1: 5 (Yellow 5) +3 (Home Field — Yellow 5) = **8**
- **P1 wins uncontested → +5 VP**

** Green Zone:**

- P0: 7 (Green 7) +3 (Home Field — Green 7) = **10**
- P2: 5 (Green 5) +3 (Home Field — Green 5) = **8**
- P3: 3 (Green 3) +3 (Home Field — Green 3) = **6**
- **P0 wins** (10 vs P2=8, P3=6) → **+5 VP**

** Blue Zone:**

- P1: 7 (Blue 7) +3 (Home Field — Blue 7) = **10**
- P2: 5 (Blue 5) +3 (Home Field — Blue 5) = **8**
- P3: 3 (Blue 3) +3 (Home Field — Blue 3) = **6**
- **P1 wins** (10 vs P2=8, P3=6) → **+5 VP**

*Lone Wolf: +3 bonus VP for uncontested zones.*

#### Scoreboard

| Player | Style | VP | Cards Left |
|--------|-------|----|------------|
| P0 | sniper | **25** | 3 |
| P1 | aggressive | **23** | 3 |
| P2 | hoarder | **30** | 4 |
| P3 | spread | **5** | 3 |

---
## Round 4

**Condition Card: Efficiency** (scoring)
> *Ties broken by fewest cards.*

### Deploy

*All players simultaneously place cards face-down on their boards.*

**P0** (sniper) — plays 3 cards to 3 zones:
  -  Red: Red 0
  -  Yellow: Yellow 1
  -  Green: Green 0
  - *0 cards held back*

**P1** (aggressive) — plays 2 cards to 2 zones:
  -  Green: Green 0
  -  Blue: Blue 1
  - *1 cards held back*

**P2** (hoarder) — plays 4 cards to 4 zones:
  -  Red: Red 1
  -  Yellow: Yellow 0
  -  Green: Dud (Green, plays as 5)
  -  Blue: Blue 0
  - *0 cards held back*

**P3** (spread) — plays 2 cards to 2 zones:
  -  Green: Green 1
  -  Blue: Blue 0
  - *1 cards held back*

### Reveal

| Zone | Player | Cards |
|------|--------|-------|
|  Red | P0 | Red 0 |
|  Red | P2 | Red 1 |
|  Yellow | P0 | Yellow 1 |
|  Yellow | P2 | Yellow 0 |
|  Green | P0 | Green 0 |
|  Green | P1 | Green 0 |
|  Green | P2 | Dud (Green, plays as 5) |
|  Green | P3 | Green 1 |
|  Blue | P1 | Blue 1 |
|  Blue | P2 | Blue 0 |
|  Blue | P3 | Blue 0 |

### Strength & Scoring

** Red Zone:**

- P0: 0 (Red 0) +3 (Home Field — Red 0) = **3**
- P2: 1 (Red 1) +3 (Home Field — Red 1) = **4**
- **P2 wins** (4 vs P0=3) → **+5 VP**

** Yellow Zone:**

- P0: 1 (Yellow 1) +3 (Home Field — Yellow 1) = **4**
- P2: 0 (Yellow 0) +3 (Home Field — Yellow 0) = **3**
- **P0 wins** (4 vs P2=3) → **+5 VP**

** Green Zone:**

- P0: 0 (Green 0) +3 (Home Field — Green 0) = **3**
- P1: 0 (Green 0) +3 (Home Field — Green 0) = **3**
- P2: 5 (Dud (Green, plays as 5)) +3 (Home Field — Dud (Green, plays as 5)) = **8**
- P3: 1 (Green 1) +3 (Home Field — Green 1) = **4**
- **P2 wins** (8 vs P0=3, P1=3, P3=4) → **+5 VP**

** Blue Zone:**

- P1: 1 (Blue 1) +3 (Home Field — Blue 1) = **4**
- P2: 0 (Blue 0) +3 (Home Field — Blue 0) = **3**
- P3: 0 (Blue 0) +3 (Home Field — Blue 0) = **3**
- **P1 wins** (4 vs P2=3, P3=3) → **+5 VP**

#### Scoreboard

| Player | Style | VP | Cards Left |
|--------|-------|----|------------|
| P0 | sniper | **30** | 0 |
| P1 | aggressive | **28** | 1 |
| P2 | hoarder | **40** | 0 |
| P3 | spread | **5** | 1 |

---
## Final Results

| Player | Style | Final VP | Zones Won | Cards Played |
|--------|-------|----------|-----------|--------------|
| P0 | sniper | **30** | 4 | 12 |
| P1 | aggressive | **28** | 5 | 11 |
| P2 🏆 | hoarder | **40** | 6 | 12 |
| P3 | spread | **5** | 1 | 11 |

> **Player 2 (hoarder) wins by 10 VP!**
>
> *Patience rewarded. Saving cards for the right moment paid off.*

---
### Game Statistics

- Home Field triggers: 36
- Mascot combos: 3
- Bomb kills: 1
- Shield saves: 0
- Swap uses: 0
- Bounty wins: 1, fails: 0
- Dud plays: 4
- Conditions: Light Touch, Double Stakes, Lone Wolf, Efficiency

---
*Generated by the v0.1 simulation engine.*