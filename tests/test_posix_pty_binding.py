"""Native ownership, line discipline, geometry, and teardown evidence (POSIX).

Slice 1 of the vertical accepted in
``docs/agent/design/posix-pty-adapter-and-examples-vertical-boundary.md``
(issue #267). The binding's job is to make a real POSIX pseudoterminal
answer the same child surface the ConPTY binding answers, so the adapter
above the binding port needs no platform branch.

Two behaviors the design deliberately refused to predict are **measured**
here rather than assumed, because a plausible-sounding wrong sentence about
either is the classic way a pty binding ships a defect:

- the line discipline the child actually inherits, and
- what a master descriptor reports once its last slave is gone.

A third is measured because it is the whole reason the binding spawns
through a trampoline instead of ``preexec_fn``: the child really does get a
controlling terminal.

The probe tests run everywhere; everything else is Linux-only evidence, per
the boundary's decision 2 (claim only what CI verifies).
"""

from __future__ import annotations

import contextlib
import errno
import os
import pathlib
import select
import subprocess
import sys
import threading
import time

import pytest

from termverify import _posix_pty
from termverify._posix_pty import (
    FORCED_TERMINATION_SIGNAL,
    PosixPtyChild,
    PosixPtyClosedError,
    PosixPtyConcurrentIOError,
    PosixPtyEndOfStreamError,
)
from termverify._terminal_binding import (
    TerminalClosedError,
    TerminalConcurrentIOError,
    TerminalEndOfStreamError,
    TerminalGeometryMismatchError,
    TerminalUnsupportedError,
)

from ._end_of_stream_tails import TAILS as _TAILS
from ._end_of_stream_tails import Tail, subject_script

_LINUX_ONLY = pytest.mark.skipif(
    not sys.platform.startswith("linux"),
    reason="POSIX PTY binding evidence (claimed on Linux only, decision 2)",
)

_INITIAL_ROWS = 24
_INITIAL_COLUMNS = 80
_TIMEOUT_S = 20.0


def _spawn(
    script: str, *, rows: int = _INITIAL_ROWS, columns: int = _INITIAL_COLUMNS
) -> PosixPtyChild:
    return PosixPtyChild.spawn(
        [sys.executable, "-I", "-u", "-c", script], rows=rows, columns=columns
    )


def _read_until(
    child: PosixPtyChild, needle: str, *, timeout: float = _TIMEOUT_S
) -> str:
    """Collect decoded output until ``needle`` appears, or fail loudly.

    The deadline bounds the *wait before* each read, not merely the gaps
    between reads. ``child.read()`` blocks in a ``poll`` with no timeout by
    design — the wake byte a close writes is what ends it — so checking the
    clock only between reads left this helper with no bound at all against a
    child that goes silent, which is what
    :func:`test_read_until_fails_loudly_when_the_child_goes_silent` pins.

    Bounded in practice rather than absolutely, and the gap is worth
    knowing: once inside ``child.read()``, losing readability between the
    poll and the ``os.read`` sends ``_read_chunk`` back into
    ``_wait_until_ready``, which polls with no timeout of its own. Only a
    close ends that one. It is the same race
    :func:`test_a_read_retries_when_readability_is_lost_after_the_poll`
    injects deliberately, so it is real — but nothing else can consume this
    pty's bytes, which is why one wait here is enough in every case the
    suite produces.

    Waiting on the master descriptor here rather than giving ``read`` a
    timeout keeps the binding's own read path exactly as the adapter drives
    it: a timeout parameter used by nothing but tests is a second code path
    the evidence tests would then be measuring instead of the real one.
    """
    collected = ""
    deadline = time.monotonic() + timeout
    while needle not in collected:
        assert _readable_within(child, deadline - time.monotonic()), (
            f"timed out waiting for {needle!r}; collected so far: {collected!r}"
        )
        collected += child.read()
    return collected


def _readable_within(child: PosixPtyChild, seconds: float) -> bool:
    """Report whether the child's master descriptor becomes readable in time.

    A non-positive budget is reported as "not readable" without a syscall.
    ``poll`` reads a negative timeout as *wait forever* — measured here, not
    assumed — so passing an exhausted budget straight through would spend
    the bound and then discard it, which is the failure this helper exists
    to prevent.
    """
    if seconds <= 0:
        return False
    poller = select.poll()  # type: ignore[attr-defined,unused-ignore]
    poller.register(child._master_fd, select.POLLIN)  # type: ignore[attr-defined,unused-ignore]
    return bool(poller.poll(seconds * 1000))


# --------------------------------------------------------------------------
# Probe — runs on every platform
# --------------------------------------------------------------------------


def test_the_probe_reports_support_only_on_linux() -> None:
    """The claim is Linux; every other platform fails closed.

    Decision 2 of the boundary: the probe answers before any spawn, and a
    platform the CI matrix does not verify reports unsupported rather than
    running unverified. macOS is deliberately included in "unsupported" —
    it is not that a pty cannot work there, it is that nothing here has
    ever run there.
    """
    assert _posix_pty.is_supported() is sys.platform.startswith("linux")


def test_spawn_fails_closed_where_the_probe_says_unsupported() -> None:
    if _posix_pty.is_supported():
        pytest.skip("fail-closed spawn is observable only off the claimed platform")
    with pytest.raises(_posix_pty.PosixPtyUnsupportedError):
        PosixPtyChild.spawn([sys.executable, "-c", "pass"], rows=24, columns=80)


# --------------------------------------------------------------------------
# The measurements the design refused to predict
# --------------------------------------------------------------------------

#: Reports the terminal state the child actually inherited, then waits.
#: The flag *names* are resolved in the child, against the child's own
#: ``termios``: asserting them in the parent would mean importing a
#: Unix-only module into a test module that must import on Windows, and
#: would ask the parent what the child sees instead of asking the child.
#: The binding's own ``IUTF8`` value is injected rather than resolved in the
#: child, because ``termios.IUTF8`` does not exist before Python 3.13 —
#: naming it there killed the child before it printed anything, which is how
#: the Ubuntu 3.12 leg reported this as an end-of-stream. Injecting the
#: binding's constant also stops this from becoming a second copy of a value
#: that must agree with the one the binding sets.
_TERMIOS_CHILD = (
    f"_IUTF8 = {_posix_pty._IUTF8}\n"
    + """
import os, sys, termios
a = termios.tcgetattr(0)
iflag, oflag, lflag = a[0], a[1], a[3]
for name, flag, value in (
    ("OPOST", "oflag", termios.OPOST),
    ("ONLCR", "oflag", termios.ONLCR),
    ("ECHO", "lflag", termios.ECHO),
    ("ICANON", "lflag", termios.ICANON),
    ("ISIG", "lflag", termios.ISIG),
    ("ICRNL", "iflag", termios.ICRNL),
    ("IUTF8", "iflag", _IUTF8),
    ("ECHOE", "lflag", termios.ECHOE),
    ("ECHOK", "lflag", termios.ECHOK),
    ("ECHOKE", "lflag", termios.ECHOKE),
    ("IXON", "iflag", termios.IXON),
    ("ECHOCTL", "lflag", termios.ECHOCTL),
    ("IEXTEN", "lflag", termios.IEXTEN),
):
    print(name, bool({"iflag": iflag, "oflag": oflag, "lflag": lflag}[flag] & value))
print("CTTY", os.ttyname(0))
print("SID", os.getsid(0) == os.getpid())
# The two that actually require a *controlling* terminal. Opening
# /dev/tty fails ENXIO for a session leader that has none, and
# tcgetpgrp fails ENOTTY on a terminal that is not the caller's
# controlling one. Neither getsid nor ttyname can tell the difference,
# which is why they alone left the trampoline's ioctl unpinned.
try:
    tty_fd = os.open("/dev/tty", os.O_RDWR)
    os.close(tty_fd)
    print("DEVTTY True")
except OSError as error:
    print("DEVTTY False", error.errno)
try:
    print("FGPGRP", os.tcgetpgrp(0) == os.getpgrp())
except OSError as error:
    print("FGPGRP False", error.errno)
print("READY")
sys.stdin.readline()
"""
)


@_LINUX_ONLY
def test_the_child_inherits_the_line_discipline_the_binding_set() -> None:
    """Measured, not assumed — and it is deliberately *not* raw mode.

    Design rule 5 requires the discipline to be explicit and recorded. It
    does not require raw: a subject under TermVerify should see the
    terminal a person's subject sees, which post-processes output and
    echoes input. A subject that wants raw calls ``tcsetattr`` itself and
    wins, exactly as on a real terminal.
    """
    child = _spawn(_TERMIOS_CHILD)
    try:
        output = _read_until(child, "READY")
        for flag, expected, why in (
            ("OPOST", True, "output post-processing must be on"),
            ("ONLCR", True, "newline translation must be on"),
            ("ECHO", True, "a conventional terminal echoes"),
            ("ICANON", True, "a conventional terminal is canonical"),
            ("ISIG", True, "a conventional terminal generates signals"),
            ("ICRNL", True, "a conventional terminal maps CR to NL"),
            # The editing echoes, which travel together. ECHOE was always
            # on while ECHOK and ECHOKE were off, unremarked — an erase
            # echoed as a person would see it, a kill echoed nothing,
            # although this binding installs ^U as cc[VKILL] itself. There
            # is no reading under which those are different decisions, and
            # the conventional one is what the module argues for.
            ("ECHOE", True, "the erase character echoes as a person's does"),
            ("ECHOK", True, "so does the kill character this module installs"),
            ("ECHOKE", True, "and it erases the line rather than adding one"),
            ("IUTF8", True, "erasing a multibyte character erases the character"),
            # These three are ON in the kernel default and the binding
            # turns them OFF, so they are what makes this test able to
            # fail: with the configuration removed, the child would report
            # them True. IXON would let a harness write of 0x13 stall the
            # evidence stream; ECHOCTL and IEXTEN would echo harness bytes
            # back in expanded forms the subject never produced.
            ("IXON", False, "flow control must not be able to stall evidence"),
            ("ECHOCTL", False, "control bytes must not echo as ^X"),
            ("IEXTEN", False, "no implementation-defined input processing"),
        ):
            assert f"{flag} {expected}" in output, f"{why}; child reported: {output!r}"
    finally:
        child.close(force=True)


@_LINUX_ONLY
def test_configuring_the_line_discipline_is_idempotent_and_measured() -> None:
    """What a fresh pty hands back, recorded instead of predicted.

    The boundary design refused to state this, and the issue asked for it
    to be established on the legs that run. Whatever the default is, the
    binding's configured state must hold afterwards — that is the contract
    ``_configure_line_discipline`` exists to create, and this is the test
    that would fail if a future kernel default silently changed the
    evidence a subject produces.
    """
    master_fd, slave_fd = os.openpty()  # type: ignore[attr-defined,unused-ignore]
    try:
        inherited = _posix_pty.terminal_flags(slave_fd)
        # Wipe the three flag words first. Without this the test cannot
        # fail: a fresh Linux pty already carries every flag the binding
        # sets, so configuring is indistinguishable from doing nothing —
        # the review's finding, and it was right. Deleting the body of
        # _configure_line_discipline must break this test.
        _posix_pty.set_terminal_flags(slave_fd, 0, 0, 0)
        assert _posix_pty.terminal_flags(slave_fd) == (0, 0, 0)
        _posix_pty._configure_line_discipline(slave_fd)
        once = _posix_pty.terminal_flags(slave_fd)
        _posix_pty._configure_line_discipline(slave_fd)
        twice = _posix_pty.terminal_flags(slave_fd)
    finally:
        os.close(master_fd)
        os.close(slave_fd)
    assert once != (0, 0, 0), "configuration set nothing at all"
    assert once == twice, (
        f"configuring the line discipline is not idempotent:"
        f" inherited={inherited} once={once} twice={twice}"
    )
    # `inherited` is deliberately not asserted on: pinning it would pin the
    # kernel's choice rather than the binding's contract, and the design
    # refused to predict it. It rides in the message above so a future
    # divergence is visible wherever it breaks something.


#: Flag names, by word, resolved against the running kernel's ``termios``.
#: Only single-bit flags, and the delay masks were measured rather than
#: assumed to be otherwise: on Linux ``NLDLY`` (0x100), ``BSDLY`` (0x2000),
#: ``VTDLY`` (0x4000) and ``FFDLY`` (0x8000) are single bits and are listed
#: like any other, while ``CRDLY`` (0x600) and ``TABDLY`` (0x1800) are the
#: two genuinely multi-bit fields — a *changed bit* named through those would
#: report nonsense, since their zero value is a legitimate setting. The
#: coverage assertion below is what stops that pair's exclusion from hiding a
#: real change.
_FLAG_NAMES: dict[str, tuple[str, ...]] = {
    "iflag": (
        "IGNBRK",
        "BRKINT",
        "IGNPAR",
        "PARMRK",
        "INPCK",
        "ISTRIP",
        "INLCR",
        "IGNCR",
        "ICRNL",
        "IUCLC",
        "IXON",
        "IXANY",
        "IXOFF",
        "IMAXBEL",
        "IUTF8",
    ),
    "oflag": (
        "OPOST",
        "OLCUC",
        "ONLCR",
        "OCRNL",
        "ONOCR",
        "ONLRET",
        "OFILL",
        "OFDEL",
        "NLDLY",
        "BSDLY",
        "VTDLY",
        "FFDLY",
    ),
    "lflag": (
        "ISIG",
        "ICANON",
        "XCASE",
        "ECHO",
        "ECHOE",
        "ECHOK",
        "ECHONL",
        "NOFLSH",
        "TOSTOP",
        "ECHOCTL",
        "ECHOPRT",
        "ECHOKE",
        "FLUSHO",
        "PENDIN",
        "IEXTEN",
        "EXTPROC",
    ),
}


#: Every flag `_configure_line_discipline` states it chooses against the
#: conventional terminal. Anything else it changes is an unnamed deviation.
_NAMED_DEVIATIONS = frozenset({"IXON", "ECHOCTL", "IEXTEN", "IUTF8"})


def _flag_bit(name: str) -> int:
    """Resolve one flag by name, falling back to the binding's constant.

    Only ``IUTF8`` needs the fallback, and it needs it on exactly the leg
    where the binding is supplying the value itself: ``termios.IUTF8`` does
    not exist before Python 3.13, so a table asking only ``termios`` would
    be unable to name the one bit whose absence started this — and would
    then report the binding's own deviation as an *unnameable* changed bit.
    """
    import termios

    if name == "IUTF8":
        return getattr(termios, "IUTF8", _posix_pty._IUTF8)
    return getattr(termios, name, 0)


def _named_changed_flags(word: str, before: int, after: int) -> set[str]:
    """Name every bit that differs between two values of one flag word.

    Fails rather than under-reports: a changed bit this module cannot name
    is exactly the silent deviation the caller is asking about, so it is
    surfaced as its own assertion instead of being dropped.
    """
    changed = before ^ after
    named: set[str] = set()
    covered = 0
    for name in _FLAG_NAMES[word]:
        bit = _flag_bit(name)
        if bit and changed & bit == bit:
            named.add(name)
            covered |= bit
    assert covered == changed, (
        f"{word} changed bits this test cannot name:"
        f" {changed & ~covered:#x} (before={before:#x} after={after:#x})"
    )
    return named


@_LINUX_ONLY
def test_the_configured_discipline_deviates_from_the_default_only_as_stated() -> None:
    """Every deviation from the kernel default is named, or this fails.

    The function's own rule is that a choice which costs something is named
    rather than left to be discovered, and its docstring named three. It
    made **six** on 3.13 and later: ``ECHOK`` off, ``ECHOKE`` off and
    ``IUTF8`` on were unremarked, and nothing pinned them —
    ``_TERMIOS_CHILD`` checked nine flags and none of these. On 3.12 it made
    five, of which two were unnamed, because ``termios.IUTF8`` does not
    exist there and the flag was not being set at all; that discrepancy was
    itself the defect ``_IUTF8`` now removes.

    With ``ECHOK`` and ``ECHOKE`` off, the ``^U`` this module explicitly
    installs as ``cc[VKILL]`` killed the line and echoed nothing, where the
    default erases it — so a harness-written kill produced different
    transcript bytes for a reason no reader could find.

    The deviation set is *measured against the running kernel* rather than
    spelled out here. Hardcoding the expected words would restate the
    implementation and pass by construction; comparing configured against
    inherited pins what the binding changes about the terminal a person
    would get — which is the contract — and leaves the default itself
    unpinned, as the design decided.

    **Asserted as a subset, and only this direction is sound.** Which named
    choices *show up* as deviations depends on the kernel: ``IUTF8`` is a
    deviation on the kernel this was written against and would silently
    stop being one on a kernel that already defaults it on. So a lost
    deviation cannot be detected here at all — turning ``IXON`` back on
    would shrink the set and still pass. That direction is
    :func:`test_the_child_inherits_the_line_discipline_the_binding_set`'s
    job, which asserts the absolute state the child sees and does not
    depend on any default.
    """
    master_fd, slave_fd = os.openpty()  # type: ignore[attr-defined,unused-ignore]
    try:
        inherited = _posix_pty.terminal_flags(slave_fd)
        _posix_pty._configure_line_discipline(slave_fd)
        configured = _posix_pty.terminal_flags(slave_fd)
    finally:
        os.close(master_fd)
        os.close(slave_fd)
    deviations = set()
    for index, word in enumerate(("iflag", "oflag", "lflag")):
        deviations |= _named_changed_flags(word, inherited[index], configured[index])
    assert deviations <= _NAMED_DEVIATIONS, (
        f"the binding deviates from this kernel's default in flags"
        f" `_configure_line_discipline` does not name:"
        f" {sorted(deviations - _NAMED_DEVIATIONS)}"
    )


@_LINUX_ONLY
def test_the_supplied_iutf8_constant_matches_the_interpreters_own() -> None:
    """The one assumption the supplied constant introduces, checked.

    `_IUTF8` exists because ``termios.IUTF8`` arrives only in Python 3.13,
    and reading it defensively left the flag *off* on 3.12 — the same
    subject erasing a multibyte character differently depending on which
    interpreter drove the harness. Supplying the value fixes that and buys
    one assumption in exchange: that the bit is the one Linux's
    ``asm-generic/termbits.h`` defines.

    This is where that assumption is paid for, and the coverage is narrower
    than it first looks. The comparison needs a Linux host *and* an
    interpreter that has the constant, so it runs on Ubuntu 3.13 and Ubuntu
    3.14 — **two of the six matrix legs**, two of the three that can run
    this binding at all. It is skipped on Windows by the marker (there is
    no ``termios`` to compare against) and on 3.12 by the guard below,
    which is precisely the leg the constant exists for. An architecture
    whose termios bits differ from the generic ones fails here; an
    architecture that only ever runs 3.12 does not.
    """
    import termios

    if not hasattr(termios, "IUTF8"):
        pytest.skip("this interpreter has no termios.IUTF8 to compare against")
    assert _posix_pty._IUTF8 == termios.IUTF8


@_LINUX_ONLY
def test_a_changed_flag_with_no_name_is_reported_rather_than_dropped() -> None:
    """The flag tables above are not exhaustive, so silence would be the bug.

    ``_named_changed_flags`` reports deviations *by name*, and the test that
    consumes it asserts over the names — so a changed bit the tables cannot
    name would be dropped, and the deviation check would pass while the
    binding quietly changed something. The tables deliberately omit the
    multi-bit delay masks, which is exactly the kind of gap that makes this
    escape hatch necessary rather than theoretical.
    """
    assert _named_changed_flags("lflag", 0, 0) == set()
    with pytest.raises(AssertionError, match="cannot name"):
        _named_changed_flags("lflag", 0, 1 << 30)


@_LINUX_ONLY
def test_the_child_is_a_session_leader_with_a_controlling_terminal() -> None:
    """The reason the binding spawns through a trampoline.

    Without a controlling terminal there is no foreground process group,
    so the kernel delivers no ``SIGWINCH`` and the subject cannot open
    ``/dev/tty``.

    **The first two assertions cannot detect that, and used to be the
    whole test.** ``getsid`` reports the session ``start_new_session``
    already created, and ``ttyname(0)`` only resolves the descriptor's
    path — both are true of a child with no controlling terminal at all,
    so deleting the trampoline's ``TIOCSCTTY`` left the entire suite
    green. They are kept because they pin the *session*, which is what
    the teardown's ``killpg`` depends on; the two below are what pin the
    controlling terminal, and removing that ioctl must now fail here.
    """
    child = _spawn(_TERMIOS_CHILD)
    try:
        output = _read_until(child, "READY")
        assert "SID True" in output, f"child is not a session leader: {output!r}"
        assert "CTTY /dev/pts/" in output, f"child has no pty on fd 0: {output!r}"
        assert "DEVTTY True" in output, (
            f"the child cannot open /dev/tty, so it has no controlling"
            f" terminal: {output!r}"
        )
        assert "FGPGRP True" in output, (
            f"the child is not the foreground process group of its terminal,"
            f" so no SIGWINCH will reach it: {output!r}"
        )
    finally:
        child.close(force=True)


@_LINUX_ONLY
def test_end_of_stream_is_reported_once_the_child_and_its_slave_are_gone() -> None:
    """Measured: Linux reports ``EIO``, not an empty read.

    The binding normalizes whatever the platform does into its own
    end-of-stream signal, and the exit record is captured with it — the
    child has exited by definition at that point, so the bounded wait is a
    reaping delay and never a liveness guess.
    """
    child = _spawn("print('BYE')")
    try:
        _read_until(child, "BYE")
        with pytest.raises(PosixPtyEndOfStreamError):
            for _ in range(100):
                child.read()
        assert child.exit_status == 0
    finally:
        child.close(force=True)


#: Exits mid-codepoint: five ASCII bytes and then two of the three bytes of
#: U+20AC EURO SIGN, which nothing will ever complete. A subject killed
#: inside a ``write`` leaves the same shape behind — reasoned, not measured
#: here, and the reasoning is that a partial write puts fewer than all the
#: bytes of the final codepoint into the pty.
#:
#: What does **not** produce this shape, though issue #279 listed it as a
#: second cause: a pty splitting a subject's final character across reads.
#: On Linux — the only platform this binding claims, and where the
#: end-of-stream signal is ``EIO`` rather than an empty read — the master
#: reports it only once its buffer is drained *and* the last slave is gone,
#: so every byte the subject did write is delivered before end-of-stream and
#: the incremental decoder heals the split. What can still be held at
#: end-of-stream is therefore only a sequence whose *remaining* bytes the
#: subject never wrote.
_TRUNCATED_TAIL_CHILD = (
    "import sys\n"
    "sys.stdout.buffer.write(b'START')\n"
    "sys.stdout.buffer.write(b'\\xe2\\x82')\n"
    "sys.stdout.buffer.flush()\n"
)

#: The control for the test below: the same shape with the codepoint
#: *complete*, so a flush that invented a replacement would be visible.
_COMPLETE_TAIL_CHILD = (
    "import sys\n"
    "sys.stdout.buffer.write(b'START')\n"
    "sys.stdout.buffer.write(b'\\xe2\\x82\\xac')\n"
    "sys.stdout.buffer.flush()\n"
)


@_LINUX_ONLY
def test_a_truncated_trailing_codepoint_surfaces_rather_than_vanishing() -> None:
    """Bytes the binding received must not leave the evidence unmarked.

    A pty is a byte conduit with no decoder in it, so the subject's
    unfinished sequence arrives here verbatim and the incremental decoder
    holds it — correctly, while more bytes could still complete it. At
    end-of-stream nothing can, and issue #279 measured what happened next:
    the two bytes were discarded and the transcript asserted the subject
    produced ``START`` and nothing more, which is false.

    They are flushed as replacement text on the read that meets
    end-of-stream, and the end-of-stream is raised by the read after that —
    the contract ``TerminalEndOfStreamError`` states and the ConPTY binding
    already honored.
    """
    child = _spawn(_TRUNCATED_TAIL_CHILD)
    try:
        collected = _read_until(child, "START")
        with pytest.raises(PosixPtyEndOfStreamError):
            for _ in range(100):
                collected += child.read()
        assert collected == "START�"
        assert child.exit_status == 0
    finally:
        child.close(force=True)


@_LINUX_ONLY
@pytest.mark.parametrize("row", _TAILS, ids=lambda row: row.name)
def test_the_end_of_stream_tail_table_holds_on_this_host(row: Tail) -> None:
    """Every row of the divergence table, measured against a real pty.

    The Windows twin of this is
    ``tests/test_conpty_binding.py::test_the_end_of_stream_tail_table_holds_on_this_host``,
    and both parametrize over the same data in
    ``tests/_end_of_stream_tails.py``, which is also where the rule the table
    measures is written down. Only some of these rows are #279's doing — the
    ``opened_by_279`` column says which, and the ones that are not are issue
    #282 — but all of them are stated in ``_terminal_binding.py``, and the
    round-2 review of #279 found eight rows stated and pinned by nothing.
    """
    child = _spawn(subject_script(row.tail))
    try:
        collected = _read_until(child, "START")
        with pytest.raises(PosixPtyEndOfStreamError):
            for _ in range(100):
                collected += child.read()
        assert collected == row.posix, (
            f"the pty binding rendered {row.name} ({row.tail!r}) as"
            f" {collected!r}, not {row.posix!r}. The divergence table in"
            f" _terminal_binding.py was written on the old measurement."
        )
        assert child.exit_status == 0
    finally:
        child.close(force=True)


@_LINUX_ONLY
def test_a_close_in_the_flush_gap_cannot_lose_the_end_of_stream() -> None:
    """The hazard the one-call deferral creates, and the latch that closes it.

    Deferring the end-of-stream by one call opens a gap: the read that met it
    returned text, and the read that would raise it has not happened yet. A
    close landing in that gap used to turn the run's ending into
    :class:`PosixPtyClosedError`, which the adapter classifies as a *failure*
    — so a subject that exited 0 and whose exit record had already been
    captured would be reported as a binding closed outside the abort
    deadline. The watchdog's expiry is exactly such a close, so this is
    reachable rather than theoretical, and it was measured by the round-2
    adversarial review of #279.

    A stream that has ended cannot un-end, so the binding latches it: once
    end-of-stream has been observed, a later close does not overwrite it and
    ``read`` keeps reporting the truth. That is also what makes the
    "never dropped" half of
    :class:`~termverify._terminal_binding.TerminalEndOfStreamError`'s
    contract true rather than aspirational.
    """
    child = _spawn(_TRUNCATED_TAIL_CHILD)
    try:
        collected = _read_until(child, "START")
        # Read to exactly the flush — the moment the gap opens.
        deadline = time.monotonic() + _TIMEOUT_S
        while "�" not in collected:
            assert time.monotonic() < deadline, (
                f"the flush never arrived; collected {collected!r}"
            )
            collected += child.read()
        assert collected == "START�"
        assert child.exit_status == 0

        # The close lands in the gap, exactly as the watchdog's would.
        child.close(force=True)

        with pytest.raises(PosixPtyEndOfStreamError):
            child.read()
        assert child.exit_status == 0
    finally:
        child.close(force=True)


@_LINUX_ONLY
def test_a_complete_trailing_codepoint_gains_no_replacement() -> None:
    """The flush must report a truncation, never manufacture one.

    Without this, a flush that returned ``U+FFFD`` unconditionally would
    pass the test above while corrupting every run that ended on a
    multibyte character.
    """
    child = _spawn(_COMPLETE_TAIL_CHILD)
    try:
        collected = _read_until(child, "START")
        with pytest.raises(PosixPtyEndOfStreamError):
            for _ in range(100):
                collected += child.read()
        assert collected == "START€"
        assert child.exit_status == 0
    finally:
        child.close(force=True)


# --------------------------------------------------------------------------
# Geometry
# --------------------------------------------------------------------------

#: Reports its window size on demand: once at startup, then once per line
#: of input. Deliberately not driven by ``SIGWINCH`` — proving the geometry
#: changed and proving the signal arrives are different claims, and the
#: signal is issue #269's evidence.
_GEOMETRY_CHILD = """
import os, sys
def report():
    size = os.get_terminal_size(0)
    print("SIZE", size.lines, size.columns)
for line in iter(sys.stdin.readline, ''):
    report()
"""


@_LINUX_ONLY
def test_the_child_observes_the_creation_geometry() -> None:
    """The needle is the whole expected line, and that is not cosmetic.

    Waiting for a *prefix* of what is then asserted is a race the reader
    loses roughly whenever the pty splits the line: the wait is satisfied by
    ``SIZE`` while the digits are still in the kernel, and the assertion
    then fails on output that was about to arrive. It cost a red on the
    Ubuntu 3.14 leg — not here, but in
    :func:`test_the_environment_overlay_and_cwd_compose_inside_the_binding`,
    which had the same shape with ``TV `` for a needle. These two geometry
    tests were found by looking for the shape, not by failing. The full text
    costs nothing — ``_read_until`` reports everything it collected when it
    times out, so a genuinely wrong geometry still says what it saw.
    """
    child = _spawn(_GEOMETRY_CHILD, rows=30, columns=100)
    try:
        child.write("go\n")
        assert "SIZE 30 100" in _read_until(child, "SIZE 30 100")
    finally:
        child.close(force=True)


@_LINUX_ONLY
def test_the_child_observes_a_resized_geometry() -> None:
    child = _spawn(_GEOMETRY_CHILD, rows=30, columns=100)
    try:
        child.write("go\n")
        _read_until(child, "SIZE 30 100")
        child.resize(rows=12, columns=40)
        child.write("go\n")
        assert "SIZE 12 40" in _read_until(child, "SIZE 12 40")
    finally:
        child.close(force=True)


@_LINUX_ONLY
def test_the_kernel_applies_a_geometry_the_windows_console_would_substitute() -> None:
    """The POSIX band is wider than ConPTY's, and this measures it.

    Issue #228 recorded that the Windows console silently substitutes
    geometries outside its own band, so its receipt claims more than it
    delivers. The claim here is only what this test observes.
    """
    child = _spawn(_GEOMETRY_CHILD, rows=200, columns=500)
    try:
        child.write("go\n")
        assert "SIZE 200 500" in _read_until(child, "SIZE 200 500")
    finally:
        child.close(force=True)


# --------------------------------------------------------------------------
# I/O discipline and teardown
# --------------------------------------------------------------------------


@_LINUX_ONLY
def test_a_second_concurrent_read_wears_its_own_error() -> None:
    """A harness defect never wears a subject failure code (issue #261)."""
    child = _spawn("import sys; sys.stdin.readline()")
    started = threading.Event()
    failures: list[BaseException] = []

    def blocked_read() -> None:
        started.set()
        try:
            child.read()
        except BaseException as error:  # noqa: BLE001 - recorded for the assert
            failures.append(error)

    reader = threading.Thread(target=blocked_read, daemon=True)
    reader.start()
    assert started.wait(_TIMEOUT_S)
    try:
        # Wait for the read to be *in flight*, not merely for the thread to
        # have started. The earlier version raced: if this thread's read won,
        # it blocked in `poll` on a silent child with nothing to wake it, and
        # the close that would have freed it sits after the loop — an
        # indefinite hang rather than a failure, with no pytest-timeout
        # configured to end it.
        deadline = time.monotonic() + _TIMEOUT_S
        while not child._read_in_flight:
            assert time.monotonic() < deadline, "the reader never reached the poll"
            time.sleep(0.01)
        with pytest.raises(PosixPtyConcurrentIOError):
            child.read()
    finally:
        child.close(force=True)
    reader.join(_TIMEOUT_S)
    assert not reader.is_alive()
    assert failures and isinstance(failures[0], PosixPtyClosedError)


@_LINUX_ONLY
def test_a_blocked_read_is_woken_by_a_forced_close() -> None:
    """The self-pipe, not containment, is what ends a blocked read.

    A close must not depend on reaching whoever holds the other end — the
    finding (R4) that shaped the JSONL binding's POSIX path.

    **Both halves of the arrangement are load-bearing, and the earlier form
    had neither.** It slept 0.2s and asserted only the exception *type*. If
    the reader had not reached the read when the close landed, the read was
    rejected by the top guard with ``PosixPtyClosedError("the POSIX PTY
    binding is closed")`` — the same type, from a path that never touches
    the self-pipe this test is named for. So the test passed either way and
    a machine under load quietly stopped testing the guarantee. The spin
    below is the deterministic form the sibling concurrency test already
    uses, and the message is what tells the two paths apart: only an
    interrupted read says "closed *during* a read".

    **And neither of those was enough either — the timing is the third
    load-bearing part.** Pointing ``read`` at the wrong end of the wake pipe
    left this test green: the reader is never signalled, the teardown's
    delivery wait expires after ``_IO_DELIVERY_WAIT_S``, and only then
    does ``_release_descriptors`` free the pipe, whose closure the blocked
    ``poll`` reports as ``POLLERR`` regardless of the mask it asked for. So
    the read *was* woken, with the right type and the right message — by a
    descriptor being freed underneath a blocked syscall after the teardown
    gave up waiting for it, which is the precise hazard ``close``'s ordering
    exists to prevent. Measured: 0.02s when the wake byte arrives, 5.03s
    when it does not. Only the clock can tell those apart.
    """
    child = _spawn("import sys; sys.stdin.readline()")
    woken = threading.Event()
    failures: list[BaseException] = []
    woken_at: list[float] = []

    def blocked_read() -> None:
        try:
            child.read()
        except BaseException as error:  # noqa: BLE001 - recorded for the assert
            failures.append(error)
        finally:
            woken_at.append(time.monotonic())
            woken.set()

    reader = threading.Thread(target=blocked_read, daemon=True)
    reader.start()
    deadline = time.monotonic() + _TIMEOUT_S
    while not child._read_in_flight:
        assert time.monotonic() < deadline, "the reader never reached the read"
        time.sleep(0.01)
    closed_at = time.monotonic()
    child.close(force=True)
    assert woken.wait(_TIMEOUT_S), "the blocked read was never woken"
    assert failures and isinstance(failures[0], PosixPtyClosedError)
    assert "closed during a read" in str(failures[0]), (
        f"the read was rejected before it began, so the self-pipe was never"
        f" exercised: {failures[0]!r}"
    )
    elapsed = woken_at[0] - closed_at
    assert elapsed < _posix_pty._IO_DELIVERY_WAIT_S / 2, (
        f"the read took {elapsed:.2f}s to wake against a"
        f" {_posix_pty._IO_DELIVERY_WAIT_S}s delivery wait, so what freed it was the"
        f" teardown giving up and closing the pipe, not the wake byte"
    )


@_LINUX_ONLY
def test_a_close_does_not_flush_the_decoder_the_way_end_of_stream_does() -> None:
    """The asymmetry the end-of-stream flush is only correct because of.

    A truncated tail is evidence that the subject left a sequence
    unfinished — but only when the stream *ended*. A close may have
    abandoned output the child had already written, so the same held bytes
    establish nothing, and turning them into a ``U+FFFD`` would put a
    character into a transcript on the strength of a teardown.

    Nothing in the suite forbade that. Two mutations were run against it, and
    both left every *other* test green because their decoders are empty by
    the time a close lands: widening ``read``'s handler to
    ``except (PosixPtyEndOfStreamError, PosixPtyClosedError)``, and widening
    it all the way to ``except Exception``. Only this test reds. Both halves
    of the arrangement are why — it **proves its own precondition**, reading
    the parked tail back out of the decoder rather than assuming it is there,
    and then repeats the blocked-read spin the sibling test above uses so the
    close lands on a read that is genuinely in flight.

    A third mutation is what the tail of this test covers: moving the flush
    *above* ``read``'s closed-binding guard, so a read arriving after the
    teardown returns the held bytes instead of raising. That path is adjacent
    to this one and was unpinned until an adversarial review of #279 measured
    it surviving.
    """
    child = _spawn(
        "import sys\n"
        "sys.stdout.buffer.write(b'START')\n"
        "sys.stdout.buffer.write(b'\\xe2\\x82')\n"
        "sys.stdout.buffer.flush()\n"
        "sys.stdin.readline()\n"
    )
    try:
        _read_until(child, "START")
        deadline = time.monotonic() + _TIMEOUT_S
        while child._decoder.getstate()[0] != b"\xe2\x82":
            assert _readable_within(child, deadline - time.monotonic()), (
                "the truncated tail never reached the decoder, so this test"
                " would have proven nothing about flushing it"
            )
            assert child.read() == "", "the tail decoded to text of its own"
        # The precondition, stated as an assertion rather than as a hope.
        assert child._decoder.getstate()[0] == b"\xe2\x82"

        returned: list[str] = []
        failures: list[BaseException] = []
        woken = threading.Event()

        def blocked_read() -> None:
            try:
                returned.append(child.read())
            except BaseException as error:  # noqa: BLE001 - recorded for the assert
                failures.append(error)
            finally:
                woken.set()

        reader = threading.Thread(target=blocked_read, daemon=True)
        reader.start()
        deadline = time.monotonic() + _TIMEOUT_S
        while not child._read_in_flight:
            assert time.monotonic() < deadline, "the reader never reached the read"
            time.sleep(0.01)
        child.close(force=True)
        assert woken.wait(_TIMEOUT_S), "the blocked read was never woken"
        assert not returned, (
            f"a close flushed the decoder and returned {returned[0]!r} as though"
            " the subject had truncated its own output"
        )
        assert failures and isinstance(failures[0], PosixPtyClosedError)
        assert "closed during a read" in str(failures[0]), (
            f"the read was rejected before it began, so the flush path this"
            f" test is named for was never reached: {failures[0]!r}"
        )

        # The adjacent path, and the tail is still parked: a read that the
        # closed-binding guard *rejects* must not flush either. Nothing
        # forbade moving the flush above that guard until this line.
        assert child._decoder.getstate()[0] == b"\xe2\x82"
        with pytest.raises(PosixPtyClosedError) as rejected:
            child.read()
        assert "binding is closed" in str(rejected.value), (
            f"a read after the teardown reported something other than the"
            f" closed binding: {rejected.value!r}"
        )
    finally:
        child.close(force=True)


@_LINUX_ONLY
def test_a_write_that_cannot_proceed_watches_the_wake_pipe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The write side's half of the wake guarantee, which nothing exercised.

    ``test_a_write_woken_by_a_close_reports_the_closed_binding`` patches
    ``_wait_until_ready`` to answer "woken", so it proves the raise and
    never the wake. Pointing ``write`` at the wrong end of the wake pipe
    left the whole suite green.

    **The first attempt at this test was wrong about the platform, and CI
    said so.** It tried to block a real write by giving a non-reading child
    more bytes than the pty would buffer — but a pty in canonical mode
    *discards* input once its queue is full rather than pushing back on the
    master, so the write can simply complete. It passed on five matrix legs
    on the timing of the echo queue and failed on the sixth. A test whose
    premise is "this syscall will block" needs the platform to guarantee
    that, and this one does not.

    So the block is injected instead: every write to the master reports
    ``BlockingIOError``, which is the state ``_write_all`` is written for,
    and the loop then turns entirely on what ``_wait_until_ready`` says
    about the wake pipe. Deterministic on every leg, and it fails rather
    than hangs — with the wrong end polled, the loop never sees a wake and
    the bounded wait below reports it.

    What this does *not* cover is a genuinely blocked ``os.write`` being
    freed by the wake byte, and ``close``'s wait for that write's delivery.
    Both are recorded in #278 rather than pinned by something flaky.
    """
    child = _spawn("import time; time.sleep(300)")
    woken = threading.Event()
    failures: list[BaseException] = []
    real_write = os.write

    def never_ready(fd: int, data: object) -> int:
        # Only the master. The wake byte `close` writes must get through,
        # or this arranges the very failure it is checking for.
        if fd == child._master_fd:
            raise BlockingIOError
        return real_write(fd, data)  # type: ignore[arg-type]

    def spinning_write() -> None:
        try:
            child.write("x")
        except BaseException as error:  # noqa: BLE001 - recorded for the assert
            failures.append(error)
        finally:
            woken.set()

    monkeypatch.setattr(os, "write", never_ready)
    writer = threading.Thread(target=spinning_write, daemon=True)
    writer.start()
    deadline = time.monotonic() + _TIMEOUT_S
    while not child._write_in_flight:
        assert time.monotonic() < deadline, "the writer never reached the write"
        time.sleep(0.01)
    try:
        child.close(force=True)
        assert woken.wait(_TIMEOUT_S), (
            "the write never observed the wake pipe: it is watching a"
            " descriptor a close does not signal"
        )
        assert failures and isinstance(failures[0], PosixPtyClosedError), failures
        assert "closed during a write" in str(failures[0]), failures[0]
    finally:
        monkeypatch.undo()
        writer.join(_TIMEOUT_S)


@_LINUX_ONLY
def test_a_forced_close_kills_the_session_and_records_the_real_exit() -> None:
    child = _spawn("import time; time.sleep(300)")
    pid = child.pid
    child.close(force=True)
    assert child.exit_status == -FORCED_TERMINATION_SIGNAL
    with pytest.raises(OSError):
        os.kill(pid, 0)


@_LINUX_ONLY
def test_a_release_only_close_of_a_live_child_is_refused() -> None:
    """Silently abandoning a live pty child has no honest reading.

    The refusal must **not** wear ``PosixPtyClosedError``: that type means
    "the binding is closed" everywhere else, so the natural idiom
    ``except PosixPtyClosedError: pass`` around a release-only close would
    turn a refusal-to-abandon into a leaked live child holding the pty.
    The binding is still open afterwards, which is the other half.

    It wears its own type rather than a bare ``RuntimeError``, which is the
    supertype of three of this module's four other error types — see
    :func:`test_the_live_child_refusal_catches_nothing_else`.
    """
    child = _spawn("import time; time.sleep(300)")
    try:
        with pytest.raises(_posix_pty.PosixPtyLiveChildError) as caught:
            child.close(force=False)
        assert not isinstance(caught.value, PosixPtyClosedError)
        assert child.is_alive()
        # Still usable, not half-closed.
        child.resize(rows=10, columns=20)
    finally:
        child.close(force=True)


def test_the_live_child_refusal_catches_nothing_else() -> None:
    """A refusal type must not be a supertype of the failures around it.

    The refusal used to raise a bare ``RuntimeError``, which three of this
    module's four other error types derive from — so ``except RuntimeError``
    written for a release-only close silently swallowed a closed binding, a
    single-flight violation and an unsupported host as well. That is the
    same defect the test above pins from the other side, and it is why
    ``PosixPtyClosedError`` was not simply reused.

    A type relationship is not platform evidence, so this runs everywhere.
    """
    others = (
        _posix_pty.PosixPtyUnsupportedError,
        PosixPtyClosedError,
        PosixPtyConcurrentIOError,
        PosixPtyEndOfStreamError,
    )
    for other in others:
        assert not issubclass(other, _posix_pty.PosixPtyLiveChildError), (
            f"{other.__name__} would be caught by a handler written for the"
            f" release-only refusal"
        )
    assert sum(issubclass(other, RuntimeError) for other in others) == 3, (
        "the breadth that made a bare RuntimeError wrong has changed; the"
        " refusal's type needs re-deciding rather than re-asserting"
    )
    # The other direction, and the loop above cannot see it: the assertions
    # there hold trivially while this type is a leaf, so making it derive
    # from a *neutral* kind passes all of them. `TerminalClosedError` is the
    # one that matters — `terminal.py` catches it, so the refusal would
    # become adapter-classified evidence, which is exactly what this type
    # exists to prevent and what `_terminal_binding.py` states it is not.
    for kind in (
        TerminalClosedError,
        TerminalConcurrentIOError,
        TerminalEndOfStreamError,
        TerminalGeometryMismatchError,
        TerminalUnsupportedError,
    ):
        assert not issubclass(_posix_pty.PosixPtyLiveChildError, kind), (
            f"the refusal derives from {kind.__name__}, so the adapter would"
            f" classify it as evidence about the subject"
        )


@_LINUX_ONLY
def test_every_operation_after_close_reports_the_closed_binding() -> None:
    child = _spawn("import time; time.sleep(300)")
    child.close(force=True)
    for operation in (
        lambda: child.read(),
        lambda: child.write("x"),
        lambda: child.resize(rows=10, columns=10),
    ):
        with pytest.raises(PosixPtyClosedError):
            operation()
    child.close(force=True)  # idempotent


@_LINUX_ONLY
def test_a_missing_command_fails_in_the_parent_where_it_can_be_named() -> None:
    """The trampoline cannot report a missing command usefully.

    Resolution happens in the parent precisely so the failure names the
    command instead of surfacing as an opaque interpreter exit.
    """
    with pytest.raises(FileNotFoundError, match="tv-no-such-command"):
        PosixPtyChild.spawn(
            ["tv-no-such-command"], rows=_INITIAL_ROWS, columns=_INITIAL_COLUMNS
        )


@_LINUX_ONLY
def test_the_environment_overlay_and_cwd_compose_inside_the_binding() -> None:
    """The ratcheted adapter above never reads ambient state itself."""
    child = PosixPtyChild.spawn(
        [
            sys.executable,
            "-I",
            "-u",
            "-c",
            "import os; print('TV', os.environ.get('TV_MARKER'), os.getcwd())",
        ],
        rows=_INITIAL_ROWS,
        columns=_INITIAL_COLUMNS,
        env_overlay={"TV_MARKER": "overlaid"},
        cwd="/tmp",
    )
    try:
        # The needle is the whole line. Waiting for the prefix "TV " let the
        # read return with the environment value in hand and the working
        # directory still in the kernel, which is exactly how the Ubuntu
        # 3.14 leg reported `assert 'TV overlaid /tmp' in 'TV overlaid'`.
        output = _read_until(child, "TV overlaid /tmp")
        assert "TV overlaid /tmp" in output, output
    finally:
        child.close(force=True)


# --------------------------------------------------------------------------
# Failure legs
#
# Fault injection rather than luck: an untested failure leg drifts in prose
# before it drifts in code, and every one of these is a path the binding
# promises something about. Patches are scoped to the descriptor or the call
# under test, so nothing else in the process is affected.
# --------------------------------------------------------------------------


@_LINUX_ONLY
def test_an_empty_argv_names_no_subject() -> None:
    with pytest.raises(ValueError, match="argv must name a subject command"):
        PosixPtyChild.spawn([], rows=_INITIAL_ROWS, columns=_INITIAL_COLUMNS)


@_LINUX_ONLY
def test_a_failed_spawn_releases_the_master(monkeypatch: pytest.MonkeyPatch) -> None:
    """No descriptor outlives a spawn that never produced a child."""

    def refuse(*args: object, **kwargs: object) -> object:
        raise OSError("refused")

    before = len(os.listdir("/proc/self/fd"))
    monkeypatch.setattr(subprocess, "Popen", refuse)
    with pytest.raises(OSError, match="refused"):
        _spawn("pass")
    monkeypatch.undo()
    assert len(os.listdir("/proc/self/fd")) == before


@_LINUX_ONLY
def test_a_failed_construction_kills_the_child_it_cannot_adopt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The fail-closed path whose trigger is descriptor exhaustion.

    ``os.pipe`` is what fails on EMFILE/ENFILE, and it fails *after* the
    child exists — so the binding must end that child rather than leak it.
    """
    reached: list[int] = []

    def refuse(self: PosixPtyChild) -> None:
        reached.append(1)
        raise OSError("EMFILE")

    # Patched at the binding's own step rather than at ``os.pipe``:
    # ``subprocess.Popen`` opens a pipe of its own for the exec handshake,
    # so a global patch fails the *spawn* and never reaches the
    # construction path this test is about. It did exactly that on CI.
    monkeypatch.setattr(PosixPtyChild, "_adopt_wake_pipe", refuse)
    with pytest.raises(OSError, match="failed to adopt the pty descriptors") as caught:
        _spawn("import time; time.sleep(300)")
    monkeypatch.undo()
    assert reached, "the fault was never reached"
    # The contract, not just the message: no child outlives a failed spawn.
    orphan = int(str(caught.value).rsplit(maxsplit=1)[-1])
    deadline = time.monotonic() + _TIMEOUT_S
    while True:
        try:
            os.kill(orphan, 0)
        except OSError:
            break
        assert time.monotonic() < deadline, f"child {orphan} outlived a failed spawn"


@_LINUX_ONLY
def test_a_wake_pipe_that_cannot_be_configured_is_released(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``os.pipe`` is not the only fallible call in adoption.

    ``_adopt_wake_pipe`` creates the pipe and then makes three descriptors
    non-blocking, and its docstring pointed at ``spawn``'s handler for that
    second failure — but that handler releases the *master* only, so a
    failing ``os.set_blocking`` stranded both wake descriptors. The method
    that opened them releases them.

    The assertion cannot pass for the wrong reason: if the injected fault
    fired somewhere earlier, the spawn would fail with a different message
    and the ``match`` below would not hold.
    """
    reached: list[int] = []

    def refuse(fd: int, blocking: bool) -> None:
        reached.append(fd)
        raise OSError(errno.EMFILE, "injected")

    before = len(os.listdir("/proc/self/fd"))
    monkeypatch.setattr(os, "set_blocking", refuse)
    with pytest.raises(OSError, match="failed to adopt the pty descriptors"):
        _spawn("import time; time.sleep(300)")
    monkeypatch.undo()
    assert reached, "the fault was never reached"
    assert len(os.listdir("/proc/self/fd")) == before, (
        "the wake pipe outlived the adoption that opened it"
    )


#: Forks a grandchild that stays in the session, reports its pid, and then
#: both sleep. The grandchild is what a pid-only kill misses.
_FORKING_SUBJECT = """
import os, sys, time
child = os.fork()
if child == 0:
    time.sleep(300)
    os._exit(0)
print(child, flush=True)
time.sleep(300)
"""


@_LINUX_ONLY
def test_abandoning_a_spawn_ends_the_descendants_it_already_forked() -> None:
    """The group, not the pid — and no pty is needed to prove it.

    ``start_new_session=True`` puts the child in a session of its own before
    the exec, so a subject that reached ``execv`` and forked has descendants
    that signalling the pid alone leaves running. They hold the pty slave
    open, which is what stops the master reporting the hangup — so a
    survivor suppresses the end-of-stream that would otherwise be the only
    sign it was there.

    The three spawn-failure paths claim "no child outlives a failed spawn".
    That claim was false while they killed the pid, and the tests could not
    see it: their subjects never fork, so a pid kill and a group kill are
    indistinguishable there. The mutation that removes ``killpg`` survives
    every one of them, which is why this exercises the helper directly.

    **One environmental assumption, stated because this test's whole point
    is not passing for the wrong reason.** The grandchild is orphaned by the
    kill, so only PID 1 can reap it, and ``os.kill(pid, 0)`` succeeds
    against an unreaped zombie. Both legs of the declared matrix reap
    orphans; a container run without an init would spin here for the full
    timeout and report a false red rather than a false green.
    """
    process = subprocess.Popen(  # noqa: S603 - fixed argv
        [sys.executable, "-I", "-u", "-c", _FORKING_SUBJECT],
        stdout=subprocess.PIPE,
        start_new_session=True,
    )
    assert process.stdout is not None
    grandchild = int(process.stdout.readline())
    try:
        _posix_pty._abandon_spawned_child(process)
        deadline = time.monotonic() + _TIMEOUT_S
        while True:
            try:
                os.kill(grandchild, 0)
            except OSError:
                break
            assert time.monotonic() < deadline, (
                f"grandchild {grandchild} outlived the abandoned spawn; a"
                f" pid-only kill leaves the session's descendants running"
            )
            time.sleep(0.01)
    finally:
        process.stdout.close()
        with contextlib.suppress(OSError):
            os.kill(grandchild, FORCED_TERMINATION_SIGNAL)


@_LINUX_ONLY
def test_an_ordinary_close_releases_every_descriptor_the_spawn_took() -> None:
    """The success path had no descriptor accounting at all.

    Three tests count ``/proc/self/fd`` around a *failed* spawn, and none
    counted it around a successful one — so ``_release_descriptors`` could
    be emptied out entirely with the whole suite green. Deleting either the
    master's close or the wake pipe's loop leaks on **every** run rather
    than on a rare error path: a harness driving subjects in sequence, which
    is the product's ordinary mode, walks into ``EMFILE`` and first learns
    about it from an unrelated later spawn.

    The spawn is asserted to actually take descriptors, so the comparison
    cannot pass by measuring nothing.
    """
    before = len(os.listdir("/proc/self/fd"))
    child = _spawn("import time; time.sleep(300)")
    try:
        assert len(os.listdir("/proc/self/fd")) > before, (
            "the spawn took no descriptors, so releasing them proves nothing"
        )
    finally:
        child.close(force=True)
    assert len(os.listdir("/proc/self/fd")) == before, (
        "a successful close left the master or the wake pipe open"
    )


@_LINUX_ONLY
def test_a_spawn_whose_exec_status_fails_leaves_no_child_and_no_descriptor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """What the *spawn* does when the new bound fires had never run.

    This slice's headline repair is bounding the exec-status wait, and the
    bound is pinned — but only against ``_read_exec_status`` called directly
    on a pipe a test holds open. The ``OSError`` it now raises lands in a
    handler in ``_spawn_posix`` that no test had ever entered, so the thing
    the bound exists to protect was unverified: a stalled trampoline would
    have been caught by the timeout and then leaked the master and the child
    on the way out.
    """
    spawned: list[subprocess.Popen[bytes]] = []
    real_popen = subprocess.Popen

    def recording(*args: object, **kwargs: object) -> subprocess.Popen[bytes]:
        process = real_popen(*args, **kwargs)  # type: ignore[call-overload]
        spawned.append(process)
        return process  # type: ignore[no-any-return]

    def timed_out(status_read: int, *, timeout: float = 0.0) -> str | None:
        raise OSError("the subject's exec status did not arrive within 60s")

    before = len(os.listdir("/proc/self/fd"))
    monkeypatch.setattr(subprocess, "Popen", recording)
    monkeypatch.setattr(_posix_pty, "_read_exec_status", timed_out)
    with pytest.raises(OSError, match="exec status"):
        _spawn("import time; time.sleep(300)")
    monkeypatch.undo()
    assert spawned, "the fault fired before a child existed"
    deadline = time.monotonic() + _TIMEOUT_S
    while spawned[0].poll() is None:
        assert time.monotonic() < deadline, (
            f"child {spawned[0].pid} outlived the spawn that gave up on it"
        )
        time.sleep(0.01)
    # *Which* signal, not merely that it died. Releasing the master hangs up
    # the terminal, and the child is the session leader holding it — so it
    # dies of `SIGHUP` whether or not the teardown killed anything, and an
    # "it is gone" assertion passes with the kill deleted. This is what the
    # mutation harness caught in the first version of this test.
    assert spawned[0].returncode == -FORCED_TERMINATION_SIGNAL, (
        f"the child ended by signal {-spawned[0].returncode}, not by this"
        f" path's own kill; the hangup from closing the master would do that"
        f" on its own, so the teardown is unproven"
    )
    assert len(os.listdir("/proc/self/fd")) == before, (
        "the master outlived the spawn that gave up on it"
    )


@_LINUX_ONLY
def test_an_interrupt_during_the_abandon_still_releases_the_master(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Why the master's close sits in a ``finally`` and not after the reap.

    ``_abandon_spawned_child`` suppresses the failures a kill and a reap
    produce, but not an interrupt — and the reap it performs is bounded at
    thirty seconds, which is a wide window for a second Ctrl-C from someone
    who has already pressed it once. With the close written after the call
    instead of under a ``finally``, that second interrupt skips it and
    leaks the master on the way out of a spawn that is already failing.
    """
    spawned: list[subprocess.Popen[bytes]] = []
    real_popen = subprocess.Popen
    real_wait = subprocess.Popen.wait

    def recording(*args: object, **kwargs: object) -> subprocess.Popen[bytes]:
        process = real_popen(*args, **kwargs)  # type: ignore[call-overload]
        spawned.append(process)
        return process  # type: ignore[no-any-return]

    def timed_out(status_read: int, *, timeout: float = 0.0) -> str | None:
        raise OSError("the subject's exec status did not arrive within 60s")

    def interrupted(self: object, timeout: float | None = None) -> int:
        raise KeyboardInterrupt("a second Ctrl-C, during the reap")

    before = len(os.listdir("/proc/self/fd"))
    # `wait` is patched on the captured class, not on `subprocess.Popen`:
    # the next line replaces that name with a *function*, which has no
    # `wait` to set.
    monkeypatch.setattr(real_popen, "wait", interrupted)
    monkeypatch.setattr(subprocess, "Popen", recording)
    monkeypatch.setattr(_posix_pty, "_read_exec_status", timed_out)
    with pytest.raises(KeyboardInterrupt):
        _spawn("import time; time.sleep(300)")
    monkeypatch.undo()
    try:
        assert len(os.listdir("/proc/self/fd")) == before, (
            "the master outlived a spawn interrupted during its own cleanup"
        )
    finally:
        # The reap never ran, so this test owns ending and reaping the
        # child — the kill did land, since only `wait` was stubbed.
        assert spawned, "the fault fired before a child existed"
        with contextlib.suppress(OSError):
            os.killpg(spawned[0].pid, FORCED_TERMINATION_SIGNAL)  # type: ignore[attr-defined,unused-ignore]
        with contextlib.suppress(OSError, subprocess.TimeoutExpired):
            real_wait(spawned[0], timeout=_TIMEOUT_S)


@_LINUX_ONLY
def test_an_interrupted_adoption_leaves_no_child_and_no_descriptor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The half of the pair that owns the master must run for *any* failure.

    Adoption releases its own wake pipe on any exception, but the caller
    that owns the master and the child caught only ``OSError`` — so an
    interruption between the spawn and the adoption leaked the master and
    left a live session-leader child on a pty with no binding to close it.
    That is verbatim the defect the status-read handler one call earlier was
    written to fix; it was repaired there and not here.

    ``KeyboardInterrupt`` is the reachable case and is asserted to stay
    itself: only a descriptor failure is re-dressed as the spawn error that
    names the child.
    """
    spawned: list[subprocess.Popen[bytes]] = []
    real_popen = subprocess.Popen

    def recording(*args: object, **kwargs: object) -> subprocess.Popen[bytes]:
        process = real_popen(*args, **kwargs)  # type: ignore[call-overload]
        spawned.append(process)
        return process  # type: ignore[no-any-return]

    def interrupt(fd: int, blocking: bool) -> None:
        raise KeyboardInterrupt("simulated Ctrl-C inside adoption")

    before = len(os.listdir("/proc/self/fd"))
    monkeypatch.setattr(subprocess, "Popen", recording)
    monkeypatch.setattr(os, "set_blocking", interrupt)
    with pytest.raises(KeyboardInterrupt):
        _spawn("import time; time.sleep(300)")
    monkeypatch.undo()
    assert spawned, "the fault fired before a child existed"
    deadline = time.monotonic() + _TIMEOUT_S
    while spawned[0].poll() is None:
        assert time.monotonic() < deadline, (
            f"child {spawned[0].pid} outlived the spawn that could not adopt it"
        )
        time.sleep(0.01)
    # The signal, for the reason its sibling above records: the hangup from
    # releasing the master kills a session leader by itself.
    assert spawned[0].returncode == -FORCED_TERMINATION_SIGNAL, (
        f"the child ended by signal {-spawned[0].returncode}, not by this"
        f" path's own kill, so the teardown is unproven"
    )
    assert len(os.listdir("/proc/self/fd")) == before, (
        "the master outlived the spawn that could not adopt it"
    )


@_LINUX_ONLY
def test_the_wait_for_the_exec_status_is_bounded() -> None:
    """The spawn's one blocking call had no bound of any kind.

    Every other wait in this module is bounded or escapable by the wake
    pipe; this one blocked until the trampoline's write end was gone, which
    is normally the exec itself. "Normally" is the problem: nothing here
    holds that end but the child, so a child that stalls before its exec —
    a machine so loaded the interpreter never finishes starting, a stopped
    process — hung the spawn with no diagnostic and no child to kill.

    Exercised on a pipe this test holds open, which is exactly the state a
    stalled trampoline leaves behind.

    The second call passes a budget that has *already* expired — the state
    the loop reaches after a read leaves nothing left — because that is the
    only way to enter the non-positive branch deterministically. A positive
    budget always times out inside ``poll`` first, so the branch would be
    unpinned and deleting it would cost nothing: the wait would then hand a
    negative timeout to ``poll``, which blocks indefinitely, and the bound
    would be spent and then discarded.

    **Both calls run on a worker, and that is the point of this test's
    shape.** An inline version *hangs* when either bound is removed rather
    than failing, and there is no per-test timeout configured — so a
    regression would stop CI with no diagnostic, which is precisely the
    failure mode this PR exists to remove. It must fail, not hang. The write
    end is closed before the join so a worker still inside the call is woken
    by the hangup instead of being left blocked on a descriptor number this
    test is about to free.

    The elapsed time is asserted because the budget's *units* are otherwise
    unpinned: `poll` takes milliseconds, and dropping the conversion turns a
    60-second bound into a 60-millisecond one with every test still green —
    a budget that fires on a slow machine, which is the failure the constant
    was sized to avoid.
    """
    read_fd, write_fd = os.pipe()
    outcome: list[BaseException] = []
    elapsed: list[float] = []
    finished = threading.Event()
    budget = 0.5

    def wait_for_a_status_that_never_comes() -> None:
        for timeout in (budget, -1.0):
            started = time.monotonic()
            try:
                _posix_pty._read_exec_status(read_fd, timeout=timeout)
            except BaseException as error:  # noqa: BLE001 - recorded for the assert
                outcome.append(error)
            elapsed.append(time.monotonic() - started)
        finished.set()

    worker = threading.Thread(target=wait_for_a_status_that_never_comes, daemon=True)
    worker.start()
    try:
        assert finished.wait(_TIMEOUT_S), (
            "_read_exec_status never returned against a write end nobody"
            " closes: the wait is unbounded"
        )
        assert len(outcome) == 2, f"a call returned instead of failing: {outcome}"
        for error in outcome:
            assert isinstance(error, OSError), error
            assert "exec status" in str(error), error
        assert elapsed[0] >= budget, (
            f"the budget expired after {elapsed[0]:.3f}s of a {budget}s bound;"
            f" the timeout is not being passed in the units poll takes"
        )
    finally:
        # Before the join: a hangup wakes a worker still inside the call,
        # where closing the read end would leave it polling a freed number.
        os.close(write_fd)
        worker.join(_TIMEOUT_S)
        os.close(read_fd)


@_LINUX_ONLY
def test_exit_status_is_observed_without_a_close() -> None:
    """The property reports a real exit the moment the OS has one."""
    child = _spawn("pass")
    try:
        with pytest.raises(PosixPtyEndOfStreamError):
            for _ in range(100):
                child.read()
        assert child.exit_status == 0
        assert child.is_alive() is False
    finally:
        child.close(force=True)


@_LINUX_ONLY
def test_a_read_retries_when_readability_is_lost_after_the_poll(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty return and a lost race are not the same fact.

    Reporting end-of-stream for a ``BlockingIOError`` would turn a
    scheduling artifact into a claim that the subject ended.
    """
    child = _spawn("print('HELLO')")
    try:
        real_read = os.read
        pending = [True]

        def flaky(fd: int, size: int) -> bytes:
            if fd == child._master_fd and pending[0]:
                pending[0] = False
                raise BlockingIOError
            return real_read(fd, size)

        monkeypatch.setattr(os, "read", flaky)
        assert "HELLO" in _read_until(child, "HELLO")
        assert pending[0] is False, "the fault was never reached"
    finally:
        monkeypatch.undo()
        child.close(force=True)


@_LINUX_ONLY
def test_an_empty_read_is_end_of_stream(monkeypatch: pytest.MonkeyPatch) -> None:
    """Defensive leg: Linux answers EIO, but an empty read means the same.

    The child is short-lived on purpose. End-of-stream captures the exit
    record, and against a long-running child that capture would wait out
    its full bounded window for an exit that is not coming — thirty
    seconds of test time to observe a branch that takes none.
    """
    child = _spawn("pass")
    try:
        real_read = os.read

        def empty(fd: int, size: int) -> bytes:
            if fd == child._master_fd:
                return b""
            return real_read(fd, size)

        monkeypatch.setattr(os, "read", empty)
        with pytest.raises(PosixPtyEndOfStreamError):
            child.read()
    finally:
        monkeypatch.undo()
        child.close(force=True)


@_LINUX_ONLY
def test_a_read_that_fails_for_another_reason_is_not_end_of_stream(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The child must *produce* something, or this test waits on ``poll``.

    Patching ``os.read`` does not shorten the wait that precedes it: a read
    blocks in ``poll`` until the pty is readable, so against a silent
    300-second child the injected fault only fires when that child finally
    exits. Measured on CI at 300.03s before the child was given something
    to say.
    """
    child = _spawn("print('READY')")
    try:
        real_read = os.read

        def broken(fd: int, size: int) -> bytes:
            if fd == child._master_fd:
                raise OSError(errno.EBADF, "bad descriptor")
            return real_read(fd, size)

        monkeypatch.setattr(os, "read", broken)
        with pytest.raises(OSError) as caught:
            child.read()
        assert not isinstance(caught.value, PosixPtyEndOfStreamError)
    finally:
        monkeypatch.undo()
        child.close(force=True)


@_LINUX_ONLY
def test_write_rejects_a_non_string() -> None:
    child = _spawn("import time; time.sleep(300)")
    try:
        with pytest.raises(TypeError, match="text must be a string"):
            child.write(b"bytes")  # type: ignore[arg-type]
    finally:
        child.close(force=True)


@_LINUX_ONLY
def test_a_second_concurrent_write_wears_its_own_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The write-side twin of the read-side guard (issue #261)."""
    child = _spawn("import time; time.sleep(300)")
    entered = threading.Event()
    release = threading.Event()

    def blocking_write(self: PosixPtyChild, fd: int, wake: int, payload: bytes) -> None:
        entered.set()
        release.wait(_TIMEOUT_S)

    monkeypatch.setattr(PosixPtyChild, "_write_all", blocking_write)
    writer = threading.Thread(target=lambda: child.write("first"), daemon=True)
    writer.start()
    try:
        assert entered.wait(_TIMEOUT_S)
        with pytest.raises(PosixPtyConcurrentIOError):
            child.write("second")
    finally:
        release.set()
        writer.join(_TIMEOUT_S)
        monkeypatch.undo()
        child.close(force=True)


@_LINUX_ONLY
def test_a_write_woken_by_a_close_reports_the_closed_binding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    child = _spawn("import time; time.sleep(300)")
    try:
        monkeypatch.setattr(
            _posix_pty,
            "_wait_until_ready",
            lambda fd, wake, *, write: True,
        )
        with pytest.raises(PosixPtyClosedError, match="closed during a write"):
            child.write("never arrives")
    finally:
        monkeypatch.undo()
        child.close(force=True)


@_LINUX_ONLY
def test_a_forced_close_falls_back_to_the_pid_when_no_group_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The repair for the CI red: ESRCH means kill the process itself.

    A child forked but not yet through ``setsid`` has no group of its own,
    and swallowing that ``ESRCH`` is what let it outlive its own teardown.
    """
    child = _spawn("import time; time.sleep(300)")
    pid = child.pid

    def no_such_group(pgid: int, signal_number: int) -> None:
        raise ProcessLookupError(errno.ESRCH, "no such process group")

    monkeypatch.setattr(os, "killpg", no_such_group)
    child.close(force=True)
    monkeypatch.undo()
    assert child.exit_status == -FORCED_TERMINATION_SIGNAL
    with pytest.raises(OSError):
        os.kill(pid, 0)


@_LINUX_ONLY
def test_a_close_that_cannot_signal_says_so_rather_than_returning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed kill must not read as a successful teardown.

    An earlier version of this test pinned the opposite — it asserted the
    close returned quietly on ``EPERM`` — which is how a test enshrines a
    defect. Swallowing it would let ``close`` return having killed nothing,
    with the only trace being ``exit_status is None``, which is also what a
    slow reap looks like. Realistic whenever the subject changes uid.
    """
    child = _spawn("import time; time.sleep(300)")
    pid = child.pid
    try:

        def refused(pgid: int, signal_number: int) -> None:
            raise PermissionError(errno.EPERM, "not permitted")

        # Only `os.killpg` is patched. `EPERM` is not `ESRCH`, so it
        # propagates out of `_terminate_session` and the `process.kill()`
        # fallback below it is never reached — a patch on `Popen.kill` here
        # would be arranging for a call that cannot happen, which reads as
        # coverage of a path this test does not exercise.
        monkeypatch.setattr(os, "killpg", refused)
        with pytest.raises(PermissionError):
            child.close(force=True)
    finally:
        # The close was refused the signal, so the child is still running:
        # this test owns ending it, *and* reaping it. Without the wait the
        # stubbed kill leaves a zombie for the rest of the session, because
        # nothing else calls `wait` on a child whose teardown raised.
        monkeypatch.undo()
        with contextlib.suppress(OSError):
            os.killpg(pid, FORCED_TERMINATION_SIGNAL)  # type: ignore[attr-defined,unused-ignore]
        with contextlib.suppress(OSError, subprocess.TimeoutExpired):
            child._process.wait(timeout=_TIMEOUT_S)


@_LINUX_ONLY
def test_a_second_close_waits_for_the_first_to_capture_the_exit_record() -> None:
    """A concurrent close must not hand back a half-closed binding.

    The adapter above consults ``exit_status`` immediately after closing,
    and its watchdog closes from a timer thread — so two closes in flight
    is the designed path, not a hypothetical. A second close that returned
    on seeing the ``_closed`` flag would let its caller read ``None`` for a
    child that is about to report ``-9``.
    """
    child = _spawn("import time; time.sleep(300)")
    observed: list[int | None] = []
    started = threading.Event()

    def slow_capture(self: PosixPtyChild, process: object) -> None:
        started.set()
        time.sleep(0.5)  # arrangement, not evidence: widen the window
        with self._lock:
            self._exit_status = -FORCED_TERMINATION_SIGNAL

    original_capture = PosixPtyChild._capture_exit_status_after_close
    original_terminate = PosixPtyChild._terminate_session
    # The kill is stubbed out too. With the real one running, the child is
    # SIGKILLed before the follower is scheduled, so `process.poll()` can
    # supply -9 on its own and the test passes even with the fix reverted —
    # it would turn on the kernel's reap timing rather than on whether the
    # follower waited. Round 2 caught that; this is the deterministic form.
    PosixPtyChild._capture_exit_status_after_close = slow_capture  # type: ignore[method-assign]
    PosixPtyChild._terminate_session = lambda self, process: None  # type: ignore[method-assign]
    try:
        first = threading.Thread(target=lambda: child.close(force=True), daemon=True)
        first.start()
        assert started.wait(_TIMEOUT_S)
        child.close(force=True)
        observed.append(child.exit_status)
        first.join(_TIMEOUT_S)
    finally:
        PosixPtyChild._capture_exit_status_after_close = original_capture  # type: ignore[method-assign]
        PosixPtyChild._terminate_session = original_terminate  # type: ignore[method-assign]
        with contextlib.suppress(OSError):
            os.killpg(child.pid, FORCED_TERMINATION_SIGNAL)  # type: ignore[attr-defined,unused-ignore]
        # Reap it: _terminate_session was stubbed, so nothing else does,
        # and an unreaped child is a zombie for the rest of the session.
        with contextlib.suppress(OSError, subprocess.TimeoutExpired):
            child._process.wait(timeout=_TIMEOUT_S)
    assert observed == [-FORCED_TERMINATION_SIGNAL], (
        f"the second close returned before the exit record existed: {observed}"
    )


@_LINUX_ONLY
def test_a_second_close_learns_that_the_first_could_not_kill(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed teardown must not read as success to whoever arrives second.

    The thread that raises is typically the watchdog timer, whose
    exception reaches ``threading.excepthook`` and no caller at all — so
    if the follower returned normally, *nobody* would learn the child
    survived, and ``exit_status`` would be ``None``, which is also what a
    slow reap looks like.
    """
    child = _spawn("import time; time.sleep(300)")
    pid = child.pid

    def refused(*args: object) -> None:
        raise PermissionError(errno.EPERM, "not permitted")

    # `Popen.kill` is deliberately not patched: `EPERM` propagates out of
    # `_terminate_session` before the pid fallback, so patching it would
    # arrange for a call that cannot happen. Same reason as its sibling
    # above.
    monkeypatch.setattr(os, "killpg", refused)
    try:
        with pytest.raises(PermissionError):
            child.close(force=True)
        # The follower arrives after the leader has finished and failed.
        with pytest.raises(PermissionError):
            child.close(force=True)
    finally:
        monkeypatch.undo()
        with contextlib.suppress(OSError):
            os.killpg(pid, FORCED_TERMINATION_SIGNAL)  # type: ignore[attr-defined,unused-ignore]
        with contextlib.suppress(OSError, subprocess.TimeoutExpired):
            child._process.wait(timeout=_TIMEOUT_S)


def _fail_read_with(
    monkeypatch: pytest.MonkeyPatch, child: PosixPtyChild, error_number: int
) -> None:
    """Make the next read reach the discriminator with a failing os.read.

    ``_wait_until_ready`` is forced to report "ready, not woken", so the
    read proceeds to ``os.read`` and the injected error is what the
    discriminator is asked about. Without this the wake pipe short-circuits
    at the poll and the branch under test is never entered — which is why
    it had no coverage at all.
    """
    real_read = os.read

    def failing(fd: int, size: int) -> bytes:
        if fd == child._master_fd:
            raise OSError(error_number, "injected")
        return real_read(fd, size)

    monkeypatch.setattr(
        _posix_pty, "_wait_until_ready", lambda fd, wake, *, write: False
    )
    monkeypatch.setattr(os, "read", failing)


@_LINUX_ONLY
def test_an_end_of_stream_that_a_close_caused_reports_the_closed_binding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The positive branch of the close-versus-end-of-stream discriminator.

    Nothing reached it before: every test that exercises a close wakes the
    reader inside ``poll``, which raises earlier, and every test that
    reaches the discriminator gets ``False``. Both guards could be deleted
    with the suite still green — the same defect this slice fixed for the
    controlling terminal, applied to the fix for the other Critical.

    The wake byte is written directly, which is exactly what ``close``
    does first and is what "a close reached this read" means.
    """
    child = _spawn("import time; time.sleep(300)")
    try:
        os.write(child._wake_write, b"\x00")
        _fail_read_with(monkeypatch, child, errno.EIO)
        with pytest.raises(PosixPtyClosedError, match="closed during a read"):
            child.read()
    finally:
        monkeypatch.undo()
        child.close(force=True)


@_LINUX_ONLY
def test_an_end_of_stream_with_no_close_behind_it_is_end_of_stream(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The negative branch, against the identical injection.

    The pair is what makes either assertion meaningful: same fault, same
    path, opposite verdicts, decided only by whether the wake pipe fired.
    """
    child = _spawn("import time; time.sleep(300)")
    try:
        _fail_read_with(monkeypatch, child, errno.EIO)
        with pytest.raises(PosixPtyEndOfStreamError):
            child.read()
    finally:
        monkeypatch.undo()
        child.close(force=True)


@_LINUX_ONLY
def test_the_status_pipe_write_end_is_kept_clear_of_the_stdio_range() -> None:
    """A write end on 0, 1 or 2 would be replaced by the pty slave.

    ``pass_fds`` entries keep their numbers, and the child's
    ``dup2(slave, 0/1/2)`` runs first — so a low write end means the
    trampoline's failure text goes into the subject's transcript while the
    parent reads success. Reachable whenever the parent runs with a closed
    stdin.
    """
    # Freeing the stdio range is what makes this able to fail, and freeing
    # *fd 0 alone is not enough* — which is how this test spent a round
    # passing without the fix it names. `os.pipe()` returns the two lowest
    # free descriptors, so with only fd 0 free the read end lands on 0 and
    # the write end on whatever is next above the process's open set —
    # measured at 4 in one environment and 13 in another, and `> 2` either
    # way, so the assertion was satisfied by the kernel rather than by the
    # relocation loop. With 0, 1 and 2 all free it answers (0, 1), measured
    # in both, and the assertion needs the loop.
    #
    # Every dup is taken before any close, so a failure partway cannot leave
    # the process without stdio. The restore order does not matter — each
    # `dup2` names its own target descriptor — so it runs in the same order
    # as the dups.
    spares = [os.dup(fd) for fd in (0, 1, 2)]
    try:
        for fd in (0, 1, 2):
            os.close(fd)
        read_fd, write_fd = _posix_pty._status_pipe()
        try:
            assert write_fd > 2, f"status write end landed at {write_fd}"
        finally:
            os.close(read_fd)
            os.close(write_fd)
    finally:
        for fd, spare in enumerate(spares):
            os.dup2(spare, fd)
            os.close(spare)


# --------------------------------------------------------------------------
# The helper every evidence test leans on
#
# Eight tests read through `_read_until` before this slice and ten do now, so
# a defect in it is a defect in all of them at once — and the failure mode it
# had was the one that costs the most to diagnose: not a wrong answer, but no
# answer at all.
# --------------------------------------------------------------------------


@_LINUX_ONLY
def test_read_until_fails_loudly_when_the_child_goes_silent() -> None:
    """The helper's own docstring promised this and it did not hold.

    The deadline was evaluated only *between* reads, and ``child.read()``
    blocks in a ``poll`` with no timeout by design — the wake pipe a close
    writes is what ends it. So against a child that goes silent without
    producing the needle, the helper had no bound at all: the only thing
    that ended the leg was CI's ``timeout-minutes: 30``, which kills the job
    with no diagnostic and no collected output.

    The assertion is run on a worker so that a regression *fails* here
    instead of hanging the suite the way the defect did.
    """
    child = _spawn("import time; time.sleep(300)")
    outcome: list[BaseException] = []
    finished = threading.Event()

    def wait_for_a_needle_that_never_comes() -> None:
        try:
            _read_until(child, "NEVER ARRIVES", timeout=0.5)
        except BaseException as error:  # noqa: BLE001 - recorded for the assert
            outcome.append(error)
        finally:
            finished.set()

    watcher = threading.Thread(target=wait_for_a_needle_that_never_comes, daemon=True)
    watcher.start()
    try:
        assert finished.wait(_TIMEOUT_S), (
            "_read_until never returned against a silent child: it is unbounded"
        )
        assert outcome, "_read_until returned instead of failing"
        assert isinstance(outcome[0], AssertionError), outcome[0]
        assert "timed out waiting for" in str(outcome[0]), outcome[0]
    finally:
        child.close(force=True)


@_LINUX_ONLY
def test_read_until_fails_loudly_when_the_child_never_says_the_needle() -> None:
    """The other half of the bound: the budget is a deadline, not a timeout.

    A silent child leaves the helper waiting; a *chatty* one keeps it
    working, and that is the case a per-read timeout would never end. Each
    read here returns promptly and the loop goes round again, so a helper
    that gave every wait the full timeout afresh would collect output for as
    long as the child produced it — forever, against a child that simply
    never says the needle. What bounds this run is that each wait gets only
    the time *remaining* against one deadline.
    """
    child = _spawn(
        "import time\nwhile True:\n    print('NOISE')\n    time.sleep(0.005)\n"
    )
    outcome: list[BaseException] = []
    finished = threading.Event()

    def wait_for_a_needle_that_never_comes() -> None:
        try:
            _read_until(child, "NEVER ARRIVES", timeout=0.5)
        except BaseException as error:  # noqa: BLE001 - recorded for the assert
            outcome.append(error)
        finally:
            finished.set()

    watcher = threading.Thread(target=wait_for_a_needle_that_never_comes, daemon=True)
    watcher.start()
    try:
        assert finished.wait(_TIMEOUT_S), (
            "_read_until never returned against a chatty child: its spent"
            " budget was discarded rather than enforced"
        )
        assert outcome, "_read_until returned instead of failing"
        assert isinstance(outcome[0], AssertionError), outcome[0]
        assert "NOISE" in str(outcome[0]), (
            f"the failure must carry what was collected: {outcome[0]}"
        )
    finally:
        child.close(force=True)


@_LINUX_ONLY
def test_an_exhausted_budget_is_never_handed_to_poll_as_wait_forever() -> None:
    """The guard the two tests above reach only by accident, pinned directly.

    They normally fail while the remaining budget is still a small
    *positive* number — the wait times out before the clock crosses the
    deadline — so the branch that matters goes unentered and deleting it
    left both green. "Normally" is measured, not assumed: instrumenting the
    two showed the silent case never reaching a non-positive budget, and
    the chatty case reaching one in roughly **one run in eight**, when the
    scheduler happens to overshoot the deadline between a poll and the next
    iteration. A branch covered one run in eight is not pinned by those
    tests; it is occasionally visited by them.

    Also measured rather than reasoned: ``poll`` blocks indefinitely on a
    negative timeout, so an exhausted budget handed through would wait
    forever for the child that has already outlived its deadline.

    Arranged against a child with output *pending*, which is what makes the
    assertion able to fail without hanging: an unguarded ``poll`` returns
    that readiness immediately and answers True, where the guard answers
    False without a syscall.
    """
    child = _spawn("print('PENDING')")
    try:
        assert _readable_within(child, _TIMEOUT_S), "the child produced nothing"
        # Same descriptor, same pending bytes, only the budget differs.
        assert _readable_within(child, 0) is False
        assert _readable_within(child, -0.5) is False
        assert _readable_within(child, _TIMEOUT_S) is True
    finally:
        child.close(force=True)


@_LINUX_ONLY
def test_a_subject_that_cannot_be_executed_fails_the_spawn(
    tmp_path: pathlib.Path,
) -> None:
    """A pre-exec failure must not become subject evidence.

    The trampoline's fds 0/1/2 are the pty slave, so an unhandled failure
    there would print a Python traceback straight into the subject's output
    stream and exit 1 — indistinguishable from a subject that exited 1.
    ``shutil.which`` does not prevent this: a script with no shebang is
    executable and still cannot be ``execv``'d.

    This is the **fourth** spawn-failure path, and the descriptor count
    below is what it was missing. Its three siblings each count
    ``/proc/self/fd``; this one drove the branch and asserted only the
    message, so deleting its ``os.close(master_fd)`` leaked a pty master per
    attempt with the whole suite green — the failure a harness retrying a
    mistyped subject command hits until ``EMFILE`` surfaces somewhere
    unrelated.
    """
    script = tmp_path / "no-shebang"
    script.write_bytes(b"echo this file has no shebang\n")
    script.chmod(0o755)
    before = len(os.listdir("/proc/self/fd"))
    with pytest.raises(OSError, match="the subject could not be started") as caught:
        PosixPtyChild.spawn([str(script)], rows=_INITIAL_ROWS, columns=_INITIAL_COLUMNS)
    assert "no-shebang" in str(caught.value)
    assert len(os.listdir("/proc/self/fd")) == before, (
        "the master outlived a spawn whose subject could not be executed"
    )
