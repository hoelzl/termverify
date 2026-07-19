"""The ``termverify.key-encoding/v1`` registry.

A pure, total function from valid ``termverify.key/v1`` chords to exactly
one xterm-legacy normal-mode byte string or the explicit verdict
unencodable (``None``), per the accepted design
(``docs/agent/design/key-to-terminal-byte-mapping.md``). The registry is
committed data plus committed arithmetic — never derived from terminfo,
toolkit enums, OS virtual-key codes, or any other ambient host state — and
its full enumeration is digest-bound in ``tests/test_key_encoding_v1.py``.

A chord is encodable exactly when the legacy encoding represents every
component of the chord by definition; it is unencodable when the only
candidate bytes would drop a modifier or misrepresent the base. Four
disclosed byte collisions are inherent to the legacy byte space:
``Control+m``/``Enter`` (CR), ``Control+i``/``Tab`` (HT), and their two
``Alt``-prefixed forms.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

from termverify._key_v1 import (
    KEY_MODIFIED_BASES,
    KEY_MODIFIERS,
    KEY_NAMED_BASES,
    is_key_chord,
)

#: CSI-final family: unmodified ``ESC [ <final>``; modified
#: ``ESC [ 1 ; m <final>`` for every modifier subset.
_CSI_FINAL_BASES: Final = {
    "ArrowUp": "A",
    "ArrowDown": "B",
    "ArrowRight": "C",
    "ArrowLeft": "D",
    "Home": "H",
    "End": "F",
}

#: Tilde family: unmodified ``ESC [ <n> ~``; modified ``ESC [ <n> ; m ~``.
_TILDE_BASES: Final = {
    "Insert": 2,
    "Delete": 3,
    "PageUp": 5,
    "PageDown": 6,
    "F5": 15,
    "F6": 17,
    "F7": 18,
    "F8": 19,
    "F9": 20,
    "F10": 21,
    "F11": 23,
    "F12": 24,
}

#: F1-F4: unmodified SS3 ``ESC O <final>``; modified ``ESC [ 1 ; m <final>``.
_SS3_BASES: Final = {"F1": "P", "F2": "Q", "F3": "R", "F4": "S"}

#: C0 bases: the unmodified single byte. Exactly five modified forms are
#: encodable (``Shift+Tab`` and ``Alt``+base); every other modified subset
#: has no legacy form that represents the modifier and fails closed.
_C0_BASES: Final = {"Enter": "\r", "Tab": "\t", "Escape": "\x1b", "Backspace": "\x7f"}

#: The xterm modifier-parameter weights over the canonical modifier names.
_MODIFIER_WEIGHTS: Final = {"Shift": 1, "Alt": 2, "Control": 4, "Meta": 8}

_LETTERS: Final = frozenset("abcdefghijklmnopqrstuvwxyz")
_DIGITS: Final = frozenset("0123456789")


def _modifier_parameter(modifiers: tuple[str, ...]) -> int:
    return 1 + sum(_MODIFIER_WEIGHTS[modifier] for modifier in modifiers)


def all_key_chords() -> tuple[tuple[str, ...], ...]:
    """Every valid ``termverify.key/v1`` chord in the documented order.

    Named bases first, in ``KEY_NAMED_BASES`` order, then modified-only
    bases in ``KEY_MODIFIED_BASES`` order. For each base, modifier subsets
    ascend by bitmask, where bit ``i`` selects ``KEY_MODIFIERS[i]``;
    modified-only bases skip the two subsets without a trigger modifier
    (the empty set and ``{Shift}``). This yields exactly
    26*16 + 69*14 = 1382 chords.
    """
    chords: list[tuple[str, ...]] = []
    for base in KEY_NAMED_BASES + KEY_MODIFIED_BASES:
        for mask in range(16):
            modifiers = tuple(
                modifier
                for index, modifier in enumerate(KEY_MODIFIERS)
                if mask & (1 << index)
            )
            chord = (*modifiers, base)
            if is_key_chord(chord):
                chords.append(chord)
    return tuple(chords)


def encode_key_chord(keys: Sequence[str]) -> str | None:
    """Encode one valid chord, or return ``None`` for unencodable.

    Raises :class:`ValueError` for anything that is not a canonical
    ``termverify.key/v1`` chord: invalidity is a caller error, never a
    verdict.
    """
    if not is_key_chord(keys):
        raise ValueError("keys must be one canonical termverify.key/v1 chord")
    chord = tuple(keys)
    modifiers = chord[:-1]
    base = chord[-1]
    modifier_set = frozenset(modifiers)

    if base in _CSI_FINAL_BASES:
        final = _CSI_FINAL_BASES[base]
        if not modifiers:
            return f"\x1b[{final}"
        return f"\x1b[1;{_modifier_parameter(modifiers)}{final}"

    if base in _TILDE_BASES:
        number = _TILDE_BASES[base]
        if not modifiers:
            return f"\x1b[{number}~"
        return f"\x1b[{number};{_modifier_parameter(modifiers)}~"

    if base in _SS3_BASES:
        final = _SS3_BASES[base]
        if not modifiers:
            return f"\x1bO{final}"
        return f"\x1b[1;{_modifier_parameter(modifiers)}{final}"

    if base in _C0_BASES:
        byte = _C0_BASES[base]
        if not modifiers:
            return byte
        if base == "Tab" and modifier_set == {"Shift"}:
            return "\x1b[Z"
        if modifier_set == {"Alt"}:
            return "\x1b" + byte
        return None

    # Modified-only bases: letters, digits, Space. Any Shift or Meta has no
    # distinct legacy form here and fails closed rather than alias or drop.
    if "Shift" in modifier_set or "Meta" in modifier_set:
        return None
    if base in _LETTERS:
        if modifier_set == {"Control"}:
            return chr(ord(base) - 0x60)
        if modifier_set == {"Alt"}:
            return "\x1b" + base
        return "\x1b" + chr(ord(base) - 0x60)
    # Digits and Space: only the Alt form exists; Control forms are
    # historically inconsistent and their NUL candidate is a hostile-input
    # hazard at the native wide-string boundary.
    if modifier_set == {"Alt"}:
        return "\x1b" + (" " if base == "Space" else base)
    return None
