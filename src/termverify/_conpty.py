"""Minimal Windows ConPTY binding boundary for the terminal adapter plan.

This module is the only place that touches ``pywinpty``. It owns the native
``winpty._winpty.PTY`` object directly instead of ``winpty.PtyProcess``: the
``PtyProcess`` wrapper routes output through an internal socket-relay reader
thread that swallows the native end-of-stream signal and can drop buffered
output once the child exits, and the accepted verification plan rejects
reader-thread state as evidence. Driving the native object keeps every
observable — output bytes, end-of-stream, liveness, exit status — a direct
native signal.

Process-tree containment uses a Windows job object created per spawn with
``JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`` and neither breakaway limit, so every
descendant the child starts inherits membership and cannot leave. Forced
close terminates the whole tree atomically with ``TerminateJobObject``;
releasing the binding closes the job handle, which makes the OS sweep any
survivors even if this process dies abruptly. Disclosed boundary: the child
is assigned to the job immediately after ``CreateProcess`` returns, so a
process the child manages to start within that microseconds-wide window
would fall outside the job; the binding does not claim pre-start assignment.

The binding stays deliberately thin: every future adapter behavior above it
must be testable cross-platform against an injected fake binding, so this
native boundary is excluded from the coverage ratchet with recorded rationale
in the developer guide. Cancellation and recovery are evidenced at this
binding level only — startup failure fails closed, forced close recovers
from hostile children (flood, busy spin, write storm) without leaking
handles or threads, and conin writes are consumed without backpressure so a
blocked write is not a reachable state. Classification into the structured
failure/abort taxonomy is adapter behavior and remains unclaimed here.

``write`` intentionally returns ``None``: the ConPTY write return value is not
a reliable byte-count receipt, and exposing it would fabricate evidence.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import subprocess
import sys
import threading
import time
from collections.abc import Sequence
from typing import Any, Final

_CHILD_EXIT_WAIT_MS = 30_000
_READ_CANCEL_TIMEOUT_SECONDS = 30.0
_READ_CANCEL_RETRY_SECONDS = 0.01

#: Exit code set on every process in the tree by a forced close. The value
#: keeps parity with the previous single-process termination convention.
FORCED_TERMINATION_EXIT_CODE: Final = 15


class ConptyUnsupportedError(RuntimeError):
    """Raised when the ConPTY binding is used on a host without ConPTY."""


class ConptyClosedError(RuntimeError):
    """Raised when an operation is attempted after the binding was closed."""


class ConptyEndOfStreamError(Exception):
    """Raised by ``read`` when the native output pipe reports end-of-stream.

    Only raised while the binding is open: a read interrupted by ``close``
    raises :class:`ConptyClosedError` instead, because close may abandon
    buffered output. On this genuine end-of-stream path Windows pipe
    semantics deliver all buffered output before the read side observes the
    broken pipe, so every byte the pseudoconsole emitted has been returned by
    earlier ``read`` calls when this is raised.
    """


if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

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
    _kernel32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    _kernel32.TerminateProcess.restype = wintypes.BOOL

    def _create_containment_job() -> int:
        """Create a kill-on-close job object for one pseudoconsole child."""
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
        if not _kernel32.AssignProcessToJobObject(job, process_handle):
            raise OSError(f"AssignProcessToJobObject failed: {ctypes.get_last_error()}")

    def _terminate_job(job: int, exit_code: int) -> None:
        if not _kernel32.TerminateJobObject(job, exit_code):
            raise OSError(f"TerminateJobObject failed: {ctypes.get_last_error()}")

    def _terminate_process(process_handle: int, exit_code: int) -> None:
        _kernel32.TerminateProcess(process_handle, exit_code)

    def _wait_for_handle(handle: int, timeout_ms: int) -> bool:
        """OS wait on a real handle; True once it is signaled, never a sleep.

        A wait failure is a real error, not a timeout, and is raised as such
        so it cannot masquerade as "the process did not terminate".
        """
        result = int(_kernel32.WaitForSingleObject(handle, timeout_ms))
        if result == _WAIT_OBJECT_0:
            return True
        if result == _WAIT_TIMEOUT:
            return False
        raise OSError(
            f"WaitForSingleObject failed ({result:#x}): {ctypes.get_last_error()}"
        )

    def _close_handle(handle: int) -> None:
        _kernel32.CloseHandle(handle)

else:

    def _unsupported() -> ConptyUnsupportedError:
        return ConptyUnsupportedError(
            "the ConPTY binding requires Windows; this host has no ConPTY"
        )

    def _create_containment_job() -> int:
        raise _unsupported()

    def _open_containment_handle(pid: int) -> int:
        raise _unsupported()

    def _assign_to_job(job: int, process_handle: int) -> None:
        raise _unsupported()

    def _terminate_job(job: int, exit_code: int) -> None:
        raise _unsupported()

    def _terminate_process(process_handle: int, exit_code: int) -> None:
        raise _unsupported()

    def _wait_for_handle(handle: int, timeout_ms: int) -> bool:
        raise _unsupported()

    def _close_handle(handle: int) -> None:
        raise _unsupported()


class ConptyChild:
    """Thin ownership wrapper around one native ConPTY pseudoconsole child."""

    def __init__(self, pty: Any, pid: int, job: int, process_handle: int) -> None:
        self._pty: Any | None = pty
        self._pid = pid
        self._job: int | None = job
        self._process_handle: int | None = process_handle
        self._exit_status: int | None = None
        self._lock = threading.Lock()
        self._pending_io = 0

    @classmethod
    def spawn(cls, argv: Sequence[str], *, rows: int, columns: int) -> ConptyChild:
        """Spawn a contained child on a ConPTY pseudoconsole.

        The child is assigned to a fresh kill-on-close job object before the
        binding is returned. If containment cannot be established, the child
        is terminated and the spawn fails closed: no uncontained session is
        ever handed out.
        """
        if os.name != "nt":
            raise ConptyUnsupportedError(
                "the ConPTY binding requires Windows; this host has no ConPTY"
            )
        from winpty import Backend
        from winpty._winpty import PTY

        arguments = list(argv)
        command = shutil.which(arguments[0])
        if command is None:
            raise FileNotFoundError(
                f"the command was not found or was not executable: {arguments[0]}"
            )
        pty = PTY(columns, rows, backend=Backend.ConPTY)
        environment = (
            "\0".join(f"{name}={value}" for name, value in os.environ.items()) + "\0"
        )
        cmdline = (
            " " + subprocess.list2cmdline(arguments[1:]) if len(arguments) > 1 else None
        )
        if not pty.spawn(command, cmdline=cmdline, cwd=os.getcwd(), env=environment):
            raise OSError(f"ConPTY spawn reported failure for {command}")
        pid = int(pty.pid)
        job: int | None = None
        process_handle: int | None = None
        try:
            job = _create_containment_job()
            process_handle = _open_containment_handle(pid)
            _assign_to_job(job, process_handle)
        except OSError as error:
            if process_handle is not None:
                _terminate_process(process_handle, FORCED_TERMINATION_EXIT_CODE)
                _close_handle(process_handle)
            if job is not None:
                _close_handle(job)
            # Drop the native reference before raising so the exception
            # traceback cannot pin the pseudoconsole handles.
            del pty
            raise OSError(
                f"failed to contain ConPTY child {pid} in a job object"
            ) from error
        return cls(pty, pid, job, process_handle)

    @property
    def pid(self) -> int:
        """Return the child's OS process id."""
        return self._pid

    def read(self) -> str:
        """Block until pseudoconsole output is available and return it.

        Raises :class:`ConptyEndOfStreamError` when the binding is still open
        and the native output pipe reports end-of-stream after the child has
        exited; the native exit status has been captured by then. Raises
        :class:`ConptyClosedError` when the binding is closed before or while
        the read is in flight. Any other native read failure — the binding
        open, the child alive — is re-raised unchanged.
        """
        pty = self._begin_io()
        try:
            return str(pty.read(blocking=True))
        except Exception as error:
            replacement = self._classify_io_failure(pty, end_of_stream=True)
            # Drop the frame-local native reference before raising: the
            # exception's traceback keeps this frame alive, and a pinned
            # native object would defer the handle release indefinitely.
            del pty
            if replacement is None:
                raise
            raise replacement from error
        finally:
            self._end_io()

    def write(self, text: str) -> None:
        """Write ``text`` to the child without claiming a byte-count receipt.

        Raises :class:`ConptyClosedError` when the binding is closed before
        or while the write is in flight; other native write failures are
        re-raised unchanged.
        """
        pty = self._begin_io()
        try:
            pty.write(text)
        except Exception as error:
            replacement = self._classify_io_failure(pty, end_of_stream=False)
            del pty
            if replacement is None:
                raise
            raise replacement from error
        finally:
            self._end_io()

    def resize(self, *, rows: int, columns: int) -> None:
        """Resize the pseudoconsole explicitly."""
        self._require_open().set_size(columns, rows)

    def is_alive(self) -> bool:
        """Report whether the child process is still alive.

        A closed binding reports ``False``: it no longer owns a live native
        session through which liveness could be observed.
        """
        pty = self._pty
        return False if pty is None else bool(pty.isalive())

    def close(self, *, force: bool) -> None:
        """Release native ownership; with ``force``, terminate the child's tree.

        The forced path terminates the entire job — the child and every
        descendant — atomically with ``TerminateJobObject`` (uniform exit
        code :data:`FORCED_TERMINATION_EXIT_CODE`), waits on the child's real
        process handle, and captures the native exit record before releasing
        the handles.

        A release-only close (``force=False``) of a live child records no
        exit status — the binding never observed a native exit record — while
        the pseudoconsole handle release itself makes ConPTY terminate the
        attached client, which callers can observe at the OS level. The close
        waits for that termination on the child's process handle and then
        closes the job handle, whose kill-on-close limit sweeps any remaining
        descendants; the no-kill path therefore cannot leak a process tree
        either.

        Close first unpublishes the native object so no new I/O can start,
        then cancels pending native I/O until every in-flight read and write
        has returned. Interrupted I/O surfaces :class:`ConptyClosedError` with
        its frame-local native reference dropped, so a held exception cannot
        pin the native object and the handles are released as soon as the
        last frame still holding it unwinds.
        """
        with self._lock:
            pty = self._pty
            if pty is None:
                return
            self._pty = None
            job = self._job
            process_handle = self._process_handle
            self._job = None
            self._process_handle = None
        child_exited = True
        try:
            try:
                if force and pty.isalive():
                    if job is None:
                        # Defensive: unreachable on the only construction
                        # path; failing fast beats waiting on a live child.
                        raise OSError("no containment job to terminate")
                    _terminate_job(job, FORCED_TERMINATION_EXIT_CODE)
                    if process_handle is not None and not _wait_for_handle(
                        process_handle, _CHILD_EXIT_WAIT_MS
                    ):
                        raise OSError(
                            f"child process {self._pid} did not terminate on"
                            " forced close"
                        )
                if not pty.isalive():
                    self._capture_exit_status(pty)
            finally:
                try:
                    self._cancel_pending_io(pty)
                finally:
                    # Release the binding's native reference even when the
                    # cancel loop raises: the propagating exception's
                    # traceback must never pin the native object. The
                    # destructor closes the pseudoconsole once the last
                    # in-flight frame unwinds.
                    del pty
            if not force and process_handle is not None:
                child_exited = _wait_for_handle(process_handle, _CHILD_EXIT_WAIT_MS)
        finally:
            if job is not None:
                # Kill-on-close sweeps every remaining job member, so even a
                # failed graceful path cannot leak the tree.
                _close_handle(job)
            if not child_exited and process_handle is not None:
                child_exited = _wait_for_handle(process_handle, _CHILD_EXIT_WAIT_MS)
            if process_handle is not None:
                _close_handle(process_handle)
        if not child_exited:
            raise OSError(
                f"child process {self._pid} did not terminate after handle release"
            )

    def _cancel_pending_io(self, pty: Any) -> None:
        """Cancel native I/O until no read or write frame can block on ``pty``."""
        deadline = time.monotonic() + _READ_CANCEL_TIMEOUT_SECONDS
        while True:
            with self._lock:
                pending = self._pending_io
            if pending == 0:
                return
            with contextlib.suppress(Exception):
                pty.cancel_io()
            if time.monotonic() >= deadline:
                raise OSError("pending native ConPTY I/O did not cancel during close")
            time.sleep(_READ_CANCEL_RETRY_SECONDS)

    @property
    def exit_status(self) -> int | None:
        """Return the natively observed exit status, else ``None``."""
        pty = self._pty
        if self._exit_status is None and pty is not None:
            self._capture_exit_status(pty)
        return self._exit_status

    def _require_open(self) -> Any:
        pty = self._pty
        if pty is None:
            raise ConptyClosedError("the ConPTY binding is closed")
        return pty

    def _begin_io(self) -> Any:
        """Atomically take the native object and count the in-flight call."""
        with self._lock:
            pty = self._pty
            if pty is None:
                raise ConptyClosedError("the ConPTY binding is closed")
            self._pending_io += 1
            return pty

    def _end_io(self) -> None:
        with self._lock:
            self._pending_io -= 1

    def _classify_io_failure(
        self, pty: Any, *, end_of_stream: bool
    ) -> Exception | None:
        """Map a native I/O failure to the binding's honest exception, if any.

        A failure observed after ``close`` unpublished the native object is
        the close's own cancellation (or indistinguishable from it) and
        becomes :class:`ConptyClosedError` — never an end-of-stream claim,
        because close may have abandoned buffered output. A read failure on
        an open binding with a dead child is the native end-of-stream signal.
        Anything else is the caller's to see unchanged (``None``).
        """
        if not pty.isalive():
            self._capture_exit_status(pty)
        if self._pty is None:
            return ConptyClosedError("the ConPTY binding was closed during native I/O")
        if end_of_stream and not pty.isalive():
            return ConptyEndOfStreamError(
                "the native ConPTY output pipe reported end-of-stream"
            )
        return None

    def _capture_exit_status(self, pty: Any) -> None:
        status = pty.get_exitstatus()
        if status is not None:
            self._exit_status = int(status)
