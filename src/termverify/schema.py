"""Installed access to the packaged transcript JSON Schema resource.

The packaged schema is the canonical committed copy of the deliberately
non-exhaustive Draft 2020-12 structural aid. Runtime validation in
:mod:`termverify.transcript` remains authoritative for acceptance; the
documented ``$id`` is an identifier, not a resolvable publication contract.
"""

from __future__ import annotations

import json
from importlib.resources import files
from typing import Final, cast

from termverify.transcript import JsonValue

TRANSCRIPT_SCHEMA_V1_ID: Final[str] = (
    "https://termverify.dev/schemas/termverify.transcript/v1.schema.json"
)

_TRANSCRIPT_SCHEMA_V1_RESOURCE: Final = (
    "schemas",
    "termverify.transcript",
    "v1.schema.json",
)


def transcript_schema_v1_bytes() -> bytes:
    """Return the exact bytes of the packaged v1 transcript schema."""
    resource = files("termverify").joinpath(*_TRANSCRIPT_SCHEMA_V1_RESOURCE)
    return resource.read_bytes()


def transcript_schema_v1_json() -> dict[str, JsonValue]:
    """Return the parsed v1 transcript schema as a fresh object per call."""
    parsed = json.loads(transcript_schema_v1_bytes())
    if not isinstance(parsed, dict):
        raise TypeError("packaged transcript schema must be a JSON object")
    return cast(dict[str, JsonValue], parsed)
