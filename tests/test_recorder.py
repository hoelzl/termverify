from __future__ import annotations

from typing import cast

import pytest
from hypothesis import given
from hypothesis import strategies as st

from termverify.adapter import (
    AdapterFailure,
    ClockAdvance,
    ClockConfiguration,
    ClockReceipt,
    ConstraintName,
    Cursor,
    DeliveryRecord,
    Diagnostic,
    DispatchInput,
    EnforcedConstraints,
    EpochCompleted,
    EpochResult,
    Event,
    ExitStatus,
    FilesystemConfiguration,
    FilesystemReceipt,
    Frame,
    JsonInput,
    KeyInput,
    LocaleReceipt,
    ManualTime,
    NetworkConfiguration,
    NetworkReceipt,
    Observation,
    ProcessObservation,
    Region,
    Resize,
    RunConfiguration,
    RunFailed,
    RunFinished,
    SeedReceipt,
    Started,
    StartFailed,
    StartResult,
    StartTerminated,
    StartUnsupported,
    Stop,
    TerminalConfiguration,
    TerminalReceipt,
    TerminalResult,
    TextInput,
    TimezoneReceipt,
    UiObservation,
)
from termverify.recorder import (
    TranscriptRecorder,
    TranscriptRecorderError,
    run_scripted,
)
from termverify.transcript import parse_transcript

RUN_ID = "run-recorder"

SUBJECT: dict[str, JsonInput] = {
    "format": "termverify.replay-subject/v1",
    "application": {"id": "fixture-app", "version": "1", "build": "b1"},
    "fixture": {"id": "basic", "version": "1"},
    "adapter": {"id": "termverify.direct", "version": "1"},
    "normalizer": {"id": "termverify.identity", "version": "1"},
    "state_schema": {"id": "fixture-state", "version": "1"},
}


def _configuration(initial_ms: int = 0) -> RunConfiguration:
    return RunConfiguration(
        seed=42,
        clock=ClockConfiguration(initial_ms=initial_ms),
        locale="en-US",
        timezone="UTC",
        terminal=TerminalConfiguration(columns=80, rows=24, capabilities=()),
        filesystem=FilesystemConfiguration(root_id="fixture-root"),
        network=NetworkConfiguration.deny(),
    )


def _constraints(
    run_id: str = RUN_ID, configuration: RunConfiguration | None = None
) -> EnforcedConstraints:
    configuration = configuration or _configuration()
    return EnforcedConstraints(
        run_id=run_id,
        requested=configuration,
        seed=SeedReceipt(run_id, configuration.seed, "constructive"),
        clock=ClockReceipt(run_id, configuration.clock, "constructive"),
        locale=LocaleReceipt(run_id, configuration.locale, "constructive"),
        timezone=TimezoneReceipt(run_id, configuration.timezone, "constructive"),
        terminal=TerminalReceipt(run_id, configuration.terminal, "constructive"),
        filesystem=FilesystemReceipt(run_id, configuration.filesystem, "constructive"),
        network=NetworkReceipt(run_id, configuration.network, "constructive"),
    )


def _observation(
    at_ms: int = 0,
    *,
    process: ProcessObservation | None = None,
    frame: Frame | None = None,
    events: tuple[Event, ...] = (),
) -> Observation:
    return Observation(
        at_ms=ManualTime(at_ms),
        state={"count": 0},
        events=events,
        ui=UiObservation(
            regions=(Region("main", "document", 0, 0, 80, 24),),
            focus="main",
            cursor=Cursor(0, 0, True),
            mode=None,
        ),
        frame=frame,
        process=process,
    )


def test_full_run_produces_a_codec_accepted_transcript() -> None:
    recorder = TranscriptRecorder(RUN_ID, _configuration(), SUBJECT)
    recorder.record_start(Started(_constraints(), _observation()))
    recorder.record_epoch(
        TextInput(ManualTime(0), "hello"), EpochCompleted(_observation())
    )
    recorder.record_epoch(
        KeyInput(ManualTime(0), ("Enter",)), EpochCompleted(_observation())
    )
    recorder.record_epoch(
        Resize(ManualTime(0), 120, 40), EpochCompleted(_observation())
    )
    recorder.record_epoch(
        ClockAdvance(ManualTime(1000), 1000), EpochCompleted(_observation(1000))
    )
    recorder.record_epoch(
        Stop(ManualTime(1000)),
        TerminalResult(
            _observation(
                1000, process=ProcessObservation.exited(ExitStatus("code", 0))
            ),
            RunFinished.code(0),
        ),
    )

    records = parse_transcript(recorder.transcript())

    assert [record["kind"] for record in records] == [
        "run.started",
        *(["capability.result"] * 7),
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
    assert all(record["run_id"] == RUN_ID for record in records)
    assert [record["id"] for record in records] == [
        f"record-{sequence:04d}" for sequence in range(len(records))
    ]
    started = records[0]["payload"]
    assert started == {
        "config": _configuration().to_protocol(),
        "subject": SUBJECT,
    }
    seed_result = records[1]["payload"]
    assert seed_result == {
        "constraint": "seed",
        "status": "enforced",
        "effective": "42",
        "tier": "constructive",
    }
    text_input = records[9]["payload"]
    assert text_input == {"at_ms": 0, "text": "hello"}
    key_input = records[11]["payload"]
    assert key_input == {"at_ms": 0, "keys": ["Enter"]}
    resize_input = records[13]["payload"]
    assert resize_input == {"at_ms": 0, "columns": 120, "rows": 40}
    clock_input = records[15]["payload"]
    assert clock_input == {"at_ms": 1000, "delta_ms": 1000}
    stop_input = records[17]["payload"]
    assert stop_input == {"at_ms": 1000}
    final_observation = cast(dict[str, object], records[18]["payload"])
    assert final_observation["process"] == {
        "state": "exited",
        "exit": {"kind": "code", "value": 0},
    }
    assert final_observation["ui"] == {
        "regions": [
            {
                "id": "main",
                "role": "document",
                "bounds": {"column": 0, "row": 0, "columns": 80, "rows": 24},
            }
        ],
        "focus": "main",
        "cursor": {"column": 0, "row": 0, "visible": True},
        "mode": None,
    }
    assert records[-1]["payload"] == {"exit": {"kind": "code", "value": 0}}


def test_epoch_diagnostics_precede_the_closing_observation() -> None:
    recorder = TranscriptRecorder(RUN_ID, _configuration(), SUBJECT)
    recorder.record_start(Started(_constraints(), _observation()))
    diagnostic = Diagnostic(
        ManualTime(0), "command-rejected", "no such exit", {"turn": 1}
    )
    recorder.record_epoch(
        TextInput(ManualTime(0), "move nowhere"),
        EpochCompleted(_observation(), diagnostics=(diagnostic,)),
    )
    recorder.record_epoch(
        Stop(ManualTime(0)),
        TerminalResult(
            _observation(process=ProcessObservation.exited(ExitStatus("code", 0))),
            RunFinished.code(0),
        ),
    )

    records = parse_transcript(recorder.transcript())

    kinds = [record["kind"] for record in records]
    assert kinds[9:12] == ["input.text", "diagnostic", "observation"]
    assert records[10]["payload"] == {
        "at_ms": 0,
        "code": "command-rejected",
        "message": "no such exit",
        "details": {"turn": 1},
    }


def _receipt_prefix(
    length: int, run_id: str = RUN_ID
) -> tuple[
    SeedReceipt
    | ClockReceipt
    | LocaleReceipt
    | TimezoneReceipt
    | TerminalReceipt
    | FilesystemReceipt
    | NetworkReceipt,
    ...,
]:
    constraints = _constraints(run_id)
    receipts = (
        constraints.seed,
        constraints.clock,
        constraints.locale,
        constraints.timezone,
        constraints.terminal,
        constraints.filesystem,
        constraints.network,
    )
    return receipts[:length]


CONSTRAINTS: tuple[ConstraintName, ...] = (
    "seed",
    "clock",
    "locale",
    "timezone",
    "terminal",
    "filesystem",
    "network",
)


@pytest.mark.parametrize("index", range(7))
def test_start_unsupported_at_each_prefix(index: int) -> None:
    constraint = CONSTRAINTS[index]
    recorder = TranscriptRecorder(RUN_ID, _configuration(), SUBJECT)
    recorder.record_start(
        StartUnsupported(
            RUN_ID,
            _configuration(),
            _receipt_prefix(index),
            constraint,
            "constraint-unsupported",
            f"{constraint} is unsupported",
            {"probe": "failed"},
        )
    )

    records = parse_transcript(recorder.transcript())

    assert len(records) == index + 3
    unsupported_capability = records[-2]["payload"]
    assert unsupported_capability == {
        "constraint": constraint,
        "status": "unsupported",
        "reason": f"{constraint} is unsupported",
    }
    assert records[-1]["kind"] == "run.unsupported"
    assert records[-1]["payload"] == {
        "constraint": constraint,
        "code": "constraint-unsupported",
        "message": f"{constraint} is unsupported",
        "details": {"probe": "failed"},
    }


def test_start_failed_before_capabilities() -> None:
    recorder = TranscriptRecorder(RUN_ID, _configuration(), SUBJECT)
    recorder.record_start(
        StartFailed(
            RUN_ID,
            _configuration(),
            (),
            AdapterFailure("adapter-start-failed", "boom"),
        )
    )

    records = parse_transcript(recorder.transcript())

    assert [record["kind"] for record in records] == ["run.started", "run.failed"]
    assert records[-1]["payload"] == {
        "error": {"code": "adapter-start-failed", "message": "boom"}
    }


def test_start_failed_after_full_negotiation_with_diagnostics() -> None:
    recorder = TranscriptRecorder(RUN_ID, _configuration(), SUBJECT)
    diagnostic = Diagnostic(ManualTime(0), "startup-detail", "details", None)
    recorder.record_start(
        StartFailed(
            RUN_ID,
            _configuration(),
            _receipt_prefix(7),
            AdapterFailure("adapter-start-failed", "boom", {"why": "init"}),
            diagnostics=(diagnostic,),
        )
    )

    records = parse_transcript(recorder.transcript())

    kinds = [record["kind"] for record in records]
    assert kinds == [
        "run.started",
        *(["capability.result"] * 7),
        "diagnostic",
        "run.failed",
    ]
    assert records[8]["payload"] == {
        "at_ms": 0,
        "code": "startup-detail",
        "message": "details",
    }
    assert records[-1]["payload"] == {
        "error": {
            "code": "adapter-start-failed",
            "message": "boom",
            "details": {"why": "init"},
        }
    }


def test_start_terminated_with_exit_observation() -> None:
    recorder = TranscriptRecorder(RUN_ID, _configuration(), SUBJECT)
    recorder.record_start(
        StartTerminated(
            _constraints(),
            TerminalResult(
                _observation(process=ProcessObservation.exited(ExitStatus("code", 3))),
                RunFinished.code(3),
            ),
        )
    )

    records = parse_transcript(recorder.transcript())

    kinds = [record["kind"] for record in records]
    assert kinds == [
        "run.started",
        *(["capability.result"] * 7),
        "observation",
        "run.finished",
    ]
    assert records[-1]["payload"] == {"exit": {"kind": "code", "value": 3}}


def test_start_terminated_without_observation() -> None:
    recorder = TranscriptRecorder(RUN_ID, _configuration(), SUBJECT)
    recorder.record_start(
        StartTerminated(
            _constraints(),
            TerminalResult(None, RunFinished.signal("term")),
        )
    )

    records = parse_transcript(recorder.transcript())

    assert [record["kind"] for record in records] == [
        "run.started",
        *(["capability.result"] * 7),
        "run.finished",
    ]
    assert records[-1]["payload"] == {"exit": {"kind": "signal", "value": "term"}}


def test_runtime_failure_without_observation_records_run_failed() -> None:
    recorder = TranscriptRecorder(RUN_ID, _configuration(), SUBJECT)
    recorder.record_start(Started(_constraints(), _observation()))
    recorder.record_epoch(
        TextInput(ManualTime(0), "crash"),
        TerminalResult(
            None,
            RunFailed(
                AdapterFailure("adapter-runtime-failed", "boom", {"input_kind": "text"})
            ),
        ),
    )

    records = parse_transcript(recorder.transcript())

    assert [record["kind"] for record in records][-2:] == [
        "input.text",
        "run.failed",
    ]
    assert records[-1]["payload"] == {
        "error": {
            "code": "adapter-runtime-failed",
            "message": "boom",
            "details": {"input_kind": "text"},
        }
    }


def test_natural_exit_during_dispatch_records_finished() -> None:
    recorder = TranscriptRecorder(RUN_ID, _configuration(), SUBJECT)
    recorder.record_start(Started(_constraints(), _observation()))
    recorder.record_epoch(
        TextInput(ManualTime(0), "quit"),
        TerminalResult(
            _observation(
                process=ProcessObservation.exited(ExitStatus("code", 0)),
                events=(Event("Quit", {"reason": "player"}),),
            ),
            RunFinished.code(0),
        ),
    )

    records = parse_transcript(recorder.transcript())

    final_observation = cast(dict[str, object], records[-2]["payload"])
    assert final_observation["events"] == [
        {"type": "Quit", "data": {"reason": "player"}}
    ]
    assert records[-1]["kind"] == "run.finished"


def test_delivered_tier_receipts_record_delivery() -> None:
    configuration = _configuration()
    constraints = EnforcedConstraints(
        run_id=RUN_ID,
        requested=configuration,
        seed=SeedReceipt(
            RUN_ID,
            configuration.seed,
            "delivered",
            DeliveryRecord({"TERMVERIFY_SEED": "42"}),
        ),
        clock=ClockReceipt(RUN_ID, configuration.clock, "constructive"),
        locale=LocaleReceipt(RUN_ID, configuration.locale, "constructive"),
        timezone=TimezoneReceipt(RUN_ID, configuration.timezone, "constructive"),
        terminal=TerminalReceipt(RUN_ID, configuration.terminal, "os"),
        filesystem=FilesystemReceipt(
            RUN_ID,
            configuration.filesystem,
            "delivered",
            DeliveryRecord({"TERMVERIFY_FS_ROOT": "C:/sandbox"}, cwd="C:/sandbox"),
        ),
        network=NetworkReceipt(RUN_ID, configuration.network, "constructive"),
    )
    recorder = TranscriptRecorder(RUN_ID, configuration, SUBJECT)
    recorder.record_start(
        StartTerminated(constraints, TerminalResult(None, RunFinished.code(0)))
    )

    records = parse_transcript(recorder.transcript())

    assert records[1]["payload"] == {
        "constraint": "seed",
        "status": "enforced",
        "effective": "42",
        "tier": "delivered",
        "delivery": {"channel": "spawn-env", "env": {"TERMVERIFY_SEED": "42"}},
    }
    seq5 = records[5]["payload"]
    assert isinstance(seq5, dict) and seq5["tier"] == "os"
    seq6 = records[6]["payload"]
    assert isinstance(seq6, dict) and seq6["delivery"] == {
        "channel": "spawn-env",
        "env": {"TERMVERIFY_FS_ROOT": "C:/sandbox"},
        "cwd": "C:/sandbox",
    }


def _started_recorder() -> TranscriptRecorder:
    recorder = TranscriptRecorder(RUN_ID, _configuration(), SUBJECT)
    recorder.record_start(Started(_constraints(), _observation()))
    return recorder


def _terminal_result(at_ms: int = 0) -> TerminalResult:
    return TerminalResult(
        _observation(at_ms, process=ProcessObservation.exited(ExitStatus("code", 0))),
        RunFinished.code(0),
    )


def test_invalid_subject_is_a_structured_error_at_construction() -> None:
    with pytest.raises(TranscriptRecorderError) as caught:
        TranscriptRecorder(RUN_ID, _configuration(), {"format": "wrong"})
    assert caught.value.code == "invalid-subject"


def test_non_mapping_subject_is_a_structured_error() -> None:
    with pytest.raises(TranscriptRecorderError) as caught:
        TranscriptRecorder(RUN_ID, _configuration(), None)  # type: ignore[arg-type]
    assert caught.value.code == "invalid-subject"


def test_invalid_configuration_is_a_structured_error() -> None:
    with pytest.raises(TranscriptRecorderError) as caught:
        TranscriptRecorder(RUN_ID, None, SUBJECT)  # type: ignore[arg-type]
    assert caught.value.code == "invalid-configuration"


def test_record_start_twice_is_a_structured_error() -> None:
    recorder = _started_recorder()
    with pytest.raises(TranscriptRecorderError) as caught:
        recorder.record_start(Started(_constraints(), _observation()))
    assert caught.value.code == "recorder-not-created"


def test_record_epoch_before_start_is_a_structured_error() -> None:
    recorder = TranscriptRecorder(RUN_ID, _configuration(), SUBJECT)
    with pytest.raises(TranscriptRecorderError) as caught:
        recorder.record_epoch(
            TextInput(ManualTime(0), "early"), EpochCompleted(_observation())
        )
    assert caught.value.code == "recorder-not-idle"


def test_record_epoch_after_terminal_is_a_structured_error() -> None:
    recorder = _started_recorder()
    recorder.record_epoch(Stop(ManualTime(0)), _terminal_result())
    with pytest.raises(TranscriptRecorderError) as caught:
        recorder.record_epoch(
            TextInput(ManualTime(0), "late"), EpochCompleted(_observation())
        )
    assert caught.value.code == "recorder-not-idle"


def test_transcript_before_terminal_is_a_structured_error() -> None:
    recorder = _started_recorder()
    with pytest.raises(TranscriptRecorderError) as caught:
        recorder.transcript()
    assert caught.value.code == "recorder-not-terminal"


def test_stop_with_epoch_result_is_a_structured_error() -> None:
    recorder = _started_recorder()
    with pytest.raises(TranscriptRecorderError) as caught:
        recorder.record_epoch(Stop(ManualTime(0)), EpochCompleted(_observation()))
    assert caught.value.code == "stop-result-mismatch"


def test_input_at_wrong_manual_time_is_a_structured_error() -> None:
    recorder = _started_recorder()
    with pytest.raises(TranscriptRecorderError) as caught:
        recorder.record_epoch(
            TextInput(ManualTime(5), "skewed"),
            EpochCompleted(_observation(5)),
        )
    assert caught.value.code == "manual-clock-mismatch"


def test_clock_advance_mismatch_is_a_structured_error() -> None:
    recorder = _started_recorder()
    with pytest.raises(TranscriptRecorderError) as caught:
        recorder.record_epoch(
            ClockAdvance(ManualTime(5), 10), EpochCompleted(_observation(5))
        )
    assert caught.value.code == "manual-clock-mismatch"


def test_foreign_run_result_is_a_structured_error() -> None:
    recorder = TranscriptRecorder(RUN_ID, _configuration(), SUBJECT)
    with pytest.raises(TranscriptRecorderError) as caught:
        recorder.record_start(Started(_constraints("run-other"), _observation()))
    assert caught.value.code == "result-run-mismatch"


def test_non_start_result_is_a_structured_error() -> None:
    recorder = TranscriptRecorder(RUN_ID, _configuration(), SUBJECT)
    with pytest.raises(TranscriptRecorderError) as caught:
        recorder.record_start(None)  # type: ignore[arg-type]
    assert caught.value.code == "invalid-start-result"


def test_non_input_epoch_value_is_a_structured_error() -> None:
    recorder = _started_recorder()
    with pytest.raises(TranscriptRecorderError) as caught:
        recorder.record_epoch(None, EpochCompleted(_observation()))  # type: ignore[arg-type]
    assert caught.value.code == "invalid-input"


def test_non_epoch_result_is_a_structured_error() -> None:
    recorder = _started_recorder()
    with pytest.raises(TranscriptRecorderError) as caught:
        recorder.record_epoch(TextInput(ManualTime(0), "x"), None)  # type: ignore[arg-type]
    assert caught.value.code == "invalid-epoch-result"


def test_recorder_state_is_unchanged_after_a_rejected_contribution() -> None:
    recorder = _started_recorder()
    with pytest.raises(TranscriptRecorderError):
        recorder.record_epoch(
            TextInput(ManualTime(5), "skewed"), EpochCompleted(_observation(5))
        )
    recorder.record_epoch(
        TextInput(ManualTime(0), "hello"), EpochCompleted(_observation())
    )
    recorder.record_epoch(Stop(ManualTime(0)), _terminal_result())
    records = parse_transcript(recorder.transcript())
    assert [record["kind"] for record in records][9:] == [
        "input.text",
        "observation",
        "input.stop",
        "observation",
        "run.finished",
    ]


def test_mistimed_epoch_observation_is_a_structured_error() -> None:
    recorder = _started_recorder()
    with pytest.raises(TranscriptRecorderError) as caught:
        recorder.record_epoch(
            TextInput(ManualTime(0), "x"), EpochCompleted(_observation(5))
        )
    assert caught.value.code == "evidence-time-mismatch"


def test_mistimed_terminal_observation_is_a_structured_error() -> None:
    recorder = _started_recorder()
    with pytest.raises(TranscriptRecorderError) as caught:
        recorder.record_epoch(Stop(ManualTime(0)), _terminal_result(5))
    assert caught.value.code == "evidence-time-mismatch"


def test_mistimed_terminal_diagnostic_is_a_structured_error() -> None:
    recorder = _started_recorder()
    with pytest.raises(TranscriptRecorderError) as caught:
        recorder.record_epoch(
            TextInput(ManualTime(0), "crash"),
            TerminalResult(
                None,
                RunFailed(AdapterFailure("adapter-runtime-failed", "boom")),
                diagnostics=(Diagnostic(ManualTime(999), "late", "m"),),
            ),
        )
    assert caught.value.code == "evidence-time-mismatch"


def test_mistimed_contribution_appends_no_record() -> None:
    recorder = _started_recorder()
    with pytest.raises(TranscriptRecorderError):
        recorder.record_epoch(
            TextInput(ManualTime(0), "x"), EpochCompleted(_observation(5))
        )
    recorder.record_epoch(Stop(ManualTime(0)), _terminal_result())
    records = parse_transcript(recorder.transcript())
    assert [record["kind"] for record in records][9:] == [
        "input.stop",
        "observation",
        "run.finished",
    ]


def test_stop_drain_without_final_observation() -> None:
    recorder = _started_recorder()
    recorder.record_epoch(
        Stop(ManualTime(0)), TerminalResult(None, RunFinished.code(0))
    )
    records = parse_transcript(recorder.transcript())
    assert [record["kind"] for record in records][9:] == [
        "input.stop",
        "run.finished",
    ]


def test_unfreezable_subject_is_a_structured_error() -> None:
    with pytest.raises(TranscriptRecorderError) as caught:
        TranscriptRecorder(
            RUN_ID,
            _configuration(),
            {**SUBJECT, "x-bad": float("nan")},
        )
    assert caught.value.code == "invalid-subject"


def test_invalid_run_id_is_a_structured_error() -> None:
    with pytest.raises(TranscriptRecorderError) as caught:
        TranscriptRecorder("RUN-X", _configuration(), SUBJECT)
    assert caught.value.code == "invalid-run-id"


class _ScriptedAdapter:
    """A fake adapter that answers each call from a scripted result list."""

    def __init__(
        self,
        start_result: StartResult,
        epoch_results: list[EpochResult] | None = None,
    ) -> None:
        self._start_result = start_result
        self._epoch_results = list(epoch_results or [])
        self.dispatched: list[object] = []

    def start(self, run_id: str, configuration: RunConfiguration) -> StartResult:
        return self._start_result

    def dispatch(self, input_event: DispatchInput) -> EpochResult:
        self.dispatched.append(input_event)
        return self._epoch_results.pop(0)

    def advance_clock(self, input_event: ClockAdvance) -> EpochResult:
        self.dispatched.append(input_event)
        return self._epoch_results.pop(0)

    def stop(self, input_event: Stop) -> TerminalResult:
        self.dispatched.append(input_event)
        return cast(TerminalResult, self._epoch_results.pop(0))


def test_run_scripted_records_a_full_run() -> None:
    adapter = _ScriptedAdapter(
        Started(_constraints(), _observation()),
        [
            EpochCompleted(_observation()),
            EpochCompleted(_observation(500)),
            _terminal_result(500),
        ],
    )
    scripted = run_scripted(
        adapter,
        RUN_ID,
        _configuration(),
        SUBJECT,
        (
            TextInput(ManualTime(0), "hello"),
            ClockAdvance(ManualTime(500), 500),
            Stop(ManualTime(500)),
        ),
    )

    records = parse_transcript(scripted.transcript)
    assert records[-1]["kind"] == "run.finished"
    assert type(scripted.result) is TerminalResult
    assert [type(item) for item in adapter.dispatched] == [
        TextInput,
        ClockAdvance,
        Stop,
    ]


def test_run_scripted_returns_on_natural_termination() -> None:
    adapter = _ScriptedAdapter(
        Started(_constraints(), _observation()),
        [_terminal_result()],
    )
    scripted = run_scripted(
        adapter,
        RUN_ID,
        _configuration(),
        SUBJECT,
        (
            TextInput(ManualTime(0), "quit"),
            TextInput(ManualTime(0), "never sent"),
        ),
    )

    assert type(scripted.result) is TerminalResult
    assert len(adapter.dispatched) == 1
    records = parse_transcript(scripted.transcript)
    assert records[-1]["kind"] == "run.finished"


def test_run_scripted_returns_unsupported_start_without_dispatching() -> None:
    unsupported = StartUnsupported(
        RUN_ID,
        _configuration(),
        (),
        "seed",
        "constraint-not-enforced",
        "seed is not enforced",
    )
    adapter = _ScriptedAdapter(unsupported)
    scripted = run_scripted(
        adapter,
        RUN_ID,
        _configuration(),
        SUBJECT,
        (TextInput(ManualTime(0), "never sent"),),
    )

    assert scripted.result is unsupported
    assert adapter.dispatched == []
    records = parse_transcript(scripted.transcript)
    assert records[-1]["kind"] == "run.unsupported"


def test_run_scripted_returns_a_failed_start_without_dispatching() -> None:
    failed = StartFailed(
        RUN_ID,
        _configuration(),
        (),
        AdapterFailure("adapter-start-failed", "boom"),
    )
    adapter = _ScriptedAdapter(failed)
    scripted = run_scripted(
        adapter,
        RUN_ID,
        _configuration(),
        SUBJECT,
        (TextInput(ManualTime(0), "never sent"),),
    )

    assert scripted.result is failed
    assert adapter.dispatched == []
    assert parse_transcript(scripted.transcript)[-1]["kind"] == "run.failed"


def test_run_scripted_returns_a_terminated_start_without_dispatching() -> None:
    terminated = StartTerminated(
        _constraints(), TerminalResult(None, RunFinished.code(0))
    )
    adapter = _ScriptedAdapter(terminated)
    scripted = run_scripted(
        adapter,
        RUN_ID,
        _configuration(),
        SUBJECT,
        (TextInput(ManualTime(0), "never sent"),),
    )

    assert scripted.result is terminated
    assert adapter.dispatched == []
    assert parse_transcript(scripted.transcript)[-1]["kind"] == "run.finished"


def test_run_scripted_without_termination_is_a_structured_error() -> None:
    adapter = _ScriptedAdapter(
        Started(_constraints(), _observation()),
        [EpochCompleted(_observation())],
    )
    with pytest.raises(TranscriptRecorderError) as caught:
        run_scripted(
            adapter,
            RUN_ID,
            _configuration(),
            SUBJECT,
            (TextInput(ManualTime(0), "hello"),),
        )
    assert caught.value.code == "script-not-terminated"


def test_run_scripted_rejects_a_non_tuple_script() -> None:
    adapter = _ScriptedAdapter(Started(_constraints(), _observation()))
    with pytest.raises(TranscriptRecorderError) as caught:
        run_scripted(
            adapter,
            RUN_ID,
            _configuration(),
            SUBJECT,
            [TextInput(ManualTime(0), "list")],  # type: ignore[arg-type]
        )
    assert caught.value.code == "invalid-script"


def test_identical_runs_produce_byte_identical_transcripts() -> None:
    def one_run() -> bytes:
        adapter = _ScriptedAdapter(
            Started(_constraints(), _observation()),
            [EpochCompleted(_observation()), _terminal_result()],
        )
        return run_scripted(
            adapter,
            RUN_ID,
            _configuration(),
            SUBJECT,
            (TextInput(ManualTime(0), "hello"), Stop(ManualTime(0))),
        ).transcript

    assert one_run() == one_run()


_INPUT_KIND_NAMES = {
    "text": "input.text",
    "key": "input.key",
    "resize": "input.resize",
    "clock": "input.clock_advanced",
}


@given(
    epochs=st.lists(
        st.tuples(
            st.sampled_from(sorted(_INPUT_KIND_NAMES)),
            st.integers(min_value=0, max_value=2),
            st.booleans(),
        ),
        max_size=6,
    ),
    final=st.sampled_from(["stop", "natural-exit", "runtime-failure"]),
)
def test_every_generated_lifecycle_shape_round_trips_through_the_codec(
    epochs: list[tuple[str, int, bool]], final: str
) -> None:
    recorder = TranscriptRecorder(RUN_ID, _configuration(), SUBJECT)
    recorder.record_start(Started(_constraints(), _observation()))
    expected = ["run.started", *(["capability.result"] * 7), "observation"]
    now = 0
    for kind, diagnostic_count, with_frame in epochs:
        if kind == "text":
            input_event: TextInput | KeyInput | Resize | ClockAdvance = TextInput(
                ManualTime(now), "t"
            )
        elif kind == "key":
            input_event = KeyInput(ManualTime(now), ("Enter",))
        elif kind == "resize":
            input_event = Resize(ManualTime(now), 100, 30)
        else:
            now += 7
            input_event = ClockAdvance(ManualTime(now), 7)
        diagnostics = tuple(
            Diagnostic(ManualTime(now), f"code-{index}", "m")
            for index in range(diagnostic_count)
        )
        frame = Frame(("line", "line"), 4, 2) if with_frame else None
        recorder.record_epoch(
            input_event,
            EpochCompleted(_observation(now, frame=frame), diagnostics=diagnostics),
        )
        expected += [
            _INPUT_KIND_NAMES[kind],
            *(["diagnostic"] * diagnostic_count),
            "observation",
        ]
    if final == "stop":
        recorder.record_epoch(Stop(ManualTime(now)), _terminal_result(now))
        expected += ["input.stop", "observation", "run.finished"]
    elif final == "natural-exit":
        recorder.record_epoch(TextInput(ManualTime(now), "quit"), _terminal_result(now))
        expected += ["input.text", "observation", "run.finished"]
    else:
        recorder.record_epoch(
            TextInput(ManualTime(now), "crash"),
            TerminalResult(
                None,
                RunFailed(AdapterFailure("adapter-runtime-failed", "boom")),
            ),
        )
        expected += ["input.text", "run.failed"]

    records = parse_transcript(recorder.transcript())

    assert [record["kind"] for record in records] == expected


class _CooperativeApplication:
    """A deterministic in-process fixture subject for integration evidence."""

    def __init__(self) -> None:
        self._count = 0

    def _observation(self, at_ms: int, exited: bool = False) -> Observation:
        return Observation(
            at_ms=ManualTime(at_ms),
            state={"count": self._count},
            events=(),
            ui=UiObservation(
                regions=(Region("main", "document", 0, 0, 80, 24),),
                focus="main",
                cursor=Cursor(0, 0, True),
                mode=None,
            ),
            process=ProcessObservation.exited(ExitStatus("code", 0))
            if exited
            else ProcessObservation.running(),
        )

    def enforce_seed(self, run_id: str, requested: int) -> SeedReceipt:
        return SeedReceipt(run_id, requested, "constructive")

    def enforce_clock(self, run_id: str, requested: ClockConfiguration) -> ClockReceipt:
        return ClockReceipt(run_id, requested, "constructive")

    def enforce_locale(self, run_id: str, requested: str) -> LocaleReceipt:
        return LocaleReceipt(run_id, requested, "constructive")

    def enforce_timezone(self, run_id: str, requested: str) -> TimezoneReceipt:
        return TimezoneReceipt(run_id, requested, "constructive")

    def enforce_terminal(
        self, run_id: str, requested: TerminalConfiguration
    ) -> TerminalReceipt:
        return TerminalReceipt(run_id, requested, "constructive")

    def enforce_filesystem(
        self, run_id: str, requested: FilesystemConfiguration
    ) -> FilesystemReceipt:
        return FilesystemReceipt(run_id, requested, "constructive")

    def enforce_network(
        self, run_id: str, requested: NetworkConfiguration
    ) -> NetworkReceipt:
        return NetworkReceipt(run_id, requested, "constructive")

    def initialize(self) -> EpochCompleted:
        return EpochCompleted(self._observation(0))

    def dispatch(self, input_event: object) -> EpochCompleted:
        self._count += 1
        at_ms = int(input_event.at_ms)  # type: ignore[attr-defined]
        return EpochCompleted(self._observation(at_ms))

    def advance_clock(self, input_event: ClockAdvance) -> EpochCompleted:
        return EpochCompleted(self._observation(int(input_event.at_ms)))

    def stop(self, input_event: Stop) -> TerminalResult:
        return TerminalResult(
            self._observation(int(input_event.at_ms), exited=True),
            RunFinished.code(0),
        )

    def abort(self, input_event: Stop) -> None:
        return None


def test_orchestrated_direct_adapter_run_yields_a_codec_accepted_transcript() -> None:
    from termverify.direct import DirectAdapter

    def one_run() -> bytes:
        adapter = DirectAdapter(_CooperativeApplication())
        scripted = run_scripted(
            adapter,
            RUN_ID,
            _configuration(),
            SUBJECT,
            (
                TextInput(ManualTime(0), "hello"),
                KeyInput(ManualTime(0), ("Enter",)),
                Resize(ManualTime(0), 120, 40),
                ClockAdvance(ManualTime(250), 250),
                Stop(ManualTime(250)),
            ),
        )
        assert type(scripted.result) is TerminalResult
        assert type(scripted.result.outcome) is RunFinished
        return scripted.transcript

    first = one_run()

    records = parse_transcript(first)
    assert [record["kind"] for record in records] == [
        "run.started",
        *(["capability.result"] * 7),
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
    assert first == one_run()
