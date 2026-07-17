"""Synchronous execution for deterministic in-process application ports."""

from __future__ import annotations

from collections.abc import Callable
from threading import Lock
from typing import Literal, NamedTuple, Protocol, cast

from termverify._protocol_v1 import CONSTRAINT_NAMES
from termverify.adapter import (
    AdapterFailure,
    ClockAdvance,
    ClockReceipt,
    ConstraintName,
    ConstraintPorts,
    ConstraintUnsupported,
    DispatchInput,
    EnforcedConstraints,
    EnforcementReceipt,
    EpochCompleted,
    EpochResult,
    FilesystemReceipt,
    KeyInput,
    LocaleReceipt,
    ManualTime,
    NetworkReceipt,
    Resize,
    RunConfiguration,
    RunFailed,
    RunFinished,
    SeedReceipt,
    Started,
    StartFailed,
    StartResult,
    StartTerminated,
    StartUnsupported,
    Stop,
    TerminalReceipt,
    TerminalResult,
    TextInput,
    TimezoneReceipt,
    _validate_run_id,
)

__all__ = ["DirectAdapter", "DirectApplication"]

_State = Literal[
    "created",
    "negotiating",
    "initializing",
    "idle",
    "active",
    "stopping",
    "terminal",
]


class _ResultFailureMessages(NamedTuple):
    invalid_epoch: str
    invalid_terminal_outcome: str
    invalid_terminal_evidence: str
    unexpected: str


_EPOCH_RESULT_MESSAGES = _ResultFailureMessages(
    invalid_epoch="application returned invalid epoch evidence",
    invalid_terminal_outcome="application returned invalid terminal outcome",
    invalid_terminal_evidence="application returned invalid terminal evidence",
    unexpected="application did not report quiescence or termination",
)
_STOP_RESULT_MESSAGES = _ResultFailureMessages(
    invalid_epoch="application did not report termination",
    invalid_terminal_outcome="application returned invalid terminal outcome",
    invalid_terminal_evidence="application returned invalid terminal evidence",
    unexpected="application did not report termination",
)


class DirectApplication(
    ConstraintPorts, Protocol
):  # pragma: no cover - structural declaration
    """One bound constraint-enforcement and deterministic execution port."""

    def initialize(self) -> EpochCompleted | TerminalResult | AdapterFailure: ...

    def dispatch(
        self, input_event: DispatchInput
    ) -> EpochCompleted | TerminalResult | AdapterFailure: ...

    def advance_clock(
        self, input_event: ClockAdvance
    ) -> EpochCompleted | TerminalResult | AdapterFailure: ...

    def stop(self, input_event: Stop) -> TerminalResult | AdapterFailure: ...

    def abort(self, input_event: Stop) -> None: ...


def _start_failure(
    run_id: str,
    configuration: RunConfiguration,
    enforced: tuple[EnforcementReceipt, ...],
    constraint: ConstraintName,
) -> StartFailed:
    return StartFailed(
        run_id=run_id,
        requested=configuration,
        enforced=enforced,
        failure=AdapterFailure(
            "adapter-start-failed",
            "constraint enforcement failed",
            {"constraint": constraint},
        ),
    )


def _negotiate_constraint(
    operation: Callable[[], object],
    expected_type: type[EnforcementReceipt],
    expected_value: object,
    constraint: ConstraintName,
    run_id: str,
    configuration: RunConfiguration,
    enforced: tuple[EnforcementReceipt, ...],
) -> EnforcementReceipt | StartUnsupported | StartFailed:
    try:
        value = operation()
    except Exception:
        return _start_failure(run_id, configuration, enforced, constraint)

    if type(value) is expected_type:
        receipt = value
        if receipt.run_id == run_id and receipt.effective == expected_value:
            return receipt
        return _start_failure(run_id, configuration, enforced, constraint)
    if type(value) is ConstraintUnsupported:
        if value.constraint != constraint:
            return _start_failure(run_id, configuration, enforced, constraint)
        return StartUnsupported(
            run_id=run_id,
            requested=configuration,
            enforced=enforced,
            constraint=value.constraint,
            code=value.code,
            message=value.message,
            details=value.details,
        )
    if type(value) is AdapterFailure and value.code == "adapter-start-failed":
        return StartFailed(
            run_id=run_id,
            requested=configuration,
            enforced=enforced,
            failure=value,
        )
    return _start_failure(run_id, configuration, enforced, constraint)


def _terminal_time_is_valid(result: TerminalResult, at_ms: ManualTime) -> bool:
    return (result.observation is None or result.observation.at_ms == at_ms) and all(
        diagnostic.at_ms == at_ms for diagnostic in result.diagnostics
    )


def _with_abort_failure(failure: AdapterFailure) -> AdapterFailure:
    """Preserve opaque application details under a collision-safe namespace."""
    return AdapterFailure(
        failure.code,
        failure.message,
        {"application": failure.details, "abort": "failed"},
    )


class DirectAdapter:
    """Drive one deterministic application through synchronous single-flight epochs."""

    def __init__(self, application: DirectApplication) -> None:
        self._constraints = application
        self._application = application
        self._state: _State = "created"
        self._manual_time: ManualTime | None = None
        self._state_lock = Lock()

    def _set_state(self, state: _State) -> None:
        with self._state_lock:
            self._state = state

    def _set_time_and_state(self, at_ms: ManualTime, state: _State) -> None:
        with self._state_lock:
            self._manual_time = at_ms
            self._state = state

    def _abort_application(self, at_ms: ManualTime) -> bool:
        try:
            abort = cast(Callable[[Stop], object], self._application.abort)
            result = abort(Stop(at_ms))
        except Exception:
            return False
        return result is None

    def _abort_start(
        self, failure: AdapterFailure, at_ms: ManualTime
    ) -> AdapterFailure:
        if self._abort_application(at_ms):
            return failure
        return _with_abort_failure(failure)

    def _abort_runtime(
        self,
        message: str,
        at_ms: ManualTime,
        failure: AdapterFailure | None = None,
    ) -> TerminalResult:
        if failure is None:
            failure = AdapterFailure("adapter-runtime-failed", message)
        if not self._abort_application(at_ms):
            failure = _with_abort_failure(failure)
        self._set_time_and_state(at_ms, "terminal")
        return TerminalResult(None, RunFailed(failure))

    def _classify_runtime_result(
        self,
        result: object,
        at_ms: ManualTime,
        *,
        allow_epoch: bool,
        messages: _ResultFailureMessages,
    ) -> EpochResult:
        if type(result) is EpochCompleted:
            if not allow_epoch:
                return self._abort_runtime(messages.unexpected, at_ms)
            if result.observation.at_ms != at_ms or any(
                diagnostic.at_ms != at_ms for diagnostic in result.diagnostics
            ):
                return self._abort_runtime(messages.invalid_epoch, at_ms)
            self._set_time_and_state(at_ms, "idle")
            return result
        if type(result) is TerminalResult:
            if type(result.outcome) is not RunFinished:
                return self._abort_runtime(messages.invalid_terminal_outcome, at_ms)
            if not _terminal_time_is_valid(result, at_ms):
                return self._abort_runtime(messages.invalid_terminal_evidence, at_ms)
            self._set_time_and_state(at_ms, "terminal")
            return result
        if type(result) is AdapterFailure and result.code == "adapter-runtime-failed":
            return self._abort_runtime(result.message, at_ms, result)
        return self._abort_runtime(messages.unexpected, at_ms)

    def start(self, run_id: str, configuration: RunConfiguration) -> StartResult:
        if type(configuration) is not RunConfiguration:
            raise TypeError("configuration must be RunConfiguration")
        _validate_run_id(run_id)
        with self._state_lock:
            if self._state != "created":
                raise RuntimeError("direct adapter has already started")
            self._state = "negotiating"
        operations = (
            lambda: self._constraints.enforce_seed(run_id, configuration.seed),
            lambda: self._constraints.enforce_clock(run_id, configuration.clock),
            lambda: self._constraints.enforce_locale(run_id, configuration.locale),
            lambda: self._constraints.enforce_timezone(run_id, configuration.timezone),
            lambda: self._constraints.enforce_terminal(run_id, configuration.terminal),
            lambda: self._constraints.enforce_filesystem(
                run_id, configuration.filesystem
            ),
            lambda: self._constraints.enforce_network(run_id, configuration.network),
        )
        receipt_types: tuple[type[EnforcementReceipt], ...] = (
            SeedReceipt,
            ClockReceipt,
            LocaleReceipt,
            TimezoneReceipt,
            TerminalReceipt,
            FilesystemReceipt,
            NetworkReceipt,
        )
        expected_values = (
            configuration.seed,
            configuration.clock,
            configuration.locale,
            configuration.timezone,
            configuration.terminal,
            configuration.filesystem,
            configuration.network,
        )
        steps: tuple[
            tuple[
                ConstraintName,
                Callable[[], object],
                type[EnforcementReceipt],
                object,
            ],
            ...,
        ] = tuple(
            zip(
                CONSTRAINT_NAMES,
                operations,
                receipt_types,
                expected_values,
                strict=True,
            )
        )
        receipts: list[EnforcementReceipt] = []
        for constraint, operation, receipt_type, expected_value in steps:
            result = _negotiate_constraint(
                operation,
                receipt_type,
                expected_value,
                constraint,
                run_id,
                configuration,
                tuple(receipts),
            )
            if isinstance(result, (StartUnsupported, StartFailed)):
                self._set_state("terminal")
                return result
            receipts.append(result)

        self._set_state("initializing")
        constraints = EnforcedConstraints(
            run_id=run_id,
            requested=configuration,
            seed=cast(SeedReceipt, receipts[0]),
            clock=cast(ClockReceipt, receipts[1]),
            locale=cast(LocaleReceipt, receipts[2]),
            timezone=cast(TimezoneReceipt, receipts[3]),
            terminal=cast(TerminalReceipt, receipts[4]),
            filesystem=cast(FilesystemReceipt, receipts[5]),
            network=cast(NetworkReceipt, receipts[6]),
        )
        initial_ms = ManualTime(configuration.clock.initial_ms)
        try:
            initialized = self._application.initialize()
        except Exception:
            failure = self._abort_start(
                AdapterFailure(
                    "adapter-start-failed", "application initialization failed"
                ),
                initial_ms,
            )
            self._set_state("terminal")
            return StartFailed(
                run_id=run_id,
                requested=configuration,
                enforced=tuple(receipts),
                failure=failure,
            )
        if type(initialized) is TerminalResult:
            if type(initialized.outcome) is RunFinished and _terminal_time_is_valid(
                initialized, initial_ms
            ):
                self._set_state("terminal")
                return StartTerminated(constraints=constraints, result=initialized)
            failure = self._abort_start(
                AdapterFailure(
                    "adapter-start-failed",
                    "application returned invalid initial terminal evidence",
                ),
                initial_ms,
            )
            self._set_state("terminal")
            return StartFailed(
                run_id,
                configuration,
                tuple(receipts),
                failure,
            )
        if type(initialized) is AdapterFailure:
            failure = initialized
            if failure.code != "adapter-start-failed":
                failure = AdapterFailure(
                    "adapter-start-failed", "application initialization failed"
                )
            failure = self._abort_start(failure, initial_ms)
            self._set_state("terminal")
            return StartFailed(run_id, configuration, tuple(receipts), failure)
        if type(initialized) is not EpochCompleted or (
            initialized.observation.at_ms != configuration.clock.initial_ms
            or any(
                diagnostic.at_ms != configuration.clock.initial_ms
                for diagnostic in initialized.diagnostics
            )
        ):
            failure = self._abort_start(
                AdapterFailure(
                    "adapter-start-failed",
                    "application returned invalid initial evidence",
                ),
                initial_ms,
            )
            self._set_state("terminal")
            return StartFailed(
                run_id,
                configuration,
                tuple(receipts),
                failure,
            )
        try:
            started = Started(
                constraints=constraints,
                observation=initialized.observation,
                diagnostics=initialized.diagnostics,
            )
        except Exception:
            failure = self._abort_start(
                AdapterFailure(
                    "adapter-start-failed",
                    "application returned invalid initial evidence",
                ),
                initial_ms,
            )
            self._set_state("terminal")
            return StartFailed(
                run_id,
                configuration,
                tuple(receipts),
                failure,
            )
        self._set_time_and_state(started.observation.at_ms, "idle")
        return started

    def dispatch(self, input_event: DispatchInput) -> EpochResult:
        if type(input_event) not in (KeyInput, TextInput, Resize):
            raise TypeError("dispatch input must be KeyInput, TextInput, or Resize")
        with self._state_lock:
            if self._state != "idle":
                raise RuntimeError("direct adapter is not idle")
            if input_event.at_ms != self._manual_time:
                raise ValueError("input must use the current manual time")
            self._state = "active"
        try:
            result = self._application.dispatch(input_event)
        except Exception:
            return self._abort_runtime("application dispatch failed", input_event.at_ms)
        return self._classify_runtime_result(
            result,
            input_event.at_ms,
            allow_epoch=True,
            messages=_EPOCH_RESULT_MESSAGES,
        )

    def advance_clock(self, input_event: ClockAdvance) -> EpochResult:
        if type(input_event) is not ClockAdvance:
            raise TypeError("clock input must be ClockAdvance")
        with self._state_lock:
            if self._state != "idle":
                raise RuntimeError("direct adapter is not idle")
            if (
                self._manual_time is None
                or input_event.at_ms != self._manual_time + input_event.delta_ms
            ):
                raise ValueError("clock advance must move the current manual time")
            self._state = "active"
        try:
            result = self._application.advance_clock(input_event)
        except Exception:
            return self._abort_runtime(
                "application clock advance failed", input_event.at_ms
            )
        return self._classify_runtime_result(
            result,
            input_event.at_ms,
            allow_epoch=True,
            messages=_EPOCH_RESULT_MESSAGES,
        )

    def stop(self, input_event: Stop) -> TerminalResult:
        if type(input_event) is not Stop:
            raise TypeError("stop input must be Stop")
        with self._state_lock:
            if self._state != "idle":
                raise RuntimeError("direct adapter is not idle")
            if input_event.at_ms != self._manual_time:
                raise ValueError("stop must use the current manual time")
            self._state = "stopping"
        try:
            result = self._application.stop(input_event)
        except Exception:
            return self._abort_runtime("application stop failed", input_event.at_ms)
        return cast(
            TerminalResult,
            self._classify_runtime_result(
                result,
                input_event.at_ms,
                allow_epoch=False,
                messages=_STOP_RESULT_MESSAGES,
            ),
        )
