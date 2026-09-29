"""Disposable search process; no Tk calls or mutable game state cross this boundary."""

import multiprocessing as mp
import traceback

from .ai import SearchConfig, choose_move
from .engine import Position


def _run(connection, position, config):
    try:
        result = choose_move(position, config, lambda state: connection.send(("progress", state)))
        connection.send(("result", result))
    except Exception:
        connection.send(("error", traceback.format_exc()))
    finally:
        connection.close()


class SearchWorker:
    def __init__(self):
        self.process = None
        self.connection = None

    def start(self, position: Position, config: SearchConfig):
        self.cancel()
        context = mp.get_context("spawn")
        receiver, sender = context.Pipe(duplex=False)
        process = context.Process(target=_run, args=(sender, position, config), daemon=True)
        try:
            process.start()
        except BaseException:
            receiver.close()
            sender.close()
            raise
        sender.close()
        self.process, self.connection = process, receiver

    def messages(self):
        messages = []
        if self.connection is not None:
            try:
                while self.connection.poll():
                    messages.append(self.connection.recv())
            except (EOFError, OSError):
                pass
        return messages

    @property
    def alive(self):
        return self.process is not None and self.process.is_alive()

    def cancel(self):
        if self.process is not None:
            if self.process.is_alive():
                self.process.terminate()
            self.process.join(timeout=0.5)
            if self.process.is_alive():
                self.process.kill()
                self.process.join(timeout=0.5)
            if not self.process.is_alive():
                self.process.close()
            self.process = None
        if self.connection is not None:
            self.connection.close()
            self.connection = None
