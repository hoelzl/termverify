"""Protocol-driven verification for autonomous terminal applications.

The names re-exported here are the curated public surface. Adapter authors
implement the contract defined in :mod:`termverify.adapter` and, for
in-process subjects, :mod:`termverify.direct`; every contract name is
importable from ``termverify`` directly and is identical to its module-path
definition, so both import styles stay interchangeable. The surface is
pre-1.0: compatibility intent and changes are recorded in ``CHANGELOG.md``.

The surface also carries the authoritative transcript codec
(:func:`parse_transcript`, :func:`serialize_transcript`,
:class:`TranscriptValidationError`) alongside the non-authoritative schema
aid, and the closed key registries (:data:`KEY_NAMES`,
:func:`is_key_chord`, :func:`encode_key_chord`). The registries are defined
in private modules; the names are public, their module paths are not.
"""

from importlib.metadata import version

from termverify._key_encoding_v1 import encode_key_chord
from termverify._key_v1 import KEY_NAMES, is_key_chord
from termverify.adapter import (
    ENFORCEMENT_TIERS,
    Adapter,
    AdapterFailure,
    ClockAdvance,
    ClockConfiguration,
    ClockReceipt,
    ConstraintName,
    ConstraintPorts,
    ConstraintUnsupported,
    Cursor,
    DeliveryRecord,
    Diagnostic,
    DispatchInput,
    EnforcedConstraints,
    EnforcementReceipt,
    EnforcementTier,
    EpochCompleted,
    EpochResult,
    Event,
    ExitStatus,
    FilesystemConfiguration,
    FilesystemReceipt,
    Frame,
    FrozenJsonValue,
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
    StartResult,
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
from termverify.direct import DirectAdapter, DirectApplication
from termverify.evidence import persist_transcript_evidence
from termverify.schema import (
    TRANSCRIPT_SCHEMA_V1_ID,
    transcript_schema_v1_bytes,
    transcript_schema_v1_json,
)
from termverify.transcript import (
    TranscriptValidationError,
    parse_transcript,
    serialize_transcript,
)

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
    "DeliveryRecord",
    "Diagnostic",
    "DirectAdapter",
    "DirectApplication",
    "DispatchInput",
    "ENFORCEMENT_TIERS",
    "EnforcedConstraints",
    "EnforcementReceipt",
    "EnforcementTier",
    "EpochCompleted",
    "EpochResult",
    "Event",
    "ExitStatus",
    "FilesystemConfiguration",
    "FilesystemReceipt",
    "Frame",
    "FrozenJsonValue",
    "JsonInput",
    "KEY_NAMES",
    "KeyInput",
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
    "StartResult",
    "StartTerminated",
    "StartUnsupported",
    "Started",
    "Stop",
    "TRANSCRIPT_SCHEMA_V1_ID",
    "TerminalConfiguration",
    "TerminalReceipt",
    "TerminalResult",
    "TextInput",
    "TimezoneReceipt",
    "TranscriptValidationError",
    "UiObservation",
    "__version__",
    "encode_key_chord",
    "freeze_json",
    "is_key_chord",
    "parse_transcript",
    "persist_transcript_evidence",
    "serialize_transcript",
    "transcript_schema_v1_bytes",
    "transcript_schema_v1_json",
]

__version__ = version("termverify")
