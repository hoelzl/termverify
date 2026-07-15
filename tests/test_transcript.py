from __future__ import annotations

from pathlib import Path

import pytest

from termverify.transcript import (
    JsonValue,
    TranscriptValidationError,
    parse_transcript,
    serialize_transcript,
)

FIXTURES = Path("tests/fixtures/transcripts/v1")


def test_parse_transcript_accepts_canonical_valid_fixture() -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())

    assert [record["kind"] for record in transcript] == [
        "run.started",
        "capability.result",
        "capability.result",
        "capability.result",
        "capability.result",
        "capability.result",
        "capability.result",
        "capability.result",
        "input.text",
        "observation",
        "run.finished",
    ]


def test_parse_transcript_rejects_wrong_protocol_fixture() -> None:
    fixture = (FIXTURES / "invalid" / "wrong-protocol.jsonl").read_bytes()

    with pytest.raises(TranscriptValidationError, match="protocol"):
        parse_transcript(fixture)


def test_serialize_transcript_emits_canonical_fixture_bytes() -> None:
    fixture = (FIXTURES / "valid" / "basic.jsonl").read_bytes()

    assert serialize_transcript(parse_transcript(fixture)) == fixture


def test_parse_transcript_rejects_unsupported_constraint_without_terminal_match() -> (
    None
):
    fixture = (FIXTURES / "valid" / "basic.jsonl").read_bytes()
    invalid = fixture.replace(
        b'"constraint":"network","effective":{"mode":"deny"},"status":"enforced"',
        (
            b'"constraint":"network","reason":"network isolation unavailable",'
            b'"status":"unsupported"'
        ),
    )

    with pytest.raises(TranscriptValidationError, match="unsupported"):
        parse_transcript(invalid)


def test_parse_transcript_accepts_early_unsupported_constraint() -> None:
    lines = (FIXTURES / "valid" / "basic.jsonl").read_bytes().splitlines()
    unsupported = lines[1].replace(
        b'"constraint":"seed","effective":"0","status":"enforced"',
        (
            b'"constraint":"seed","reason":"seed injection unavailable",'
            b'"status":"unsupported"'
        ),
    )
    terminal = (
        b'{"id":"record-002","kind":"run.unsupported",'
        b'"payload":{"code":"constraint-unsupported","constraint":"seed",'
        b'"message":"seed injection unavailable"},'
        b'"protocol":"termverify.transcript/v1","run_id":"run-basic","seq":2}'
    )

    transcript = parse_transcript(b"\n".join((lines[0], unsupported, terminal)) + b"\n")

    assert [record["kind"] for record in transcript] == [
        "run.started",
        "capability.result",
        "run.unsupported",
    ]


def test_parse_transcript_rejects_unsupported_terminal_for_wrong_constraint() -> None:
    lines = (FIXTURES / "valid" / "basic.jsonl").read_bytes().splitlines()
    unsupported = lines[1].replace(
        b'"constraint":"seed","effective":"0","status":"enforced"',
        (
            b'"constraint":"seed","reason":"seed injection unavailable",'
            b'"status":"unsupported"'
        ),
    )
    terminal = (
        b'{"id":"record-002","kind":"run.unsupported",'
        b'"payload":{"code":"constraint-unsupported","constraint":"clock",'
        b'"message":"seed injection unavailable"},'
        b'"protocol":"termverify.transcript/v1","run_id":"run-basic","seq":2}'
    )

    with pytest.raises(TranscriptValidationError, match="constraint"):
        parse_transcript(b"\n".join((lines[0], unsupported, terminal)) + b"\n")


def test_serialize_transcript_rejects_missing_deterministic_config() -> None:
    fixture = (FIXTURES / "valid" / "basic.jsonl").read_bytes()
    transcript = parse_transcript(fixture)
    transcript[0]["payload"] = {}

    with pytest.raises(TranscriptValidationError, match="config"):
        serialize_transcript(transcript)


def test_serialize_transcript_rejects_invalid_deterministic_seed() -> None:
    fixture = (FIXTURES / "valid" / "basic.jsonl").read_bytes()
    transcript = parse_transcript(fixture)
    payload = transcript[0]["payload"]
    assert isinstance(payload, dict)
    config = payload["config"]
    assert isinstance(config, dict)
    config["seed"] = "not-a-decimal-seed"

    with pytest.raises(TranscriptValidationError, match="seed"):
        serialize_transcript(transcript)


def test_serialize_transcript_rejects_incomplete_terminal_config() -> None:
    fixture = (FIXTURES / "valid" / "basic.jsonl").read_bytes()
    transcript = parse_transcript(fixture)
    payload = transcript[0]["payload"]
    assert isinstance(payload, dict)
    config = payload["config"]
    assert isinstance(config, dict)
    config["terminal"] = {"columns": 80}

    with pytest.raises(TranscriptValidationError, match="terminal"):
        serialize_transcript(transcript)


def test_serialize_transcript_rejects_duplicate_terminal_capabilities() -> None:
    fixture = (FIXTURES / "valid" / "basic.jsonl").read_bytes()
    transcript = parse_transcript(fixture)
    payload = transcript[0]["payload"]
    assert isinstance(payload, dict)
    config = payload["config"]
    assert isinstance(config, dict)
    terminal = config["terminal"]
    assert isinstance(terminal, dict)
    terminal["capabilities"] = ["ansi", "ansi"]

    with pytest.raises(TranscriptValidationError, match="terminal"):
        serialize_transcript(transcript)


def test_serialize_transcript_rejects_invalid_network_config() -> None:
    fixture = (FIXTURES / "valid" / "basic.jsonl").read_bytes()
    transcript = parse_transcript(fixture)
    payload = transcript[0]["payload"]
    assert isinstance(payload, dict)
    config = payload["config"]
    assert isinstance(config, dict)
    config["network"] = {"mode": "permit"}

    with pytest.raises(TranscriptValidationError, match="network"):
        serialize_transcript(transcript)


def test_serialize_transcript_rejects_malformed_network_allow_list_entry() -> None:
    fixture = (FIXTURES / "valid" / "basic.jsonl").read_bytes()
    transcript = parse_transcript(fixture)
    payload = transcript[0]["payload"]
    assert isinstance(payload, dict)
    config = payload["config"]
    assert isinstance(config, dict)
    config["network"] = {
        "allowed": [{"host": "example.test", "port": 0}],
        "mode": "allow-list",
    }

    with pytest.raises(TranscriptValidationError, match="network"):
        serialize_transcript(transcript)


def test_serialize_transcript_rejects_duplicate_network_allow_list_entry() -> None:
    fixture = (FIXTURES / "valid" / "basic.jsonl").read_bytes()
    transcript = parse_transcript(fixture)
    payload = transcript[0]["payload"]
    assert isinstance(payload, dict)
    config = payload["config"]
    assert isinstance(config, dict)
    entry: dict[str, JsonValue] = {"host": "example.test", "port": 443}
    config["network"] = {"allowed": [entry, entry], "mode": "allow-list"}

    with pytest.raises(TranscriptValidationError, match="network"):
        serialize_transcript(transcript)


def test_serialize_transcript_rejects_invalid_filesystem_config() -> None:
    fixture = (FIXTURES / "valid" / "basic.jsonl").read_bytes()
    transcript = parse_transcript(fixture)
    payload = transcript[0]["payload"]
    assert isinstance(payload, dict)
    config = payload["config"]
    assert isinstance(config, dict)
    config["filesystem"] = {"mode": "host", "root_id": "fixture-root"}

    with pytest.raises(TranscriptValidationError, match="filesystem"):
        serialize_transcript(transcript)


def test_serialize_transcript_rejects_empty_locale_config() -> None:
    fixture = (FIXTURES / "valid" / "basic.jsonl").read_bytes()
    transcript = parse_transcript(fixture)
    payload = transcript[0]["payload"]
    assert isinstance(payload, dict)
    config = payload["config"]
    assert isinstance(config, dict)
    config["locale"] = ""

    with pytest.raises(TranscriptValidationError, match="locale"):
        serialize_transcript(transcript)


def test_serialize_transcript_rejects_non_finite_json_number() -> None:
    fixture = (FIXTURES / "valid" / "basic.jsonl").read_bytes()
    transcript = parse_transcript(fixture)
    payload = transcript[9]["payload"]
    assert isinstance(payload, dict)
    payload["state"] = {"value": float("nan")}

    with pytest.raises(TranscriptValidationError, match="JSON number"):
        serialize_transcript(transcript)


def test_parse_transcript_rejects_non_finite_json_number() -> None:
    fixture = (FIXTURES / "valid" / "basic.jsonl").read_text(encoding="utf-8")
    data = fixture.replace('"text":"hello"', '"text":NaN').encode("utf-8")

    with pytest.raises(TranscriptValidationError, match="JSON number"):
        parse_transcript(data)


def test_serialize_transcript_uses_rfc_8785_number_rendering() -> None:
    fixture = (FIXTURES / "valid" / "basic.jsonl").read_bytes()
    transcript = parse_transcript(fixture)
    payload = transcript[9]["payload"]
    assert isinstance(payload, dict)
    payload["state"] = {"value": 1.0}

    serialized = serialize_transcript(transcript)

    assert b'"state":{"value":1}' in serialized
    assert parse_transcript(serialized) == transcript


def test_serialize_transcript_rejects_mismatched_enforced_effective_value() -> None:
    fixture = (FIXTURES / "valid" / "basic.jsonl").read_bytes()
    transcript = parse_transcript(fixture)
    payload = transcript[1]["payload"]
    assert isinstance(payload, dict)
    payload["effective"] = "1"

    with pytest.raises(TranscriptValidationError, match="effective"):
        serialize_transcript(transcript)


def test_serialize_transcript_rejects_input_without_manual_time() -> None:
    fixture = (FIXTURES / "valid" / "basic.jsonl").read_bytes()
    transcript = parse_transcript(fixture)
    transcript[8]["payload"] = {"text": "hello"}

    with pytest.raises(TranscriptValidationError, match="at_ms"):
        serialize_transcript(transcript)


def test_serialize_transcript_rejects_text_input_without_text() -> None:
    fixture = (FIXTURES / "valid" / "basic.jsonl").read_bytes()
    transcript = parse_transcript(fixture)
    transcript[8]["payload"] = {"at_ms": 0}

    with pytest.raises(TranscriptValidationError, match="input.text"):
        serialize_transcript(transcript)


def test_serialize_transcript_rejects_unknown_v1_input_kind() -> None:
    fixture = (FIXTURES / "valid" / "basic.jsonl").read_bytes()
    transcript = parse_transcript(fixture)
    transcript[8]["kind"] = "input.unknown"

    with pytest.raises(TranscriptValidationError, match="input kind"):
        serialize_transcript(transcript)


def test_serialize_transcript_rejects_unknown_v1_record_kind() -> None:
    fixture = (FIXTURES / "valid" / "basic.jsonl").read_bytes()
    transcript = parse_transcript(fixture)
    transcript[9]["kind"] = "observation.unknown"

    with pytest.raises(TranscriptValidationError, match="record kind"):
        serialize_transcript(transcript)


def test_serialize_transcript_rejects_unknown_generic_input_member() -> None:
    fixture = (FIXTURES / "valid" / "basic.jsonl").read_bytes()
    transcript = parse_transcript(fixture)
    payload = transcript[8]["payload"]
    assert isinstance(payload, dict)
    payload["unexpected"] = True

    with pytest.raises(TranscriptValidationError, match="payload member"):
        serialize_transcript(transcript)


def test_serialize_transcript_rejects_key_input_without_normalized_keys() -> None:
    fixture = (FIXTURES / "valid" / "basic.jsonl").read_bytes()
    transcript = parse_transcript(fixture)
    transcript[8]["kind"] = "input.key"
    transcript[8]["payload"] = {"at_ms": 0, "keys": []}

    with pytest.raises(TranscriptValidationError, match="input.key"):
        serialize_transcript(transcript)


def test_serialize_transcript_rejects_resize_with_non_positive_dimensions() -> None:
    fixture = (FIXTURES / "valid" / "basic.jsonl").read_bytes()
    transcript = parse_transcript(fixture)
    transcript[8]["kind"] = "input.resize"
    transcript[8]["payload"] = {"at_ms": 0, "columns": 0, "rows": 24}

    with pytest.raises(TranscriptValidationError, match="input.resize"):
        serialize_transcript(transcript)


def test_serialize_transcript_rejects_mouse_press_without_button() -> None:
    fixture = (FIXTURES / "valid" / "basic.jsonl").read_bytes()
    transcript = parse_transcript(fixture)
    transcript[8]["kind"] = "input.mouse"
    transcript[8]["payload"] = {"action": "press", "at_ms": 0, "column": 0, "row": 0}

    with pytest.raises(TranscriptValidationError, match="input.mouse"):
        serialize_transcript(transcript)


def test_serialize_transcript_rejects_clock_advance_with_wrong_time() -> None:
    fixture = (FIXTURES / "valid" / "basic.jsonl").read_bytes()
    transcript = parse_transcript(fixture)
    transcript[8]["kind"] = "input.clock_advanced"
    transcript[8]["payload"] = {"at_ms": 0, "delta_ms": 1}

    with pytest.raises(TranscriptValidationError, match="input.clock_advanced"):
        serialize_transcript(transcript)


def test_serialize_transcript_rejects_clipboard_input_without_text() -> None:
    fixture = (FIXTURES / "valid" / "basic.jsonl").read_bytes()
    transcript = parse_transcript(fixture)
    transcript[8]["kind"] = "input.clipboard_set"
    transcript[8]["payload"] = {"at_ms": 0}

    with pytest.raises(TranscriptValidationError, match="input.clipboard_set"):
        serialize_transcript(transcript)


def test_serialize_transcript_rejects_stop_input_with_extra_member() -> None:
    fixture = (FIXTURES / "valid" / "basic.jsonl").read_bytes()
    transcript = parse_transcript(fixture)
    transcript[8]["kind"] = "input.stop"
    transcript[8]["payload"] = {"at_ms": 0, "reason": "unexpected"}

    with pytest.raises(TranscriptValidationError, match="input.stop"):
        serialize_transcript(transcript)


def test_serialize_transcript_rejects_diagnostic_without_code() -> None:
    fixture = (FIXTURES / "valid" / "basic.jsonl").read_bytes()
    transcript = parse_transcript(fixture)
    transcript[9]["kind"] = "diagnostic"
    transcript[9]["payload"] = {"at_ms": 0, "message": "missing code"}

    with pytest.raises(TranscriptValidationError, match="diagnostic"):
        serialize_transcript(transcript)


def test_serialize_transcript_rejects_failed_run_without_structured_error() -> None:
    fixture = (FIXTURES / "valid" / "basic.jsonl").read_bytes()
    transcript = parse_transcript(fixture)
    transcript[-1]["kind"] = "run.failed"
    transcript[-1]["payload"] = {}

    with pytest.raises(TranscriptValidationError, match="run.failed"):
        serialize_transcript(transcript)


def test_serialize_transcript_rejects_observation_without_required_members() -> None:
    fixture = (FIXTURES / "valid" / "basic.jsonl").read_bytes()
    transcript = parse_transcript(fixture)
    transcript[9]["payload"] = {"at_ms": 0}

    with pytest.raises(TranscriptValidationError, match="observation"):
        serialize_transcript(transcript)


def test_serialize_transcript_rejects_ui_without_required_members() -> None:
    fixture = (FIXTURES / "valid" / "basic.jsonl").read_bytes()
    transcript = parse_transcript(fixture)
    payload = transcript[9]["payload"]
    assert isinstance(payload, dict)
    payload["ui"] = {}

    with pytest.raises(TranscriptValidationError, match="ui"):
        serialize_transcript(transcript)


def test_serialize_transcript_rejects_ui_focus_not_in_regions() -> None:
    fixture = (FIXTURES / "valid" / "basic.jsonl").read_bytes()
    transcript = parse_transcript(fixture)
    payload = transcript[9]["payload"]
    assert isinstance(payload, dict)
    ui = payload["ui"]
    assert isinstance(ui, dict)
    ui["focus"] = "missing-region"

    with pytest.raises(TranscriptValidationError, match="focus"):
        serialize_transcript(transcript)


def test_serialize_transcript_rejects_observation_event_without_type() -> None:
    fixture = (FIXTURES / "valid" / "basic.jsonl").read_bytes()
    transcript = parse_transcript(fixture)
    payload = transcript[9]["payload"]
    assert isinstance(payload, dict)
    payload["events"] = [{"data": None}]

    with pytest.raises(TranscriptValidationError, match="event"):
        serialize_transcript(transcript)


def test_serialize_transcript_rejects_frame_with_wrong_line_count() -> None:
    fixture = (FIXTURES / "valid" / "basic.jsonl").read_bytes()
    transcript = parse_transcript(fixture)
    payload = transcript[9]["payload"]
    assert isinstance(payload, dict)
    payload["frame"] = {"columns": 80, "lines": [""], "rows": 2}

    with pytest.raises(TranscriptValidationError, match="frame"):
        serialize_transcript(transcript)


def test_serialize_transcript_rejects_exited_process_without_exit() -> None:
    fixture = (FIXTURES / "valid" / "basic.jsonl").read_bytes()
    transcript = parse_transcript(fixture)
    payload = transcript[9]["payload"]
    assert isinstance(payload, dict)
    payload["process"] = {"state": "exited"}

    with pytest.raises(TranscriptValidationError, match="process"):
        serialize_transcript(transcript)


def test_serialize_transcript_rejects_malformed_finished_exit() -> None:
    fixture = (FIXTURES / "valid" / "basic.jsonl").read_bytes()
    transcript = parse_transcript(fixture)
    transcript[-1]["payload"] = {"exit": {"kind": "code", "value": "zero"}}

    with pytest.raises(TranscriptValidationError, match="exit"):
        serialize_transcript(transcript)
