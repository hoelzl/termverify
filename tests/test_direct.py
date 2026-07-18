from __future__ import annotations

from dataclasses import replace
from threading import Event, Thread
from typing import Any, cast

import pytest

from termverify.adapter import (
    Adapter,
    AdapterFailure,
    ClockAdvance,
    ClockConfiguration,
    ClockReceipt,
    ConstraintUnsupported,
    Cursor,
    Diagnostic,
    DispatchInput,
    EnforcedConstraints,
    EpochCompleted,
    FilesystemConfiguration,
    FilesystemReceipt,
    KeyInput,
    LocaleReceipt,
    ManualTime,
    NetworkConfiguration,
    NetworkReceipt,
    Observation,
    ProcessObservation,
    Region,
    RunConfiguration,
    RunFailed,
    RunFinished,
    SeedReceipt,
    Started,
    StartFailed,
    StartTerminated,
    StartUnsupported,
    Stop,
    TerminalConfiguration,
    TerminalReceipt,
    TerminalResult,
    TextInput,
    TimezoneReceipt,
    UiObservation,
)
from termverify.direct import DirectAdapter


def _configuration() -> RunConfiguration:
    return RunConfiguration(
        seed=42,
        clock=ClockConfiguration(initial_ms=0),
        locale="en-US",
        timezone="UTC",
        terminal=TerminalConfiguration(columns=80, rows=24, capabilities=()),
        filesystem=FilesystemConfiguration(root_id="fixture-root"),
        network=NetworkConfiguration.deny(),
    )


def _observation(at_ms: int = 0) -> Observation:
    return Observation(
        at_ms=ManualTime(at_ms),
        state={"count": 0},
        events=(),
        ui=UiObservation(
            regions=(Region("main", "document", 0, 0, 80, 24),),
            focus="main",
            cursor=Cursor(0, 0, True),
            mode=None,
        ),
    )


class _Ports:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.aborts: list[ManualTime] = []

    def enforce_seed(
        self, run_id: str, requested: int
    ) -> SeedReceipt | ConstraintUnsupported | AdapterFailure:
        self.calls.append("seed")
        return SeedReceipt(run_id, requested, "constructive")

    def enforce_clock(
        self, run_id: str, requested: ClockConfiguration
    ) -> ClockReceipt | ConstraintUnsupported | AdapterFailure:
        self.calls.append("clock")
        return ClockReceipt(run_id, requested, "constructive")

    def enforce_locale(
        self, run_id: str, requested: str
    ) -> LocaleReceipt | ConstraintUnsupported | AdapterFailure:
        self.calls.append("locale")
        return LocaleReceipt(run_id, requested, "constructive")

    def enforce_timezone(
        self, run_id: str, requested: str
    ) -> TimezoneReceipt | ConstraintUnsupported | AdapterFailure:
        self.calls.append("timezone")
        return TimezoneReceipt(run_id, requested, "constructive")

    def enforce_terminal(
        self, run_id: str, requested: TerminalConfiguration
    ) -> TerminalReceipt | ConstraintUnsupported | AdapterFailure:
        self.calls.append("terminal")
        return TerminalReceipt(run_id, requested, "constructive")

    def enforce_filesystem(
        self, run_id: str, requested: FilesystemConfiguration
    ) -> FilesystemReceipt | ConstraintUnsupported | AdapterFailure:
        self.calls.append("filesystem")
        return FilesystemReceipt(run_id, requested, "constructive")

    def enforce_network(
        self, run_id: str, requested: NetworkConfiguration
    ) -> NetworkReceipt | ConstraintUnsupported | AdapterFailure:
        self.calls.append("network")
        return NetworkReceipt(run_id, requested, "constructive")


class _Application(_Ports):
    def initialize(self) -> EpochCompleted | TerminalResult | AdapterFailure:
        return EpochCompleted(_observation())

    def dispatch(
        self, input_event: DispatchInput
    ) -> EpochCompleted | TerminalResult | AdapterFailure:
        return EpochCompleted(_observation(input_event.at_ms))

    def advance_clock(
        self, input_event: ClockAdvance
    ) -> EpochCompleted | TerminalResult | AdapterFailure:
        return EpochCompleted(_observation(input_event.at_ms))

    def stop(self, input_event: Stop) -> TerminalResult | AdapterFailure:
        raise AssertionError("not used")

    def abort(self, input_event: Stop) -> None:
        self.aborts.append(input_event.at_ms)


def test_start_negotiates_constraints_in_order_before_readiness() -> None:
    application = _Application()
    adapter: Adapter = DirectAdapter(application)

    result = adapter.start("run-direct", _configuration())

    assert isinstance(result, Started)
    assert isinstance(result.constraints, EnforcedConstraints)
    assert result.observation == _observation()
    assert application.calls == [
        "seed",
        "clock",
        "locale",
        "timezone",
        "terminal",
        "filesystem",
        "network",
    ]


class _NeverApplication(_Application):
    def initialize(self) -> EpochCompleted | TerminalResult | AdapterFailure:
        raise AssertionError("initialization must not run")


@pytest.mark.parametrize(
    "constraint",
    ["seed", "clock", "locale", "timezone", "terminal", "filesystem", "network"],
)
def test_start_stops_at_first_unsupported_constraint(constraint: str) -> None:
    application = _NeverApplication()

    def unsupported(*args: object) -> ConstraintUnsupported:
        del args
        application.calls.append(constraint)
        return ConstraintUnsupported(
            constraint,  # type: ignore[arg-type]
            "constraint-unsupported",
            "port unavailable",
        )

    method_name = f"enforce_{constraint}"
    setattr(application, method_name, unsupported)
    adapter = DirectAdapter(application)

    result = adapter.start("run-direct", _configuration())

    assert isinstance(result, StartUnsupported)
    assert result.constraint == constraint
    order = [
        "seed",
        "clock",
        "locale",
        "timezone",
        "terminal",
        "filesystem",
        "network",
    ]
    index = order.index(constraint)
    assert len(result.enforced) == index
    assert application.calls == order[: index + 1]


class _NamedTimezoneUnsupportedApplication(_NeverApplication):
    def enforce_timezone(
        self, run_id: str, requested: str
    ) -> TimezoneReceipt | ConstraintUnsupported | AdapterFailure:
        del run_id
        self.calls.append("timezone")
        assert requested == "Europe/Berlin"
        return ConstraintUnsupported(
            "timezone",
            "constraint-unsupported",
            "named timezone enforcement is unavailable",
        )


def test_canonical_named_timezone_request_can_report_structured_unsupported() -> None:
    application = _NamedTimezoneUnsupportedApplication()
    adapter = DirectAdapter(application)
    configuration = replace(_configuration(), timezone="Europe/Berlin")

    result = adapter.start("run-direct", configuration)

    assert isinstance(result, StartUnsupported)
    assert result.constraint == "timezone"
    assert result.code == "constraint-unsupported"
    assert result.enforced == (
        SeedReceipt("run-direct", 42, "constructive"),
        ClockReceipt("run-direct", ClockConfiguration(0), "constructive"),
        LocaleReceipt("run-direct", "en-US", "constructive"),
    )
    assert application.calls == ["seed", "clock", "locale", "timezone"]


class _RaisingLocaleApplication(_NeverApplication):
    def enforce_locale(
        self, run_id: str, requested: str
    ) -> LocaleReceipt | ConstraintUnsupported | AdapterFailure:
        del run_id, requested
        self.calls.append("locale")
        raise RuntimeError("host-specific exception text")


def test_start_converts_constraint_port_exception_to_stable_failure() -> None:
    application = _RaisingLocaleApplication()
    adapter = DirectAdapter(application)

    result = adapter.start("run-direct", _configuration())

    assert isinstance(result, StartFailed)
    assert len(result.enforced) == 2
    assert result.failure == AdapterFailure(
        "adapter-start-failed",
        "constraint enforcement failed",
        {"constraint": "locale"},
    )
    assert application.calls == ["seed", "clock", "locale"]


class _ExitsDuringInitialization(_Application):
    def initialize(self) -> EpochCompleted | TerminalResult | AdapterFailure:
        exit_status = RunFinished.code(0)
        return TerminalResult(
            observation=replace(
                _observation(),
                process=ProcessObservation.exited(exit_status.exit),
            ),
            outcome=exit_status,
        )


def test_start_reports_subject_exit_during_initialization() -> None:
    adapter = DirectAdapter(_ExitsDuringInitialization())

    result = adapter.start("run-direct", _configuration())

    assert isinstance(result, StartTerminated)
    assert result.result.outcome == RunFinished.code(0)


def test_dispatch_returns_application_reported_quiescent_observation() -> None:
    adapter = DirectAdapter(_Application())
    assert isinstance(adapter.start("run-direct", _configuration()), Started)

    result = adapter.dispatch(TextInput(ManualTime(0), "hello"))

    assert result == EpochCompleted(_observation())


class _CapturingKeyApplication(_Application):
    def __init__(self) -> None:
        super().__init__()
        self.dispatched: DispatchInput | None = None

    def dispatch(
        self, input_event: DispatchInput
    ) -> EpochCompleted | TerminalResult | AdapterFailure:
        self.dispatched = input_event
        return super().dispatch(input_event)


def test_dispatch_forwards_semantic_key_input_unchanged() -> None:
    application = _CapturingKeyApplication()
    adapter = DirectAdapter(application)
    assert isinstance(adapter.start("run-direct", _configuration()), Started)
    input_event = KeyInput(ManualTime(0), ("Control", "c"))

    result = adapter.dispatch(input_event)

    assert result == EpochCompleted(_observation())
    assert application.dispatched is input_event


class _UnsupportedKeyApplication(_Application):
    def dispatch(
        self, input_event: DispatchInput
    ) -> EpochCompleted | TerminalResult | AdapterFailure:
        if type(input_event) is KeyInput:
            return AdapterFailure(
                "adapter-runtime-failed",
                "semantic key input is unsupported",
                {"input_kind": "key", "reason": "unsupported"},
            )
        return super().dispatch(input_event)


def test_application_key_input_unsupported_is_structured_runtime_failure() -> None:
    application = _UnsupportedKeyApplication()
    adapter = DirectAdapter(application)
    assert isinstance(adapter.start("run-direct", _configuration()), Started)

    result = adapter.dispatch(KeyInput(ManualTime(0), ("Enter",)))

    assert result == TerminalResult(
        None,
        RunFailed(
            AdapterFailure(
                "adapter-runtime-failed",
                "semantic key input is unsupported",
                {"input_kind": "key", "reason": "unsupported"},
            )
        ),
    )
    assert application.aborts == [ManualTime(0)]


def test_dispatch_is_rejected_before_readiness() -> None:
    adapter = DirectAdapter(_Application())

    with pytest.raises(RuntimeError, match="not idle"):
        adapter.dispatch(TextInput(ManualTime(0), "too early"))


def test_dispatch_requires_the_current_manual_time() -> None:
    adapter = DirectAdapter(_Application())
    assert isinstance(adapter.start("run-direct", _configuration()), Started)

    with pytest.raises(ValueError, match="current manual time"):
        adapter.dispatch(TextInput(ManualTime(1), "future input"))


class _WrongTimeApplication(_Application):
    def dispatch(
        self, input_event: DispatchInput
    ) -> EpochCompleted | TerminalResult | AdapterFailure:
        del input_event
        return EpochCompleted(_observation(1))


def test_invalid_quiescence_evidence_fails_the_run_and_is_absorbing() -> None:
    adapter = DirectAdapter(_WrongTimeApplication())
    assert isinstance(adapter.start("run-direct", _configuration()), Started)

    result = adapter.dispatch(TextInput(ManualTime(0), "hello"))

    assert result == TerminalResult(
        observation=None,
        outcome=RunFailed(
            AdapterFailure(
                "adapter-runtime-failed",
                "application returned invalid epoch evidence",
            )
        ),
    )
    with pytest.raises(RuntimeError, match="not idle"):
        adapter.dispatch(TextInput(ManualTime(0), "after failure"))


def test_clock_advance_moves_manual_time_only_through_the_explicit_port() -> None:
    adapter = DirectAdapter(_Application())
    assert isinstance(adapter.start("run-direct", _configuration()), Started)

    result = adapter.advance_clock(ClockAdvance(ManualTime(5), 5))

    assert result == EpochCompleted(_observation(5))
    assert adapter.dispatch(TextInput(ManualTime(5), "after clock")) == EpochCompleted(
        _observation(5)
    )


def test_clock_advance_rejects_inconsistent_time_and_delta_without_side_effects() -> (
    None
):
    adapter = DirectAdapter(_Application())
    assert isinstance(adapter.start("run-direct", _configuration()), Started)

    with pytest.raises(ValueError, match="move the current manual time"):
        adapter.advance_clock(ClockAdvance(ManualTime(5), 4))

    assert adapter.advance_clock(ClockAdvance(ManualTime(5), 5)) == EpochCompleted(
        _observation(5)
    )


class _StoppingApplication(_Application):
    def stop(self, input_event: Stop) -> TerminalResult | AdapterFailure:
        return TerminalResult(
            observation=_observation(input_event.at_ms),
            outcome=RunFinished.code(0),
        )


def test_stop_drains_to_terminal_result_and_prevents_further_input() -> None:
    adapter = DirectAdapter(_StoppingApplication())
    assert isinstance(adapter.start("run-direct", _configuration()), Started)

    result = adapter.stop(Stop(ManualTime(0)))

    assert result == TerminalResult(_observation(), RunFinished.code(0))
    with pytest.raises(RuntimeError, match="not idle"):
        adapter.dispatch(TextInput(ManualTime(0), "after stop"))
    with pytest.raises(RuntimeError, match="not idle"):
        adapter.stop(Stop(ManualTime(0)))


def test_adapter_can_start_only_once() -> None:
    adapter = DirectAdapter(_Application())
    assert isinstance(adapter.start("run-direct", _configuration()), Started)

    with pytest.raises(RuntimeError, match="already started"):
        adapter.start("run-again", _configuration())


class _RaisingInitialization(_Application):
    def initialize(self) -> EpochCompleted | TerminalResult | AdapterFailure:
        raise RuntimeError("host-specific exception text")


def test_initialization_exception_becomes_start_failure() -> None:
    application = _RaisingInitialization()
    adapter = DirectAdapter(application)

    result = adapter.start("run-direct", _configuration())

    assert isinstance(result, StartFailed)
    assert len(result.enforced) == 7
    assert result.failure == AdapterFailure(
        "adapter-start-failed", "application initialization failed"
    )
    assert application.aborts == [ManualTime(0)]


class _WrongInitialTime(_Application):
    def initialize(self) -> EpochCompleted | TerminalResult | AdapterFailure:
        return EpochCompleted(_observation(1))


def test_invalid_initial_quiescence_becomes_start_failure() -> None:
    adapter = DirectAdapter(_WrongInitialTime())

    result = adapter.start("run-direct", _configuration())

    assert isinstance(result, StartFailed)
    assert result.failure.message == "application returned invalid initial evidence"


def test_started_construction_failure_aborts_and_becomes_terminal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application = _Application()
    adapter = DirectAdapter(application)

    def reject_started(**kwargs: Any) -> Started:
        del kwargs
        raise ValueError("post-initialization invariant failed")

    monkeypatch.setattr("termverify.direct.Started", reject_started)

    result = adapter.start("run-direct", _configuration())

    assert isinstance(result, StartFailed)
    assert result.failure == AdapterFailure(
        "adapter-start-failed", "application returned invalid initial evidence"
    )
    assert application.aborts == [ManualTime(0)]
    with pytest.raises(RuntimeError, match="already started"):
        adapter.start("run-again", _configuration())


class _RaisingDispatch(_Application):
    def dispatch(
        self, input_event: DispatchInput
    ) -> EpochCompleted | TerminalResult | AdapterFailure:
        del input_event
        raise RuntimeError("host-specific exception text")


def test_dispatch_exception_becomes_runtime_failure() -> None:
    application = _RaisingDispatch()
    adapter = DirectAdapter(application)
    assert isinstance(adapter.start("run-direct", _configuration()), Started)

    result = adapter.dispatch(TextInput(ManualTime(0), "hello"))

    assert result == TerminalResult(
        None,
        RunFailed(
            AdapterFailure("adapter-runtime-failed", "application dispatch failed")
        ),
    )
    assert application.aborts == [ManualTime(0)]


class _RaisingAbort(_RaisingDispatch):
    def abort(self, input_event: Stop) -> None:
        del input_event
        raise RuntimeError("host-specific abort exception")


class _MalformedRuntimeAbort(_RaisingDispatch):
    def abort(self, input_event: Stop) -> Any:
        del input_event
        return "not-cleaned"


class _MalformedStartupAbort(_RaisingInitialization):
    def abort(self, input_event: Stop) -> Any:
        del input_event
        return AdapterFailure("adapter-runtime-failed", "not an abort receipt")


class _RuntimeAbortLookupFailure(_RaisingDispatch):
    def __getattribute__(self, name: str) -> Any:
        if name == "abort":
            raise RuntimeError("abort lookup failed")
        return super().__getattribute__(name)


class _StartupAbortLookupFailure(_RaisingInitialization):
    def __getattribute__(self, name: str) -> Any:
        if name == "abort":
            raise RuntimeError("abort lookup failed")
        return super().__getattribute__(name)


def test_abort_lookup_failure_is_recorded_and_terminal_is_absorbing() -> None:
    startup_adapter = DirectAdapter(_StartupAbortLookupFailure())
    startup_result = startup_adapter.start("run-startup", _configuration())
    assert isinstance(startup_result, StartFailed)
    assert startup_result.failure.details == {
        "application": None,
        "abort": "failed",
    }
    with pytest.raises(RuntimeError, match="already started"):
        startup_adapter.start("run-again", _configuration())

    runtime_adapter = DirectAdapter(_RuntimeAbortLookupFailure())
    assert isinstance(runtime_adapter.start("run-runtime", _configuration()), Started)
    runtime_result = runtime_adapter.dispatch(TextInput(ManualTime(0), "fail"))
    assert runtime_result == TerminalResult(
        None,
        RunFailed(
            AdapterFailure(
                "adapter-runtime-failed",
                "application dispatch failed",
                {"application": None, "abort": "failed"},
            )
        ),
    )
    with pytest.raises(RuntimeError, match="not idle"):
        runtime_adapter.stop(Stop(ManualTime(0)))


def test_malformed_abort_result_is_recorded_for_startup_and_runtime() -> None:
    startup_adapter = DirectAdapter(_MalformedStartupAbort())
    startup_result = startup_adapter.start("run-startup", _configuration())
    assert isinstance(startup_result, StartFailed)
    assert startup_result.failure.details == {
        "application": None,
        "abort": "failed",
    }

    runtime_adapter = DirectAdapter(_MalformedRuntimeAbort())
    assert isinstance(runtime_adapter.start("run-runtime", _configuration()), Started)
    runtime_result = runtime_adapter.dispatch(TextInput(ManualTime(0), "fail"))
    assert runtime_result == TerminalResult(
        None,
        RunFailed(
            AdapterFailure(
                "adapter-runtime-failed",
                "application dispatch failed",
                {"application": None, "abort": "failed"},
            )
        ),
    )


class _FailingInitializationAbort(_Application):
    def __init__(
        self, initialized: RuntimeError | EpochCompleted | AdapterFailure
    ) -> None:
        super().__init__()
        self.initialized = initialized

    def initialize(self) -> EpochCompleted | TerminalResult | AdapterFailure:
        if isinstance(self.initialized, RuntimeError):
            raise self.initialized
        return self.initialized

    def abort(self, input_event: Stop) -> None:
        del input_event
        raise RuntimeError("host-specific abort exception")


@pytest.mark.parametrize(
    ("initialized", "message"),
    [
        (RuntimeError("initialize failed"), "application initialization failed"),
        (
            EpochCompleted(_observation(1)),
            "application returned invalid initial evidence",
        ),
        (
            AdapterFailure("adapter-start-failed", "application refused startup"),
            "application refused startup",
        ),
    ],
)
def test_startup_abort_failure_is_recorded_without_losing_original_failure(
    initialized: RuntimeError | EpochCompleted | AdapterFailure,
    message: str,
) -> None:
    adapter = DirectAdapter(_FailingInitializationAbort(initialized))

    result = adapter.start("run-direct", _configuration())

    assert isinstance(result, StartFailed)
    assert result.failure.code == "adapter-start-failed"
    assert result.failure.message == message
    assert result.failure.details == {"application": None, "abort": "failed"}


class _DetailedRuntimeFailureWithFailingAbort(_Application):
    def __init__(self, details: Any) -> None:
        super().__init__()
        self.details = details

    def dispatch(
        self, input_event: DispatchInput
    ) -> EpochCompleted | TerminalResult | AdapterFailure:
        del input_event
        return AdapterFailure(
            "adapter-runtime-failed",
            "application reported failure",
            self.details,
        )

    def abort(self, input_event: Stop) -> None:
        self.aborts.append(input_event.at_ms)
        raise RuntimeError("abort failed")


@pytest.mark.parametrize(
    "details",
    [
        {"abort": "application value", "context": "dispatch"},
        ["non-mapping", 7],
    ],
)
def test_abort_failure_preserves_application_failure_details(details: Any) -> None:
    application = _DetailedRuntimeFailureWithFailingAbort(details)
    adapter = DirectAdapter(application)
    assert isinstance(adapter.start("run-direct", _configuration()), Started)

    result = adapter.dispatch(TextInput(ManualTime(0), "fail"))

    assert result == TerminalResult(
        None,
        RunFailed(
            AdapterFailure(
                "adapter-runtime-failed",
                "application reported failure",
                {"application": details, "abort": "failed"},
            )
        ),
    )
    assert application.aborts == [ManualTime(0)]
    with pytest.raises(RuntimeError, match="not idle"):
        adapter.dispatch(TextInput(ManualTime(0), "absorbed"))


def test_abort_exception_remains_a_stable_absorbing_runtime_failure() -> None:
    adapter = DirectAdapter(_RaisingAbort())
    assert isinstance(adapter.start("run-direct", _configuration()), Started)

    result = adapter.dispatch(TextInput(ManualTime(0), "hello"))

    assert result == TerminalResult(
        None,
        RunFailed(
            AdapterFailure(
                "adapter-runtime-failed",
                "application dispatch failed",
                {"application": None, "abort": "failed"},
            )
        ),
    )
    with pytest.raises(RuntimeError, match="not idle"):
        adapter.stop(Stop(ManualTime(0)))


def test_operation_methods_reject_the_wrong_input_contract_type() -> None:
    adapter = DirectAdapter(_Application())
    assert isinstance(adapter.start("run-direct", _configuration()), Started)

    with pytest.raises(TypeError, match="KeyInput, TextInput, or Resize"):
        adapter.dispatch(cast(Any, ClockAdvance(ManualTime(1), 1)))
    with pytest.raises(TypeError, match="ClockAdvance"):
        adapter.advance_clock(cast(Any, TextInput(ManualTime(0), "wrong")))
    with pytest.raises(TypeError, match="Stop"):
        adapter.stop(cast(Any, TextInput(ManualTime(0), "wrong")))


class _WrongTerminalTime(_Application):
    def dispatch(
        self, input_event: DispatchInput
    ) -> EpochCompleted | TerminalResult | AdapterFailure:
        del input_event
        return TerminalResult(_observation(1), RunFinished.code(0))


class _NaturalExitApplication(_Application):
    @staticmethod
    def _result(at_ms: ManualTime) -> TerminalResult:
        return TerminalResult(
            _observation(at_ms),
            RunFinished.code(0),
            (Diagnostic(at_ms, "subject-exited", "subject exited"),),
        )

    def dispatch(
        self, input_event: DispatchInput
    ) -> EpochCompleted | TerminalResult | AdapterFailure:
        return self._result(input_event.at_ms)

    def advance_clock(
        self, input_event: ClockAdvance
    ) -> EpochCompleted | TerminalResult | AdapterFailure:
        return self._result(input_event.at_ms)


def test_dispatch_accepts_valid_natural_exit_and_becomes_absorbing() -> None:
    adapter = DirectAdapter(_NaturalExitApplication())
    assert isinstance(adapter.start("run-direct", _configuration()), Started)

    result = adapter.dispatch(TextInput(ManualTime(0), "exit"))

    assert isinstance(result, TerminalResult)
    assert isinstance(result.outcome, RunFinished)
    assert result.diagnostics[0].at_ms == ManualTime(0)
    with pytest.raises(RuntimeError, match="not idle"):
        adapter.dispatch(TextInput(ManualTime(0), "after exit"))


def test_clock_accepts_valid_natural_exit_and_becomes_absorbing() -> None:
    adapter = DirectAdapter(_NaturalExitApplication())
    assert isinstance(adapter.start("run-direct", _configuration()), Started)

    result = adapter.advance_clock(ClockAdvance(ManualTime(2), 2))

    assert isinstance(result, TerminalResult)
    assert isinstance(result.outcome, RunFinished)
    assert result.diagnostics[0].at_ms == ManualTime(2)
    with pytest.raises(RuntimeError, match="not idle"):
        adapter.dispatch(TextInput(ManualTime(2), "after exit"))


def test_terminal_result_must_use_the_active_epoch_time() -> None:
    adapter = DirectAdapter(_WrongTerminalTime())
    assert isinstance(adapter.start("run-direct", _configuration()), Started)

    result = adapter.dispatch(TextInput(ManualTime(0), "exit"))

    assert result == TerminalResult(
        None,
        RunFailed(
            AdapterFailure(
                "adapter-runtime-failed",
                "application returned invalid terminal evidence",
            )
        ),
    )


class _RaisingClock(_Application):
    def advance_clock(
        self, input_event: ClockAdvance
    ) -> EpochCompleted | TerminalResult | AdapterFailure:
        del input_event
        raise RuntimeError("host-specific exception text")


class _RaisingStop(_Application):
    def stop(self, input_event: Stop) -> TerminalResult | AdapterFailure:
        del input_event
        raise RuntimeError("host-specific exception text")


class _WrongClockEvidence(_Application):
    def advance_clock(
        self, input_event: ClockAdvance
    ) -> EpochCompleted | TerminalResult | AdapterFailure:
        return EpochCompleted(_observation(input_event.at_ms + 1))


class _WrongStopTerminalTime(_Application):
    def stop(self, input_event: Stop) -> TerminalResult | AdapterFailure:
        return TerminalResult(_observation(input_event.at_ms + 1), RunFinished.code(0))


def test_clock_rejects_wrong_time_evidence_and_aborts() -> None:
    application = _WrongClockEvidence()
    adapter = DirectAdapter(application)
    assert isinstance(adapter.start("run-direct", _configuration()), Started)

    result = adapter.advance_clock(ClockAdvance(ManualTime(1), 1))

    assert isinstance(result, TerminalResult)
    assert isinstance(result.outcome, RunFailed)
    assert application.aborts == [ManualTime(1)]
    with pytest.raises(RuntimeError, match="not idle"):
        adapter.dispatch(TextInput(ManualTime(1), "absorbed"))


def test_stop_rejects_wrong_time_terminal_evidence_and_aborts() -> None:
    application = _WrongStopTerminalTime()
    adapter = DirectAdapter(application)
    assert isinstance(adapter.start("run-direct", _configuration()), Started)

    result = adapter.stop(Stop(ManualTime(0)))

    assert isinstance(result.outcome, RunFailed)
    assert application.aborts == [ManualTime(0)]
    with pytest.raises(RuntimeError, match="not idle"):
        adapter.dispatch(TextInput(ManualTime(0), "absorbed"))


def test_clock_and_stop_exceptions_become_runtime_failures() -> None:
    clock_adapter = DirectAdapter(_RaisingClock())
    assert isinstance(clock_adapter.start("run-clock", _configuration()), Started)
    clock_result = clock_adapter.advance_clock(ClockAdvance(ManualTime(1), 1))
    assert isinstance(clock_result, TerminalResult)
    assert clock_result.outcome == RunFailed(
        AdapterFailure("adapter-runtime-failed", "application clock advance failed")
    )

    stop_adapter = DirectAdapter(_RaisingStop())
    assert isinstance(stop_adapter.start("run-stop", _configuration()), Started)
    stop_result = stop_adapter.stop(Stop(ManualTime(0)))
    assert stop_result.outcome == RunFailed(
        AdapterFailure("adapter-runtime-failed", "application stop failed")
    )


class _InitialTerminal(_Application):
    def __init__(self, result: TerminalResult) -> None:
        super().__init__()
        self._result = result

    def initialize(self) -> EpochCompleted | TerminalResult | AdapterFailure:
        return self._result


@pytest.mark.parametrize(
    "terminal_result",
    [
        TerminalResult(
            None,
            RunFailed(AdapterFailure("adapter-runtime-failed", "failed too early")),
        ),
        TerminalResult(_observation(1), RunFinished.code(0)),
    ],
)
def test_invalid_initial_terminal_result_becomes_start_failure(
    terminal_result: TerminalResult,
) -> None:
    adapter = DirectAdapter(_InitialTerminal(terminal_result))

    result = adapter.start("run-direct", _configuration())

    assert isinstance(result, StartFailed)
    assert result.failure == AdapterFailure(
        "adapter-start-failed", "application returned invalid initial terminal evidence"
    )


class _RuntimeFailureApplication(_Application):
    failure = AdapterFailure(
        "adapter-runtime-failed", "application reported a deterministic failure"
    )

    def dispatch(
        self, input_event: DispatchInput
    ) -> EpochCompleted | TerminalResult | AdapterFailure:
        del input_event
        return self.failure

    def advance_clock(
        self, input_event: ClockAdvance
    ) -> EpochCompleted | TerminalResult | AdapterFailure:
        del input_event
        return self.failure

    def stop(self, input_event: Stop) -> TerminalResult | AdapterFailure:
        del input_event
        return self.failure


def test_application_runtime_failure_is_preserved_for_every_operation() -> None:
    expected = RunFailed(_RuntimeFailureApplication.failure)

    dispatch_adapter = DirectAdapter(_RuntimeFailureApplication())
    assert isinstance(dispatch_adapter.start("run-dispatch", _configuration()), Started)
    dispatch_result = dispatch_adapter.dispatch(TextInput(ManualTime(0), "fail"))
    assert isinstance(dispatch_result, TerminalResult)
    assert dispatch_result.outcome == expected

    clock_adapter = DirectAdapter(_RuntimeFailureApplication())
    assert isinstance(clock_adapter.start("run-clock", _configuration()), Started)
    clock_result = clock_adapter.advance_clock(ClockAdvance(ManualTime(1), 1))
    assert isinstance(clock_result, TerminalResult)
    assert clock_result.outcome == expected

    stop_adapter = DirectAdapter(_RuntimeFailureApplication())
    assert isinstance(stop_adapter.start("run-stop", _configuration()), Started)
    assert stop_adapter.stop(Stop(ManualTime(0))).outcome == expected


class _PrewrappedRuntimeFailure(_Application):
    result = TerminalResult(
        None,
        RunFailed(AdapterFailure("adapter-runtime-failed", "prewrapped failure")),
    )

    def dispatch(
        self, input_event: DispatchInput
    ) -> EpochCompleted | TerminalResult | AdapterFailure:
        del input_event
        return self.result

    def advance_clock(
        self, input_event: ClockAdvance
    ) -> EpochCompleted | TerminalResult | AdapterFailure:
        del input_event
        return self.result

    def stop(self, input_event: Stop) -> TerminalResult | AdapterFailure:
        del input_event
        return self.result


def test_prewrapped_runtime_failure_is_rejected_and_aborted_for_every_operation() -> (
    None
):
    expected = TerminalResult(
        None,
        RunFailed(
            AdapterFailure(
                "adapter-runtime-failed",
                "application returned invalid terminal outcome",
            )
        ),
    )
    dispatch_application = _PrewrappedRuntimeFailure()
    dispatch_adapter = DirectAdapter(dispatch_application)
    assert isinstance(dispatch_adapter.start("run-dispatch", _configuration()), Started)
    dispatch_result = dispatch_adapter.dispatch(TextInput(ManualTime(0), "fail"))
    assert dispatch_result == expected
    assert dispatch_application.aborts == [ManualTime(0)]

    clock_application = _PrewrappedRuntimeFailure()
    clock_adapter = DirectAdapter(clock_application)
    assert isinstance(clock_adapter.start("run-clock", _configuration()), Started)
    clock_result = clock_adapter.advance_clock(ClockAdvance(ManualTime(1), 1))
    assert clock_result == expected
    assert clock_application.aborts == [ManualTime(1)]

    stop_application = _PrewrappedRuntimeFailure()
    stop_adapter = DirectAdapter(stop_application)
    assert isinstance(stop_adapter.start("run-stop", _configuration()), Started)
    stop_result = stop_adapter.stop(Stop(ManualTime(0)))
    assert stop_result == expected
    assert stop_application.aborts == [ManualTime(0)]


class _ClassificationApplication(_Application):
    def __init__(self, result: object) -> None:
        super().__init__()
        self.result = result

    def dispatch(
        self, input_event: DispatchInput
    ) -> EpochCompleted | TerminalResult | AdapterFailure:
        del input_event
        return cast(EpochCompleted | TerminalResult | AdapterFailure, self.result)

    def advance_clock(
        self, input_event: ClockAdvance
    ) -> EpochCompleted | TerminalResult | AdapterFailure:
        del input_event
        return cast(EpochCompleted | TerminalResult | AdapterFailure, self.result)

    def stop(self, input_event: Stop) -> TerminalResult | AdapterFailure:
        del input_event
        return cast(TerminalResult | AdapterFailure, self.result)


@pytest.mark.parametrize("operation", ["dispatch", "clock", "stop"])
@pytest.mark.parametrize(
    "category",
    [
        "epoch",
        "terminal",
        "failure",
        "wrong-failure-code",
        "foreign",
        "wrong-time",
        "wrong-terminal-outcome",
    ],
)
def test_runtime_result_classification_matrix(operation: str, category: str) -> None:
    at_ms = ManualTime(1 if operation == "clock" else 0)
    if category == "epoch":
        application_result: object = EpochCompleted(_observation(at_ms))
    elif category == "terminal":
        application_result = TerminalResult(_observation(at_ms), RunFinished.code(0))
    elif category == "failure":
        application_result = AdapterFailure(
            "adapter-runtime-failed", "application reported failure"
        )
    elif category == "wrong-failure-code":
        application_result = AdapterFailure(
            "adapter-start-failed", "wrong failure phase"
        )
    elif category == "foreign":
        application_result = object()
    elif category == "wrong-time":
        application_result = TerminalResult(
            _observation(at_ms + 1), RunFinished.code(0)
        )
    else:
        application_result = TerminalResult(
            None,
            RunFailed(AdapterFailure("adapter-runtime-failed", "prewrapped")),
        )
    application = _ClassificationApplication(application_result)
    adapter = DirectAdapter(application)
    assert isinstance(
        adapter.start(f"run-{operation}-{category}", _configuration()), Started
    )

    if operation == "dispatch":
        result = adapter.dispatch(TextInput(at_ms, "input"))
    elif operation == "clock":
        result = adapter.advance_clock(ClockAdvance(at_ms, 1))
    else:
        result = adapter.stop(Stop(at_ms))

    if category == "epoch" and operation != "stop":
        assert result == application_result
        assert application.aborts == []
        return
    if category == "terminal":
        assert result == application_result
        assert application.aborts == []
    else:
        assert isinstance(result, TerminalResult)
        assert isinstance(result.outcome, RunFailed)
        if category == "failure":
            expected_message = "application reported failure"
        elif category == "wrong-time":
            expected_message = "application returned invalid terminal evidence"
        elif category == "wrong-terminal-outcome":
            expected_message = "application returned invalid terminal outcome"
        elif operation == "stop":
            expected_message = "application did not report termination"
        else:
            expected_message = "application did not report quiescence or termination"
        assert result.outcome.failure.message == expected_message
        assert application.aborts == [at_ms]
    with pytest.raises(RuntimeError, match="not idle"):
        adapter.dispatch(TextInput(at_ms, "absorbed"))


class _ReentrantApplication(_Application):
    adapter: DirectAdapter | None = None
    reentrant_error: RuntimeError | None = None

    def dispatch(
        self, input_event: DispatchInput
    ) -> EpochCompleted | TerminalResult | AdapterFailure:
        assert self.adapter is not None
        try:
            self.adapter.dispatch(TextInput(input_event.at_ms, "overlap"))
        except RuntimeError as error:
            self.reentrant_error = error
        return EpochCompleted(_observation(input_event.at_ms))


def test_reentrant_input_is_rejected_until_the_epoch_completes() -> None:
    application = _ReentrantApplication()
    adapter = DirectAdapter(application)
    application.adapter = adapter
    assert isinstance(adapter.start("run-direct", _configuration()), Started)

    assert adapter.dispatch(TextInput(ManualTime(0), "outer")) == EpochCompleted(
        _observation()
    )
    assert application.reentrant_error is not None
    assert "not idle" in str(application.reentrant_error)


class _BlockingApplication(_Application):
    def __init__(self) -> None:
        super().__init__()
        self.entered = Event()
        self.release = Event()

    def dispatch(
        self, input_event: DispatchInput
    ) -> EpochCompleted | TerminalResult | AdapterFailure:
        self.entered.set()
        if not self.release.wait(timeout=5):
            raise AssertionError("test did not release blocked dispatch")
        return EpochCompleted(_observation(input_event.at_ms))


def test_concurrent_input_is_rejected_while_an_epoch_is_active() -> None:
    application = _BlockingApplication()
    adapter = DirectAdapter(application)
    assert isinstance(adapter.start("run-direct", _configuration()), Started)
    results: list[EpochCompleted | TerminalResult] = []

    worker = Thread(
        target=lambda: results.append(
            adapter.dispatch(TextInput(ManualTime(0), "first"))
        )
    )
    worker.start()
    assert application.entered.wait(timeout=5)
    try:
        with pytest.raises(RuntimeError, match="not idle"):
            adapter.dispatch(TextInput(ManualTime(0), "overlap"))
    finally:
        application.release.set()
        worker.join(timeout=5)

    assert not worker.is_alive()
    assert results == [EpochCompleted(_observation())]


class _BlockingInitialization(_Application):
    def __init__(self) -> None:
        super().__init__()
        self.entered = Event()
        self.release = Event()

    def initialize(self) -> EpochCompleted | TerminalResult | AdapterFailure:
        self.entered.set()
        if not self.release.wait(timeout=5):
            raise AssertionError("test did not release initialization")
        return EpochCompleted(_observation())


def test_readiness_and_initial_manual_time_are_published_atomically() -> None:
    application = _BlockingInitialization()
    adapter = DirectAdapter(application)
    starts: list[Started | StartFailed | StartTerminated | StartUnsupported] = []
    worker = Thread(
        target=lambda: starts.append(adapter.start("run-direct", _configuration()))
    )
    worker.start()
    assert application.entered.wait(timeout=5)
    try:
        with pytest.raises(RuntimeError, match="not idle"):
            adapter.dispatch(TextInput(ManualTime(0), "before readiness"))
    finally:
        application.release.set()
        worker.join(timeout=5)

    assert not worker.is_alive()
    assert len(starts) == 1
    assert isinstance(starts[0], Started)
    result = adapter.dispatch(TextInput(ManualTime(0), "after readiness"))
    assert result == EpochCompleted(_observation())


def test_start_rejects_invalid_arguments_before_constraint_side_effects() -> None:
    wrong_configuration_application = _Application()
    adapter = DirectAdapter(wrong_configuration_application)
    with pytest.raises(TypeError, match="RunConfiguration"):
        adapter.start("run-direct", cast(Any, object()))
    assert wrong_configuration_application.calls == []

    wrong_run_id_application = _Application()
    adapter = DirectAdapter(wrong_run_id_application)
    with pytest.raises(ValueError, match="run_id"):
        adapter.start("INVALID RUN", _configuration())
    assert wrong_run_id_application.calls == []


class _SeedResponseApplication(_NeverApplication):
    def __init__(self, response: object) -> None:
        super().__init__()
        self.response = response

    def enforce_seed(
        self, run_id: str, requested: int
    ) -> SeedReceipt | ConstraintUnsupported | AdapterFailure:
        del run_id, requested
        self.calls.append("seed")
        return cast(SeedReceipt | ConstraintUnsupported | AdapterFailure, self.response)


@pytest.mark.parametrize(
    ("response", "expected_failure"),
    [
        (
            SeedReceipt("run-direct", 43, "constructive"),
            AdapterFailure(
                "adapter-start-failed",
                "constraint enforcement failed",
                {"constraint": "seed"},
            ),
        ),
        (
            SeedReceipt("other-run", 42, "constructive"),
            AdapterFailure(
                "adapter-start-failed",
                "constraint enforcement failed",
                {"constraint": "seed"},
            ),
        ),
        (
            ClockReceipt(
                "run-direct", ClockConfiguration(initial_ms=0), "constructive"
            ),
            AdapterFailure(
                "adapter-start-failed",
                "constraint enforcement failed",
                {"constraint": "seed"},
            ),
        ),
        (
            ConstraintUnsupported(
                "clock", "constraint-unsupported", "wrong constraint"
            ),
            AdapterFailure(
                "adapter-start-failed",
                "constraint enforcement failed",
                {"constraint": "seed"},
            ),
        ),
        (
            AdapterFailure("adapter-start-failed", "seed port failed"),
            AdapterFailure("adapter-start-failed", "seed port failed"),
        ),
        (
            AdapterFailure("adapter-runtime-failed", "wrong phase"),
            AdapterFailure(
                "adapter-start-failed",
                "constraint enforcement failed",
                {"constraint": "seed"},
            ),
        ),
    ],
)
def test_constraint_port_results_fail_closed(
    response: object,
    expected_failure: AdapterFailure,
) -> None:
    application = _SeedResponseApplication(response)
    adapter = DirectAdapter(application)

    result = adapter.start("run-direct", _configuration())

    assert isinstance(result, StartFailed)
    assert result.enforced == ()
    assert result.failure == expected_failure
    assert application.calls == ["seed"]
