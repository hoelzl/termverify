from __future__ import annotations

import json
from pathlib import Path

import pytest

from termverify.evidence import JsonValue, redact_evidence, write_sanitized_evidence


def test_write_sanitized_evidence_redacts_nested_values_at_any_destination(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "artifacts" / "nested" / "evidence.json"

    write_sanitized_evidence(
        destination,
        {
            "state": {"api_token": "super-secret"},
            "events": [{"data": {"clipboard": "copied-secret"}}],
            "x-application": {"authorization": "Bearer confidential"},
        },
    )

    assert json.loads(destination.read_text(encoding="utf-8")) == {
        "state": {"api_token": "<redacted:api_token>"},
        "events": [{"data": {"clipboard": "<redacted:clipboard>"}}],
        "x-application": {"authorization": "<redacted:authorization>"},
    }


def test_write_sanitized_evidence_redacts_absolute_paths(tmp_path: Path) -> None:
    destination = tmp_path / "fixtures" / "nested" / "evidence.json"

    write_sanitized_evidence(
        destination,
        {"process": {"working_directory": "C:/Users/example/private"}},
    )

    assert json.loads(destination.read_text(encoding="utf-8")) == {
        "process": {"working_directory": "<redacted:path>"}
    }


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


def test_write_sanitized_evidence_rejects_non_finite_numbers(tmp_path: Path) -> None:
    destination = tmp_path / "evidence.json"

    with pytest.raises(ValueError, match="JSON"):
        write_sanitized_evidence(destination, {"value": float("nan")})

    assert not destination.exists()
