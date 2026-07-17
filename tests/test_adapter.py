from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from typing import Any, Protocol, cast

import pytest

from termverify.adapter import (
    Adapter,
    AdapterFailure,
    ClockAdvance,
    ClockConfiguration,
    ClockReceipt,
    ConstraintName,
    ConstraintPorts,
    ConstraintUnsupported,
    Cursor,
    Diagnostic,
    DispatchInput,
    EnforcedConstraints,
    EpochCompleted,
    Event,
    ExitStatus,
    FilesystemConfiguration,
    FilesystemReceipt,
    Frame,
    JsonInput,
    KeyInput,
    LocaleReceipt,
    ManualTime,
    NetworkConfiguration,
    NetworkEndpoint,
    NetworkReceipt,
    Observation,
    ProcessObservation,
    Region,
    Resize,
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
    freeze_json,
)


def _configuration() -> RunConfiguration:
    return RunConfiguration(
        seed=42,
        clock=ClockConfiguration(initial_ms=0),
        locale="en-US",
        timezone="UTC",
        terminal=TerminalConfiguration(
            columns=80,
            rows=24,
            capabilities=(),
        ),
        filesystem=FilesystemConfiguration(root_id="fixture-root"),
        network=NetworkConfiguration.deny(),
    )


def _observation(at_ms: int = 0) -> Observation:
    return Observation(
        at_ms=ManualTime(at_ms),
        state={"count": 1, "items": ["one"]},
        events=(Event(type="updated", data={"count": 1}),),
        ui=UiObservation(
            regions=(
                Region(
                    id="main",
                    role="document",
                    column=0,
                    row=0,
                    columns=80,
                    rows=24,
                ),
            ),
            focus="main",
            cursor=Cursor(column=0, row=0, visible=True),
            mode=None,
        ),
        frame=Frame(lines=("ready",), columns=80, rows=1),
    )


def _constraints(
    run_id: str = "run-contract",
    configuration: RunConfiguration | None = None,
) -> EnforcedConstraints:
    configuration = configuration or _configuration()
    return EnforcedConstraints(
        run_id=run_id,
        requested=configuration,
        seed=SeedReceipt(run_id=run_id, effective=configuration.seed),
        clock=ClockReceipt(run_id=run_id, effective=configuration.clock),
        locale=LocaleReceipt(run_id=run_id, effective=configuration.locale),
        timezone=TimezoneReceipt(run_id=run_id, effective=configuration.timezone),
        terminal=TerminalReceipt(run_id=run_id, effective=configuration.terminal),
        filesystem=FilesystemReceipt(
            run_id=run_id,
            effective=configuration.filesystem,
        ),
        network=NetworkReceipt(run_id=run_id, effective=configuration.network),
    )


def test_run_configuration_is_immutable_and_matches_v1_payload() -> None:
    configuration = _configuration()

    assert configuration.to_protocol() == {
        "seed": "42",
        "clock": {"mode": "manual", "initial_ms": 0},
        "locale": "en-US",
        "timezone": "UTC",
        "terminal": {
            "columns": 80,
            "rows": 24,
            "capabilities": [],
        },
        "filesystem": {"mode": "sandbox", "root_id": "fixture-root"},
        "network": {"mode": "deny"},
    }
    with pytest.raises(FrozenInstanceError):
        configuration.seed = 7  # type: ignore[misc]

    payload = configuration.to_protocol()
    terminal = cast(dict[str, object], payload["terminal"])
    capabilities = cast(list[str], terminal["capabilities"])
    capabilities.append("mutated")
    assert configuration.terminal.capabilities == ()


def test_allow_list_configuration_emits_sorted_v1_endpoint_objects() -> None:
    configuration = replace(
        _configuration(),
        network=NetworkConfiguration.allow_list(
            (("a.example", 443), ("b.example", 80))
        ),
    )

    assert configuration.to_protocol()["network"] == {
        "mode": "allow-list",
        "allowed": [
            {"host": "a.example", "port": 443},
            {"host": "b.example", "port": 80},
        ],
    }


@pytest.mark.parametrize("timezone", ["UTC", "Etc/UTC", "Europe/Berlin"])
def test_run_configuration_accepts_canonical_v1_timezone_names(timezone: str) -> None:
    configuration = replace(_configuration(), timezone=timezone)

    assert configuration.timezone == timezone
    assert configuration.to_protocol()["timezone"] == timezone


@pytest.mark.parametrize(
    "timezone",
    ["US/Eastern", "Europe/Kiev", "Mars/Olympus", "../UTC", "europe/Berlin"],
)
def test_run_configuration_rejects_noncanonical_v1_timezone_names(
    timezone: str,
) -> None:
    with pytest.raises(ValueError, match="timezone registry"):
        replace(_configuration(), timezone=timezone)


@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (lambda: replace(_configuration(), seed=-1), "seed"),
        (lambda: replace(_configuration(), seed=2**64), "seed"),
        (lambda: ClockConfiguration(initial_ms=-1), "initial_ms"),
        (lambda: TerminalConfiguration(0, 24, ()), "columns"),
        (lambda: TerminalConfiguration(80, 24, ("z", "a")), "sorted"),
        (lambda: TerminalConfiguration(80, 24, ("a", "a")), "unique"),
        (lambda: FilesystemConfiguration(root_id=""), "root_id"),
        (lambda: NetworkConfiguration.allow_list((("", 80),)), "host"),
        (lambda: NetworkConfiguration.allow_list((("example.test", 0),)), "port"),
        (
            lambda: NetworkConfiguration.allow_list(
                (("z.example", 443), ("a.example", 443))
            ),
            "sorted",
        ),
        (
            lambda: replace(_configuration(), locale="not_a_locale"),
            "locale",
        ),
        (
            lambda: replace(_configuration(), timezone=""),
            "timezone",
        ),
    ],
)
def test_invalid_configuration_is_rejected(factory: object, message: str) -> None:
    callable_factory = cast("CallableFactory", factory)
    with pytest.raises((TypeError, ValueError), match=message):
        callable_factory()


class CallableFactory(Protocol):
    def __call__(self) -> object: ...


def test_json_values_are_copied_and_transitively_immutable() -> None:
    nested_source: dict[str, JsonInput] = {"name": "before"}
    source: JsonInput = {"items": [1, nested_source]}
    frozen = freeze_json(source)
    cast(dict[str, JsonInput], source)["items"] = []
    nested_source["name"] = "after"

    assert frozen == {"items": (1, {"name": "before"})}
    with pytest.raises(TypeError):
        cast(dict[str, object], frozen)["new"] = "value"
    frozen_items = cast(
        tuple[JsonInput, ...], cast(dict[str, JsonInput], frozen)["items"]
    )
    with pytest.raises(TypeError):
        cast(dict[str, JsonInput], frozen_items[1])["name"] = "mutated"


class _MutableInt(int):
    pass


class _MutableFloat(float):
    pass


class _MutableStr(str):
    pass


class _EqualityImpostor:
    def __eq__(self, other: object) -> bool:
        return True

    def __hash__(self) -> int:
        return hash("deny")


@pytest.mark.parametrize(
    "value",
    [_MutableInt(1), _MutableFloat(1.0), _MutableStr("value")],
)
def test_json_scalar_subclasses_are_rejected(value: object) -> None:
    value.extra = []  # type: ignore[attr-defined]
    with pytest.raises(TypeError, match="exact JSON builtin"):
        freeze_json(cast(JsonInput, value))


def test_manual_time_has_no_mutable_instance_attributes() -> None:
    at_ms = ManualTime(0)
    with pytest.raises(AttributeError):
        at_ms.extra = []  # type: ignore[attr-defined]


def test_literal_and_identifier_equality_impostors_are_rejected() -> None:
    impostor = _EqualityImpostor()
    with pytest.raises((TypeError, ValueError)):
        NetworkConfiguration(cast(Any, impostor))
    with pytest.raises((TypeError, ValueError)):
        ProcessObservation(cast(Any, impostor))
    with pytest.raises((TypeError, ValueError)):
        ConstraintUnsupported(
            cast(ConstraintName, impostor),
            "constraint-unsupported",
            "bad",
        )
    with pytest.raises(TypeError, match="run_id"):
        SeedReceipt(cast(str, _MutableStr("run-contract")), 42)


def test_observation_validates_structure_and_freezes_application_values() -> None:
    observation = _observation()

    assert observation.state == {"count": 1, "items": ("one",)}
    assert observation.events[0].data == {"count": 1}
    with pytest.raises(ValueError, match="focus"):
        UiObservation(
            regions=(),
            focus="missing",
            cursor=Cursor(0, 0, True),
            mode=None,
        )
    with pytest.raises(ValueError, match="rows"):
        Frame(lines=("one",), columns=80, rows=2)
    assert ProcessObservation.running().state == "running"
    assert ProcessObservation.exited(RunFinished.code(0).exit).state == "exited"
    with pytest.raises(ValueError, match="exit"):
        ProcessObservation(state="exited", exit=None)
    with pytest.raises(ValueError, match="state"):
        ProcessObservation(state="invalid", exit=None)  # type: ignore[arg-type]


def test_inputs_and_diagnostics_validate_manual_time() -> None:
    assert KeyInput(at_ms=ManualTime(0), keys=("Control", "c")).keys == (
        "Control",
        "c",
    )
    assert TextInput(at_ms=ManualTime(0), text="hello").text == "hello"
    assert Resize(at_ms=ManualTime(1), columns=100, rows=40).columns == 100
    assert ClockAdvance(at_ms=ManualTime(5), delta_ms=5).delta_ms == 5
    assert Stop(at_ms=ManualTime(5)).at_ms == 5
    assert Diagnostic(at_ms=ManualTime(0), code="notice", message="ok").details is None

    with pytest.raises(ValueError, match="non-negative"):
        ManualTime(-1)
    with pytest.raises(ValueError, match="positive"):
        ClockAdvance(at_ms=ManualTime(0), delta_ms=0)
    with pytest.raises(ValueError, match="positive"):
        Resize(at_ms=ManualTime(0), columns=0, rows=24)
    with pytest.raises(TypeError, match="tuple"):
        KeyInput(at_ms=ManualTime(0), keys=cast(Any, ["Enter"]))
    with pytest.raises(ValueError, match="termverify.key/v1"):
        KeyInput(at_ms=ManualTime(0), keys=("enter",))
    with pytest.raises(ValueError, match="code"):
        Diagnostic(at_ms=ManualTime(0), code="", message="bad")


def test_key_input_is_immutable_and_rejects_noncanonical_chords() -> None:
    input_event = KeyInput(
        at_ms=ManualTime(0),
        keys=("Control", "Alt", "Shift", "Meta", "F12"),
    )

    with pytest.raises(FrozenInstanceError):
        input_event.keys = ("Escape",)  # type: ignore[misc]
    with pytest.raises(TypeError, match="at_ms"):
        KeyInput(at_ms=cast(ManualTime, 0), keys=("Enter",))
    with pytest.raises(ValueError, match="termverify.key/v1"):
        KeyInput(at_ms=ManualTime(0), keys=("Shift", "a"))


def test_receipts_are_constraint_specific_run_bound_and_immutable() -> None:
    constraints = _constraints()

    assert constraints.seed.run_id == "run-contract"
    assert constraints.network.effective == NetworkConfiguration.deny()
    with pytest.raises(FrozenInstanceError):
        constraints.seed.effective = 7  # type: ignore[misc]
    with pytest.raises(TypeError, match="seed"):
        EnforcedConstraints(
            run_id="run-contract",
            requested=_configuration(),
            seed=cast(SeedReceipt, constraints.clock),
            clock=constraints.clock,
            locale=constraints.locale,
            timezone=constraints.timezone,
            terminal=constraints.terminal,
            filesystem=constraints.filesystem,
            network=constraints.network,
        )
    with pytest.raises(ValueError, match="same run"):
        EnforcedConstraints(
            run_id="run-contract",
            requested=_configuration(),
            seed=constraints.seed,
            clock=constraints.clock,
            locale=constraints.locale,
            timezone=constraints.timezone,
            terminal=constraints.terminal,
            filesystem=constraints.filesystem,
            network=NetworkReceipt(
                run_id="another-run",
                effective=constraints.network.effective,
            ),
        )
    with pytest.raises(ValueError, match="requested seed"):
        EnforcedConstraints(
            run_id="run-contract",
            requested=_configuration(),
            seed=SeedReceipt("run-contract", 41),
            clock=constraints.clock,
            locale=constraints.locale,
            timezone=constraints.timezone,
            terminal=constraints.terminal,
            filesystem=constraints.filesystem,
            network=constraints.network,
        )


def test_receipts_cannot_claim_deferred_enforcement_boundaries() -> None:
    with pytest.raises(ValueError, match="terminal capability registry"):
        TerminalReceipt(
            run_id="run-contract",
            effective=TerminalConfiguration(80, 24, ("ansi",)),
        )
    with pytest.raises(ValueError, match="allow-list"):
        NetworkReceipt(
            run_id="run-contract",
            effective=NetworkConfiguration.allow_list((("example.test", 443),)),
        )
    with pytest.raises(ValueError, match="named timezone"):
        TimezoneReceipt(run_id="run-contract", effective="Europe/Berlin")


def test_constraint_unsupported_is_immutable_and_freezes_details() -> None:
    details: JsonInput = {"available": ["seed"]}
    unsupported = ConstraintUnsupported(
        constraint="clock",
        code="constraint-unsupported",
        message="clock port unavailable",
        details=details,
    )
    cast(dict[str, JsonInput], details)["available"] = []

    assert unsupported.details == {"available": ("seed",)}
    with pytest.raises(FrozenInstanceError):
        unsupported.code = "constraint-not-enforced"  # type: ignore[misc]


class _ConstraintPorts:
    def enforce_seed(
        self, run_id: str, requested: int
    ) -> SeedReceipt | ConstraintUnsupported | AdapterFailure:
        return SeedReceipt(run_id, requested)

    def enforce_clock(
        self, run_id: str, requested: ClockConfiguration
    ) -> ClockReceipt | ConstraintUnsupported | AdapterFailure:
        return ClockReceipt(run_id, requested)

    def enforce_locale(
        self, run_id: str, requested: str
    ) -> LocaleReceipt | ConstraintUnsupported | AdapterFailure:
        return LocaleReceipt(run_id, requested)

    def enforce_timezone(
        self, run_id: str, requested: str
    ) -> TimezoneReceipt | ConstraintUnsupported | AdapterFailure:
        return TimezoneReceipt(run_id, requested)

    def enforce_terminal(
        self, run_id: str, requested: TerminalConfiguration
    ) -> TerminalReceipt | ConstraintUnsupported | AdapterFailure:
        return TerminalReceipt(run_id, requested)

    def enforce_filesystem(
        self, run_id: str, requested: FilesystemConfiguration
    ) -> FilesystemReceipt | ConstraintUnsupported | AdapterFailure:
        return FilesystemReceipt(run_id, requested)

    def enforce_network(
        self, run_id: str, requested: NetworkConfiguration
    ) -> NetworkReceipt | ConstraintUnsupported | AdapterFailure:
        return NetworkReceipt(run_id, requested)


def test_constraint_ports_return_constraint_specific_receipts() -> None:
    ports: ConstraintPorts = _ConstraintPorts()
    configuration = _configuration()

    seed = ports.enforce_seed("run-contract", configuration.seed)
    clock = ports.enforce_clock("run-contract", configuration.clock)
    assert isinstance(seed, SeedReceipt)
    assert isinstance(clock, ClockReceipt)
    assert seed.effective == 42
    assert clock.effective.initial_ms == 0


def test_structured_start_outcomes_are_immutable() -> None:
    startup_diagnostic = Diagnostic(ManualTime(0), "startup", "ready")
    started = Started(
        constraints=_constraints(),
        observation=_observation(),
        diagnostics=(startup_diagnostic,),
    )
    unsupported = StartUnsupported(
        run_id="run-contract",
        requested=_configuration(),
        enforced=(started.constraints.seed,),
        constraint="clock",
        code="constraint-unsupported",
        message="clock port unavailable",
    )
    failed = StartFailed(
        run_id="run-contract",
        requested=_configuration(),
        enforced=(started.constraints.seed,),
        failure=AdapterFailure(code="adapter-start-failed", message="failed"),
    )

    assert started.observation.at_ms == 0
    assert started.diagnostics == (startup_diagnostic,)
    assert unsupported.constraint == "clock"
    assert failed.failure.code == "adapter-start-failed"
    with pytest.raises(ValueError, match="order"):
        StartUnsupported(
            run_id="run-contract",
            requested=_configuration(),
            enforced=(started.constraints.clock,),
            constraint="seed",
            code="constraint-unsupported",
            message="bad prefix",
        )
    with pytest.raises(ValueError, match="initial clock"):
        Started(constraints=_constraints(), observation=_observation(at_ms=1))
    with pytest.raises(ValueError, match="unsupported code"):
        StartUnsupported(
            run_id="run-contract",
            requested=_configuration(),
            enforced=(started.constraints.seed,),
            constraint="clock",
            code="other",
            message="bad code",
        )
    with pytest.raises(ValueError, match="requested seed"):
        StartUnsupported(
            run_id="run-contract",
            requested=_configuration(),
            enforced=(SeedReceipt("run-contract", 41),),
            constraint="clock",
            code="constraint-unsupported",
            message="wrong effective value",
        )
    with pytest.raises(ValueError, match="same run"):
        StartUnsupported(
            run_id="run-contract",
            requested=_configuration(),
            enforced=(SeedReceipt("another-run", 42),),
            constraint="clock",
            code="constraint-unsupported",
            message="wrong run",
        )
    with pytest.raises(ValueError, match="same run"):
        StartFailed(
            run_id="run-contract",
            requested=_configuration(),
            enforced=(SeedReceipt("another-run", 42),),
            failure=AdapterFailure(code="adapter-start-failed", message="failed"),
        )
    with pytest.raises(ValueError, match="start failure code"):
        StartFailed(
            run_id="run-contract",
            requested=_configuration(),
            enforced=(),
            failure=AdapterFailure(code="adapter-runtime-failed", message="bad"),
        )


def test_epoch_and_terminal_results_preserve_process_lifecycle() -> None:
    exited = Observation(
        at_ms=ManualTime(0),
        state={},
        events=(),
        ui=_observation().ui,
        process=ProcessObservation.exited(RunFinished.code(0).exit),
    )
    with pytest.raises(ValueError, match="terminal result"):
        EpochCompleted(observation=exited)
    with pytest.raises(ValueError, match="exit evidence"):
        TerminalResult(observation=exited, outcome=RunFinished.code(1))
    with pytest.raises(ValueError, match="runtime failure code"):
        RunFailed(AdapterFailure("adapter-start-failed", "bad phase"))
    with pytest.raises(ValueError, match="exited-process evidence"):
        TerminalResult(
            observation=_observation(),
            outcome=RunFailed(AdapterFailure("adapter-runtime-failed", "failed")),
        )
    with pytest.raises(ValueError, match="report exit"):
        TerminalResult(
            observation=replace(_observation(), process=ProcessObservation.running()),
            outcome=RunFinished.code(0),
        )
    with pytest.raises(ValueError, match="readiness"):
        Started(constraints=_constraints(), observation=exited)

    result = TerminalResult(observation=exited, outcome=RunFinished.code(0))
    assert result.observation == exited
    assert RunFinished.signal("TERM").exit == ExitStatus("signal", "TERM")
    start_result = StartTerminated(constraints=_constraints(), result=result)
    assert start_result.result == result
    with pytest.raises(ValueError, match="subject exit"):
        StartTerminated(
            constraints=_constraints(),
            result=TerminalResult(
                observation=None,
                outcome=RunFailed(AdapterFailure("adapter-runtime-failed", "failed")),
            ),
        )
    with pytest.raises(ValueError, match="initial clock"):
        StartTerminated(
            constraints=_constraints(),
            result=TerminalResult(
                observation=replace(exited, at_ms=ManualTime(1)),
                outcome=RunFinished.code(0),
            ),
        )


def test_started_rejects_mismatched_diagnostic_time() -> None:
    constraints = _constraints()

    with pytest.raises(ValueError, match="diagnostic time"):
        Started(
            constraints=constraints,
            observation=_observation(0),
            diagnostics=(Diagnostic(ManualTime(1), "startup", "late"),),
        )


def test_epoch_completed_rejects_mismatched_diagnostic_time() -> None:
    with pytest.raises(ValueError, match="diagnostic time"):
        EpochCompleted(
            observation=_observation(5),
            diagnostics=(Diagnostic(ManualTime(4), "epoch", "early"),),
        )


def test_terminal_result_rejects_mismatched_diagnostic_time() -> None:
    with pytest.raises(ValueError, match="diagnostic time"):
        TerminalResult(
            observation=_observation(5),
            outcome=RunFinished.code(0),
            diagnostics=(Diagnostic(ManualTime(4), "terminal", "early"),),
        )


def test_start_terminated_rejects_mismatched_diagnostic_without_observation() -> None:
    configuration = replace(
        _configuration(),
        clock=ClockConfiguration(initial_ms=7),
    )
    constraints = _constraints(configuration=configuration)
    result = TerminalResult(
        observation=None,
        outcome=RunFinished.code(0),
        diagnostics=(Diagnostic(ManualTime(8), "terminal", "late"),),
    )
    assert result.observation is None

    with pytest.raises(ValueError, match="diagnostic time"):
        StartTerminated(
            constraints=constraints,
            result=result,
        )


def test_start_failed_rejects_mismatched_diagnostic_after_negotiation() -> None:
    configuration = replace(
        _configuration(),
        clock=ClockConfiguration(initial_ms=7),
    )
    constraints = _constraints(configuration=configuration)
    enforced = (
        constraints.seed,
        constraints.clock,
        constraints.locale,
        constraints.timezone,
        constraints.terminal,
        constraints.filesystem,
        constraints.network,
    )

    with pytest.raises(ValueError, match="diagnostic time"):
        StartFailed(
            run_id=constraints.run_id,
            requested=constraints.requested,
            enforced=enforced,
            failure=AdapterFailure("adapter-start-failed", "failed"),
            diagnostics=(Diagnostic(ManualTime(8), "startup", "late"),),
        )


def test_start_failed_still_forbids_diagnostics_before_complete_negotiation() -> None:
    constraints = _constraints()

    with pytest.raises(ValueError, match="complete negotiation"):
        StartFailed(
            run_id=constraints.run_id,
            requested=constraints.requested,
            enforced=(constraints.seed,),
            failure=AdapterFailure("adapter-start-failed", "failed"),
            diagnostics=(Diagnostic(ManualTime(0), "startup", "message"),),
        )


def test_result_aggregates_accept_matching_diagnostic_times() -> None:
    constraints = _constraints()
    enforced = (
        constraints.seed,
        constraints.clock,
        constraints.locale,
        constraints.timezone,
        constraints.terminal,
        constraints.filesystem,
        constraints.network,
    )
    initial_diagnostic = Diagnostic(ManualTime(0), "startup", "ready")
    epoch_diagnostic = Diagnostic(ManualTime(5), "epoch", "ready")

    assert Started(
        constraints=constraints,
        observation=_observation(0),
        diagnostics=(initial_diagnostic,),
    ).diagnostics == (initial_diagnostic,)
    assert EpochCompleted(
        observation=_observation(5),
        diagnostics=(epoch_diagnostic,),
    ).diagnostics == (epoch_diagnostic,)
    assert TerminalResult(
        observation=_observation(5),
        outcome=RunFinished.code(0),
        diagnostics=(epoch_diagnostic,),
    ).diagnostics == (epoch_diagnostic,)
    assert StartTerminated(
        constraints=constraints,
        result=TerminalResult(
            observation=None,
            outcome=RunFinished.code(0),
            diagnostics=(initial_diagnostic,),
        ),
    ).result.diagnostics == (initial_diagnostic,)
    assert StartFailed(
        run_id=constraints.run_id,
        requested=constraints.requested,
        enforced=enforced,
        failure=AdapterFailure("adapter-start-failed", "failed"),
        diagnostics=(initial_diagnostic,),
    ).diagnostics == (initial_diagnostic,)


class _FakeAdapter:
    def start(self, run_id: str, configuration: RunConfiguration) -> Started:
        assert configuration == _configuration()
        return Started(_constraints(run_id), _observation())

    def dispatch(self, input_event: DispatchInput) -> EpochCompleted:
        return EpochCompleted(observation=_observation(input_event.at_ms))

    def advance_clock(self, input_event: ClockAdvance) -> EpochCompleted:
        return EpochCompleted(observation=_observation(input_event.at_ms))

    def stop(self, input_event: Stop) -> TerminalResult:
        return TerminalResult(
            observation=_observation(input_event.at_ms),
            outcome=RunFinished.code(0),
        )


def test_test_double_can_implement_adapter_contract_without_ambient_state() -> None:
    adapter: Adapter = _FakeAdapter()

    started = adapter.start("run-contract", _configuration())
    assert isinstance(started, Started)
    dispatched = adapter.dispatch(TextInput(ManualTime(0), "hello"))
    assert isinstance(dispatched, EpochCompleted)
    assert dispatched.observation.at_ms == 0
    advanced = adapter.advance_clock(ClockAdvance(ManualTime(5), 5))
    assert isinstance(advanced, EpochCompleted)
    assert advanced.observation.at_ms == 5
    result = adapter.stop(Stop(ManualTime(5)))
    assert isinstance(result, TerminalResult)
    assert result.outcome == RunFinished.code(0)


@pytest.mark.parametrize(
    "factory",
    [
        lambda: freeze_json(float("nan")),
        lambda: freeze_json(cast(JsonInput, object())),
        lambda: ManualTime(cast(int, True)),
        lambda: TerminalConfiguration(80, 24, cast(tuple[str, ...], ["ansi"])),
        lambda: TerminalConfiguration(80, 24, ("",)),
        lambda: FilesystemConfiguration(cast(str, 1)),
        lambda: NetworkEndpoint(cast(str, 1), 80),
        lambda: NetworkEndpoint("example.test", cast(int, True)),
        lambda: NetworkConfiguration(cast(Any, "invalid")),
        lambda: NetworkConfiguration("deny", (NetworkEndpoint("example.test", 80),)),
        lambda: NetworkConfiguration(
            "allow-list", cast(tuple[NetworkEndpoint, ...], (object(),))
        ),
        lambda: NetworkConfiguration.allow_list(
            cast(tuple[tuple[str, int], ...], [("example.test", 80)])
        ),
        lambda: replace(_configuration(), clock=cast(ClockConfiguration, object())),
        lambda: replace(
            _configuration(), terminal=cast(TerminalConfiguration, object())
        ),
        lambda: replace(
            _configuration(), filesystem=cast(FilesystemConfiguration, object())
        ),
        lambda: replace(_configuration(), network=cast(NetworkConfiguration, object())),
        lambda: Cursor(0, 0, cast(bool, 1)),
        lambda: UiObservation(
            cast(tuple[Region, ...], []), None, Cursor(0, 0, True), None
        ),
        lambda: UiObservation(
            (
                Region("same", "one", 0, 0, 1, 1),
                Region("same", "two", 0, 0, 1, 1),
            ),
            None,
            Cursor(0, 0, True),
            None,
        ),
        lambda: UiObservation((), None, cast(Cursor, object()), None),
        lambda: UiObservation((), None, Cursor(0, 0, True), cast(str | None, 1)),
        lambda: Frame(cast(tuple[str, ...], ["line"]), 80, 1),
        lambda: Frame(cast(tuple[str, ...], (1,)), 80, 1),
        lambda: Observation(cast(ManualTime, 0), {}, (), _observation().ui),
        lambda: Observation(
            ManualTime(0), {}, cast(tuple[Event, ...], []), _observation().ui
        ),
        lambda: Observation(ManualTime(0), {}, (), cast(UiObservation, object())),
        lambda: Observation(
            ManualTime(0), {}, (), _observation().ui, cast(Frame, object())
        ),
        lambda: Observation(
            ManualTime(0),
            {},
            (),
            _observation().ui,
            process=cast(ProcessObservation, object()),
        ),
        lambda: Diagnostic(cast(ManualTime, 0), "code", "message"),
        lambda: Diagnostic(ManualTime(0), "code", cast(str, 1)),
        lambda: TextInput(cast(ManualTime, 0), "text"),
        lambda: TextInput(ManualTime(0), cast(str, 1)),
        lambda: Resize(cast(ManualTime, 0), 80, 24),
        lambda: ClockAdvance(cast(ManualTime, 0), 1),
        lambda: Stop(cast(ManualTime, 0)),
        lambda: AdapterFailure("adapter-start-failed", cast(str, 1)),
        lambda: ExitStatus("code", cast(int | str, True)),
        lambda: RunFinished(cast(ExitStatus, object())),
        lambda: SeedReceipt("INVALID RUN", 1),
        lambda: SeedReceipt("run-contract", 2**64),
        lambda: ClockReceipt("run-contract", cast(ClockConfiguration, object())),
        lambda: LocaleReceipt("run-contract", "not_a_locale"),
        lambda: TerminalReceipt("run-contract", cast(TerminalConfiguration, object())),
        lambda: FilesystemReceipt(
            "run-contract", cast(FilesystemConfiguration, object())
        ),
        lambda: NetworkReceipt("run-contract", cast(NetworkConfiguration, object())),
        lambda: Started(cast(EnforcedConstraints, object()), _observation()),
        lambda: Started(_constraints(), cast(Observation, object())),
        lambda: StartUnsupported(
            run_id="run-contract",
            requested=_configuration(),
            enforced=cast(tuple[SeedReceipt], [SeedReceipt("run-contract", 42)]),
            constraint="clock",
            code="constraint-unsupported",
            message="bad tuple",
        ),
        lambda: StartUnsupported(
            run_id="run-contract",
            requested=_configuration(),
            enforced=(),
            constraint=cast(ConstraintName, "invalid"),
            code="constraint-unsupported",
            message="bad constraint",
        ),
        lambda: StartUnsupported(
            run_id="run-contract",
            requested=_configuration(),
            enforced=(),
            constraint="seed",
            code="constraint-unsupported",
            message=cast(str, 1),
        ),
        lambda: StartFailed(
            run_id="run-contract",
            requested=_configuration(),
            enforced=(),
            failure=cast(AdapterFailure, object()),
        ),
        lambda: StartFailed(
            run_id="run-contract",
            requested=_configuration(),
            enforced=(),
            failure=AdapterFailure("adapter-start-failed", "failed"),
            diagnostics=(Diagnostic(ManualTime(0), "startup", "message"),),
        ),
        lambda: EpochCompleted(cast(Observation, object())),
        lambda: EpochCompleted(_observation(), cast(tuple[Diagnostic, ...], [])),
        lambda: TerminalResult(cast(Observation | None, object()), RunFinished.code(0)),
        lambda: TerminalResult(None, cast(RunFinished | RunFailed, object())),
        lambda: StartTerminated(
            cast(EnforcedConstraints, object()),
            TerminalResult(None, RunFinished.code(0)),
        ),
        lambda: StartTerminated(_constraints(), cast(TerminalResult, object())),
    ],
)
def test_invalid_runtime_shapes_fail_closed(factory: CallableFactory) -> None:
    with pytest.raises((TypeError, ValueError)):
        factory()
