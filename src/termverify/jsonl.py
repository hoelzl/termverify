"""Public JSONL-subprocess adapter over the `termverify.control/v1` wire.

This module implements slice 1 of the accepted JSONL control transport
design (`docs/agent/design/jsonl-control-transport.md`): the
``JsonlBindingPort``/``JsonlChildPort`` injection boundary, truthful
constraint negotiation, and the epoch machinery — handshake, single-flight
epoch loop, failure classification, watchdog-driven abort deadline, and
forced teardown — all cross-platform and testable against fake bindings.
The real pipe/process binding is slice 2; no process is spawned here.

The adapter implements the same ``Adapter`` contract as the direct and
ConPTY adapters, so the recorder, replay engine, and conformance suites
consume its runs unchanged. Everything on the wire is validated by the
strict `termverify.control/v1` codec (`termverify.control`): a malformed
or out-of-lifecycle peer message is a structured failure, never a guess.

Negotiation is truthful by construction:

- The adapter owns the ``terminal`` constraint and never delegates it:
  dimensions are declared in the handshake configuration, and requested
  terminal capabilities are rejected fail-closed — the transport exposes
  no terminal, and the capability registry is not activated.
- The six non-terminal constraints belong to injected ``ConstraintPorts``
  stating the ``delivered`` tier: exactly the recorded values are placed
  into the child's spawn environment and working directory, and honoring
  them is the subject's documented cooperation obligation. The shipped
  ports live in ``termverify.cooperation``.
- There is no default port set: constructing the adapter without ports
  is a type error, because the only truthful default
  (``constraint-not-enforced`` for everything) would make every start
  unsupported.

Readiness and quiescence are defined only by protocol messages:

- After spawn the adapter sends exactly one ``session.hello`` and reads
  the child's reply: ``session.unsupported`` (negotiation ends as
  ``StartUnsupported`` — the run began but cannot be served),
  ``session.failed`` (``StartFailed`` with the child's error), or
  ``session.ready`` carrying the initial readiness observation.
- Each epoch is one input message, zero or more diagnostics, and exactly
  one closing ``observation`` — or a terminal message. The wire position
  is the causality; there are no timestamps on the wire.
- Native end-of-stream plus the observed exit record ends the run
  truthfully; a missing exit record is a structured failure, never a
  fabricated exit. The OS-observed record is authoritative; a child's
  claimed ``run.finished`` exit that disagrees is disclosed as a
  diagnostic.
- Wall-clock silence is never evidence. The only wall-clock input is the
  mandatory, explicitly configured abort deadline: a watchdog armed
  before each blocking read force-closes the binding when it expires,
  which always produces a structured failure disclosing the deadline
  policy and never a successful epoch.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Mapping, Sequence
from typing import Final, Literal, Protocol, cast, runtime_checkable

from termverify._json import JsonValue
from termverify._negotiation import AuthorizedTiers, negotiate
from termverify.adapter import (
    AdapterFailure,
    ClockAdvance,
    ClockReceipt,
    ConstraintPorts,
    Cursor,
    DeliveryRecord,
    Diagnostic,
    DispatchInput,
    EnforcedConstraints,
    EnforcementReceipt,
    EpochCompleted,
    EpochResult,
    Event,
    ExitStatus,
    FilesystemReceipt,
    Frame,
    JsonInput,
    KeyInput,
    LocaleReceipt,
    ManualTime,
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
from termverify.control import (
    CONTROL_PROTOCOL_V1,
    MAX_EPOCH_DIAGNOSTICS,
    MAX_STARTUP_DIAGNOSTICS,
    ControlProtocolError,
    parse_message,
    serialize_message,
)

__all__ = [
    "JsonlAdapter",
    "JsonlBinding",
    "JsonlBindingPort",
    "JsonlChildClosedError",
    "JsonlChildPort",
    "JsonlEndOfStreamError",
    "JsonlWatchdogPort",
    "TimerWatchdog",
]

#: The adapter's own failure-taxonomy codes (normative in
#: `docs/knowledge/control-protocol.md`).
_SPAWN_FAILED: Final = "spawn-failed"
_HANDSHAKE_TIMEOUT: Final = "handshake-timeout"
_PEER_MALFORMED: Final = "peer-malformed"
_PEER_LIFECYCLE: Final = "peer-lifecycle"
_EPOCH_TIMEOUT: Final = "epoch-timeout"
_TEARDOWN_FORCED: Final = "teardown-forced"

type _State = Literal[
    "created", "negotiating", "initializing", "idle", "active", "stopping", "terminal"
]


class JsonlEndOfStreamError(Exception):
    """The child's stdout reached end-of-stream (the child exited)."""


class JsonlChildClosedError(Exception):
    """The binding was closed outside the abort deadline."""


@runtime_checkable
class JsonlChildPort(Protocol):
    """One spawned control-protocol child: line I/O plus exit evidence."""

    def write_line(self, line: bytes) -> None:
        """Write one framed message line to the child's stdin."""
        ...  # pragma: no cover - structural declaration

    def read_line(self) -> bytes:
        """Read one framed message line from the child's stdout.

        Raises :class:`JsonlEndOfStreamError` at end-of-stream and
        :class:`JsonlChildClosedError` when the binding was closed.
        """
        ...  # pragma: no cover - structural declaration

    def close(self, *, force: bool) -> None:
        """Close the pipes and, when forced, terminate the child tree."""
        ...  # pragma: no cover - structural declaration

    @property
    def exit_status(self) -> int | None:
        """The OS-observed exit code, or None while none was observed."""
        ...  # pragma: no cover - structural declaration


@runtime_checkable
class JsonlBindingPort(Protocol):
    """The ambient boundary: spawn one child speaking the control protocol."""

    def spawn(
        self,
        argv: Sequence[str],
        *,
        env_overlay: Mapping[str, str] | None = None,
        cwd: str | None = None,
    ) -> JsonlChildPort:
        """Spawn the subject with the delivered environment and directory."""
        ...  # pragma: no cover - structural declaration


@runtime_checkable
class JsonlWatchdogPort(Protocol):
    """Arms the abort deadline; the expiry callback force-closes the child."""

    def arm(self, delay_ms: int, expire: Callable[[], None]) -> Callable[[], None]:
        """Arm the deadline and return the disarm callback."""
        ...  # pragma: no cover - structural declaration


class TimerWatchdog:
    """Default watchdog: a ``threading.Timer`` per armed deadline."""

    def arm(self, delay_ms: int, expire: Callable[[], None]) -> Callable[[], None]:
        timer = threading.Timer(delay_ms / 1000, expire)
        timer.daemon = True
        timer.start()
        return timer.cancel


class JsonlBinding:
    """The shipped real binding: one contained pipe subprocess per spawn.

    A thin delegate to ``termverify._jsonl_pipe.PipeJsonlChild`` — the
    pipe-only generalization of the ConPTY binding's containment patterns:
    a kill-on-close job object on Windows, a process group on POSIX, with
    identical observable outcomes on every platform (real exit record,
    forced-termination record, no survivors).
    """

    def spawn(
        self,
        argv: Sequence[str],
        *,
        env_overlay: Mapping[str, str] | None = None,
        cwd: str | None = None,
    ) -> JsonlChildPort:
        from termverify._jsonl_pipe import PipeJsonlChild

        return PipeJsonlChild.spawn(argv, env_overlay=env_overlay, cwd=cwd)


#: The `termverify.enforcement-tier/v1` authorization matrix row for the
#: JSONL architecture: every constraint, including the adapter's own
#: terminal negotiation, states ``delivered`` — exact recorded values
#: delivered to the subject (via the handshake configuration for the
#: terminal, via the spawn environment for the rest), with honoring left
#: to subject cooperation. Nothing at this boundary enforces by an OS or
#: constructive mechanism.
_AUTHORIZED_TIERS: AuthorizedTiers = (
    "delivered",
    "delivered",
    "delivered",
    "delivered",
    "delivered",
    "delivered",
    "delivered",
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


def _as_json_input(value: JsonValue) -> JsonInput:
    """Narrow a codec-produced JSON value to the contract's JsonInput.

    The codec validates to ``JsonValue`` (``list``/``dict`` containers);
    the contract's value types accept ``JsonInput`` (which additionally
    permits ``tuple``/``Mapping``). A codec value is always admissible as
    ``JsonInput`` — the union difference is one-directional — so the cast
    is sound and centralizes the one deliberate type relationship.
    """
    return cast(JsonInput, value)


def _validate_deadline(deadline_ms: object) -> int:
    if type(deadline_ms) is not int:
        raise TypeError("abort_deadline_ms must be an integer")
    if deadline_ms <= 0:
        raise ValueError("abort_deadline_ms must be positive")
    return deadline_ms


class _DeliveryInvariantError(ValueError):
    """One spawn-delivery invariant breach, labeled for diagnostics."""

    def __init__(self, invariant: str, message: str) -> None:
        super().__init__(message)
        self.invariant = invariant


def _assemble_spawn_overlay(
    deliveries: Sequence[DeliveryRecord],
) -> tuple[dict[str, str] | None, str | None]:
    """Assemble the spawn environment overlay from validated delivery records.

    Evidence-driven spawn: what the receipts record is exactly what the
    child is given, with no side channel between ports and spawn. The
    delivery records must be mutually disjoint — compared case-folded,
    because Windows environment lookup is case-insensitive and two
    case-variant entries would let one recorded delivery silently shadow
    another — and may name at most one working directory; a violation
    raises :class:`_DeliveryInvariantError` for the caller to report as an
    invariant breach.
    """
    overlay: dict[str, str] = {}
    seen: set[str] = set()
    cwd: str | None = None
    for delivery in deliveries:
        for name, value in delivery.env.items():
            folded = name.casefold()
            if folded in seen:
                raise _DeliveryInvariantError(
                    "delivery-disjoint",
                    "delivery records must be mutually disjoint under"
                    " case-insensitive Windows environment semantics;"
                    f" variable {name!r} was delivered twice",
                )
            seen.add(folded)
            overlay[name] = value
        if delivery.cwd is not None:
            if cwd is not None:
                raise _DeliveryInvariantError(
                    "single-working-directory",
                    "delivery records may name at most one working directory",
                )
            cwd = delivery.cwd
    return (overlay if overlay else None), cwd


class _EpochFailure(Exception):
    """Internal classification carrier for one failed epoch step."""

    def __init__(self, code: str, message: str, details: dict[str, JsonInput]) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details: dict[str, JsonInput] = dict(details)


class _ReadOutcome:
    """One epoch read: a closing observation, or a terminal result."""

    __slots__ = ("diagnostics", "observation", "terminal")

    def __init__(
        self,
        *,
        observation: Observation | None,
        diagnostics: tuple[Diagnostic, ...],
        terminal: TerminalResult | None,
    ) -> None:
        self.observation = observation
        self.diagnostics = diagnostics
        self.terminal = terminal


class JsonlAdapter:
    """Drive one control-protocol subject through the injected binding port.

    The subject command line is bound at construction, exactly as the
    direct adapter binds its application. The abort deadline is mandatory
    host policy with no default: it can only produce a structured
    failure, never evidence of quiescence.
    """

    def __init__(
        self,
        argv: Sequence[str],
        *,
        binding: JsonlBindingPort,
        abort_deadline_ms: int,
        constraint_ports: ConstraintPorts,
        watchdog: JsonlWatchdogPort | None = None,
    ) -> None:
        self._argv = _validate_argv(argv)
        self._binding = binding
        self._abort_deadline_ms = _validate_deadline(abort_deadline_ms)
        if constraint_ports is None:
            raise TypeError(
                "constraint_ports is required: the JSONL adapter has no"
                " truthful default ports — delivered-tier ports (for example"
                " termverify.cooperation.CooperationConstraintPorts) must be"
                " an explicit host decision"
            )
        self._constraints: ConstraintPorts = constraint_ports
        self._watchdog: JsonlWatchdogPort = (
            watchdog if watchdog is not None else TimerWatchdog()
        )
        self._state: _State = "created"
        self._state_lock = threading.Lock()
        self._manual_time: ManualTime | None = None
        self._child: JsonlChildPort | None = None
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
    ) -> TerminalReceipt | AdapterFailure:
        if requested.capabilities:
            return AdapterFailure(
                "adapter-start-failed",
                "the JSONL transport exposes no terminal: requested terminal"
                " capabilities cannot be declared or enforced, and the"
                " capability registry is not activated",
                {"constraint": "terminal"},
            )
        return TerminalReceipt(
            run_id,
            requested,
            tier="delivered",
            delivery=DeliveryRecord.hello_config(),
        )

    # --- wire mapping ------------------------------------------------------

    @staticmethod
    def _write_message(child: JsonlChildPort, kind: str, payload: JsonInput) -> None:
        message: dict[str, JsonValue] = {
            "protocol": CONTROL_PROTOCOL_V1,
            "kind": kind,
            "payload": cast(JsonValue, payload),
        }
        child.write_line(serialize_message(message))

    @staticmethod
    def _exit_record(payload: dict[str, JsonValue], name: str) -> ExitStatus:
        record = cast(dict[str, JsonValue], payload[name])
        if record["kind"] == "signal":
            return ExitStatus("signal", cast(str, record["value"]))
        return ExitStatus("code", cast(int, record["value"]))

    @staticmethod
    def _map_cursor(payload: dict[str, JsonValue]) -> Cursor:
        return Cursor(
            column=cast(int, payload["column"]),
            row=cast(int, payload["row"]),
            visible=cast(bool, payload["visible"]),
        )

    @classmethod
    def _map_ui(cls, payload: dict[str, JsonValue]) -> UiObservation:
        regions = tuple(
            Region(
                id=cast(str, region["id"]),
                role=cast(str, region["role"]),
                column=cast(int, region["column"]),
                row=cast(int, region["row"]),
                columns=cast(int, region["columns"]),
                rows=cast(int, region["rows"]),
            )
            for region in cast(list[dict[str, JsonValue]], payload["regions"])
        )
        return UiObservation(
            regions=regions,
            focus=cast("str | None", payload.get("focus")),
            cursor=cls._map_cursor(cast(dict[str, JsonValue], payload["cursor"])),
            mode=cast("str | None", payload.get("mode")),
        )

    def _map_observation(
        self, at_ms: ManualTime, payload: dict[str, JsonValue]
    ) -> Observation:
        frame: Frame | None = None
        if "frame" in payload:
            frame_payload = cast(dict[str, JsonValue], payload["frame"])
            frame = Frame(
                lines=tuple(cast(list[str], frame_payload["lines"])),
                columns=cast(int, frame_payload["columns"]),
                rows=cast(int, frame_payload["rows"]),
            )
        process: ProcessObservation | None = None
        if "process" in payload:
            process_payload = cast(dict[str, JsonValue], payload["process"])
            if process_payload["state"] == "running":
                process = ProcessObservation.running()
            else:
                process = ProcessObservation.exited(
                    self._exit_record(process_payload, "exit")
                )
        events = tuple(
            Event(cast(str, event["type"]), _as_json_input(event["data"]))
            for event in cast(list[dict[str, JsonValue]], payload["events"])
        )
        return Observation(
            at_ms,
            _as_json_input(payload["state"]),
            events,
            self._map_ui(cast(dict[str, JsonValue], payload["ui"])),
            frame=frame,
            process=process,
        )

    @staticmethod
    def _map_diagnostic(at_ms: ManualTime, payload: dict[str, JsonValue]) -> Diagnostic:
        return Diagnostic(
            at_ms,
            cast(str, payload["code"]),
            cast(str, payload["message"]),
            _as_json_input(payload.get("details")),
        )

    # --- epoch machinery ---------------------------------------------------

    def _read_message(
        self, child: JsonlChildPort, expired: threading.Event
    ) -> tuple[str, dict[str, JsonValue]]:
        """Read one validated message; return (kind, payload).

        Raises :class:`JsonlEndOfStreamError` at end-of-stream and
        :class:`_EpochFailure` for every other failure, classified.
        """

        def expire() -> None:
            expired.set()
            try:
                child.close(force=True)
            except Exception:
                return
            self._deadline_closed = True

        disarm = self._watchdog.arm(self._abort_deadline_ms, expire)
        try:
            line = child.read_line()
        except JsonlEndOfStreamError:
            raise
        except JsonlChildClosedError as error:
            raise _EpochFailure(
                _PEER_LIFECYCLE,
                "the JSONL binding was closed outside the abort deadline",
                {"during": "read"},
            ) from error
        except Exception as error:
            raise _EpochFailure(
                _PEER_MALFORMED,
                "a JSONL binding read failed",
                {"during": "read"},
            ) from error
        finally:
            disarm()
        try:
            message = parse_message(line)
        except ControlProtocolError as error:
            raise _EpochFailure(
                _PEER_MALFORMED,
                f"the child sent a message outside termverify.control/v1: {error}",
                {"during": "parse"},
            ) from error
        return (
            cast(str, message["kind"]),
            cast(dict[str, JsonValue], message["payload"]),
        )

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
        self, at_ms: ManualTime, code: str, message: str, details: dict[str, JsonInput]
    ) -> TerminalResult:
        if not self._close_child():
            details = {**details, "close": "failed"}
        self._set_time_and_state(at_ms, "terminal")
        return TerminalResult(
            None,
            RunFailed(
                AdapterFailure(
                    "adapter-runtime-failed", message, {**details, "failure": code}
                )
            ),
        )

    def _deadline_abort(self, at_ms: ManualTime, phase: str) -> TerminalResult:
        code = _HANDSHAKE_TIMEOUT if phase == "handshake" else _EPOCH_TIMEOUT
        return self._fail_runtime(
            at_ms,
            code,
            "the abort deadline expired before the closing message was"
            " observed; the deadline is host abort policy, not evidence",
            {"abort-deadline-ms": self._abort_deadline_ms, "phase": phase},
        )

    def _observed_exit_status(self) -> ExitStatus | None:
        child = self._child
        if child is None:
            return None
        status = child.exit_status
        if status is None:
            return None
        try:
            return ExitStatus("code", status)
        except Exception:
            return None

    @staticmethod
    def _exit_observation(at_ms: ManualTime, observed: ExitStatus) -> Observation:
        """The synthetic observation for a terminal-without-observation end.

        The transcript's terminal record carries the exit; this observation
        exists so the contract's ``TerminalResult`` can carry the exited
        process evidence the validator requires for ``RunFailed``.
        """
        return Observation(
            at_ms,
            None,
            (),
            UiObservation(
                regions=(),
                focus=None,
                cursor=Cursor(column=0, row=0, visible=False),
                mode=None,
            ),
            process=ProcessObservation.exited(observed),
        )

    def _terminal_from_child(
        self,
        at_ms: ManualTime,
        kind: str,
        payload: dict[str, JsonValue],
        diagnostics: tuple[Diagnostic, ...],
    ) -> TerminalResult:
        """Build the terminal result for a child's terminal message."""
        observed = self._observed_exit_status()
        if kind == "run.failed":
            error = cast(dict[str, JsonValue], payload["error"])
            if not self._close_child():
                return self._fail_runtime(
                    at_ms,
                    _PEER_LIFECYCLE,
                    "the JSONL binding could not be closed after the child"
                    " reported run.failed",
                    {"during": "close"},
                )
            self._set_time_and_state(at_ms, "terminal")
            return TerminalResult(
                (
                    self._exit_observation(at_ms, observed)
                    if observed is not None
                    else None
                ),
                RunFailed(
                    AdapterFailure(
                        "adapter-runtime-failed",
                        f"the subject reported run.failed: {error['message']}",
                        {
                            "subject-code": _as_json_input(error["code"]),
                            "subject-details": _as_json_input(error.get("details")),
                        },
                    )
                ),
                diagnostics=diagnostics,
            )
        claimed = self._exit_record(payload, "exit")
        if observed is None:
            return self._fail_runtime(
                at_ms,
                _PEER_LIFECYCLE,
                "the child reported run.finished but no OS exit record was"
                " observed; a claimed exit is not evidence of one",
                {"missing": "exit-record"},
            )
        if not self._close_child():
            return self._fail_runtime(
                at_ms,
                _PEER_LIFECYCLE,
                "the JSONL binding could not be closed after the child exited",
                {"during": "close"},
            )
        self._set_time_and_state(at_ms, "terminal")
        result_diagnostics = diagnostics
        if claimed != observed:
            result_diagnostics = (
                *diagnostics,
                Diagnostic(
                    at_ms,
                    "exit-record-mismatch",
                    "the subject's claimed exit record disagrees with the"
                    " OS-observed record; the OS record is authoritative",
                    {
                        "claimed": (
                            {"kind": "signal", "value": claimed.value}
                            if claimed.kind == "signal"
                            else {"kind": "code", "value": claimed.value}
                        ),
                        "observed": {"kind": "code", "value": observed.value},
                    },
                ),
            )
        return TerminalResult(
            self._exit_observation(at_ms, observed),
            RunFinished(observed),
            diagnostics=result_diagnostics,
        )

    def _finish_from_eos(
        self, at_ms: ManualTime, diagnostics: tuple[Diagnostic, ...]
    ) -> TerminalResult:
        """The child's stdout closed without a terminal message."""
        observed = self._observed_exit_status()
        if observed is None:
            return self._fail_runtime(
                at_ms,
                _PEER_LIFECYCLE,
                "the child closed its output without a terminal message and"
                " no OS exit record was observed",
                {"missing": "exit-record"},
            )
        if not self._close_child():
            return self._fail_runtime(
                at_ms,
                _PEER_LIFECYCLE,
                "the JSONL binding could not be closed after the child exited",
                {"during": "close"},
            )
        self._set_time_and_state(at_ms, "terminal")
        return TerminalResult(
            self._exit_observation(at_ms, observed),
            RunFinished(observed),
            diagnostics=diagnostics,
        )

    def _read_epoch(self, at_ms: ManualTime, phase: str) -> _ReadOutcome:
        """Read one epoch: diagnostics, then one closing message.

        ``phase`` is ``"epoch"`` (after an input), ``"stop"`` (the drain),
        or ``"handshake"`` (after session.hello); it selects the
        diagnostic budget, the deadline failure code, and which kinds are
        legal closings.
        """
        child = cast(JsonlChildPort, self._child)
        expired = threading.Event()
        diagnostics: list[Diagnostic] = []
        budget = (
            MAX_STARTUP_DIAGNOSTICS if phase == "handshake" else (MAX_EPOCH_DIAGNOSTICS)
        )
        handshake_replies = {"session.unsupported", "session.failed", "session.ready"}
        while True:
            try:
                kind, payload = self._read_message(child, expired)
            except JsonlEndOfStreamError:
                return _ReadOutcome(
                    observation=None,
                    diagnostics=(),
                    terminal=self._finish_from_eos(at_ms, tuple(diagnostics)),
                )
            except _EpochFailure as failure:
                if expired.is_set() or self._deadline_closed:
                    return _ReadOutcome(
                        observation=None,
                        diagnostics=(),
                        terminal=self._deadline_abort(at_ms, phase),
                    )
                return _ReadOutcome(
                    observation=None,
                    diagnostics=(),
                    terminal=self._fail_runtime(
                        at_ms, failure.code, failure.message, failure.details
                    ),
                )
            if expired.is_set():
                # The deadline fired during this read even though a message
                # still arrived (the forced close failed or lost the race):
                # the abort policy fired, so no successful epoch may be
                # claimed.
                return _ReadOutcome(
                    observation=None,
                    diagnostics=(),
                    terminal=self._deadline_abort(at_ms, phase),
                )
            if kind == "diagnostic":
                diagnostics.append(self._map_diagnostic(at_ms, payload))
                if len(diagnostics) > budget:
                    return _ReadOutcome(
                        observation=None,
                        diagnostics=(),
                        terminal=self._fail_runtime(
                            at_ms,
                            _PEER_MALFORMED,
                            "the child exceeded the v1 diagnostic budget",
                            {"during": phase, "budget": budget},
                        ),
                    )
                continue
            if phase == "handshake":
                if kind in handshake_replies:
                    # Replies carry their own classification for start();
                    # surface the raw payload through a sentinel observation
                    # slot by returning it via the terminal path is wrong —
                    # instead this branch is handled by _start_handshake,
                    # which never reaches here.
                    raise AssertionError(
                        "handshake replies are handled by _start_handshake"
                    )
                return _ReadOutcome(
                    observation=None,
                    diagnostics=(),
                    terminal=self._fail_runtime(
                        at_ms,
                        _PEER_LIFECYCLE,
                        "the child answered session.hello with a message kind"
                        " that is not a handshake reply",
                        {"during": phase, "kind": kind},
                    ),
                )
            if kind == "observation":
                process = payload.get("process")
                if type(process) is dict and process.get("state") == "exited":
                    return _ReadOutcome(
                        observation=None,
                        diagnostics=(),
                        terminal=self._fail_runtime(
                            at_ms,
                            _PEER_LIFECYCLE,
                            "an epoch observation carried exited-process"
                            " evidence; a terminal message must close the run"
                            " instead",
                            {"during": phase, "kind": kind},
                        ),
                    )
                return _ReadOutcome(
                    observation=self._map_observation(at_ms, payload),
                    diagnostics=tuple(diagnostics),
                    terminal=None,
                )
            if kind in ("run.finished", "run.failed"):
                return _ReadOutcome(
                    observation=None,
                    diagnostics=(),
                    terminal=self._terminal_from_child(
                        at_ms, kind, payload, tuple(diagnostics)
                    ),
                )
            return _ReadOutcome(
                observation=None,
                diagnostics=(),
                terminal=self._fail_runtime(
                    at_ms,
                    _PEER_LIFECYCLE,
                    "the child sent a message kind that is not valid in this"
                    " lifecycle position",
                    {"during": phase, "kind": kind},
                ),
            )

    def _run_epoch(
        self,
        at_ms: ManualTime,
        write: Callable[[], None],
        write_failure: str,
        phase: str,
    ) -> EpochResult:
        if write is not None:
            try:
                write()
            except Exception:
                return self._fail_runtime(
                    at_ms,
                    _PEER_LIFECYCLE,
                    write_failure,
                    {"during": "write"},
                )
        outcome = self._read_epoch(at_ms, phase)
        if outcome.terminal is not None:
            return outcome.terminal
        self._set_time_and_state(at_ms, "idle")
        return EpochCompleted(
            cast(Observation, outcome.observation), diagnostics=outcome.diagnostics
        )

    def _run_stop_drain(self, at_ms: ManualTime) -> TerminalResult:
        """Read the stop epoch: optional closing observation, then terminal."""
        child = cast(JsonlChildPort, self._child)
        expired = threading.Event()
        diagnostics: list[Diagnostic] = []
        seen_observation = False
        while True:
            try:
                kind, payload = self._read_message(child, expired)
            except JsonlEndOfStreamError:
                return self._finish_from_eos(at_ms, tuple(diagnostics))
            except _EpochFailure as failure:
                if expired.is_set() or self._deadline_closed:
                    return self._deadline_abort(at_ms, "stop")
                return self._fail_runtime(
                    at_ms, failure.code, failure.message, failure.details
                )
            if expired.is_set():
                return self._deadline_abort(at_ms, "stop")
            if kind == "diagnostic":
                diagnostics.append(self._map_diagnostic(at_ms, payload))
                if len(diagnostics) > MAX_EPOCH_DIAGNOSTICS:
                    return self._fail_runtime(
                        at_ms,
                        _PEER_MALFORMED,
                        "the child exceeded the v1 diagnostic budget",
                        {"during": "stop", "budget": MAX_EPOCH_DIAGNOSTICS},
                    )
                continue
            if kind == "observation":
                if seen_observation:
                    return self._fail_runtime(
                        at_ms,
                        _PEER_LIFECYCLE,
                        "the stop drain contained more than one observation",
                        {"during": "stop", "kind": kind},
                    )
                process = payload.get("process")
                if type(process) is dict and process.get("state") == "exited":
                    return self._fail_runtime(
                        at_ms,
                        _PEER_LIFECYCLE,
                        "a drain observation carried exited-process evidence;"
                        " a terminal message must close the run instead",
                        {"during": "stop", "kind": kind},
                    )
                seen_observation = True
                continue
            if kind in ("run.finished", "run.failed"):
                return self._terminal_from_child(
                    at_ms, kind, payload, tuple(diagnostics)
                )
            return self._fail_runtime(
                at_ms,
                _PEER_LIFECYCLE,
                "the child sent a message kind that is not valid in the stop drain",
                {"during": "stop", "kind": kind},
            )

    # --- adapter protocol --------------------------------------------------

    def start(self, run_id: str, configuration: RunConfiguration) -> StartResult:
        if type(configuration) is not RunConfiguration:
            raise TypeError("configuration must be RunConfiguration")
        _validate_run_id(run_id)
        with self._state_lock:
            if self._state != "created":
                raise RuntimeError("JSONL adapter has already started")
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

        def start_failed(
            code: str, message: str, details: dict[str, JsonInput]
        ) -> StartFailed:
            self._set_state("terminal")
            return StartFailed(
                run_id=run_id,
                requested=configuration,
                enforced=receipts,
                failure=AdapterFailure(
                    "adapter-start-failed", message, {**details, "failure": code}
                ),
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
        try:
            env_overlay, cwd = _assemble_spawn_overlay(
                tuple(
                    receipt.delivery
                    for receipt in receipts
                    if receipt.delivery is not None
                )
            )
        except _DeliveryInvariantError as breach:
            return start_failed(
                _SPAWN_FAILED,
                "the delivered spawn environment violates the delivery invariants",
                {"during": "spawn-overlay", "invariant": breach.invariant},
            )
        try:
            self._child = self._binding.spawn(
                self._argv, env_overlay=env_overlay, cwd=cwd
            )
        except Exception:
            return start_failed(
                _SPAWN_FAILED,
                "the JSONL subject could not be spawned",
                {"during": "spawn"},
            )
        initial_ms = ManualTime(configuration.clock.initial_ms)
        try:
            self._write_message(
                self._child,
                "session.hello",
                _as_json_input(
                    {
                        "run_id": run_id,
                        "config": configuration.to_protocol(),
                        "at_ms": int(initial_ms),
                    }
                ),
            )
        except Exception:
            self._close_child()
            return start_failed(
                _SPAWN_FAILED,
                "the session.hello message could not be written to the child",
                {"during": "write"},
            )
        return self._start_handshake(run_id, configuration, constraints, initial_ms)

    def _start_handshake(
        self,
        run_id: str,
        configuration: RunConfiguration,
        constraints: EnforcedConstraints,
        initial_ms: ManualTime,
    ) -> StartResult:
        """Read and classify the child's handshake reply."""
        child = cast(JsonlChildPort, self._child)
        expired = threading.Event()
        diagnostics: list[Diagnostic] = []

        def start_failed(
            code: str, message: str, details: dict[str, JsonInput]
        ) -> StartFailed:
            self._close_child()
            self._set_state("terminal")
            return StartFailed(
                run_id=run_id,
                requested=configuration,
                enforced=(
                    constraints.seed,
                    constraints.clock,
                    constraints.locale,
                    constraints.timezone,
                    constraints.terminal,
                    constraints.filesystem,
                    constraints.network,
                ),
                failure=AdapterFailure(
                    "adapter-start-failed", message, {**details, "failure": code}
                ),
            )

        while True:
            try:
                kind, payload = self._read_message(child, expired)
            except JsonlEndOfStreamError:
                terminal = self._finish_from_eos(initial_ms, tuple(diagnostics))
                return StartTerminated(constraints=constraints, result=terminal)
            except _EpochFailure as failure:
                if expired.is_set() or self._deadline_closed:
                    return start_failed(
                        _HANDSHAKE_TIMEOUT,
                        "the abort deadline expired before the handshake reply"
                        " was observed; the deadline is host abort policy, not"
                        " evidence",
                        {
                            "abort-deadline-ms": self._abort_deadline_ms,
                            "phase": "handshake",
                        },
                    )
                return start_failed(failure.code, failure.message, failure.details)
            if expired.is_set():
                return start_failed(
                    _HANDSHAKE_TIMEOUT,
                    "the abort deadline expired before the handshake reply"
                    " was observed; the deadline is host abort policy, not"
                    " evidence",
                    {
                        "abort-deadline-ms": self._abort_deadline_ms,
                        "phase": "handshake",
                    },
                )
            if kind == "diagnostic":
                diagnostics.append(self._map_diagnostic(initial_ms, payload))
                if len(diagnostics) > MAX_STARTUP_DIAGNOSTICS:
                    return start_failed(
                        _PEER_MALFORMED,
                        "the child exceeded the v1 startup diagnostic budget",
                        {"during": "handshake", "budget": MAX_STARTUP_DIAGNOSTICS},
                    )
                continue
            if kind == "session.unsupported":
                constraint = cast(str, payload["constraint"])
                code = cast(str, payload["code"])
                self._close_child()
                self._set_state("terminal")
                return self._unsupported_from_child(
                    run_id,
                    configuration,
                    (
                        constraints.seed,
                        constraints.clock,
                        constraints.locale,
                        constraints.timezone,
                        constraints.terminal,
                        constraints.filesystem,
                        constraints.network,
                    ),
                    constraint,
                    code,
                    payload,
                )
            if kind == "session.failed":
                error = cast(dict[str, JsonValue], payload["error"])
                self._close_child()
                self._set_state("terminal")
                return StartFailed(
                    run_id=run_id,
                    requested=configuration,
                    enforced=(
                        constraints.seed,
                        constraints.clock,
                        constraints.locale,
                        constraints.timezone,
                        constraints.terminal,
                        constraints.filesystem,
                        constraints.network,
                    ),
                    failure=AdapterFailure(
                        "adapter-start-failed",
                        f"the subject refused the session: {error['message']}",
                        {
                            "subject-code": _as_json_input(error["code"]),
                            "subject-details": _as_json_input(error.get("details")),
                        },
                    ),
                )
            if kind == "session.ready":
                observation_payload = cast(dict[str, JsonValue], payload["observation"])
                observation = self._map_observation(initial_ms, observation_payload)
                self._set_time_and_state(initial_ms, "idle")
                return Started(
                    constraints=constraints,
                    observation=observation,
                    diagnostics=tuple(diagnostics),
                )
            return start_failed(
                _PEER_LIFECYCLE,
                "the child answered session.hello with a message kind that"
                " is not a handshake reply",
                {"during": "handshake", "kind": kind},
            )

    def _unsupported_from_child(
        self,
        run_id: str,
        configuration: RunConfiguration,
        receipts: tuple[EnforcementReceipt, ...],
        constraint: str,
        code: str,
        payload: dict[str, JsonValue],
    ) -> StartResult:
        """Map a child's session.unsupported onto the contract's vocabulary.

        The child refuses one constraint. The run already negotiated every
        constraint successfully through the ports, so the honest contract
        shape is StartUnsupported against the full enforced prefix — which
        the contract cannot express (StartUnsupported requires the
        unsupported constraint to follow the enforced prefix in
        configuration-table order). The truthful shape available is
        StartFailed carrying the child's refusal, because claiming an
        enforcement failure that did not happen would fabricate evidence.
        """
        return StartFailed(
            run_id=run_id,
            requested=configuration,
            enforced=receipts,
            failure=AdapterFailure(
                "adapter-start-failed",
                f"the subject cannot serve the negotiated {constraint}"
                f" constraint: {payload['message']}",
                {
                    "constraint": constraint,
                    "subject-code": code,
                    "subject-details": _as_json_input(payload.get("details")),
                },
            ),
        )

    def dispatch(self, input_event: DispatchInput) -> EpochResult:
        if type(input_event) not in (KeyInput, TextInput, Resize):
            raise TypeError("dispatch input must be KeyInput, TextInput, or Resize")
        with self._state_lock:
            if self._state != "idle":
                raise RuntimeError("JSONL adapter is not idle")
            if input_event.at_ms != self._manual_time:
                raise ValueError("input must use the current manual time")
            self._state = "active"
        at_ms = input_event.at_ms
        if type(input_event) is TextInput:
            text = input_event.text

            def write_text() -> None:
                self._write_message(
                    cast(JsonlChildPort, self._child), "input.text", {"text": text}
                )

            return self._run_epoch(
                at_ms,
                write_text,
                "the input text could not be written to the child",
                "epoch",
            )
        if type(input_event) is KeyInput:
            keys: list[str] = list(input_event.keys)

            def write_key() -> None:
                key_payload: dict[str, JsonValue] = {"keys": list(keys)}
                self._write_message(
                    cast(JsonlChildPort, self._child),
                    "input.key",
                    _as_json_input(key_payload),
                )

            return self._run_epoch(
                at_ms,
                write_key,
                "the key input could not be written to the child",
                "epoch",
            )
        resize = cast(Resize, input_event)

        def write_resize() -> None:
            self._write_message(
                cast(JsonlChildPort, self._child),
                "input.resize",
                {"columns": resize.columns, "rows": resize.rows},
            )

        return self._run_epoch(
            at_ms,
            write_resize,
            "the resize could not be written to the child",
            "epoch",
        )

    def advance_clock(self, input_event: ClockAdvance) -> EpochResult:
        if type(input_event) is not ClockAdvance:
            raise TypeError("clock input must be ClockAdvance")
        with self._state_lock:
            if self._state != "idle":
                raise RuntimeError("JSONL adapter is not idle")
            if (
                self._manual_time is None
                or input_event.at_ms != self._manual_time + input_event.delta_ms
            ):
                raise ValueError("clock advance must move the current manual time")
            self._state = "active"
        at_ms = input_event.at_ms

        def write_clock() -> None:
            self._write_message(
                cast(JsonlChildPort, self._child),
                "input.clock",
                {"at_ms": int(at_ms)},
            )

        return self._run_epoch(
            at_ms,
            write_clock,
            "the clock advance could not be written to the child",
            "epoch",
        )

    def stop(self, input_event: Stop) -> TerminalResult:
        if type(input_event) is not Stop:
            raise TypeError("stop input must be Stop")
        with self._state_lock:
            if self._state != "idle":
                raise RuntimeError("JSONL adapter is not idle")
            if input_event.at_ms != self._manual_time:
                raise ValueError("stop must use the current manual time")
            self._state = "stopping"
        at_ms = input_event.at_ms
        try:
            self._write_message(cast(JsonlChildPort, self._child), "input.stop", {})
        except Exception:
            return self._fail_runtime(
                at_ms,
                _PEER_LIFECYCLE,
                "the input.stop message could not be written to the child",
                {"during": "write"},
            )
        return self._run_stop_drain(at_ms)
