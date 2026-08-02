"""Real POSIX pseudoterminal binding for the terminal adapter (issue #267).

This module is the POSIX sibling of ``_conpty.py``: the thin native
ownership layer that turns a real pseudoterminal into the child surface the
terminal adapter already drives (``read``, ``write``, ``resize``,
``is_alive``, ``close(force=)``, ``pid``, ``exit_status``), so the adapter
above the binding port needs no platform branch.

**The platform claim is Linux only** (boundary decision 2). The probe
answers before any spawn, and every other platform — macOS included —
reports unsupported. That is not a claim that a pty cannot work there; it
is the refusal to claim a platform CI has never run.

**The child gets a controlling terminal, and not through ``preexec_fn``.**
A session leader acquires a controlling terminal only by calling
``TIOCSCTTY`` itself; a parent cannot do it on the child's behalf, and
inheriting the slave as fds 0/1/2 does not do it either. Without one there
is no foreground process group, so the kernel delivers no ``SIGWINCH`` on
resize and the subject cannot open ``/dev/tty`` — a materially less
faithful terminal than the one a person drives. The usual route is
``subprocess``'s ``preexec_fn``, which CPython documents as unsafe in the
presence of threads: it runs Python code between ``fork`` and ``exec``, and
this product runs a watchdog timer thread. So the binding spawns a
**trampoline** instead — a fresh, single-threaded interpreter that calls
``TIOCSCTTY`` and then ``execv`` (``setsid`` is done by CPython's own
fork-exec helper; see :data:`_TRAMPOLINE`). The fork is followed
immediately by an exec, which CPython performs in C, so no Python code ever
runs in a forked-but-not-exec'd child. ``execv`` replaces the process
image, so the subject keeps the pid and the exit status; the cost is one
interpreter startup per spawn. ``argv[0]`` is the *resolved* path rather
than the word the caller wrote — matching the JSONL transport, and worth
knowing for a subject that branches on its own name.

**Line discipline is set explicitly, and it is deliberately conventional.**
Design rule 5 requires the discipline to be explicit and recorded rather
than inherited, because it changes what the subject sees and what reaches
the transcript. It does *not* require raw mode, and raw would be the wrong
choice: a subject under TermVerify should see the terminal a person's
subject sees (design principle 2), and that terminal post-processes output
(``OPOST|ONLCR``) and echoes input. Turning those off would make a plain
``print`` render as a staircase and would diverge from what the ConPTY
binding's console already does. Full-screen subjects call ``tcsetattr``
themselves and win, exactly as they do on a real terminal.
:func:`_configure_line_discipline` assigns the three flag words and the
control characters outright — an overlay would leave every unnamed bit
ambient — and states which fields stay inherited and why.

**What that choice costs, stated rather than absorbed.** With ``ECHO`` and
``ICANON`` on, the line discipline echoes every byte the harness writes
back onto the master's read side, so *harness input appears in the
subject's output stream*, and its interleaving with the subject's own
output is decided by the kernel's scheduling rather than by either party.
Three consequences follow, and they belong to the adapter above rather
than to this module: a readiness marker appearing in **input** is
indistinguishable from one the subject emitted; two replays of one run can
order echo against output differently; and ``ISIG`` means some writes are
not input at all — ``\x03`` delivers ``SIGINT`` to the foreground group and
never reaches the subject as data. Issue #273 carries this to the adapter
slice, where the marker scanner lives. ``IXON`` is off for a related
reason recorded at :func:`_configure_line_discipline`.

**Naming.** The error types here are POSIX-named while ``_conpty.py`` keeps
its own. Calling a pty failure ``ConptyClosedError`` would be false at the
point it is raised, and unifying the two taxonomies is exactly the work
issue #268 does when it generalizes the adapter over a neutral binding
port. Until then each binding names its own failures truthfully.

Like ``_jsonl_pipe.py`` and unlike ``_conpty.py``, this module is **not**
coverage-omitted. Its platform legs carry ``# coverage: exclude-windows``
markers rather than bare ``# pragma: no cover``, because a bare pragma is a
static source exclusion that drops the leg from measurement on every
platform (issue #230); the per-OS overlays keep each leg ratcheted where it
actually runs.
"""

from __future__ import annotations

import codecs
import errno
import os
import select
import shutil
import struct
import subprocess
import sys
import threading
import time
from collections.abc import Mapping, Sequence
from contextlib import suppress
from typing import Final

from termverify._terminal_binding import (
    TerminalClosedError,
    TerminalConcurrentIOError,
    TerminalEndOfStreamError,
    TerminalUnsupportedError,
)

# ``fcntl`` and ``termios`` are Unix-only and are imported *inside* the
# functions that need them, below their platform guard. This module must
# still import on Windows — the adapter's support probe is answered by
# calling into it from any platform — and a module-level conditional
# import would leave those names unbound to a Windows type-check even
# where every use is unreachable, because name binding is decided before
# reachability is. ``select`` and ``struct`` are cross-platform and stay
# at the top.

__all__ = [
    "FORCED_TERMINATION_SIGNAL",
    "PosixPtyChild",
    "PosixPtyClosedError",
    "PosixPtyConcurrentIOError",
    "PosixPtyEndOfStreamError",
    "PosixPtyLiveChildError",
    "PosixPtyUnsupportedError",
    "is_supported",
    "set_terminal_flags",
    "terminal_flags",
]

#: Signal delivered to the child's process group by a forced close. The
#: observed exit record is its negation, per ``waitpid`` semantics — the
#: same convention ``_jsonl_pipe.py`` already reports on POSIX.
FORCED_TERMINATION_SIGNAL: Final = 9  # SIGKILL

#: Bounded wait for the child to be reaped once it has provably exited or
#: been killed. Far beyond any scheduling delay, far below any hang.
_CHILD_EXIT_WAIT_S: Final = 30.0

#: Bounded wait for an interrupted read or write to deliver its error after
#: a close has unblocked the syscall.
_IO_DELIVERY_WAIT_S: Final = 5.0

#: Bounded wait for the trampoline to report its exec status. Covers a fresh
#: interpreter starting on a loaded host by orders of magnitude, because a
#: budget that can fire on a slow machine would fail spawns that were going
#: to work — a worse defect than the hang it replaces.
_EXEC_STATUS_WAIT_S: Final = 60.0

_READ_CHUNK_BYTES: Final = 65536

#: ``IUTF8``, supplied rather than imported. ``termios.IUTF8`` arrives in
#: **Python 3.13**; on the 3.12 this project still supports the constant does
#: not exist, and reading it defensively meant the flag was silently *off*
#: there — so the same subject on the same kernel erased a multibyte
#: character one way under 3.12 and another under 3.13, a determinism input
#: varying by interpreter rather than by platform. Supplying it makes the
#: line discipline identical on every supported interpreter.
#:
#: The value is the one Linux's ``asm-generic/termbits.h`` defines, which is
#: what every architecture this project's CI runs on uses. That assumption is
#: checked wherever it can be:
#: :func:`test_the_supplied_iutf8_constant_matches_the_interpreters_own`
#: compares it against ``termios.IUTF8`` on 3.13 and 3.14, both operating
#: systems — so an architecture whose termios bits differ from the generic
#: ones fails there rather than silently naming the wrong bit. It cannot be
#: checked on 3.12, which is the whole reason this constant exists.
_IUTF8: Final = 0x4000

#: The trampoline. It runs in a fresh interpreter that has just been
#: ``exec``'d, so it is single-threaded by construction and none of the
#: fork-safety hazards of ``preexec_fn`` apply. It does the one thing only
#: the child itself can do — acquire the controlling terminal — and then
#: becomes the subject.
#:
#: ``setsid`` is deliberately **not** here: ``Popen(start_new_session=True)``
#: performs it in CPython's C fork-exec helper, before this interpreter
#: starts. That matters for teardown, not for style. A forced close
#: identifies the child's process group by its pid, and until something
#: calls ``setsid`` no such group exists — so a close racing a just-spawned
#: child would signal a group that is not there yet. Moving ``setsid`` into
#: the helper shrinks that window to the fork itself; the ``ESRCH``
#: fallback in :meth:`PosixPtyChild._terminate_session` closes what
#: remains. This is a repair, not a precaution: with ``setsid`` in the
#: trampoline and the ``ESRCH`` suppressed, the Ubuntu legs for
#: ``test_a_forced_close_kills_the_session_and_records_the_real_exit``
#: reported ``exit_status`` ``None`` — the close signalled a group that
#: did not exist yet, killed nothing, and the bounded wait timed out.
#: Which of the two changes alone would suffice was not measured; both
#: are kept because they close different halves of the window.
#:
#: A failure before the exec reports itself on a **status pipe**, never on
#: the terminal. Its fds 0/1/2 are the pty slave, so an unhandled exception
#: would print a Python traceback straight into the subject's output stream
#: and exit 1 — manufacturing subject evidence out of a harness failure,
#: and indistinguishable from a subject that exited 1. ``shutil.which`` in
#: the parent does not cover this: it proves the file exists and is
#: executable, while ``execv`` still fails for a script with no shebang
#: (``ENOEXEC``), a shebang naming an absent interpreter, ``ETXTBSY``, or
#: an unlink between the check and the call. The pipe's write end is
#: marked close-on-exec, so a successful exec closes it and the parent
#: reads end-of-file; a failure writes the error first. Same shape as the
#: exec-status pipe CPython's own ``subprocess`` uses, and the same reason.
_TRAMPOLINE: Final = (
    "import os,sys\n"
    "status = -1\n"
    "try:\n"
    "    import fcntl, termios\n"
    "    status = int(sys.argv[1])\n"
    "    fcntl.fcntl(status, fcntl.F_SETFD, fcntl.FD_CLOEXEC)\n"
    "    fcntl.ioctl(0, termios.TIOCSCTTY, 0)\n"
    "    os.execv(sys.argv[2], sys.argv[2:])\n"
    "except BaseException as error:\n"
    "    try:\n"
    "        if status >= 0:\n"
    "            os.write(status, repr(error).encode('utf-8', 'replace')[:512])\n"
    "    except BaseException:\n"
    "        pass\n"
    "    os._exit(127)\n"
)


class PosixPtyUnsupportedError(TerminalUnsupportedError):
    """Raised when the binding is used on a host it does not claim."""


class PosixPtyClosedError(TerminalClosedError):
    """Raised when an operation is attempted after the binding was closed."""


class PosixPtyConcurrentIOError(TerminalConcurrentIOError):
    """Raised when a read or write is attempted while another is in flight.

    Single-flight is a port contract the adapter honors; this is defense in
    depth. It is a *caller* defect and wears its own type so no layer above
    can classify it as subject evidence — the disposition issue #261
    settled for both bindings.
    """


class PosixPtyLiveChildError(RuntimeError):
    """Raised when a release-only close would abandon a live child.

    Its own type because the alternatives are all wrong in the same
    direction. A bare ``RuntimeError`` — what this path raised before — is
    the *supertype* of three of the four kinds above, so ``except
    RuntimeError`` written for this refusal silently swallowed a closed
    binding, a single-flight violation and an unsupported host as well; and
    :class:`PosixPtyClosedError` would mean the opposite of what happened,
    since the binding is still open and the child still running.

    Deliberately **not** one of the neutral kinds in
    ``_terminal_binding.py``, because there is nothing neutral to name: the
    ConPTY binding permits a release-only close of a live child, where
    releasing the pseudoconsole handle makes the OS terminate the attached
    client, so the two bindings answer this call differently and the
    difference is real rather than an oversight. Closing a pty master
    hangs up the terminal but guarantees nothing about a child that ignores
    ``SIGHUP``, which is why this side refuses instead. The adapter never
    reaches either answer — it closes with ``force=True`` on every path —
    so the divergence is latent, and it is recorded in
    ``_terminal_binding.py`` beside the other one the two bindings do not
    give equally.
    """


class PosixPtyEndOfStreamError(TerminalEndOfStreamError):
    """Raised by ``read`` when the pseudoterminal reports end-of-stream.

    Only raised while the binding is open: a read interrupted by ``close``
    raises :class:`PosixPtyClosedError`, because a close may have abandoned
    output the child had already written.
    """


def is_supported() -> bool:
    """Report whether this host is one the binding claims.

    The explicit probe makes platform support answerable at negotiation
    time — before any spawn — without the ratcheted adapter reading ambient
    platform state.
    """
    if not sys.platform.startswith("linux"):
        return False
    return hasattr(os, "openpty") and hasattr(  # coverage: exclude-windows
        os, "killpg"
    )


def terminal_flags(fd: int) -> tuple[int, int, int]:  # coverage: exclude-windows
    """Return ``(iflag, oflag, lflag)`` for ``fd``.

    Public to the package rather than private because the binding's tests
    use it to *measure* the state a fresh pty is handed, instead of
    asserting a default the design deliberately refused to predict.

    A thin ``tcgetattr`` wrapper, so unlike :func:`is_supported` it carries
    no platform claim beyond "not Windows": it reads whatever terminal the
    caller already has.
    """
    if sys.platform == "win32":  # coverage: exclude-posix - POSIX-only path
        raise AssertionError("the POSIX PTY path is POSIX-only")
    import termios

    attributes = termios.tcgetattr(fd)
    return attributes[0], attributes[1], attributes[3]


def set_terminal_flags(  # coverage: exclude-windows - POSIX-only helper
    fd: int, iflag: int, oflag: int, lflag: int
) -> None:
    """Assign the three flag words on ``fd``, leaving the rest alone.

    The counterpart to :func:`terminal_flags`, and it exists for the same
    reason: the binding's tests clear these words before configuring, so
    that a configuration doing nothing at all is distinguishable from one
    that works. Without it the flags a fresh pty already carries make the
    contract untestable.

    **No production code calls this**, and that is the point rather than an
    oversight — it is in ``__all__`` because it is part of what this module
    offers the package, and what it offers here is the ability to measure
    the binding rather than take its word.
    """
    if sys.platform == "win32":  # coverage: exclude-posix - POSIX-only path
        raise AssertionError("the POSIX PTY path is POSIX-only")
    import termios

    _, _, cflag, _, ispeed, ospeed, cc = termios.tcgetattr(fd)
    termios.tcsetattr(
        fd, termios.TCSANOW, [iflag, oflag, cflag, lflag, ispeed, ospeed, cc]
    )


def _configure_line_discipline(fd: int) -> None:  # coverage: exclude-windows
    """Set the terminal state on ``fd`` to an absolute, stated value.

    Design rule 5 asks for a discipline that is recorded rather than
    inherited. An overlay does not deliver that: OR-ing a handful of named
    bits onto whatever ``openpty`` returned leaves every *unnamed* bit
    ambient, and several of those change transcript bytes directly —
    ``ECHOCTL`` decides whether a control byte echoes as ``^C``,
    ``cc[VERASE]`` decides which byte erases at all, ``IUTF8`` decides how
    a multibyte character erases. So the three flag words and the control
    characters are assigned outright, and what is *not* set is stated:

    - ``cflag``, ``ispeed`` and ``ospeed`` stay inherited. They describe a
      serial line — parity, stop bits, baud — and a pseudoterminal has no
      wire for them to describe. Nothing in them reaches evidence.

    Every choice that deviates from the conventional terminal is named
    here, and
    :func:`test_the_configured_discipline_deviates_from_the_default_only_as_stated`
    fails if this list stops being exhaustive — it diffs the configured
    words against what the running kernel hands a fresh pty and reports any
    flag this docstring does not mention. There are four:

    - ``IXON`` is **off**. Software flow control would let a harness write
      of ``0x13`` suspend the subject's output until ``0x11`` arrived —
      a byte that silently stalls the evidence stream is the opposite of a
      determinism input.
    - ``ECHOCTL`` and ``IEXTEN`` are **off**, so no byte the harness writes
      is echoed back in an expanded form the subject never produced.
    - ``IUTF8`` is **on**, so erasing a multibyte character erases the
      character rather than one of its bytes. It is a deviation on kernels
      that do not default it on, which is why it is named here rather than
      only at the assignment. The value is supplied by :data:`_IUTF8` rather
      than read from ``termios``, so that this holds on Python 3.12 too —
      the constant is not there before 3.13, and reading it defensively
      turned the flag off on one third of the supported matrix.

    ``ECHO`` and ``ICANON`` stay **on**, per the module docstring's
    faithfulness argument — with the consequence recorded there. So do the
    editing echoes ``ECHOE``, ``ECHOK`` and ``ECHOKE``, and that is a
    correction: ``ECHOE`` was on while ``ECHOK`` and ``ECHOKE`` were off,
    which no argument supports. This function installs ``^U`` as
    ``cc[VKILL]`` itself, so with those two off a harness-written kill
    erased the line and echoed nothing back, where the terminal a person
    drives shows the erasure — a difference in transcript bytes produced by
    a choice nobody had made on purpose. The three travel together now.
    """
    if sys.platform == "win32":  # coverage: exclude-posix - POSIX-only path
        raise AssertionError("the POSIX PTY path is POSIX-only")
    import termios

    _, _, cflag, _, ispeed, ospeed, cc = termios.tcgetattr(fd)
    # IUTF8 governs how a multibyte character erases and is Linux-specific.
    # Supplied by this module rather than read from `termios`, because the
    # constant does not exist before Python 3.13 — see :data:`_IUTF8`. The
    # comment this replaces called that a typing workaround; it was a
    # runtime one, and reading it defensively left the flag off on 3.12.
    iflag = termios.ICRNL | _IUTF8
    oflag = termios.OPOST | termios.ONLCR
    lflag = (
        termios.ISIG
        | termios.ICANON
        | termios.ECHO
        | termios.ECHOE
        | termios.ECHOK
        | termios.ECHOKE
    )
    control = list(cc)
    for name, value in (
        ("VINTR", 3),  # ^C
        ("VQUIT", 28),  # ^\
        ("VERASE", 127),  # DEL
        ("VKILL", 21),  # ^U
        ("VEOF", 4),  # ^D
        ("VSUSP", 26),  # ^Z
        ("VMIN", 1),
        ("VTIME", 0),
    ):
        control[getattr(termios, name)] = value
    termios.tcsetattr(
        fd,
        termios.TCSANOW,
        [iflag, oflag, cflag, lflag, ispeed, ospeed, control],
    )


def _set_window_size(  # coverage: exclude-windows - POSIX-only leg
    fd: int, *, rows: int, columns: int
) -> None:
    """Apply the geometry through ``TIOCSWINSZ``.

    Unlike the Windows console, which silently substitutes geometries
    outside its own band (issue #228), the kernel applies what it is given
    here. The band this binding can actually claim is measured by its
    tests rather than asserted in prose.
    """
    if sys.platform == "win32":  # coverage: exclude-posix - POSIX-only path
        raise AssertionError("the POSIX PTY path is POSIX-only")
    import fcntl
    import termios

    packed = struct.pack("HHHH", rows, columns, 0, 0)
    fcntl.ioctl(fd, termios.TIOCSWINSZ, packed)


def _status_pipe() -> tuple[int, int]:  # coverage: exclude-windows - POSIX-only
    """Return ``(read, write)`` with the write end above the stdio range.

    The relocation is not hygiene. ``subprocess`` passes ``pass_fds``
    entries through at their original numbers, and the child's
    ``dup2(slave, 0/1/2)`` runs before its descriptor cleanup — so a write
    end that landed on 0, 1 or 2 (which it can, whenever the parent runs
    with a closed stdin, as an embedded or daemonised harness does) is
    silently replaced by the pty slave in the child. The trampoline would
    then write its failure text *into the subject's transcript*, while the
    parent saw its own end closed and read the whole thing as success.
    CPython relocates its own exec-status pipe for exactly this reason.
    """
    read_fd, write_fd = os.pipe()
    spares: list[int] = []
    try:
        while write_fd < 3:
            # The dup comes *before* the append, so a failing dup does not
            # leave the same number in both `spares` and `write_fd` — the
            # handler below would then close it twice, and between the two
            # closes another thread's `open` can be handed that number and
            # have it closed underneath it. Narrow, but it needs exactly
            # the two conditions this function and its caller exist for: a
            # free low descriptor, and dup failing on exhaustion.
            relocated = os.dup(write_fd)
            spares.append(write_fd)
            write_fd = relocated
    except BaseException:
        os.close(read_fd)
        for fd in (*spares, write_fd):
            with _suppress_os_errors():
                os.close(fd)
        raise
    for fd in spares:
        os.close(fd)
    return read_fd, write_fd


def _read_exec_status(  # coverage: exclude-windows - POSIX-only helper
    status_read: int, *, timeout: float = _EXEC_STATUS_WAIT_S
) -> str | None:
    """Return the trampoline's failure text, or ``None`` if it exec'd.

    Waits until the write end is gone, which the exec itself does: the
    trampoline marks it close-on-exec, so end-of-file *is* the success
    signal. What that costs is a fresh interpreter starting — the price
    :data:`_TRAMPOLINE` documents — and then an ``ioctl`` and an ``execv``;
    nothing the subject does is in the wait, because the subject does not
    exist until the ``execv`` that ends it.

    Bounded anyway. Every other wait in this module is either bounded or
    escapable through the wake pipe, and this one is neither: no binding
    exists yet, so there is nothing to signal it. Nothing but the child
    holds that write end, so a child that stalls *before* its exec — a host
    too loaded to finish starting an interpreter, a process stopped by a
    signal — would otherwise hang the spawn with no diagnostic. The budget
    is generous by orders of magnitude against an interpreter startup,
    because a timeout that can fire on a slow machine would be a worse
    defect than the hang.
    """
    if sys.platform == "win32":  # coverage: exclude-posix - POSIX-only path
        raise AssertionError("the POSIX PTY path is POSIX-only")
    chunks: list[bytes] = []
    deadline = time.monotonic() + timeout
    poller = select.poll()
    poller.register(status_read, select.POLLIN)
    while True:
        remaining = deadline - time.monotonic()
        # A non-positive budget must never reach `poll`, which reads a
        # negative timeout as "wait forever" — spending the bound and then
        # discarding it.
        if remaining <= 0 or not poller.poll(remaining * 1000):
            raise OSError(
                "the subject's exec status did not arrive within"
                f" {timeout:g}s; the child stalled before its exec"
            )
        chunk = os.read(status_read, 512)
        if not chunk:
            break
        chunks.append(chunk)
    if not chunks:
        return None
    return b"".join(chunks).decode("utf-8", "replace")


def _wait_until_ready(  # coverage: exclude-windows - POSIX-only helper
    fd: int, wake: int, *, write: bool
) -> bool:
    """Block until ``fd`` is ready or ``wake`` fires; True if ``wake`` did.

    ``poll`` rather than ``select``, for the reason ``_jsonl_pipe.py``
    records at its twin of this helper: ``select`` cannot express a
    descriptor at or above ``FD_SETSIZE``. The twin is deliberately not
    imported — it is six lines of stdlib calls with no policy in them, and
    importing it would make this binding depend on the JSONL transport's
    module for no functional reason. If a third native binding ever wants
    it, that is when it earns a shared home.
    """
    if sys.platform == "win32":  # coverage: exclude-posix - POSIX-only path
        raise AssertionError("the POSIX PTY path is POSIX-only")
    poller = select.poll()
    poller.register(wake, select.POLLIN)
    poller.register(fd, select.POLLOUT if write else select.POLLIN)
    # No timeout: the wake-up pipe is what ends an otherwise endless wait,
    # and every close signals it before touching any descriptor.
    return any(ready == wake for ready, _events in poller.poll())


class _suppress_os_errors:  # coverage: exclude-windows - POSIX paths only
    """Context manager: teardown ignores already-gone descriptors."""

    def __enter__(self) -> None:
        return None

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
        return isinstance(exc_type, type) and issubclass(
            exc_type, (OSError, ValueError)
        )


class PosixPtyChild:
    """One spawned subject on the slave side of a pseudoterminal.

    The parent keeps the master descriptor and nothing else: its copy of
    the slave is closed immediately after the spawn, because a slave held
    open by this process would keep the master readable forever and no
    end-of-stream would ever arrive when the child exits.
    """

    def __init__(  # coverage: exclude-windows - reachable only via spawn
        self, process: subprocess.Popen[bytes], master_fd: int
    ) -> None:
        # Not optional: nothing ever clears it, and typing it as though
        # something might made five branches permanently unreachable in a
        # module that deliberately joined the coverage ratchet. A binding
        # exists only for a process that was spawned.
        self._process: subprocess.Popen[bytes] = process
        self._pid = process.pid
        self._master_fd = master_fd
        self._lock = threading.Lock()
        self._closed = False
        # The event a second close waits on, and the failure it must learn
        # about. Without them a second close returns the instant it sees
        # `_closed`, while the first is still inside its bounded wait for
        # the exit record — so the caller reads `exit_status` and gets
        # `None` for a child that is about to report -9, or worse, for one
        # the leader failed to kill at all. The adapter above consults
        # `exit_status` immediately after closing and its watchdog closes
        # from a timer thread, so both callers are real.
        self._close_done = threading.Event()
        self._close_failure: BaseException | None = None
        self._exit_status: int | None = None
        self._read_in_flight = False
        self._write_in_flight = False
        self._interrupted_read = threading.Event()
        self._interrupted_write = threading.Event()
        self._interrupted_read.set()
        self._interrupted_write.set()
        self._decoder = codecs.getincrementaldecoder("utf-8")("replace")
        self._wake_read = -1
        self._wake_write = -1
        self._adopt_wake_pipe()

    def _adopt_wake_pipe(self) -> None:  # coverage: exclude-windows
        """Create the interruption pipe and make every descriptor non-blocking.

        The wake pipe comes before any state the caller can observe, so a
        failure here leaves nothing half-built for the caller to unwind.
        ``os.pipe`` is not the only fallible call: ``os.set_blocking`` can
        raise too, and ``spawn``'s handler releases the *master* only — so
        this method releases what this method opened, and the two together
        leave no descriptor behind. The master is deliberately not closed
        here; it is the caller's, and closing it from both places is how a
        descriptor number gets freed twice.

        Both ends are non-blocking: a close signalling a full wake pipe
        would be a teardown blocking on its own interruption.
        """
        self._wake_read, self._wake_write = os.pipe()
        try:
            os.set_blocking(self._wake_write, False)
            os.set_blocking(self._wake_read, False)
            os.set_blocking(self._master_fd, False)
        except BaseException:
            for fd in (self._wake_read, self._wake_write):
                with _suppress_os_errors():
                    os.close(fd)
            self._wake_read = -1
            self._wake_write = -1
            raise

    @classmethod
    def spawn(
        cls,
        argv: Sequence[str],
        *,
        rows: int,
        columns: int,
        env_overlay: Mapping[str, str] | None = None,
        cwd: str | None = None,
    ) -> PosixPtyChild:
        """Start one subject on a fresh pseudoterminal.

        The environment overlay and working directory compose here, inside
        the binding, so the ratcheted adapter above never reads ambient
        state.
        """
        if not is_supported():
            raise PosixPtyUnsupportedError(
                "the POSIX PTY binding is claimed on Linux only; this host is"
                f" {sys.platform}"
            )
        return cls._spawn_posix(  # coverage: exclude-windows - POSIX-only leg
            argv, rows=rows, columns=columns, env_overlay=env_overlay, cwd=cwd
        )

    @classmethod
    def _spawn_posix(  # coverage: exclude-windows - POSIX-only leg
        cls,
        argv: Sequence[str],
        *,
        rows: int,
        columns: int,
        env_overlay: Mapping[str, str] | None,
        cwd: str | None,
    ) -> PosixPtyChild:
        if sys.platform == "win32":  # coverage: exclude-posix - POSIX-only
            raise AssertionError("the POSIX PTY path is POSIX-only")
        arguments = [str(argument) for argument in argv]
        if not arguments:
            raise ValueError("argv must name a subject command")
        command = shutil.which(arguments[0])
        if command is None:
            raise FileNotFoundError(
                f"the command was not found or was not executable: {arguments[0]}"
            )
        merged = dict(os.environ)
        if env_overlay is not None:
            merged.update(env_overlay)
        master_fd, slave_fd = os.openpty()
        # Inside its own guard: this is a fallible call, and before the
        # round-2 review it sat between `openpty` and the `try` below, so
        # descriptor exhaustion here leaked the pty pair — and made the
        # exhaustion it reports monotonically worse on every retry.
        try:
            status_read, status_write = _status_pipe()
        except BaseException:
            os.close(master_fd)
            os.close(slave_fd)
            raise
        process: subprocess.Popen[bytes] | None = None
        try:
            _configure_line_discipline(slave_fd)
            _set_window_size(slave_fd, rows=rows, columns=columns)
            process = subprocess.Popen(  # noqa: S603 - argv is a validated list
                [
                    sys.executable,
                    "-I",
                    "-c",
                    _TRAMPOLINE,
                    str(status_write),
                    command,
                    *arguments[1:],
                ],
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                env=merged,
                cwd=cwd,
                close_fds=True,
                pass_fds=(status_write,),
                # The session is created here, in CPython's C fork-exec
                # helper, rather than by the trampoline — see _TRAMPOLINE.
                start_new_session=True,
            )
        except BaseException:
            os.close(master_fd)
            os.close(status_read)
            raise
        finally:
            # The parent's copies go as soon as the child owns its own: a
            # slave held here would keep the master readable forever, so a
            # child's exit would never surface as end-of-stream, and a
            # status write end held here would never report end-of-file.
            os.close(slave_fd)
            os.close(status_write)
        try:
            failure = _read_exec_status(status_read)
        except BaseException:
            # Reachable by a KeyboardInterrupt inside the blocking read.
            # Every other failure point on this path has a handler; before
            # the round-2 review this one did not, so a Ctrl-C during a
            # spawn orphaned the subject on a pty with no binding left to
            # close it.
            with _suppress_os_errors():
                process.kill()
            with suppress(OSError, subprocess.TimeoutExpired):
                process.wait(timeout=_CHILD_EXIT_WAIT_S)
            os.close(master_fd)
            raise
        finally:
            os.close(status_read)
        if failure is not None:
            # The child never became the subject. Reap it and fail the
            # spawn naming the command, instead of handing back a binding
            # whose first read would return a Python traceback.
            with _suppress_os_errors():
                process.kill()
            with suppress(OSError, subprocess.TimeoutExpired):
                process.wait(timeout=_CHILD_EXIT_WAIT_S)
            os.close(master_fd)
            raise OSError(
                f"the subject could not be started: {arguments[0]} ({failure})"
            )
        try:
            return cls(process, master_fd)
        except OSError as error:
            # Construction calls `os.pipe`, which fails on EMFILE/ENFILE.
            # Fail closed rather than leaking a live child and the master:
            # no child outlives a failed spawn.
            try:
                process.kill()
                process.wait(timeout=_CHILD_EXIT_WAIT_S)
            except (OSError, subprocess.TimeoutExpired):
                pass
            finally:
                with _suppress_os_errors():
                    os.close(master_fd)
            raise OSError(
                f"failed to adopt the pty descriptors for child {process.pid}"
            ) from error

    @property
    def pid(self) -> int:  # coverage: exclude-windows - needs an instance
        return self._pid

    @property
    def exit_status(self) -> int | None:  # coverage: exclude-windows
        """Return the OS-observed exit status, else ``None``.

        A signal termination is the negative signal number, per ``waitpid``
        semantics, so a forced close reports ``-FORCED_TERMINATION_SIGNAL``.
        Never fabricated: a binding that has not observed an exit reports
        ``None``.
        """
        with self._lock:
            if self._exit_status is not None:
                return self._exit_status
            process = self._process
        status = process.poll()
        if status is None:
            return None
        with self._lock:
            self._exit_status = int(status)
            return self._exit_status

    def is_alive(self) -> bool:  # coverage: exclude-windows
        with self._lock:
            process = self._process
        return process.poll() is None

    def read(self) -> str:  # coverage: exclude-windows - POSIX-only leg
        """Read one decoded chunk of subject output.

        One incremental decoder runs for the life of the child (the rule
        ``_conpty.py`` established at issue #197), so a read landing
        mid-codepoint heals across chunks instead of embedding an
        irreparable ``U+FFFD`` in evidence.
        """
        with self._lock:
            if self._closed:
                raise PosixPtyClosedError("the POSIX PTY binding is closed")
            if self._read_in_flight:
                raise PosixPtyConcurrentIOError(
                    "the POSIX PTY binding allows one in-flight read"
                )
            self._read_in_flight = True
            self._interrupted_read.clear()
            fd = self._master_fd
            wake = self._wake_read
        try:
            return self._decoder.decode(self._read_chunk(fd, wake))
        finally:
            with self._lock:
                self._read_in_flight = False
                self._interrupted_read.set()

    def _read_chunk(  # coverage: exclude-windows - POSIX-only leg
        self, fd: int, wake: int
    ) -> bytes:
        while True:
            if _wait_until_ready(fd, wake, write=False):
                raise PosixPtyClosedError(
                    "the POSIX PTY binding was closed during a read"
                )
            try:
                chunk = os.read(fd, _READ_CHUNK_BYTES)
            except BlockingIOError:
                # Readability can be lost between the poll and the read;
                # wait again rather than reporting a spurious end-of-stream.
                continue
            except OSError as error:
                if self._interrupted_by_close():
                    raise PosixPtyClosedError(
                        "the POSIX PTY binding was closed during a read"
                    ) from error
                if error.errno == errno.EIO:
                    # A master whose last slave is gone reports EIO on
                    # Linux rather than an empty read. It is this
                    # platform's end-of-stream and is normalized to the
                    # binding's own signal — measured, not assumed.
                    raise self._end_of_stream() from error
                raise
            if not chunk:
                if self._interrupted_by_close():
                    raise PosixPtyClosedError(
                        "the POSIX PTY binding was closed during a read"
                    )
                raise self._end_of_stream()
            return chunk

    def _interrupted_by_close(self) -> bool:  # coverage: exclude-windows
        """Report whether a close interrupted *this* read.

        The distinction matters and the obvious test gets it wrong. Asking
        whether the binding ``_closed`` is strictly broader than the
        contract :class:`PosixPtyEndOfStreamError` states: a child that
        exited cleanly leaves ``EIO`` pending on the master, and a close
        arriving between the poll and the read would then turn a genuine
        end-of-stream into a closed-binding error — losing the exit record
        for a run that terminated normally. That is the mirror image of
        the defect the state check was added to fix, and it was found by
        the round-2 review of this module.

        What is asked instead is whether the *wake pipe fired*, which is
        the only thing that means "a close reached this read". A close
        writes it before touching any descriptor, so a read that was
        genuinely interrupted always observes it.
        """
        if sys.platform == "win32":  # coverage: exclude-posix - POSIX-only path
            raise AssertionError("the POSIX PTY path is POSIX-only")
        if self._wake_read < 0:
            return True
        try:
            # ``poll`` rather than ``select``, for the reason this module
            # already records at :func:`_wait_until_ready` and the sibling
            # binding records with its consequence: ``select`` cannot
            # express a descriptor at or above ``FD_SETSIZE`` and raises
            # ``ValueError`` on one — which is not an ``OSError``, so the
            # handler below would not catch it, and a routine end-of-stream
            # would surface as an unclassifiable exception out of ``read``.
            # A harness with a raised ``RLIMIT_NOFILE`` driving many
            # subjects reaches that descriptor range, which is the same
            # descriptor-pressure case the rest of this path guards.
            poller = select.poll()
            poller.register(self._wake_read, select.POLLIN)
            return bool(poller.poll(0))
        except OSError:
            # The descriptor is already gone, which only a close does.
            return True

    def _end_of_stream(self) -> PosixPtyEndOfStreamError:  # coverage: exclude-windows
        self._capture_exit_status_after_eos()
        return PosixPtyEndOfStreamError("the pseudoterminal reported end-of-stream")

    def write(self, text: str) -> None:  # coverage: exclude-windows
        """Write subject input to the pseudoterminal.

        Tracked exactly like a read, and for the same reason: a close must
        not free the master descriptor's number while a write is still
        inside ``poll``/``os.write`` on it, because any concurrent ``open``
        in the process can reuse that number and the bytes would land in an
        unrelated file. Trading a hang for silent corruption is strictly
        worse than the hang.

        Failure modes, stated because the layer above classifies them, in
        the order they fire: ``TypeError`` for a non-``str`` payload, which
        is checked before anything is locked or encoded because a caller
        handing bytes to a text port has a defect no amount of terminal
        state can explain; :class:`PosixPtyClosedError` when the binding is
        closed or a close interrupts the write;
        :class:`PosixPtyConcurrentIOError` for a violated single-flight
        contract; and a bare ``OSError`` with
        ``errno.EIO`` when the subject is gone — a master whose last slave
        has closed reports that rather than a broken pipe. The binding does
        not translate ``EIO`` here into an end-of-stream signal: on the read
        side that fact ends the evidence stream, while on the write side it
        means the input had nowhere to go, and the two are not the same
        claim about the run.
        """
        if not isinstance(text, str):
            raise TypeError("text must be a string")
        payload = text.encode("utf-8")
        with self._lock:
            if self._closed:
                raise PosixPtyClosedError("the POSIX PTY binding is closed")
            if self._write_in_flight:
                raise PosixPtyConcurrentIOError(
                    "the POSIX PTY binding allows one in-flight write"
                )
            self._write_in_flight = True
            self._interrupted_write.clear()
            fd = self._master_fd
            wake = self._wake_read
        try:
            self._write_all(fd, wake, payload)
        finally:
            with self._lock:
                self._write_in_flight = False
                self._interrupted_write.set()

    def _write_all(  # coverage: exclude-windows - POSIX-only leg
        self, fd: int, wake: int, payload: bytes
    ) -> None:
        view = memoryview(payload)
        while view:
            if _wait_until_ready(fd, wake, write=True):
                raise PosixPtyClosedError(
                    "the POSIX PTY binding was closed during a write"
                )
            try:
                written = os.write(fd, view)
            except BlockingIOError:
                continue
            view = view[written:]

    def resize(  # coverage: exclude-windows - POSIX-only leg
        self, *, rows: int, columns: int
    ) -> None:
        # The ioctl runs *under* the lock, unlike the read and write paths,
        # which cannot hold it because they block. `TIOCSWINSZ` does not
        # block, and holding the lock is what stops a concurrent close from
        # freeing the master's descriptor number between the snapshot and
        # the call. The number is immediately reusable: a harness driving
        # several subjects mints more pty masters, so the resize could
        # otherwise land on another subject's terminal — quietly, since
        # `TIOCSWINSZ` succeeds there.
        with self._lock:
            if self._closed:
                raise PosixPtyClosedError("the POSIX PTY binding is closed")
            _set_window_size(self._master_fd, rows=rows, columns=columns)

    def close(self, *, force: bool) -> None:  # coverage: exclude-windows
        """Release the pseudoterminal; optionally kill the session first.

        Ordering is the invariant ``_jsonl_pipe.py`` records and pays for:
        **signal the wake-up before terminating anything or touching any
        descriptor.** A blocked read or write is woken first, its delivery
        is waited for, and only then does the master descriptor go.

        That ordering is what stops a syscall being left holding a
        descriptor number this method has already freed — within the bound
        it can enforce, which is stated rather than implied: each delivery
        wait is capped at :data:`_IO_DELIVERY_WAIT_S`, and the release runs
        when it expires. A read or write still inside the kernel after five
        seconds of having been woken is not something a teardown can wait
        out without becoming the hang it exists to prevent, so the trade is
        made deliberately and in one direction only. What such a call
        observes is a closed wake pipe, which
        :meth:`_interrupted_by_close` reads as "a close reached this read".
        """
        with self._lock:
            already_closed = self._closed
            process = self._process
            wake = self._wake_write
            if not already_closed:
                # Liveness is decided inline rather than through
                # `is_alive`: the lock is not reentrant, and calling a
                # method that takes it from inside the critical section
                # would deadlock the teardown this method exists to
                # guarantee.
                if not force and process.poll() is None:
                    raise PosixPtyLiveChildError(
                        "a release-only close of a live pty child would abandon"
                        " it; use force=True"
                    )
                self._closed = True
        if already_closed:
            # Another thread owns this teardown, or one already finished.
            # Wait for it rather than returning into a half-closed binding
            # whose exit record has not been captured yet; a completed
            # teardown has the event set and returns at once.
            #
            # The budget covers the leader's *worst* case — both delivery
            # waits plus the reap — because a follower that gave up early
            # would return exactly the half-closed result this branch
            # exists to prevent, only 30 seconds later and just as
            # silently.
            if not self._close_done.wait(_IO_DELIVERY_WAIT_S * 2 + _CHILD_EXIT_WAIT_S):
                raise RuntimeError(
                    "another thread's close of the pty binding did not finish"
                )
            self._reraise_close_failure()
            return
        failure: BaseException | None = None
        try:
            with _suppress_os_errors():
                os.write(wake, b"\x00")
            self._interrupted_read.wait(_IO_DELIVERY_WAIT_S)
            self._interrupted_write.wait(_IO_DELIVERY_WAIT_S)
            if force:
                self._terminate_session(process)
            self._capture_exit_status_after_close(process)
        except BaseException as error:
            # Recorded so the *other* callers of close learn it too. A
            # teardown that failed to kill anything must not read as a
            # success to whoever arrives second — and the thread that
            # raises is often the watchdog timer, whose exception reaches
            # `threading.excepthook` and no caller at all.
            failure = error
            raise
        finally:
            # The release belongs here, not in the try: a termination that
            # fails now *propagates* rather than being swallowed, and a
            # raising close that skipped this would leak the master and the
            # wake pipe on exactly the path where the child also survives.
            # The binding is closed either way; what the caller learns is
            # that the kill failed.
            self._release_descriptors()
            with self._lock:
                self._close_failure = failure
            self._close_done.set()

    def _reraise_close_failure(self) -> None:  # coverage: exclude-windows
        """Re-raise, on a follower, whatever the leader's teardown hit."""
        with self._lock:
            failure = self._close_failure
        if failure is not None:
            raise failure

    def _terminate_session(  # coverage: exclude-windows - POSIX-only leg
        self, process: subprocess.Popen[bytes]
    ) -> None:
        """Kill the child's whole process group.

        The child is a session leader, so the group is the session's, and
        every descendant that stayed in it dies with it. Disclosed, not
        guaranteed: a ``setsid()`` descendant has left the group and is not
        reaped — the same boundary the JSONL transport states. What is
        guaranteed is narrower and true: such a survivor cannot stall this
        teardown, because the wake-up above does not depend on reaching
        whoever holds the other end.
        """
        if sys.platform == "win32":  # coverage: exclude-posix - POSIX-only
            raise AssertionError("the POSIX PTY path is POSIX-only")
        try:
            os.killpg(process.pid, FORCED_TERMINATION_SIGNAL)
            return
        except ProcessLookupError:
            # No group with that id — the child was forked but has not yet
            # reached its ``setsid``, so there is nothing but the process
            # itself to end. Silently suppressing this is what made a
            # forced close kill nothing and report no exit record at all:
            # the child outlived the close and the bounded wait below
            # timed out. Fall through to the pid.
            pass
        # Every *other* signal failure — EPERM against a subject that
        # changed uid, most realistically — propagates. Swallowing it
        # would let `close` return normally having killed nothing, and the
        # only trace would be `exit_status is None`, which is also what a
        # slow reap looks like. The sibling binding raises here for the
        # same reason: a caller is told the termination failed rather than
        # reading a success the binding cannot vouch for.
        process.kill()

    def _capture_exit_status_after_close(  # coverage: exclude-windows
        self, process: subprocess.Popen[bytes]
    ) -> None:
        with self._lock:
            if self._exit_status is not None:
                return
        try:
            status = int(process.wait(timeout=_CHILD_EXIT_WAIT_S))
        except subprocess.TimeoutExpired:
            # No exit record is better than a fabricated one; the layer
            # above reports the absence.
            return
        with self._lock:
            self._exit_status = status

    def _capture_exit_status_after_eos(self) -> None:  # coverage: exclude-windows
        """Capture after end-of-stream: the child has exited by definition.

        The OS may not have reaped it at the moment the pty reports EIO, so
        a single ``poll`` can still read ``None``. The wait is bounded and
        is a reaping delay, never a liveness guess.
        """
        with self._lock:
            if self._exit_status is not None:
                return
            process = self._process
        try:
            status = int(process.wait(timeout=_CHILD_EXIT_WAIT_S))
        except subprocess.TimeoutExpired:
            return
        with self._lock:
            self._exit_status = status

    def _release_descriptors(self) -> None:  # coverage: exclude-windows
        with _suppress_os_errors():
            os.close(self._master_fd)
        self._master_fd = -1
        # The wake pipe goes last: an I/O call woken by it may still be
        # unwinding, and this method has already waited for that delivery.
        # No `fd >= 0` guard: only the leader reaches this, exactly once,
        # and `_adopt_wake_pipe` either produced both descriptors or raised
        # before any caller could hold the binding. An already-gone
        # descriptor is what `_suppress_os_errors` is for.
        for fd in (self._wake_read, self._wake_write):
            with _suppress_os_errors():
                os.close(fd)
        self._wake_read = -1
        self._wake_write = -1
