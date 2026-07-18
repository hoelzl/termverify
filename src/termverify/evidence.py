"""Safe persistence helpers for terminal-verification evidence."""

from __future__ import annotations

import os
import re
from copy import deepcopy
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Literal

from termverify._json import JsonValue as JsonValue
from termverify.transcript import Record, serialize_transcript

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
    re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{10,}\b"),
    re.compile(r"\b(?:xox[baprs]|xapp|xwfp)-[A-Za-z0-9-]{10,}\b"),
    re.compile(r"\bxoxe(?:\.xox[bp])?-[A-Za-z0-9-]{10,}\b"),
    re.compile(r"\bMII[A-Za-z0-9+/]{20,}={0,2}(?=$|[^A-Za-z0-9+/=])"),
    re.compile(
        r"(?:^|[^A-Za-z0-9])"
        r"(?:api[_-]?key|credential|password|secret|token)\s*[:=]\s*\S+",
        re.IGNORECASE,
    ),
    re.compile(r"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----"),
)
_CAMEL_CASE_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
_PAYLOAD_MEMBERS = {
    "run.started": frozenset({"config", "subject"}),
    "capability.result": frozenset(
        {"constraint", "status", "effective", "reason", "tier", "delivery"}
    ),
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
        result = {
            key: _redaction_marker(key)
            if _is_sensitive_key(key)
            else _redaction_marker("path")
            if _is_path_key(key)
            else _redact_clipboard_payload(item)
            if key == "payload" and value.get("kind") == "input.clipboard_set"
            else redact_evidence(item)
            for key, item in value.items()
            if not key.startswith("x-")
        }
        for index, _key in enumerate(
            sorted(key for key in value if key.startswith("x-"))
        ):
            result[f"x-redacted-{index:04d}"] = _redaction_marker("extension")
        return result
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
    """Sanitize and atomically replace canonical transcript *records*.

    Atomic replacement does not imply crash-durable storage.
    """
    if mode != "safe":
        raise ValueError(
            "sensitive persistence is unavailable until access and cleanup "
            "boundaries are implemented"
        )
    sanitized = deepcopy(records)
    # Validate one stable snapshot so malformed input cannot become valid merely
    # because a sensitive value is replaced or through concurrent mutation.
    serialize_transcript(sanitized)
    for record in sanitized:
        _redact_transcript_record(record)
    serialized = serialize_transcript(sanitized)
    destination.parent.mkdir(parents=True, exist_ok=True)
    _replace_atomically(destination, serialized)


def _replace_atomically(destination: Path, serialized: bytes) -> None:
    temporary: Path | None = None
    primary_error: BaseException | None = None
    try:
        with NamedTemporaryFile(
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            written = stream.write(serialized)
            if written != len(serialized):
                raise OSError(
                    f"short temporary write: expected {len(serialized)} bytes, "
                    f"wrote {written}"
                )
        os.replace(temporary, destination)
    except BaseException as error:
        primary_error = error
        raise
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError as cleanup_error:
                if primary_error is None:
                    raise
                primary_error.add_note(
                    f"temporary evidence cleanup failed: {cleanup_error}"
                )


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
        if constraint == "timezone" and "effective" in payload:
            payload["effective"] = "UTC"
        elif isinstance(constraint, str):
            _redact_constraint_config(constraint, effective)
        if payload.get("status") == "unsupported" and "effective" in payload:
            payload["effective"] = _redaction_marker("unknown")
        if "reason" in payload:
            payload["reason"] = _redaction_marker("diagnostic")
        delivery = payload.get("delivery")
        if isinstance(delivery, dict):
            _redact_delivery(delivery)
    elif kind == "input.key":
        keys = payload.get("keys")
        if isinstance(keys, list):
            payload["keys"] = ["Escape"]
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
            _redact_exit(exit_value)
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
        for index, event in enumerate(events):
            if isinstance(event, dict):
                _redact_unknown_members(event, frozenset({"type", "data"}))
                if "type" in event:
                    event["type"] = _redaction_marker(f"event-type-{index:04d}")
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
            _redact_exit(exit_value)


def _redact_diagnostic(
    value: dict[str, JsonValue], extra_members: frozenset[str] = frozenset()
) -> None:
    _redact_unknown_members(
        value,
        frozenset({"at_ms", "code", "message", "details"}) | extra_members,
    )
    if "code" in value:
        value["code"] = _redaction_marker("diagnostic-code")
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
        _redact_terminal_config(terminal)
    if "timezone" in config:
        config["timezone"] = "UTC"
    filesystem = config.get("filesystem")
    if isinstance(filesystem, dict):
        _redact_filesystem_config(filesystem)
    network = config.get("network")
    if isinstance(network, dict):
        _redact_network_config(network)


def _redact_terminal_config(config: dict[str, JsonValue]) -> None:
    _redact_unknown_members(config, frozenset({"columns", "rows", "capabilities"}))
    capabilities = config.get("capabilities")
    if isinstance(capabilities, list):
        config["capabilities"] = _ordered_markers(
            "terminal-capability", len(capabilities)
        )


def _redact_exit(exit_value: dict[str, JsonValue]) -> None:
    _redact_unknown_members(exit_value, frozenset({"kind", "value"}))
    if exit_value.get("kind") == "signal" and "value" in exit_value:
        exit_value["value"] = _redaction_marker("signal")


def _redact_filesystem_config(config: dict[str, JsonValue]) -> None:
    _redact_unknown_members(config, frozenset({"mode", "root_id"}))
    if "root_id" in config:
        config["root_id"] = _redaction_marker("sandbox-root")


def _redact_network_config(config: dict[str, JsonValue]) -> None:
    _redact_unknown_members(config, frozenset({"mode", "allowed"}))
    allowed = config.get("allowed")
    if isinstance(allowed, list):
        markers = _ordered_markers("network-host", len(allowed))
        for index, entry in enumerate(allowed):
            if isinstance(entry, dict):
                _redact_unknown_members(entry, frozenset({"host", "port"}))
                if "host" in entry:
                    entry["host"] = markers[index]


def _redact_delivery(delivery: dict[str, JsonValue]) -> None:
    """Redact delivered spawn-environment values while keeping the shape valid.

    Delivered values embed host-specific detail (absolute sandbox paths,
    requested configuration echoes), so safe evidence replaces every variable
    name and value with deterministic ordered markers and the working
    directory with a path marker; post-redaction revalidation still sees a
    structurally valid delivery record.
    """
    _redact_unknown_members(delivery, frozenset({"env", "cwd"}))
    env = delivery.get("env")
    if isinstance(env, dict):
        delivery["env"] = {
            str(name): _redaction_marker("delivery")
            for name in _ordered_markers("delivery-env", len(env))
        }
    if "cwd" in delivery:
        delivery["cwd"] = _redaction_marker("path")


def _redact_constraint_config(constraint: str, value: JsonValue) -> None:
    if not isinstance(value, dict):
        return
    if constraint == "clock":
        _redact_unknown_members(value, frozenset({"mode", "initial_ms"}))
    elif constraint == "terminal":
        _redact_terminal_config(value)
    elif constraint == "filesystem":
        _redact_filesystem_config(value)
    elif constraint == "network":
        _redact_network_config(value)


def _redact_ui(ui: dict[str, JsonValue]) -> None:
    _redact_unknown_members(ui, frozenset({"regions", "focus", "cursor", "mode"}))
    if ui.get("mode") is not None:
        ui["mode"] = _redaction_marker("ui-mode")
    cursor = ui.get("cursor")
    if isinstance(cursor, dict):
        _redact_unknown_members(cursor, frozenset({"column", "row", "visible"}))
    regions = ui.get("regions")
    if isinstance(regions, list):
        focus = ui.get("focus")
        region_ids: dict[str, str] = {}
        for index, region in enumerate(regions):
            if not isinstance(region, dict):
                continue
            _redact_unknown_members(region, frozenset({"id", "role", "bounds"}))
            region_id = region.get("id")
            marker = _redaction_marker(f"region-{index:04d}")
            if isinstance(region_id, str):
                region_ids[region_id] = marker
                region["id"] = marker
            if "role" in region:
                region["role"] = _redaction_marker(f"region-role-{index:04d}")
            bounds = region.get("bounds")
            if isinstance(bounds, dict):
                _redact_unknown_members(
                    bounds,
                    frozenset({"column", "row", "columns", "rows"}),
                )
        if isinstance(focus, str):
            ui["focus"] = region_ids[focus]


def _redact_unknown_members(
    value: dict[str, JsonValue], known_members: frozenset[str]
) -> None:
    for key in value:
        if key not in known_members and not key.startswith("x-"):
            value[key] = _redaction_marker("unknown")


def _redact_extension_values(value: JsonValue) -> None:
    if isinstance(value, dict):
        extension_keys = sorted(key for key in value if key.startswith("x-"))
        for key, item in list(value.items()):
            if not key.startswith("x-"):
                _redact_extension_values(item)
        for key in extension_keys:
            del value[key]
        for index, _key in enumerate(extension_keys):
            value[f"x-redacted-{index:04d}"] = _redaction_marker("extension")
    elif isinstance(value, list):
        for item in value:
            _redact_extension_values(item)


def _ordered_markers(reason: str, count: int) -> list[JsonValue]:
    width = max(4, len(str(max(0, count - 1))))
    return [_redaction_marker(f"{reason}-{index:0{width}d}") for index in range(count)]


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
    result = {
        key: redact_evidence(item)
        if key == "at_ms"
        and isinstance(item, int)
        and not isinstance(item, bool)
        and item >= 0
        else _redaction_marker("clipboard")
        for key, item in value.items()
        if not key.startswith("x-")
    }
    for index, _key in enumerate(sorted(key for key in value if key.startswith("x-"))):
        result[f"x-redacted-{index:04d}"] = _redaction_marker("extension")
    return result


def _redaction_marker(reason: str) -> str:
    return f"<redacted:{reason}>"
