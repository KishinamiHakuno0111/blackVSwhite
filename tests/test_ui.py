"""Exercise real Tk widgets without opening dialogs or relying on screen coordinates."""

from pathlib import Path
import random
import tempfile
import time
import tkinter as tk
import unittest

from reversi.ai import SearchConfig, choose_move
from reversi.engine import Game, Position, squares
from reversi.ui import ChessApp, MODES
from reversi.worker import SearchWorker


class FakeWorker:
    def __init__(self):
        self.alive = False
        self.pending = []
        self.starts = 0
        self.cancellations = 0

    def start(self, position, config):
        self.alive = True
        self.position = position
        self.starts += 1

    def messages(self):
        result, self.pending = self.pending, []
        return result

    def finish(self):
        self.pending.append(("result", choose_move(self.position, SearchConfig(0, 1, 0, 0))))
        self.alive = False

    def cancel(self):
        self.cancellations += 1
        self.alive = False
        self.pending = []


class UITests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.worker = FakeWorker()
        self.app = ChessApp(self.root, self.worker)
        self.root.update()

    def tearDown(self):
        self.app.close()

    def drain(self):
        if self.app.poll_id is not None:
            self.root.after_cancel(self.app.poll_id)
            self.app.poll_id = None
        self.app._poll_search()

    def set_mode(self, mode):
        self.app.mode_var.set(mode)
        self.app.new_game()
        self.root.update()

    def test_canvas_click_and_keyboard_move(self):
        self.set_mode(MODES[1])
        x, y = self.app.board.center(34)
        self.app.board.event_generate("<Button-1>", x=int(x), y=int(y))
        self.root.update()
        self.assertEqual(len(self.app.game.history), 1)
        self.assertEqual(self.app.game.history[-1].move, 34)
        next_move = next(squares(self.app.game.position.legal()))
        self.app.board.keyboard_square = next_move
        self.app.board.focus_force()
        self.root.update()
        self.app.board.event_generate("<Return>")
        self.root.update()
        self.assertEqual(len(self.app.game.history), 2)

    def test_invalid_click_and_outside_board(self):
        original = self.app.game.position
        self.app.play_move(0)
        self.assertEqual(self.app.game.position, original)
        self.assertIn("不能落子", self.app.status_var.get())
        self.assertIsNone(self.app.board.square_at(0, 0))
        self.assertEqual(self.app.board.square_at(*self.app.board.center(99)), 99)

    def test_human_ai_reply_and_round_undo(self):
        self.app.play_move(34)
        self.app._cancel_search()
        self.app._begin_ai()
        self.assertTrue(self.app.busy)
        before = self.app.game.position
        self.app.play_move(next(squares(before.legal())))
        self.assertEqual(self.app.game.position, before)
        self.worker.finish()
        self.drain()
        self.assertEqual(len(self.app.game.history), 2)
        self.app.undo()
        self.assertEqual(self.app.game.position, Position.initial())
        self.assertFalse(self.app.busy)

    def test_undo_during_search_cancels_pending_result(self):
        self.app.play_move(34)
        self.app._cancel_search()
        self.app._begin_ai()
        self.worker.finish()
        self.app.undo()
        self.drain()
        self.assertEqual(self.app.game.position, Position.initial())
        self.assertFalse(self.app.busy)

    def test_new_game_invalidates_old_result(self):
        self.app.play_move(34)
        self.app._cancel_search()
        self.app._begin_ai()
        self.worker.finish()
        self.app.new_game()
        self.drain()
        self.assertEqual(self.app.game.position, Position.initial())
        self.assertEqual(self.app.game.history, [])

    def test_hint_does_not_play_the_move(self):
        original = self.app.game.position
        self.app.request_hint()
        self.worker.finish()
        self.drain()
        self.assertEqual(self.app.game.position, original)
        self.assertIn(self.app.hint_move, tuple(squares(original.legal())))
        self.app.play_move(self.app.hint_move)
        self.assertEqual(len(self.app.game.history), 1)
        self.assertIsNone(self.app.hint_move)

    def test_demo_pause_and_step_undo(self):
        self.set_mode(MODES[2])
        self.app._cancel_search()
        self.app._begin_ai()
        self.app.toggle_pause()
        self.assertTrue(self.app.paused)
        self.assertFalse(self.app.busy)
        self.assertIsNone(self.app.next_ai_id)
        self.app.toggle_pause()
        self.assertIsNotNone(self.app.next_ai_id)

    def test_restore_validates_before_replacing_game(self):
        self.app.play_move(34)
        before = self.app.game.position
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "game.json"
            game = Game()
            game.save(path, {"mode": "bad"})
            with self.assertRaises(ValueError):
                self.app.restore(path)
            self.assertEqual(self.app.game.position, before)
            game.save(path, {"level": []})
            with self.assertRaises(ValueError):
                self.app.restore(path)
            self.assertEqual(self.app.game.position, before)
            game.save(path, {"mode": MODES[2], "human_color": 0, "level": "快速"})
            self.app.restore(path)
            self.assertTrue(self.app.paused)
            self.assertEqual(self.app.game.position, Position.initial())

    def test_complete_game_displays_winner_and_disables_moves(self):
        self.set_mode(MODES[1])
        rng = random.Random(16)
        while not self.app.game.position.is_over:
            self.app.play_move(rng.choice(tuple(squares(self.app.game.position.legal()))))
        self.assertIn("对局结束", self.app.status_var.get())
        self.assertFalse(self.app.board.enabled)
        self.assertIn("disabled", self.app.hint_button.state())
        before = self.app.game.position
        self.app.play_move(0)
        self.assertEqual(self.app.game.position, before)

    def test_minimum_window_layout_has_room_for_the_board(self):
        self.root.geometry("1000x780")
        self.root.update()
        self.assertGreaterEqual(self.app.board.cell, 40)
        self.assertGreater(self.app.move_list.winfo_height(), 50)
        self.assertLess(self.app.pause_button.winfo_rooty() + self.app.pause_button.winfo_height(),
                        self.root.winfo_rooty() + self.root.winfo_height())


class WorkerTests(unittest.TestCase):
    def test_real_spawn_search_and_cancellation(self):
        worker = SearchWorker()
        try:
            worker.start(Position.initial(), SearchConfig(.1, 3, 0, 0))
            deadline = time.monotonic() + 8
            result = None
            while time.monotonic() < deadline:
                for kind, payload in worker.messages():
                    self.assertNotEqual(kind, "error", payload)
                    if kind == "result":
                        result = payload
                if result is not None:
                    break
                time.sleep(.02)
            self.assertIsNotNone(result)
            self.assertIn(result.move, tuple(squares(Position.initial().legal())))
            worker.start(Position.initial(), SearchConfig(10, 100, 0, 0))
            worker.cancel()
            self.assertFalse(worker.alive)
            self.assertEqual(worker.messages(), [])
        finally:
            worker.cancel()


class LiveUITests(unittest.TestCase):
    def test_actual_ai_reply_hint_and_white_player_opening(self):
        root = tk.Tk()
        app = ChessApp(root)
        app.level = "快速"
        pulses = []
        heartbeat_id = None
        def heartbeat():
            nonlocal heartbeat_id
            pulses.append(time.monotonic())
            if not app.closed:
                heartbeat_id = root.after(10, heartbeat)
        heartbeat_id = root.after(10, heartbeat)
        def wait_until(predicate):
            deadline = time.monotonic() + 8
            while not predicate() and time.monotonic() < deadline:
                root.update()
                time.sleep(.01)
            self.assertTrue(predicate(), app.stats_var.get())
        try:
            app.play_move(34)
            wait_until(lambda: len(app.game.history) == 2)
            self.assertGreater(len(pulses), 10, "Tk must remain responsive during AI search")
            self.assertTrue(app._is_human())
            original = app.game.position
            app.request_hint()
            wait_until(lambda: not app.busy)
            self.assertEqual(app.game.position, original)
            self.assertIn(app.hint_move, tuple(squares(original.legal())))
            app.undo()
            self.assertEqual(app.game.position, Position.initial())
            app.color_var.set("白棋 · 后手")
            app.level_var.set("快速")
            app.new_game()
            wait_until(lambda: len(app.game.history) == 1)
            self.assertEqual(app.game.position.turn, 1)
            self.assertTrue(app._is_human())
        finally:
            if heartbeat_id is not None:
                root.after_cancel(heartbeat_id)
            app.close()


if __name__ == "__main__":
    unittest.main()
