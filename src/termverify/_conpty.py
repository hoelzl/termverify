"""Minimal Windows ConPTY binding boundary for the terminal adapter plan.

This module is the only place that touches ``pywinpty``. It owns the native
``winpty._winpty.PTY`` object directly instead of ``winpty.PtyProcess``: the
``PtyProcess`` wrapper routes output through an internal socket-relay reader
thread that swallows the native end-of-stream signal and can drop buffered
output once the child exits, and the accepted verification plan rejects
reader-thread state as evidence. Driving the native object keeps every
observable — output bytes, end-of-stream, liveness, exit status — a direct
native signal.

The binding stays deliberately thin: every future adapter behavior above it
must be testable cross-platform against an injected fake binding, so this
native boundary is excluded from the coverage ratchet with recorded rationale
in the developer guide. Nothing here claims process-tree teardown or
cancellation recovery; those claims require the later verified slices of the
accepted terminal-adapter decision.

``write`` intentionally returns ``None``: the ConPTY write return value is not
a reliable byte-count receipt, and exposing it would fabricate evidence.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Sequence
from typing import Any

_CHILD_EXIT_WAIT_MS = 30_000
_READ_CANCEL_TIMEOUT_SECONDS = 30.0
_READ_CANCEL_RETRY_SECONDS = 0.01


class ConptyUnsupportedError(RuntimeError):
    """Raised when the ConPTY binding is used on a host without ConPTY."""


class ConptyClosedError(RuntimeError):
    """Raised when an operation is attempted after the binding was closed."""


class ConptyEndOfStreamError(Exception):
    """Raised by ``read`` when the native output pipe reports end-of-stream.

    Windows pipe semantics deliver all buffered output before the read side
    observes the broken pipe, so every byte the pseudoconsole emitted has been
    returned by earlier ``read`` calls when this is raised.
    """


if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    _SYNCHRONIZE = 0x0010_0000
    _WAIT_OBJECT_0 = 0

    def _wait_for_child_exit(pid: int, timeout_ms: int) -> bool:
        """Wait on the child's real process handle until it terminates.

        This is an OS wait on the process object, not a sleep: the return
        value reflects the handle becoming signaled, and a missing handle
        means the process was already gone.
        """
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = [
            wintypes.DWORD,
            wintypes.BOOL,
            wintypes.DWORD,
        ]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel32.WaitForSingleObject.restype = wintypes.DWORD
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        handle = kernel32.OpenProcess(_SYNCHRONIZE, False, pid)
        if not handle:
            return True
        try:
            return bool(
                kernel32.WaitForSingleObject(handle, timeout_ms) == _WAIT_OBJECT_0
            )
        finally:
            kernel32.CloseHandle(handle)

else:

    def _wait_for_child_exit(pid: int, timeout_ms: int) -> bool:
        raise ConptyUnsupportedError(
            "the ConPTY binding requires Windows; this host has no ConPTY"
        )


class ConptyChild:
    """Thin ownership wrapper around one native ConPTY pseudoconsole child."""

    def __init__(self, pty: Any, pid: int) -> None:
        self._pty: Any | None = pty
        self._pid = pid
        self._exit_status: int | None = None
        self._lock = threading.Lock()
        self._pending_reads = 0

    @classmethod
    def spawn(cls, argv: Sequence[str], *, rows: int, columns: int) -> ConptyChild:
        """Spawn a child on a ConPTY pseudoconsole with explicit dimensions."""
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
        return cls(pty, int(pty.pid))

    @property
    def pid(self) -> int:
        """Return the child's OS process id."""
        return self._pid

    def read(self) -> str:
        """Block until pseudoconsole output is available and return it.

        Raises :class:`ConptyEndOfStreamError` when the native output pipe
        reports end-of-stream after the child has exited; the native exit
        status has been captured by then. A native read failure while the
        child is still alive is re-raised unchanged.
        """
        with self._lock:
            pty = self._pty
            if pty is None:
                raise ConptyClosedError("the ConPTY binding is closed")
            self._pending_reads += 1
        try:
            return str(pty.read(blocking=True))
        except Exception as error:
            if not pty.isalive():
                self._capture_exit_status(pty)
                raise ConptyEndOfStreamError(
                    "the native ConPTY output pipe reported end-of-stream"
                ) from error
            raise
        finally:
            with self._lock:
                self._pending_reads -= 1

    def write(self, text: str) -> None:
        """Write ``text`` to the child without claiming a byte-count receipt."""
        self._require_open().write(text)

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
        """Release native ownership; with ``force``, terminate a live child.

        The forced path terminates the child, waits on its real process
        handle, and captures the native exit record before releasing the
        handles. A release-only close (``force=False``) of a live child
        records no exit status — the binding never observed a native exit
        record — while the handle release itself makes ConPTY terminate the
        attached client, which callers can observe at the OS level.

        Close first unpublishes the native object so no new read can start,
        then cancels pending native I/O until every in-flight read has
        returned. The native handles are therefore released as soon as the
        last frame still holding the object unwinds, never left behind a
        read that blocked after a single cancellation was already spent.
        """
        with self._lock:
            pty = self._pty
            if pty is None:
                return
            self._pty = None
        try:
            if force and pty.isalive():
                os.kill(self._pid, signal.SIGTERM)
                if not _wait_for_child_exit(self._pid, _CHILD_EXIT_WAIT_MS):
                    raise OSError(
                        f"child process {self._pid} did not terminate on forced close"
                    )
            if not pty.isalive():
                self._capture_exit_status(pty)
        finally:
            self._cancel_pending_reads(pty)

    def _cancel_pending_reads(self, pty: Any) -> None:
        """Cancel native I/O until no read frame can still block on ``pty``."""
        deadline = time.monotonic() + _READ_CANCEL_TIMEOUT_SECONDS
        while True:
            with self._lock:
                pending = self._pending_reads
            if pending == 0:
                return
            with contextlib.suppress(Exception):
                pty.cancel_io()
            if time.monotonic() >= deadline:
                raise OSError("pending native ConPTY reads did not cancel during close")
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

    def _capture_exit_status(self, pty: Any) -> None:
        status = pty.get_exitstatus()
        if status is not None:
            self._exit_status = int(status)
