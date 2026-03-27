# Summit Scramble — Simulation Analysis Report

**Simulator:** 1,000 AI-vs-AI games per configuration | Seeded RNG | Heuristic AI with tunable skill/style/aggression

---

## Executive Summary

Summit Scramble plays well across all player counts. Games are fast (12–19 turns), all formations see use, every faction ability triggers regularly, and the Confetti Cannon and Trip-Up mechanics create memorable moments at healthy rates. The core climbing loop is sound.

The simulation did surface **six edge cases and balance observations** worth considering, ranging from a genuine rules gap to minor balance tuning opportunities.

---

## Key Metrics (1,000 Games Per Config)

### Game Length

| Players | Avg Turns | Range    | Avg Tricks | Range   |
|---------|-----------|----------|------------|---------|
| 3       | 12.7      | 5–19     | 12.2       | 4–18    |
| 4       | 16.0      | 10–22    | 14.9       | 8–20    |
| 5       | 18.6      | 11–24    | 16.9       | 10–23   |

Games land cleanly in the 20-minute target window. No games hit the turn limit after the bug fix (see Edge Case #1).

### Win Rates by Seat Position

| Seat | 3-Player | 4-Player | 5-Player |
|------|----------|----------|----------|
| P0   | 29.8%    | 25.4%    | **24.4%** |
| P1   | **35.4%** | **27.1%** | 21.7%    |
| P2   | 34.8%    | 24.4%    | 20.6%    |
| P3   | —        | 23.1%    | 16.4%    |
| P4   | —        | —        | 16.9%    |

### Formation Usage

| Formation        | 3-Player | 4-Player | 5-Player |
|------------------|----------|----------|----------|
| Solo Sprint      | 44.8%    | 48.3%    | 53.6%    |
| Surge (2-3)      | 23.2%    | 22.8%    | 21.2%    |
| Daisy Chain      | 23.2%    | 20.1%    | 16.7%    |
| Confetti Cannon  | 4.3%     | 2.6%     | 1.4%     |
| Trip-Up          | 4.6%     | 6.1%     | 7.1%     |

### Faction Ability Triggers (per game avg, 4-player)

| Ability       | Avg/Game | Notes |
|---------------|----------|-------|
| Rotation      | 1.6      | Most common — Red's disruption is valuable |
| Recalibrate   | 1.4      | Strong acceleration (net -1 card) |
| Reclaim       | 1.3      | Consistent value from Base Camp access |
| Streamline    | 1.2      | Pure speed — reliable acceleration |
| Scout         | 1.1      | Slightly below others |
| Revelation    | 0.9      | Least triggered — constraint (fewer cards) limits it |

### Special Plays

| Mechanic   | 3-Player     | 4-Player     | 5-Player     |
|------------|--------------|--------------|--------------|
| Cannons    | 0.48/game (41%) | 0.43/game (37%) | 0.29/game (26%) |
| Trip-Ups   | 0.81/game (60%) | 1.44/game (82%) | 2.02/game (92%) |

---

## Edge Cases and Findings

### 1. RULES GAP: Ability-Emptied Hands (Severity: High)

**What happened:** In ~0.4% of 4-player games, a player's hand was reduced to 0 cards by a faction ability (Streamline discarding their last card, or Recalibrate netting -1 when they had 2 cards). The rules say "When you play your last card, you reach The Summit" — but abilities aren't *playing* cards. These players had empty hands but weren't technically "out," creating a deadlock where no one could progress.

**Recommendation:** Add an explicit rule: *"If a Faction Ability reduces your hand to zero cards, you immediately reach The Summit, just as if you'd played your last card."* This is the most natural interpretation and is already how most players would rule it at the table. The alternative (you keep an empty hand and pass forever) creates a non-game. The Streamline and Recalibrate abilities are specifically designed as acceleration tools — going out via acceleration is thematically perfect.

**Frequency:** Rare but inevitable. Streamline triggering on a 1-card hand, or Recalibrate triggering on a 2-card hand, will happen in roughly 1 in 200 games.

### 2. BALANCE: First-Player Advantage at 3 Players (Severity: Low-Medium)

**What happened:** At 3 players, Player 0 (first to act) wins only 29.8% of games, while Players 1 and 2 win ~35% each. This is a **disadvantage** for going first — the opposite of what you'd expect in a climbing game. The cause: the first player leads (spending cards) while followers can pass for free, conserving resources. With only 3 players, the leader exposes themselves more before getting back around.

**Recommendation:** This is mild enough (~5% below expected) that it may not need fixing. However, if it bothers you, two options: (a) the 3-player starting hand could be 14 instead of 15 for the first player (slight compensation), or (b) the last-place player leading the next round (already in the rules) naturally corrects across a championship. Monitor with playtesting — the AI may not perfectly model human play here.

### 3. BALANCE: Conservative Style Is Nonviable (Severity: Medium)

**What happened:** In the 4-style matchup (aggressive, balanced, conservative, rush), the conservative player (P2) won only **9.5%** of games — dramatically underperforming vs the expected 25%. Meanwhile aggressive (28.5%), balanced (33.0%), and rush (29.0%) all performed well.

**Why this matters for design:** Summit Scramble is a racing game — the first to empty their hand wins. Holding back strong cards and passing often (the conservative approach) is mathematically punished because every pass is a turn spent not shedding cards. This isn't necessarily a problem (the game *should* reward aggression in a race), but it means **there's no "turtle" strategy.** If you want strategic diversity, you might need a mechanic that occasionally rewards patience — perhaps a bonus for winning a trick with a large gap (beating a 3 with a 10) or a "momentum" bonus for winning consecutive tricks.

**Counter-argument:** The design notes already acknowledge this tension ("every card played is one step closer to The Summit — but also one fewer card for fights ahead"). A purely conservative strategy *should* lose. The finding validates the design intent.

### 4. OBSERVATION: Trip-Up Frequency Scales Dramatically with Player Count (Severity: Info)

**What happened:** Trip-Ups occur in 60% of 3-player games but **92% of 5-player games**, averaging 2.0 per game at 5 players. This is because more players means more 0s in hands and more solo 10s being played.

**Why it matters:** At 5 players, solo 10s are almost never safe. This may make high cards feel less powerful than intended, since the "crown jewel" play (solo 10) is essentially always counterable. Players may learn to avoid solo 10s entirely at 5 players, instead using 10s only in Surges or Chains where they're Trip-Up-proof.

**Recommendation:** This is probably fine — it creates a meaningful strategic shift between player counts and makes the 0 cards more interesting. But watch for player frustration at 5 players where 10s feel "useless" as solos. If this becomes an issue, you could limit Trip-Ups to once per round at 5 players, or require the 0 to be of a specific faction (e.g., higher faction priority than the 10's faction).

### 5. OBSERVATION: Revelation Is the Least-Triggered Ability (Severity: Low)

**What happened:** Blue's Revelation (see hand, take 1, give 1) triggers 30-40% less often than other abilities (0.9/game vs 1.2-1.6 for others). The constraint — target must have *fewer cards* than you — limits when it can fire. In a race to empty your hand, the player who's winning (fewer cards) is exactly who you want to target, but you can only target players who are *ahead* of you.

**Why it matters:** Revelation is designed as an intel-gathering and disruption tool. But the "fewer cards" restriction means it mostly fires early in the game when hand sizes haven't diverged much, and rarely fires in the tense endgame when intel matters most. By the time someone is at 2-3 cards (when stealing a card would be devastating), almost everyone else has similar or fewer cards too.

**Recommendation:** Consider whether "fewer cards" is the right constraint. Alternatives: (a) "different number of cards" (can target anyone who isn't tied with you), (b) "any other player" with a cost (discard 1 extra to use it), or (c) keep it as-is and accept that Blue is slightly less powerful — the intel value of seeing a hand may compensate in human games where information matters more than in AI simulations.

### 6. OBSERVATION: Confetti Cannons Are Rare at 5 Players (Severity: Low)

**What happened:** Cannons appear in only 26% of 5-player games (vs 41% at 3 players). With only 11 cards per hand at 5 players, assembling 4 of the same rank is much harder. The 66-card deck has at most 6 copies of each rank (one per faction), but you'd need to collect 4 of 6 from a hand of 11.

**Why it matters:** Cannons are described as the "ultimate celebration" and a table-shaking event. At 5 players they're more of a theoretical possibility than a practical one. Players almost never get to experience the interrupt mechanic of the Cannon at higher player counts.

**Recommendation:** This is likely fine — at 5 players the Trip-Up fills the interrupt role beautifully (92% of games). The Cannon is naturally more viable at 3 players where starting hands are 15 cards. If you wanted more Cannons, you could allow 3-of-a-kind Cannons at 5 players only, but this adds complexity for marginal gain.

---

## Style Matchup Results (4 Players, 1,000 Games)

| Seat | Style        | Win Rate | Avg Finish |
|------|-------------|----------|------------|
| P0   | Aggressive  | 28.5%    | 2.41       |
| P1   | Balanced    | **33.0%** | **2.21**  |
| P2   | Conservative| 9.5%     | 3.06       |
| P3   | Rush        | 29.0%    | 2.33       |

**Balanced wins most** — it plays the best cards at the right moments without over-committing. **Rush is close** — pure card-shedding is rewarded in a race. **Conservative is crushed** — passivity kills in a climbing game. This pattern makes design sense for a racing game.

## Skill Gap Results (4 Players, 1,000 Games)

| Seat | Skill | Win Rate | Avg Finish |
|------|-------|----------|------------|
| P0   | 1.0 (expert)  | 26.5%  | 2.42 |
| P1   | 0.3 (beginner)| 24.7%  | 2.51 |
| P2   | 0.3 (beginner)| 23.8%  | 2.55 |
| P3   | 0.3 (beginner)| 25.0%  | 2.51 |

**Skill gap is very small.** The expert wins only slightly more than beginners (~2% advantage). This is consistent with a game that has high variance from the deal and trick dynamics. The game is accessible to mixed-skill tables, but may lack depth for competitive players. If you want skill to matter more, consider adding more decision points (perhaps more abilities that require timing choices, or a hand management mechanic during setup like drafting/mulliganing).

---

## Championship Results (200 Championships, 4 Players)

| Metric | Value |
|--------|-------|
| Avg rounds per championship | 7.8 |
| Range | 6–10 rounds |
| Avg total fatigue (winner) | ~22.8 Zzz's |

Win rates flatten nicely across a championship — the multi-round format reduces variance and rewards consistent play. The 30 Zzz limit produces a good championship length (7-8 rounds = roughly 2 hours of play).

---

## Files Delivered

- `simulator/config.json` — All tunable rules
- `simulator/cards.py` — Card dataclasses and deck
- `simulator/game_state.py` — Full game engine
- `simulator/ai_player.py` — Heuristic AI with skill/style/aggression
- `simulator/run_simulation.py` — Batch runner with CLI
- `simulator/narrate_game.py` — Single-game narration engine
- `narrated_game.md` — Example narrated game (seed 42)
