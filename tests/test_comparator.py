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
    Diagnostic,
    EnforcedConstraints,
    EpochCompleted,
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
    StartUnsupported,
    Stop,
    TerminalConfiguration,
    TerminalReceipt,
    TerminalResult,
    TextInput,
    TimezoneReceipt,
    UiObservation,
)
from termverify.comparator import (
    ComparisonVerdict,
    TranscriptInputError,
    compare_transcripts,
    render_report,
)
from termverify.recorder import TranscriptRecorder
from termverify.transcript import (
    JsonValue,
    parse_transcript,
    serialize_transcript,
)

RUN_ID = "run-compare"

SUBJECT: dict[str, JsonInput] = {
    "format": "termverify.replay-subject/v1",
    "application": {"id": "fixture-app", "version": "1", "build": "b1"},
    "fixture": {"id": "basic", "version": "1"},
    "adapter": {"id": "termverify.direct", "version": "1"},
    "normalizer": {"id": "termverify.identity", "version": "1"},
    "state_schema": {"id": "fixture-state", "version": "1"},
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


def _transcript(
    run_id: str = RUN_ID,
    *,
    text: str = "hello",
    state: JsonInput | None = None,
    extra_epoch: bool = False,
    exit_code: int = 0,
) -> bytes:
    recorder = TranscriptRecorder(run_id, _configuration(), SUBJECT)
    recorder.record_start(Started(_constraints(run_id), _observation()))
    recorder.record_epoch(
        TextInput(ManualTime(0), text),
        EpochCompleted(_observation(state=state)),
    )
    if extra_epoch:
        recorder.record_epoch(
            KeyInput(ManualTime(0), ("Enter",)), EpochCompleted(_observation())
        )
    recorder.record_epoch(
        Stop(ManualTime(0)),
        TerminalResult(
            _observation(
                process=ProcessObservation.exited(ExitStatus("code", exit_code))
            ),
            RunFinished.code(exit_code),
        ),
    )
    return recorder.transcript()


def test_a_transcript_is_equivalent_to_itself() -> None:
    transcript = _transcript()

    verdict = compare_transcripts(transcript, transcript)

    assert type(verdict) is ComparisonVerdict
    assert verdict.equivalent is True
    assert verdict.divergences == ()
    assert verdict.left_record_count == verdict.right_record_count


def test_run_id_is_the_only_identity_exclusion() -> None:
    verdict = compare_transcripts(_transcript("run-compare"), _transcript("run-other"))

    assert verdict.equivalent is True
    assert verdict.divergences == ()


def test_a_payload_difference_is_located_by_sequence_kind_and_member() -> None:
    verdict = compare_transcripts(_transcript(text="hello"), _transcript(text="world"))

    assert verdict.equivalent is False
    assert len(verdict.divergences) == 1
    divergence = verdict.divergences[0]
    assert divergence.sequence == 9
    assert divergence.left_kind == "input.text"
    assert divergence.right_kind == "input.text"
    assert len(divergence.differences) == 1
    difference = divergence.differences[0]
    assert difference.path == "payload.text"
    assert difference.left == '"hello"'
    assert difference.right == '"world"'
    assert verdict.first_divergence_sequence == 9


def test_an_invalid_left_side_is_a_structured_input_error() -> None:
    with pytest.raises(TranscriptInputError) as caught:
        compare_transcripts(b"not a transcript\n", _transcript())
    assert caught.value.side == "left"


def test_an_invalid_right_side_is_a_structured_input_error() -> None:
    with pytest.raises(TranscriptInputError) as caught:
        compare_transcripts(_transcript(), b"")
    assert caught.value.side == "right"


def test_a_record_count_difference_is_a_divergence() -> None:
    verdict = compare_transcripts(_transcript(), _transcript(extra_epoch=True))

    assert verdict.equivalent is False
    assert verdict.left_record_count == 14
    assert verdict.right_record_count == 16
    missing = [
        divergence for divergence in verdict.divergences if divergence.left_kind is None
    ]
    assert missing
    assert all(
        divergence.right_kind is not None and divergence.differences == ()
        for divergence in missing
    )


def _mutated(transcript: bytes, sequence: int, **changes: object) -> bytes:
    """Reserialize *transcript* with envelope/payload members replaced.

    Mutations pass back through the strict codec, so every mutated copy
    used in a comparison is itself a valid transcript.
    """
    records = parse_transcript(transcript)
    record = dict(records[sequence])
    payload_changes = changes.pop("payload", None)
    if payload_changes is not None:
        payload = dict(cast(dict[str, JsonValue], record["payload"]))
        payload.update(cast(dict[str, JsonValue], payload_changes))
        record["payload"] = payload
    record.update(cast(dict[str, JsonValue], changes))
    mutable = [dict(item) for item in records]
    mutable[sequence] = record
    return serialize_transcript(mutable)


def _full_transcript() -> bytes:
    """One valid transcript touching every input kind the recorder emits.

    The two v1 input kinds the slice-1 recorder cannot emit (mouse and
    clipboard) get their divergence coverage through directly serialized
    transcripts; see ``_replaced``.
    """
    recorder = TranscriptRecorder(RUN_ID, _configuration(), SUBJECT)
    recorder.record_start(Started(_constraints(), _observation()))
    recorder.record_epoch(
        TextInput(ManualTime(0), "hello"),
        EpochCompleted(
            _observation(),
            diagnostics=(Diagnostic(ManualTime(0), "note", "detail"),),
        ),
    )
    recorder.record_epoch(
        KeyInput(ManualTime(0), ("Enter",)), EpochCompleted(_observation())
    )
    recorder.record_epoch(
        Resize(ManualTime(0), 100, 30), EpochCompleted(_observation())
    )
    recorder.record_epoch(
        ClockAdvance(ManualTime(50), 50), EpochCompleted(_observation(50))
    )
    recorder.record_epoch(
        Stop(ManualTime(50)),
        TerminalResult(
            _observation(50, process=ProcessObservation.exited(ExitStatus("code", 0))),
            RunFinished.code(0),
        ),
    )
    return recorder.transcript()


def _transcript_with_delta(delta_ms: int) -> bytes:
    recorder = TranscriptRecorder(RUN_ID, _configuration(), SUBJECT)
    recorder.record_start(Started(_constraints(), _observation()))
    recorder.record_epoch(
        ClockAdvance(ManualTime(delta_ms), delta_ms),
        EpochCompleted(_observation(delta_ms)),
    )
    recorder.record_epoch(
        Stop(ManualTime(delta_ms)),
        TerminalResult(
            _observation(
                delta_ms,
                process=ProcessObservation.exited(ExitStatus("code", 0)),
            ),
            RunFinished.code(0),
        ),
    )
    return recorder.transcript()


def _unsupported_transcript(message: str = "seed is unsupported") -> bytes:
    recorder = TranscriptRecorder(RUN_ID, _configuration(), SUBJECT)
    recorder.record_start(
        StartUnsupported(
            RUN_ID, _configuration(), (), "seed", "constraint-unsupported", message
        )
    )
    return recorder.transcript()


def _failed_transcript(message: str = "boom") -> bytes:
    recorder = TranscriptRecorder(RUN_ID, _configuration(), SUBJECT)
    recorder.record_start(Started(_constraints(), _observation()))
    recorder.record_epoch(
        TextInput(ManualTime(0), "crash"),
        TerminalResult(
            None,
            RunFailed(AdapterFailure("adapter-runtime-failed", message)),
        ),
    )
    return recorder.transcript()


_FULL = _full_transcript()

_KIND_MUTATIONS: dict[str, tuple[bytes, bytes, str]] = {
    "run.started": (
        _FULL,
        _mutated(
            _FULL,
            0,
            payload={
                "subject": {
                    **cast(dict[str, JsonValue], SUBJECT),
                    "fixture": {"id": "altered", "version": "1"},
                }
            },
        ),
        "payload.subject.fixture.id",
    ),
    "capability.result": (
        _FULL,
        _mutated(_FULL, 3, payload={"tier": "os"}),
        "payload.tier",
    ),
    "observation": (
        _FULL,
        _mutated(_FULL, 8, payload={"state": {"count": 99}}),
        "payload.state.count",
    ),
    "input.text": (
        _FULL,
        _mutated(_FULL, 9, payload={"text": "world"}),
        "payload.text",
    ),
    "diagnostic": (
        _FULL,
        _mutated(_FULL, 10, payload={"message": "other"}),
        "payload.message",
    ),
    "input.key": (
        _FULL,
        _mutated(_FULL, 12, payload={"keys": ["Escape"]}),
        "payload.keys[0]",
    ),
    "input.resize": (
        _FULL,
        _mutated(_FULL, 14, payload={"columns": 90}),
        "payload.columns",
    ),
    "input.clock_advanced": (
        _transcript_with_delta(50),
        _transcript_with_delta(75),
        "payload.at_ms",
    ),
    "input.stop": (
        _FULL,
        _mutated(_FULL, 18, payload={"x-note": "annotated"}),
        "payload.x-note",
    ),
    "run.finished": (
        _transcript(exit_code=0),
        _transcript(exit_code=3),
        "payload.exit.value",
    ),
    "run.failed": (
        _failed_transcript("boom"),
        _failed_transcript("bust"),
        "payload.error.message",
    ),
    "run.unsupported": (
        _unsupported_transcript("seed is unsupported"),
        _unsupported_transcript("seed probe failed"),
        "payload.message",
    ),
}


@pytest.mark.parametrize("kind", sorted(_KIND_MUTATIONS))
def test_a_divergence_is_detected_for_every_record_kind(kind: str) -> None:
    left, right, expected_path = _KIND_MUTATIONS[kind]

    verdict = compare_transcripts(left, right)

    assert verdict.equivalent is False
    matching = [
        divergence
        for divergence in verdict.divergences
        if divergence.left_kind == kind or divergence.right_kind == kind
    ]
    assert matching, verdict.divergences
    paths = [
        difference.path
        for divergence in matching
        for difference in divergence.differences
    ]
    assert expected_path in paths


def test_an_envelope_only_difference_is_a_divergence() -> None:
    left = _FULL
    right = _mutated(_FULL, 9, id="record-alt")

    verdict = compare_transcripts(left, right)

    assert verdict.equivalent is False
    assert len(verdict.divergences) == 1
    divergence = verdict.divergences[0]
    assert divergence.sequence == 9
    assert [difference.path for difference in divergence.differences] == ["id"]


def test_symmetry_mirrors_left_and_right() -> None:
    left = _FULL
    right = _mutated(_FULL, 9, payload={"text": "world"})

    forward = compare_transcripts(left, right)
    backward = compare_transcripts(right, left)

    assert forward.equivalent is backward.equivalent is False
    assert len(forward.divergences) == len(backward.divergences) == 1
    forward_difference = forward.divergences[0].differences[0]
    backward_difference = backward.divergences[0].differences[0]
    assert forward_difference.path == backward_difference.path
    assert forward_difference.left == backward_difference.right
    assert forward_difference.right == backward_difference.left


_EPOCH_SPECS = st.lists(
    st.tuples(
        st.sampled_from(["text", "key", "resize", "clock"]),
        st.text(
            alphabet=st.characters(codec="ascii", categories=("L", "N")),
            max_size=8,
        ),
    ),
    max_size=5,
)


def _generated_transcript(epochs: list[tuple[str, str]], run_id: str = RUN_ID) -> bytes:
    recorder = TranscriptRecorder(run_id, _configuration(), SUBJECT)
    recorder.record_start(Started(_constraints(run_id), _observation()))
    now = 0
    for kind, token in epochs:
        if kind == "text":
            input_event: TextInput | KeyInput | Resize | ClockAdvance = TextInput(
                ManualTime(now), token
            )
        elif kind == "key":
            input_event = KeyInput(ManualTime(now), ("Enter",))
        elif kind == "resize":
            input_event = Resize(ManualTime(now), 100 + len(token), 30)
        else:
            now += 5
            input_event = ClockAdvance(ManualTime(now), 5)
        recorder.record_epoch(
            input_event,
            EpochCompleted(_observation(now, state={"token": token})),
        )
    recorder.record_epoch(
        Stop(ManualTime(now)),
        TerminalResult(
            _observation(now, process=ProcessObservation.exited(ExitStatus("code", 0))),
            RunFinished.code(0),
        ),
    )
    return recorder.transcript()


@given(epochs=_EPOCH_SPECS)
def test_equivalence_is_reflexive(epochs: list[tuple[str, str]]) -> None:
    transcript = _generated_transcript(epochs)
    verdict = compare_transcripts(transcript, transcript)
    assert verdict.equivalent is True
    assert verdict.divergences == ()


@given(epochs=_EPOCH_SPECS)
def test_equivalence_is_run_id_insensitive(
    epochs: list[tuple[str, str]],
) -> None:
    verdict = compare_transcripts(
        _generated_transcript(epochs, "run-one"),
        _generated_transcript(epochs, "run-two"),
    )
    assert verdict.equivalent is True


@given(epochs=_EPOCH_SPECS, other=_EPOCH_SPECS)
def test_comparison_is_symmetric(
    epochs: list[tuple[str, str]], other: list[tuple[str, str]]
) -> None:
    left = _generated_transcript(epochs)
    right = _generated_transcript(other)

    forward = compare_transcripts(left, right)
    backward = compare_transcripts(right, left)

    assert forward.equivalent is backward.equivalent
    assert [d.sequence for d in forward.divergences] == [
        d.sequence for d in backward.divergences
    ]
    for forward_divergence, backward_divergence in zip(
        forward.divergences, backward.divergences, strict=True
    ):
        assert forward_divergence.left_kind == backward_divergence.right_kind
        assert forward_divergence.right_kind == backward_divergence.left_kind
        assert [
            (difference.path, difference.left, difference.right)
            for difference in forward_divergence.differences
        ] == [
            (difference.path, difference.right, difference.left)
            for difference in backward_divergence.differences
        ]


def test_the_reproduced_glyphwright_transcript_is_self_equivalent() -> None:
    from test_recorder_conformance import reproduce_spike_transcript

    _, reproduced = reproduce_spike_transcript()
    verdict = compare_transcripts(reproduced, reproduced)
    assert verdict.equivalent is True
    assert verdict.left_record_count == 28


def test_mutated_glyphwright_copies_diverge_where_mutated() -> None:
    from test_recorder_conformance import reproduce_spike_transcript

    _, reproduced = reproduce_spike_transcript()
    mutations: list[tuple[int, dict[str, JsonValue], str]] = [
        (9, {"text": "peek"}, "payload.text"),
        (14, {"message": "changed"}, "payload.message"),
        (21, {"columns": 121}, "payload.columns"),
    ]
    for sequence, payload_changes, expected_path in mutations:
        verdict = compare_transcripts(
            reproduced,
            _mutated(reproduced, sequence, payload=payload_changes),
        )
        assert verdict.equivalent is False
        assert verdict.first_divergence_sequence == sequence
        assert [
            difference.path
            for divergence in verdict.divergences
            for difference in divergence.differences
        ] == [expected_path]


def test_report_is_deterministic_for_equal_verdicts() -> None:
    left = _FULL
    right = _mutated(_FULL, 9, payload={"text": "world"})

    first = render_report(compare_transcripts(left, right))
    second = render_report(compare_transcripts(left, right))

    assert first == second
    assert first.encode("utf-8") == second.encode("utf-8")


def test_equivalent_report_states_the_verdict_and_counts() -> None:
    report = render_report(compare_transcripts(_FULL, _FULL))

    assert "verdict: equivalent" in report
    assert "left records: 21" in report
    assert "right records: 21" in report


def test_divergent_report_locates_the_first_divergence() -> None:
    report = render_report(
        compare_transcripts(_FULL, _mutated(_FULL, 9, payload={"text": "world"}))
    )

    assert "verdict: divergent" in report
    assert "first at seq 9" in report
    assert "payload.text" in report
    assert '"hello"' in report
    assert '"world"' in report


def _replaced(
    transcript: bytes, sequence: int, kind: str, payload: dict[str, JsonValue]
) -> bytes:
    """Reserialize *transcript* with one record's kind and payload swapped.

    Used for the two v1 input kinds the slice-1 recorder cannot emit
    (`input.mouse`, `input.clipboard_set`): the comparator's contract is
    transcript bytes, so valid transcripts carrying them are built through
    the strict serializer directly.
    """
    records = [dict(item) for item in parse_transcript(transcript)]
    record = dict(records[sequence])
    record["kind"] = kind
    record["payload"] = payload
    records[sequence] = record
    return serialize_transcript(records)


def test_a_mouse_input_divergence_is_detected() -> None:
    left = _replaced(
        _FULL,
        9,
        "input.mouse",
        {"at_ms": 0, "action": "press", "column": 1, "row": 1, "button": "left"},
    )
    right = _replaced(
        _FULL,
        9,
        "input.mouse",
        {"at_ms": 0, "action": "press", "column": 1, "row": 1, "button": "right"},
    )

    verdict = compare_transcripts(left, right)

    assert verdict.equivalent is False
    divergence = verdict.divergences[0]
    assert divergence.left_kind == divergence.right_kind == "input.mouse"
    assert [d.path for d in divergence.differences] == ["payload.button"]


def test_a_clipboard_input_divergence_is_detected() -> None:
    left = _replaced(_FULL, 9, "input.clipboard_set", {"at_ms": 0, "text": "alpha"})
    right = _replaced(_FULL, 9, "input.clipboard_set", {"at_ms": 0, "text": "beta"})

    verdict = compare_transcripts(left, right)

    assert verdict.equivalent is False
    divergence = verdict.divergences[0]
    assert divergence.left_kind == divergence.right_kind == "input.clipboard_set"
    assert [d.path for d in divergence.differences] == ["payload.text"]


def test_both_sides_invalid_reports_the_left_side_first() -> None:
    with pytest.raises(TranscriptInputError) as caught:
        compare_transcripts(b"", b"")
    assert caught.value.side == "left"


def test_truncation_discloses_the_exact_hidden_byte_count() -> None:
    long_text = "é" * 200
    report = render_report(
        compare_transcripts(_FULL, _mutated(_FULL, 9, payload={"text": long_text}))
    )

    assert "(+283 bytes)" in report


def test_report_bounds_long_member_values() -> None:
    long_text = "x" * 400
    report = render_report(
        compare_transcripts(_FULL, _mutated(_FULL, 9, payload={"text": long_text}))
    )

    assert "bytes)" in report
    assert long_text not in report


def test_report_renders_missing_records() -> None:
    report = render_report(
        compare_transcripts(_transcript(), _transcript(extra_epoch=True))
    )

    assert "missing on the left side" in report


def test_first_divergence_sequence_is_none_when_equivalent() -> None:
    verdict = compare_transcripts(_FULL, _FULL)
    assert verdict.first_divergence_sequence is None


def test_a_type_difference_is_a_divergence() -> None:
    left = _transcript(state={"count": 0})
    right = _transcript(state={"count": "0"})

    verdict = compare_transcripts(left, right)

    assert verdict.equivalent is False
    difference = verdict.divergences[0].differences[0]
    assert difference.path == "payload.state.count"
    assert difference.left == "0"
    assert difference.right == '"0"'


def test_a_list_length_difference_is_one_divergent_member() -> None:
    left = _transcript(state={"items": [1]})
    right = _transcript(state={"items": [1, 2]})

    verdict = compare_transcripts(left, right)

    assert verdict.equivalent is False
    difference = verdict.divergences[0].differences[0]
    assert difference.path == "payload.state.items"
    assert difference.left == "[1]"
    assert difference.right == "[1,2]"


def test_an_envelope_member_absent_on_one_side_is_a_divergence() -> None:
    annotated = _mutated(_FULL, 9, **{"x-extra": "note"})

    forward = compare_transcripts(_FULL, annotated)
    backward = compare_transcripts(annotated, _FULL)

    assert forward.equivalent is backward.equivalent is False
    forward_difference = forward.divergences[0].differences[0]
    assert forward_difference.path == "x-extra"
    assert forward_difference.left is None
    assert forward_difference.right == '"note"'
    backward_difference = backward.divergences[0].differences[0]
    assert backward_difference.left == '"note"'
    assert backward_difference.right is None


def test_non_bytes_input_is_a_structured_input_error() -> None:
    with pytest.raises(TranscriptInputError) as caught:
        compare_transcripts("text", _transcript())  # type: ignore[arg-type]
    assert caught.value.side == "left"


def test_report_renders_records_missing_on_the_right_side() -> None:
    report = render_report(
        compare_transcripts(_transcript(extra_epoch=True), _transcript())
    )

    assert "missing on the right side" in report


def test_report_rejects_non_verdict_values() -> None:
    with pytest.raises(TypeError):
        render_report(None)  # type: ignore[arg-type]
