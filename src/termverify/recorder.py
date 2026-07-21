"""Assemble adapter result values into `termverify.transcript/v1` records.

The recorder is a pure consumer of the frozen v1 protocol: it emits only
records the protocol already defines, and its output is valid only because
the strict codec in :mod:`termverify.transcript` accepts it. The recorder's
own lifecycle checks surface an adapter-integration bug at its cause; they
are a usability layer, never a second validation path.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, cast

from termverify._json import JsonValue
from termverify._protocol_v1 import CONSTRAINT_NAMES
from termverify.adapter import (
    Adapter,
    ClockAdvance,
    Diagnostic,
    DispatchInput,
    EnforcementReceipt,
    EpochCompleted,
    EpochResult,
    ExitStatus,
    FrozenJsonValue,
    JsonInput,
    KeyInput,
    Observation,
    Resize,
    RunConfiguration,
    RunFailed,
    RunFinished,
    Started,
    StartFailed,
    StartResult,
    StartTerminated,
    StartUnsupported,
    Stop,
    TerminalResult,
    TextInput,
    _validate_run_id,
    freeze_json,
)
from termverify.transcript import (
    Record,
    TranscriptValidationError,
    _validate_replay_subject,
    serialize_transcript,
)

__all__ = [
    "ScriptedInput",
    "ScriptedRun",
    "TranscriptRecorder",
    "TranscriptRecorderError",
    "run_scripted",
]

type ScriptedInput = DispatchInput | ClockAdvance | Stop

_PROTOCOL = "termverify.transcript/v1"
_State = Literal["created", "idle", "terminal"]


class TranscriptRecorderError(ValueError):
    """A structured recorder contract or lifecycle violation at record time."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _thaw(value: FrozenJsonValue) -> JsonValue:
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    return value


def _exit_payload(exit_status: ExitStatus) -> dict[str, JsonValue]:
    return {"kind": exit_status.kind, "value": exit_status.value}


def _observation_payload(observation: Observation) -> dict[str, JsonValue]:
    payload: dict[str, JsonValue] = {
        "at_ms": int(observation.at_ms),
        "state": _thaw(observation.state),
        "events": [
            {"type": event.type, "data": _thaw(event.data)}
            for event in observation.events
        ],
        "ui": {
            "regions": [
                {
                    "id": region.id,
                    "role": region.role,
                    "bounds": {
                        "column": region.column,
                        "row": region.row,
                        "columns": region.columns,
                        "rows": region.rows,
                    },
                }
                for region in observation.ui.regions
            ],
            "focus": observation.ui.focus,
            "cursor": {
                "column": observation.ui.cursor.column,
                "row": observation.ui.cursor.row,
                "visible": observation.ui.cursor.visible,
            },
            "mode": observation.ui.mode,
        },
    }
    if observation.frame is not None:
        payload["frame"] = {
            "lines": list(observation.frame.lines),
            "columns": observation.frame.columns,
            "rows": observation.frame.rows,
        }
    if observation.process is not None:
        process: dict[str, JsonValue] = {"state": observation.process.state}
        if observation.process.exit is not None:
            process["exit"] = _exit_payload(observation.process.exit)
        payload["process"] = process
    return payload


def _diagnostic_payload(diagnostic: Diagnostic) -> dict[str, JsonValue]:
    payload: dict[str, JsonValue] = {
        "at_ms": int(diagnostic.at_ms),
        "code": diagnostic.code,
        "message": diagnostic.message,
    }
    if diagnostic.details is not None:
        payload["details"] = _thaw(diagnostic.details)
    return payload


def _capability_payload(
    constraint: str, receipt: EnforcementReceipt
) -> dict[str, JsonValue]:
    effective: JsonValue
    if constraint == "seed":
        effective = str(receipt.effective)
    elif constraint == "clock":
        effective = {
            "mode": "manual",
            "initial_ms": receipt.effective.initial_ms,  # type: ignore[union-attr]
        }
    elif constraint in ("locale", "timezone"):
        effective = cast(str, receipt.effective)
    elif constraint == "terminal":
        terminal = receipt.effective
        effective = {
            "columns": terminal.columns,  # type: ignore[union-attr]
            "rows": terminal.rows,  # type: ignore[union-attr]
            "capabilities": list(terminal.capabilities),  # type: ignore[union-attr]
        }
    elif constraint == "filesystem":
        effective = {
            "mode": "sandbox",
            "root_id": receipt.effective.root_id,  # type: ignore[union-attr]
        }
    else:
        network = receipt.effective
        effective = {"mode": network.mode}  # type: ignore[union-attr]
    payload: dict[str, JsonValue] = {
        "constraint": constraint,
        "status": "enforced",
        "effective": effective,
        "tier": receipt.tier,
    }
    if receipt.delivery is not None:
        delivery: dict[str, JsonValue] = {"channel": receipt.delivery.channel}
        if receipt.delivery.channel == "spawn-env":
            delivery["env"] = dict(receipt.delivery.env)
            if receipt.delivery.cwd is not None:
                delivery["cwd"] = receipt.delivery.cwd
        payload["delivery"] = delivery
    return payload


class TranscriptRecorder:
    """Record one adapter run as `termverify.transcript/v1` records.

    Contributions arrive as the immutable adapter result values in occurrence
    order: exactly one :meth:`record_start`, then, for a started run, one
    :meth:`record_epoch` per dispatched input until a terminal result. An
    out-of-order or mistimed contribution is an immediate
    :class:`TranscriptRecorderError`, and a rejected contribution appends
    nothing. :meth:`transcript` returns the finished run through the strict
    serializer — the codec remains the only acceptance gate, and a codec
    rule the recorder does not mirror (for example the canonical-encoding
    string rules) still surfaces there as a
    :class:`~termverify.transcript.TranscriptValidationError`.
    """

    def __init__(
        self,
        run_id: str,
        configuration: RunConfiguration,
        subject: Mapping[str, JsonInput],
    ) -> None:
        if type(configuration) is not RunConfiguration:
            raise TranscriptRecorderError(
                "invalid-configuration",
                "configuration must be a RunConfiguration",
            )
        if not isinstance(subject, Mapping):
            raise TranscriptRecorderError(
                "invalid-subject", "subject must be a JSON object"
            )
        try:
            _validate_run_id(run_id)
        except (TypeError, ValueError) as error:
            raise TranscriptRecorderError("invalid-run-id", str(error)) from error
        try:
            subject_payload = cast(dict[str, JsonValue], _thaw(freeze_json(subject)))
            _validate_replay_subject(subject_payload)
        except (TranscriptValidationError, TypeError, ValueError) as error:
            raise TranscriptRecorderError("invalid-subject", str(error)) from error
        self._run_id = run_id
        self._configuration = configuration
        self._manual_time = configuration.clock.initial_ms
        self._state: _State = "created"
        self._records: list[Record] = []
        self._append(
            "run.started",
            {
                "config": configuration.to_protocol(),
                "subject": subject_payload,
            },
        )

    def _append(self, kind: str, payload: dict[str, JsonValue]) -> None:
        sequence = len(self._records)
        self._records.append(
            {
                "protocol": _PROTOCOL,
                "run_id": self._run_id,
                "seq": sequence,
                "id": f"record-{sequence:04d}",
                "kind": kind,
                "payload": payload,
            }
        )

    def _require_state(self, expected: _State, action: str) -> None:
        if self._state == expected:
            return
        raise TranscriptRecorderError(
            f"recorder-not-{expected}",
            f"{action} requires the {expected} recorder state, not {self._state}",
        )

    def _append_capability_results(
        self, receipts: tuple[EnforcementReceipt, ...]
    ) -> None:
        for constraint, receipt in zip(CONSTRAINT_NAMES, receipts, strict=False):
            self._append("capability.result", _capability_payload(constraint, receipt))

    def _append_diagnostics(self, diagnostics: tuple[Diagnostic, ...]) -> None:
        for diagnostic in diagnostics:
            self._append("diagnostic", _diagnostic_payload(diagnostic))

    def _append_terminal_outcome(self, outcome: RunFinished | RunFailed) -> None:
        if isinstance(outcome, RunFinished):
            self._append("run.finished", {"exit": _exit_payload(outcome.exit)})
            return
        error: dict[str, JsonValue] = {
            "code": outcome.failure.code,
            "message": outcome.failure.message,
        }
        if outcome.failure.details is not None:
            error["details"] = _thaw(outcome.failure.details)
        self._append("run.failed", {"error": error})

    def _append_terminal_result(self, result: TerminalResult) -> None:
        self._append_diagnostics(result.diagnostics)
        if result.observation is not None:
            self._append("observation", _observation_payload(result.observation))
        self._append_terminal_outcome(result.outcome)
        self._state = "terminal"

    def _require_run_binding(self, run_id: str, requested: RunConfiguration) -> None:
        if run_id != self._run_id or requested != self._configuration:
            raise TranscriptRecorderError(
                "result-run-mismatch",
                "start result does not belong to this recorder's run",
            )

    def record_start(self, result: StartResult) -> None:
        """Record the outcome of the adapter's `start` call."""
        self._require_state("created", "record_start")
        if type(result) is Started:
            constraints = result.constraints
            self._require_run_binding(constraints.run_id, constraints.requested)
            self._append_capability_results(
                (
                    constraints.seed,
                    constraints.clock,
                    constraints.locale,
                    constraints.timezone,
                    constraints.terminal,
                    constraints.filesystem,
                    constraints.network,
                )
            )
            self._append_diagnostics(result.diagnostics)
            self._append("observation", _observation_payload(result.observation))
            self._state = "idle"
            return
        if type(result) is StartTerminated:
            constraints = result.constraints
            self._require_run_binding(constraints.run_id, constraints.requested)
            self._append_capability_results(
                (
                    constraints.seed,
                    constraints.clock,
                    constraints.locale,
                    constraints.timezone,
                    constraints.terminal,
                    constraints.filesystem,
                    constraints.network,
                )
            )
            self._append_terminal_result(result.result)
            return
        if type(result) is StartUnsupported:
            self._require_run_binding(result.run_id, result.requested)
            self._append_capability_results(result.enforced)
            self._append(
                "capability.result",
                {
                    "constraint": result.constraint,
                    "status": "unsupported",
                    "reason": result.message,
                },
            )
            payload: dict[str, JsonValue] = {
                "constraint": result.constraint,
                "code": result.code,
                "message": result.message,
            }
            if result.details is not None:
                payload["details"] = _thaw(result.details)
            self._append("run.unsupported", payload)
            self._state = "terminal"
            return
        if type(result) is StartFailed:
            self._require_run_binding(result.run_id, result.requested)
            self._append_capability_results(result.enforced)
            self._append_diagnostics(result.diagnostics)
            error: dict[str, JsonValue] = {
                "code": result.failure.code,
                "message": result.failure.message,
            }
            if result.failure.details is not None:
                error["details"] = _thaw(result.failure.details)
            self._append("run.failed", {"error": error})
            self._state = "terminal"
            return
        raise TranscriptRecorderError(
            "invalid-start-result", "record_start requires a StartResult value"
        )

    def record_epoch(self, input_event: ScriptedInput, result: EpochResult) -> None:
        """Record one dispatched input together with its epoch result."""
        self._require_state("idle", "record_epoch")
        input_type = type(input_event)
        if input_type not in (KeyInput, TextInput, Resize, ClockAdvance, Stop):
            raise TranscriptRecorderError(
                "invalid-input", "record_epoch requires an adapter input value"
            )
        if type(result) not in (EpochCompleted, TerminalResult):
            raise TranscriptRecorderError(
                "invalid-epoch-result",
                "record_epoch requires an EpochCompleted or TerminalResult",
            )
        if input_type is ClockAdvance:
            advance = cast(ClockAdvance, input_event)
            if advance.at_ms != self._manual_time + advance.delta_ms:
                raise TranscriptRecorderError(
                    "manual-clock-mismatch",
                    "clock advance does not move the current manual time",
                )
        elif input_event.at_ms != self._manual_time:
            raise TranscriptRecorderError(
                "manual-clock-mismatch",
                "input does not use the current manual time",
            )
        if input_type is Stop and type(result) is EpochCompleted:
            raise TranscriptRecorderError(
                "stop-result-mismatch",
                "a stop input requires a terminal result",
            )
        epoch_time = int(input_event.at_ms)
        if type(result) is EpochCompleted:
            evidence_times = [int(result.observation.at_ms)]
        else:
            terminal = cast(TerminalResult, result)
            evidence_times = [
                int(diagnostic.at_ms) for diagnostic in terminal.diagnostics
            ]
            if terminal.observation is not None:
                evidence_times.append(int(terminal.observation.at_ms))
        if any(evidence_time != epoch_time for evidence_time in evidence_times):
            raise TranscriptRecorderError(
                "evidence-time-mismatch",
                "epoch evidence does not use the input's manual time",
            )
        if input_type is KeyInput:
            key = cast(KeyInput, input_event)
            self._append(
                "input.key",
                {"at_ms": int(key.at_ms), "keys": list(key.keys)},
            )
        elif input_type is TextInput:
            text = cast(TextInput, input_event)
            self._append("input.text", {"at_ms": int(text.at_ms), "text": text.text})
        elif input_type is Resize:
            resize = cast(Resize, input_event)
            self._append(
                "input.resize",
                {
                    "at_ms": int(resize.at_ms),
                    "columns": resize.columns,
                    "rows": resize.rows,
                },
            )
        elif input_type is ClockAdvance:
            advance = cast(ClockAdvance, input_event)
            self._append(
                "input.clock_advanced",
                {"at_ms": int(advance.at_ms), "delta_ms": advance.delta_ms},
            )
            self._manual_time = int(advance.at_ms)
        else:
            self._append("input.stop", {"at_ms": int(input_event.at_ms)})
        if type(result) is EpochCompleted:
            self._append_diagnostics(result.diagnostics)
            self._append("observation", _observation_payload(result.observation))
            return
        self._append_terminal_result(cast(TerminalResult, result))

    def transcript(self) -> bytes:
        """Serialize the finished run through the strict codec."""
        self._require_state("terminal", "transcript")
        return serialize_transcript([dict(record) for record in self._records])


@dataclass(frozen=True, slots=True)
class ScriptedRun:
    """The validated transcript and terminal outcome of one scripted run."""

    transcript: bytes
    result: StartTerminated | StartUnsupported | StartFailed | TerminalResult


def run_scripted(
    adapter: Adapter,
    run_id: str,
    configuration: RunConfiguration,
    subject: Mapping[str, JsonInput],
    inputs: tuple[ScriptedInput, ...],
) -> ScriptedRun:
    """Drive one adapter through a scripted input sequence, recording as it goes.

    The orchestrator adds no scheduling, retry, timeout, or multi-subject
    semantics: it starts the adapter, dispatches the scripted inputs in
    order, and returns the validated transcript bytes with the terminal
    outcome once the run ends by scripted stop or natural termination.
    Inputs remaining after a natural termination are never dispatched. A
    script that ends with the run still open is a structured error: the
    orchestrator fabricates no stop on the caller's behalf. An exception
    raised by the adapter itself (a caller contract breach such as
    dispatching from a non-idle state) propagates unchanged and discards
    the partial recording — structured outcomes, including runtime
    failures, are returned as recorded results instead.
    """
    if type(inputs) is not tuple or any(
        type(item) not in (KeyInput, TextInput, Resize, ClockAdvance, Stop)
        for item in inputs
    ):
        raise TranscriptRecorderError(
            "invalid-script", "inputs must be a tuple of adapter input values"
        )
    recorder = TranscriptRecorder(run_id, configuration, subject)
    start = adapter.start(run_id, configuration)
    recorder.record_start(start)
    if type(start) is not Started:
        return ScriptedRun(
            recorder.transcript(),
            cast(StartTerminated | StartUnsupported | StartFailed, start),
        )
    for input_event in inputs:
        if type(input_event) is ClockAdvance:
            result: EpochResult = adapter.advance_clock(input_event)
        elif type(input_event) is Stop:
            result = adapter.stop(input_event)
        else:
            result = adapter.dispatch(cast(DispatchInput, input_event))
        recorder.record_epoch(input_event, result)
        if type(result) is TerminalResult:
            return ScriptedRun(recorder.transcript(), result)
    raise TranscriptRecorderError(
        "script-not-terminated",
        "the scripted input sequence ended while the run was still open",
    )
