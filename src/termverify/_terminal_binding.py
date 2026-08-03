r"""Platform-neutral failure taxonomy for the terminal binding port.

**This docstring is raw**, and must stay so. It names byte sequences —
``\xe2\x82``, ``\xc0``, ``\x82`` — and in a cooked string Python interprets
every one of them. While the divergence measurement was still tabulated here,
the lone-continuation row rendered as an invisible C1 control character at
runtime while reading correctly in the source. Nothing catches that on its
own: those are *valid* escapes, so ruff's ``W605`` stays silent, and ``ruff``,
``ruff format`` and ``mypy`` were all green with the table mangled. Found by
the round-2 adversarial review of issue #279, which read ``__doc__`` rather
than the file, and now guarded for the whole package by
``tests/test_docstring_escapes.py``.

The terminal adapter (``termverify.terminal``) classifies a binding failure
into evidence: an end-of-stream ends the run truthfully from the observed exit
record, a close outside the abort deadline is a structured runtime failure, a
single-flight violation is a *harness* defect that must never be dressed as
subject evidence (issue #261), and a geometry the binding did not adopt must
name both geometries rather than collapse into a generic spawn failure (issue
#228).

Those four classifications are the adapter's, and the adapter cannot name a
platform: the binding port hides which binding it holds. So the failure kinds
live here, above no platform and below the adapter, and each shipped binding
subclasses them as ``Conpty*`` (``termverify._conpty``) and ``PosixPty*``
(``termverify._posix_pty``).

Five kinds, four classifications, and the arithmetic is deliberate. The fifth,
:class:`TerminalUnsupportedError`, is **not** classified by the adapter and is
not meant to be: reaching it means a spawn was attempted without the port's
explicit probe having been honoured, which is a caller or binding defect with
nothing to say about the subject, so it lands in the generic spawn-failure
branch like any other unexpected exception. It lives here because both bindings
raise it and a binding author needs a base to derive from — not because the
adapter does anything with it.

``_posix_pty`` subclasses four of the five: there is no
``PosixPtyGeometryMismatchError``, for the reason given below.

**Why subclasses and not one shared set of concrete types.** A diagnostic that
says only "the binding was closed" loses which binding closed, and every one of
these types already appears in a message a human reads while debugging a real
subject. The kind is what the adapter needs; the family is what the reader
needs. Subclassing gives both without a platform conditional anywhere.

**Why this is what makes the adapter platform-neutral, and not merely
platform-unaware.** Before this module the adapter caught ``Conpty*``
concretely, so a POSIX end-of-stream fell through to the generic
"a native read failed" branch: the run would be reported as a runtime failure
instead of finishing from the child's real exit record — a false statement
about the subject, produced by a correctly working binding. The port's error
contract has to be neutral for the port to absorb the platform at all.

A binding is *not* required to raise every kind. ``_posix_pty`` raises no
geometry mismatch because ``TIOCSWINSZ`` adopts what it is given: a dimension
that does not fit the ``unsigned short`` the ``winsize`` struct packs is
refused by ``struct.pack`` before the ioctl, rather than silently wrapping, so
the binding never runs a child at a geometry other than the requested one.
``CreatePseudoConsole`` does wrap — a request goes into signed 16-bit ``COORD``
members unchecked and can be silently adopted as something smaller (issue
#228) — which is why that kind exists at all. The adapter's handling of an
unraised kind is unreachable through one binding and reachable through the
other, which is the ordinary shape of a port with two implementations, not a
gap to be filled with a conditional.

**What the two bindings do not give equally, stated rather than implied.** The
guarantee above is that no *subject* ever runs at an unrequested geometry, and
it holds on both. Not "no child": ConPTY learns what a geometry was adopted as
by spawning a throwaway probe child into the console and reading the size back,
so a child does run there — just never the subject, which is what a
``tier="os"`` receipt is a claim about.

The *evidence* on the refusal path does not match: an
out-of-range POSIX request surfaces as the ``struct.error`` from packing the
``winsize``, which the adapter classifies as a plain failed resize with no
``terminal-rows``/``adopted-*`` details, where ConPTY produces the structured
#228 record. Same host error, unequal transcript. Nothing false is recorded
either way, and geometries that large are not what a real subject asks for —
but a POSIX binding that raised this kind for its own out-of-range refusals
would close the gap, and that is a binding-side change belonging with the
adapter-level POSIX evidence in #269, not to this refactor.

A second divergence, latent rather than observable, sits on ``close``. A
release-only close (``force=False``) of a *live* child is permitted by the
ConPTY binding, where releasing the pseudoconsole handle makes the OS
terminate the attached client, and refused by the POSIX binding with
``PosixPtyLiveChildError``, because closing a pty master hangs up the
terminal and guarantees nothing about a child that ignores ``SIGHUP``. Both
answers are truthful about their own platform and neither is a failure kind
the adapter classifies: it closes with ``force=True`` on every path, so no
run reaches either. Recorded here because the port's contract is what a
third binding would be written against, and "close(force=False) on a live
child" is exactly the kind of question its author would otherwise have to
answer by reading two implementations.

**A third, and it is not one the bindings choose.** Both honour the
end-of-stream flush stated at :class:`TerminalEndOfStreamError`; what differs
is what reaches them to be flushed. A pty decodes nothing, so a subject that
stops part-way through a multibyte character hands its unfinished bytes to
the POSIX binding, which surfaces them as ``U+FFFD``. The Windows console
host is itself a UTF-8 decoder, so those bytes are consumed and discarded
before the ConPTY binding sees any of them — the binding still receives the
rest of the subject's output, just nothing of that sequence.

The divergence **this change opens** is exactly the incomplete-but-valid
prefix. The width matters because the obvious phrasings on either side of it
are both false, and each was written here and measured false in turn: "a bad
trailing byte" is too wide, and "otherwise the two agree" is too narrow.

**The row data is not repeated here.** It lives once, as executable data, in
``tests/_end_of_stream_tails.py``, where both bindings' suites parametrize
over it — ``test_the_end_of_stream_tail_table_holds_on_this_host`` asserts the
ConPTY column on Windows and the POSIX column on Linux, so every row is
measured on both platforms on every CI run. Three review rounds of issue #279
found this table restated in prose and stale; the third found eight of its
rows pinned by nothing at all. A table that is data cannot go stale against
itself, and a row cannot be added without obliging both platforms.

**The rule those rows measure**, which is what belongs in this module:

- The Windows console host decodes **structurally**. It reads the lead byte,
  learns how many continuation bytes to expect, and resolves the sequence only
  when a byte arrives that cannot structurally continue it. Whatever it is
  still waiting on at end of stream is discarded.
- Python's incremental decoder, which is what a pty binding has, **validates
  as well as counts**: it holds only a genuine prefix of a valid character and
  rejects anything else on sight.

Three regions follow. **Both waiting** — a valid prefix — is the one #279
opened: the host drops those bytes, and the pty hands them over for the flush
to report. **The host waiting alone** — ``\xc0``, which can never legally lead,
and the overlong ``\xe0\x80`` — diverges too, and diverged before #279, because
Python held nothing there and no flush is involved. **Neither waiting** is
agreement, except that a complete-but-invalid sequence can still draw a
different *number* of replacement characters, which the surrogate row shows.

So two different things are recorded, and only the first is this change's.
Everything outside region one is issue #282: the two decoders disagreeing
about which *complete* byte sequences are invalid, rather than about which are
unfinished. None of that is the flush's doing and none of it changed here; it
is recorded because bounding this change's divergence is what measured it.

Nothing false is recorded either way — at end of stream each binding accounts
for every byte it received, and the ConPTY binding cannot account for bytes
the host destroyed upstream of it. *Accounts for*, not *reports*: the flush
emits a single ``U+FFFD`` however many bytes were held, so a one-byte and a
three-byte truncation are indistinguishable in the transcript. The claim is
that nothing is silently dropped, not that the tail is recoverable. (At end
of stream, and only there: a read interrupted by a close reports nothing
held, on both, for the reason :class:`TerminalEndOfStreamError` gives.)

Issue #279 predicted this divergence with the platforms the other way round —
ConPTY surfacing the replacement, POSIX dropping it — and filed the fix as a
way to *close* a gap. Measured on both hosts, the prediction was false and the
bindings agreed: they lost the same two bytes for different reasons. Closing
the POSIX side's loss is therefore what *opened* this divergence, deliberately.
The alternative was parity bought by continuing to discard evidence one side
actually has, which is the wrong direction for a project whose thesis is that
a transcript states only what was observed. Every row of the measurement is
pinned on both platforms by
``test_the_end_of_stream_tail_table_holds_on_this_host`` over the data in
``tests/_end_of_stream_tails.py``, so a console host that changes its mind
fails a test rather than silently re-converging the two.

These names are private on purpose. They are the *binding author's* contract,
not the harness caller's: nothing a host writes against
``termverify.terminal`` needs them, so exporting them would widen the public
surface for an audience of two modules. A third binding written inside this
package would import them the same way; if one ever needs to live outside it,
that is the change that should make them public, with the compatibility
question asked then rather than pre-answered now.
"""

from __future__ import annotations

__all__ = [
    "TerminalClosedError",
    "TerminalConcurrentIOError",
    "TerminalEndOfStreamError",
    "TerminalGeometryMismatchError",
    "TerminalUnsupportedError",
]


class TerminalUnsupportedError(RuntimeError):
    """Raised when a binding is used on a host it does not claim.

    Reaching the adapter at all means a spawn was attempted without the
    port's explicit probe having been honoured, so this is a caller or
    binding defect rather than evidence about the subject.
    """


class TerminalClosedError(RuntimeError):
    """Raised when an operation is attempted after the binding was closed.

    Includes an operation *interrupted* by a close: a close may abandon
    output the child had already written, so the adapter must not read the
    interruption as an orderly end of stream.
    """


class TerminalConcurrentIOError(RuntimeError):
    """Raised when a read or write starts while another is in flight.

    Single-flight is a port contract the adapter honours, so this is defense
    in depth against a caller defect — and it wears its own type precisely so
    no layer above can classify a harness bug as subject evidence, the
    disposition issue #261 settled for both bindings.
    """


class TerminalEndOfStreamError(Exception):
    """Raised by ``read`` when the terminal reports end of stream.

    Deliberately not a subclass of :class:`TerminalClosedError` or of
    ``OSError``: this is the one binding failure that is *not* a failure —
    it is how a run ends truthfully, and the adapter turns it into the
    child's observed exit record. Collapsing it into any other kind would
    turn every clean subject exit into a runtime failure.

    Raised only while the binding is open; a read interrupted by ``close``
    raises :class:`TerminalClosedError` instead.

    **The decoder is flushed before this is raised.** A binding decodes the
    bytes it receives, so at end of stream it may still hold an incomplete
    sequence that nothing can now complete. Those bytes are returned as
    replacement text by the read that *meets* end of stream, and this error
    is raised by the read after it — never delivered alongside text and never
    dropped.

    The deferral is **conditional, not unconditional**, and a third binding
    should implement it that way: only a read with something to flush returns
    text instead of raising. When the decoder is empty — the ordinary case,
    every run whose output ends on a complete character — this is raised by
    the very read that meets end of stream, with no extra call. Both shipped
    bindings behave so.

    **"Never dropped" costs a latch, and a binding that skips it will drop
    it.** The deferral opens a gap between the read that returned the flushed
    text and the read that owes the raise, and a ``close`` landing in that gap
    would otherwise answer :class:`TerminalClosedError` — which the adapter
    classifies as a failure, so a run that had already ended, with its exit
    record captured, is reported as a binding closed outside the abort
    deadline instead of finishing. The adapter's watchdog expiry *is* such a
    close, so this is reachable rather than theoretical; it was measured on
    the POSIX binding by the round-2 adversarial review of issue #279. Once
    end of stream has been observed a binding must latch it: a stream that
    ended cannot un-end, and a later close does not overwrite that answer.
    Both shipped bindings latch, and touch no descriptor or handle on that
    path, so it is safe after teardown.

    The asymmetry with ``close`` is the reason the flush is honest. At end of
    stream an incomplete tail is evidence that the stream really did end
    mid-sequence; after a close it is evidence of nothing, because the close
    may have abandoned output the child had already written. So a read
    interrupted by a close raises :class:`TerminalClosedError` with the
    decoder untouched. Whether "the stream ended mid-sequence" also means
    "the *subject* truncated its output" is a question about what sits
    between the subject and the binding, and the two platforms answer it
    differently — see the module docstring.

    Both shipped bindings owe this, and one did not pay it until issue #279:
    the POSIX binding discarded whatever the decoder held, so a subject that
    exited mid-codepoint left a transcript asserting it produced only the
    bytes before it. What the two platforms then put *in front of* that
    contract still differs, which the module docstring records.
    """


class TerminalGeometryMismatchError(OSError):
    """The binding cannot, or provably did not, adopt the geometry.

    Subclasses ``OSError`` so that a binding raising it from a spawn or a
    resize is still handled by callers written for ordinary OS failures; the
    structured members are what let the adapter's failure record name the
    geometry the subject actually ran at, so a receipt's ``tier="os"`` claim
    never stands for a geometry the subject did not have (issue #228).
    """

    def __init__(
        self,
        message: str,
        *,
        requested: tuple[int, int],
        adopted: tuple[int, int] | None,
    ) -> None:
        super().__init__(message)
        #: The requested ``(rows, columns)``.
        self.requested = requested
        #: The adopted ``(rows, columns)`` as measured, or ``None`` when the
        #: refusal is predictive — nothing was spawned, so nothing was
        #: measured.
        self.adopted = adopted
