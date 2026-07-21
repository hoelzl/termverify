"""Branch-coverage tests for the `termverify.control/v1` codec validators.

The happy-path round trips live in `tests/test_control_codec.py`; this
module walks the validator failure branches and ceiling checks so the
codec's strictness is itself under test, one branch per expectation.
"""

from __future__ import annotations

import json
from typing import cast

import pytest

from termverify._json import JsonValue
from termverify.control import (
    CONTROL_PROTOCOL_V1,
    ControlProtocolError,
    parse_message,
    serialize_message,
)

_RUN_ID = "01hgw0mg5e6w1a6b0rzg3zqk0r"


def _config(**overrides: object) -> dict[str, JsonValue]:
    config: dict[str, JsonValue] = {
        "seed": "42",
        "clock": {"mode": "manual", "initial_ms": 0},
        "locale": "en-US",
        "timezone": "UTC",
        "terminal": {"columns": 80, "rows": 24, "capabilities": []},
        "filesystem": {"mode": "sandbox", "root_id": "root"},
        "network": {"mode": "deny"},
    }
    for key, value in overrides.items():
        config[key] = cast(JsonValue, value)
    return config


def _envelope(kind: str, payload: object) -> dict[str, JsonValue]:
    return {
        "protocol": CONTROL_PROTOCOL_V1,
        "kind": kind,
        "payload": cast(JsonValue, payload),
    }


def _wire(kind: str, payload: object) -> bytes:
    return json.dumps(_envelope(kind, payload)).encode() + b"\n"


def _hello_payload(**config_overrides: object) -> dict[str, JsonValue]:
    return {
        "run_id": _RUN_ID,
        "config": _config(**config_overrides),
        "at_ms": 0,
    }


def _rejects(kind: str, payload: object) -> None:
    with pytest.raises(ControlProtocolError):
        parse_message(_wire(kind, payload))


# --- framing ---------------------------------------------------------------


def test_parse_rejects_non_bytes() -> None:
    with pytest.raises(TypeError):
        parse_message(cast(bytes, "{}"))


def test_parse_rejects_line_past_the_hard_cap() -> None:
    with pytest.raises(ControlProtocolError):
        parse_message(b"x" * (4 * 1024 * 1024 + 2))


def test_parse_rejects_bom() -> None:
    with pytest.raises(ControlProtocolError):
        parse_message(b"\xef\xbb\xbf" + b'{"protocol":"x"}\n')


def test_parse_rejects_carriage_return() -> None:
    with pytest.raises(ControlProtocolError):
        parse_message(b'{"protocol":"x"}\r\n')


def test_parse_rejects_missing_lf() -> None:
    with pytest.raises(ControlProtocolError):
        parse_message(b'{"protocol":"x"}')


def test_parse_rejects_embedded_lf() -> None:
    with pytest.raises(ControlProtocolError):
        parse_message(b'{"protocol":\n"x"}\n')


def test_parse_rejects_lexical_nesting_beyond_the_limit() -> None:
    with pytest.raises(ControlProtocolError):
        parse_message(b"[" * 65 + b"\n")


def test_lexical_scan_handles_escaped_quotes_and_braces_in_strings() -> None:
    # Escaped quotes, backslashes, and braces inside strings must not
    # disturb the lexical nesting scan.
    with pytest.raises(ControlProtocolError):
        parse_message(b'"\\\\ \\" { }"\n')


def test_parse_rejects_invalid_utf8() -> None:
    with pytest.raises(ControlProtocolError):
        parse_message(b'{"protocol":"\xff"}\n')


def test_parse_rejects_missing_payload_member() -> None:
    with pytest.raises(ControlProtocolError):
        parse_message(b'{"protocol":"termverify.control/v1","kind":"input.stop"}\n')


# --- generic payload-member checks -----------------------------------------


def test_payload_must_be_an_object() -> None:
    _rejects("input.stop", [])


def test_payload_rejects_reserved_member() -> None:
    _rejects("input.stop", {"extra": 1})


def test_payload_accepts_x_prefixed_member() -> None:
    parse_message(_wire("input.stop", {"x-note": 1}))


def test_payload_rejects_missing_required_member() -> None:
    _rejects("input.text", {})


def test_serialize_rejects_non_mapping() -> None:
    with pytest.raises(TypeError):
        serialize_message(cast(dict[str, JsonValue], ["x"]))


# --- session.hello ----------------------------------------------------------


def test_hello_rejects_bad_run_id_characters() -> None:
    payload = _hello_payload()
    payload["run_id"] = "UPPER"
    _rejects("session.hello", payload)


def test_hello_rejects_non_integer_at_ms() -> None:
    payload = _hello_payload()
    payload["at_ms"] = "0"
    _rejects("session.hello", payload)


def test_hello_rejects_negative_at_ms() -> None:
    payload = _hello_payload()
    payload["at_ms"] = -1
    _rejects("session.hello", payload)


def test_config_must_be_an_object() -> None:
    _rejects("session.hello", {"run_id": _RUN_ID, "config": [], "at_ms": 0})


def test_config_rejects_reserved_member() -> None:
    _rejects("session.hello", _hello_payload(bogus=1))


def test_config_reports_missing_members() -> None:
    _rejects("session.hello", {"run_id": _RUN_ID, "config": {}, "at_ms": 0})


def test_config_rejects_empty_seed() -> None:
    _rejects("session.hello", _hello_payload(seed=""))


def test_config_rejects_non_decimal_seed() -> None:
    _rejects("session.hello", _hello_payload(seed="42a"))


def test_config_rejects_non_object_clock() -> None:
    _rejects("session.hello", _hello_payload(clock=1))


def test_config_rejects_non_manual_clock() -> None:
    _rejects(
        "session.hello",
        _hello_payload(clock={"mode": "wall", "initial_ms": 0}),
    )


def test_config_rejects_bad_initial_ms() -> None:
    _rejects(
        "session.hello",
        _hello_payload(clock={"mode": "manual", "initial_ms": "0"}),
    )


def test_config_rejects_empty_locale() -> None:
    _rejects("session.hello", _hello_payload(locale=""))


def test_config_rejects_empty_timezone() -> None:
    _rejects("session.hello", _hello_payload(timezone=""))


def test_config_rejects_non_object_terminal() -> None:
    _rejects("session.hello", _hello_payload(terminal=1))


def test_config_rejects_bad_terminal_columns() -> None:
    _rejects(
        "session.hello",
        _hello_payload(terminal={"columns": 0, "rows": 24, "capabilities": []}),
    )


def test_config_rejects_bad_terminal_rows() -> None:
    _rejects(
        "session.hello",
        _hello_payload(terminal={"columns": 80, "rows": "24", "capabilities": []}),
    )


def test_config_rejects_bad_capabilities() -> None:
    _rejects(
        "session.hello",
        _hello_payload(terminal={"columns": 80, "rows": 24, "capabilities": [1]}),
    )


def test_config_rejects_non_object_filesystem() -> None:
    _rejects("session.hello", _hello_payload(filesystem=1))


def test_config_rejects_non_sandbox_filesystem() -> None:
    _rejects(
        "session.hello",
        _hello_payload(filesystem={"mode": "host", "root_id": "root"}),
    )


def test_config_rejects_empty_root_id() -> None:
    _rejects(
        "session.hello",
        _hello_payload(filesystem={"mode": "sandbox", "root_id": ""}),
    )


def test_config_rejects_non_object_network() -> None:
    _rejects("session.hello", _hello_payload(network=1))


def test_config_rejects_unknown_network_mode() -> None:
    _rejects("session.hello", _hello_payload(network={"mode": "open"}))


def test_config_rejects_non_list_allow_list() -> None:
    _rejects(
        "session.hello",
        _hello_payload(network={"mode": "allow-list", "allowed": "x"}),
    )


def test_config_rejects_non_object_endpoint() -> None:
    _rejects(
        "session.hello",
        _hello_payload(network={"mode": "allow-list", "allowed": [1]}),
    )


def test_config_rejects_empty_endpoint_host() -> None:
    _rejects(
        "session.hello",
        _hello_payload(
            network={"mode": "allow-list", "allowed": [{"host": "", "port": 1}]}
        ),
    )


def test_config_rejects_bad_endpoint_port() -> None:
    _rejects(
        "session.hello",
        _hello_payload(
            network={
                "mode": "allow-list",
                "allowed": [{"host": "h", "port": 0}],
            }
        ),
    )


def test_config_accepts_allow_list_network() -> None:
    parse_message(
        _wire(
            "session.hello",
            _hello_payload(
                network={
                    "mode": "allow-list",
                    "allowed": [{"host": "h", "port": 443}],
                }
            ),
        )
    )


# --- session.unsupported / session.failed / session.ready -------------------


def test_unsupported_rejects_unknown_constraint() -> None:
    _rejects(
        "session.unsupported",
        {
            "constraint": "bogus",
            "code": "constraint-unsupported",
            "message": "m",
        },
    )


def test_unsupported_rejects_unknown_code() -> None:
    _rejects(
        "session.unsupported",
        {"constraint": "network", "code": "other", "message": "m"},
    )


def test_unsupported_rejects_non_string_message() -> None:
    _rejects(
        "session.unsupported",
        {"constraint": "network", "code": "constraint-unsupported", "message": 1},
    )


def test_unsupported_accepts_optional_details() -> None:
    parse_message(
        _wire(
            "session.unsupported",
            {
                "constraint": "network",
                "code": "constraint-not-enforced",
                "message": "m",
                "details": None,
            },
        )
    )


def test_ready_rejects_non_object_observation() -> None:
    _rejects("session.ready", {"observation": 1})


def test_ready_rejects_exited_process_evidence() -> None:
    _rejects(
        "session.ready",
        {
            "observation": {
                "state": "ready",
                "ui": {"regions": [], "cursor": _cursor()},
                "events": [],
                "process": {
                    "state": "exited",
                    "exit": {"kind": "code", "value": 0},
                },
            }
        },
    )


def test_diagnostic_rejects_empty_code() -> None:
    _rejects("diagnostic", {"code": "", "message": "m"})


def test_diagnostic_rejects_non_string_message() -> None:
    _rejects("diagnostic", {"code": "c", "message": 1})


def test_diagnostic_accepts_optional_details() -> None:
    parse_message(
        _wire("diagnostic", {"code": "c", "message": "m", "details": {"k": 1}})
    )


# --- error shape ------------------------------------------------------------


def test_error_shape_must_be_an_object() -> None:
    _rejects("session.failed", {"error": 1})


def test_error_shape_rejects_reserved_member() -> None:
    _rejects(
        "session.failed",
        {"error": {"code": "c", "message": "m", "bogus": 1}},
    )


def test_error_shape_rejects_empty_code() -> None:
    _rejects("session.failed", {"error": {"code": "", "message": "m"}})


def test_error_shape_rejects_non_string_message() -> None:
    _rejects("session.failed", {"error": {"code": "c", "message": 1}})


def test_error_shape_accepts_x_member_and_details() -> None:
    parse_message(
        _wire(
            "run.failed",
            {"error": {"code": "c", "message": "m", "details": 1, "x-t": 2}},
        )
    )


# --- input kinds ------------------------------------------------------------


def test_input_text_rejects_non_string() -> None:
    _rejects("input.text", {"text": 1})


def test_input_key_rejects_non_list_keys() -> None:
    _rejects("input.key", {"keys": "Enter"})


def test_input_key_rejects_non_string_key() -> None:
    _rejects("input.key", {"keys": [1]})


def test_input_key_rejects_empty_keys() -> None:
    _rejects("input.key", {"keys": []})


def test_input_resize_rejects_bad_columns() -> None:
    _rejects("input.resize", {"columns": 0, "rows": 24})


def test_input_resize_rejects_bad_rows() -> None:
    _rejects("input.resize", {"columns": 80, "rows": "24"})


def test_input_clock_rejects_bad_at_ms() -> None:
    _rejects("input.clock", {"at_ms": -1})


# --- exit record ------------------------------------------------------------


def test_exit_record_must_be_an_object() -> None:
    _rejects("run.finished", {"exit": 1})


def test_exit_record_rejects_reserved_member() -> None:
    _rejects(
        "run.finished",
        {"exit": {"kind": "code", "value": 0, "bogus": 1}},
    )


def test_exit_record_rejects_unknown_kind() -> None:
    _rejects("run.finished", {"exit": {"kind": "other", "value": 0}})


def test_exit_record_rejects_non_int_code_value() -> None:
    _rejects("run.finished", {"exit": {"kind": "code", "value": "0"}})


def test_exit_record_rejects_empty_signal_value() -> None:
    _rejects("run.finished", {"exit": {"kind": "signal", "value": ""}})


def test_exit_record_accepts_signal_with_x_member() -> None:
    parse_message(
        _wire(
            "run.finished",
            {"exit": {"kind": "signal", "value": "SIGTERM", "x-t": 1}},
        )
    )


# --- observation payload ------------------------------------------------------


def _cursor(**overrides: object) -> dict[str, JsonValue]:
    cursor: dict[str, JsonValue] = {"column": 0, "row": 0, "visible": True}
    for key, value in overrides.items():
        cursor[key] = cast(JsonValue, value)
    return cursor


def _ui(**overrides: object) -> dict[str, JsonValue]:
    ui: dict[str, JsonValue] = {"regions": [], "cursor": _cursor()}
    for key, value in overrides.items():
        ui[key] = cast(JsonValue, value)
    return ui


def _observation(**overrides: object) -> dict[str, JsonValue]:
    observation: dict[str, JsonValue] = {
        "state": "idle",
        "ui": _ui(),
        "events": [],
    }
    for key, value in overrides.items():
        observation[key] = cast(JsonValue, value)
    return observation


def test_observation_requires_state() -> None:
    _rejects("observation", {"ui": _ui(), "events": []})


def test_observation_requires_ui() -> None:
    _rejects("observation", {"state": "idle", "events": []})


def test_observation_rejects_non_list_events() -> None:
    _rejects("observation", _observation(events={}))


def test_ui_must_be_an_object() -> None:
    _rejects("observation", _observation(ui=1))


def test_ui_rejects_reserved_member() -> None:
    _rejects("observation", _observation(ui=_ui(bogus=1)))


def test_ui_rejects_non_list_regions() -> None:
    _rejects("observation", _observation(ui=_ui(regions={})))


def test_ui_requires_cursor() -> None:
    _rejects("observation", _observation(ui={"regions": []}))


def test_ui_rejects_non_string_mode() -> None:
    _rejects("observation", _observation(ui=_ui(mode=1)))


def test_ui_accepts_null_mode_focus_and_x_member() -> None:
    parse_message(
        _wire(
            "observation",
            _observation(ui=_ui(mode=None, focus=None, **{"x-t": 1})),
        )
    )


def test_cursor_must_be_an_object() -> None:
    _rejects("observation", _observation(ui=_ui(cursor=1)))


def test_cursor_rejects_reserved_member() -> None:
    _rejects("observation", _observation(ui=_ui(cursor=_cursor(bogus=1))))


def test_cursor_rejects_bad_column() -> None:
    _rejects(
        "observation",
        _observation(ui=_ui(cursor=_cursor(column="0"))),
    )


def test_cursor_rejects_bad_row() -> None:
    _rejects("observation", _observation(ui=_ui(cursor=_cursor(row=-1))))


def test_cursor_rejects_non_bool_visible() -> None:
    _rejects(
        "observation",
        _observation(ui=_ui(cursor=_cursor(visible=1))),
    )


def _region(**overrides: object) -> dict[str, JsonValue]:
    region: dict[str, JsonValue] = {
        "id": "r1",
        "role": "main",
        "column": 0,
        "row": 0,
        "columns": 10,
        "rows": 5,
    }
    for key, value in overrides.items():
        region[key] = cast(JsonValue, value)
    return region


def test_region_must_be_an_object() -> None:
    _rejects("observation", _observation(ui=_ui(regions=[1])))


def test_region_rejects_reserved_member() -> None:
    _rejects(
        "observation",
        _observation(ui=_ui(regions=[_region(bogus=1)])),
    )


def test_region_rejects_empty_id() -> None:
    _rejects("observation", _observation(ui=_ui(regions=[_region(id="")])))


def test_region_rejects_empty_role() -> None:
    _rejects(
        "observation",
        _observation(ui=_ui(regions=[_region(role="")])),
    )


def test_region_rejects_bad_column() -> None:
    _rejects(
        "observation",
        _observation(ui=_ui(regions=[_region(column="0")])),
    )


def test_region_rejects_bad_row() -> None:
    _rejects("observation", _observation(ui=_ui(regions=[_region(row=-1)])))


def test_region_rejects_zero_columns() -> None:
    _rejects(
        "observation",
        _observation(ui=_ui(regions=[_region(columns=0)])),
    )


def test_region_rejects_zero_rows() -> None:
    _rejects("observation", _observation(ui=_ui(regions=[_region(rows=0)])))


def test_region_ids_must_be_unique() -> None:
    _rejects(
        "observation",
        _observation(ui=_ui(regions=[_region(), _region()])),
    )


def test_focus_must_be_non_empty() -> None:
    _rejects("observation", _observation(ui=_ui(focus="")))


def test_focus_must_name_a_region() -> None:
    _rejects("observation", _observation(ui=_ui(focus="ghost")))


def test_focus_may_name_a_region() -> None:
    parse_message(
        _wire(
            "observation",
            _observation(ui=_ui(regions=[_region()], focus="r1")),
        )
    )


def test_event_must_be_an_object() -> None:
    _rejects("observation", _observation(events=[1]))


def test_event_rejects_reserved_member() -> None:
    _rejects(
        "observation",
        _observation(events=[{"type": "t", "data": None, "bogus": 1}]),
    )


def test_event_rejects_empty_type() -> None:
    _rejects("observation", _observation(events=[{"type": "", "data": None}]))


def test_event_requires_data() -> None:
    _rejects("observation", _observation(events=[{"type": "t"}]))


def test_event_accepts_data_and_x_member() -> None:
    parse_message(
        _wire(
            "observation",
            _observation(events=[{"type": "t", "data": 1, "x-t": 2}]),
        )
    )


def _frame(**overrides: object) -> dict[str, JsonValue]:
    frame: dict[str, JsonValue] = {"lines": ["a"], "columns": 1, "rows": 1}
    for key, value in overrides.items():
        frame[key] = cast(JsonValue, value)
    return frame


def test_frame_must_be_an_object() -> None:
    _rejects("observation", _observation(frame=1))


def test_frame_rejects_reserved_member() -> None:
    _rejects("observation", _observation(frame=_frame(bogus=1)))


def test_frame_rejects_non_list_lines() -> None:
    _rejects("observation", _observation(frame=_frame(lines={})))


def test_frame_rejects_non_string_line() -> None:
    _rejects("observation", _observation(frame=_frame(lines=[1])))


def test_frame_rejects_bad_columns() -> None:
    _rejects("observation", _observation(frame=_frame(columns=0)))


def test_frame_rejects_bad_rows() -> None:
    _rejects("observation", _observation(frame=_frame(rows="1")))


def test_frame_rows_must_match_line_count() -> None:
    _rejects("observation", _observation(frame=_frame(rows=2)))


def test_frame_accepts_x_member() -> None:
    parse_message(_wire("observation", _observation(frame=_frame(**{"x-t": 1}))))


def test_process_must_be_an_object() -> None:
    _rejects("observation", _observation(process=1))


def test_process_rejects_reserved_member() -> None:
    _rejects(
        "observation",
        _observation(process={"state": "running", "bogus": 1}),
    )


def test_process_running_cannot_carry_exit() -> None:
    _rejects(
        "observation",
        _observation(
            process={
                "state": "running",
                "exit": {"kind": "code", "value": 0},
            }
        ),
    )


def test_process_exited_requires_exit() -> None:
    _rejects("observation", _observation(process={"state": "exited"}))


def test_process_rejects_unknown_state() -> None:
    _rejects("observation", _observation(process={"state": "zombie"}))


def test_process_accepts_running_and_exited() -> None:
    parse_message(_wire("observation", _observation(process={"state": "running"})))
    parse_message(
        _wire(
            "observation",
            _observation(
                process={
                    "state": "exited",
                    "exit": {"kind": "code", "value": 0},
                }
            ),
        )
    )


# --- input.stop and terminal kinds -------------------------------------------


def test_input_stop_round_trips() -> None:
    parse_message(serialize_message(_envelope("input.stop", {})))


def test_run_failed_rejects_bad_error() -> None:
    _rejects("run.failed", {"error": 1})


def test_run_finished_round_trips() -> None:
    parse_message(
        serialize_message(
            _envelope("run.finished", {"exit": {"kind": "code", "value": 0}})
        )
    )


def test_serialize_accepts_envelope_x_member() -> None:
    message = _envelope("input.stop", {})
    message["x-trace"] = "abc"
    parse_message(serialize_message(message))


def test_serialize_rejects_reserved_envelope_member() -> None:
    message = _envelope("input.stop", {})
    message["extra"] = 1
    with pytest.raises(ControlProtocolError):
        serialize_message(message)


def test_serialize_rejects_wrong_protocol() -> None:
    message = _envelope("input.stop", {})
    message["protocol"] = "termverify.control/v2"
    with pytest.raises(ControlProtocolError):
        serialize_message(message)


def test_serialize_rejects_unknown_kind() -> None:
    message = _envelope("bogus", {})
    with pytest.raises(ControlProtocolError):
        serialize_message(message)


def test_serialize_rejects_missing_payload() -> None:
    message: dict[str, JsonValue] = {
        "protocol": CONTROL_PROTOCOL_V1,
        "kind": "input.stop",
    }
    with pytest.raises(ControlProtocolError):
        serialize_message(message)


def test_serialize_rejects_message_past_the_line_cap() -> None:
    message = _envelope("diagnostic", {"code": "c", "message": "m"})
    message["x-pad"] = "x" * (4 * 1024 * 1024)
    with pytest.raises(ControlProtocolError):
        serialize_message(message)


# --- structural budgets -------------------------------------------------------


def test_budget_rejects_value_count_overflow() -> None:
    with pytest.raises(ControlProtocolError):
        parse_message(_wire("input.stop", {"x-v": [0] * 100_001}))


def test_budget_rejects_single_string_bytes_overflow() -> None:
    with pytest.raises(ControlProtocolError):
        parse_message(_wire("input.stop", {"x-v": "x" * (1024 * 1024 + 1)}))


def test_budget_rejects_aggregate_string_bytes_overflow() -> None:
    pad = "x" * (1024 * 1024 - 10)
    with pytest.raises(ControlProtocolError):
        parse_message(
            _wire(
                "input.stop",
                {
                    "x-a": pad,
                    "x-b": pad,
                    "x-c": "y" * (128 * 1024),
                },
            )
        )


def test_budget_rejects_collection_items_overflow() -> None:
    with pytest.raises(ControlProtocolError):
        parse_message(_wire("input.stop", {"x-v": [0] * 16_385}))


def test_budget_rejects_member_count_overflow() -> None:
    members = {f"x-{index}": 0 for index in range(16_385)}
    with pytest.raises(ControlProtocolError):
        parse_message(_wire("input.stop", members))


def test_budget_rejects_structural_nesting_overflow() -> None:
    nested: JsonValue = 0
    for _ in range(70):
        nested = [nested]
    with pytest.raises(ControlProtocolError):
        parse_message(_wire("input.stop", {"x-v": nested}))


def test_budget_rejects_object_keys_overflow() -> None:
    key = "k" * (1024 * 1024 + 1)
    with pytest.raises(ControlProtocolError):
        parse_message(_wire("input.stop", {key: 0}))


def test_budget_rejects_non_json_value() -> None:
    message = _envelope("input.stop", {})
    message["x-v"] = cast(JsonValue, object())
    with pytest.raises(ControlProtocolError):
        serialize_message(message)


def test_serialize_rejects_collection_items_overflow() -> None:
    message = _envelope("input.stop", {"x-v": cast(JsonValue, [0] * 16_385)})
    with pytest.raises(ControlProtocolError):
        serialize_message(message)


# --- review-driven regression tests (PR #175 adversarial review) ---------------


def test_parse_rejects_non_finite_float_constants() -> None:
    # RFC 8785's number model has no NaN/Infinity; the parser must be at
    # least as strict as the serializer, which rejects them.
    for constant in (b"NaN", b"Infinity", b"-Infinity"):
        with pytest.raises(ControlProtocolError):
            parse_message(
                b'{"protocol":"termverify.control/v1","kind":"input.stop",'
                b'"payload":{},"x-v":' + constant + b"}\n"
            )


def test_serialize_rejects_non_finite_float() -> None:
    message = _envelope("input.stop", {})
    message["x-v"] = cast(JsonValue, float("nan"))
    with pytest.raises(ControlProtocolError):
        serialize_message(message)


def test_ready_rejects_reserved_observation_member() -> None:
    _rejects(
        "session.ready",
        {"observation": _observation(bogus=1)},
    )


def test_ready_accepts_observation_x_member_and_optional_members() -> None:
    parse_message(
        _wire(
            "session.ready",
            {
                "observation": _observation(
                    frame=_frame(),
                    process={"state": "running"},
                    **{"x-trace": 1},
                )
            },
        )
    )


def test_budget_does_not_count_object_keys_as_values() -> None:
    # The spec is verbatim: "object keys are not value nodes". Built as
    # raw JSON text: one 50-deep chain whose innermost object carries
    # 16,384 members — 16,000 small lists of 5 (16,000×7 = 112,000 nodes
    # if keys count; 96,000 value nodes if they do not) plus one 3,900-item
    # list. Value nodes total 99,954, inside the 100,000 budget only when
    # keys are not counted. Every collection stays at or under the
    # 16,384-item ceiling, and the depth is 56 < 64.
    small = "[" + ",".join(["0"] * 5) + "]"
    members = [f'"x-{index}":{small}' for index in range(16_000)]
    members.append('"x-pad":[' + ",".join(["0"] * 3_900) + "]")
    chain = '{"x-0":' * 50 + "{" + ",".join(members) + "}" + "}" * 50
    line = (
        '{"protocol":"termverify.control/v1","kind":"input.stop",'
        '"payload":{"x-v":' + chain + "}}\n"
    )
    parse_message(line.encode())


def test_config_rejects_seed_with_leading_zero() -> None:
    _rejects("session.hello", _hello_payload(seed="042"))


def test_config_rejects_non_ascii_seed() -> None:
    _rejects("session.hello", _hello_payload(seed="\u0664\u0662"))


def test_config_rejects_seed_past_u64() -> None:
    _rejects("session.hello", _hello_payload(seed="18446744073709551616"))


def test_config_accepts_max_u64_seed() -> None:
    parse_message(_wire("session.hello", _hello_payload(seed="18446744073709551615")))


def test_config_rejects_clock_reserved_member() -> None:
    _rejects(
        "session.hello",
        _hello_payload(clock={"mode": "manual", "initial_ms": 0, "bogus": 1}),
    )


def test_config_rejects_terminal_reserved_member() -> None:
    _rejects(
        "session.hello",
        _hello_payload(
            terminal={"columns": 80, "rows": 24, "capabilities": [], "bogus": 1}
        ),
    )


def test_config_rejects_filesystem_reserved_member() -> None:
    _rejects(
        "session.hello",
        _hello_payload(filesystem={"mode": "sandbox", "root_id": "root", "bogus": 1}),
    )


def test_config_rejects_network_reserved_member() -> None:
    _rejects(
        "session.hello",
        _hello_payload(network={"mode": "deny", "allowed": []}),
    )


def test_config_rejects_endpoint_reserved_member() -> None:
    _rejects(
        "session.hello",
        _hello_payload(
            network={
                "mode": "allow-list",
                "allowed": [{"host": "h", "port": 1, "bogus": 1}],
            }
        ),
    )


def test_config_rejects_empty_capability() -> None:
    _rejects(
        "session.hello",
        _hello_payload(terminal={"columns": 80, "rows": 24, "capabilities": [""]}),
    )


def test_config_rejects_unsorted_capabilities() -> None:
    _rejects(
        "session.hello",
        _hello_payload(
            terminal={"columns": 80, "rows": 24, "capabilities": ["b", "a"]}
        ),
    )


def test_config_rejects_duplicate_capabilities() -> None:
    _rejects(
        "session.hello",
        _hello_payload(
            terminal={"columns": 80, "rows": 24, "capabilities": ["a", "a"]}
        ),
    )


def test_config_rejects_malformed_locale() -> None:
    _rejects("session.hello", _hello_payload(locale="!!!"))


def test_config_rejects_unknown_timezone() -> None:
    _rejects("session.hello", _hello_payload(timezone="Not/AZone"))


def test_config_rejects_port_above_65535() -> None:
    _rejects(
        "session.hello",
        _hello_payload(
            network={
                "mode": "allow-list",
                "allowed": [{"host": "h", "port": 70000}],
            }
        ),
    )


def test_config_rejects_unsorted_allow_list() -> None:
    _rejects(
        "session.hello",
        _hello_payload(
            network={
                "mode": "allow-list",
                "allowed": [{"host": "b", "port": 1}, {"host": "a", "port": 1}],
            }
        ),
    )


def test_config_rejects_duplicate_allow_list_entry() -> None:
    _rejects(
        "session.hello",
        _hello_payload(
            network={
                "mode": "allow-list",
                "allowed": [{"host": "a", "port": 1}, {"host": "a", "port": 1}],
            }
        ),
    )
