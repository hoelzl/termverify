r"""The measured end-of-stream tail table, in one place, for both platforms.

``src/termverify/_terminal_binding.py`` states what the two bindings do with
a subject that writes ``START`` and then one bad tail before exiting. Issue
#279 opened one row of that difference deliberately; three more rows predate
it. Every round of review on #280 found the table restated somewhere and gone
stale, and the round-2 review found that eight of its rows were pinned by
nothing at all — in a commit whose own test docstring says "an unpinned
stated fact is the shape this project keeps finding to be false".

So the table lives here, once, and each binding's suite parametrizes over it:
``tests/test_conpty_binding.py`` asserts the ``conpty`` column on Windows and
``tests/test_posix_pty_binding.py`` asserts the ``posix`` column on Linux.
Adding a row obliges both platforms at once, and neither column can drift
from the other's idea of which tails exist.

Not importable as a test module by pytest — the leading underscore keeps it
out of collection.

**The rule the table measures**, stated once here and referenced rather than
paraphrased elsewhere:

- The Windows console host decodes **structurally**. It reads the lead byte,
  learns how many continuation bytes to expect, and resolves the sequence
  only when a byte arrives that cannot structurally continue it. At end of
  stream anything it is still waiting on is discarded.
- Python's incremental decoder **validates as well as counts**. It holds only
  what is a genuine prefix of a valid character, and rejects on sight
  anything that cannot become one.

Three regions follow, and they are what the ``opened_by_279`` column records:

1. **Both wait** — a valid prefix. The host drops it; the pty hands it over
   and the flush reports it. This is the divergence #279 opened.
2. **The host waits, Python does not** — ``\xc0`` (never a legal lead) and
   ``\xe0\x80`` (legal-shaped continuation, illegal range). Divergent, and
   divergent before #279: no flush is involved, because Python held nothing.
3. **Neither waits** — the tail is resolved on arrival by both. They agree,
   except that a complete-but-invalid sequence can still draw a different
   *number* of replacement characters, which is the surrogate row.

Regions 2 and 3's inequalities are issue #282; region 1 is #279's.
"""

from __future__ import annotations

from typing import Final, NamedTuple


class Tail(NamedTuple):
    """One measured row: what each binding shows for one trailing byte string."""

    #: Short identifier, used as the pytest parametrization id.
    name: str
    #: The bytes the subject writes after ``START``, then exits.
    tail: bytes
    #: Decoded text the ConPTY binding yields, escapes stripped.
    conpty: str
    #: Decoded text the POSIX pty binding yields.
    posix: str
    #: True where the difference is the one issue #279 deliberately opened —
    #: that is, where Python's decoder was holding bytes at end of stream.
    opened_by_279: bool


#: Written before every tail, so each row has an anchor to read up to.
PREFIX: Final = b"START"

#: Measured on a real console host (Windows 11 and the CI ``windows-latest``
#: images) and a real Linux pty. Not reasoned: every cell was observed.
TAILS: Final[tuple[Tail, ...]] = (
    # -- region 1: both decoders are waiting; #279 opened these ------------
    Tail("valid-prefix-1of2", b"\xc2", "START", "START�", True),
    Tail("valid-prefix-1of3", b"\xe0", "START", "START�", True),
    Tail("valid-prefix-1of4", b"\xf0", "START", "START�", True),
    Tail("valid-prefix-2of3", b"\xe2\x82", "START", "START�", True),
    Tail("valid-prefix-2of4", b"\xf0\x9f", "START", "START�", True),
    Tail("valid-prefix-3of4", b"\xf0\x9f\x98", "START", "START�", True),
    # -- region 2: the host waits structurally, Python rejects on sight ----
    Tail("never-valid-lead", b"\xc0", "START", "START�", False),
    Tail("overlong-continuation", b"\xe0\x80", "START", "START��", False),
    # -- region 3: neither waits -------------------------------------------
    Tail("lone-continuation", b"\x82", "START�", "START�", False),
    Tail("never-valid-byte", b"\xff", "START�", "START�", False),
    Tail("lead-then-ascii", b"\xe2\x28", "START�(", "START�(", False),
    Tail(
        "surrogate-complete",
        b"\xed\xa0\x80",
        "START��",
        "START���",
        False,
    ),
)


def subject_script(tail: bytes) -> str:
    """A subject that writes ``START``, then ``tail``, then exits.

    Built from the bytes rather than written out per row, so a row cannot
    disagree with the subject that measures it.
    """
    return (
        "import sys\n"
        f"sys.stdout.buffer.write({PREFIX!r})\n"
        f"sys.stdout.buffer.write({tail!r})\n"
        "sys.stdout.buffer.flush()\n"
    )
