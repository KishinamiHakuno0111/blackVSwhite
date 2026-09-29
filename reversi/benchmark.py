"""Reproducible paired openings and color swaps against the old greedy baseline."""

import argparse
import json
from pathlib import Path
import random
from time import perf_counter

from .ai import SearchConfig, choose_move, greedy_move
from .engine import SIZE, Game, squares


def run(games=6, seconds=.08, seed=2026):
    results = []
    start = perf_counter()
    for index in range(games):
        game = Game()
        rng = random.Random(seed + index // 2)
        for _ in range(4):
            if game.position.is_over:
                break
            game.play(rng.choice(tuple(squares(game.position.legal()))))
        ai_color = index % 2
        ai_seconds = 0.0
        depths = []
        config = SearchConfig(seconds, 8, 10, 0, seed)
        while not game.position.is_over:
            position = game.position
            if position.turn == ai_color:
                analysis = choose_move(position, config)
                move = analysis.move
                ai_seconds += analysis.elapsed
                depths.append(analysis.depth)
            else:
                move = greedy_move(position)
            if move is None or not position.legal() & (1 << move):
                raise AssertionError("Player produced an illegal move")
            game.play(move)
        winner = game.position.winner
        row = {"game": index + 1, "seed": seed + index // 2, "ai_color": ai_color,
               "black": game.position.counts[0], "white": game.position.counts[1],
               "outcome": "draw" if winner is None else "win" if winner == ai_color else "loss",
               "moves": len(game.history), "ai_seconds": round(ai_seconds, 3),
               "mean_depth": round(sum(depths) / len(depths), 2)}
        results.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
    summary = {"size": SIZE, "games": games, "seconds_per_move": seconds, "seed": seed,
               "opponent": "maximum immediate flips", "random_opening_plies": 4,
               "paired_openings_color_swap": True, "elapsed": round(perf_counter() - start, 3),
               "wins": sum(r["outcome"] == "win" for r in results),
               "draws": sum(r["outcome"] == "draw" for r in results),
               "losses": sum(r["outcome"] == "loss" for r in results), "results": results}
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", type=int, default=6)
    parser.add_argument("--seconds", type=float, default=.08)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.games <= 0 or args.games % 2:
        parser.error("--games must be a positive even number for paired color swaps")
    summary = run(args.games, args.seconds, args.seed)
    print(f"AI: {summary['wins']} wins, {summary['draws']} draws, {summary['losses']} losses")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
