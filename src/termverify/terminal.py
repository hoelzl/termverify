"""Public platform-neutral terminal adapter over the terminal binding port.

This module implements slices 2 and 3 of the accepted ConPTY adapter design
(`docs/agent/design/conpty-adapter-design.md`): the ``TerminalBindingPort``/
``TerminalChildPort`` protocols, truthful constraint negotiation, and the epoch
machinery — readiness-marker protocol, epoch loop, failure classification,
watchdog-driven abort deadline, and forced stop teardown.

**The adapter names no platform, and that is a checked property** (issue #268).
It was already true when this was ``termverify.conpty``: every platform
difference is absorbed by the binding port, so the epoch machinery here is
driven identically by the Windows pseudoconsole, by a POSIX pseudoterminal, and
by a fake. What #268 changed is that the names, the messages and the failure
taxonomy say so — a message naming a platform is a claim this layer has no
evidence for, because the port hides which binding it holds. The two shipped
bindings are :class:`ConptyBinding` and :class:`PosixPtyBinding`; hosts inject
one, and the adapter never asks which. ``tests/test_terminal_platform_neutrality.py``
ratchets the property: zero ``sys.platform``/``os.name`` reads, no import that
could make one, and no emitted message naming a platform. Crossing that zero is
a stop-and-return to the owner, not a waiver — the generalization was
authorized on the premise it measures.

All logic is testable against fake bindings, normalizers and watchdog triggers.
The native boundaries are ``termverify._conpty`` and ``termverify._posix_pty``;
of those two, only ``_conpty`` is omitted from the coverage ratchet, and
``_posix_pty`` joined it under per-platform pragmas (issue #267).

Integration evidence for the real paths is per binding, and is not equal:
``tests/test_conpty_integration.py`` proves end-to-end start/text/resize/exit,
forced stop and deadline abort against a cooperative fixture subject on the
Windows CI matrix. The POSIX binding's evidence today stops at the binding
(``tests/test_posix_pty_binding.py``); the matching adapter-level legs are
issue #269, and until they land nothing here should be read as a proven POSIX
end-to-end path.

Negotiation is truthful by construction:

- The adapter owns the ``terminal`` constraint and never delegates it:
  dimensions are an OS-level parameter of pseudoterminal creation on both
  bindings, platform support is decided by the binding port's explicit probe
  before any spawn, and requested terminal capabilities are rejected
  fail-closed because the capability registry is not activated.
- The six non-terminal constraints belong to injected ``ConstraintPorts``.
  The shipped default, :class:`ApplyNothingConstraintPorts`, reports every one
  of them ``constraint-not-enforced`` — no OS mechanism at this boundary
  enforces them — so ``start()`` with defaults ends as
  ``StartUnsupported(constraint="seed")`` before any child exists.
- Every receipt states its `termverify.enforcement-tier/v1` tier, validated
  against the fail-closed authorization matrix: the adapter's own terminal
  negotiation states ``os`` — geometry is an OS-level creation and resize
  parameter of the pseudoterminal in both bindings, proven by child
  observation on the Windows matrix at the adapter level and, for the POSIX
  binding, at the binding's own ``TIOCSWINSZ`` legs pending #269 — and
  injected ports may state only ``delivered`` —
  exact recorded values placed in the subject's spawn environment, honored
  only by subject cooperation. The opt-in ports that emit that tier live in
  ``termverify.cooperation``; the spawn is evidence-driven, with the child's
  environment overlay and working directory assembled from the validated
  receipts' delivery records under fail-closed disjointness invariants.

Readiness and quiescence are defined only by observable evidence:

- A verified subject cooperates by emitting an explicit readiness marker —
  after startup and after processing each input. A marker is
  :data:`READINESS_MARKER_PREFIX_DEFAULT` (configurable), a token, and
  :data:`READINESS_MARKER_TERMINATOR`; the token must be one the subject has
  not used before in this run. The adapter scans the decoded output stream
  in stream order and honours the first marker whose token is new; raw
  chunks are always fed to the normalizer unmodified and retained as ordered
  ``terminal.output`` events, so replaying the normalizer over the raw
  evidence reproduces the frames.
- **The marker is printable on purpose, and carries a token on purpose.**
  Both follow from how ConPTY delivers output, and neither is negotiable
  (issue #232). The POSIX binding does not need either constraint and
  inherits both anyway: one marker contract on both platforms, so a subject
  implements readiness once and runs under either binding (issue #204,
  boundary decision 3). The reasons below are therefore the *origin* of the
  shape, not a claim that a pty imposes it:

  1. ConPTY emits pass-through OSC on a different path from rendered text,
     and the OSC path is *ahead*. A marker written as a private-use OSC —
     which the default was until 2026-07-26 — therefore overtakes the very
     output it is supposed to bound: measured, a subject's single atomic
     write of ``TV_BEFORE`` + marker + ``TV_AFTER`` arrived as the marker
     alone, then the text. The adapter would end the epoch on a marker whose
     output had not been delivered, and report a frame missing it. Only text
     that goes through the renderer is ordered against other rendered
     output.
  2. Rendered text is screen *state*, and the console re-emits screen state
     whenever it repaints — after a scroll, a resize, or a teardown. A
     constant marker therefore arrives again in later epochs, and an epoch
     would complete on a marker its input never caused. A per-emission token
     is what distinguishes a new marker from a redrawn old one.

  The cost is that markers occupy screen cells and appear in frame
  evidence. Subjects should emit them where that is harmless — on their
  own newline-terminated line. A line *wrap* is not a hazard: wrapping is
  screen-buffer layout, not stream content, so a marker wider than the
  terminal arrives contiguous and is honoured (measured on the Windows
  host, issue #233 review). What the token charset defends against is a
  marker whose screen cells are disturbed mid-emission — a TUI patching
  cells with cursor-addressed rewrites interleaves console artefacts into
  the token — and such a candidate is skipped, so the epoch fails closed
  on its deadline instead of completing wrongly.
- Native end-of-stream plus the observed native exit record ends the run
  truthfully; a missing exit record is a structured failure, never a
  fabricated exit.
- Wall-clock silence is never evidence. The only wall-clock input is the
  mandatory, explicitly configured abort deadline: a watchdog armed before
  each blocking read force-closes the binding when it expires, which always
  produces a structured failure disclosing the deadline policy and never a
  successful epoch. That watchdog alone is not enough: because it is
  re-armed for every read, a subject trickling output just under the
  deadline never exceeds any single read's deadline and could hold an epoch
  open forever (finding R2). The same configured value therefore also bounds
  the epoch *as a whole*, checked between reads — so the worst case is up to
  **twice** the deadline, once for the epoch's own bound and once for the
  read in flight when it passes. It remains one policy with one message and
  no new evidence source; the recorded ``bound`` says which of the two
  fired, because a stalled read and a subject that never reaches readiness
  need opposite remediations. Retained output is bounded separately, which
  bounds memory rather than time: an epoch may retain only what its chunks
  can cost the one observation record they land in. They land there as a
  *single* coalesced ``terminal.output`` string (issue #195), so the binding
  ceiling at ordinary geometry is the per-string one, and only a terminal
  at 261,121 *total cells* or above makes the per-record string sum bind
  first.
  Chunk *count* is not a separate axis: coalescing means no number of reads
  can reach the protocol's collection ceiling.
- The deadline a host may safely configure is a property of the *binding*, not
  of this module, and the ConPTY binding has a disclosed floor: conhost defers
  client output while its unanswered ``CSI c`` device-attributes query waits
  (measured ~3.1 s; see the DA-stall disclosure in the adapter design
  document), so under that binding a deadline at or below that floor plus
  spawn overhead fails every real start by policy. Whether the POSIX binding
  has a floor of its own is unmeasured, and #269 is where it would be found;
  no floor has been assumed for it here.
"""

from __future__ import annotations

import re
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from typing import Any, Final, Literal, Protocol, cast, runtime_checkable

from termverify._key_encoding_v1 import encode_key_chord
from termverify._negotiation import AuthorizedTiers, negotiate
from termverify._terminal_binding import (
    TerminalClosedError,
    TerminalConcurrentIOError,
    TerminalEndOfStreamError,
    TerminalGeometryMismatchError,
)
from termverify.adapter import (
    AdapterFailure,
    AppliedConstraints,
    ClockAdvance,
    ClockConfiguration,
    ClockReceipt,
    ConstraintPorts,
    ConstraintUnsupported,
    DeliveryRecord,
    Diagnostic,
    DispatchInput,
    EpochCompleted,
    EpochResult,
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
from termverify.transcript import (
    _MAX_COLLECTION_ITEMS,
    _MAX_RECORD_STRING_BYTES,
    _MAX_STRING_BYTES,
)
from termverify.vt import (
    ScreenSnapshot,
    TerminalOutputNormalizer,
    VtNormalizationError,
    VtScreenNormalizer,
)

__all__ = [
    "ApplyNothingConstraintPorts",
    "ConptyBinding",
    "NormalizerFactory",
    "PosixPtyBinding",
    "READINESS_MARKER_PREFIX_DEFAULT",
    "READINESS_MARKER_TERMINATOR",
    "TerminalAdapter",
    "TerminalBindingPort",
    "TerminalChildPort",
    "TerminalWatchdogPort",
    "TimerWatchdog",
]

#: Default readiness-marker prefix. A marker is this prefix, a token, and
#: :data:`READINESS_MARKER_TERMINATOR`. The text is deliberately printable:
#: it has to reach the adapter *through the console renderer*, in order with
#: the output it bounds. Hosts can configure any non-empty prefix instead.
READINESS_MARKER_PREFIX_DEFAULT: Final = "<<termverify.ready:"

#: Closes every readiness marker. Not configurable: the token charset below
#: excludes ``>``, so this terminates a marker unambiguously whatever prefix
#: a host configures.
READINESS_MARKER_TERMINATOR: Final = ">>"

#: Longest legal marker token.
_MAX_MARKER_TOKEN: Final = 64

#: Longest a complete marker can be after its prefix: the token plus the
#: terminator. Bounds both how far the scanner looks for a terminator and how
#: much of a partial candidate it will hold — past this, no terminator can
#: still close a legal token, so the candidate was never a marker. The
#: terminator counts: a candidate holding a maximum-length token and the
#: first character of a split terminator is still viable, and dropping it
#: would lose the marker.
_MAX_MARKER_CANDIDATE: Final = _MAX_MARKER_TOKEN + len(READINESS_MARKER_TERMINATOR)

#: A marker's token must match this: printable, bounded, and free of any
#: character the console emits between the cells it renders. A candidate
#: whose token does not match is not a marker, so a marker whose screen
#: cells were disturbed mid-emission (a cursor-addressed rewrite) fails
#: closed into the epoch deadline rather than being honoured with a mangled
#: token — see the marker-protocol notes in the module docstring.
_MARKER_TOKEN = re.compile(rf"[0-9A-Za-z._-]{{1,{_MAX_MARKER_TOKEN}}}\Z")

#: UTF-8's worst case for one screen cell. The screen model stores any
#: character at or above U+00A0 in a single cell, so a cell can cost up to
#: four bytes in the frame lines the codec measures — counting cells as bytes
#: under-reserves for any non-ASCII screen.
_MAX_UTF8_BYTES_PER_CELL: Final = 4
_NORMALIZATION_DETAIL_BYTES: Final = 4096

#: Reserve for an observation record's fixed strings: the envelope's
#: protocol, kind, run and record identifiers, the cursor and mode values,
#: the event's own member names, and the member names around them. Unlike
#: the frame these do not scale with the geometry — the epoch's chunks reach
#: the record as a *single* coalesced event, so their envelope cost is paid
#: once rather than per chunk — and they measure ~216 bytes in practice.
#:
#: The margin is wide but not unconditional: `run_id` is host-supplied and
#: `_validate_run_id` constrains its charset, not its length, so the real
#: cost is ``206 + len(run_id)`` and a run identifier of 3,891 characters
#: (~3.8 KiB) is the first that defeats this reserve, after which the codec
#: rejects a record the adapter admitted. Callers are expected to use
#: identifiers of ordinary length; this is a stated assumption, not an
#: enforced invariant.
_FIXED_RECORD_STRING_BYTES: Final = 4 * 1024

#: The `termverify.enforcement-tier/v1` authorization matrix row for the
#: terminal-adapter architecture, in constraint order: the adapter's own
#: terminal negotiation emits ``os`` (geometry is a pseudoterminal
#: creation/resize parameter in both shipped bindings) and injected
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
class TerminalChildPort(Protocol):
    """Per-child binding surface, shaped exactly like ``ConptyChild``.

    ``PosixPtyChild`` is shaped to the same surface (issue #267), so the
    epoch machinery drives either without knowing which it holds.
    """

    @property
    def pid(self) -> int: ...

    @property
    def exit_status(self) -> int | ExitStatus | None: ...

    def read(self) -> str: ...

    def write(self, text: str) -> None: ...

    def resize(self, *, rows: int, columns: int) -> None: ...

    def is_alive(self) -> bool: ...

    def close(self, *, force: bool) -> None: ...


@runtime_checkable
class TerminalBindingPort(Protocol):
    """Injected boundary to a native pseudoterminal binding.

    Two are shipped — :class:`ConptyBinding` and :class:`PosixPtyBinding` —
    and the adapter cannot tell them apart, which is the point: every
    platform difference is absorbed here rather than branched on above.

    The explicit support probe makes platform support answerable at
    negotiation time — before any spawn — without the adapter reading
    ambient platform state. Fake bindings supply their own probe, so both
    negotiation outcomes are drivable on every platform.

    A binding reports failure through the error hierarchy in
    ``termverify._terminal_binding``: the adapter classifies those base
    types, so a third binding is classified correctly without the adapter
    learning its name.
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
    ) -> TerminalChildPort: ...


@runtime_checkable
class NormalizerFactory(Protocol):
    """Constructs one run's output normalizer at the initial dimensions."""

    def __call__(self, *, rows: int, columns: int) -> TerminalOutputNormalizer: ...


@runtime_checkable
class TerminalWatchdogPort(Protocol):
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


def _bounded_normalization_detail(value: str) -> str:
    """Bound one diagnostic value in UTF-8 bytes with disclosed truncation."""
    encoded = value.encode("utf-8", errors="backslashreplace")
    if len(encoded) <= _NORMALIZATION_DETAIL_BYTES:
        return encoded.decode("utf-8")
    hidden = len(encoded)
    while True:
        suffix = f"... (+{hidden} bytes)"
        prefix_budget = _NORMALIZATION_DETAIL_BYTES - len(suffix.encode("utf-8"))
        prefix = encoded[:prefix_budget].decode("utf-8", errors="ignore")
        actual_hidden = len(encoded) - len(prefix.encode("utf-8"))
        if actual_hidden == hidden:
            return prefix + suffix
        hidden = actual_hidden


class _ExitStatusChild:
    """Adapt a native child's raw status into protocol exit evidence."""

    def __init__(self, native: Any, convert_exit: Callable[[int], ExitStatus]) -> None:
        self._native = native
        self._convert_exit = convert_exit

    @property
    def pid(self) -> int:
        return cast(int, self._native.pid)

    @property
    def exit_status(self) -> ExitStatus | None:
        status = self._native.exit_status
        return None if status is None else self._convert_exit(status)

    def read(self) -> str:
        return cast(str, self._native.read())

    def write(self, text: str) -> None:
        self._native.write(text)

    def resize(self, *, rows: int, columns: int) -> None:
        self._native.resize(rows=rows, columns=columns)

    def is_alive(self) -> bool:
        return cast(bool, self._native.is_alive())

    def close(self, *, force: bool) -> None:
        self._native.close(force=force)


class ConptyBinding:
    """Windows binding port delegating to ``termverify._conpty``.

    The native module is imported inside the methods, not at module scope:
    this module is platform-neutral and importing it must not pull in a
    binding the host cannot use. That is also what keeps the probe honest —
    :meth:`is_supported` answers by asking the native layer, so a Windows
    host without the pseudoconsole entry points reports unsupported.
    """

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
    ) -> TerminalChildPort:
        from termverify._conpty import ConptyChild

        native = ConptyChild.spawn(
            argv, rows=rows, columns=columns, env_overlay=env_overlay, cwd=cwd
        )
        return _ExitStatusChild(native, lambda status: ExitStatus("code", status))


class PosixPtyBinding:
    """POSIX binding port delegating to ``termverify._posix_pty``.

    The sibling of :class:`ConptyBinding`, and deliberately its structural
    twin: same lazy native import, same probe-before-spawn contract, same
    child surface. Which of the two a host injects is the host's choice and
    the adapter never asks — that is what makes the adapter above this port
    platform-neutral rather than platform-branching.

    The platform claim is Linux only (issue #204, boundary decision 2), and
    :meth:`is_supported` is where that claim is made. Every other platform,
    macOS included, reports unsupported: not a claim that a pty cannot work
    there, but a refusal to claim a platform CI has never run.
    """

    def is_supported(self) -> bool:
        from termverify import _posix_pty

        return _posix_pty.is_supported()

    def spawn(
        self,
        argv: Sequence[str],
        *,
        rows: int,
        columns: int,
        env_overlay: Mapping[str, str] | None = None,
        cwd: str | None = None,
    ) -> TerminalChildPort:
        import signal

        from termverify._posix_pty import PosixPtyChild

        native = PosixPtyChild.spawn(
            argv, rows=rows, columns=columns, env_overlay=env_overlay, cwd=cwd
        )

        def convert_exit(status: int) -> ExitStatus:
            if status < 0:
                signal_number = -status
                try:
                    name = signal.Signals(signal_number).name.removeprefix("SIG")
                except ValueError:
                    name = str(signal_number)
                return ExitStatus("signal", name)
            return ExitStatus("code", status)

        return _ExitStatusChild(native, convert_exit)


class ApplyNothingConstraintPorts:
    """Truthful default ports: nothing is enforced at the terminal boundary."""

    def apply_seed(
        self, run_id: str, requested: int
    ) -> SeedReceipt | ConstraintUnsupported | AdapterFailure:
        del run_id, requested
        return ConstraintUnsupported(
            "seed",
            "constraint-not-enforced",
            "no OS mechanism binds a subject's RNG through a pseudoterminal;"
            " environment injection is subject cooperation, not enforcement",
        )

    def apply_clock(
        self, run_id: str, requested: ClockConfiguration
    ) -> ClockReceipt | ConstraintUnsupported | AdapterFailure:
        del run_id, requested
        return ConstraintUnsupported(
            "clock",
            "constraint-not-enforced",
            "the child runs on the ambient wall clock; manual-time injection"
            " is subject cooperation, not enforcement",
        )

    def apply_locale(
        self, run_id: str, requested: str
    ) -> LocaleReceipt | ConstraintUnsupported | AdapterFailure:
        del run_id, requested
        return ConstraintUnsupported(
            "locale",
            "constraint-not-enforced",
            "locale environment variables are advisory to the child, not"
            " boundary enforcement",
        )

    def apply_timezone(
        self, run_id: str, requested: str
    ) -> TimezoneReceipt | ConstraintUnsupported | AdapterFailure:
        del run_id, requested
        return ConstraintUnsupported(
            "timezone",
            "constraint-not-enforced",
            "timezone environment variables are advisory to the child, and"
            " named-timezone enforcement remains blocked on the owner",
        )

    def apply_terminal(
        self, run_id: str, requested: TerminalConfiguration
    ) -> TerminalReceipt | ConstraintUnsupported | AdapterFailure:
        del run_id, requested
        return ConstraintUnsupported(
            "terminal",
            "constraint-unsupported",
            "terminal enforcement is owned by the terminal adapter and cannot"
            " be delegated to injected ports",
        )

    def apply_filesystem(
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

    def apply_network(
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


def _validate_marker_prefix(prefix: object) -> str:
    if type(prefix) is not str:
        raise TypeError("readiness_marker_prefix must be a string")
    if not prefix:
        raise ValueError("readiness_marker_prefix must be non-empty")
    if not all(char.isprintable() for char in prefix):
        # The marker is printable so it travels the renderer's path, ordered
        # against the output it bounds (#232). A control character puts it
        # back on a pass-through path: "\x1b]7791;" is an OSC opener, and
        # ConPTY relays OSC *ahead* of rendered text — the exact ordering
        # defect the printable marker exists to fix (#233 review).
        raise ValueError(
            "readiness_marker_prefix must be printable: a control character"
            " would route the marker onto a pass-through path that can"
            " overtake the output the marker bounds"
        )
    if READINESS_MARKER_TERMINATOR in prefix:
        raise ValueError(
            "readiness_marker_prefix must not contain"
            f" {READINESS_MARKER_TERMINATOR!r}: it would terminate the marker"
            " before its token"
        )
    if _MARKER_TOKEN.match(prefix):
        # A prefix made only of token characters can be absorbed into a
        # neighbouring candidate's token: a stray occurrence followed by the
        # real marker yields one token spanning both, which is well-formed,
        # so the genuine token is never recorded and the next repaint of
        # that marker completes another epoch — exactly the double-honour
        # #232 exists to prevent.
        raise ValueError(
            "readiness_marker_prefix must contain a character outside"
            f" {_MARKER_TOKEN.pattern}, so it cannot be mistaken for part of"
            " a token"
        )
    return prefix


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
    delivery records must be mutually disjoint and may name at most one
    working directory; a violation raises :class:`_DeliveryInvariantError`
    for the caller to report as an invariant breach.

    Disjointness is compared **case-folded, on both platforms**, and that is
    the stricter of the two semantics rather than a Windows special case.
    Windows environment lookup is case-insensitive, so two case-variant
    entries would let one recorded delivery silently shadow another; POSIX
    lookup is case-sensitive, so there they are two distinct variables and
    folding refuses a pair that would have worked. Refusing the wider set
    unconditionally is what keeps this function free of a platform branch,
    and it fails in the safe direction: the cost is a refusal a host can fix
    by renaming, against a transcript that silently misreports which value
    the subject received. No shipped port delivers case-variant names, so
    nothing reaches it through them.
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
                    " case-insensitive environment semantics, which is the"
                    " stricter of the two platforms' and is applied on both;"
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

    def __init__(self, message: str, details: dict[str, JsonInput]) -> None:
        super().__init__(message)
        self.message = message
        self.details: dict[str, JsonInput] = dict(details)


class TerminalAdapter:
    """Drive one terminal subject through the injected terminal binding port.

    The subject command line is bound at construction, exactly as the direct
    adapter binds its application. The abort deadline is mandatory host
    policy with no default: it can only produce a structured failure, never
    evidence of quiescence.
    """

    def __init__(
        self,
        argv: Sequence[str],
        *,
        binding: TerminalBindingPort,
        abort_deadline_ms: int,
        constraint_ports: ConstraintPorts | None = None,
        normalizer_factory: NormalizerFactory | None = None,
        readiness_marker_prefix: str = READINESS_MARKER_PREFIX_DEFAULT,
        watchdog: TerminalWatchdogPort | None = None,
        monotonic: Callable[[], float] | None = None,
    ) -> None:
        self._argv = _validate_argv(argv)
        self._binding = binding
        self._abort_deadline_ms = _validate_deadline(abort_deadline_ms)
        if constraint_ports is None:
            constraint_ports = ApplyNothingConstraintPorts()
        self._constraints: ConstraintPorts = constraint_ports
        if normalizer_factory is None:
            normalizer_factory = VtScreenNormalizer
        self._normalizer_factory: NormalizerFactory = normalizer_factory
        self._marker_prefix = _validate_marker_prefix(readiness_marker_prefix)
        # Tokens already honoured. The console re-emits whatever stands on
        # screen whenever it repaints, so a marker's text can arrive again
        # long after the epoch it ended; only an unseen token counts as a new
        # one. One entry per completed epoch, so this grows with the run's
        # length and not with its output.
        self._honoured_tokens: set[str] = set()
        self._watchdog: TerminalWatchdogPort = (
            watchdog if watchdog is not None else TimerWatchdog()
        )
        # Injected so the per-epoch deadline is drivable without sleeping.
        # It measures the deadline the host already configured; it is not a
        # second wall-clock input, and it is never evidence.
        self._monotonic: Callable[[], float] = (
            monotonic if monotonic is not None else time.monotonic
        )
        self._deadline_bound: str = "read"
        self._state: _State = "created"
        self._state_lock = threading.Lock()
        self._manual_time: ManualTime | None = None
        self._child: TerminalChildPort | None = None
        self._normalizer: TerminalOutputNormalizer | None = None
        self._last_snapshot: ScreenSnapshot | None = None
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

    def _apply_terminal(
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
                "the injected terminal binding reports this host unsupported",
            )
        return TerminalReceipt(run_id, requested, tier="os")

    # --- marker protocol ---------------------------------------------------

    def _scan_for_marker(self) -> bool:
        """Consume the stream buffer up to and including one *new* marker.

        Markers count in stream order: transcript-position causality is the
        evidence, and the subject's cooperation contract is exactly one
        marker per processed input, each carrying a token it has not used
        before in this run.

        A candidate is skipped rather than honoured when its token has
        already been honoured — a terminal that repaints screen state puts a
        marker's text back in the stream whenever the viewport is redrawn,
        which ConPTY measurably does — or when the token is malformed, which
        is what a marker
        whose screen cells were disturbed mid-emission looks like. Skipping
        is the fail-closed direction: the epoch runs on to its deadline and
        reports a structured failure, rather than completing on output the
        subject never sent.

        Without a match, only the shortest tail that could still complete a
        split marker is retained. A candidate that has already outrun the
        longest legal token without reaching a terminator is dropped: it can
        never become a marker, and keeping it would let one stray prefix in
        the subject's own output retain the rest of the run.

        Rejected candidates resume the search one character past where they
        began, not past where they ended. A prefix the subject printed by
        accident would otherwise take the *next* genuine marker's terminator
        as its own, and skipping past that swallows the real marker.
        """
        prefix = self._marker_prefix
        scanned = 0
        while True:
            index = self._pending.find(prefix, scanned)
            if index < 0:
                break
            body = index + len(prefix)
            # Bounded: a terminator further out than a whole marker cannot be
            # this candidate's, and searching to the end of the buffer for it
            # is what let one stray prefix borrow a later marker's terminator.
            end = self._pending.find(
                READINESS_MARKER_TERMINATOR, body, body + _MAX_MARKER_CANDIDATE
            )
            if end < 0:
                if len(self._pending) - body < _MAX_MARKER_CANDIDATE:
                    # The rest may still be arriving; keep the candidate.
                    self._pending = self._pending[index:]
                    return False
                # Too much has arrived after this prefix for any terminator
                # to still close a legal token, so it was never a marker.
                scanned = index + 1
                continue
            token = self._pending[body:end]
            if _MARKER_TOKEN.match(token) and token not in self._honoured_tokens:
                self._honoured_tokens.add(token)
                self._pending = self._pending[end + len(READINESS_MARKER_TERMINATOR) :]
                return True
            scanned = index + 1
        # No prefix begins at or after ``scanned``, and nothing older than a
        # prefix-length tail can begin one.
        keep = len(prefix) - 1
        if not keep:
            self._pending = ""
            return False
        self._pending = self._pending[max(scanned, len(self._pending) - keep) :]
        return False

    # --- epoch loop --------------------------------------------------------

    def _read_chunk(self, child: TerminalChildPort, expired: threading.Event) -> str:
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
        except TerminalEndOfStreamError:
            raise
        except TerminalClosedError as error:
            raise _EpochFailure(
                "the terminal binding was closed outside the abort deadline",
                {"during": "read"},
            ) from error
        except TerminalConcurrentIOError as error:
            raise _EpochFailure(
                "concurrent native I/O was observed under the adapter's"
                " single-flight discipline",
                {"during": "read", "invariant": "single-flight"},
            ) from error
        except Exception as error:
            raise _EpochFailure(
                "a native terminal read failed", {"during": "read"}
            ) from error
        finally:
            disarm()

    def _feed(self, chunk: str) -> None:
        normalizer = cast(TerminalOutputNormalizer, self._normalizer)
        try:
            normalizer.feed(chunk)
        except VtNormalizationError as error:
            reason = getattr(error, "reason", None)
            sequence = getattr(error, "sequence", None)
            if type(reason) is not str or type(sequence) is not str:
                raise _EpochFailure(
                    "terminal output normalization failed", {"during": "normalize"}
                ) from error
            raise _EpochFailure(
                "the subject emitted terminal output the normalizer could not"
                " interpret",
                {
                    "during": "normalize",
                    "reason": _bounded_normalization_detail(reason),
                    "sequence": _bounded_normalization_detail(sequence),
                },
            ) from error
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
        self._last_snapshot = snapshot
        return snapshot

    def _observation(
        self,
        at_ms: ManualTime,
        chunks: Sequence[str],
        process: ProcessObservation | None,
    ) -> Observation:
        # Defense in depth, and cheap: the pre-read gate in
        # `_read_epoch_chunks` is what gives the "refused before any read"
        # property, but it does not sit on *every* path that emits a record.
        # `stop()` reaches here directly, protected only by the argument that
        # a bad geometry always failed its epoch first and so left the adapter
        # non-idle. That argument holds today, and an argument is exactly what
        # this slice has twice shipped in place of a check (rounds 6 and 8).
        # Every caller already classifies `_EpochFailure`.
        geometry_failure = self._geometry_failure()
        if geometry_failure is not None:
            raise geometry_failure
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

    def _epoch_output_budget(self) -> int:
        """Retained chunk bytes this epoch may cost its observation record.

        The epoch's chunks reach the transcript as **one** string: the
        recorder merges adjacent ``terminal.output`` events into a single
        event (issue #195), because chunk boundaries are OS read scheduling,
        not subject behavior. Two v1 ceilings therefore apply at once, and
        the budget is whichever binds first:

        - the **per-string** ceiling, which the merged chunk meets on its
          own. At ordinary geometry this is the binding one, and at half the
          per-record sum it is the reason a budget derived only from that
          sum admitted epochs the codec rejected — measured at 1.98x the
          ceiling for a plain 80x24 run.
        - the **per-record string sum**, less what the rest of the record
          costs. That is dominated by the frame, at a geometry the host
          chooses and ``dispatch(Resize(...))`` can change mid-run, so it is
          computed rather than reserved: a flat headroom was wrong in both
          directions, too small for a wide terminal and too large for an
          ordinary one.

        The frame's cost is counted in **bytes, not cells**. The codec counts
        UTF-8 bytes, and the screen model puts any character at or above
        U+00A0 into a cell one-for-one, so box drawing costs three bytes per
        cell and an emoji four. Reserving one byte per cell under-reserved by
        up to 4x (adversarial review of this PR, round 4). Four bytes per
        cell is UTF-8's worst case per code point, so the reserve cannot be
        short.

        That under-reserve is only observable where the per-record sum is the
        binding ceiling, which is above ~261,000 cells: below it the
        per-string ceiling binds and the frame reserve is entirely slack. The
        witness is therefore a large 4-byte-per-cell frame — 800x400 of
        emoji, which the tests exercise — not an ordinary TUI. An earlier
        revision of this docstring cited a box-drawn 100x30, which was true
        of the budget shape round 4 rejected and which #195 and the ``min()``
        below then made false (round 7, finding 3).

        Bounded here: the frame's *aggregate* byte cost against the
        per-record sum. Bounded by ``_geometry_failure``, because bytes
        cannot express them, are the frame's other two costs: its row count
        against the record's collection ceiling, and one frame **line** —
        a single string of ``columns`` code points — against the per-string
        ceiling.
        """
        frame_bytes = _MAX_UTF8_BYTES_PER_CELL * self._rows * self._columns
        record_budget = (
            _MAX_RECORD_STRING_BYTES - frame_bytes - _FIXED_RECORD_STRING_BYTES
        )
        return min(_MAX_STRING_BYTES, record_budget)

    def _geometry_failure(self) -> _EpochFailure | None:
        """Why this geometry admits no recordable epoch, or ``None``.

        The frame meets three v1 ceilings, in three different units, and one
        check cannot serve all three. Each axis gets its own, and the failure
        details name the axis that bound rather than a single number the host
        would have to reverse-engineer:

        - **rows** against the record's collection ceiling. `frame.lines` is
          one item per row, so above it no epoch is recordable at any cell
          count — a ten-column terminal reaches it at 163,850 cells, a third
          of the cell threshold.
        - **columns** against the per-string ceiling, which one frame line
          meets on its own at ``4 * columns`` bytes. Only a single-row
          terminal can reach this without the cell bound firing first: at two
          rows, any width over 262,144 already exceeds the cell threshold.
        - **cells**, through the byte budget, which is the aggregate case.

        The row and column checks replaced an argument that they were
        unreachable through the real binding because ``COORD`` is 16-bit.
        Measured on the Windows dev host, that is simply false: ``PTY()``
        range-checks nothing, and 262,145x1, 1,048,577x1, 10x100,000 and
        10x32,768 all create a pseudoconsole and spawn into it. A geometry
        that is cheap to check is not worth an argument about whether a host
        can request it (round 8, finding B1).
        """
        if self._rows > _MAX_COLLECTION_ITEMS:
            return _EpochFailure(
                "the requested terminal has more rows than one observation"
                " record's frame may carry, so no epoch can be recorded at"
                " this geometry",
                {"budget": "geometry", "terminal-rows": self._rows},
            )
        if self._columns > _MAX_STRING_BYTES // _MAX_UTF8_BYTES_PER_CELL:
            return _EpochFailure(
                "the requested terminal is wider than one line of its own"
                " frame may be, so no epoch can be recorded at this geometry",
                {"budget": "geometry", "terminal-columns": self._columns},
            )
        if self._epoch_output_budget() <= 0:
            return _EpochFailure(
                "the requested terminal leaves an observation record no room"
                " for output once its own frame is reserved, so no epoch can"
                " be recorded at this geometry",
                {
                    "budget": "geometry",
                    "terminal-cells": self._rows * self._columns,
                },
            )
        return None

    def _read_epoch_chunks(
        self, child: TerminalChildPort, chunks: list[str], expired: threading.Event
    ) -> None:
        """Read until one readiness marker is observed in stream order.

        Bounded on every axis an unbounded loop would otherwise leak, so a
        subject that never emits the marker can neither hold the epoch open
        nor outgrow what its own evidence can hold:

        - **time**, by the configured abort deadline applied to the epoch as
          a whole. The per-read watchdog cannot do this: because it is
          re-armed for every read, a trickle just under it never exceeds any
          single read's deadline (finding R2). The epoch therefore carries
          its own deadline, checked between reads.
        - **retained output bytes**, against what the single coalesced
          ``terminal.output`` string those chunks become may cost its
          observation record.

        ``TerminalChildPort.read`` may return an empty string, and since the
        ConPTY binding took ownership of decoding (issue #197) it regularly
        does: a native read landing inside a multi-byte codepoint decodes to
        nothing until the rest of it arrives. Empty reads are skipped here
        rather than retained — they are not evidence, and they never advance
        the byte counter, so counting them would be the one way an epoch
        could hold unbounded chunks. Their bytes are counted on the read that
        completes the character. A port that returned empty strings forever
        would still be ended by the epoch deadline above, which is the only
        bound that does not depend on the port yielding anything.

        The per-object cost of retention is not counted either: at the
        ceiling a two-byte-per-read trickle retains ~27 MB of Python objects
        (a one-byte trickle costs less, ~8 MB, because single-character ASCII
        decodes are interned) before the deadline or this budget ends it.

        Each bound is a structured failure, never a claimed epoch.
        """
        # Before the marker scan, not inside the read loop. The geometry is
        # fixed for the whole epoch (only `dispatch(Resize(...))` moves it,
        # between epochs), and an epoch whose marker is already buffered
        # returns below without ever reading — which let a resize past the
        # threshold complete an epoch that the codec then rejected, losing
        # the run's evidence at the end (round 6, finding 1). Every axis is
        # checked here for that reason, and `_geometry_failure` owns which
        # axes those are.
        geometry_failure = self._geometry_failure()
        if geometry_failure is not None:
            raise geometry_failure
        budget = self._epoch_output_budget()
        if self._scan_for_marker():
            return
        epoch_deadline_at = self._monotonic() + self._abort_deadline_ms / 1000
        output_bytes = 0
        while True:
            chunk = self._read_chunk(child, expired)
            # An empty decode is not evidence: it means the native read
            # landed inside a codepoint and the binding is holding those
            # bytes until the rest arrives. Recording it would put a
            # `terminal.output` event in the observation asserting the child
            # emitted nothing, and replaying it feeds the normalizer nothing.
            # The bytes are not lost — they surface on the read that
            # completes the character, and are counted then.
            if chunk:
                # Count before honoring the marker: the marker-bearing chunk
                # is retained like any other, so excluding it would let the
                # epoch exceed its own bound by a whole read.
                try:
                    chunk_bytes = len(chunk.encode("utf-8"))
                except UnicodeEncodeError:
                    # The codec measures strict UTF-8, so a chunk that cannot
                    # be encoded (a lone surrogate from an injected port; the
                    # shipped bindings decode with ``errors="replace"``) would
                    # produce an observation the serializer must reject,
                    # losing the whole transcript at `transcript()` time.
                    # Fail the epoch here instead, before any such chunk is
                    # retained.
                    raise _EpochFailure(
                        "the subject emitted output that cannot be represented"
                        " as UTF-8 evidence",
                        {"during": "read", "encoding": "utf-8"},
                    ) from None
                output_bytes += chunk_bytes
                if output_bytes > budget:
                    raise _EpochFailure(
                        "the epoch retained more output than one observation"
                        " record may carry; the budget is adapter abort policy,"
                        " not evidence",
                        {"budget": "bytes", "epoch-output-byte-budget": budget},
                    )
                chunks.append(chunk)
                self._feed(chunk)
                self._pending += chunk
                if self._scan_for_marker():
                    return
            if self._monotonic() >= epoch_deadline_at:
                # The per-read watchdog cannot end this: a trickle just under
                # the deadline never exceeds any single read's deadline, which
                # is exactly finding R2. The epoch's own deadline — the same
                # configured value — is what ends it, and the abort is the
                # ordinary deadline abort, classified by `expired` below.
                if not expired.is_set():
                    # Only when the watchdog did not already fire: a stalled
                    # read that won the close race arrives here with the
                    # deadline spent, and it is a stalled read, not a subject
                    # that never reached readiness.
                    self._deadline_bound = "epoch"
                expired.set()
                raise _EpochFailure(
                    "the abort deadline expired before readiness evidence was observed",
                    {"during": "read"},
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
        self,
        at_ms: ManualTime,
        message: str,
        details: dict[str, JsonInput],
        observation: Observation | None = None,
    ) -> TerminalResult:
        if not self._close_child():
            details = {**details, "close": "failed"}
        self._set_time_and_state(at_ms, "terminal")
        return TerminalResult(
            observation,
            RunFailed(AdapterFailure("adapter-runtime-failed", message, details)),
        )

    def _failure_observation_from_exit(
        self,
        at_ms: ManualTime,
        chunks: Sequence[str],
        details: dict[str, JsonInput],
    ) -> Observation | None:
        """Retain an exit observed before a later epoch failure.

        The raw chunks and native exit remain evidence even when the epoch
        itself must fail — a normalization rejection (#283) or an expired
        abort deadline (#284). This deliberately does not call
        ``_snapshot``: it reuses only the last successfully normalized snapshot.
        That snapshot may belong to a larger pre-resize geometry, so its frame
        is accounted against the record's string budget before it is attached:
        an observation the codec must reject would lose the whole transcript.
        """
        child = cast(TerminalChildPort, self._child)
        try:
            status = child.exit_status
        except Exception:
            # A raising injected port means the exit evidence is unavailable;
            # the normalization failure must still proceed without it.
            return None
        if status is None:
            return None
        if type(status) is int:
            status = ExitStatus("code", status)
        if type(status) is not ExitStatus:
            return None
        snapshot = self._last_snapshot
        if snapshot is None:
            return None
        frame: Frame | None = snapshot.frame
        try:
            frame_bytes = sum(
                len(line.encode("utf-8")) for line in snapshot.frame.lines
            )
            chunks_bytes = sum(len(chunk.encode("utf-8")) for chunk in chunks)
        except UnicodeEncodeError:
            frame_bytes = _MAX_RECORD_STRING_BYTES
            chunks_bytes = 0
        if (
            frame_bytes + chunks_bytes + _FIXED_RECORD_STRING_BYTES
            > _MAX_RECORD_STRING_BYTES
        ):
            frame = None
            details["observation-frame"] = "omitted-budget"
        return Observation(
            at_ms,
            {
                "terminal": {
                    "columns": snapshot.frame.columns,
                    "rows": snapshot.frame.rows,
                }
            },
            tuple(Event("terminal.output", {"chunk": chunk}) for chunk in chunks),
            UiObservation(
                regions=(),
                focus=None,
                cursor=snapshot.cursor,
                mode=snapshot.mode,
            ),
            frame=frame,
            process=ProcessObservation.exited(status),
        )

    def _deadline_abort(
        self, at_ms: ManualTime, chunks: Sequence[str]
    ) -> TerminalResult:
        # ``bound`` is recorded because two aborts that look identical need
        # opposite remediations: ``read`` means one read blocked for the whole
        # deadline (a stalled subject), ``epoch`` means the subject kept
        # producing output but never reached readiness (raise the deadline, or
        # fix the marker). Without it the evidence cannot tell them apart.
        bound = self._deadline_bound
        self._deadline_bound = "read"
        details: dict[str, JsonInput] = {
            "abort-deadline-ms": self._abort_deadline_ms,
            "bound": bound,
        }
        # An exit observed before the deadline fired is evidence about the
        # process, not clemency for the epoch: it is retained, and the
        # expired epoch stays failed (issue #284 policy).
        observation = self._failure_observation_from_exit(at_ms, chunks, details)
        return self._fail_runtime(
            at_ms,
            "the abort deadline expired before quiescence evidence was"
            " observed; the deadline is host abort policy, not evidence",
            details,
            observation,
        )

    def _finish_from_exit(
        self, at_ms: ManualTime, chunks: Sequence[str]
    ) -> TerminalResult:
        child = cast(TerminalChildPort, self._child)
        try:
            status = child.exit_status
        except Exception:
            return self._fail_runtime(
                at_ms,
                "the native exit record could not be observed",
                {"during": "exit-record"},
            )
        if status is None:
            return self._fail_runtime(
                at_ms,
                "the child exited but no native exit record was observed",
                {"missing": "exit-record"},
            )
        if type(status) is int:
            status = ExitStatus("code", status)
        if type(status) is not ExitStatus:
            return self._fail_runtime(
                at_ms,
                "the native exit record is invalid",
                {"during": "exit-record"},
            )
        try:
            observation = self._observation(
                at_ms, chunks, ProcessObservation.exited(status)
            )
        except _EpochFailure as failure:
            return self._fail_runtime(at_ms, failure.message, failure.details)
        if not self._close_child():
            return self._fail_runtime(
                at_ms,
                "the terminal binding could not be closed after the child exited",
                {"during": "close"},
                observation,
            )
        self._set_time_and_state(at_ms, "terminal")
        return TerminalResult(observation, RunFinished(status))

    def _run_epoch(
        self,
        at_ms: ManualTime,
        write: Callable[[], None] | None,
        write_step: str,
        write_failure: str,
    ) -> EpochResult:
        child = cast(TerminalChildPort, self._child)
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
                except _EpochFailure:
                    # A step that already built its structured failure (for
                    # example the geometry-structured resize refusal) must
                    # not be re-wrapped into the generic step details.
                    raise
                except Exception as error:
                    raise _EpochFailure(
                        write_failure,
                        {"during": write_step, "reason": str(error)},
                    ) from error
            self._read_epoch_chunks(child, chunks, expired)
            if expired.is_set():
                # The deadline expired during this epoch even though a marker
                # was still observed (the forced close failed or lost the
                # race): the abort policy fired, so no successful epoch may
                # be claimed.
                return self._deadline_abort(at_ms, chunks)
            observation = self._observation(at_ms, chunks, None)
        except TerminalEndOfStreamError:
            # Reaching this handler with the deadline already expired is not
            # a policy violation: the end of stream was observed no later
            # than the deadline-driven close reaching the read — an EIO that
            # lands in the expire→wake window is indistinguishable here from
            # an observation that preceded the expiry — and the owner's
            # #284 policy lets an end of stream observed before the close
            # arrives finish the run. An expiry with no end of stream
            # observed never reaches this handler: the close interrupts the
            # read first, which classifies as the deadline abort above.
            return self._finish_from_exit(at_ms, chunks)
        except _EpochFailure as failure:
            if expired.is_set() or self._deadline_closed:
                return self._deadline_abort(at_ms, chunks)
            failure_observation = (
                self._failure_observation_from_exit(at_ms, chunks, failure.details)
                if failure.details.get("during") == "normalize"
                else None
            )
            return self._fail_runtime(
                at_ms, failure.message, failure.details, failure_observation
            )
        self._set_time_and_state(at_ms, "idle")
        return EpochCompleted(observation)

    # --- adapter protocol --------------------------------------------------

    def start(self, run_id: str, configuration: RunConfiguration) -> StartResult:
        if type(configuration) is not RunConfiguration:
            raise TypeError("configuration must be RunConfiguration")
        _validate_run_id(run_id)
        with self._state_lock:
            if self._state != "created":
                raise RuntimeError("terminal adapter has already started")
            self._state = "negotiating"
        negotiated = negotiate(
            run_id,
            configuration,
            (
                lambda: self._constraints.apply_seed(run_id, configuration.seed),
                lambda: self._constraints.apply_clock(run_id, configuration.clock),
                lambda: self._constraints.apply_locale(run_id, configuration.locale),
                lambda: self._constraints.apply_timezone(
                    run_id, configuration.timezone
                ),
                lambda: self._apply_terminal(run_id, configuration.terminal),
                lambda: self._constraints.apply_filesystem(
                    run_id, configuration.filesystem
                ),
                lambda: self._constraints.apply_network(run_id, configuration.network),
            ),
            _AUTHORIZED_TIERS,
        )
        if not isinstance(negotiated, tuple):
            self._set_state("terminal")
            return negotiated
        receipts = tuple(negotiated)

        def start_failed(
            message: str,
            details: dict[str, JsonInput],
            *,
            close_child: bool = False,
        ) -> StartFailed:
            if close_child and not self._close_child():
                details = {**details, "close": "failed"}
            self._set_state("terminal")
            return StartFailed(
                run_id=run_id,
                requested=configuration,
                applied=receipts,
                failure=AdapterFailure("adapter-start-failed", message, details),
            )

        self._set_state("initializing")
        constraints = AppliedConstraints(
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
        except _DeliveryInvariantError as breach:
            # Defense-in-depth against a buggy or hostile injected port:
            # the shipped ports deliver disjoint, closed variable sets, so
            # this invariant breach is not reachable through them. It occurs
            # after negotiation completed, with the full receipt set
            # available for diagnostics, and is never silently merged.
            return start_failed(
                "the delivered spawn environment violates the delivery invariants",
                {"during": "spawn-overlay", "invariant": breach.invariant},
            )
        try:
            self._child = self._binding.spawn(
                self._argv,
                rows=terminal.rows,
                columns=terminal.columns,
                env_overlay=env_overlay,
                cwd=cwd,
            )
        except TerminalGeometryMismatchError as mismatch:
            # The console cannot, or provably did not, adopt the requested
            # geometry: name what was requested and what was adopted rather
            # than collapsing into the generic spawn failure — the receipt's
            # tier="os" claim must never stand for a geometry the subject
            # did not run at (issue #228).
            geometry_details: dict[str, JsonInput] = {
                "during": "spawn",
                "terminal-rows": terminal.rows,
                "terminal-columns": terminal.columns,
                "reason": str(mismatch),
            }
            if mismatch.adopted is not None:
                geometry_details["adopted-rows"] = mismatch.adopted[0]
                geometry_details["adopted-columns"] = mismatch.adopted[1]
            return start_failed(
                "the terminal binding did not adopt the requested terminal geometry",
                geometry_details,
            )
        except Exception as error:
            return start_failed(
                "the terminal child could not be spawned",
                {"during": "spawn", "reason": str(error)},
            )
        self._columns = terminal.columns
        self._rows = terminal.rows
        self._pending = ""
        self._last_snapshot = None
        try:
            self._normalizer = self._normalizer_factory(
                rows=terminal.rows, columns=terminal.columns
            )
        except Exception:
            return start_failed(
                "the output normalizer could not be constructed",
                {"during": "normalizer"},
                close_child=True,
            )
        try:
            self._snapshot()
        except _EpochFailure as snapshot_failure:
            return start_failed(
                snapshot_failure.message,
                snapshot_failure.details,
                close_child=True,
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
            applied=receipts,
            failure=AdapterFailure(
                "adapter-start-failed", failure.message, failure.details
            ),
            observation=terminal_result.observation,
        )

    def dispatch(self, input_event: DispatchInput) -> EpochResult:
        if type(input_event) not in (KeyInput, TextInput, Resize):
            raise TypeError("dispatch input must be KeyInput, TextInput, or Resize")
        with self._state_lock:
            if self._state != "idle":
                raise RuntimeError("terminal adapter is not idle")
            if input_event.at_ms != self._manual_time:
                raise ValueError("input must use the current manual time")
            self._state = "active"
        if type(input_event) is KeyInput:
            encoded = encode_key_chord(input_event.keys)
            if encoded is None:
                return self._fail_runtime(
                    input_event.at_ms,
                    "the key chord has no termverify.key-encoding/v1 form;"
                    " the registry fails closed rather than drop a modifier"
                    " or misrepresent the base",
                    {
                        "unsupported": "key-encoding",
                        "keys": list(input_event.keys),
                    },
                )
            key_child = cast(TerminalChildPort, self._child)

            def write_key() -> None:
                key_child.write(encoded)

            return self._run_epoch(
                input_event.at_ms,
                write_key,
                "write",
                "the encoded key input could not be written to the child",
            )
        child = cast(TerminalChildPort, self._child)
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
            try:
                child.resize(rows=resize.rows, columns=resize.columns)
            except TerminalGeometryMismatchError as mismatch:
                # The geometry boundary is evidence, not an opaque write
                # failure: name what was requested, what the binding adopted
                # (when it measured anything), and why the resize was refused.
                # The normalizer is not notified, so it is never told about a
                # geometry the child does not have (issue #228). What the
                # binding did with the old size is the binding's statement to
                # make in `reason`, not this layer's to assert -- ConPTY
                # provably keeps the previous size, and that is a fact about
                # ConPTY.
                details: dict[str, JsonInput] = {
                    "during": "resize",
                    "terminal-rows": resize.rows,
                    "terminal-columns": resize.columns,
                    "reason": str(mismatch),
                }
                if mismatch.adopted is not None:
                    details["adopted-rows"] = mismatch.adopted[0]
                    details["adopted-columns"] = mismatch.adopted[1]
                raise _EpochFailure(
                    "the terminal binding did not adopt the requested resize geometry",
                    details,
                ) from mismatch
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
                raise RuntimeError("terminal adapter is not idle")
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
                raise RuntimeError("terminal adapter is not idle")
            if input_event.at_ms != self._manual_time:
                raise ValueError("stop must use the current manual time")
            self._state = "stopping"
        at_ms = input_event.at_ms
        child = cast(TerminalChildPort, self._child)
        if not self._close_child():
            return self._fail_runtime(
                at_ms,
                "the terminal binding could not be closed on forced stop",
                {"during": "close"},
            )
        try:
            status = child.exit_status
        except Exception:
            return self._fail_runtime(
                at_ms,
                "the native exit record could not be observed",
                {"during": "exit-record"},
            )
        if status is None:
            return self._fail_runtime(
                at_ms,
                "forced stop observed no native exit record",
                {"missing": "exit-record"},
            )
        if type(status) is int:
            status = ExitStatus("code", status)
        if type(status) is not ExitStatus:
            return self._fail_runtime(
                at_ms,
                "the native exit record is invalid",
                {"during": "exit-record"},
            )
        try:
            observation = self._observation(
                at_ms, (), ProcessObservation.exited(status)
            )
        except _EpochFailure as failure:
            return self._fail_runtime(at_ms, failure.message, failure.details)
        self._set_time_and_state(at_ms, "terminal")
        return TerminalResult(
            observation,
            RunFinished(status),
            diagnostics=(
                Diagnostic(
                    at_ms,
                    "forced-termination",
                    "the run was ended by forced terminal teardown; output"
                    " produced after the last observed readiness marker may"
                    " be lost",
                ),
            ),
        )
