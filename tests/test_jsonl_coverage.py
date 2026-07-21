"""Failure-path tests for `termverify.jsonl` against scripted fake children.

The happy-path contract tests live in `tests/test_jsonl_adapter.py`; this
module walks the failure taxonomy — negotiation refusals, spawn-overlay
invariants, lifecycle violations, deadline aborts, and drain/teardown
shapes — with a controllable watchdog.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from typing import cast

import pytest

from termverify.adapter import (
    AdapterFailure,
    ClockAdvance,
    ClockConfiguration,
    ClockReceipt,
    DeliveryRecord,
    EpochCompleted,
    EpochResult,
    FilesystemConfiguration,
    FrozenJsonValue,
    ManualTime,
    NetworkConfiguration,
    RunConfiguration,
    RunFailed,
    RunFinished,
    SeedReceipt,
    Started,
    StartFailed,
    StartTerminated,
    Stop,
    TerminalConfiguration,
    TerminalResult,
    TextInput,
)
from termverify.cooperation import CooperationConstraintPorts
from termverify.jsonl import (
    JsonlAdapter,
    JsonlChildClosedError,
    JsonlChildPort,
    JsonlEndOfStreamError,
    JsonlWatchdogPort,
    _assemble_spawn_overlay,
    _DeliveryInvariantError,
)

_RUN_ID = "01hgw0mg5e6w1a6b0rzg3zqk0r"


def _details(
    failure: AdapterFailure,
) -> Mapping[str, FrozenJsonValue]:
    """Narrow a failure's details to the mapping every failure here builds."""
    details = failure.details
    assert isinstance(details, Mapping)
    return details


def _terminal(result: EpochResult) -> TerminalResult:
    """Narrow an epoch result to its terminal variant."""
    assert isinstance(result, TerminalResult)
    return result


def _failed(result: EpochResult) -> RunFailed:
    """Narrow an epoch result to a failed terminal outcome."""
    outcome = _terminal(result).outcome
    assert isinstance(outcome, RunFailed)
    return outcome


def _finished(result: EpochResult) -> RunFinished:
    """Narrow an epoch result to a finished terminal outcome."""
    outcome = _terminal(result).outcome
    assert isinstance(outcome, RunFinished)
    return outcome


class FakeChild:
    """A scriptable JsonlChildPort with configurable read/close failures."""

    def __init__(
        self,
        inbound: list[bytes] | None = None,
        *,
        read_error: Exception | None = None,
        close_error: bool = False,
        write_error: bool = False,
        exit_status: int | None = 0,
    ) -> None:
        self._inbound: list[bytes] = list(inbound or [])
        self.outbound: list[bytes] = []
        self.closed: tuple[bool, ...] = ()
        self.exit_status: int | None = exit_status
        self._read_error = read_error
        self._close_error = close_error
        self._write_error = write_error

    def write_line(self, line: bytes) -> None:
        if self._write_error:
            raise OSError("pipe closed")
        self.outbound.append(line)

    def read_line(self) -> bytes:
        if self._read_error is not None:
            raise self._read_error
        if not self._inbound:
            raise JsonlEndOfStreamError
        return self._inbound.pop(0)

    def close(self, *, force: bool) -> None:
        self.closed = self.closed + (force,)
        if self._close_error:
            raise OSError("close failed")


class FakeBinding:
    def __init__(self, child: FakeChild | None = None) -> None:
        self.child = child if child is not None else FakeChild()
        self.spawn_calls: list[
            tuple[tuple[str, ...], Mapping[str, str] | None, str | None]
        ] = []
        self.raise_on_spawn = False

    def spawn(
        self,
        argv: Sequence[str],
        *,
        env_overlay: Mapping[str, str] | None = None,
        cwd: str | None = None,
    ) -> JsonlChildPort:
        self.spawn_calls.append((tuple(argv), env_overlay, cwd))
        if self.raise_on_spawn:
            raise OSError("spawn failed")
        return self.child


class ExplodingWatchdog:
    def arm(self, delay_ms: int, expire: Callable[[], None]) -> Callable[[], None]:
        def disarm() -> None:
            return None

        return disarm


class FiringWatchdog:
    """A watchdog whose expire callback fires immediately on arm."""

    def arm(self, delay_ms: int, expire: Callable[[], None]) -> Callable[[], None]:
        def disarm() -> None:
            return None

        # Fire immediately; the child read below will raise.
        expire()
        return disarm


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
    watchdog: JsonlWatchdogPort | None = None,
) -> tuple[JsonlAdapter, FakeChild, FakeBinding]:
    bound_child = child if child is not None else FakeChild([_hello_reply()])
    binding = FakeBinding(bound_child)
    kwargs: dict[str, object] = {
        "binding": binding,
        "constraint_ports": CooperationConstraintPorts(filesystem_roots={"root": "."}),
        "abort_deadline_ms": 60_000,
    }
    if watchdog is not None:
        kwargs["watchdog"] = watchdog
    adapter = JsonlAdapter(tuple(argv), **kwargs)  # type: ignore[arg-type]
    return adapter, bound_child, binding


# --- construction -------------------------------------------------------------


def test_argv_must_be_a_sequence_of_strings() -> None:
    with pytest.raises(TypeError):
        JsonlAdapter(
            cast(Sequence[str], "subject"),
            binding=FakeBinding(),
            constraint_ports=CooperationConstraintPorts(),
            abort_deadline_ms=60_000,
        )


def test_argv_must_contain_only_strings() -> None:
    with pytest.raises(TypeError):
        JsonlAdapter(
            (cast(str, 1),),
            binding=FakeBinding(),
            constraint_ports=CooperationConstraintPorts(),
            abort_deadline_ms=60_000,
        )


def test_argv_must_name_a_subject_command() -> None:
    with pytest.raises(ValueError):
        JsonlAdapter(
            (),
            binding=FakeBinding(),
            constraint_ports=CooperationConstraintPorts(),
            abort_deadline_ms=60_000,
        )


def test_argv_must_contain_non_empty_strings() -> None:
    with pytest.raises(ValueError):
        JsonlAdapter(
            ("",),
            binding=FakeBinding(),
            constraint_ports=CooperationConstraintPorts(),
            abort_deadline_ms=60_000,
        )


def test_abort_deadline_must_be_an_integer() -> None:
    with pytest.raises(TypeError):
        JsonlAdapter(
            ("subject",),
            binding=FakeBinding(),
            constraint_ports=CooperationConstraintPorts(),
            abort_deadline_ms=cast(int, "60"),
        )


def test_abort_deadline_must_be_positive() -> None:
    with pytest.raises(ValueError):
        JsonlAdapter(
            ("subject",),
            binding=FakeBinding(),
            constraint_ports=CooperationConstraintPorts(),
            abort_deadline_ms=0,
        )


def test_constraint_ports_is_required() -> None:
    with pytest.raises(TypeError):
        JsonlAdapter(
            ("subject",),
            binding=FakeBinding(),
            constraint_ports=None,  # type: ignore[arg-type]
            abort_deadline_ms=60_000,
        )


# --- spawn-overlay invariants ---------------------------------------------------


def test_overlay_rejects_case_folded_duplicate_env() -> None:
    first = DeliveryRecord(env={"Path": "a"})
    second = DeliveryRecord(env={"PATH": "b"})
    with pytest.raises(_DeliveryInvariantError):
        _assemble_spawn_overlay((first, second))


def test_overlay_rejects_multiple_working_directories() -> None:
    first = DeliveryRecord(env={"A": "1"}, cwd="x")
    second = DeliveryRecord(env={"B": "2"}, cwd="y")
    with pytest.raises(_DeliveryInvariantError):
        _assemble_spawn_overlay((first, second))


def test_overlay_returns_none_for_empty_env() -> None:
    assert _assemble_spawn_overlay(()) == (None, None)


# --- start() negotiation refusals ---------------------------------------------


def test_start_rejects_terminal_capabilities() -> None:
    adapter, _, _ = _adapter()
    config = _config(
        terminal=TerminalConfiguration(columns=80, rows=24, capabilities=("cursor",))
    )
    result = adapter.start(_RUN_ID, config)
    assert isinstance(result, StartFailed)
    assert result.failure.code == "adapter-start-failed"
    assert _details(result.failure)["constraint"] == "terminal"


def test_start_rejects_spawn_overlay_invariant_breach() -> None:
    class OverlayBreachPorts(CooperationConstraintPorts):
        def enforce_seed(self, run_id: str, seed: int) -> SeedReceipt:
            return SeedReceipt(
                run_id,
                seed,
                "delivered",
                DeliveryRecord(env={"Path": "a"}),
            )

        def enforce_clock(self, run_id: str, clock: ClockConfiguration) -> ClockReceipt:
            return ClockReceipt(
                run_id,
                clock,
                "delivered",
                DeliveryRecord(env={"PATH": "b"}),
            )

    adapter = JsonlAdapter(
        ("subject",),
        binding=FakeBinding(),
        constraint_ports=OverlayBreachPorts(filesystem_roots={"root": "."}),
        abort_deadline_ms=60_000,
    )
    result = adapter.start(_RUN_ID, _config())
    assert isinstance(result, StartFailed)
    assert "invariant" in _details(result.failure)


def test_start_rejects_spawn_failure() -> None:
    child = FakeChild([_hello_reply()])
    adapter, _, binding = _adapter(child)
    binding.raise_on_spawn = True
    result = adapter.start(_RUN_ID, _config())
    assert isinstance(result, StartFailed)
    assert _details(result.failure)["during"] == "spawn"


def test_start_rejects_hello_write_failure() -> None:
    child = FakeChild([_hello_reply()], write_error=True)
    adapter, _, _ = _adapter(child)
    result = adapter.start(_RUN_ID, _config())
    assert isinstance(result, StartFailed)
    assert _details(result.failure)["during"] == "write"


def test_start_rejects_child_closed_during_handshake() -> None:
    child = FakeChild([_hello_reply()])
    child._read_error = JsonlChildClosedError("closed")
    adapter, _, _ = _adapter(child)
    result = adapter.start(_RUN_ID, _config())
    assert isinstance(result, StartFailed)
    assert _details(result.failure)["during"] == "read"


def test_start_maps_handshake_eof_to_start_terminated() -> None:
    child = FakeChild([_hello_reply()])
    child._read_error = JsonlEndOfStreamError()
    adapter, _, _ = _adapter(child)
    result = adapter.start(_RUN_ID, _config())
    assert isinstance(result, StartTerminated)


def test_start_rejects_read_failure_during_handshake() -> None:
    child = FakeChild([_hello_reply()], read_error=OSError("boom"))
    adapter, _, _ = _adapter(child)
    result = adapter.start(_RUN_ID, _config())
    assert isinstance(result, StartFailed)
    assert _details(result.failure)["during"] == "read"


def test_start_rejects_deadline_abort_during_handshake() -> None:
    child = FakeChild([_hello_reply()])
    child._read_error = JsonlEndOfStreamError()
    adapter, _, _ = _adapter(child, watchdog=FiringWatchdog())
    result = adapter.start(_RUN_ID, _config())
    # End-of-stream is classified before the deadline check: the child
    # vanished, so the honest shape is StartTerminated even though the
    # abort deadline also fired.
    assert isinstance(result, StartTerminated)


def test_start_rejects_malformed_handshake_reply() -> None:
    child = FakeChild([b"not json\n"])
    adapter, _, _ = _adapter(child)
    result = adapter.start(_RUN_ID, _config())
    assert isinstance(result, StartFailed)
    assert _details(result.failure)["during"] == "parse"


def test_start_rejects_non_handshake_reply_kind() -> None:
    reply = (
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
    child = FakeChild([reply])
    adapter, _, _ = _adapter(child)
    result = adapter.start(_RUN_ID, _config())
    assert isinstance(result, StartFailed)
    assert _details(result.failure)["kind"] == "observation"


def test_start_rejects_excessive_startup_diagnostics() -> None:
    diagnostics = [
        json.dumps(
            {
                "protocol": "termverify.control/v1",
                "kind": "diagnostic",
                "payload": {"code": "c", "message": "m"},
            }
        ).encode()
        + b"\n"
    ] * 101
    diagnostics.append(_hello_reply())
    child = FakeChild(diagnostics)
    adapter, _, _ = _adapter(child)
    result = adapter.start(_RUN_ID, _config())
    assert isinstance(result, StartFailed)
    assert "budget" in result.failure.message


def test_start_accepts_session_ready_with_diagnostics() -> None:
    diagnostics = [
        json.dumps(
            {
                "protocol": "termverify.control/v1",
                "kind": "diagnostic",
                "payload": {"code": "c", "message": "m"},
            }
        ).encode()
        + b"\n"
    ]
    diagnostics.append(_hello_reply())
    child = FakeChild(diagnostics)
    adapter, _, _ = _adapter(child)
    result = adapter.start(_RUN_ID, _config())
    assert isinstance(result, Started)
    assert len(result.diagnostics) == 1


# --- dispatch() failure paths ---------------------------------------------------


def _started_adapter() -> tuple[JsonlAdapter, FakeChild, FakeBinding]:
    child = FakeChild([_hello_reply()])
    adapter, child, binding = _adapter(child)
    result = adapter.start(_RUN_ID, _config())
    assert isinstance(result, Started)
    return adapter, child, binding


def test_dispatch_rejects_non_dispatch_input() -> None:
    adapter, _, _ = _started_adapter()
    with pytest.raises(TypeError):
        adapter.dispatch(cast(TextInput, "hello"))


def test_dispatch_rejects_non_idle_state() -> None:
    adapter, _, _ = _started_adapter()
    adapter._set_state("active")
    with pytest.raises(RuntimeError):
        adapter.dispatch(TextInput(at_ms=ManualTime(0), text="x"))


def test_dispatch_rejects_stale_manual_time() -> None:
    adapter, _, _ = _started_adapter()
    with pytest.raises(ValueError):
        adapter.dispatch(TextInput(at_ms=ManualTime(1), text="x"))


def test_dispatch_rejects_write_failure() -> None:
    adapter, child, _ = _started_adapter()
    child._write_error = True
    result = adapter.dispatch(TextInput(at_ms=ManualTime(0), text="x"))
    assert isinstance(_terminal(result).outcome, RunFailed)
    assert _details(_failed(result).failure)["during"] == "write"


def test_dispatch_rejects_child_closed_during_epoch() -> None:
    adapter, child, _ = _started_adapter()
    child._read_error = JsonlChildClosedError("closed")
    result = adapter.dispatch(TextInput(at_ms=ManualTime(0), text="x"))
    assert isinstance(_terminal(result).outcome, RunFailed)
    assert _details(_failed(result).failure)["during"] == "read"


def test_dispatch_rejects_read_failure_during_epoch() -> None:
    adapter, child, _ = _started_adapter()
    child._read_error = OSError("boom")
    result = adapter.dispatch(TextInput(at_ms=ManualTime(0), text="x"))
    assert isinstance(_terminal(result).outcome, RunFailed)
    assert _details(_failed(result).failure)["during"] == "read"


def test_dispatch_rejects_deadline_abort_during_epoch() -> None:
    child = FakeChild([_hello_reply()])
    adapter = JsonlAdapter(
        ("subject",),
        binding=FakeBinding(child),
        constraint_ports=CooperationConstraintPorts(filesystem_roots={"root": "."}),
        abort_deadline_ms=60_000,
        watchdog=FiringWatchdog(),
    )
    child._read_error = JsonlEndOfStreamError()
    adapter.start(_RUN_ID, _config())
    # After start, the child is now closed by the watchdog; the adapter is
    # terminal, so dispatch must fail fast.
    with pytest.raises(RuntimeError):
        adapter.dispatch(TextInput(at_ms=ManualTime(0), text="x"))


def test_dispatch_rejects_excessive_epoch_diagnostics() -> None:
    diagnostics = [
        json.dumps(
            {
                "protocol": "termverify.control/v1",
                "kind": "diagnostic",
                "payload": {"code": "c", "message": "m"},
            }
        ).encode()
        + b"\n"
    ] * 101
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
    diagnostics.append(observation)
    child = FakeChild([_hello_reply()] + diagnostics)
    adapter, _, _ = _adapter(child)
    adapter.start(_RUN_ID, _config())
    result = adapter.dispatch(TextInput(at_ms=ManualTime(0), text="x"))
    assert isinstance(_terminal(result).outcome, RunFailed)
    assert "budget" in _failed(result).failure.message


def test_dispatch_rejects_exited_process_evidence() -> None:
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
                    "process": {
                        "state": "exited",
                        "exit": {"kind": "code", "value": 0},
                    },
                },
            }
        ).encode()
        + b"\n"
    )
    child = FakeChild([_hello_reply(), observation])
    adapter, _, _ = _adapter(child)
    adapter.start(_RUN_ID, _config())
    result = adapter.dispatch(TextInput(at_ms=ManualTime(0), text="x"))
    assert isinstance(_terminal(result).outcome, RunFailed)
    assert "exited" in _failed(result).failure.message


def test_dispatch_rejects_invalid_lifecycle_kind() -> None:
    reply = (
        json.dumps(
            {
                "protocol": "termverify.control/v1",
                "kind": "session.unsupported",
                "payload": {
                    "constraint": "network",
                    "code": "constraint-unsupported",
                    "message": "m",
                },
            }
        ).encode()
        + b"\n"
    )
    child = FakeChild([_hello_reply(), reply])
    adapter, _, _ = _adapter(child)
    adapter.start(_RUN_ID, _config())
    result = adapter.dispatch(TextInput(at_ms=ManualTime(0), text="x"))
    assert isinstance(_terminal(result).outcome, RunFailed)
    assert "lifecycle" in _failed(result).failure.message


def test_dispatch_rejects_run_finished_without_os_exit() -> None:
    finished = (
        json.dumps(
            {
                "protocol": "termverify.control/v1",
                "kind": "run.finished",
                "payload": {"exit": {"kind": "code", "value": 0}},
            }
        ).encode()
        + b"\n"
    )
    child = FakeChild([_hello_reply(), finished], exit_status=None)
    adapter, _, _ = _adapter(child)
    adapter.start(_RUN_ID, _config())
    result = adapter.dispatch(TextInput(at_ms=ManualTime(0), text="x"))
    assert isinstance(_terminal(result).outcome, RunFailed)
    assert _details(_failed(result).failure)["missing"] == "exit-record"


def test_dispatch_rejects_close_failure_after_run_finished() -> None:
    finished = (
        json.dumps(
            {
                "protocol": "termverify.control/v1",
                "kind": "run.finished",
                "payload": {"exit": {"kind": "code", "value": 0}},
            }
        ).encode()
        + b"\n"
    )
    child = FakeChild([_hello_reply(), finished], close_error=True)
    adapter, _, _ = _adapter(child)
    adapter.start(_RUN_ID, _config())
    result = adapter.dispatch(TextInput(at_ms=ManualTime(0), text="x"))
    assert isinstance(_terminal(result).outcome, RunFailed)
    assert _details(_failed(result).failure)["during"] == "close"


def test_dispatch_rejects_close_failure_after_run_failed() -> None:
    failed = (
        json.dumps(
            {
                "protocol": "termverify.control/v1",
                "kind": "run.failed",
                "payload": {"error": {"code": "c", "message": "m"}},
            }
        ).encode()
        + b"\n"
    )
    child = FakeChild([_hello_reply(), failed], close_error=True)
    adapter, _, _ = _adapter(child)
    adapter.start(_RUN_ID, _config())
    result = adapter.dispatch(TextInput(at_ms=ManualTime(0), text="x"))
    assert isinstance(_terminal(result).outcome, RunFailed)
    assert _details(_failed(result).failure)["during"] == "close"


def test_dispatch_reports_run_failed_with_subject_error() -> None:
    failed = (
        json.dumps(
            {
                "protocol": "termverify.control/v1",
                "kind": "run.failed",
                "payload": {
                    "error": {
                        "code": "boom",
                        "message": "subject exploded",
                        "details": {"k": 1},
                    }
                },
            }
        ).encode()
        + b"\n"
    )
    child = FakeChild([_hello_reply(), failed])
    adapter, _, _ = _adapter(child)
    adapter.start(_RUN_ID, _config())
    result = adapter.dispatch(TextInput(at_ms=ManualTime(0), text="x"))
    assert isinstance(_terminal(result).outcome, RunFailed)
    assert "subject exploded" in _failed(result).failure.message
    assert _details(_failed(result).failure)["subject-code"] == "boom"


def test_dispatch_reports_exit_record_mismatch() -> None:
    finished = (
        json.dumps(
            {
                "protocol": "termverify.control/v1",
                "kind": "run.finished",
                "payload": {"exit": {"kind": "code", "value": 1}},
            }
        ).encode()
        + b"\n"
    )
    child = FakeChild([_hello_reply(), finished], exit_status=0)
    adapter, _, _ = _adapter(child)
    adapter.start(_RUN_ID, _config())
    result = adapter.dispatch(TextInput(at_ms=ManualTime(0), text="x"))
    assert isinstance(_terminal(result).outcome, RunFinished)
    assert any(
        diagnostic.code == "exit-record-mismatch" for diagnostic in result.diagnostics
    )


def test_dispatch_finish_from_eos_without_exit_record() -> None:
    child = FakeChild([_hello_reply()], exit_status=None)
    adapter, _, _ = _adapter(child)
    adapter.start(_RUN_ID, _config())
    result = adapter.dispatch(TextInput(at_ms=ManualTime(0), text="x"))
    assert isinstance(_terminal(result).outcome, RunFailed)
    assert _details(_failed(result).failure)["missing"] == "exit-record"


def test_dispatch_finish_from_eos_with_close_failure() -> None:
    child = FakeChild([_hello_reply()], close_error=True)
    adapter, _, _ = _adapter(child)
    adapter.start(_RUN_ID, _config())
    result = adapter.dispatch(TextInput(at_ms=ManualTime(0), text="x"))
    assert isinstance(_terminal(result).outcome, RunFailed)
    assert _details(_failed(result).failure)["during"] == "close"


def test_dispatch_accepts_run_finished_with_matching_exit() -> None:
    finished = (
        json.dumps(
            {
                "protocol": "termverify.control/v1",
                "kind": "run.finished",
                "payload": {"exit": {"kind": "code", "value": 0}},
            }
        ).encode()
        + b"\n"
    )
    child = FakeChild([_hello_reply(), finished], exit_status=0)
    adapter, _, _ = _adapter(child)
    adapter.start(_RUN_ID, _config())
    result = adapter.dispatch(TextInput(at_ms=ManualTime(0), text="x"))
    assert isinstance(_terminal(result).outcome, RunFinished)
    assert _finished(result).exit.kind == "code"
    assert _finished(result).exit.value == 0


# --- advance_clock() failure paths -----------------------------------------------


def test_advance_clock_rejects_non_clock_input() -> None:
    adapter, _, _ = _started_adapter()
    with pytest.raises(TypeError):
        adapter.advance_clock(cast(ClockAdvance, "100"))


def test_advance_clock_rejects_non_idle_state() -> None:
    adapter, _, _ = _started_adapter()
    adapter._set_state("active")
    with pytest.raises(RuntimeError):
        adapter.advance_clock(ClockAdvance(at_ms=ManualTime(100), delta_ms=100))


def test_advance_clock_rejects_wrong_delta() -> None:
    adapter, _, _ = _started_adapter()
    with pytest.raises(ValueError):
        adapter.advance_clock(ClockAdvance(at_ms=ManualTime(100), delta_ms=50))


def test_advance_clock_rejects_write_failure() -> None:
    adapter, child, _ = _started_adapter()
    child._write_error = True
    result = adapter.advance_clock(ClockAdvance(at_ms=ManualTime(100), delta_ms=100))
    assert isinstance(_terminal(result).outcome, RunFailed)
    assert _details(_failed(result).failure)["during"] == "write"


def test_advance_clock_accepts_observation() -> None:
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
    child = FakeChild([_hello_reply(), observation])
    adapter, _, _ = _adapter(child)
    adapter.start(_RUN_ID, _config())
    result = adapter.advance_clock(ClockAdvance(at_ms=ManualTime(100), delta_ms=100))
    assert isinstance(result, EpochCompleted)


# --- stop() failure paths ---------------------------------------------------


def test_stop_rejects_non_stop_input() -> None:
    adapter, _, _ = _started_adapter()
    with pytest.raises(TypeError):
        adapter.stop(cast(Stop, "stop"))


def test_stop_rejects_non_idle_state() -> None:
    adapter, _, _ = _started_adapter()
    adapter._set_state("active")
    with pytest.raises(RuntimeError):
        adapter.stop(Stop(at_ms=ManualTime(0)))


def test_stop_rejects_stale_manual_time() -> None:
    adapter, _, _ = _started_adapter()
    with pytest.raises(ValueError):
        adapter.stop(Stop(at_ms=ManualTime(1)))


def test_stop_rejects_write_failure() -> None:
    adapter, child, _ = _started_adapter()
    child._write_error = True
    result = adapter.stop(Stop(at_ms=ManualTime(0)))
    assert isinstance(_terminal(result).outcome, RunFailed)
    assert _details(_failed(result).failure)["during"] == "write"


def test_stop_rejects_excessive_drain_diagnostics() -> None:
    diagnostics = [
        json.dumps(
            {
                "protocol": "termverify.control/v1",
                "kind": "diagnostic",
                "payload": {"code": "c", "message": "m"},
            }
        ).encode()
        + b"\n"
    ] * 101
    finished = (
        json.dumps(
            {
                "protocol": "termverify.control/v1",
                "kind": "run.finished",
                "payload": {"exit": {"kind": "code", "value": 0}},
            }
        ).encode()
        + b"\n"
    )
    diagnostics.append(finished)
    child = FakeChild([_hello_reply()] + diagnostics)
    adapter, _, _ = _adapter(child)
    adapter.start(_RUN_ID, _config())
    result = adapter.stop(Stop(at_ms=ManualTime(0)))
    assert isinstance(_terminal(result).outcome, RunFailed)
    assert "budget" in _failed(result).failure.message


def test_stop_rejects_multiple_drain_observations() -> None:
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
    finished = (
        json.dumps(
            {
                "protocol": "termverify.control/v1",
                "kind": "run.finished",
                "payload": {"exit": {"kind": "code", "value": 0}},
            }
        ).encode()
        + b"\n"
    )
    child = FakeChild([_hello_reply(), observation, observation, finished])
    adapter, _, _ = _adapter(child)
    adapter.start(_RUN_ID, _config())
    result = adapter.stop(Stop(at_ms=ManualTime(0)))
    assert isinstance(_terminal(result).outcome, RunFailed)
    assert "more than one observation" in _failed(result).failure.message


def test_stop_rejects_exited_process_evidence_in_drain() -> None:
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
                    "process": {
                        "state": "exited",
                        "exit": {"kind": "code", "value": 0},
                    },
                },
            }
        ).encode()
        + b"\n"
    )
    finished = (
        json.dumps(
            {
                "protocol": "termverify.control/v1",
                "kind": "run.finished",
                "payload": {"exit": {"kind": "code", "value": 0}},
            }
        ).encode()
        + b"\n"
    )
    child = FakeChild([_hello_reply(), observation, finished])
    adapter, _, _ = _adapter(child)
    adapter.start(_RUN_ID, _config())
    result = adapter.stop(Stop(at_ms=ManualTime(0)))
    assert isinstance(_terminal(result).outcome, RunFailed)
    assert "exited" in _failed(result).failure.message


def test_stop_rejects_invalid_drain_kind() -> None:
    reply = (
        json.dumps(
            {
                "protocol": "termverify.control/v1",
                "kind": "session.unsupported",
                "payload": {
                    "constraint": "network",
                    "code": "constraint-unsupported",
                    "message": "m",
                },
            }
        ).encode()
        + b"\n"
    )
    child = FakeChild([_hello_reply(), reply])
    adapter, _, _ = _adapter(child)
    adapter.start(_RUN_ID, _config())
    result = adapter.stop(Stop(at_ms=ManualTime(0)))
    assert isinstance(_terminal(result).outcome, RunFailed)
    assert "stop drain" in _failed(result).failure.message


def test_stop_rejects_deadline_abort_during_drain() -> None:
    child = FakeChild([_hello_reply()])
    adapter = JsonlAdapter(
        ("subject",),
        binding=FakeBinding(child),
        constraint_ports=CooperationConstraintPorts(filesystem_roots={"root": "."}),
        abort_deadline_ms=60_000,
        watchdog=FiringWatchdog(),
    )
    adapter.start(_RUN_ID, _config())
    with pytest.raises(RuntimeError):
        adapter.stop(Stop(at_ms=ManualTime(0)))


def test_stop_finish_from_eos_with_close_failure() -> None:
    child = FakeChild([_hello_reply()], close_error=True)
    adapter, _, _ = _adapter(child)
    adapter.start(_RUN_ID, _config())
    result = adapter.stop(Stop(at_ms=ManualTime(0)))
    assert isinstance(_terminal(result).outcome, RunFailed)
    assert _details(_failed(result).failure)["during"] == "close"


def test_stop_accepts_run_finished_after_drain_observation() -> None:
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
    finished = (
        json.dumps(
            {
                "protocol": "termverify.control/v1",
                "kind": "run.finished",
                "payload": {"exit": {"kind": "code", "value": 0}},
            }
        ).encode()
        + b"\n"
    )
    child = FakeChild([_hello_reply(), observation, finished], exit_status=0)
    adapter, _, _ = _adapter(child)
    adapter.start(_RUN_ID, _config())
    result = adapter.stop(Stop(at_ms=ManualTime(0)))
    assert isinstance(_terminal(result).outcome, RunFinished)
    assert _finished(result).exit.kind == "code"
    assert _finished(result).exit.value == 0
