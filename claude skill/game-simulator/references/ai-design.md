# AI Player Design Reference

How to build heuristic AI players that produce meaningful simulation data. The AI needs to be good enough that balance conclusions are trustworthy — when the simulator says a card is too hard to complete, you want confidence that it's actually too hard, not that the AI just couldn't figure it out.

## Table of Contents

1. [Three Axes of AI Behavior](#three-axes)
2. [Skill Level System](#skill-levels)
3. [Play Style Profiles](#play-style-profiles)
4. [Aggression Axis](#aggression)
5. [Action Selection Architecture](#action-selection)
6. [Evaluation Functions](#evaluation-functions)
7. [CLI Integration](#cli-integration)

---

## Three Axes

Every AI player is defined by three independent parameters:

**Skill** (0.0 – 1.0): How many mistakes the player makes. At 1.0 (expert), play is optimal within the heuristic's limits. Lower values introduce realistic beginner errors. This axis answers: "Is the game still fun when players aren't perfect?"

**Style** (categorical: balanced, rush, economy, control, etc.): What strategic approach the player takes. Different styles produce different action patterns and validate that the game supports multiple viable strategies. This axis answers: "Does one strategy dominate, or can different approaches all win?"

**Aggression** (0.0 – 1.0): How willing the player is to spend resources. High aggression = spend freely, grab expensive options. Low aggression = hoard resources, wait for cheap opportunities. This is a continuous dial layered on top of style.

These three axes are independent. You can have a skilled rusher, an unskilled economy player, or an aggressive beginner. The combinations produce meaningfully different play patterns.

---

## Skill Levels

Skill controls the probability of making various types of mistakes. At skill=1.0, no mistakes occur. At skill=0.0, all mistake types fire at their maximum rates. The probability scales linearly: `mistake_chance = max_rate * (1.0 - skill)`.

### Mistake Types

Each mistake type models a real beginner error:

**Missing completable objectives** — The player fails to notice they can complete an available objective. At skill=0.0, this happens ~40% of the time. The AI literally skips its best move.

```python
def _maybe_miss_objective(self) -> bool:
    """Beginners sometimes don't notice they can complete something."""
    miss_rate = 0.4 * (1.0 - self.skill)
    return self.rng.random() < miss_rate
```

**Noisy valuation** — The player misjudges how good a card or action is. At skill=0.0, noise of ±4 is added to every score. This means beginners sometimes draft bad cards over good ones, or pick low-VP objectives over high-VP ones.

```python
def _noisy_score(self, base_score: float) -> float:
    """Add noise to valuation. Beginners misjudge card quality."""
    noise_range = 4.0 * (1.0 - self.skill)
    if noise_range == 0:
        return base_score
    noise = self.rng.uniform(-noise_range, noise_range)
    return base_score + noise
```

**Tunnel vision** — The player fixates on a single faction/strategy and ignores better options elsewhere. At skill=0.0, ~30% chance of locking onto whatever faction they started with.

```python
def _should_tunnel_vision(self) -> bool:
    """Beginners sometimes over-commit to their first strategy."""
    rate = 0.3 * (1.0 - self.skill)
    return self.rng.random() < rate
```

**Forgetting special rules** — The player forgets that a game mechanic exists (e.g., that wild cards can substitute for any type). At skill=0.0, ~25% chance of forgetting.

```python
def _forget_special_rule(self) -> bool:
    """Beginners sometimes forget that wildcards/substitutions exist."""
    rate = 0.25 * (1.0 - self.skill)
    return self.rng.random() < rate
```

**Bad timing on expensive actions** — The player uses expensive/disruptive actions at the wrong time. At skill=0.0, ~20% chance of inverting the wipe/reset decision (using it when they shouldn't, not using it when they should).

```python
def _bad_timing_decision(self) -> bool:
    """Beginners sometimes make expensive plays at the wrong moment."""
    rate = 0.2 * (1.0 - self.skill)
    return self.rng.random() < rate
```

### Why These Mistakes Matter

Skill level modeling answers important design questions:
- **Is the game too punishing for beginners?** If expert win rate is 60%+ against beginners, the skill gap might be too large for a fun mixed-skill table.
- **Is the game too random?** If beginners win as often as experts, skill doesn't matter enough — the game might be too luck-dependent.
- **Are rules too complex?** If "forgetting special rules" barely affects outcomes, the rule might not be pulling its weight.

A good target: experts should win more often than beginners, but not crushingly so. In a 3-player game with 1 expert and 2 beginners, something like 40-45% expert vs 25-30% per beginner feels right — advantage is real but a beginner can still win on a good day.

---

## Play Style Profiles

Each style is a dict of parameters that modify how the AI evaluates actions:

```python
STYLE_PROFILES = {
    "balanced": {
        "description": "Well-rounded default play.",
        "objective_vp_weight": 1.0,     # How much VP matters
        "card_count_weight": 0.0,       # Prefer using fewer cards? (0=don't care)
        "draft_threshold": 2.0,         # Min score to bother drafting
        "reset_patience": 3,            # Turns stuck before resetting the board
        "hoard_resources": False,       # Accumulate resources?
        "rush_easy_objectives": False,  # Prioritize quick completions?
    },
    "rush": {
        "description": "Speed strategy. Complete cheap objectives fast.",
        "objective_vp_weight": 0.5,     # Volume over quality
        "card_count_weight": 2.0,       # Strongly prefer fewer-card objectives
        "draft_threshold": 1.0,         # Draft aggressively
        "reset_patience": 2,            # Reset board quickly when stuck
        "hoard_resources": False,
        "rush_easy_objectives": True,
    },
    "economy": {
        "description": "Resource hoarder. Waits for big payoffs.",
        "objective_vp_weight": 2.0,     # Only chase high-VP objectives
        "card_count_weight": -1.0,      # Willing to spend more cards
        "draft_threshold": 3.0,         # Very picky
        "reset_patience": 5,            # Hates spending on resets
        "hoard_resources": True,
        "rush_easy_objectives": False,
    },
    "control": {
        "description": "Disruptive. Resets the board to deny opponents.",
        "objective_vp_weight": 1.0,
        "card_count_weight": 0.0,
        "draft_threshold": 2.0,
        "reset_patience": 2,            # Resets early and often
        "hoard_resources": False,
        "rush_easy_objectives": False,
    },
}
```

### Using Style in Decisions

Style parameters modify scoring, not replace it. The AI still uses the same evaluation logic — styles just shift the weights:

```python
def _score_objective(self, objective, cards_needed, game):
    """Score an objective for completion priority."""
    vp = objective.vp
    card_cost = len(cards_needed)

    # Style-weighted score
    score = vp * self.style_profile["objective_vp_weight"]
    score -= card_cost * self.style_profile["card_count_weight"]

    # Rush bonus for easy objectives
    if self.style_profile["rush_easy_objectives"] and objective.tier <= 2:
        score += 3.0

    return self._noisy_score(score)  # Apply skill noise
```

### What Styles Tell You

When you run all four styles against each other, you learn:
- **Does one style dominate?** If rush always wins, the game probably rewards speed too much. If economy always wins, the endgame payoffs are too generous.
- **Are actions balanced?** Styles should produce genuinely different action profiles. If control players never actually reset the board, the reset mechanic isn't impactful enough.
- **Is there meaningful strategy?** If all styles produce the same win rate, strategic choice might not matter (too much randomness).

A healthy game shows each style winning 20-35% in a 4-way matchup, with different styles favored in different game states.

---

## Aggression

Aggression is a continuous 0.0–1.0 parameter that modifies resource-spending decisions:

```python
def _evaluate_draft(self, player, slot, card, game):
    """Score a potential draft."""
    base_value = self._card_value(card)
    cost = game.rules["slot_pricing"][slot]
    bonus = game.market_bonuses[slot]

    score = base_value + bonus - cost

    # Aggression modifies willingness to pay
    if cost > 0:
        score += (self.aggression - 0.5) * 2  # High aggression = less cost-sensitive

    return score
```

Aggression doesn't need to be a separate style — it's a dial that can be applied to any style. An aggressive economy player still hoards, just with a slightly higher spending threshold.

---

## Action Selection Architecture

### Priority-Based Scoring

Don't use a rigid decision tree. Instead, score every legal action and pick the highest:

```python
def choose_action(self, player, game) -> dict:
    """Evaluate all actions and return the best one."""
    candidates = []

    # 1. Check for completable objectives
    if not self._maybe_miss_objective():
        completable = find_completable(player.hand, game.display)
        for obj, cards in completable:
            score = self._score_objective(obj, cards, game)
            candidates.append(("complete", score, {"objective": obj, "cards": cards}))

    # 2. Evaluate board reset
    reset_score = self._evaluate_reset(player, game)
    if reset_score > 0:
        candidates.append(("reset", reset_score, {}))

    # 3. Evaluate each draft option
    for slot, item in enumerate(game.market):
        if item is not None:
            score = self._evaluate_draft(player, slot, item, game)
            candidates.append(("draft", score, {"slot": slot}))

    # 4. Evaluate other actions (scramble, timeout, etc.)
    # ...

    # 5. Fallback
    if not candidates:
        return {"type": "timeout"}

    # Pick highest-scoring action
    best = max(candidates, key=lambda x: x[1])
    return self._build_action_dict(best)
```

### Why Not a Decision Tree?

A decision tree (if/elif/elif) is brittle:
- Adding a new action means finding the right place in the tree
- Interactions between actions are hard to model (e.g., "should I draft this card or complete that objective?" requires comparing them)
- Style and skill modifiers need to be sprinkled everywhere

A scoring system lets all actions compete on the same numeric scale. Styles shift the weights, skill adds noise, and the highest score wins. Much easier to extend and debug.

---

## Evaluation Functions

Each action type needs its own evaluation function. Here are the key patterns:

### Objective Completion

```python
def _score_objective(self, objective, cards_needed, game):
    vp = objective.vp
    cards_used = len(cards_needed)

    score = vp * self.style_profile["objective_vp_weight"]
    score -= cards_used * self.style_profile["card_count_weight"]

    # Bonus if this triggers a secondary scoring condition
    if self._triggers_bonus(objective):
        score += 3.0

    return self._noisy_score(score)
```

### Draft Evaluation

```python
def _evaluate_draft(self, player, slot, card, game):
    base_value = self._card_value(card)
    cost = game.rules["slot_pricing"][slot]
    bonus_resources = game.market_bonuses.get(slot, 0)

    score = base_value + bonus_resources - cost

    # Big bonus if this card enables completing an objective next turn
    if self._enables_completion(player, card, game):
        score += 5.0

    # Aggression modifier
    score += (self.aggression - 0.5) * cost

    return self._noisy_score(score)
```

### Board Reset Evaluation

```python
def _evaluate_reset(self, player, game):
    """Should we reset the board (wipe market, shuffle display, etc.)?"""
    cost = game.rules["reset_cost"]
    if player.resources < cost:
        return -999  # Can't afford it

    # Style-driven patience
    patience = self.style_profile["reset_patience"]
    turns_stuck = player.turns_without_progress

    if turns_stuck < patience:
        return -1  # Not stuck enough yet

    # Score based on how bad current options are
    current_options = len(find_completable(player.hand, game.display))
    score = 5.0 - current_options * 2.0  # Worse options = more reason to reset

    # Control style gets bonus for denying opponents
    if self.style_profile.get("deny_opponents"):
        opponent_threats = self._count_opponent_near_completion(game)
        score += opponent_threats * 2.0

    # Skill-based timing errors
    if self._bad_timing_decision():
        score = -score  # Invert the decision

    return score
```

---

## CLI Integration

### Player Config Flags

```python
# Per-player skill
parser.add_argument("--skill", type=str, default=None,
                   help="Comma-separated skills: '1.0,0.5,0.3'")

# Per-player style
parser.add_argument("--styles", type=str, default=None,
                   help="Comma-separated styles: 'rush,economy,balanced'")

# Presets for common configurations
parser.add_argument("--preset", type=str, default=None,
                   choices=["experts", "beginners", "mixed", "styles"])
```

### Parsing Player Configs

```python
def build_player_configs(args, num_players):
    configs = [{}] * num_players

    if args.preset == "experts":
        configs = [{"skill": 1.0, "style": "balanced"} for _ in range(num_players)]
    elif args.preset == "beginners":
        configs = [{"skill": 0.3, "style": "balanced"} for _ in range(num_players)]
    elif args.preset == "mixed":
        configs = [{"skill": 1.0, "style": "balanced"}]
        configs += [{"skill": 0.3, "style": "balanced"} for _ in range(num_players - 1)]
    elif args.preset == "styles":
        style_list = ["rush", "economy", "control", "balanced"]
        configs = [{"skill": 1.0, "style": style_list[i % len(style_list)]}
                  for i in range(num_players)]

    # Override with explicit flags
    if args.skill:
        skills = [float(s) for s in args.skill.split(",")]
        for i, s in enumerate(skills):
            if i < len(configs):
                configs[i]["skill"] = s

    if args.styles:
        styles = args.styles.split(",")
        for i, s in enumerate(styles):
            if i < len(configs):
                configs[i]["style"] = s.strip()

    return configs
```

### Useful Presets

Define presets that answer common design questions:

| Preset | What it tests |
|--------|--------------|
| `experts` | Baseline — how does the game play with optimal-ish play? |
| `beginners` | Is the game accessible? Do beginners stall or get confused? |
| `mixed` | Does skill gap feel fair? Can beginners compete? |
| `styles` | Are multiple strategies viable? Does one dominate? |
