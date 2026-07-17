# Pre-release Boundary Hardening Handover

## Handover metadata

- **Status:** draft — the maintainer accepted the scope transfer on 2026-07-17,
  but this successor does not become active until the remaining Phase 1
  transcript-resource slice and amended completion gates pass and the reviewed
  supersession/archive transition activates it.
- **Owner:** project maintainer
- **Created:** 2026-07-17
- **Updated:** 2026-07-17
- **Review required:** yes — activation and every workstream that changes public
  compatibility, enforcement, distribution, security, or release claims require
  executable evidence and independent human-readable review.
- **Predecessor:**
  [Phase 1 readiness hardening handover](phase-1-readiness-hardening-handover.md)
  (active until the later supersession transition)
- **Successor:** none
- **Activation:** only after the predecessor's deterministic transcript-resource
  limits and amended fixture/schema/workflow completion gates pass, an exact
  candidate receives independent review, and the predecessor is marked
  `superseded` and archived in the same reviewed transition.
- **Completion:** every transferred criterion below is implemented and verified,
  or is moved intact through another explicit owner-reviewed successor boundary;
  no unsupported semantic, containment, terminal, schema-publication, or release
  claim is exposed in the meantime.

## Purpose and boundaries

This draft successor preserves the criteria that the maintainer explicitly
removed from the current Phase 1 implementation boundary on 2026-07-17. The
transfer is scope governance, not evidence that any criterion is complete. It
also does not activate Phase 2, transcript replay/comparison, sensitive evidence
retention, behavioral baselines, artifact publication, or a production terminal
adapter.

The predecessor remains active for one implementation class: deterministic,
fail-closed transcript byte, line, record-count, nesting, and structured-value
limits with parser/serializer symmetry. This successor must not absorb or weaken
that work before the predecessor's reviewed supersession transition.

## Accepted transferred scope

Every row has disposition **transfer intact to this named successor**.

| Workstream | Transferred criterion | Unsupported-until-approved boundary |
| --- | --- | --- |
| Deterministic vocabulary and configuration semantics | Named-timezone membership, tzdb source/version, canonical-versus-alias policy, update and compatibility semantics | `TimezoneReceipt` continues to reject named zones other than `UTC`; no ambient `zoneinfo` membership is inferred. |
| Deterministic vocabulary and configuration semantics | Closed, versioned semantic key-name registry, including modifier/chord spelling and adapter mapping | The immutable/direct adapter surface continues to omit `input.key`; syntax-only transcript strings are not approved semantic names. |
| Deterministic vocabulary and configuration semantics | Closed, versioned terminal-capability registry with observable semantics and enforcement evidence | Non-empty terminal-capability receipts remain rejected; requested/effective equality is not enforcement proof. |
| Concurrent event correlation | Explicit correlation and ordering for concurrent inputs or unsolicited/asynchronous events | V1 remains single-flight; idle unsolicited body records remain invalid; no wall-clock quiet period is evidence of causality or quiescence. |
| Production containment | Filesystem root mapping and lifecycle, traversal, symlink/reparse-point handling, child-process inheritance/containment, cleanup, and failure semantics | Direct execution may route an explicit application port but does not prove OS containment; terminal/subprocess enforcement remains unsupported. |
| Production containment | Network allow-list DNS, address normalization, redirects, proxies, loopback, subprocess inheritance, and failure semantics | Direct receipts remain deny-only; allow-list enforcement remains rejected; terminal/subprocess enforcement remains unsupported. |
| Distribution and release governance | Installed schema access API and exact wheel/sdist resource contract | Repository schema presence is not installed access; no package claim is made until isolated installation tests pass. |
| Distribution and release governance | Resolvable canonical schema publication for the documented `$id` | The current unresolved host is not a publication contract. Runtime validation remains authoritative. |
| Distribution and release governance | Release checklist, changelog/compatibility policy, security-disclosure process, and build/release provenance | Required before the first supported external artifact; no stable/public release claim is implied by the current pre-alpha package. |
| Distribution and release governance | Reviewed behavior-based coverage-ratchet activation | Coverage remains reported without an invented threshold until a separately reviewed no-regression rule is accepted. |
| Production terminal adapter | Direct native pseudoconsole ownership/close, native EOF and final-frame draining, process-tree teardown, cancellation/recovery, and truthful OS-level enforcement evidence | PR #53 remains partial binding-level feasibility evidence; no spike promotion or `pywinpty` dependency is authorized. |

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
  decomposition.

## Workstream gates

Each workstream needs its own focused issue, branch, external sibling worktree,
TDD evidence where behavior changes, full relevant validation, and exact-candidate
independent review. Workstreams may proceed only after this handover becomes
active and only when their public semantics and non-goals are accepted.

### 1. Deterministic vocabulary and configuration semantics

Define registry ownership, versioning, aliases, normalization, update policy,
and enforcement evidence before exposing named timezone, key, or terminal
capability semantics. Do not derive protocol meaning from ambient host registries,
toolkit enums, terminfo, virtual-key codes, or escape sequences.

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

### 5. Production terminal adapter

Select a dependency and public boundary only through a separate rationale and
verification plan. Prove native ownership, close, EOF/final-frame drain,
process-tree teardown, cancellation/recovery, dimensions, and truthful constraint
enforcement. PR #53 is a reproduction hypothesis and binding feasibility record,
not production evidence.

## Risks and non-negotiables

- Do not expose unresolved key, capability, timezone, filesystem, network, or
  terminal semantics through permissive syntax or fabricated receipts.
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

- Keep **draft** while the predecessor remains active.
- Mark **active** only in the same reviewed change that marks the predecessor
  `superseded`, archives it, updates the index, and proves the predecessor's
  resource/amended-gate boundary passed.
- Mark **blocked** only when all safe work depends on an unresolved owner decision,
  unavailable independent review, or external enforcement evidence.
- Mark **complete** only when every transferred criterion is implemented and the
  integrated boundary passes its required review, or when another named successor
  accepts every unresolved criterion intact.
- Activation or completion of this handover does not activate Phase 2.
