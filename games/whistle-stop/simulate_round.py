"""
simulate_round.py — One round of Whistle Stop
"""

from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from game_state import GameState, Player, Route, STATION_POS, ROUTE_CARDS_BEFORE_STATION
from cards import HMCard


@dataclass
class RevealedCard:
    player: Player
    card: HMCard
    declared_rank: Optional[int] = None
    declared_faction: Optional[str] = None
    position_placed: int = -1


@dataclass
class RoundResult:
    round_number: int
    reveals: List[RevealedCard]
    placements: List[Tuple[int, int]]
    movements: List[Tuple[int, int, int]]  # pid, new_pos, steps_taken
    scoring: List[Tuple[int, float]]
    station_reached: bool
    station_placer: Optional[int] = None
    passed_by_player: Dict[int, List[int]] = field(default_factory=dict)

    def __post_init__(self):
        if self.passed_by_player is None:
            self.passed_by_player = {}


def simulate_round(
    gs: GameState,
    chosen_cards: Dict[int, HMCard],
    declared_ranks: Optional[Dict[int, int]] = None,
    declared_factions: Optional[Dict[int, str]] = None,
    verbose: bool = False
) -> RoundResult:
    declared_ranks = declared_ranks or {}
    declared_factions = declared_factions or {}
    gs.round_number += 1

    # Build reveals
    reveals = []
    for pid, card in chosen_cards.items():
        player = gs.player_by_id(pid)
        reveals.append(RevealedCard(
            player=player,
            card=card,
            declared_rank=declared_ranks.get(pid),
            declared_faction=declared_factions.get(pid),
        ))

    # Sort low → high
    def eff_rank(rc: RevealedCard) -> int:
        if rc.card.is_wild and rc.card.rank == 0:
            return rc.declared_rank if rc.declared_rank is not None else 0
        return rc.card.rank

    reveals.sort(key=eff_rank)

    # Place cards (append to route end)
    placements = []
    for rc in reveals:
        pid = rc.player.player_id
        try:
            rc.player.hand.remove(rc.card)
        except ValueError:
            pass

        next_pos = gs.route.next_position()
        if next_pos <= STATION_POS:
            actual = gs.route.place_card(rc.card, position=next_pos)
            rc.position_placed = actual
            placements.append((pid, actual))

            if gs.route.is_station_reached() and not gs.station_placer_id:
                gs.station_placer_id = pid
                rc.player.placed_station = True
                if verbose:
                    print(f"  🏁 STATION REACHED! Placed by {rc.player.name} ({rc.card})")
        else:
            placements.append((pid, -1))

    # Move trains
    movements = []
    scoring_data = []

    for rc in reveals:
        pid = rc.player.player_id
        player = rc.player

        eff_rank = rc.declared_rank if rc.declared_rank is not None else rc.card.rank
        eff_faction = rc.declared_faction if rc.declared_faction else rc.card.faction

        # Faction bonus
        bonus = 0
        if eff_faction in gs.FACTION_BONUS:
            if not rc.card.is_wild:
                bonus = gs.FACTION_BONUS[eff_faction]
            elif rc.declared_faction:
                bonus = gs.FACTION_BONUS[rc.declared_faction]

        total_steps = eff_rank + bonus
        is_wild_10 = rc.card.is_wild and rc.card.rank == 10

        old_pos = player.position
        new_pos, passed = player.move_train(total_steps, gs.route)
        movements.append((pid, new_pos, total_steps))

        if verbose:
            bonus_str = f"+{bonus} bonus" if bonus else "no bonus"
            mult = " [×2]" if is_wild_10 else ""
            print(f"  {player.name} ({eff_faction} {eff_rank}): "
                  f"pos {old_pos}→{new_pos} [{total_steps} = {eff_rank}+{bonus_str}]{mult}")

        # Score
        vp = 0.0

        # Passed: 0.5 VP each (1× for Red)
        for pos in passed:
            if pos == 0:
                continue
            card_at = gs.route.get_card_at(pos)
            if card_at:
                val = 0.5
                if card_at.card.faction == "red" and not card_at.card.is_wild:
                    val *= 2.0
                vp += val

        # Landed: 0.5× rank VP (1× for Red, ×2 for Wild 10)
        landed_card = gs.route.get_card_at(new_pos)
        if landed_card and landed_card.position > 0:
            lv = float(landed_card.card.rank) * 0.5
            if landed_card.card.faction == "red" and not landed_card.card.is_wild:
                lv *= 2.0
            if is_wild_10:
                lv *= 2.0
            vp += lv
            if verbose:
                print(f"    Passed {len(passed)}: +{vp-lv:.0f} | Landed on {landed_card}: +{lv:.0f} → {vp:.0f} VP")
        elif verbose:
            print(f"    Passed {len(passed)}: +{vp:.0f}")

        player.score += vp
        scoring_data.append((pid, vp))

    # Draw back to hand_size
    gs.draw_phase()

    gs.check_endgame()

    return RoundResult(
        round_number=gs.round_number,
        reveals=reveals,
        placements=placements,
        movements=movements,
        scoring=scoring_data,
        station_reached=gs.route.is_station_reached(),
        station_placer=gs.station_placer_id,
    )
