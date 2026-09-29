"""Slow, independent array implementation used only as a correctness oracle."""

from functools import lru_cache
import random


def initial():
    board = [2] * 100
    board[44] = board[55] = 1
    board[45] = board[54] = 0
    return tuple(board)


def flips(board, player, move):
    if not 0 <= move < 100 or board[move] != 2:
        return ()
    row, col = divmod(move, 10)
    captured = []
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            if not dr and not dc:
                continue
            r, c = row + dr, col + dc
            ray = []
            while 0 <= r < 10 and 0 <= c < 10 and board[r * 10 + c] == 1 - player:
                ray.append(r * 10 + c)
                r, c = r + dr, c + dc
            if ray and 0 <= r < 10 and 0 <= c < 10 and board[r * 10 + c] == player:
                captured += ray
    return tuple(captured)


def legal(board, player):
    return tuple(i for i in range(100) if flips(board, player, i))


def play(board, player, move):
    result = list(board)
    captured = flips(board, player, move)
    if not captured:
        raise ValueError(move)
    for square in (*captured, move):
        result[square] = player
    return tuple(result)


def bitboards(board):
    return tuple(sum(1 << i for i, value in enumerate(board) if value == color) for color in (0, 1))


def ending(seed, empties=6):
    rng = random.Random(seed)
    board, player, passes = initial(), 0, 0
    while board.count(2) > empties and passes < 2:
        options = legal(board, player)
        if not options:
            passes += 1
        else:
            board = play(board, player, rng.choice(options))
            passes = 0
        player = 1 - player
    return board, player


@lru_cache(maxsize=30000)
def solve(board, player):
    options = legal(board, player)
    if not options:
        if not legal(board, 1 - player):
            return board.count(player) - board.count(1 - player), ()
        score, _ = solve(board, 1 - player)
        return -score, ()
    scored = [(move, -solve(play(board, player, move), 1 - player)[0]) for move in options]
    best = max(value for _, value in scored)
    return best, tuple(move for move, value in scored if value == best)
