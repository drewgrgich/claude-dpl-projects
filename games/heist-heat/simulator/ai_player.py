"""
Heist Heat — Heuristic AI Player

Three play styles:
- Cautious: Gets away early, avoids high-heat cracks, plays safe
- Aggressive: Pushes for big chains, stays in longer, high-risk high-reward
- Opportunistic: Balanced play, adapts based on game state

Three axes: skill (0-1), style (categorical), aggression (0-1)
"""

from typing import List, Tuple, Optional, Dict
from collections import Counter
import random

from cards import Card, VaultGrid
# game_state imported locally to avoid circular imports


STYLE_PROFILES = {
    "cautious": {
        "description": "Plays safe. Gets away early. Avoids high-heat targets.",
        "getaway_eagerness": 0.9,      # How quickly to getaway once possible
        "high_rank_avoidance": 0.7,     # Avoid cracking high-rank vault cards
        "chain_seeking": 0.3,           # How much to value chain potential
        "alarm_avoidance": 0.9,         # Avoid face-down cards near alarms
        "heat_sensitivity": 2.0,        # Multiplier on heat concerns
        "faction_power_eagerness": 0.4, # How quickly to use faction powers
    },
    "aggressive": {
        "description": "Pushes luck. Seeks big chains. Stays in late.",
        "getaway_eagerness": 0.3,
        "high_rank_avoidance": 0.2,
        "chain_seeking": 0.9,
        "alarm_avoidance": 0.3,
        "heat_sensitivity": 0.5,
        "faction_power_eagerness": 0.8,
    },
    "opportunistic": {
        "description": "Balanced play. Adapts to game state.",
        "getaway_eagerness": 0.6,
        "high_rank_avoidance": 0.5,
        "chain_seeking": 0.6,
        "alarm_avoidance": 0.5,
        "heat_sensitivity": 1.0,
        "faction_power_eagerness": 0.6,
    },
}


class HeuristicAI:
    """
    AI player for Heist Heat.

    Decision flow each turn:
    1. Should I getaway? (if heat >= threshold)
    2. If not, which vault card should I crack?
    3. Should I use a faction power?
    """

    def __init__(self, skill: float = 1.0, style: str = "opportunistic",
                 aggression: float = 0.5, rng_seed: int = None):
        self.skill = max(0.0, min(1.0, skill))
        self.style = style
        self.aggression = max(0.0, min(1.0, aggression))
        self.profile = STYLE_PROFILES.get(style, STYLE_PROFILES["opportunistic"])
        self.rng = random.Random(rng_seed)

    # ── Noise/Mistake Helpers ───────────────────────────────────────

    def _noisy_score(self, base: float) -> float:
        noise_range = 3.0 * (1.0 - self.skill)
        if noise_range == 0:
            return base
        return base + self.rng.uniform(-noise_range, noise_range)

    def _should_miss_opportunity(self) -> bool:
        return self.rng.random() < 0.3 * (1.0 - self.skill)

    def _bad_timing(self) -> bool:
        return self.rng.random() < 0.2 * (1.0 - self.skill)

    # ── Main Decision ───────────────────────────────────────────────

    def choose_action(self, player, game) -> dict:
        """
        Choose an action for this turn.
        Returns dict: {"type": "getaway"} or {"type": "crack", ...}
        """
        # Can't do anything with no cards
        if player.hand_size == 0:
            if game.heat >= game.heat_getaway:
                return {"type": "getaway"}
            else:
                return {"type": "pass"}  # Stuck waiting

        # Should I getaway?
        if game.heat >= game.heat_getaway and self._should_getaway(player, game):
            return {"type": "getaway"}

        # Choose a crack target
        crack_choice = self._choose_crack(player, game)
        if crack_choice:
            return crack_choice

        # Fallback: getaway if possible, else pass
        if game.heat >= game.heat_getaway:
            return {"type": "getaway"}
        return {"type": "pass"}

    def choose_action_with_reasoning(self, player, game) -> Tuple[dict, str]:
        """Choose action and return reasoning string for narration."""
        reasoning_lines = []

        if player.hand_size == 0:
            if game.heat >= game.heat_getaway:
                return {"type": "getaway"}, "No cards left — must getaway."
            return {"type": "pass"}, "No cards left. Waiting for round to end."

        # Evaluate getaway
        getaway_score = self._evaluate_getaway(player, game)
        if game.heat >= game.heat_getaway:
            reasoning_lines.append(
                f"Getaway option: score={getaway_score:.1f} "
                f"(stash={len(player.stash)} cards, heat={game.heat})"
            )

        # Evaluate all crack targets
        crack_options = self._evaluate_all_cracks(player, game)
        if crack_options:
            top_3 = crack_options[:3]
            for score, row, col, card_idx, use_power, reasoning in top_3:
                hand_card = player.hand[card_idx]
                target = game.vault.get(row, col)
                target_str = f"{target!r}" if game.vault.revealed[row][col] else "??"
                reasoning_lines.append(
                    f"Crack ({row},{col})={target_str} with {hand_card!r}: "
                    f"score={score:.1f} {reasoning}"
                )

        # Decision
        if (game.heat >= game.heat_getaway and getaway_score > 0 and
                (not crack_options or getaway_score > crack_options[0][0])):
            reasoning_lines.append(f"**Decision: GETAWAY** (score {getaway_score:.1f})")
            return {"type": "getaway"}, "\n".join(reasoning_lines)

        if crack_options:
            best = crack_options[0]
            score, row, col, card_idx, use_power, _ = best
            action = {
                "type": "crack",
                "row": row, "col": col,
                "hand_card_idx": card_idx,
                "use_faction_power": use_power,
            }
            power_str = " (using faction power)" if use_power else ""
            reasoning_lines.append(
                f"**Decision: CRACK ({row},{col}) with "
                f"{player.hand[card_idx]!r}{power_str}**"
            )
            return action, "\n".join(reasoning_lines)

        if game.heat >= game.heat_getaway:
            reasoning_lines.append("**Decision: GETAWAY** (no good cracks)")
            return {"type": "getaway"}, "\n".join(reasoning_lines)

        reasoning_lines.append("**Decision: PASS** (stuck)")
        return {"type": "pass"}, "\n".join(reasoning_lines)

    # ── Getaway Evaluation ──────────────────────────────────────────

    def _should_getaway(self, player, game) -> bool:
        score = self._evaluate_getaway(player, game)
        crack_options = self._evaluate_all_cracks(player, game)
        best_crack = crack_options[0][0] if crack_options else -999
        return score > best_crack

    def _evaluate_getaway(self, player, game) -> float:
        if game.heat < game.heat_getaway:
            return -999

        stash_value = len(player.stash)
        heat_pressure = (game.heat - game.heat_getaway) / (game.heat_end - game.heat_getaway)

        # Base score: stash value * heat pressure * eagerness
        score = stash_value * (1 + heat_pressure * 2) * self.profile["getaway_eagerness"]

        # Bonus if stash is big
        if stash_value >= 5:
            score += 3.0

        # Penalty if stash is empty (no point getting away with nothing)
        if stash_value == 0:
            score -= 5.0

        # Heat sensitivity
        if game.heat >= game.heat_end - 1:
            score += 10.0 * self.profile["heat_sensitivity"]

        # Aggression pushes you to stay
        score -= self.aggression * 3.0

        # Skill noise
        return self._noisy_score(score)

    # ── Crack Evaluation ────────────────────────────────────────────

    def _choose_crack(self, player, game) -> Optional[dict]:
        options = self._evaluate_all_cracks(player, game)
        if not options:
            return None
        best = options[0]
        _, row, col, card_idx, use_power, _ = best
        return {
            "type": "crack",
            "row": row, "col": col,
            "hand_card_idx": card_idx,
            "use_faction_power": use_power,
        }

    def _evaluate_all_cracks(self, player, game) -> list:
        """
        Evaluate all possible crack targets with all possible hand cards.
        Returns sorted list of (score, row, col, hand_card_idx, use_power, reasoning).
        """
        options = []
        vault_positions = game.vault.occupied_positions()

        if not vault_positions or player.hand_size == 0:
            return options

        for r, c in vault_positions:
            vault_card = game.vault.get(r, c)
            is_known = game.vault.revealed[r][c]

            for card_idx, hand_card in enumerate(player.hand):
                # Evaluate with and without faction power
                for use_power in [False, True]:
                    if use_power and hand_card.faction in player.faction_powers_used:
                        continue
                    # Skip non-useful powers for crack evaluation
                    if use_power and hand_card.faction in ("GREEN", "ORANGE"):
                        # Peek powers — evaluate separately
                        score = self._score_peek_power(
                            player, game, hand_card, r, c, vault_card, is_known
                        )
                        if score > 0:
                            options.append((
                                score, r, c, card_idx, True,
                                f"(peek power {hand_card.faction})"
                            ))
                        continue

                    if use_power and hand_card.faction == "BLUE":
                        # Steal power
                        score = self._score_blue_steal(player, game)
                        if score > 0:
                            options.append((
                                score, r, c, card_idx, True, "(Blue steal)"
                            ))
                        continue

                    score, reasoning = self._score_crack(
                        player, game, hand_card, r, c, vault_card,
                        is_known, use_power
                    )
                    if score > -50:
                        options.append((score, r, c, card_idx, use_power, reasoning))

        options.sort(key=lambda x: x[0], reverse=True)
        return options

    def _score_crack(self, player, game, hand_card: Card,
                     row: int, col: int, vault_card: Card,
                     is_known: bool, use_power: bool) -> Tuple[float, str]:
        """Score a specific crack attempt."""
        effective_rank = hand_card.rank
        reasoning = ""

        # Red power bonus
        if use_power and hand_card.faction == "RED":
            effective_rank += 2
            reasoning += "+2 Red "

        # Purple safety net (handled at game level, but affects score)
        purple_safety = (use_power and hand_card.faction == "PURPLE")

        if is_known:
            # Known vault card — can calculate exactly
            if effective_rank >= vault_card.rank:
                # Will succeed
                score = self._score_successful_crack(
                    game, vault_card, row, col, effective_rank
                )
                reasoning += f"sure-win vs {vault_card!r} "
            else:
                if purple_safety:
                    score = -1.0  # Will fail but card comes back
                    reasoning += "fail+Purple "
                else:
                    score = -10.0 - hand_card.rank  # Bad idea
                    reasoning += f"certain-fail vs {vault_card!r} "
        else:
            # Unknown vault card — probabilistic
            # Estimate success probability
            success_prob = self._estimate_success_prob(effective_rank)
            expected_value = success_prob * self._estimate_chain_value(
                game, row, col, effective_rank
            )
            fail_cost = (1 - success_prob) * (hand_card.rank * 0.5 + 2)

            if purple_safety:
                fail_cost *= 0.1  # Nearly free to fail (card returns + draw)

            score = expected_value - fail_cost
            reasoning += f"p(win)={success_prob:.0%} "

        # Heat cost concern
        heat_concern = self.profile["heat_sensitivity"] * (game.heat / game.heat_end)
        score -= heat_concern * 1.5

        # Avoid wasting high cards on easy targets
        if is_known and vault_card.rank <= 3 and hand_card.rank >= 8:
            score -= 2.0
            reasoning += "overkill "

        # Prefer using low-rank cards when possible
        score -= hand_card.rank * 0.1

        # Chain potential bonus
        chain_potential = self._estimate_chain_size(game, row, col, effective_rank)
        score += chain_potential * self.profile["chain_seeking"]
        if chain_potential > 1:
            reasoning += f"chain~{chain_potential} "

        # Yellow perfect-fit bonus (within ±tolerance)
        if use_power and hand_card.faction == "YELLOW" and is_known:
            tolerance = game.rules.get("yellow_rank_tolerance", 0)
            if abs(hand_card.rank - vault_card.rank) <= tolerance:
                # Perfect fit: claim ALL adjacent regardless of rank
                adj_count = len([
                    (nr, nc) for nr, nc in game.vault.orthogonal_neighbors(row, col)
                    if game.vault.get(nr, nc) is not None
                ])
                score += adj_count * 3.0
                reasoning += f"Yellow-perfect({adj_count}adj) "

        return self._noisy_score(score), reasoning

    def _score_successful_crack(self, game, vault_card, row, col,
                                 effective_rank) -> float:
        """Score a crack we know will succeed."""
        base = vault_card.rank * 0.5 + 1.0  # Base value of the card

        # Chain value
        chain_est = self._estimate_chain_size(game, row, col, effective_rank)
        base += chain_est * 1.5

        # Penalty for alarms
        if vault_card.is_alarm:
            base -= 3.0  # +3 heat is bad

        return base

    def _estimate_success_prob(self, effective_rank: int) -> float:
        """Estimate probability of beating a random face-down card."""
        # Ranks 0-10, uniform distribution
        # We beat ranks 0 through effective_rank
        beatable = min(effective_rank + 1, 11)
        return beatable / 11.0

    def _estimate_chain_value(self, game, row, col, effective_rank) -> float:
        """Estimate expected value of chain reaction."""
        chain_size = self._estimate_chain_size(game, row, col, effective_rank)
        return chain_size * 1.5  # Each chained card is roughly 1.5 value

    def _estimate_chain_size(self, game, row: int, col: int,
                              effective_rank: int) -> int:
        """Estimate how many cards a chain might claim."""
        count = 0
        for nr, nc in game.vault.orthogonal_neighbors(row, col):
            card = game.vault.get(nr, nc)
            if card is None:
                continue
            if game.vault.revealed[nr][nc]:
                if card.rank <= effective_rank and not card.is_alarm:
                    count += 1
            else:
                # Unknown card — probabilistic
                prob = self._estimate_success_prob(effective_rank) * 0.6
                count += prob
        return count

    def _score_peek_power(self, player, game, hand_card, row, col,
                           vault_card, is_known) -> float:
        """Score using Green or Orange peek power."""
        if is_known:
            return -1  # No point peeking at known cards

        face_down = game.vault.face_down_positions()
        if len(face_down) < 2:
            return 0  # Not enough unknowns to make peeking worthwhile

        base = 3.0 * self.profile["faction_power_eagerness"]
        # More valuable early when many cards are unknown
        base += len(face_down) * 0.3
        return self._noisy_score(base)

    def _score_blue_steal(self, player, game) -> float:
        """Score using Blue steal power."""
        targets = [p for p in game.players
                   if p.id != player.id and len(p.stash) >= 2]
        if not targets:
            return -10

        best_stash = max(len(p.stash) for p in targets)
        score = best_stash * 1.5 * self.profile["faction_power_eagerness"]
        return self._noisy_score(score)

    # ── Green/Orange Peek Follow-up ─────────────────────────────────

    def choose_crack_after_green_peek(self, player, game,
                                       peek_results: list,
                                       played_card: Card,
                                       hand_card_idx: int) -> dict:
        """After seeing peeked cards, choose which to crack."""
        # Evaluate each peeked position
        best_score = -999
        best_pos = None

        for r, c, card in peek_results:
            if card is not None and played_card.rank >= card.rank:
                score = self._score_successful_crack(
                    game, card, r, c, played_card.rank
                )
                if score > best_score:
                    best_score = score
                    best_pos = (r, c)

        if best_pos:
            return {"row": best_pos[0], "col": best_pos[1]}

        # None of the peeked cards are good; pick original target or any face-down
        positions = game.vault.occupied_positions()
        if positions:
            return {"row": positions[0][0], "col": positions[0][1]}
        return None

    def choose_crack_after_orange_peek(self, player, game,
                                        target_card: Card,
                                        target_pos: tuple,
                                        played_card: Card) -> dict:
        """After seeing the target card, decide whether to commit or change."""
        if played_card.rank >= target_card.rank:
            return {"keep_target": True}

        # Target is too strong — find a different one
        positions = game.vault.occupied_positions()
        for r, c in positions:
            if (r, c) == target_pos:
                continue
            card = game.vault.get(r, c)
            if game.vault.revealed[r][c] and card and played_card.rank >= card.rank:
                return {"keep_target": False, "new_row": r, "new_col": c}

        # No better known targets — try a random face-down
        face_down = game.vault.face_down_positions()
        if face_down:
            pos = self.rng.choice(face_down)
            return {"keep_target": False, "new_row": pos[0], "new_col": pos[1]}

        # Stuck with original
        return {"keep_target": True}
