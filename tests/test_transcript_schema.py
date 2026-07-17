from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from termverify.transcript import (
    JsonValue,
    TranscriptValidationError,
    parse_transcript,
    serialize_transcript,
)

SCHEMA_PATH = Path("schemas/termverify.transcript/v1.schema.json")
FIXTURE_PATH = Path("tests/fixtures/transcripts/v1/valid/basic.jsonl")


def _schema() -> dict[str, Any]:
    value = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _started_record() -> dict[str, object]:
    first_line = FIXTURE_PATH.read_text(encoding="utf-8").splitlines()[0]
    value = json.loads(first_line)
    assert isinstance(value, dict)
    return value


def test_v1_schema_declares_protocol_and_draft() -> None:
    schema = _schema()

    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert (
        schema["$id"]
        == "https://termverify.dev/schemas/termverify.transcript/v1.schema.json"
    )
    assert schema["properties"]["protocol"]["const"] == "termverify.transcript/v1"


def test_v1_schema_requires_versioned_replay_subject_for_run_started() -> None:
    schema = _schema()

    subject = schema["$defs"]["replaySubject"]
    assert subject["properties"]["format"]["const"] == ("termverify.replay-subject/v1")
    assert set(subject["required"]) == {
        "format",
        "application",
        "fixture",
        "adapter",
        "normalizer",
        "state_schema",
    }
    run_started = schema["$defs"]["runStartedPayload"]
    assert set(run_started["required"]) == {"config", "subject"}
    assert run_started["properties"]["subject"] == {"$ref": "#/$defs/replaySubject"}


def test_v1_schema_closes_run_started_config_to_deterministic_members() -> None:
    schema = _schema()

    config = schema["$defs"]["runtimeConfig"]
    assert set(config["required"]) == {
        "seed",
        "clock",
        "locale",
        "timezone",
        "terminal",
        "filesystem",
        "network",
    }
    assert config["additionalProperties"] is False
    assert schema["$defs"]["runStartedPayload"]["properties"]["config"] == {
        "$ref": "#/$defs/runtimeConfig"
    }


def test_v1_schema_closes_nested_deterministic_config_members() -> None:
    schema = _schema()
    definitions = schema["$defs"]
    expected_members = {
        "clockConfig": {"mode", "initial_ms"},
        "terminalConfig": {"columns", "rows", "capabilities"},
        "filesystemConfig": {"mode", "root_id"},
        "networkAllowEntry": {"host", "port"},
    }
    for name, members in expected_members.items():
        definition = definitions[name]
        assert set(definition["required"]) == members
        assert definition["additionalProperties"] is False
    for branch in definitions["networkConfig"]["oneOf"]:
        assert branch["additionalProperties"] is False
    runtime_properties = definitions["runtimeConfig"]["properties"]
    for member in ("clock", "terminal", "filesystem", "network"):
        assert runtime_properties[member] == {"$ref": f"#/$defs/{member}Config"}


def test_v1_schema_is_valid_draft_2020_12_and_accepts_canonical_record() -> None:
    schema = _schema()
    Draft202012Validator.check_schema(schema)

    assert Draft202012Validator(schema).is_valid(_started_record())


@pytest.mark.parametrize(
    ("member", "value"),
    [
        ("seed", ""),
        ("seed", "00"),
        ("seed", "not-decimal"),
        ("seed", str(2**64)),
        ("locale", ""),
        ("timezone", ""),
    ],
)
def test_v1_schema_rejects_invalid_representable_config_scalar(
    member: str, value: str
) -> None:
    record = _started_record()
    payload = record["payload"]
    assert isinstance(payload, dict)
    config = payload["config"]
    assert isinstance(config, dict)
    config[member] = value

    assert not Draft202012Validator(_schema()).is_valid(record)


def test_v1_schema_accepts_maximum_uint64_seed() -> None:
    record = _started_record()
    payload = record["payload"]
    assert isinstance(payload, dict)
    config = payload["config"]
    assert isinstance(config, dict)
    config["seed"] = str(2**64 - 1)

    assert Draft202012Validator(_schema()).is_valid(record)


@pytest.mark.parametrize("member", ["argv", "environment", "path"])
def test_v1_schema_rejects_nested_terminal_generic_member(member: str) -> None:
    record = deepcopy(_started_record())
    payload = record["payload"]
    assert isinstance(payload, dict)
    config = payload["config"]
    assert isinstance(config, dict)
    terminal = config["terminal"]
    assert isinstance(terminal, dict)
    terminal[member] = ["private"]

    assert not Draft202012Validator(_schema()).is_valid(record)


def test_runtime_owns_terminal_capability_ordering_beyond_schema() -> None:
    records = parse_transcript(FIXTURE_PATH.read_bytes())
    payload = records[0]["payload"]
    assert isinstance(payload, dict)
    config = payload["config"]
    assert isinstance(config, dict)
    terminal = config["terminal"]
    assert isinstance(terminal, dict)
    terminal["capabilities"] = ["color", "ansi"]
    capability = records[5]["payload"]
    assert isinstance(capability, dict)
    capability["effective"] = deepcopy(terminal)

    assert Draft202012Validator(_schema()).is_valid(records[0])
    with pytest.raises(TranscriptValidationError, match="terminal"):
        serialize_transcript(records)


def test_runtime_owns_timezone_registry_membership_beyond_schema() -> None:
    schema = _schema()
    timezone_schema = schema["$defs"]["runtimeConfig"]["properties"]["timezone"]
    assert "termverify.timezone/v1" in timezone_schema["$comment"]
    records = parse_transcript(FIXTURE_PATH.read_bytes())
    payload = records[0]["payload"]
    assert isinstance(payload, dict)
    config = payload["config"]
    assert isinstance(config, dict)
    config["timezone"] = "US/Eastern"

    assert Draft202012Validator(schema).is_valid(records[0])
    with pytest.raises(TranscriptValidationError, match="timezone"):
        serialize_transcript(records)


def test_runtime_owns_semantic_key_registry_and_chord_grammar_beyond_schema() -> None:
    schema = _schema()
    assert "termverify.key/v1" in schema["$comment"]
    records = parse_transcript(FIXTURE_PATH.read_bytes())
    records[9]["kind"] = "input.key"
    records[9]["payload"] = {"at_ms": 0, "keys": ["enter"]}

    assert Draft202012Validator(schema).is_valid(records[9])
    with pytest.raises(TranscriptValidationError, match="input.key"):
        serialize_transcript(records)


def test_runtime_owns_network_pair_uniqueness_beyond_schema() -> None:
    records = parse_transcript(FIXTURE_PATH.read_bytes())
    payload = records[0]["payload"]
    assert isinstance(payload, dict)
    config = payload["config"]
    assert isinstance(config, dict)
    network: dict[str, JsonValue] = {
        "allowed": [
            {"host": "example.invalid", "port": 443, "x-name": "first"},
            {"host": "example.invalid", "port": 443, "x-name": "second"},
        ],
        "mode": "allow-list",
    }
    config["network"] = network
    capability = records[7]["payload"]
    assert isinstance(capability, dict)
    capability["effective"] = deepcopy(network)

    assert Draft202012Validator(_schema()).is_valid(records[0])
    with pytest.raises(TranscriptValidationError, match="network"):
        serialize_transcript(records)


def test_runtime_owns_network_ordering_beyond_schema() -> None:
    records = parse_transcript(FIXTURE_PATH.read_bytes())
    payload = records[0]["payload"]
    assert isinstance(payload, dict)
    config = payload["config"]
    assert isinstance(config, dict)
    network: dict[str, JsonValue] = {
        "allowed": [
            {"host": "z.example.invalid", "port": 443},
            {"host": "a.example.invalid", "port": 443},
        ],
        "mode": "allow-list",
    }
    config["network"] = network
    capability = records[7]["payload"]
    assert isinstance(capability, dict)
    capability["effective"] = deepcopy(network)

    assert Draft202012Validator(_schema()).is_valid(records[0])
    with pytest.raises(TranscriptValidationError, match="network"):
        serialize_transcript(records)


def test_runtime_owns_cross_record_lifecycle_beyond_schema() -> None:
    records = parse_transcript(FIXTURE_PATH.read_bytes())
    records[1]["seq"] = 2

    validator = Draft202012Validator(_schema())
    assert all(validator.is_valid(record) for record in records)
    with pytest.raises(TranscriptValidationError, match="seq"):
        serialize_transcript(records)
