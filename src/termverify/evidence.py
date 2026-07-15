"""Safe persistence helpers for terminal-verification evidence."""

from __future__ import annotations

import json
import re
from pathlib import Path

type JsonValue = (
    None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]
)

_SENSITIVE_KEY_PARTS = frozenset(
    {
        "authorization",
        "clipboard",
        "cookie",
        "credential",
        "password",
        "secret",
        "token",
    }
)
_PATH_KEY_PARTS = frozenset({"cwd", "directory", "file", "path"})
_CREDENTIAL_PATTERNS = (
    re.compile(r"\bBearer\s+\S+", re.IGNORECASE),
    re.compile(r"\bAuthorization\s*:\s*Basic\s+\S+", re.IGNORECASE),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9-]{20,}\b"),
    re.compile(
        r"\b(?:api[_-]?key|credential|password|secret|token)\s*[:=]\s*\S+",
        re.IGNORECASE,
    ),
    re.compile(r"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----"),
)
_CAMEL_CASE_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def redact_evidence(value: JsonValue) -> JsonValue:
    """Return *value* with sensitive structured values replaced deterministically."""
    if isinstance(value, dict):
        return {
            key: _redaction_marker(key)
            if _is_sensitive_key(key)
            else _redaction_marker("path")
            if _is_path_key(key)
            else _redact_clipboard_payload(item)
            if key == "payload" and value.get("kind") == "input.clipboard_set"
            else redact_evidence(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_evidence(item) for item in value]
    if isinstance(value, str) and any(
        pattern.search(value) for pattern in _CREDENTIAL_PATTERNS
    ):
        return _redaction_marker("credential")
    return value


def write_sanitized_evidence(destination: Path, evidence: JsonValue) -> None:
    """Redact *evidence* before writing canonical JSON to any destination."""
    try:
        serialized = json.dumps(
            redact_evidence(evidence),
            allow_nan=False,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    except ValueError as error:
        raise ValueError("evidence contains a non-finite JSON number") from error
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(serialized + "\n", encoding="utf-8")


def _is_sensitive_key(key: str) -> bool:
    return any(part in _SENSITIVE_KEY_PARTS for part in _key_parts(key))


def _is_path_key(key: str) -> bool:
    return any(part in _PATH_KEY_PARTS for part in _key_parts(key))


def _key_parts(key: str) -> list[str]:
    separated = _CAMEL_CASE_BOUNDARY.sub("_", key)
    return re.split(r"[^a-z0-9]+", separated.casefold())


def _redact_clipboard_payload(value: JsonValue) -> JsonValue:
    if not isinstance(value, dict):
        return _redaction_marker("clipboard")
    return {
        key: redact_evidence(item)
        if key == "at_ms"
        and isinstance(item, int)
        and not isinstance(item, bool)
        and item >= 0
        else _redaction_marker("clipboard")
        for key, item in value.items()
    }


def _redaction_marker(reason: str) -> str:
    return f"<redacted:{reason}>"
