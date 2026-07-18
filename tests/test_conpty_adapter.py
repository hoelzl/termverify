"""Negotiation evidence for the public ConPTY adapter.

Everything here runs cross-platform against fake bindings and fake constraint
ports: the adapter owns terminal negotiation, delegates the six non-terminal
constraints, and every negotiation failure ends the start before any child is
spawned. Epoch behavior after a complete negotiation is covered in
``test_conpty_epochs``.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import cast

import pytest

from termverify import _conpty
from termverify._conpty import ConptyChild
from termverify.adapter import (
    Adapter,
    AdapterFailure,
    ClockAdvance,
    ClockConfiguration,
    ClockReceipt,
    ConstraintName,
    ConstraintPorts,
    ConstraintUnsupported,
    DeliveryRecord,
    FilesystemConfiguration,
    FilesystemReceipt,
    LocaleReceipt,
    ManualTime,
    NetworkConfiguration,
    NetworkReceipt,
    Resize,
    RunConfiguration,
    SeedReceipt,
    StartFailed,
    StartUnsupported,
    Stop,
    TerminalConfiguration,
    TerminalReceipt,
    TextInput,
    TimezoneReceipt,
)
from termverify.conpty import (
    ConptyAdapter,
    ConptyBinding,
    ConptyBindingPort,
    ConptyChildPort,
    UnenforcedConstraintPorts,
)

_NON_TERMINAL_CONSTRAINTS = (
    "seed",
    "clock",
    "locale",
    "timezone",
    "filesystem",
    "network",
)


def _configuration(capabilities: tuple[str, ...] = ()) -> RunConfiguration:
    return RunConfiguration(
        seed=42,
        clock=ClockConfiguration(initial_ms=0),
        locale="en-US",
        timezone="UTC",
        terminal=TerminalConfiguration(columns=80, rows=24, capabilities=capabilities),
        filesystem=FilesystemConfiguration(root_id="fixture-root"),
        network=NetworkConfiguration.deny(),
    )


class _Binding:
    """Fake binding: configurable probe, refuses to spawn a child."""

    def __init__(self, *, supported: bool = True) -> None:
        self._supported = supported
        self.probe_calls = 0
        self.spawn_calls = 0

    def is_supported(self) -> bool:
        self.probe_calls += 1
        return self._supported

    def spawn(self, argv: Sequence[str], *, rows: int, columns: int) -> ConptyChildPort:
        self.spawn_calls += 1
        raise OSError("this negotiation fake refuses to spawn a child")


def _delivery(constraint: str) -> DeliveryRecord:
    """One structurally valid fake delivery record per constraint."""
    if constraint == "filesystem":
        return DeliveryRecord(
            env={"TERMVERIFY_FS_ROOT": "C:\\sandbox\\fixture-root"},
            cwd="C:\\sandbox\\fixture-root",
        )
    return DeliveryRecord(env={f"TERMVERIFY_{constraint.upper()}": "value"})


class _EnforcingPorts:
    """Fake injected ports stating the delivered tier for every constraint."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def enforce_seed(
        self, run_id: str, requested: int
    ) -> SeedReceipt | ConstraintUnsupported | AdapterFailure:
        self.calls.append("seed")
        return SeedReceipt(run_id, requested, "delivered", _delivery("seed"))

    def enforce_clock(
        self, run_id: str, requested: ClockConfiguration
    ) -> ClockReceipt | ConstraintUnsupported | AdapterFailure:
        self.calls.append("clock")
        return ClockReceipt(run_id, requested, "delivered", _delivery("clock"))

    def enforce_locale(
        self, run_id: str, requested: str
    ) -> LocaleReceipt | ConstraintUnsupported | AdapterFailure:
        self.calls.append("locale")
        return LocaleReceipt(run_id, requested, "delivered", _delivery("locale"))

    def enforce_timezone(
        self, run_id: str, requested: str
    ) -> TimezoneReceipt | ConstraintUnsupported | AdapterFailure:
        self.calls.append("timezone")
        return TimezoneReceipt(run_id, requested, "delivered", _delivery("timezone"))

    def enforce_terminal(
        self, run_id: str, requested: TerminalConfiguration
    ) -> TerminalReceipt | ConstraintUnsupported | AdapterFailure:
        raise AssertionError("terminal enforcement must never be delegated")

    def enforce_filesystem(
        self, run_id: str, requested: FilesystemConfiguration
    ) -> FilesystemReceipt | ConstraintUnsupported | AdapterFailure:
        self.calls.append("filesystem")
        return FilesystemReceipt(
            run_id, requested, "delivered", _delivery("filesystem")
        )

    def enforce_network(
        self, run_id: str, requested: NetworkConfiguration
    ) -> NetworkReceipt | ConstraintUnsupported | AdapterFailure:
        self.calls.append("network")
        return NetworkReceipt(run_id, requested, "delivered", _delivery("network"))


def _adapter(
    binding: _Binding | None = None,
    ports: ConstraintPorts | None = None,
) -> tuple[ConptyAdapter, _Binding]:
    bound = binding if binding is not None else _Binding()
    if ports is None:
        adapter = ConptyAdapter(("subject",), binding=bound, abort_deadline_ms=60_000)
    else:
        adapter = ConptyAdapter(
            ("subject",),
            binding=bound,
            constraint_ports=ports,
            abort_deadline_ms=60_000,
        )
    return adapter, bound


def test_conpty_adapter_satisfies_the_adapter_protocol() -> None:
    adapter, _ = _adapter()
    checked: Adapter = adapter
    assert checked is adapter


def test_conpty_child_satisfies_the_child_port() -> None:
    child: ConptyChildPort = ConptyChild(object(), 1, 0, 0)
    assert isinstance(child, ConptyChildPort)


def test_native_binding_satisfies_the_binding_port() -> None:
    binding: ConptyBindingPort = ConptyBinding()
    assert isinstance(binding, ConptyBindingPort)


def test_probe_reports_the_spawn_precondition() -> None:
    import os

    assert _conpty.is_supported() is (os.name == "nt")
    assert ConptyBinding().is_supported() is (os.name == "nt")


def test_native_binding_delegates_the_probe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(_conpty, "is_supported", lambda: True)
    assert ConptyBinding().is_supported() is True
    monkeypatch.setattr(_conpty, "is_supported", lambda: False)
    assert ConptyBinding().is_supported() is False


def test_native_binding_delegates_spawn(monkeypatch: pytest.MonkeyPatch) -> None:
    sentinel = ConptyChild(object(), 7, 0, 0)
    recorded: list[tuple[tuple[str, ...], int, int]] = []

    def fake_spawn(argv: Sequence[str], *, rows: int, columns: int) -> ConptyChild:
        recorded.append((tuple(argv), rows, columns))
        return sentinel

    monkeypatch.setattr(ConptyChild, "spawn", staticmethod(fake_spawn))

    child = ConptyBinding().spawn(["subject", "--flag"], rows=24, columns=80)

    assert child is sentinel
    assert recorded == [(("subject", "--flag"), 24, 80)]


@pytest.mark.parametrize("constraint", _NON_TERMINAL_CONSTRAINTS)
def test_default_ports_report_not_enforced(constraint: str) -> None:
    ports = UnenforcedConstraintPorts()
    configuration = _configuration()
    requested = {
        "seed": configuration.seed,
        "clock": configuration.clock,
        "locale": configuration.locale,
        "timezone": configuration.timezone,
        "filesystem": configuration.filesystem,
        "network": configuration.network,
    }[constraint]
    enforce = getattr(ports, f"enforce_{constraint}")

    result = enforce("run-conpty", requested)

    assert type(result) is ConstraintUnsupported
    assert result.constraint == constraint
    assert result.code == "constraint-not-enforced"
    assert result.message


def test_default_ports_refuse_delegated_terminal_enforcement() -> None:
    result = UnenforcedConstraintPorts().enforce_terminal(
        "run-conpty", _configuration().terminal
    )

    assert type(result) is ConstraintUnsupported
    assert result.constraint == "terminal"
    assert result.code == "constraint-unsupported"


def test_default_start_fails_closed_at_seed_without_spawning() -> None:
    adapter, binding = _adapter()

    result = adapter.start("run-conpty", _configuration())

    assert type(result) is StartUnsupported
    assert result.run_id == "run-conpty"
    assert result.requested == _configuration()
    assert result.constraint == "seed"
    assert result.code == "constraint-not-enforced"
    assert result.enforced == ()
    assert binding.spawn_calls == 0


@pytest.mark.parametrize(
    ("constraint", "prefix_length"),
    [
        ("seed", 0),
        ("clock", 1),
        ("locale", 2),
        ("timezone", 3),
        ("filesystem", 5),
        ("network", 6),
    ],
)
def test_negotiation_stops_at_first_unsupported_port_constraint(
    constraint: str, prefix_length: int
) -> None:
    ports = _EnforcingPorts()

    def unsupported(*args: object) -> ConstraintUnsupported:
        del args
        ports.calls.append(constraint)
        return ConstraintUnsupported(
            cast(ConstraintName, constraint),
            "constraint-not-enforced",
            "not enforced by this fixture",
        )

    setattr(ports, f"enforce_{constraint}", unsupported)
    adapter, binding = _adapter(ports=ports)

    result = adapter.start("run-conpty", _configuration())

    assert type(result) is StartUnsupported
    assert result.constraint == constraint
    assert result.code == "constraint-not-enforced"
    assert len(result.enforced) == prefix_length
    assert ports.calls[-1] == constraint
    assert binding.spawn_calls == 0


def test_unsupported_probe_fails_terminal_negotiation() -> None:
    ports = _EnforcingPorts()
    adapter, binding = _adapter(binding=_Binding(supported=False), ports=ports)

    result = adapter.start("run-conpty", _configuration())

    assert type(result) is StartUnsupported
    assert result.constraint == "terminal"
    assert result.code == "constraint-unsupported"
    assert len(result.enforced) == 4
    assert "ConPTY" in result.message
    assert ports.calls == ["seed", "clock", "locale", "timezone"]
    assert binding.probe_calls == 1
    assert binding.spawn_calls == 0


def test_requested_terminal_capabilities_fail_closed() -> None:
    adapter, binding = _adapter(ports=_EnforcingPorts())

    result = adapter.start("run-conpty", _configuration(capabilities=("mouse",)))

    assert type(result) is StartUnsupported
    assert result.constraint == "terminal"
    assert result.code == "constraint-unsupported"
    assert len(result.enforced) == 4
    assert binding.spawn_calls == 0


def test_raising_port_yields_start_failed() -> None:
    ports = _EnforcingPorts()

    def broken(
        run_id: str, requested: ClockConfiguration
    ) -> ClockReceipt | ConstraintUnsupported | AdapterFailure:
        raise RuntimeError("port exploded")

    ports.enforce_clock = broken  # type: ignore[method-assign]
    adapter, _ = _adapter(ports=ports)

    result = adapter.start("run-conpty", _configuration())

    assert type(result) is StartFailed
    assert result.failure.code == "adapter-start-failed"
    assert len(result.enforced) == 1
    assert result.failure.details == {"constraint": "clock"}


def test_raising_probe_yields_start_failed_at_terminal() -> None:
    class _RaisingProbeBinding(_Binding):
        def is_supported(self) -> bool:
            raise RuntimeError("probe exploded")

    adapter, _ = _adapter(binding=_RaisingProbeBinding(), ports=_EnforcingPorts())

    result = adapter.start("run-conpty", _configuration())

    assert type(result) is StartFailed
    assert result.failure.code == "adapter-start-failed"
    assert len(result.enforced) == 4
    assert result.failure.details == {"constraint": "terminal"}


def test_mismatched_receipt_yields_start_failed() -> None:
    ports = _EnforcingPorts()

    def wrong_run(
        run_id: str, requested: int
    ) -> SeedReceipt | ConstraintUnsupported | AdapterFailure:
        del run_id
        return SeedReceipt("other-run", requested, "delivered", _delivery("seed"))

    ports.enforce_seed = wrong_run  # type: ignore[method-assign]
    adapter, _ = _adapter(ports=ports)

    result = adapter.start("run-conpty", _configuration())

    assert type(result) is StartFailed
    assert result.enforced == ()
    assert result.failure.details == {"constraint": "seed"}


def test_complete_negotiation_proceeds_to_exactly_one_spawn() -> None:
    ports = _EnforcingPorts()
    adapter, binding = _adapter(ports=ports)

    result = adapter.start("run-conpty", _configuration())

    assert type(result) is StartFailed
    assert len(result.enforced) == 7
    terminal = result.enforced[4]
    assert type(terminal) is TerminalReceipt
    assert terminal.run_id == "run-conpty"
    assert terminal.effective == _configuration().terminal
    assert result.failure.code == "adapter-start-failed"
    assert result.failure.details == {"during": "spawn"}
    assert ports.calls == [
        "seed",
        "clock",
        "locale",
        "timezone",
        "filesystem",
        "network",
    ]
    assert binding.probe_calls == 1
    assert binding.spawn_calls == 1


def test_start_validates_inputs() -> None:
    adapter, _ = _adapter()

    with pytest.raises(TypeError):
        adapter.start("run-conpty", cast("RunConfiguration", object()))
    with pytest.raises(ValueError):
        adapter.start("Bad Run Id", _configuration())


def test_start_is_single_use() -> None:
    adapter, _ = _adapter()
    adapter.start("run-conpty", _configuration())

    with pytest.raises(RuntimeError):
        adapter.start("run-conpty", _configuration())


def test_constructor_validates_argv() -> None:
    binding = _Binding()

    with pytest.raises(ValueError):
        ConptyAdapter((), binding=binding, abort_deadline_ms=60_000)
    with pytest.raises(TypeError):
        ConptyAdapter(
            cast("tuple[str, ...]", ("subject", 3)),
            binding=binding,
            abort_deadline_ms=60_000,
        )
    with pytest.raises(ValueError):
        ConptyAdapter(("",), binding=binding, abort_deadline_ms=60_000)
    with pytest.raises(TypeError):
        ConptyAdapter(
            cast("tuple[str, ...]", "subject"),
            binding=binding,
            abort_deadline_ms=60_000,
        )


@pytest.mark.parametrize("started", [False, True])
def test_epoch_operations_require_an_idle_adapter(started: bool) -> None:
    adapter, _ = _adapter()
    if started:
        adapter.start("run-conpty", _configuration())

    with pytest.raises(RuntimeError):
        adapter.dispatch(TextInput(ManualTime(0), "x"))
    with pytest.raises(RuntimeError):
        adapter.dispatch(Resize(ManualTime(0), columns=80, rows=24))
    with pytest.raises(RuntimeError):
        adapter.advance_clock(ClockAdvance(ManualTime(5), delta_ms=5))
    with pytest.raises(RuntimeError):
        adapter.stop(Stop(ManualTime(0)))


def test_epoch_operations_validate_input_types() -> None:
    adapter, _ = _adapter()

    with pytest.raises(TypeError):
        adapter.dispatch(cast("TextInput", object()))
    with pytest.raises(TypeError):
        adapter.advance_clock(cast("ClockAdvance", object()))
    with pytest.raises(TypeError):
        adapter.stop(cast("Stop", object()))
