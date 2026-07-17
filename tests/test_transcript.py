from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Never, cast

import pytest

from termverify.transcript import (
    JsonValue,
    TranscriptValidationError,
    parse_transcript,
    serialize_transcript,
)

FIXTURES = Path("tests/fixtures/transcripts/v1")
READINESS_INDEX = 8
INPUT_INDEX = 9
OBSERVATION_INDEX = 10
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


class _ExplodingList(list[object]):
    def __iter__(self) -> Never:
        raise RuntimeError("list subclass iteration must not run")


class _ExplodingDict(dict[object, object]):
    def items(self) -> Never:
        raise RuntimeError("dict subclass items must not run")


class _ExplodingClassLookup:
    def __getattribute__(self, name: str) -> object:
        if name == "__class__":
            raise RuntimeError("class lookup must not run")
        return super().__getattribute__(name)


def _json_value_count(value: JsonValue) -> int:
    pending = [value]
    count = 0
    while pending:
        current = pending.pop()
        count += 1
        if isinstance(current, list):
            pending.extend(current)
        elif isinstance(current, dict):
            pending.extend(current.values())
    return count


def _json_string_bytes(value: JsonValue) -> int:
    pending = [value]
    total = 0
    while pending:
        current = pending.pop()
        if isinstance(current, str):
            total += len(current.encode())
        elif isinstance(current, list):
            pending.extend(current)
        elif isinstance(current, dict):
            total += sum(len(key.encode()) for key in current)
            pending.extend(current.values())
    return total


def _set_observation_record_string_bytes(
    transcript: list[dict[str, JsonValue]], target: int
) -> None:
    payload = transcript[OBSERVATION_INDEX]["payload"]
    assert isinstance(payload, dict)
    state: list[JsonValue] = ["x" * (1024 * 1024), ""]
    payload["state"] = state
    remaining = target - _json_string_bytes(transcript[OBSERVATION_INDEX])
    assert 0 <= remaining <= 1024 * 1024
    state[1] = "y" * remaining
    assert _json_string_bytes(transcript[OBSERVATION_INDEX]) == target


def _set_observation_record_value_count(
    transcript: list[dict[str, JsonValue]], target: int
) -> None:
    payload = transcript[OBSERVATION_INDEX]["payload"]
    assert isinstance(payload, dict)
    state: list[JsonValue] = [[] for _ in range(10)]
    payload["state"] = state
    remaining = target - _json_value_count(transcript[OBSERVATION_INDEX])
    for child in state:
        assert isinstance(child, list)
        added = min(10_000, remaining)
        child.extend([None] * added)
        remaining -= added
    assert remaining == 0
    assert _json_value_count(transcript[OBSERVATION_INDEX]) == target


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
        "observation",
        "input.text",
        "observation",
        "run.finished",
    ]


def test_parse_transcript_rejects_total_bytes_before_framing() -> None:
    oversized = b" " * (32 * 1024 * 1024 + 1)

    with pytest.raises(TranscriptValidationError, match="transcript bytes"):
        parse_transcript(oversized)


def test_parse_transcript_rejects_line_bytes_before_json_decoding() -> None:
    oversized = b" " * (4 * 1024 * 1024 + 1) + b"\n"

    with pytest.raises(TranscriptValidationError, match="line 1 bytes"):
        parse_transcript(oversized)


def test_parse_transcript_rejects_record_count_before_json_decoding() -> None:
    oversized = b"x\n" * 10_001

    with pytest.raises(TranscriptValidationError, match="record count"):
        parse_transcript(oversized)


def test_parse_transcript_requires_initial_readiness_observation() -> None:
    records = [
        json.loads(line)
        for line in (FIXTURES / "valid" / "basic.jsonl").read_bytes().splitlines()
    ]
    del records[READINESS_INDEX]
    for sequence, record in enumerate(records):
        record["id"] = f"record-{sequence:03d}"
        record["seq"] = sequence
    fixture = b"".join(
        json.dumps(
            record, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        ).encode()
        + b"\n"
        for record in records
    )

    with pytest.raises(TranscriptValidationError, match="initial readiness"):
        parse_transcript(fixture)


def test_serialize_transcript_rejects_overlapping_input_epochs() -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    overlapping_input = deepcopy(transcript[INPUT_INDEX])
    transcript.insert(OBSERVATION_INDEX, overlapping_input)
    for sequence, record in enumerate(transcript):
        record["id"] = f"record-{sequence:03d}"
        record["seq"] = sequence

    with pytest.raises(TranscriptValidationError, match="input epoch"):
        serialize_transcript(transcript)


def test_serialize_transcript_rejects_unsolicited_idle_observation() -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    transcript.insert(INPUT_INDEX, deepcopy(transcript[READINESS_INDEX]))
    for sequence, record in enumerate(transcript):
        record["id"] = f"record-{sequence:03d}"
        record["seq"] = sequence

    with pytest.raises(TranscriptValidationError, match="idle"):
        serialize_transcript(transcript)


def test_serialize_transcript_rejects_unsolicited_idle_diagnostic() -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    diagnostic = deepcopy(transcript[READINESS_INDEX])
    diagnostic["kind"] = "diagnostic"
    diagnostic["payload"] = {
        "at_ms": 0,
        "code": "synthetic",
        "message": "synthetic",
    }
    transcript.insert(INPUT_INDEX, diagnostic)
    for sequence, record in enumerate(transcript):
        record["id"] = f"record-{sequence:03d}"
        record["seq"] = sequence

    with pytest.raises(TranscriptValidationError, match="idle"):
        serialize_transcript(transcript)


def test_serialize_transcript_rejects_input_after_stop() -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    later_input = deepcopy(transcript[INPUT_INDEX])
    transcript[INPUT_INDEX]["kind"] = "input.stop"
    transcript[INPUT_INDEX]["payload"] = {"at_ms": 0}
    transcript.insert(-1, later_input)
    for sequence, record in enumerate(transcript):
        record["id"] = f"record-{sequence:03d}"
        record["seq"] = sequence

    with pytest.raises(TranscriptValidationError, match="after input.stop"):
        serialize_transcript(transcript)


def test_serialize_transcript_rejects_body_after_process_exit_observation() -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    observation_payload = transcript[OBSERVATION_INDEX]["payload"]
    assert isinstance(observation_payload, dict)
    observation_payload["process"] = {
        "state": "exited",
        "exit": {"kind": "code", "value": 0},
    }
    transcript.insert(OBSERVATION_INDEX + 1, deepcopy(transcript[INPUT_INDEX]))
    for sequence, record in enumerate(transcript):
        record["id"] = f"record-{sequence:03d}"
        record["seq"] = sequence

    with pytest.raises(TranscriptValidationError, match="process exit observation"):
        serialize_transcript(transcript)


def test_transcript_accepts_adapter_failure_before_capability_results() -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    failed = deepcopy(transcript[-1])
    failed["kind"] = "run.failed"
    failed["payload"] = {
        "error": {"code": "adapter-start-failed", "message": "synthetic"}
    }
    transcript = [transcript[0], failed]
    for sequence, record in enumerate(transcript):
        record["id"] = f"record-{sequence:03d}"
        record["seq"] = sequence

    encoded = serialize_transcript(transcript)

    assert parse_transcript(encoded) == transcript


def test_parse_transcript_rejects_wrong_protocol_fixture() -> None:
    fixture = (FIXTURES / "invalid" / "wrong-protocol.jsonl").read_bytes()

    with pytest.raises(TranscriptValidationError, match="protocol"):
        parse_transcript(fixture)


def test_serialize_transcript_emits_canonical_fixture_bytes() -> None:
    fixture = (FIXTURES / "valid" / "basic.jsonl").read_bytes()

    assert serialize_transcript(parse_transcript(fixture)) == fixture


@pytest.mark.parametrize("framing", ["all-crlf", "mixed-crlf", "bare-cr"])
def test_parse_transcript_rejects_non_lf_record_separators(framing: str) -> None:
    fixture = (FIXTURES / "valid" / "basic.jsonl").read_bytes()
    if framing == "all-crlf":
        invalid = fixture.replace(b"\n", b"\r\n")
    elif framing == "mixed-crlf":
        invalid = fixture.replace(b"\n", b"\r\n", 1)
    else:
        invalid = b"\r".join(fixture.splitlines()) + b"\n"

    with pytest.raises(TranscriptValidationError, match="LF"):
        parse_transcript(invalid)


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


@pytest.mark.parametrize("api", ["parse", "serialize"])
@pytest.mark.parametrize("seed", ["18446744073709551616", "9" * 5_000])
def test_transcript_rejects_out_of_range_decimal_seed_cleanly(
    api: str, seed: str
) -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    payload = transcript[0]["payload"]
    assert isinstance(payload, dict)
    config = payload["config"]
    assert isinstance(config, dict)
    config["seed"] = seed
    capability_payload = transcript[1]["payload"]
    assert isinstance(capability_payload, dict)
    capability_payload["effective"] = seed

    with pytest.raises(TranscriptValidationError, match="seed"):
        if api == "parse":
            parse_transcript(
                b"\n".join(
                    json.dumps(
                        record,
                        ensure_ascii=False,
                        separators=(",", ":"),
                        sort_keys=True,
                    ).encode()
                    for record in transcript
                )
                + b"\n"
            )
        else:
            serialize_transcript(transcript)


def test_transcript_accepts_maximum_unsigned_64_bit_seed() -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    maximum_seed = "18446744073709551615"
    payload = transcript[0]["payload"]
    assert isinstance(payload, dict)
    config = payload["config"]
    assert isinstance(config, dict)
    config["seed"] = maximum_seed
    capability_payload = transcript[1]["payload"]
    assert isinstance(capability_payload, dict)
    capability_payload["effective"] = maximum_seed

    encoded = serialize_transcript(transcript)

    assert parse_transcript(encoded) == transcript


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


@pytest.mark.parametrize("record", [[], "record", 1, None])
def test_serialize_transcript_rejects_non_object_record(record: object) -> None:
    records = cast(list[dict[str, JsonValue]], [record])

    with pytest.raises(TranscriptValidationError, match="record must be an object"):
        serialize_transcript(records)


def test_serialize_transcript_rejects_non_list_record_collection() -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    records = cast(list[dict[str, JsonValue]], tuple(transcript))

    with pytest.raises(TranscriptValidationError, match="records must be a list"):
        serialize_transcript(records)


def test_serialize_transcript_rejects_record_count_before_record_validation() -> None:
    records = cast(list[dict[str, JsonValue]], [{}] * 10_001)

    with pytest.raises(TranscriptValidationError, match="record count"):
        serialize_transcript(records)


def test_transcript_accepts_record_count_at_v1_limit() -> None:
    basic = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    transcript = deepcopy(basic[:INPUT_INDEX])
    for _ in range(4_995):
        transcript.extend(
            (deepcopy(basic[INPUT_INDEX]), deepcopy(basic[OBSERVATION_INDEX]))
        )
    transcript.append(deepcopy(basic[-1]))
    for sequence, record in enumerate(transcript):
        record["id"] = f"record-{sequence:05d}"
        record["seq"] = sequence

    encoded = serialize_transcript(transcript)

    assert len(transcript) == 10_000
    assert parse_transcript(encoded) == transcript


@pytest.mark.parametrize(
    "location",
    ["record-collection", "record", "nested-list", "nested-object"],
)
def test_serialize_transcript_rejects_container_subclass_without_invoking_it(
    location: str,
) -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    records = transcript
    if location == "record-collection":
        records = cast(list[dict[str, JsonValue]], _ExplodingList(transcript))
    elif location == "record":
        records[0] = cast(dict[str, JsonValue], _ExplodingDict(records[0]))
    else:
        payload = transcript[OBSERVATION_INDEX]["payload"]
        assert isinstance(payload, dict)
        value: object
        if location == "nested-list":
            value = _ExplodingList(["ready"])
        else:
            value = _ExplodingDict({"ready": True})
        cast(dict[str, object], payload)["state"] = value

    with pytest.raises(TranscriptValidationError):
        serialize_transcript(records)


def test_serialize_transcript_rejects_host_value_without_class_lookup() -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    payload = transcript[OBSERVATION_INDEX]["payload"]
    assert isinstance(payload, dict)
    cast(dict[str, object], payload)["state"] = _ExplodingClassLookup()

    with pytest.raises(TranscriptValidationError, match="unsupported JSON value type"):
        serialize_transcript(transcript)


@pytest.mark.parametrize(
    "location",
    ["envelope", "config", "nested-protocol", "extension", "application-data"],
)
def test_serialize_transcript_rejects_non_string_json_object_key(
    location: str,
) -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    started = transcript[0]["payload"]
    observation = transcript[OBSERVATION_INDEX]["payload"]
    assert isinstance(started, dict)
    assert isinstance(observation, dict)
    config = started["config"]
    assert isinstance(config, dict)
    if location == "envelope":
        target: object = transcript[0]
    elif location == "config":
        target = config
    elif location == "nested-protocol":
        target = config["terminal"]
    elif location == "extension":
        observation["x-data"] = {}
        target = observation["x-data"]
    else:
        observation["state"] = {}
        target = observation["state"]
    assert isinstance(target, dict)
    cast(dict[object, object], target)[1] = "invalid"

    with pytest.raises(TranscriptValidationError, match="keys must be strings"):
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
    transcript[9]["kind"] = "run.started"
    transcript[9]["payload"] = transcript[0]["payload"]

    with pytest.raises(TranscriptValidationError, match="run.started"):
        serialize_transcript(transcript)


def test_serialize_transcript_rejects_intermediate_terminal_record() -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    transcript[9]["kind"] = "run.failed"
    transcript[9]["payload"] = {
        "error": {"code": "adapter-runtime-failed", "message": "failed"}
    }

    with pytest.raises(TranscriptValidationError, match="terminal"):
        serialize_transcript(transcript)


def test_serialize_transcript_rejects_record_after_terminal() -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    record = transcript[9].copy()
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
    payload = transcript[10]["payload"]
    assert isinstance(payload, dict)
    payload["state"] = {"value": float("nan")}

    with pytest.raises(TranscriptValidationError, match="JSON number"):
        serialize_transcript(transcript)


@pytest.mark.parametrize("location", ["state", "extension"])
@pytest.mark.parametrize("magnitude", ["ordinary", "oversized"])
def test_serialize_transcript_rejects_out_of_domain_python_integer_cleanly(
    location: str, magnitude: str
) -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    payload = transcript[10]["payload"]
    assert isinstance(payload, dict)
    value = 2**53 if magnitude == "ordinary" else 10**4_999
    if location == "state":
        payload["state"] = {"value": value}
    else:
        payload["x-large-integer"] = value

    with pytest.raises(TranscriptValidationError, match="canonicalized"):
        serialize_transcript(transcript)


@pytest.mark.parametrize("location", ["state", "extension"])
def test_serialize_transcript_rejects_tuple_json_value(location: str) -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    payload = transcript[10]["payload"]
    assert isinstance(payload, dict)
    key = "state" if location == "state" else "x-array"
    cast(dict[str, object], payload)[key] = ("ready",)

    with pytest.raises(TranscriptValidationError, match="JSON arrays must use lists"):
        serialize_transcript(transcript)


@pytest.mark.parametrize("location", ["state", "extension"])
def test_serialize_transcript_rejects_unsupported_host_json_value(
    location: str,
) -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    payload = transcript[OBSERVATION_INDEX]["payload"]
    assert isinstance(payload, dict)
    key = "state" if location == "state" else "x-host-value"
    cast(dict[str, object], payload)[key] = object()

    with pytest.raises(TranscriptValidationError, match="unsupported JSON value"):
        serialize_transcript(transcript)


def test_serialize_transcript_preserves_list_json_value() -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    payload = transcript[10]["payload"]
    assert isinstance(payload, dict)
    payload["state"] = ["ready"]

    assert parse_transcript(serialize_transcript(transcript)) == transcript


@pytest.mark.parametrize("collection", ["array", "object"])
def test_serialize_transcript_rejects_collection_beyond_v1_limit(
    collection: str,
) -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    payload = transcript[OBSERVATION_INDEX]["payload"]
    assert isinstance(payload, dict)
    payload["state"] = (
        list(range(16_385))
        if collection == "array"
        else {f"item-{index}": None for index in range(16_385)}
    )

    with pytest.raises(TranscriptValidationError, match="collection"):
        serialize_transcript(transcript)


@pytest.mark.parametrize("collection", ["array", "object"])
def test_parse_transcript_rejects_collection_beyond_v1_limit(
    collection: str,
) -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    payload = transcript[OBSERVATION_INDEX]["payload"]
    assert isinstance(payload, dict)
    payload["state"] = (
        list(range(16_385))
        if collection == "array"
        else {f"item-{index}": None for index in range(16_385)}
    )
    encoded = b"".join(
        json.dumps(
            record, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        ).encode()
        + b"\n"
        for record in transcript
    )

    with pytest.raises(TranscriptValidationError, match="collection"):
        parse_transcript(encoded)


@pytest.mark.parametrize("collection", ["array", "object"])
def test_transcript_accepts_collection_at_v1_limit(collection: str) -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    payload = transcript[OBSERVATION_INDEX]["payload"]
    assert isinstance(payload, dict)
    payload["state"] = (
        list(range(16_384))
        if collection == "array"
        else {f"item-{index}": None for index in range(16_384)}
    )

    encoded = serialize_transcript(transcript)

    assert parse_transcript(encoded) == transcript


def test_serialize_transcript_rejects_value_nodes_beyond_v1_limit() -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    _set_observation_record_value_count(transcript, 100_001)

    with pytest.raises(TranscriptValidationError, match="value count"):
        serialize_transcript(transcript)


def test_parse_transcript_rejects_value_nodes_beyond_v1_limit() -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    _set_observation_record_value_count(transcript, 100_001)
    encoded = b"".join(
        json.dumps(
            record, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        ).encode()
        + b"\n"
        for record in transcript
    )

    with pytest.raises(TranscriptValidationError, match="value count"):
        parse_transcript(encoded)


def test_transcript_accepts_value_nodes_at_v1_limit() -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    _set_observation_record_value_count(transcript, 100_000)

    encoded = serialize_transcript(transcript)

    assert parse_transcript(encoded) == transcript


def test_serialize_transcript_rejects_string_bytes_beyond_v1_limit() -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    payload = transcript[OBSERVATION_INDEX]["payload"]
    assert isinstance(payload, dict)
    payload["state"] = "x" * (1024 * 1024 + 1)

    with pytest.raises(TranscriptValidationError, match="string bytes"):
        serialize_transcript(transcript)


def test_parse_transcript_rejects_string_bytes_beyond_v1_limit() -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    payload = transcript[OBSERVATION_INDEX]["payload"]
    assert isinstance(payload, dict)
    payload["state"] = "x" * (1024 * 1024 + 1)
    encoded = b"".join(
        json.dumps(
            record, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        ).encode()
        + b"\n"
        for record in transcript
    )

    with pytest.raises(TranscriptValidationError, match="string bytes"):
        parse_transcript(encoded)


@pytest.mark.parametrize(
    ("api", "location"),
    [("parse", "value"), ("serialize", "value"), ("serialize", "key")],
)
def test_transcript_normalizes_lone_surrogate_strings(
    api: str,
    location: str,
) -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    payload = transcript[OBSERVATION_INDEX]["payload"]
    assert isinstance(payload, dict)
    if location == "key":
        payload["x-\ud800"] = None
    else:
        payload["state"] = "\ud800"

    with pytest.raises(TranscriptValidationError) as exc_info:
        if api == "serialize":
            serialize_transcript(transcript)
        else:
            encoded = b"".join(
                json.dumps(
                    record,
                    ensure_ascii=True,
                    separators=(",", ":"),
                    sort_keys=True,
                ).encode()
                + b"\n"
                for record in transcript
            )
            parse_transcript(encoded)

    assert str(exc_info.value) == "record cannot be canonicalized as RFC 8785"


@pytest.mark.parametrize("api", ["parse", "serialize"])
def test_transcript_rejects_object_key_bytes_beyond_v1_limit(api: str) -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    payload = transcript[OBSERVATION_INDEX]["payload"]
    assert isinstance(payload, dict)
    payload["x-" + "k" * (1024 * 1024)] = None

    with pytest.raises(TranscriptValidationError, match="string bytes"):
        if api == "serialize":
            serialize_transcript(transcript)
        else:
            encoded = b"".join(
                json.dumps(
                    record,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                ).encode()
                + b"\n"
                for record in transcript
            )
            parse_transcript(encoded)


def test_transcript_accepts_object_key_bytes_at_v1_limit() -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    payload = transcript[OBSERVATION_INDEX]["payload"]
    assert isinstance(payload, dict)
    payload["x-" + "k" * (1024 * 1024 - 2)] = None

    encoded = serialize_transcript(transcript)

    assert parse_transcript(encoded) == transcript


def test_transcript_accepts_individual_string_at_v1_limit() -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    payload = transcript[OBSERVATION_INDEX]["payload"]
    assert isinstance(payload, dict)
    payload["state"] = "x" * (1024 * 1024)

    encoded = serialize_transcript(transcript)

    assert parse_transcript(encoded) == transcript


def test_serialize_transcript_rejects_record_string_bytes_beyond_v1_limit() -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    _set_observation_record_string_bytes(transcript, 2 * 1024 * 1024 + 1)

    with pytest.raises(TranscriptValidationError, match="record string bytes"):
        serialize_transcript(transcript)


def test_parse_transcript_rejects_record_string_bytes_beyond_v1_limit() -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    _set_observation_record_string_bytes(transcript, 2 * 1024 * 1024 + 1)
    encoded = b"".join(
        json.dumps(
            record, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        ).encode()
        + b"\n"
        for record in transcript
    )

    with pytest.raises(TranscriptValidationError, match="record string bytes"):
        parse_transcript(encoded)


def test_transcript_accepts_record_string_bytes_at_v1_limit() -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    _set_observation_record_string_bytes(transcript, 2 * 1024 * 1024)

    encoded = serialize_transcript(transcript)

    assert parse_transcript(encoded) == transcript


def test_serialize_transcript_rejects_canonical_line_bytes_beyond_v1_limit() -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    payload = transcript[OBSERVATION_INDEX]["payload"]
    assert isinstance(payload, dict)
    payload["state"] = ""
    baseline = len(
        json.dumps(
            transcript[OBSERVATION_INDEX],
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
    )
    escaped, plain = divmod(4 * 1024 * 1024 + 1 - baseline, 6)
    payload["state"] = "\0" * escaped + "x" * plain
    oversized_line = json.dumps(
        transcript[OBSERVATION_INDEX],
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()

    assert len(oversized_line) == 4 * 1024 * 1024 + 1

    with pytest.raises(TranscriptValidationError, match="line 11 bytes"):
        serialize_transcript(transcript)


def test_transcript_accepts_canonical_line_bytes_at_v1_limit() -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    payload = transcript[OBSERVATION_INDEX]["payload"]
    assert isinstance(payload, dict)
    payload["state"] = ""
    baseline = len(
        json.dumps(
            transcript[OBSERVATION_INDEX],
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
    )
    escaped, plain = divmod(4 * 1024 * 1024 - baseline, 6)
    payload["state"] = "\0" * escaped + "x" * plain

    encoded = serialize_transcript(transcript)

    assert len(encoded.splitlines()[OBSERVATION_INDEX]) == 4 * 1024 * 1024
    assert parse_transcript(encoded) == transcript


def test_serialize_transcript_rejects_total_bytes_beyond_v1_limit() -> None:
    basic = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    transcript = deepcopy(basic[:INPUT_INDEX])
    for _ in range(8):
        transcript.extend(
            (deepcopy(basic[INPUT_INDEX]), deepcopy(basic[OBSERVATION_INDEX]))
        )
    transcript.append(deepcopy(basic[-1]))
    body_observations: list[dict[str, JsonValue]] = []
    for sequence, record in enumerate(transcript):
        record["id"] = f"record-{sequence:03d}"
        record["seq"] = sequence
        if record["kind"] == "observation" and sequence != READINESS_INDEX:
            body_observations.append(record)
    for record in body_observations[:-1]:
        payload = record["payload"]
        assert isinstance(payload, dict)
        payload["state"] = ""
        baseline = len(
            json.dumps(
                record,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode()
        )
        escaped, plain = divmod(4 * 1024 * 1024 - baseline, 6)
        payload["state"] = "\0" * escaped + "x" * plain
    final_observation = body_observations[-1]
    final_payload = final_observation["payload"]
    assert isinstance(final_payload, dict)
    final_payload["state"] = ""
    encoded_lines = [
        json.dumps(
            record, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        ).encode()
        for record in transcript
    ]
    final_index = transcript.index(final_observation)
    other_bytes = sum(len(line) + 1 for line in encoded_lines) - (
        len(encoded_lines[final_index]) + 1
    )
    final_line_bytes = 32 * 1024 * 1024 + 1 - other_bytes - 1
    remaining = final_line_bytes - len(encoded_lines[final_index])
    escaped, plain = divmod(remaining, 6)
    final_payload["state"] = "\0" * escaped + "x" * plain
    encoded_size = sum(
        len(
            json.dumps(
                record,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode()
        )
        + 1
        for record in transcript
    )

    assert encoded_size == 32 * 1024 * 1024 + 1

    with pytest.raises(TranscriptValidationError, match="transcript bytes"):
        serialize_transcript(transcript)


def test_transcript_accepts_total_bytes_at_v1_limit() -> None:
    basic = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    transcript = deepcopy(basic[:INPUT_INDEX])
    for _ in range(8):
        transcript.extend(
            (deepcopy(basic[INPUT_INDEX]), deepcopy(basic[OBSERVATION_INDEX]))
        )
    transcript.append(deepcopy(basic[-1]))
    body_observations: list[dict[str, JsonValue]] = []
    for sequence, record in enumerate(transcript):
        record["id"] = f"record-{sequence:03d}"
        record["seq"] = sequence
        if record["kind"] == "observation" and sequence != READINESS_INDEX:
            body_observations.append(record)
    for record in body_observations[:-1]:
        payload = record["payload"]
        assert isinstance(payload, dict)
        payload["state"] = ""
        baseline = len(
            json.dumps(
                record,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode()
        )
        escaped, plain = divmod(4 * 1024 * 1024 - baseline, 6)
        payload["state"] = "\0" * escaped + "x" * plain
    final_observation = body_observations[-1]
    final_payload = final_observation["payload"]
    assert isinstance(final_payload, dict)
    final_payload["state"] = ""
    encoded_lines = [
        json.dumps(
            record, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        ).encode()
        for record in transcript
    ]
    final_index = transcript.index(final_observation)
    other_bytes = sum(len(line) + 1 for line in encoded_lines) - (
        len(encoded_lines[final_index]) + 1
    )
    final_line_bytes = 32 * 1024 * 1024 - other_bytes - 1
    remaining = final_line_bytes - len(encoded_lines[final_index])
    escaped, plain = divmod(remaining, 6)
    final_payload["state"] = "\0" * escaped + "x" * plain

    encoded = serialize_transcript(transcript)

    assert len(encoded) == 32 * 1024 * 1024
    assert parse_transcript(encoded) == transcript


def test_parse_transcript_rejects_non_finite_json_number() -> None:
    fixture = (FIXTURES / "valid" / "basic.jsonl").read_text(encoding="utf-8")
    data = fixture.replace('"text":"hello"', '"text":NaN').encode("utf-8")

    with pytest.raises(TranscriptValidationError, match="JSON number"):
        parse_transcript(data)


@pytest.mark.parametrize("location", ["envelope", "nested-state"])
def test_parse_transcript_rejects_oversized_json_integer_cleanly(
    location: str,
) -> None:
    oversized_integer = b"9" * 5_000
    if location == "envelope":
        data = (
            b'{"id":"record-000","kind":"run.started","payload":{},'
            b'"protocol":"termverify.transcript/v1","run_id":"run-basic","seq":'
            + oversized_integer
            + b"}\n"
        )
    else:
        fixture = (FIXTURES / "valid" / "basic.jsonl").read_bytes()
        data = fixture.replace(
            b'"state":{}', b'"state":{"value":' + oversized_integer + b"}"
        )

    with pytest.raises(TranscriptValidationError, match="invalid JSON"):
        parse_transcript(data)


def test_parse_transcript_preserves_duplicate_member_diagnostic() -> None:
    fixture = (FIXTURES / "valid" / "basic.jsonl").read_bytes()
    data = fixture.replace(b'"seq":0}', b'"seq":0,"seq":0}', 1)

    with pytest.raises(TranscriptValidationError, match="duplicate JSON member: seq"):
        parse_transcript(data)


def test_parse_transcript_rejects_nesting_beyond_v1_limit() -> None:
    data = b"[" * 65 + b"0" + b"]" * 65 + b"\n"

    with pytest.raises(TranscriptValidationError, match="nesting"):
        parse_transcript(data)


def test_parse_transcript_ignores_brackets_inside_escaped_json_string() -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    payload = transcript[OBSERVATION_INDEX]["payload"]
    assert isinstance(payload, dict)
    payload["state"] = '\\"' + "[{" * 1_000
    encoded = serialize_transcript(transcript)

    assert parse_transcript(encoded) == transcript


def test_parse_transcript_converts_excessive_nesting_to_validation_error() -> None:
    data = b'{"x":' * 2_000 + b"0" + b"}" * 2_000 + b"\n"

    with pytest.raises(TranscriptValidationError, match="nesting"):
        parse_transcript(data)


def test_serialize_transcript_rejects_nesting_beyond_v1_limit() -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    payload = transcript[OBSERVATION_INDEX]["payload"]
    assert isinstance(payload, dict)
    root: list[JsonValue] = []
    nested = root
    for _ in range(62):
        child: list[JsonValue] = []
        nested.append(child)
        nested = child
    payload["state"] = root

    with pytest.raises(TranscriptValidationError, match="nesting"):
        serialize_transcript(transcript)


def test_transcript_accepts_nesting_at_v1_limit() -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    payload = transcript[OBSERVATION_INDEX]["payload"]
    assert isinstance(payload, dict)
    root: list[JsonValue] = []
    nested = root
    for _ in range(61):
        child: list[JsonValue] = []
        nested.append(child)
        nested = child
    payload["state"] = root

    encoded = serialize_transcript(transcript)

    assert parse_transcript(encoded) == transcript


def test_serialize_transcript_converts_excessive_nesting_to_validation_error() -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    payload = transcript[10]["payload"]
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


@pytest.mark.parametrize("container", ["array", "object"])
def test_serialize_transcript_rejects_cyclic_json_container_cleanly(
    container: str,
) -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    payload = transcript[OBSERVATION_INDEX]["payload"]
    assert isinstance(payload, dict)
    if container == "array":
        cycle: object = []
        cast(list[object], cycle).append(cycle)
    else:
        cycle = {}
        cast(dict[str, object], cycle)["self"] = cycle
    cast(dict[str, object], payload)["state"] = cycle

    with pytest.raises(TranscriptValidationError, match="nesting"):
        serialize_transcript(transcript)


def test_serialize_transcript_uses_rfc_8785_number_rendering() -> None:
    fixture = (FIXTURES / "valid" / "basic.jsonl").read_bytes()
    transcript = parse_transcript(fixture)
    payload = transcript[10]["payload"]
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


@pytest.mark.parametrize(
    ("constraint", "member"),
    [
        ("clock", "initial_ms"),
        ("terminal", "columns"),
        ("terminal", "rows"),
        ("network", "port"),
    ],
)
def test_serialize_transcript_rejects_integral_float_effective_integer(
    constraint: str,
    member: str,
) -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    started = transcript[0]["payload"]
    assert isinstance(started, dict)
    config = started["config"]
    assert isinstance(config, dict)
    result_index = {
        "clock": 2,
        "terminal": 5,
        "network": 7,
    }[constraint]
    result = transcript[result_index]["payload"]
    assert isinstance(result, dict)
    effective = result["effective"]
    assert isinstance(effective, dict)
    if constraint == "network":
        network: dict[str, JsonValue] = {
            "mode": "allow-list",
            "allowed": [{"host": "example.test", "port": 443}],
        }
        config["network"] = network
        result["effective"] = deepcopy(network)
        effective = result["effective"]
        assert isinstance(effective, dict)
        allowed = effective["allowed"]
        assert isinstance(allowed, list)
        endpoint = allowed[0]
        assert isinstance(endpoint, dict)
        endpoint[member] = 443.0
    else:
        effective[member] = float(cast(int, effective[member]))

    with pytest.raises(TranscriptValidationError, match="effective"):
        serialize_transcript(transcript)


def test_serialize_transcript_rejects_nested_numeric_category_mismatch() -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    started = transcript[0]["payload"]
    result = transcript[5]["payload"]
    assert isinstance(started, dict)
    assert isinstance(result, dict)
    config = started["config"]
    effective = result["effective"]
    assert isinstance(config, dict)
    assert isinstance(effective, dict)
    terminal = config["terminal"]
    assert isinstance(terminal, dict)
    terminal["x-thresholds"] = [1, {"value": 2}]
    effective["x-thresholds"] = [1, {"value": 2.0}]

    with pytest.raises(TranscriptValidationError, match="effective"):
        serialize_transcript(transcript)


@pytest.mark.parametrize(
    "location",
    ["input", "diagnostic", "observation", "process-exit", "terminal-exit"],
)
def test_serialize_transcript_rejects_integral_float_protocol_integer(
    location: str,
) -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    if location == "input":
        payload = transcript[INPUT_INDEX]["payload"]
        assert isinstance(payload, dict)
        payload["at_ms"] = 0.0
    elif location == "diagnostic":
        diagnostic = deepcopy(transcript[INPUT_INDEX])
        diagnostic["kind"] = "diagnostic"
        diagnostic["payload"] = {
            "at_ms": 0.0,
            "code": "synthetic",
            "message": "synthetic",
        }
        transcript.insert(INPUT_INDEX, diagnostic)
        for sequence, record in enumerate(transcript):
            record["id"] = f"record-{sequence:03d}"
            record["seq"] = sequence
    elif location == "observation":
        payload = transcript[OBSERVATION_INDEX]["payload"]
        assert isinstance(payload, dict)
        payload["at_ms"] = 0.0
    elif location == "process-exit":
        payload = transcript[OBSERVATION_INDEX]["payload"]
        assert isinstance(payload, dict)
        payload["process"] = {
            "state": "exited",
            "exit": {"kind": "code", "value": 0.0},
        }
    else:
        payload = transcript[-1]["payload"]
        assert isinstance(payload, dict)
        exit_value = payload["exit"]
        assert isinstance(exit_value, dict)
        exit_value["value"] = 0.0

    with pytest.raises(TranscriptValidationError):
        serialize_transcript(transcript)


def test_serialize_transcript_preserves_application_defined_finite_float() -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    payload = transcript[OBSERVATION_INDEX]["payload"]
    assert isinstance(payload, dict)
    payload["state"] = {"progress": 1.5}

    assert parse_transcript(serialize_transcript(transcript)) == transcript


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
    transcript[9]["payload"] = {"text": "hello"}

    with pytest.raises(TranscriptValidationError, match="at_ms"):
        serialize_transcript(transcript)


def test_serialize_transcript_rejects_text_input_without_text() -> None:
    fixture = (FIXTURES / "valid" / "basic.jsonl").read_bytes()
    transcript = parse_transcript(fixture)
    transcript[9]["payload"] = {"at_ms": 0}

    with pytest.raises(TranscriptValidationError, match="input.text"):
        serialize_transcript(transcript)


def test_serialize_transcript_rejects_unknown_v1_input_kind() -> None:
    fixture = (FIXTURES / "valid" / "basic.jsonl").read_bytes()
    transcript = parse_transcript(fixture)
    transcript[9]["kind"] = "input.unknown"

    with pytest.raises(TranscriptValidationError, match="input kind"):
        serialize_transcript(transcript)


def test_serialize_transcript_rejects_unknown_v1_record_kind() -> None:
    fixture = (FIXTURES / "valid" / "basic.jsonl").read_bytes()
    transcript = parse_transcript(fixture)
    transcript[10]["kind"] = "observation.unknown"

    with pytest.raises(TranscriptValidationError, match="record kind"):
        serialize_transcript(transcript)


def test_serialize_transcript_rejects_unknown_generic_input_member() -> None:
    fixture = (FIXTURES / "valid" / "basic.jsonl").read_bytes()
    transcript = parse_transcript(fixture)
    payload = transcript[9]["payload"]
    assert isinstance(payload, dict)
    payload["unexpected"] = True

    with pytest.raises(TranscriptValidationError, match="payload member"):
        serialize_transcript(transcript)


def test_serialize_transcript_rejects_key_input_without_normalized_keys() -> None:
    fixture = (FIXTURES / "valid" / "basic.jsonl").read_bytes()
    transcript = parse_transcript(fixture)
    transcript[9]["kind"] = "input.key"
    transcript[9]["payload"] = {"at_ms": 0, "keys": []}

    with pytest.raises(TranscriptValidationError, match="input.key"):
        serialize_transcript(transcript)


def test_serialize_transcript_rejects_resize_with_non_positive_dimensions() -> None:
    fixture = (FIXTURES / "valid" / "basic.jsonl").read_bytes()
    transcript = parse_transcript(fixture)
    transcript[9]["kind"] = "input.resize"
    transcript[9]["payload"] = {"at_ms": 0, "columns": 0, "rows": 24}

    with pytest.raises(TranscriptValidationError, match="input.resize"):
        serialize_transcript(transcript)


def test_serialize_transcript_rejects_mouse_press_without_button() -> None:
    fixture = (FIXTURES / "valid" / "basic.jsonl").read_bytes()
    transcript = parse_transcript(fixture)
    transcript[9]["kind"] = "input.mouse"
    transcript[9]["payload"] = {"action": "press", "at_ms": 0, "column": 0, "row": 0}

    with pytest.raises(TranscriptValidationError, match="input.mouse"):
        serialize_transcript(transcript)


@pytest.mark.parametrize("action", [[], {}, "drag"])
def test_transcript_rejects_invalid_mouse_action(action: JsonValue) -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    transcript[9]["kind"] = "input.mouse"
    transcript[9]["payload"] = {
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
    transcript[9]["kind"] = "input.mouse"
    transcript[9]["payload"] = {
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
    transcript[9]["kind"] = "input.mouse"
    transcript[9]["payload"] = {
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
    transcript[9]["kind"] = "input.mouse"
    payload: dict[str, JsonValue] = {
        "action": "move",
        "at_ms": 0,
        "column": 0,
        "row": 0,
    }
    payload[member] = None
    transcript[9]["payload"] = payload

    with pytest.raises(TranscriptValidationError, match="mouse move"):
        serialize_transcript(transcript)


@pytest.mark.parametrize("action", ["press", "release"])
def test_serialize_transcript_rejects_delta_member_for_mouse_button_action(
    action: str,
) -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    transcript[9]["kind"] = "input.mouse"
    transcript[9]["payload"] = {
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
    transcript[9]["kind"] = "input.mouse"
    transcript[9]["payload"] = {
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
    transcript[9]["kind"] = "input.mouse"
    transcript[9]["payload"] = payload
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
    transcript[9]["kind"] = "input.mouse"
    transcript[9]["payload"] = payload

    assert parse_transcript(serialize_transcript(transcript)) == transcript


def test_serialize_transcript_rejects_clock_advance_with_wrong_time() -> None:
    fixture = (FIXTURES / "valid" / "basic.jsonl").read_bytes()
    transcript = parse_transcript(fixture)
    transcript[9]["kind"] = "input.clock_advanced"
    transcript[9]["payload"] = {"at_ms": 0, "delta_ms": 1}

    with pytest.raises(TranscriptValidationError, match="input.clock_advanced"):
        serialize_transcript(transcript)


@pytest.mark.parametrize("kind", ["diagnostic", "observation"])
def test_transcript_rejects_evidence_time_that_differs_from_manual_clock(
    kind: str,
) -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    payload = transcript[10]["payload"]
    assert isinstance(payload, dict)
    payload["at_ms"] = 1
    if kind == "diagnostic":
        transcript[10]["kind"] = kind
        transcript[10]["payload"] = {
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
    transcript[9]["kind"] = "input.clock_advanced"
    transcript[9]["payload"] = {"at_ms": 1, "delta_ms": 1}
    evidence = transcript[10]["payload"]
    assert isinstance(evidence, dict)
    evidence["at_ms"] = 1
    if kind == "diagnostic":
        transcript[10]["kind"] = kind
        transcript[10]["payload"] = {
            "at_ms": 1,
            "code": "synthetic",
            "message": "synthetic",
        }

    encoded = serialize_transcript(transcript)

    assert parse_transcript(encoded) == transcript


def test_serialize_transcript_rejects_clipboard_input_without_text() -> None:
    fixture = (FIXTURES / "valid" / "basic.jsonl").read_bytes()
    transcript = parse_transcript(fixture)
    transcript[9]["kind"] = "input.clipboard_set"
    transcript[9]["payload"] = {"at_ms": 0}

    with pytest.raises(TranscriptValidationError, match="input.clipboard_set"):
        serialize_transcript(transcript)


def test_serialize_transcript_rejects_stop_input_with_extra_member() -> None:
    fixture = (FIXTURES / "valid" / "basic.jsonl").read_bytes()
    transcript = parse_transcript(fixture)
    transcript[9]["kind"] = "input.stop"
    transcript[9]["payload"] = {"at_ms": 0, "reason": "unexpected"}

    with pytest.raises(TranscriptValidationError, match="input.stop"):
        serialize_transcript(transcript)


def test_serialize_transcript_rejects_diagnostic_without_code() -> None:
    fixture = (FIXTURES / "valid" / "basic.jsonl").read_bytes()
    transcript = parse_transcript(fixture)
    transcript[10]["kind"] = "diagnostic"
    transcript[10]["payload"] = {"at_ms": 0, "message": "missing code"}

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
    transcript[10]["payload"] = {"at_ms": 0}

    with pytest.raises(TranscriptValidationError, match="observation"):
        serialize_transcript(transcript)


def test_serialize_transcript_rejects_ui_without_required_members() -> None:
    fixture = (FIXTURES / "valid" / "basic.jsonl").read_bytes()
    transcript = parse_transcript(fixture)
    payload = transcript[10]["payload"]
    assert isinstance(payload, dict)
    payload["ui"] = {}

    with pytest.raises(TranscriptValidationError, match="ui"):
        serialize_transcript(transcript)


@pytest.mark.parametrize("member", ["regions", "focus", "cursor", "mode"])
def test_transcript_rejects_ui_without_required_member(member: str) -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    payload = transcript[10]["payload"]
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
    payload = transcript[10]["payload"]
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
    payload = transcript[10]["payload"]
    assert isinstance(payload, dict)
    ui = payload["ui"]
    assert isinstance(ui, dict)
    ui["focus"] = "missing-region"

    with pytest.raises(TranscriptValidationError, match="focus"):
        serialize_transcript(transcript)


def test_serialize_transcript_rejects_observation_event_without_type() -> None:
    fixture = (FIXTURES / "valid" / "basic.jsonl").read_bytes()
    transcript = parse_transcript(fixture)
    payload = transcript[10]["payload"]
    assert isinstance(payload, dict)
    payload["events"] = [{"data": None}]

    with pytest.raises(TranscriptValidationError, match="event"):
        serialize_transcript(transcript)


def test_serialize_transcript_rejects_frame_with_wrong_line_count() -> None:
    fixture = (FIXTURES / "valid" / "basic.jsonl").read_bytes()
    transcript = parse_transcript(fixture)
    payload = transcript[10]["payload"]
    assert isinstance(payload, dict)
    payload["frame"] = {"columns": 80, "lines": [""], "rows": 2}

    with pytest.raises(TranscriptValidationError, match="frame"):
        serialize_transcript(transcript)


def test_serialize_transcript_rejects_exited_process_without_exit() -> None:
    fixture = (FIXTURES / "valid" / "basic.jsonl").read_bytes()
    transcript = parse_transcript(fixture)
    payload = transcript[10]["payload"]
    assert isinstance(payload, dict)
    payload["process"] = {"state": "exited"}

    with pytest.raises(TranscriptValidationError, match="process"):
        serialize_transcript(transcript)


def test_transcript_rejects_exited_process_code_that_differs_from_finished() -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    payload = transcript[10]["payload"]
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
    observation = transcript[10]["payload"]
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
    observation = transcript[10]["payload"]
    terminal = transcript[-1]["payload"]
    assert isinstance(observation, dict)
    assert isinstance(terminal, dict)
    observation["process"] = {"exit": deepcopy(exit_value), "state": "exited"}
    terminal["exit"] = deepcopy(exit_value)

    encoded = serialize_transcript(transcript)

    assert parse_transcript(encoded) == transcript


def test_transcript_exit_coherence_ignores_uninterpreted_extensions() -> None:
    transcript = parse_transcript((FIXTURES / "valid" / "basic.jsonl").read_bytes())
    observation = transcript[10]["payload"]
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
    if kind.startswith("input."):
        transcript[INPUT_INDEX]["kind"] = kind
        transcript[INPUT_INDEX]["payload"] = body_payloads[kind]
        if kind == "input.clock_advanced":
            observation = transcript[OBSERVATION_INDEX]["payload"]
            assert isinstance(observation, dict)
            observation["at_ms"] = 1
        return transcript, INPUT_INDEX
    if kind == "diagnostic":
        diagnostic = deepcopy(transcript[INPUT_INDEX])
        diagnostic["kind"] = kind
        diagnostic["payload"] = body_payloads[kind]
        transcript.insert(OBSERVATION_INDEX, diagnostic)
        for sequence, record in enumerate(transcript):
            record["id"] = f"record-{sequence:03d}"
            record["seq"] = sequence
        return transcript, OBSERVATION_INDEX
    if kind == "observation":
        return transcript, OBSERVATION_INDEX
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
        transcript[READINESS_INDEX]["kind"] = kind
        transcript[READINESS_INDEX]["payload"] = {
            "code": "constraint-unsupported",
            "constraint": "network",
            "message": "synthetic",
        }
        del transcript[READINESS_INDEX + 1 :]
        return transcript, READINESS_INDEX
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
