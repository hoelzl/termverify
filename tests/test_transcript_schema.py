from __future__ import annotations

import json
from pathlib import Path

SCHEMA_PATH = Path("schemas/termverify.transcript/v1.schema.json")


def test_v1_schema_declares_protocol_and_draft() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert (
        schema["$id"]
        == "https://termverify.dev/schemas/termverify.transcript/v1.schema.json"
    )
    assert schema["properties"]["protocol"]["const"] == "termverify.transcript/v1"
