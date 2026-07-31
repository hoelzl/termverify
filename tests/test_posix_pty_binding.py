"""Native ownership, line discipline, geometry, and teardown evidence (POSIX).

Slice 1 of the vertical accepted in
``docs/agent/design/posix-pty-adapter-and-examples-vertical-boundary.md``
(issue #267). The binding's job is to make a real POSIX pseudoterminal
answer the same child surface the ConPTY binding answers, so the adapter
above the binding port needs no platform branch.

Two behaviors the design deliberately refused to predict are **measured**
here rather than assumed, because a plausible-sounding wrong sentence about
either is the classic way a pty binding ships a defect:

- the line discipline the child actually inherits, and
- what a master descriptor reports once its last slave is gone.

A third is measured because it is the whole reason the binding spawns
through a trampoline instead of ``preexec_fn``: the child really does get a
controlling terminal.

The probe tests run everywhere; everything else is Linux-only evidence, per
the boundary's decision 2 (claim only what CI verifies).
"""

from __future__ import annotations

import os
import sys
import threading
import time

import pytest

from termverify import _posix_pty
from termverify._posix_pty import (
    FORCED_TERMINATION_SIGNAL,
    PosixPtyChild,
    PosixPtyClosedError,
    PosixPtyConcurrentIOError,
    PosixPtyEndOfStreamError,
)

_LINUX_ONLY = pytest.mark.skipif(
    not sys.platform.startswith("linux"),
    reason="POSIX PTY binding evidence (claimed on Linux only, decision 2)",
)

_INITIAL_ROWS = 24
_INITIAL_COLUMNS = 80
_TIMEOUT_S = 20.0


def _spawn(
    script: str, *, rows: int = _INITIAL_ROWS, columns: int = _INITIAL_COLUMNS
) -> PosixPtyChild:
    return PosixPtyChild.spawn(
        [sys.executable, "-I", "-u", "-c", script], rows=rows, columns=columns
    )


def _read_until(
    child: PosixPtyChild, needle: str, *, timeout: float = _TIMEOUT_S
) -> str:
    """Collect decoded output until ``needle`` appears, or fail loudly."""
    collected = ""
    deadline = time.monotonic() + timeout
    while needle not in collected:
        assert time.monotonic() < deadline, (
            f"timed out waiting for {needle!r}; collected so far: {collected!r}"
        )
        collected += child.read()
    return collected


# --------------------------------------------------------------------------
# Probe — runs on every platform
# --------------------------------------------------------------------------


def test_the_probe_reports_support_only_on_linux() -> None:
    """The claim is Linux; every other platform fails closed.

    Decision 2 of the boundary: the probe answers before any spawn, and a
    platform the CI matrix does not verify reports unsupported rather than
    running unverified. macOS is deliberately included in "unsupported" —
    it is not that a pty cannot work there, it is that nothing here has
    ever run there.
    """
    assert _posix_pty.is_supported() is sys.platform.startswith("linux")


def test_spawn_fails_closed_where_the_probe_says_unsupported() -> None:
    if _posix_pty.is_supported():
        pytest.skip("fail-closed spawn is observable only off the claimed platform")
    with pytest.raises(_posix_pty.PosixPtyUnsupportedError):
        PosixPtyChild.spawn([sys.executable, "-c", "pass"], rows=24, columns=80)


# --------------------------------------------------------------------------
# The measurements the design refused to predict
# --------------------------------------------------------------------------

#: Reports the terminal state the child actually inherited, then waits.
#: The flag *names* are resolved in the child, against the child's own
#: ``termios``: asserting them in the parent would mean importing a
#: Unix-only module into a test module that must import on Windows, and
#: would ask the parent what the child sees instead of asking the child.
_TERMIOS_CHILD = """
import os, sys, termios
a = termios.tcgetattr(0)
iflag, oflag, lflag = a[0], a[1], a[3]
for name, flag, value in (
    ("OPOST", "oflag", termios.OPOST),
    ("ONLCR", "oflag", termios.ONLCR),
    ("ECHO", "lflag", termios.ECHO),
    ("ICANON", "lflag", termios.ICANON),
    ("ISIG", "lflag", termios.ISIG),
    ("ICRNL", "iflag", termios.ICRNL),
):
    print(name, bool({"iflag": iflag, "oflag": oflag, "lflag": lflag}[flag] & value))
print("CTTY", os.ttyname(0))
print("SID", os.getsid(0) == os.getpid())
print("READY")
sys.stdin.readline()
"""


@_LINUX_ONLY
def test_the_child_inherits_the_line_discipline_the_binding_set() -> None:
    """Measured, not assumed — and it is deliberately *not* raw mode.

    Design rule 5 requires the discipline to be explicit and recorded. It
    does not require raw: a subject under TermVerify should see the
    terminal a person's subject sees, which post-processes output and
    echoes input. A subject that wants raw calls ``tcsetattr`` itself and
    wins, exactly as on a real terminal.
    """
    child = _spawn(_TERMIOS_CHILD)
    try:
        output = _read_until(child, "READY")
        for flag, why in (
            ("OPOST", "output post-processing must be on"),
            ("ONLCR", "newline translation must be on"),
            ("ECHO", "a conventional terminal echoes"),
            ("ICANON", "a conventional terminal is canonical"),
            ("ISIG", "a conventional terminal generates signals"),
            ("ICRNL", "a conventional terminal maps CR to NL"),
        ):
            assert f"{flag} True" in output, f"{why}; child reported: {output!r}"
    finally:
        child.close(force=True)


@_LINUX_ONLY
def test_configuring_the_line_discipline_is_idempotent_and_measured() -> None:
    """What a fresh pty hands back, recorded instead of predicted.

    The boundary design refused to state this, and the issue asked for it
    to be established on the legs that run. Whatever the default is, the
    binding's configured state must hold afterwards — that is the contract
    ``_configure_line_discipline`` exists to create, and this is the test
    that would fail if a future kernel default silently changed the
    evidence a subject produces.
    """
    master_fd, slave_fd = os.openpty()  # type: ignore[attr-defined,unused-ignore]
    try:
        inherited = _posix_pty.terminal_flags(slave_fd)
        _posix_pty._configure_line_discipline(slave_fd)
        once = _posix_pty.terminal_flags(slave_fd)
        _posix_pty._configure_line_discipline(slave_fd)
        twice = _posix_pty.terminal_flags(slave_fd)
    finally:
        os.close(master_fd)
        os.close(slave_fd)
    # The inherited default is *recorded*, not asserted: pinning it would
    # pin the kernel's choice rather than the binding's contract, and the
    # design refused to predict it. It rides in the failure messages so a
    # future divergence is visible at the point it breaks something.
    assert once == twice, (
        f"configuring the line discipline is not idempotent:"
        f" inherited={inherited} once={once} twice={twice}"
    )
    # What the flags *mean* is asserted where it is observable as
    # behavior — by the child, in the test above. This one owns the two
    # properties that test cannot see: the measurement, and stability
    # under reapplication.


@_LINUX_ONLY
def test_the_child_is_a_session_leader_with_a_controlling_terminal() -> None:
    """The reason the binding spawns through a trampoline.

    Without a controlling terminal there is no foreground process group,
    so the kernel delivers no ``SIGWINCH`` and the subject cannot open
    ``/dev/tty``. This is the assertion that would fail if the trampoline
    were replaced by a plain spawn.
    """
    child = _spawn(_TERMIOS_CHILD)
    try:
        output = _read_until(child, "READY")
        assert "SID True" in output, f"child is not a session leader: {output!r}"
        assert "CTTY /dev/pts/" in output, f"child has no pty on fd 0: {output!r}"
    finally:
        child.close(force=True)


@_LINUX_ONLY
def test_end_of_stream_is_reported_once_the_child_and_its_slave_are_gone() -> None:
    """Measured: Linux reports ``EIO``, not an empty read.

    The binding normalizes whatever the platform does into its own
    end-of-stream signal, and the exit record is captured with it — the
    child has exited by definition at that point, so the bounded wait is a
    reaping delay and never a liveness guess.
    """
    child = _spawn("print('BYE')")
    try:
        _read_until(child, "BYE")
        with pytest.raises(PosixPtyEndOfStreamError):
            for _ in range(100):
                child.read()
        assert child.exit_status == 0
    finally:
        child.close(force=True)


# --------------------------------------------------------------------------
# Geometry
# --------------------------------------------------------------------------

#: Reports its window size on demand: once at startup, then once per line
#: of input. Deliberately not driven by ``SIGWINCH`` — proving the geometry
#: changed and proving the signal arrives are different claims, and the
#: signal is issue #269's evidence.
_GEOMETRY_CHILD = """
import os, sys
def report():
    size = os.get_terminal_size(0)
    print("SIZE", size.lines, size.columns)
for line in iter(sys.stdin.readline, ''):
    report()
"""


@_LINUX_ONLY
def test_the_child_observes_the_creation_geometry() -> None:
    child = _spawn(_GEOMETRY_CHILD, rows=30, columns=100)
    try:
        child.write("go\n")
        output = _read_until(child, "SIZE")
        assert "SIZE 30 100" in output, output
    finally:
        child.close(force=True)


@_LINUX_ONLY
def test_the_child_observes_a_resized_geometry() -> None:
    child = _spawn(_GEOMETRY_CHILD, rows=30, columns=100)
    try:
        child.write("go\n")
        _read_until(child, "SIZE 30 100")
        child.resize(rows=12, columns=40)
        child.write("go\n")
        assert "SIZE 12 40" in _read_until(child, "SIZE 12 40")
    finally:
        child.close(force=True)


@_LINUX_ONLY
def test_the_kernel_applies_a_geometry_the_windows_console_would_substitute() -> None:
    """The POSIX band is wider than ConPTY's, and this measures it.

    Issue #228 recorded that the Windows console silently substitutes
    geometries outside its own band, so its receipt claims more than it
    delivers. The claim here is only what this test observes.
    """
    child = _spawn(_GEOMETRY_CHILD, rows=200, columns=500)
    try:
        child.write("go\n")
        assert "SIZE 200 500" in _read_until(child, "SIZE")
    finally:
        child.close(force=True)


# --------------------------------------------------------------------------
# I/O discipline and teardown
# --------------------------------------------------------------------------


@_LINUX_ONLY
def test_a_second_concurrent_read_wears_its_own_error() -> None:
    """A harness defect never wears a subject failure code (issue #261)."""
    child = _spawn("import sys; sys.stdin.readline()")
    started = threading.Event()
    failures: list[BaseException] = []

    def blocked_read() -> None:
        started.set()
        try:
            child.read()
        except BaseException as error:  # noqa: BLE001 - recorded for the assert
            failures.append(error)

    reader = threading.Thread(target=blocked_read, daemon=True)
    reader.start()
    assert started.wait(_TIMEOUT_S)
    try:
        # The blocked read is in flight; the second one must be refused
        # rather than joining it on the descriptor.
        deadline = time.monotonic() + _TIMEOUT_S
        while True:
            try:
                child.read()
            except PosixPtyConcurrentIOError:
                break
            except PosixPtyEndOfStreamError:  # pragma: no cover - defensive
                pytest.fail("the child ended before the concurrency was observed")
            assert time.monotonic() < deadline, "never observed an in-flight read"
    finally:
        child.close(force=True)
    reader.join(_TIMEOUT_S)
    assert not reader.is_alive()
    assert failures and isinstance(failures[0], PosixPtyClosedError)


@_LINUX_ONLY
def test_a_blocked_read_is_woken_by_a_forced_close() -> None:
    """The self-pipe, not containment, is what ends a blocked read.

    A close must not depend on reaching whoever holds the other end — the
    finding (R4) that shaped the JSONL binding's POSIX path.
    """
    child = _spawn("import sys; sys.stdin.readline()")
    woken = threading.Event()
    failures: list[BaseException] = []

    def blocked_read() -> None:
        try:
            child.read()
        except BaseException as error:  # noqa: BLE001 - recorded for the assert
            failures.append(error)
        finally:
            woken.set()

    reader = threading.Thread(target=blocked_read, daemon=True)
    reader.start()
    time.sleep(0.2)  # arrangement, not evidence: let the read reach `poll`
    child.close(force=True)
    assert woken.wait(_TIMEOUT_S), "the blocked read was never woken"
    assert failures and isinstance(failures[0], PosixPtyClosedError)


@_LINUX_ONLY
def test_a_forced_close_kills_the_session_and_records_the_real_exit() -> None:
    child = _spawn("import time; time.sleep(300)")
    pid = child.pid
    child.close(force=True)
    assert child.exit_status == -FORCED_TERMINATION_SIGNAL
    with pytest.raises(OSError):
        os.kill(pid, 0)


@_LINUX_ONLY
def test_a_release_only_close_of_a_live_child_is_refused() -> None:
    """Silently abandoning a live pty child has no honest reading."""
    child = _spawn("import time; time.sleep(300)")
    try:
        with pytest.raises(PosixPtyClosedError):
            child.close(force=False)
        assert child.is_alive()
    finally:
        child.close(force=True)


@_LINUX_ONLY
def test_every_operation_after_close_reports_the_closed_binding() -> None:
    child = _spawn("import time; time.sleep(300)")
    child.close(force=True)
    for operation in (
        lambda: child.read(),
        lambda: child.write("x"),
        lambda: child.resize(rows=10, columns=10),
    ):
        with pytest.raises(PosixPtyClosedError):
            operation()
    child.close(force=True)  # idempotent


@_LINUX_ONLY
def test_a_missing_command_fails_in_the_parent_where_it_can_be_named() -> None:
    """The trampoline cannot report a missing command usefully.

    Resolution happens in the parent precisely so the failure names the
    command instead of surfacing as an opaque interpreter exit.
    """
    with pytest.raises(FileNotFoundError, match="tv-no-such-command"):
        PosixPtyChild.spawn(
            ["tv-no-such-command"], rows=_INITIAL_ROWS, columns=_INITIAL_COLUMNS
        )


@_LINUX_ONLY
def test_the_environment_overlay_and_cwd_compose_inside_the_binding() -> None:
    """The ratcheted adapter above never reads ambient state itself."""
    child = PosixPtyChild.spawn(
        [
            sys.executable,
            "-I",
            "-u",
            "-c",
            "import os; print('TV', os.environ.get('TV_MARKER'), os.getcwd())",
        ],
        rows=_INITIAL_ROWS,
        columns=_INITIAL_COLUMNS,
        env_overlay={"TV_MARKER": "overlaid"},
        cwd="/tmp",
    )
    try:
        output = _read_until(child, "TV ")
        assert "TV overlaid /tmp" in output, output
    finally:
        child.close(force=True)
