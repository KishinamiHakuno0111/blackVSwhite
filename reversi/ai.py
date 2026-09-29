"""Bounded iterative-deepening negamax with conservative stability and exact endings.

The old strategies are retained as evaluation features, not their broken control flow.
Random playouts only help root move ordering; minimax still decides the final move.
"""

from dataclasses import dataclass
from math import isfinite
import random
from time import perf_counter
from typing import Callable

from .engine import (ALL, BOTTOM, CORNERS, DIRECTIONS, EDGES, LEFT, RIGHT, TOP,
                     Position, flipped_bits, legal_bits, neighbors, shift, squares)

WIN = 100_000
INF = 1_000_000
EXACT, LOWER, UPPER = 0, 1, 2
WEIGHTS = (
    100, -25, 12, 6, 5, 5, 6, 12, -25, 100,
    -25, -45, -2, -2, -2, -2, -2, -2, -45, -25,
    12, -2, 4, 2, 2, 2, 2, 4, -2, 12,
    6, -2, 2, 1, 1, 1, 1, 2, -2, 6,
    5, -2, 2, 1, 1, 1, 1, 2, -2, 5,
    5, -2, 2, 1, 1, 1, 1, 2, -2, 5,
    6, -2, 2, 1, 1, 1, 1, 2, -2, 6,
    12, -2, 4, 2, 2, 2, 2, 4, -2, 12,
    -25, -45, -2, -2, -2, -2, -2, -2, -45, -25,
    100, -25, 12, 6, 5, 5, 6, 12, -25, 100,
)
CORNER_AREAS = ((0, (1, 10, 11)), (9, (8, 19, 18)),
                (90, (80, 91, 81)), (99, (89, 98, 88)))


@dataclass(frozen=True, slots=True)
class SearchConfig:
    time_limit: float = 3.0
    max_depth: int = 12
    exact_empty: int = 12
    rollout_samples: int = 2
    seed: int = 2026
    table_limit: int = 120_000

    def __post_init__(self):
        if not isfinite(self.time_limit) or self.time_limit < 0:
            raise ValueError("搜索时间必须是非负有限数")
        if not 1 <= self.max_depth <= 100 or not 0 <= self.exact_empty <= 20:
            raise ValueError("搜索深度配置无效")
        if not 0 <= self.rollout_samples <= 100 or self.table_limit < 1:
            raise ValueError("搜索配置无效")


LEVELS = {
    "快速": SearchConfig(0.3, 5, 8, 0),
    "均衡": SearchConfig(1.0, 8, 10, 1),
    "深入": SearchConfig(3.0, 12, 12, 2),
}


@dataclass(frozen=True, slots=True)
class SearchResult:
    move: int | None
    score: int
    depth: int
    nodes: int
    elapsed: float
    solved: bool
    pv: tuple[int, ...] = ()
    rollouts: int = 0
    tt_hits: int = 0


@dataclass(slots=True)
class Entry:
    depth: int
    score: int
    flag: int
    move: int | None


def stable_bits(own: int) -> int:
    """Conservative, color-specific stability proof (may undercount).

    A disc is admitted only when, in each of the four axes, at least one
    side is the board edge or an already-proven stable disc of the same color.
    This propagates out of owned corners and cannot label a flippable disc stable.
    """
    stable = own & CORNERS
    boundary = TOP | BOTTOM | LEFT | RIGHT
    while True:
        secured = shift(stable, DIRECTIONS[0]) | shift(stable, DIRECTIONS[1]) | LEFT | RIGHT
        secured &= shift(stable, DIRECTIONS[2]) | shift(stable, DIRECTIONS[3]) | TOP | BOTTOM
        secured &= shift(stable, DIRECTIONS[4]) | shift(stable, DIRECTIONS[5]) | boundary
        secured &= shift(stable, DIRECTIONS[6]) | shift(stable, DIRECTIONS[7]) | boundary
        expanded = stable | (own & secured)
        if expanded == stable:
            return stable
        stable = expanded


def empty_regions(empty: int) -> tuple[int, ...]:
    """Four-connected empty regions: diagonal adjacency does not merge regions."""
    regions = []
    while empty:
        region = empty & -empty
        while True:
            adjacent = 0
            for direction in DIRECTIONS[:4]:
                adjacent |= shift(region, direction)
            expanded = region | (adjacent & empty)
            if expanded == region:
                break
            region = expanded
        regions.append(region)
        empty ^= region
    return tuple(regions)


def positional_value(own: int, other: int) -> int:
    value = sum(WEIGHTS[i] for i in squares(own)) - sum(WEIGHTS[i] for i in squares(other))
    # An occupied corner no longer needs the empty-corner C/X-square penalty.
    for corner, nearby in CORNER_AREAS:
        if (own | other) & (1 << corner):
            for move in nearby:
                adjustment = 8 - WEIGHTS[move]
                if own & (1 << move):
                    value += adjustment
                elif other & (1 << move):
                    value -= adjustment
    return value


def evaluation_features(own: int, other: int, own_moves: int | None = None) -> dict[str, int]:
    empty = ALL ^ (own | other)
    own_moves = legal_bits(own, other) if own_moves is None else own_moves
    other_moves = legal_bits(other, own)
    bordering_empty = neighbors(empty)
    parity = 0
    if empty.bit_count() <= 20:
        for region in empty_regions(empty):
            if region.bit_count() % 2:
                # Contested regions contribute symmetrically. This is a heuristic,
                # not a guarantee of who makes the final move in a region.
                parity += bool(region & own_moves) - bool(region & other_moves)
    return {
        "position": positional_value(own, other),
        "mobility": own_moves.bit_count() - other_moves.bit_count(),
        "potential": (neighbors(other) & empty).bit_count() - (neighbors(own) & empty).bit_count(),
        "corners": (own & CORNERS).bit_count() - (other & CORNERS).bit_count(),
        "stable": stable_bits(own).bit_count() - stable_bits(other).bit_count(),
        "frontier": (own & bordering_empty).bit_count() - (other & bordering_empty).bit_count(),
        "discs": own.bit_count() - other.bit_count(),
        "parity": parity,
    }


def evaluate(own: int, other: int, own_moves: int | None = None) -> int:
    features = evaluation_features(own, other, own_moves)
    empty = 100 - (own | other).bit_count()
    disc_weight = -1 if empty > 60 else 1 if empty > 20 else 8
    mobility_weight = 14 if empty > 20 else 9
    return (features["position"] * 2 + features["mobility"] * mobility_weight
            + features["potential"] * 3 + features["corners"] * 160
            + features["stable"] * 24 - features["frontier"] * 7
            + features["discs"] * disc_weight + features["parity"] * 12)


def terminal_score(own: int, other: int) -> int:
    difference = own.bit_count() - other.bit_count()
    return WIN + difference * 100 if difference > 0 else -WIN + difference * 100 if difference < 0 else 0


class SearchTimeout(Exception):
    pass


class Searcher:
    def __init__(self, config: SearchConfig = SearchConfig()):
        self.config = config
        self.table: dict[tuple[int, int], Entry] = {}
        self.history = [0] * 100
        self.nodes = 0
        self.tt_hits = 0
        self.rollouts = 0
        self.deadline = 0.0
        self.root_key: tuple[int, int] | None = None
        self.rollout_order: dict[int, int] = {}

    def _check_time(self):
        if perf_counter() >= self.deadline:
            raise SearchTimeout

    def _ordered(self, own, other, moves, tt_move=None):
        empty = ALL ^ (own | other)
        odd_regions = 0
        if empty.bit_count() <= 12:
            for region in empty_regions(empty):
                if region.bit_count() % 2:
                    odd_regions |= region
        dangerous = 0
        for corner, nearby in CORNER_AREAS:
            if empty & (1 << corner):
                dangerous |= sum(1 << move for move in nearby)

        def priority(move):
            bit = 1 << move
            score = WEIGHTS[move] + min(self.history[move], 500)
            if bit & CORNERS:
                score += 4000
            if bit & dangerous:
                score -= 200
            if bit & odd_regions:
                score += 120
            if (own, other) == self.root_key:
                score += self.rollout_order.get(move, 0)
            if move == tt_move:
                score += 1_000_000
            return score

        return sorted(squares(moves), key=priority, reverse=True)

    def _search(self, own: int, other: int, depth: int, alpha: int, beta: int) -> int:
        self.nodes += 1
        if self.nodes & 63 == 0:
            self._check_time()
        key = own, other
        entry = self.table.get(key)
        if entry and entry.depth >= depth:
            self.tt_hits += 1
            if entry.flag == EXACT:
                return entry.score
            if entry.flag == LOWER:
                alpha = max(alpha, entry.score)
            else:
                beta = min(beta, entry.score)
            if alpha >= beta:
                return entry.score
        moves = legal_bits(own, other)
        if not moves:
            if not legal_bits(other, own):
                return terminal_score(own, other)
            # A pass changes the side to move, not the number of placements remaining.
            return -self._search(other, own, depth, -beta, -alpha)
        if depth <= 0:
            return evaluate(own, other, moves)
        initial_alpha, initial_beta = alpha, beta
        best, best_move = -INF, None
        for move in self._ordered(own, other, moves, entry.move if entry else None):
            flips = flipped_bits(own, other, move)
            child_own = other ^ flips
            child_other = own | flips | (1 << move)
            score = -self._search(child_own, child_other, depth - 1, -beta, -alpha)
            if score > best:
                best, best_move = score, move
            alpha = max(alpha, score)
            if alpha >= beta:
                self.history[move] += depth * depth
                break
        flag = UPPER if best <= initial_alpha else LOWER if best >= initial_beta else EXACT
        if len(self.table) >= self.config.table_limit:
            self.table.clear()
        self.table[key] = Entry(depth, best, flag, best_move)
        return best

    def _rollout_ordering(self, own, other, moves):
        if not self.config.rollout_samples or self.config.time_limit < 0.5:
            return
        # Never spend more than 8% of the budget on random rollout ordering.
        end = min(self.deadline, perf_counter() + self.config.time_limit * 0.08)
        rng = random.Random(self.config.seed ^ own ^ other)
        totals, counts = {}, {}
        candidates = self._ordered(own, other, moves)
        for _ in range(self.config.rollout_samples):
            for move in candidates:
                if perf_counter() >= end:
                    return self._finish_rollouts(totals, counts)
                flips = flipped_bits(own, other, move)
                a, b = other ^ flips, own | flips | (1 << move)
                root_turn = False
                while True:
                    if perf_counter() >= end:
                        return self._finish_rollouts(totals, counts)
                    legal = legal_bits(a, b)
                    if not legal:
                        if not legal_bits(b, a):
                            break
                        a, b, root_turn = b, a, not root_turn
                        continue
                    choices = tuple(squares(legal & CORNERS or legal))
                    pick = rng.choice(choices)
                    flips = flipped_bits(a, b, pick)
                    a, b = b ^ flips, a | flips | (1 << pick)
                    root_turn = not root_turn
                difference = a.bit_count() - b.bit_count()
                if not root_turn:
                    difference = -difference
                totals[move] = totals.get(move, 0) + (1 if difference > 0 else -1 if difference < 0 else 0)
                counts[move] = counts.get(move, 0) + 1
                self.rollouts += 1
        self._finish_rollouts(totals, counts)

    def _finish_rollouts(self, totals, counts):
        self.rollout_order = {move: round(80 * total / counts[move]) for move, total in totals.items()}

    def _pv(self, own: int, other: int, depth: int) -> tuple[int, ...]:
        line = []
        for _ in range(depth):
            if not legal_bits(own, other):
                if not legal_bits(other, own):
                    break
                own, other = other, own
            entry = self.table.get((own, other))
            if not entry or entry.move is None:
                break
            flips = flipped_bits(own, other, entry.move)
            if not flips:
                break
            line.append(entry.move)
            own, other = other ^ flips, own | flips | (1 << entry.move)
        return tuple(line)

    def choose(self, position: Position, progress: Callable[[SearchResult], None] | None = None) -> SearchResult:
        start = perf_counter()
        self.deadline = start + self.config.time_limit
        self.table.clear()
        self.history = [0] * 100
        self.nodes = self.tt_hits = self.rollouts = 0
        self.rollout_order = {}
        own, other = position.pieces(position.turn), position.pieces(1 - position.turn)
        self.root_key = own, other
        moves = legal_bits(own, other)
        if not moves:
            over = not legal_bits(other, own)
            return SearchResult(None, terminal_score(own, other) if over else evaluate(own, other),
                                0, 0, perf_counter() - start, over)
        fallback = self._ordered(own, other, moves)[0]
        best = SearchResult(fallback, evaluate(own, other, moves), 0, 0, 0.0, False, (fallback,))
        self._rollout_ordering(own, other, moves)
        empty = position.empty_count
        target = empty if empty <= self.config.exact_empty else min(empty, self.config.max_depth)
        for depth in range(1, target + 1):
            try:
                self._check_time()
                score = self._search(own, other, depth, -INF, INF)
                self._check_time()
            except SearchTimeout:
                break
            root = self.table.get((own, other))
            if root is None or root.move is None or not moves & (1 << root.move):
                break
            best = SearchResult(root.move, score, depth, self.nodes, perf_counter() - start,
                                depth >= empty, self._pv(own, other, depth), self.rollouts, self.tt_hits)
            if progress:
                progress(best)
            if best.solved:
                break
        return SearchResult(best.move, best.score, best.depth, self.nodes, perf_counter() - start,
                            best.solved, best.pv, self.rollouts, self.tt_hits)


def choose_move(position: Position, config: SearchConfig = SearchConfig(), progress=None) -> SearchResult:
    return Searcher(config).choose(position, progress)


def greedy_move(position: Position) -> int | None:
    """The original maximum-immediate-flips strategy, retained as a benchmark."""
    moves = tuple(squares(position.legal()))
    if not moves:
        return None
    return max(moves, key=lambda move: flipped_bits(position.pieces(position.turn),
                                                   position.pieces(1 - position.turn), move).bit_count())
