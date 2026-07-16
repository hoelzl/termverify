"""Parsing and validation for `termverify.transcript/v1` JSONL transcripts."""

from __future__ import annotations

import json
import math
import re
from typing import cast

import rfc8785

type JsonValue = (
    None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]
)
type Record = dict[str, JsonValue]

_PROTOCOL = "termverify.transcript/v1"
_MAX_SEED = "18446744073709551615"
_IDENTIFIER_PATTERN = re.compile(r"[a-z0-9._-]+")
_GRANDFATHERED_LANGUAGE_TAGS = frozenset(
    {
        "art-lojban",
        "cel-gaulish",
        "en-gb-oed",
        "i-ami",
        "i-bnn",
        "i-default",
        "i-enochian",
        "i-hak",
        "i-klingon",
        "i-lux",
        "i-mingo",
        "i-navajo",
        "i-pwn",
        "i-tao",
        "i-tay",
        "i-tsu",
        "no-bok",
        "no-nyn",
        "sgn-be-fr",
        "sgn-be-nl",
        "sgn-ch-de",
        "zh-guoyu",
        "zh-hakka",
        "zh-min",
        "zh-min-nan",
        "zh-xiang",
    }
)
_CONSTRAINTS = (
    "seed",
    "clock",
    "locale",
    "timezone",
    "terminal",
    "filesystem",
    "network",
)
_TERMINAL_KINDS = frozenset({"run.finished", "run.failed", "run.unsupported"})
_INPUT_KINDS = frozenset(
    {
        "input.key",
        "input.text",
        "input.resize",
        "input.mouse",
        "input.clock_advanced",
        "input.clipboard_set",
        "input.stop",
    }
)
_INPUT_MEMBERS = {
    "input.key": frozenset({"at_ms", "keys"}),
    "input.text": frozenset({"at_ms", "text"}),
    "input.resize": frozenset({"at_ms", "columns", "rows"}),
    "input.mouse": frozenset({"at_ms", "action", "column", "row", "button", "delta"}),
    "input.clock_advanced": frozenset({"at_ms", "delta_ms"}),
    "input.clipboard_set": frozenset({"at_ms", "text"}),
    "input.stop": frozenset({"at_ms"}),
}
_PAYLOAD_MEMBERS = {
    **_INPUT_MEMBERS,
    "diagnostic": frozenset({"at_ms", "code", "message", "details"}),
    "observation": frozenset({"at_ms", "state", "events", "ui", "frame", "process"}),
    "run.finished": frozenset({"exit"}),
    "run.failed": frozenset({"error"}),
    "run.unsupported": frozenset({"constraint", "code", "message", "details"}),
}
_RECORD_KINDS = (
    _INPUT_KINDS
    | _TERMINAL_KINDS
    | {
        "run.started",
        "capability.result",
        "diagnostic",
        "observation",
    }
)


class TranscriptValidationError(ValueError):
    """Raised when a transcript violates the v1 contract."""


def parse_transcript(data: bytes) -> list[Record]:
    """Parse canonical v1 JSONL *data* and validate its envelope and lifecycle."""
    if (
        data.startswith(b"\xef\xbb\xbf")
        or b"\r" in data
        or not data.endswith(b"\n")
        or b"\n\n" in data
    ):
        raise TranscriptValidationError(
            "transcript must use exactly one final LF without a BOM"
        )
    try:
        records = [
            _parse_line(line, number) for number, line in enumerate(data.splitlines())
        ]
        _validate_lifecycle(records)
        return records
    except RecursionError as error:
        raise TranscriptValidationError(
            "transcript JSON nesting exceeds the supported depth"
        ) from error


def serialize_transcript(records: list[Record]) -> bytes:
    """Validate and encode *records* for in-memory use, not safe persistence."""
    try:
        raw_records: object = records
        if type(raw_records) is not list:
            raise TranscriptValidationError("transcript records must be a list")
        validated_records: list[Record] = []
        for sequence, value in enumerate(raw_records):
            if type(value) is not dict:
                raise TranscriptValidationError("transcript record must be an object")
            _validate_json_value(value)
            record = cast(Record, value)
            _validate_envelope(record, sequence)
            validated_records.append(record)
        _validate_lifecycle(validated_records)
        return b"".join(
            _canonical_record(record) + b"\n" for record in validated_records
        )
    except RecursionError as error:
        raise TranscriptValidationError(
            "transcript JSON nesting exceeds the supported depth"
        ) from error


def _validate_json_value(value: object) -> None:
    if value is None or type(value) in {bool, int, str}:
        return
    if isinstance(value, tuple):
        raise TranscriptValidationError("JSON arrays must use lists")
    if type(value) is float:
        if not math.isfinite(value):
            raise TranscriptValidationError("JSON number must be finite")
        return
    if type(value) is list:
        for item in value:
            _validate_json_value(item)
        return
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str:
                raise TranscriptValidationError("JSON object keys must be strings")
            _validate_json_value(item)
        return
    raise TranscriptValidationError("unsupported JSON value type")


def _canonical_record(record: Record) -> bytes:
    try:
        return rfc8785.dumps(record)
    except (rfc8785.CanonicalizationError, ValueError) as error:
        raise TranscriptValidationError(
            "record cannot be canonicalized as RFC 8785"
        ) from error


def _parse_line(line: bytes, number: int) -> Record:
    if not line:
        raise TranscriptValidationError(f"line {number + 1}: blank lines are invalid")
    try:
        text = line.decode("utf-8")
        raw = json.loads(text, object_pairs_hook=_reject_duplicate_members)
    except TranscriptValidationError:
        raise
    except (UnicodeDecodeError, ValueError) as error:
        raise TranscriptValidationError(f"line {number + 1}: invalid JSON") from error
    if not isinstance(raw, dict):
        raise TranscriptValidationError(f"line {number + 1}: record must be an object")
    record = cast(Record, raw)
    _validate_json_value(record)
    if _canonical_record(record) != line:
        raise TranscriptValidationError(
            f"line {number + 1}: record is not canonical JSON"
        )
    _validate_envelope(record, number)
    return record


def _reject_duplicate_members(
    pairs: list[tuple[str, JsonValue]],
) -> dict[str, JsonValue]:
    result: dict[str, JsonValue] = {}
    for key, value in pairs:
        if key in result:
            raise TranscriptValidationError(f"duplicate JSON member: {key}")
        result[key] = value
    return result


def _validate_envelope(record: Record, sequence: int) -> None:
    required = {"protocol", "run_id", "seq", "id", "kind", "payload"}
    if not required <= record.keys() or any(
        not key.startswith("x-") and key not in required for key in record
    ):
        raise TranscriptValidationError("record has invalid envelope members")
    if (
        record["protocol"] != _PROTOCOL
        or not isinstance(record["seq"], int)
        or isinstance(record["seq"], bool)
        or record["seq"] != sequence
    ):
        raise TranscriptValidationError("record protocol or sequence is invalid")
    if not all(
        isinstance(record[key], str) and record[key] for key in ("run_id", "id", "kind")
    ):
        raise TranscriptValidationError(
            "record identifiers and kind must be non-empty strings"
        )
    if any(
        _IDENTIFIER_PATTERN.fullmatch(cast(str, record[key])) is None
        for key in ("run_id", "id")
    ):
        raise TranscriptValidationError("record identifier grammar is invalid")
    if not isinstance(record["payload"], dict):
        raise TranscriptValidationError("record payload must be an object")


def _validate_lifecycle(records: list[Record]) -> None:
    for record in records:
        kind = record["kind"]
        if kind not in _RECORD_KINDS:
            if isinstance(kind, str) and kind.startswith("input."):
                raise TranscriptValidationError("input kind is not defined by v1")
            raise TranscriptValidationError("record kind is not defined by v1")
        payload = record["payload"]
        if (
            isinstance(kind, str)
            and kind in _PAYLOAD_MEMBERS
            and isinstance(payload, dict)
            and _has_unknown_generic_members(payload, _PAYLOAD_MEMBERS[kind])
        ):
            raise TranscriptValidationError(
                f"{kind} payload member is not defined by v1"
            )
    if not records or records[0]["kind"] != "run.started":
        raise TranscriptValidationError("transcript must start with run.started")
    if any(record["kind"] == "run.started" for record in records[1:]):
        raise TranscriptValidationError("run.started may appear only once")
    terminal_indexes = [
        index
        for index, record in enumerate(records)
        if record["kind"] in _TERMINAL_KINDS
    ]
    if terminal_indexes != [len(records) - 1]:
        raise TranscriptValidationError(
            "transcript must contain exactly one final terminal record"
        )
    run_id = records[0]["run_id"]
    identifiers: set[JsonValue] = set()
    for record in records:
        if record["run_id"] != run_id or record["id"] in identifiers:
            raise TranscriptValidationError("record run_id or id is invalid")
        identifiers.add(record["id"])
    started_payload = records[0]["payload"]
    if not isinstance(started_payload, dict):
        raise TranscriptValidationError("run.started payload must be an object")
    if any(
        key not in {"config", "subject"} and not key.startswith("x-")
        for key in started_payload
    ):
        raise TranscriptValidationError("run.started members are invalid")
    if "config" not in started_payload:
        raise TranscriptValidationError("run.started config is incomplete")
    subject = started_payload.get("subject")
    if not isinstance(subject, dict):
        raise TranscriptValidationError("run.started subject is missing")
    _validate_replay_subject(subject)
    config = started_payload.get("config")
    required_config = {
        "seed",
        "clock",
        "locale",
        "timezone",
        "terminal",
        "filesystem",
        "network",
    }
    if (
        not isinstance(config, dict)
        or not required_config <= config.keys()
        or any(
            key not in required_config and not key.startswith("x-") for key in config
        )
    ):
        raise TranscriptValidationError("run.started config is incomplete")
    seed = config["seed"]
    if (
        not isinstance(seed, str)
        or not seed.isascii()
        or not seed.isdecimal()
        or (len(seed) > 1 and seed.startswith("0"))
        or len(seed) > len(_MAX_SEED)
        or (len(seed) == len(_MAX_SEED) and seed > _MAX_SEED)
    ):
        raise TranscriptValidationError("run.started seed is invalid")
    terminal_config = config["terminal"]
    if not isinstance(terminal_config, dict) or _has_unknown_generic_members(
        terminal_config, frozenset({"columns", "rows", "capabilities"})
    ):
        raise TranscriptValidationError("run.started terminal is invalid")
    terminal_dimensions = (
        terminal_config.get("columns"),
        terminal_config.get("rows"),
    )
    if not all(
        isinstance(value, int) and not isinstance(value, bool) and value > 0
        for value in terminal_dimensions
    ):
        raise TranscriptValidationError("run.started terminal is invalid")
    terminal_capabilities = terminal_config.get("capabilities")
    if not isinstance(terminal_capabilities, list) or not all(
        isinstance(capability, str) and capability
        for capability in terminal_capabilities
    ):
        raise TranscriptValidationError("run.started terminal is invalid")
    canonical_capabilities = cast(list[str], terminal_capabilities)
    if canonical_capabilities != sorted(canonical_capabilities) or len(
        canonical_capabilities
    ) != len(set(canonical_capabilities)):
        raise TranscriptValidationError("run.started terminal is invalid")
    network_config = config["network"]
    if not isinstance(network_config, dict):
        raise TranscriptValidationError("run.started network is invalid")
    network_mode = network_config.get("mode")
    if network_mode == "deny":
        if _has_unknown_generic_members(network_config, frozenset({"mode"})):
            raise TranscriptValidationError("run.started network is invalid")
    elif network_mode == "allow-list":
        if _has_unknown_generic_members(network_config, frozenset({"mode", "allowed"})):
            raise TranscriptValidationError("run.started network is invalid")
        allowed = network_config.get("allowed")
        if not isinstance(allowed, list):
            raise TranscriptValidationError("run.started network is invalid")
        allow_pairs: list[tuple[str, int]] = []
        for entry in allowed:
            if not isinstance(entry, dict) or _has_unknown_generic_members(
                entry, frozenset({"host", "port"})
            ):
                raise TranscriptValidationError("run.started network is invalid")
            host = entry.get("host")
            port = entry.get("port")
            if (
                not isinstance(host, str)
                or not host
                or not isinstance(port, int)
                or isinstance(port, bool)
                or not 1 <= port <= 65535
            ):
                raise TranscriptValidationError("run.started network is invalid")
            allow_pairs.append((host, port))
        if allow_pairs != sorted(allow_pairs) or len(allow_pairs) != len(
            set(allow_pairs)
        ):
            raise TranscriptValidationError("run.started network is invalid")
    else:
        raise TranscriptValidationError("run.started network is invalid")
    filesystem_config = config["filesystem"]
    if (
        not isinstance(filesystem_config, dict)
        or _has_unknown_generic_members(
            filesystem_config, frozenset({"mode", "root_id"})
        )
        or filesystem_config.get("mode") != "sandbox"
        or not isinstance(filesystem_config.get("root_id"), str)
        or not filesystem_config["root_id"]
    ):
        raise TranscriptValidationError("run.started filesystem is invalid")
    locale = config["locale"]
    if not isinstance(locale, str) or not _is_well_formed_language_tag(locale):
        raise TranscriptValidationError("run.started locale is invalid")
    if not isinstance(config["timezone"], str) or not config["timezone"]:
        raise TranscriptValidationError("run.started timezone is invalid")
    terminal_payload = records[-1]["payload"]
    if records[-1]["kind"] == "run.finished":
        if not isinstance(terminal_payload, dict):
            raise TranscriptValidationError("run.finished payload must be an object")
        exit_value = terminal_payload.get("exit")
        if not isinstance(exit_value, dict):
            raise TranscriptValidationError("run.finished exit must be an object")
        if _has_unknown_generic_members(exit_value, frozenset({"kind", "value"})):
            raise TranscriptValidationError("run.finished exit members are invalid")
        exit_kind = exit_value.get("kind")
        exit_result = exit_value.get("value")
        valid_exit = (
            exit_kind == "code"
            and isinstance(exit_result, int)
            and not isinstance(exit_result, bool)
        ) or (
            exit_kind == "signal" and isinstance(exit_result, str) and bool(exit_result)
        )
        if not valid_exit:
            raise TranscriptValidationError("run.finished exit is invalid")
    if records[-1]["kind"] == "run.failed":
        if not isinstance(terminal_payload, dict):
            raise TranscriptValidationError("run.failed payload must be an object")
        error_value = terminal_payload.get("error")
        if (
            not isinstance(error_value, dict)
            or _has_unknown_generic_members(
                error_value, frozenset({"code", "message", "details"})
            )
            or not isinstance(error_value.get("code"), str)
            or not error_value["code"]
            or not isinstance(error_value.get("message"), str)
        ):
            raise TranscriptValidationError("run.failed error is invalid")
    capabilities: list[Record] = []
    for record in records[1:]:
        if record["kind"] != "capability.result":
            break
        capabilities.append(record)
    payloads = [record["payload"] for record in capabilities]
    if not all(isinstance(payload, dict) for payload in payloads):
        raise TranscriptValidationError("capability result payload must be an object")
    capability_payloads = cast(list[dict[str, JsonValue]], payloads)
    constraints = [payload.get("constraint") for payload in capability_payloads]
    if constraints != list(_CONSTRAINTS[: len(capabilities)]):
        raise TranscriptValidationError("capability results are out of order")
    statuses = [payload.get("status") for payload in capability_payloads]
    if any(
        not isinstance(status, str) or status not in {"enforced", "unsupported"}
        for status in statuses
    ):
        raise TranscriptValidationError("capability result status is invalid")
    for constraint, status, payload in zip(
        constraints, statuses, capability_payloads, strict=True
    ):
        if not isinstance(constraint, str):
            raise TranscriptValidationError("capability result constraint is invalid")
        allowed_members = (
            frozenset({"constraint", "status", "effective"})
            if status == "enforced"
            else frozenset({"constraint", "status", "reason"})
        )
        if _has_unknown_generic_members(payload, allowed_members):
            raise TranscriptValidationError(
                "capability result members are invalid for its status"
            )
        if status == "enforced" and not _json_equivalent(
            payload.get("effective"), config[constraint]
        ):
            raise TranscriptValidationError(
                "enforced capability effective value does not match config"
            )
        if status == "unsupported" and not isinstance(payload.get("reason"), str):
            raise TranscriptValidationError("unsupported capability reason is invalid")
    if "unsupported" in statuses:
        unsupported_index = statuses.index("unsupported")
        if unsupported_index != len(statuses) - 1:
            raise TranscriptValidationError(
                "capability results must stop at the first unsupported constraint"
            )
        terminal_index = len(capabilities) + 1
        terminal = records[terminal_index]
        if len(records) != terminal_index + 1 or terminal["kind"] != "run.unsupported":
            raise TranscriptValidationError(
                "unsupported constraint must be followed by run.unsupported"
            )
        unsupported_payload = terminal["payload"]
        if (
            not isinstance(unsupported_payload, dict)
            or unsupported_payload.get("constraint") != constraints[unsupported_index]
            or not isinstance(unsupported_payload.get("code"), str)
            or not unsupported_payload["code"]
            or not isinstance(unsupported_payload.get("message"), str)
        ):
            raise TranscriptValidationError(
                "run.unsupported constraint or payload is invalid"
            )
    elif len(capabilities) != len(_CONSTRAINTS):
        negotiation_failed = (
            records[-1]["kind"] == "run.failed"
            and len(records) == len(capabilities) + 2
        )
        if not negotiation_failed:
            raise TranscriptValidationError("capability results are missing")
    elif records[-1]["kind"] == "run.unsupported":
        raise TranscriptValidationError(
            "run.unsupported requires an unsupported capability result"
        )
    if len(capabilities) == len(_CONSTRAINTS):
        _validate_execution_epochs(records[len(capabilities) + 1 : -1])
    if any(
        record["kind"] == "capability.result"
        for record in records[len(capabilities) + 1 :]
    ):
        raise TranscriptValidationError(
            "capability results must precede all body and terminal records"
        )
    clock_config = config["clock"]
    if not isinstance(clock_config, dict) or _has_unknown_generic_members(
        clock_config, frozenset({"mode", "initial_ms"})
    ):
        raise TranscriptValidationError("run.started clock is invalid")
    manual_time = clock_config.get("initial_ms")
    if (
        clock_config.get("mode") != "manual"
        or not isinstance(manual_time, int)
        or isinstance(manual_time, bool)
        or manual_time < 0
    ):
        raise TranscriptValidationError("run.started clock is invalid")
    for record in records[len(capabilities) + 1 : -1]:
        if not isinstance(record["kind"], str) or not record["kind"].startswith(
            "input."
        ):
            continue
        if record["kind"] not in _INPUT_KINDS:
            raise TranscriptValidationError("input kind is not defined by v1")
        input_payload = record["payload"]
        if not isinstance(input_payload, dict):
            raise TranscriptValidationError("input payload must be an object")
        if any(
            key not in _INPUT_MEMBERS[record["kind"]] and not key.startswith("x-")
            for key in input_payload
        ):
            raise TranscriptValidationError(
                f"{record['kind']} payload member is not defined by v1"
            )
        at_ms = input_payload.get("at_ms")
        if not isinstance(at_ms, int) or isinstance(at_ms, bool) or at_ms < 0:
            raise TranscriptValidationError(
                "input at_ms must be a non-negative integer"
            )
        if record["kind"] == "input.clock_advanced":
            delta_ms = input_payload.get("delta_ms")
            if (
                not isinstance(delta_ms, int)
                or isinstance(delta_ms, bool)
                or delta_ms <= 0
                or at_ms != manual_time + delta_ms
            ):
                raise TranscriptValidationError(
                    "input.clock_advanced must advance the manual clock"
                )
            manual_time = at_ms
        elif at_ms != manual_time:
            raise TranscriptValidationError(
                "input at_ms does not match the manual clock"
            )
        if record["kind"] == "input.text" and not isinstance(
            input_payload.get("text"), str
        ):
            raise TranscriptValidationError("input.text requires a string text member")
        if record["kind"] == "input.clipboard_set" and not isinstance(
            input_payload.get("text"), str
        ):
            raise TranscriptValidationError(
                "input.clipboard_set requires a string text member"
            )
        if record["kind"] == "input.stop" and any(
            key != "at_ms" and not key.startswith("x-") for key in input_payload
        ):
            raise TranscriptValidationError("input.stop forbids additional members")
        if record["kind"] == "input.key":
            keys = input_payload.get("keys")
            if (
                not isinstance(keys, list)
                or not keys
                or not all(isinstance(key, str) and key for key in keys)
            ):
                raise TranscriptValidationError(
                    "input.key requires non-empty normalized keys"
                )
        if record["kind"] == "input.resize":
            dimensions = (input_payload.get("columns"), input_payload.get("rows"))
            if not all(
                isinstance(value, int) and not isinstance(value, bool) and value > 0
                for value in dimensions
            ):
                raise TranscriptValidationError(
                    "input.resize requires positive columns and rows"
                )
        if record["kind"] == "input.mouse":
            action = input_payload.get("action")
            coordinates = (input_payload.get("column"), input_payload.get("row"))
            if (
                not isinstance(action, str)
                or action not in {"press", "release", "move", "scroll"}
                or not all(
                    isinstance(value, int)
                    and not isinstance(value, bool)
                    and value >= 0
                    for value in coordinates
                )
            ):
                raise TranscriptValidationError(
                    "input.mouse action or position is invalid"
                )
            button = input_payload.get("button")
            delta = input_payload.get("delta")
            if action in {"press", "release"}:
                if (
                    not isinstance(button, str)
                    or button not in {"left", "middle", "right"}
                    or "delta" in input_payload
                ):
                    raise TranscriptValidationError("input.mouse button is invalid")
            elif action == "scroll":
                if (
                    "button" in input_payload
                    or not isinstance(delta, int)
                    or isinstance(delta, bool)
                    or not delta
                ):
                    raise TranscriptValidationError(
                        "input.mouse scroll delta is invalid"
                    )
            elif "button" in input_payload or "delta" in input_payload:
                raise TranscriptValidationError(
                    "input.mouse move forbids button and delta"
                )
    for record in records[len(capabilities) + 1 : -1]:
        if record["kind"] != "diagnostic":
            continue
        diagnostic_payload = record["payload"]
        if not isinstance(diagnostic_payload, dict):
            raise TranscriptValidationError("diagnostic payload must be an object")
        diagnostic_time = diagnostic_payload.get("at_ms")
        if (
            not isinstance(diagnostic_time, int)
            or isinstance(diagnostic_time, bool)
            or diagnostic_time < 0
            or not isinstance(diagnostic_payload.get("code"), str)
            or not diagnostic_payload["code"]
            or not isinstance(diagnostic_payload.get("message"), str)
        ):
            raise TranscriptValidationError("diagnostic payload is invalid")
    for record in records[len(capabilities) + 1 : -1]:
        if record["kind"] != "observation":
            continue
        observation_payload = record["payload"]
        if not isinstance(observation_payload, dict):
            raise TranscriptValidationError("observation payload must be an object")
        observation_time = observation_payload.get("at_ms")
        if (
            not isinstance(observation_time, int)
            or isinstance(observation_time, bool)
            or observation_time < 0
            or "state" not in observation_payload
            or not isinstance(observation_payload.get("events"), list)
            or not isinstance(observation_payload.get("ui"), dict)
        ):
            raise TranscriptValidationError("observation payload is invalid")
        ui = observation_payload["ui"]
        assert isinstance(ui, dict)
        cursor = ui.get("cursor")
        if (
            not {"regions", "focus", "cursor", "mode"} <= ui.keys()
            or not isinstance(ui.get("regions"), list)
            or _has_unknown_generic_members(
                ui, frozenset({"regions", "focus", "cursor", "mode"})
            )
            or ui.get("focus") is not None
            and not isinstance(ui.get("focus"), str)
            or not isinstance(cursor, dict)
            or not isinstance(ui.get("mode"), str)
            and ui.get("mode") is not None
        ):
            raise TranscriptValidationError("observation ui is invalid")
        cursor_values = (cursor.get("column"), cursor.get("row"))
        if (
            _has_unknown_generic_members(
                cursor, frozenset({"column", "row", "visible"})
            )
            or not all(
                isinstance(value, int) and not isinstance(value, bool) and value >= 0
                for value in cursor_values
            )
            or not isinstance(cursor.get("visible"), bool)
        ):
            raise TranscriptValidationError("observation ui cursor is invalid")
        regions = ui["regions"]
        assert isinstance(regions, list)
        region_ids: set[str] = set()
        for region in regions:
            if not isinstance(region, dict):
                raise TranscriptValidationError("observation ui region is invalid")
            region_id = region.get("id")
            bounds = region.get("bounds")
            if (
                not isinstance(region_id, str)
                or _has_unknown_generic_members(
                    region, frozenset({"id", "role", "bounds"})
                )
                or not region_id
                or region_id in region_ids
                or not isinstance(region.get("role"), str)
                or not region["role"]
                or not isinstance(bounds, dict)
            ):
                raise TranscriptValidationError("observation ui region is invalid")
            dimensions = (bounds.get("columns"), bounds.get("rows"))
            origin = (bounds.get("column"), bounds.get("row"))
            if (
                _has_unknown_generic_members(
                    bounds, frozenset({"column", "row", "columns", "rows"})
                )
                or not all(
                    isinstance(value, int) and not isinstance(value, bool) and value > 0
                    for value in dimensions
                )
                or not all(
                    isinstance(value, int)
                    and not isinstance(value, bool)
                    and value >= 0
                    for value in origin
                )
            ):
                raise TranscriptValidationError("observation ui bounds are invalid")
            region_ids.add(region_id)
        if ui["focus"] is not None and ui["focus"] not in region_ids:
            raise TranscriptValidationError("observation ui focus is not a region")
        events = observation_payload["events"]
        assert isinstance(events, list)
        for event in events:
            if (
                not isinstance(event, dict)
                or _has_unknown_generic_members(event, frozenset({"type", "data"}))
                or not isinstance(event.get("type"), str)
                or not event["type"]
                or "data" not in event
            ):
                raise TranscriptValidationError("observation event is invalid")
        if "frame" in observation_payload:
            frame = observation_payload["frame"]
            if not isinstance(frame, dict):
                raise TranscriptValidationError("observation frame is invalid")
            lines = frame.get("lines")
            dimensions = (frame.get("columns"), frame.get("rows"))
            if (
                not isinstance(lines, list)
                or _has_unknown_generic_members(
                    frame, frozenset({"lines", "columns", "rows"})
                )
                or not all(isinstance(line, str) for line in lines)
                or not all(
                    isinstance(value, int) and not isinstance(value, bool) and value > 0
                    for value in dimensions
                )
                or len(lines) != frame.get("rows")
            ):
                raise TranscriptValidationError("observation frame is invalid")
        if "process" in observation_payload:
            process = observation_payload["process"]
            if not isinstance(process, dict):
                raise TranscriptValidationError("observation process is invalid")
            if process.get("state") == "running" and not _has_unknown_generic_members(
                process, frozenset({"state"})
            ):
                continue
            exit_value = process.get("exit")
            if (
                process.get("state") != "exited"
                or _has_unknown_generic_members(process, frozenset({"state", "exit"}))
                or not isinstance(exit_value, dict)
                or _has_unknown_generic_members(
                    exit_value, frozenset({"kind", "value"})
                )
                or not (
                    exit_value.get("kind") == "code"
                    and isinstance(exit_value.get("value"), int)
                    and not isinstance(exit_value["value"], bool)
                    or exit_value.get("kind") == "signal"
                    and isinstance(exit_value.get("value"), str)
                    and bool(exit_value["value"])
                )
            ):
                raise TranscriptValidationError("observation process is invalid")
            if records[-1]["kind"] == "run.finished":
                finished_exit = cast(
                    dict[str, JsonValue],
                    cast(dict[str, JsonValue], terminal_payload)["exit"],
                )
                if exit_value.get("kind") != finished_exit.get(
                    "kind"
                ) or not _json_equivalent(
                    exit_value.get("value"), finished_exit.get("value")
                ):
                    raise TranscriptValidationError(
                        "observation process exit does not match run.finished exit"
                    )
    _validate_evidence_times(
        records[len(capabilities) + 1 : -1],
        cast(int, clock_config["initial_ms"]),
    )


def _validate_execution_epochs(body: list[Record]) -> None:
    readiness_observed = False
    input_epoch_open = False
    stop_seen = False
    for index, record in enumerate(body):
        kind = record["kind"]
        if not readiness_observed:
            if kind == "diagnostic":
                continue
            if kind != "observation":
                raise TranscriptValidationError(
                    "initial readiness observation must precede input"
                )
            readiness_observed = True
        elif isinstance(kind, str) and kind.startswith("input."):
            if stop_seen:
                raise TranscriptValidationError("input is not allowed after input.stop")
            if input_epoch_open:
                raise TranscriptValidationError(
                    "input epoch must close before another input"
                )
            input_epoch_open = True
            stop_seen = kind == "input.stop"
        elif kind == "observation":
            if not input_epoch_open:
                raise TranscriptValidationError(
                    "observation is not allowed while the run is idle"
                )
            input_epoch_open = False
        elif kind == "diagnostic" and not input_epoch_open:
            raise TranscriptValidationError(
                "diagnostic is not allowed while the run is idle"
            )
        if kind == "observation":
            payload = record["payload"]
            process = payload.get("process") if isinstance(payload, dict) else None
            if (
                isinstance(process, dict)
                and process.get("state") == "exited"
                and index != len(body) - 1
            ):
                raise TranscriptValidationError(
                    "process exit observation must be the final body record"
                )


def _validate_evidence_times(records: list[Record], manual_time: int) -> None:
    for record in records:
        payload = cast(dict[str, JsonValue], record["payload"])
        if record["kind"] == "input.clock_advanced":
            manual_time = cast(int, payload["at_ms"])
        elif (
            record["kind"] in {"diagnostic", "observation"}
            and payload["at_ms"] != manual_time
        ):
            raise TranscriptValidationError(
                f"{record['kind']} at_ms does not match the manual clock"
            )


def _is_well_formed_language_tag(value: str) -> bool:
    if value == "C":
        return True
    if value.lower() in _GRANDFATHERED_LANGUAGE_TAGS:
        return True

    subtags = value.split("-")
    if any(
        not 1 <= len(subtag) <= 8 or not subtag.isascii() or not subtag.isalnum()
        for subtag in subtags
    ):
        return False
    if subtags[0].lower() == "x":
        return len(subtags) > 1

    primary = subtags[0]
    if not primary.isalpha() or not 2 <= len(primary) <= 8:
        return False
    index = 1
    if len(primary) <= 3:
        extlang_count = 0
        while (
            index < len(subtags)
            and len(subtags[index]) == 3
            and subtags[index].isalpha()
            and extlang_count < 3
        ):
            index += 1
            extlang_count += 1
    if index < len(subtags) and len(subtags[index]) == 4 and subtags[index].isalpha():
        index += 1
    if index < len(subtags) and (
        (len(subtags[index]) == 2 and subtags[index].isalpha())
        or (len(subtags[index]) == 3 and subtags[index].isdigit())
    ):
        index += 1

    variants: set[str] = set()
    while index < len(subtags) and (
        5 <= len(subtags[index]) <= 8
        or (len(subtags[index]) == 4 and subtags[index][0].isdigit())
    ):
        variant = subtags[index].lower()
        if variant in variants:
            return False
        variants.add(variant)
        index += 1

    extension_singletons: set[str] = set()
    while (
        index < len(subtags)
        and len(subtags[index]) == 1
        and subtags[index].lower() != "x"
    ):
        singleton = subtags[index].lower()
        if singleton in extension_singletons:
            return False
        extension_singletons.add(singleton)
        index += 1
        extension_start = index
        while index < len(subtags) and len(subtags[index]) >= 2:
            index += 1
        if index == extension_start:
            return False

    if index < len(subtags) and subtags[index].lower() == "x":
        index += 1
        if index == len(subtags):
            return False
        index = len(subtags)
    return index == len(subtags)


def _json_equivalent(left: JsonValue, right: JsonValue) -> bool:
    if type(left) is not type(right):
        return False
    if isinstance(left, list):
        right_list = cast(list[JsonValue], right)
        return len(left) == len(right_list) and all(
            _json_equivalent(left_item, right_item)
            for left_item, right_item in zip(left, right_list, strict=True)
        )
    if isinstance(left, dict):
        right_dict = cast(dict[str, JsonValue], right)
        return left.keys() == right_dict.keys() and all(
            _json_equivalent(left[key], right_dict[key]) for key in left
        )
    return left == right


def _validate_replay_subject(subject: dict[str, JsonValue]) -> None:
    if subject.get("format") != "termverify.replay-subject/v1":
        raise TranscriptValidationError("run.started subject format is invalid")
    required = {
        "format",
        "application",
        "fixture",
        "adapter",
        "normalizer",
        "state_schema",
    }
    if not required <= subject.keys() or any(
        key not in required | {"platform"} and not key.startswith("x-")
        for key in subject
    ):
        raise TranscriptValidationError("run.started subject members are incomplete")
    application = subject["application"]
    if not isinstance(application, dict) or not _has_exact_selector_members(
        application, frozenset({"id", "version", "build"})
    ):
        raise TranscriptValidationError("run.started subject application is invalid")
    for name in ("fixture", "adapter", "normalizer", "state_schema"):
        selector = subject[name]
        if not isinstance(selector, dict) or not _has_exact_selector_members(
            selector, frozenset({"id", "version"})
        ):
            raise TranscriptValidationError(f"run.started subject {name} is invalid")
    if "platform" in subject:
        platform = subject["platform"]
        if not isinstance(platform, dict) or not _has_exact_selector_members(
            platform, frozenset({"os", "architecture"})
        ):
            raise TranscriptValidationError("run.started subject platform is invalid")


def _has_exact_selector_members(
    value: dict[str, JsonValue], required: frozenset[str]
) -> bool:
    return (
        required <= value.keys()
        and all(
            isinstance(value[key], str)
            and _IDENTIFIER_PATTERN.fullmatch(cast(str, value[key])) is not None
            for key in required
        )
        and not any(key not in required and not key.startswith("x-") for key in value)
    )


def _has_unknown_generic_members(
    value: dict[str, JsonValue], allowed: frozenset[str]
) -> bool:
    return any(key not in allowed and not key.startswith("x-") for key in value)
