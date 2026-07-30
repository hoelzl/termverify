"""OS-level evidence for the real JSONL pipe/process binding (slice 2).

These tests prove the real ``termverify._jsonl_pipe`` binding against real
subprocesses on every CI leg — pipes are portable, so unlike the ConPTY
binding there is no platform skip. The asserted evidence is always an OS
observation (real exit codes, pipe semantics, process liveness), never
helper-thread or wall-clock state:

- **Spawn and line I/O:** a real child exchanges framed lines over the two
  pipes; end-of-stream is reported only after every buffered line has been
  delivered, and the OS-observed exit record is captured.
- **Natural exit:** the child's exit code is observed through the binding's
  own ``exit_status`` exactly once the child exits.
- **Forced teardown:** a forced close terminates the child tree (a spawned
  grandchild dies with it), reports the uniform forced exit code on
  Windows / SIGKILL on POSIX, and leaves no survivor; a release-only close
  of a live child is refused rather than silently leaking the tree.
- **Delivery:** the spawn environment overlay and working directory the
  receipts record are exactly what the child observes.
- **Failures:** a missing command fails closed at spawn; writes and reads
  after close raise the binding's closed error.
- **Containment results (Windows):** a failed job-object call is checked and
  reported — a failed assignment fails the spawn closed and kills the child,
  and a failed termination is raised instead of read as a success. The
  boundaries of that checking are held too: a child that exits inside the
  assignment window still spawns and reports its real exit (Windows cannot
  assign an exited process, which is not a containment failure); a forced
  close of such a binding claims nothing it cannot do, since its job is
  permanently empty; and a failed termination with a read in flight still
  sweeps every job member and returns, instead of stranding the teardown
  behind the blocked reader's pipe lock.

The fixture children are minimal ``python -c`` scripts in the ConPTY
integration pattern: they read stdin as bytes, decode UTF-8, and split on
newlines — the ordinary subject-side obligation for this transport, with
no console-input caveats (issue #169 does not apply to pipes).
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import Any

import pytest

from termverify._jsonl_pipe import FORCED_TERMINATION_SIGNAL, PipeJsonlChild
from termverify.control import _MAX_LINE_BYTES, ControlProtocolError, parse_message
from termverify.jsonl import (
    JsonlChildClosedError,
    JsonlConcurrentReadError,
    JsonlEndOfStreamError,
)

_OS_WAIT_TIMEOUT_S = 30.0
_POLL_INTERVAL_S = 0.02
#: Arrangement, never evidence: let a helper thread's read reach the
#: blocking syscall before the test closes underneath it. Over-waiting
#: costs time; under-waiting only makes the test arrange a weaker case.
_READ_ARRIVAL_S = 0.2


def _call_capturing(call: Callable[[], object]) -> BaseException | None:
    """Run `call` in a helper thread, returning the exception it raised.

    Assertions belong on the test thread: an `assert` inside a thread body
    would fail the thread and leave the test asserting on a timeout.
    """
    try:
        call()
    except BaseException as error:  # noqa: BLE001 - diagnostic capture
        return error
    return None


#: Echo child: reports its pid and delivered environment, echoes each line
#: back uppercased, exits 3 on the "exit" line, and hangs forever on "hang".
_ECHO_CHILD = """\
import os
import sys

fd_in = sys.stdin.buffer
fd_out = sys.stdout.buffer

fd_out.write(b"TV_PID:" + str(os.getpid()).encode() + b"\\n")
fd_out.write(b"TV_MARK=" + os.environ.get("TV_MARK", "<missing>").encode() + b"\\n")
fd_out.write(b"TV_CWD=" + os.getcwd().encode() + b"\\n")
fd_out.flush()
for line in fd_in:
    command = line.rstrip(b"\\n").decode("utf-8")
    if command == "exit":
        fd_out.write(b"TV_EXIT\\n")
        fd_out.flush()
        sys.exit(3)
    if command == "hang":
        import time

        time.sleep(600)
    fd_out.write(b"TV_ECHO:" + line.rstrip(b"\\n") + b"\\n")
    fd_out.flush()
"""

#: Tree child: spawns one grandchild that sleeps forever, reports both pids,
#: then hangs forever; only a tree teardown can end it.
_TREE_CHILD = """\
import os
import subprocess
import sys
import time

grandchild = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(600)"])
sys.stdout.write(f"TV_PID:{os.getpid()}\\n")
sys.stdout.write(f"TV_GRANDCHILD:{grandchild.pid}\\n")
sys.stdout.flush()
time.sleep(600)
"""


#: Escaping child (POSIX): starts a grandchild in its OWN session, holding
#: the inherited stdout write end, then exits itself. `killpg` on the
#: child's group cannot reach a process in another session, so the write
#: end outlives the whole contained tree and a reader blocked on stdout
#: never observes end-of-stream. This is review finding R4's subject, and
#: the same shape as #213's descendant-held pipe.
_ESCAPING_CHILD = """\
import os
import subprocess
import sys
import time

grandchild = subprocess.Popen(
    [sys.executable, "-c", "import time; time.sleep(600)"],
    stdout=sys.stdout,
    start_new_session=True,
)
sys.stdout.write(f"TV_GRANDCHILD:{grandchild.pid}\\n")
sys.stdout.flush()
sys.exit(0)
"""


def _argv(script: str) -> list[str]:
    return [sys.executable, "-I", "-u", "-c", script]


def _spawn(script: str = _ECHO_CHILD, **kwargs: object) -> PipeJsonlChild:
    return PipeJsonlChild.spawn(_argv(script), **kwargs)  # type: ignore[arg-type]


@contextmanager
def _reaped(child: PipeJsonlChild) -> Iterator[PipeJsonlChild]:
    """Cleanup arrangement, not evidence: never leak a child past a failure."""
    try:
        yield child
    finally:
        child.close(force=True)


def _wait_for_exit(pid: int) -> None:
    """OS-level liveness wait: returns once the pid no longer exists."""
    deadline = time.monotonic() + _OS_WAIT_TIMEOUT_S
    while time.monotonic() < deadline:
        if not _pid_alive(pid):
            return
        time.sleep(_POLL_INTERVAL_S)
    raise AssertionError(f"process {pid} is still alive after the wait budget")


def _pid_alive(pid: int) -> bool:
    if os.name == "nt":
        # An exit code of 259 (STILL_ACTIVE) means the process is alive; any
        # other answer — including "no such process" — means it is gone.
        completed = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f"$p = Get-Process -Id {pid} -ErrorAction SilentlyContinue;"
                " if ($p) { exit 0 } else { exit 1 }",
            ],
            capture_output=True,
            check=False,
        )
        return completed.returncode == 0
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def test_spawn_exchanges_lines_and_observes_natural_exit() -> None:
    child = _spawn()
    with _reaped(child):
        banner = child.read_line()
        assert banner.startswith(b"TV_PID:")
        mark = child.read_line()
        assert mark == b"TV_MARK=<missing>\n"
        cwd_line = child.read_line()
        assert cwd_line.startswith(b"TV_CWD=")

        child.write_line(b"hello\n")
        assert child.read_line() == b"TV_ECHO:hello\n"

        child.write_line(b"exit\n")
        assert child.read_line() == b"TV_EXIT\n"
        with pytest.raises(JsonlEndOfStreamError):
            child.read_line()
        assert child.exit_status == 3


def test_end_of_stream_delivers_every_buffered_line_first() -> None:
    """Pipe semantics: buffered output arrives before the end-of-stream."""
    child = _spawn()
    with _reaped(child):
        child.write_line(b"one\n")
        child.write_line(b"exit\n")
        lines: list[bytes] = []
        with pytest.raises(JsonlEndOfStreamError):
            while True:
                lines.append(child.read_line())
        assert b"TV_ECHO:one\n" in lines
        assert lines[-1] == b"TV_EXIT\n"
        assert child.exit_status == 3


def test_forced_close_terminates_a_hanging_child_os_observed() -> None:
    child = _spawn()
    pid = child.pid
    child.read_line()
    child.write_line(b"hang\n")
    child.close(force=True)
    if os.name == "nt":
        assert child.exit_status == 15
    else:
        assert child.exit_status == -FORCED_TERMINATION_SIGNAL
    _wait_for_exit(pid)


def test_forced_close_terminates_the_whole_tree() -> None:
    child = _spawn(_TREE_CHILD)
    first = child.read_line()
    second = child.read_line()
    pid = int(first.split(b":", 1)[1])
    grandchild_pid = int(second.split(b":", 1)[1])
    assert _pid_alive(grandchild_pid)
    child.close(force=True)
    _wait_for_exit(pid)
    _wait_for_exit(grandchild_pid)
    assert not _pid_alive(grandchild_pid)


def test_release_only_close_of_a_live_child_is_refused() -> None:
    child = _spawn()
    with _reaped(child):
        child.read_line()
        with pytest.raises(RuntimeError, match="release-only close"):
            child.close(force=False)
        # Refusal is a true no-op: the binding is exactly as it was —
        # reads still work, and a later forced close still tears the
        # live tree down honestly (a half-closed binding would abandon
        # the contained tree until parent exit). Two banner lines remain
        # after the first read (TV_MARK, TV_CWD).
        child.read_line()
        child.read_line()
        child.write_line(b"ping\n")
        assert child.read_line() == b"TV_ECHO:ping\n"
        child.close(force=True)
        expected = 15 if os.name == "nt" else -9
        assert child.exit_status == expected
        # After refusal and a real forced close, the close is settled:
        # a further close returns immediately.
        child.close(force=False)


def test_second_concurrent_read_raises_the_bindings_own_error() -> None:
    """A second in-flight read is a caller contract violation.

    It must surface as the binding's own ``RuntimeError``, never as
    ``JsonlChildClosedError`` — the adapter classifies the closed error as
    a peer failure, which would pin a harness bug on the subject
    (review 2026-07-24, section 4). The violated binding stays usable:
    the first read still completes normally.
    """
    child = _spawn()
    with _reaped(child):
        child.read_line()
        child.read_line()
        child.read_line()
        outcome: list[BaseException | None] = []
        reader = threading.Thread(
            target=lambda: outcome.append(_call_capturing(child.read_line))
        )
        reader.start()
        # Arrangement: let the first read reach the blocking syscall so the
        # second read is genuinely concurrent, not merely sequential.
        time.sleep(_READ_ARRIVAL_S)
        try:
            with pytest.raises(JsonlConcurrentReadError, match="one in-flight read"):
                child.read_line()
        finally:
            child.write_line(b"ping\n")
            reader.join(timeout=_OS_WAIT_TIMEOUT_S)
        assert not reader.is_alive(), "the first read was never unblocked"
        assert outcome == [None], f"the first read failed: {outcome}"


def test_read_racing_a_refused_release_only_close_never_sees_closed() -> None:
    """A refused release-only close is invisible to a concurrent reader.

    The refusal decision must happen before any closed state becomes
    observable: a read racing the refused close either waits or succeeds,
    but never fails with the binding's closed error (review 2026-07-24,
    section 4: the transient ``_closed`` window). The child's liveness
    poll is gated so the race is deterministic — private arrangement,
    public evidence: the assertions are on ``read_line``'s and ``close``'s
    public outcomes.
    """
    child = _spawn()
    with _reaped(child):
        child.read_line()
        child.read_line()
        child.read_line()
        # The racing read's reply is already on its way before the race
        # begins, so the reader returns promptly once allowed to proceed.
        child.write_line(b"ping\n")
        process = child._process  # noqa: SLF001 - gated-poll arrangement
        assert process is not None
        original_poll = process.poll
        in_poll = threading.Event()
        release_poll = threading.Event()

        def gated_poll() -> int | None:
            in_poll.set()
            release_poll.wait(timeout=_OS_WAIT_TIMEOUT_S)
            return original_poll()

        process.poll = gated_poll  # type: ignore[method-assign]
        try:
            closer_outcome: list[BaseException | None] = []
            closer = threading.Thread(
                target=lambda: closer_outcome.append(
                    _call_capturing(lambda: child.close(force=False))
                )
            )
            closer.start()
            assert in_poll.wait(timeout=_OS_WAIT_TIMEOUT_S)
            reader_outcome: list[BaseException | None] = []
            reader = threading.Thread(
                target=lambda: reader_outcome.append(_call_capturing(child.read_line))
            )
            reader.start()
            # Without the ordering fix the racing read fails immediately
            # with the closed error; give it the arrival window, then let
            # the refusal proceed.
            time.sleep(_READ_ARRIVAL_S)
            release_poll.set()
            closer.join(timeout=_OS_WAIT_TIMEOUT_S)
            reader.join(timeout=_OS_WAIT_TIMEOUT_S)
        finally:
            process.poll = original_poll  # type: ignore[method-assign]
        assert not closer.is_alive() and not reader.is_alive()
        assert isinstance(closer_outcome[0], RuntimeError), (
            f"the release-only close was not refused: {closer_outcome}"
        )
        assert reader_outcome == [None], (
            f"the racing read observed the refused close: {reader_outcome}"
        )


def test_release_only_close_of_an_exited_child_captures_the_record() -> None:
    child = _spawn()
    with _reaped(child):
        child.write_line(b"exit\n")
        with pytest.raises(JsonlEndOfStreamError):
            while True:
                child.read_line()
        child.close(force=False)
        assert child.exit_status == 3


def test_spawn_delivers_env_overlay_and_cwd(tmp_path: Path) -> None:
    child = PipeJsonlChild.spawn(
        _argv(_ECHO_CHILD), env_overlay={"TV_MARK": "delivered"}, cwd=str(tmp_path)
    )
    with _reaped(child):
        child.read_line()
        assert child.read_line() == b"TV_MARK=delivered\n"
        cwd_line = child.read_line().decode()
        observed = cwd_line.split("=", 1)[1].rstrip("\r\n")
        assert os.path.normcase(observed) == os.path.normcase(str(tmp_path))


def test_spawn_missing_command_fails_closed() -> None:
    with pytest.raises(FileNotFoundError):
        PipeJsonlChild.spawn(["termverify-no-such-command-anywhere"])


def test_io_after_close_raises_the_closed_error() -> None:
    child = _spawn()
    child.read_line()
    child.close(force=True)
    with pytest.raises(JsonlChildClosedError):
        child.read_line()
    with pytest.raises(JsonlChildClosedError):
        child.write_line(b"late\n")
    # Closing twice is a no-op, never an error.
    child.close(force=True)


def test_forced_close_unblocks_an_in_flight_read() -> None:
    """The watchdog path: close from another thread ends a blocked read."""
    import threading

    child = _spawn()
    pid = child.pid
    # Drain the whole banner (pid, mark, cwd) so the next read genuinely
    # blocks on a live child with no buffered output.
    child.read_line()
    child.read_line()
    child.read_line()
    outcome: list[BaseException] = []
    reading = threading.Event()

    def read() -> None:
        reading.set()
        try:
            child.read_line()
        except BaseException as error:  # noqa: BLE001 - recorded for assertion
            outcome.append(error)

    reader = threading.Thread(target=read)
    reader.start()
    assert reading.wait(timeout=5.0)
    child.write_line(b"hang\n")
    # Let the read genuinely block, then force-close from this thread —
    # the exact watchdog arrangement the adapter's abort deadline drives.
    time.sleep(0.2)
    child.close(force=True)
    reader.join(timeout=_OS_WAIT_TIMEOUT_S)
    assert not reader.is_alive()
    assert len(outcome) == 1
    assert isinstance(outcome[0], JsonlChildClosedError)
    _wait_for_exit(pid)


#: Flood child: streams newline-free bytes forever — a hostile subject
#: probing the reader's memory bound (adversarial review 2026-07-24, R1).
_FLOOD_CHILD = """\
import sys

chunk = b"a" * 65536
while True:
    sys.stdout.buffer.write(chunk)
    sys.stdout.buffer.flush()
"""


#: Maximal-line child: one conforming line of exactly the framed ceiling
#: (body of MAXBYTES bytes plus LF) and the next message, emitted as one
#: single write so the tail bytes are adjacent in the pipe when the parent
#: drains the LF — the coalescing the regression test exists to force is
#: then deterministic, not an OS scheduling race (re-review finding).
#: Then a hang so the pipe stays open.
_MAXIMAL_LINE_CHILD = """\
import sys
import time

sys.stdout.buffer.write(b"a" * MAXBYTES + b"\\nnext\\n")
sys.stdout.buffer.flush()
time.sleep(600)
"""


def test_read_line_bounds_a_newline_free_flood_at_the_protocol_line_ceiling() -> None:
    """A subject streaming bytes without LF cannot grow the buffer unboundedly.

    The binding must stop accumulating once the LF-free buffer exceeds
    the ``termverify.control/v1`` framed-line ceiling and hand the
    oversized buffer to the caller, whose ``parse_message`` rejects it —
    the existing peer-malformed path. The deadline bounds time; this
    bounds memory. The read runs on a joined helper thread so a
    regression fails this test within the wait budget instead of hanging
    the CI job with unbounded memory.
    """
    with _reaped(_spawn(_FLOOD_CHILD)) as child:
        outcome: list[bytes | BaseException] = []

        def _read() -> None:
            try:
                outcome.append(child.read_line())
            except BaseException as error:  # noqa: BLE001 - diagnostic capture
                outcome.append(error)

        reader = threading.Thread(target=_read, daemon=True)
        reader.start()
        reader.join(timeout=_OS_WAIT_TIMEOUT_S)
        assert not reader.is_alive(), (
            "read_line did not bound the newline-free flood within the budget"
        )
        assert outcome and isinstance(outcome[0], bytes), (
            f"read_line raised instead of returning the bounded line: {outcome!r}"
        )
        line = outcome[0]
        assert len(line) > _MAX_LINE_BYTES
        assert len(line) <= _MAX_LINE_BYTES + 1 + 65536
        assert not line.endswith(b"\n")
        with pytest.raises(ControlProtocolError) as excinfo:
            parse_message(line)
        assert "exceed the v1 limit" in str(excinfo.value)


def test_read_line_frames_a_maximal_line_followed_by_more_data_exactly() -> None:
    """Regression guard (adversarial re-review of this slice): the memory
    bound must not fire while an LF is buffered.

    A conforming subject may send a maximal framed line (body exactly at
    the ceiling, then LF) with the next message coalescing into the same
    buffered reads; the binding must frame both lines exactly rather
    than merging them into a rejected pseudo-line.
    """
    script = _MAXIMAL_LINE_CHILD.replace("MAXBYTES", str(_MAX_LINE_BYTES))
    with _reaped(_spawn(script)) as child:
        first = child.read_line()
        assert len(first) == _MAX_LINE_BYTES + 1
        assert first == b"a" * _MAX_LINE_BYTES + b"\n"
        assert child.read_line() == b"next\n"


#: Job-object containment is a Windows-only mechanism, so its result-check
#: evidence (adversarial review 2026-07-24, R3) is Windows-only too. Both
#: tests force the native failure leg by replacing the module's bound
#: ``_kernel32`` function with one that returns the BOOL failure value;
#: the patch target is written as an import path because the symbol does
#: not exist — and would not type-check — on the POSIX legs.
_windows_only = pytest.mark.skipif(
    sys.platform != "win32",
    reason="job-object containment is a Windows-only mechanism",
)

#: Windows refuses to assign an already-exited process to a job object
#: with this error; the spawn path must read it as "nothing left to
#: contain" rather than as a containment failure.
_ERROR_ACCESS_DENIED = 5


def _module_symbol(name: str) -> Any:
    """Fetch a Windows-only module global without a typed reference.

    The containment helpers exist only inside ``_jsonl_pipe``'s
    ``sys.platform == "win32"`` block, so naming one directly would fail
    type checking on the POSIX legs even inside a skipped test.
    """
    from termverify import _jsonl_pipe

    return _jsonl_pipe.__dict__[name]


def _patch_assignment_into_the_window(
    monkeypatch: pytest.MonkeyPatch, refused: list[OSError]
) -> None:
    """Enter the assignment window deterministically, not by racing it.

    The **real** ``AssignProcessToJobObject`` still runs, unchanged — only
    later, after the child's own exit has been observed through its
    process handle. So the failure driven is the one Windows actually
    produces for an exited process, and any refusal it raises is recorded
    in ``refused`` for the caller to assert.
    """
    real_assign = _module_symbol("_assign_to_job")
    wait_for_handle = _module_symbol("_wait_for_handle")

    def _assign_after_the_child_exits(job: int, process_handle: int) -> None:
        assert wait_for_handle(process_handle, int(_OS_WAIT_TIMEOUT_S * 1000)), (
            "the fast child did not exit within the wait budget"
        )
        try:
            real_assign(job, process_handle)
        except OSError as error:
            refused.append(error)
            raise

    monkeypatch.setattr(
        "termverify._jsonl_pipe._assign_to_job", _assign_after_the_child_exits
    )


def _kill_pid(pid: int) -> None:
    """Cleanup arrangement, never evidence: end a deliberately orphaned pid."""
    with suppress(OSError):
        os.kill(pid, 9)


@_windows_only
def test_spawn_fails_closed_when_job_assignment_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed ``AssignProcessToJobObject`` must not hand out a session.

    The BOOL return is the only signal Windows gives that assignment did
    not happen. Discarding it would return a binding whose spawn
    docstring promises containment while the child in fact runs outside
    the job — a forced close would then terminate an empty job and leave
    the tree alive. The spawn must instead fail closed: terminate the
    child, release the handles, and raise.
    """
    import ctypes

    def _refuse_assignment(job: int, process_handle: int) -> int:
        # Report a real Windows error code so the wrapper's message is
        # asserted against something meaningful: the wrapper must relay
        # `GetLastError`, and one reporting a fabricated code would fail
        # the assertion below.
        ctypes.set_last_error(_ERROR_ACCESS_DENIED)  # type: ignore[attr-defined,unused-ignore]
        return 0

    monkeypatch.setattr(
        "termverify._jsonl_pipe._kernel32.AssignProcessToJobObject",
        _refuse_assignment,
    )
    with pytest.raises(OSError) as failure:
        _spawn()
    contained = re.search(
        r"failed to contain pipe child (\d+) in a job object", str(failure.value)
    )
    assert contained is not None, f"unexpected spawn failure: {failure.value}"
    cause = failure.value.__cause__
    assert isinstance(cause, OSError)
    assert str(cause) == (f"AssignProcessToJobObject failed: {_ERROR_ACCESS_DENIED}")
    # The spawned process named in the failure is terminated, not merely
    # unreferenced. On this toolchain that pid is the venv launcher rather
    # than the interpreter itself, so this is evidence that the spawn
    # released what it created — the surviving-descendant boundary is the
    # disclosed assignment window, not something this leg can close.
    _wait_for_exit(int(contained.group(1)))


@_windows_only
def test_forced_close_reports_a_failed_job_termination(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed ``TerminateJobObject`` must be reported, not swallowed.

    Containment itself still holds — the job handle the teardown releases
    in its ``finally`` carries kill-on-close, so the tree dies either
    way. What the check adds is truthfulness: a caller learns the
    graceful termination failed instead of reading a silent success from
    a close that only worked by accident.
    """
    child = _spawn(_TREE_CHILD)
    pid = int(child.read_line().split(b":", 1)[1])
    grandchild_pid = int(child.read_line().split(b":", 1)[1])
    assert _pid_alive(grandchild_pid)
    monkeypatch.setattr(
        "termverify._jsonl_pipe._kernel32.TerminateJobObject",
        lambda job, exit_code: 0,
    )
    with pytest.raises(OSError, match="TerminateJobObject failed"):
        child.close(force=True)
    _wait_for_exit(pid)
    _wait_for_exit(grandchild_pid)
    assert not _pid_alive(grandchild_pid)


#: Fast child: exits immediately with a distinctive code, so the spawn
#: path's job assignment lands on an already-exited process.
_FAST_EXIT_CHILD = """\
import sys

sys.exit(7)
"""


@_windows_only
def test_spawn_survives_a_child_that_exits_inside_the_assignment_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A subject that exits before assignment is not a containment failure.

    Windows refuses ``AssignProcessToJobObject`` on an exited process with
    ERROR_ACCESS_DENIED. Reading that as "containment failed" would fail
    the spawn of a perfectly legitimate fast subject — non-deterministically,
    since it depends on whether the child wins the race — and would report
    a contained-session failure for a child that needs no containment
    (adversarial review of PR #211, finding 3).

    The window is entered deterministically rather than raced: the real
    assignment runs, unchanged, after the child's real exit is observed
    through its own process handle, so the failure this test drives is the
    one Windows actually produces.
    """
    refused: list[OSError] = []
    _patch_assignment_into_the_window(monkeypatch, refused)

    with _reaped(_spawn(_FAST_EXIT_CHILD)) as child:
        with pytest.raises(JsonlEndOfStreamError):
            child.read_line()
        child.close(force=False)
        assert child.exit_status == 7

    # The disclosed cause is pinned by the OS, not assumed: the real
    # assignment refused an exited process with ERROR_ACCESS_DENIED.
    assert refused, "the real assignment did not run inside the window"
    assert f"AssignProcessToJobObject failed: {_ERROR_ACCESS_DENIED}" in str(refused[0])


#: Orphaning child: starts a grandchild that holds none of the child's
#: pipes, reports its pid, then exits at once — so the spawn's assignment
#: lands on a corpse and the grandchild is outside the empty job.
_ORPHANING_CHILD = """\
import subprocess
import sys

grandchild = subprocess.Popen(
    [sys.executable, "-c", "import time; time.sleep(600)"],
    stdin=subprocess.DEVNULL,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)
sys.stdout.buffer.write(b"TV_GRANDCHILD:" + str(grandchild.pid).encode() + b"\\n")
sys.stdout.buffer.flush()
sys.exit(9)
"""


@_windows_only
def test_a_forced_close_after_the_window_leg_claims_nothing_it_cannot_do(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The window leg's binding must not pretend to contain anything.

    A binding handed out for an already-exited child owns a job that stays
    **permanently empty**: Windows job membership comes only from
    assignment or from inheritance through a member, and this child was
    never assigned. A forced close therefore terminates nothing — it can
    only report the child's honest exit record (adversarial review round 2
    of PR #214, finding 2).

    What this test does **not** assert is that the child's descendant
    survives, even though it is uncontained by us: on the toolchain this
    suite runs under, the launcher's own outer job sweeps it, so a
    survivor is not observable here. That is precisely why the limit is
    disclosed in :meth:`spawn` rather than asserted — the containment that
    covers this case is somebody else's, and the binding must not claim
    credit for it.
    """
    _patch_assignment_into_the_window(monkeypatch, [])

    child = _spawn(_ORPHANING_CHILD)
    grandchild_pid = int(child.read_line().split(b":", 1)[1])
    try:
        with pytest.raises(JsonlEndOfStreamError):
            child.read_line()
        # A forced close of a binding whose job is empty is honest and
        # quiet: the real exit record, no fabricated termination, no error.
        child.close(force=True)
        assert child.exit_status == 9
    finally:
        _kill_pid(grandchild_pid)  # cleanup, not evidence


@_windows_only
def test_forced_close_with_a_read_in_flight_sweeps_the_tree_and_returns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed job termination must not strand the teardown mid-flight.

    This is the watchdog shape: the adapter force-closes from its
    deadline timer while the main thread is blocked in ``read_line``
    (adversarial review of PR #211, finding 1). A failed
    ``TerminateJobObject`` leaves the child alive, so the blocked reader
    keeps the pipe's lock; if the teardown reached ``_close_pipes``
    first, its ``detach`` would wait on that lock forever, the job handle
    would never be released, kill-on-close would never fire, and the
    whole tree would leak while ``close`` never returned.

    Releasing containment before touching the pipes is what makes the
    documented behavior true for a contained tree: every job member is
    swept, the sweep unblocks the blocked read, and the caller still
    learns the graceful termination failed. A write-end holder outside the
    job is a different, disclosed case (#213).
    """
    child = _spawn(_TREE_CHILD)
    pid = int(child.read_line().split(b":", 1)[1])
    grandchild_pid = int(child.read_line().split(b":", 1)[1])
    try:
        assert _pid_alive(grandchild_pid)

        reading = threading.Event()
        outcome: list[BaseException | bytes] = []

        def _read() -> None:
            reading.set()
            try:
                outcome.append(child.read_line())
            except BaseException as error:  # noqa: BLE001 - diagnostic capture
                outcome.append(error)

        reader = threading.Thread(target=_read, daemon=True)
        reader.start()
        assert reading.wait(timeout=_OS_WAIT_TIMEOUT_S)
        # Best-effort arrangement, not evidence: the tree child is silent
        # after its banner, so this gives the reader a moment to reach the
        # read syscall. If it has not blocked yet the assertions below all
        # still hold — the test simply stops exercising the deadlock, which
        # is why the reverted implementation is what proves it does.
        time.sleep(0.2)

        monkeypatch.setattr(
            "termverify._jsonl_pipe._kernel32.TerminateJobObject",
            lambda job, exit_code: 0,
        )

        closing: list[BaseException | None] = []

        def _close() -> None:
            try:
                child.close(force=True)
                closing.append(None)
            except BaseException as error:  # noqa: BLE001 - diagnostic capture
                closing.append(error)

        closer = threading.Thread(target=_close, daemon=True)
        closer.start()
        closer.join(timeout=_OS_WAIT_TIMEOUT_S)
        assert not closer.is_alive(), "close deadlocked with a read in flight"
        assert closing and isinstance(closing[0], OSError), (
            f"close did not report the failed termination: {closing!r}"
        )
        assert "TerminateJobObject failed" in str(closing[0])
        # The raise is the result: no exit record is fabricated for a
        # teardown whose graceful termination the binding cannot vouch for.
        assert child.exit_status is None

        reader.join(timeout=_OS_WAIT_TIMEOUT_S)
        assert not reader.is_alive(), "the in-flight read was never unblocked"
        _wait_for_exit(pid)
        _wait_for_exit(grandchild_pid)
        assert not _pid_alive(grandchild_pid)
    finally:
        # Cleanup, not evidence: a regression must not leak the tree.
        _kill_pid(grandchild_pid)
        _kill_pid(pid)


_posix_only = pytest.mark.skipif(
    sys.platform == "win32",
    reason="process-group containment and its escape are POSIX mechanisms",
)


@_posix_only
def test_a_forced_close_wakes_a_read_blocked_on_an_escaped_descendants_pipe() -> None:
    """A read no containment can unblock must still end (R4, #196, #213).

    The subject starts a grandchild in its **own session**, holding the
    inherited stdout write end, and then exits. `killpg` reaches a process
    group, not another session, so the write end outlives the whole
    contained tree: the reader blocked on stdout never observes
    end-of-stream, and no containment this binding owns can make it.

    Measured before the fix, on all three Ubuntu legs (run 30183983506):
    `close(force=True)` **returned cleanly** and the reader was still
    blocked 30 seconds later, when the join gave up — "the blocked read
    was never woken". (Still blocked at the join is what the log supports;
    the thread is a daemon the run then abandoned.) So
    the observed defect is not a stuck teardown but a worse-behaved one:
    close reported success, closed the stdout descriptor, and left a
    thread blocked on that descriptor's number, free for the next `open`
    in the process to reuse.

    The `_close_pipes`-blocks-inside-a-`finally` shape that #213 and #217
    describe was *not* reached here, because the immediate child had
    already exited. It is not asserted by this test, and this docstring
    does not claim it.

    The remedy is not containment — the orphan is disclosed as unreapable —
    but interruption the binding owns outright: the reader waits on the
    child's stdout **and** a self-pipe, and any close writes that pipe.
    """
    child = _spawn(_ESCAPING_CHILD)
    grandchild_pid = 0
    try:
        first = child.read_line()
        grandchild_pid = int(first.decode().split(":", 1)[1])
        assert _pid_alive(grandchild_pid)

        # A read that can never complete: the immediate child is gone, so
        # nothing will write again, and the grandchild holds the write end
        # open so end-of-stream never arrives either.
        read_error: list[BaseException | None] = []
        reader = threading.Thread(
            target=lambda: read_error.append(_call_capturing(child.read_line)),
            daemon=True,
        )
        reader.start()
        time.sleep(_READ_ARRIVAL_S)

        closing: list[BaseException | None] = []
        closer = threading.Thread(
            target=lambda: closing.append(
                _call_capturing(lambda: child.close(force=True))
            ),
            daemon=True,
        )
        closer.start()
        closer.join(timeout=_OS_WAIT_TIMEOUT_S)
        assert not closer.is_alive(), (
            "close never returned: it is blocked behind a read that no"
            " containment can unblock"
        )
        assert closing == [None], f"close failed: {closing!r}"

        reader.join(timeout=_OS_WAIT_TIMEOUT_S)
        assert not reader.is_alive(), "the blocked read was never woken"
        assert isinstance(read_error[0], JsonlChildClosedError), (
            "an interrupted read must surface as closed, never as"
            f" end-of-stream: {read_error!r}"
        )
    finally:
        # Cleanup, not evidence: the escaped grandchild is exactly the
        # survivor this slice discloses as unreapable, so the test reaps it.
        if grandchild_pid:
            _kill_pid(grandchild_pid)


def test_write_line_delivers_a_maximal_line_byte_exact() -> None:
    """A line far past the pipe buffer must arrive whole, and unreordered.

    On POSIX this is the only test that exercises `_write_all`'s
    partial-write loop: a pipe buffer is 64 KiB or less, so a line this
    size cannot be written in one `os.write` and the loop must advance the
    memoryview correctly. A loop that dropped or repeated a slice would
    corrupt the wire silently — the failure mode a hang at least announces
    (adversarial review, finding M4).
    """
    payload = bytes(_MAX_LINE_BYTES - 32)
    body = payload.translate(bytes.maketrans(b"\x00", b"z"))
    child = _spawn(_ECHO_CHILD)
    with _reaped(child):
        for _ in range(3):
            child.read_line()
        child.write_line(body + b"\n")
        echoed = child.read_line()
    assert echoed == b"TV_ECHO:" + body + b"\n"


@_posix_only
def test_a_forced_close_wakes_a_write_blocked_on_a_child_that_never_reads() -> None:
    """The wake-up covers both directions, not only the read.

    A subject that stops draining its stdin fills the pipe buffer, and a
    write with nowhere to go blocks. Containment can end that too — by
    killing the child — but only when the write end's fate is the child's;
    the binding's own interruption does not depend on that, and it is what
    lets the adapter's abort deadline classify a stuck write.
    """
    child = _spawn(_ECHO_CHILD)
    try:
        for _ in range(3):
            child.read_line()
        # Stop the child from reading, then write far more than any pipe
        # buffer can hold: the write cannot complete until it is woken.
        child.write_line(b"hang\n")
        write_error: list[BaseException | None] = []
        flood = bytes(_MAX_LINE_BYTES) + b"\n"
        writer = threading.Thread(
            target=lambda: write_error.append(
                _call_capturing(lambda: child.write_line(flood))
            ),
            daemon=True,
        )
        writer.start()
        time.sleep(_READ_ARRIVAL_S)

        # On its own thread with a joined timeout, like the read test: a
        # regression that re-wedges the teardown must fail this test, not
        # hang the CI job (no `pytest-timeout` is installed).
        closing: list[BaseException | None] = []
        closer = threading.Thread(
            target=lambda: closing.append(
                _call_capturing(lambda: child.close(force=True))
            ),
            daemon=True,
        )
        closer.start()
        closer.join(timeout=_OS_WAIT_TIMEOUT_S)
        assert not closer.is_alive(), "close never returned with a write in flight"
        assert closing == [None], f"close failed: {closing!r}"

        writer.join(timeout=_OS_WAIT_TIMEOUT_S)
        assert not writer.is_alive(), "the blocked write was never woken"
        # The *type* is the assertion, not merely that something raised.
        # "Some exception" would also accept the `OSError(EBADF)` a write
        # gets when the teardown frees the descriptor underneath it —
        # which is exactly the untracked-write defect this arrangement
        # exists to catch, so accepting it would pin nothing (round 2, J3).
        assert isinstance(write_error[0], JsonlChildClosedError), (
            "an interrupted write must surface as a closed binding, not as"
            f" a descriptor error: {write_error!r}"
        )
    finally:
        child.close(force=True)
