# Get Stuffed — Simulation Analysis Report

**Total games simulated:** 2,500 (500 per configuration)
**Configurations tested:** 2-player, 4-player, 6-player, 4-player styles, 4-player expert vs beginners

---

## Executive Summary

Get Stuffed is well-designed overall. Most games finish in a reasonable number of turns, Sugar Crash rarely needs to intervene, and the core shedding loop works. However, the simulation surfaced **four findings worth investigating** — ranging from a notable first-player disadvantage to a near-total absence of skill expression.

---

## Finding 1: First-Player Disadvantage (All Player Counts)

The player who goes first consistently underperforms. This is the opposite of most card games.

| Players | P0 Win Rate | Expected | Deviation |
|---------|-------------|----------|-----------|
| 2       | 47.0%       | 50.0%    | -3.0%     |
| 4       | 20.8%       | 25.0%    | -4.2%     |
| 6       | 13.2%       | 16.7%    | -3.5%     |

**Why this happens:** P0 acts with the least information. Every other player benefits from seeing cards played and powers triggered before their first turn. In a shedding game, knowing what factions/ranks are in play is valuable — P0 plays blind.

At 6 players, the effect is even more pronounced. P0 and P1 are both disadvantaged (13.2% and 14.2%), while P3 peaks at 20.4%. The "sweet spot" appears to be the middle seats.

**Possible fixes to test:**
- Give P0 a bonus draw (peek top 1-2 cards of stash before first turn)
- Have P0 start with one fewer card (advantage of playing first offsets smaller hand)
- Use the first pit card to set an initial "common knowledge" baseline

---

## Finding 2: Skill Barely Matters (Expert vs Beginners)

In the mixed-skill test (1 expert at skill=1.0 vs 3 beginners at skill=0.3), the expert won **25.2%** of games — exactly the expected 25%. Beginners won at essentially the same rate.

| Player | Skill | Win Rate |
|--------|-------|----------|
| P0     | 1.0   | 25.2%    |
| P1     | 0.3   | 25.2%    |
| P2     | 0.3   | 23.6%    |
| P3     | 0.3   | 26.0%    |

**What this means:** Get Stuffed is *highly luck-dependent*. Strategic decisions (which card to play when you have options, how to use powers) don't substantially change outcomes. This is not necessarily a problem — the game targets ages 10+ and play times of 10-15 minutes, so a luck-heavy design fits the genre. But if you want skilled players to feel rewarded, the game needs more decision points.

**Why skill doesn't help much:** Most turns have only 1-2 playable cards, so the "choice" is trivial. The biggest swing factor is scavenging luck — flipping a 0 vs a 10 during scavenging is a massive difference (0 penalty cards vs 10), and no skill can prevent it.

**Possible fixes to increase skill expression:**
- Allow players to hold multiple playable cards and choose strategically (already works, but the matching rules are so tight that options are few)
- Add a "discard a card to draw 2" action as an alternative to playing
- Let players see the top card of the Stash before choosing to play or pass

---

## Finding 3: Aggressive Shedding Dominates (Style Comparison)

When four different AI strategies compete, the aggressive shedder wins most often:

| Style            | Seat | Win Rate |
|------------------|------|----------|
| Balanced         | P0   | 23.4%    |
| **Aggressive Shed** | **P1** | **31.6%** |
| Disruptive       | P2   | 23.8%    |
| Hoarder          | P3   | 21.2%    |

Aggressive shedding (play cards fast, use wilds freely, don't conserve for later) beats all other approaches by a significant margin. This makes sense — in a shedding game, the primary win condition is "get rid of cards," so the strategy of "get rid of cards faster" should logically win. But a 10% gap over the hoarder suggests that hoarding wilds and high-power cards is actively punished.

**What this means for design:** Holding cards for strategic moments (the "I'll save this Time Traveler for the perfect time" instinct) is a losing play. The game rewards volume over timing. If that's intentional, no changes needed. If you want strategic variety, consider:

- Making powers stronger so saving a high-rank card for the right moment is worth the delay
- Penalizing rapid play somehow (e.g., if you play 3+ cards in one turn sequence via Re-Tinker/Foresaw, draw 1)
- Making wilds more limited (perhaps 0-5 instead of 0-10 for Purple, reducing the number of wild cards from 11 to 6)

---

## Finding 4: Scavenging Penalty Distribution

The penalty system works well overall, but the shape is worth understanding:

| Penalty Size | Frequency | Impact |
|-------------|-----------|--------|
| 0 cards     | 9.5%      | Flipped a rank-0 card. Zero penalty. |
| 1-2 cards   | 64%       | Light penalty. Manageable. |
| 3-5 cards   | 23%       | Moderate. Noticeable hand bloat. |
| 6-8 cards   | 3%        | Brutal. Game-changing setback. |
| 9-10 cards  | 0.2%      | Catastrophic. Essentially game-ending. |

The **mercy save rate is 47%** — nearly half of all scavenges are rescued by drawing a matching card during the penalty. This is a healthy number: it means the Mercy Clause meaningfully helps without trivializing the scavenge risk.

However, the ~3% chance of drawing 6-10 penalty cards creates enormous variance. A player who gets unlucky early with a high-penalty scavenge essentially cannot recover. Since the penalty is determined by a single random card flip, there's no way to mitigate this.

**Possible adjustment:** Cap the maximum penalty at 7 (or remove rank 8-10 from the penalty calculation, treating them as 7). This would keep scavenging scary without the occasional game-destroying 10-card penalty.

---

## Healthy Metrics (Things Working Well)

**Game length** is appropriate for the format:

| Players | Avg Turns | Per Player | Minutes (est) |
|---------|-----------|------------|---------------|
| 2       | 37        | ~18        | 8-12          |
| 4       | 48        | ~12        | 10-15         |
| 6       | 50        | ~8         | 10-15         |

**Sugar Crash** activates rarely (2-18% depending on player count) and only in long games, exactly as intended. It's a safety valve, not a regular occurrence.

**Power balance** is excellent. All five non-wild factions trigger at nearly identical rates (3.5-4.1 per game). No faction's power is noticeably over- or under-used.

**Reshuffles** average 0.2-0.6 per game — the deck is big enough that most games never reshuffle, and very few need the second reshuffle that triggers Sugar Crash.

---

## Simulator Usage Guide

All tools are in the `simulator/` directory. No dependencies needed — standard Python only.

### Run a batch simulation
```bash
python run_simulation.py -n 500 -p 4          # 500 games, 4 players
python run_simulation.py -n 200 -p 3 --json results.json  # Export data
```

### Test different configurations
```bash
python run_simulation.py -n 500 -p 4 --preset experts     # All expert AI
python run_simulation.py -n 500 -p 4 --preset beginners   # All beginner AI
python run_simulation.py -n 500 -p 4 --preset mixed        # 1 expert + 3 beginners
python run_simulation.py -n 500 -p 4 --preset styles       # 4 different strategies
```

### Watch a single game play out
```bash
python narrate_game.py --seed 42 -p 4         # Print to stdout
python narrate_game.py --seed 42 -p 4 -o game.md  # Save to file
```

### Tune rules via config.json
All tunable values live in `config.json`. Change starting hand sizes, power parameters, Sugar Crash timing, etc. without editing code.
