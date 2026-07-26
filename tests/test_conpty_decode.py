"""Incremental UTF-8 decoding evidence for the ConPTY raw-byte read path.

Finding R7 of ``docs/agent/reviews/adversarial-review-2026-07-24.md``: the
previous read path took pre-decoded ``str`` from ``pywinpty``, so a native
read landing mid-codepoint embedded an irreparable ``U+FFFD`` in evidence and
lost the character outright. A measured 200,000-character burst of ``U+65E5``
through that path produced 29 replacement characters across 21 reads and lost
12 characters.

These tests pin the healed contract at the binding boundary and need no
Windows host: :class:`ConptyChild` is constructed directly over a fake native
session that hands out byte chunks split at adversarial points, which is the
same seam the native session implements. The claim under test is exact: after
this slice a ``U+FFFD`` in ConPTY evidence means the child genuinely emitted
invalid UTF-8, never that a native read landed between two bytes of one
codepoint.
"""

from __future__ import annotations

from typing import Final

import pytest

from termverify._conpty import ConptyChild, ConptyEndOfStreamError

#: One character per UTF-8 encoded length, so every split point below
#: exercises a distinct continuation-byte arithmetic.
_ONE_BYTE: Final = "A"
_TWO_BYTE: Final = "é"  # LATIN SMALL LETTER E WITH ACUTE
_THREE_BYTE: Final = "日"  # CJK UNIFIED IDEOGRAPH-65E5
_FOUR_BYTE: Final = "\U0001f600"  # GRINNING FACE
_MIXED: Final = _ONE_BYTE + _TWO_BYTE + _THREE_BYTE + _FOUR_BYTE


class _FakeNativeSession:
    """Hand out pre-split byte chunks the way a native ``ReadFile`` would."""

    def __init__(self, chunks: list[bytes], *, alive_after: bool = False) -> None:
        self._chunks = list(chunks)
        self._alive_after = alive_after
        self.exit_status: int | None = 0
        self.closed = False

    def read_bytes(self) -> bytes:
        if not self._chunks:
            raise OSError("the native output pipe reported end-of-stream")
        return self._chunks.pop(0)

    def write(self, data: bytes) -> None:  # pragma: no cover - unused here
        raise AssertionError("these tests never write")

    def set_size(self, columns: int, rows: int) -> None:  # pragma: no cover
        raise AssertionError("these tests never resize")

    def isalive(self) -> bool:
        return bool(self._chunks) or self._alive_after

    def get_exitstatus(self) -> int | None:
        return None if self.isalive() else self.exit_status

    def cancel_io(self) -> None:  # pragma: no cover - unused here
        pass

    def close(self) -> None:
        self.closed = True


def _child(chunks: list[bytes]) -> ConptyChild:
    """Build a binding over a fake session; no native handles are involved."""
    return ConptyChild(
        _FakeNativeSession(chunks), pid=4321, job=None, process_handle=None
    )


def _drain(child: ConptyChild) -> str:
    parts: list[str] = []
    while True:
        try:
            parts.append(child.read())
        except ConptyEndOfStreamError:
            return "".join(parts)


def _split_every_point(text: str) -> list[list[bytes]]:
    """Every single-cut split of ``text``'s UTF-8 encoding, cut included."""
    encoded = text.encode("utf-8")
    return [[encoded[:cut], encoded[cut:]] for cut in range(1, len(encoded))]


@pytest.mark.parametrize(
    "text",
    [_TWO_BYTE, _THREE_BYTE, _FOUR_BYTE, _MIXED],
    ids=["two-byte", "three-byte", "four-byte", "mixed"],
)
def test_every_split_point_of_a_codepoint_heals_across_reads(text: str) -> None:
    """A read landing mid-codepoint must not corrupt or lose the character."""
    for chunks in _split_every_point(text):
        child = _child(chunks)
        assert _drain(child) == text
        assert "�" not in _drain(_child(chunks))


def test_byte_at_a_time_trickle_reconstructs_the_stream_exactly() -> None:
    """The worst case: every native read returns exactly one byte."""
    text = _MIXED * 64
    encoded = text.encode("utf-8")
    child = _child([encoded[index : index + 1] for index in range(len(encoded))])
    decoded = _drain(child)
    assert decoded == text
    assert decoded.count("�") == 0


def test_volume_burst_split_at_every_third_byte_is_byte_exact() -> None:
    """The regression the measured pywinpty burst produced, in miniature."""
    text = _THREE_BYTE * 20_000
    encoded = text.encode("utf-8")
    # Cut at 1000-byte boundaries: 1000 % 3 != 0, so most cuts land inside a
    # codepoint rather than between two.
    chunks = [encoded[index : index + 1000] for index in range(0, len(encoded), 1000)]
    decoded = _drain(_child(chunks))
    assert decoded == text
    assert decoded.count("�") == 0
    assert decoded.count(_THREE_BYTE) == 20_000


def test_genuinely_invalid_bytes_still_surface_as_replacement() -> None:
    """Healing splits must not hide real corruption the child emitted."""
    decoded = _drain(_child([b"a\xffb"]))
    assert decoded == "a�b"


def test_truncated_trailing_sequence_is_flushed_before_end_of_stream() -> None:
    """A child that dies mid-codepoint truly truncated its output; say so.

    The incomplete tail is held back while more bytes could still complete it,
    so it surfaces as replacement text on the read that meets end-of-stream —
    and the end-of-stream itself is raised by the read after that, never
    swallowed.
    """
    child = _child([_THREE_BYTE.encode("utf-8")[:2]])
    assert child.read() == ""  # the two bytes could still have been completed
    assert child.read() == "�"  # they were not: the child truncated its output
    with pytest.raises(ConptyEndOfStreamError):
        child.read()


def test_complete_output_reports_end_of_stream_without_extra_text() -> None:
    """The flush must not invent a chunk when nothing was left buffered."""
    child = _child([_THREE_BYTE.encode("utf-8")])
    assert child.read() == _THREE_BYTE
    with pytest.raises(ConptyEndOfStreamError):
        child.read()
