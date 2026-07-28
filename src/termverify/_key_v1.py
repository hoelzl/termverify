"""The ``termverify.key/v1`` registry.

The closed set of semantic key names an ``input.key`` record may carry, and
the predicate that decides whether a value is one canonical chord. Names are
exact and case-sensitive; v1 performs no trimming, case folding, Unicode
normalization, alias rewriting, or modifier reordering (see
``docs/knowledge/protocol.md``). :data:`KEY_NAMES` and :func:`is_key_chord`
are re-exported from the top-level ``termverify`` package: the names are
public, this module path is not.
"""

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

#: Every valid ``termverify.key/v1`` name, in reviewed registry order: the
#: four modifiers, then the bases valid with or without a modifier, then the
#: bases valid only in a chord carrying ``Control``, ``Alt``, or ``Meta``
#: (``Shift`` alone does not qualify them). Membership here is necessary but
#: not sufficient for a chord — use :func:`is_key_chord` for that.
KEY_NAMES = KEY_MODIFIERS + KEY_NAMED_BASES + KEY_MODIFIED_BASES

_KEY_MODIFIER_SET = frozenset(KEY_MODIFIERS)
_KEY_NAMED_BASE_SET = frozenset(KEY_NAMED_BASES)
_KEY_MODIFIED_BASE_SET = frozenset(KEY_MODIFIED_BASES)
_KEY_MODIFIED_TRIGGERS = frozenset(("Control", "Alt", "Meta"))


def is_key_chord(value: object) -> bool:
    """Report whether *value* is one canonical ``termverify.key/v1`` chord.

    A chord is a non-empty sequence of exact :data:`KEY_NAMES` entries: zero
    or more distinct modifiers in the canonical ``Control``, ``Alt``,
    ``Shift``, ``Meta`` order, followed by exactly one base. Bases that are
    ordinary printable characters require at least one of ``Control``,
    ``Alt``, or ``Meta`` — unmodified printable insertion, including
    ``Shift``-ed uppercase, is ``input.text``, not ``input.key``.

    Acceptance is by **exact type**, matching the fail-closed discipline of
    the transcript codec: the sequence must be a ``list`` or ``tuple`` itself
    and every component must be a ``str`` itself. A subclass, a ``NamedTuple``
    of key names, or any other :class:`~collections.abc.Sequence` is
    ``False``, not a chord.

    Total and side-effect free: any other value, including a modifier-only,
    misordered, or duplicated-modifier sequence, is ``False`` rather than an
    error.
    """
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
