"""Deterministic VT output normalization for terminal evidence.

Implements the ``TerminalOutputNormalizer`` port fixed by the accepted ConPTY
adapter design (`docs/agent/design/conpty-adapter-design.md`) for the closed
v1 sequence subset documented in `docs/agent/design/vt-normalizer-decision.md`.

The screen model is a pure function of the fed chunk sequence, the initial
dimensions, and resize notifications: no clock, locale, or other ambient
state. Anything outside the documented subset raises
:class:`VtNormalizationError` — a frame is never silently wrong.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Protocol, runtime_checkable

from termverify.adapter import Cursor, Frame

NORMALIZER_ID: Final = "termverify.vt"
NORMALIZER_VERSION: Final = "1"

_TAB_INTERVAL: Final = 8
_STRING_OPENERS: Final = {"]": "osc", "P": "dcs", "X": "sos", "^": "pm", "_": "apc"}
_CHARSET_DESIGNATORS: Final = frozenset("()*+")
_CSI_PARAM_CHARS: Final = frozenset("0123456789;:")


class VtNormalizationError(Exception):
    """Raised when output falls outside the documented v1 VT subset."""

    def __init__(self, message: str, sequence: str) -> None:
        super().__init__(f"{message}: {sequence!r}")
        self.sequence = sequence


@dataclass(frozen=True, slots=True)
class ScreenSnapshot:
    frame: Frame
    cursor: Cursor
    mode: str

    def __post_init__(self) -> None:
        if type(self.frame) is not Frame:
            raise TypeError("frame has the wrong type")
        if type(self.cursor) is not Cursor:
            raise TypeError("cursor has the wrong type")
        if self.mode not in ("normal", "alternate"):
            raise ValueError("mode must be 'normal' or 'alternate'")


@runtime_checkable
class TerminalOutputNormalizer(Protocol):
    """Port for turning decoded terminal output into screen evidence."""

    def feed(self, chunk: str) -> None: ...

    def notify_resize(self, *, rows: int, columns: int) -> None: ...

    def snapshot(self) -> ScreenSnapshot: ...


def _require_dimension(value: int, label: str) -> int:
    if type(value) is not int:
        raise TypeError(f"{label} must be an integer")
    if value <= 0:
        raise ValueError(f"{label} must be positive")
    return value


def _blank_grid(rows: int, columns: int) -> list[list[str]]:
    return [[" "] * columns for _ in range(rows)]


def _default_tab_stops(columns: int) -> set[int]:
    return set(range(0, columns, _TAB_INTERVAL))


class VtScreenNormalizer:
    """Screen-model normalizer for the documented v1 VT subset."""

    def __init__(self, *, rows: int, columns: int) -> None:
        self._rows = _require_dimension(rows, "rows")
        self._columns = _require_dimension(columns, "columns")
        self._reset_run_state()

    def _reset_run_state(self) -> None:
        self._primary = _blank_grid(self._rows, self._columns)
        self._alternate = _blank_grid(self._rows, self._columns)
        self._mode = "normal"
        self._row = 0
        self._column = 0
        self._visible = True
        self._pending_wrap = False
        self._saved_cursor: tuple[int, int, bool] | None = None
        self._margin_top = 0
        self._margin_bottom = self._rows - 1
        self._tab_stops = _default_tab_stops(self._columns)
        self._parse_state = "ground"
        self._collected = ""
        self._string_kind = ""

    @property
    def _grid(self) -> list[list[str]]:
        return self._primary if self._mode == "normal" else self._alternate

    def feed(self, chunk: str) -> None:
        if type(chunk) is not str:
            raise TypeError("chunk must be a string")
        for character in chunk:
            self._consume(character)

    def notify_resize(self, *, rows: int, columns: int) -> None:
        rows = _require_dimension(rows, "rows")
        columns = _require_dimension(columns, "columns")
        self._primary = self._resized(self._primary, rows, columns)
        self._alternate = self._resized(self._alternate, rows, columns)
        self._rows = rows
        self._columns = columns
        self._row = min(self._row, rows - 1)
        self._column = min(self._column, columns - 1)
        self._margin_top = 0
        self._margin_bottom = rows - 1
        self._tab_stops = _default_tab_stops(columns)
        self._pending_wrap = False

    def _resized(
        self, grid: list[list[str]], rows: int, columns: int
    ) -> list[list[str]]:
        resized = _blank_grid(rows, columns)
        for row in range(min(rows, self._rows)):
            for column in range(min(columns, self._columns)):
                resized[row][column] = grid[row][column]
        return resized

    def snapshot(self) -> ScreenSnapshot:
        lines = tuple("".join(row) for row in self._grid)
        return ScreenSnapshot(
            frame=Frame(lines=lines, columns=self._columns, rows=self._rows),
            cursor=Cursor(column=self._column, row=self._row, visible=self._visible),
            mode=self._mode,
        )

    def _consume(self, character: str) -> None:
        state = self._parse_state
        if state == "ground":
            self._consume_ground(character)
        elif state == "escape":
            self._consume_escape(character)
        elif state == "charset":
            self._parse_state = "ground"
        elif state == "csi":
            self._consume_csi(character)
        elif state == "string":
            self._consume_string(character)
        else:  # state == "string-escape"
            self._consume_string_escape(character)

    def _consume_ground(self, character: str) -> None:
        code = ord(character)
        if 0x7F <= code <= 0x9F:
            raise VtNormalizationError("unsupported control character", character)
        if code >= 0x20:
            self._write(character)
        elif character == "\x1b":
            self._parse_state = "escape"
        elif character == "\r":
            self._column = 0
            self._pending_wrap = False
        elif character == "\n":
            self._line_feed()
        elif character == "\b":
            self._column = max(0, self._column - 1)
            self._pending_wrap = False
        elif character == "\t":
            self._horizontal_tab()
        elif character != "\x07":
            raise VtNormalizationError("unsupported control character", character)

    def _consume_escape(self, character: str) -> None:
        if character == "[":
            self._parse_state = "csi"
            self._collected = ""
            return
        if character in _STRING_OPENERS:
            self._parse_state = "string"
            self._string_kind = _STRING_OPENERS[character]
            return
        if character in _CHARSET_DESIGNATORS:
            self._parse_state = "charset"
            return
        self._parse_state = "ground"
        if character == "7":
            self._save_cursor()
        elif character == "8":
            self._restore_cursor()
        elif character == "D":
            self._line_feed()
        elif character == "E":
            self._column = 0
            self._pending_wrap = False
            self._line_feed()
        elif character == "M":
            self._reverse_line_feed()
        elif character == "H":
            self._tab_stops.add(self._column)
        elif character == "c":
            self._reset_run_state()
        elif character not in ("=", ">"):
            raise VtNormalizationError("unsupported escape sequence", character)

    def _consume_csi(self, character: str) -> None:
        code = ord(character)
        if (
            character in _CSI_PARAM_CHARS
            or (character == "?" and not self._collected)
            or 0x20 <= code <= 0x2F
        ):
            self._collected += character
            return
        if not 0x40 <= code <= 0x7E:
            self._parse_state = "ground"
            raise VtNormalizationError(
                "malformed control sequence", self._collected + character
            )
        self._parse_state = "ground"
        self._dispatch_csi(self._collected, character)

    def _consume_string(self, character: str) -> None:
        if character == "\x1b":
            self._parse_state = "string-escape"
        elif character == "\x07" and self._string_kind == "osc":
            self._parse_state = "ground"

    def _consume_string_escape(self, character: str) -> None:
        self._parse_state = "ground"
        if character != "\\":
            raise VtNormalizationError(
                "unterminated string sequence", "\x1b" + character
            )

    def _write(self, character: str) -> None:
        if self._pending_wrap:
            self._pending_wrap = False
            self._column = 0
            self._line_feed()
        self._grid[self._row][self._column] = character
        if self._column == self._columns - 1:
            self._pending_wrap = True
        else:
            self._column += 1

    def _line_feed(self) -> None:
        if self._row == self._margin_bottom:
            self._scroll_up(1)
        elif self._row < self._rows - 1:
            self._row += 1

    def _reverse_line_feed(self) -> None:
        if self._row == self._margin_top:
            self._scroll_down(1)
        elif self._row > 0:
            self._row -= 1

    def _horizontal_tab(self) -> None:
        stops = sorted(stop for stop in self._tab_stops if stop > self._column)
        self._column = stops[0] if stops else self._columns - 1
        self._pending_wrap = False

    def _save_cursor(self) -> None:
        self._saved_cursor = (self._row, self._column, self._pending_wrap)

    def _restore_cursor(self) -> None:
        row, column, pending = (
            self._saved_cursor if self._saved_cursor else (0, 0, False)
        )
        self._row = min(row, self._rows - 1)
        self._column = min(column, self._columns - 1)
        self._pending_wrap = pending and self._column == self._columns - 1

    def _move_up(self, count: int) -> None:
        limit = self._margin_top if self._row >= self._margin_top else 0
        self._row = max(limit, self._row - count)

    def _move_down(self, count: int) -> None:
        limit = (
            self._margin_bottom if self._row <= self._margin_bottom else self._rows - 1
        )
        self._row = min(limit, self._row + count)

    def _scroll_up(self, count: int) -> None:
        grid = self._grid
        for _ in range(min(count, self._margin_bottom - self._margin_top + 1)):
            del grid[self._margin_top]
            grid.insert(self._margin_bottom, [" "] * self._columns)

    def _scroll_down(self, count: int) -> None:
        grid = self._grid
        for _ in range(min(count, self._margin_bottom - self._margin_top + 1)):
            del grid[self._margin_bottom]
            grid.insert(self._margin_top, [" "] * self._columns)

    def _dispatch_csi(self, params: str, final: str) -> None:
        sequence = params + final
        if any(0x20 <= ord(character) <= 0x2F for character in params):
            raise VtNormalizationError("unsupported control sequence", sequence)
        if params.startswith("?"):
            self._dispatch_private_mode(params[1:], final, sequence)
            return
        if final == "m":
            return
        values = self._int_params(params, sequence)
        self._pending_wrap = False
        if final in "Hf":
            self._row = min(self._param(values, 0, 1) - 1, self._rows - 1)
            self._column = min(self._param(values, 1, 1) - 1, self._columns - 1)
        elif final == "A":
            self._move_up(self._param(values, 0, 1))
        elif final == "B":
            self._move_down(self._param(values, 0, 1))
        elif final == "C":
            self._column = min(
                self._columns - 1, self._column + self._param(values, 0, 1)
            )
        elif final == "D":
            self._column = max(0, self._column - self._param(values, 0, 1))
        elif final == "E":
            self._move_down(self._param(values, 0, 1))
            self._column = 0
        elif final == "F":
            self._move_up(self._param(values, 0, 1))
            self._column = 0
        elif final == "G":
            self._column = min(self._param(values, 0, 1) - 1, self._columns - 1)
        elif final == "d":
            self._row = min(self._param(values, 0, 1) - 1, self._rows - 1)
        elif final == "J":
            self._erase_display(self._param(values, 0, 0), sequence)
        elif final == "K":
            self._erase_line(self._param(values, 0, 0), sequence)
        elif final == "@":
            self._insert_characters(self._param(values, 0, 1))
        elif final == "P":
            self._delete_characters(self._param(values, 0, 1))
        elif final == "X":
            self._erase_characters(self._param(values, 0, 1))
        elif final == "L":
            self._insert_lines(self._param(values, 0, 1))
        elif final == "M":
            self._delete_lines(self._param(values, 0, 1))
        elif final == "S":
            self._scroll_up(self._param(values, 0, 1))
        elif final == "T":
            self._scroll_down(self._param(values, 0, 1))
        elif final == "r":
            self._set_margins(values)
        elif final == "g":
            self._clear_tab_stops(self._param(values, 0, 0), sequence)
        else:
            raise VtNormalizationError("unsupported control sequence", sequence)

    def _dispatch_private_mode(self, params: str, final: str, sequence: str) -> None:
        if final not in "hl":
            raise VtNormalizationError("unsupported control sequence", sequence)
        enable = final == "h"
        for mode in self._int_params(params, sequence):
            if mode == 25:
                self._visible = enable
            elif mode == 1049:
                self._switch_alternate(enable, save_cursor=True, clear_on="enter")
            elif mode == 1047:
                self._switch_alternate(enable, save_cursor=False, clear_on="leave")
            elif mode == 1048:
                if enable:
                    self._save_cursor()
                else:
                    self._restore_cursor()
            elif mode != 12:
                raise VtNormalizationError("unsupported private mode", sequence)

    def _switch_alternate(
        self, enable: bool, *, save_cursor: bool, clear_on: str
    ) -> None:
        if enable and self._mode == "normal":
            if save_cursor:
                self._save_cursor()
            self._mode = "alternate"
            self._pending_wrap = False
            if clear_on == "enter":
                self._alternate = _blank_grid(self._rows, self._columns)
        elif not enable and self._mode == "alternate":
            if clear_on == "leave":
                self._alternate = _blank_grid(self._rows, self._columns)
            self._mode = "normal"
            self._pending_wrap = False
            if save_cursor:
                self._restore_cursor()

    def _erase_display(self, selector: int, sequence: str) -> None:
        grid = self._grid
        if selector == 0:
            self._erase_line(0, sequence)
            for row in range(self._row + 1, self._rows):
                grid[row] = [" "] * self._columns
        elif selector == 1:
            self._erase_line(1, sequence)
            for row in range(self._row):
                grid[row] = [" "] * self._columns
        elif selector == 2:
            for row in range(self._rows):
                grid[row] = [" "] * self._columns
        else:
            raise VtNormalizationError("unsupported erase selector", sequence)

    def _erase_line(self, selector: int, sequence: str) -> None:
        line = self._grid[self._row]
        if selector == 0:
            for column in range(self._column, self._columns):
                line[column] = " "
        elif selector == 1:
            for column in range(self._column + 1):
                line[column] = " "
        elif selector == 2:
            self._grid[self._row] = [" "] * self._columns
        else:
            raise VtNormalizationError("unsupported erase selector", sequence)

    def _insert_characters(self, count: int) -> None:
        line = self._grid[self._row]
        kept = line[self._column : self._columns - count]
        line[self._column : self._column + count] = [" "] * min(
            count, self._columns - self._column
        )
        line[self._column + count :] = kept
        del line[self._columns :]

    def _delete_characters(self, count: int) -> None:
        line = self._grid[self._row]
        del line[self._column : self._column + count]
        line.extend([" "] * (self._columns - len(line)))

    def _erase_characters(self, count: int) -> None:
        line = self._grid[self._row]
        for column in range(self._column, min(self._column + count, self._columns)):
            line[column] = " "

    def _insert_lines(self, count: int) -> None:
        if not self._margin_top <= self._row <= self._margin_bottom:
            return
        grid = self._grid
        for _ in range(min(count, self._margin_bottom - self._row + 1)):
            del grid[self._margin_bottom]
            grid.insert(self._row, [" "] * self._columns)

    def _delete_lines(self, count: int) -> None:
        if not self._margin_top <= self._row <= self._margin_bottom:
            return
        grid = self._grid
        for _ in range(min(count, self._margin_bottom - self._row + 1)):
            del grid[self._row]
            grid.insert(self._margin_bottom, [" "] * self._columns)

    def _set_margins(self, values: tuple[int, ...]) -> None:
        top = self._param(values, 0, 1) - 1
        bottom = self._param(values, 1, self._rows) - 1
        if top < 0 or bottom >= self._rows or top >= bottom:
            return
        self._margin_top = top
        self._margin_bottom = bottom
        self._row = 0
        self._column = 0

    def _clear_tab_stops(self, selector: int, sequence: str) -> None:
        if selector == 0:
            self._tab_stops.discard(self._column)
        elif selector == 3:
            self._tab_stops.clear()
        else:
            raise VtNormalizationError("unsupported tab clear selector", sequence)

    @staticmethod
    def _int_params(params: str, sequence: str) -> tuple[int, ...]:
        if not params:
            return ()
        values: list[int] = []
        for part in params.split(";"):
            if part and not part.isdigit():
                raise VtNormalizationError("unsupported parameter", sequence)
            values.append(int(part) if part else -1)
        return tuple(values)

    @staticmethod
    def _param(values: tuple[int, ...], index: int, default: int) -> int:
        if index >= len(values) or values[index] < 0:
            return default
        value = values[index]
        return value if value > 0 or default == 0 else default
