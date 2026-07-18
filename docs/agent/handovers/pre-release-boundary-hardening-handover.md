# Pre-release Boundary Hardening Handover

## Handover metadata

- **Status:** active — effective when the reviewed transition resolving issue
  #87 merges. The predecessor's deterministic transcript-resource and amended
  completion gates passed independent integrated review. Phase 2 is not active.
- **Owner:** project maintainer
- **Created:** 2026-07-17
- **Updated:** 2026-07-17
- **Review required:** yes — activation and every workstream that changes public
  compatibility, enforcement, distribution, security, or release claims require
  executable evidence and independent human-readable review.
- **Predecessor:**
  [Phase 1 readiness hardening handover](archive/phase-1-readiness-hardening-handover.md)
  (superseded and archived in the same transition)
- **Successor:** none
- **Activation:** authorized by the independent integrated review of exact merged
  `main` at `806372efa3897b7c2d88c2f58b0c8a9abe9cb401`, tree
  `bbf85b7b4ccae7a97bbc81016f70b25fe2be997e`, and effective when the separately
  reviewed documentation transition resolving issue #87 merges and archives the
  predecessor.
- **Completion:** every transferred criterion below is implemented and verified,
  or is moved intact through another explicit owner-reviewed successor boundary;
  no unsupported semantic, containment, terminal, schema-publication, or release
  claim is exposed in the meantime.

## Purpose and boundaries

This active successor preserves the criteria that the maintainer explicitly
removed from the current Phase 1 implementation boundary on 2026-07-17. The
transfer is scope governance, not evidence that any criterion is complete. It
also does not activate Phase 2, transcript replay/comparison, sensitive evidence
retention, behavioral baselines, artifact publication, or a production terminal
adapter.

The predecessor completed deterministic, fail-closed transcript byte, line,
record-count, nesting, and structured-value limits with parser/serializer
symmetry before supersession. This successor does not absorb, weaken, or reopen
that completed boundary.

## Accepted transferred scope

Every row has disposition **transfer intact to this named successor**.

| Workstream | Transferred criterion | Current boundary |
| --- | --- | --- |
| Deterministic vocabulary and configuration semantics | Named-timezone enforcement evidence and any post-freeze registry evolution beyond the protocol-bound v1 registry | `TimezoneReceipt` continues to reject named zones other than `UTC`; no ambient `zoneinfo` membership or enforcement is inferred. |
| Deterministic vocabulary and configuration semantics | Closed, versioned semantic key-name registry, including modifier/chord spelling and adapter mapping | Implemented as protocol-owned `termverify.key/v1`, immutable `KeyInput`, and direct dispatch that forwards it unchanged. Terminal-byte/toolkit mapping and key-support negotiation remain separate unsupported work. |
| Deterministic vocabulary and configuration semantics | Closed, versioned terminal-capability registry with observable semantics and enforcement evidence | Non-empty terminal-capability receipts remain rejected; requested/effective equality is not enforcement proof. |
| Concurrent event correlation | Explicit correlation and ordering for concurrent inputs or unsolicited/asynchronous events | V1 remains single-flight; idle unsolicited body records remain invalid; no wall-clock quiet period is evidence of causality or quiescence. |
| Production containment | Filesystem root mapping and lifecycle, traversal, symlink/reparse-point handling, child-process inheritance/containment, cleanup, and failure semantics | Direct execution may route an explicit application port but does not prove OS containment; terminal/subprocess enforcement remains unsupported. |
| Production containment | Network allow-list DNS, address normalization, redirects, proxies, loopback, subprocess inheritance, and failure semantics | Direct receipts remain deny-only; allow-list enforcement remains rejected; terminal/subprocess enforcement remains unsupported. |
| Distribution and release governance | Installed schema access API and exact wheel/sdist resource contract | Implemented: the canonical schema is a packaged resource with public byte/object accessors, and isolated wheel and sdist installation checks verify byte identity with the committed copy. Canonical `$id` publication remains transferred and unresolved. |
| Distribution and release governance | Resolvable canonical schema publication for the documented `$id` | The current unresolved host is not a publication contract. Runtime validation remains authoritative. |
| Distribution and release governance | Release checklist, changelog/compatibility policy, security-disclosure process, and build/release provenance | Implemented as governance: reviewed checklist, changelog with pre-1.0 policy, private-disclosure process, and a tag-triggered attested draft-artifact workflow. No release is authorized, no index publishing exists, and the package remains pre-alpha. |
| Distribution and release governance | Reviewed behavior-based coverage-ratchet activation | Implemented: the committed `fail_under` floor is the integer floor of the reviewed observed total (94.43% at activation), raises require sustained durable coverage, and lowering requires explicit owner review. |
| Production terminal adapter | Direct native pseudoconsole ownership/close, native EOF and final-frame draining, process-tree teardown, cancellation/recovery, and truthful OS-level enforcement evidence | The accepted dependency decision (`docs/agent/design/terminal-adapter-dependency-decision.md`) authorizes reviewed implementation slices with pinned `pywinpty`/ConPTY behind its verification plan. Slices 2–4 landed durable Windows-matrix evidence for native ownership/close, EOF/final-frame drain, job-object process-tree teardown, and binding-level cancellation/recovery with hostile-child fixtures (plan items 2–4 and the binding half of item 5); taxonomy classification, dimensions receipts, and every enforcement claim remain unproven until their planned evidence lands. |

## Completion-definition amendments retained from the predecessor

These criteria were **removed from the predecessor's literal completion
requirements**, not transferred here as mandatory exhaustive work:

1. A "complete fixture corpus" means reviewed behavior-based coverage of every
   supported path. Evidence may combine canonical fixtures, focused positive and
   negative tests, and generated properties. Canonical fixtures remain required
   where exact bytes and compatibility identity are the behavior under review.
2. Draft 2020-12 JSON Schema remains a deliberately non-exhaustive structural and
   record-local aid. Exhaustive per-kind encoding is not a phase-completion
   condition. Schema/runtime agreement is required only for rules the schema
   actually encodes; runtime validation remains authoritative for complete
   acceptance.
3. The retained workflow-security boundary is the existing pinned `zizmor` and
   OSV-Scanner coverage. An additional syntax/policy checker is not a completion
   condition unless later evidence shows maintained, non-duplicative signal.

A future workstream may propose broader fixtures, schema coverage, or another
workflow checker, but this handover must not silently turn those optional
improvements back into predecessor completion gates.

## Confirmed completed boundaries not to reopen

The following reviewed behavior belongs to the predecessor/remediation history
and is not work for this successor unless fresh executable evidence shows a
regression:

- parser/serializer semantic identity, canonical RFC 8785 bytes, duplicate-member
  rejection, recursive JSON shape/type strictness, and recursive tuple rejection;
- readiness, single-flight epochs, port-reported quiescence, drain-aware stop,
  terminal closure, and exact receipt type/run/effective-value binding;
- immutable adapter values, deep-frozen application JSON, and diagnostic-time
  coherence at aggregate construction boundaries;
- direct-runtime failure classification, compound abort-detail preservation,
  cleanup-safe startup failure handling, and absorbing terminal state;
- field-first fail-closed evidence classification, deterministic transformation
  of unbounded semantic strings and `x-` names, secondary credential defense,
  and post-redaction semantic revalidation;
- same-directory unique temporary writes, close, and atomic safe replacement at
  the accepted no-`fsync`, no-crash-durability level;
- narrow shared v1 internals and behavior-preserving lifecycle-validator
  decomposition;
- closed `termverify.key/v1` membership and chord grammar, immutable `KeyInput`,
  direct dispatch without text/byte fallback, and registry-valid safe-evidence
  key transformation.

## Workstream gates

Each workstream needs its own focused issue, branch, external sibling worktree,
TDD evidence where behavior changes, full relevant validation, and exact-candidate
independent review. A workstream may proceed only when its public semantics and
non-goals are accepted.

### 1. Deterministic vocabulary and configuration semantics

Define registry ownership, versioning, aliases, normalization, update policy,
and enforcement evidence before exposing named timezone, key, or terminal
capability semantics. Do not derive protocol meaning from ambient host registries,
toolkit enums, terminfo, virtual-key codes, or escape sequences.

The owner accepted the first focused contract slice on 2026-07-17. Requested
timezone membership is now bound to the closed `termverify.timezone/v1`
registry: literal `UTC` plus primary `Zone` names from pinned IANA TZDB 2026c,
with exact case-sensitive spelling, no normalization, and no `Link`, `backzone`,
or `factory` names. Runtime validation owns membership independently of ambient
host data; schema validation remains deliberately non-exhaustive. V1 corrections
remain owner-reviewed during inception, while post-freeze membership or meaning
changes require a new transcript protocol version. This accepted request-level
contract does not authorize named-timezone receipts: named enforcement evidence
remains transferred and fail-closed.

The owner accepted the second focused contract slice on 2026-07-17. Semantic
key input is now bound to the closed `termverify.key/v1` component registry and
one-chord array grammar: exact case-sensitive names, canonical unique modifier
ordering, no aliases or normalization, and no toolkit, virtual-key, or escape
byte values. Unmodified printable insertion remains `input.text`. The immutable
adapter exposes `KeyInput`, and direct dispatch forwards it unchanged; an
application that cannot execute it uses the existing structured runtime-failure
and abort path rather than post-readiness `run.unsupported` or silent fallback.
Safe persistence replaces every chord with the valid `["Escape"]` sentinel and
revalidates. Runtime validation owns the registry beyond the deliberately
non-exhaustive schema. Post-freeze membership or meaning changes require a new
transcript and key-registry version. Terminal encoding and capability evidence
remain outside this slice.

### 2. Concurrent event correlation

Introduce explicit versioned correlation only when a demonstrated application
requires concurrent or unsolicited work. Preserve transcript-position causality
and single-flight v1 rather than weakening it retroactively. This workstream does
not authorize replay/comparison.

### 3. Production containment

Specify and prove filesystem and network policy at the relevant direct or OS
boundary. Requested policy remains distinct from receipts and observations of
what was actually enforced. Fail unsupported rather than falling back to ambient
filesystem, DNS, proxy, loopback, or subprocess behavior.

### 4. Distribution and release governance

Define installed schema access, canonical publication, release/security/provenance
controls, and the coverage-ratchet activation rule before the first supported
external artifact. Preserve the schema's non-exhaustive role and keep behavioral
acceptance runtime-authoritative.

The owner accepted the first focused distribution slice on 2026-07-17 (issue
#95). The canonical committed transcript schema lives inside the package at
`src/termverify/schemas/termverify.transcript/v1.schema.json` as the single
authoritative copy, so wheel and sdist carry it automatically. The public API
exposes `TRANSCRIPT_SCHEMA_V1_ID`, exact resource bytes, and a fresh parsed
object per call. Isolated `--no-project` installation checks against both built
artifacts verify version metadata, public callables, and byte identity between
the installed resource and the committed schema. This slice does not publish a
resolvable `$id`, change schema content or its non-exhaustive role, weaken
runtime authority, or make any release claim; those criteria remain transferred
and fail-closed.

The owner accepted the second focused distribution slice on 2026-07-17 (issue
#97): behavior-based coverage-ratchet activation. The committed
`fail_under = 94` floor in `pyproject.toml` is the integer floor of the
reviewed observed full-suite total (94.43% line-and-branch at activation), so
the gate encodes observed behavior rather than an invented threshold.
Executable evidence showed the gate failing at a floor above the observed
total and passing at the activated floor; the committed reporting precision
makes the comparison a strict floor without integer rounding grace. Raising
the floor requires the observed total to stay at least one point above the
current floor across the CI matrix;
lowering it requires explicit owner review with recorded rationale
(`docs/developer-guide/development.md`). This slice adds no per-file gates, no
behavioral baselines, and no tests whose only purpose is to move the number.

The owner accepted the third focused distribution slice on 2026-07-17 (issue
#99): release governance controls. `CHANGELOG.md` records the pre-1.0
compatibility policy and keeps package versioning explicitly distinct from the
immutable transcript and registry protocol versions. `SECURITY.md` defines
private disclosure through GitHub advisories with a truthful pre-alpha support
scope. `docs/developer-guide/release.md` is the reviewed checklist: version
bump and changelog in a human-reviewed PR, tag-triggered CI build, isolated
installed-package contract checks, GitHub build-provenance attestation, and a
draft-only GitHub release whose publication is a manual human decision. The
`Release` workflow builds and attests draft artifacts only; it cannot publish
to a package index because no such pipeline or credential exists. Accepting
these controls authorizes no release: the first supported external artifact
still requires the checklist's preconditions and the owner-reviewed completion
state of this handover.

### 5. Production terminal adapter

Select a dependency and public boundary only through a separate rationale and
verification plan. Prove native ownership, close, EOF/final-frame drain,
process-tree teardown, cancellation/recovery, dimensions, and truthful constraint
enforcement. PR #53 is a reproduction hypothesis and binding feasibility record,
not production evidence.

The owner accepted the dependency and verification decision on 2026-07-17
(issue #102):
[`terminal-adapter-dependency-decision.md`](../design/terminal-adapter-dependency-decision.md)
selects pinned `pywinpty` with the ConPTY backend exclusively, fixes the
public boundary to the existing `Adapter`/`ConstraintPorts` contract with
fail-closed semantics, and defines the executable verification plan for
ownership/close, EOF/final-frame drain, process-tree teardown,
cancellation/recovery, dimensions, truthful receipts, and dependency
governance. Acceptance authorizes reviewed implementation slices to add the
pinned dependency behind that plan; no adapter exists, and every claim in the
transferred criterion stays unproven until its planned evidence lands.

Implementation slice 1 landed on 2026-07-17 (issue #104): `pywinpty` is a
pinned Windows-marker dependency, the thin `termverify._conpty` binding is the
only module touching it, and the spike behaviors are promoted into durable
Windows-matrix integration tests — child creation, initial dimensions, echoed
input, marker-bounded burst on a dedicated reader thread, explicit resize,
forced close, integer exit status — plus a fail-closed non-Windows spawn
test. The binding is the single reviewed coverage-ratchet exclusion with
rationale in the developer guide. Native EOF and final-frame drain,
process-tree teardown, cancellation/recovery, dimensions receipts, and every
enforcement claim remain unproven and fail-closed; the binding's `write`
deliberately returns no byte-count receipt.

Implementation slice 2 landed on 2026-07-17 (issue #106), covering
verification-plan items 2 and 3. The binding now owns the native
`winpty._winpty.PTY` object directly: pywinpty's `PtyProcess` wrapper routes
output through an internal socket-relay reader thread that measurably lost
buffered output after child exit and swallowed the native end-of-stream
signal, and the plan rejects reader-thread state as evidence. Durable
Windows-matrix tests now prove: a marker-bounded 1 MiB burst written by an
exiting child drains byte-complete until the native output pipe reports
end-of-stream, classified from the failing native read plus the native
liveness and exit records; forced close terminates the child, verified by an
OS process-handle wait with exit-code agreement between the OS record and the
binding; and a release-only close proves deterministic native handle release
because ConPTY itself terminates the attached client with
`STATUS_CONTROL_C_EXIT`, observed entirely outside the binding, while the
binding truthfully records no exit status it never observed. Close
unpublishes the native object, cancels in-flight native reads and writes
until each returns, classifies I/O interrupted by close as the closed error
instead of leaking raw native failures, and drops frame-local native
references before raising so a held exception traceback cannot pin the
handles; a regression test closes while a reader is parked on an empty pipe
and observes the client's `STATUS_CONTROL_C_EXIT` termination while the
terminal exception is still held. End-of-stream classification is only
claimed while the binding is open, because a close may abandon buffered
output. Process-tree teardown, cancellation/recovery taxonomy, dimensions
receipts, enforcement receipts, and evidence normalization remain unproven
and fail-closed.

Implementation slice 3 landed on 2026-07-17 (issue #108), covering
verification-plan item 4: process-tree teardown. Every spawn now assigns the
child to a fresh Windows job object with
`JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` and neither breakaway limit before the
binding is handed out; a containment failure terminates the just-spawned
child and fails the spawn closed. Forced close terminates the whole tree
atomically with `TerminateJobObject` (uniform exit code 15, preserving the
slice-2 exit-code evidence) and waits on the child's already-held process
handle, eliminating the previous pid-based kill and its recycle window.
Release-only close keeps its slice-2 semantics for the direct child
(pseudoconsole release, `STATUS_CONTROL_C_EXIT`), waits for that
termination on the child's process handle, then closes the job handle so
the kill-on-close limit sweeps any remaining descendants — and the same
sweep fires if the owning process dies abruptly. Durable Windows-matrix
tests with a deliberately spawning child prove both paths by OS
process-handle waits on the child and the grandchild, with the two kill
mechanisms attributed separately: a console-attached grandchild dies of the
pseudoconsole teardown itself (`STATUS_CONTROL_C_EXIT`), while a
console-detached grandchild — which the pseudoconsole cannot reach — is
killed only by the job sweep (exit code 0), isolating the sweep as its own
evidenced mechanism. A fault-injected containment failure at spawn is also
proven fail-closed: the spawn raises and the already-created child is
OS-observed terminated. Disclosed boundary:
job assignment happens immediately after `CreateProcess` returns, so a
process the child starts within that microseconds-wide window would fall
outside the job; the binding documents this rather than claiming pre-start
assignment. Cancellation/recovery taxonomy, dimensions receipts,
enforcement receipts, and evidence normalization remain unproven and
fail-closed.

Implementation slice 4 landed on 2026-07-18 (issue #110), covering the
binding-level half of verification-plan item 5 with hostile-child fixtures.
Adversarial review of the first candidate found that overlapped native I/O
on one pseudoconsole — a concurrent `pty.write` against a blocked
`pty.read` — intermittently crashes the interpreter with a native access
violation (reproduced ~2% per run under a write storm, faulthandler-
attributed, upstream `pywinpty` shares the pattern). The binding therefore
now enforces the transcript protocol's single-flight model at its own
boundary: at most one read or write may be in flight, overlap fails fast
with `ConptyConcurrentIOError`, and `close` remains the one
concurrent-safe operation. Startup failure fails closed for both modes: a
missing command raises before any native session exists, and a command the
OS refuses to start surfaces a classified error whose held exception chain
provably cannot pin the native pseudoconsole. Forced close recovers,
OS-observed, from an unbounded output flood, from a busy unresponsive
child (job termination needs no cooperation), and from an in-flight native
write: a deliberately large write keeps the native call in flight while
close lands, and ordering evidence shows close returns only after the
write frame returned — the wait-out discipline that prevents the
release-during-native-call crash (observed experimentally). Handle release
stays observable under hostile load: a release-only close under flood
still ends the child with `STATUS_CONTROL_C_EXIT`. Conin writes showed no
backpressure on the verified matrix (7.1 GiB in 20 s against a child that
never reads, experiment recorded in issue #110), and a write that did
block on some SKU would fail the bounded-flood test loudly rather than
hang it. Classification of these outcomes into the structured
failure/abort taxonomy is adapter behavior and stays unclaimed until the
public `Adapter` slice; dimensions receipts, enforcement receipts, and
evidence normalization remain unproven and fail-closed.

The owner accepted the ConPTY adapter design on 2026-07-18 (issue #112,
`docs/agent/design/conpty-adapter-design.md`, adversarially reviewed). It
scopes verification-plan items 5 (classification half), 6, 7, and 8 into
four authorized implementation slices: a public `ConptyAdapter` layered
above an injected binding port (with an explicit support probe) and an
injected output-normalizer port, truthful negotiation in which the adapter
enforces only the terminal constraint and shipped default ports report the
other six constraints as not enforced, readiness defined solely by an
explicit subject-emitted marker or observed end-of-stream plus exit record,
a mandatory explicitly configured abort deadline that can only produce
structured failure, and raw-VT retention with replayable normalization. No
adapter code exists yet; every claim in that document stays fail-closed
until its slice lands with evidence.

Adapter slice 1 landed on 2026-07-18 (issue #115): the normalizer
reuse/dependency assessment (`docs/agent/design/vt-normalizer-decision.md`,
rejecting `pyte` on license, dormancy, and fail-open grounds) and
`termverify.vt` — the `TerminalOutputNormalizer` port exactly as the
adapter design fixed it, plus a deterministic in-house screen model for a
closed, documented VT subset with replay identity `termverify.vt`/`1`.
Unknown grid-affecting input fails closed with a structured error and a
defined post-error parser state; string sequences (including the readiness
marker's private OSC) are consumed and never rendered; the module is
cross-platform, pure, and 100% line- and branch-covered under the ratchet.
The v1 subset's coverage of real ConPTY output remains an unproven claim
until the Windows integration slice; adapter negotiation, epoch machinery,
and all receipts remain unbuilt and fail-closed.

## Risks and non-negotiables

- Do not expose unresolved capability, timezone-enforcement, filesystem,
  network, terminal-mapping, or other semantics through permissive syntax or
  fabricated receipts.
- Do not infer quiescence, drain completion, or causality from wall-clock silence.
- Do not promote the ConPTY spike or add `pywinpty` without a separately accepted
  dependency and verification decision.
- Do not make schema acceptance equivalent to protocol conformance.
- Do not weaken safe-evidence classification, post-redaction revalidation, or
  atomic replacement, and do not enable sensitive persistence or claim crash
  durability.
- Do not activate behavioral baselines or approve golden masters automatically.
- Do not activate Phase 2 from this handover. A separate accepted phase-boundary
  decision remains mandatory.

## Transition rules

- This handover is **active** effective when the reviewed transition resolving
  issue #87 marks the predecessor `superseded`, archives it, and updates the
  index in the same merge.
- Mark **blocked** only when all safe work depends on an unresolved owner decision,
  unavailable independent review, or external enforcement evidence.
- Mark **complete** only when every transferred criterion is implemented and the
  integrated boundary passes its required review, or when another named successor
  accepts every unresolved criterion intact.
- Activation or completion of this handover does not activate Phase 2.
