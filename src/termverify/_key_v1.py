from __future__ import annotations

from typing import cast

KEY_MODIFIERS = (
    "Control",
    "Alt",
    "Shift",
    "Meta",
)

KEY_NAMED_BASES = (
    "Enter",
    "Tab",
    "Escape",
    "Backspace",
    "Delete",
    "Insert",
    "ArrowUp",
    "ArrowDown",
    "ArrowLeft",
    "ArrowRight",
    "Home",
    "End",
    "PageUp",
    "PageDown",
    "F1",
    "F2",
    "F3",
    "F4",
    "F5",
    "F6",
    "F7",
    "F8",
    "F9",
    "F10",
    "F11",
    "F12",
)

KEY_MODIFIED_BASES = (
    "a",
    "b",
    "c",
    "d",
    "e",
    "f",
    "g",
    "h",
    "i",
    "j",
    "k",
    "l",
    "m",
    "n",
    "o",
    "p",
    "q",
    "r",
    "s",
    "t",
    "u",
    "v",
    "w",
    "x",
    "y",
    "z",
    "0",
    "1",
    "2",
    "3",
    "4",
    "5",
    "6",
    "7",
    "8",
    "9",
    "Space",
    "!",
    '"',
    "#",
    "$",
    "%",
    "&",
    "'",
    "(",
    ")",
    "*",
    "+",
    ",",
    "-",
    ".",
    "/",
    ":",
    ";",
    "<",
    "=",
    ">",
    "?",
    "@",
    "[",
    "\\",
    "]",
    "^",
    "_",
    "`",
    "{",
    "|",
    "}",
    "~",
)

KEY_NAMES = KEY_MODIFIERS + KEY_NAMED_BASES + KEY_MODIFIED_BASES

_KEY_MODIFIER_SET = frozenset(KEY_MODIFIERS)
_KEY_NAMED_BASE_SET = frozenset(KEY_NAMED_BASES)
_KEY_MODIFIED_BASE_SET = frozenset(KEY_MODIFIED_BASES)
_KEY_MODIFIED_TRIGGERS = frozenset(("Control", "Alt", "Meta"))


def is_key_chord(value: object) -> bool:
    if type(value) not in (list, tuple) or not value:
        return False
    components = cast(list[object] | tuple[object, ...], value)
    if not all(type(component) is str for component in components):
        return False

    keys = cast(tuple[str, ...], tuple(components))
    modifiers = keys[:-1]
    base = keys[-1]
    if base not in _KEY_NAMED_BASE_SET | _KEY_MODIFIED_BASE_SET:
        return False
    if any(modifier not in _KEY_MODIFIER_SET for modifier in modifiers):
        return False
    if modifiers != tuple(
        modifier for modifier in KEY_MODIFIERS if modifier in modifiers
    ):
        return False
    return base not in _KEY_MODIFIED_BASE_SET or any(
        modifier in _KEY_MODIFIED_TRIGGERS for modifier in modifiers
    )
