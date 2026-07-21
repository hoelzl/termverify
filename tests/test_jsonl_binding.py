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

The fixture children are minimal ``python -c`` scripts in the ConPTY
integration pattern: they read stdin as bytes, decode UTF-8, and split on
newlines — the ordinary subject-side obligation for this transport, with
no console-input caveats (issue #169 does not apply to pipes).
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from termverify._jsonl_pipe import FORCED_TERMINATION_SIGNAL, PipeJsonlChild
from termverify.jsonl import JsonlChildClosedError, JsonlEndOfStreamError

_OS_WAIT_TIMEOUT_S = 30.0
_POLL_INTERVAL_S = 0.02

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
