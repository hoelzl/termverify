# Adapter-Author Surface

External subjects implement the TermVerify producer contract: an `Adapter`
drives a run, `ConstraintPorts` enforces the requested constraints, and (for
the in-process path) `DirectApplication` executes input and clock epochs. The
curated public surface for that work is the top-level `termverify` package:
every contract name is re-exported there and is identical to its module-path
definition, so both import styles are interchangeable.

```python
from termverify import (
    Adapter,
    ConstraintPorts,
    DirectAdapter,
    DirectApplication,
    RunConfiguration,
    TextInput,
)
```

The module paths remain public and documented — `termverify.adapter` defines
the contract, `termverify.direct` the deterministic in-process runtime.
`tests/test_public_surface.py` pins the guarantee that the two surfaces never
drift: every name in `termverify.adapter.__all__` and
`termverify.direct.__all__` is importable from `termverify`.

## What the surface contains

- **The contract protocols**: `Adapter`, `ConstraintPorts`,
  `DirectApplication`, and the reference in-process runtime `DirectAdapter`.
- **Run configuration values**: `RunConfiguration` and the per-constraint
  configurations (`ClockConfiguration`, `TerminalConfiguration`,
  `FilesystemConfiguration`, `NetworkConfiguration`, `NetworkEndpoint`),
  plus `ManualTime` and `Region`.
- **Inputs**: `TextInput`, `KeyInput`, `Resize`, `ClockAdvance`, `Stop`, and
  the `DispatchInput` union.
- **Results and receipts**: the start results (`Started`, `StartFailed`,
  `StartTerminated`, `StartUnsupported`, `StartResult`), epoch results
  (`EpochCompleted`, `EpochResult`, `TerminalResult`, `AdapterFailure`),
  run outcomes (`RunFinished`, `RunFailed`, `ExitStatus`), the enforcement
  receipts (`SeedReceipt`, `ClockReceipt`, `LocaleReceipt`,
  `TimezoneReceipt`, `TerminalReceipt`, `FilesystemReceipt`,
  `NetworkReceipt`, `EnforcementReceipt`, `EnforcedConstraints`,
  `ConstraintUnsupported`), and the enforcement-tier vocabulary
  (`EnforcementTier`, `ENFORCEMENT_TIERS`, `DeliveryRecord`).
- **Observations and evidence values**: `Observation`, `UiObservation`,
  `ProcessObservation`, `Frame`, `Cursor`, `Event`, `Diagnostic`.
- **Supporting types**: `ConstraintName`, `JsonInput`, `FrozenJsonValue`,
  `freeze_json`, and the transcript-schema access API
  (`TRANSCRIPT_SCHEMA_V1_ID`, `transcript_schema_v1_bytes`,
  `transcript_schema_v1_json`, `persist_transcript_evidence`).

## What the surface deliberately excludes

- `termverify.conpty` (Windows-only real-terminal runtime) and
  `termverify.cooperation` (opt-in delivered-tier ports) stay at their module
  paths; importing them from the top level would make the portable core's
  import surface platform- and opt-in-dependent.
- The verification core (`termverify.recorder`, `termverify.comparator`,
  `termverify.replay`) is consumer-side, not adapter-author-side; it stays at
  its module paths until a consumer-surface decision curates it separately.
- Private helpers (any `_`-prefixed module or name) are never part of the
  surface, regardless of importability.

## Compatibility intent

The package is pre-1.0 (see the policy in `CHANGELOG.md`): every `0.x`
release may contain breaking Python-API changes, always listed in the
changelog with a migration note, never silent. The stated intent for this
surface is that the top-level names above and their module paths move only
with such a documented entry. Protocol artifacts (`termverify.transcript/v1`
and its registries) are versioned independently of the package and are
immutable after freeze.

## Where to go next

- [Direct adapter guide](direct-adapter.md) — semantics of the in-process
  path: single-flight discipline, manual-time rules, failure containment,
  receipt binding.
- `docs/knowledge/protocol.md` — the transcript wire contract your recorded
  runs must satisfy.
- Issue [#114](https://github.com/hoelzl/termverify/issues/114) tracks the
  external subjects' asks, including a future examples directory; GlyphWright's
  direct-adapter spike is the current external conformance fixture at
  `tests/fixtures/external/glyphwright-direct-spike/`.
