"""Strict-codec tests for `termverify.control/v1` (`termverify.control`)."""

from __future__ import annotations

import json
from typing import cast

import pytest

from termverify._json import JsonValue
from termverify.control import (
    CONTROL_PROTOCOL_V1,
    MAX_EPOCH_DIAGNOSTICS,
    MAX_STARTUP_DIAGNOSTICS,
    ControlProtocolError,
    parse_message,
    serialize_message,
)

_RUN_ID = "01hgw0mg5e6w1a6b0rzg3zqk0r"


def _envelope(kind: str, payload: object) -> dict[str, JsonValue]:
    return {
        "protocol": CONTROL_PROTOCOL_V1,
        "kind": kind,
        "payload": cast(JsonValue, payload),
    }


def _hello_payload() -> dict[str, JsonValue]:
    return {
        "run_id": _RUN_ID,
        "config": {
            "seed": "42",
            "clock": {"mode": "manual", "initial_ms": 0},
            "locale": "en-US",
            "timezone": "UTC",
            "terminal": {"columns": 80, "rows": 24, "capabilities": []},
            "filesystem": {"mode": "sandbox", "root_id": "r"},
            "network": {"mode": "deny"},
        },
        "at_ms": 0,
    }


def test_control_protocol_version_is_v1() -> None:
    assert CONTROL_PROTOCOL_V1 == "termverify.control/v1"
    assert MAX_STARTUP_DIAGNOSTICS > 0
    assert MAX_EPOCH_DIAGNOSTICS > 0


def test_parse_accepts_a_valid_session_hello() -> None:
    message = parse_message(
        serialize_message(
            {
                "protocol": CONTROL_PROTOCOL_V1,
                "kind": "session.hello",
                "payload": _hello_payload(),
            }
        )
    )
    assert message["kind"] == "session.hello"


def test_parse_rejects_wrong_protocol_member() -> None:
    with pytest.raises(ControlProtocolError):
        parse_message(
            b'{"protocol":"termverify.control/v2","kind":"session.hello",'
            b'"payload":{}}\n'
        )


def test_parse_rejects_unknown_kind() -> None:
    with pytest.raises(ControlProtocolError):
        parse_message(
            b'{"protocol":"termverify.control/v1","kind":"bogus","payload":{}}\n'
        )


def test_parse_accepts_x_prefixed_extension_member() -> None:
    envelope: dict[str, JsonValue] = {
        "protocol": CONTROL_PROTOCOL_V1,
        "kind": "session.hello",
        "payload": _hello_payload(),
        "x-trace": "abc",
    }
    message = parse_message(serialize_message(envelope))
    assert message["x-trace"] == "abc"


def test_parse_rejects_non_x_reserved_envelope_member() -> None:
    with pytest.raises(ControlProtocolError):
        parse_message(
            b'{"protocol":"termverify.control/v1","kind":"session.hello",'
            b'"payload":{},"extra":1}\n'
        )


def test_parse_rejects_duplicate_members() -> None:
    with pytest.raises(ControlProtocolError):
        parse_message(
            b'{"protocol":"termverify.control/v1","protocol":'
            b'"termverify.control/v1","kind":"session.hello","payload":{}}\n'
        )


def test_parse_rejects_non_json() -> None:
    with pytest.raises(ControlProtocolError):
        parse_message(b"not json\n")


def test_parse_rejects_json_scalar() -> None:
    with pytest.raises(ControlProtocolError):
        parse_message(b"42\n")


def test_parse_rejects_overlong_line() -> None:
    big = b'{"protocol":"termverify.control/v1","kind":"diagnostic","payload":{}}'
    big = big + b" " * (64 * 1024)
    with pytest.raises(ControlProtocolError):
        parse_message(big + b"\n")


def test_parse_accepts_all_wire_kinds() -> None:
    kinds = (
        "session.hello",
        "session.unsupported",
        "session.failed",
        "session.ready",
        "input.text",
        "input.key",
        "input.resize",
        "input.clock",
        "input.stop",
        "run.finished",
        "run.failed",
        "observation",
        "diagnostic",
    )
    for kind in kinds:
        assert kind in {
            "session.hello",
            "session.unsupported",
            "session.failed",
            "session.ready",
            "input.text",
            "input.key",
            "input.resize",
            "input.clock",
            "input.stop",
            "run.finished",
            "run.failed",
            "observation",
            "diagnostic",
        }


def test_round_trip_session_hello() -> None:
    message: dict[str, JsonValue] = {
        "protocol": CONTROL_PROTOCOL_V1,
        "kind": "session.hello",
        "payload": _hello_payload(),
    }
    wire = serialize_message(message)
    assert wire.endswith(b"\n")
    assert b'"' in wire
    parsed = parse_message(wire)
    assert parsed["kind"] == "session.hello"
    payload = parsed["payload"]
    assert isinstance(payload, dict)
    assert payload["run_id"] == _RUN_ID


def test_serialize_rejects_undeliverable_message() -> None:
    message = _envelope("session.hello", {"run_id": "x"})
    with pytest.raises(ControlProtocolError):
        serialize_message(message)


# --- unpaired surrogates (adversarial review 2026-07-24, R5) ------------------


def _line_with_envelope_extension(value: object) -> bytes:
    """Serialize by hand: json.dumps escapes lone surrogates without error,
    so the resulting line is valid UTF-8 bytes carrying a uDxxx escape
    sequence — exactly what a hostile subject can put on the wire."""
    message = _envelope("session.hello", _hello_payload())
    message["x-note"] = cast(JsonValue, value)
    return (json.dumps(message) + "\n").encode("ascii")


def test_parse_rejects_a_lone_surrogate_in_a_string_value() -> None:
    """RFC 8785 canonicalization raises on lone surrogates, so admitting
    one at parse time lets hostile input crash the recording pipeline
    instead of failing peer-malformed."""
    with pytest.raises(ControlProtocolError, match="unpaired surrogate"):
        parse_message(_line_with_envelope_extension("\ud800"))


def test_parse_rejects_a_lone_surrogate_in_an_object_key() -> None:
    with pytest.raises(ControlProtocolError, match="unpaired surrogate"):
        parse_message(_line_with_envelope_extension({"k\udfff": "v"}))


def test_parse_still_accepts_paired_surrogates_as_astral_characters() -> None:
    """A valid surrogate pair is an ordinary astral codepoint and must
    round-trip — the rejection targets only unpaired halves."""
    message = parse_message(_line_with_envelope_extension("\U0001f600"))
    assert message["x-note"] == "\U0001f600"
    assert parse_message(serialize_message(message))["x-note"] == "\U0001f600"


def test_parse_rejects_a_lone_surrogate_inside_a_payload_string() -> None:
    """Position-independence guard: the walk covers payload members too,
    so a refactor moving the check into per-member validators cannot
    silently miss a spot."""
    line = (
        json.dumps(
            {
                "protocol": CONTROL_PROTOCOL_V1,
                "kind": "diagnostic",
                "payload": {"code": "x-probe", "message": "\udbff"},
            }
        )
        + "\n"
    ).encode("ascii")
    with pytest.raises(ControlProtocolError, match="unpaired surrogate"):
        parse_message(line)


def test_serialize_rejects_a_lone_surrogate_with_the_codec_error() -> None:
    """Symmetry: the serialize direction fails with ControlProtocolError,
    not a leaked rfc8785 exception."""
    message = _envelope("session.hello", _hello_payload())
    message["x-note"] = "\udc00"
    with pytest.raises(ControlProtocolError, match="unpaired surrogate"):
        serialize_message(message)
