import argparse
import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple


CONFIG_PATH = Path(__file__).with_name("monster_mixer_config.json")


@dataclass(frozen=True)
class Card:
    suit: str
    rank: int

    def __str__(self) -> str:
        return f"{self.suit[0]}{self.rank}"


class Deck:
    def __init__(self, cards: List[Card], rng: random.Random) -> None:
        self._cards = cards[:]
        rng.shuffle(self._cards)

    @classmethod
    def from_config(cls, config: Dict, rng: random.Random) -> "Deck":
        suits = config["suits"]
        ranks_cfg = config["ranks"]
        cards: List[Card] = []
        for suit in suits:
            for rank in range(ranks_cfg["min"], ranks_cfg["dup_low_max_rank"] + 1):
                for _ in range(ranks_cfg["dup_low"]):
                    cards.append(Card(suit=suit, rank=rank))
            for rank in range(ranks_cfg["dup_mid_min_rank"], ranks_cfg["dup_mid_max_rank"] + 1):
                for _ in range(ranks_cfg["dup_mid"]):
                    cards.append(Card(suit=suit, rank=rank))
            for _ in range(ranks_cfg["dup_high"]):
                cards.append(Card(suit=suit, rank=ranks_cfg["max"]))
        for extra in config.get("extra_high_cards", []):
            cards.append(Card(suit=extra["suit"], rank=extra["rank"]))
        return cls(cards, rng)

    def draw(self) -> Optional[Card]:
        if not self._cards:
            return None
        return self._cards.pop()

    def draw_many(self, n: int) -> List[Card]:
        drawn = []
        for _ in range(n):
            card = self.draw()
            if card is None:
                break
            drawn.append(card)
        return drawn

    def remaining(self) -> int:
        return len(self._cards)


class Lineup:
    def __init__(self) -> None:
        self.cards: List[Card] = []

    def trailing_run_length(self, suit: str) -> int:
        length = 0
        for card in reversed(self.cards):
            if card.suit != suit:
                break
            length += 1
        return length

    def leading_run_length(self, suit: str) -> int:
        length = 0
        for card in self.cards:
            if card.suit != suit:
                break
            length += 1
        return length

    def run_at_position(self, card: Card, position: int) -> int:
        """Return run length card would belong to if inserted at `position`.
        position 0 = left end, position = len(cards) = right end.
        """
        left_count = 0
        for i in range(position - 1, -1, -1):
            if self.cards[i].suit == card.suit:
                left_count += 1
            else:
                break
        right_count = 0
        for i in range(position, len(self.cards)):
            if self.cards[i].suit == card.suit:
                right_count += 1
            else:
                break
        return left_count + 1 + right_count

    def place(self, card: Card, scoring: Dict[str, int], position: str = "right") -> Tuple[int, bool, int]:
        if position == "right":
            run_len_before = self.trailing_run_length(card.suit)
            run_len_after = run_len_before + 1
            self.cards.append(card)
            remove_index = -1
        elif position == "left":
            run_len_before = self.leading_run_length(card.suit)
            run_len_after = run_len_before + 1
            self.cards.insert(0, card)
            remove_index = 0
        else:
            raise ValueError("Position must be 'left' or 'right'.")

        if run_len_after == 1:
            return scoring["isolated"], False, run_len_after
        if run_len_after == 2:
            return scoring["run2"], False, run_len_after
        if run_len_after == 3:
            score = scoring["run3"] + scoring["bouncer_penalty"]
            self.cards.pop(remove_index)
            return score, True, run_len_after

        raise ValueError("Run length exceeded 3, which should be impossible.")

    def place_anywhere(self, card: Card, scoring: Dict[str, int], position: int) -> Tuple[int, bool, int]:
        """Insert card at arbitrary position. Returns (score_delta, bouncer, run_len_after)."""
        run_len_after = self.run_at_position(card, position)
        self.cards.insert(position, card)
        if run_len_after == 1:
            return scoring["isolated"], False, run_len_after
        if run_len_after == 2:
            return scoring["run2"], False, run_len_after
        if run_len_after == 3:
            score = scoring["run3"] + scoring["bouncer_penalty"]
            self.cards.pop(position)
            return score, True, run_len_after
        raise ValueError("Run length exceeded 3")


@dataclass
class Player:
    player_id: int
    hand: List[Card]
    score: int = 0
    cards_played: int = 0


class MonsterMixerGame:
    def __init__(self, num_players: int, seed: int, config: Dict) -> None:
        if num_players < 2 or num_players > 5:
            raise ValueError("Player count must be between 2 and 5.")
        self.num_players = num_players
        self.config = config
        self.rng = random.Random(seed)
        self.deck = Deck.from_config(config, self.rng)
        self.lineup = Lineup()
        self.players = [Player(player_id=i, hand=[]) for i in range(num_players)]
        self.log: List[str] = []
        self.bouncer_cap_per_round = config.get("bouncer_cap_per_round", 0)
        self.player_bouncer_counts: List[int] = [0] * num_players
        self.metrics = {
            "isolated": 0,
            "forced_isolated": 0,
            "run2": 0,
            "run3": 0,
            "bouncer": 0,
            "turns": 0,
            "scores": [],
        }

    def deal(self, hand_size: int) -> None:
        for player in self.players:
            player.hand = self.deck.draw_many(hand_size)

    def ai_choose_card(self, player: Player) -> Tuple[Card, int]:
        scoring = self.config["scoring"]
        ai = self.config["ai_heuristics"]
        cap = self.bouncer_cap_per_round
        used = self.player_bouncer_counts[player.player_id]
        at_cap = cap > 0 and used >= cap
        best_score = float("-inf")
        best_choices: List[Tuple[Card, int]] = []
        placement_opts = self.config.get("placement_options", ["right"])
        for card in player.hand:
            if "anywhere" in placement_opts:
                positions = list(range(len(self.lineup.cards) + 1))
            elif "right" in placement_opts and "left" in placement_opts:
                positions = ["right", "left"]
            elif "right" in placement_opts:
                positions = ["right"]
            else:
                positions = ["left"]
            for position in positions:
                if isinstance(position, int):
                    run_after = self.lineup.run_at_position(card, position)
                elif position == "right":
                    run_after = self.lineup.trailing_run_length(card.suit) + 1
                elif position == "left":
                    run_after = self.lineup.leading_run_length(card.suit) + 1
                else:
                    continue
                if run_after == 1:
                    base = scoring["isolated"]
                    bias = ai["isolated_bonus"]
                elif run_after == 2:
                    base = scoring["run2"]
                    bias = ai["run2_bonus"]
                elif run_after == 3:
                    if at_cap:
                        continue  # skip — would exceed bouncer cap
                    base = scoring["run3"] + scoring["bouncer_penalty"]
                    bias = -ai["run3_penalty"]
                else:
                    continue
                value = base + bias
                if value > best_score:
                    best_score = value
                    best_choices = [(card, position)]
                elif value == best_score:
                    best_choices.append((card, position))
        # If all options were skipped due to cap, fall back to best non-run3
        if not best_choices:
            for card in player.hand:
                if "anywhere" in placement_opts:
                    positions = list(range(len(self.lineup.cards) + 1))
                elif "right" in placement_opts:
                    positions = ["right"]
                else:
                    positions = ["left"]
                for position in positions:
                    if isinstance(position, int):
                        run_after = self.lineup.run_at_position(card, position)
                    else:
                        run_after = self.lineup.trailing_run_length(card.suit) + 1
                    if run_after == 3 and at_cap:
                        continue
                    if run_after == 1:
                        base = scoring["isolated"]
                        bias = ai["isolated_bonus"]
                    elif run_after == 2:
                        base = scoring["run2"]
                        bias = ai["run2_bonus"]
                    elif run_after == 3:
                        base = scoring["run3"] + scoring["bouncer_penalty"]
                        bias = -ai["run3_penalty"]
                    else:
                        continue
                    value = base + bias
                    if value > best_score:
                        best_score = value
                        best_choices = [(card, position)]
                    elif value == best_score:
                        best_choices.append((card, position))
        return self.rng.choice(best_choices)

    def play_turn(self, player: Player) -> None:
        hand_before = player.hand[:]
        placement_opts = self.config.get("placement_options", ["right"])
        run_opportunity = {}
        for candidate in hand_before:
            best_run = 0
            if "anywhere" in placement_opts:
                for pos in range(len(self.lineup.cards) + 1):
                    run = self.lineup.run_at_position(candidate, pos)
                    best_run = max(best_run, run)
            elif "right" in placement_opts and "left" in placement_opts:
                best_run = max(
                    self.lineup.trailing_run_length(candidate.suit),
                    self.lineup.leading_run_length(candidate.suit)
                )
            elif "right" in placement_opts:
                best_run = self.lineup.trailing_run_length(candidate.suit)
            else:
                best_run = self.lineup.leading_run_length(candidate.suit)
            run_opportunity[candidate] = best_run
        card, position = self.ai_choose_card(player)
        player.hand.remove(card)
        if isinstance(position, int):
            score_delta, bouncer, run_len_after = self.lineup.place_anywhere(card, self.config["scoring"], position)
        else:
            score_delta, bouncer, run_len_after = self.lineup.place(card, self.config["scoring"], position)
        player.score += score_delta
        player.cards_played += 1
        self.metrics["turns"] += 1
        if run_len_after == 1:
            self.metrics["isolated"] += 1
            had_match = any(run_opportunity[candidate] >= 1 for candidate in hand_before)
            if not had_match:
                self.metrics["forced_isolated"] += 1
        elif run_len_after == 2:
            self.metrics["run2"] += 1
        elif run_len_after == 3:
            self.metrics["run3"] += 1
        if bouncer:
            self.metrics["bouncer"] += 1
            self.player_bouncer_counts[player.player_id] += 1

    def play_round(self, starting_index: int) -> None:
        self.player_bouncer_counts = [0] * self.num_players
        players_in_order = self.players[starting_index:] + self.players[:starting_index]
        while any(player.hand for player in self.players):
            for player in players_in_order:
                if player.hand:
                    self.play_turn(player)

    def play_game(self) -> Dict:
        if self.num_players == 2:
            self.deal(self.config["hand_size_2p"])
            start = self.rng.randrange(self.num_players)
            self.play_round(start)
        else:
            self.deal(self.config["hand_size"])
            while True:
                start = self.rng.randrange(self.num_players)
                self.play_round(start)
                if self.deck.remaining() >= self.config["hand_size"] * self.num_players:
                    self.deal(self.config["hand_size"])
                else:
                    break
        self.metrics["scores"] = [player.score for player in self.players]
        return {
            "scores": [player.score for player in self.players],
            "cards_played": [player.cards_played for player in self.players],
            "metrics": self.metrics,
        }


def load_config(path: Path) -> Dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def simulate_games(num_players: int, games: int, seed: int, config: Dict) -> Dict:
    rng = random.Random(seed)
    all_scores: List[List[int]] = []
    all_metrics = {
        "isolated": 0,
        "forced_isolated": 0,
        "run2": 0,
        "run3": 0,
        "bouncer": 0,
        "turns": 0,
    }
    win_counts = [0 for _ in range(num_players)]
    score_spreads: List[int] = []
    for _ in range(games):
        game_seed = rng.randrange(1_000_000_000)
        game = MonsterMixerGame(num_players, game_seed, config)
        result = game.play_game()
        scores = result["scores"]
        all_scores.append(scores)
        max_score = max(scores)
        winners = [i for i, s in enumerate(scores) if s == max_score]
        for w in winners:
            win_counts[w] += 1 / len(winners)
        score_spreads.append(max_score - min(scores))
        metrics = result["metrics"]
        for key in all_metrics:
            all_metrics[key] += metrics[key]
    return {
        "scores": all_scores,
        "wins": win_counts,
        "metrics": all_metrics,
        "score_spreads": score_spreads,
    }


def summarize_simulation(sim: Dict, games: int, num_players: int) -> Dict:
    scores = sim["scores"]
    totals = [0 for _ in range(num_players)]
    for game_scores in scores:
        for i, s in enumerate(game_scores):
            totals[i] += s
    avg_scores = [t / games for t in totals]
    metrics = sim["metrics"]
    turns = metrics["turns"]
    return {
        "avg_scores": avg_scores,
        "win_rates": [w / games for w in sim["wins"]],
        "avg_spread": sum(sim["score_spreads"]) / games,
        "turns": turns,
        "isolated_rate": metrics["isolated"] / turns if turns else 0,
        "forced_isolated_rate": metrics["forced_isolated"] / turns if turns else 0,
        "run2_rate": metrics["run2"] / turns if turns else 0,
        "run3_rate": metrics["run3"] / turns if turns else 0,
        "bouncer_rate": metrics["bouncer"] / turns if turns else 0,
        "avg_points_per_turn": sum(avg_scores) / (turns / num_players) if turns else 0,
    }


def run_cli() -> None:
    parser = argparse.ArgumentParser(description="Monster Mixer simulator")
    parser.add_argument("--players", type=int, default=4)
    parser.add_argument("--games", type=int, default=100)
    parser.add_argument("--seed", type=int, default=1)
    args = parser.parse_args()

    config = load_config(CONFIG_PATH)
    sim = simulate_games(args.players, args.games, args.seed, config)
    summary = summarize_simulation(sim, args.games, args.players)

    print(f"Players: {args.players}")
    print(f"Games: {args.games}")
    print(f"Avg scores: {summary['avg_scores']}")
    print(f"Win rates: {summary['win_rates']}")
    print(f"Avg spread: {summary['avg_spread']:.2f}")
    print(f"Isolated rate: {summary['isolated_rate']:.3f}")
    print(f"Forced isolated rate: {summary['forced_isolated_rate']:.3f}")
    print(f"Run2 rate: {summary['run2_rate']:.3f}")
    print(f"Run3 rate: {summary['run3_rate']:.3f}")
    print(f"Bouncer rate: {summary['bouncer_rate']:.3f}")


if __name__ == "__main__":
    run_cli()
