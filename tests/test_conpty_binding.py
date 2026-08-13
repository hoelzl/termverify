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
  fails fast because the native layer is not thread-safe for it; a bounded
  interactive-scale conin workload makes sustained progress on this matrix.

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
    ConptyGeometryMismatchError,
    ConptyUnsupportedError,
)

from ._end_of_stream_tails import TAILS as _TAILS
from ._end_of_stream_tails import Tail, subject_script

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


#: Issue #279's subject, on the binding that issue predicted would answer it
#: with a replacement character: five ASCII bytes, then two of the three
#: bytes of U+20AC EURO SIGN, then exit.
_TRUNCATED_TAIL_CHILD: Final = """\
import sys

sys.stdout.buffer.write(b"START")
sys.stdout.buffer.write(b"\\xe2\\x82")
sys.stdout.buffer.flush()
"""

#: The same subject, lingering before it exits. Without this case, "the host
#: consumes the incomplete sequence" would be indistinguishable from "the host
#: lost a race with the exit", and only the first is a statement about the
#: host's decoder.
_TRUNCATED_TAIL_LINGER_CHILD: Final = """\
import sys, time

sys.stdout.buffer.write(b"START")
sys.stdout.buffer.write(b"\\xe2\\x82")
sys.stdout.buffer.flush()
time.sleep(1.5)
"""

#: The same truncation with a byte *after* it, so the console host must
#: decide rather than keep waiting. The control for the test below.
_TRUNCATED_MIDSTREAM_CHILD: Final = """\
import sys

sys.stdout.buffer.write(b"A\\xe2\\x82B")
sys.stdout.buffer.flush()
"""


def _drain_to_end(script: str) -> tuple[str, BaseException, int | None]:
    """Run a short-lived subject to end-of-stream; return its rendered text.

    The escapes the console host wraps every session in are stripped, for
    the reason :data:`_ESCAPE` exists: a character inside an escape sequence
    is not a character the child wrote.
    """
    child = _spawn(script)
    drain = _Drain(child)
    try:
        terminal = drain.wait_for_end()
    finally:
        drain.join()
        child.close(force=True)
    return _ESCAPE.sub("", drain.text()), terminal, child.exit_status


@pytest.mark.skipif(os.name != "nt", reason="Windows ConPTY binding evidence")
@pytest.mark.parametrize(
    "script",
    [_TRUNCATED_TAIL_CHILD, _TRUNCATED_TAIL_LINGER_CHILD],
    ids=["exits-immediately", "lingers-first"],
)
def test_a_truncated_trailing_codepoint_never_reaches_this_binding(
    script: str,
) -> None:
    """Measured for issue #279, which predicted the opposite of this.

    The issue reported that this subject yields ``U+FFFD`` here while the
    POSIX binding drops it silently, and filed the difference as an
    evidence divergence between the two bindings. Measured on a real
    console host, it does not: the host is itself a UTF-8 decoder, it holds
    the incomplete sequence waiting for a byte that never comes, and the
    two bytes are gone before this binding sees anything. The lingering
    variant is what makes that a statement about the host's decoder rather
    than about a race with the child's exit.

    What that means for the binding's own ``final=True`` flush, which
    :mod:`tests.test_conpty_decode` pins over a fake native session: it is a
    property of the *conout pipe*, and no real console host has been
    observed to end that pipe mid-codepoint. The flush is right for the
    stream it reads; it is simply not what produces this subject's evidence.
    """
    text, terminal, status = _drain_to_end(script)
    assert isinstance(terminal, ConptyEndOfStreamError)
    assert text == "START", (
        f"the console host's rendering of a truncated trailing codepoint is"
        f" {text!r}, not 'START'. Issue #279's measurement — the host consumes"
        " the incomplete sequence, so it never reaches this binding — no"
        " longer holds, and the platform difference recorded in"
        " _terminal_binding.py was written on it."
    )
    assert status == 0


@pytest.mark.skipif(os.name != "nt", reason="Windows ConPTY binding evidence")
def test_a_truncated_codepoint_the_host_can_decide_is_replaced() -> None:
    """The control: the zero above is the host waiting, not a dead pipeline.

    Give the host a byte that cannot continue the sequence and it resolves
    the same truncation into ``U+FFFD`` immediately. Without this, the test
    above would pass just as well against a pipeline that could never carry
    a replacement character at all.
    """
    text, terminal, status = _drain_to_end(_TRUNCATED_MIDSTREAM_CHILD)
    assert isinstance(terminal, ConptyEndOfStreamError)
    assert text == "A�B"
    assert status == 0


@pytest.mark.skipif(os.name != "nt", reason="Windows ConPTY binding evidence")
@pytest.mark.parametrize("row", _TAILS, ids=lambda row: row.name)
def test_the_end_of_stream_tail_table_holds_on_this_host(row: Tail) -> None:
    """Every row of the divergence table, measured against a real host.

    ``_terminal_binding.py`` states what each binding shows for a subject
    that writes ``START`` and then one bad tail. Three review rounds of
    issue #279 found that table restated and stale, and the third found
    eight of its rows pinned by nothing — so the table is now data
    (``tests/_end_of_stream_tails.py``), both platforms parametrize over it,
    and a row cannot be stated without being measured on each side.

    A failure here is a change in the console host, not in this binding:
    nothing in ``_conpty.py`` decides these outcomes, because the host
    decodes upstream of it.
    """
    text, terminal, status = _drain_to_end(subject_script(row.tail))
    assert isinstance(terminal, ConptyEndOfStreamError)
    assert text == row.conpty, (
        f"the console host rendered {row.name} ({row.tail!r}) as {text!r},"
        f" not {row.conpty!r}. The divergence table in _terminal_binding.py"
        f" and issue #282 were both written on the old measurement."
    )
    assert status == 0


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


def _spy_spawned_process_handles(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Open an OS handle to every child the binding creates (issue #235).

    The handle is opened inside the ``CreateProcessW`` interception, while
    the child is still suspended, so exit-code evidence taken later can
    never race PID reaping or reuse. Opening a handle only *after* the
    teardown under test races the very termination it means to observe —
    the error-87 ``OpenProcess`` flake recorded on issue #202.
    """
    handles: list[int] = []
    _spy_spawned(monkeypatch, handles=handles)
    return handles


def _spy_spawned(
    monkeypatch: pytest.MonkeyPatch, *, handles: list[int] | None = None
) -> list[Any]:
    """Record (pid, thread handle, creation flags) for every spawned child.

    The returned list — and *handles* when given — are live: the spy
    appends as children are created, so callers observe spawns that happen
    after this helper returns.
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
            if handles is not None:
                try:
                    handles.append(_open_process_handle(pid))
                except BaseException:
                    # Fail closed like the code under test: a raise out of
                    # this interception makes the binding treat the spawn
                    # as failed, so the just-created suspended child must
                    # not outlive the failed arrangement (PR #263 review,
                    # I2). The kernel handle in `information` is live and
                    # ours to use before the binding sees the result.
                    _terminate_process(int(information.hProcess))
                    raise
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
    # DWORD is spelled c_uint32 here: ctypes.wintypes does not exist off
    # Windows, and the Linux mypy leg checks this file too.
    native: Any = conpty_module
    flags = ctypes.c_uint32()
    return bool(native._kernel32.GetHandleInformation(handle, ctypes.byref(flags)))


def _spy_verified_closes(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """Record handles OS-verified closed at the moment of their CloseHandle.

    The validity check runs inside the spy, immediately after the real
    ``CloseHandle`` returns in the same call stack: a later check cannot
    distinguish a recycled handle value (the CI failure this replaces —
    the constructor's own allocations reused the freed value before the
    test could ask the OS).
    """
    import termverify._conpty as conpty_module

    native: Any = conpty_module
    kernel32 = native._kernel32
    real_close_handle = kernel32.CloseHandle
    verified: list[int] = []

    def recording_close_handle(handle):  # type: ignore[no-untyped-def]
        result = real_close_handle(handle)
        value = int(handle.value if hasattr(handle, "value") else handle)
        if result and not _handle_is_open(value):
            verified.append(value)
        return result

    monkeypatch.setattr(kernel32, "CloseHandle", recording_close_handle)
    return verified


def _assert_os_terminated(handle: int) -> None:
    """Prove by a spawn-time OS handle that the child died forced.

    The handle must come from ``_spy_spawned_process_handles`` — opened
    while the child was suspended — so this wait cannot race the reaping
    of the very termination it observes (issue #202).
    """
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
    verified_closed = _spy_verified_closes(monkeypatch)

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
        assert thread_handle in verified_closed, (
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

    child_handles = _spy_spawned_process_handles(monkeypatch)

    def exploding_pid(self):  # type: ignore[no-untyped-def]
        raise KeyboardInterrupt("injected pre-try failure")

    monkeypatch.setattr(
        conpty_module._PseudoConsoleSession, "pid", property(exploding_pid)
    )

    with pytest.raises(KeyboardInterrupt):
        _spawn(_BLOCKING_CHILD)
    assert child_handles, "the injected failure fired before the child existed"
    _assert_os_terminated(child_handles[0])


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

    child_handles: list[int] = []
    spawned = _spy_spawned(monkeypatch, handles=child_handles)
    verified_closed = _spy_verified_closes(monkeypatch)

    def failing_resume(thread_handle: int) -> None:
        raise OSError("injected resume failure")

    monkeypatch.setattr(conpty_module, "_resume_main_thread", failing_resume)

    with pytest.raises(OSError, match="failed to contain ConPTY child"):
        _spawn(_BLOCKING_CHILD)
    assert spawned, "the injected failure fired before the child existed"
    _, thread_handle, _ = spawned[0]
    assert thread_handle in verified_closed, "the thread handle leaked on the teardown"
    _assert_os_terminated(child_handles[0])


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

    child_handles = _spy_spawned_process_handles(monkeypatch)
    native: Any = conpty_module
    monkeypatch.setattr(native._kernel32, "CreateEventW", lambda *args: 0)

    with pytest.raises(OSError):
        _spawn(_BLOCKING_CHILD)
    assert child_handles, "the injected failure fired before the child existed"
    _assert_os_terminated(child_handles[0])


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

    child_handles = _spy_spawned_process_handles(monkeypatch)
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
    assert child_handles, "the injected failure fired before the child existed"
    _assert_os_terminated(child_handles[0])


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

    child_handles = _spy_spawned_process_handles(monkeypatch)
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
    assert child_handles, "the injected failure fired before the child existed"
    _assert_os_terminated(child_handles[0])


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
_WRITE_PROBE_CHUNKS: Final = 64


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
def test_interactive_scale_writes_progress_against_non_reading_child() -> None:
    """Item 5 (write path): bounded interactive-scale progress on this matrix.

    The child never reads stdin. The probe records only that this 4 MiB
    workload completes; it does not infer unbounded consumption or the
    absence of backpressure. The former 16 MiB flood was a load-sensitive
    throughput benchmark whose 60-second cap flipped under host contention.
    The helper thread and timeout only keep a contradiction from hanging the
    test process; they are not evidence of a latency or throughput guarantee.
    """
    child = _spawn(_DEAF_CHILD)
    watchdog = _ForcedCloseWatchdog(child)
    collected: list[str] = []
    completed = threading.Event()
    write_errors: list[BaseException] = []

    def flood() -> None:
        try:
            for _ in range(_WRITE_PROBE_CHUNKS):
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

    assert finished, f"bounded write probe did not complete: {write_errors!r}"
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
print("TV_CWD:" + os.getcwd() + ":TV_CWD_END", flush=True)
print("TV_DELIVERY_DONE", flush=True)
"""


def _extract_cwd(combined: str) -> str:
    """Recover the child's cwd from raw terminal output.

    Raw ConPTY output is diagnostic evidence, not a clean byte channel:
    the renderer may inject OSC/CSI sequences and wrap-induced line breaks
    into and after the child's text with no newline in between (the
    windows-3.14 flake observed on PR #263's CI). The child brackets the
    path with an explicit terminator, and every VT sequence and line
    break is stripped before matching, so neither trailing escapes nor a
    mid-path wrap can corrupt the capture.
    """
    flattened = re.sub(
        r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b\[[0-9;?]*[A-Za-z]|\x1b.|[\r\n]",
        "",
        combined,
    )
    match = re.search(r"TV_CWD:(.+?):TV_CWD_END", flattened)
    assert match is not None, "TV_CWD marker not found in the drained output"
    return match.group(1)


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
    assert Path(_extract_cwd(combined)).resolve() == sandbox.resolve()


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
    assert Path(_extract_cwd(combined)).resolve() == Path(os.getcwd()).resolve()


# --- geometry verification (issue #228) -------------------------------------
#
# The pseudoconsole's COORD is a signed 16-bit member per axis, and conhost
# range-checks nothing at creation: a request that does not survive the int16
# wrap is silently truncated (the child runs at a size the receipt claims
# ``tier="os"`` for), refused with a raw HRESULT, or the child dies at console
# attach. ``ConptyChild.spawn`` verifies every geometry before handing out a
# session: predictable misfires are refused outright, and the rest are proven
# by a probe child's read-back of the adopted size, cached per process.


def _spawn_at(script: str, *, rows: int, columns: int) -> ConptyChild:
    return ConptyChild.spawn(
        [sys.executable, "-I", "-u", "-c", script], rows=rows, columns=columns
    )


def _refusal_must_not_spawn(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail the test if the refusal path spawns anything at all.

    The predictive half of the verification refuses from the measured model
    *without spawning* — no subject, not even the probe child. A refusal
    that still reaches ``_open_session`` has lost its predictive layer and
    is paying a probe (or leaking a dying child) for a known-bad geometry.
    """
    import termverify._conpty as conpty_module

    def _spying_open(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("a predictable geometry refusal spawned a child")

    monkeypatch.setattr(conpty_module, "_open_session", _spying_open)


@pytest.mark.skipif(os.name != "nt", reason="Windows ConPTY binding evidence")
def test_a_geometry_wrapping_to_zero_fails_structured_before_creation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A wrapped-to-zero COORD member is refused with the structured error.

    Measured on the dev host: rows=65536 wraps to 0 and CreatePseudoConsole
    answers with E_INVALIDARG; the spawn must surface the geometry refusal,
    not the raw HRESULT.
    """
    _refusal_must_not_spawn(monkeypatch)
    with pytest.raises(ConptyGeometryMismatchError, match="65536"):
        _spawn_at(_BLOCKING_CHILD, rows=65_536, columns=10)


@pytest.mark.skipif(os.name != "nt", reason="Windows ConPTY binding evidence")
def test_a_geometry_wrapping_negative_fails_before_the_child_dies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A wrapped-negative COORD member is refused before the child exists.

    Measured on the dev host: columns=100000 wraps to a negative int16 and
    conhost kills the child at console attach (STATUS_DLL_INIT_FAILED) — the
    run started and produced a cryptic exit, not a geometry failure.
    """
    _refusal_must_not_spawn(monkeypatch)
    with pytest.raises(ConptyGeometryMismatchError, match="100000"):
        _spawn_at(_BLOCKING_CHILD, rows=10, columns=100_000)


@pytest.mark.skipif(os.name != "nt", reason="Windows ConPTY binding evidence")
def test_a_geometry_the_console_would_silently_truncate_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The overclaim class itself: silent truncation to a different size.

    Measured on the dev host: rows=65546 wraps to 10 and the child runs at
    10 rows while the receipt records 65546 at ``tier="os"``.
    """
    _refusal_must_not_spawn(monkeypatch)
    with pytest.raises(ConptyGeometryMismatchError, match="65546"):
        _spawn_at(_BLOCKING_CHILD, rows=65_546, columns=10)


@pytest.mark.skipif(os.name != "nt", reason="Windows ConPTY binding evidence")
def test_an_exactly_adopted_geometry_spawns_and_is_cached() -> None:
    """A geometry the console adopts exactly passes and is cached."""
    import termverify._conpty as conpty_module

    conpty_module._GEOMETRY_ADOPTIONS.pop((40, 120), None)
    child = _spawn_at(_BLOCKING_CHILD, rows=40, columns=120)
    try:
        assert child.is_alive()
    finally:
        child.close(force=True)
    assert conpty_module._GEOMETRY_ADOPTIONS[(40, 120)] == (40, 120)


@pytest.mark.skipif(os.name != "nt", reason="Windows ConPTY binding evidence")
def test_a_verified_geometry_is_not_probed_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The per-process cache bounds the read-back cost to one probe."""
    import termverify._conpty as conpty_module

    conpty_module._GEOMETRY_ADOPTIONS.pop((50, 132), None)
    _spawn_at(_BLOCKING_CHILD, rows=50, columns=132).close(force=True)

    def _reprobe(rows: int, columns: int) -> tuple[int, int]:
        raise AssertionError("a verified geometry was probed again")

    monkeypatch.setattr(conpty_module, "_probe_geometry", _reprobe)
    _spawn_at(_BLOCKING_CHILD, rows=50, columns=132).close(force=True)


@pytest.mark.skipif(os.name != "nt", reason="Windows ConPTY binding evidence")
def test_a_read_back_mismatch_fails_the_spawn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The read-back half: a diverging adoption fails the spawn structured.

    On this host the predictive check already refuses every known misfire;
    the read-back guards the residual — a Windows build whose conhost
    substitutes instead of truncating (the 120x30 observation in #228).
    """
    import termverify._conpty as conpty_module

    conpty_module._GEOMETRY_ADOPTIONS.pop((41, 121), None)
    monkeypatch.setattr(
        conpty_module, "_probe_geometry", lambda rows, columns: (rows - 1, columns)
    )
    try:
        with pytest.raises(ConptyGeometryMismatchError, match="adopted"):
            _spawn_at(_BLOCKING_CHILD, rows=41, columns=121)
    finally:
        # A monkeypatched probe's cached mismatch is poison for later
        # honest verifications in this process; do not leave it behind.
        conpty_module._GEOMETRY_ADOPTIONS.pop((41, 121), None)


@pytest.mark.skipif(os.name != "nt", reason="Windows ConPTY binding evidence")
def test_a_failing_probe_fails_the_spawn_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A probe that cannot answer must not hand out an unverified session."""
    import termverify._conpty as conpty_module

    conpty_module._GEOMETRY_ADOPTIONS.pop((42, 122), None)

    def _boom(rows: int, columns: int) -> tuple[int, int]:
        raise OSError("probe exploded")

    monkeypatch.setattr(conpty_module, "_probe_geometry", _boom)
    with pytest.raises(OSError, match="probe exploded"):
        _spawn_at(_BLOCKING_CHILD, rows=42, columns=122)


# --- resize-boundary verification (issue #228, review round 1, F1) ---------
#
# The resize boundary re-opens the same defect class: measured on the dev
# host against the post-spawn-fix code, ResizePseudoConsole silently
# truncates a wrapping geometry (7x65600 adopted as 64 columns), silently
# NO-OPS a wrap-to-zero (the console keeps its previous size), and errors
# only on wrap-negative — while the adapter's normalizer was told the
# requested size. ``ConptyChild.resize`` verifies exactly like ``spawn``.


@pytest.mark.skipif(os.name != "nt", reason="Windows ConPTY binding evidence")
def test_a_resize_the_console_would_silently_truncate_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """7x65600 would silently resize the console to 7x64: refuse it.

    Measured on the dev host: ResizePseudoConsole adopted 64 columns and
    reported success — the normalizer would have modeled 65600.
    """
    child = _spawn_at(_BLOCKING_CHILD, rows=30, columns=120)
    try:
        _refusal_must_not_spawn(monkeypatch)
        with pytest.raises(ConptyGeometryMismatchError, match="65600"):
            child.resize(rows=7, columns=65_600)
        # The refused resize changed nothing: the session is still healthy
        # and a legitimate resize still takes effect.
        # Recovery targets the cached setup geometry, so the no-spawn spy
        # stays silent; a live resize still takes effect after the refusal.
        child.resize(rows=30, columns=120)
        assert child.is_alive()
    finally:
        child.close(force=True)


@pytest.mark.skipif(os.name != "nt", reason="Windows ConPTY binding evidence")
def test_a_resize_wrapping_to_zero_fails_instead_of_silently_no_oping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The sneakiest misfire: wrap-to-zero at resize is a silent no-op.

    Measured on the dev host: resizing to columns=65536 returned success
    and the console kept its previous size — the adapter would believe a
    resize that never happened. Refuse it structurally instead.
    """
    child = _spawn_at(_BLOCKING_CHILD, rows=30, columns=120)
    try:
        _refusal_must_not_spawn(monkeypatch)
        with pytest.raises(ConptyGeometryMismatchError, match="65536"):
            child.resize(rows=30, columns=65_536)
        # Recovery targets the cached setup geometry, so the no-spawn spy
        # stays silent; a live resize still takes effect after the refusal.
        child.resize(rows=30, columns=120)
        assert child.is_alive()
    finally:
        child.close(force=True)


@pytest.mark.skipif(os.name != "nt", reason="Windows ConPTY binding evidence")
def test_a_resize_wrapping_negative_fails_structured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Wrap-negative errors natively at resize; refuse it before that."""
    child = _spawn_at(_BLOCKING_CHILD, rows=30, columns=120)
    try:
        _refusal_must_not_spawn(monkeypatch)
        with pytest.raises(ConptyGeometryMismatchError, match="40000"):
            child.resize(rows=30, columns=40_000)
        assert child.is_alive()
    finally:
        child.close(force=True)


@pytest.mark.skipif(os.name != "nt", reason="Windows ConPTY binding evidence")
def test_a_resize_to_an_exactly_adopted_geometry_succeeds() -> None:
    """An uncached exact geometry is probed once, then the resize applies."""
    import termverify._conpty as conpty_module

    conpty_module._GEOMETRY_ADOPTIONS.pop((50, 132), None)
    child = _spawn_at(_BLOCKING_CHILD, rows=30, columns=120)
    try:
        child.resize(rows=50, columns=132)
        assert child.is_alive()
        assert conpty_module._GEOMETRY_ADOPTIONS[(50, 132)] == (50, 132)
    finally:
        child.close(force=True)


@pytest.mark.skipif(os.name != "nt", reason="Windows ConPTY binding evidence")
def test_a_resize_read_back_mismatch_fails_the_resize(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The resize half of the read-back: a diverging adoption fails closed."""
    import termverify._conpty as conpty_module

    conpty_module._GEOMETRY_ADOPTIONS.pop((41, 130), None)
    monkeypatch.setattr(
        conpty_module, "_probe_geometry", lambda rows, columns: (rows - 1, columns)
    )
    child = _spawn_at(_BLOCKING_CHILD, rows=30, columns=120)
    try:
        with pytest.raises(ConptyGeometryMismatchError, match="adopted"):
            child.resize(rows=41, columns=130)
        assert child.is_alive()
    finally:
        child.close(force=True)
        # The mismatch is cached by design (fail-closed from cache on
        # repeat); a monkeypatched probe's entry is poison for every later
        # honest verification in this process, so the test must not leave
        # it behind.
        conpty_module._GEOMETRY_ADOPTIONS.pop((41, 130), None)


# --- probe failure-mode guards (issue #228, review round 1, F3) ------------
#
# ``_probe_geometry`` fails closed on three infrastructure paths: a wedged
# probe (deadline), no exit record, and an undecodable exit status (crash
# aliasing). These guards are platform-neutral once the child spawn is
# stubbed, so they run on every host.


class _StubProbeChild:
    """The ``ConptyChild`` surface ``_probe_geometry`` uses, scripted."""

    def __init__(self, *, alive: bool, status: int | None) -> None:
        self._alive = alive
        self._status = status
        self.closed_with_force: bool | None = None

    def is_alive(self) -> bool:
        return self._alive

    @property
    def exit_status(self) -> int | None:
        return self._status

    def close(self, *, force: bool) -> None:
        self.closed_with_force = force
        self._alive = False


def _stub_probe_spawn(monkeypatch: pytest.MonkeyPatch, child: _StubProbeChild) -> None:
    import termverify._conpty as conpty_module

    def _stub_spawn_contained(
        cls: type[Any], /, argv: Any, **kwargs: Any
    ) -> _StubProbeChild:
        return child

    monkeypatch.setattr(
        conpty_module.ConptyChild,
        "_spawn_contained",
        classmethod(_stub_spawn_contained),
    )


def test_a_wedged_probe_fails_closed_and_is_reaped_forcefully(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import termverify._conpty as conpty_module

    monkeypatch.setattr(conpty_module, "_GEOMETRY_PROBE_TIMEOUT_SECONDS", 0.2)
    child = _StubProbeChild(alive=True, status=None)
    _stub_probe_spawn(monkeypatch, child)

    with pytest.raises(OSError, match="did not exit"):
        conpty_module._probe_geometry(24, 80)
    assert child.closed_with_force is True


def test_a_probe_without_an_exit_record_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import termverify._conpty as conpty_module

    child = _StubProbeChild(alive=False, status=None)
    _stub_probe_spawn(monkeypatch, child)

    with pytest.raises(OSError, match="no exit record"):
        conpty_module._probe_geometry(24, 80)
    assert child.closed_with_force is True


def test_a_probe_crash_exit_status_cannot_alias_a_geometry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The load-bearing decode guard: a crash status decodes out of band.

    STATUS_DLL_INIT_FAILED (0xC0000142) as (columns<<16)|rows would claim
    columns=49152 — outside [1, 32767], so the probe fails closed instead
    of "verifying" a geometry no console has.
    """
    import termverify._conpty as conpty_module

    child = _StubProbeChild(alive=False, status=0xC0000142)
    _stub_probe_spawn(monkeypatch, child)

    with pytest.raises(OSError, match="probe child failed"):
        conpty_module._probe_geometry(24, 80)
    assert child.closed_with_force is True


def test_the_geometry_contract_rejects_non_int_axes() -> None:
    """Geometry axes are ints; anything else is a contract violation.

    Platform-neutral: the guard runs before any native call. ``bool`` is an
    ``int`` subclass but not a geometry, so the check is on the exact type.
    """
    import termverify._conpty as conpty_module

    with pytest.raises(TypeError, match="rows.*str"):
        conpty_module._verify_geometry("24", 80)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="columns.*float"):
        conpty_module._verify_geometry(24, 80.5)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="rows.*bool"):
        conpty_module._verify_geometry(True, 80)


@pytest.mark.skipif(os.name != "nt", reason="Windows ConPTY binding evidence")
def test_a_resize_to_the_maximum_coord_axis_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The resize-only kill band: an axis of exactly 32767 kills the client.

    Measured on the dev host (review round 2): ResizePseudoConsole to an
    axis of exactly 32767 with an otherwise adoptable geometry — including
    a same-size resize — returns success while the attached client dies
    within half a second (observed as STATUS_CONTROL_C_EXIT (0xC000013A)
    for a stdin-blocked client); every 32766 variant is fine. Creation is
    unaffected (32767x32767 is adopted exactly), so the creation-semantics
    probe cannot see the band: the run would record a subject exit the
    adapter's own resize caused. Refuse it predictively.
    """
    child = _spawn_at(_BLOCKING_CHILD, rows=30, columns=120)
    try:
        _refusal_must_not_spawn(monkeypatch)
        for rows, columns in ((1, 32_767), (32_767, 1), (32_767, 32_767)):
            with pytest.raises(
                ConptyGeometryMismatchError, match="otherwise adoptable"
            ):
                child.resize(rows=rows, columns=columns)
        # The type contract precedes even the kill-band check.
        with pytest.raises(TypeError, match="must be an int"):
            child.resize(rows=32_767.0, columns=1)  # type: ignore[arg-type]
        # The refused resizes changed nothing: a same-size resize to the
        # cached creation geometry still takes effect.
        child.resize(rows=30, columns=120)
        assert child.is_alive()
    finally:
        child.close(force=True)
