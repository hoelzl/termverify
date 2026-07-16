from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from termverify.evidence import (
    JsonValue,
    persist_transcript_evidence,
    redact_evidence,
)
from termverify.transcript import TranscriptValidationError, parse_transcript

TRANSCRIPT_FIXTURE = Path("tests/fixtures/transcripts/v1/valid/basic.jsonl")


def test_persist_transcript_evidence_redacts_text_before_canonical_write(
    tmp_path: Path,
) -> None:
    records = parse_transcript(TRANSCRIPT_FIXTURE.read_bytes())
    input_payload = records[9]["payload"]
    assert isinstance(input_payload, dict)
    input_payload["text"] = "password=hunter2"
    destination = tmp_path / "artifacts" / "nested" / "transcript.jsonl"

    persist_transcript_evidence(destination, records)

    persisted = parse_transcript(destination.read_bytes())
    assert persisted[9]["payload"] == {
        "at_ms": 0,
        "text": "<redacted:input-text>",
    }
    assert input_payload["text"] == "password=hunter2"


def test_persist_transcript_evidence_preserves_replay_subject(
    tmp_path: Path,
) -> None:
    records = parse_transcript(TRANSCRIPT_FIXTURE.read_bytes())
    started_payload = records[0]["payload"]
    assert isinstance(started_payload, dict)
    subject = deepcopy(started_payload["subject"])
    destination = tmp_path / "transcript.jsonl"

    persist_transcript_evidence(destination, records)

    persisted = parse_transcript(destination.read_bytes())
    persisted_started = persisted[0]["payload"]
    assert isinstance(persisted_started, dict)
    assert persisted_started["subject"] == subject


def test_persist_transcript_evidence_rejects_credential_shaped_subject_selector(
    tmp_path: Path,
) -> None:
    records = parse_transcript(TRANSCRIPT_FIXTURE.read_bytes())
    started_payload = records[0]["payload"]
    assert isinstance(started_payload, dict)
    subject = started_payload["subject"]
    assert isinstance(subject, dict)
    application = subject["application"]
    assert isinstance(application, dict)
    application["build"] = "ghp_" + "a" * 24
    destination = tmp_path / "transcript.jsonl"

    with pytest.raises(ValueError, match="credential-shaped selector"):
        persist_transcript_evidence(destination, records)

    assert not destination.exists()


def test_persist_transcript_evidence_redacts_subject_extensions_only(
    tmp_path: Path,
) -> None:
    records = parse_transcript(TRANSCRIPT_FIXTURE.read_bytes())
    started_payload = records[0]["payload"]
    assert isinstance(started_payload, dict)
    subject = started_payload["subject"]
    assert isinstance(subject, dict)
    normalizer = subject["normalizer"]
    assert isinstance(normalizer, dict)
    subject["x-private"] = {"hostname": "private-host"}
    subject["x-credential"] = "ghp_" + "a" * 24
    normalizer["x-private"] = "private normalizer detail"
    application = deepcopy(subject["application"])
    destination = tmp_path / "transcript.jsonl"

    persist_transcript_evidence(destination, records)

    persisted = parse_transcript(destination.read_bytes())
    persisted_started = persisted[0]["payload"]
    assert isinstance(persisted_started, dict)
    persisted_subject = persisted_started["subject"]
    assert isinstance(persisted_subject, dict)
    assert persisted_subject["application"] == application
    assert persisted_subject["x-private"] == "<redacted:extension>"
    assert persisted_subject["x-credential"] == "<redacted:extension>"
    persisted_normalizer = persisted_subject["normalizer"]
    assert isinstance(persisted_normalizer, dict)
    assert persisted_normalizer["x-private"] == "<redacted:extension>"


def test_persist_transcript_evidence_redacts_nested_config_extension(
    tmp_path: Path,
) -> None:
    records = parse_transcript(TRANSCRIPT_FIXTURE.read_bytes())
    started_payload = records[0]["payload"]
    assert isinstance(started_payload, dict)
    config = started_payload["config"]
    assert isinstance(config, dict)
    terminal = config["terminal"]
    assert isinstance(terminal, dict)
    terminal["x-private"] = "private terminal detail"
    capability_payload = records[5]["payload"]
    assert isinstance(capability_payload, dict)
    capability_payload["effective"] = deepcopy(terminal)
    destination = tmp_path / "transcript.jsonl"

    persist_transcript_evidence(destination, records)

    persisted = parse_transcript(destination.read_bytes())
    persisted_started = persisted[0]["payload"]
    assert isinstance(persisted_started, dict)
    persisted_config = persisted_started["config"]
    assert isinstance(persisted_config, dict)
    persisted_terminal = persisted_config["terminal"]
    assert isinstance(persisted_terminal, dict)
    assert persisted_terminal["x-private"] == "<redacted:extension>"
    persisted_capability = persisted[5]["payload"]
    assert isinstance(persisted_capability, dict)
    assert persisted_capability["effective"] == persisted_terminal


def test_persist_transcript_evidence_redacts_semantic_evidence_fields(
    tmp_path: Path,
) -> None:
    records = parse_transcript(TRANSCRIPT_FIXTURE.read_bytes())
    input_record = records[9]
    input_record["kind"] = "input.clipboard_set"
    input_payload = input_record["payload"]
    assert isinstance(input_payload, dict)
    input_payload["text"] = "copied secret"
    observation = records[10]
    observation["x-private"] = {"value": "extension secret"}
    observation_payload = observation["payload"]
    assert isinstance(observation_payload, dict)
    observation_payload.update(
        {
            "state": {"account": "private"},
            "events": [{"type": "saved", "data": {"value": "private"}}],
            "frame": {"columns": 80, "rows": 1, "lines": ["private frame"]},
            "x-private": {"value": "payload secret"},
        }
    )
    terminal_payload = records[-1]["payload"]
    assert isinstance(terminal_payload, dict)
    records[-1]["kind"] = "run.failed"
    terminal_payload.clear()
    terminal_payload["error"] = {
        "code": "adapter-runtime-failed",
        "message": "private diagnostic",
        "details": {"trace": "private trace"},
    }
    destination = tmp_path / "nested" / "transcript.jsonl"

    persist_transcript_evidence(destination, records)

    persisted = parse_transcript(destination.read_bytes())
    assert persisted[9]["payload"] == {
        "at_ms": 0,
        "text": "<redacted:clipboard>",
    }
    persisted_observation = persisted[10]
    assert persisted_observation["x-private"] == "<redacted:extension>"
    assert persisted_observation["payload"] == {
        "at_ms": 0,
        "events": [{"type": "saved", "data": "<redacted:event-data>"}],
        "frame": {
            "columns": 80,
            "rows": 1,
            "lines": ["<redacted:frame>"],
        },
        "state": "<redacted:state>",
        "ui": {
            "cursor": {"column": 0, "row": 0, "visible": False},
            "focus": None,
            "mode": None,
            "regions": [],
        },
        "x-private": "<redacted:extension>",
    }
    assert persisted[-1]["payload"] == {
        "error": {
            "code": "adapter-runtime-failed",
            "message": "<redacted:diagnostic>",
            "details": "<redacted:diagnostic>",
        }
    }


def test_persist_transcript_evidence_redacts_sandbox_and_network_identity(
    tmp_path: Path,
) -> None:
    records = parse_transcript(TRANSCRIPT_FIXTURE.read_bytes())
    started_payload = records[0]["payload"]
    assert isinstance(started_payload, dict)
    config = started_payload["config"]
    assert isinstance(config, dict)
    config["filesystem"] = {
        "mode": "sandbox",
        "root_id": "C:/Users/example/private",
    }
    config["network"] = {
        "mode": "allow-list",
        "allowed": [
            {"host": "a.internal.example", "port": 443},
            {"host": "z.internal.example", "port": 443},
        ],
    }
    filesystem_result = records[6]["payload"]
    network_result = records[7]["payload"]
    assert isinstance(filesystem_result, dict)
    assert isinstance(network_result, dict)
    filesystem_result["effective"] = deepcopy(config["filesystem"])
    network_result["effective"] = deepcopy(config["network"])
    destination = tmp_path / "transcript.jsonl"

    persist_transcript_evidence(destination, records)

    persisted = parse_transcript(destination.read_bytes())
    persisted_started = persisted[0]["payload"]
    assert isinstance(persisted_started, dict)
    persisted_config = persisted_started["config"]
    assert isinstance(persisted_config, dict)
    assert persisted_config["filesystem"] == {
        "mode": "sandbox",
        "root_id": "<redacted:sandbox-root>",
    }
    assert persisted_config["network"] == {
        "mode": "allow-list",
        "allowed": [
            {"host": "<redacted:network-host-0000>", "port": 443},
            {"host": "<redacted:network-host-0001>", "port": 443},
        ],
    }
    assert persisted[6]["payload"] == {
        "constraint": "filesystem",
        "effective": persisted_config["filesystem"],
        "status": "enforced",
    }
    assert persisted[7]["payload"] == {
        "constraint": "network",
        "effective": persisted_config["network"],
        "status": "enforced",
    }


def test_persist_transcript_evidence_rejects_unknown_semantic_members(
    tmp_path: Path,
) -> None:
    records = parse_transcript(TRANSCRIPT_FIXTURE.read_bytes())
    started_payload = records[0]["payload"]
    assert isinstance(started_payload, dict)
    observation_payload = records[10]["payload"]
    assert isinstance(observation_payload, dict)
    observation_payload["private"] = "unclassified observation"
    events = observation_payload["events"]
    ui = observation_payload["ui"]
    assert isinstance(events, list)
    assert isinstance(ui, dict)
    events.append(
        {
            "type": "synthetic",
            "data": None,
            "private": "unclassified event",
        }
    )
    ui["private"] = "unclassified ui"
    finished_payload = records[-1]["payload"]
    assert isinstance(finished_payload, dict)
    finished_payload["private"] = "unclassified terminal result"
    finished_exit = finished_payload["exit"]
    assert isinstance(finished_exit, dict)
    finished_exit["private"] = "unclassified exit"
    destination = tmp_path / "transcript.jsonl"

    with pytest.raises(TranscriptValidationError, match="member"):
        persist_transcript_evidence(destination, records)

    assert not destination.exists()


def test_persist_transcript_evidence_rejects_effective_unsupported_capability(
    tmp_path: Path,
) -> None:
    records = parse_transcript(TRANSCRIPT_FIXTURE.read_bytes())
    unsupported_result = records[1]
    result_payload = unsupported_result["payload"]
    assert isinstance(result_payload, dict)
    result_payload.update(
        {
            "status": "unsupported",
            "reason": "private capability reason",
            "effective": {"private": "unclassified effective value"},
        }
    )
    terminal = deepcopy(records[-1])
    terminal.update({"seq": 2, "id": "record-002", "kind": "run.unsupported"})
    terminal["payload"] = {
        "constraint": "seed",
        "code": "seed-not-enforceable",
        "message": "private unsupported message",
        "details": {"private": "unsupported details"},
    }
    records = records[:2] + [terminal]
    destination = tmp_path / "transcript.jsonl"

    with pytest.raises(TranscriptValidationError, match="members"):
        persist_transcript_evidence(destination, records)

    assert not destination.exists()


def test_persist_transcript_evidence_rejects_sensitive_retention(
    tmp_path: Path,
) -> None:
    records = parse_transcript(TRANSCRIPT_FIXTURE.read_bytes())
    destination = tmp_path / "sensitive" / "transcript.jsonl"

    with pytest.raises(ValueError, match="sensitive persistence"):
        persist_transcript_evidence(destination, records, mode="sensitive")

    assert not destination.exists()


def test_redact_evidence_redacts_nested_values() -> None:
    assert redact_evidence(
        {
            "state": {"api_token": "super-secret"},
            "events": [{"data": {"clipboard": "copied-secret"}}],
            "x-application": {"authorization": "Bearer confidential"},
        }
    ) == {
        "state": {"api_token": "<redacted:api_token>"},
        "events": [{"data": {"clipboard": "<redacted:clipboard>"}}],
        "x-application": {"authorization": "<redacted:authorization>"},
    }


def test_redact_evidence_redacts_unvalidated_replay_subject_credentials() -> None:
    credential = "ghp_" + "a" * 24

    assert redact_evidence(
        {
            "kind": "run.started",
            "payload": {"subject": {"application": {"build": credential}}},
        }
    ) == {
        "kind": "run.started",
        "payload": {"subject": {"application": {"build": "<redacted:credential>"}}},
    }


def test_redact_evidence_redacts_absolute_paths() -> None:
    assert redact_evidence(
        {"process": {"working_directory": "C:/Users/example/private"}}
    ) == {"process": {"working_directory": "<redacted:path>"}}


def test_redact_evidence_normalizes_camel_case_sensitive_keys() -> None:
    assert redact_evidence({"apiToken": "secret", "clientSecret": "secret"}) == {
        "apiToken": "<redacted:apiToken>",
        "clientSecret": "<redacted:clientSecret>",
    }


def test_redact_evidence_classifies_clipboard_payload_by_record_kind() -> None:
    record: dict[str, JsonValue] = {
        "kind": "input.clipboard_set",
        "payload": {"at_ms": 0, "text": "copied secret"},
    }

    assert redact_evidence(record) == {
        "kind": "input.clipboard_set",
        "payload": {"at_ms": 0, "text": "<redacted:clipboard>"},
    }


def test_redact_evidence_redacts_all_clipboard_payload_extensions() -> None:
    record: dict[str, JsonValue] = {
        "kind": "input.clipboard_set",
        "payload": {
            "at_ms": 0,
            "text": "copied secret",
            "x-raw": "second secret",
        },
    }

    assert redact_evidence(record) == {
        "kind": "input.clipboard_set",
        "payload": {
            "at_ms": 0,
            "text": "<redacted:clipboard>",
            "x-raw": "<redacted:clipboard>",
        },
    }


def test_redact_evidence_fails_closed_for_malformed_clipboard_payload() -> None:
    record: dict[str, JsonValue] = {
        "kind": "input.clipboard_set",
        "payload": "copied secret",
    }

    assert redact_evidence(record) == {
        "kind": "input.clipboard_set",
        "payload": "<redacted:clipboard>",
    }


def test_redact_evidence_redacts_malformed_clipboard_timestamp() -> None:
    record: dict[str, JsonValue] = {
        "kind": "input.clipboard_set",
        "payload": {"at_ms": "copied secret", "text": "copied secret"},
    }

    assert redact_evidence(record) == {
        "kind": "input.clipboard_set",
        "payload": {
            "at_ms": "<redacted:clipboard>",
            "text": "<redacted:clipboard>",
        },
    }


@pytest.mark.parametrize(
    "value",
    [
        ["../../private.txt"],
        {"raw": "C:/Users/example/private.txt"},
    ],
)
def test_redact_evidence_redacts_structured_path_values(value: JsonValue) -> None:
    assert redact_evidence({"path": value}) == {"path": "<redacted:path>"}


@pytest.mark.parametrize(
    "path",
    [
        r"\\server\share\private.txt",
        r"\\?\C:\Users\example\private.txt",
        r"C:private.txt",
        r"..\..\private.txt",
        "../../private.txt",
        "sandbox/relative.txt",
    ],
)
def test_redact_evidence_redacts_unsafe_path_forms(path: str) -> None:
    assert redact_evidence({"filePath": path}) == {"filePath": "<redacted:path>"}


@pytest.mark.parametrize(
    "text",
    [
        "Authorization: Basic dXNlcjpwYXNzd29yZA==",
        "OPENAI_API_KEY=sk-proj-abcdefghijklmnopqrstuvwxyz123456",
        "password=hunter2",
        "-----BEGIN PRIVATE KEY-----",
    ],
)
def test_redact_evidence_redacts_credentials_in_free_text(text: str) -> None:
    assert redact_evidence(text) == "<redacted:credential>"


def test_persist_transcript_evidence_rejects_non_finite_numbers(tmp_path: Path) -> None:
    records = parse_transcript(TRANSCRIPT_FIXTURE.read_bytes())
    observation_payload = records[10]["payload"]
    assert isinstance(observation_payload, dict)
    observation_payload["state"] = {"value": float("nan")}
    destination = tmp_path / "transcript.jsonl"

    with pytest.raises(TranscriptValidationError, match="finite"):
        persist_transcript_evidence(destination, records)

    assert not destination.exists()
