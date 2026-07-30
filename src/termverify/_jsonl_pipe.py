"""Real pipe/process binding for the JSONL control transport (slice 2).

This module is the thin native ownership layer under
``termverify.jsonl.JsonlAdapter``: one spawned subprocess per child, two
binary pipes (stdin write, stdout read), process-tree containment, and
honest exit records. It implements the ``JsonlChildPort`` shape from
``termverify.jsonl`` directly rather than importing it, mirroring the
``_conpty.py`` architecture: all adapter logic above the binding is
fake-driven and ratcheted, while this native boundary is proven by
real-subprocess integration tests. Unlike ``_conpty.py`` this module is
not listed in coverage's ``omit``. Its platform legs carry
``# coverage: exclude-posix`` / ``# coverage: exclude-windows`` markers
instead of bare ``# pragma: no cover``, because a bare pragma is a static
source exclusion that removes the leg from measurement on **every**
platform (issue #230). The CI quality legs point ``COVERAGE_RCFILE`` at a
per-OS overlay (``coverage-windows.toml`` / ``coverage-posix.toml``) that
excludes only the legs which cannot run on that platform, so each leg is
ratcheted exactly where it runs; local ``pytest --cov`` runs keep both
markers excluded via ``pyproject.toml``, which is honest because CI
measures them per-OS.

Pipes are portable, so process ownership and framing are identical on
Windows and POSIX. Interrupting blocked I/O is not, and that difference
is stated below rather than smoothed over:

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

Interrupting blocked I/O is where the two platforms genuinely differ, and
the difference is a mechanism difference, not a strength claim:

- **POSIX** owns both pipes as raw descriptors and waits on ``poll``
  over the descriptor *and* a self-pipe, so any close that proceeds wakes
  a blocked read or write outright (a release-only close of a live child
  is refused before it signals anything, and leaves the binding usable).
  This does not depend on reaching whoever holds
  the other end, which is what makes it answer review finding R4: a
  ``setsid()`` descendant escapes ``killpg`` and can hold the child's
  stdout write end open forever, and the reader still ends — as a closed
  binding, promptly, with the run classified honestly.
- **Windows** cannot: ``select`` does not work on anonymous pipe handles.
  There the child's death closes its stdout write end, and that remains
  the interruption, so a forced close terminates the tree first. A holder
  outside the job — a process started inside the disclosed assignment
  window, or a descendant of a child that exited before assignment — is
  not swept and can still stall the teardown's pipe release (issue #213).

A forced close terminates the tree and releases the child's stdin second.
On POSIX the wake-up precedes both, so a write blocked against a child
that stopped draining its stdin ends without waiting for anything; the
old ordering argument for that case (kill first so the flush fails fast)
belonged to the buffered writer, which POSIX no longer uses at teardown
at all. On Windows the buffered writer stands, and ``detach`` flushes it
(issue #217): the ordering is what keeps that flush bounded, and it is
bounded *because the tree is already dead*, which is the honest statement
of it.

``exit_status`` is captured from the real process only — a release-only
close of a live child records no exit status, never a fabricated one, and
is refused outright because silently abandoning a live pipe child has no
honest reading.

Disclosed on every platform: a process that has left the containment is
**not reaped**. Reaping it portably would need cgroups or a subreaper,
rejected as horizontal platform machinery. What the binding guarantees is
narrower and true — such a survivor cannot stall the run's teardown on
POSIX, and cannot make the run report anything it did not observe.

I/O is single-flight by contract, matching the adapter's lifecycle: at
most one read and one write are ever in flight, and ``close`` is the one
concurrent-safe operation. An interrupted ``read_line`` surfaces as
``JsonlChildClosedError``, never as end-of-stream, because close may have
abandoned buffered output.
"""

from __future__ import annotations

import io
import os
import select
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

#: Bytes requested per native read; the framing layer above reassembles.
_READ_CHUNK_BYTES: Final = 65_536

#: One byte is a wake-up. The self-pipe is never drained, so once a close
#: has signaled it every later read and write wakes immediately too, which
#: is the behavior a closed binding owes its callers anyway.
_WAKE_BYTE: Final = b"\x00"


if sys.platform == "win32":  # coverage: exclude-posix - Windows-only containment
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

    def _assign_to_job(job: int, process_handle: int) -> None:
        """Contain the child; a failed BOOL means it is *not* contained."""
        if not _kernel32.AssignProcessToJobObject(job, process_handle):
            raise OSError(f"AssignProcessToJobObject failed: {ctypes.get_last_error()}")

    def _terminate_job(job: int, exit_code: int) -> None:
        """Terminate every job member; a failed BOOL is a real failure."""
        if not _kernel32.TerminateJobObject(job, exit_code):
            raise OSError(f"TerminateJobObject failed: {ctypes.get_last_error()}")

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
        self._write_in_flight = False
        self._interrupted_write = threading.Event()
        self._interrupted_write.set()
        self._wake_read = -1
        self._wake_write = -1
        self._raw_stdin: io.RawIOBase | None = None
        self._raw_stdout: io.RawIOBase | None = None
        if sys.platform != "win32":  # coverage: exclude-windows - POSIX-only leg
            self._adopt_posix_descriptors(process)

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
        object before the binding is returned; every containment call's
        result is checked, so if containment cannot be established the
        child is terminated, its handles and pipes are released, and the
        spawn fails closed — no uncontained live child is handed out.

        One case is not a failure, and it is a disclosed boundary rather
        than a guarantee: a child that has already exited cannot be
        assigned at all (Windows answers ERROR_ACCESS_DENIED for an exited
        process), so a subject that wins the race against its own
        containment is handed out with its real exit record instead of
        being blamed for a containment failure. Such a binding's job is
        **permanently empty** — job membership comes only from assignment
        or from inheritance through a member — so it contains nothing, and
        no later close can terminate a descendant the exited child left
        behind. This is the same window already disclosed above for
        descendants started before assignment; it is not widened by
        handing the binding out, because failing the spawn would not
        contain that descendant either, only misreport the cause. A
        descendant that inherits the child's stdout write end can also
        block the teardown's pipe release indefinitely — on Windows only,
        which is where this whole paragraph applies: POSIX wakes its own
        blocked I/O through the self-pipe and does not depend on reaching
        the holder at all (issue #213).

        On POSIX the child starts its own session so a forced close can
        kill its process group.
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
        if sys.platform == "win32":  # coverage: exclude-posix - containment
            job: int | None = None
            process_handle: int | None = None
            try:
                job = _create_containment_job()
                process_handle = _open_containment_handle(process.pid)
                _assign_to_job(job, process_handle)
            except OSError as error:
                if (
                    job is not None
                    and process_handle is not None
                    and process.poll() is not None
                ):
                    # The child already exited, so assignment was refused
                    # on a corpse (ERROR_ACCESS_DENIED) and there is no
                    # live session to protect: a fast subject is
                    # legitimate, and failing its spawn would blame
                    # containment for a race the child simply won. The
                    # binding reports the real exit record. Disclosed, not
                    # guaranteed: this job stays empty forever — nothing
                    # can join a job its member was never assigned to —
                    # so a descendant the child left behind is
                    # uncontained, exactly as in the assignment window
                    # this leg sits inside. See the spawn docstring.
                    return cls(process, job=job, process_handle=process_handle)
                try:
                    process.kill()
                    process.wait(timeout=_CHILD_EXIT_WAIT_S)
                finally:
                    # Release every resource even if the child cannot be
                    # reaped: a TimeoutExpired is not an OSError and would
                    # otherwise escape unclassified, leaking two kernel
                    # handles and both pipes on the way out.
                    _release_pipes(process)
                    if process_handle is not None:
                        _kernel32.CloseHandle(process_handle)
                    if job is not None:
                        _kernel32.CloseHandle(job)
                raise OSError(
                    f"failed to contain pipe child {process.pid} in a job object"
                ) from error
            return cls(process, job=job, process_handle=process_handle)
        try:  # coverage: exclude-windows - POSIX-only leg
            return cls(process)
        except OSError as error:
            # Construction can now fail: adopting the descriptors calls
            # `os.pipe`, which fails on EMFILE/ENFILE. Fail closed like the
            # Windows containment leg rather than leaking a live child and
            # both pipes — the spawn contract is that no child outlives a
            # failed spawn (adversarial review, finding m5).
            try:
                process.kill()
                process.wait(timeout=_CHILD_EXIT_WAIT_S)
            except (OSError, subprocess.TimeoutExpired):
                pass
            finally:
                _release_pipes(process)
            raise OSError(
                f"failed to adopt the pipe descriptors for child {process.pid}"
            ) from error

    def _adopt_posix_descriptors(
        self, process: subprocess.Popen[bytes]
    ) -> None:  # coverage: exclude-windows - POSIX-only leg
        """Take the two pipes as raw descriptors, plus a wake-up pipe.

        Detaching here, in the constructor, is the one moment at which it
        is provably free, and the two wrappers are free for *different*
        reasons. ``BufferedWriter.detach`` **flushes** (issue #217) — the
        buffered layer offers no release-without-flush operation — so a
        teardown-time detach against a child that never drains its stdin
        can block on the very path that exists to guarantee a bounded
        failure. ``BufferedReader.detach`` does not flush; it **silently
        discards** whatever it has buffered, so detaching a reader that has
        already read would lose bytes with no error at all.

        Both are safe here because of the *call site*, not because of
        ``detach``: this runs only ever straight out of
        ``subprocess.Popen``, so neither buffer has been used. Constructing
        from a ``Popen`` that has been read from or written to would break
        the claim silently — hence writing the invariant down rather than
        leaving it to be inferred. For the same reason the ``Popen`` must
        never be used as a context manager: ``__exit__`` calls ``close``
        on both wrappers, which raises once they are detached.

        What this buys beyond the flush: the buffered objects also own
        locks. A read blocked inside ``BufferedReader.read1`` holds one,
        and every later ``detach``/``close`` waits on it — which is how a
        blocked read turned a forced close into a permanent hang inside a
        ``finally`` (#213). Owning raw descriptors leaves no lock to
        inherit, and ``select`` over the descriptor plus this wake-up pipe
        gives the binding an interruption it owns outright, instead of
        borrowing one from containment that a descendant can escape.

        Both descriptors are non-blocking: with ``select`` deciding when
        to move bytes, a partial read or write must report itself rather
        than block, and a write that would block must return control so
        the wake-up pipe can still be observed.
        """
        stdin = cast("io.BufferedWriter | None", process.stdin)
        stdout = cast("io.BufferedReader | None", process.stdout)
        # Popen(stdin=PIPE, stdout=PIPE) wires both; the single
        # construction path guarantees it.
        assert stdin is not None and stdout is not None
        # The wake pipe comes FIRST, because it is the only step here that
        # can fail (`os.pipe` raises on EMFILE/ENFILE). Detaching is the
        # point of no return: once the wrappers are detached, `spawn`'s
        # fail-closed path cannot release the child's descriptors through
        # them — every call raises `ValueError: raw stream has been
        # detached`, which `_suppress_os_errors` swallows, so the release
        # closes nothing and two descriptors survive on a path whose
        # trigger is descriptor exhaustion. Ordering the fallible step
        # before the irreversible one makes the failure leave the object
        # exactly as `spawn` found it (adversarial review round 2, J2).
        self._wake_read, self._wake_write = os.pipe()
        # The writer must never block: a close signaling a full wake pipe
        # would be a teardown blocking on its own interruption mechanism.
        os.set_blocking(self._wake_write, False)
        os.set_blocking(self._wake_read, False)
        self._raw_stdin = stdin.detach()
        self._raw_stdout = stdout.detach()
        os.set_blocking(self._raw_stdin.fileno(), False)
        os.set_blocking(self._raw_stdout.fileno(), False)

    def _signal_wake(self) -> None:  # coverage: exclude-windows - POSIX-only leg
        """Wake any blocked read or write. Idempotent and never blocking."""
        if self._wake_write < 0:
            return
        with _suppress_os_errors():
            os.write(self._wake_write, _WAKE_BYTE)

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
        if sys.platform != "win32":  # coverage: exclude-windows - POSIX-only leg
            with self._lock:
                if self._closed or self._raw_stdin is None:
                    raise JsonlChildClosedError("the JSONL pipe binding is closed")
                if self._write_in_flight:
                    # Single-flight is a port contract the adapter honors,
                    # so this is defense in depth — but the asymmetry it
                    # removes ran the wrong way: an unenforced overlapping
                    # read fails as a hang, an unenforced overlapping write
                    # fails as silent corruption, because the second
                    # writer's `finally` would clear the in-flight flag
                    # while the first is still inside `os.write` and a
                    # close would then free the descriptor under it.
                    raise JsonlChildClosedError(
                        "the JSONL pipe binding allows one in-flight write"
                    )
                fd = self._raw_stdin.fileno()
                wake = self._wake_read
                # Tracked exactly like a read, and for the same reason: a
                # close must not close this descriptor while a write is
                # still inside `poll`/`os.write` on it. Untracked, the fd
                # number is free the instant `_close_pipes` runs, and any
                # concurrent `open` in the process can reuse it — the write
                # would then put control-protocol bytes into an unrelated
                # file. Trading a hang for silent corruption is strictly
                # worse than the hang (adversarial review, finding M3).
                self._write_in_flight = True
                self._interrupted_write.clear()
            try:
                self._write_all(fd, wake, line)
            finally:
                with self._lock:
                    self._write_in_flight = False
                    self._interrupted_write.set()
            return
        with self._lock:
            stdin = self._stdin()
        stdin.write(line)
        stdin.flush()

    def _write_all(
        self, fd: int, wake: int, line: bytes
    ) -> None:  # coverage: exclude-windows - POSIX-only leg
        """Write every byte, waiting for writability, wakeable throughout.

        A child that has stopped draining its stdin fills the pipe buffer
        and the write would otherwise block with no way out. Waiting on
        the wake-up pipe alongside the descriptor means a concurrent close
        ends the write as a closed binding — the same interruption the
        reader gets, so the adapter's deadline can produce a structured
        failure on either direction.

        Both descriptors are passed in, snapshotted under the lock by the
        caller. Re-reading ``self._wake_read`` here would race a close that
        has already reset it to -1, and ``poll`` rejects a negative
        descriptor with a ``ValueError`` that is not this binding's
        documented closed error.
        """
        view = memoryview(line)
        while view:
            if _wait_until_ready(fd, wake, write=True):
                raise JsonlChildClosedError(
                    "the JSONL pipe binding was closed during a write"
                )
            try:
                written = os.write(fd, view)
            except BlockingIOError:
                # Writability can be lost between the poll and the write;
                # wait again rather than failing a write that can proceed.
                continue
            view = view[written:]

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
        once no read is still unwinding.

        Disclosed residual: that wait is bounded, and on expiry the close
        proceeds anyway. It is a very strong probability reduction rather
        than a proof — after the wake-up, ``poll`` returns at once and
        neither ``os.read`` nor ``os.write`` can block on a non-blocking
        descriptor, so only scheduler starvation reaches the timeout — but
        it is not the guarantee an unqualified "only once" would claim.
        """
        with self._lock:
            if self._closed:
                raise JsonlChildClosedError("the JSONL pipe binding is closed")
            if self._read_in_flight:
                # A caller defect, not a subject failure: the closed error
                # is classified as a peer failure by the adapter, so a
                # violated single-flight contract must not wear it.
                raise RuntimeError("the JSONL pipe binding allows one in-flight read")
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
            try:
                chunk = self._read_chunk()
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
            if (
                len(self._read_buffer) > _MAX_LINE_BYTES + 1
                and b"\n" not in self._read_buffer
            ):
                # Memory bound, not framing: only an LF-free over-ceiling
                # buffer can never become a valid line. A buffered LF means
                # complete lines exist — the loop top drains them, and an
                # oversized *framed* line is still rejected by length in
                # parse_message, never here.
                line = bytes(self._read_buffer)
                self._read_buffer.clear()
                return line

    def _read_chunk(self) -> bytes:
        """Read one native chunk, wakeable on POSIX, buffered on Windows.

        On POSIX the reader waits on the child's stdout **and** the
        binding's own wake-up pipe, so a close ends the read whoever holds
        the write end. That is the whole point: containment can only
        unblock a reader by ending the process that holds the other end,
        and a ``setsid()`` descendant is not a process this binding can
        end (finding R4). On Windows ``select`` does not work on anonymous
        pipe handles, so the buffered read stands and the job object
        remains the interruption — with the out-of-job holder disclosed.
        """
        if sys.platform == "win32":  # coverage: exclude-posix - Windows-only leg
            with self._lock:
                if self._closed:
                    raise JsonlChildClosedError("the JSONL pipe binding is closed")
                stdout = self._stdout()
            return stdout.read1(_READ_CHUNK_BYTES)
        with self._lock:  # coverage: exclude-windows - POSIX-only leg
            if self._closed or self._raw_stdout is None:
                raise JsonlChildClosedError("the JSONL pipe binding is closed")
            fd = self._raw_stdout.fileno()
            # Snapshotted with the descriptor, never re-read below: a close
            # resets it to -1, and a negative descriptor is a `ValueError`
            # from `poll`, not this binding's documented closed error.
            wake = self._wake_read
        while True:  # coverage: exclude-windows - POSIX-only leg
            if _wait_until_ready(fd, wake, write=False):
                raise JsonlChildClosedError(
                    "the JSONL pipe binding was closed during a read"
                )
            try:
                return os.read(fd, _READ_CHUNK_BYTES)
            except BlockingIOError:
                # Readability can be lost between the poll and the read;
                # wait again rather than reporting a spurious end-of-stream,
                # which an empty return would be indistinguishable from.
                continue

    def close(self, *, force: bool) -> None:
        """Release ownership; with ``force``, terminate the child's tree.

        The forced path relies on containment — the Windows job object
        terminated with the uniform forced exit code, or the POSIX
        process-group ``SIGKILL`` — to end every contained process, waits
        for the real exit, and captures the observed exit record. A
        containment call that fails is raised, not swallowed: the teardown
        releases the job handle before it touches the pipes, so
        kill-on-close still sweeps every remaining job *member* — which
        also unblocks a read blocked on a member's pipe — and the caller
        is told the termination failed rather than reading a success the
        binding cannot vouch for. What that does not cover is a process
        outside the job: a descendant started inside the disclosed
        assignment window, or any descendant of a child that exited before
        assignment (see :meth:`spawn`). Such a process is not swept, and
        if it holds the child's stdout write end it can block the pipe
        release indefinitely — issue #213, and Windows-only: the sentences
        about the job object describe the platform that has one, while
        POSIX interrupts its own blocked I/O and never waits on the
        holder. On the raising path the exit
        record is not captured: the raise is the result, and
        ``exit_status`` stays ``None``. A second close
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
        interrupted_write: threading.Event | None = None
        with self._lock:
            if self._closed:
                # Another close owns the teardown; wait for it to finish
                # so callers never observe a half-closed binding (the
                # adapter consults exit_status right after closing).
                done = self._close_done if self._closing else None
                if done is None:
                    return
            else:
                process = self._process
                assert process is not None
                # The refusal is decided before any closed state exists,
                # inside the same lock window, so a concurrent read never
                # observes a transiently closed binding that is about to
                # refuse. `poll` is a non-blocking liveness probe; holding
                # the lock across it is safe.
                live = process.poll() is None
                if live and not force:
                    raise RuntimeError(
                        "a release-only close of a live JSONL pipe child is"
                        " refused: the binding never abandons a live tree"
                        " and never fabricates an exit record"
                    )
                self._closed = True
                self._closing = True
                done = None
                job = self._job
                process_handle = self._process_handle
                self._process = None
                self._job = None
                self._process_handle = None
                if self._read_in_flight:
                    interrupted = self._interrupted_read
                if self._write_in_flight:
                    interrupted_write = self._interrupted_write
        if done is not None:
            done.wait()
            return
        # Only the teardown-owning path reaches here, so the else branch
        # above ran and bound the child; restated for the type checker,
        # whose narrowing does not survive the branch join.
        assert process is not None
        # Wake FIRST, before termination and before any descriptor is
        # touched. On POSIX this is the binding's own interruption and it
        # cannot fail: a blocked read or write ends as a closed binding
        # whoever holds the other end of the pipe, including a descendant
        # no containment here can reach (finding R4, issues #213/#217).
        # It is also the general form of the invariant the Windows handle
        # ordering already follows — release every mechanism that can
        # unblock an operation before performing one that can block on it.
        if sys.platform != "win32":  # coverage: exclude-windows - POSIX-only leg
            self._signal_wake()
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
            if interrupted_write is not None:
                # Same wait for the other direction, and it is not
                # symmetry for its own sake: `_close_pipes` frees the
                # stdin descriptor's *number*, and a write still inside
                # `os.write` on it would then be writing into whatever
                # the process opened next.
                interrupted_write.wait(timeout=_READ_DELIVERY_WAIT_S)
            self._wait_out(process, process_handle)
            try:
                status = process.wait(timeout=_CHILD_EXIT_WAIT_S)
            except subprocess.TimeoutExpired as error:
                raise OSError(
                    f"pipe child {self._pid} was not reaped after termination"
                ) from error
            self._exit_status = int(status)
        finally:
            if (
                job is not None and sys.platform == "win32"
            ):  # coverage: exclude-posix - Windows-only leg
                # Kill-on-close sweeps every remaining job member, so even
                # a failed graceful path cannot leak a *contained* process.
                # Release it before the pipes: a member still alive here —
                # after a failed TerminateJobObject — may hold the write
                # end a blocked read is waiting on, and that read owns the
                # pipe's lock, so ``_close_pipes``' detach would wait on
                # the lock forever and never reach this release. Sweeping
                # first ends the member, which unblocks the read, which
                # lets the pipes close. A write-end holder *outside* the
                # job is not swept and can still stall the release (#213).
                _kernel32.CloseHandle(job)
            if (
                process_handle is not None and sys.platform == "win32"
            ):  # coverage: exclude-posix - Windows-only leg
                _kernel32.CloseHandle(process_handle)
            self._close_pipes(process)
            # Reap opportunistically, never by waiting: on the raising path
            # the child was not reaped in the ``try``, and kill-on-close has
            # usually ended it by now. A non-blocking poll releases the OS
            # record without turning a failed teardown into another wait —
            # and cannot set an exit record, so ``exit_status`` stays
            # ``None`` exactly as documented.
            with _suppress_os_errors():
                process.poll()
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
        # Kill first, release the writer second — a **Windows** ordering
        # argument, kept because Windows still has a buffered writer here.
        # ``detach`` on a ``BufferedWriter`` flushes whatever it still
        # holds (the buffered layer offers no release-without-flush
        # operation, #217), and against the subject this teardown exists
        # for — one that never drains its stdin, with a full pipe buffer —
        # that flush blocks forever. Ending the tree first makes the flush
        # fail fast against a dead reader instead, which is what lets a
        # write under the abort deadline produce a structured failure
        # rather than a hang (adversarial review 2026-07-24, finding C2).
        # POSIX returns below before touching any writer at all: the
        # wake-up pipe, already signaled, has ended any blocked write, so
        # the ordering has nothing left to protect there. Both are the same
        # invariant: release every mechanism that can unblock an operation
        # before performing one that can block on it.
        if sys.platform == "win32":  # coverage: exclude-posix - containment
            if job is None:
                # Defensive: unreachable on the only construction path.
                raise OSError("no containment job to terminate")
            _terminate_job(job, _FORCED_TERMINATION_EXIT_CODE)
        else:
            with suppress(ProcessLookupError):
                os.killpg(process.pid, FORCED_TERMINATION_SIGNAL)  # type: ignore[attr-defined,unused-ignore]
        if sys.platform != "win32":  # coverage: exclude-windows - POSIX-only leg
            # Nothing to release here: POSIX detached both wrappers at
            # construction, so there is no buffered writer to flush and
            # the raw descriptor belongs to `_close_pipes`. The wake-up
            # pipe, signaled before this call, has already ended any write
            # that was blocked on a child no longer draining its stdin.
            return
        if process.stdin is not None:  # coverage: exclude-posix - Windows-only leg
            with _suppress_os_errors():
                raw = cast("io.BufferedWriter", process.stdin).detach()
                # Close the raw stream rather than dropping it: an
                # abandoned raw file releases its descriptor only through
                # its finalizer, and does so with a ResourceWarning.
                raw.close()

    def _wait_out(
        self, process: subprocess.Popen[bytes], process_handle: int | None
    ) -> None:
        """Wait for the real exit; on Windows prefer the handle wait."""
        if (
            sys.platform == "win32" and process_handle is not None
        ):  # coverage: exclude-posix - Windows-only leg
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

        Recorded decision (review 2026-07-24, section 4; issue #200): the
        grace stays unconditional here. The adapter consults this only
        after a child-sent terminal message — its own failure paths build
        their results without an exit record — and after any terminal
        message a conforming child's exit is imminent, so the wait
        returns in milliseconds and captures the record
        deterministically. A graceless probe would make the closing
        exited-process observation's presence depend on OS reap timing —
        transcript nondeterminism — to save bounded latency that only a
        subject breaching the exit-after-terminal-message obligation
        ever incurs, and only on an already-failed run.
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
        if sys.platform == "win32":  # coverage: exclude-posix - Windows-only leg
            _release_pipes(process)
            return
        # POSIX owns the raw descriptors outright, so releasing them is
        # two closes with nothing to flush and no lock to wait on. The
        # wake-up pipe goes last: a read or write woken by it may still be
        # unwinding, and `close` has already waited for that delivery.
        for stream in (self._raw_stdin, self._raw_stdout):
            if stream is None:
                continue
            with _suppress_os_errors():
                stream.close()
        self._raw_stdin = None
        self._raw_stdout = None
        for fd in (self._wake_read, self._wake_write):
            if fd >= 0:
                with _suppress_os_errors():
                    os.close(fd)
        self._wake_read = -1
        self._wake_write = -1


def _wait_until_ready(  # coverage: exclude-windows - POSIX-only helper
    fd: int, wake: int, *, write: bool
) -> bool:
    """Block until ``fd`` is ready or ``wake`` fires; True if ``wake`` did.

    ``poll`` rather than ``select``: ``select`` cannot express a
    descriptor at or above ``FD_SETSIZE`` and raises on one, so a host
    with many open descriptors would start failing reads that the old
    buffered path served. ``poll`` has no such ceiling and is available on
    every POSIX target this binding supports.
    """
    if sys.platform == "win32":  # coverage: exclude-posix - POSIX-only helper
        raise AssertionError("the pollable path is POSIX-only")
    poller = select.poll()
    poller.register(wake, select.POLLIN)
    poller.register(fd, select.POLLOUT if write else select.POLLIN)
    # No timeout: the wake-up pipe is what ends an otherwise endless wait,
    # and every close signals it before touching either descriptor.
    return any(ready == wake for ready, _events in poller.poll())


def _release_pipes(process: subprocess.Popen[bytes]) -> None:
    """Release both of the child's pipe descriptors, deterministically.

    ``detach`` hands back the raw stream and leaves the buffered wrapper
    unusable, so the object that still owns the descriptor is the *raw*
    one: closing the detached wrapper only raises, and the descriptor
    would then survive until its finalizer ran — the garbage collector a
    teardown must not depend on. Closing the raw stream is what actually
    releases it.

    Detaching a ``BufferedWriter`` flushes it first; the buffered layer
    offers no release-without-flush operation. A child that never drains
    its stdin can therefore still stall this call, which is why the forced
    path terminates the tree before reaching it — and why issue #217
    tracks removing that stall rather than describing it away.
    """
    for pipe in (process.stdin, process.stdout):
        if pipe is None:
            continue
        raw: io.RawIOBase | None = None
        with _suppress_os_errors():
            raw = cast("io.BufferedIOBase", pipe).detach()
        with _suppress_os_errors():
            (pipe if raw is None else raw).close()


class _suppress_os_errors:
    """Context manager: pipe teardown ignores already-gone descriptors."""

    def __enter__(self) -> None:
        return None

    def __exit__(self, exc_type: object, exc: object, tb: object) -> bool:
        return isinstance(exc_type, type) and issubclass(
            exc_type, (OSError, ValueError)
        )
