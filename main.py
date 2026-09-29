"""Run with python main.py, or double-click start_game.bat on Windows."""

import multiprocessing


if __name__ == "__main__":
    multiprocessing.freeze_support()
    import sys
    if len(sys.argv) == 3 and sys.argv[1] == "--smoke-test":
        from reversi.smoke import run
        raise SystemExit(run(sys.argv[2]))
    else:
        from reversi.ui import main
        main()
