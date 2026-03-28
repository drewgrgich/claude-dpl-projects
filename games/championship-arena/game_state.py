"""Game state structures for Championship Arena."""

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable
from cards import HMCard, Deck


# ─── Spectator Cards ────────────────────────────────────────────────────────────

SPECTATOR_CARDS = [
    {"id": 1,  "emoji": "🎉", "name": "The Roaring Crowd",
     "desc": "Double all FP this round (1→2, 3→6, 6→12)"},
    {"id": 2,  "emoji": "😱", "name": "The Jittery Hamster",
     "desc": "Highest single die at Red Ring wins +1 FP"},
    {"id": 3,  "emoji": "🎭", "name": "The Dramatic Ref",
     "desc": "Player with most cards reveals a Stunt Double swap with opponent"},
    {"id": 4,  "emoji": "🌟", "name": "The Starstruck Fan",
     "desc": "Choose player → draws 3 cards, next win = +2 FP bonus"},
    {"id": 5,  "emoji": "🤝", "name": "The Friendly Wager",
     "desc": "Winner of lowest-scoring Ring draws 1 card from each opponent"},
    {"id": 6,  "emoji": "🔥", "name": "The Underdog Cheer",
     "desc": "Fewest FP player rolls 5 dice (max 2/Ring still applies)"},
    {"id": 7,  "emoji": "👏", "name": "The Audience Gift",
     "desc": "All players draw 1 card from the deck"},
    {"id": 8,  "emoji": "🎭", "name": "The Grand Stand",
     "desc": "Player with fewest Trophies draws 2 cards"},
    {"id": 9,  "emoji": "👑", "name": "The Champion's Welcome",
     "desc": "Most Trophies draws 2 cards"},
    {"id": 10, "emoji": "💨", "name": "The Momentum Shift",
     "desc": "All players who are behind in FP draw 1 extra card"},
    {"id": 11, "emoji": "🤝", "name": "The Peace Offering",
     "desc": "All players reveal Stunt Doubles, those who do draw 1 card"},
    {"id": 12, "emoji": "🌈", "name": "The Rainbow Ring",
     "desc": "Choose a Ring: all cards = 10, dice normal (even overrides Purple)"},
]


# ─── Talents ───────────────────────────────────────────────────────────────────

TALENTS = [
    {"id": 1, "name": "The Showman",
     "desc": "Score double FP this round. If win 0 Rings, lose 2 FP.",
     "trigger": "before_roll"},
    {"id": 2, "name": "The Time Traveler",
     "desc": "After reveal, swap one of your cards with opponent's at same Ring.",
     "trigger": "after_reveal"},
    {"id": 3, "name": "The Collector",
     "desc": "When you claim a Ring, draw +2 cards instead of standard.",
     "trigger": "passive"},
    {"id": 4, "name": "The Sprinter",
     "desc": "All your dice are +2 this round.",
     "trigger": "before_roll"},
    {"id": 5, "name": "The Analyst",
     "desc": "Look at all face-down cards at one Ring before reveal.",
     "trigger": "before_resolution"},
    {"id": 6, "name": "The Illusionist",
     "desc": "Choose one Ring to be Wild (any suit matches) this round.",
     "trigger": "before_roll"},
]


# ─── Ring ──────────────────────────────────────────────────────────────────────

@dataclass
class Ring:
    color: str
    power_type: str  # 'highest_dice' | 'most_cards' | 'extremes' | 'odd_double' | 'even_double' | 'lowest_wins'
    trophies: List[HMCard] = field(default_factory=list)

    def apply_power(self, energy_scores: Dict[str, Dict['Player', int]]) -> Dict['Player', int]:
        """Apply ring power to energy scores. Returns adjusted scores per player."""
        players = list(energy_scores.keys())
        raw_scores = {p: energy_scores[p] for p in players}

        if self.power_type == "highest_dice":
            # Red: dice only, cards ignored
            return {p: raw_scores[p] for p in players}
        elif self.power_type == "most_cards":
            # Orange: most cards wins (all cards count as 1)
            # handled separately
            return raw_scores
        elif self.power_type == "extremes":
            # Yellow: only 0s and 10s count
            return raw_scores
        elif self.power_type == "odd_double":
            # Green: odd dice doubled
            return raw_scores
        elif self.power_type == "even_double":
            # Blue: even card ranks doubled
            return raw_scores
        elif self.power_type == "lowest_wins":
            # Purple: lowest wins
            return raw_scores
        return raw_scores


# ─── Player ─────────────────────────────────────────────────────────────────────

@dataclass
class Player:
    id: int
    hand: List[HMCard] = field(default_factory=list)
    dice: List[int] = field(default_factory=list)  # rolled values
    assigned_dice: Dict[str, List[int]] = field(default_factory=dict)  # ring → dice
    played_cards: Dict[str, HMCard] = field(default_factory=dict)  # ring → card
    stunt_double: Optional[HMCard] = None  # hidden stunt double
    talent: Optional[dict] = None
    trophies: List[HMCard] = field(default_factory=list)
    fp: int = 0
    score: int = 0  # total FP accumulated
    # Bonus tracking for spectator effects
    starstruck_bonus_fp: int = 0  # accumulated +2 FP bonus from Starstruck Fan
    starstruck_active: bool = False  # next win gets +2 FP bonus
    talent_used_this_round: bool = False

    def num_cards_in_play(self) -> int:
        """Total cards in hand + trophies."""
        return len(self.hand) + len(self.trophies)

    def __repr__(self):
        return f"P{self.id}"


# ─── Spectator Deck ─────────────────────────────────────────────────────────────

@dataclass
class SpectatorDeck:
    cards: List[dict] = field(default_factory=list)
    discard: List[dict] = field(default_factory=list)

    def reset(self):
        self.cards = list(SPECTATOR_CARDS)
        self.shuffle()
        self.discard = []

    def shuffle(self):
        random.shuffle(self.cards)

    def draw(self) -> Optional[dict]:
        if not self.cards:
            if not self.discard:
                return None
            self.cards = self.discard
            self.discard = []
            self.shuffle()
        return self.cards.pop(0)

    def discard_card(self, card: dict):
        self.discard.append(card)


# ─── Game State ────────────────────────────────────────────────────────────────

@dataclass
class GameState:
    deck: Deck
    spectator_deck: SpectatorDeck
    stunt_pool: List[HMCard] = field(default_factory=list)
    active_rings: List[Ring] = field(default_factory=list)
    players: List[Player] = field(default_factory=list)
    round_number: int = 0
    winner: Optional[Player] = None
    # Track for Jeering Rival (player who lost last round)
    last_round_loser: Optional[Player] = None
    # Current round's spectator card
    current_spectator: Optional[dict] = None
    # Chaos round flag
    chaos_round: bool = False
    # Rainbow ring choice
    rainbow_ring: Optional[str] = None
    # Jittery Hamster bonus (player_id → bool)
    jittery_hamster_winner: Optional[int] = None
    # Starstruck Fan target
    starstruck_target: Optional[int] = None
    # Underdog (player with 5 dice)
    underdog_player: Optional[int] = None

    def get_ring_by_color(self, color: str) -> Optional[Ring]:
        for r in self.active_rings:
            if r.color == color:
                return r
        return None

    def get_player_by_id(self, pid: int) -> Optional[Player]:
        for p in self.players:
            if p.id == pid:
                return p
        return None

    def get_winner(self) -> Optional[Player]:
        for p in self.players:
            if p.fp >= 15:
                return p
        return None

    def is_game_over(self) -> bool:
        return self.get_winner() is not None

    def pick_active_rings(self, num_rings: int = 3):
        """Randomly pick active rings for this round."""
        all_colors = ["Red", "Orange", "Yellow", "Green", "Blue", "Purple"]
        chosen = random.sample(all_colors, num_rings)
        power_map = {
            "Red": "highest_dice",
            "Orange": "most_cards",
            "Yellow": "extremes",
            "Green": "odd_double",
            "Blue": "even_double",
            "Purple": "lowest_wins",
        }
        self.active_rings = [Ring(color=c, power_type=power_map[c]) for c in chosen]

    def fill_stunt_pool(self, target: int = 6):
        """Draw cards from deck to fill stunt pool to target size."""
        while len(self.stunt_pool) < target and not self.deck.is_empty():
            drawn = self.deck.draw()
            self.stunt_pool.extend(drawn)

    def remove_stunt_pool_card(self, rank: int) -> Optional[HMCard]:
        """Remove and return a stunt pool card matching the given rank."""
        for i, card in enumerate(self.stunt_pool):
            if card.rank == rank:
                return self.stunt_pool.pop(i)
        return None

    def add_trophy_to_ring(self, ring_color: str, card: HMCard):
        ring = self.get_ring_by_color(ring_color)
        if ring:
            ring.trophies.append(card)

    def all_players_acted(self) -> bool:
        """Check if all players have assigned dice and played cards."""
        for p in self.players:
            if len(p.assigned_dice) == 0 and len(p.played_cards) == 0:
                return False
        return True

    def reset_round_state(self):
        """Reset per-round state between rounds."""
        self.current_spectator = None
        self.chaos_round = False
        self.rainbow_ring = None
        self.jittery_hamster_winner = None
        self.starstruck_target = None
        self.underdog_player = None
        for p in self.players:
            p.starstruck_active = False
            p.talent_used_this_round = False
