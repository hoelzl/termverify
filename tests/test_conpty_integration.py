"""Windows integration evidence for the public ConPTY adapter (slice 4).

These tests promote the public claims of verification-plan items 5-8 of the
accepted terminal-adapter decision — as scoped by the ConPTY adapter design
(`docs/agent/design/conpty-adapter-design.md`) — into repeatable
Windows-matrix CI evidence on the real path: default ``ConptyBinding``,
native ``ConptyChild``, and the real ``VtScreenNormalizer``.

- **Marker passthrough:** ConPTY relays the private-use OSC readiness marker
  verbatim through the output pipe, so the provisional OSC default holds and
  the design needs no printable-default amendment. A host-configured
  printable marker works identically and appears in frames.
- **Cooperative fixture child:** a subject that honors the design's
  cooperation contract — an explicit readiness marker after startup and
  after processing each input, including a detected resize. A resize
  delivers no bytes to the child's stdin, so the fixture watches the
  terminal size actively; that is subject cooperation by design, exactly
  the obligation the marker protocol places on verified subjects.
- **End-to-end epochs (items 5-8):** start-to-readiness with cursor and
  frame evidence, a text epoch, a resize epoch whose child-observed
  dimensions appear in the observation, subject exit via native
  end-of-stream with the observed exit record, forced stop with the
  forced-termination disclosure, and a deadline abort against a hanging
  subject with OS-observed teardown.
- **Normalizer coverage and replay:** the real output ConPTY emits for
  these sessions normalizes without a fail-closed error, and replaying the
  normalizer over the retained raw ``terminal.output`` chunks reproduces
  every frame — the replay rule that makes frames trustworthy evidence.

OS-level observations reuse the process-handle helpers from the binding
evidence module; asserted evidence is adapter results, raw chunks, frames,
and OS exit codes — never helper-thread or wall-clock state.

The cooperation-tier section at the end of this module is slice 3 of the
accepted cooperation-tier design
(`docs/agent/design/cooperation-tier-constraint-ports.md`): the first fully
successful verified terminal run — cooperation ports with a host-owned
sandbox, delivered-tier receipts, a subject echoing every delivered
variable and its working directory into frames, replay identity, and the
forced-stop/deadline paths re-exercised under those ports.
"""

from __future__ import annotations

import os
import re
import sys
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Final, cast

import pytest

# Shared Windows evidence fixtures: the OS process-handle helpers prove
# teardown outside the binding, and the enforcing constraint ports let a
# start negotiate fully; both are established test fixtures, deliberately
# imported rather than duplicated.
from test_conpty_binding import (
    _close_process_handle,
    _open_process_handle,
    _terminate_process,
    _wait_for_os_exit_code,
)
from test_conpty_epochs import _configuration, _EnforcingPorts

from termverify._conpty import (
    FORCED_TERMINATION_EXIT_CODE,
    ConptyChild,
    ConptyEndOfStreamError,
)
from termverify.adapter import (
    ClockConfiguration,
    EpochCompleted,
    ExitStatus,
    FilesystemConfiguration,
    ManualTime,
    NetworkConfiguration,
    Observation,
    Resize,
    RunConfiguration,
    RunFailed,
    RunFinished,
    Started,
    StartTerminated,
    StartUnsupported,
    Stop,
    TerminalConfiguration,
    TerminalResult,
    TextInput,
)
from termverify.conpty import READINESS_MARKER_DEFAULT, ConptyAdapter, ConptyBinding
from termverify.cooperation import CooperationConstraintPorts, RealDirectoryProbe
from termverify.vt import VtScreenNormalizer

_INITIAL_ROWS: Final = 24
_INITIAL_COLUMNS: Final = 80
_RESIZED_ROWS: Final = 30
_RESIZED_COLUMNS: Final = 100
_OS_WAIT_TIMEOUT_MS: Final = 30_000
#: Generous deadline for epochs that must succeed: it bounds a regression
#: instead of hanging CI and is never treated as evidence.
_SAFE_DEADLINE_MS: Final = 120_000
#: Deadline for the abort test. The start epoch under the same deadline pays
#: a measured, constant ~3.1 s ambient floor: conhost defers client output
#: while its unanswered ``CSI c`` device-attributes query times out (the
#: DA-stall disclosure in the adapter design). 20 s leaves the start epoch
#: a wide margin above that floor plus loaded-CI spawn overhead; the hanging
#: epoch itself begins after readiness and has no ambient floor, so its
#: expiry timing is not load-sensitive.
_ABORT_DEADLINE_MS: Final = 20_000

_PRINTABLE_MARKER: Final = "<<TV-READY>>"

# Cooperative fixture subject implementing the design's cooperation
# contract: one readiness marker after startup and after processing each
# input. Commands are lines; "exit" ends the process without a marker so
# the epoch ends in native end-of-stream, and "hang" never answers so only
# the abort deadline can end the epoch. A resize reaches a Windows console
# client as no stdin bytes, so the fixture detects it by watching the
# reported terminal size and answers with a marker — active cooperation,
# which is exactly what the marker protocol demands of verified subjects.
_COOPERATIVE_CHILD_TEMPLATE: Final = """\
import os
import sys
import threading
import time

MARKER = {marker!r}

lock = threading.Lock()

def emit(text):
    with lock:
        sys.stdout.write(text + MARKER)
        sys.stdout.flush()

def size():
    value = os.get_terminal_size(sys.stdout.fileno())
    return f"{{value.columns}}x{{value.lines}}"

def watch():
    last = size()
    while True:
        time.sleep(0.01)
        current = size()
        if current != last:
            last = current
            emit(f"TV_RESIZED:{{current}}\\r\\n")

threading.Thread(target=watch, daemon=True).start()
emit(f"TV_PID:{{os.getpid()}} TV_SIZE:{{size()}}\\r\\n")
for line in sys.stdin:
    command = line.strip()
    if command == "exit":
        sys.stdout.write("TV_EXIT\\r\\n")
        sys.stdout.flush()
        sys.exit(3)
    if command == "hang":
        time.sleep(600)
    emit(f"TV_ECHO:{{command}}\\r\\n")
"""

_EXIT_BEFORE_READINESS_CHILD: Final = """\
import sys

sys.stdout.write("TV_SHORT\\r\\n")
sys.stdout.flush()
sys.exit(7)
"""

_OSC_EMITTING_CHILD: Final = """\
import sys

sys.stdout.write("TV_BEFORE")
sys.stdout.flush()
sys.stdout.write({marker!r})
sys.stdout.flush()
sys.stdout.write("TV_AFTER")
sys.stdout.flush()
"""


def _argv(script: str) -> list[str]:
    return [sys.executable, "-I", "-u", "-c", script]


def _cooperative_argv(marker: str = READINESS_MARKER_DEFAULT) -> list[str]:
    return _argv(_COOPERATIVE_CHILD_TEMPLATE.format(marker=marker))


def _adapter(
    argv: Sequence[str],
    *,
    abort_deadline_ms: int = _SAFE_DEADLINE_MS,
    readiness_marker: str = READINESS_MARKER_DEFAULT,
) -> ConptyAdapter:
    return ConptyAdapter(
        argv,
        binding=ConptyBinding(),
        abort_deadline_ms=abort_deadline_ms,
        constraint_ports=_EnforcingPorts(),
        readiness_marker=readiness_marker,
    )


@contextmanager
def _reaped(adapter: ConptyAdapter) -> Iterator[ConptyAdapter]:
    """Cleanup arrangement, not evidence: never leak a child past a failure.

    A failed assertion mid-run would otherwise leave the fixture child
    blocked on stdin until interpreter exit. Force-closing the binding on
    the way out is a no-op for runs that already reached a terminal result,
    because every terminal result closes the binding.
    """
    try:
        yield adapter
    finally:
        child = adapter._child  # noqa: SLF001 - cleanup-only access
        if child is not None:
            child.close(force=True)


def _chunks(observation: Observation) -> list[str]:
    assert all(event.type == "terminal.output" for event in observation.events)
    return [
        cast("Mapping[str, str]", event.data)["chunk"] for event in observation.events
    ]


def _frame_text(observation: Observation) -> str:
    assert observation.frame is not None
    return "\n".join(observation.frame.lines)


def _observed_pid(observation: Observation) -> int:
    match = re.search(r"TV_PID:(\d+)", "".join(_chunks(observation)))
    assert match is not None, "the fixture child did not report its pid"
    return int(match.group(1))


def _assert_replay_reproduces(
    observations: Sequence[Observation], *, rows: int, columns: int
) -> None:
    """The design's replay rule: raw chunks -> the recorded frames.

    Feeds every observation's retained ``terminal.output`` chunks through a
    fresh normalizer, applying the resize notification exactly where the
    recorded effective dimensions change (the adapter resizes before it
    reads an epoch's output), and requires frame and cursor identity at
    every epoch boundary.
    """
    normalizer = VtScreenNormalizer(rows=rows, columns=columns)
    current = (columns, rows)
    for observation in observations:
        state = cast("Mapping[str, Mapping[str, int]]", observation.state)
        terminal = state["terminal"]
        dimensions = (terminal["columns"], terminal["rows"])
        if dimensions != current:
            normalizer.notify_resize(rows=dimensions[1], columns=dimensions[0])
            current = dimensions
        for chunk in _chunks(observation):
            normalizer.feed(chunk)
        snapshot = normalizer.snapshot()
        assert snapshot.frame == observation.frame
        assert snapshot.cursor == observation.ui.cursor
        assert snapshot.mode == observation.ui.mode


@pytest.mark.skipif(os.name != "nt", reason="Windows ConPTY integration evidence")
def test_conpty_relays_private_osc_marker_verbatim() -> None:
    """The provisional OSC readiness default survives ConPTY unmodified.

    The adapter design disclosed that no repository evidence showed ConPTY
    relaying a private OSC sequence verbatim. This is that evidence: the
    exact ``OSC 7791;ready ST`` byte sequence a child emits arrives
    unmodified in the raw output stream, between the surrounding printable
    sentinels, so the marker scan and the design's OSC default are sound.
    """
    script = _OSC_EMITTING_CHILD.format(marker=READINESS_MARKER_DEFAULT)
    child = ConptyChild.spawn(
        _argv(script), rows=_INITIAL_ROWS, columns=_INITIAL_COLUMNS
    )
    chunks: list[str] = []
    try:
        while True:
            chunks.append(child.read())
    except ConptyEndOfStreamError:
        pass
    finally:
        child.close(force=True)

    combined = "".join(chunks)
    before = combined.find("TV_BEFORE")
    marker = combined.find(READINESS_MARKER_DEFAULT)
    after = combined.find("TV_AFTER")
    assert 0 <= before < marker < after, repr(combined[-300:])
    assert child.exit_status == 0


@pytest.mark.skipif(os.name != "nt", reason="Windows ConPTY integration evidence")
def test_full_verified_run_start_text_resize_and_subject_exit() -> None:
    """Items 5-8 end to end: start, text epoch, resize epoch, subject exit.

    One real session drives the whole happy path. Every epoch's quiescence
    is the fixture's readiness marker observed in stream order; the resize
    epoch's evidence is the child-observed dimensions surfacing in the
    frame while the observation carries the new effective dimensions; the
    run ends with the native end-of-stream and the observed exit record,
    never a fabricated one. Real ConPTY output normalizes without a
    fail-closed error, and the retained raw chunks replay to the recorded
    frames.
    """
    adapter = _adapter(_cooperative_argv())
    observations: list[Observation] = []

    with _reaped(adapter):
        started = adapter.start("run-conpty-integration", _configuration())
        assert type(started) is Started, started
        observation = started.observation
        observations.append(observation)
        assert observation.state == {
            "terminal": {"columns": _INITIAL_COLUMNS, "rows": _INITIAL_ROWS}
        }
        raw = "".join(_chunks(observation))
        assert READINESS_MARKER_DEFAULT in raw
        initial_text = _frame_text(observation)
        assert re.search(r"TV_PID:\d+", initial_text)
        assert f"TV_SIZE:{_INITIAL_COLUMNS}x{_INITIAL_ROWS}" in initial_text
        # The OSC marker is consumed by string-sequence semantics, not
        # stripped: it is present in the raw evidence above and absent from
        # the frame.
        assert "7791" not in initial_text
        assert observation.ui.cursor.visible is True

        result = adapter.dispatch(TextInput(ManualTime(0), "hello\r\n"))
        assert type(result) is EpochCompleted, result
        observations.append(result.observation)
        assert "TV_ECHO:hello" in _frame_text(result.observation)

        resized = adapter.dispatch(
            Resize(ManualTime(0), columns=_RESIZED_COLUMNS, rows=_RESIZED_ROWS)
        )
        assert type(resized) is EpochCompleted, resized
        observations.append(resized.observation)
        assert resized.observation.state == {
            "terminal": {"columns": _RESIZED_COLUMNS, "rows": _RESIZED_ROWS}
        }
        resized_frame = resized.observation.frame
        assert resized_frame is not None
        assert resized_frame.columns == _RESIZED_COLUMNS
        assert resized_frame.rows == _RESIZED_ROWS
        # The child itself observed the new dimensions: end-to-end resize
        # evidence through a full dispatch(Resize) epoch, not an API echo.
        assert f"TV_RESIZED:{_RESIZED_COLUMNS}x{_RESIZED_ROWS}" in _frame_text(
            resized.observation
        )

        final = adapter.dispatch(TextInput(ManualTime(0), "exit\r\n"))
        assert type(final) is TerminalResult, final
        assert final.outcome == RunFinished(ExitStatus("code", 3))
        assert final.observation is not None
        observations.append(final.observation)
        process = final.observation.process
        assert process is not None
        assert process.state == "exited"
        assert "TV_EXIT" in _frame_text(final.observation)

    _assert_replay_reproduces(
        observations, rows=_INITIAL_ROWS, columns=_INITIAL_COLUMNS
    )
    with pytest.raises(RuntimeError):
        adapter.dispatch(TextInput(ManualTime(0), "late\r\n"))


@pytest.mark.skipif(os.name != "nt", reason="Windows ConPTY integration evidence")
def test_printable_marker_appears_in_frames_and_replays_identically() -> None:
    """A host-configured printable marker renders in frames, as designed.

    The design claims a printable marker appears in frames and in replays
    identically — the mitigation path had OSC passthrough failed. The
    fixture emits the printable marker, readiness is still observed, the
    marker text is part of the frame, and the replay reproduces it.
    """
    adapter = _adapter(
        _cooperative_argv(_PRINTABLE_MARKER), readiness_marker=_PRINTABLE_MARKER
    )
    with _reaped(adapter):
        started = adapter.start("run-conpty-printable", _configuration())
        assert type(started) is Started, started
        observation = started.observation
        assert _PRINTABLE_MARKER in "".join(_chunks(observation))
        assert _PRINTABLE_MARKER in _frame_text(observation)
        _assert_replay_reproduces(
            [observation], rows=_INITIAL_ROWS, columns=_INITIAL_COLUMNS
        )

        stopped = adapter.stop(Stop(ManualTime(0)))
    assert type(stopped) is TerminalResult
    assert stopped.outcome == RunFinished(
        ExitStatus("code", FORCED_TERMINATION_EXIT_CODE)
    )


@pytest.mark.skipif(os.name != "nt", reason="Windows ConPTY integration evidence")
def test_subject_exit_before_readiness_is_start_terminated() -> None:
    """A subject that exits before its first marker ends as StartTerminated.

    The initialize epoch observes native end-of-stream and the real exit
    record; no readiness is claimed and no exit status is fabricated.
    """
    adapter = _adapter(_argv(_EXIT_BEFORE_READINESS_CHILD))
    with _reaped(adapter):
        result = adapter.start("run-conpty-short", _configuration())
        assert type(result) is StartTerminated, result
    assert result.result.outcome == RunFinished(ExitStatus("code", 7))
    observation = result.result.observation
    assert observation is not None
    assert "TV_SHORT" in _frame_text(observation)
    process = observation.process
    assert process is not None
    assert process.state == "exited"


@pytest.mark.skipif(os.name != "nt", reason="Windows ConPTY integration evidence")
def test_forced_stop_tears_down_the_real_child_os_observed() -> None:
    """Forced stop ends the run truthfully and the OS confirms the kill.

    The result carries the uniform forced exit code observed from the
    native record, the forced-termination disclosure diagnostic bounds the
    evidence, and an OS process-handle wait on the fixture's self-reported
    pid confirms the child is gone with that same exit code.
    """
    adapter = _adapter(_cooperative_argv())
    started = adapter.start("run-conpty-stop", _configuration())
    assert type(started) is Started, started
    handle = _open_process_handle(_observed_pid(started.observation))
    try:
        stopped = adapter.stop(Stop(ManualTime(0)))
        os_exit_code = _wait_for_os_exit_code(handle, _OS_WAIT_TIMEOUT_MS)
    finally:
        _terminate_process(handle)
        _close_process_handle(handle)

    assert type(stopped) is TerminalResult
    assert stopped.outcome == RunFinished(
        ExitStatus("code", FORCED_TERMINATION_EXIT_CODE)
    )
    assert os_exit_code == FORCED_TERMINATION_EXIT_CODE
    assert [diagnostic.code for diagnostic in stopped.diagnostics] == [
        "forced-termination"
    ]
    process = cast(Observation, stopped.observation).process
    assert process is not None
    assert process.state == "exited"
    with pytest.raises(RuntimeError):
        adapter.dispatch(TextInput(ManualTime(0), "late\r\n"))


@pytest.mark.skipif(os.name != "nt", reason="Windows ConPTY integration evidence")
def test_deadline_abort_on_hanging_subject_recovers_os_observed() -> None:
    """The abort deadline ends a marker-less hang as a structured failure.

    The fixture accepts the input and then never answers; no marker and no
    end-of-stream can end the epoch, so the armed watchdog force-closes the
    binding. The result is a structured runtime failure disclosing the
    deadline policy — never a successful epoch, never fabricated evidence —
    with no quiescent observation, and the OS confirms the whole child tree
    was torn down by the deadline-driven close.
    """
    adapter = _adapter(_cooperative_argv(), abort_deadline_ms=_ABORT_DEADLINE_MS)
    started = adapter.start("run-conpty-deadline", _configuration())
    assert type(started) is Started, started
    handle = _open_process_handle(_observed_pid(started.observation))
    try:
        result = adapter.dispatch(TextInput(ManualTime(0), "hang\r\n"))
        os_exit_code = _wait_for_os_exit_code(handle, _OS_WAIT_TIMEOUT_MS)
    finally:
        _terminate_process(handle)
        _close_process_handle(handle)

    assert type(result) is TerminalResult, result
    assert result.observation is None
    outcome = result.outcome
    assert type(outcome) is RunFailed
    assert outcome.failure.code == "adapter-runtime-failed"
    details = cast("Mapping[str, int]", outcome.failure.details)
    assert details["abort-deadline-ms"] == _ABORT_DEADLINE_MS
    assert os_exit_code == FORCED_TERMINATION_EXIT_CODE
    with pytest.raises(RuntimeError):
        adapter.dispatch(TextInput(ManualTime(0), "late\r\n"))


# --- Cooperation-tier slice 3: the first fully verified terminal run ---

#: Wide enough that a delivered absolute sandbox path echoes into the frame
#: without wrapping; the width is a requested terminal dimension like any
#: other, enforced by the adapter at the os tier.
_WIDE_COLUMNS: Final = 200
_WIDE_ROWS: Final = 30

_DELIVERED_VARIABLES: Final = (
    "TERMVERIFY_SEED",
    "TERMVERIFY_CLOCK_INITIAL_MS",
    "TERMVERIFY_LOCALE",
    "TZ",
    "TERMVERIFY_TIMEZONE",
    "TERMVERIFY_FS_ROOT",
    "TERMVERIFY_NETWORK",
)

# Cooperating subject for the cooperation-tier evidence: it reads every
# delivered variable and its own working directory and echoes them into the
# terminal — the observable end of the delivery contract. Commands mirror
# the cooperative fixture: "exit" ends without a marker so the run ends in
# native end-of-stream; "hang" never answers so only the abort deadline can
# end the epoch.
_DELIVERY_ECHO_CHILD_TEMPLATE: Final = """\
import os
import sys
import time

MARKER = {marker!r}

def emit(text):
    sys.stdout.write(text + MARKER)
    sys.stdout.flush()

names = {names!r}
lines = ["TV_PID:" + str(os.getpid())]
for name in names:
    lines.append("TV_" + name + "=" + os.environ.get(name, "<missing>"))
lines.append("TV_CWD=" + os.getcwd())
emit("\\r\\n".join(lines) + "\\r\\n")
for line in sys.stdin:
    command = line.strip()
    if command == "exit":
        sys.stdout.write("TV_EXIT\\r\\n")
        sys.stdout.flush()
        sys.exit(0)
    if command == "hang":
        time.sleep(600)
    emit("TV_ECHO:" + command + "\\r\\n")
"""


def _delivery_echo_argv() -> list[str]:
    return _argv(
        _DELIVERY_ECHO_CHILD_TEMPLATE.format(
            marker=READINESS_MARKER_DEFAULT, names=_DELIVERED_VARIABLES
        )
    )


def _cooperation_configuration() -> RunConfiguration:
    return RunConfiguration(
        seed=42,
        clock=ClockConfiguration(initial_ms=0),
        locale="en-US",
        timezone="UTC",
        terminal=TerminalConfiguration(
            columns=_WIDE_COLUMNS, rows=_WIDE_ROWS, capabilities=()
        ),
        filesystem=FilesystemConfiguration(root_id="fixture-root"),
        network=NetworkConfiguration.deny(),
    )


def _cooperation_adapter(
    sandbox: Path, *, abort_deadline_ms: int = _SAFE_DEADLINE_MS
) -> ConptyAdapter:
    return ConptyAdapter(
        _delivery_echo_argv(),
        binding=ConptyBinding(),
        abort_deadline_ms=abort_deadline_ms,
        constraint_ports=CooperationConstraintPorts({"fixture-root": str(sandbox)}),
    )


def _host_sandbox(tmp_path: Path) -> Path:
    """Host-owned sandbox lifecycle: the test creates it, the port never does."""
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    return sandbox


@pytest.mark.skipif(os.name != "nt", reason="Windows ConPTY integration evidence")
def test_first_fully_successful_verified_run_with_cooperation_ports(
    tmp_path: Path,
) -> None:
    """The design's slice-3 claim: a fully successful real start.

    Cooperation ports, real binding, real normalizer. The receipts carry
    the delivered tier with the exact delivery records; the subject reads
    every delivered variable and its working directory and echoes them into
    frames — the delivery is observable end to end, without any claim that
    the subject honored the values beyond what the frames show. The run
    continues through a text epoch, ends in native end-of-stream with the
    observed exit record, and the retained raw chunks replay to the
    recorded frames.
    """
    sandbox = _host_sandbox(tmp_path)
    adapter = _cooperation_adapter(sandbox)
    observations: list[Observation] = []

    with _reaped(adapter):
        started = adapter.start("run-verified", _cooperation_configuration())
        assert type(started) is Started, started
        constraints = started.constraints

        assert constraints.terminal.tier == "os"
        assert constraints.terminal.delivery is None
        expected_root = RealDirectoryProbe().resolve_directory(str(sandbox))
        assert expected_root is not None
        expected_env = {
            "TERMVERIFY_SEED": "42",
            "TERMVERIFY_CLOCK_INITIAL_MS": "0",
            "TERMVERIFY_LOCALE": "en-US",
            "TZ": "UTC0",
            "TERMVERIFY_TIMEZONE": "UTC",
            "TERMVERIFY_FS_ROOT": expected_root,
            "TERMVERIFY_NETWORK": "deny",
        }
        delivered: dict[str, str] = {}
        for receipt in (
            constraints.seed,
            constraints.clock,
            constraints.locale,
            constraints.timezone,
            constraints.filesystem,
            constraints.network,
        ):
            assert receipt.tier == "delivered"
            assert receipt.delivery is not None
            delivered.update(receipt.delivery.env)
        assert delivered == expected_env
        assert constraints.filesystem.delivery is not None
        assert constraints.filesystem.delivery.cwd == expected_root

        observation = started.observation
        observations.append(observation)
        frame = _frame_text(observation)
        for name, value in expected_env.items():
            # Line-anchored: the value must end at the frame padding, so a
            # frame showing a longer value cannot satisfy a prefix of it.
            assert re.search(
                rf"^TV_{re.escape(name)}={re.escape(value)} *$", frame, re.MULTILINE
            ), f"frame does not show TV_{name}={value}"
        observed_cwd = re.search(r"TV_CWD=(\S+)", frame)
        assert observed_cwd is not None
        assert os.path.normcase(observed_cwd.group(1)) == os.path.normcase(
            expected_root
        )

        result = adapter.dispatch(TextInput(ManualTime(0), "hello\r\n"))
        assert type(result) is EpochCompleted, result
        observations.append(result.observation)
        assert "TV_ECHO:hello" in _frame_text(result.observation)

        final = adapter.dispatch(TextInput(ManualTime(0), "exit\r\n"))
        assert type(final) is TerminalResult, final
        assert final.outcome == RunFinished(ExitStatus("code", 0))
        assert final.observation is not None
        observations.append(final.observation)
        process = final.observation.process
        assert process is not None
        assert process.state == "exited"
        assert "TV_EXIT" in _frame_text(final.observation)

    _assert_replay_reproduces(observations, rows=_WIDE_ROWS, columns=_WIDE_COLUMNS)
    with pytest.raises(RuntimeError):
        adapter.dispatch(TextInput(ManualTime(0), "late\r\n"))


@pytest.mark.skipif(os.name != "nt", reason="Windows ConPTY integration evidence")
def test_forced_stop_under_cooperation_ports_os_observed(tmp_path: Path) -> None:
    """Forced stop keeps its truthful semantics under the cooperation ports."""
    adapter = _cooperation_adapter(_host_sandbox(tmp_path))
    started = adapter.start("run-verified-stop", _cooperation_configuration())
    assert type(started) is Started, started
    handle = _open_process_handle(_observed_pid(started.observation))
    try:
        stopped = adapter.stop(Stop(ManualTime(0)))
        os_exit_code = _wait_for_os_exit_code(handle, _OS_WAIT_TIMEOUT_MS)
    finally:
        _terminate_process(handle)
        _close_process_handle(handle)

    assert type(stopped) is TerminalResult
    assert stopped.outcome == RunFinished(
        ExitStatus("code", FORCED_TERMINATION_EXIT_CODE)
    )
    assert os_exit_code == FORCED_TERMINATION_EXIT_CODE
    assert [diagnostic.code for diagnostic in stopped.diagnostics] == [
        "forced-termination"
    ]


@pytest.mark.skipif(os.name != "nt", reason="Windows ConPTY integration evidence")
def test_deadline_abort_under_cooperation_ports_os_observed(tmp_path: Path) -> None:
    """The abort deadline keeps its structured-failure semantics as well."""
    adapter = _cooperation_adapter(
        _host_sandbox(tmp_path), abort_deadline_ms=_ABORT_DEADLINE_MS
    )
    started = adapter.start("run-verified-deadline", _cooperation_configuration())
    assert type(started) is Started, started
    handle = _open_process_handle(_observed_pid(started.observation))
    try:
        result = adapter.dispatch(TextInput(ManualTime(0), "hang\r\n"))
        os_exit_code = _wait_for_os_exit_code(handle, _OS_WAIT_TIMEOUT_MS)
    finally:
        _terminate_process(handle)
        _close_process_handle(handle)

    assert type(result) is TerminalResult, result
    assert result.observation is None
    outcome = result.outcome
    assert type(outcome) is RunFailed
    assert outcome.failure.code == "adapter-runtime-failed"
    details = cast("Mapping[str, int]", outcome.failure.details)
    assert details["abort-deadline-ms"] == _ABORT_DEADLINE_MS
    assert os_exit_code == FORCED_TERMINATION_EXIT_CODE


@pytest.mark.skipif(os.name != "nt", reason="Windows ConPTY integration evidence")
def test_unresolvable_sandbox_fails_unsupported_before_any_child(
    tmp_path: Path,
) -> None:
    """A missing host sandbox ends the start honestly, before any spawn."""
    adapter = ConptyAdapter(
        _delivery_echo_argv(),
        binding=ConptyBinding(),
        abort_deadline_ms=_SAFE_DEADLINE_MS,
        constraint_ports=CooperationConstraintPorts(
            {"fixture-root": str(tmp_path / "missing")}
        ),
    )
    result = adapter.start("run-verified-missing", _cooperation_configuration())

    assert type(result) is StartUnsupported, result
    assert result.constraint == "filesystem"
    assert result.code == "constraint-unsupported"
