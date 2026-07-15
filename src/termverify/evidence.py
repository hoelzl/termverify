"""Safe persistence helpers for terminal-verification evidence."""

from __future__ import annotations

import re
from copy import deepcopy
from pathlib import Path
from typing import Literal

from termverify.transcript import Record, serialize_transcript

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
_PAYLOAD_MEMBERS = {
    "run.started": frozenset({"config"}),
    "capability.result": frozenset({"constraint", "status", "effective", "reason"}),
    "input.key": frozenset({"at_ms", "keys"}),
    "input.text": frozenset({"at_ms", "text"}),
    "input.resize": frozenset({"at_ms", "columns", "rows"}),
    "input.mouse": frozenset({"at_ms", "action", "column", "row", "button", "delta"}),
    "input.clock_advanced": frozenset({"at_ms", "delta_ms"}),
    "input.clipboard_set": frozenset({"at_ms", "text"}),
    "input.stop": frozenset({"at_ms"}),
    "observation": frozenset({"at_ms", "state", "events", "ui", "frame", "process"}),
    "diagnostic": frozenset({"at_ms", "code", "message", "details"}),
    "run.finished": frozenset({"exit"}),
    "run.failed": frozenset({"error"}),
    "run.unsupported": frozenset({"constraint", "code", "message", "details"}),
}


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


def persist_transcript_evidence(
    destination: Path,
    records: list[Record],
    *,
    mode: Literal["safe", "sensitive"] = "safe",
) -> None:
    """Sanitize and canonically persist validated transcript *records*."""
    if mode != "safe":
        raise ValueError(
            "sensitive persistence is unavailable until access and cleanup "
            "boundaries are implemented"
        )
    sanitized = deepcopy(records)
    # Validate one stable snapshot so malformed input cannot become valid merely
    # because a sensitive value is replaced or through concurrent mutation.
    serialize_transcript(sanitized)
    for index, record in enumerate(sanitized):
        redacted = redact_evidence(record)
        if not isinstance(redacted, dict):
            raise TypeError("transcript record redaction must produce an object")
        sanitized[index] = redacted
        _redact_transcript_record(sanitized[index])
    serialized = serialize_transcript(sanitized)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(serialized)


def _redact_transcript_record(record: Record) -> None:
    _redact_extension_values(record)
    kind = record.get("kind")
    payload = record.get("payload")
    if not isinstance(payload, dict):
        return
    if isinstance(kind, str):
        _redact_unknown_members(payload, _PAYLOAD_MEMBERS.get(kind, frozenset()))
    if kind == "run.started":
        config = payload.get("config")
        if isinstance(config, dict):
            _redact_runtime_config(config)
    elif kind == "capability.result":
        effective = payload.get("effective")
        constraint = payload.get("constraint")
        if isinstance(constraint, str):
            _redact_constraint_config(constraint, effective)
        if payload.get("status") == "unsupported" and "effective" in payload:
            payload["effective"] = _redaction_marker("unknown")
        if "reason" in payload:
            payload["reason"] = _redaction_marker("diagnostic")
    elif kind == "input.text" and "text" in payload:
        payload["text"] = _redaction_marker("input-text")
    elif kind == "input.clipboard_set" and "text" in payload:
        payload["text"] = _redaction_marker("clipboard")
    elif kind == "observation":
        _redact_observation(payload)
    elif kind == "diagnostic":
        _redact_diagnostic(payload)
    elif kind == "run.finished":
        exit_value = payload.get("exit")
        if isinstance(exit_value, dict):
            _redact_unknown_members(exit_value, frozenset({"kind", "value"}))
    elif kind == "run.failed":
        error = payload.get("error")
        if isinstance(error, dict):
            _redact_diagnostic(error)
    elif kind == "run.unsupported":
        _redact_diagnostic(payload, frozenset({"constraint"}))


def _redact_observation(payload: dict[str, JsonValue]) -> None:
    if "state" in payload:
        payload["state"] = _redaction_marker("state")
    events = payload.get("events")
    if isinstance(events, list):
        for event in events:
            if isinstance(event, dict):
                _redact_unknown_members(event, frozenset({"type", "data"}))
                if "data" in event:
                    event["data"] = _redaction_marker("event-data")
    ui = payload.get("ui")
    if isinstance(ui, dict):
        _redact_ui(ui)
    frame = payload.get("frame")
    if isinstance(frame, dict):
        _redact_unknown_members(frame, frozenset({"columns", "rows", "lines"}))
        lines = frame.get("lines")
        if isinstance(lines, list):
            frame["lines"] = [_redaction_marker("frame") for _ in lines]
    process = payload.get("process")
    if isinstance(process, dict):
        _redact_unknown_members(process, frozenset({"state", "exit"}))
        exit_value = process.get("exit")
        if isinstance(exit_value, dict):
            _redact_unknown_members(exit_value, frozenset({"kind", "value"}))


def _redact_diagnostic(
    value: dict[str, JsonValue], extra_members: frozenset[str] = frozenset()
) -> None:
    _redact_unknown_members(
        value,
        frozenset({"at_ms", "code", "message", "details"}) | extra_members,
    )
    for key in ("message", "details"):
        if key in value:
            value[key] = _redaction_marker("diagnostic")


def _redact_runtime_config(config: dict[str, JsonValue]) -> None:
    _redact_unknown_members(
        config,
        frozenset(
            {"seed", "clock", "locale", "timezone", "terminal", "filesystem", "network"}
        ),
    )
    clock = config.get("clock")
    if isinstance(clock, dict):
        _redact_unknown_members(clock, frozenset({"mode", "initial_ms"}))
    terminal = config.get("terminal")
    if isinstance(terminal, dict):
        _redact_unknown_members(
            terminal, frozenset({"columns", "rows", "capabilities"})
        )
    filesystem = config.get("filesystem")
    if isinstance(filesystem, dict):
        _redact_filesystem_config(filesystem)
    network = config.get("network")
    if isinstance(network, dict):
        _redact_network_config(network)


def _redact_filesystem_config(config: dict[str, JsonValue]) -> None:
    _redact_unknown_members(config, frozenset({"mode", "root_id"}))
    if "root_id" in config:
        config["root_id"] = _redaction_marker("sandbox-root")


def _redact_network_config(config: dict[str, JsonValue]) -> None:
    _redact_unknown_members(config, frozenset({"mode", "allowed"}))
    allowed = config.get("allowed")
    if isinstance(allowed, list):
        for index, entry in enumerate(allowed):
            if isinstance(entry, dict):
                _redact_unknown_members(entry, frozenset({"host", "port"}))
                if "host" in entry:
                    entry["host"] = _redaction_marker(f"network-host-{index:04d}")


def _redact_constraint_config(constraint: str, value: JsonValue) -> None:
    if not isinstance(value, dict):
        return
    if constraint == "clock":
        _redact_unknown_members(value, frozenset({"mode", "initial_ms"}))
    elif constraint == "terminal":
        _redact_unknown_members(value, frozenset({"columns", "rows", "capabilities"}))
    elif constraint == "filesystem":
        _redact_filesystem_config(value)
    elif constraint == "network":
        _redact_network_config(value)


def _redact_ui(ui: dict[str, JsonValue]) -> None:
    _redact_unknown_members(ui, frozenset({"regions", "focus", "cursor", "mode"}))
    cursor = ui.get("cursor")
    if isinstance(cursor, dict):
        _redact_unknown_members(cursor, frozenset({"column", "row", "visible"}))
    regions = ui.get("regions")
    if isinstance(regions, list):
        for region in regions:
            if not isinstance(region, dict):
                continue
            _redact_unknown_members(region, frozenset({"id", "role", "bounds"}))
            bounds = region.get("bounds")
            if isinstance(bounds, dict):
                _redact_unknown_members(
                    bounds,
                    frozenset({"column", "row", "columns", "rows"}),
                )


def _redact_unknown_members(
    value: dict[str, JsonValue], known_members: frozenset[str]
) -> None:
    for key in value:
        if key not in known_members and not key.startswith("x-"):
            value[key] = _redaction_marker("unknown")


def _redact_extension_values(value: JsonValue) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key.startswith("x-"):
                value[key] = _redaction_marker("extension")
            else:
                _redact_extension_values(item)
    elif isinstance(value, list):
        for item in value:
            _redact_extension_values(item)


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
