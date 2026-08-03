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

**``opened_by_279`` is an operational column, not a rule.** It is true where
Python's decoder is *still holding bytes* at end of stream, because those and
only those are what the flush can report. Resist the urge to summarise it —
four attempts were made during #280's review rounds and every one was
measured false. The last and most plausible, "an incomplete but *valid*
prefix", is falsified by ``b"\xed\xa0"``: CPython holds it, so the flush
reports it, yet UTF-8 can never encode a surrogate so it is a prefix of
nothing valid. It also flushes as *two* replacement characters, which
falsified "one ``U+FFFD`` however many bytes were held".

As orientation only, two decoders are involved and they hold overlapping but
different sets. The console host decodes **structurally**: it reads the lead
byte, learns how many continuations to expect, and waits until something
cannot structurally continue — so it waits on ``\xc0`` and on the overlong
``\xe0\x80``. Python rejects those two at once, and holds ``\xed\xa0``, which
the host also holds. Where both hold is #279's divergence; where they differ
the bindings diverged already, before #279 and unchanged by it, because
Python held nothing for a flush to find. Those are issue #282.
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
    # A surrogate *lead* plus one continuation. Both decoders hold it, so the
    # flush reports it and this is #279's — but it is not a prefix of any
    # valid character, because UTF-8 cannot encode surrogates. It is the row
    # that falsified four attempts to characterise this set by a rule, and it
    # flushes as TWO replacements, which falsified "one U+FFFD however many
    # bytes were held". Found by the round-3 adversarial review.
    Tail("surrogate-prefix", b"\xed\xa0", "START", "START��", True),
    Tail("four-byte-lead-alone", b"\xf4", "START", "START�", True),
    # -- region 2: the host waits structurally, Python rejects on sight ----
    Tail("never-valid-lead", b"\xc0", "START", "START�", False),
    Tail("overlong-continuation", b"\xe0\x80", "START", "START��", False),
    Tail("overlong-four-byte", b"\xf0\x80", "START", "START��", False),
    Tail("above-max-codepoint", b"\xf4\x90", "START", "START��", False),
    # -- region 3: neither waits -------------------------------------------
    Tail("lone-continuation", b"\x82", "START�", "START�", False),
    Tail("never-valid-byte", b"\xff", "START�", "START�", False),
    Tail("lead-then-ascii", b"\xe2\x28", "START�(", "START�(", False),
    Tail("five-byte-lead", b"\xf8", "START�", "START�", False),
    Tail("never-valid-fe", b"\xfe", "START�", "START�", False),
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
