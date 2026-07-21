"""Adapter-contract tests for `termverify.jsonl` against a scripted fake child."""

from __future__ import annotations

import json
import threading
from collections.abc import Mapping, Sequence

import pytest

from termverify.adapter import (
    Adapter,
    ClockAdvance,
    ClockConfiguration,
    EpochCompleted,
    FilesystemConfiguration,
    KeyInput,
    ManualTime,
    NetworkConfiguration,
    Resize,
    RunConfiguration,
    RunFinished,
    Started,
    StartFailed,
    StartTerminated,
    Stop,
    TerminalConfiguration,
    TextInput,
)
from termverify.cooperation import CooperationConstraintPorts
from termverify.jsonl import (
    JsonlAdapter,
    JsonlBindingPort,
    JsonlChildPort,
    JsonlEndOfStreamError,
)

_RUN_ID = "01hgw0mg5e6w1a6b0rzg3zqk0r"


class FakeChild:
    """A scriptable JsonlChildPort: scripted inbound lines, recorded outbound."""

    def __init__(self, inbound: list[bytes] | None = None) -> None:
        self._inbound: list[bytes] = list(inbound or [])
        self.outbound: list[bytes] = []
        self.closed: tuple[bool, ...] = ()
        self.exit_status: int | None = 0
        self._lock = threading.Lock()

    def feed(self, line: bytes) -> None:
        with self._lock:
            self._inbound.append(line)

    def write_line(self, line: bytes) -> None:
        self.outbound.append(line)

    def read_line(self) -> bytes:
        with self._lock:
            if not self._inbound:
                raise JsonlEndOfStreamError
            return self._inbound.pop(0)

    def close(self, *, force: bool) -> None:
        self.closed = self.closed + (force,)


class FakeBinding:
    def __init__(self, child: FakeChild | None = None) -> None:
        self.child = child if child is not None else FakeChild()
        self.spawn_calls: list[
            tuple[tuple[str, ...], Mapping[str, str] | None, str | None]
        ] = []

    def spawn(
        self,
        argv: Sequence[str],
        *,
        env_overlay: Mapping[str, str] | None = None,
        cwd: str | None = None,
    ) -> JsonlChildPort:
        self.spawn_calls.append((tuple(argv), env_overlay, cwd))
        return self.child


def _config(**overrides: object) -> RunConfiguration:
    base: dict[str, object] = {
        "seed": 42,
        "clock": ClockConfiguration(initial_ms=0),
        "locale": "en-US",
        "timezone": "UTC",
        "terminal": TerminalConfiguration(columns=80, rows=24, capabilities=()),
        "filesystem": FilesystemConfiguration(root_id="root"),
        "network": NetworkConfiguration(mode="deny"),
    }
    base.update(overrides)
    return RunConfiguration(**base)  # type: ignore[arg-type]


def _hello_reply(run_id: str = _RUN_ID) -> bytes:
    return (
        json.dumps(
            {
                "protocol": "termverify.control/v1",
                "kind": "session.ready",
                "payload": {
                    "observation": {
                        "state": "ready",
                        "ui": {
                            "regions": [],
                            "cursor": {"column": 0, "row": 0, "visible": True},
                        },
                        "events": [],
                    }
                },
            }
        ).encode()
        + b"\n"
    )


def _adapter(
    child: FakeChild | None = None,
    argv: Sequence[str] = ("subject",),
) -> tuple[JsonlAdapter, FakeChild, FakeBinding]:
    bound_child = child if child is not None else FakeChild([_hello_reply()])
    binding = FakeBinding(bound_child)
    adapter = JsonlAdapter(
        tuple(argv),
        binding=binding,
        constraint_ports=CooperationConstraintPorts(filesystem_roots={"root": "."}),
        abort_deadline_ms=60_000,
    )
    return adapter, bound_child, binding


def test_adapter_satisfies_the_adapter_protocol() -> None:
    adapter, _, _ = _adapter()
    checked: Adapter = adapter
    assert checked is adapter


def test_binding_satisfies_the_binding_port() -> None:
    binding: JsonlBindingPort = FakeBinding()
    assert isinstance(binding, JsonlBindingPort)


def test_fake_child_satisfies_the_child_port() -> None:
    child: JsonlChildPort = FakeChild()
    assert isinstance(child, JsonlChildPort)


def test_start_rejects_invalid_run_id() -> None:
    adapter, _, _ = _adapter()
    with pytest.raises((TypeError, ValueError)):
        adapter.start("UPPER CASE", _config())


def test_start_spawns_child_and_sends_hello() -> None:
    child = FakeChild([_hello_reply()])
    adapter, _, binding = _adapter(child)
    result = adapter.start(_RUN_ID, _config())
    assert isinstance(result, Started)
    assert len(binding.spawn_calls) == 1
    argv, env_overlay, cwd = binding.spawn_calls[0]
    assert argv == ("subject",)
    assert env_overlay == {
        "TERMVERIFY_SEED": "42",
        "TERMVERIFY_CLOCK_INITIAL_MS": "0",
        "TERMVERIFY_LOCALE": "en-US",
        "TZ": "UTC0",
        "TERMVERIFY_TIMEZONE": "UTC",
        "TERMVERIFY_FS_ROOT": cwd,
        "TERMVERIFY_NETWORK": "deny",
    }
    assert cwd is not None
    assert child.outbound, "expected a session.hello line"
    hello = json.loads(child.outbound[0])
    assert hello["kind"] == "session.hello"
    assert hello["payload"]["run_id"] == _RUN_ID
    assert hello["payload"]["at_ms"] == 0


def test_start_terminal_receipt_records_hello_config_delivery() -> None:
    adapter, _, _ = _adapter(FakeChild([_hello_reply()]))
    result = adapter.start(_RUN_ID, _config())
    assert isinstance(result, Started)
    terminal = result.constraints.terminal
    assert terminal.tier == "delivered"
    assert terminal.delivery is not None
    assert terminal.delivery.channel == "hello-config"
    assert dict(terminal.delivery.env) == {}
    assert terminal.delivery.cwd is None


def test_start_maps_session_unsupported_to_start_failed() -> None:
    reply = (
        json.dumps(
            {
                "protocol": "termverify.control/v1",
                "kind": "session.unsupported",
                "payload": {
                    "constraint": "network",
                    "code": "no-network",
                    "message": "the subject cannot deny the network",
                    "details": None,
                },
            }
        ).encode()
        + b"\n"
    )
    adapter, child, _ = _adapter(FakeChild([reply]))
    result = adapter.start(_RUN_ID, _config())
    assert isinstance(result, StartFailed)
    assert result.failure.code == "adapter-start-failed"
    assert child.closed, "child should be closed after refusal"


def test_start_maps_session_failed_to_start_failed() -> None:
    reply = (
        json.dumps(
            {
                "protocol": "termverify.control/v1",
                "kind": "session.failed",
                "payload": {
                    "error": {
                        "code": "boom",
                        "message": "init exploded",
                        "details": None,
                    }
                },
            }
        ).encode()
        + b"\n"
    )
    adapter, _, _ = _adapter(FakeChild([reply]))
    result = adapter.start(_RUN_ID, _config())
    assert isinstance(result, StartFailed)


def test_start_maps_eof_to_start_terminated() -> None:
    adapter, _, _ = _adapter(FakeChild([]))
    result = adapter.start(_RUN_ID, _config())
    assert isinstance(result, StartTerminated)


def test_start_maps_malformed_reply_to_start_failed() -> None:
    adapter, _, _ = _adapter(FakeChild([b"not json\n"]))
    result = adapter.start(_RUN_ID, _config())
    assert isinstance(result, StartFailed)


def test_dispatch_text_sends_input_text() -> None:
    ready = _hello_reply()
    observation = (
        json.dumps(
            {
                "protocol": "termverify.control/v1",
                "kind": "observation",
                "payload": {
                    "state": "idle",
                    "ui": {
                        "regions": [],
                        "cursor": {"column": 0, "row": 0, "visible": True},
                    },
                    "events": [],
                },
            }
        ).encode()
        + b"\n"
    )
    child = FakeChild([ready, observation])
    adapter, _, _ = _adapter(child)
    started = adapter.start(_RUN_ID, _config())
    assert isinstance(started, Started)
    epoch = adapter.dispatch(TextInput(at_ms=ManualTime(0), text="hello"))
    assert isinstance(epoch, EpochCompleted)
    kinds = [json.loads(line)["kind"] for line in child.outbound]
    assert "input.text" in kinds


def test_dispatch_key_sends_input_key() -> None:
    ready = _hello_reply()
    observation = (
        json.dumps(
            {
                "protocol": "termverify.control/v1",
                "kind": "observation",
                "payload": {
                    "state": "idle",
                    "ui": {
                        "regions": [],
                        "cursor": {"column": 0, "row": 0, "visible": True},
                    },
                    "events": [],
                },
            }
        ).encode()
        + b"\n"
    )
    child = FakeChild([ready, observation])
    adapter, _, _ = _adapter(child)
    adapter.start(_RUN_ID, _config())
    epoch = adapter.dispatch(KeyInput(at_ms=ManualTime(0), keys=("Enter",)))
    assert isinstance(epoch, EpochCompleted)
    kinds = [json.loads(line)["kind"] for line in child.outbound]
    assert "input.key" in kinds


def test_dispatch_resize_sends_input_resize() -> None:
    ready = _hello_reply()
    observation = (
        json.dumps(
            {
                "protocol": "termverify.control/v1",
                "kind": "observation",
                "payload": {
                    "state": "idle",
                    "ui": {
                        "regions": [],
                        "cursor": {"column": 0, "row": 0, "visible": True},
                    },
                    "events": [],
                },
            }
        ).encode()
        + b"\n"
    )
    child = FakeChild([ready, observation])
    adapter, _, _ = _adapter(child)
    adapter.start(_RUN_ID, _config())
    epoch = adapter.dispatch(Resize(at_ms=ManualTime(0), columns=120, rows=40))
    assert isinstance(epoch, EpochCompleted)
    kinds = [json.loads(line)["kind"] for line in child.outbound]
    assert "input.resize" in kinds


def test_advance_clock_sends_input_clock() -> None:
    ready = _hello_reply()
    observation = (
        json.dumps(
            {
                "protocol": "termverify.control/v1",
                "kind": "observation",
                "payload": {
                    "state": "idle",
                    "ui": {
                        "regions": [],
                        "cursor": {"column": 0, "row": 0, "visible": True},
                    },
                    "events": [],
                },
            }
        ).encode()
        + b"\n"
    )
    child = FakeChild([ready, observation])
    adapter, _, _ = _adapter(child)
    adapter.start(_RUN_ID, _config())
    epoch = adapter.advance_clock(ClockAdvance(at_ms=ManualTime(100), delta_ms=100))
    assert isinstance(epoch, EpochCompleted)
    kinds = [json.loads(line)["kind"] for line in child.outbound]
    assert "input.clock" in kinds


def test_stop_drains_to_terminal() -> None:
    ready = _hello_reply()
    finished = (
        json.dumps(
            {
                "protocol": "termverify.control/v1",
                "kind": "run.finished",
                "payload": {
                    "exit": {"kind": "code", "value": 0},
                },
            }
        ).encode()
        + b"\n"
    )
    child = FakeChild([ready, finished])
    adapter, _, _ = _adapter(child)
    adapter.start(_RUN_ID, _config())
    result = adapter.stop(Stop(at_ms=ManualTime(0)))
    assert isinstance(result.outcome, RunFinished)
    assert child.closed, "stop should close the child"
    kinds = [json.loads(line)["kind"] for line in child.outbound]
    assert "input.stop" in kinds
