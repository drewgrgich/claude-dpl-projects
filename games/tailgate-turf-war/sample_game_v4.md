# Zone Control v0.1 — Narrated Game

**Seed:** 17 · **Players:** 3 · **Rounds:** 3 · **VP/Zone:** 5

> *Four zones. Three rounds. Forty-eight cards. Every deployment is a blind bet.*

---
## Setup

Four zone cards are laid out:  Red ·  Yellow ·  Green ·  Blue.

Each player is dealt **12 cards** for the entire game.

**Player 0** — *Balanced* (a well-rounded strategist)
> Hand (12):  M, 1, 6, 9 ·  1, 2, 3 ·  2, 4, 6, 7, 8

**Player 1** — *Aggressive* (a high-volume player who floods every zone)
> Hand (12):  3, 4 ·  M ·  4, 5, 6 ·  M, 1, D(5), 9 · ⚡ 🛡️Shield, 💣Bomb

**Player 2** — *Sniper* (a precision player hunting mascot combos)
> Hand (12):  5, 7 ·  5, 9 ·  2, D(5), 7, 8, 9 ·  3, 5 · ⚡ 💰Bounty

---
## Card Passing

Each player selects **2** cards to pass to the player on their left.

- **P0** passes to P1: Yellow 1, Red 1
- **P1** passes to P2: Blue 1, Red 3
- **P2** passes to P0: Dud (Green, plays as 5), Green 2

**After passing:**

- P0:  M, 6, 9 ·  2, 3 ·  2, D(5) ·  2, 4, 6, 7, 8
- P1:  1, 4 ·  M, 1 ·  4, 5, 6 ·  M, D(5), 9 · ⚡ 🛡️Shield, 💣Bomb
- P2:  3, 5, 7 ·  5, 9 ·  7, 8, 9 ·  1, 3, 5 · ⚡ 💰Bounty

---
## Round 1

**Condition Card: No Matching Colors** (card_restriction)
> *Each card you play must be a different color.*

### Deploy

*All players simultaneously place cards face-down on their boards.*

**P0** (balanced) — plays 4 cards to 3 zones:
  -  Red: Red Mascot, Red 9
  -  Green: Dud (Green, plays as 5)
  -  Blue: Blue 8
  - *8 cards held back*

**P1** (aggressive) — plays 4 cards to 1 zone:
  -  Blue: Blue Mascot, Blue 9, 🛡️Shield (Red), 💣Bomb (Yellow)
  - *8 cards held back*

**P2** (sniper) — plays 3 cards to 3 zones:
  -  Yellow: Yellow 9
  -  Green: Green 9
  -  Blue: 💰Bounty (Blue)
  - *9 cards held back*

### Reveal

| Zone | Player | Cards |
|------|--------|-------|
|  Red | P0 | Red Mascot, Red 9 |
|  Yellow | P2 | Yellow 9 |
|  Green | P0 | Dud (Green, plays as 5) |
|  Green | P2 | Green 9 |
|  Blue | P0 | Blue 8 |
|  Blue | P1 | Blue Mascot, Blue 9, 🛡️Shield (Red), 💣Bomb (Yellow) |
|  Blue | P2 | 💰Bounty (Blue) |

### Action Resolution

*Actions resolve in fixed order: Shield → Bomb → Swap → Bounty*

- 🛡️ BLUE: P1 Shield active
- 💣 BLUE: P1 Bomb destroys BLU-8 (P0)
- 💰 BLUE: P2 Bounty active

### Strength & Scoring

** Red Zone:**

- P0: 9×2=18 (Mascot doubles Red 9) +3 (Home Field — Red 9) = **21**
- **P0 wins uncontested → +5 VP**

** Yellow Zone:**

- P2: 9 (Yellow 9) +3 (Home Field — Yellow 9) = **12**
- **P2 wins uncontested → +5 VP**

** Green Zone:**

- P0: 5 (Dud (Green, plays as 5)) +3 (Home Field — Dud (Green, plays as 5)) = **8**
- P2: 9 (Green 9) +3 (Home Field — Green 9) = **12**
- **P2 wins** (12 vs P0=8) → **+5 VP**

** Blue Zone:**

- P1: 9×2=18 (Mascot doubles Blue 9) +3 (Home Field — Blue 9) = **21**
- P2: 0 (only action cards — no rank)
- **P1 wins** (21 vs P2=0) → **+5 VP**
  - 💰 P2 Bounty bust — 0 VP

#### Scoreboard

| Player | Style | VP | Cards Left |
|--------|-------|----|------------|
| P0 | balanced | **5** | 8 |
| P1 | aggressive | **5** | 8 |
| P2 | sniper | **10** | 9 |

---
## Round 2

**Condition Card: Double Stakes** (scoring)
> *Each zone is worth double VP this round.*

### Deploy

*All players simultaneously place cards face-down on their boards.*

**P0** (balanced) — plays 4 cards to 4 zones:
  -  Red: Red 6
  -  Yellow: Yellow 3
  -  Green: Green 2
  -  Blue: Blue 7
  - *4 cards held back*

**P1** (aggressive) — plays 4 cards to 3 zones:
  -  Red: Red 4
  -  Green: Yellow Mascot, Green 6
  -  Blue: Dud (Blue, plays as 5)
  - *4 cards held back*

**P2** (sniper) — plays 4 cards to 4 zones:
  -  Red: Red 7
  -  Yellow: Yellow 5
  -  Green: Green 8
  -  Blue: Blue 5
  - *5 cards held back*

### Reveal

| Zone | Player | Cards |
|------|--------|-------|
|  Red | P0 | Red 6 |
|  Red | P1 | Red 4 |
|  Red | P2 | Red 7 |
|  Yellow | P0 | Yellow 3 |
|  Yellow | P2 | Yellow 5 |
|  Green | P0 | Green 2 |
|  Green | P1 | Yellow Mascot, Green 6 |
|  Green | P2 | Green 8 |
|  Blue | P0 | Blue 7 |
|  Blue | P1 | Dud (Blue, plays as 5) |
|  Blue | P2 | Blue 5 |

### Strength & Scoring

*Double Stakes! Each zone worth **10 VP** this round.*

** Red Zone:**

- P0: 6 (Red 6) +3 (Home Field — Red 6) = **9**
- P1: 4 (Red 4) +3 (Home Field — Red 4) = **7**
- P2: 7 (Red 7) +3 (Home Field — Red 7) = **10**
- **P2 wins** (10 vs P0=9, P1=7) → **+10 VP**

** Yellow Zone:**

- P0: 3 (Yellow 3) +3 (Home Field — Yellow 3) = **6**
- P2: 5 (Yellow 5) +3 (Home Field — Yellow 5) = **8**
- **P2 wins** (8 vs P0=6) → **+10 VP**

** Green Zone:**

- P0: 2 (Green 2) +3 (Home Field — Green 2) = **5**
- P1: 6×2=12 (Mascot doubles Green 6) +3 (Home Field — Green 6) = **15**
- P2: 8 (Green 8) +3 (Home Field — Green 8) = **11**
- **P1 wins** (15 vs P0=5, P2=11) → **+10 VP**

** Blue Zone:**

- P0: 7 (Blue 7) +3 (Home Field — Blue 7) = **10**
- P1: 5 (Dud (Blue, plays as 5)) +3 (Home Field — Dud (Blue, plays as 5)) = **8**
- P2: 5 (Blue 5) +3 (Home Field — Blue 5) = **8**
- **P0 wins** (10 vs P1=8, P2=8) → **+10 VP**

#### Scoreboard

| Player | Style | VP | Cards Left |
|--------|-------|----|------------|
| P0 | balanced | **15** | 4 |
| P1 | aggressive | **15** | 4 |
| P2 | sniper | **30** | 5 |

---
## Round 3

**Condition Card: Fortify** (scoring)
> *3+ cards at a zone gives +2 bonus VP.*

### Deploy

*All players simultaneously place cards face-down on their boards.*

**P0** (balanced) — plays 4 cards to 2 zones:
  -  Yellow: Yellow 2
  -  Blue: Blue 6, Blue 4, Blue 2
  - *0 cards held back*

**P1** (aggressive) — plays 4 cards to 4 zones:
  -  Red: Green 4
  -  Yellow: Yellow 1
  -  Green: Green 5
  -  Blue: Red 1
  - *0 cards held back*

**P2** (sniper) — plays 5 cards to 3 zones:
  -  Red: Red 5, Red 3
  -  Green: Green 7
  -  Blue: Blue 3, Blue 1
  - *0 cards held back*

### Reveal

| Zone | Player | Cards |
|------|--------|-------|
|  Red | P1 | Green 4 |
|  Red | P2 | Red 5, Red 3 |
|  Yellow | P0 | Yellow 2 |
|  Yellow | P1 | Yellow 1 |
|  Green | P1 | Green 5 |
|  Green | P2 | Green 7 |
|  Blue | P0 | Blue 6, Blue 4, Blue 2 |
|  Blue | P1 | Red 1 |
|  Blue | P2 | Blue 3, Blue 1 |

### Strength & Scoring

** Red Zone:**

- P1: 4 (Green 4) = **4**
- P2: 5 (Red 5) +2 (1 extra × 2) +3 (Home Field — Red 5) = **10**
- **P2 wins** (10 vs P1=4) → **+5 VP**

** Yellow Zone:**

- P0: 2 (Yellow 2) +3 (Home Field — Yellow 2) = **5**
- P1: 1 (Yellow 1) +3 (Home Field — Yellow 1) = **4**
- **P0 wins** (5 vs P1=4) → **+5 VP**

** Green Zone:**

- P1: 5 (Green 5) +3 (Home Field — Green 5) = **8**
- P2: 7 (Green 7) +3 (Home Field — Green 7) = **10**
- **P2 wins** (10 vs P1=8) → **+5 VP**

** Blue Zone:**

- P0: 6 (Blue 6) +4 (2 extra × 2) +3 (Home Field — Blue 6) = **13**
- P1: 1 (Red 1) = **1**
- P2: 3 (Blue 3) +2 (1 extra × 2) +3 (Home Field — Blue 3) = **8**
- **P0 wins** (13 vs P1=1, P2=8) → **+5 VP**

*Fortify: +2 bonus VP for 3+ cards at a zone.*

#### Scoreboard

| Player | Style | VP | Cards Left |
|--------|-------|----|------------|
| P0 | balanced | **27** | 0 |
| P1 | aggressive | **15** | 0 |
| P2 | sniper | **40** | 0 |

---
## Final Results

| Player | Style | Final VP | Zones Won | Cards Played |
|--------|-------|----------|-----------|--------------|
| P0 | balanced | **27** | 4 | 12 |
| P1 | aggressive | **15** | 2 | 12 |
| P2 🏆 | sniper | **40** | 6 | 12 |

> **Player 2 (sniper) wins by 13 VP!**
>
> *Surgical precision — the Mascot combo is a thing of beauty.*

---
### Game Statistics

- Home Field triggers: 23
- Mascot combos: 3
- Bomb kills: 1
- Shield saves: 0
- Swap uses: 0
- Bounty wins: 0, fails: 1
- Dud plays: 2
- Conditions: No Matching Colors, Double Stakes, Fortify

---
*Generated by the v0.1 simulation engine.*