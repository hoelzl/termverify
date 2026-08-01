"""Negotiation evidence for the public terminal adapter.

Everything here runs cross-platform against fake bindings and fake constraint
ports: the adapter owns terminal negotiation, delegates the six non-terminal
constraints, and every negotiation failure ends the start before any child is
spawned. Epoch behavior after a complete negotiation is covered in
``test_terminal_epochs``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import cast

import pytest

from termverify import _conpty, _posix_pty
from termverify._conpty import ConptyChild, ConptyGeometryMismatchError
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
from termverify.terminal import (
    ApplyNothingConstraintPorts,
    ConptyBinding,
    PosixPtyBinding,
    TerminalAdapter,
    TerminalBindingPort,
    TerminalChildPort,
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

    def spawn(
        self,
        argv: Sequence[str],
        *,
        rows: int,
        columns: int,
        env_overlay: Mapping[str, str] | None = None,
        cwd: str | None = None,
    ) -> TerminalChildPort:
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

    def apply_seed(
        self, run_id: str, requested: int
    ) -> SeedReceipt | ConstraintUnsupported | AdapterFailure:
        self.calls.append("seed")
        return SeedReceipt(run_id, requested, "delivered", _delivery("seed"))

    def apply_clock(
        self, run_id: str, requested: ClockConfiguration
    ) -> ClockReceipt | ConstraintUnsupported | AdapterFailure:
        self.calls.append("clock")
        return ClockReceipt(run_id, requested, "delivered", _delivery("clock"))

    def apply_locale(
        self, run_id: str, requested: str
    ) -> LocaleReceipt | ConstraintUnsupported | AdapterFailure:
        self.calls.append("locale")
        return LocaleReceipt(run_id, requested, "delivered", _delivery("locale"))

    def apply_timezone(
        self, run_id: str, requested: str
    ) -> TimezoneReceipt | ConstraintUnsupported | AdapterFailure:
        self.calls.append("timezone")
        return TimezoneReceipt(run_id, requested, "delivered", _delivery("timezone"))

    def apply_terminal(
        self, run_id: str, requested: TerminalConfiguration
    ) -> TerminalReceipt | ConstraintUnsupported | AdapterFailure:
        raise AssertionError("terminal enforcement must never be delegated")

    def apply_filesystem(
        self, run_id: str, requested: FilesystemConfiguration
    ) -> FilesystemReceipt | ConstraintUnsupported | AdapterFailure:
        self.calls.append("filesystem")
        return FilesystemReceipt(
            run_id, requested, "delivered", _delivery("filesystem")
        )

    def apply_network(
        self, run_id: str, requested: NetworkConfiguration
    ) -> NetworkReceipt | ConstraintUnsupported | AdapterFailure:
        self.calls.append("network")
        return NetworkReceipt(run_id, requested, "delivered", _delivery("network"))


def _adapter(
    binding: _Binding | None = None,
    ports: ConstraintPorts | None = None,
) -> tuple[TerminalAdapter, _Binding]:
    bound = binding if binding is not None else _Binding()
    if ports is None:
        adapter = TerminalAdapter(("subject",), binding=bound, abort_deadline_ms=60_000)
    else:
        adapter = TerminalAdapter(
            ("subject",),
            binding=bound,
            constraint_ports=ports,
            abort_deadline_ms=60_000,
        )
    return adapter, bound


def test_terminal_adapter_satisfies_the_adapter_protocol() -> None:
    adapter, _ = _adapter()
    checked: Adapter = adapter
    assert checked is adapter


def test_conpty_child_satisfies_the_child_port() -> None:
    child: TerminalChildPort = ConptyChild(object(), 1, 0, 0)
    assert isinstance(child, TerminalChildPort)


def test_native_binding_satisfies_the_binding_port() -> None:
    binding: TerminalBindingPort = ConptyBinding()
    assert isinstance(binding, TerminalBindingPort)


def test_probe_reports_the_spawn_precondition() -> None:
    import os

    expected = os.name == "nt" and _conpty._HAS_PSEUDOCONSOLE
    assert _conpty.is_supported() is expected
    assert ConptyBinding().is_supported() is expected


def test_probe_reports_unsupported_without_pseudoconsole_entry_points(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Being Windows is not the precondition; having ConPTY is.

    Pseudoconsoles arrived in Windows 10 1809. On an older build the spawn
    fails closed, so a probe that answered "supported" would let negotiation
    promise a run that can never start.
    """
    monkeypatch.setattr(_conpty, "_HAS_PSEUDOCONSOLE", False)

    assert _conpty.is_supported() is False
    assert ConptyBinding().is_supported() is False


def test_native_binding_delegates_the_probe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(_conpty, "is_supported", lambda: True)
    assert ConptyBinding().is_supported() is True
    monkeypatch.setattr(_conpty, "is_supported", lambda: False)
    assert ConptyBinding().is_supported() is False


def test_native_binding_delegates_spawn(monkeypatch: pytest.MonkeyPatch) -> None:
    sentinel = ConptyChild(object(), 7, 0, 0)
    recorded: list[
        tuple[tuple[str, ...], int, int, Mapping[str, str] | None, str | None]
    ] = []

    def fake_spawn(
        argv: Sequence[str],
        *,
        rows: int,
        columns: int,
        env_overlay: Mapping[str, str] | None = None,
        cwd: str | None = None,
    ) -> ConptyChild:
        recorded.append((tuple(argv), rows, columns, env_overlay, cwd))
        return sentinel

    monkeypatch.setattr(ConptyChild, "spawn", staticmethod(fake_spawn))

    child = ConptyBinding().spawn(
        ["subject", "--flag"],
        rows=24,
        columns=80,
        env_overlay={"TERMVERIFY_SEED": "42"},
        cwd="C:/sandbox",
    )

    assert child is sentinel
    assert recorded == [
        (("subject", "--flag"), 24, 80, {"TERMVERIFY_SEED": "42"}, "C:/sandbox")
    ]


# --- the POSIX binding's delegation ----------------------------------------
#
# The mirror of the two tests above, and it exists because it did not. The
# round-2 review transposed `rows=columns, columns=rows` in `PosixPtyBinding`
# and the whole suite stayed green: nothing anywhere called either of its
# methods, so the second of the slice's two bindings had its geometry plumbing
# — the very thing the receipt's ``tier="os"`` claim is made about — verified
# by nothing at all. Neither test needs a pty, so neither is waiting on #269.


def test_posix_binding_satisfies_the_binding_port() -> None:
    binding: TerminalBindingPort = PosixPtyBinding()
    assert isinstance(binding, TerminalBindingPort)


def test_posix_binding_delegates_the_probe(monkeypatch: pytest.MonkeyPatch) -> None:
    """Delegation, not a hardcoded answer.

    ``PosixPtyBinding().is_supported()`` is ``False`` on this Windows host and
    ``True`` on Linux, so asserting either constant would make the test pass
    for the wrong reason on one leg. Patching the native probe is what
    distinguishes delegation from a coincidence.
    """
    monkeypatch.setattr(_posix_pty, "is_supported", lambda: True)
    assert PosixPtyBinding().is_supported() is True
    monkeypatch.setattr(_posix_pty, "is_supported", lambda: False)
    assert PosixPtyBinding().is_supported() is False


def test_posix_binding_delegates_spawn(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every argument forwarded, and ``rows``/``columns`` not transposed.

    ``rows`` and ``columns`` are both ``int`` and adjacent in the signature, so
    a swap type-checks, lints clean, and is invisible to every other test in
    the repository. Asymmetric values (24 vs 80) are what make the swap
    observable; equal ones would not be.
    """
    sentinel = object()
    recorded: list[
        tuple[tuple[str, ...], int, int, Mapping[str, str] | None, str | None]
    ] = []

    def fake_spawn(
        argv: Sequence[str],
        *,
        rows: int,
        columns: int,
        env_overlay: Mapping[str, str] | None = None,
        cwd: str | None = None,
    ) -> object:
        recorded.append((tuple(argv), rows, columns, env_overlay, cwd))
        return sentinel

    monkeypatch.setattr(_posix_pty.PosixPtyChild, "spawn", staticmethod(fake_spawn))

    child = PosixPtyBinding().spawn(
        ["subject", "--flag"],
        rows=24,
        columns=80,
        env_overlay={"TERMVERIFY_SEED": "42"},
        cwd="/sandbox",
    )

    assert child is sentinel
    assert recorded == [
        (("subject", "--flag"), 24, 80, {"TERMVERIFY_SEED": "42"}, "/sandbox")
    ]


@pytest.mark.parametrize("constraint", _NON_TERMINAL_CONSTRAINTS)
def test_default_ports_report_not_enforced(constraint: str) -> None:
    ports = ApplyNothingConstraintPorts()
    configuration = _configuration()
    requested = {
        "seed": configuration.seed,
        "clock": configuration.clock,
        "locale": configuration.locale,
        "timezone": configuration.timezone,
        "filesystem": configuration.filesystem,
        "network": configuration.network,
    }[constraint]
    port = getattr(ports, f"apply_{constraint}")

    result = port("run-conpty", requested)

    assert type(result) is ConstraintUnsupported
    assert result.constraint == constraint
    assert result.code == "constraint-not-enforced"
    assert result.message


def test_default_ports_refuse_delegated_terminal_enforcement() -> None:
    result = ApplyNothingConstraintPorts().apply_terminal(
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
    assert result.applied == ()
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

    setattr(ports, f"apply_{constraint}", unsupported)
    adapter, binding = _adapter(ports=ports)

    result = adapter.start("run-conpty", _configuration())

    assert type(result) is StartUnsupported
    assert result.constraint == constraint
    assert result.code == "constraint-not-enforced"
    assert len(result.applied) == prefix_length
    assert ports.calls[-1] == constraint
    assert binding.spawn_calls == 0


def test_unsupported_probe_fails_terminal_negotiation() -> None:
    """The refusal cites the probe, and does not name a platform.

    Until #268 this message said "no ConPTY pseudoconsole support", which was
    a statement the adapter had no evidence for even before the POSIX binding
    existed: what it holds is a ``TerminalBindingPort``, and the only thing it
    learned is that the port's own probe answered no. It is a
    ``StartUnsupported`` message, which the recorder writes into the transcript
    twice — as a ``capability.result`` reason and as the ``run.unsupported``
    message (``recorder.py``) — so on a Linux host with a POSIX binding
    injected the recorded evidence would have blamed a pseudoconsole that was
    never involved.
    """
    ports = _EnforcingPorts()
    adapter, binding = _adapter(binding=_Binding(supported=False), ports=ports)

    result = adapter.start("run-conpty", _configuration())

    assert type(result) is StartUnsupported
    assert result.constraint == "terminal"
    assert result.code == "constraint-unsupported"
    assert len(result.applied) == 4
    assert "binding" in result.message
    assert "unsupported" in result.message
    # No platform, because the adapter cannot see one. Checked as an explicit
    # absence: an assertion on the wording alone would still pass a message
    # that named a platform in the same sentence. Case-folded, because
    # ``"ConPTY" not in message`` is satisfied by ``CONPTY``.
    folded = result.message.casefold()
    for platform in ("conpty", "pseudoconsole", "console", "windows", "posix", "pty"):
        assert platform not in folded, platform
    assert ports.calls == ["seed", "clock", "locale", "timezone"]
    assert binding.probe_calls == 1
    assert binding.spawn_calls == 0


def test_requested_terminal_capabilities_fail_closed() -> None:
    adapter, binding = _adapter(ports=_EnforcingPorts())

    result = adapter.start("run-conpty", _configuration(capabilities=("mouse",)))

    assert type(result) is StartUnsupported
    assert result.constraint == "terminal"
    assert result.code == "constraint-unsupported"
    assert len(result.applied) == 4
    assert binding.spawn_calls == 0


def test_raising_port_yields_start_failed() -> None:
    ports = _EnforcingPorts()

    def broken(
        run_id: str, requested: ClockConfiguration
    ) -> ClockReceipt | ConstraintUnsupported | AdapterFailure:
        raise RuntimeError("port exploded")

    ports.apply_clock = broken  # type: ignore[method-assign]
    adapter, _ = _adapter(ports=ports)

    result = adapter.start("run-conpty", _configuration())

    assert type(result) is StartFailed
    assert result.failure.code == "adapter-start-failed"
    assert len(result.applied) == 1
    assert result.failure.details == {"constraint": "clock"}


def test_raising_probe_yields_start_failed_at_terminal() -> None:
    class _RaisingProbeBinding(_Binding):
        def is_supported(self) -> bool:
            raise RuntimeError("probe exploded")

    adapter, _ = _adapter(binding=_RaisingProbeBinding(), ports=_EnforcingPorts())

    result = adapter.start("run-conpty", _configuration())

    assert type(result) is StartFailed
    assert result.failure.code == "adapter-start-failed"
    assert len(result.applied) == 4
    assert result.failure.details == {"constraint": "terminal"}


def test_mismatched_receipt_yields_start_failed() -> None:
    ports = _EnforcingPorts()

    def wrong_run(
        run_id: str, requested: int
    ) -> SeedReceipt | ConstraintUnsupported | AdapterFailure:
        del run_id
        return SeedReceipt("other-run", requested, "delivered", _delivery("seed"))

    ports.apply_seed = wrong_run  # type: ignore[method-assign]
    adapter, _ = _adapter(ports=ports)

    result = adapter.start("run-conpty", _configuration())

    assert type(result) is StartFailed
    assert result.applied == ()
    assert result.failure.details == {"constraint": "seed"}


def test_complete_negotiation_proceeds_to_exactly_one_spawn() -> None:
    ports = _EnforcingPorts()
    adapter, binding = _adapter(ports=ports)

    result = adapter.start("run-conpty", _configuration())

    assert type(result) is StartFailed
    assert len(result.applied) == 7
    terminal = result.applied[4]
    assert type(terminal) is TerminalReceipt
    assert terminal.run_id == "run-conpty"
    assert terminal.effective == _configuration().terminal
    assert result.failure.code == "adapter-start-failed"
    assert result.failure.details == {
        "during": "spawn",
        "reason": "this negotiation fake refuses to spawn a child",
    }
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
        TerminalAdapter((), binding=binding, abort_deadline_ms=60_000)
    with pytest.raises(TypeError):
        TerminalAdapter(
            cast("tuple[str, ...]", ("subject", 3)),
            binding=binding,
            abort_deadline_ms=60_000,
        )
    with pytest.raises(ValueError):
        TerminalAdapter(("",), binding=binding, abort_deadline_ms=60_000)
    with pytest.raises(TypeError):
        TerminalAdapter(
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


def test_a_geometry_mismatch_yields_a_structured_start_failed() -> None:
    """#228: a console that cannot adopt the request is a geometry failure.

    The failure names what was requested and what the console adopted, not a
    bare "could not be spawned" — the transcript's ``tier="os"`` receipt must
    never stand for a geometry the subject did not run at.
    """

    class _GeometryRefusingBinding(_Binding):
        def spawn(
            self,
            argv: Sequence[str],
            *,
            rows: int,
            columns: int,
            env_overlay: Mapping[str, str] | None = None,
            cwd: str | None = None,
        ) -> TerminalChildPort:
            raise ConptyGeometryMismatchError(
                "requested terminal geometry 100000x10 but the pseudoconsole"
                " adopted 120x30",
                requested=(10, 100_000),
                adopted=(30, 120),
            )

    adapter, _ = _adapter(binding=_GeometryRefusingBinding(), ports=_EnforcingPorts())

    result = adapter.start("run-conpty", _configuration())

    assert type(result) is StartFailed
    assert result.failure.code == "adapter-start-failed"
    assert "geometry" in result.failure.message
    assert result.failure.details == {
        "during": "spawn",
        "terminal-rows": 24,
        "terminal-columns": 80,
        "adopted-rows": 30,
        "adopted-columns": 120,
        "reason": "requested terminal geometry 100000x10 but the pseudoconsole"
        " adopted 120x30",
    }


def test_a_predicted_geometry_refusal_yields_start_failed_without_adopted() -> None:
    """Predictive refusals measured nothing, so the details name no adoption.

    A refusal from the COORD-wrap model happens before any child exists; the
    failure details carry the request and the reason but no adopted size.
    """

    class _PredictingRefusalBinding(_Binding):
        def spawn(
            self,
            argv: Sequence[str],
            *,
            rows: int,
            columns: int,
            env_overlay: Mapping[str, str] | None = None,
            cwd: str | None = None,
        ) -> TerminalChildPort:
            raise ConptyGeometryMismatchError(
                "the requested terminal geometry 100000x10 cannot be adopted:"
                " columns=100000 wraps to -31072 in the console's signed"
                " 16-bit COORD member, and conhost kills the child at console"
                " attach",
                requested=(10, 100_000),
                adopted=None,
            )

    adapter, _ = _adapter(binding=_PredictingRefusalBinding(), ports=_EnforcingPorts())

    result = adapter.start("run-conpty", _configuration())

    assert type(result) is StartFailed
    assert result.failure.code == "adapter-start-failed"
    # Whole-dict equality: the request and the reason are present, and the
    # adopted keys are provably absent — nothing was measured.
    assert result.failure.details == {
        "during": "spawn",
        "terminal-rows": 24,
        "terminal-columns": 80,
        "reason": "the requested terminal geometry 100000x10 cannot be adopted:"
        " columns=100000 wraps to -31072 in the console's signed"
        " 16-bit COORD member, and conhost kills the child at console"
        " attach",
    }
