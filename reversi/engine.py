"""Pure rules. Squares are row-major, A1=0 and J10=99; black moves first."""

from dataclasses import dataclass
import json
import os
from pathlib import Path
import tempfile

SIZE = 10
BLACK, WHITE, EMPTY = 0, 1, 2
ALL = (1 << (SIZE * SIZE)) - 1
LEFT = sum(1 << (r * SIZE) for r in range(SIZE))
RIGHT = LEFT << (SIZE - 1)
TOP = (1 << SIZE) - 1
BOTTOM = TOP << (SIZE * (SIZE - 1))
CORNERS = (1 << 0) | (1 << 9) | (1 << 90) | (1 << 99)
EDGES = LEFT | RIGHT | TOP | BOTTOM
# Each mask excludes source squares that would wrap across a row.
DIRECTIONS = (
    (1, ALL ^ RIGHT), (-1, ALL ^ LEFT), (10, ALL), (-10, ALL),
    (11, ALL ^ RIGHT), (-11, ALL ^ LEFT), (9, ALL ^ LEFT), (-9, ALL ^ RIGHT),
)


def shift(bits: int, direction: tuple[int, int]) -> int:
    delta, mask = direction
    bits &= mask
    return (bits << delta) & ALL if delta > 0 else bits >> -delta


def squares(bits: int):
    while bits:
        bit = bits & -bits
        yield bit.bit_length() - 1
        bits ^= bit


def neighbors(bits: int) -> int:
    result = 0
    for direction in DIRECTIONS:
        result |= shift(bits, direction)
    return result


def legal_bits(own: int, other: int) -> int:
    empty = ALL ^ (own | other)
    result = 0
    for delta, mask in DIRECTIONS:
        # Inline shifts here: this is the search's most frequent operation.
        if delta > 0:
            captured = ((own & mask) << delta) & other
            frontier = captured
            while frontier:
                frontier = (((frontier & mask) << delta) & other) & ~captured
                captured |= frontier
            result |= ((captured & mask) << delta) & empty
        else:
            distance = -delta
            captured = ((own & mask) >> distance) & other
            frontier = captured
            while frontier:
                frontier = (((frontier & mask) >> distance) & other) & ~captured
                captured |= frontier
            result |= ((captured & mask) >> distance) & empty
    return result


def flipped_bits(own: int, other: int, move: int) -> int:
    if type(move) is not int or not 0 <= move < SIZE * SIZE:
        return 0
    bit = 1 << move
    if bit & (own | other):
        return 0
    result = 0
    for direction in DIRECTIONS:
        cursor = shift(bit, direction)
        captured = 0
        while cursor & other:
            captured |= cursor
            cursor = shift(cursor, direction)
        if cursor & own:
            result |= captured
    return result


def coordinate(move: int) -> str:
    if not 0 <= move < SIZE * SIZE:
        raise ValueError("落点超出棋盘")
    return f"{chr(65 + move % SIZE)}{move // SIZE + 1}"


def parse_coordinate(value: str) -> int:
    if not isinstance(value, str) or len(value) not in (2, 3):
        raise ValueError("落点应为 A1 到 J10")
    value = value.upper()
    if value[0] not in "ABCDEFGHIJ" or not value[1:].isdigit():
        raise ValueError("落点应为 A1 到 J10")
    row = int(value[1:])
    if not 1 <= row <= SIZE:
        raise ValueError("落点应为 A1 到 J10")
    return (row - 1) * SIZE + ord(value[0]) - 65


@dataclass(frozen=True, slots=True)
class Position:
    black: int
    white: int
    turn: int = BLACK

    def __post_init__(self):
        if type(self.black) is not int or type(self.white) is not int:
            raise ValueError("棋盘必须使用整数位图")
        if self.black < 0 or self.white < 0 or (self.black | self.white) & ~ALL:
            raise ValueError("棋盘超出 10×10 范围")
        if self.black & self.white or type(self.turn) is not int or self.turn not in (BLACK, WHITE):
            raise ValueError("棋盘颜色或回合无效")

    @classmethod
    def initial(cls):
        return cls((1 << 45) | (1 << 54), (1 << 44) | (1 << 55))

    def pieces(self, color: int) -> int:
        if type(color) is not int or color not in (BLACK, WHITE):
            raise ValueError("棋手颜色无效")
        return self.black if color == BLACK else self.white

    @property
    def empty(self) -> int:
        return ALL ^ (self.black | self.white)

    @property
    def empty_count(self) -> int:
        return 100 - (self.black | self.white).bit_count()

    @property
    def counts(self) -> tuple[int, int]:
        return self.black.bit_count(), self.white.bit_count()

    def at(self, move: int) -> int:
        if type(move) is not int or not 0 <= move < 100:
            raise ValueError("落点超出棋盘")
        bit = 1 << move
        return BLACK if self.black & bit else WHITE if self.white & bit else EMPTY

    def legal(self, color: int | None = None) -> int:
        color = self.turn if color is None else color
        return legal_bits(self.pieces(color), self.pieces(1 - color))

    @property
    def is_over(self) -> bool:
        return not self.legal(BLACK) and not self.legal(WHITE)

    @property
    def winner(self) -> int | None:
        if not self.is_over:
            raise ValueError("对局尚未结束")
        b, w = self.counts
        return BLACK if b > w else WHITE if w > b else None

    def play(self, move: int):
        own, other = self.pieces(self.turn), self.pieces(1 - self.turn)
        flips = flipped_bits(own, other, move)
        if not flips:
            raise ValueError("此处不能落子，必须至少翻转一枚对方棋子")
        own |= flips | (1 << move)
        other ^= flips
        if self.turn == BLACK:
            return Position(own, other, WHITE)
        return Position(other, own, BLACK)

    def passed(self):
        if self.legal():
            raise ValueError("存在合法落点，不能跳过回合")
        return Position(self.black, self.white, 1 - self.turn)


@dataclass(frozen=True, slots=True)
class MoveRecord:
    before: Position
    after: Position
    move: int
    color: int
    flipped: int
    skipped: int | None


class Game:
    """Owns move history and automatically handles forced passes."""

    def __init__(self):
        self.position = Position.initial()
        self.history: list[MoveRecord] = []

    def play(self, move: int) -> MoveRecord:
        before = self.position
        after = before.play(move)
        flipped = flipped_bits(before.pieces(before.turn), before.pieces(1 - before.turn), move).bit_count()
        skipped = None
        if not after.legal() and after.legal(1 - after.turn):
            skipped = after.turn
            after = after.passed()
        record = MoveRecord(before, after, move, before.turn, flipped, skipped)
        self.history.append(record)
        self.position = after
        return record

    def undo(self) -> MoveRecord | None:
        if not self.history:
            return None
        record = self.history.pop()
        self.position = record.before
        return record

    def to_dict(self, settings: dict | None = None) -> dict:
        return {"format": "black-white-chess", "version": 1, "size": SIZE,
                "moves": [coordinate(r.move) for r in self.history], "settings": settings or {}}

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict) or data.get("format") != "black-white-chess":
            raise ValueError("这不是黑白棋存档")
        if (type(data.get("version")) is not int or data["version"] != 1
                or type(data.get("size")) is not int or data["size"] != SIZE):
            raise ValueError("不支持此存档版本或棋盘尺寸")
        moves = data.get("moves")
        if not isinstance(moves, list) or len(moves) > 96 or not isinstance(data.get("settings", {}), dict):
            raise ValueError("存档结构无效")
        game = cls()
        for i, value in enumerate(moves, 1):
            try:
                game.play(parse_coordinate(value))
            except (ValueError, TypeError) as exc:
                raise ValueError(f"存档第 {i} 步无效：{exc}") from exc
        return game

    def save(self, path: str | Path, settings: dict | None = None):
        """Atomic replacement: a failed write cannot truncate an existing game."""
        path = Path(path)
        text = json.dumps(self.to_dict(settings), ensure_ascii=False, indent=2)
        fd, temp = tempfile.mkstemp(prefix=".reversi-", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                stream.write(text)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp, path)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)

    @classmethod
    def load(cls, path: str | Path):
        with Path(path).open("r", encoding="utf-8-sig") as stream:
            text = stream.read(100_001)
        if len(text) > 100_000:
            raise ValueError("存档过大")
        try:
            data = json.loads(text)
        except (json.JSONDecodeError, RecursionError) as exc:
            raise ValueError("存档不是有效的 JSON") from exc
        return cls.from_dict(data), data.get("settings", {})
