import json
from pathlib import Path
import random
import tempfile
import unittest

from reversi.engine import (ALL, BLACK, WHITE, EMPTY, Game, Position, coordinate,
                            flipped_bits, parse_coordinate, squares)
from . import reference as ref


class RulesTests(unittest.TestCase):
    def test_eight_by_eight_limits_and_old_save_rejection(self):
        self.assertEqual(ALL, (1 << 64) - 1)
        self.assertEqual(coordinate(63), "H8")
        self.assertEqual(parse_coordinate("h8"), 63)
        for move in (64, 99):
            with self.assertRaises(ValueError):
                Position.initial().at(move)
            with self.assertRaises(ValueError):
                coordinate(move)
        game = Game()
        self.assertEqual(game.to_dict()["size"], 8)
        for moves in ([], ["E4"]):
            with self.assertRaisesRegex(ValueError, "仅支持 8×8"):
                Game.from_dict({**game.to_dict(), "size": 10, "moves": moves})

    def test_initial_and_coordinates(self):
        position = Position.initial()
        self.assertEqual(position.counts, (2, 2))
        self.assertEqual(position.empty_count, 60)
        self.assertEqual({coordinate(i) for i in squares(position.legal())}, {"D3", "C4", "F5", "E6"})
        for i in range(64):
            self.assertEqual(parse_coordinate(coordinate(i).lower()), i)
        for value in ("A0", "I1", "J10", "H9", "A9", "A01", "A100", "11", "", None):
            with self.assertRaises(ValueError):
                parse_coordinate(value)

    def test_illegal_moves_do_not_mutate_state(self):
        game = Game()
        initial = game.position
        for move in (-1, 64, 1000000, 0, 27, True, "D3"):
            with self.assertRaises(ValueError):
                game.play(move)
            self.assertEqual(game.position, initial)
            self.assertEqual(game.history, [])
        with self.assertRaises(ValueError):
            initial.passed()
        with self.assertRaises(ValueError):
            _ = initial.winner

    def test_eight_direction_flip(self):
        board = [2] * 64
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr or dc:
                    board[(3 + dr) * 8 + 3 + dc] = WHITE
                    board[(3 + 2 * dr) * 8 + 3 + 2 * dc] = BLACK
        position = Position(*ref.bitboards(board))
        self.assertEqual(flipped_bits(position.black, position.white, 27).bit_count(), 8)
        self.assertEqual(position.play(27).counts, (17, 0))

    def test_no_horizontal_or_diagonal_wrap(self):
        # A naive integer shift would mistake H1, A2, B2 for a horizontal ray.
        position = Position(1 << 7, 1 << 8)
        self.assertFalse(position.legal() & (1 << 9))
        for own, other in ((1 << 7, 1 << 16), (1 << 56, 1 << 47)):
            position = Position(own, other)
            board = tuple(position.at(i) for i in range(64))
            self.assertEqual(set(squares(position.legal())), set(ref.legal(board, BLACK)))

    def test_random_complete_games_against_array_oracle(self):
        checked_moves, forced_passes = 0, 0
        for seed in range(30):
            rng = random.Random(seed)
            board, position, passes = ref.initial(), Position.initial(), 0
            while passes < 2:
                for color in (BLACK, WHITE):
                    self.assertEqual(set(squares(position.legal(color))), set(ref.legal(board, color)))
                options = ref.legal(board, position.turn)
                if not options:
                    passes += 1
                    forced_passes += 1
                    position = position.passed()
                    continue
                passes = 0
                move = rng.choice(options)
                board = ref.play(board, position.turn, move)
                position = position.play(move)
                self.assertEqual((position.black, position.white), ref.bitboards(board))
                checked_moves += 1
            self.assertTrue(position.is_over)
            b, w = board.count(BLACK), board.count(WHITE)
            self.assertEqual(position.counts, (b, w))
            self.assertEqual(position.winner, BLACK if b > w else WHITE if w > b else None)
        self.assertGreater(checked_moves, 1700)
        self.assertGreater(forced_passes, 60)

    def test_terminal_with_empty_squares_and_draw(self):
        position = Position(1, 0)
        self.assertTrue(position.is_over)
        self.assertEqual(position.winner, BLACK)
        self.assertEqual(position.empty_count, 63)
        self.assertIsNone(Position(1, 1 << 63).winner)

    def test_pass_history_undo_and_roundtrip(self):
        game = Game()
        # Seed 2 reaches a forced pass on the independent 8x8 reference board.
        rng = random.Random(2)
        skip_seen = False
        while not game.position.is_over:
            before = game.position
            move = rng.choice(tuple(squares(before.legal())))
            record = game.play(move)
            if record.skipped is not None:
                skip_seen = True
                self.assertEqual(game.position.turn, before.turn)
                game.undo()
                self.assertEqual(game.position, before)
                game.play(move)
        self.assertTrue(skip_seen)
        restored = Game.from_dict(game.to_dict())
        self.assertEqual(restored.position, game.position)
        self.assertEqual(restored.history, game.history)
        while game.history:
            game.undo()
        self.assertEqual(game.position, Position.initial())

    def test_validated_atomic_save(self):
        game = Game()
        game.play(19)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "棋局.json"
            game.save(path, {"mode": "人机对战"})
            loaded, settings = Game.load(path)
            self.assertEqual(loaded.position, game.position)
            self.assertEqual(settings["mode"], "人机对战")
            self.assertEqual(len(list(Path(directory).iterdir())), 1)
            payload = game.to_dict()
            payload["moves"] = ["A1"]
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "第 1 步"):
                Game.load(path)
        for data in ({}, [], {"format": "black-white-chess", "version": 5},
                     {**game.to_dict(), "moves": ["D3"] * 61}):
            with self.assertRaises(ValueError):
                Game.from_dict(data)

    def test_position_validation(self):
        for args in ((-1, 0), (ALL + 1, 0), (1, 1), (0, 0, 2), (0.0, 0)):
            with self.assertRaises(ValueError):
                Position(*args)


if __name__ == "__main__":
    unittest.main()
