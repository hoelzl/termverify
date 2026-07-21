"""Strict `termverify.control/v1` codec: message model, parsing, serialization.

This module is the authoritative runtime acceptance for the control
protocol; `docs/knowledge/control-protocol.md` is the normative
specification. The codec mirrors the transcript codec's habits: fixed
protocol-owned resource limits checked before JSON decoding, duplicate
member rejection, RFC 8785 canonical serialization, and closed payload
vocabularies — anything outside the documented shape raises
:class:`ControlProtocolError`, never a guess or a repair.

The codec is pure: no clock, process, filesystem, or network state. It
parses and validates single messages; lifecycle position (which kind is
legal *now*) is the adapter's state machine, and lifecycle violations
surface there as `peer-lifecycle` rather than here as `peer-malformed`.
"""

from __future__ import annotations

import json
import math
from typing import Final, NoReturn, cast

import rfc8785

from termverify._json import JsonValue
from termverify._language_tag import is_well_formed_language_tag
from termverify._timezone_v1 import is_timezone_name

__all__ = [
    "CONTROL_PROTOCOL_V1",
    "MAX_EPOCH_DIAGNOSTICS",
    "MAX_STARTUP_DIAGNOSTICS",
    "ControlProtocolError",
    "parse_message",
    "serialize_message",
]

#: The exact protocol tag every v1 message envelope carries.
CONTROL_PROTOCOL_V1: Final = "termverify.control/v1"

#: Fixed v1 resource limits (normative values in
#: `docs/knowledge/control-protocol.md`). Kept numerically identical to
#: the transcript protocol's per-record budgets on purpose: one ceiling
#: family, two protocols.
_MAX_LINE_BYTES: Final = 4 * 1024 * 1024
_MAX_JSON_NESTING: Final = 64
_MAX_COLLECTION_ITEMS: Final = 16_384
_MAX_JSON_VALUES: Final = 100_000
_MAX_STRING_BYTES: Final = 1024 * 1024
_MAX_MESSAGE_STRING_BYTES: Final = 2 * 1024 * 1024

#: Diagnostic-count ceilings; exceeding them is a `peer-malformed`
#: structural failure (the budget lives here because it is protocol
#: policy, not adapter policy).
MAX_STARTUP_DIAGNOSTICS: Final = 100
MAX_EPOCH_DIAGNOSTICS: Final = 100

#: Seed ceiling, mirrored from the transcript codec: an unsigned 64-bit
#: integer as a decimal string with no leading zeros.
_MAX_SEED: Final = "18446744073709551615"

#: Adapter-to-child message kinds.
_INPUT_KINDS: Final = frozenset(
    {
        "session.hello",
        "input.text",
        "input.key",
        "input.resize",
        "input.clock",
        "input.stop",
    }
)

#: Child-to-adapter message kinds.
_CHILD_KINDS: Final = frozenset(
    {
        "session.unsupported",
        "session.failed",
        "session.ready",
        "diagnostic",
        "observation",
        "run.finished",
        "run.failed",
    }
)

_MESSAGE_KINDS: Final = _INPUT_KINDS | _CHILD_KINDS

_CONSTRAINT_NAMES: Final = (
    "seed",
    "clock",
    "locale",
    "timezone",
    "terminal",
    "filesystem",
    "network",
)

#: Required payload members per kind. All payloads are closed apart from
#: `x-` extensions; optional members are listed in `_OPTIONAL_MEMBERS`.
_REQUIRED_MEMBERS: Final = {
    "session.hello": frozenset({"run_id", "config", "at_ms"}),
    "session.unsupported": frozenset({"constraint", "code", "message"}),
    "session.failed": frozenset({"error"}),
    "session.ready": frozenset({"observation"}),
    "diagnostic": frozenset({"code", "message"}),
    "input.text": frozenset({"text"}),
    "input.key": frozenset({"keys"}),
    "input.resize": frozenset({"columns", "rows"}),
    "input.clock": frozenset({"at_ms"}),
    "input.stop": frozenset(),
    "observation": frozenset({"state", "ui", "events"}),
    "run.finished": frozenset({"exit"}),
    "run.failed": frozenset({"error"}),
}
_OPTIONAL_MEMBERS: Final = {
    "session.unsupported": frozenset({"details"}),
    "diagnostic": frozenset({"details"}),
    "observation": frozenset({"frame", "process"}),
}


class ControlProtocolError(ValueError):
    """Raised when bytes or a message violate `termverify.control/v1`."""


def _fail(message: str) -> NoReturn:
    raise ControlProtocolError(message)


def _require_non_empty_string(value: object, name: str) -> None:
    if type(value) is not str or not value:
        _fail(f"{name} must be a non-empty string")


def _require_plain_int(value: object, name: str, *, positive: bool = False) -> None:
    if type(value) is not int:
        _fail(f"{name} must be an integer")
    if positive and value <= 0:
        _fail(f"{name} must be positive")
    if not positive and value < 0:
        _fail(f"{name} must be non-negative")


def _validate_run_id(value: object) -> None:
    _require_non_empty_string(value, "run_id")
    text = cast(str, value)
    if any(char not in "abcdefghijklmnopqrstuvwxyz0123456789._-" for char in text):
        _fail("run_id uses characters outside the v1 identifier grammar")


def _validate_error_shape(value: object, name: str) -> None:
    if type(value) is not dict:
        _fail(f"{name} must be an object")
    error = cast(dict[str, JsonValue], value)
    for member in error:
        if member not in ("code", "message", "details") and not member.startswith("x-"):
            _fail(f"{name} member {member!r} is reserved")
    _require_non_empty_string(error.get("code"), f"{name}.code")
    if type(error.get("message")) is not str:
        _fail(f"{name}.message must be a string")


def _validate_exit_record(value: object, name: str) -> None:
    if type(value) is not dict:
        _fail(f"{name} must be an object")
    record = cast(dict[str, JsonValue], value)
    for member in record:
        if member not in ("kind", "value") and not member.startswith("x-"):
            _fail(f"{name} member {member!r} is reserved")
    kind = record.get("kind")
    if kind == "code":
        if type(record.get("value")) is not int:
            _fail(f"{name}.value must be an integer for a code exit")
    elif kind == "signal":
        _require_non_empty_string(record.get("value"), f"{name}.value")
    else:
        _fail(f"{name}.kind must be 'code' or 'signal'")


def _validate_cursor(value: object) -> None:
    if type(value) is not dict:
        _fail("ui.cursor must be an object")
    cursor = cast(dict[str, JsonValue], value)
    for member in cursor:
        if member not in ("column", "row", "visible") and not member.startswith("x-"):
            _fail(f"ui.cursor member {member!r} is reserved")
    _require_plain_int(cursor.get("column"), "ui.cursor.column")
    _require_plain_int(cursor.get("row"), "ui.cursor.row")
    if type(cursor.get("visible")) is not bool:
        _fail("ui.cursor.visible must be a boolean")


def _validate_region(value: object, index: int) -> None:
    if type(value) is not dict:
        _fail(f"ui.regions[{index}] must be an object")
    region = cast(dict[str, JsonValue], value)
    for member in region:
        if member not in ("id", "role", "column", "row", "columns", "rows") and (
            not member.startswith("x-")
        ):
            _fail(f"ui.regions[{index}] member {member!r} is reserved")
    _require_non_empty_string(region.get("id"), f"ui.regions[{index}].id")
    _require_non_empty_string(region.get("role"), f"ui.regions[{index}].role")
    _require_plain_int(region.get("column"), f"ui.regions[{index}].column")
    _require_plain_int(region.get("row"), f"ui.regions[{index}].row")
    _require_plain_int(
        region.get("columns"), f"ui.regions[{index}].columns", positive=True
    )
    _require_plain_int(region.get("rows"), f"ui.regions[{index}].rows", positive=True)


def _validate_ui(value: object) -> None:
    if type(value) is not dict:
        _fail("ui must be an object")
    ui = cast(dict[str, JsonValue], value)
    for member in ui:
        if member not in ("regions", "focus", "cursor", "mode") and (
            not member.startswith("x-")
        ):
            _fail(f"ui member {member!r} is reserved")
    regions = ui.get("regions")
    if type(regions) is not list:
        _fail("ui.regions must be an array")
    ids: list[str] = []
    for index, region in enumerate(regions):
        _validate_region(region, index)
        ids.append(cast(str, cast(dict[str, JsonValue], region)["id"]))
    if len(ids) != len(set(ids)):
        _fail("ui region ids must be unique")
    focus = ui.get("focus")
    if focus is not None:
        _require_non_empty_string(focus, "ui.focus")
        if focus not in ids:
            _fail("ui.focus must name a region")
    if "cursor" not in ui:
        _fail("ui.cursor is required")
    _validate_cursor(ui["cursor"])
    mode = ui.get("mode")
    if mode is not None and type(mode) is not str:
        _fail("ui.mode must be a string or null")


def _validate_event(value: object, index: int) -> None:
    if type(value) is not dict:
        _fail(f"events[{index}] must be an object")
    event = cast(dict[str, JsonValue], value)
    for member in event:
        if member not in ("type", "data") and not member.startswith("x-"):
            _fail(f"events[{index}] member {member!r} is reserved")
    _require_non_empty_string(event.get("type"), f"events[{index}].type")
    if "data" not in event:
        _fail(f"events[{index}].data is required")


def _validate_frame(value: object) -> None:
    if type(value) is not dict:
        _fail("frame must be an object")
    frame = cast(dict[str, JsonValue], value)
    for member in frame:
        if member not in ("lines", "columns", "rows") and not member.startswith("x-"):
            _fail(f"frame member {member!r} is reserved")
    lines = frame.get("lines")
    if type(lines) is not list or any(type(line) is not str for line in lines):
        _fail("frame.lines must be an array of strings")
    _require_plain_int(frame.get("columns"), "frame.columns", positive=True)
    _require_plain_int(frame.get("rows"), "frame.rows", positive=True)
    if len(lines) != cast(int, frame["rows"]):
        _fail("frame rows must equal the number of lines")


def _validate_process(value: object) -> None:
    if type(value) is not dict:
        _fail("process must be an object")
    process = cast(dict[str, JsonValue], value)
    for member in process:
        if member not in ("state", "exit") and not member.startswith("x-"):
            _fail(f"process member {member!r} is reserved")
    state = process.get("state")
    if state == "running":
        if "exit" in process:
            _fail("a running process observation cannot carry exit evidence")
    elif state == "exited":
        if "exit" not in process:
            _fail("an exited process observation requires exit evidence")
        _validate_exit_record(process["exit"], "process.exit")
    else:
        _fail("process.state must be 'running' or 'exited'")


def _validate_observation_payload(payload: dict[str, JsonValue]) -> None:
    for member in payload:
        if (
            member not in _REQUIRED_MEMBERS["observation"]
            and member not in _OPTIONAL_MEMBERS["observation"]
            and (not member.startswith("x-"))
        ):
            _fail(f"observation payload member {member!r} is reserved")
    if "state" not in payload:
        _fail("observation.state is required")
    if "ui" not in payload:
        _fail("observation.ui is required")
    _validate_ui(payload["ui"])
    events = payload.get("events")
    if type(events) is not list:
        _fail("observation.events must be an array")
    for index, event in enumerate(events):
        _validate_event(event, index)
    if "frame" in payload:
        _validate_frame(payload["frame"])
    if "process" in payload:
        _validate_process(payload["process"])


def _validate_config(value: object) -> None:
    if type(value) is not dict:
        _fail("config must be an object")
    config = cast(dict[str, JsonValue], value)
    required = {
        "seed",
        "clock",
        "locale",
        "timezone",
        "terminal",
        "filesystem",
        "network",
    }
    for member in config:
        if member not in required and not member.startswith("x-"):
            _fail(f"config member {member!r} is reserved")
    missing = required - set(config)
    if missing:
        _fail(f"config is missing required members: {sorted(missing)}")
    # The hello config is exactly the transcript/v1 run.started config
    # shape (docs/knowledge/control-protocol.md); the checks below mirror
    # the transcript validator member for member.
    _require_non_empty_string(config["seed"], "config.seed")
    seed = cast(str, config["seed"])
    if (
        not seed.isascii()
        or not seed.isdecimal()
        or (len(seed) > 1 and seed.startswith("0"))
        or len(seed) > len(_MAX_SEED)
        or (len(seed) == len(_MAX_SEED) and seed > _MAX_SEED)
    ):
        _fail("config.seed must be a canonical unsigned 64-bit decimal string")
    clock = config["clock"]
    if type(clock) is not dict:
        _fail("config.clock must be an object")
    clock_members = clock
    for member in clock_members:
        if member not in ("mode", "initial_ms") and not member.startswith("x-"):
            _fail(f"config.clock member {member!r} is reserved")
    if clock_members.get("mode") != "manual":
        _fail("config.clock.mode must be 'manual'")
    _require_plain_int(clock_members.get("initial_ms"), "config.clock.initial_ms")
    _require_non_empty_string(config["locale"], "config.locale")
    if not is_well_formed_language_tag(cast(str, config["locale"])):
        _fail("config.locale must be a well-formed BCP 47 language tag")
    _require_non_empty_string(config["timezone"], "config.timezone")
    if not is_timezone_name(config["timezone"]):
        _fail("config.timezone must name a termverify.timezone/v1 entry")
    terminal = config["terminal"]
    if type(terminal) is not dict:
        _fail("config.terminal must be an object")
    terminal_members = terminal
    for member in terminal_members:
        if member not in ("columns", "rows", "capabilities") and (
            not member.startswith("x-")
        ):
            _fail(f"config.terminal member {member!r} is reserved")
    _require_plain_int(
        terminal_members.get("columns"), "config.terminal.columns", positive=True
    )
    _require_plain_int(
        terminal_members.get("rows"), "config.terminal.rows", positive=True
    )
    capabilities = terminal_members.get("capabilities")
    if type(capabilities) is not list or any(
        type(capability) is not str or not capability for capability in capabilities
    ):
        _fail("config.terminal.capabilities must be an array of non-empty strings")
    canonical_capabilities = cast(list[str], capabilities)
    if canonical_capabilities != sorted(canonical_capabilities) or len(
        canonical_capabilities
    ) != len(set(canonical_capabilities)):
        _fail("config.terminal.capabilities must be sorted and unique")
    filesystem = config["filesystem"]
    if type(filesystem) is not dict:
        _fail("config.filesystem must be an object")
    filesystem_members = filesystem
    for member in filesystem_members:
        if member not in ("mode", "root_id") and not member.startswith("x-"):
            _fail(f"config.filesystem member {member!r} is reserved")
    if filesystem_members.get("mode") != "sandbox":
        _fail("config.filesystem.mode must be 'sandbox'")
    _require_non_empty_string(
        filesystem_members.get("root_id"), "config.filesystem.root_id"
    )
    network = config["network"]
    if type(network) is not dict:
        _fail("config.network must be an object")
    network_members = network
    mode = network_members.get("mode")
    if mode == "deny":
        for member in network_members:
            if member != "mode" and not member.startswith("x-"):
                _fail(f"config.network member {member!r} is reserved")
    elif mode == "allow-list":
        for member in network_members:
            if member not in ("mode", "allowed") and not member.startswith("x-"):
                _fail(f"config.network member {member!r} is reserved")
        allowed = network_members.get("allowed")
        if type(allowed) is not list:
            _fail("config.network.allowed must be an array")
        allow_pairs: list[tuple[str, int]] = []
        for index, endpoint in enumerate(allowed):
            if type(endpoint) is not dict:
                _fail(f"config.network.allowed[{index}] must be an object")
            endpoint_members = endpoint
            for member in endpoint_members:
                if member not in ("host", "port") and not member.startswith("x-"):
                    _fail(
                        f"config.network.allowed[{index}] member {member!r} is reserved"
                    )
            _require_non_empty_string(
                endpoint_members.get("host"), f"config.network.allowed[{index}].host"
            )
            port = endpoint_members.get("port")
            _require_plain_int(
                port,
                f"config.network.allowed[{index}].port",
                positive=True,
            )
            if cast(int, port) > 65535:
                _fail(f"config.network.allowed[{index}].port must be at most 65535")
            allow_pairs.append((cast(str, endpoint_members["host"]), cast(int, port)))
        if allow_pairs != sorted(allow_pairs) or len(allow_pairs) != len(
            set(allow_pairs)
        ):
            _fail("config.network.allowed must be sorted and unique")
    else:
        _fail("config.network.mode must be 'deny' or 'allow-list'")


def _validate_payload(kind: str, payload: object) -> None:
    if type(payload) is not dict:
        _fail("payload must be an object")
    members = cast(dict[str, JsonValue], payload)
    required = _REQUIRED_MEMBERS[kind]
    optional = _OPTIONAL_MEMBERS.get(kind, frozenset())
    for member in members:
        if (
            member not in required
            and member not in optional
            and (not member.startswith("x-"))
        ):
            _fail(f"{kind} payload member {member!r} is reserved")
    for member in required:
        if member not in members:
            _fail(f"{kind} payload is missing required member {member!r}")

    if kind == "session.hello":
        _validate_run_id(members["run_id"])
        _validate_config(members["config"])
        _require_plain_int(members["at_ms"], "session.hello.at_ms")
    elif kind == "session.unsupported":
        constraint = members["constraint"]
        if constraint not in _CONSTRAINT_NAMES:
            _fail("session.unsupported.constraint must name a v1 constraint")
        code = members["code"]
        if code not in ("constraint-unsupported", "constraint-not-enforced"):
            _fail("session.unsupported.code is outside the v1 vocabulary")
        if type(members["message"]) is not str:
            _fail("session.unsupported.message must be a string")
    elif kind == "session.failed":
        _validate_error_shape(members["error"], "session.failed.error")
    elif kind == "session.ready":
        if type(members["observation"]) is not dict:
            _fail("session.ready.observation must be an object")
        ready_observation = members["observation"]
        _validate_observation_payload(ready_observation)
        process = ready_observation.get("process")
        if type(process) is dict and process.get("state") == "exited":
            _fail("readiness cannot contain exited-process evidence")
    elif kind == "diagnostic":
        _require_non_empty_string(members["code"], "diagnostic.code")
        if type(members["message"]) is not str:
            _fail("diagnostic.message must be a string")
    elif kind == "input.text":
        if type(members["text"]) is not str:
            _fail("input.text.text must be a string")
    elif kind == "input.key":
        keys = members["keys"]
        if type(keys) is not list or any(type(key) is not str for key in keys):
            _fail("input.key.keys must be an array of strings")
        if not keys:
            _fail("input.key.keys must be non-empty")
    elif kind == "input.resize":
        _require_plain_int(members["columns"], "input.resize.columns", positive=True)
        _require_plain_int(members["rows"], "input.resize.rows", positive=True)
    elif kind == "input.clock":
        _require_plain_int(members["at_ms"], "input.clock.at_ms")
    elif kind == "input.stop":
        pass
    elif kind == "observation":
        _validate_observation_payload(members)
    elif kind == "run.finished":
        _validate_exit_record(members["exit"], "run.finished.exit")
    elif kind == "run.failed":
        _validate_error_shape(members["error"], "run.failed.error")


def _validate_json_value(value: object) -> None:
    """Iterative structural budget check, mirroring the transcript codec.

    Object keys are not value nodes (docs/knowledge/control-protocol.md):
    they count against the string budgets only, never the value count.
    """
    pending: list[tuple[object, int]] = [(value, 1)]
    value_count = 0
    string_bytes = 0
    while pending:
        current, depth = pending.pop()
        value_count += 1
        if value_count > _MAX_JSON_VALUES:
            _fail("message JSON value count exceeds the v1 limit")
        if type(current) is str:
            encoded = len(current.encode("utf-8", errors="replace"))
            if encoded > _MAX_STRING_BYTES:
                _fail("message string bytes exceed the v1 limit")
            string_bytes += encoded
            if string_bytes > _MAX_MESSAGE_STRING_BYTES:
                _fail("message aggregate string bytes exceed the v1 limit")
            continue
        if current is None or type(current) in {bool, int}:
            continue
        if type(current) is float:
            if not math.isfinite(current):
                _fail("message numbers must be finite")
            continue
        if type(current) is list:
            items = cast(list[JsonValue], current)
            if len(items) > _MAX_COLLECTION_ITEMS:
                _fail("message collection items exceed the v1 limit")
            if depth >= _MAX_JSON_NESTING and items:
                _fail("message JSON nesting exceeds the v1 limit")
            pending.extend((item, depth + 1) for item in items)
            continue
        if type(current) is dict:
            members = cast(dict[str, JsonValue], current)
            if len(members) > _MAX_COLLECTION_ITEMS:
                _fail("message collection items exceed the v1 limit")
            if depth >= _MAX_JSON_NESTING and members:
                _fail("message JSON nesting exceeds the v1 limit")
            for key, item in members.items():
                if type(key) is not str:
                    _fail("message object keys must be strings")
                encoded = len(key.encode("utf-8", errors="replace"))
                if encoded > _MAX_STRING_BYTES:
                    _fail("message string bytes exceed the v1 limit")
                string_bytes += encoded
                if string_bytes > _MAX_MESSAGE_STRING_BYTES:
                    _fail("message aggregate string bytes exceed the v1 limit")
                pending.append((item, depth + 1))
            continue
        _fail("message contains a value outside the JSON model")


def _validate_lexical_nesting(line: bytes) -> None:
    depth = 0
    in_string = False
    escaped = False
    for byte in line:
        if in_string:
            if escaped:
                escaped = False
            elif byte == 0x5C:  # backslash
                escaped = True
            elif byte == 0x22:  # quote
                in_string = False
            continue
        if byte == 0x22:
            in_string = True
        elif byte in (0x7B, 0x5B):  # { [
            depth += 1
            if depth > _MAX_JSON_NESTING:
                _fail("message JSON nesting exceeds the v1 limit")
        elif byte in (0x7D, 0x5D):  # } ]
            depth -= 1


def _reject_duplicate_members(
    pairs: list[tuple[str, JsonValue]],
) -> dict[str, JsonValue]:
    result: dict[str, JsonValue] = {}
    for key, value in pairs:
        if key in result:
            _fail(f"duplicate object member {key!r}")
        result[key] = value
    return result


def parse_message(line: bytes) -> dict[str, JsonValue]:
    """Parse and validate one LF-terminated `termverify.control/v1` line.

    Returns the message as a mutable JSON object. Raises
    :class:`ControlProtocolError` for any framing, budget, envelope, or
    payload violation.
    """
    if type(line) is not bytes:
        raise TypeError("a control message must be bytes")
    if len(line) > _MAX_LINE_BYTES + 1:
        _fail("message line bytes exceed the v1 limit")
    if line.startswith(b"\xef\xbb\xbf") or b"\r" in line:
        _fail("message must be plain UTF-8 without a BOM or CR")
    if not line.endswith(b"\n"):
        _fail("message must end with exactly one LF")
    body = line[:-1]
    if b"\n" in body:
        _fail("message must be a single line")
    if len(body) > _MAX_LINE_BYTES:
        _fail("message line bytes exceed the v1 limit")
    _validate_lexical_nesting(body)
    try:
        text = body.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise ControlProtocolError("message is not valid UTF-8") from error
    try:
        raw: object = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_members,
            parse_constant=lambda constant: _fail("message numbers must be finite"),
        )
    except json.JSONDecodeError as error:
        raise ControlProtocolError("message is not valid JSON") from error
    if type(raw) is not dict:
        _fail("message must be a JSON object")
    message = cast(dict[str, JsonValue], raw)
    _validate_json_value(message)

    for member in message:
        if member not in ("protocol", "kind", "payload") and not member.startswith(
            "x-"
        ):
            _fail(f"envelope member {member!r} is reserved")
    if message.get("protocol") != CONTROL_PROTOCOL_V1:
        _fail("envelope protocol must be exactly termverify.control/v1")
    kind = message.get("kind")
    if type(kind) is not str or kind not in _MESSAGE_KINDS:
        _fail("envelope kind is outside the v1 vocabulary")
    if "payload" not in message:
        _fail("envelope payload is required")
    _validate_payload(kind, message["payload"])
    return message


def serialize_message(message: dict[str, JsonValue]) -> bytes:
    """Validate and canonically serialize one message for the wire.

    The same validation as :func:`parse_message` applies, so every
    serialized message is admissible to the parser under the same
    ceilings. Returns the canonical bytes including the final LF.
    """
    if type(message) is not dict:
        raise TypeError("a control message must be a JSON object")
    _validate_json_value(message)
    for member in message:
        if member not in ("protocol", "kind", "payload") and not member.startswith(
            "x-"
        ):
            _fail(f"envelope member {member!r} is reserved")
    if message.get("protocol") != CONTROL_PROTOCOL_V1:
        _fail("envelope protocol must be exactly termverify.control/v1")
    kind = message.get("kind")
    if type(kind) is not str or kind not in _MESSAGE_KINDS:
        _fail("envelope kind is outside the v1 vocabulary")
    if "payload" not in message:
        _fail("envelope payload is required")
    _validate_payload(kind, message["payload"])
    try:
        canonical = rfc8785.dumps(message)
    except (rfc8785.CanonicalizationError, ValueError) as error:
        raise ControlProtocolError(
            "message cannot be canonically serialized"
        ) from error
    if len(canonical) > _MAX_LINE_BYTES:
        _fail("message line bytes exceed the v1 limit")
    return canonical + b"\n"
