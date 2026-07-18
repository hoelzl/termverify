"""Public Windows terminal adapter over the ConPTY binding port.

This module implements the negotiation skeleton authorized as slice 2 of the
accepted ConPTY adapter design (`docs/agent/design/conpty-adapter-design.md`):
the ``ConptyBindingPort``/``ConptyChildPort`` protocols, the adapter
constructor surface, and truthful constraint negotiation. Epoch machinery is
slice 3; until it lands, a fully negotiated start fails closed with a
structured ``StartFailed`` disclosing the unimplemented tail, and no child is
ever spawned. Nothing here claims a successful run exists.

All logic is cross-platform and testable against fake bindings and ports;
``termverify._conpty`` remains the only native, ratchet-excluded boundary.

Negotiation is truthful by construction:

- The adapter owns the ``terminal`` constraint and never delegates it:
  dimensions are an OS-level parameter of pseudoconsole creation, platform
  support is decided by the binding port's explicit probe before any spawn,
  and requested terminal capabilities are rejected fail-closed because the
  capability registry is not activated.
- The six non-terminal constraints belong to injected ``ConstraintPorts``.
  The shipped default, :class:`UnenforcedConstraintPorts`, reports every one
  of them ``constraint-not-enforced`` — no OS mechanism at this boundary
  enforces them — so ``start()`` with defaults ends as
  ``StartUnsupported(constraint="seed")`` before any child exists. Verified
  terminal runs require ports that genuinely enforce their constraint.
"""

from __future__ import annotations

from collections.abc import Sequence
from threading import Lock
from typing import Literal, Protocol, runtime_checkable

from termverify._negotiation import negotiate
from termverify.adapter import (
    AdapterFailure,
    ClockAdvance,
    ClockConfiguration,
    ClockReceipt,
    ConstraintPorts,
    ConstraintUnsupported,
    DispatchInput,
    EpochResult,
    FilesystemConfiguration,
    FilesystemReceipt,
    KeyInput,
    LocaleReceipt,
    NetworkConfiguration,
    NetworkReceipt,
    Resize,
    RunConfiguration,
    SeedReceipt,
    StartFailed,
    StartResult,
    Stop,
    TerminalConfiguration,
    TerminalReceipt,
    TerminalResult,
    TextInput,
    TimezoneReceipt,
    _validate_run_id,
)

__all__ = [
    "ConptyAdapter",
    "ConptyBinding",
    "ConptyBindingPort",
    "ConptyChildPort",
    "UnenforcedConstraintPorts",
]

_State = Literal["created", "negotiating", "terminal"]


@runtime_checkable
class ConptyChildPort(Protocol):
    """Per-child binding surface, shaped exactly like ``ConptyChild``."""

    @property
    def pid(self) -> int: ...

    @property
    def exit_status(self) -> int | None: ...

    def read(self) -> str: ...

    def write(self, text: str) -> None: ...

    def resize(self, *, rows: int, columns: int) -> None: ...

    def is_alive(self) -> bool: ...

    def close(self, *, force: bool) -> None: ...


@runtime_checkable
class ConptyBindingPort(Protocol):
    """Injected boundary to the native ConPTY binding.

    The explicit support probe makes platform support answerable at
    negotiation time — before any spawn — without the adapter reading
    ambient platform state. Fake bindings supply their own probe, so both
    negotiation outcomes are drivable on every platform.
    """

    def is_supported(self) -> bool: ...

    def spawn(
        self, argv: Sequence[str], *, rows: int, columns: int
    ) -> ConptyChildPort: ...


class ConptyBinding:
    """Default binding port delegating to ``termverify._conpty``."""

    def is_supported(self) -> bool:
        from termverify import _conpty

        return _conpty.is_supported()

    def spawn(self, argv: Sequence[str], *, rows: int, columns: int) -> ConptyChildPort:
        from termverify._conpty import ConptyChild

        return ConptyChild.spawn(argv, rows=rows, columns=columns)


class UnenforcedConstraintPorts:
    """Truthful default ports: nothing is enforced at the ConPTY boundary."""

    def enforce_seed(
        self, run_id: str, requested: int
    ) -> SeedReceipt | ConstraintUnsupported | AdapterFailure:
        del run_id, requested
        return ConstraintUnsupported(
            "seed",
            "constraint-not-enforced",
            "no OS mechanism binds a subject's RNG through a pseudoconsole;"
            " environment injection is subject cooperation, not enforcement",
        )

    def enforce_clock(
        self, run_id: str, requested: ClockConfiguration
    ) -> ClockReceipt | ConstraintUnsupported | AdapterFailure:
        del run_id, requested
        return ConstraintUnsupported(
            "clock",
            "constraint-not-enforced",
            "the child runs on the ambient wall clock; manual-time injection"
            " is subject cooperation, not enforcement",
        )

    def enforce_locale(
        self, run_id: str, requested: str
    ) -> LocaleReceipt | ConstraintUnsupported | AdapterFailure:
        del run_id, requested
        return ConstraintUnsupported(
            "locale",
            "constraint-not-enforced",
            "locale environment variables are advisory to the child, not"
            " boundary enforcement",
        )

    def enforce_timezone(
        self, run_id: str, requested: str
    ) -> TimezoneReceipt | ConstraintUnsupported | AdapterFailure:
        del run_id, requested
        return ConstraintUnsupported(
            "timezone",
            "constraint-not-enforced",
            "timezone environment variables are advisory to the child, and"
            " named-timezone enforcement remains blocked on the owner",
        )

    def enforce_terminal(
        self, run_id: str, requested: TerminalConfiguration
    ) -> TerminalReceipt | ConstraintUnsupported | AdapterFailure:
        del run_id, requested
        return ConstraintUnsupported(
            "terminal",
            "constraint-unsupported",
            "terminal enforcement is owned by the ConPTY adapter and cannot"
            " be delegated to injected ports",
        )

    def enforce_filesystem(
        self, run_id: str, requested: FilesystemConfiguration
    ) -> FilesystemReceipt | ConstraintUnsupported | AdapterFailure:
        del run_id, requested
        return ConstraintUnsupported(
            "filesystem",
            "constraint-not-enforced",
            "filesystem containment enforcement is an owner-blocked"
            " workstream; no containment is enforced at this boundary",
        )

    def enforce_network(
        self, run_id: str, requested: NetworkConfiguration
    ) -> NetworkReceipt | ConstraintUnsupported | AdapterFailure:
        del run_id, requested
        return ConstraintUnsupported(
            "network",
            "constraint-not-enforced",
            "the job object does not block network access; network denial is"
            " not provable at this boundary",
        )


def _validate_argv(argv: Sequence[str]) -> tuple[str, ...]:
    if isinstance(argv, str) or not isinstance(argv, Sequence):
        raise TypeError("argv must be a sequence of strings")
    values = tuple(argv)
    if any(type(value) is not str for value in values):
        raise TypeError("argv must contain only strings")
    if not values:
        raise ValueError("argv must name a subject command")
    if any(not value for value in values):
        raise ValueError("argv must contain non-empty strings")
    return values


class ConptyAdapter:
    """Drive one terminal subject through the injected ConPTY binding port.

    Slice-2 skeleton: negotiation only. The subject command line is bound at
    construction, exactly as the direct adapter binds its application.
    """

    def __init__(
        self,
        argv: Sequence[str],
        *,
        binding: ConptyBindingPort,
        constraint_ports: ConstraintPorts | None = None,
    ) -> None:
        self._argv = _validate_argv(argv)
        self._binding = binding
        if constraint_ports is None:
            constraint_ports = UnenforcedConstraintPorts()
        self._constraints: ConstraintPorts = constraint_ports
        self._state: _State = "created"
        self._state_lock = Lock()

    def _enforce_terminal(
        self, run_id: str, requested: TerminalConfiguration
    ) -> TerminalReceipt | ConstraintUnsupported:
        if requested.capabilities:
            return ConstraintUnsupported(
                "terminal",
                "constraint-unsupported",
                "the terminal capability registry is not activated; requested"
                " capabilities cannot be enforced",
            )
        if not self._binding.is_supported():
            return ConstraintUnsupported(
                "terminal",
                "constraint-unsupported",
                "this host provides no ConPTY pseudoconsole support",
            )
        return TerminalReceipt(run_id, requested)

    def start(self, run_id: str, configuration: RunConfiguration) -> StartResult:
        if type(configuration) is not RunConfiguration:
            raise TypeError("configuration must be RunConfiguration")
        _validate_run_id(run_id)
        with self._state_lock:
            if self._state != "created":
                raise RuntimeError("ConPTY adapter has already started")
            self._state = "negotiating"
        negotiated = negotiate(
            run_id,
            configuration,
            (
                lambda: self._constraints.enforce_seed(run_id, configuration.seed),
                lambda: self._constraints.enforce_clock(run_id, configuration.clock),
                lambda: self._constraints.enforce_locale(run_id, configuration.locale),
                lambda: self._constraints.enforce_timezone(
                    run_id, configuration.timezone
                ),
                lambda: self._enforce_terminal(run_id, configuration.terminal),
                lambda: self._constraints.enforce_filesystem(
                    run_id, configuration.filesystem
                ),
                lambda: self._constraints.enforce_network(
                    run_id, configuration.network
                ),
            ),
        )
        with self._state_lock:
            self._state = "terminal"
        if not isinstance(negotiated, tuple):
            return negotiated
        # Slice-2 boundary: every constraint produced a receipt, but the
        # epoch machinery that could truthfully produce readiness evidence
        # does not exist yet, so the start fails closed before any spawn.
        return StartFailed(
            run_id=run_id,
            requested=configuration,
            enforced=negotiated,
            failure=AdapterFailure(
                "adapter-start-failed",
                "the ConPTY adapter epoch machinery is not implemented;"
                " no child was spawned",
                {"unimplemented": "epoch-machinery"},
            ),
        )

    def dispatch(self, input_event: DispatchInput) -> EpochResult:
        if type(input_event) not in (KeyInput, TextInput, Resize):
            raise TypeError("dispatch input must be KeyInput, TextInput, or Resize")
        raise RuntimeError("ConPTY adapter is not idle")

    def advance_clock(self, input_event: ClockAdvance) -> EpochResult:
        if type(input_event) is not ClockAdvance:
            raise TypeError("clock input must be ClockAdvance")
        raise RuntimeError("ConPTY adapter is not idle")

    def stop(self, input_event: Stop) -> TerminalResult:
        if type(input_event) is not Stop:
            raise TypeError("stop input must be Stop")
        raise RuntimeError("ConPTY adapter is not idle")
