# Changelog

All notable changes to the termverify package are documented in this file. The
format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
the package adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
with the pre-1.0 policy below.

## Versioning and compatibility policy

- **Package versions are not protocol versions.** The transcript wire contract
  (`termverify.transcript/v1`) and its closed registries
  (`termverify.timezone/v1`, `termverify.key/v1`) are versioned independently
  and are immutable after freeze; changing their membership or meaning requires
  a new protocol or registry version, never a package release note alone.
- **Before 1.0.0** every `0.x` release may contain breaking changes to the
  Python API. Breaking changes are listed under a **Changed** or **Removed**
  heading with a migration note; they are never silent.
- **Pre-alpha status.** No published release exists yet and no stable/public
  support claim is made. The first supported external artifact requires the
  release checklist in `docs/developer-guide/release.md`.
- Golden masters, baselines, and fixtures never update automatically as part
  of a release; human-reviewed diffs remain mandatory.

## [Unreleased]

### Added

- Deterministic transcript v1 codec, semantic lifecycle validator, and
  fail-closed resource limits with parser/serializer symmetry.
- Closed protocol-owned v1 registries for requested timezone names and
  semantic key chords, with an immutable direct-dispatch key representation.
- Immutable producer-side adapter contract and deterministic in-process direct
  runtime with structured failure classification.
- Safe transcript-persistence boundary with fail-closed evidence
  classification, redaction, and atomic same-directory replacement.
- Packaged canonical transcript schema with installed access API
  (`TRANSCRIPT_SCHEMA_V1_ID`, `transcript_schema_v1_bytes`,
  `transcript_schema_v1_json`) and isolated installed-artifact contract checks.
- No-regression coverage ratchet with a strict committed floor.
- Release governance: this changelog and policy, security-disclosure process,
  release checklist, and tag-triggered build-provenance workflow producing
  attested draft artifacts only.
- Closed `termverify.enforcement-tier/v1` vocabulary (`os`, `constructive`,
  `delivered`) with a per-negotiation-path authorization matrix validated
  fail-closed during receipt binding, and a `DeliveryRecord` value for
  delivered-tier receipts.
- Opt-in `termverify.cooperation` module: `CooperationConstraintPorts`
  delivering all six non-terminal constraints at the `delivered` tier with
  the accepted per-constraint contracts (`TERMVERIFY_*` variables, `TZ=UTC0`
  UTC-only, sandbox-root working directory through an injectable directory
  probe, deny-only network), plus evidence-driven spawn: the ConPTY adapter
  assembles the child's environment overlay and working directory from the
  validated delivery records, with fail-closed disjointness invariants.
  Defaults are unchanged — `UnenforcedConstraintPorts` still fails closed.
- First fully successful verified terminal run as durable Windows-matrix
  integration evidence: cooperation ports with a host-owned sandbox, real
  ConPTY binding and normalizer, delivered-tier receipts, a cooperating
  subject echoing every delivered variable and its working directory into
  frames, subject exit via native end-of-stream, replay identity over the
  retained raw output, and forced-stop/deadline paths re-exercised.
- Closed `termverify.key-encoding/v1` registry: a digest-bound total mapping
  from each of the 934 valid `termverify.key/v1` chords to exactly one
  xterm-legacy normal-mode byte string or the explicit fail-closed verdict
  unencodable, with four disclosed legacy byte collisions. The ConPTY
  adapter's `dispatch` now executes encodable `KeyInput` chords by writing
  the registry bytes exactly once through the single-flight child write and
  running the standard quiescent epoch; an unencodable chord is a structured
  runtime failure (`{"unsupported": "key-encoding", "keys": [...]}`) before
  any child write, replacing the previous unconditional `KeyInput` rejection
  (`{"unsupported": "key-input"}`). Delivery only: no input-mode tracking,
  no key-support negotiation, no claim of subject decoding; processed-input
  signal bytes (for example `Control+c` → 0x03) are disclosed as
  subject-side interpretation.
- Real-child Windows-matrix evidence for the key-encoding registry: a
  cooperative raw-mode fixture subject (processed input, line input, and
  echo disabled; virtual-terminal input enabled) observes the exact
  registry bytes for one representative chord per encodable family class —
  including the signal byte 0x03 arriving as input under raw mode — echoes
  them into frames with replay identity, and the unencodable path stays
  fail-closed on the real adapter with OS-observed teardown.
- Phase 2 verification core, slice 1 (`termverify.recorder`): a public
  `TranscriptRecorder` that assembles the immutable adapter result values
  into `termverify.transcript/v1` records in occurrence order, enforcing
  the lifecycle shape at record time with structured
  `TranscriptRecorderError` values, and a minimal `run_scripted`
  orchestrator that drives one adapter through a scripted input sequence
  and returns validated transcript bytes plus the terminal outcome. Output
  passes only through the existing strict serializer; the codec remains
  the sole acceptance gate, no protocol member changes, and no scheduling,
  retry, timeout, or comparison capability is added. GlyphWright's spike
  transcript is imported unmodified as an external conformance fixture
  with provenance (`tests/fixtures/external/glyphwright-direct-spike/`).
- Phase 2 verification core, slice 2 (`termverify.comparator`): an exact
  transcript comparator — both inputs must pass the strict codec (an
  invalid side is a structured `TranscriptInputError`, never a comparison
  result), records compare by canonical semantic equality of envelope and
  payload over the full sequence with exactly one disclosed identity
  exclusion (envelope `run_id`), and the structured verdict lists every
  divergent record with its exact differing members in deterministic
  order. `render_report` renders a verdict as deterministic plain text
  (summary, first divergence position, bounded member-level diff); it is
  a rendering of the verdict only, never a second comparison
  implementation, and no test asserts stored report bytes as behavioral
  truth. No normalizers, tolerances, or per-scenario configuration exist;
  extending the exclusion set requires an owner-accepted amendment.
- Phase 2 verification core, slice 3 (`termverify.replay`): caller-bound
  transcript replay. `replay_transcript` takes a validated source
  transcript and a caller-supplied adapter, re-executes the source's
  configuration and input sequence in transcript order under the same
  single-flight discipline, records the new run with the slice-1
  recorder, and returns the new transcript plus the slice-2 comparison.
  Replay binding is disclosed, not enforced: the caller-supplied
  `termverify.replay-subject/v1` selector is recorded in the new
  transcript and selector agreement is reported, never a precondition. A
  source whose lifecycle ended in a failed or unsupported start replays
  nothing and reports that structurally; sources carrying input kinds the
  adapter contract cannot dispatch (`input.mouse`,
  `input.clipboard_set`) fail closed before any adapter call; early
  terminations disclose dispatched-versus-source input counts; a replay
  whose input sequence ends with the run still open is a structured
  error. No scheduling, retry, timeout, multi-subject, or differential
  semantics.

### Changed

- **Breaking (pre-release protocol amendment; transcript protocol stays
  v1):** every enforcement receipt (`SeedReceipt`, `ClockReceipt`,
  `LocaleReceipt`, `TimezoneReceipt`, `TerminalReceipt`, `FilesystemReceipt`,
  `NetworkReceipt`) now requires a mandatory `tier` from
  `termverify.enforcement-tier/v1`, and delivered-tier receipts must carry a
  `delivery` record (mandatory pairing in both directions). Migration: every
  external `ConstraintPorts`/`DirectApplication` implementation must add the
  tier to its receipt construction — direct applications state
  `constructive`, ports injected into the ConPTY adapter state `delivered`
  plus the delivery record, and the ConPTY adapter's own terminal negotiation
  states `os`. An unauthorized tier for a negotiation path is rejected as a
  structured `StartFailed`. Transcript `capability.result` records with
  `status: "enforced"` likewise require `tier` (and `delivery` exactly when
  the tier is `delivered`). No released artifact or recorded transcript
  carries the prior shapes.
- **Breaking:** `ConptyBindingPort.spawn` (and the native
  `termverify._conpty.ConptyChild.spawn`) gained keyword parameters
  `env_overlay` and `cwd`; external binding implementations must accept
  them. Omitting both preserves the prior spawn behavior exactly.
- **Breaking:** `DeliveryRecord` and transcript delivery validation now
  reject syntactically undeliverable environment entries — `=` or NUL in a
  variable name, NUL in a value or working directory — fail-closed.
