# Phase 2 Boundary: The Verification Core

- **Status:** proposed — drafted 2026-07-19 in response to the converging
  external-subject prioritization signal in
  [issue #114](https://github.com/hoelzl/termverify/issues/114). The active
  [pre-release boundary hardening handover](../handovers/pre-release-boundary-hardening-handover.md)
  states that Phase 2 requires a separate accepted phase-boundary decision;
  this document is that decision candidate. It authorizes nothing until the
  owner accepts it, and it adds no code itself. Until acceptance, no
  recorder, comparator, replay, or report capability exists or is claimed.
- **Issue:** to be opened for acceptance review; prioritization input is
  [#114](https://github.com/hoelzl/termverify/issues/114)
- **Date:** 2026-07-19
- **Inputs:** issue #114 and its follow-up comments (GlyphWright direct-spike
  evidence including its hand-written ~120-line `TranscriptRecorder` and
  committed 28-record `transcript.jsonl`; the RecursiveNeon reassessment and
  its recommended ordering); the frozen `termverify.transcript/v1` protocol
  and strict codec (`docs/knowledge/protocol.md`,
  `src/termverify/transcript.py`); the immutable adapter execution contract
  and its result values (`src/termverify/adapter.py`,
  `docs/agent/design/phase-1-adapter-execution-contract.md`); the
  `termverify.replay-subject/v1` selector already required in every
  `run.started` payload; the handover's risks and non-negotiables; the
  reuse-assessment adoption ladders
  ([`recursive-neon-reuse-assessment.md`](recursive-neon-reuse-assessment.md)).

## Problem

Both external subjects independently reached the same blocker. Evidence
*production* is complete: the direct and ConPTY adapters produce validated,
deterministic, replayable `termverify.transcript/v1` evidence, and
GlyphWright's spike reproduced a byte-identical transcript across identical
runs with zero accommodation. Evidence *consumption* does not exist: every
adapter author must hand-write transcript assembly, and nothing in
TermVerify can compare two transcripts, replay one against a subject, or
render a human-readable verdict. A verification library that cannot verify
is the gap between "the foundations are robust" and "the tool is usable."

## Decision summary

Phase 2 activates with a deliberately narrow **verification core**: a
transcript recorder plus run orchestrator, an exact transcript comparator
with a deterministic human-readable report, and transcript-driven subject
replay. The core is a pure consumer of the frozen v1 protocol. It changes
no transcript semantics, weakens no fail-closed boundary, adds no
dependency, and makes no release claim. Three implementation slices are
authorized on acceptance, each through the standard workstream gate
(focused issue, sibling worktree, TDD, full validation, adversarial
review).

## Design rules

These bind all three slices:

1. **Pure consumer of v1.** The core reads and writes only records the
   frozen `termverify.transcript/v1` protocol already defines. Any need for
   a new record kind, payload member, or vocabulary suspends the slice and
   returns to the owner; the recorder must not become a side door into
   protocol evolution.
2. **The strict codec is the only gate.** Recorder output is valid only if
   `parse_transcript(serialize_transcript(records))` round-trips; the
   comparator and replay engine accept only transcripts that pass
   `parse_transcript`. No second, looser validation path may appear.
3. **Deterministic, ambient-free, cross-platform.** The core consumes
   adapter result values and transcript bytes. It never consults wall
   clock, terminal, filesystem, network, or randomness. Everything is
   fake-driven under the coverage ratchet; no Windows-only evidence is
   required because no native boundary is touched.
4. **Fail closed, verdict structured.** Invalid input, lifecycle violations
   at record time, and comparison mismatches produce structured errors or
   verdicts, never silent repair, truncation, or fabricated records.
5. **No baseline governance.** The comparator states whether two
   transcripts are equivalent under the disclosed rule. Nothing stores,
   blesses, or updates an expected transcript automatically; golden-master
   workflow remains outside this boundary per the handover.

## Slice 1: transcript recorder and run orchestrator

A public `TranscriptRecorder` that assembles the immutable adapter result
values into `termverify.transcript/v1` records in occurrence order:

- `run.started` from the `RunConfiguration` and a caller-supplied
  `termverify.replay-subject/v1` selector;
- `capability.result` records from the validated receipt prefix or the
  `ConstraintUnsupported` outcome, in configuration-table order, including
  tier and delivery members exactly as negotiated;
- the initial readiness observation, single-flight input epochs (input,
  epoch diagnostics, closing observation), and idle diagnostics-free
  causality exactly as the protocol's lifecycle shape requires;
- the terminal record from `RunFinished`, `RunFailed`, or the
  unsupported/failed start results.

The recorder enforces the lifecycle shape at record time: an out-of-order
contribution (input while an epoch is open, a record after the terminal
record, an observation while idle) is an immediate structured error, so an
adapter-integration bug surfaces at its cause rather than as a validation
failure over the finished artifact. Output is produced only through the
existing strict serializer.

Above it, a minimal run orchestrator drives one `Adapter` through a
scripted input sequence — start, scripted dispatches, stop or natural
termination — recording as it goes and returning validated transcript
bytes plus the terminal outcome. It adds no scheduling, retry, timeout, or
multi-subject semantics: policy stays with the caller and the adapters.

Evidence: unit and property tests over fake adapters for every lifecycle
shape the protocol admits (negotiation failure at each prefix, startup
failure before readiness, epochs with diagnostics, stop drain with and
without final observation, natural exit, runtime failure); integration
evidence that the orchestrator over the real `DirectAdapter` with a
cooperative fixture application yields a transcript the strict codec
accepts. GlyphWright's committed spike `transcript.jsonl` is imported as an
external conformance fixture with recorded provenance and license note,
per the reuse rule: the recorder must be able to reproduce a semantically
identical transcript from the equivalent result sequence.

## Slice 2: exact comparator and deterministic report

A comparator that takes two byte sequences, validates each with
`parse_transcript` (an invalid side is a structured input error, not a
comparison result), and produces a structured verdict: **equivalent** or a
list of divergences, each locating the first differing record by sequence
number and kind with the exact differing members.

The v1 equivalence rule is exact and closed: records compare by canonical
semantic equality of envelope and payload — the codec's existing JSON
equivalence — over the full record sequence, with exactly one disclosed
identity exclusion: the envelope `run_id`, which names a run rather than
its behavior. Everything else compares, including manual-clock times,
tiers, delivery records, diagnostics, and the `run.started` subject
selector. There are no normalizers, predicates, tolerances, or
per-scenario configuration in this phase; fuzzy or cross-subject
comparison is differential orchestration and stays outside this boundary.

The report renders a verdict as deterministic plain text: identical inputs
produce identical report bytes. It contains a summary (record counts,
verdict, first divergence position) and a bounded, human-readable
member-level diff per divergence. It is a rendering of the structured
verdict, never a second comparison implementation, and it is not a golden
master: no test may assert against stored report bytes as behavioral
truth.

Evidence: property tests that equivalence is reflexive, symmetric, and
run-id-insensitive; targeted divergence tests for every record kind and
for envelope-only differences; fixture tests over the GlyphWright
transcript against mutated copies; report determinism tests.

## Slice 3: transcript-driven subject replay

A replay engine that takes a validated source transcript and a
caller-supplied `Adapter` plus ports, re-executes the source's
configuration and input sequence in transcript order under the same
single-flight discipline, records the new run with the slice-1 recorder,
and returns the new transcript plus the slice-2 comparison of the two.

Replay binding is disclosed, not enforced: the engine records the
caller-supplied subject selector in the new transcript and reports whether
it equals the source's selector, but it does not resolve, launch, or
version-match subjects itself — the `termverify.replay-subject/v1`
selector remains an identity claim, and selector agreement is part of the
verdict rather than a precondition. A source transcript whose lifecycle
ended in a failed or unsupported start replays nothing and reports that
structurally.

Evidence: fake-adapter tests for faithful re-dispatch of every input kind
including clock advances and resize, for divergence detection when the
subject behaves differently, and for honest handling of replays that
terminate early; integration evidence that a `DirectAdapter` run recorded
by slice 1 replays to an equivalent transcript, and that a deliberately
perturbed subject (different seed behavior, changed observation) yields
the expected structured divergence.

## Non-goals of this boundary

Explicitly outside, each requiring its own future owner decision:

- **JSONL subprocess control transport** (issue #114 ask 2): a second live
  runtime flavor with its own framing, handshake, and failure taxonomy —
  a separate design, sequenced after this core exists to consume it.
- **Differential multi-target orchestration**, scenario-specific
  normalizers, predicates, oracle policies, and cross-subject comparison.
- **Cross-mode semantic comparison** between direct structured state and
  terminal frame evidence, and any structured telemetry channel for it.
- **Behavioral baselines and golden-master governance**; nothing here
  approves or updates stored expectations automatically.
- **Concurrent or unsolicited event correlation**; the core inherits
  single-flight v1 and must not weaken it.
- **New transcript, registry, or vocabulary versions**; the protocol
  stays exactly v1.
- **A POSIX PTY adapter, release claims, or index publication.**
- **The packaged adapter-author surface** (issue #114 ask 4) is endorsed
  as cheap parallel hygiene but is deliberately not part of this
  boundary; it proceeds as its own small issue so neither workstream
  gates the other.

## Risks

- **Scope creep through the recorder.** The recorder sits exactly where
  pressure for "just one more member" will arrive from external subjects.
  Mitigation: design rule 1 makes any protocol need a stop-and-return
  event, and adversarial review of each slice checks for smuggled
  semantics.
- **A second validation path.** A recorder that "knows" the lifecycle
  could drift from the codec's rules. Mitigation: the recorder's own
  checks are a usability layer; the strict codec remains the only
  acceptance gate and every test asserts through it.
- **Comparator leniency by convenience.** Excluding more than `run_id`
  (times, diagnostics, subjects) would make early demos greener and
  verdicts weaker. Mitigation: the exclusion set is closed by this
  design; extending it requires an owner-accepted amendment.
- **Replay overreach.** Launching subjects from selectors would import
  ambient process, path, and environment semantics this project has
  deliberately kept out. Mitigation: replay stays caller-bound; selector
  agreement is reported, not enforced.

## Acceptance and sequencing

On owner acceptance, the three slices are authorized in order — each may
begin only when the previous is accepted, since each consumes its
predecessor. Completion of slice 3 is the natural reassessment point for
the deferred asks (JSONL transport, differential orchestration) against
the demonstrated needs of the external subjects' then-current examples.
Acceptance of this design activates Phase 2 for exactly this scope and
nothing else; the handover's transferred criteria, retirements, and
deferrals are unchanged.
