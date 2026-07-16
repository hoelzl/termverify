from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from termverify.transcript import (
    JsonValue,
    TranscriptValidationError,
    parse_transcript,
    serialize_transcript,
)

FIXTURES = Path("tests/fixtures/transcripts/v1")
GRANDFATHERED_LOCALES = (
    "art-lojban",
    "cel-gaulish",
    "en-GB-oed",
    "i-ami",
    "i-bnn",
    "i-default",
    "i-enochian",
    "i-hak",
    "i-klingon",
    "i-lux",
    "i-mingo",
    "i-navajo",
    "i-pwn",
    "i-tao",
    "i-tay",
    "i-tsu",
    "no-bok",
    "no-nyn",
    "sgn-BE-FR",
    "sgn-BE-NL",
    "sgn-CH-DE",
    "zh-guoyu",
    "zh-hakka",
    "zh-min",
    "zh-min-nan",
    "zh-xiang",
)
MALFORMED_LOCALES = (
    "c",
    "en_US",
    "a-DE",
    "de-419-DE",
    "en-a",
    "en-x",
    "en-a-aaa-A-bbb",
    "en-0-aaa-0-bbb",
    "sl-rozaj-ROZAJ",
    "i-not-registered",
    "abcdefghi",
    "en-abcdefghi",
    "x-abcdefghi",
    "abc-def-ghi-jkl-mno",
    "en--US",
    "én-US",
)


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


def test_parse_transcript_rejects_missing_replay_subject() -> None:
    lines = (FIXTURES / "valid" / "basic.jsonl").read_bytes().splitlines()
    started = json.loads(lines[0])
    started["payload"].pop("subject")
    lines[0] = json.dumps(
        started, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode()

    with pytest.raises(TranscriptValidationError, match="subject"):
        parse_transcript(b"\n".join(lines) + b"\n")


def test_serialize_transcript_rejects_wrong_replay_subject_format() -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    payload = transcript[0]["payload"]
    assert isinstance(payload, dict)
    subject = payload["subject"]
    assert isinstance(subject, dict)
    subject["format"] = "termverify.replay-subject/v2"

    with pytest.raises(TranscriptValidationError, match="subject format"):
        serialize_transcript(transcript)


def test_serialize_transcript_requires_each_replay_subject_selector() -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    payload = transcript[0]["payload"]
    assert isinstance(payload, dict)
    subject = payload["subject"]
    assert isinstance(subject, dict)
    subject.pop("application")

    with pytest.raises(TranscriptValidationError, match="subject members"):
        serialize_transcript(transcript)


def test_serialize_transcript_rejects_unknown_replay_subject_member() -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    payload = transcript[0]["payload"]
    assert isinstance(payload, dict)
    subject = payload["subject"]
    assert isinstance(subject, dict)
    subject["hostname"] = "developer-machine"

    with pytest.raises(TranscriptValidationError, match="subject members"):
        serialize_transcript(transcript)


def test_serialize_transcript_requires_application_build_identity() -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    payload = transcript[0]["payload"]
    assert isinstance(payload, dict)
    subject = payload["subject"]
    assert isinstance(subject, dict)
    application = subject["application"]
    assert isinstance(application, dict)
    application.pop("build")

    with pytest.raises(TranscriptValidationError, match="application"):
        serialize_transcript(transcript)


def test_serialize_transcript_rejects_unstable_application_identity() -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    payload = transcript[0]["payload"]
    assert isinstance(payload, dict)
    subject = payload["subject"]
    assert isinstance(subject, dict)
    application = subject["application"]
    assert isinstance(application, dict)
    application["id"] = "Developer App"

    with pytest.raises(TranscriptValidationError, match="application"):
        serialize_transcript(transcript)


@pytest.mark.parametrize(
    "selector", ["fixture", "adapter", "normalizer", "state_schema"]
)
def test_serialize_transcript_requires_versioned_replay_selector(selector: str) -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    payload = transcript[0]["payload"]
    assert isinstance(payload, dict)
    subject = payload["subject"]
    assert isinstance(subject, dict)
    selected = subject[selector]
    assert isinstance(selected, dict)
    selected.pop("version")

    with pytest.raises(TranscriptValidationError, match=selector):
        serialize_transcript(transcript)


def test_serialize_transcript_accepts_normalized_platform_identity() -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    payload = transcript[0]["payload"]
    assert isinstance(payload, dict)
    subject = payload["subject"]
    assert isinstance(subject, dict)
    subject["platform"] = {"architecture": "x86_64", "os": "windows"}

    serialized = serialize_transcript(transcript)

    assert parse_transcript(serialized) == transcript


def test_serialize_transcript_rejects_volatile_platform_identity() -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    payload = transcript[0]["payload"]
    assert isinstance(payload, dict)
    subject = payload["subject"]
    assert isinstance(subject, dict)
    subject["platform"] = {
        "architecture": "x86_64",
        "hostname": "developer-machine",
        "os": "windows",
    }

    with pytest.raises(TranscriptValidationError, match="platform"):
        serialize_transcript(transcript)


def test_serialize_transcript_rejects_unknown_run_started_member() -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    payload = transcript[0]["payload"]
    assert isinstance(payload, dict)
    payload["invocation"] = {"argv": ["private-command"]}

    with pytest.raises(TranscriptValidationError, match="run.started members"):
        serialize_transcript(transcript)


def test_serialize_transcript_rejects_volatile_config_member() -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    payload = transcript[0]["payload"]
    assert isinstance(payload, dict)
    config = payload["config"]
    assert isinstance(config, dict)
    config["argv"] = ["C:/Users/example/private/app.exe", "--token=secret"]

    with pytest.raises(TranscriptValidationError, match="config"):
        serialize_transcript(transcript)


def test_serialize_transcript_rejects_noncanonical_leading_zero_seed() -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    payload = transcript[0]["payload"]
    assert isinstance(payload, dict)
    config = payload["config"]
    assert isinstance(config, dict)
    config["seed"] = "00"
    capability_payload = transcript[1]["payload"]
    assert isinstance(capability_payload, dict)
    capability_payload["effective"] = "00"

    with pytest.raises(TranscriptValidationError, match="seed"):
        serialize_transcript(transcript)


@pytest.mark.parametrize(
    ("constraint", "member"),
    [
        ("clock", "argv"),
        ("terminal", "environment"),
        ("filesystem", "path"),
        ("network-entry", "argv"),
    ],
)
def test_serialize_transcript_rejects_nested_volatile_config_member(
    constraint: str, member: str
) -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    started_payload = transcript[0]["payload"]
    assert isinstance(started_payload, dict)
    config = started_payload["config"]
    assert isinstance(config, dict)
    capability_constraint = constraint
    if constraint == "network-entry":
        capability_constraint = "network"
        config["network"] = {
            "allowed": [{"host": "example.invalid", "port": 443, member: ["secret"]}],
            "mode": "allow-list",
        }
    else:
        target = config[constraint]
        assert isinstance(target, dict)
        target[member] = ["secret"]
    for record in transcript:
        payload = record["payload"]
        if (
            record["kind"] == "capability.result"
            and isinstance(payload, dict)
            and payload.get("constraint") == capability_constraint
        ):
            payload["effective"] = deepcopy(config[capability_constraint])
            break

    with pytest.raises(
        TranscriptValidationError, match=f"run.started {capability_constraint}"
    ):
        serialize_transcript(transcript)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda record: record.__setitem__("protocol", "wrong/v1"), "protocol"),
        (lambda record: record.__setitem__("seq", 1), "sequence"),
        (lambda record: record.pop("kind"), "envelope"),
        (lambda record: record.__setitem__("unexpected", True), "envelope"),
    ],
)
def test_serialize_transcript_rejects_invalid_record_envelope(
    mutation: object, message: str
) -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    assert callable(mutation)
    mutation(transcript[0])

    with pytest.raises(TranscriptValidationError, match=message):
        serialize_transcript(transcript)


def test_serialize_transcript_rejects_boolean_sequence() -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    transcript[0]["seq"] = False

    with pytest.raises(TranscriptValidationError, match="sequence"):
        serialize_transcript(transcript)


@pytest.mark.parametrize("field", ["run_id", "id"])
def test_serialize_transcript_rejects_identifier_outside_v1_grammar(
    field: str,
) -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    transcript[0][field] = "Upper Case"

    with pytest.raises(TranscriptValidationError, match="identifier"):
        serialize_transcript(transcript)


def test_serialize_transcript_rejects_repeated_run_started() -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    transcript[8]["kind"] = "run.started"
    transcript[8]["payload"] = transcript[0]["payload"]

    with pytest.raises(TranscriptValidationError, match="run.started"):
        serialize_transcript(transcript)


def test_serialize_transcript_rejects_intermediate_terminal_record() -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    transcript[8]["kind"] = "run.failed"
    transcript[8]["payload"] = {
        "error": {"code": "adapter-runtime-failed", "message": "failed"}
    }

    with pytest.raises(TranscriptValidationError, match="terminal"):
        serialize_transcript(transcript)


def test_serialize_transcript_rejects_record_after_terminal() -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    record = transcript[8].copy()
    record["seq"] = len(transcript)
    record["id"] = "record-after-terminal"
    transcript.append(record)

    with pytest.raises(TranscriptValidationError, match="terminal"):
        serialize_transcript(transcript)


def test_serialize_transcript_rejects_unsupported_terminal_after_enforcement() -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    transcript[-1]["kind"] = "run.unsupported"
    transcript[-1]["payload"] = {}

    with pytest.raises(TranscriptValidationError, match="run.unsupported"):
        serialize_transcript(transcript)


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


def test_serialize_transcript_requires_terminal_capabilities() -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    payload = transcript[0]["payload"]
    assert isinstance(payload, dict)
    config = payload["config"]
    assert isinstance(config, dict)
    terminal = config["terminal"]
    assert isinstance(terminal, dict)
    terminal.pop("capabilities")
    capability = transcript[5]["payload"]
    assert isinstance(capability, dict)
    effective = capability["effective"]
    assert isinstance(effective, dict)
    effective.pop("capabilities")

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


def test_serialize_transcript_rejects_malformed_locale_config() -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    started_payload = transcript[0]["payload"]
    assert isinstance(started_payload, dict)
    config = started_payload["config"]
    assert isinstance(config, dict)
    config["locale"] = "not a tag!"
    locale_result = transcript[3]["payload"]
    assert isinstance(locale_result, dict)
    assert locale_result["constraint"] == "locale"
    locale_result["effective"] = "not a tag!"

    with pytest.raises(TranscriptValidationError, match="locale"):
        serialize_transcript(transcript)


def test_serialize_transcript_rejects_incomplete_private_use_locale() -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    started_payload = transcript[0]["payload"]
    assert isinstance(started_payload, dict)
    config = started_payload["config"]
    assert isinstance(config, dict)
    config["locale"] = "x"
    locale_result = transcript[3]["payload"]
    assert isinstance(locale_result, dict)
    assert locale_result["constraint"] == "locale"
    locale_result["effective"] = "x"

    with pytest.raises(TranscriptValidationError, match="locale"):
        serialize_transcript(transcript)


@pytest.mark.parametrize(
    "locale",
    MALFORMED_LOCALES,
)
def test_serialize_transcript_rejects_non_well_formed_locale(locale: str) -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    started_payload = transcript[0]["payload"]
    assert isinstance(started_payload, dict)
    config = started_payload["config"]
    assert isinstance(config, dict)
    config["locale"] = locale
    locale_result = transcript[3]["payload"]
    assert isinstance(locale_result, dict)
    assert locale_result["constraint"] == "locale"
    locale_result["effective"] = locale

    with pytest.raises(TranscriptValidationError, match="locale"):
        serialize_transcript(transcript)


@pytest.mark.parametrize(
    "locale",
    [
        "C",
        "de",
        "zh-cmn-Hans-CN",
        "sl-rozaj-biske",
        "de-CH-1901",
        "x-whatever",
        "en-US-u-islamcal",
        "i-KLINGON",
        "abcd",
        "abcdefgh-123-1abc-abcdefgh-a-aa-abcdefgh-x-a-abcdefgh",
        *GRANDFATHERED_LOCALES,
    ],
)
def test_locale_spelling_round_trips_for_well_formed_tags(locale: str) -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    started_payload = transcript[0]["payload"]
    assert isinstance(started_payload, dict)
    config = started_payload["config"]
    assert isinstance(config, dict)
    config["locale"] = locale
    locale_result = transcript[3]["payload"]
    assert isinstance(locale_result, dict)
    assert locale_result["constraint"] == "locale"
    locale_result["effective"] = locale

    reparsed = parse_transcript(serialize_transcript(transcript))
    reparsed_started = reparsed[0]["payload"]
    assert isinstance(reparsed_started, dict)
    reparsed_config = reparsed_started["config"]
    assert isinstance(reparsed_config, dict)
    assert reparsed_config["locale"] == locale


@pytest.mark.parametrize("locale", MALFORMED_LOCALES)
def test_parse_transcript_rejects_non_well_formed_locale(locale: str) -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    started_payload = transcript[0]["payload"]
    assert isinstance(started_payload, dict)
    config = started_payload["config"]
    assert isinstance(config, dict)
    config["locale"] = locale
    locale_result = transcript[3]["payload"]
    assert isinstance(locale_result, dict)
    assert locale_result["constraint"] == "locale"
    locale_result["effective"] = locale
    encoded = b"".join(
        json.dumps(
            record, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        ).encode()
        + b"\n"
        for record in transcript
    )

    with pytest.raises(TranscriptValidationError, match="locale"):
        parse_transcript(encoded)


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


def test_parse_transcript_converts_excessive_nesting_to_validation_error() -> None:
    data = b'{"x":' * 2_000 + b"0" + b"}" * 2_000 + b"\n"

    with pytest.raises(TranscriptValidationError, match="nesting"):
        parse_transcript(data)


def test_serialize_transcript_converts_excessive_nesting_to_validation_error() -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    payload = transcript[9]["payload"]
    assert isinstance(payload, dict)
    nested: list[JsonValue] = []
    root = nested
    for _ in range(2_000):
        child: list[JsonValue] = []
        nested.append(child)
        nested = child
    payload["state"] = root

    with pytest.raises(TranscriptValidationError, match="nesting"):
        serialize_transcript(transcript)


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


def test_serialize_transcript_rejects_boolean_effective_integer() -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    started = transcript[0]["payload"]
    capability = transcript[2]["payload"]
    assert isinstance(started, dict)
    assert isinstance(capability, dict)
    config = started["config"]
    effective = capability["effective"]
    assert isinstance(config, dict)
    assert isinstance(effective, dict)
    clock = config["clock"]
    assert isinstance(clock, dict)
    clock["initial_ms"] = 1
    effective["initial_ms"] = True

    with pytest.raises(TranscriptValidationError, match="effective"):
        serialize_transcript(transcript)


@pytest.mark.parametrize("status", [[], {}, "pending"])
def test_transcript_rejects_invalid_capability_status(status: JsonValue) -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    payload = transcript[1]["payload"]
    assert isinstance(payload, dict)
    payload["status"] = status

    with pytest.raises(TranscriptValidationError, match="status"):
        serialize_transcript(transcript)

    encoded = b"".join(
        json.dumps(
            record, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        ).encode()
        + b"\n"
        for record in transcript
    )
    with pytest.raises(TranscriptValidationError, match="status"):
        parse_transcript(encoded)


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


@pytest.mark.parametrize("action", [[], {}, "drag"])
def test_transcript_rejects_invalid_mouse_action(action: JsonValue) -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    transcript[8]["kind"] = "input.mouse"
    transcript[8]["payload"] = {
        "action": action,
        "at_ms": 0,
        "column": 0,
        "row": 0,
    }

    with pytest.raises(TranscriptValidationError, match="action"):
        serialize_transcript(transcript)

    encoded = b"".join(
        json.dumps(
            record, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        ).encode()
        + b"\n"
        for record in transcript
    )
    with pytest.raises(TranscriptValidationError, match="action"):
        parse_transcript(encoded)


@pytest.mark.parametrize("action", ["press", "release"])
@pytest.mark.parametrize("button", [[], {}, "primary"])
def test_transcript_rejects_invalid_mouse_button(
    action: str, button: JsonValue
) -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    transcript[8]["kind"] = "input.mouse"
    transcript[8]["payload"] = {
        "action": action,
        "at_ms": 0,
        "button": button,
        "column": 0,
        "row": 0,
    }

    with pytest.raises(TranscriptValidationError, match="button"):
        serialize_transcript(transcript)

    encoded = b"".join(
        json.dumps(
            record, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        ).encode()
        + b"\n"
        for record in transcript
    )
    with pytest.raises(TranscriptValidationError, match="button"):
        parse_transcript(encoded)


def test_serialize_transcript_rejects_boolean_mouse_scroll_delta() -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    transcript[8]["kind"] = "input.mouse"
    transcript[8]["payload"] = {
        "action": "scroll",
        "at_ms": 0,
        "column": 0,
        "delta": True,
        "row": 0,
    }

    with pytest.raises(TranscriptValidationError, match="scroll delta"):
        serialize_transcript(transcript)


@pytest.mark.parametrize("member", ["button", "delta"])
def test_serialize_transcript_rejects_forbidden_member_for_mouse_move(
    member: str,
) -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    transcript[8]["kind"] = "input.mouse"
    payload: dict[str, JsonValue] = {
        "action": "move",
        "at_ms": 0,
        "column": 0,
        "row": 0,
    }
    payload[member] = None
    transcript[8]["payload"] = payload

    with pytest.raises(TranscriptValidationError, match="mouse move"):
        serialize_transcript(transcript)


@pytest.mark.parametrize("action", ["press", "release"])
def test_serialize_transcript_rejects_delta_member_for_mouse_button_action(
    action: str,
) -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    transcript[8]["kind"] = "input.mouse"
    transcript[8]["payload"] = {
        "action": action,
        "at_ms": 0,
        "button": "left",
        "column": 0,
        "delta": None,
        "row": 0,
    }

    with pytest.raises(TranscriptValidationError, match="mouse button"):
        serialize_transcript(transcript)


def test_serialize_transcript_rejects_button_member_for_mouse_scroll() -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    transcript[8]["kind"] = "input.mouse"
    transcript[8]["payload"] = {
        "action": "scroll",
        "at_ms": 0,
        "button": None,
        "column": 0,
        "delta": 1,
        "row": 0,
    }

    with pytest.raises(TranscriptValidationError, match="scroll delta"):
        serialize_transcript(transcript)


@pytest.mark.parametrize(
    "payload",
    [
        {"action": "move", "at_ms": 0, "button": None, "column": 0, "row": 0},
        {"action": "move", "at_ms": 0, "column": 0, "delta": None, "row": 0},
        {
            "action": "press",
            "at_ms": 0,
            "button": "left",
            "column": 0,
            "delta": None,
            "row": 0,
        },
        {
            "action": "release",
            "at_ms": 0,
            "button": "left",
            "column": 0,
            "delta": None,
            "row": 0,
        },
        {
            "action": "scroll",
            "at_ms": 0,
            "button": None,
            "column": 0,
            "delta": 1,
            "row": 0,
        },
    ],
)
def test_parse_transcript_rejects_action_forbidden_mouse_member(
    payload: dict[str, JsonValue],
) -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    transcript[8]["kind"] = "input.mouse"
    transcript[8]["payload"] = payload
    encoded = b"".join(
        json.dumps(
            record, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        ).encode()
        + b"\n"
        for record in transcript
    )

    with pytest.raises(TranscriptValidationError, match="input.mouse"):
        parse_transcript(encoded)


@pytest.mark.parametrize(
    "payload",
    [
        {
            "action": "press",
            "at_ms": 0,
            "button": "left",
            "column": 0,
            "row": 0,
        },
        {
            "action": "release",
            "at_ms": 0,
            "button": "right",
            "column": 0,
            "row": 0,
        },
        {"action": "move", "at_ms": 0, "column": 0, "row": 0},
        {"action": "scroll", "at_ms": 0, "column": 0, "delta": -1, "row": 0},
    ],
)
def test_mouse_action_with_extension_round_trips(
    payload: dict[str, JsonValue],
) -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    payload["x-synthetic"] = {"uninterpreted": True}
    transcript[8]["kind"] = "input.mouse"
    transcript[8]["payload"] = payload

    assert parse_transcript(serialize_transcript(transcript)) == transcript


def test_serialize_transcript_rejects_clock_advance_with_wrong_time() -> None:
    fixture = (FIXTURES / "valid" / "basic.jsonl").read_bytes()
    transcript = parse_transcript(fixture)
    transcript[8]["kind"] = "input.clock_advanced"
    transcript[8]["payload"] = {"at_ms": 0, "delta_ms": 1}

    with pytest.raises(TranscriptValidationError, match="input.clock_advanced"):
        serialize_transcript(transcript)


@pytest.mark.parametrize("kind", ["diagnostic", "observation"])
def test_transcript_rejects_evidence_time_that_differs_from_manual_clock(
    kind: str,
) -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    payload = transcript[9]["payload"]
    assert isinstance(payload, dict)
    payload["at_ms"] = 1
    if kind == "diagnostic":
        transcript[9]["kind"] = kind
        transcript[9]["payload"] = {
            "at_ms": 1,
            "code": "synthetic",
            "message": "synthetic",
        }

    with pytest.raises(TranscriptValidationError, match="manual clock"):
        serialize_transcript(transcript)

    encoded = (
        b"\n".join(
            json.dumps(
                record, ensure_ascii=False, separators=(",", ":"), sort_keys=True
            ).encode()
            for record in transcript
        )
        + b"\n"
    )
    with pytest.raises(TranscriptValidationError, match="manual clock"):
        parse_transcript(encoded)


@pytest.mark.parametrize("kind", ["diagnostic", "observation"])
def test_transcript_accepts_evidence_at_explicitly_advanced_manual_time(
    kind: str,
) -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    transcript[8]["kind"] = "input.clock_advanced"
    transcript[8]["payload"] = {"at_ms": 1, "delta_ms": 1}
    evidence = transcript[9]["payload"]
    assert isinstance(evidence, dict)
    evidence["at_ms"] = 1
    if kind == "diagnostic":
        transcript[9]["kind"] = kind
        transcript[9]["payload"] = {
            "at_ms": 1,
            "code": "synthetic",
            "message": "synthetic",
        }

    encoded = serialize_transcript(transcript)

    assert parse_transcript(encoded) == transcript


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


@pytest.mark.parametrize("member", ["regions", "focus", "cursor", "mode"])
def test_transcript_rejects_ui_without_required_member(member: str) -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    payload = transcript[9]["payload"]
    assert isinstance(payload, dict)
    ui = payload["ui"]
    assert isinstance(ui, dict)
    del ui[member]

    with pytest.raises(TranscriptValidationError, match="ui"):
        serialize_transcript(transcript)

    encoded = b"".join(
        json.dumps(
            record, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        ).encode()
        + b"\n"
        for record in transcript
    )
    with pytest.raises(TranscriptValidationError, match="ui"):
        parse_transcript(encoded)


def test_transcript_accepts_nullable_ui_members_with_extension() -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    payload = transcript[9]["payload"]
    assert isinstance(payload, dict)
    ui = payload["ui"]
    assert isinstance(ui, dict)
    ui["focus"] = None
    ui["mode"] = None
    ui["x-synthetic"] = {"uninterpreted": True}

    assert parse_transcript(serialize_transcript(transcript)) == transcript


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


def test_transcript_rejects_exited_process_code_that_differs_from_finished() -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    payload = transcript[9]["payload"]
    assert isinstance(payload, dict)
    payload["process"] = {
        "exit": {"kind": "code", "value": 99},
        "state": "exited",
    }

    with pytest.raises(TranscriptValidationError, match="process exit"):
        serialize_transcript(transcript)

    encoded = (
        b"\n".join(
            json.dumps(
                record, ensure_ascii=False, separators=(",", ":"), sort_keys=True
            ).encode()
            for record in transcript
        )
        + b"\n"
    )
    with pytest.raises(TranscriptValidationError, match="process exit"):
        parse_transcript(encoded)


def test_transcript_rejects_exited_process_signal_that_differs_from_finished() -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    observation = transcript[9]["payload"]
    terminal = transcript[-1]["payload"]
    assert isinstance(observation, dict)
    assert isinstance(terminal, dict)
    observation["process"] = {
        "exit": {"kind": "signal", "value": "SIGTERM"},
        "state": "exited",
    }
    terminal["exit"] = {"kind": "signal", "value": "SIGKILL"}

    with pytest.raises(TranscriptValidationError, match="process exit"):
        serialize_transcript(transcript)

    encoded = (
        b"\n".join(
            json.dumps(
                record, ensure_ascii=False, separators=(",", ":"), sort_keys=True
            ).encode()
            for record in transcript
        )
        + b"\n"
    )
    with pytest.raises(TranscriptValidationError, match="process exit"):
        parse_transcript(encoded)


@pytest.mark.parametrize(
    "exit_value",
    [
        {"kind": "code", "value": 0},
        {"kind": "signal", "value": "SIGTERM"},
    ],
)
def test_transcript_accepts_exited_process_that_matches_finished(
    exit_value: dict[str, JsonValue],
) -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    observation = transcript[9]["payload"]
    terminal = transcript[-1]["payload"]
    assert isinstance(observation, dict)
    assert isinstance(terminal, dict)
    observation["process"] = {"exit": deepcopy(exit_value), "state": "exited"}
    terminal["exit"] = deepcopy(exit_value)

    encoded = serialize_transcript(transcript)

    assert parse_transcript(encoded) == transcript


def test_transcript_rejects_one_mismatched_exit_among_multiple_observations() -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    first_observation = transcript[9]["payload"]
    assert isinstance(first_observation, dict)
    first_observation["process"] = {
        "exit": {"kind": "code", "value": 0},
        "state": "exited",
    }
    second_observation = deepcopy(transcript[9])
    second_observation["id"] = "record-second-observation"
    second_observation["seq"] = 10
    second_payload = second_observation["payload"]
    assert isinstance(second_payload, dict)
    second_payload["process"] = {
        "exit": {"kind": "code", "value": 99},
        "state": "exited",
    }
    transcript.insert(-1, second_observation)
    transcript[-1]["seq"] = 11

    with pytest.raises(TranscriptValidationError, match="process exit"):
        serialize_transcript(transcript)


def test_transcript_accepts_multiple_matching_exited_process_observations() -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    first_observation = transcript[9]["payload"]
    assert isinstance(first_observation, dict)
    first_observation["process"] = {
        "exit": {"kind": "code", "value": 0},
        "state": "exited",
    }
    second_observation = deepcopy(transcript[9])
    second_observation["id"] = "record-second-observation"
    second_observation["seq"] = 10
    transcript.insert(-1, second_observation)
    transcript[-1]["seq"] = 11

    encoded = serialize_transcript(transcript)

    assert parse_transcript(encoded) == transcript


def test_transcript_exit_coherence_ignores_uninterpreted_extensions() -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    observation = transcript[9]["payload"]
    terminal = transcript[-1]["payload"]
    assert isinstance(observation, dict)
    assert isinstance(terminal, dict)
    observation["process"] = {
        "exit": {
            "kind": "code",
            "value": 0,
            "x-observation": {"source": "observation"},
        },
        "state": "exited",
    }
    terminal_exit = terminal["exit"]
    assert isinstance(terminal_exit, dict)
    terminal_exit["x-terminal"] = {"source": "terminal"}

    encoded = serialize_transcript(transcript)

    assert parse_transcript(encoded) == transcript


def test_serialize_transcript_rejects_malformed_finished_exit() -> None:
    fixture = (FIXTURES / "valid" / "basic.jsonl").read_bytes()
    transcript = parse_transcript(fixture)
    transcript[-1]["payload"] = {"exit": {"kind": "code", "value": "zero"}}

    with pytest.raises(TranscriptValidationError, match="exit"):
        serialize_transcript(transcript)


def _transcript_with_payload_kind(kind: str) -> tuple[list[dict[str, JsonValue]], int]:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    body_payloads: dict[str, dict[str, JsonValue]] = {
        "input.key": {"at_ms": 0, "keys": ["enter"]},
        "input.text": {"at_ms": 0, "text": "hello"},
        "input.resize": {"at_ms": 0, "columns": 80, "rows": 24},
        "input.mouse": {
            "action": "move",
            "at_ms": 0,
            "column": 0,
            "row": 0,
        },
        "input.clock_advanced": {"at_ms": 1, "delta_ms": 1},
        "input.clipboard_set": {"at_ms": 0, "text": "synthetic"},
        "input.stop": {"at_ms": 0},
        "diagnostic": {"at_ms": 0, "code": "synthetic", "message": "synthetic"},
        "observation": {
            "at_ms": 0,
            "events": [],
            "state": {},
            "ui": {
                "cursor": {"column": 0, "row": 0, "visible": False},
                "focus": None,
                "mode": None,
                "regions": [],
            },
        },
    }
    if kind in body_payloads:
        transcript[8]["kind"] = kind
        transcript[8]["payload"] = body_payloads[kind]
        if kind == "input.clock_advanced":
            observation = transcript[9]["payload"]
            assert isinstance(observation, dict)
            observation["at_ms"] = 1
        return transcript, 8
    if kind == "run.started":
        return transcript, 0
    if kind == "capability.result":
        return transcript, 1
    if kind == "run.finished":
        return transcript, len(transcript) - 1
    if kind == "run.failed":
        transcript[-1]["kind"] = kind
        transcript[-1]["payload"] = {
            "error": {"code": "adapter-runtime-failed", "message": "synthetic"}
        }
        return transcript, len(transcript) - 1
    if kind == "run.unsupported":
        capability = transcript[7]["payload"]
        assert isinstance(capability, dict)
        capability.clear()
        capability.update(
            {
                "constraint": "network",
                "reason": "synthetic",
                "status": "unsupported",
            }
        )
        transcript[8]["kind"] = kind
        transcript[8]["payload"] = {
            "code": "constraint-unsupported",
            "constraint": "network",
            "message": "synthetic",
        }
        del transcript[9:]
        return transcript, 8
    raise AssertionError(f"unsupported test kind: {kind}")


def _add_complete_observation_evidence(payload: dict[str, JsonValue]) -> None:
    payload["events"] = [{"data": {}, "type": "synthetic"}]
    ui = payload["ui"]
    assert isinstance(ui, dict)
    ui["regions"] = [
        {
            "bounds": {"column": 0, "columns": 1, "row": 0, "rows": 1},
            "id": "main",
            "role": "main",
        }
    ]
    payload["frame"] = {"columns": 1, "lines": [""], "rows": 1}
    payload["process"] = {
        "exit": {"kind": "code", "value": 0},
        "state": "exited",
    }


@pytest.mark.parametrize(
    "kind",
    [
        "run.started",
        "capability.result",
        "input.key",
        "input.text",
        "input.resize",
        "input.mouse",
        "input.clock_advanced",
        "input.clipboard_set",
        "input.stop",
        "observation",
        "diagnostic",
        "run.finished",
        "run.failed",
        "run.unsupported",
    ],
)
def test_serialize_transcript_rejects_unknown_generic_payload_member(kind: str) -> None:
    transcript, index = _transcript_with_payload_kind(kind)
    payload = transcript[index]["payload"]
    assert isinstance(payload, dict)
    payload["unexpected"] = True

    with pytest.raises(TranscriptValidationError, match="member"):
        serialize_transcript(transcript)
    encoded = (
        b"\n".join(
            json.dumps(
                record, ensure_ascii=False, separators=(",", ":"), sort_keys=True
            ).encode()
            for record in transcript
        )
        + b"\n"
    )
    with pytest.raises(TranscriptValidationError, match="member"):
        parse_transcript(encoded)


@pytest.mark.parametrize(
    ("kind", "path"),
    [
        ("run.finished", ("exit",)),
        ("run.failed", ("error",)),
        ("observation", ("ui",)),
        ("observation", ("ui", "cursor")),
        ("observation", ("events", 0)),
        ("observation", ("ui", "regions", 0)),
        ("observation", ("ui", "regions", 0, "bounds")),
        ("observation", ("frame",)),
        ("observation", ("process",)),
        ("observation", ("process", "exit")),
    ],
)
def test_serialize_transcript_rejects_unknown_nested_generic_member(
    kind: str, path: tuple[str | int, ...]
) -> None:
    transcript, index = _transcript_with_payload_kind(kind)
    payload = transcript[index]["payload"]
    assert isinstance(payload, dict)
    if kind == "observation":
        _add_complete_observation_evidence(payload)
    target: JsonValue = payload
    for member in path:
        if isinstance(member, str):
            assert isinstance(target, dict)
            target = target[member]
        else:
            assert isinstance(target, list)
            target = target[member]
    assert isinstance(target, dict)
    target["unexpected"] = True

    with pytest.raises(TranscriptValidationError, match="invalid|member"):
        serialize_transcript(transcript)


@pytest.mark.parametrize(
    ("status", "extra_member"),
    [("enforced", "reason"), ("unsupported", "effective")],
)
def test_serialize_transcript_rejects_capability_member_for_wrong_status(
    status: str, extra_member: str
) -> None:
    transcript, _ = _transcript_with_payload_kind("run.unsupported")
    capability = transcript[7]["payload"]
    assert isinstance(capability, dict)
    if status == "enforced":
        transcript, _ = _transcript_with_payload_kind("capability.result")
        capability = transcript[1]["payload"]
        assert isinstance(capability, dict)
        capability[extra_member] = "synthetic"
    else:
        capability[extra_member] = {"mode": "deny"}

    with pytest.raises(TranscriptValidationError, match="member"):
        serialize_transcript(transcript)


@pytest.mark.parametrize(
    ("kind", "path"),
    [
        ("run.started", ()),
        ("capability.result", ()),
        ("input.key", ()),
        ("input.text", ()),
        ("input.resize", ()),
        ("input.mouse", ()),
        ("input.clock_advanced", ()),
        ("input.clipboard_set", ()),
        ("input.stop", ()),
        ("diagnostic", ()),
        ("observation", ()),
        ("run.finished", ()),
        ("run.finished", ("exit",)),
        ("run.failed", ()),
        ("run.failed", ("error",)),
        ("run.unsupported", ()),
        ("observation", ("ui",)),
        ("observation", ("ui", "cursor")),
        ("observation", ("events", 0)),
        ("observation", ("ui", "regions", 0)),
        ("observation", ("ui", "regions", 0, "bounds")),
        ("observation", ("frame",)),
        ("observation", ("process",)),
        ("observation", ("process", "exit")),
    ],
)
def test_serialize_transcript_accepts_extension_in_closed_object(
    kind: str, path: tuple[str | int, ...]
) -> None:
    transcript, index = _transcript_with_payload_kind(kind)
    target = transcript[index]["payload"]
    assert isinstance(target, dict)
    if kind == "observation":
        _add_complete_observation_evidence(target)
    for member in path:
        if isinstance(member, str):
            assert isinstance(target, dict)
            target = target[member]
        else:
            assert isinstance(target, list)
            target = target[member]
    assert isinstance(target, dict)
    target["x-synthetic"] = {"uninterpreted": True}

    assert parse_transcript(serialize_transcript(transcript)) == transcript
