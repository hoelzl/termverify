"""Real pipe/process binding for the JSONL control transport (slice 2).

This module is the thin native ownership layer under
``termverify.jsonl.JsonlAdapter``: one spawned subprocess per child, two
binary pipes (stdin write, stdout read), process-tree containment, and
honest exit records. It implements the ``JsonlChildPort`` shape from
``termverify.jsonl`` directly rather than importing it, mirroring the
``_conpty.py`` architecture: all adapter logic above the binding is
fake-driven and ratcheted, while this native boundary is proven by
real-subprocess integration tests and excluded from the coverage ratchet.

Pipes are portable, so this binding runs identically on Windows and POSIX:

- **Windows:** the child is assigned to a kill-on-close job object created
  per spawn (the ConPTY binding's proven pattern), so a forced close
  terminates the whole tree atomically with the uniform forced exit code
  15, and releasing the job handle sweeps any survivors even if this
  process dies abruptly. Disclosed boundary: assignment happens
  immediately after ``CreateProcess`` returns, so a process the child
  manages to start within that microseconds-wide window falls outside the
  job.
- **POSIX:** the child starts its own session (``start_new_session``), so
  the whole process group receives ``SIGKILL`` on a forced close. The
  observed exit record of a signal-killed child is the negative signal
  number reported by ``waitpid`` semantics.

A forced close closes the child's stdin first: a cooperative child blocked
on input observes end-of-stream and may exit on its own, but containment
(job object / process-group kill) is what guarantees the tree dies, and
the binding never waits on cooperation. ``exit_status`` is captured from
the real process only — a release-only close of a live child records no
exit status, never a fabricated one, and is refused outright because
silently abandoning a live pipe child has no honest reading.

I/O is single-flight by contract, matching the adapter's lifecycle: at
most one read and one write are ever in flight, and ``close`` is the one
concurrent-safe operation. A blocked ``read_line`` ends when the pipes are
closed underneath it by a concurrent forced close (the watchdog path);
that interruption surfaces as ``JsonlChildClosedError``, never as
end-of-stream, because close may have abandoned buffered output.
"""

from __future__ import annotations

import io
import os
import shutil
import subprocess
import sys
import threading
from collections.abc import Mapping, Sequence
from contextlib import suppress
from typing import IO, Final, cast

from termverify.control import _MAX_LINE_BYTES
from termverify.jsonl import JsonlChildClosedError, JsonlEndOfStreamError

__all__ = ["FORCED_TERMINATION_SIGNAL", "PipeJsonlChild"]

_CHILD_EXIT_WAIT_S: Final = 30.0
_WAIT_POLL_S: Final = 0.01
#: Bounded wait for an interrupted read to deliver its error after a
#: forced close has unblocked the syscall — far beyond any scheduling
#: delay, far below any hang a caller could mistake for liveness.
_READ_DELIVERY_WAIT_S: Final = 5.0

#: Exit code set on every process in the tree by a forced close on
#: Windows, kept identical to the ConPTY binding's convention.
_FORCED_TERMINATION_EXIT_CODE: Final = 15

#: Signal delivered to the child's process group by a forced close on
#: POSIX; the observed exit record is its negation.
FORCED_TERMINATION_SIGNAL: Final = 9  # SIGKILL


if sys.platform == "win32":  # pragma: no cover - Windows-only containment
    import ctypes
    from ctypes import wintypes

    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _kernel32.OpenProcess.restype = wintypes.HANDLE
    _kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    _kernel32.WaitForSingleObject.restype = wintypes.DWORD
    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    _kernel32.CloseHandle.restype = wintypes.BOOL
    _kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    _kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    _kernel32.SetInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    _kernel32.SetInformationJobObject.restype = wintypes.BOOL
    _kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    _kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
    _kernel32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
    _kernel32.TerminateJobObject.restype = wintypes.BOOL

    _SYNCHRONIZE = 0x0010_0000
    _PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    _PROCESS_SET_QUOTA = 0x0100
    _PROCESS_TERMINATE = 0x0001
    _WAIT_OBJECT_0 = 0
    _WAIT_TIMEOUT = 0x102
    _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
    _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000

    class _IoCounters(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_uint64),
            ("WriteOperationCount", ctypes.c_uint64),
            ("OtherOperationCount", ctypes.c_uint64),
            ("ReadTransferCount", ctypes.c_uint64),
            ("WriteTransferCount", ctypes.c_uint64),
            ("OtherTransferCount", ctypes.c_uint64),
        ]

    class _JobBasicLimits(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class _JobExtendedLimits(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", _JobBasicLimits),
            ("IoInfo", _IoCounters),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    def _create_containment_job() -> int:
        """Create a kill-on-close job object for one pipe child."""
        job = _kernel32.CreateJobObjectW(None, None)
        if not job:
            raise OSError(f"CreateJobObject failed: {ctypes.get_last_error()}")
        limits = _JobExtendedLimits()
        limits.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not _kernel32.SetInformationJobObject(
            job,
            _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
            ctypes.byref(limits),
            ctypes.sizeof(limits),
        ):
            error = ctypes.get_last_error()
            _kernel32.CloseHandle(job)
            raise OSError(f"SetInformationJobObject failed: {error}")
        return int(job)

    def _open_containment_handle(pid: int) -> int:
        """Open the child's real process handle for assignment and waits."""
        handle = _kernel32.OpenProcess(
            _SYNCHRONIZE
            | _PROCESS_QUERY_LIMITED_INFORMATION
            | _PROCESS_SET_QUOTA
            | _PROCESS_TERMINATE,
            False,
            pid,
        )
        if not handle:
            raise OSError(f"OpenProcess({pid}) failed: {ctypes.get_last_error()}")
        return int(handle)

    def _wait_for_handle(handle: int, timeout_ms: int) -> bool:
        """OS wait on a real handle; True once it is signaled, never a sleep."""
        result = int(_kernel32.WaitForSingleObject(handle, timeout_ms))
        if result == _WAIT_OBJECT_0:
            return True
        if result == _WAIT_TIMEOUT:
            return False
        raise OSError(
            f"WaitForSingleObject failed ({result:#x}): {ctypes.get_last_error()}"
        )


class PipeJsonlChild:
    """Thin ownership wrapper around one pipe-connected control-protocol child.

    Implements the ``JsonlChildPort`` shape: line I/O over the two binary
    pipes, an honest ``exit_status`` observed only from the real process,
    and a forced close that terminates the whole child tree.
    """

    def __init__(
        self,
        process: subprocess.Popen[bytes],
        *,
        job: int | None = None,
        process_handle: int | None = None,
    ) -> None:
        self._process: subprocess.Popen[bytes] | None = process
        self._pid = process.pid
        self._job = job
        self._process_handle = process_handle
        self._exit_status: int | None = None
        self._read_buffer = bytearray()
        self._lock = threading.Lock()
        self._closed = False
        self._closing = False
        self._close_done = threading.Event()
        self._read_in_flight = False
        self._interrupted_read = threading.Event()
        self._interrupted_read.set()

    @classmethod
    def spawn(
        cls,
        argv: Sequence[str],
        *,
        env_overlay: Mapping[str, str] | None = None,
        cwd: str | None = None,
    ) -> PipeJsonlChild:
        """Spawn a contained pipe child speaking the control protocol.

        ``env_overlay`` variables are overlaid onto this process's ambient
        environment at spawn time; an overlay variable always wins over an
        ambient variable of the same name. Disclosed: the child inherits
        the ambient environment underneath the overlay — ambient contents
        are not evidence and are not recorded, only the overlay is. ``cwd``
        selects the child's working directory; without it, the child
        starts in this process's current directory.

        On Windows the child is assigned to a fresh kill-on-close job
        object before the binding is returned; if containment cannot be
        established, the child is terminated and the spawn fails closed —
        no uncontained session is ever handed out. On POSIX the child
        starts its own session so a forced close can kill its process
        group.
        """
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
        process = subprocess.Popen(  # noqa: S603 - argv is a validated list
            [command, *arguments[1:]],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=merged,
            cwd=cwd,
            start_new_session=os.name != "nt",
        )
        if sys.platform == "win32":  # pragma: no cover - Windows-only containment leg
            job: int | None = None
            process_handle: int | None = None
            try:
                job = _create_containment_job()
                process_handle = _open_containment_handle(process.pid)
                _kernel32.AssignProcessToJobObject(job, process_handle)
            except OSError as error:
                process.kill()
                process.wait()
                if process_handle is not None:
                    _kernel32.CloseHandle(process_handle)
                if job is not None:
                    _kernel32.CloseHandle(job)
                raise OSError(
                    f"failed to contain pipe child {process.pid} in a job object"
                ) from error
            return cls(process, job=job, process_handle=process_handle)
        return cls(process)

    @property
    def pid(self) -> int:
        """Return the child's OS process id."""
        return self._pid

    def write_line(self, line: bytes) -> None:
        """Write one framed message line to the child's stdin.

        Raises :class:`JsonlChildClosedError` when the binding was closed,
        and :class:`BrokenPipeError` when the child's end of the pipe is
        gone (the child exited); both surface through the adapter's
        classified failure paths.
        """
        with self._lock:
            stdin = self._stdin()
        stdin.write(line)
        stdin.flush()

    def read_line(self) -> bytes:
        """Read one framed message line from the child's stdout.

        Raises :class:`JsonlEndOfStreamError` at end-of-stream — only
        after every buffered line has been delivered — and
        :class:`JsonlChildClosedError` when the binding was closed before
        or while the read was in flight.

        Memory is bounded: once the accumulating buffer exceeds the
        ``termverify.control/v1`` line ceiling without an LF, the
        oversized buffer is returned as-is; ``parse_message`` rejects it
        by length, so a newline-free flood fails as peer-malformed
        instead of growing the buffer without bound.

        Single-flight: one in-flight read at a time (the port contract);
        the binding tracks it so a forced close can interrupt the blocked
        syscall and then wait — bounded, without holding the lock — for
        the interrupted read to deliver its error, handing ownership back
        only once no read is still unwinding.
        """
        with self._lock:
            if self._closed:
                raise JsonlChildClosedError("the JSONL pipe binding is closed")
            if self._read_in_flight:
                raise JsonlChildClosedError(
                    "the JSONL pipe binding allows one in-flight read"
                )
            self._read_in_flight = True
            self._interrupted_read.clear()
        try:
            return self._read_line_tracked()
        finally:
            with self._lock:
                self._read_in_flight = False
                self._interrupted_read.set()

    def _read_line_tracked(self) -> bytes:
        while True:
            with self._lock:
                if self._closed:
                    raise JsonlChildClosedError("the JSONL pipe binding is closed")
            newline = self._read_buffer.find(b"\n")
            if newline >= 0:
                line = bytes(self._read_buffer[: newline + 1])
                del self._read_buffer[: newline + 1]
                return line
            with self._lock:
                if self._closed:
                    raise JsonlChildClosedError("the JSONL pipe binding is closed")
                stdout = self._stdout()
            try:
                chunk = stdout.read1(65_536)
            except (OSError, ValueError) as error:
                with self._lock:
                    closed = self._closed
                if closed:
                    raise JsonlChildClosedError(
                        "the JSONL pipe binding was closed during a read"
                    ) from error
                raise
            if not chunk:
                with self._lock:
                    closed = self._closed
                if closed:
                    raise JsonlChildClosedError(
                        "the JSONL pipe binding was closed during a read"
                    )
                if self._read_buffer:
                    line = bytes(self._read_buffer)
                    self._read_buffer.clear()
                    return line
                self._capture_exit_status_after_eos()
                raise JsonlEndOfStreamError("the child's stdout reported end-of-stream")
            self._read_buffer.extend(chunk)
            if len(self._read_buffer) > _MAX_LINE_BYTES + 1:
                line = bytes(self._read_buffer)
                self._read_buffer.clear()
                return line

    def close(self, *, force: bool) -> None:
        """Release ownership; with ``force``, terminate the child's tree.

        The forced path relies on containment — the Windows job object
        terminated with the uniform forced exit code, or the POSIX
        process-group ``SIGKILL`` — to end the whole tree, waits for the
        real exit, and captures the observed exit record. A second close
        arriving while another thread's close is in flight waits for that
        teardown to finish, so callers never observe a half-closed
        binding (the adapter consults ``exit_status`` right after
        closing).

        A release-only close of a child that already exited captures its
        exit record and releases the handles. A release-only close of a
        live child is refused: abandoning a live pipe child would either
        leak the tree (no containment is in force) or kill it while
        claiming otherwise, and the binding does not fabricate either.
        """
        interrupted: threading.Event | None = None
        with self._lock:
            if self._closed:
                # Another close owns the teardown; wait for it to finish
                # so callers never observe a half-closed binding (the
                # adapter consults exit_status right after closing).
                done = self._close_done if self._closing else None
                if done is None:
                    return
            else:
                self._closed = True
                self._closing = True
                done = None
                process = self._process
                job = self._job
                process_handle = self._process_handle
                self._process = None
                self._job = None
                self._process_handle = None
                if self._read_in_flight:
                    interrupted = self._interrupted_read
        if done is not None:
            done.wait()
            return
        assert process is not None
        live = process.poll() is None
        if live and not force:
            # Refusal must be a true no-op: restore ownership so the
            # binding is exactly as it was — still usable, and a later
            # forced close can still tear the live tree down honestly.
            # Nothing outside this lock window has run yet (no read can
            # have been interrupted: the tree was never terminated).
            with self._lock:
                self._process = process
                self._job = job
                self._process_handle = process_handle
                self._closed = False
                self._closing = False
            raise RuntimeError(
                "a release-only close of a live JSONL pipe child is"
                " refused: the binding never abandons a live tree"
                " and never fabricates an exit record"
            )
        try:
            if live:
                # Kill FIRST: the child's death closes its stdout
                # write-end, which is the reliable interruption of a read
                # blocked in ReadFile on another thread — closing the
                # parent's handle or CancelIoEx on a synchronous anonymous
                # pipe does not reliably deliver that. The interrupted
                # read surfaces JsonlChildClosedError (the closed flag is
                # already set), never end-of-stream — close may have
                # abandoned buffered output.
                self._terminate_tree(process, job)
            if interrupted is not None:
                # The interrupted read is unblocked but may not yet have
                # delivered its JsonlChildClosedError; handing ownership
                # back this instant would let a caller observe a closed
                # binding with a read still unwinding. Wait — bounded,
                # without the lock — for that delivery.
                interrupted.wait(timeout=_READ_DELIVERY_WAIT_S)
            self._wait_out(process, process_handle)
            try:
                status = process.wait(timeout=_CHILD_EXIT_WAIT_S)
            except subprocess.TimeoutExpired as error:
                raise OSError(
                    f"pipe child {self._pid} was not reaped after termination"
                ) from error
            self._exit_status = int(status)
        finally:
            self._close_pipes(process)
            if (
                process_handle is not None and sys.platform == "win32"
            ):  # pragma: no cover - Windows-only leg
                _kernel32.CloseHandle(process_handle)
            if (
                job is not None and sys.platform == "win32"
            ):  # pragma: no cover - Windows-only leg
                # Kill-on-close sweeps every remaining job member, so even
                # a failed graceful path cannot leak the tree.
                _kernel32.CloseHandle(job)
            with self._lock:
                self._closing = False
                self._close_done.set()

    @property
    def exit_status(self) -> int | None:
        """Return the OS-observed exit status, else ``None``.

        On POSIX a signal termination is the negative signal number, per
        ``waitpid`` semantics; a forced close therefore reports
        ``-FORCED_TERMINATION_SIGNAL``. On Windows a forced close reports
        the uniform forced exit code 15.

        A claimed exit that has not yet been reaped (the child sent
        ``run.finished`` and is exiting) is allowed a short bounded
        grace; a child that never exits reports ``None`` after it.
        """
        self._capture_exit_status_with_grace()
        return self._exit_status

    # --- internals ---------------------------------------------------------

    def _stdin(self) -> IO[bytes]:
        if self._closed or self._process is None or self._process.stdin is None:
            raise JsonlChildClosedError("the JSONL pipe binding is closed")
        return self._process.stdin

    def _stdout(self) -> io.BufferedReader:
        if self._closed or self._process is None or self._process.stdout is None:
            raise JsonlChildClosedError("the JSONL pipe binding is closed")
        # Popen(stdin=PIPE, stdout=PIPE) wires the buffered streams; the
        # single construction path guarantees it.
        return cast("io.BufferedReader", self._process.stdout)

    def _terminate_tree(
        self, process: subprocess.Popen[bytes], job: int | None
    ) -> None:
        # Detach the buffered stdin writer first: it may hold unflushed
        # input, and ``stdin.close`` (here or in ``_close_pipes``) would
        # flush it before closing — a child that is not draining its
        # pipe (the exact hang the abort deadline exists for) would
        # block that flush forever. The forced teardown must release
        # the handle, never flush.
        if process.stdin is not None:
            with _suppress_os_errors():
                cast("io.BufferedWriter", process.stdin).detach()
        if sys.platform == "win32":  # pragma: no cover - Windows-only containment leg
            if job is None:
                # Defensive: unreachable on the only construction path.
                raise OSError("no containment job to terminate")
            _kernel32.TerminateJobObject(job, _FORCED_TERMINATION_EXIT_CODE)
        else:
            with suppress(ProcessLookupError):
                os.killpg(process.pid, FORCED_TERMINATION_SIGNAL)  # type: ignore[attr-defined,unused-ignore]

    def _wait_out(
        self, process: subprocess.Popen[bytes], process_handle: int | None
    ) -> None:
        """Wait for the real exit; on Windows prefer the handle wait."""
        if (
            sys.platform == "win32" and process_handle is not None
        ):  # pragma: no cover - Windows-only leg
            if not _wait_for_handle(process_handle, int(_CHILD_EXIT_WAIT_S * 1000)):
                raise OSError(
                    f"pipe child {self._pid} did not terminate on forced close"
                )
            process.wait(timeout=_CHILD_EXIT_WAIT_S)
            return
        try:
            process.wait(timeout=_CHILD_EXIT_WAIT_S)
        except subprocess.TimeoutExpired as error:
            raise OSError(
                f"pipe child {self._pid} did not terminate on forced close"
            ) from error

    def _capture_exit_status(self) -> None:
        if self._exit_status is not None:
            return
        process = self._process
        if process is None:
            return
        status = process.poll()
        if status is not None:
            self._exit_status = int(status)

    _REAP_GRACE_S: Final = 2.0

    def _capture_exit_status_with_grace(self) -> None:
        """Capture, allowing a bounded reaping window for a claimed exit.

        The protocol sequence ``run.finished`` followed by the child's
        actual exit makes the exit imminent at the moment the adapter
        consults ``exit_status``; a bare ``poll`` can read ``None``
        inside the OS reaping gap and the run would fail as
        peer-lifecycle despite a cooperating child. The window is
        deliberately short: a child that claims an exit and then keeps
        running is a protocol breach, and the grace must not turn that
        breach into a hang — after it, ``None`` stands and the adapter's
        fail-closed path reports the missing record.
        """
        if self._exit_status is not None:
            return
        process = self._process
        if process is None:
            return
        try:
            self._exit_status = int(process.wait(timeout=self._REAP_GRACE_S))
        except subprocess.TimeoutExpired:
            return

    def _capture_exit_status_after_eos(self) -> None:
        """Capture after end-of-stream: the child has exited by definition.

        The OS may not have reaped the child at the moment its stdout
        closes (``sys.exit`` flushes and closes the pipe before the exit
        completes), so a single ``poll`` can still read ``None``. The
        wait is bounded: on an end-of-stream the exit has already
        happened, so it is a reaping delay, never a liveness guess.
        """
        if self._exit_status is not None:
            return
        process = self._process
        if process is None:
            return
        try:
            self._exit_status = int(process.wait(timeout=_CHILD_EXIT_WAIT_S))
        except subprocess.TimeoutExpired as error:
            raise OSError(
                f"pipe child {self._pid} was not reaped after end-of-stream"
            ) from error

    def _close_pipes(self, process: subprocess.Popen[bytes]) -> None:
        for pipe in (process.stdin, process.stdout):
            if pipe is not None:
                with _suppress_os_errors():
                    # Detach first: ``close`` on the buffered stdin writer
                    # would flush any leftover input before closing, and a
                    # terminated child never drains it — the forced
                    # teardown must release the handle, not flush.
                    cast("io.BufferedIOBase", pipe).detach()
                with _suppress_os_errors():
                    pipe.close()


class _suppress_os_errors:
    """Context manager: pipe teardown ignores already-gone descriptors."""

    def __enter__(self) -> None:
        return None

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
        return isinstance(exc_type, type) and issubclass(
            exc_type, (OSError, ValueError)
        )
