"""Durable native ownership, close, and EOF-drain evidence for the ConPTY binding.

These tests promote verification-plan items 2 and 3 of the accepted
terminal-adapter decision into repeatable Windows-matrix CI evidence:

- **Native ownership and close (item 2):** closing the binding releases the
  native pseudoconsole deterministically, verified by OS-level process-handle
  waits and child-observable exit codes, never by reader-thread state. A
  release-only close proves the handles were actually released because ConPTY
  itself terminates the attached client with ``STATUS_CONTROL_C_EXIT``.
- **EOF and final-frame drain (item 3):** output is serviced until the native
  output pipe reports end-of-stream after the child exits, and the final
  marker-bounded burst delivered before that signal is byte-complete. The
  binding drives the native ``PTY`` object directly, so there is no relay
  reader thread whose death could masquerade as EOF.

The slice-1 lifecycle behaviors (creation, dimensions, echo, burst, resize,
forced close, integer exit status) remain covered against the native read
semantics. Process-tree teardown, cancellation/recovery taxonomy, dimensions
receipts, and enforcement receipts remain later unproven slices.
"""

from __future__ import annotations

import os
import queue
import re
import signal
import sys
import threading
import time
from typing import Final

import pytest

from termverify._conpty import (
    ConptyChild,
    ConptyClosedError,
    ConptyEndOfStreamError,
    ConptyUnsupportedError,
)

_INITIAL_ROWS: Final = 24
_INITIAL_COLUMNS: Final = 80
_RESIZED_ROWS: Final = 30
_RESIZED_COLUMNS: Final = 100
_BURST_CHUNK_BYTES: Final = 1024
_BURST_CHUNKS: Final = 1024
_BURST_BYTES: Final = _BURST_CHUNK_BYTES * _BURST_CHUNKS
_TIMEOUT_SECONDS: Final = 60.0
_OS_WAIT_TIMEOUT_MS: Final = 30_000

# Documented Windows termination status delivered to a console client when its
# pseudoconsole is closed underneath it: proof the native handles were
# released, observable entirely outside this binding.
_STATUS_CONTROL_C_EXIT: Final = 0xC000013A

_EXITING_BURST_CHILD: Final = f"""\
import sys

print("TV_START", flush=True)
for _ in range({_BURST_CHUNKS}):
    sys.stdout.write("Z" * {_BURST_CHUNK_BYTES})
    sys.stdout.flush()
print("TV_END", flush=True)
"""

_BLOCKING_CHILD: Final = """\
import sys

print("TV_READY", flush=True)
sys.stdin.readline()
print("TV_UNREACHED", flush=True)
"""

_LIFECYCLE_CHILD: Final = f"""\
import os
import sys

def size():
    value = os.get_terminal_size(sys.stdout.fileno())
    return f"{{value.columns}}x{{value.lines}}"

print(f"TV_INITIAL:{{size()}}", flush=True)
first = sys.stdin.readline().strip()
print(f"TV_INPUT:{{first}}", flush=True)
print("TV_BURST_START", flush=True)
for _ in range({_BURST_CHUNKS}):
    sys.stdout.write("Z" * {_BURST_CHUNK_BYTES})
    sys.stdout.flush()
print("TV_BURST_DONE:{_BURST_BYTES}", flush=True)
second = sys.stdin.readline().strip()
print(f"TV_RESIZED:{{size()}}", flush=True)
print(f"TV_TRIGGER:{{second}}", flush=True)
print("TV_WAITING", flush=True)
sys.stdin.readline()
"""


if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    _SYNCHRONIZE: Final = 0x0010_0000
    _PROCESS_QUERY_LIMITED_INFORMATION: Final = 0x1000
    _WAIT_OBJECT_0: Final = 0

    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _kernel32.OpenProcess.argtypes = [
        wintypes.DWORD,
        wintypes.BOOL,
        wintypes.DWORD,
    ]
    _kernel32.OpenProcess.restype = wintypes.HANDLE
    _kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    _kernel32.WaitForSingleObject.restype = wintypes.DWORD
    _kernel32.GetExitCodeProcess.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.DWORD),
    ]
    _kernel32.GetExitCodeProcess.restype = wintypes.BOOL
    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    _kernel32.CloseHandle.restype = wintypes.BOOL

    def _open_process_handle(pid: int) -> int:
        """Open a real OS handle to the child before any close/kill races."""
        handle = _kernel32.OpenProcess(
            _SYNCHRONIZE | _PROCESS_QUERY_LIMITED_INFORMATION, False, pid
        )
        assert handle, f"OpenProcess({pid}) failed: {ctypes.get_last_error()}"
        return int(handle)

    def _wait_for_os_exit_code(handle: int, timeout_ms: int) -> int | None:
        """Wait on the process handle; return the OS exit code once signaled."""
        result = _kernel32.WaitForSingleObject(handle, timeout_ms)
        if result != _WAIT_OBJECT_0:
            return None
        code = wintypes.DWORD()
        assert _kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
        return int(code.value)

    def _close_process_handle(handle: int) -> None:
        _kernel32.CloseHandle(handle)

else:  # pragma: no cover - Windows-only evidence helpers

    def _open_process_handle(pid: int) -> int:
        raise ConptyUnsupportedError("OS process-handle evidence requires Windows")

    def _wait_for_os_exit_code(handle: int, timeout_ms: int) -> int | None:
        raise ConptyUnsupportedError("OS process-handle evidence requires Windows")

    def _close_process_handle(handle: int) -> None:
        raise ConptyUnsupportedError("OS process-handle evidence requires Windows")


class _Drain:
    """Collect native reads on a helper thread so tests can bound blocking calls.

    The thread exists only to keep a hung native read from hanging the test
    run; the asserted evidence is the collected output and the terminal
    exception raised by the binding, never this thread's state.
    """

    def __init__(self, child: ConptyChild) -> None:
        self._child = child
        self._condition = threading.Condition()
        self._chunks: list[str] = []
        self._terminal: BaseException | None = None
        self._done = False
        self._thread = threading.Thread(target=self._run, name="tv-drain", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        try:
            while True:
                chunk = self._child.read()
                with self._condition:
                    self._chunks.append(chunk)
                    self._condition.notify_all()
        except BaseException as error:
            with self._condition:
                self._terminal = error
                self._done = True
                self._condition.notify_all()

    def text(self) -> str:
        with self._condition:
            return "".join(self._chunks)

    def wait_for_marker(self, marker: str) -> None:
        with self._condition:
            arrived = self._condition.wait_for(
                lambda: marker in "".join(self._chunks) or self._done,
                timeout=_TIMEOUT_SECONDS,
            )
            assert arrived, f"timed out waiting for {marker!r}"
            assert marker in "".join(self._chunks), (
                f"stream ended before {marker!r}: {self._terminal!r}"
            )

    def wait_for_end(self) -> BaseException:
        with self._condition:
            ended = self._condition.wait_for(lambda: self._done, _TIMEOUT_SECONDS)
            assert ended, "timed out waiting for the native end-of-stream signal"
            assert self._terminal is not None
            return self._terminal

    def join(self) -> None:
        self._thread.join(_TIMEOUT_SECONDS)
        assert not self._thread.is_alive()


def _spawn(script: str) -> ConptyChild:
    return ConptyChild.spawn(
        [sys.executable, "-I", "-u", "-c", script],
        rows=_INITIAL_ROWS,
        columns=_INITIAL_COLUMNS,
    )


def test_spawn_fails_closed_off_windows() -> None:
    if os.name == "nt":
        pytest.skip("fail-closed spawn behavior is observable only off Windows")
    with pytest.raises(ConptyUnsupportedError):
        ConptyChild.spawn(
            [sys.executable, "-c", "pass"],
            rows=_INITIAL_ROWS,
            columns=_INITIAL_COLUMNS,
        )


@pytest.mark.skipif(os.name != "nt", reason="Windows ConPTY binding evidence")
def test_final_frame_drains_byte_complete_to_native_end_of_stream() -> None:
    """Item 3: service output past child exit until the native pipe ends."""
    child = _spawn(_EXITING_BURST_CHILD)
    drain = _Drain(child)
    try:
        terminal = drain.wait_for_end()
    finally:
        drain.join()
        child.close(force=True)

    # The end-of-stream signal is the binding's native classification, raised
    # from the failing native read after the child exited — not a stopped
    # reader thread and not a close initiated by this test.
    assert isinstance(terminal, ConptyEndOfStreamError)

    combined = drain.text()
    start = combined.find("TV_START")
    end = combined.find("TV_END")
    assert 0 <= start < end, combined[-200:]
    assert combined[start:end].count("Z") == _BURST_BYTES
    assert not child.is_alive()
    assert child.exit_status == 0


@pytest.mark.skipif(os.name != "nt", reason="Windows ConPTY binding evidence")
def test_forced_close_terminates_child_observed_at_os_level() -> None:
    """Item 2: forced close ends the child, proven by an OS handle wait."""
    child = _spawn(_BLOCKING_CHILD)
    drain = _Drain(child)
    handle = _open_process_handle(child.pid)
    try:
        drain.wait_for_marker("TV_READY")
        assert child.is_alive()

        child.close(force=True)

        os_exit_code = _wait_for_os_exit_code(handle, _OS_WAIT_TIMEOUT_MS)
    finally:
        child.close(force=True)
        _close_process_handle(handle)
        drain.join()

    assert os_exit_code == int(signal.SIGTERM)
    assert child.exit_status == int(signal.SIGTERM)
    assert not child.is_alive()
    assert "TV_UNREACHED" not in drain.text()
    # Close unpublishes the native object before terminating the child, so a
    # read interrupted by the close surfaces the closed classification.
    assert isinstance(drain.wait_for_end(), ConptyClosedError)
    with pytest.raises(ConptyClosedError):
        child.read()
    with pytest.raises(ConptyClosedError):
        child.write("late\r\n")
    with pytest.raises(ConptyClosedError):
        child.resize(rows=_RESIZED_ROWS, columns=_RESIZED_COLUMNS)


@pytest.mark.skipif(os.name != "nt", reason="Windows ConPTY binding evidence")
def test_release_only_close_releases_native_handles_child_observably() -> None:
    """Item 2: releasing the handles alone terminates the attached client.

    No kill is issued: the only cause of the child's death is the native
    handle release (``ClosePseudoConsole``), which Windows reports to the
    client as ``STATUS_CONTROL_C_EXIT``. The binding truthfully records no
    exit status because it never observed a native exit record.
    """
    child = _spawn(_BLOCKING_CHILD)
    drain = _Drain(child)
    handle = _open_process_handle(child.pid)
    try:
        drain.wait_for_marker("TV_READY")
        assert child.is_alive()

        child.close(force=False)

        os_exit_code = _wait_for_os_exit_code(handle, _OS_WAIT_TIMEOUT_MS)
    finally:
        child.close(force=True)
        _close_process_handle(handle)
        drain.join()

    assert os_exit_code == _STATUS_CONTROL_C_EXIT
    assert child.exit_status is None
    assert not child.is_alive()


@pytest.mark.skipif(os.name != "nt", reason="Windows ConPTY binding evidence")
def test_release_only_close_releases_handles_despite_held_read_exception() -> None:
    """Item 2 regression: a read racing the close cannot pin the native handles.

    The reader is deliberately parked on an *empty* pipe before the close, so
    the close's cancellation surfaces inside a blocking native read. The
    terminal exception is captured and held alive across the OS wait: if the
    exception's traceback still referenced the native object, the destructor
    (and ``ClosePseudoConsole``) could not run and the child would survive.
    Observing ``STATUS_CONTROL_C_EXIT`` while the exception is held proves the
    handles were released regardless.
    """
    child = _spawn(_BLOCKING_CHILD)
    drain = _Drain(child)
    handle = _open_process_handle(child.pid)
    try:
        drain.wait_for_marker("TV_READY")
        # Arrangement, not evidence: give the reader time to drain residual
        # frames and re-enter a blocking read on the now-quiet pipe, the
        # interleaving that previously leaked a raw native error whose
        # traceback pinned the handles.
        time.sleep(0.5)

        child.close(force=False)

        terminal = drain.wait_for_end()
        os_exit_code = _wait_for_os_exit_code(handle, _OS_WAIT_TIMEOUT_MS)
    finally:
        child.close(force=True)
        _close_process_handle(handle)
        drain.join()

    assert isinstance(terminal, ConptyClosedError)
    assert os_exit_code == _STATUS_CONTROL_C_EXIT
    assert child.exit_status is None
    assert not child.is_alive()


@pytest.mark.skipif(os.name != "nt", reason="Windows ConPTY binding evidence")
def test_conpty_child_lifecycle_matches_spike_evidence() -> None:
    """Slice-1 lifecycle evidence retained against the native read semantics."""
    child = _spawn(_LIFECYCLE_CHILD)
    drain = _Drain(child)
    input_queue: queue.Queue[str | None] = queue.Queue()
    write_errors: list[str] = []

    def drain_input() -> None:
        try:
            while True:
                item = input_queue.get()
                if item is None:
                    return
                child.write(item)
        except (ConptyClosedError, OSError) as error:
            write_errors.append(f"input service: {type(error).__name__}")

    writer = threading.Thread(target=drain_input, name="tv-input", daemon=True)
    writer.start()
    try:
        drain.wait_for_marker("TV_INITIAL:")
        input_queue.put("synthetic-input\r\n")
        drain.wait_for_marker("TV_INPUT:synthetic-input")
        drain.wait_for_marker(f"TV_BURST_DONE:{_BURST_BYTES}")

        child.resize(rows=_RESIZED_ROWS, columns=_RESIZED_COLUMNS)
        input_queue.put("measure-after-resize\r\n")
        drain.wait_for_marker("TV_WAITING")

        assert child.is_alive()
        assert not write_errors, write_errors
    finally:
        child.close(force=True)
        input_queue.put(None)
        writer.join(_TIMEOUT_SECONDS)
        drain.join()

    assert not writer.is_alive()
    assert isinstance(drain.wait_for_end(), ConptyClosedError)
    assert not child.is_alive()
    assert type(child.exit_status) is int

    combined = drain.text()
    initial = re.search(r"TV_INITIAL:(\d+x\d+)", combined)
    resized = re.search(r"TV_RESIZED:(\d+x\d+)", combined)
    assert initial is not None
    assert initial.group(1) == f"{_INITIAL_COLUMNS}x{_INITIAL_ROWS}"
    assert resized is not None
    assert resized.group(1) == f"{_RESIZED_COLUMNS}x{_RESIZED_ROWS}"
    burst_start = combined.find("TV_BURST_START")
    burst_end = combined.find("TV_BURST_DONE")
    assert 0 <= burst_start < burst_end
    assert combined[burst_start:burst_end].count("Z") == _BURST_BYTES
