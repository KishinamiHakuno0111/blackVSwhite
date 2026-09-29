"""Exercise the shipped executable, including its real frozen AI subprocess."""

import json
from pathlib import Path
import sys
import tempfile
import time
import traceback


def run(report_path):
    report = {"ok": False, "frozen": bool(getattr(sys, "frozen", False)),
              "python": sys.version, "executable": sys.executable, "checks": []}
    app = None
    try:
        import tkinter as tk
        from .engine import Position, squares
        from .ui import ChessApp, MODES

        root = tk.Tk()
        app = ChessApp(root)
        app.level_var.set("快速")
        app.new_game()
        root.update()
        report["checks"].append("Tk window and 10x10 board created")

        def check(condition, message):
            if not condition:
                raise AssertionError(message)
            report["checks"].append(message)

        def wait_until(predicate):
            deadline = time.monotonic() + 25
            while not predicate() and time.monotonic() < deadline:
                root.update()
                time.sleep(.01)
            if not predicate():
                raise AssertionError("AI did not finish: " + app.stats_var.get())

        x, y = app.board.center(34)
        app.board.event_generate("<Button-1>", x=int(x), y=int(y))
        check(len(app.game.history) == 1, "Mouse click placed a legal move")
        wait_until(lambda: len(app.game.history) == 2)
        check(app._is_human(), "Real AI subprocess replied and returned control")

        original = app.game.position
        app.request_hint()
        wait_until(lambda: not app.busy)
        check(app.game.position == original and app.hint_move in tuple(squares(original.legal())),
              "AI hint is legal and leaves the board unchanged")
        with tempfile.TemporaryDirectory(prefix="reversi-smoke-") as directory:
            path = Path(directory) / "存档.json"
            app.game.save(path, {"mode": MODES[0], "human_color": 0, "level": "快速"})
            app.undo()
            check(app.game.position == Position.initial(), "Undo restored initial board")
            app.restore(path)
            check(app.game.position == original, "Saved game restored successfully")

        app.color_var.set("白棋 · 后手")
        app.new_game()
        wait_until(lambda: len(app.game.history) == 1)
        check(app._is_human(), "AI opens when the human plays white")

        app.mode_var.set(MODES[1])
        app.new_game()
        while not app.game.position.is_over:
            app.play_move(next(squares(app.game.position.legal())))
        check("对局结束" in app.status_var.get() and not app.board.enabled,
              "Complete two-player game reaches a displayed result")
        report["ok"] = True
    except Exception:
        report["error"] = traceback.format_exc()
    finally:
        if app is not None:
            app.close()
        Path(report_path).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if report["ok"] else 1
