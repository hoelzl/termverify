"""Public Windows terminal adapter over the ConPTY binding port.

This module implements slices 2 and 3 of the accepted ConPTY adapter design
(`docs/agent/design/conpty-adapter-design.md`): the ``ConptyBindingPort``/
``ConptyChildPort`` protocols, truthful constraint negotiation, and the epoch
machinery — readiness-marker protocol, epoch loop, failure classification,
watchdog-driven abort deadline, and forced stop teardown. All logic is
cross-platform and testable against fake bindings, normalizers, and watchdog
triggers; ``termverify._conpty`` remains the only native, ratchet-excluded
boundary. Windows integration evidence for the real path (slice 4) lives in
``tests/test_conpty_integration.py``: end-to-end start/text/resize/exit,
forced stop, and deadline abort against a cooperative fixture subject on the
Windows CI matrix.

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
  ``StartUnsupported(constraint="seed")`` before any child exists.
- Every receipt states its `termverify.enforcement-tier/v1` tier, validated
  against the fail-closed authorization matrix: the adapter's own terminal
  negotiation states ``os`` (an OS-level pseudoconsole parameter, proven on
  the Windows matrix), and injected ports may state only ``delivered`` —
  exact recorded values placed in the subject's spawn environment, honored
  only by subject cooperation. The opt-in ports that emit that tier live in
  ``termverify.cooperation``; the spawn is evidence-driven, with the child's
  environment overlay and working directory assembled from the validated
  receipts' delivery records under fail-closed disjointness invariants.

Readiness and quiescence are defined only by observable evidence:

- A verified subject cooperates by emitting an explicit readiness marker —
  after startup and after processing each input. The adapter scans the
  decoded output stream for the configured marker in stream order; raw
  chunks are always fed to the normalizer unmodified and retained as ordered
  ``terminal.output`` events, so replaying the normalizer over the raw
  evidence reproduces the frames.
- :data:`READINESS_MARKER_DEFAULT` is a private-use OSC sequence. The
  Windows integration evidence shows ConPTY relaying it verbatim through
  the raw output stream, so the default is no longer provisional; the
  marker remains configurable, and a printable marker has its own
  frame-visibility and replay evidence.
- Native end-of-stream plus the observed native exit record ends the run
  truthfully; a missing exit record is a structured failure, never a
  fabricated exit.
- Wall-clock silence is never evidence. The only wall-clock input is the
  mandatory, explicitly configured abort deadline: a watchdog armed before
  each blocking read force-closes the binding when it expires, which always
  produces a structured failure disclosing the deadline policy and never a
  successful epoch. Hosts must budget the deadline above the disclosed
  DA-stall floor: conhost defers client output while its unanswered
  ``CSI c`` device-attributes query waits (measured ~3.1 s; see the
  DA-stall disclosure in the adapter design document), so a deadline at or
  below that floor plus spawn overhead fails every real start by policy.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Mapping, Sequence
from typing import Final, Literal, Protocol, cast, runtime_checkable

from termverify._conpty import (
    ConptyClosedError,
    ConptyConcurrentIOError,
    ConptyEndOfStreamError,
)
from termverify._negotiation import AuthorizedTiers, negotiate
from termverify.adapter import (
    AdapterFailure,
    ClockAdvance,
    ClockConfiguration,
    ClockReceipt,
    ConstraintPorts,
    ConstraintUnsupported,
    DeliveryRecord,
    Diagnostic,
    DispatchInput,
    EnforcedConstraints,
    EpochCompleted,
    EpochResult,
    Event,
    ExitStatus,
    FilesystemConfiguration,
    FilesystemReceipt,
    JsonInput,
    KeyInput,
    LocaleReceipt,
    ManualTime,
    NetworkConfiguration,
    NetworkReceipt,
    Observation,
    ProcessObservation,
    Resize,
    RunConfiguration,
    RunFailed,
    RunFinished,
    SeedReceipt,
    Started,
    StartFailed,
    StartResult,
    StartTerminated,
    Stop,
    TerminalConfiguration,
    TerminalReceipt,
    TerminalResult,
    TextInput,
    TimezoneReceipt,
    UiObservation,
    _validate_run_id,
)
from termverify.vt import ScreenSnapshot, TerminalOutputNormalizer, VtScreenNormalizer

__all__ = [
    "READINESS_MARKER_DEFAULT",
    "ConptyAdapter",
    "ConptyBinding",
    "ConptyBindingPort",
    "ConptyChildPort",
    "ConptyWatchdogPort",
    "NormalizerFactory",
    "TimerWatchdog",
    "UnenforcedConstraintPorts",
]

#: Default readiness marker: a private-use OSC sequence (OSC … ST) that a
#: compliant screen model consumes without rendering. Windows integration
#: evidence (``tests/test_conpty_integration.py``) shows ConPTY relaying
#: this exact sequence verbatim, so the default carries a passthrough claim
#: backed by the CI matrix. Hosts can configure any exact non-empty string
#: instead.
READINESS_MARKER_DEFAULT: Final = "\x1b]7791;ready\x1b\\"

#: The `termverify.enforcement-tier/v1` authorization matrix row for the
#: ConPTY architecture, in constraint order: the adapter's own terminal
#: negotiation emits ``os`` (dimensions are a pseudoconsole creation/resize
#: parameter, proven by child observation on the Windows matrix) and injected
#: constraint ports may state only ``delivered``. Any other tier is a
#: contract breach rejected as a structured ``StartFailed``.
_AUTHORIZED_TIERS: AuthorizedTiers = (
    "delivered",
    "delivered",
    "delivered",
    "delivered",
    "os",
    "delivered",
    "delivered",
)

_State = Literal[
    "created",
    "negotiating",
    "initializing",
    "idle",
    "active",
    "stopping",
    "terminal",
]


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
        self,
        argv: Sequence[str],
        *,
        rows: int,
        columns: int,
        env_overlay: Mapping[str, str] | None = None,
        cwd: str | None = None,
    ) -> ConptyChildPort: ...


@runtime_checkable
class NormalizerFactory(Protocol):
    """Constructs one run's output normalizer at the initial dimensions."""

    def __call__(self, *, rows: int, columns: int) -> TerminalOutputNormalizer: ...


@runtime_checkable
class ConptyWatchdogPort(Protocol):
    """Injectable abort-deadline trigger.

    ``arm`` schedules ``expire`` to run once the deadline elapses and
    returns a disarm callable. The trigger is injectable so the deadline
    classification path is fully testable against fakes; the shipped
    default is :class:`TimerWatchdog`.
    """

    def arm(
        self, deadline_ms: int, expire: Callable[[], None]
    ) -> Callable[[], None]: ...


class TimerWatchdog:
    """Default wall-clock watchdog for the configured abort deadline."""

    def arm(self, deadline_ms: int, expire: Callable[[], None]) -> Callable[[], None]:
        timer = threading.Timer(deadline_ms / 1000.0, expire)
        timer.daemon = True
        timer.start()
        return timer.cancel


class ConptyBinding:
    """Default binding port delegating to ``termverify._conpty``."""

    def is_supported(self) -> bool:
        from termverify import _conpty

        return _conpty.is_supported()

    def spawn(
        self,
        argv: Sequence[str],
        *,
        rows: int,
        columns: int,
        env_overlay: Mapping[str, str] | None = None,
        cwd: str | None = None,
    ) -> ConptyChildPort:
        from termverify._conpty import ConptyChild

        return ConptyChild.spawn(
            argv, rows=rows, columns=columns, env_overlay=env_overlay, cwd=cwd
        )


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
            "OS filesystem containment is an explicit non-goal; sandbox-root"
            " delivery requires the opt-in cooperation ports, and these"
            " default ports deliver nothing",
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


def _validate_marker(marker: object) -> str:
    if type(marker) is not str:
        raise TypeError("readiness_marker must be a string")
    if not marker:
        raise ValueError("readiness_marker must be non-empty")
    return marker


def _validate_deadline(deadline_ms: object) -> int:
    if type(deadline_ms) is not int:
        raise TypeError("abort_deadline_ms must be an integer")
    if deadline_ms <= 0:
        raise ValueError("abort_deadline_ms must be positive")
    return deadline_ms


def _assemble_spawn_overlay(
    deliveries: Sequence[DeliveryRecord],
) -> tuple[dict[str, str] | None, str | None]:
    """Assemble the spawn environment overlay from validated delivery records.

    Evidence-driven spawn: what the receipts record is exactly what the
    child is given, with no side channel between ports and spawn. The
    delivery records must be mutually disjoint and name at most one working
    directory; a violation raises ``ValueError`` for the caller to report as
    an invariant breach.
    """
    overlay: dict[str, str] = {}
    cwd: str | None = None
    for delivery in deliveries:
        for name, value in delivery.env.items():
            if name in overlay:
                raise ValueError(
                    "delivery records must be mutually disjoint; variable"
                    f" {name!r} was delivered twice"
                )
            overlay[name] = value
        if delivery.cwd is not None:
            if cwd is not None:
                raise ValueError(
                    "delivery records may name at most one working directory"
                )
            cwd = delivery.cwd
    return (overlay if overlay else None), cwd


class _EpochFailure(Exception):
    """Internal classification carrier for one failed epoch step."""

    def __init__(self, message: str, details: dict[str, str]) -> None:
        super().__init__(message)
        self.message = message
        self.details: dict[str, JsonInput] = dict(details)


class ConptyAdapter:
    """Drive one terminal subject through the injected ConPTY binding port.

    The subject command line is bound at construction, exactly as the direct
    adapter binds its application. The abort deadline is mandatory host
    policy with no default: it can only produce a structured failure, never
    evidence of quiescence.
    """

    def __init__(
        self,
        argv: Sequence[str],
        *,
        binding: ConptyBindingPort,
        abort_deadline_ms: int,
        constraint_ports: ConstraintPorts | None = None,
        normalizer_factory: NormalizerFactory | None = None,
        readiness_marker: str = READINESS_MARKER_DEFAULT,
        watchdog: ConptyWatchdogPort | None = None,
    ) -> None:
        self._argv = _validate_argv(argv)
        self._binding = binding
        self._abort_deadline_ms = _validate_deadline(abort_deadline_ms)
        if constraint_ports is None:
            constraint_ports = UnenforcedConstraintPorts()
        self._constraints: ConstraintPorts = constraint_ports
        if normalizer_factory is None:
            normalizer_factory = VtScreenNormalizer
        self._normalizer_factory: NormalizerFactory = normalizer_factory
        self._marker = _validate_marker(readiness_marker)
        self._watchdog: ConptyWatchdogPort = (
            watchdog if watchdog is not None else TimerWatchdog()
        )
        self._state: _State = "created"
        self._state_lock = threading.Lock()
        self._manual_time: ManualTime | None = None
        self._child: ConptyChildPort | None = None
        self._normalizer: TerminalOutputNormalizer | None = None
        self._pending = ""
        self._columns = 0
        self._rows = 0
        self._deadline_closed = False

    def _set_state(self, state: _State) -> None:
        with self._state_lock:
            self._state = state

    def _set_time_and_state(self, at_ms: ManualTime, state: _State) -> None:
        with self._state_lock:
            self._manual_time = at_ms
            self._state = state

    # --- negotiation -------------------------------------------------------

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
        return TerminalReceipt(run_id, requested, tier="os")

    # --- marker protocol ---------------------------------------------------

    def _scan_for_marker(self) -> bool:
        """Consume the stream buffer up to and including one marker.

        Markers count in stream order: transcript-position causality is the
        evidence, and the subject's cooperation contract is exactly one
        marker per processed input. Without a match, only the shortest tail
        that could still complete a split marker is retained.
        """
        index = self._pending.find(self._marker)
        if index >= 0:
            self._pending = self._pending[index + len(self._marker) :]
            return True
        keep = len(self._marker) - 1
        self._pending = self._pending[-keep:] if keep else ""
        return False

    # --- epoch loop --------------------------------------------------------

    def _read_chunk(self, child: ConptyChildPort, expired: threading.Event) -> str:
        def expire() -> None:
            expired.set()
            try:
                child.close(force=True)
            except Exception:
                return
            self._deadline_closed = True

        disarm = self._watchdog.arm(self._abort_deadline_ms, expire)
        try:
            return child.read()
        except ConptyEndOfStreamError:
            raise
        except ConptyClosedError as error:
            raise _EpochFailure(
                "the ConPTY binding was closed outside the abort deadline",
                {"during": "read"},
            ) from error
        except ConptyConcurrentIOError as error:
            raise _EpochFailure(
                "concurrent native I/O was observed under the adapter's"
                " single-flight discipline",
                {"during": "read", "invariant": "single-flight"},
            ) from error
        except Exception as error:
            raise _EpochFailure(
                "a native ConPTY read failed", {"during": "read"}
            ) from error
        finally:
            disarm()

    def _feed(self, chunk: str) -> None:
        normalizer = cast(TerminalOutputNormalizer, self._normalizer)
        try:
            normalizer.feed(chunk)
        except Exception as error:
            raise _EpochFailure(
                "terminal output normalization failed", {"during": "normalize"}
            ) from error

    def _snapshot(self) -> ScreenSnapshot:
        normalizer = cast(TerminalOutputNormalizer, self._normalizer)
        try:
            snapshot = normalizer.snapshot()
        except Exception as error:
            raise _EpochFailure(
                "the normalizer snapshot failed", {"during": "snapshot"}
            ) from error
        if (
            type(snapshot) is not ScreenSnapshot
            or snapshot.frame.columns != self._columns
            or snapshot.frame.rows != self._rows
        ):
            raise _EpochFailure(
                "the normalized frame does not match the effective terminal dimensions",
                {"during": "snapshot"},
            )
        return snapshot

    def _observation(
        self,
        at_ms: ManualTime,
        chunks: Sequence[str],
        process: ProcessObservation | None,
    ) -> Observation:
        snapshot = self._snapshot()
        return Observation(
            at_ms,
            {"terminal": {"columns": self._columns, "rows": self._rows}},
            tuple(Event("terminal.output", {"chunk": chunk}) for chunk in chunks),
            UiObservation(
                regions=(),
                focus=None,
                cursor=snapshot.cursor,
                mode=snapshot.mode,
            ),
            frame=snapshot.frame,
            process=process,
        )

    def _read_epoch_chunks(
        self, child: ConptyChildPort, chunks: list[str], expired: threading.Event
    ) -> None:
        """Read until one readiness marker is observed in stream order."""
        if self._scan_for_marker():
            return
        while True:
            chunk = self._read_chunk(child, expired)
            chunks.append(chunk)
            self._feed(chunk)
            self._pending += chunk
            if self._scan_for_marker():
                return

    def _close_child(self) -> bool:
        child = self._child
        self._child = None
        if child is None:
            return True
        try:
            child.close(force=True)
        except Exception:
            return False
        return True

    def _fail_runtime(
        self, at_ms: ManualTime, message: str, details: dict[str, JsonInput]
    ) -> TerminalResult:
        if not self._close_child():
            details = {**details, "close": "failed"}
        self._set_time_and_state(at_ms, "terminal")
        return TerminalResult(
            None, RunFailed(AdapterFailure("adapter-runtime-failed", message, details))
        )

    def _deadline_abort(self, at_ms: ManualTime) -> TerminalResult:
        return self._fail_runtime(
            at_ms,
            "the abort deadline expired before quiescence evidence was"
            " observed; the deadline is host abort policy, not evidence",
            {"abort-deadline-ms": self._abort_deadline_ms},
        )

    def _finish_from_exit(
        self, at_ms: ManualTime, chunks: Sequence[str]
    ) -> TerminalResult:
        child = cast(ConptyChildPort, self._child)
        status = child.exit_status
        if status is None:
            return self._fail_runtime(
                at_ms,
                "the child exited but no native exit record was observed",
                {"missing": "exit-record"},
            )
        try:
            exit_status = ExitStatus("code", status)
        except Exception:
            return self._fail_runtime(
                at_ms,
                "the native exit record is invalid",
                {"during": "exit-record"},
            )
        try:
            observation = self._observation(
                at_ms, chunks, ProcessObservation.exited(exit_status)
            )
        except _EpochFailure as failure:
            return self._fail_runtime(at_ms, failure.message, failure.details)
        if not self._close_child():
            return self._fail_runtime(
                at_ms,
                "the ConPTY binding could not be closed after the child exited",
                {"during": "close"},
            )
        self._set_time_and_state(at_ms, "terminal")
        return TerminalResult(observation, RunFinished(exit_status))

    def _run_epoch(
        self,
        at_ms: ManualTime,
        write: Callable[[], None] | None,
        write_step: str,
        write_failure: str,
    ) -> EpochResult:
        child = cast(ConptyChildPort, self._child)
        chunks: list[str] = []
        # Deadline attribution is deliberately scoped: `expired` records an
        # expiry during THIS epoch's reads, and `_deadline_closed` records
        # that some expiry actually force-closed the binding (whose aftermath
        # any later failure then is). A failed expiry close in an earlier
        # epoch must never relabel an unrelated later failure.
        expired = threading.Event()
        try:
            if write is not None:
                try:
                    write()
                except Exception as error:
                    raise _EpochFailure(
                        write_failure, {"during": write_step}
                    ) from error
            self._read_epoch_chunks(child, chunks, expired)
            if expired.is_set():
                # The deadline expired during this epoch even though a marker
                # was still observed (the forced close failed or lost the
                # race): the abort policy fired, so no successful epoch may
                # be claimed.
                return self._deadline_abort(at_ms)
            observation = self._observation(at_ms, chunks, None)
        except ConptyEndOfStreamError:
            return self._finish_from_exit(at_ms, chunks)
        except _EpochFailure as failure:
            if expired.is_set() or self._deadline_closed:
                return self._deadline_abort(at_ms)
            return self._fail_runtime(at_ms, failure.message, failure.details)
        self._set_time_and_state(at_ms, "idle")
        return EpochCompleted(observation)

    # --- adapter protocol --------------------------------------------------

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
            _AUTHORIZED_TIERS,
        )
        if not isinstance(negotiated, tuple):
            self._set_state("terminal")
            return negotiated
        receipts = tuple(negotiated)

        def start_failed(message: str, details: dict[str, JsonInput]) -> StartFailed:
            self._set_state("terminal")
            return StartFailed(
                run_id=run_id,
                requested=configuration,
                enforced=receipts,
                failure=AdapterFailure("adapter-start-failed", message, details),
            )

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
        terminal = configuration.terminal
        try:
            env_overlay, cwd = _assemble_spawn_overlay(
                tuple(
                    receipt.delivery
                    for receipt in receipts
                    if receipt.delivery is not None
                )
            )
        except ValueError:
            # Defense-in-depth against a buggy or hostile injected port:
            # the shipped ports deliver disjoint, closed variable sets, so
            # this invariant breach is not reachable through them. It occurs
            # after negotiation completed, with the full receipt set
            # available for diagnostics, and is never silently merged.
            return start_failed(
                "the delivered spawn environment violates the delivery invariants",
                {"during": "spawn-overlay", "invariant": "delivery-disjoint"},
            )
        try:
            self._child = self._binding.spawn(
                self._argv,
                rows=terminal.rows,
                columns=terminal.columns,
                env_overlay=env_overlay,
                cwd=cwd,
            )
        except Exception:
            return start_failed(
                "the ConPTY child could not be spawned", {"during": "spawn"}
            )
        self._columns = terminal.columns
        self._rows = terminal.rows
        self._pending = ""
        try:
            self._normalizer = self._normalizer_factory(
                rows=terminal.rows, columns=terminal.columns
            )
        except Exception:
            self._close_child()
            return start_failed(
                "the output normalizer could not be constructed",
                {"during": "normalizer"},
            )
        initial_ms = ManualTime(configuration.clock.initial_ms)
        result = self._run_epoch(initial_ms, None, "", "")
        if type(result) is EpochCompleted:
            return Started(constraints=constraints, observation=result.observation)
        terminal_result = cast(TerminalResult, result)
        if type(terminal_result.outcome) is RunFinished:
            return StartTerminated(constraints=constraints, result=terminal_result)
        failure = cast(RunFailed, terminal_result.outcome).failure
        return StartFailed(
            run_id=run_id,
            requested=configuration,
            enforced=receipts,
            failure=AdapterFailure(
                "adapter-start-failed", failure.message, failure.details
            ),
        )

    def dispatch(self, input_event: DispatchInput) -> EpochResult:
        if type(input_event) not in (KeyInput, TextInput, Resize):
            raise TypeError("dispatch input must be KeyInput, TextInput, or Resize")
        with self._state_lock:
            if self._state != "idle":
                raise RuntimeError("ConPTY adapter is not idle")
            if input_event.at_ms != self._manual_time:
                raise ValueError("input must use the current manual time")
            self._state = "active"
        if type(input_event) is KeyInput:
            return self._fail_runtime(
                input_event.at_ms,
                "the ConPTY adapter cannot execute semantic key input; no"
                " key-to-terminal byte mapping exists",
                {"unsupported": "key-input"},
            )
        child = cast(ConptyChildPort, self._child)
        if type(input_event) is TextInput:
            text = input_event.text

            def write_text() -> None:
                child.write(text)

            return self._run_epoch(
                input_event.at_ms,
                write_text,
                "write",
                "the input text could not be written to the child",
            )
        resize = cast(Resize, input_event)

        def apply_resize() -> None:
            child.resize(rows=resize.rows, columns=resize.columns)
            cast(TerminalOutputNormalizer, self._normalizer).notify_resize(
                rows=resize.rows, columns=resize.columns
            )
            self._rows = resize.rows
            self._columns = resize.columns

        return self._run_epoch(
            resize.at_ms, apply_resize, "resize", "the resize could not be applied"
        )

    def advance_clock(self, input_event: ClockAdvance) -> EpochResult:
        if type(input_event) is not ClockAdvance:
            raise TypeError("clock input must be ClockAdvance")
        with self._state_lock:
            if self._state != "idle":
                raise RuntimeError("ConPTY adapter is not idle")
            if (
                self._manual_time is None
                or input_event.at_ms != self._manual_time + input_event.delta_ms
            ):
                raise ValueError("clock advance must move the current manual time")
            self._state = "active"
        return self._run_epoch(input_event.at_ms, None, "", "")

    def stop(self, input_event: Stop) -> TerminalResult:
        if type(input_event) is not Stop:
            raise TypeError("stop input must be Stop")
        with self._state_lock:
            if self._state != "idle":
                raise RuntimeError("ConPTY adapter is not idle")
            if input_event.at_ms != self._manual_time:
                raise ValueError("stop must use the current manual time")
            self._state = "stopping"
        at_ms = input_event.at_ms
        child = cast(ConptyChildPort, self._child)
        if not self._close_child():
            return self._fail_runtime(
                at_ms,
                "the ConPTY binding could not be closed on forced stop",
                {"during": "close"},
            )
        status = child.exit_status
        if status is None:
            return self._fail_runtime(
                at_ms,
                "forced stop observed no native exit record",
                {"missing": "exit-record"},
            )
        try:
            exit_status = ExitStatus("code", status)
        except Exception:
            return self._fail_runtime(
                at_ms,
                "the native exit record is invalid",
                {"during": "exit-record"},
            )
        try:
            observation = self._observation(
                at_ms, (), ProcessObservation.exited(exit_status)
            )
        except _EpochFailure as failure:
            return self._fail_runtime(at_ms, failure.message, failure.details)
        self._set_time_and_state(at_ms, "terminal")
        return TerminalResult(
            observation,
            RunFinished(exit_status),
            diagnostics=(
                Diagnostic(
                    at_ms,
                    "forced-termination",
                    "the run was ended by forced ConPTY teardown; output"
                    " produced after the last observed readiness marker may"
                    " be lost",
                ),
            ),
        )
