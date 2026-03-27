# Zone Control v0.1 — Narrated Game

**Seed:** 204 · **Players:** 4 · **Rounds:** 4 · **VP/Zone:** 5

> *Four zones. 4 rounds. 56 cards. Every deployment is a blind bet.*

---
## Setup

Four zone cards are laid out:  Red ·  Yellow ·  Green ·  Blue.

Each player is dealt **12 cards** for the entire game.

**Player 0** — *Sniper* (a precision player hunting mascot combos)
> Hand (12):  M, 0, 1, 1, 9 ·  1, 10 ·  1, 3 ·  0, 10 · ⚡ 🔄Swap

**Player 1** — *Aggressive* (a high-volume player who floods every zone)
> Hand (12):  0 ·  1, 5, D(5), 10 ·  M, 10 ·  0, 1, D(5), 7, 10

**Player 2** — *Hoarder* (a patient operator saving for later rounds)
> Hand (12):  10 ·  0, 0, 3 ·  7, 9 ·  M, 3, 5, 9 · ⚡ 🛡️Shield, 💰Bounty

**Player 3** — *Spread* (a zone-coverage maximizer)
> Hand (12):  3, 7, 10 ·  7, 9 ·  0, 0, 5, D(5), 9 ·  1, 9

---
## Card Passing

Each player selects **2** cards to pass to the player on their left.

- **P0** passes to P1: Blue 0, Red 0
- **P1** passes to P2: Red 0, Blue 0
- **P2** passes to P3: Yellow 0, Yellow 0
- **P3** passes to P0: Green 0, Green 0

**After passing:**

- P0:  M, 1, 1, 9 ·  1, 10 ·  0, 0, 1, 3 ·  10 · ⚡ 🔄Swap
- P1:  0 ·  1, 5, D(5), 10 ·  M, 10 ·  0, 1, D(5), 7, 10
- P2:  0, 10 ·  3 ·  7, 9 ·  M, 0, 3, 5, 9 · ⚡ 🛡️Shield, 💰Bounty
- P3:  3, 7, 10 ·  0, 0, 7, 9 ·  5, D(5), 9 ·  1, 9

---
## Round 1

**Condition Card: Spread Out** (placement)
> *min_2_zones*

### Deploy

*All players simultaneously place cards face-down on their boards.*

**P0** (sniper) — plays 4 cards to 2 zones:
  -  Red: Blue 10
  -  Blue: Red Mascot, 🔄Swap (Green), Green 0
  - *8 cards held back*

**P1** (aggressive) — plays 3 cards to 2 zones:
  -  Green: Green Mascot, Green 10
  -  Blue: Blue 10
  - *9 cards held back*

**P2** (hoarder) — plays 3 cards to 2 zones:
  -  Red: Blue Mascot, Red 0
  -  Yellow: Red 10
  - *9 cards held back*

**P3** (spread) — plays 3 cards to 3 zones:
  -  Red: Red 10
  -  Yellow: Yellow 9
  -  Blue: Blue 9
  - *9 cards held back*

### Reveal

| Zone | Player | Cards |
|------|--------|-------|
|  Red | P0 | Blue 10 |
|  Red | P2 | Blue Mascot, Red 0 |
|  Red | P3 | Red 10 |
|  Yellow | P2 | Red 10 |
|  Yellow | P3 | Yellow 9 |
|  Green | P1 | Green Mascot, Green 10 |
|  Blue | P0 | Red Mascot, 🔄Swap (Green), Green 0 |
|  Blue | P1 | Blue 10 |
|  Blue | P3 | Blue 9 |

### Action Resolution

*Actions resolve in fixed order: Shield → Bomb → Swap → Bounty*

- 🔄 BLUE: P0 Swap — no beneficial swap

### Strength & Scoring

** Red Zone:**

- P0: 10 (Blue 10) = **10**
- P2: 0×2=0 (Mascot doubles Red 0) +3 (Home Field — Red 0) = **3**
- P3: 10 (Red 10) +3 (Home Field — Red 10) = **13**
- **P3 wins** (13 vs P0=10, P2=3) → **+5 VP**

** Yellow Zone:**

- P2: 10 (Red 10) = **10**
- P3: 9 (Yellow 9) +3 (Home Field — Yellow 9) = **12**
- **P3 wins** (12 vs P2=10) → **+5 VP**

** Green Zone:**

- P1: 10×2=20 (Mascot doubles Green 10) +3 (Home Field — Green 10) = **23**
- **P1 wins uncontested → +5 VP**

** Blue Zone:**

- P0: 0×2=0 (Mascot doubles Green 0) = **0**
- P1: 10 (Blue 10) +3 (Home Field — Blue 10) = **13**
- P3: 9 (Blue 9) +3 (Home Field — Blue 9) = **12**
- **P1 wins** (13 vs P0=0, P3=12) → **+5 VP**

#### Scoreboard

| Player | Style | VP | Cards Left |
|--------|-------|----|------------|
| P0 | sniper | **0** | 8 |
| P1 | aggressive | **10** | 9 |
| P2 | hoarder | **0** | 9 |
| P3 | spread | **10** | 9 |

---
## Round 2

**Condition Card: Rainbow** (card_restriction)
> *unique_colors_per_zone*

### Deploy

*All players simultaneously place cards face-down on their boards.*

**P0** (sniper) — plays 2 cards to 2 zones:
  -  Red: Red 9
  -  Yellow: Yellow 10
  - *6 cards held back*

**P1** (aggressive) — plays 3 cards to 3 zones:
  -  Red: Dud (Blue, plays as 5)
  -  Yellow: Yellow 10
  -  Blue: Blue 7
  - *6 cards held back*

**P2** (hoarder) — plays 2 cards to 2 zones:
  -  Green: Green 9
  -  Blue: Blue 9
  - *7 cards held back*

**P3** (spread) — plays 3 cards to 3 zones:
  -  Red: Red 7
  -  Yellow: Yellow 7
  -  Green: Green 9
  - *6 cards held back*

### Reveal

| Zone | Player | Cards |
|------|--------|-------|
|  Red | P0 | Red 9 |
|  Red | P1 | Dud (Blue, plays as 5) |
|  Red | P3 | Red 7 |
|  Yellow | P0 | Yellow 10 |
|  Yellow | P1 | Yellow 10 |
|  Yellow | P3 | Yellow 7 |
|  Green | P2 | Green 9 |
|  Green | P3 | Green 9 |
|  Blue | P1 | Blue 7 |
|  Blue | P2 | Blue 9 |

### Strength & Scoring

** Red Zone:**

- P0: 9 (Red 9) +3 (Home Field — Red 9) = **12**
- P1: 5 (Dud (Blue, plays as 5)) = **5**
- P3: 7 (Red 7) +3 (Home Field — Red 7) = **10**
- **P0 wins** (12 vs P1=5, P3=10) → **+5 VP**

** Yellow Zone:**

- P0: 10 (Yellow 10) +3 (Home Field — Yellow 10) = **13**
- P1: 10 (Yellow 10) +3 (Home Field — Yellow 10) = **13**
- P3: 7 (Yellow 7) +3 (Home Field — Yellow 7) = **10**
- **Tie: P0 & P1** (both 13) → **+3 VP each**

** Green Zone:**

- P2: 9 (Green 9) +3 (Home Field — Green 9) = **12**
- P3: 9 (Green 9) +3 (Home Field — Green 9) = **12**
- **Tie: P2 & P3** (both 12) → **+3 VP each**

** Blue Zone:**

- P1: 7 (Blue 7) +3 (Home Field — Blue 7) = **10**
- P2: 9 (Blue 9) +3 (Home Field — Blue 9) = **12**
- **P2 wins** (12 vs P1=10) → **+5 VP**

#### Scoreboard

| Player | Style | VP | Cards Left |
|--------|-------|----|------------|
| P0 | sniper | **8** | 6 |
| P1 | aggressive | **13** | 6 |
| P2 | hoarder | **8** | 7 |
| P3 | spread | **13** | 6 |

---
## Round 3

**Condition Card: Inversion** (scoring)
> *Lowest strength wins each zone!*

### Deploy

*All players simultaneously place cards face-down on their boards.*

**P0** (sniper) — plays 3 cards to 3 zones:
  -  Red: Red 1
  -  Yellow: Yellow 1
  -  Green: Green 3
  - *3 cards held back*

**P1** (aggressive) — plays 3 cards to 3 zones:
  -  Red: Dud (Yellow, plays as 5)
  -  Yellow: Yellow 5
  -  Blue: Blue 1
  - *3 cards held back*

**P2** (hoarder) — plays 3 cards to 1 zone:
  -  Green: Green 7, 💰Bounty (Blue), 🛡️Shield (Red)
  - *4 cards held back*

**P3** (spread) — plays 3 cards to 3 zones:
  -  Red: Red 3
  -  Yellow: Dud (Green, plays as 5)
  -  Green: Green 5
  - *3 cards held back*

### Reveal

| Zone | Player | Cards |
|------|--------|-------|
|  Red | P0 | Red 1 |
|  Red | P1 | Dud (Yellow, plays as 5) |
|  Red | P3 | Red 3 |
|  Yellow | P0 | Yellow 1 |
|  Yellow | P1 | Yellow 5 |
|  Yellow | P3 | Dud (Green, plays as 5) |
|  Green | P0 | Green 3 |
|  Green | P2 | Green 7, 💰Bounty (Blue), 🛡️Shield (Red) |
|  Green | P3 | Green 5 |
|  Blue | P1 | Blue 1 |

### Action Resolution

*Actions resolve in fixed order: Shield → Bomb → Swap → Bounty*

- 🛡️ GREEN: P2 Shield active
- 💰 GREEN: P2 Bounty active

### Strength & Scoring

*Inversion! **Lowest** strength wins each zone.*

** Red Zone:**

- P0: 1 (Red 1) +3 (Home Field — Red 1) = **4**
- P1: 5 (Dud (Yellow, plays as 5)) = **5**
- P3: 3 (Red 3) +3 (Home Field — Red 3) = **6**
- **P0 wins** (4 vs P1=5, P3=6) → **+5 VP**

** Yellow Zone:**

- P0: 1 (Yellow 1) +3 (Home Field — Yellow 1) = **4**
- P1: 5 (Yellow 5) +3 (Home Field — Yellow 5) = **8**
- P3: 5 (Dud (Green, plays as 5)) = **5**
- **P0 wins** (4 vs P1=8, P3=5) → **+5 VP**

** Green Zone:**

- P0: 3 (Green 3) +3 (Home Field — Green 3) = **6**
- P2: 7 (Green 7) +3 (Home Field — Green 7) = **10**
- P3: 5 (Green 5) +3 (Home Field — Green 5) = **8**
- **P0 wins** (6 vs P2=10, P3=8) → **+5 VP**
  - 💰 P2 Bounty bust — 0 VP

** Blue Zone:**

- P1: 1 (Blue 1) +3 (Home Field — Blue 1) = **4**
- **P1 wins uncontested → +5 VP**

#### Scoreboard

| Player | Style | VP | Cards Left |
|--------|-------|----|------------|
| P0 | sniper | **23** | 3 |
| P1 | aggressive | **18** | 3 |
| P2 | hoarder | **8** | 4 |
| P3 | spread | **13** | 3 |

---
## Round 4

**Condition Card: Naturals Only** (card_restriction)
> *Mascots cannot be played this round.*

### Deploy

*All players simultaneously place cards face-down on their boards.*

**P0** (sniper) — plays 3 cards to 2 zones:
  -  Red: Red 1
  -  Green: Green 1, Green 0
  - *0 cards held back*

**P1** (aggressive) — plays 3 cards to 3 zones:
  -  Red: Red 0
  -  Yellow: Yellow 1
  -  Blue: Blue 0
  - *0 cards held back*

**P2** (hoarder) — plays 4 cards to 2 zones:
  -  Yellow: Yellow 3
  -  Blue: Blue 5, Blue 3, Blue 0
  - *0 cards held back*

**P3** (spread) — plays 2 cards to 2 zones:
  -  Yellow: Yellow 0
  -  Blue: Blue 1
  - *1 cards held back*

### Reveal

| Zone | Player | Cards |
|------|--------|-------|
|  Red | P0 | Red 1 |
|  Red | P1 | Red 0 |
|  Yellow | P1 | Yellow 1 |
|  Yellow | P2 | Yellow 3 |
|  Yellow | P3 | Yellow 0 |
|  Green | P0 | Green 1, Green 0 |
|  Blue | P1 | Blue 0 |
|  Blue | P2 | Blue 5, Blue 3, Blue 0 |
|  Blue | P3 | Blue 1 |

### Strength & Scoring

** Red Zone:**

- P0: 1 (Red 1) +3 (Home Field — Red 1) = **4**
- P1: 0 (Red 0) +3 (Home Field — Red 0) = **3**
- **P0 wins** (4 vs P1=3) → **+5 VP**

** Yellow Zone:**

- P1: 1 (Yellow 1) +3 (Home Field — Yellow 1) = **4**
- P2: 3 (Yellow 3) +3 (Home Field — Yellow 3) = **6**
- P3: 0 (Yellow 0) +3 (Home Field — Yellow 0) = **3**
- **P2 wins** (6 vs P1=4, P3=3) → **+5 VP**

** Green Zone:**

- P0: 1 (Green 1) +2 (1 extra × 2) +3 (Home Field — Green 1) = **6**
- **P0 wins uncontested → +5 VP**

** Blue Zone:**

- P1: 0 (Blue 0) +3 (Home Field — Blue 0) = **3**
- P2: 5 (Blue 5) +4 (2 extra × 2) +3 (Home Field — Blue 5) = **12**
- P3: 1 (Blue 1) +3 (Home Field — Blue 1) = **4**
- **P2 wins** (12 vs P1=3, P3=4) → **+5 VP**

#### Scoreboard

| Player | Style | VP | Cards Left |
|--------|-------|----|------------|
| P0 | sniper | **33** | 0 |
| P1 | aggressive | **18** | 0 |
| P2 | hoarder | **18** | 0 |
| P3 | spread | **13** | 1 |

---
## Final Results

| Player | Style | Final VP | Zones Won | Cards Played |
|--------|-------|----------|-----------|--------------|
| P0 🏆 | sniper | **33** | 7 | 12 |
| P1 | aggressive | **18** | 4 | 12 |
| P2 | hoarder | **18** | 4 | 12 |
| P3 | spread | **13** | 3 | 11 |

> **Player 0 (sniper) wins by 15 VP!**
>
> *Surgical precision — the Mascot combo is a thing of beauty.*

---
### Game Statistics

- Home Field triggers: 32
- Mascot combos: 3
- Bomb kills: 0
- Shield saves: 0
- Swap uses: 0
- Bounty wins: 0, fails: 1
- Dud plays: 3
- Conditions: Spread Out, Rainbow, Inversion, Naturals Only

---
*Generated by the v0.1 simulation engine.*