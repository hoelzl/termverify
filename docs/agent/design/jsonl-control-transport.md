# JSONL Subprocess Control Transport: `termverify.control/v1` and the Second Live Runtime

- **Status:** accepted — both authorized implementation slices are merged
  (slice 1: issue #173 / PR #175; slice 2: issue #173 / PR #177) with
  adversarial-review verdicts; the JSONL transport and `termverify.control/v1`
  exist in `src/termverify/`. Status corrected 2026-07-25 per adversarial
  review 2026-07-24 (P8 drift finding). Originally drafted 2026-07-20 in
  response to the owner decision recorded in
  [issue #114](https://github.com/hoelzl/termverify/issues/114#issuecomment-5021323593):
  proceed with ask 2, Option B (a TermVerify-owned, versioned wire
  protocol). Acceptance of this design authorizes the two implementation
  slices in "Slices and sequencing" and nothing else; no transport
  capability exists or is claimed until its slice lands with evidence and
  an adversarial-review verdict.
- **Issue:** [#114](https://github.com/hoelzl/termverify/issues/114) ask 2
  (prioritization input from GlyphWright); the deferred reassessment named
  by the
  [Phase 2 boundary](phase-2-verification-core-boundary.md) ("Acceptance
  and sequencing") is discharged by the owner decision above.
- **Date:** 2026-07-20
- **Inputs:** issue #114 and its comments (GlyphWright's `0010`
  assessment: the JSONL-subprocess flavor is the expected workhorse);
  the frozen `termverify.transcript/v1` protocol and strict codec
  (`docs/knowledge/protocol.md`, `src/termverify/transcript.py`); the
  immutable adapter execution contract
  (`src/termverify/adapter.py`,
  [`phase-1-adapter-execution-contract.md`](phase-1-adapter-execution-contract.md));
  the direct runtime (`src/termverify/direct.py`) and the ConPTY runtime
  (`src/termverify/conpty.py`, `src/termverify/_conpty.py`) as the two
  existing implementations of that contract; the cooperation-tier
  constraint ports (`src/termverify/cooperation.py`,
  [`cooperation-tier-constraint-ports.md`](cooperation-tier-constraint-ports.md))
  whose spawn-time delivery semantics a subprocess runtime consumes; the
  enforcement-tier vocabulary (`src/termverify/_enforcement_tier_v1.py`);
  the frozen `termverify.key/v1` chord registry
  (`src/termverify/_key_v1.py`); the containment and exit-record patterns
  of the ConPTY binding; the ESC/CRT-reader disclosure
  (`docs/developer-guide/conpty-adapter.md`, issue #169), which
  distinguishes pipe input from console input.

## Problem

TermVerify has exactly two live runtimes, and both have a structural
limit for external subjects. The direct runtime requires the subject to
be importable Python in the verifier's process — no process isolation,
and no place for subjects in other languages or behind containment
boundaries. The ConPTY runtime provides process isolation but observes
through a terminal: subjects must render ANSI, evidence passes through a
normalizer, and input passes through conhost's console-input translation
with its documented caveats (issue #169).

GlyphWright's assessment names the missing flavor as the workhorse:
**spawn a child process, exchange line-delimited JSON, adapt to the port
protocol** — process isolation with full semantic observations and no
ANSI parsing, serving any JSONL-speaking subject, not just GlyphWright.
Today nothing in TermVerify speaks JSONL *to* a child; the transcript
JSONL is an evidence format, not a live control protocol.

The question the owner decision answered is whose vocabulary the child
speaks. Three options were considered:

- **Option A — subject-owned protocol, generic transport.** TermVerify
  would ship framing (newline-delimited JSON), a lifecycle handshake,
  and a failure taxonomy; the payload vocabulary would be each subject's
  own schema. Rejected: epoch causality, quiescence, capability
  negotiation, and evidence mapping then become per-subject code — the
  same "every adapter author rewrites it" trap the GlyphWright spike
  measured for the recorder — and this would be the first TermVerify
  boundary whose flowing content TermVerify cannot validate.
- **Option B — TermVerify-owned wire protocol
  (`termverify.control/v1`).** A closed, versioned control vocabulary
  mapping 1:1 onto the existing adapter contract. The transport adapter
  is fully generic: any conforming subject works with zero per-subject
  code, and recorded transcripts come out in the same shape as
  direct-adapter transcripts, which is exactly what differential
  direct-vs-JSONL conformance testing needs. **Accepted by owner
  decision 2026-07-20.**
- **Option C — TermVerify envelope, subject-owned payload.** Rejected:
  weakens the evidence semantics the comparator relies on and splits
  responsibility for quiescence and readiness between an envelope and an
  opaque payload.

Option B is the only option consistent with the established
architecture: every other boundary in TermVerify is a closed, versioned,
fail-closed vocabulary (`termverify.transcript/v1`, `termverify.key/v1`,
`termverify.key-encoding/v1`, `termverify.enforcement-tier/v1`,
`termverify.replay-subject/v1`). The subject-side obligation becomes
"implement `termverify.control/v1`" — for GlyphWright, a thin frontend
over its public API; speaking a wire protocol is not an import, so its
harness-neutrality ADR is untouched. Because `termverify.transcript/v1`
already fixes the run lifecycle (negotiation → readiness →
single-flight epochs → terminal record), most of this design is mapping
that lifecycle onto an interactive wire, not inventing a new one.

## Design rules

These bind both slices:

1. **The contract is the boundary.** The transport implements the
   existing `Adapter` protocol (`start`, `dispatch`, `advance_clock`,
   `stop`) and emits exactly the contract's value types. Callers —
   including the recorder, replay engine, and conformance suites —
   cannot tell a transport run from a direct or ConPTY run except by the
   subject selector and receipt contents they asked to record. No
   transport-specific type escapes into the contract.
2. **`termverify.control/v1` is closed, versioned, and fail-closed.**
   The wire vocabulary is fixed by this design and validated strictly on
   receipt: every inbound line must parse as canonical JSON, carry the
   exact protocol tag, match the lifecycle state, and respect fixed
   resource limits; anything else is a structured `run.failed`, never a
   guess or a repair. The protocol stays single-flight: no unsolicited
   messages, no interleaving, no correlation ids. Post-freeze amendments
   require a `v2`; the protocol lands unfrozen and freezes at the first
   PyPI publication after its slice merges, per the established
   inception policy.
3. **Fail closed at the process boundary.** Spawn failure, a child that
   exits early, a silent child past the abort deadline, a malformed
   peer, and teardown all produce structured results or errors with
   honest exit records. No fabricated observations, no silent record
   drops, no leaked child processes.
4. **Deterministic core, injected ambient boundary.** All process,
   pipe, and watchdog touchpoints sit behind an injectable binding, as
   in the ConPTY architecture: the adapter logic above the binding is
   fully fake-driven and ratcheted; the real binding is a thin ownership
   wrapper proven by real-subprocess integration tests on every CI leg.
   Pipes are portable, so this is the first runtime with identical
   integration evidence on Windows and POSIX.
5. **No containment claims.** The transport composes the existing
   cooperation-tier constraint ports for spawn-time delivery at the
   `delivered` tier. OS sandboxing remains the recorded non-goal;
   nothing here claims the subject honored a delivered constraint.

## Reuse assessment

Per the repo's adoption conventions, the obvious prior art was assessed
before designing a wire vocabulary:

- **JSON-RPC 2.0.** The canonical request/response JSONL protocol.
  Rejected as a base: its `id`-correlated request/response matching
  exists precisely to support concurrency and out-of-order replies,
  both of which are anti-features under transcript/v1's single-flight
  causality (transcript order supplies causality; a second in-flight
  input is invalid). Notifications and batching are likewise outside
  the single-flight model. What remains after removing the unwanted
  machinery — "JSON objects, one per line, on pipes" — is framing, not
  JSON-RPC. The one idea worth keeping is the explicit error-object
  shape (`code`, `message`, `details`), which transcript/v1 already
  uses for `run.failed`; `termverify.control/v1` adopts the same shape
  for peer errors so a wire failure and a transcript failure read alike.
- **Language Server Protocol (LSP).** The heavyweight prior art for
  lifecycle plus framing over pipes. Rejected: `Content-Length` header
  framing exists to multiplex over transports JSONL does not need; the
  initialize/initialized/shutdown handshake is a capability negotiation
  TermVerify already owns in richer form (the seven-constraint
  negotiation); and the message surface (asynchronous server-push
  notifications everywhere) contradicts single-flight. Adopting LSP
  would import a large surface to use almost none of it.
- **The subject-side JSONL protocols of the external subjects**
  (GlyphWright's `glyphwright.session/1`, `glyphwright.frame/1`, and
  siblings). These are evidence stream formats for one application, not
  control protocols; they have no capability negotiation, no input
  channel, and no failure taxonomy. GlyphWright's own assessment asks
  for the generic transport rather than adoption of its format. The
  correct relationship is a thin subject-side frontend translating
  between `termverify.control/v1` and the subject's API.

The design therefore builds no dependency and adopts no external
protocol; the framing is newline-delimited canonical JSON per the
repo's existing `_json`/rfc8785 habits, and the vocabulary is new but
derived member-for-member from the frozen transcript lifecycle.

## Architecture

```text
caller (recorder, replay, conformance suite)
      │  Adapter protocol, contract value types — unchanged
┌─────▼─────────────────────────────────────────────┐
│ JsonlAdapter (src/termverify/jsonl.py)            │
│  - lifecycle state machine (negotiation → ready → │
│    single-flight epochs → terminal)               │
│  - capability negotiation via ConstraintPorts     │
│  - termverify.control/v1 codec, strict, canonical │
│  - abort-deadline watchdog per epoch              │
├───────────────────────────────────────────────────┤
│ ChildBinding (injectable; real: pipes + process)  │
│  - spawn, write line, read line, exit status,     │
│    forced teardown of the child tree              │
└─────┬─────────────────────────────────────────────┘
      │  termverify.control/v1 over stdin/stdout pipes
┌─────▼─────────────────────────────────────────────┐
│ subject process (any language)                    │
│  speaks the control protocol; reads input         │
│  byte-wise from a PIPE — console-input caveats    │
│  (issue #169) do not apply                        │
└───────────────────────────────────────────────────┘
```

The adapter is deliberately the *third* implementation of one contract:
`DirectAdapter` (in-process), `ConptyAdapter` (terminal), `JsonlAdapter`
(structured pipe). Everything above the contract — recorder, comparator,
replay — works unchanged.

## `termverify.control/v1` message vocabulary

Every message is one canonical-JSON object on one line, UTF-8, no
embedded newlines, carrying exactly the members defined for its kind
plus uninterpreted `x-` extensions; the envelope member `protocol` is
exactly `termverify.control/v1`. Fixed resource limits (maximum line
length, maximum diagnostics per epoch, maximum startup diagnostics)
mirror `termverify.transcript/v1`'s fixed limits and are normative in
the protocol document, not implementation constants.

### Handshake and capability negotiation (adapter → child)

1. The adapter spawns the child through the cooperation-tier constraint
   ports (delivery environment and working directory exactly as the
   receipts will claim), then sends `session.hello` carrying the
   `run_id`, the requested constraint set from `RunConfiguration`, and
   the initial manual time. This message is the wire form of
   `run.started`'s configuration; the receipts the adapter returns are
   built from the *ports'* outcomes, with the child's matching
   acknowledgement required for liveness only — a child may not
   renegotiate, only refuse (`session.unsupported`, which maps to
   `ConstraintUnsupported` in configuration-table order) or fail.
2. On successful negotiation the child performs its initialization and
   sends exactly one `session.ready` message. Zero or more `diagnostic`
   messages may precede it; no other body message may. Its position —
   not a payload member — declares initialization complete and the
   subject ready for input, mirroring the transcript's initial
   readiness observation.

### Epochs (single-flight)

After readiness, each epoch is exactly:

1. one input message — `input.text`, `input.key` (a `termverify.key/v1`
   semantic chord; the child is a structured peer, so no
   `key-encoding/v1` byte encoding is involved), `input.resize`,
   `input.clock` (a manual-time advance; see below), or `input.stop`;
2. zero or more `diagnostic` messages caused while handling that input;
3. exactly one `observation` message closing the epoch at deterministic
   quiescence, unless a terminal message closes it first.

`observation` carries the same structure the contract's `Observation`
value carries: subject-defined UI observation, optional frame, zero or
more ordered events, and the process observation (`running`, or
`exited` with an exit status). The adapter maps fields mechanically;
any semantic content is the subject's evidence, not the adapter's
interpretation.

### Terminal messages

- `run.finished` from the child, followed by the child's actual exit —
  the adapter's `RunFinished` carries the *OS-observed* exit record
  (code or signal), with the child's claimed record disclosed as a
  diagnostic when both exist and differ. The OS record wins: evidence
  describes what the process did.
- `run.failed` from the child carries the `code`/`message`/`details`
  error shape; the adapter maps it to `RunFailed` verbatim.
- Adapter-side failures (spawn failure, malformed peer, abort-deadline
  expiry, forced teardown) produce the same structured results with
  codes from the transport's own taxonomy; they never wait on the
  child's cooperation.

### Failure taxonomy

The transport owns the structured codes for the failure class the
direct runtime cannot have: `spawn-failed`, `handshake-timeout`,
`peer-malformed` (non-JSON, wrong protocol tag, unknown kind, limit
violation), `peer-lifecycle` (message out of state — an observation
with no epoch open, a second readiness, body traffic after a terminal
message), and `epoch-timeout` (the abort deadline expired with an epoch
open). All are `run.failed`/`StartFailed`
material, never diagnostics.

> **Amendment (issue #178):** the originally-enumerated sixth code
> `teardown-forced` was removed before `termverify.control/v1` froze
> (first PyPI publication). It was defined but never emitted — the
> deadline-abort path emits `epoch-timeout` and discloses the
> forced-termination exit record in the terminal result, which is the
> intended surface. The protocol text
> (`docs/knowledge/control-protocol.md`) is authoritative; the
> disclosure claim now lives on the `epoch-timeout` row.

## Constraint semantics across the process boundary

> **Amended 2026-07-20** by
> [channel-tagged delivery records](channel-tagged-delivery-records.md)
> (owner decision on issue #173): the delivery model is no longer
> spawn-env-only. Six constraints remain `spawn-env` deliveries; the
> terminal constraint is a `hello-config` delivery — the dimensions in
> `session.hello.config` are the delivered values, and the receipt's
> delivery record names that channel. The tier claim (delivered, never
> honored) is unchanged.

Six constraints are spawn-time deliveries consumed from the existing
cooperation ports, with identical tier semantics: `delivered` where the
port delivers, honestly `unsupported` where the request exceeds the
port (named timezones, network allow-lists, non-empty terminal
capabilities). The terminal constraint is truthfully `unsupported` at
the `constructive` tier for any non-empty capability request — the
transport exposes no terminal — and is trivially satisfied for the empty
request.

**The clock channel is the one genuinely new capability.** The ConPTY
path can deliver only the initial manual time
(`TERMVERIFY_CLOCK_INITIAL_MS`); advances are adapter-side bookkeeping
the running child never sees. The control protocol makes
`advance_clock` a live wire message (`input.clock` carrying the target
manual time): the subject's port obligation — "your only clock is the
injected one" — becomes an operational channel, and a cooperative
subject can hold time-dependent behavior (animation step counts,
timeout simulation) to the same manual time the transcript records.
Subjects that ignore it after receipt breach their documented
cooperation obligation; the receipt claims delivery and liveness, never
compliance, exactly as the cooperation-tier design frames every
delivered constraint.

## Process lifecycle and teardown

The real child binding is the pipe-only generalization of the ConPTY
binding's proven patterns: spawn with an owned process tree (a
containment job on Windows; a process group on POSIX), capture a real
exit record on natural exit, and on abort-deadline expiry or
`Stop`-forced teardown terminate the tree and report the
forced-termination exit record with a disclosure diagnostic — the same
honesty rule as the ConPTY adapter's code-15 forced stop. Single-flight
I/O discipline applies: at most one read and one write in flight, and
writes during an open epoch are forbidden by the lifecycle machine, so
no interleaving can reach the wire.

Because the child's stdin is a pipe, not a console input buffer, the
Windows CRT wide-reader caveats of issue #169 do not apply; the
subject-side disclosure for this transport is the ordinary one: read
stdin as bytes, decode UTF-8, split on newlines.

## Slices and sequencing

Two slices are authorized on acceptance, each through the standard
workstream gate (focused issue, sibling worktree, TDD, full validation,
adversarial review):

1. **Protocol vocabulary, codec, and fake-child adapter.** The
   `termverify.control/v1` message model, strict canonical codec with
   the fixed limits, the lifecycle state machine, and `JsonlAdapter`
   against an injected fake binding — full contract behavior
   (negotiation including every unsupported/unsupported-mid-negotiation
   path, all five input kinds, quiescent epochs, early exit,
   early-exit-mid-epoch, every failure-taxonomy code, forced teardown)
   fake-driven under the coverage ratchet, plus protocol conformance
   tests for the codec's accept/reject boundary. No real process is
   spawned in this slice.
2. **Real-subprocess integration evidence.** The pipe/process binding,
   a reference fixture subject speaking `termverify.control/v1`
   (committed under `tests/fixtures/`, the loopback-plus-script pattern
   the ConPTY fixtures established), and integration tests proving a
   real run: negotiation with delivered-tier receipts, text/key/resize/
   clock epochs, natural exit with an OS-observed record, and forced
   teardown — on every CI leg, Windows and POSIX alike, since pipes
   are portable. A recorded fixture run passes through the recorder and
   comparator end-to-end, proving the Phase 2 core consumes the
   transport unchanged.

A GlyphWright JSONL-frontend conformance fixture (the second external
subject, alongside the vendored direct spike) is explicitly **not**
part of these slices; it follows the subject's own implementation of
`termverify.control/v1` and proceeds as its own later decision, as the
direct-spike vendoring did.

## Non-goals

Each requires its own future owner decision:

- **Asynchronous or unsolicited traffic.** The protocol is
  single-flight per transcript/v1; general async work awaits an
  explicit polling/draining/correlation contract, as the transcript
  protocol itself records.
- **Subject discovery or launch from replay selectors.** Replay stays
  caller-bound: the caller supplies an `Adapter`; the transport never
  resolves a `replay-subject/v1` selector into a spawn command.
- **OS containment or sandboxing.** Unchanged from the recorded
  containment non-goal.
- **New transcript, registry, or vocabulary versions beyond
  `termverify.control/v1` itself.** The transcript protocol stays
  exactly v1; the transport emits nothing the recorder cannot already
  record. Any design-level need for a transcript change suspends the
  slice and returns to the owner.
- **A public spawn-string API.** How the caller names its executable
  and arguments is adapter-construction configuration, not protocol;
  fixture identity in the replay selector remains the stable evidence
  claim. Raw `argv` remains forbidden as a generic subject member.
- **A POSIX PTY adapter, release claims, or index publication** beyond
  the established freeze-at-next-publication note for the new protocol.

## Risks

- **Protocol scope creep at the wire.** The control protocol sits where
  every external subject will ask for "just one more message kind."
  Mitigation: rule 2 — the vocabulary is closed by this design; any new
  kind is a stop-and-return event and eventually a v2.
- **A second lifecycle interpretation.** The wire lifecycle and the
  transcript lifecycle must never drift. Mitigation: this design
  derives each message from the transcript lifecycle shape it mirrors,
  and slice 1's conformance tests assert the mapping; the strict
  transcript codec remains the only evidence gate.
- **Teardown platform skew.** Windows job objects and POSIX process
  groups differ; a leaky abstraction would re-import ambient process
  semantics. Mitigation: the binding owns the difference behind one
  interface with identical observable outcomes (real exit record,
  forced-termination record, no survivors), and slice 2 runs identical
  assertions on every leg.
- **Clock-channel overclaim.** A live `input.clock` may read as "the
  subject's clock is controlled." It is not; it is delivered and
  acknowledged, never enforced. Mitigation: rule 5 and the receipt
  semantics above; the disclosure is normative in the developer-guide
  documentation slice 2 adds.

## Acceptance and sequencing

On owner acceptance, the two slices are authorized in order — slice 2
consumes slice 1's codec and adapter. Completion of slice 2 is the
natural reassessment point for external-subject conformance fixtures
against the transport. Acceptance activates this design for exactly the
scope above and nothing else; every other deferred ask and non-goal
stands unchanged.
