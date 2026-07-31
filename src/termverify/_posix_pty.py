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
``setsid``, ``TIOCSCTTY``, and then ``execv``. The fork is followed
immediately by an exec, which CPython performs in C, so no Python code ever
runs in a forked-but-not-exec'd child. ``execv`` replaces the process
image, so the subject keeps the pid, the exit status, and the argv the
caller asked for; the cost is one interpreter startup per spawn.

**Line discipline is set explicitly, and it is deliberately conventional.**
Design rule 5 requires the discipline to be explicit and recorded rather
than inherited, because it changes what the subject sees and what reaches
the transcript. It does *not* require raw mode, and raw would be the wrong
choice: a subject under TermVerify should see the terminal a person's
subject sees (design principle 2), and that terminal post-processes output
(``OPOST|ONLCR``) and echoes input. Turning those off would make a plain
``print`` render as a staircase and would diverge from what the ConPTY
binding's console already does. Full-screen subjects call ``tcsetattr``
themselves and win, exactly as they do on a real terminal. The flags are
set one by one in :func:`_configure_line_discipline`, so the state is a
contract rather than an accident of whatever ``openpty`` handed back, and
the child's own view of them is asserted in the binding's tests.

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
from collections.abc import Mapping, Sequence
from typing import Final

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
    "PosixPtyUnsupportedError",
    "is_supported",
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

_READ_CHUNK_BYTES: Final = 65536

#: The trampoline. It runs in a fresh interpreter that has just been
#: ``exec``'d, so it is single-threaded by construction and none of the
#: fork-safety hazards of ``preexec_fn`` apply. It does the three things
#: only the child itself can do, then becomes the subject.
#:
#: It reports a failed ``execv`` only as a non-zero interpreter exit, which
#: is why the command is resolved by ``shutil.which`` in the parent: a
#: missing command fails there, where the failure can name it, instead of
#: arriving here as an opaque exit code.
_TRAMPOLINE: Final = (
    "import fcntl,os,sys,termios\n"
    "os.setsid()\n"
    "fcntl.ioctl(0, termios.TIOCSCTTY, 0)\n"
    "os.execv(sys.argv[1], sys.argv[1:])\n"
)


class PosixPtyUnsupportedError(RuntimeError):
    """Raised when the binding is used on a host it does not claim."""


class PosixPtyClosedError(RuntimeError):
    """Raised when an operation is attempted after the binding was closed."""


class PosixPtyConcurrentIOError(RuntimeError):
    """Raised when a read or write is attempted while another is in flight.

    Single-flight is a port contract the adapter honors; this is defense in
    depth. It is a *caller* defect and wears its own type so no layer above
    can classify it as subject evidence — the disposition issue #261
    settled for both bindings.
    """


class PosixPtyEndOfStreamError(Exception):
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
    return hasattr(os, "openpty") and hasattr(os, "killpg")


def terminal_flags(fd: int) -> tuple[int, int, int]:  # coverage: exclude-windows
    """Return ``(iflag, oflag, lflag)`` for ``fd``.

    Public to the package rather than private because the binding's tests
    use it to *measure* the state a fresh pty is handed, instead of
    asserting a default the design deliberately refused to predict.
    """
    if sys.platform == "win32":  # coverage: exclude-posix - POSIX-only path
        raise AssertionError("the POSIX PTY path is POSIX-only")
    import termios

    attributes = termios.tcgetattr(fd)
    return attributes[0], attributes[1], attributes[3]


def _configure_line_discipline(fd: int) -> None:  # coverage: exclude-windows
    """Set the explicit, conventional terminal state on ``fd``.

    Recorded rather than inherited (design rule 5). Whether a fresh pty
    already carries this state is *not* assumed here — the binding's tests
    measure it — and setting it explicitly is what turns whatever the
    kernel happens to hand back into a contract, so a future default
    change becomes a test failure instead of an evidence change nobody
    notices.
    """
    if sys.platform == "win32":  # coverage: exclude-posix - POSIX-only path
        raise AssertionError("the POSIX PTY path is POSIX-only")
    import termios

    attributes = termios.tcgetattr(fd)
    iflag, oflag, cflag, lflag, ispeed, ospeed, cc = attributes
    iflag |= termios.ICRNL | termios.IXON
    iflag &= ~(termios.INLCR | termios.IGNCR)
    oflag |= termios.OPOST | termios.ONLCR
    lflag |= termios.ICANON | termios.ECHO | termios.ECHOE | termios.ISIG
    lflag &= ~termios.ECHONL
    termios.tcsetattr(
        fd,
        termios.TCSANOW,
        [iflag, oflag, cflag, lflag, ispeed, ospeed, cc],
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


class _suppress_os_errors:
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

    def __init__(self, process: subprocess.Popen[bytes], master_fd: int) -> None:
        self._process: subprocess.Popen[bytes] | None = process
        self._pid = process.pid
        self._master_fd = master_fd
        self._lock = threading.Lock()
        self._closed = False
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

        The wake pipe comes before any state the caller can observe, and it
        is the only fallible step here, so a failure leaves nothing to
        unwind. Both ends are non-blocking: a close signalling a full wake
        pipe would be a teardown blocking on its own interruption.
        """
        self._wake_read, self._wake_write = os.pipe()
        os.set_blocking(self._wake_write, False)
        os.set_blocking(self._wake_read, False)
        os.set_blocking(self._master_fd, False)

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
        return cls._spawn_posix(
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
                    command,
                    *arguments[1:],
                ],
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                env=merged,
                cwd=cwd,
                close_fds=True,
            )
        except BaseException:
            os.close(master_fd)
            raise
        finally:
            # The parent's copy goes as soon as the child owns its own: a
            # slave held here would keep the master readable forever, so a
            # child's exit would never surface as end-of-stream.
            os.close(slave_fd)
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
    def pid(self) -> int:
        return self._pid

    @property
    def exit_status(self) -> int | None:
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
        if process is None:
            return None
        status = process.poll()
        if status is None:
            return None
        with self._lock:
            self._exit_status = int(status)
            return self._exit_status

    def is_alive(self) -> bool:
        with self._lock:
            process = self._process
        return process is not None and process.poll() is None

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
                if error.errno == errno.EIO:
                    # A master whose last slave is gone reports EIO on
                    # Linux rather than an empty read. It is this
                    # platform's end-of-stream and is normalized to the
                    # binding's own signal — measured, not assumed.
                    raise self._end_of_stream() from error
                with self._lock:
                    closed = self._closed
                if closed:
                    raise PosixPtyClosedError(
                        "the POSIX PTY binding was closed during a read"
                    ) from error
                raise
            if not chunk:
                raise self._end_of_stream()
            return chunk

    def _end_of_stream(self) -> PosixPtyEndOfStreamError:
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
        with self._lock:
            if self._closed:
                raise PosixPtyClosedError("the POSIX PTY binding is closed")
            fd = self._master_fd
        _set_window_size(fd, rows=rows, columns=columns)

    def close(self, *, force: bool) -> None:  # coverage: exclude-windows
        """Release the pseudoterminal; optionally kill the session first.

        Ordering is the invariant ``_jsonl_pipe.py`` records and pays for:
        **signal the wake-up before terminating anything or touching any
        descriptor.** A blocked read or write is woken first, its delivery
        is waited for, and only then does the master descriptor go — so no
        syscall is ever left holding a descriptor number this method has
        already freed.
        """
        with self._lock:
            if self._closed:
                return
            process = self._process
            # Liveness is decided inline rather than through `is_alive`:
            # the lock is not reentrant, and calling a method that takes it
            # from inside the critical section would deadlock the teardown
            # this method exists to guarantee.
            if not force and process is not None and process.poll() is None:
                raise PosixPtyClosedError(
                    "a release-only close of a live pty child would abandon it;"
                    " use force=True"
                )
            self._closed = True
            wake = self._wake_write
        if wake >= 0:
            with _suppress_os_errors():
                os.write(wake, b"\x00")
        self._interrupted_read.wait(_IO_DELIVERY_WAIT_S)
        self._interrupted_write.wait(_IO_DELIVERY_WAIT_S)
        if process is not None:
            if force:
                self._terminate_session(process)
            self._capture_exit_status_after_close(process)
        self._release_descriptors()

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
        with _suppress_os_errors():
            os.killpg(process.pid, FORCED_TERMINATION_SIGNAL)

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
        if process is None:
            return
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
        for fd in (self._wake_read, self._wake_write):
            if fd >= 0:
                with _suppress_os_errors():
                    os.close(fd)
        self._wake_read = -1
        self._wake_write = -1
