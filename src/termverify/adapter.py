"""Immutable, framework-neutral contracts for deterministic adapters."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal, Protocol

from termverify.transcript import JsonValue, _is_well_formed_language_tag

__all__ = [
    "Adapter",
    "AdapterFailure",
    "ClockAdvance",
    "ClockConfiguration",
    "ClockReceipt",
    "ConstraintName",
    "ConstraintPorts",
    "ConstraintUnsupported",
    "Cursor",
    "Diagnostic",
    "DispatchInput",
    "EnforcedConstraints",
    "EnforcementReceipt",
    "EpochCompleted",
    "EpochResult",
    "Event",
    "ExitStatus",
    "FilesystemConfiguration",
    "FilesystemReceipt",
    "Frame",
    "FrozenJsonValue",
    "JsonInput",
    "LocaleReceipt",
    "ManualTime",
    "NetworkConfiguration",
    "NetworkEndpoint",
    "NetworkReceipt",
    "Observation",
    "ProcessObservation",
    "Region",
    "Resize",
    "RunConfiguration",
    "RunFailed",
    "RunFinished",
    "SeedReceipt",
    "StartFailed",
    "Started",
    "StartResult",
    "StartTerminated",
    "StartUnsupported",
    "Stop",
    "TerminalConfiguration",
    "TerminalReceipt",
    "TerminalResult",
    "TextInput",
    "TimezoneReceipt",
    "UiObservation",
    "freeze_json",
]

type ConstraintName = Literal[
    "seed",
    "clock",
    "locale",
    "timezone",
    "terminal",
    "filesystem",
    "network",
]
type FrozenJsonValue = (
    None
    | bool
    | int
    | float
    | str
    | tuple[FrozenJsonValue, ...]
    | Mapping[str, FrozenJsonValue]
)
type JsonInput = (
    None
    | bool
    | int
    | float
    | str
    | list[JsonInput]
    | tuple[JsonInput, ...]
    | dict[str, JsonInput]
    | Mapping[str, JsonInput]
)

_CONSTRAINT_ORDER: tuple[ConstraintName, ...] = (
    "seed",
    "clock",
    "locale",
    "timezone",
    "terminal",
    "filesystem",
    "network",
)
_IDENTIFIER = re.compile(r"^[a-z0-9._-]+$")
_MAX_SEED = 2**64 - 1


def freeze_json(value: JsonInput) -> FrozenJsonValue:
    """Copy a JSON-compatible value into a transitively immutable representation."""
    if value is None:
        return value
    if type(value) is bool:
        return value
    if type(value) is int:
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError("JSON numbers must be finite")
        return value
    if type(value) is str:
        return value
    if isinstance(value, (bool, int, float, str)):
        raise TypeError("JSON scalars must use an exact JSON builtin type")
    if isinstance(value, (list, tuple)):
        return tuple(freeze_json(item) for item in value)
    if isinstance(value, Mapping):
        frozen: dict[str, FrozenJsonValue] = {}
        for key, item in value.items():
            if type(key) is not str:
                raise TypeError("JSON object keys must be strings")
            frozen[key] = freeze_json(item)
        return MappingProxyType(frozen)
    raise TypeError("value is not JSON-compatible")


def _require_plain_int(value: object, name: str, *, positive: bool = False) -> int:
    if type(value) is not int:
        raise TypeError(f"{name} must be an integer")
    if positive and value <= 0:
        raise ValueError(f"{name} must be positive")
    if not positive and value < 0:
        raise ValueError(f"{name} must be non-negative")
    return value


def _require_non_empty(value: object, name: str) -> str:
    if type(value) is not str:
        raise TypeError(f"{name} must be a string")
    if not value:
        raise ValueError(f"{name} must be non-empty")
    return value


def _require_choice(value: object, name: str, choices: tuple[str, ...]) -> str:
    if type(value) is not str:
        raise TypeError(f"{name} must be a string")
    if value not in choices:
        raise ValueError(f"{name} is invalid")
    return value


def _validate_run_id(run_id: object) -> str:
    value = _require_non_empty(run_id, "run_id")
    if _IDENTIFIER.fullmatch(value) is None:
        raise ValueError("run_id has invalid characters")
    return value


class ManualTime(int):
    """A non-negative manual-clock value in integer milliseconds."""

    __slots__ = ()

    def __new__(cls, value: int) -> ManualTime:
        if type(value) is cls:
            return value
        return int.__new__(cls, _require_plain_int(value, "time"))


@dataclass(frozen=True, slots=True)
class ClockConfiguration:
    """Requested manual clock configuration."""

    initial_ms: int

    def __post_init__(self) -> None:
        _require_plain_int(self.initial_ms, "initial_ms")


@dataclass(frozen=True, slots=True)
class TerminalConfiguration:
    """Requested terminal dimensions and syntax-level capability selectors."""

    columns: int
    rows: int
    capabilities: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_plain_int(self.columns, "columns", positive=True)
        _require_plain_int(self.rows, "rows", positive=True)
        if type(self.capabilities) is not tuple:
            raise TypeError("capabilities must be a tuple")
        if any(type(item) is not str or not item for item in self.capabilities):
            raise ValueError("capabilities must contain non-empty strings")
        if self.capabilities != tuple(sorted(self.capabilities)):
            raise ValueError("capabilities must be sorted")
        if len(self.capabilities) != len(set(self.capabilities)):
            raise ValueError("capabilities must be unique")


@dataclass(frozen=True, slots=True)
class FilesystemConfiguration:
    """Requested named sandbox-root capability."""

    root_id: str

    def __post_init__(self) -> None:
        _require_non_empty(self.root_id, "root_id")


@dataclass(frozen=True, slots=True, order=True)
class NetworkEndpoint:
    """One syntax-level network allow-list endpoint."""

    host: str
    port: int

    def __post_init__(self) -> None:
        _require_non_empty(self.host, "host")
        if type(self.port) is not int:
            raise TypeError("port must be an integer")
        if not 1 <= self.port <= 65535:
            raise ValueError("port must be between 1 and 65535")


@dataclass(frozen=True, slots=True)
class NetworkConfiguration:
    """Requested network denial or syntax-level allow list."""

    mode: Literal["deny", "allow-list"]
    allowed: tuple[NetworkEndpoint, ...] = ()

    def __post_init__(self) -> None:
        _require_choice(self.mode, "network mode", ("deny", "allow-list"))
        if type(self.allowed) is not tuple:
            raise TypeError("allowed endpoints must be a tuple")
        if any(type(item) is not NetworkEndpoint for item in self.allowed):
            raise TypeError("allowed endpoints must contain NetworkEndpoint values")
        if self.mode == "deny" and self.allowed:
            raise ValueError("deny mode cannot have allowed endpoints")
        if self.allowed != tuple(sorted(self.allowed)):
            raise ValueError("allowed endpoints must be sorted")
        if len(self.allowed) != len(set(self.allowed)):
            raise ValueError("allowed endpoints must be unique")

    @classmethod
    def deny(cls) -> NetworkConfiguration:
        return cls(mode="deny")

    @classmethod
    def allow_list(cls, endpoints: tuple[tuple[str, int], ...]) -> NetworkConfiguration:
        if type(endpoints) is not tuple:
            raise TypeError("allow-list endpoints must be a tuple")
        return cls(
            mode="allow-list",
            allowed=tuple(NetworkEndpoint(host, port) for host, port in endpoints),
        )


@dataclass(frozen=True, slots=True)
class RunConfiguration:
    """All deterministic constraints requested for one adapter run."""

    seed: int
    clock: ClockConfiguration
    locale: str
    timezone: str
    terminal: TerminalConfiguration
    filesystem: FilesystemConfiguration
    network: NetworkConfiguration

    def __post_init__(self) -> None:
        _require_plain_int(self.seed, "seed")
        if self.seed > _MAX_SEED:
            raise ValueError("seed must fit an unsigned 64-bit integer")
        if type(self.clock) is not ClockConfiguration:
            raise TypeError("clock has the wrong type")
        if type(self.locale) is not str or not _is_well_formed_language_tag(
            self.locale
        ):
            raise ValueError("locale is invalid")
        _require_non_empty(self.timezone, "timezone")
        if type(self.terminal) is not TerminalConfiguration:
            raise TypeError("terminal has the wrong type")
        if type(self.filesystem) is not FilesystemConfiguration:
            raise TypeError("filesystem has the wrong type")
        if type(self.network) is not NetworkConfiguration:
            raise TypeError("network has the wrong type")

    def to_protocol(self) -> dict[str, JsonValue]:
        """Return a fresh JSON-shaped v1 configuration payload."""
        network: dict[str, JsonValue] = {"mode": self.network.mode}
        if self.network.mode == "allow-list":
            network["allowed"] = [
                {"host": endpoint.host, "port": endpoint.port}
                for endpoint in self.network.allowed
            ]
        return {
            "seed": str(self.seed),
            "clock": {"mode": "manual", "initial_ms": self.clock.initial_ms},
            "locale": self.locale,
            "timezone": self.timezone,
            "terminal": {
                "columns": self.terminal.columns,
                "rows": self.terminal.rows,
                "capabilities": list(self.terminal.capabilities),
            },
            "filesystem": {
                "mode": "sandbox",
                "root_id": self.filesystem.root_id,
            },
            "network": network,
        }


@dataclass(frozen=True, slots=True)
class Region:
    id: str
    role: str
    column: int
    row: int
    columns: int
    rows: int

    def __post_init__(self) -> None:
        _require_non_empty(self.id, "region id")
        _require_non_empty(self.role, "region role")
        _require_plain_int(self.column, "column")
        _require_plain_int(self.row, "row")
        _require_plain_int(self.columns, "columns", positive=True)
        _require_plain_int(self.rows, "rows", positive=True)


@dataclass(frozen=True, slots=True)
class Cursor:
    column: int
    row: int
    visible: bool

    def __post_init__(self) -> None:
        _require_plain_int(self.column, "cursor column")
        _require_plain_int(self.row, "cursor row")
        if type(self.visible) is not bool:
            raise TypeError("cursor visible must be a boolean")


@dataclass(frozen=True, slots=True)
class UiObservation:
    regions: tuple[Region, ...]
    focus: str | None
    cursor: Cursor
    mode: str | None

    def __post_init__(self) -> None:
        if type(self.regions) is not tuple or any(
            type(region) is not Region for region in self.regions
        ):
            raise TypeError("regions must be a tuple of Region values")
        ids = tuple(region.id for region in self.regions)
        if len(ids) != len(set(ids)):
            raise ValueError("region ids must be unique")
        if self.focus is not None and (
            type(self.focus) is not str or self.focus not in ids
        ):
            raise ValueError("focus must name a region")
        if type(self.cursor) is not Cursor:
            raise TypeError("cursor has the wrong type")
        if self.mode is not None and type(self.mode) is not str:
            raise TypeError("mode must be a string or None")


@dataclass(frozen=True, slots=True)
class Frame:
    lines: tuple[str, ...]
    columns: int
    rows: int

    def __post_init__(self) -> None:
        if type(self.lines) is not tuple or any(
            type(line) is not str for line in self.lines
        ):
            raise TypeError("frame lines must be a tuple of strings")
        _require_plain_int(self.columns, "frame columns", positive=True)
        _require_plain_int(self.rows, "frame rows", positive=True)
        if len(self.lines) != self.rows:
            raise ValueError("frame rows must equal the number of lines")


@dataclass(frozen=True, slots=True, init=False)
class Event:
    type: str
    data: FrozenJsonValue

    def __init__(self, type: str, data: JsonInput) -> None:
        object.__setattr__(self, "type", _require_non_empty(type, "event type"))
        object.__setattr__(self, "data", freeze_json(data))


@dataclass(frozen=True, slots=True)
class ProcessObservation:
    state: Literal["running", "exited"]
    exit: ExitStatus | None = None

    def __post_init__(self) -> None:
        _require_choice(self.state, "process observation state", ("running", "exited"))
        if self.state == "running" and self.exit is not None:
            raise ValueError("running process observation cannot have exit evidence")
        if self.state == "exited" and type(self.exit) is not ExitStatus:
            raise ValueError("exited process observation requires exit evidence")

    @classmethod
    def running(cls) -> ProcessObservation:
        return cls(state="running")

    @classmethod
    def exited(cls, exit: ExitStatus) -> ProcessObservation:
        return cls(state="exited", exit=exit)


@dataclass(frozen=True, slots=True, init=False)
class Observation:
    at_ms: ManualTime
    state: FrozenJsonValue
    events: tuple[Event, ...]
    ui: UiObservation
    frame: Frame | None
    process: ProcessObservation | None

    def __init__(
        self,
        at_ms: ManualTime,
        state: JsonInput,
        events: tuple[Event, ...],
        ui: UiObservation,
        frame: Frame | None = None,
        process: ProcessObservation | None = None,
    ) -> None:
        if type(at_ms) is not ManualTime:
            raise TypeError("at_ms must be ManualTime")
        if type(events) is not tuple or any(
            type(event) is not Event for event in events
        ):
            raise TypeError("events must be a tuple of Event values")
        if type(ui) is not UiObservation:
            raise TypeError("ui has the wrong type")
        if frame is not None and type(frame) is not Frame:
            raise TypeError("frame has the wrong type")
        if process is not None and type(process) is not ProcessObservation:
            raise TypeError("process has the wrong type")
        object.__setattr__(self, "at_ms", at_ms)
        object.__setattr__(self, "state", freeze_json(state))
        object.__setattr__(self, "events", events)
        object.__setattr__(self, "ui", ui)
        object.__setattr__(self, "frame", frame)
        object.__setattr__(self, "process", process)


@dataclass(frozen=True, slots=True, init=False)
class Diagnostic:
    at_ms: ManualTime
    code: str
    message: str
    details: FrozenJsonValue

    def __init__(
        self,
        at_ms: ManualTime,
        code: str,
        message: str,
        details: JsonInput = None,
    ) -> None:
        if type(at_ms) is not ManualTime:
            raise TypeError("at_ms must be ManualTime")
        object.__setattr__(self, "at_ms", at_ms)
        object.__setattr__(self, "code", _require_non_empty(code, "code"))
        if type(message) is not str:
            raise TypeError("message must be a string")
        object.__setattr__(self, "message", message)
        object.__setattr__(self, "details", freeze_json(details))


@dataclass(frozen=True, slots=True)
class TextInput:
    at_ms: ManualTime
    text: str

    def __post_init__(self) -> None:
        if type(self.at_ms) is not ManualTime:
            raise TypeError("at_ms must be ManualTime")
        if type(self.text) is not str:
            raise TypeError("text must be a string")


@dataclass(frozen=True, slots=True)
class Resize:
    at_ms: ManualTime
    columns: int
    rows: int

    def __post_init__(self) -> None:
        if type(self.at_ms) is not ManualTime:
            raise TypeError("at_ms must be ManualTime")
        _require_plain_int(self.columns, "columns", positive=True)
        _require_plain_int(self.rows, "rows", positive=True)


@dataclass(frozen=True, slots=True)
class ClockAdvance:
    at_ms: ManualTime
    delta_ms: int

    def __post_init__(self) -> None:
        if type(self.at_ms) is not ManualTime:
            raise TypeError("at_ms must be ManualTime")
        _require_plain_int(self.delta_ms, "delta_ms", positive=True)


@dataclass(frozen=True, slots=True)
class Stop:
    at_ms: ManualTime

    def __post_init__(self) -> None:
        if type(self.at_ms) is not ManualTime:
            raise TypeError("at_ms must be ManualTime")


@dataclass(frozen=True, slots=True, init=False)
class AdapterFailure:
    code: str
    message: str
    details: FrozenJsonValue

    def __init__(self, code: str, message: str, details: JsonInput = None) -> None:
        object.__setattr__(self, "code", _require_non_empty(code, "failure code"))
        if type(message) is not str:
            raise TypeError("failure message must be a string")
        object.__setattr__(self, "message", message)
        object.__setattr__(self, "details", freeze_json(details))


@dataclass(frozen=True, slots=True)
class ExitStatus:
    kind: Literal["code", "signal"]
    value: int | str

    def __post_init__(self) -> None:
        kind = _require_choice(self.kind, "exit status kind", ("code", "signal"))
        valid_code = kind == "code" and type(self.value) is int
        valid_signal = kind == "signal" and type(self.value) is str and bool(self.value)
        if not valid_code and not valid_signal:
            raise ValueError("exit status is invalid")


@dataclass(frozen=True, slots=True)
class RunFinished:
    exit: ExitStatus

    def __post_init__(self) -> None:
        if type(self.exit) is not ExitStatus:
            raise TypeError("finished exit has the wrong type")

    @classmethod
    def code(cls, value: int) -> RunFinished:
        return cls(ExitStatus("code", value))

    @classmethod
    def signal(cls, value: str) -> RunFinished:
        return cls(ExitStatus("signal", value))


@dataclass(frozen=True, slots=True)
class RunFailed:
    failure: AdapterFailure

    def __post_init__(self) -> None:
        if type(self.failure) is not AdapterFailure:
            raise TypeError("runtime failure has the wrong type")
        if self.failure.code != "adapter-runtime-failed":
            raise ValueError("runtime failure code must be adapter-runtime-failed")


@dataclass(frozen=True, slots=True)
class SeedReceipt:
    run_id: str
    effective: int

    def __post_init__(self) -> None:
        _validate_run_id(self.run_id)
        _require_plain_int(self.effective, "effective seed")
        if self.effective > _MAX_SEED:
            raise ValueError("effective seed must fit an unsigned 64-bit integer")


@dataclass(frozen=True, slots=True)
class ClockReceipt:
    run_id: str
    effective: ClockConfiguration

    def __post_init__(self) -> None:
        _validate_run_id(self.run_id)
        if type(self.effective) is not ClockConfiguration:
            raise TypeError("effective clock has the wrong type")


@dataclass(frozen=True, slots=True)
class LocaleReceipt:
    run_id: str
    effective: str

    def __post_init__(self) -> None:
        _validate_run_id(self.run_id)
        if type(self.effective) is not str or not _is_well_formed_language_tag(
            self.effective
        ):
            raise ValueError("effective locale is invalid")


@dataclass(frozen=True, slots=True)
class TimezoneReceipt:
    run_id: str
    effective: str

    def __post_init__(self) -> None:
        _validate_run_id(self.run_id)
        _require_non_empty(self.effective, "effective timezone")
        if self.effective != "UTC":
            raise ValueError(
                "named timezone enforcement requires the deferred timezone policy"
            )


@dataclass(frozen=True, slots=True)
class TerminalReceipt:
    run_id: str
    effective: TerminalConfiguration

    def __post_init__(self) -> None:
        _validate_run_id(self.run_id)
        if type(self.effective) is not TerminalConfiguration:
            raise TypeError("effective terminal has the wrong type")
        if self.effective.capabilities:
            raise ValueError(
                "terminal capability registry is not approved for enforcement"
            )


@dataclass(frozen=True, slots=True)
class FilesystemReceipt:
    run_id: str
    effective: FilesystemConfiguration

    def __post_init__(self) -> None:
        _validate_run_id(self.run_id)
        if type(self.effective) is not FilesystemConfiguration:
            raise TypeError("effective filesystem has the wrong type")


@dataclass(frozen=True, slots=True)
class NetworkReceipt:
    run_id: str
    effective: NetworkConfiguration

    def __post_init__(self) -> None:
        _validate_run_id(self.run_id)
        if type(self.effective) is not NetworkConfiguration:
            raise TypeError("effective network has the wrong type")
        if self.effective.mode != "deny":
            raise ValueError("allow-list network enforcement is deferred")


type EnforcementReceipt = (
    SeedReceipt
    | ClockReceipt
    | LocaleReceipt
    | TimezoneReceipt
    | TerminalReceipt
    | FilesystemReceipt
    | NetworkReceipt
)
_RECEIPT_TYPES = (
    SeedReceipt,
    ClockReceipt,
    LocaleReceipt,
    TimezoneReceipt,
    TerminalReceipt,
    FilesystemReceipt,
    NetworkReceipt,
)


@dataclass(frozen=True, slots=True, init=False)
class ConstraintUnsupported:
    constraint: ConstraintName
    code: str
    message: str
    details: FrozenJsonValue

    def __init__(
        self,
        constraint: ConstraintName,
        code: str,
        message: str,
        details: JsonInput = None,
    ) -> None:
        _require_choice(constraint, "unsupported constraint", _CONSTRAINT_ORDER)
        _require_choice(
            code,
            "unsupported code",
            ("constraint-unsupported", "constraint-not-enforced"),
        )
        if type(message) is not str:
            raise TypeError("unsupported message must be a string")
        object.__setattr__(self, "constraint", constraint)
        object.__setattr__(self, "code", code)
        object.__setattr__(self, "message", message)
        object.__setattr__(self, "details", freeze_json(details))


class ConstraintPorts(Protocol):  # pragma: no cover - structural declarations
    """Application-facing paths that apply deterministic constraints."""

    def enforce_seed(
        self, run_id: str, requested: int
    ) -> SeedReceipt | ConstraintUnsupported | AdapterFailure: ...

    def enforce_clock(
        self, run_id: str, requested: ClockConfiguration
    ) -> ClockReceipt | ConstraintUnsupported | AdapterFailure: ...

    def enforce_locale(
        self, run_id: str, requested: str
    ) -> LocaleReceipt | ConstraintUnsupported | AdapterFailure: ...

    def enforce_timezone(
        self, run_id: str, requested: str
    ) -> TimezoneReceipt | ConstraintUnsupported | AdapterFailure: ...

    def enforce_terminal(
        self, run_id: str, requested: TerminalConfiguration
    ) -> TerminalReceipt | ConstraintUnsupported | AdapterFailure: ...

    def enforce_filesystem(
        self, run_id: str, requested: FilesystemConfiguration
    ) -> FilesystemReceipt | ConstraintUnsupported | AdapterFailure: ...

    def enforce_network(
        self, run_id: str, requested: NetworkConfiguration
    ) -> NetworkReceipt | ConstraintUnsupported | AdapterFailure: ...


@dataclass(frozen=True, slots=True)
class EnforcedConstraints:
    run_id: str
    requested: RunConfiguration
    seed: SeedReceipt
    clock: ClockReceipt
    locale: LocaleReceipt
    timezone: TimezoneReceipt
    terminal: TerminalReceipt
    filesystem: FilesystemReceipt
    network: NetworkReceipt

    def __post_init__(self) -> None:
        _validate_run_id(self.run_id)
        if type(self.requested) is not RunConfiguration:
            raise TypeError("requested configuration has the wrong type")
        receipts = (
            self.seed,
            self.clock,
            self.locale,
            self.timezone,
            self.terminal,
            self.filesystem,
            self.network,
        )
        for name, receipt, receipt_type in zip(
            _CONSTRAINT_ORDER, receipts, _RECEIPT_TYPES, strict=True
        ):
            if type(receipt) is not receipt_type:
                raise TypeError(f"{name} receipt has the wrong type")
        _validate_receipt_binding(self.run_id, self.requested, receipts)


def _validate_receipt_binding(
    run_id: str,
    requested: RunConfiguration,
    receipts: tuple[EnforcementReceipt, ...],
) -> None:
    expected = (
        requested.seed,
        requested.clock,
        requested.locale,
        requested.timezone,
        requested.terminal,
        requested.filesystem,
        requested.network,
    )
    for name, receipt, requested_value in zip(
        _CONSTRAINT_ORDER, receipts, expected, strict=False
    ):
        if receipt.run_id != run_id:
            raise ValueError("all receipts must belong to the same run")
        if receipt.effective != requested_value:
            raise ValueError(f"{name} receipt does not match the requested {name}")


@dataclass(frozen=True, slots=True)
class Started:
    constraints: EnforcedConstraints
    observation: Observation
    diagnostics: tuple[Diagnostic, ...] = ()

    def __post_init__(self) -> None:
        if type(self.constraints) is not EnforcedConstraints:
            raise TypeError("constraints have the wrong type")
        if type(self.observation) is not Observation:
            raise TypeError("observation has the wrong type")
        if (
            self.observation.process is not None
            and self.observation.process.state == "exited"
        ):
            raise ValueError("readiness cannot contain exited-process evidence")
        if self.observation.at_ms != self.constraints.clock.effective.initial_ms:
            raise ValueError("initial observation must use the effective initial clock")
        _validate_diagnostics(self.diagnostics)


def _validate_receipt_prefix(
    run_id: str,
    requested: RunConfiguration,
    receipts: tuple[EnforcementReceipt, ...],
) -> None:
    _validate_run_id(run_id)
    if type(requested) is not RunConfiguration:
        raise TypeError("requested configuration has the wrong type")
    if type(receipts) is not tuple:
        raise TypeError("enforced receipts must be a tuple")
    if len(receipts) > len(_CONSTRAINT_ORDER):
        raise ValueError("enforced receipt prefix is too long")
    for index, receipt in enumerate(receipts):
        if type(receipt) is not _RECEIPT_TYPES[index]:
            raise ValueError("enforced receipts are out of configuration order")
    _validate_receipt_binding(run_id, requested, receipts)


@dataclass(frozen=True, slots=True, init=False)
class StartUnsupported:
    run_id: str
    requested: RunConfiguration
    enforced: tuple[EnforcementReceipt, ...]
    constraint: ConstraintName
    code: str
    message: str
    details: FrozenJsonValue

    def __init__(
        self,
        run_id: str,
        requested: RunConfiguration,
        enforced: tuple[EnforcementReceipt, ...],
        constraint: ConstraintName,
        code: str,
        message: str,
        details: JsonInput = None,
    ) -> None:
        _validate_receipt_prefix(run_id, requested, enforced)
        _require_choice(constraint, "unsupported constraint", _CONSTRAINT_ORDER)
        if len(enforced) != _CONSTRAINT_ORDER.index(constraint):
            raise ValueError("unsupported constraint does not follow receipt order")
        object.__setattr__(self, "run_id", run_id)
        object.__setattr__(self, "requested", requested)
        object.__setattr__(self, "enforced", enforced)
        object.__setattr__(self, "constraint", constraint)
        _require_choice(
            code,
            "unsupported code",
            ("constraint-unsupported", "constraint-not-enforced"),
        )
        object.__setattr__(self, "code", code)
        if type(message) is not str:
            raise TypeError("unsupported message must be a string")
        object.__setattr__(self, "message", message)
        object.__setattr__(self, "details", freeze_json(details))


@dataclass(frozen=True, slots=True)
class StartFailed:
    run_id: str
    requested: RunConfiguration
    enforced: tuple[EnforcementReceipt, ...]
    failure: AdapterFailure
    diagnostics: tuple[Diagnostic, ...] = ()

    def __post_init__(self) -> None:
        _validate_receipt_prefix(self.run_id, self.requested, self.enforced)
        if type(self.failure) is not AdapterFailure:
            raise TypeError("failure has the wrong type")
        if self.failure.code != "adapter-start-failed":
            raise ValueError("start failure code must be adapter-start-failed")
        _validate_diagnostics(self.diagnostics)
        if self.diagnostics and len(self.enforced) != len(_CONSTRAINT_ORDER):
            raise ValueError("startup diagnostics require complete negotiation")


def _validate_diagnostics(diagnostics: tuple[Diagnostic, ...]) -> None:
    if type(diagnostics) is not tuple or any(
        type(diagnostic) is not Diagnostic for diagnostic in diagnostics
    ):
        raise TypeError("diagnostics must be a tuple of Diagnostic values")


@dataclass(frozen=True, slots=True)
class EpochCompleted:
    observation: Observation
    diagnostics: tuple[Diagnostic, ...] = ()

    def __post_init__(self) -> None:
        if type(self.observation) is not Observation:
            raise TypeError("observation has the wrong type")
        if (
            self.observation.process is not None
            and self.observation.process.state == "exited"
        ):
            raise ValueError("exited-process observation requires a terminal result")
        _validate_diagnostics(self.diagnostics)


@dataclass(frozen=True, slots=True)
class TerminalResult:
    observation: Observation | None
    outcome: RunFinished | RunFailed
    diagnostics: tuple[Diagnostic, ...] = ()

    def __post_init__(self) -> None:
        if self.observation is not None and type(self.observation) is not Observation:
            raise TypeError("terminal observation has the wrong type")
        if type(self.outcome) not in (RunFinished, RunFailed):
            raise TypeError("terminal outcome has the wrong type")
        if (
            self.observation is not None
            and self.observation.process is not None
            and self.observation.process.state != "exited"
        ):
            raise ValueError("terminal process evidence must report exit")
        if (
            type(self.outcome) is RunFinished
            and self.observation is not None
            and self.observation.process is not None
            and self.observation.process.state == "exited"
            and self.observation.process.exit != self.outcome.exit
        ):
            raise ValueError("process exit evidence must match the finished outcome")
        if (
            type(self.outcome) is RunFailed
            and self.observation is not None
            and (
                self.observation.process is None
                or self.observation.process.state != "exited"
            )
        ):
            raise ValueError(
                "failure observations must contain exited-process evidence"
            )
        _validate_diagnostics(self.diagnostics)


@dataclass(frozen=True, slots=True)
class StartTerminated:
    constraints: EnforcedConstraints
    result: TerminalResult

    def __post_init__(self) -> None:
        if type(self.constraints) is not EnforcedConstraints:
            raise TypeError("constraints have the wrong type")
        if type(self.result) is not TerminalResult:
            raise TypeError("terminal result has the wrong type")
        if type(self.result.outcome) is not RunFinished:
            raise ValueError("initialization termination must be a subject exit")
        if (
            self.result.observation is not None
            and self.result.observation.at_ms
            != self.constraints.clock.effective.initial_ms
        ):
            raise ValueError(
                "initialization terminal observation must use the effective "
                "initial clock"
            )


type StartResult = Started | StartTerminated | StartUnsupported | StartFailed
type DispatchInput = TextInput | Resize
type EpochResult = EpochCompleted | TerminalResult


class Adapter(Protocol):  # pragma: no cover - structural declarations
    """Synchronous single-flight direct-adapter boundary."""

    def start(self, run_id: str, configuration: RunConfiguration) -> StartResult: ...

    def dispatch(self, input_event: DispatchInput) -> EpochResult: ...

    def advance_clock(self, input_event: ClockAdvance) -> EpochResult: ...

    def stop(self, input_event: Stop) -> TerminalResult: ...
