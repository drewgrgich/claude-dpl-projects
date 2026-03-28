#!/usr/bin/env python3
"""
Championship Arena — Iteration Driver v1.2
Tests 7 rule-change hypotheses against the fun audit.

Strategy: patch modules in-place (no module reload), run audit, revert.
"""

import os
import sys
import json
import random
import importlib
from typing import Dict, Tuple, Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# ─── Baseline ──────────────────────────────────────────────────────────────────

def run_audit(num_games: int = 250) -> Dict:
    """Run fun audit with current module state."""
    from fun_audit import run_fun_audit
    return run_fun_audit(num_games)


def fmt_d(audit, key):
    return f"{audit['dimensions'][key]['letter']}({audit['dimensions'][key]['value']:.0f})"


# ─── Patches (applied in-place, no reload) ─────────────────────────────────────

# Each patch is a dict with apply() and revert() that modify live modules.

def _make_patch(patch_id: str):
    """Decorator factory to register patches."""
    def decorator(fn):
        PATCHES[patch_id] = fn
        return fn
    return decorator


PATCHES: Dict[str, dict] = {}

# ─── Iteration A: FP target 25 ─────────────────────────────────────────────────

def _patch_A():
    # 1. Patch config.json
    cfg = json.load(open("config.json"))
    cfg["fp_to_win"] = 25
    json.dump(cfg, open("config.json", "w"), indent=2)
    # 2. Patch GameState.get_winner in-place
    import game_state as gs_mod
    def patched_get_winner(self):
        for p in self.players:
            if p.fp >= 25:
                return p
        return None
    gs_mod.GameState.get_winner = patched_get_winner

def _revert_A():
    cfg = json.load(open("config.json"))
    cfg["fp_to_win"] = 15
    json.dump(cfg, open("config.json", "w"), indent=2)
    import game_state as gs_mod
    importlib.reload(gs_mod)

PATCHES["A: FP target 25"] = (_patch_A, _revert_A)

# ─── Iteration B: Harder Sweeps ─────────────────────────────────────────────────

def _patch_B():
    import simulate_round as sr_mod
    orig = sr_mod.award_fp
    def harder_sweep(player, num_rings_won, gs, spectator_active):
        base_fp = {1: 1, 2: 3, 3: 4}  # sweep 6 → 4
        fp = base_fp.get(num_rings_won, 0)
        if spectator_active:
            fp *= 2
        if player.talent and player.talent["name"] == "The Showman":
            fp *= 2
        player.fp += fp
        if player.starstruck_active and num_rings_won > 0:
            player.fp += 2
            player.starstruck_active = False
        if gs.jittery_hamster_winner == player.id:
            player.fp += 1
    sr_mod.award_fp = harder_sweep

def _revert_B():
    import simulate_round as sr_mod
    importlib.reload(sr_mod)

PATCHES["B: Harder Sweeps (sweep=4 FP)"] = (_patch_B, _revert_B)

# ─── Iteration C: Spectator every OTHER round ───────────────────────────────────

def _patch_C():
    import simulate_round as sr_mod
    import random as rnd

    orig_round = sr_mod.simulate_round

    def odd_only_round(gs, audit_data=None):
        if gs.round_number % 2 == 1:  # odd → draw spectator
            return orig_round(gs, audit_data)

        # ── Even round: no spectator card ────────────────────────────────
        narration = f"\n{'='*60}\n"
        narration += f"  ROUND {gs.round_number} (No Spectator)\n"
        narration += f"{'='*60}\n"
        gs.round_number += 1

        gs.chaos_round = False
        gs.rainbow_ring = None
        gs.jittery_hamster_winner = None
        gs.starstruck_target = None
        gs.underdog_player = None
        if audit_data:
            audit_data["spectator_impact_this_round"] = False
            audit_data["talent_decisive"] = False
            audit_data["sweep_rounds"] = 0

        for p in gs.players:
            num_dice = 4
            if gs.underdog_player == p.id:
                num_dice = 5
            if gs.chaos_round:
                p.dice = [0] * num_dice
            else:
                p.dice = [rnd.randint(1, 6) for _ in range(num_dice)]

        narration += f"  🎲 Dice: {[(p.id, p.dice) for p in gs.players]}\n"

        from ai_player import AIPlayer
        ais = {p.id: AIPlayer(p, len(gs.players)) for p in gs.players}

        for p in gs.players:
            if p.talent and p.talent["trigger"] == "before_roll" and not p.talent_used_this_round:
                sr_mod.apply_talents_pre_roll(gs, p, ais[p.id])
                if audit_data:
                    audit_data["talent_decisive"] = True

        for p in gs.players:
            ais[p.id].assign_dice(gs)
            ais[p.id].play_cards(gs)

        narration += f"  🎯 Assignments: {[(p.id, p.assigned_dice) for p in gs.players]}\n"
        narration += f"  🃏 Cards: {[(p.id, list(p.played_cards.values())) for p in gs.players]}\n"

        narration += "  ✨ REVEAL!\n"
        for p in gs.players:
            for ring_color, card in p.played_cards.items():
                narration += f"    {p} @ {ring_color}: {card}\n"

        for p in gs.players:
            if p.talent and p.talent["name"] == "The Time Traveler" and not p.talent_used_this_round:
                sr_mod.apply_talents_after_reveal(gs, p, ais[p.id])
                if audit_data:
                    audit_data["talent_decisive"] = True

        sr_mod.resolve_stunt_doubles(gs)

        narration += "\n  📊 ENERGY:\n"
        for ring in gs.active_rings:
            for p in gs.players:
                if ring.color in p.assigned_dice or ring.power_type == "most_cards":
                    if ring.power_type == "most_cards":
                        score = sr_mod.calc_orange_energy(p, ring, gs)
                    else:
                        score = sr_mod.calc_ring_energy(p, ring, gs)
                    narration += f"    {p} @ {ring.color}: {score}\n"

        ring_winners = sr_mod.claim_rings(gs)

        rings_per_player: Dict[int, int] = {p.id: 0 for p in gs.players}
        for ring_color, winner in ring_winners.items():
            if winner:
                rings_per_player[winner.id] += 1

        narration += "\n  🏆 RING CLAIMS:\n"
        last_loser = None
        for ring_color, winner in ring_winners.items():
            ring = gs.get_ring_by_color(ring_color)
            if winner:
                narration += f"    {ring_color} → {winner}\n"
                sr_mod.award_trophy(winner, ring, gs)
                purple_count = sum(1 for c in winner.played_cards.values() if c.suit == "Purple")
                sr_mod.draw_cards_after_win(winner, gs, purple_count)
            else:
                narration += f"    {ring_color} → NO CLAIM\n"

        for player_id, num_rings in rings_per_player.items():
            player = gs.get_player_by_id(player_id)
            if player and num_rings > 0:
                sr_mod.award_fp(player, num_rings, gs, False)
                if num_rings == 3:
                    narration += f"    🎉 SWEEP by {player}!\n"
                    if audit_data:
                        audit_data["sweep_rounds"] += 1

        for p in gs.players:
            drafted = ais[p.id].draft_from_stunt_pool(gs)

        winner = gs.get_winner()
        if winner:
            gs.winner = winner
            narration += f"\n  🏆 WINNER: {winner} with {winner.fp} FP!\n"

        last_loser = None
        for player_id, num_rings in rings_per_player.items():
            if num_rings == 0:
                last_loser = gs.get_player_by_id(player_id)
        gs.last_round_loser = last_loser

        for p in gs.players:
            p.assigned_dice = {}
            p.played_cards = {}

        gs.reset_round_state()
        if gs.get_winner():
            gs.winner = gs.get_winner()

        return gs, narration

    sr_mod.simulate_round = odd_only_round

def _revert_C():
    import simulate_round as sr_mod
    importlib.reload(sr_mod)

PATCHES["C: Spectator every OTHER round"] = (_patch_C, _revert_C)

# ─── Iteration D: Talent Nerfs ──────────────────────────────────────────────────

def _patch_D():
    import simulate_round as sr_mod

    orig_pre = sr_mod.apply_talents_pre_roll

    def nerfed_pre(gs, player, ai):
        if not player.talent or player.talent_used_this_round:
            return
        name = player.talent["name"]
        if name == "The Showman":
            if getattr(player, "_showman_used", False):
                return
            player._showman_used = True
            player.talent_used_this_round = True
        elif name == "The Sprinter":
            if getattr(player, "_sprinter_used", False):
                return
            player._sprinter_used = True
            player.talent_used_this_round = True
        else:
            orig_pre(gs, player, ai)

    sr_mod.apply_talents_pre_roll = nerfed_pre

def _revert_D():
    import simulate_round as sr_mod
    importlib.reload(sr_mod)

PATCHES["D: Talent Nerfs (Showman/Sprinter once/game)"] = (_patch_D, _revert_D)

# ─── Iteration E: Ring Power Buffs ─────────────────────────────────────────────

def _patch_E():
    import simulate_round as sr_mod
    orig = sr_mod.award_fp
    def buffed_award_fp(player, num_rings_won, gs, spectator_active):
        base_fp = {1: 2, 2: 4, 3: 8}  # buffed from {1:1, 2:3, 3:6}
        fp = base_fp.get(num_rings_won, 0)
        if spectator_active:
            fp *= 2
        if player.talent and player.talent["name"] == "The Showman":
            fp *= 2
        player.fp += fp
        if player.starstruck_active and num_rings_won > 0:
            player.fp += 2
            player.starstruck_active = False
        if gs.jittery_hamster_winner == player.id:
            player.fp += 1
    sr_mod.award_fp = buffed_award_fp

def _revert_E():
    import simulate_round as sr_mod
    importlib.reload(sr_mod)

PATCHES["E: Ring Power Buffs (2/4/8 FP)"] = (_patch_E, _revert_E)

# ─── Iteration F: Tamer Spectator Cards ────────────────────────────────────────

TAMED_SPECTATORS = [
    {"id": 1,  "emoji": "🎉", "name": "The Roaring Crowd",
     "desc": "Double all FP this round (1→2, 3→6, 6→12)"},
    {"id": 2,  "emoji": "😱", "name": "The Jittery Hamster",
     "desc": "Highest single die at Red Ring wins +1 FP"},
    {"id": 3,  "emoji": "🎭", "name": "The Dramatic Ref",
     "desc": "Player with most cards reveals a Stunt Double swap with opponent"},
    {"id": 4,  "emoji": "🌟", "name": "The Starstruck Fan",
     "desc": "Choose player → draws 3 cards, next win = +2 FP bonus"},
    {"id": 13, "emoji": "🤝", "name": "The Friendly Wager",
     "desc": "Winner of lowest-scoring Ring draws 1 card from each opponent"},
    {"id": 6,  "emoji": "🔥", "name": "The Underdog Cheer",
     "desc": "Fewest FP player rolls 5 dice (max 2/Ring still applies)"},
    {"id": 14, "emoji": "👏", "name": "The Audience Gift",
     "desc": "All players draw 1 card from the deck"},
    {"id": 15, "emoji": "🎭", "name": "The Grand Stand",
     "desc": "Player with fewest Trophies draws 2 cards"},
    {"id": 9,  "emoji": "👑", "name": "The Champion's Welcome",
     "desc": "Most Trophies draws 2 cards"},
    {"id": 16, "emoji": "💨", "name": "The Momentum Shift",
     "desc": "All players who are behind in FP draw 1 extra card"},
    {"id": 11, "emoji": "🤝", "name": "The Peace Offering",
     "desc": "All players reveal Stunt Doubles, those who do draw 1 card"},
    {"id": 12, "emoji": "🌈", "name": "The Rainbow Ring",
     "desc": "Choose a Ring: all cards = 10, dice normal"},
]

def _patch_F():
    import game_state as gs_mod
    import simulate_round as sr_mod

    gs_mod.SPECTATOR_CARDS = TAMED_SPECTATORS

    orig_resolve = sr_mod.resolve_spectator_card

    def tamed_resolve(gs, card, starting_player_idx):
        cid = card["id"]
        if cid == 13:
            narration = f"  🎭 SPECTATOR: 🤝 The Friendly Wager\n"
            gs.chaos_round = False; gs.rainbow_ring = None
            gs.jittery_hamster_winner = None; gs.starstruck_target = None
            gs.underdog_player = None
            narration += "  → (gentle) No mechanical effect this round.\n"
            return narration
        elif cid == 14:
            narration = f"  🎭 SPECTATOR: 👏 The Audience Gift\n"
            gs.chaos_round = False; gs.rainbow_ring = None
            gs.jittery_hamster_winner = None; gs.starstruck_target = None
            gs.underdog_player = None
            for p in gs.players:
                drawn = gs.deck.draw(1)
                if drawn:
                    p.hand.extend(drawn)
            narration += "  → All players draw 1 card.\n"
            return narration
        elif cid == 15:
            narration = f"  🎭 SPECTATOR: 🎭 The Grand Stand\n"
            gs.chaos_round = False; gs.rainbow_ring = None
            gs.jittery_hamster_winner = None; gs.starstruck_target = None
            gs.underdog_player = None
            fewest = min(gs.players, key=lambda p: len(p.trophies))
            drawn = gs.deck.draw(2)
            fewest.hand.extend(drawn)
            narration += f"  → {fewest} (fewest Trophies) draws 2 cards.\n"
            return narration
        elif cid == 16:
            narration = f"  🎭 SPECTATOR: 💨 The Momentum Shift\n"
            gs.chaos_round = False; gs.rainbow_ring = None
            gs.jittery_hamster_winner = None; gs.starstruck_target = None
            gs.underdog_player = None
            max_fp = max(p.fp for p in gs.players)
            for p in gs.players:
                if p.fp < max_fp:
                    drawn = gs.deck.draw(1)
                    p.hand.extend(drawn)
            narration += "  → Behind players draw 1 card.\n"
            return narration
        return orig_resolve(gs, card, starting_player_idx)

    sr_mod.resolve_spectator_card = tamed_resolve

def _revert_F():
    importlib.reload(sys.modules["game_state"])
    importlib.reload(sys.modules["simulate_round"])

PATCHES["F: Tamer Spectators (remove 4 chaotic)"] = (_patch_F, _revert_F)

# ─── Iteration G: Progressive Victory ─────────────────────────────────────────

def _patch_G():
    import simulate_round as sr_mod

    orig_round = sr_mod.simulate_round

    def progressive_round(gs, audit_data=None):
        # Check if anyone already triggered final round
        if not getattr(gs, "final_round_triggered", False):
            for p in gs.players:
                if p.fp >= 15:
                    gs.final_round_triggered = True
                    break

        if getattr(gs, "final_round_triggered", False) and gs.winner is None:
            # ── Final Round mode ─────────────────────────────────────────
            narration = f"\n{'='*60}\n"
            narration += f"  ⚡ FINAL ROUND — Remaining rings score DOUBLE!\n"
            narration += f"{'='*60}\n"
            gs.round_number += 1

            gs.chaos_round = False; gs.rainbow_ring = None
            gs.jittery_hamster_winner = None; gs.starstruck_target = None
            gs.underdog_player = None
            if audit_data:
                audit_data["spectator_impact_this_round"] = False

            import random as rnd
            for p in gs.players:
                p.dice = [rnd.randint(1, 6) for _ in range(4)]

            from ai_player import AIPlayer
            ais = {p.id: AIPlayer(p, len(gs.players)) for p in gs.players}

            for p in gs.players:
                ais[p.id].assign_dice(gs)
                ais[p.id].play_cards(gs)

            narration += "  ✨ REVEAL (Final Round)!\n"
            for p in gs.players:
                for ring_color, card in p.played_cards.items():
                    narration += f"    {p} @ {ring_color}: {card}\n"

            sr_mod.resolve_stunt_doubles(gs)
            ring_winners = sr_mod.claim_rings(gs)

            rings_per_player: Dict[int, int] = {p.id: 0 for p in gs.players}
            for ring_color, winner in ring_winners.items():
                if winner:
                    rings_per_player[winner.id] += 1

            for player_id, num_rings in rings_per_player.items():
                player = gs.get_player_by_id(player_id)
                if player and num_rings > 0:
                    base_fp = {1: 2, 2: 6, 3: 12}  # double in final round
                    fp = base_fp.get(num_rings, 0)
                    if player.talent and player.talent["name"] == "The Showman":
                        fp *= 2
                    player.fp += fp
                    if num_rings == 3:
                        if audit_data:
                            audit_data["sweep_rounds"] += 1

            for p in gs.players:
                ais[p.id].draft_from_stunt_pool(gs)

            winner = gs.get_winner()
            if winner:
                gs.winner = winner
                narration += f"\n  🏆 FINAL WINNER: {winner} with {winner.fp} FP!\n"

            for p in gs.players:
                p.assigned_dice = {}; p.played_cards = {}

            gs.reset_round_state()
            if gs.get_winner():
                gs.winner = gs.get_winner()

            return gs, narration

        return orig_round(gs, audit_data)

    sr_mod.simulate_round = progressive_round

def _revert_G():
    import simulate_round as sr_mod
    importlib.reload(sr_mod)

PATCHES["G: Progressive Victory (Final Round at 15)"] = (_patch_G, _revert_G)


# ─── Run all iterations ─────────────────────────────────────────────────────────

def apply_and_run(name: str, num_games: int = 250) -> Dict:
    """Apply patch, run audit, revert. Returns audit dict."""
    apply_fn, revert_fn = PATCHES[name]
    try:
        apply_fn()
        audit = run_audit(num_games)
    finally:
        try:
            revert_fn()
        except Exception:
            pass
        # Clean state: reset config + full module reload for clean next run
        _reset_to_baseline()
    return audit


def _reset_to_baseline():
    """Reset everything to v1.1 baseline state."""
    # Reset fp_to_win
    cfg = json.load(open("config.json"))
    if cfg.get("fp_to_win") != 15:
        cfg["fp_to_win"] = 15
        json.dump(cfg, open("config.json", "w"), indent=2)
    # Full module reload
    for mod_name in list(sys.modules.keys()):
        if any(m in mod_name for m in ("championship", "simulate_game", "simulate_round",
                                         "game_state", "cards", "ai_player", "fun_audit")):
            try:
                del sys.modules[mod_name]
            except KeyError:
                pass


def main():
    print("=" * 70)
    print("  CHAMPIONSHIP ARENA — ITERATION DRIVER v1.2")
    print("  Testing 7 rule-change hypotheses + combinations")
    print("=" * 70)

    # ── Baseline ──────────────────────────────────────────────────────────────
    print("\n  ▶ BASELINE (v1.1, no changes)...")
    _reset_to_baseline()
    baseline = run_audit(250)
    print(f"  Baseline GPA: {baseline['gpa']:.2f} {baseline['letter']}")
    for n, d in baseline["dimensions"].items():
        print(f"    {n}: {d['letter']} ({d['value']:.1f})")

    # ── Individual iterations ───────────────────────────────────────────────
    results = {}
    for name in PATCHES:
        # Skip combos (those are separate keys)
        if ":" not in name or name.startswith("combo"):
            continue
        print(f"\n{'─'*60}")
        print(f"  ▶ {name}")
        try:
            audit = apply_and_run(name, 250)
            results[name] = audit
            print(f"  → GPA: {audit['gpa']:.2f} {audit['letter']}")
            for n, d in audit["dimensions"].items():
                delta = d["grade"] - baseline["dimensions"][n]["grade"]
                sign = "+" if delta > 0 else ""
                print(f"    {n}: {d['letter']} ({d['value']:.1f}) {sign}{delta:.1f}")
        except Exception as e:
            print(f"  ❌ FAILED: {e}")
            import traceback
            traceback.print_exc()
            results[name] = None

    # ── Combinations ────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("  COMBINATION TESTS")

    combos = {
        "Combo AC (FP25 + SpecOdd)":     ("A: FP target 25", "C: Spectator every OTHER round"),
        "Combo AD (FP25 + TalentNerf)":  ("A: FP target 25", "D: Talent Nerfs (Showman/Sprinter once/game)"),
        "Combo AE (FP25 + RingBuff)":    ("A: FP target 25", "E: Ring Power Buffs (2/4/8 FP)"),
        "Combo CE (SpecOdd + RingBuff)": ("C: Spectator every OTHER round", "E: Ring Power Buffs (2/4/8 FP)"),
        "Combo ACF (FP25 + SpecOdd + TamerSpect)": (
            "A: FP target 25", "C: Spectator every OTHER round", "F: Tamer Spectators (remove 4 chaotic)"),
        "Combo ADE (FP25 + TalentNerf + RingBuff)": (
            "A: FP target 25", "D: Talent Nerfs (Showman/Sprinter once/game)", "E: Ring Power Buffs (2/4/8 FP)"),
    }

    combo_results = {}
    for combo_name, patch_names in combos.items():
        print(f"\n  ▶ {combo_name}")
        try:
            for pn in patch_names:
                PATCHES[pn][0]()  # apply
            audit = run_audit(250)
            combo_results[combo_name] = audit
            print(f"  → GPA: {audit['gpa']:.2f} {audit['letter']}")
            for n, d in audit["dimensions"].items():
                delta = d["grade"] - baseline["dimensions"][n]["grade"]
                sign = "+" if delta > 0 else ""
                print(f"    {n}: {d['letter']} ({d['value']:.1f}) {sign}{delta:.1f}")
        except Exception as e:
            print(f"  ❌ FAILED: {e}")
            combo_results[combo_name] = None
        finally:
            for pn in reversed(patch_names):
                try:
                    PATCHES[pn][1]()  # revert
                except Exception:
                    pass
            _reset_to_baseline()

    # ── Summary table ───────────────────────────────────────────────────────
    all_results = {**results, **{n: r for n, r in combo_results.items() if r}}

    print("\n" + "=" * 70)
    print("  SUMMARY TABLE")
    print("=" * 70)
    hdr = f"  {'Iteration':<55} {'GPA':>5} {'Pace':>5} {'Score':>5} {'CmBk':>5} {'Swp':>4} {'Spec':>4} {'Tal':>4} {'Bal':>4}"
    print(hdr)
    print(f"  {'─'*55} {'─'*5} {'─'*5} {'─'*5} {'─'*5} {'─'*4} {'─'*4} {'─'*4} {'─'*4}")

    def row(name, audit):
        if not audit:
            return f"  {name:<55} FAILED"
        return (f"  {name:<55} {audit['gpa']:>5.2f} "
                f"{fmt_d(audit,'Pacing'):>5} {fmt_d(audit,'Mean Score'):>5} "
                f"{fmt_d(audit,'Comeback Rate'):>5} {fmt_d(audit,'Sweep Rate'):>4} "
                f"{fmt_d(audit,'Spectator Impact'):>4} {fmt_d(audit,'Talent Usage'):>4} "
                f"{fmt_d(audit,'Balance'):>4}")

    print(row("BASELINE (v1.1)", baseline))
    for name in results:
        print(row(name, results[name]))
    print("  Combinations:")
    for name in combo_results:
        print(row(name, combo_results[name]))

    # ── Best performer ──────────────────────────────────────────────────────
    best_name = max(all_results, key=lambda n: all_results[n]["gpa"])
    best = all_results[best_name]

    print
    print(f"  ★ BEST PERFORMER: {best_name}")
    print(f"    GPA: {best['gpa']:.2f} ({best['letter']})  "
          f"baseline was {baseline['gpa']:.2f}, Δ = {best['gpa'] - baseline['gpa']:+.2f}")
    for dim_name, d in best["dimensions"].items():
        delta = d["grade"] - baseline["dimensions"][dim_name]["grade"]
        sign = "+" if delta > 0 else ""
        print(f"    {dim_name}: {d['letter']} ({d['value']:.1f}) {sign}{delta:.1f} vs baseline")

    # ── Write ITERATION-RESULTS.md ──────────────────────────────────────────
    md = []
    md.append("# Championship Arena v1.2 — Iteration Results\n")
    md.append("**Date:** 2026-03-27\n")
    md.append("**Games per test:** 250 × 3 player counts = 750 total\n\n")

    md.append("## Summary\n\n")
    md.append("| Iteration | GPA | Pacing | Mean Score | Comeback | Sweep | Spectator | Talent | Balance |\n")
    md.append("|-----------|-----|--------|------------|----------|-------|-----------|--------|--------|\n")
    md.append(row("BASELINE (v1.1)", baseline).strip() + "|\n")
    for name in results:
        md.append(row(name, results[name]).strip() + "|\n")
    md.append("\n### Combinations\n\n")
    for name in combo_results:
        md.append(row(name, combo_results[name]).strip() + "|\n")

    md.append(f"\n## ★ Best Performer: {best_name}\n")
    md.append(f"**GPA: {best['gpa']:.2f}**  "
              f"*(baseline {baseline['gpa']:.2f}, Δ = {best['gpa'] - baseline['gpa']:+.2f})*\n\n")
    md.append("| Dimension | Value | Grade | Δ vs Baseline |\n")
    md.append("|-----------|-------|-------|---------------|\n")
    for dim_name, d in best["dimensions"].items():
        delta = d["grade"] - baseline["dimensions"][dim_name]["grade"]
        sign = "+" if delta > 0 else ""
        md.append(f"| {dim_name} | {d['value']:.1f} | {d['letter']} | {sign}{delta:.1f} |\n")

    md.append("\n## Per-Player-Count Breakdown (Best)\n\n")
    for np, r in sorted(best["results_by_players"].items()):
        md.append(f"### {np}-Player\n")
        md.append(f"- Avg rounds: {r['avg_rounds']:.1f}\n")
        md.append(f"- Avg final FP: {r['avg_fp']:.1f}\n")
        md.append(f"- Win rates: {dict(sorted(r['win_rates'].items()))}\n")
        md.append(f"- Comeback rate: {r['comeback_rate']:.1f}%\n")
        md.append(f"- Sweep rate: {r['sweep_rate']:.1f}%\n")
        md.append(f"- Spectator impact: {r['spectator_rate']:.1f}%\n")
        md.append(f"- Talent decisive: {r['talent_rate']:.1f}%\n")
        md.append(f"- Win rate spread: {r['win_spread']:.1f}%\n\n")

    change_descriptions = {
        "A: FP target 25": ("Change fp_to_win from 15 → 25. Hypothesis: games end too fast (5.1 rounds)."),
        "B: Harder Sweeps (sweep=4 FP)": ("Reduce sweep reward from 6 → 4 FP. Hypothesis: 57% sweep rate too high."),
        "C: Spectator every OTHER round": ("Draw spectator card only on odd-numbered rounds. Hypothesis: 98.5% spectator impact too high."),
        "D: Talent Nerfs (Showman/Sprinter once/game)": ("Showman and Sprinter once-per-game instead of per-round. Hypothesis: 93.7% talent decisive crowding out base mechanics."),
        "E: Ring Power Buffs (2/4/8 FP)": ("Increase base ring rewards 1→2, 2→3→4, 3→6→8. Hypothesis: base rings under-rewarded vs talents/spectators."),
        "F: Tamer Spectators (remove 4 chaotic)": ("Remove Chaos Round, Wild Card Toss, Jeering Rival, Card Shark. Hypothesis: too much spectator chaos."),
        "G: Progressive Victory (Final Round at 15)": ("First to 15 FP triggers a Final Round with doubled scoring. Hypothesis: games ending at 15 feel abrupt."),
    }

    md.append("## Iteration Details\n\n")
    for name in results:
        r = results[name]
        if not r:
            continue
        desc = change_descriptions.get(name, "")
        md.append(f"### {name}\n")
        md.append(f"{desc}\n")
        md.append(f"**GPA: {r['gpa']:.2f}** — Overall {r['letter']}\n\n")
        md.append("| Dimension | Value | Grade | Δ Baseline |\n")
        md.append("|-----------|-------|-------|------------|\n")
        for dim_name, d in r["dimensions"].items():
            delta = d["grade"] - baseline["dimensions"][dim_name]["grade"]
            sign = "+" if delta > 0 else ""
            md.append(f"| {dim_name} | {d['value']:.1f} | {d['letter']} | {sign}{delta:.1f} |\n")
        md.append("\n")

    md_text = "\n".join(md)

    output_dir = os.path.dirname(os.path.abspath(__file__))
    results_path = os.path.join(output_dir, "ITERATION-RESULTS.md")
    with open(results_path, "w") as f:
        f.write(md_text)
    print(f"\n  💾 Results → {results_path}")

    # Print summary
    print("\n" + md_text)


if __name__ == "__main__":
    main()
