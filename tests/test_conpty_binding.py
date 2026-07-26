"""Durable native ownership, close, EOF-drain, and teardown evidence (ConPTY).

These tests promote verification-plan items 2, 3, 4, and the binding-level
half of item 5 of the accepted terminal-adapter decision into repeatable
Windows-matrix CI evidence:

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
  fails closed for a missing command and for a command the OS refuses to
  start, without a held failure pinning the native pseudoconsole; forced
  close recovers from an unbounded output flood, a busy unresponsive child,
  and an in-flight native write without leaking threads, with handle
  release observed under flood via the release-only close; overlapped I/O
  fails fast because the native layer is not thread-safe for it; conin
  writes showed no backpressure on this matrix.

The slice-1 lifecycle behaviors (creation, dimensions, echo, burst, resize,
forced close, integer exit status) remain covered against the native read
semantics. Classification into the structured failure/abort taxonomy is
adapter behavior and remains for the public ``Adapter`` slice; dimensions
receipts and enforcement receipts remain later unproven slices.
"""

from __future__ import annotations

import ctypes
import os
import re
import shutil
import sys
import threading
import time
from pathlib import Path
from typing import Any, Final

import pytest

from termverify._conpty import (
    FORCED_TERMINATION_EXIT_CODE,
    ConptyChild,
    ConptyClosedError,
    ConptyConcurrentIOError,
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


#: Cursor repositioning ConPTY emits while a burst wraps: after scrolling with
#: ``\r\n`` it parks on the last column of the bottom row and rewrites that one
#: cell before continuing. The rewrite is a real character in the stream, so a
#: wrapping burst legitimately carries one repeat per reposition.
_REPOSITION = re.compile(r"\x1b\[(\d+);(\d+)H")

#: The other sequences ConPTY emits during a burst: CSI, and the OSC window
#: title it sets once the child is attached. Characters inside these are not
#: characters the child wrote.
_ESCAPE = re.compile(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b\[[0-9;?]*[A-Za-z]")


def _assert_burst_delivered_whole(region: str) -> None:
    """Assert a wrapping burst arrived complete, repeats accounted for exactly.

    "Byte-complete" is not "byte-count-equal": the console host re-emits the
    last cell of a row after each scroll, so the raw stream carries more
    burst characters than the child wrote. Whether it does that at all
    depends on how fast the reader drains — a slow reader lets the host
    coalesce whole frames and emit none — so pinning a bare count pins the
    reader's speed instead of the binding's fidelity. What must hold either
    way is that every character the child wrote arrived and that every extra
    one is a cell the host explicitly repositioned onto.
    """
    repositions = _REPOSITION.findall(region)
    # Every reposition parks on the same cell — the bottom row's last column.
    # If the host ever repositions somewhere else, the one-repeat-per-jump
    # accounting below stops describing what it emits, and this says so
    # instead of silently absorbing the difference into the count.
    assert len(set(repositions)) <= 1, (
        f"the console host repositioned to more than one cell: {set(repositions)}"
    )
    # Assert the pairing rather than inferring it from a total: a bare count
    # is equally satisfied by one lost character plus one fabricated one.
    # Each reposition must be followed by exactly the one cell it exists to
    # rewrite; strip those pairs and the remainder must hold the burst
    # exactly, with no escape left that could contribute a character to it.
    remainder: list[str] = []
    cursor = 0
    for match in _REPOSITION.finditer(region):
        remainder.append(region[cursor : match.start()])
        after = match.end()
        assert region[after : after + 1] == "Z", (
            "a reposition was not followed by the repeated cell it exists to"
            f" rewrite: {region[after : after + 20]!r}"
        )
        cursor = after + 1
    remainder.append(region[cursor:])
    # Remove the remaining escape sequences too — ConPTY sets its window
    # title mid-burst, and a character inside an escape is not a character
    # the child emitted. Anything left holding an ESC is a sequence this
    # accounting does not model, which must fail loudly rather than be
    # counted.
    stripped = _ESCAPE.sub("", "".join(remainder))
    assert "\x1b" not in stripped, (
        "the burst carried an escape sequence this accounting does not know"
        f" about: {stripped[stripped.index(chr(27)) : stripped.index(chr(27)) + 20]!r}"
    )
    assert stripped.count("Z") == _BURST_BYTES, (
        f"the burst carried {stripped.count('Z')} characters once every"
        f" repositioned repeat was removed; expected {_BURST_BYTES}"
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
    _assert_burst_delivered_whole(combined[start:end])
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
    on a handle opened while the child was still alive. With the suspended
    spawn (issue #235) the child is also provably never resumed: a failed
    containment must not leave a running uncontained process behind.
    """
    import termverify._conpty as conpty_module

    observed: dict[str, int] = {}
    resumed: list[int] = []
    real_open = conpty_module._open_containment_handle
    real_resume = conpty_module._resume_main_thread

    def observing_open(pid: int) -> int:
        observed["handle"] = _open_process_handle(pid)
        return real_open(pid)

    def failing_assign(job: int, process_handle: int) -> None:
        raise OSError("injected containment failure")

    def spying_resume(thread_handle: int) -> None:
        resumed.append(thread_handle)
        real_resume(thread_handle)

    monkeypatch.setattr(conpty_module, "_open_containment_handle", observing_open)
    monkeypatch.setattr(conpty_module, "_assign_to_job", failing_assign)
    monkeypatch.setattr(conpty_module, "_resume_main_thread", spying_resume)
    try:
        with pytest.raises(OSError, match="failed to contain ConPTY child"):
            _spawn(_BLOCKING_CHILD)
        assert "handle" in observed
        assert resumed == [], "a child that failed containment was resumed"
        exit_code = _wait_for_os_exit_code(observed["handle"], _OS_WAIT_TIMEOUT_MS)
    finally:
        if "handle" in observed:
            _terminate_process(observed["handle"])
            _close_process_handle(observed["handle"])

    assert exit_code == FORCED_TERMINATION_EXIT_CODE


def _spy_spawned_pids(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Record the pid of every child the binding creates (issue #235)."""
    pids: list[int] = []
    _spy_spawned(monkeypatch, pids=pids)
    return pids


def _spy_spawned(
    monkeypatch: pytest.MonkeyPatch, *, pids: list[int] | None = None
) -> list[Any]:
    """Record (pid, thread handle, creation flags) for every spawned child.

    The returned list — and *pids* when given — are live: the spy appends
    as children are created, so callers observe spawns that happen after
    this helper returns.
    """
    import termverify._conpty as conpty_module

    # The kernel handle and the process structure exist only in the nt
    # branch, so off-Windows mypy cannot resolve them on the module; the
    # callers are Windows-only at runtime (skipif on each test).
    native: Any = conpty_module
    kernel32 = native._kernel32
    real_create_process = kernel32.CreateProcessW
    spawned: list[Any] = []

    def recording_create_process(*args):  # type: ignore[no-untyped-def]
        result = real_create_process(*args)
        if result:
            information = ctypes.cast(
                args[9], ctypes.POINTER(native._ProcessInformation)
            ).contents
            pid = int(information.dwProcessId)
            spawned.append((pid, int(information.hThread), int(args[5])))
            if pids is not None:
                pids.append(pid)
        return result

    monkeypatch.setattr(kernel32, "CreateProcessW", recording_create_process)
    return spawned


def _handle_is_open(handle: int) -> bool:
    """Ask the OS whether a handle value is still valid (issue #235 review).

    Deterministic counterpart to spying on ``CloseHandle``: no dependence
    on handle-value coincidences in the close stream.
    """
    import termverify._conpty as conpty_module

    # The kernel handle exists only in the nt branch, so off-Windows mypy
    # cannot resolve it on the module; callers are Windows-only (skipif).
    native: Any = conpty_module
    flags = ctypes.wintypes.DWORD()
    return bool(native._kernel32.GetHandleInformation(handle, ctypes.byref(flags)))


def _assert_os_terminated(pid: int) -> None:
    """Prove by an OS handle wait that the pid is dead with the forced code."""
    handle = _open_process_handle(pid)
    try:
        exit_code = _wait_for_os_exit_code(handle, _OS_WAIT_TIMEOUT_MS)
    finally:
        _terminate_process(handle)
        _close_process_handle(handle)
    assert exit_code == FORCED_TERMINATION_EXIT_CODE


@pytest.mark.skipif(os.name != "nt", reason="Windows ConPTY binding evidence")
def test_spawn_assigns_the_containment_job_before_the_child_may_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Issue #235: the job-assignment window is closed.

    The child is created with ``CREATE_SUSPENDED``, assigned to its
    kill-on-close job while still suspended, and only then resumed — a
    descendant it starts can never predate its job membership. The evidence
    is the creation flags plus the call order: an assignment running after
    the resume would reopen the microseconds-wide escape window the module
    once disclosed.
    """
    import termverify._conpty as conpty_module

    events: list[str] = []
    real_assign = conpty_module._assign_to_job
    real_resume = conpty_module._resume_main_thread
    # The kernel handle and the creation flag exist only in the nt branch,
    # so off-Windows mypy cannot resolve them on the module; these tests
    # are Windows-only at runtime (skipif above).
    native: Any = conpty_module
    create_suspended: int = native._CREATE_SUSPENDED
    spawned = _spy_spawned(monkeypatch)

    def recording_assign(job: int, process_handle: int) -> None:
        events.append("assign")
        real_assign(job, process_handle)

    def recording_resume(thread_handle: int) -> None:
        events.append("resume")
        real_resume(thread_handle)

    monkeypatch.setattr(conpty_module, "_assign_to_job", recording_assign)
    monkeypatch.setattr(conpty_module, "_resume_main_thread", recording_resume)

    child = _spawn(_BLOCKING_CHILD)
    try:
        assert events == ["assign", "resume"]
        assert spawned, "CreateProcessW was never observed"
        assert all(flags & create_suspended for _, _, flags in spawned), (
            "the child was not created suspended"
        )
        _, thread_handle, _ = spawned[0]
        assert not _handle_is_open(thread_handle), (
            "the thread handle leaked after the successful resume"
        )
    finally:
        child.close(force=True)


@pytest.mark.skipif(os.name != "nt", reason="Windows ConPTY binding evidence")
def test_a_failure_reading_the_child_pid_still_terminates_the_suspended_child(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Issue #235 review round 3: no bookkeeping statement may sit unguarded.

    The child exists — suspended — from the moment ``_open_session``
    returns. Any exception before the containment ``try`` (a signal landing
    on the bookkeeping statements, here simulated at the ``pid`` read) must
    still run the terminate-and-release teardown, not leak a frozen orphan.
    """
    import termverify._conpty as conpty_module

    created_pid = _spy_spawned_pids(monkeypatch)

    def exploding_pid(self):  # type: ignore[no-untyped-def]
        raise KeyboardInterrupt("injected pre-try failure")

    monkeypatch.setattr(
        conpty_module._PseudoConsoleSession, "pid", property(exploding_pid)
    )

    with pytest.raises(KeyboardInterrupt):
        _spawn(_BLOCKING_CHILD)
    assert created_pid, "the injected failure fired before the child existed"
    _assert_os_terminated(created_pid[0])


@pytest.mark.skipif(os.name != "nt", reason="Windows ConPTY binding evidence")
def test_a_resume_failure_terminates_the_child_and_closes_the_thread_handle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Issue #235 review: the thread handle is closed on every path.

    A failed resume must still terminate the suspended child — it is the
    only resume path — and the teardown close must sweep the thread handle
    rather than leak one handle per failed spawn.
    """
    import termverify._conpty as conpty_module

    spawned = _spy_spawned(monkeypatch)

    def failing_resume(thread_handle: int) -> None:
        raise OSError("injected resume failure")

    monkeypatch.setattr(conpty_module, "_resume_main_thread", failing_resume)

    with pytest.raises(OSError, match="failed to contain ConPTY child"):
        _spawn(_BLOCKING_CHILD)
    assert spawned, "the injected failure fired before the child existed"
    pid, thread_handle, _ = spawned[0]
    assert not _handle_is_open(thread_handle), (
        "the thread handle leaked on the teardown"
    )
    _assert_os_terminated(pid)


@pytest.mark.skipif(os.name != "nt", reason="Windows ConPTY binding evidence")
def test_a_spawn_failure_after_creation_leaves_no_suspended_orphan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Issue #235: a suspended child must never outlive a failed spawn.

    With the child created suspended, a failure between ``CreateProcessW``
    and the resume — here fault-injected at ``CreateEventW`` — must
    terminate it: a suspended process cannot die of handle closes, so
    anything less leaks a frozen orphan. The pid is captured at creation
    and the termination proven by an OS handle wait.
    """
    import termverify._conpty as conpty_module

    created_pid = _spy_spawned_pids(monkeypatch)
    native: Any = conpty_module
    monkeypatch.setattr(native._kernel32, "CreateEventW", lambda *args: 0)

    with pytest.raises(OSError):
        _spawn(_BLOCKING_CHILD)
    assert created_pid, "the injected failure fired before the child existed"
    _assert_os_terminated(created_pid[0])


@pytest.mark.skipif(os.name != "nt", reason="Windows ConPTY binding evidence")
@pytest.mark.parametrize("failure_point", ["job-creation", "handle-open"])
def test_a_containment_setup_failure_leaves_no_suspended_orphan(
    monkeypatch: pytest.MonkeyPatch, failure_point: str
) -> None:
    """Issue #235 review: pre-assignment failures must terminate the child.

    Job creation and the containment-handle open run before the assignment;
    a failure there must still terminate the suspended child — it is not in
    a job yet, and a suspended process cannot die of handle closes, so a
    failure path that skips the termination leaks a frozen orphan.
    """
    import termverify._conpty as conpty_module

    created_pid = _spy_spawned_pids(monkeypatch)
    if failure_point == "job-creation":

        def failing_create_job() -> int:
            raise OSError("injected job creation failure")

        monkeypatch.setattr(
            conpty_module, "_create_containment_job", failing_create_job
        )
    else:

        def failing_open(pid: int) -> int:
            raise OSError("injected handle open failure")

        monkeypatch.setattr(conpty_module, "_open_containment_handle", failing_open)

    with pytest.raises(OSError, match="failed to contain ConPTY child"):
        _spawn(_BLOCKING_CHILD)
    assert created_pid, "the injected failure fired before the child existed"
    _assert_os_terminated(created_pid[0])


@pytest.mark.skipif(os.name != "nt", reason="Windows ConPTY binding evidence")
@pytest.mark.parametrize("failure_point", ["job-creation", "resume"])
@pytest.mark.parametrize("error_type", [ValueError, KeyboardInterrupt])
def test_a_non_os_error_in_the_containment_window_still_terminates_the_child(
    monkeypatch: pytest.MonkeyPatch,
    failure_point: str,
    error_type: type[BaseException],
) -> None:
    """Issue #235 review round 2: only OSError was contained.

    A KeyboardInterrupt or any other non-OSError raised between child
    creation and resume bypassed the except entirely: the suspended child
    leaked frozen. The containment teardown must run for any BaseException
    and then re-raise the original exception unchanged.
    """
    import termverify._conpty as conpty_module

    created_pid = _spy_spawned_pids(monkeypatch)
    if failure_point == "job-creation":

        def failing_create_job() -> int:
            raise error_type("injected non-OS failure")

        monkeypatch.setattr(
            conpty_module, "_create_containment_job", failing_create_job
        )
    else:

        def failing_resume(thread_handle: int) -> None:
            raise error_type("injected non-OS failure")

        monkeypatch.setattr(conpty_module, "_resume_main_thread", failing_resume)

    with pytest.raises(error_type):
        _spawn(_BLOCKING_CHILD)
    assert created_pid, "the injected failure fired before the child existed"
    _assert_os_terminated(created_pid[0])


class _ForcedCloseWatchdog:
    """Force-close the binding if a sequential test exceeds its deadline.

    Single-flight I/O means markers are awaited with main-thread blocking
    reads; if a marker never arrives, this watchdog's close cancels the read
    (surfacing ``ConptyClosedError``) so the test fails loudly instead of
    hanging the run. The watchdog is arrangement, not evidence.
    """

    def __init__(self, child: ConptyChild) -> None:
        self._timer = threading.Timer(_TIMEOUT_SECONDS, lambda: child.close(force=True))
        self._timer.daemon = True
        self._timer.start()

    def cancel(self) -> None:
        self._timer.cancel()


def _read_until(child: ConptyChild, marker: str, collected: list[str]) -> None:
    """Service output on the calling thread until ``marker`` was collected."""
    while marker not in "".join(collected):
        collected.append(child.read())


@pytest.mark.skipif(os.name != "nt", reason="Windows ConPTY binding evidence")
def test_conpty_child_lifecycle_matches_spike_evidence() -> None:
    """Slice-1 lifecycle evidence retained under the single-flight contract.

    Reads and writes alternate on one thread — the binding forbids
    overlapped I/O because the native layer is not thread-safe for it — and
    a watchdog close bounds every blocking read.
    """
    child = _spawn(_LIFECYCLE_CHILD)
    watchdog = _ForcedCloseWatchdog(child)
    collected: list[str] = []
    try:
        _read_until(child, "TV_INITIAL:", collected)
        child.write("synthetic-input\r\n")
        _read_until(child, "TV_INPUT:synthetic-input", collected)
        _read_until(child, f"TV_BURST_DONE:{_BURST_BYTES}", collected)

        child.resize(rows=_RESIZED_ROWS, columns=_RESIZED_COLUMNS)
        child.write("measure-after-resize\r\n")
        _read_until(child, "TV_WAITING", collected)

        assert child.is_alive()
    finally:
        watchdog.cancel()
        child.close(force=True)

    assert not child.is_alive()
    assert type(child.exit_status) is int

    combined = "".join(collected)
    initial = re.search(r"TV_INITIAL:(\d+x\d+)", combined)
    resized = re.search(r"TV_RESIZED:(\d+x\d+)", combined)
    assert initial is not None
    assert initial.group(1) == f"{_INITIAL_COLUMNS}x{_INITIAL_ROWS}"
    assert resized is not None
    assert resized.group(1) == f"{_RESIZED_COLUMNS}x{_RESIZED_ROWS}"
    burst_start = combined.find("TV_BURST_START")
    burst_end = combined.find("TV_BURST_DONE")
    assert 0 <= burst_start < burst_end
    _assert_burst_delivered_whole(combined[burst_start:burst_end])


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
def test_release_only_close_under_output_flood_releases_handles() -> None:
    """Item 5 + item 2: handle release stays observable under hostile load.

    The close lands while the reader services an unbounded flood, cancels
    the in-flight read, and still releases the native handles — proven by
    the flooding child dying of the pseudoconsole teardown
    (``STATUS_CONTROL_C_EXIT``), the same OS observable as the quiet-child
    release evidence.
    """
    child = _spawn(_FLOODING_CHILD)
    drain = _Drain(child)
    handle = _open_process_handle(child.pid)
    try:
        drain.wait_for_marker("TV_READY")
        drain.wait_for_at_least(2_000_000)

        child.close(force=False)

        os_exit_code = _wait_for_os_exit_code(handle, _OS_WAIT_TIMEOUT_MS)
    finally:
        child.close(force=True)
        _close_process_handle(handle)
        drain.join()

    assert os_exit_code == _STATUS_CONTROL_C_EXIT
    assert isinstance(drain.wait_for_end(), ConptyClosedError)
    assert child.exit_status is None
    assert not child.is_alive()


@pytest.mark.skipif(os.name != "nt", reason="Windows ConPTY binding evidence")
def test_write_flood_against_non_reading_child_never_blocked() -> None:
    """Item 5 (write path): no conin backpressure observed on this matrix.

    The child never reads stdin, yet every bounded write returns — conhost
    consumes input regardless of the client. The writes run on a helper
    thread only so a regression on some SKU cannot hang the test run; the
    evidence is the completion event, not thread state, and a blocked write
    would fail this test loudly rather than hanging it.
    """
    child = _spawn(_DEAF_CHILD)
    watchdog = _ForcedCloseWatchdog(child)
    collected: list[str] = []
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
        _read_until(child, "TV_READY", collected)
        writer.start()
        finished = completed.wait(_TIMEOUT_SECONDS)
    finally:
        watchdog.cancel()
        child.close(force=True)
        writer.join(_TIMEOUT_SECONDS)

    assert finished, f"bounded write flood did not complete: {write_errors!r}"
    assert not write_errors
    assert not writer.is_alive()
    assert child.exit_status == FORCED_TERMINATION_EXIT_CODE


@pytest.mark.skipif(os.name != "nt", reason="Windows ConPTY binding evidence")
def test_overlapping_io_fails_fast() -> None:
    """Single-flight contract: a write during a blocked read is refused.

    The native layer is not thread-safe for overlapped calls on one
    pseudoconsole — the refusal is what makes the crash unreachable through
    this binding — and blocking the write behind an indefinitely blocked
    read would deadlock instead.
    """
    child = _spawn(_DEAF_CHILD)
    drain = _Drain(child)
    try:
        drain.wait_for_marker("TV_READY")
        # Arrangement, not evidence: after the ready marker the child is
        # silent, so the drain thread re-enters and stays in a blocked
        # native read.
        time.sleep(0.3)

        with pytest.raises(ConptyConcurrentIOError):
            child.write("overlap\r\n")
    finally:
        child.close(force=True)
        drain.join()

    assert isinstance(drain.wait_for_end(), ConptyClosedError)


@pytest.mark.skipif(os.name != "nt", reason="Windows ConPTY binding evidence")
def test_forced_close_waits_out_in_flight_large_write() -> None:
    """Item 5 (stop during in-flight I/O): close waits out a native write.

    A single large write keeps the native call in flight for a substantial
    window. Close must land inside that window and return only after the
    write frame returned — releasing the native object during a native call
    crashes the interpreter — and the write itself completes normally
    (``cancel_io`` does not cancel conin writes; the wait-out is the
    discipline under test).

    The size is chosen against the measured conin throughput (~1 MiB/s: the
    console host turns every byte into input records), so the write stays in
    flight for seconds — long enough for the close to provably overlap it —
    while still finishing inside the close's cancellation budget. It is
    deliberately far below the budget: ``write`` now writes every byte it was
    given rather than however many the previous binding's single native call
    happened to take, so the same wall-clock window is a much smaller payload
    than it used to be.
    """
    child = _spawn(_DEAF_CHILD)
    watchdog = _ForcedCloseWatchdog(child)
    collected: list[str] = []
    events: dict[str, float] = {}
    write_errors: list[BaseException] = []

    def big_write() -> None:
        try:
            events["write_start"] = time.monotonic()
            child.write("W" * (4 * 1024 * 1024))
            events["write_end"] = time.monotonic()
        except BaseException as error:
            write_errors.append(error)

    writer = threading.Thread(target=big_write, name="tv-big-write", daemon=True)
    try:
        _read_until(child, "TV_READY", collected)
        writer.start()
        # Arrangement, not evidence: wait until the write is counted as
        # in flight, so the close provably overlaps the native call.
        deadline = time.monotonic() + _TIMEOUT_SECONDS
        while child._pending_io == 0:
            assert time.monotonic() < deadline, "write never became in-flight"
            time.sleep(0.001)

        close_called = time.monotonic()
        child.close(force=True)
        close_returned = time.monotonic()

        writer.join(_TIMEOUT_SECONDS)
    finally:
        watchdog.cancel()
        child.close(force=True)

    assert not writer.is_alive()
    assert not write_errors, write_errors
    assert "write_end" in events, "the in-flight native write did not complete"
    # Close overlapped the write and returned only after the write frame
    # returned: the ordering evidence for the wait-out discipline. The
    # second assertion is the load-bearing one — the write was still in
    # flight when close was *entered*, not merely before it. Without it the
    # test would degenerate into a tautology if conin ever got fast enough
    # for the write to finish during the arrangement spin, and would still
    # pass.
    assert events["write_start"] < close_returned
    assert events["write_end"] >= close_called, (
        "the write completed before close was entered, so this run proves"
        " nothing about close waiting one out"
    )
    assert events["write_end"] <= close_returned
    assert child.exit_status == FORCED_TERMINATION_EXIT_CODE
    with pytest.raises(ConptyClosedError):
        child.write("late\r\n")


def _assert_no_native_pin(error: BaseException) -> None:
    """Assert no traceback frame in the exception chain pins a native session."""
    # Imported here: the class exists only on Windows, and every caller is a
    # Windows-only test.
    from termverify._conpty import _PseudoConsoleSession

    seen: set[int] = set()
    stack: list[BaseException] = [error]
    while stack:
        current = stack.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        traceback = current.__traceback__
        while traceback is not None:
            for name, value in traceback.tb_frame.f_locals.items():
                # Against the imported class, not its name: this assertion
                # was pinned to pywinpty's `PTY` and silently stopped being
                # able to fail when the binding started owning the session
                # itself. A rename now breaks the import instead.
                assert not isinstance(value, _PseudoConsoleSession), (
                    f"native pseudoconsole pinned via frame local {name!r}"
                )
            traceback = traceback.tb_next
        for linked in (current.__cause__, current.__context__):
            if linked is not None:
                stack.append(linked)


@pytest.mark.skipif(os.name != "nt", reason="Windows ConPTY binding evidence")
def test_spawn_unrunnable_command_fails_closed(tmp_path: Path) -> None:
    """Item 5 (startup failure): an unrunnable command fails closed.

    The command resolves and a pseudoconsole is created, but the OS refuses
    to start the image. The spawn must surface a classified error whose
    held exception chain cannot pin the native pseudoconsole.
    """
    bogus = tmp_path / "termverify-not-a-binary.exe"
    bogus.write_text("this is not a runnable image", encoding="ascii")
    with pytest.raises(OSError, match="ConPTY spawn failed") as failure:
        ConptyChild.spawn([str(bogus)], rows=_INITIAL_ROWS, columns=_INITIAL_COLUMNS)
    _assert_no_native_pin(failure.value)


# --- Slice 2 (cooperation tier): spawn delivery of env overlay and cwd ---

_DELIVERY_CHILD: Final = """\
import os

print("TV_ENV_SEED:" + os.environ.get("TERMVERIFY_SEED", "<missing>"), flush=True)
print(
    "TV_ENV_AMBIENT:" + os.environ.get("TV_AMBIENT_CANARY", "<missing>"),
    flush=True,
)
print(
    "TV_ENV_OVERRIDE:" + os.environ.get("TV_OVERRIDE_CANARY", "<missing>"),
    flush=True,
)
print("TV_CWD:" + os.getcwd(), flush=True)
print("TV_DELIVERY_DONE", flush=True)
"""


@pytest.mark.skipif(os.name != "nt", reason="Windows ConPTY binding evidence")
def test_spawn_runs_a_program_whose_path_contains_spaces(tmp_path: Path) -> None:
    """A spaced ``argv[0]`` starts that program, not a prefix of its path.

    The command line is what the child parses into its own ``argv``, so an
    unquoted spaced program path arrives split across several arguments. The
    binding quotes ``argv[0]`` like every other argument, and names the
    executable to the OS separately, so neither reading can diverge.
    """
    spaced = tmp_path / "program dir with spaces"
    spaced.mkdir()
    # ``cmd.exe`` resolves its dependencies through the system search path, so
    # it still runs from a copy outside its own directory.
    program = spaced / "my shell.exe"
    shutil.copy(Path(os.environ["SYSTEMROOT"]) / "System32" / "cmd.exe", program)

    child = ConptyChild.spawn(
        [str(program), "/c", "echo TV_SPACED_ARGV0"],
        rows=_INITIAL_ROWS,
        columns=_INITIAL_COLUMNS,
    )
    collected: list[str] = []
    try:
        _read_until(child, "TV_SPACED_ARGV0", collected)
    finally:
        child.close(force=True)
    assert "TV_SPACED_ARGV0" in "".join(collected)


@pytest.mark.skipif(os.name != "nt", reason="Windows ConPTY binding evidence")
def test_spawn_delivers_env_overlay_and_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Cooperation-tier slice 2: the child observes delivered values.

    Proves the three disclosed overlay semantics at once: a delivered
    variable reaches the child, an overlay variable wins over an ambient
    variable of the same name, and the ambient environment is inherited
    underneath the overlay. The working directory is the delivered sandbox
    root, observed by the child itself.
    """
    monkeypatch.setenv("TV_AMBIENT_CANARY", "ambient")
    monkeypatch.setenv("TV_OVERRIDE_CANARY", "ambient")
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    child = ConptyChild.spawn(
        [sys.executable, "-I", "-u", "-c", _DELIVERY_CHILD],
        rows=_INITIAL_ROWS,
        columns=_INITIAL_COLUMNS,
        env_overlay={
            "TERMVERIFY_SEED": "42",
            "TV_OVERRIDE_CANARY": "delivered",
        },
        cwd=str(sandbox),
    )
    watchdog = _ForcedCloseWatchdog(child)
    collected: list[str] = []
    try:
        _read_until(child, "TV_DELIVERY_DONE", collected)
    finally:
        watchdog.cancel()
        child.close(force=True)

    combined = "".join(collected)
    assert "TV_ENV_SEED:42" in combined
    assert "TV_ENV_AMBIENT:ambient" in combined
    assert "TV_ENV_OVERRIDE:delivered" in combined
    cwd_match = re.search(r"TV_CWD:([^\r\n]+)", combined)
    assert cwd_match is not None
    assert Path(cwd_match.group(1)).resolve() == sandbox.resolve()


@pytest.mark.skipif(os.name != "nt", reason="Windows ConPTY binding evidence")
def test_spawn_without_overlay_keeps_the_ambient_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Omitted overlay and cwd preserve the pre-amendment spawn behavior."""
    monkeypatch.setenv("TV_AMBIENT_CANARY", "ambient")
    child = ConptyChild.spawn(
        [sys.executable, "-I", "-u", "-c", _DELIVERY_CHILD],
        rows=_INITIAL_ROWS,
        columns=_INITIAL_COLUMNS,
    )
    watchdog = _ForcedCloseWatchdog(child)
    collected: list[str] = []
    try:
        _read_until(child, "TV_DELIVERY_DONE", collected)
    finally:
        watchdog.cancel()
        child.close(force=True)

    combined = "".join(collected)
    assert "TV_ENV_SEED:<missing>" in combined
    assert "TV_ENV_AMBIENT:ambient" in combined
    cwd_match = re.search(r"TV_CWD:([^\r\n]+)", combined)
    assert cwd_match is not None
    assert Path(cwd_match.group(1)).resolve() == Path(os.getcwd()).resolve()
