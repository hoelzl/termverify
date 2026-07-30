# Adapter-Author Surface

External subjects implement the TermVerify producer contract: an `Adapter`
drives a run, `ConstraintPorts` applies the requested constraints and states
each receipt's enforcement tier, and (for the in-process path)
`DirectApplication` executes input and clock epochs. The
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
    is_key_chord,
    parse_transcript,
)
```

The module paths remain public and documented — `termverify.adapter` defines
the contract, `termverify.direct` the deterministic in-process runtime,
`termverify.transcript` the authoritative codec.
`tests/test_public_surface.py` pins the guarantee that the top level and the
module paths never drift: every name in `termverify.adapter.__all__` and
`termverify.direct.__all__` is importable from `termverify`, and every codec
and registry name re-exported at the top level is the *identical object* to
its defining module's, not a copy. The same file pins `termverify.__all__` to
an exact set, so an accidental future export fails the suite.

The key registries are the one exception to the interchangeable-import rule:
`KEY_NAMES`, `is_key_chord`, and `encode_key_chord` are public **names** whose
defining modules stay private. Import them from `termverify`, never from an
underscore path.

## What the surface contains

- **The contract protocols**: `Adapter`, `ConstraintPorts`,
  `DirectApplication`, and the reference in-process runtime `DirectAdapter`.
- **Run configuration values**: `RunConfiguration` and the per-constraint
  configurations (`ClockConfiguration`, `TerminalConfiguration`,
  `FilesystemConfiguration`, `NetworkConfiguration`, `NetworkEndpoint`),
  plus `ManualTime`.
- **Inputs**: `TextInput`, `KeyInput`, `Resize`, `ClockAdvance`, `Stop`, and
  the `DispatchInput` union.
- **Results and receipts**: the start results (`Started`, `StartFailed`,
  `StartTerminated`, `StartUnsupported`, `StartResult`), epoch results
  (`EpochCompleted`, `EpochResult`, `TerminalResult`, `AdapterFailure`),
  run outcomes (`RunFinished`, `RunFailed`, `ExitStatus`), the enforcement
  receipts (`SeedReceipt`, `ClockReceipt`, `LocaleReceipt`,
  `TimezoneReceipt`, `TerminalReceipt`, `FilesystemReceipt`,
  `NetworkReceipt`, `EnforcementReceipt`, `AppliedConstraints`,
  `ConstraintUnsupported`), and the enforcement-tier vocabulary
  (`EnforcementTier`, `ENFORCEMENT_TIERS`, `DeliveryRecord`).
- **Observations and evidence values**: `Observation`, `UiObservation`,
  `ProcessObservation`, `Frame`, `Cursor`, `Region`, `Event`, `Diagnostic`.
- **Supporting types**: `ConstraintName`, `JsonInput`, `FrozenJsonValue`,
  `freeze_json`, the package version string `__version__`, the
  transcript-schema access API (`TRANSCRIPT_SCHEMA_V1_ID`,
  `transcript_schema_v1_bytes`, `transcript_schema_v1_json`), and safe
  evidence persistence (`persist_transcript_evidence`, the surface's only
  transcript-writing function; only `mode="safe"` persists —
  `mode="sensitive"` raises).
- **The authoritative transcript codec**: `parse_transcript`,
  `serialize_transcript`, and `TranscriptValidationError`. These decide
  `termverify.transcript/v1` acceptance; the schema access API above is a
  non-exhaustive structural aid and schema acceptance is not conformance
  (`docs/knowledge/protocol.md`). The aid and the validator are both on the
  surface, so the authoritative one is never the harder import. Records are
  plain `dict`s; the alias `Record` is defined at `termverify.transcript`, a
  public module path, and the `JsonValue` it is built from is re-exported
  there from a private module — use it via `termverify.transcript`, whose
  re-export is the supported spelling.
- **The closed key registries' entry points**: `KEY_NAMES` and `is_key_chord`
  from `termverify.key/v1`, and `encode_key_chord` from
  `termverify.key-encoding/v1`. Use `is_key_chord` to validate a chord
  before putting it in a `KeyInput`, and `encode_key_chord` when your
  adapter drives a real terminal — it returns the xterm-legacy encoding as a
  `str` (encode it yourself for a byte channel), or `None` for the explicit
  fail-closed verdict *unencodable*. Both functions
  take a chord by **exact type**: a `list` or `tuple` of `str`, matching the
  codec's fail-closed discipline. A `NamedTuple` of key names or any other
  `Sequence` is rejected even when the names it carries are valid, and
  `encode_key_chord` raises `ValueError` — with the same message it uses for
  a genuinely invalid chord — rather than returning the *unencodable*
  verdict. **Your type checker will not catch the `NamedTuple` case**: it is
  a `tuple` statically and a rejection at runtime. Model chords as plain
  tuples.

## What the surface deliberately excludes

- `termverify.conpty` (Windows-only real-terminal runtime) and
  `termverify.cooperation` (opt-in delivered-tier ports) stay at their module
  paths; importing them from the top level would make the portable core's
  import surface platform- and opt-in-dependent.
- The verification core (`termverify.recorder`, `termverify.comparator`,
  `termverify.replay`) is consumer-side, not adapter-author-side; it stays at
  its module paths until a consumer-surface decision curates it separately.
  The codec above is not part of that core — it is the shared contract both
  sides validate against.
- `_`-prefixed **modules** are never part of the surface, and neither is any
  name they define that is not listed in `termverify.__all__` — including the
  rest of `termverify._key_v1` (`KEY_MODIFIERS`, `KEY_NAMED_BASES`,
  `KEY_MODIFIED_BASES`) and `termverify._key_encoding_v1.all_key_chords`.
  Importability is not membership; `termverify.__all__` is.

## Compatibility intent

The package is pre-1.0 (see the policy in `CHANGELOG.md`): every `0.x`
release may contain breaking Python-API changes, always listed in the
changelog with a migration note, never silent. The stated intent for this
surface is that the top-level names above, and their module paths where the
surface has one, move only with such a documented entry. `KEY_NAMES`,
`is_key_chord`, and `encode_key_chord` are **name-only** guarantees: the
top-level names carry the intent, their private defining modules carry none
and may move or be renamed without an entry. Protocol artifacts
(`termverify.transcript/v1` and its registries) are versioned independently
of the package and are immutable after freeze.

## Where to go next

- [Direct adapter guide](direct-adapter.md) — semantics of the in-process
  path: single-flight discipline, manual-time rules, failure containment,
  receipt binding.
- [JSONL adapter guide](jsonl-adapter.md) — operating the
  `termverify.control/v1` adapter: spawning subjects over pipes, tree
  containment, honest teardown, and the reference fixture subject.
- `docs/knowledge/protocol.md` — the transcript wire contract your recorded
  runs must satisfy.
- Issue [#114](https://github.com/hoelzl/termverify/issues/114) tracks the
  external subjects' asks, including a future examples directory; GlyphWright's
  direct-adapter spike is the current external conformance fixture at
  `tests/fixtures/external/glyphwright-direct-spike/`.
