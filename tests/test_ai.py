import random
from time import perf_counter
import unittest

from reversi.ai import (WIN, SearchConfig, Searcher, choose_move, empty_regions,
                        evaluate, evaluation_features, stable_bits)
from reversi.engine import ALL, BLACK, Game, Position, squares
from . import reference as ref


class AITests(unittest.TestCase):
    def test_stability_is_color_specific(self):
        self.assertEqual(stable_bits(ALL), ALL)
        self.assertEqual(stable_bits(0), 0)
        self.assertEqual(stable_bits(Position.initial().black), 0)
        features = evaluation_features(ALL, 0)
        self.assertEqual(features["stable"], 64)

    def test_proven_stable_discs_never_flip(self):
        for seed in range(12):
            game = Game()
            rng = random.Random(seed)
            while not game.position.is_over:
                before = game.position
                black_stable, white_stable = stable_bits(before.black), stable_bits(before.white)
                game.play(rng.choice(tuple(squares(before.legal()))))
                after = game.position
                self.assertEqual(black_stable & after.black, black_stable)
                self.assertEqual(white_stable & after.white, white_stable)

    def test_regions_use_four_neighbors_and_preserve_all_cells(self):
        self.assertEqual(len(empty_regions((1 << 0) | (1 << 9))), 2)
        empty = (1 << 0) | (1 << 1) | (1 << 8) | (1 << 63)
        regions = empty_regions(empty)
        self.assertEqual(sorted(r.bit_count() for r in regions), [1, 3])
        self.assertEqual(sum(regions), empty)
        self.assertEqual(len(empty_regions((1 << 7) | (1 << 8))), 2)

    def test_evaluation_sign_and_board_symmetry(self):
        for seed in range(4):
            board, player = ref.ending(seed, 35)
            own, other = ref.bitboards(board)
            self.assertEqual(evaluate(own, other), -evaluate(other, own))
            rotated = tuple(reversed(board))
            a, b = ref.bitboards(rotated)
            self.assertEqual(evaluate(own, other), evaluate(a, b))

    def test_evaluation_matches_all_rotations_and_reflections(self):
        # All eight symmetries must preserve evaluation, including corner penalties.
        board, _ = ref.ending(15, 20)
        expected = evaluate(*ref.bitboards(board))
        for _ in range(4):
            reflected = tuple(board[row * 8 + 7 - col] for row in range(8) for col in range(8))
            self.assertEqual(evaluate(*ref.bitboards(board)), expected)
            self.assertEqual(evaluate(*ref.bitboards(reflected)), expected)
            board = tuple(board[(7 - col) * 8 + row] for row in range(8) for col in range(8))

    def test_time_zero_returns_legal_fallback(self):
        position = Position.initial()
        result = choose_move(position, SearchConfig(0, 12, 12, 0))
        self.assertIn(result.move, tuple(squares(position.legal())))
        self.assertEqual(result.depth, 0)
        self.assertFalse(result.solved)

    def test_time_budget_and_valid_pv(self):
        board, player = ref.ending(7, 50)
        position = Position(*ref.bitboards(board), player)
        start = perf_counter()
        result = choose_move(position, SearchConfig(.08, 30, 0, 0))
        self.assertLess(perf_counter() - start, .8)
        self.assertIn(result.move, tuple(squares(position.legal())))
        current = position
        for move in result.pv:
            if not current.legal():
                current = current.passed()
            self.assertTrue(current.legal() & (1 << move))
            current = current.play(move)

    def test_exact_endgames_match_independent_exhaustive_solver(self):
        for seed in (1, 3, 8, 17, 29):
            board, player = ref.ending(seed, 6)
            difference, best_moves = ref.solve(board, player)
            position = Position(*ref.bitboards(board), player)
            if not best_moves:
                continue
            result = choose_move(position, SearchConfig(5, 2, 8, 0))
            expected = WIN + difference * 100 if difference > 0 else -WIN + difference * 100 if difference < 0 else 0
            self.assertTrue(result.solved)
            self.assertEqual(result.score, expected, (seed, difference, result))
            self.assertIn(result.move, best_moves, (seed, best_moves, result))

    def test_forced_pass_is_not_terminal_in_search(self):
        # Find a reachable late position with a pass in its descendant tree.
        board, player = ref.ending(1, 7)
        position = Position(*ref.bitboards(board), player)
        expected, _ = ref.solve(board, player)
        searcher = Searcher(SearchConfig(5, 12, 12, 0))
        searcher.deadline = perf_counter() + 5
        value = searcher._search(position.pieces(player), position.pieces(1 - player), 7, -1_000_000, 1_000_000)
        expected_score = WIN + expected * 100 if expected > 0 else -WIN + expected * 100 if expected < 0 else 0
        self.assertEqual(value, expected_score)
        # Explicit pass with exactly one legal move for the opponent.
        position = Position(1 << 1, ALL ^ ((1 << 0) | (1 << 1)), BLACK)
        self.assertFalse(position.legal())
        self.assertTrue(position.legal(1))
        searcher.deadline = perf_counter() + 2
        self.assertEqual(searcher._search(position.black, position.white, 1, -1_000_000, 1_000_000), -WIN - 6400)
        self.assertIsNone(choose_move(position).move)
        self.assertFalse(choose_move(position).solved)

    def test_terminal_score_uses_actual_disc_margin(self):
        result = choose_move(Position(1, 0))
        self.assertIsNone(result.move)
        self.assertEqual(result.score, WIN + 100)
        self.assertTrue(result.solved)

    def test_rollouts_are_bounded_and_do_not_change_completed_minimax_result(self):
        position = Position.initial()
        a = choose_move(position, SearchConfig(1, 2, 0, 1))
        b = choose_move(position, SearchConfig(1, 2, 0, 0))
        self.assertGreater(a.rollouts, 0)
        self.assertEqual(a.depth, 2)
        self.assertEqual(a.score, b.score)

    def test_searcher_reuse_and_tiny_transposition_table(self):
        searcher = Searcher(SearchConfig(1, 3, 0, 0, table_limit=2))
        position = Position.initial()
        first = searcher.choose(position)
        position = position.play(first.move)
        second = searcher.choose(position)
        self.assertIn(second.move, tuple(squares(position.legal())))
        self.assertLessEqual(len(searcher.table), 2)


if __name__ == "__main__":
    unittest.main()
