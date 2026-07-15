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
    re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
)
_ABSOLUTE_PATH_PATTERN = re.compile(r"(?:[A-Za-z]:[\\/]|/)")


def redact_evidence(value: JsonValue) -> JsonValue:
    """Return *value* with sensitive structured values replaced deterministically."""
    if isinstance(value, dict):
        return {
            key: _redaction_marker(key)
            if _is_sensitive_key(key)
            else _redaction_marker("path")
            if _is_path_key(key) and isinstance(item, str) and _is_absolute_path(item)
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
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(
            redact_evidence(evidence), ensure_ascii=False, indent=2, sort_keys=True
        )
        + "\n",
        encoding="utf-8",
    )


def _is_sensitive_key(key: str) -> bool:
    key_parts = re.split(r"[^a-z0-9]+", key.casefold())
    return any(part in _SENSITIVE_KEY_PARTS for part in key_parts)


def _is_path_key(key: str) -> bool:
    key_parts = re.split(r"[^a-z0-9]+", key.casefold())
    return any(part in _PATH_KEY_PARTS for part in key_parts)


def _is_absolute_path(value: str) -> bool:
    return _ABSOLUTE_PATH_PATTERN.match(value) is not None


def _redaction_marker(reason: str) -> str:
    return f"<redacted:{reason}>"
