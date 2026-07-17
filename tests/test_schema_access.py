from __future__ import annotations

import json
from importlib.resources import files

import pytest

import termverify.schema
from termverify import (
    TRANSCRIPT_SCHEMA_V1_ID,
    transcript_schema_v1_bytes,
    transcript_schema_v1_json,
)


def test_transcript_schema_v1_bytes_returns_packaged_resource_bytes() -> None:
    resource = (
        files("termverify") / "schemas" / "termverify.transcript" / "v1.schema.json"
    )

    assert transcript_schema_v1_bytes() == resource.read_bytes()


def test_transcript_schema_v1_bytes_parse_to_identified_draft_2020_12_schema() -> None:
    schema = json.loads(transcript_schema_v1_bytes())

    assert (
        TRANSCRIPT_SCHEMA_V1_ID
        == "https://termverify.dev/schemas/termverify.transcript/v1.schema.json"
    )
    assert schema["$id"] == TRANSCRIPT_SCHEMA_V1_ID
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"


def test_transcript_schema_v1_json_matches_exact_bytes() -> None:
    assert transcript_schema_v1_json() == json.loads(transcript_schema_v1_bytes())


def test_transcript_schema_v1_json_returns_isolated_copies() -> None:
    first = transcript_schema_v1_json()
    first.clear()

    assert transcript_schema_v1_json()["$id"] == TRANSCRIPT_SCHEMA_V1_ID


def test_transcript_schema_v1_json_rejects_non_object_resource(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(termverify.schema, "transcript_schema_v1_bytes", lambda: b"[]")

    with pytest.raises(TypeError, match="JSON object"):
        transcript_schema_v1_json()
