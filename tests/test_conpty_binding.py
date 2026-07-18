"""Durable native ownership, close, EOF-drain, and teardown evidence (ConPTY).

These tests promote verification-plan items 2, 3, and 4 of the accepted
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
- **Process-tree teardown (item 4):** a deliberately spawning child and its
  grandchild are both terminated on forced close (atomic job-object
  termination, uniform exit code) and on release-only close (kill-on-close
  job sweep), each proven by OS process-handle waits on both processes.
- **Cancellation and recovery, binding level (item 5):** startup failure
  fails closed before any session exists; forced close recovers from an
  unbounded output flood, a busy unresponsive child, and an active write
  storm without leaking handles or threads; conin writes are consumed
  without backpressure, so a blocked write is not a reachable state.

The slice-1 lifecycle behaviors (creation, dimensions, echo, burst, resize,
forced close, integer exit status) remain covered against the native read
semantics. Classification into the structured failure/abort taxonomy is
adapter behavior and remains for the public ``Adapter`` slice; dimensions
receipts and enforcement receipts remain later unproven slices.
"""

from __future__ import annotations

import os
import queue
import re
import sys
import threading
import time
from typing import Final

import pytest

from termverify._conpty import (
    FORCED_TERMINATION_EXIT_CODE,
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

# Deliberately spawning child: starts a long-lived grandchild, reports its
# pid, then blocks. Tree-teardown evidence must terminate both processes.
# The grandchild inherits the child's console, so pseudoconsole teardown can
# reach it; the detached variant below isolates the job-object sweep.
_SPAWNING_CHILD: Final = """\
import subprocess
import sys

grand = subprocess.Popen(
    [sys.executable, "-I", "-c", "import time; time.sleep(300)"],
)
print(f"TV_GRANDCHILD:{grand.pid}", flush=True)
print("TV_READY", flush=True)
sys.stdin.readline()
print("TV_UNREACHED", flush=True)
"""

# Variant whose grandchild runs with DETACHED_PROCESS: it has no console, so
# closing the pseudoconsole cannot terminate it. Only the kill-on-close job
# sweep can, which is exactly what its test isolates.
_DETACHED_SPAWNING_CHILD: Final = """\
import subprocess
import sys

grand = subprocess.Popen(
    [sys.executable, "-I", "-c", "import time; time.sleep(300)"],
    creationflags=subprocess.DETACHED_PROCESS,
)
print(f"TV_GRANDCHILD:{grand.pid}", flush=True)
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
    _PROCESS_TERMINATE: Final = 0x0001
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
    _kernel32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    _kernel32.TerminateProcess.restype = wintypes.BOOL
    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    _kernel32.CloseHandle.restype = wintypes.BOOL

    def _open_process_handle(pid: int) -> int:
        """Open a real OS handle to the process before any close/kill races."""
        handle = _kernel32.OpenProcess(
            _SYNCHRONIZE | _PROCESS_QUERY_LIMITED_INFORMATION | _PROCESS_TERMINATE,
            False,
            pid,
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

    def _terminate_process(handle: int) -> None:
        """Cleanup-only kill so a failed test cannot leak a process."""
        _kernel32.TerminateProcess(handle, 1)

    def _close_process_handle(handle: int) -> None:
        _kernel32.CloseHandle(handle)

else:  # pragma: no cover - Windows-only evidence helpers

    def _open_process_handle(pid: int) -> int:
        raise ConptyUnsupportedError("OS process-handle evidence requires Windows")

    def _wait_for_os_exit_code(handle: int, timeout_ms: int) -> int | None:
        raise ConptyUnsupportedError("OS process-handle evidence requires Windows")

    def _terminate_process(handle: int) -> None:
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

    def wait_for_at_least(self, chars: int) -> None:
        """Wait until at least ``chars`` characters of output were collected."""
        with self._condition:
            arrived = self._condition.wait_for(
                lambda: sum(map(len, self._chunks)) >= chars or self._done,
                timeout=_TIMEOUT_SECONDS,
            )
            assert arrived, f"timed out waiting for {chars} output characters"
            assert not self._done, f"stream ended early: {self._terminal!r}"

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

    assert os_exit_code == FORCED_TERMINATION_EXIT_CODE
    assert child.exit_status == FORCED_TERMINATION_EXIT_CODE
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


def _grandchild_pid(drain: _Drain) -> int:
    drain.wait_for_marker("TV_READY")
    match = re.search(r"TV_GRANDCHILD:(\d+)", drain.text())
    assert match is not None
    return int(match.group(1))


@pytest.mark.skipif(os.name != "nt", reason="Windows ConPTY binding evidence")
def test_forced_close_terminates_process_tree_at_os_level() -> None:
    """Item 4: forced close terminates the child and its descendants.

    The deliberately spawning child starts a long-lived grandchild before
    blocking. Both processes must be dead after ``close(force=True)``, proven
    by OS process-handle waits with the same deterministic exit code — the
    job-object termination is atomic across the tree, so no descendant can
    survive or be reparented past the teardown.
    """
    child = _spawn(_SPAWNING_CHILD)
    drain = _Drain(child)
    child_handle = _open_process_handle(child.pid)
    grand_handle: int | None = None
    try:
        grand_handle = _open_process_handle(_grandchild_pid(drain))
        assert child.is_alive()

        child.close(force=True)

        child_code = _wait_for_os_exit_code(child_handle, _OS_WAIT_TIMEOUT_MS)
        grand_code = _wait_for_os_exit_code(grand_handle, _OS_WAIT_TIMEOUT_MS)
    finally:
        child.close(force=True)
        if grand_handle is not None:
            _terminate_process(grand_handle)
            _close_process_handle(grand_handle)
        _close_process_handle(child_handle)
        drain.join()

    assert child_code == FORCED_TERMINATION_EXIT_CODE
    assert grand_code == FORCED_TERMINATION_EXIT_CODE
    assert child.exit_status == FORCED_TERMINATION_EXIT_CODE
    assert not child.is_alive()


@pytest.mark.skipif(os.name != "nt", reason="Windows ConPTY binding evidence")
def test_release_only_close_leaves_no_console_attached_descendant() -> None:
    """Item 4: releasing ownership leaves no console-attached process behind.

    The direct child dies of the pseudoconsole handle release
    (``STATUS_CONTROL_C_EXIT``, slice-2 evidence unchanged). The grandchild
    here inherits the child's console, so the same pseudoconsole teardown
    terminates it with the same status — this test deliberately does NOT
    attribute the grandchild's death to the job sweep; the console-detached
    test below isolates that mechanism.
    """
    child = _spawn(_SPAWNING_CHILD)
    drain = _Drain(child)
    child_handle = _open_process_handle(child.pid)
    grand_handle: int | None = None
    try:
        grand_handle = _open_process_handle(_grandchild_pid(drain))
        assert child.is_alive()

        child.close(force=False)

        child_code = _wait_for_os_exit_code(child_handle, _OS_WAIT_TIMEOUT_MS)
        grand_code = _wait_for_os_exit_code(grand_handle, _OS_WAIT_TIMEOUT_MS)
    finally:
        child.close(force=True)
        if grand_handle is not None:
            _terminate_process(grand_handle)
            _close_process_handle(grand_handle)
        _close_process_handle(child_handle)
        drain.join()

    assert child_code == _STATUS_CONTROL_C_EXIT
    assert grand_code == _STATUS_CONTROL_C_EXIT
    assert child.exit_status is None
    assert not child.is_alive()


@pytest.mark.skipif(os.name != "nt", reason="Windows ConPTY binding evidence")
def test_release_only_close_job_sweep_kills_console_detached_descendant() -> None:
    """Item 4: the kill-on-close job sweep, isolated from console teardown.

    The grandchild runs with ``DETACHED_PROCESS``, so it has no console and
    closing the pseudoconsole cannot terminate it — the only mechanism that
    can is the kill-on-close job handle released by ``close(force=False)``.
    Its OS-observed death is therefore attribution for the sweep itself, the
    guarantee that also covers abrupt owner death. The sweep terminates job
    members with exit code 0.
    """
    child = _spawn(_DETACHED_SPAWNING_CHILD)
    drain = _Drain(child)
    child_handle = _open_process_handle(child.pid)
    grand_handle: int | None = None
    try:
        grand_handle = _open_process_handle(_grandchild_pid(drain))
        assert child.is_alive()

        child.close(force=False)

        child_code = _wait_for_os_exit_code(child_handle, _OS_WAIT_TIMEOUT_MS)
        grand_code = _wait_for_os_exit_code(grand_handle, _OS_WAIT_TIMEOUT_MS)
    finally:
        child.close(force=True)
        if grand_handle is not None:
            _terminate_process(grand_handle)
            _close_process_handle(grand_handle)
        _close_process_handle(child_handle)
        drain.join()

    assert child_code == _STATUS_CONTROL_C_EXIT
    assert grand_code == 0
    assert child.exit_status is None
    assert not child.is_alive()


@pytest.mark.skipif(os.name != "nt", reason="Windows ConPTY binding evidence")
def test_spawn_containment_failure_terminates_child_and_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Item 4: a spawn that cannot be contained never hands out a session.

    Containment assignment is fault-injected to fail; the spawn must raise
    and the already-created child must be dead, proven by an OS handle wait
    on a handle opened while the child was still alive.
    """
    import termverify._conpty as conpty_module

    observed: dict[str, int] = {}
    real_open = conpty_module._open_containment_handle

    def observing_open(pid: int) -> int:
        observed["handle"] = _open_process_handle(pid)
        return real_open(pid)

    def failing_assign(job: int, process_handle: int) -> None:
        raise OSError("injected containment failure")

    monkeypatch.setattr(conpty_module, "_open_containment_handle", observing_open)
    monkeypatch.setattr(conpty_module, "_assign_to_job", failing_assign)
    try:
        with pytest.raises(OSError, match="failed to contain ConPTY child"):
            _spawn(_BLOCKING_CHILD)
        assert "handle" in observed
        exit_code = _wait_for_os_exit_code(observed["handle"], _OS_WAIT_TIMEOUT_MS)
    finally:
        if "handle" in observed:
            _terminate_process(observed["handle"])
            _close_process_handle(observed["handle"])

    assert exit_code == FORCED_TERMINATION_EXIT_CODE


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


# --- Slice 4: binding-level cancellation/recovery with hostile fixtures ---

_FLOODING_CHILD: Final = """\
import sys

print("TV_READY", flush=True)
while True:
    sys.stdout.write("F" * 65536)
    sys.stdout.flush()
"""

_BUSY_CHILD: Final = """\
import sys

print("TV_READY", flush=True)
while True:
    pass
"""

_DEAF_CHILD: Final = """\
import sys
import time

print("TV_READY", flush=True)
time.sleep(600)
"""

_WRITE_CHUNK: Final = "W" * 65536
_WRITE_FLOOD_CHUNKS: Final = 256


@pytest.mark.skipif(os.name != "nt", reason="Windows ConPTY binding evidence")
def test_spawn_missing_command_fails_closed_on_windows() -> None:
    """Item 5 (startup failure): a missing command raises before any session."""
    with pytest.raises(FileNotFoundError):
        ConptyChild.spawn(
            ["termverify-missing-command-fixture"],
            rows=_INITIAL_ROWS,
            columns=_INITIAL_COLUMNS,
        )


@pytest.mark.skipif(os.name != "nt", reason="Windows ConPTY binding evidence")
def test_forced_close_recovers_from_output_flood() -> None:
    """Item 5 (output flood): stop mid-flood tears down without cooperation.

    The child floods stdout forever; the close lands while the reader is
    actively servicing the burst. Recovery is proven by the OS-observed
    tree kill, the closed classification of the interrupted read, and the
    drain thread joining.
    """
    child = _spawn(_FLOODING_CHILD)
    drain = _Drain(child)
    handle = _open_process_handle(child.pid)
    try:
        drain.wait_for_marker("TV_READY")
        drain.wait_for_at_least(2_000_000)

        child.close(force=True)

        os_exit_code = _wait_for_os_exit_code(handle, _OS_WAIT_TIMEOUT_MS)
    finally:
        child.close(force=True)
        _close_process_handle(handle)
        drain.join()

    assert os_exit_code == FORCED_TERMINATION_EXIT_CODE
    assert child.exit_status == FORCED_TERMINATION_EXIT_CODE
    assert isinstance(drain.wait_for_end(), ConptyClosedError)
    assert not child.is_alive()


@pytest.mark.skipif(os.name != "nt", reason="Windows ConPTY binding evidence")
def test_forced_close_kills_busy_unresponsive_child() -> None:
    """Item 5 (child hang): teardown needs no cooperation from a spinning child.

    The child burns CPU in a pure loop, never reading input or producing
    further output. ``TerminateJobObject`` ends it regardless, OS-observed.
    """
    child = _spawn(_BUSY_CHILD)
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

    assert os_exit_code == FORCED_TERMINATION_EXIT_CODE
    assert child.exit_status == FORCED_TERMINATION_EXIT_CODE
    assert isinstance(drain.wait_for_end(), ConptyClosedError)
    assert not child.is_alive()


@pytest.mark.skipif(os.name != "nt", reason="Windows ConPTY binding evidence")
def test_write_flood_against_non_reading_child_never_blocks() -> None:
    """Item 5 (write path): conin writes are consumed without backpressure.

    The child never reads stdin. Every bounded write must still return —
    ConPTY's conhost consumes input regardless of the client — so a
    conin-blocked write is not a reachable state and write-side recovery
    reduces to close's pending-I/O discipline. The writes run on a helper
    thread only so a regression cannot hang the test run; the evidence is
    the completion event, not thread state.
    """
    child = _spawn(_DEAF_CHILD)
    drain = _Drain(child)
    completed = threading.Event()
    write_errors: list[BaseException] = []

    def flood() -> None:
        try:
            for _ in range(_WRITE_FLOOD_CHUNKS):
                child.write(_WRITE_CHUNK)
            completed.set()
        except BaseException as error:
            write_errors.append(error)

    writer = threading.Thread(target=flood, name="tv-write-flood", daemon=True)
    try:
        drain.wait_for_marker("TV_READY")
        writer.start()
        finished = completed.wait(_TIMEOUT_SECONDS)
    finally:
        child.close(force=True)
        writer.join(_TIMEOUT_SECONDS)
        drain.join()

    assert finished, f"bounded write flood did not complete: {write_errors!r}"
    assert not write_errors
    assert not writer.is_alive()
    assert child.exit_status == FORCED_TERMINATION_EXIT_CODE


@pytest.mark.skipif(os.name != "nt", reason="Windows ConPTY binding evidence")
def test_forced_close_during_active_write_flood_recovers() -> None:
    """Item 5 (stop during in-flight I/O): close lands inside a write storm.

    A writer thread streams input continuously while close runs. The
    pending-I/O discipline must wait out the in-flight native write before
    releasing the native object — releasing during a native call crashes
    the interpreter — and the writer must observe the closed classification,
    never a raw native error or a hang.
    """
    child = _spawn(_DEAF_CHILD)
    drain = _Drain(child)
    handle = _open_process_handle(child.pid)
    write_outcome: list[BaseException] = []

    def flood() -> None:
        try:
            while True:
                child.write(_WRITE_CHUNK)
        except BaseException as error:
            write_outcome.append(error)

    writer = threading.Thread(target=flood, name="tv-write-storm", daemon=True)
    try:
        drain.wait_for_marker("TV_READY")
        writer.start()
        # Arrangement, not evidence: let the writer reach a steady stream of
        # in-flight native writes before the close lands.
        time.sleep(0.3)

        child.close(force=True)

        os_exit_code = _wait_for_os_exit_code(handle, _OS_WAIT_TIMEOUT_MS)
        writer.join(_TIMEOUT_SECONDS)
    finally:
        child.close(force=True)
        _close_process_handle(handle)
        drain.join()

    assert not writer.is_alive()
    assert write_outcome and isinstance(write_outcome[0], ConptyClosedError)
    assert os_exit_code == FORCED_TERMINATION_EXIT_CODE
    assert child.exit_status == FORCED_TERMINATION_EXIT_CODE
    assert not child.is_alive()
