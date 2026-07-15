from __future__ import annotations

import json
from pathlib import Path

from termverify.evidence import write_sanitized_evidence


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
