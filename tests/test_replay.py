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
    Cursor,
    EnforcedConstraints,
    EpochCompleted,
    EpochResult,
    ExitStatus,
    FilesystemConfiguration,
    FilesystemReceipt,
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
from termverify.recorder import ScriptedInput, TranscriptRecorder, run_scripted
from termverify.replay import (
    ReplayError,
    ReplayNotRun,
    ReplayRun,
    replay_transcript,
)
from termverify.transcript import (
    JsonValue,
    parse_transcript,
    serialize_transcript,
)

RUN_ID = "run-replay"

SUBJECT: dict[str, JsonInput] = {
    "format": "termverify.replay-subject/v1",
    "application": {"id": "fixture-app", "version": "1", "build": "b1"},
    "fixture": {"id": "basic", "version": "1"},
    "adapter": {"id": "termverify.direct", "version": "1"},
    "normalizer": {"id": "termverify.identity", "version": "1"},
    "state_schema": {"id": "fixture-state", "version": "1"},
}

OTHER_SUBJECT: dict[str, JsonInput] = {
    **SUBJECT,
    "application": {"id": "other-app", "version": "2", "build": "b2"},
}


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


def _constraints(run_id: str = RUN_ID) -> EnforcedConstraints:
    configuration = _configuration()
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
    state: JsonInput | None = None,
    process: ProcessObservation | None = None,
) -> Observation:
    return Observation(
        at_ms=ManualTime(at_ms),
        state={"count": 0} if state is None else state,
        events=(),
        ui=UiObservation(
            regions=(Region("main", "document", 0, 0, 80, 24),),
            focus="main",
            cursor=Cursor(0, 0, True),
            mode=None,
        ),
        process=process,
    )


def _terminal_result(at_ms: int = 0, exit_code: int = 0) -> TerminalResult:
    return TerminalResult(
        _observation(
            at_ms,
            process=ProcessObservation.exited(ExitStatus("code", exit_code)),
        ),
        RunFinished.code(exit_code),
    )


class _ScriptedAdapter:
    """A fake adapter answering each call from a scripted result list."""

    def __init__(
        self,
        start_result: StartResult,
        epoch_results: list[EpochResult] | None = None,
    ) -> None:
        self._start_result = start_result
        self._epoch_results = list(epoch_results or [])
        self.received: list[ScriptedInput] = []
        self.started_with: tuple[str, RunConfiguration] | None = None

    def start(self, run_id: str, configuration: RunConfiguration) -> StartResult:
        self.started_with = (run_id, configuration)
        return self._start_result

    def dispatch(self, input_event: KeyInput | TextInput | Resize) -> EpochResult:
        self.received.append(input_event)
        return self._epoch_results.pop(0)

    def advance_clock(self, input_event: ClockAdvance) -> EpochResult:
        self.received.append(input_event)
        return self._epoch_results.pop(0)

    def stop(self, input_event: Stop) -> TerminalResult:
        self.received.append(input_event)
        return cast(TerminalResult, self._epoch_results.pop(0))


_SOURCE_INPUTS: tuple[ScriptedInput, ...] = (
    TextInput(ManualTime(0), "hello"),
    KeyInput(ManualTime(0), ("Enter",)),
    Resize(ManualTime(0), 120, 40),
    ClockAdvance(ManualTime(250), 250),
    Stop(ManualTime(250)),
)


def _epoch_results() -> list[EpochResult]:
    return [
        EpochCompleted(_observation()),
        EpochCompleted(_observation()),
        EpochCompleted(_observation()),
        EpochCompleted(_observation(250)),
        _terminal_result(250),
    ]


def _source_transcript() -> bytes:
    adapter = _ScriptedAdapter(
        Started(_constraints(), _observation()), _epoch_results()
    )
    return run_scripted(
        adapter, RUN_ID, _configuration(), SUBJECT, _SOURCE_INPUTS
    ).transcript


def test_a_faithful_replay_is_equivalent_and_re_dispatches_every_input() -> None:
    source = _source_transcript()
    adapter = _ScriptedAdapter(
        Started(_constraints(), _observation()), _epoch_results()
    )

    outcome = replay_transcript(source, adapter, RUN_ID, SUBJECT)

    assert type(outcome) is ReplayRun
    assert outcome.comparison.equivalent is True
    assert outcome.subject_matches_source is True
    assert outcome.dispatched_inputs == outcome.source_inputs == 5
    assert outcome.transcript == source
    assert adapter.received == list(_SOURCE_INPUTS)
    assert adapter.started_with == (RUN_ID, _configuration())


def test_a_divergent_subject_produces_the_expected_structured_divergence() -> None:
    source = _source_transcript()
    results = _epoch_results()
    results[1] = EpochCompleted(_observation(state={"count": 7}))
    adapter = _ScriptedAdapter(Started(_constraints(), _observation()), results)

    outcome = replay_transcript(source, adapter, RUN_ID, SUBJECT)

    assert type(outcome) is ReplayRun
    assert outcome.comparison.equivalent is False
    divergence = outcome.comparison.divergences[0]
    assert divergence.sequence == 12
    assert divergence.left_kind == divergence.right_kind == "observation"
    assert [d.path for d in divergence.differences] == ["payload.state.count"]


def test_a_differing_caller_subject_is_reported_not_enforced() -> None:
    source = _source_transcript()
    adapter = _ScriptedAdapter(
        Started(_constraints(), _observation()), _epoch_results()
    )

    outcome = replay_transcript(source, adapter, RUN_ID, OTHER_SUBJECT)

    assert type(outcome) is ReplayRun
    assert outcome.subject_matches_source is False
    assert outcome.comparison.equivalent is False
    started_payload = parse_transcript(outcome.transcript)[0]["payload"]
    assert cast(dict[str, JsonValue], started_payload)["subject"] == OTHER_SUBJECT


def test_an_early_terminating_replay_is_disclosed() -> None:
    source = _source_transcript()
    adapter = _ScriptedAdapter(
        Started(_constraints(), _observation()),
        [_terminal_result(0)],
    )

    outcome = replay_transcript(source, adapter, RUN_ID, SUBJECT)

    assert type(outcome) is ReplayRun
    assert outcome.dispatched_inputs == 1
    assert outcome.source_inputs == 5
    assert outcome.comparison.equivalent is False
    assert len(adapter.received) == 1


def _naturally_exiting_source() -> bytes:
    recorder = TranscriptRecorder(RUN_ID, _configuration(), SUBJECT)
    recorder.record_start(Started(_constraints(), _observation()))
    recorder.record_epoch(TextInput(ManualTime(0), "quit"), _terminal_result(0))
    return recorder.transcript()


def test_a_replay_that_never_terminates_is_a_structured_error() -> None:
    source = _naturally_exiting_source()
    adapter = _ScriptedAdapter(
        Started(_constraints(), _observation()),
        [EpochCompleted(_observation())],
    )

    with pytest.raises(ReplayError) as caught:
        replay_transcript(source, adapter, RUN_ID, SUBJECT)
    assert caught.value.code == "replay-not-terminated"


def test_a_replay_refused_at_start_is_an_honest_replay_run() -> None:
    source = _source_transcript()
    refused = StartUnsupported(
        RUN_ID,
        _configuration(),
        (),
        "seed",
        "constraint-not-enforced",
        "seed is not enforced",
    )
    adapter = _ScriptedAdapter(refused)

    outcome = replay_transcript(source, adapter, RUN_ID, SUBJECT)

    assert type(outcome) is ReplayRun
    assert outcome.dispatched_inputs == 0
    assert outcome.comparison.equivalent is False
    assert parse_transcript(outcome.transcript)[-1]["kind"] == "run.unsupported"


def test_an_unsupported_start_source_replays_nothing() -> None:
    recorder = TranscriptRecorder(RUN_ID, _configuration(), SUBJECT)
    recorder.record_start(
        StartUnsupported(
            RUN_ID,
            _configuration(),
            (),
            "seed",
            "constraint-unsupported",
            "seed is unsupported",
        )
    )
    source = recorder.transcript()
    adapter = _ScriptedAdapter(Started(_constraints(), _observation()))

    outcome = replay_transcript(source, adapter, RUN_ID, SUBJECT)

    assert type(outcome) is ReplayNotRun
    assert outcome.source_kind == "run.unsupported"
    assert adapter.started_with is None


def test_a_failed_start_source_replays_nothing() -> None:
    recorder = TranscriptRecorder(RUN_ID, _configuration(), SUBJECT)
    recorder.record_start(
        StartFailed(
            RUN_ID,
            _configuration(),
            (),
            AdapterFailure("adapter-start-failed", "boom"),
        )
    )
    source = recorder.transcript()
    adapter = _ScriptedAdapter(Started(_constraints(), _observation()))

    outcome = replay_transcript(source, adapter, RUN_ID, SUBJECT)

    assert type(outcome) is ReplayNotRun
    assert outcome.source_kind == "run.failed"
    assert adapter.started_with is None


def test_a_runtime_failure_source_is_replayable() -> None:
    recorder = TranscriptRecorder(RUN_ID, _configuration(), SUBJECT)
    recorder.record_start(Started(_constraints(), _observation()))
    recorder.record_epoch(
        TextInput(ManualTime(0), "crash"),
        TerminalResult(
            None,
            RunFailed(AdapterFailure("adapter-runtime-failed", "boom")),
        ),
    )
    source = recorder.transcript()
    adapter = _ScriptedAdapter(
        Started(_constraints(), _observation()),
        [
            TerminalResult(
                None,
                RunFailed(AdapterFailure("adapter-runtime-failed", "boom")),
            )
        ],
    )

    outcome = replay_transcript(source, adapter, RUN_ID, SUBJECT)

    assert type(outcome) is ReplayRun
    assert outcome.comparison.equivalent is True


def test_a_start_terminated_source_is_replayable() -> None:
    recorder = TranscriptRecorder(RUN_ID, _configuration(), SUBJECT)
    recorder.record_start(
        StartTerminated(_constraints(), TerminalResult(None, RunFinished.code(0)))
    )
    source = recorder.transcript()
    adapter = _ScriptedAdapter(
        StartTerminated(_constraints(), TerminalResult(None, RunFinished.code(0)))
    )

    outcome = replay_transcript(source, adapter, RUN_ID, SUBJECT)

    assert type(outcome) is ReplayRun
    assert outcome.source_inputs == 0
    assert outcome.comparison.equivalent is True


def test_an_invalid_source_is_a_structured_error() -> None:
    adapter = _ScriptedAdapter(Started(_constraints(), _observation()))
    with pytest.raises(ReplayError) as caught:
        replay_transcript(b"junk\n", adapter, RUN_ID, SUBJECT)
    assert caught.value.code == "invalid-source"


def test_a_non_bytes_source_is_a_structured_error() -> None:
    adapter = _ScriptedAdapter(Started(_constraints(), _observation()))
    with pytest.raises(ReplayError) as caught:
        replay_transcript("junk", adapter, RUN_ID, SUBJECT)  # type: ignore[arg-type]
    assert caught.value.code == "invalid-source"


@given(epochs=st.lists(st.sampled_from(["text", "key", "resize", "clock"]), max_size=5))
def test_property_a_faithful_replay_of_any_input_sequence_is_equivalent(
    epochs: list[str],
) -> None:
    inputs: list[ScriptedInput] = []
    results: list[EpochResult] = []
    now = 0
    for kind in epochs:
        if kind == "text":
            inputs.append(TextInput(ManualTime(now), "t"))
        elif kind == "key":
            inputs.append(KeyInput(ManualTime(now), ("Enter",)))
        elif kind == "resize":
            inputs.append(Resize(ManualTime(now), 100, 30))
        else:
            now += 5
            inputs.append(ClockAdvance(ManualTime(now), 5))
        results.append(EpochCompleted(_observation(now)))
    inputs.append(Stop(ManualTime(now)))
    results.append(_terminal_result(now))

    source = run_scripted(
        _ScriptedAdapter(Started(_constraints(), _observation()), list(results)),
        RUN_ID,
        _configuration(),
        SUBJECT,
        tuple(inputs),
    ).transcript
    replay_adapter = _ScriptedAdapter(
        Started(_constraints(), _observation()), list(results)
    )

    outcome = replay_transcript(source, replay_adapter, RUN_ID, SUBJECT)

    assert type(outcome) is ReplayRun
    assert outcome.comparison.equivalent is True
    assert outcome.transcript == source
    assert replay_adapter.received == inputs


def test_an_allow_list_source_reconstructs_the_configuration_exactly() -> None:
    """Allow-list network configs are codec-valid but receipt-refused.

    No shipped adapter can produce enforced allow-list receipts (the
    receipt contract fails them closed), so a source carrying one can only
    be hand-crafted. The replay engine must still reconstruct the
    configuration exactly and hand it to the adapter, whose honest refusal
    becomes the recorded, compared outcome.
    """
    allow_list_network: dict[str, JsonValue] = {
        "mode": "allow-list",
        "allowed": [{"host": "example.test", "port": 443}],
    }
    records = [dict(record) for record in parse_transcript(_source_transcript())]
    started = dict(records[0])
    payload = dict(cast(dict[str, JsonValue], started["payload"]))
    config = dict(cast(dict[str, JsonValue], payload["config"]))
    config["network"] = allow_list_network
    payload["config"] = config
    started["payload"] = payload
    records[0] = started
    network_capability = dict(records[7])
    network_payload = dict(cast(dict[str, JsonValue], network_capability["payload"]))
    network_payload["effective"] = allow_list_network
    network_capability["payload"] = network_payload
    records[7] = network_capability
    source = serialize_transcript(records)

    expected_configuration = RunConfiguration(
        seed=42,
        clock=ClockConfiguration(initial_ms=0),
        locale="en-US",
        timezone="UTC",
        terminal=TerminalConfiguration(columns=80, rows=24, capabilities=()),
        filesystem=FilesystemConfiguration(root_id="fixture-root"),
        network=NetworkConfiguration.allow_list((("example.test", 443),)),
    )
    refused = StartUnsupported(
        RUN_ID,
        expected_configuration,
        (),
        "seed",
        "constraint-not-enforced",
        "seed is not enforced",
    )
    replay_adapter = _ScriptedAdapter(refused)

    outcome = replay_transcript(source, replay_adapter, RUN_ID, SUBJECT)

    assert type(outcome) is ReplayRun
    assert replay_adapter.started_with == (RUN_ID, expected_configuration)
    assert outcome.comparison.equivalent is False
    assert parse_transcript(outcome.transcript)[-1]["kind"] == "run.unsupported"


class _CooperativePorts:
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


class _CooperativeApplication(_CooperativePorts):
    """A deterministic in-process fixture subject for integration evidence."""

    def __init__(self, count_step: int = 1) -> None:
        self._count = 0
        self._step = count_step

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

    def initialize(self) -> EpochCompleted:
        return EpochCompleted(self._observation(0))

    def dispatch(self, input_event: KeyInput | TextInput | Resize) -> EpochCompleted:
        self._count += self._step
        return EpochCompleted(self._observation(int(input_event.at_ms)))

    def advance_clock(self, input_event: ClockAdvance) -> EpochCompleted:
        return EpochCompleted(self._observation(int(input_event.at_ms)))

    def stop(self, input_event: Stop) -> TerminalResult:
        return TerminalResult(
            self._observation(int(input_event.at_ms), exited=True),
            RunFinished.code(0),
        )

    def abort(self, input_event: Stop) -> None:
        return None


def test_a_direct_adapter_run_replays_to_an_equivalent_transcript() -> None:
    from termverify.direct import DirectAdapter

    source = run_scripted(
        DirectAdapter(_CooperativeApplication()),
        RUN_ID,
        _configuration(),
        SUBJECT,
        _SOURCE_INPUTS,
    ).transcript

    outcome = replay_transcript(
        source, DirectAdapter(_CooperativeApplication()), RUN_ID, SUBJECT
    )

    assert type(outcome) is ReplayRun
    assert outcome.comparison.equivalent is True
    assert outcome.subject_matches_source is True
    assert outcome.transcript == source


def test_a_perturbed_direct_subject_yields_the_expected_divergence() -> None:
    from termverify.direct import DirectAdapter

    source = run_scripted(
        DirectAdapter(_CooperativeApplication(count_step=1)),
        RUN_ID,
        _configuration(),
        SUBJECT,
        _SOURCE_INPUTS,
    ).transcript

    outcome = replay_transcript(
        source,
        DirectAdapter(_CooperativeApplication(count_step=2)),
        RUN_ID,
        SUBJECT,
    )

    assert type(outcome) is ReplayRun
    assert outcome.comparison.equivalent is False
    first = outcome.comparison.divergences[0]
    assert first.sequence == 10
    assert first.left_kind == first.right_kind == "observation"
    assert [d.path for d in first.differences] == ["payload.state.count"]


def test_a_source_with_undispatchable_inputs_fails_closed() -> None:
    source_records = parse_transcript(_source_transcript())
    mutable = [dict(record) for record in source_records]
    clipboard_payload: dict[str, JsonValue] = {"at_ms": 0, "text": "clip"}
    mutable[9] = {
        **mutable[9],
        "kind": "input.clipboard_set",
        "payload": clipboard_payload,
    }
    source = serialize_transcript(mutable)
    adapter = _ScriptedAdapter(
        Started(_constraints(), _observation()), _epoch_results()
    )

    with pytest.raises(ReplayError) as caught:
        replay_transcript(source, adapter, RUN_ID, SUBJECT)
    assert caught.value.code == "replay-unsupported-input"
    assert adapter.started_with is None
