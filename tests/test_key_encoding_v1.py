"""Unit tests for the ``termverify.key-encoding/v1`` registry.

The registry is a pure, total function from valid ``termverify.key/v1``
chords to exactly one xterm-legacy normal-mode byte string or the explicit
verdict unencodable (``None``). The full enumeration is digest-bound below,
following the key/v1 and timezone/v1 registry precedent.
"""

from __future__ import annotations

import hashlib

import pytest

from termverify._key_encoding_v1 import all_key_chords, encode_key_chord
from termverify._key_v1 import is_key_chord

# --- totality over the valid chord set -------------------------------------


def test_v1_enumeration_is_total_unique_and_canonical() -> None:
    chords = all_key_chords()

    assert len(chords) == 1382
    assert len(set(chords)) == 1382
    assert all(type(chord) is tuple for chord in chords)
    assert all(is_key_chord(chord) for chord in chords)


def test_v1_every_valid_chord_has_exactly_one_verdict() -> None:
    for chord in all_key_chords():
        encoded = encode_key_chord(chord)
        assert encoded is None or (
            type(encoded) is str
            and len(encoded) > 0
            and all(0x01 <= ord(ch) <= 0x7F for ch in encoded)
        )


def test_v1_encodable_set_has_the_designed_size() -> None:
    encodable = [
        chord for chord in all_key_chords() if encode_key_chord(chord) is not None
    ]

    # 96 CSI-final + 192 tilde + 64 F1-F4 + 9 C0-base + 78 letter
    # + 10 digit + 1 Space + 32 punctuation (Alt form only) chords.
    assert len(encodable) == 482


@pytest.mark.parametrize(
    "keys",
    [
        [],
        ["enter"],
        ["NotAKey"],
        ["Ctrl", "c"],
        ["Control", "C"],
        ["Shift", "Control", "c"],
        ["Control", "Control", "c"],
        ["Control"],
        ["Enter", "Tab"],
        ["c"],
        ["Shift", "a"],
        ["Space"],
        [1],
        "Enter",
        None,
    ],
)
def test_v1_invalid_chords_are_rejected_not_verdicted(keys: object) -> None:
    with pytest.raises(ValueError):
        encode_key_chord(keys)  # type: ignore[arg-type]


# --- exact bytes: CSI-final family (Arrows, Home, End) ----------------------


@pytest.mark.parametrize(
    ("keys", "expected"),
    [
        (("ArrowUp",), "\x1b[A"),
        (("ArrowDown",), "\x1b[B"),
        (("ArrowRight",), "\x1b[C"),
        (("ArrowLeft",), "\x1b[D"),
        (("Home",), "\x1b[H"),
        (("End",), "\x1b[F"),
        (("Shift", "ArrowUp"), "\x1b[1;2A"),
        (("Alt", "ArrowDown"), "\x1b[1;3B"),
        (("Control", "ArrowRight"), "\x1b[1;5C"),
        (("Meta", "ArrowLeft"), "\x1b[1;9D"),
        (("Control", "Shift", "Home"), "\x1b[1;6H"),
        (("Control", "Alt", "Shift", "Meta", "End"), "\x1b[1;16F"),
    ],
)
def test_v1_csi_final_family_bytes(keys: tuple[str, ...], expected: str) -> None:
    assert encode_key_chord(keys) == expected


# --- exact bytes: tilde family ---------------------------------------------


@pytest.mark.parametrize(
    ("keys", "expected"),
    [
        (("Insert",), "\x1b[2~"),
        (("Delete",), "\x1b[3~"),
        (("PageUp",), "\x1b[5~"),
        (("PageDown",), "\x1b[6~"),
        (("F5",), "\x1b[15~"),
        (("F6",), "\x1b[17~"),
        (("F7",), "\x1b[18~"),
        (("F8",), "\x1b[19~"),
        (("F9",), "\x1b[20~"),
        (("F10",), "\x1b[21~"),
        (("F11",), "\x1b[23~"),
        (("F12",), "\x1b[24~"),
        (("Shift", "Delete"), "\x1b[3;2~"),
        (("Alt", "Insert"), "\x1b[2;3~"),
        (("Control", "PageUp"), "\x1b[5;5~"),
        (("Meta", "F12"), "\x1b[24;9~"),
        (("Control", "Alt", "Shift", "Meta", "F5"), "\x1b[15;16~"),
    ],
)
def test_v1_tilde_family_bytes(keys: tuple[str, ...], expected: str) -> None:
    assert encode_key_chord(keys) == expected


# --- exact bytes: F1-F4 (SS3 unmodified, CSI when modified) ----------------


@pytest.mark.parametrize(
    ("keys", "expected"),
    [
        (("F1",), "\x1bOP"),
        (("F2",), "\x1bOQ"),
        (("F3",), "\x1bOR"),
        (("F4",), "\x1bOS"),
        (("Shift", "F1"), "\x1b[1;2P"),
        (("Alt", "F2"), "\x1b[1;3Q"),
        (("Control", "F3"), "\x1b[1;5R"),
        (("Control", "Alt", "Shift", "Meta", "F4"), "\x1b[1;16S"),
    ],
)
def test_v1_f1_to_f4_family_bytes(keys: tuple[str, ...], expected: str) -> None:
    assert encode_key_chord(keys) == expected


# --- exact bytes and fail-closed verdicts: C0 bases ------------------------


@pytest.mark.parametrize(
    ("keys", "expected"),
    [
        (("Enter",), "\r"),
        (("Tab",), "\t"),
        (("Escape",), "\x1b"),
        (("Backspace",), "\x7f"),
        (("Shift", "Tab"), "\x1b[Z"),
        (("Alt", "Enter"), "\x1b\r"),
        (("Alt", "Tab"), "\x1b\t"),
        (("Alt", "Escape"), "\x1b\x1b"),
        (("Alt", "Backspace"), "\x1b\x7f"),
    ],
)
def test_v1_c0_base_family_bytes(keys: tuple[str, ...], expected: str) -> None:
    assert encode_key_chord(keys) == expected


@pytest.mark.parametrize(
    "keys",
    [
        ("Control", "Enter"),
        ("Shift", "Enter"),
        ("Meta", "Enter"),
        ("Control", "Alt", "Enter"),
        ("Control", "Tab"),
        ("Alt", "Shift", "Tab"),
        ("Control", "Shift", "Tab"),
        ("Meta", "Tab"),
        ("Control", "Escape"),
        ("Shift", "Escape"),
        ("Meta", "Escape"),
        ("Control", "Backspace"),
        ("Shift", "Backspace"),
        ("Control", "Alt", "Shift", "Meta", "Backspace"),
    ],
)
def test_v1_modifier_dropping_c0_forms_are_unencodable(
    keys: tuple[str, ...],
) -> None:
    assert encode_key_chord(keys) is None


# --- exact bytes and fail-closed verdicts: letters -------------------------


@pytest.mark.parametrize(
    ("keys", "expected"),
    [
        (("Control", "a"), "\x01"),
        (("Control", "i"), "\t"),
        (("Control", "m"), "\r"),
        (("Control", "z"), "\x1a"),
        (("Alt", "a"), "\x1ba"),
        (("Alt", "z"), "\x1bz"),
        (("Control", "Alt", "a"), "\x1b\x01"),
        (("Control", "Alt", "c"), "\x1b\x03"),
    ],
)
def test_v1_letter_family_bytes(keys: tuple[str, ...], expected: str) -> None:
    assert encode_key_chord(keys) == expected


@pytest.mark.parametrize(
    "keys",
    [
        ("Control", "Shift", "a"),
        ("Alt", "Shift", "b"),
        ("Meta", "c"),
        ("Control", "Meta", "x"),
        ("Alt", "Meta", "y"),
        ("Control", "Alt", "Shift", "Meta", "z"),
    ],
)
def test_v1_shift_and_meta_letter_forms_are_unencodable(
    keys: tuple[str, ...],
) -> None:
    assert encode_key_chord(keys) is None


# --- exact bytes and fail-closed verdicts: digits and Space ----------------


@pytest.mark.parametrize(
    ("keys", "expected"),
    [
        (("Alt", "0"), "\x1b0"),
        (("Alt", "5"), "\x1b5"),
        (("Alt", "9"), "\x1b9"),
        (("Alt", "Space"), "\x1b "),
    ],
)
def test_v1_alt_digit_and_alt_space_bytes(keys: tuple[str, ...], expected: str) -> None:
    assert encode_key_chord(keys) == expected


@pytest.mark.parametrize(
    "keys",
    [
        ("Control", "0"),
        ("Control", "2"),
        ("Control", "Alt", "1"),
        ("Alt", "Shift", "3"),
        ("Meta", "4"),
        ("Control", "Space"),
        ("Control", "Alt", "Space"),
        ("Alt", "Shift", "Space"),
        ("Meta", "Space"),
    ],
)
def test_v1_control_digit_space_and_shift_meta_forms_are_unencodable(
    keys: tuple[str, ...],
) -> None:
    assert encode_key_chord(keys) is None


# --- exact bytes and fail-closed verdicts: punctuation bases ----------------


@pytest.mark.parametrize(
    ("keys", "expected"),
    [
        (("Alt", "/"), "\x1b/"),
        (("Alt", "<"), "\x1b<"),
        (("Alt", ">"), "\x1b>"),
        (("Alt", "_"), "\x1b_"),
        (("Alt", "?"), "\x1b?"),
        (("Alt", "["), "\x1b["),
    ],
)
def test_v1_alt_punctuation_bytes(keys: tuple[str, ...], expected: str) -> None:
    assert encode_key_chord(keys) == expected


@pytest.mark.parametrize(
    "keys",
    [
        ("Control", "/"),
        ("Control", "_"),
        ("Meta", "<"),
        ("Alt", "Shift", ">"),
        ("Control", "Alt", "["),
    ],
)
def test_v1_control_meta_and_shift_punctuation_forms_are_unencodable(
    keys: tuple[str, ...],
) -> None:
    assert encode_key_chord(keys) is None


# --- disclosed byte collisions ---------------------------------------------


def test_v1_exactly_the_four_disclosed_collisions_exist() -> None:
    by_encoding: dict[str, list[tuple[str, ...]]] = {}
    for chord in all_key_chords():
        encoded = encode_key_chord(chord)
        if encoded is not None:
            by_encoding.setdefault(encoded, []).append(chord)

    collisions = {
        encoded: tuple(chords)
        for encoded, chords in by_encoding.items()
        if len(chords) > 1
    }

    assert collisions == {
        "\r": (("Enter",), ("Control", "m")),
        "\t": (("Tab",), ("Control", "i")),
        "\x1b\r": (("Alt", "Enter"), ("Control", "Alt", "m")),
        "\x1b\t": (("Alt", "Tab"), ("Control", "Alt", "i")),
    }


# --- digest binding of the full enumeration --------------------------------


def _canonical_line(chord: tuple[str, ...]) -> str:
    encoded = encode_key_chord(chord)
    verdict = (
        "unencodable"
        if encoded is None
        else " ".join(f"{ord(ch):02x}" for ch in encoded)
    )
    return "+".join(chord) + " => " + verdict


def test_v1_key_encoding_registry_complete_contents_match_reviewed_digest() -> None:
    canonical = (
        "\n".join(_canonical_line(chord) for chord in all_key_chords()) + "\n"
    ).encode()

    assert hashlib.sha256(canonical).hexdigest() == (
        "72a17da549238053c88a925cf6bf2bbe93ed2b8564c7a09188075987fcdcda95"
    )
