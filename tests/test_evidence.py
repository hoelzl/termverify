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
FAILED_TRANSCRIPT_FIXTURE = Path(
    "tests/fixtures/transcripts/v1/valid/failed-before-capabilities.jsonl"
)
UNSUPPORTED_TRANSCRIPT_FIXTURE = Path(
    "tests/fixtures/transcripts/v1/valid/unsupported-network.jsonl"
)


def _resequence(records: list[dict[str, JsonValue]]) -> None:
    for index, record in enumerate(records):
        record["seq"] = index
        record["id"] = f"record-{index:03d}"


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


def test_safe_persistence_preserves_valid_credential_shaped_structure(
    tmp_path: Path,
) -> None:
    records = parse_transcript(TRANSCRIPT_FIXTURE.read_bytes())
    run_id = "sk-" + "a" * 22
    for record in records:
        record["run_id"] = run_id
    started_payload = records[0]["payload"]
    assert isinstance(started_payload, dict)
    config = started_payload["config"]
    subject = started_payload["subject"]
    assert isinstance(config, dict)
    assert isinstance(subject, dict)
    application = subject["application"]
    assert isinstance(application, dict)
    config["locale"] = "sk-Latn-SK"
    application["build"] = run_id
    locale_result = records[3]["payload"]
    assert isinstance(locale_result, dict)
    locale_result["effective"] = config["locale"]
    destination = tmp_path / "transcript.jsonl"

    persist_transcript_evidence(destination, records)

    persisted = parse_transcript(destination.read_bytes())
    assert {record["run_id"] for record in persisted} == {run_id}
    persisted_started = persisted[0]["payload"]
    assert isinstance(persisted_started, dict)
    assert persisted_started["subject"] == subject
    persisted_config = persisted_started["config"]
    assert isinstance(persisted_config, dict)
    assert persisted_config["locale"] == "sk-Latn-SK"


def test_safe_persistence_transforms_semantic_strings_in_lockstep(
    tmp_path: Path,
) -> None:
    records = parse_transcript(TRANSCRIPT_FIXTURE.read_bytes())
    started_payload = records[0]["payload"]
    assert isinstance(started_payload, dict)
    config = started_payload["config"]
    assert isinstance(config, dict)
    terminal = config["terminal"]
    assert isinstance(terminal, dict)
    terminal["capabilities"] = ["AKIA" + "A" * 16, "xterm-private"]
    config["timezone"] = "private/timezone"
    timezone_result = records[4]["payload"]
    terminal_result = records[5]["payload"]
    assert isinstance(timezone_result, dict)
    assert isinstance(terminal_result, dict)
    timezone_result["effective"] = config["timezone"]
    terminal_result["effective"] = deepcopy(terminal)
    records[9]["kind"] = "input.key"
    records[9]["payload"] = {
        "at_ms": 0,
        "keys": ["xox" + "b-1234567890-secret", "private-key-name"],
    }
    observation_payload = records[10]["payload"]
    assert isinstance(observation_payload, dict)
    observation_payload.update(
        {
            "events": [{"type": "private-event", "data": {"private": True}}],
            "state": {"private": "state"},
            "frame": {"columns": 80, "rows": 1, "lines": ["private frame"]},
            "process": {
                "state": "exited",
                "exit": {"kind": "signal", "value": "PRIVATE_SIGNAL"},
            },
            "ui": {
                "cursor": {"column": 0, "row": 0, "visible": False},
                "focus": "private-region",
                "mode": "private-mode",
                "regions": [
                    {
                        "id": "private-region",
                        "role": "private-role",
                        "bounds": {"column": 0, "row": 0, "columns": 1, "rows": 1},
                    }
                ],
            },
        }
    )
    records[-1]["payload"] = {"exit": {"kind": "signal", "value": "PRIVATE_SIGNAL"}}
    records[10]["x-" + "AKIA" + "A" * 16] = "private extension"
    destination = tmp_path / "transcript.jsonl"

    persist_transcript_evidence(destination, records)

    persisted = parse_transcript(destination.read_bytes())
    persisted_started = persisted[0]["payload"]
    assert isinstance(persisted_started, dict)
    persisted_config = persisted_started["config"]
    assert isinstance(persisted_config, dict)
    assert persisted_config["timezone"] == "<redacted:timezone>"
    persisted_terminal = persisted_config["terminal"]
    assert isinstance(persisted_terminal, dict)
    assert persisted_terminal["capabilities"] == [
        "<redacted:terminal-capability-0000>",
        "<redacted:terminal-capability-0001>",
    ]
    assert persisted[4]["payload"] == {
        "constraint": "timezone",
        "effective": "<redacted:timezone>",
        "status": "enforced",
    }
    assert persisted[5]["payload"] == {
        "constraint": "terminal",
        "effective": persisted_terminal,
        "status": "enforced",
    }
    assert persisted[9]["payload"] == {
        "at_ms": 0,
        "keys": ["<redacted:key-0000>", "<redacted:key-0001>"],
    }
    persisted_observation = persisted[10]
    assert persisted_observation["x-redacted-0000"] == "<redacted:extension>"
    persisted_observation_payload = persisted_observation["payload"]
    assert isinstance(persisted_observation_payload, dict)
    assert persisted_observation_payload["events"] == [
        {"type": "<redacted:event-type-0000>", "data": "<redacted:event-data>"}
    ]
    assert persisted_observation_payload["state"] == "<redacted:state>"
    persisted_ui = persisted_observation_payload["ui"]
    assert isinstance(persisted_ui, dict)
    assert persisted_ui["focus"] == "<redacted:region-0000>"
    assert persisted_ui["mode"] == "<redacted:ui-mode>"
    assert persisted_ui["regions"] == [
        {
            "id": "<redacted:region-0000>",
            "role": "<redacted:region-role-0000>",
            "bounds": {"column": 0, "row": 0, "columns": 1, "rows": 1},
        }
    ]
    assert persisted_observation_payload["process"] == {
        "state": "exited",
        "exit": {"kind": "signal", "value": "<redacted:signal>"},
    }
    assert persisted[-1]["payload"] == {
        "exit": {"kind": "signal", "value": "<redacted:signal>"}
    }


@pytest.mark.parametrize("constraint", ["terminal", "network"])
def test_safe_persistence_preserves_order_beyond_four_digit_markers(
    tmp_path: Path,
    constraint: str,
) -> None:
    records = parse_transcript(TRANSCRIPT_FIXTURE.read_bytes())
    started_payload = records[0]["payload"]
    assert isinstance(started_payload, dict)
    config = started_payload["config"]
    assert isinstance(config, dict)
    capability_index = 5 if constraint == "terminal" else 7
    capability_payload = records[capability_index]["payload"]
    assert isinstance(capability_payload, dict)
    if constraint == "terminal":
        terminal = config["terminal"]
        assert isinstance(terminal, dict)
        terminal["capabilities"] = [
            f"capability-{index:05d}" for index in range(10_001)
        ]
        capability_payload["effective"] = deepcopy(terminal)
    else:
        network: dict[str, JsonValue] = {
            "mode": "allow-list",
            "allowed": [
                {"host": f"host-{index:05d}", "port": 443} for index in range(10_001)
            ],
        }
        config["network"] = network
        capability_payload["effective"] = deepcopy(network)
    destination = tmp_path / f"{constraint}.jsonl"

    persist_transcript_evidence(destination, records)

    persisted = parse_transcript(destination.read_bytes())
    persisted_started = persisted[0]["payload"]
    assert isinstance(persisted_started, dict)
    persisted_config = persisted_started["config"]
    assert isinstance(persisted_config, dict)
    if constraint == "terminal":
        persisted_terminal = persisted_config["terminal"]
        assert isinstance(persisted_terminal, dict)
        raw_markers = persisted_terminal["capabilities"]
        assert isinstance(raw_markers, list)
        markers = [marker for marker in raw_markers if isinstance(marker, str)]
    else:
        persisted_network = persisted_config["network"]
        assert isinstance(persisted_network, dict)
        allowed = persisted_network["allowed"]
        assert isinstance(allowed, list)
        markers = [
            host
            for entry in allowed
            if isinstance(entry, dict) and isinstance((host := entry.get("host")), str)
        ]
    assert len(markers) == 10_001
    assert markers[0].endswith("-00000>")
    assert markers[9_999].endswith("-09999>")
    assert markers[10_000].endswith("-10000>")
    assert markers == sorted(markers)
    assert persisted[capability_index]["payload"] == {
        "constraint": constraint,
        "effective": persisted_config[constraint],
        "status": "enforced",
    }


@pytest.mark.parametrize(
    ("kind", "payload", "expected"),
    [
        (
            "input.text",
            {"at_ms": 0, "text": "private text"},
            {"at_ms": 0, "text": "<redacted:input-text>"},
        ),
        (
            "input.clipboard_set",
            {"at_ms": 0, "text": "private clipboard"},
            {"at_ms": 0, "text": "<redacted:clipboard>"},
        ),
        (
            "input.key",
            {"at_ms": 0, "keys": ["private-key"]},
            {"at_ms": 0, "keys": ["<redacted:key-0000>"]},
        ),
        (
            "input.resize",
            {"at_ms": 0, "columns": 100, "rows": 30},
            {"at_ms": 0, "columns": 100, "rows": 30},
        ),
        (
            "input.mouse",
            {"at_ms": 0, "action": "press", "button": "left", "column": 2, "row": 3},
            {"at_ms": 0, "action": "press", "button": "left", "column": 2, "row": 3},
        ),
        (
            "input.clock_advanced",
            {"at_ms": 1, "delta_ms": 1},
            {"at_ms": 1, "delta_ms": 1},
        ),
        ("input.stop", {"at_ms": 0}, {"at_ms": 0}),
    ],
)
def test_safe_persistence_classifies_every_input_kind(
    tmp_path: Path,
    kind: str,
    payload: dict[str, JsonValue],
    expected: dict[str, JsonValue],
) -> None:
    records = parse_transcript(TRANSCRIPT_FIXTURE.read_bytes())
    records[9]["kind"] = kind
    records[9]["payload"] = payload
    if kind == "input.clock_advanced":
        observation_payload = records[10]["payload"]
        assert isinstance(observation_payload, dict)
        observation_payload["at_ms"] = 1
    destination = tmp_path / f"{kind}.jsonl"

    persist_transcript_evidence(destination, records)

    persisted = parse_transcript(destination.read_bytes())
    assert persisted[9]["kind"] == kind
    assert persisted[9]["payload"] == expected


def test_safe_persistence_redacts_diagnostic_strings(tmp_path: Path) -> None:
    records = parse_transcript(TRANSCRIPT_FIXTURE.read_bytes())
    diagnostic = deepcopy(records[9])
    diagnostic["kind"] = "diagnostic"
    diagnostic["payload"] = {
        "at_ms": 0,
        "code": "AKIA" + "A" * 16,
        "message": "private diagnostic",
        "details": {"private": "details"},
    }
    records.insert(10, diagnostic)
    _resequence(records)
    destination = tmp_path / "transcript.jsonl"

    persist_transcript_evidence(destination, records)

    persisted = parse_transcript(destination.read_bytes())
    assert persisted[10]["payload"] == {
        "at_ms": 0,
        "code": "<redacted:diagnostic-code>",
        "message": "<redacted:diagnostic>",
        "details": "<redacted:diagnostic>",
    }


@pytest.mark.parametrize(
    ("fixture", "payload_key", "expected_constraint"),
    [
        (FAILED_TRANSCRIPT_FIXTURE, "error", None),
        (UNSUPPORTED_TRANSCRIPT_FIXTURE, None, "network"),
    ],
)
def test_safe_persistence_redacts_terminal_diagnostic_strings(
    tmp_path: Path,
    fixture: Path,
    payload_key: str | None,
    expected_constraint: str | None,
) -> None:
    records = parse_transcript(fixture.read_bytes())
    payload = records[-1]["payload"]
    assert isinstance(payload, dict)
    diagnostic = payload if payload_key is None else payload[payload_key]
    assert isinstance(diagnostic, dict)
    diagnostic["code"] = "xox" + "b-1234567890-secret"
    diagnostic["message"] = "private message"
    diagnostic["details"] = {"private": "details"}
    destination = tmp_path / "transcript.jsonl"

    persist_transcript_evidence(destination, records)

    persisted = parse_transcript(destination.read_bytes())
    persisted_payload = persisted[-1]["payload"]
    assert isinstance(persisted_payload, dict)
    persisted_diagnostic = (
        persisted_payload if payload_key is None else persisted_payload[payload_key]
    )
    assert isinstance(persisted_diagnostic, dict)
    assert persisted_diagnostic["code"] == "<redacted:diagnostic-code>"
    assert persisted_diagnostic["message"] == "<redacted:diagnostic>"
    assert persisted_diagnostic["details"] == "<redacted:diagnostic>"
    if expected_constraint is not None:
        assert persisted_diagnostic["constraint"] == expected_constraint
        capability_payload = persisted[-2]["payload"]
        assert isinstance(capability_payload, dict)
        assert capability_payload["reason"] == "<redacted:diagnostic>"


def test_persist_transcript_evidence_preserves_credential_shaped_subject_selector(
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

    persist_transcript_evidence(destination, records)

    persisted = parse_transcript(destination.read_bytes())
    persisted_started = persisted[0]["payload"]
    assert isinstance(persisted_started, dict)
    assert persisted_started["subject"] == subject


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
    assert persisted_subject["x-redacted-0000"] == "<redacted:extension>"
    assert persisted_subject["x-redacted-0001"] == "<redacted:extension>"
    persisted_normalizer = persisted_subject["normalizer"]
    assert isinstance(persisted_normalizer, dict)
    assert persisted_normalizer["x-redacted-0000"] == "<redacted:extension>"


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
    assert persisted_terminal["x-redacted-0000"] == "<redacted:extension>"
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
    assert persisted_observation["x-redacted-0000"] == "<redacted:extension>"
    assert persisted_observation["payload"] == {
        "at_ms": 0,
        "events": [
            {
                "type": "<redacted:event-type-0000>",
                "data": "<redacted:event-data>",
            }
        ],
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
        "x-redacted-0000": "<redacted:extension>",
    }
    assert persisted[-1]["payload"] == {
        "error": {
            "code": "<redacted:diagnostic-code>",
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
        "x-redacted-0000": "<redacted:extension>",
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


@pytest.mark.parametrize(
    ("key", "sensitive"),
    [
        ("api_token", True),
        ("myTOKEN", True),
        ("authorization", True),
        ("APIToken", True),
        ("AWSSecret", True),
        ("DBPassword", True),
        ("GHToken", True),
        ("XToken", True),
        ("APIResponse", False),
        ("AWSRegion", False),
        ("databaseName", False),
        ("user_name", False),
        ("feature-flag", False),
    ],
)
def test_redact_evidence_classifies_acronym_and_delimited_keys(
    key: str,
    sensitive: bool,
) -> None:
    value = "synthetic-value"

    assert redact_evidence({key: value}) == {
        key: f"<redacted:{key}>" if sensitive else value
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
            "x-redacted-0000": "<redacted:extension>",
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
        "Authorization: Basic dXNlcj...ZA==",
        "OPENAI_API_KEY=«redacted:sk-…»",
        "password=hunter2",
        "-----BEGIN PRIVATE KEY-----",
        "AKIA" + "A" * 16,
        ".".join(("eyJ" + "a" * 20, "eyJ" + "b" * 20, "c" * 32)),
        "xox" + "b-" + "1234567890-abcdefghijklmnop",
        "x" + "app-1-" + "1234567890-abcdefghijklmnop",
        "x" + "wfp-" + "1234567890-abcdefghijklmnop",
        "x" + "oxe-1-" + "1234567890-abcdefghijklmnop",
        "x" + "oxe.xoxb-1-" + "1234567890-abcdefghijklmnop",
        "MII" + "A" * 64 + "==",
    ],
)
def test_redact_evidence_redacts_credentials_in_free_text(text: str) -> None:
    assert redact_evidence(text) == "<redacted:credential>"


@pytest.mark.parametrize(
    "text",
    [
        "AKIA" + "A" * 15,
        ".".join(("eyJ" + "a" * 20, "only-two-segments")),
        "xoxb-short",
        "xapp-short",
        "xwfp-short",
        "xoxe-short",
        "MII-short-public-label",
    ],
)
def test_redact_evidence_preserves_credential_pattern_near_misses(text: str) -> None:
    assert redact_evidence(text) == text


def test_persist_transcript_evidence_rejects_non_finite_numbers(tmp_path: Path) -> None:
    records = parse_transcript(TRANSCRIPT_FIXTURE.read_bytes())
    observation_payload = records[10]["payload"]
    assert isinstance(observation_payload, dict)
    observation_payload["state"] = {"value": float("nan")}
    destination = tmp_path / "transcript.jsonl"

    with pytest.raises(TranscriptValidationError, match="finite"):
        persist_transcript_evidence(destination, records)

    assert not destination.exists()
