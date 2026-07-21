"""Cross-platform real-subprocess integration evidence for the JSONL transport.

Slice 2 of the accepted JSONL control transport design
(`docs/agent/design/jsonl-control-transport.md`): the public claims of the
real pipe/process binding promoted into repeatable CI evidence on every
leg — pipes are portable, so unlike the ConPTY integration module there
is no platform skip. The fixture subject is the committed
`tests/fixtures/jsonl_echo_subject.py`, a cooperative speaker of
`termverify.control/v1`; the asserted evidence is adapter results, wire
content, transcripts, and OS-observed exit records — never helper-thread
or wall-clock state.

- **Negotiation with delivered-tier receipts:** a real start through the
  cooperation ports yields the delivered tier with the exact delivery
  records (six spawn-env, one hello-config), and the fixture echoes its
  delivered environment into a startup diagnostic.
- **Every epoch kind:** text, key, resize (the child-observed dimensions
  surface in the frame), and the live clock channel — the `input.clock`
  capability no other runtime has.
- **Natural exit with an OS-observed record:** the fixture's natural
  exit ends the run in native end-of-stream with the real exit code.
- **Forced teardown:** `stop` against a hanging subject and the abort
  deadline both end as structured, honest results with the child tree
  terminated (OS-observed), never fabricated observations.
- **Phase 2 core consumes the transport unchanged:** a recorded fixture
  run passes through `run_scripted` and `compare_transcripts` end to
  end, with replay identity across two identical runs.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Final, cast

import pytest

from termverify.adapter import (
    ClockAdvance,
    ClockConfiguration,
    Diagnostic,
    EpochCompleted,
    ExitStatus,
    FilesystemConfiguration,
    JsonInput,
    KeyInput,
    ManualTime,
    NetworkConfiguration,
    Observation,
    Resize,
    RunConfiguration,
    RunFailed,
    RunFinished,
    Started,
    Stop,
    TerminalConfiguration,
    TerminalResult,
    TextInput,
)
from termverify.comparator import compare_transcripts
from termverify.cooperation import CooperationConstraintPorts, RealDirectoryProbe
from termverify.jsonl import JsonlAdapter, JsonlBinding
from termverify.recorder import run_scripted

_FIXTURE: Final = str(Path(__file__).parent / "fixtures" / "jsonl_echo_subject.py")
_RUN_ID: Final = "run-jsonl-integration"
_SAFE_DEADLINE_MS: Final = 60_000
_ABORT_DEADLINE_MS: Final = 5_000

_SUBJECT: Final[dict[str, JsonInput]] = {
    "format": "termverify.replay-subject/v1",
    "application": {"id": "jsonl-echo-subject", "version": "1", "build": "b1"},
    "fixture": {"id": "jsonl-echo", "version": "1"},
    "adapter": {"id": "termverify.jsonl", "version": "1"},
    "normalizer": {"id": "termverify.identity", "version": "1"},
    "state_schema": {"id": "jsonl-echo-state", "version": "1"},
}


def _argv() -> list[str]:
    return [sys.executable, "-I", "-u", _FIXTURE]


def _configuration() -> RunConfiguration:
    return RunConfiguration(
        seed=42,
        clock=ClockConfiguration(initial_ms=0),
        locale="en-US",
        timezone="UTC",
        terminal=TerminalConfiguration(columns=80, rows=24, capabilities=()),
        filesystem=FilesystemConfiguration(root_id="fixture-root"),
        network=NetworkConfiguration.deny(),
    )


def _adapter(
    sandbox: Path, *, abort_deadline_ms: int = _SAFE_DEADLINE_MS
) -> JsonlAdapter:
    return JsonlAdapter(
        _argv(),
        binding=JsonlBinding(),
        abort_deadline_ms=abort_deadline_ms,
        constraint_ports=CooperationConstraintPorts({"fixture-root": str(sandbox)}),
    )


@contextmanager
def _reaped(adapter: JsonlAdapter) -> Iterator[JsonlAdapter]:
    """Cleanup arrangement, not evidence: never leak a child past a failure."""
    try:
        yield adapter
    finally:
        child = adapter._child  # noqa: SLF001 - cleanup-only access
        if child is not None:
            child.close(force=True)


def _frame_text(observation: Observation) -> str:
    assert observation.frame is not None
    return "\n".join(observation.frame.lines)


def _details(diagnostic: Diagnostic) -> Mapping[str, object]:
    details = cast("object", diagnostic.details)
    assert isinstance(details, Mapping)
    return cast("Mapping[str, object]", details)


def test_negotiation_delivered_receipts_and_observed_delivery(tmp_path: Path) -> None:
    """A real start: delivered-tier receipts, observable delivery, readiness.

    Six spawn-env receipts carry the exact variables the fixture echoes
    back in its startup diagnostic; the terminal receipt is a hello-config
    delivery; the readiness observation's frame shows the delivered
    terminal dimensions.
    """
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    adapter = _adapter(sandbox)
    with _reaped(adapter):
        started = adapter.start(_RUN_ID, _configuration())
        assert type(started) is Started, started
        constraints = started.constraints

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
            assert receipt.delivery.channel == "spawn-env"
            delivered.update(receipt.delivery.env)
        assert delivered == expected_env
        assert constraints.filesystem.delivery is not None
        assert constraints.filesystem.delivery.cwd == expected_root
        terminal = constraints.terminal
        assert terminal.tier == "delivered"
        assert terminal.delivery is not None
        assert terminal.delivery.channel == "hello-config"

        # The subject observed the delivery: its startup diagnostic echoes
        # the delivered environment, proving the receipts describe reality.
        codes = [diagnostic.code for diagnostic in started.diagnostics]
        assert "fixture-delivery" in codes
        diagnostic = next(
            item for item in started.diagnostics if item.code == "fixture-delivery"
        )
        observed = _details(diagnostic)
        subject_env = cast("Mapping[str, str]", observed["delivered"])
        for name, value in expected_env.items():
            assert subject_env[name] == value, name
        observed_cwd = cast("str", observed["cwd"])
        assert os.path.normcase(observed_cwd) == os.path.normcase(expected_root)

        frame = _frame_text(started.observation)
        assert "TV_READY" in frame
        assert "TV_SIZE:80x24" in frame

        stopped = adapter.stop(Stop(ManualTime(0)))
    assert type(stopped) is TerminalResult
    assert stopped.outcome == RunFinished(ExitStatus("code", 3))


def test_text_key_resize_and_clock_epochs(tmp_path: Path) -> None:
    """Every input kind drives a real epoch with subject-observed evidence."""
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    adapter = _adapter(sandbox)
    with _reaped(adapter):
        started = adapter.start(_RUN_ID, _configuration())
        assert type(started) is Started, started

        text = adapter.dispatch(TextInput(ManualTime(0), "hello"))
        assert type(text) is EpochCompleted, text
        assert "TV_TEXT:hello" in _frame_text(text.observation)
        assert text.observation.events[0].type == "fixture.text"

        key = adapter.dispatch(KeyInput(ManualTime(0), ("Control", "Enter")))
        assert type(key) is EpochCompleted, key
        assert "TV_KEY:Control+Enter" in _frame_text(key.observation)

        resized = adapter.dispatch(Resize(ManualTime(0), columns=120, rows=40))
        assert type(resized) is EpochCompleted, resized
        frame = resized.observation.frame
        assert frame is not None
        assert (frame.columns, frame.rows) == (120, 40)
        # The child itself observed the new dimensions through the wire.
        assert "TV_RESIZED:120x40" in _frame_text(resized.observation)

        clock = adapter.advance_clock(ClockAdvance(at_ms=ManualTime(250), delta_ms=250))
        assert type(clock) is EpochCompleted, clock
        assert "TV_CLOCK:250" in _frame_text(clock.observation)
        event = clock.observation.events[0]
        assert event.type == "fixture.clock"
        assert cast("Mapping[str, int]", event.data)["at_ms"] == 250

        final = adapter.dispatch(TextInput(ManualTime(250), "quit"))
        assert type(final) is TerminalResult, final
    assert final.outcome == RunFinished(ExitStatus("code", 7))
    observation = final.observation
    assert observation is not None
    process = observation.process
    assert process is not None
    assert process.state == "exited"
    with pytest.raises(RuntimeError):
        adapter.dispatch(TextInput(ManualTime(250), "late"))


def test_forced_stop_tears_down_the_real_child(tmp_path: Path) -> None:
    """Forced stop on a hanging epoch: structured result, OS-observed kill."""
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    adapter = _adapter(sandbox, abort_deadline_ms=_ABORT_DEADLINE_MS)
    started = adapter.start(_RUN_ID, _configuration())
    assert type(started) is Started, started
    child = adapter._child  # noqa: SLF001 - OS-liveness evidence only
    assert child is not None

    result = adapter.dispatch(TextInput(ManualTime(0), "hang"))
    assert type(result) is TerminalResult, result
    assert result.observation is None
    outcome = result.outcome
    assert type(outcome) is RunFailed
    assert outcome.failure.code == "adapter-runtime-failed"
    details = cast("Mapping[str, object]", outcome.failure.details)
    assert details["failure"] == "epoch-timeout"
    assert details["abort-deadline-ms"] == _ABORT_DEADLINE_MS
    # The OS-observed forced record is present and honest: the uniform
    # forced code 15 on Windows, the SIGKILL negation on POSIX.
    expected = 15 if os.name == "nt" else -9
    assert child.exit_status == expected
    with pytest.raises(RuntimeError):
        adapter.dispatch(TextInput(ManualTime(0), "late"))


def test_subject_reported_failure_maps_to_run_failed(tmp_path: Path) -> None:
    """A subject `run.failed` carries its error verbatim into the result."""
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    adapter = _adapter(sandbox)
    with _reaped(adapter):
        started = adapter.start(_RUN_ID, _configuration())
        assert type(started) is Started, started
        result = adapter.dispatch(TextInput(ManualTime(0), "boom"))
        assert type(result) is TerminalResult, result
        outcome = result.outcome
        assert type(outcome) is RunFailed
        assert outcome.failure.code == "adapter-runtime-failed"
        details = cast("Mapping[str, object]", outcome.failure.details)
        assert details["subject-code"] == "subject-boom"


def test_recorded_fixture_run_passes_recorder_and_comparator(
    tmp_path: Path,
) -> None:
    """The Phase 2 core consumes the transport unchanged, end to end.

    `run_scripted` drives the real adapter through the fixture subject and
    the transcript codec accepts the recording; two identical runs produce
    byte-identical transcripts, and the comparator proves a divergent
    transcript is detected — the transport needs no recorder or comparator
    changes.
    """

    def one_run() -> bytes:
        sandbox = tmp_path / "sandbox"
        sandbox.mkdir(exist_ok=True)
        adapter = _adapter(sandbox)
        scripted = run_scripted(
            adapter,
            _RUN_ID,
            _configuration(),
            _SUBJECT,
            (
                TextInput(ManualTime(0), "hello"),
                KeyInput(ManualTime(0), ("Enter",)),
                Resize(ManualTime(0), 120, 40),
                ClockAdvance(ManualTime(250), 250),
                Stop(ManualTime(250)),
            ),
        )
        assert type(scripted.result) is TerminalResult
        assert scripted.result.outcome == RunFinished(ExitStatus("code", 3))
        return scripted.transcript

    first = one_run()
    second = one_run()
    assert first == second

    records = [
        json.loads(line) for line in first.decode("utf-8").splitlines() if line.strip()
    ]
    assert [record["kind"] for record in records] == [
        "run.started",
        *(["capability.result"] * 7),
        "diagnostic",
        "observation",
        "input.text",
        "observation",
        "input.key",
        "observation",
        "input.resize",
        "observation",
        "input.clock_advanced",
        "observation",
        "input.stop",
        "observation",
        "run.finished",
    ]

    verdict = compare_transcripts(first, second)
    assert verdict.equivalent, verdict

    # The comparator compares the recorded payload bytes rather than
    # washing mutations through a normalization: a single mutated digit
    # in a recorded observation is detected. (The transport-pinning half
    # of the claim is the byte-identity of the two real runs above.)
    mutated = bytearray(first)
    marker = b'"frame":{"columns":120'
    index = first.find(marker)
    assert index > 0
    mutated[index + len(marker) - 1 : index + len(marker)] = b"1"
    divergent = compare_transcripts(first, bytes(mutated))
    assert not divergent.equivalent
