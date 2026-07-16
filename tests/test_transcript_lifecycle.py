from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import cast

import pytest
from hypothesis import given
from hypothesis import strategies as st

from termverify.transcript import (
    JsonValue,
    TranscriptValidationError,
    parse_transcript,
    serialize_transcript,
)

FIXTURES = Path("tests/fixtures/transcripts/v1")
BASIC = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())


def _reindex(records: list[dict[str, JsonValue]]) -> list[dict[str, JsonValue]]:
    for sequence, record in enumerate(records):
        record["id"] = f"record-{sequence:03d}"
        record["seq"] = sequence
    return records


def _failed_terminal(code: str = "adapter-runtime-failed") -> dict[str, JsonValue]:
    terminal = deepcopy(BASIC[-1])
    terminal["kind"] = "run.failed"
    terminal["payload"] = {"error": {"code": code, "message": "synthetic"}}
    return terminal


def _diagnostic() -> dict[str, JsonValue]:
    record = deepcopy(BASIC[9])
    record["kind"] = "diagnostic"
    record["payload"] = {
        "at_ms": 0,
        "code": "synthetic",
        "message": "synthetic",
    }
    return record


@pytest.mark.parametrize(
    "name",
    [
        "basic.jsonl",
        "failed-before-capabilities.jsonl",
        "finished-after-stop.jsonl",
        "unsupported-network.jsonl",
    ],
)
def test_canonical_outcome_fixture_round_trips_byte_for_byte(name: str) -> None:
    fixture = (FIXTURES / "valid" / name).read_bytes()

    assert serialize_transcript(parse_transcript(fixture)) == fixture


@pytest.mark.parametrize(
    ("name", "message"),
    [
        ("idle-observation.jsonl", "idle"),
        ("input-after-stop.jsonl", "after input.stop"),
        ("missing-readiness.jsonl", "initial readiness"),
        ("overlapping-inputs.jsonl", "input epoch"),
    ],
)
def test_canonical_invalid_lifecycle_fixture_is_rejected(
    name: str, message: str
) -> None:
    with pytest.raises(TranscriptValidationError, match=message):
        parse_transcript((FIXTURES / "invalid" / name).read_bytes())


@st.composite
def _legal_execution_transcripts(
    draw: st.DrawFn,
) -> list[dict[str, JsonValue]]:
    epoch_count = draw(st.integers(min_value=0, max_value=8))
    diagnostics = draw(
        st.lists(
            st.integers(min_value=0, max_value=2),
            min_size=epoch_count,
            max_size=epoch_count,
        )
    )
    stop = draw(st.booleans())
    close_final_epoch = draw(st.booleans())
    fail = draw(st.booleans())

    records = deepcopy(BASIC[:9])
    for index in range(epoch_count):
        input_record = deepcopy(BASIC[9])
        input_payload = cast(dict[str, JsonValue], input_record["payload"])
        input_payload["text"] = f"input-{index}"
        records.append(input_record)
        records.extend(_diagnostic() for _ in range(diagnostics[index]))
        is_final_epoch = index == epoch_count - 1 and not stop
        if not is_final_epoch or close_final_epoch:
            records.append(deepcopy(BASIC[10]))

    if stop:
        stop_record = deepcopy(BASIC[9])
        stop_record["kind"] = "input.stop"
        stop_record["payload"] = {"at_ms": 0}
        records.append(stop_record)
        if close_final_epoch:
            records.append(deepcopy(BASIC[10]))

    records.append(_failed_terminal() if fail else deepcopy(BASIC[-1]))
    return _reindex(records)


@given(_legal_execution_transcripts())
def test_generated_legal_execution_transcript_round_trips(
    transcript: list[dict[str, JsonValue]],
) -> None:
    encoded = serialize_transcript(transcript)

    assert parse_transcript(encoded) == transcript


@given(capability_count=st.integers(min_value=0, max_value=6))
def test_generated_negotiation_prefix_may_end_in_adapter_failure(
    capability_count: int,
) -> None:
    transcript = _reindex(
        deepcopy(BASIC[: capability_count + 1])
        + [_failed_terminal("adapter-start-failed")]
    )

    assert parse_transcript(serialize_transcript(transcript)) == transcript


@given(unsupported_index=st.integers(min_value=0, max_value=6))
def test_generated_first_unsupported_constraint_terminates_negotiation(
    unsupported_index: int,
) -> None:
    records = deepcopy(BASIC[: unsupported_index + 2])
    capability = cast(dict[str, JsonValue], records[-1]["payload"])
    constraint = cast(str, capability["constraint"])
    capability.clear()
    capability.update(
        {
            "constraint": constraint,
            "reason": "synthetic",
            "status": "unsupported",
        }
    )
    terminal = deepcopy(BASIC[-1])
    terminal["kind"] = "run.unsupported"
    terminal["payload"] = {
        "code": "constraint-unsupported",
        "constraint": constraint,
        "message": "synthetic",
    }
    transcript = _reindex(records + [terminal])

    assert parse_transcript(serialize_transcript(transcript)) == transcript


@st.composite
def _illegal_execution_transcripts(
    draw: st.DrawFn,
) -> list[dict[str, JsonValue]]:
    mutation = draw(
        st.sampled_from(
            (
                "body-after-process-exit",
                "idle-diagnostic",
                "idle-observation",
                "input-after-stop",
                "missing-readiness",
                "overlapping-inputs",
            )
        )
    )
    records = deepcopy(BASIC)
    if mutation == "body-after-process-exit":
        observation_payload = cast(dict[str, JsonValue], records[10]["payload"])
        observation_payload["process"] = {
            "state": "exited",
            "exit": {"kind": "code", "value": 0},
        }
        records.insert(-1, deepcopy(BASIC[9]))
    elif mutation == "idle-diagnostic":
        records.insert(9, _diagnostic())
    elif mutation == "idle-observation":
        records.insert(9, deepcopy(BASIC[8]))
    elif mutation == "input-after-stop":
        records[9]["kind"] = "input.stop"
        records[9]["payload"] = {"at_ms": 0}
        records.insert(-1, deepcopy(BASIC[9]))
    elif mutation == "missing-readiness":
        del records[8]
    else:
        records.insert(10, deepcopy(BASIC[9]))
    return _reindex(records)


@given(_illegal_execution_transcripts())
def test_generated_illegal_execution_transcript_is_rejected(
    transcript: list[dict[str, JsonValue]],
) -> None:
    with pytest.raises(TranscriptValidationError):
        serialize_transcript(transcript)
