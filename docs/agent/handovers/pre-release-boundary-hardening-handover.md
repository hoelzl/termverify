# Pre-release Boundary Hardening Handover

## Handover metadata

- **Status:** active — effective when the reviewed transition resolving issue
  #87 merges. The predecessor's deterministic transcript-resource and amended
  completion gates passed independent integrated review. Phase 2 is active as
  of the owner-accepted
  [Phase 2 verification-core boundary decision](../design/phase-2-verification-core-boundary.md)
  (2026-07-19, issue #146) — for exactly that design's scope and nothing else;
  this handover's transferred criteria, retirements, and deferrals are
  unchanged by that activation.
- **Owner:** project maintainer
- **Created:** 2026-07-17
- **Updated:** 2026-07-19
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
  is moved intact through another explicit owner-reviewed successor boundary,
  or is retired to an explicit non-goal by a recorded, reviewed owner decision
  (amendment 2026-07-18: retirement admitted as a disposition by the
  cooperation-tier decision);
  no unsupported semantic, containment, terminal, schema-publication, or release
  claim is exposed in the meantime.

## Purpose and boundaries

This active successor preserves the criteria that the maintainer explicitly
removed from the current Phase 1 implementation boundary on 2026-07-17. The
transfer is scope governance, not evidence that any criterion is complete. It
also does not activate Phase 2, transcript replay/comparison, sensitive evidence
retention, behavioral baselines, artifact publication, or a production terminal
adapter.

Phase 2 activation (2026-07-19): the separately accepted
[Phase 2 verification-core boundary decision](../design/phase-2-verification-core-boundary.md)
(issue #146) — not this handover — activates Phase 2 for a narrow
verification core that is a pure consumer of the frozen
`termverify.transcript/v1` protocol: three sequential implementation
slices (transcript recorder + minimal run orchestrator, exact comparator +
deterministic report, caller-bound transcript replay), each gated through
its own focused issue, sibling worktree, TDD evidence, full validation,
and adversarial review, with each slice beginning only after its
predecessor's acceptance. That decision changes no transcript semantics,
adds no dependency, makes no release claim, and leaves every transferred
criterion, retirement, and deferral in this handover unchanged; behavioral
baselines and golden-master governance remain outside its boundary.

The owner accepted Phase 2 slice 1 on 2026-07-19 (issue #148, PR #150,
adversarial review ACCEPT after one fix round — three should-fix findings
and five nits, all addressed and re-verified by the reviewer):
`termverify.recorder` provides the public `TranscriptRecorder`, which
assembles the immutable adapter result values into
`termverify.transcript/v1` records in occurrence order and fails closed
with structured errors on out-of-order, mistimed, or foreign
contributions, and the minimal `run_scripted` orchestrator, which drives
one adapter through a scripted input sequence and returns validated
transcript bytes plus the terminal outcome. Output passes only through
the existing strict serializer — the codec remains the sole acceptance
gate, and the protocol is unchanged. Evidence: unit and property tests
over fake adapters for every lifecycle shape the protocol admits at 100%
module line-and-branch coverage, byte-identical repeat runs over the real
`DirectAdapter` with a cooperative fixture application, and GlyphWright's
spike transcript imported unmodified as an external conformance fixture
with provenance and license — reproduced exactly except the disclosed
mandatory enforcement-tier member the spike predates.

The owner accepted Phase 2 slice 2 on 2026-07-19 (issue #151, PR #152,
adversarial review REJECT then ACCEPT after one fix round — one must-fix,
the missing mouse/clipboard divergence evidence; one should-fix, an exact
truncation byte count; two nits — all addressed and re-verified by the
reviewer): `termverify.comparator` provides `compare_transcripts`, which
validates both inputs with the strict codec (an invalid side is a
structured `TranscriptInputError`, never a comparison result) and compares
records by canonical semantic equality of envelope and payload over the
full sequence with exactly one disclosed identity exclusion, the envelope
`run_id` — the exclusion set is closed, and extending it requires an
owner-accepted amendment — and `render_report`, a deterministic plain-text
rendering of the structured verdict with a bounded member-level diff,
never a second comparison implementation and never a golden master.
Evidence: reflexivity, symmetry, and run-id-insensitivity properties;
targeted divergence tests for all fourteen v1 record kinds plus
envelope-only, type, list-length, and record-count differences (every
mutated copy passes back through the strict codec); fixture tests over the
recorder's accepted reproduction of the GlyphWright transcript against
mutated copies; report determinism and bounding tests that never assert
stored report bytes; 100% module line-and-branch coverage. Slice 3
(caller-bound transcript replay) is now authorized to begin; replay
remains absent until its slice lands.

The predecessor completed deterministic, fail-closed transcript byte, line,
record-count, nesting, and structured-value limits with parser/serializer
symmetry before supersession. This successor does not absorb, weaken, or reopen
that completed boundary.

## Accepted transferred scope

Every row originally had disposition **transfer intact to this named
successor**. Amendment 2026-07-18: the two production-containment rows now
carry the disposition **retired to an explicit non-goal by recorded owner
decision** with a narrower replacement scope; every other row remains
transfer-intact.

| Workstream | Transferred criterion | Current boundary |
| --- | --- | --- |
| Deterministic vocabulary and configuration semantics | Named-timezone enforcement evidence and any post-freeze registry evolution beyond the protocol-bound v1 registry | `TimezoneReceipt` continues to reject named zones other than `UTC`; no ambient `zoneinfo` membership or enforcement is inferred. Owner decision 2026-07-19: deferred until demonstrated need; the criterion stays transferred intact, and reopening needs only a new owner decision. |
| Deterministic vocabulary and configuration semantics | Closed, versioned semantic key-name registry, including modifier/chord spelling and adapter mapping | Implemented as protocol-owned `termverify.key/v1`, immutable `KeyInput`, and direct dispatch that forwards it unchanged. Owner decision 2026-07-19: the key-to-terminal byte mapping workstream proceeds under the accepted [`key-to-terminal-byte-mapping.md`](../design/key-to-terminal-byte-mapping.md) design — a closed, digest-bound `termverify.key-encoding/v1` registry with fail-closed unencodable chords and delivery-only claims. The owner accepted slice 1 (registry + ConPTY dispatch integration, issue #141, PR #142) on 2026-07-19: the adapter now executes encodable `KeyInput` chords through the registry and fails closed on unencodable ones before any child write. The owner accepted slice 2 (real-child Windows-matrix evidence, issue #143, PR #144, adversarial review ACCEPT after fixes) on 2026-07-19: a raw-mode fixture subject observes the registry bytes byte-identically per encodable family class with replay identity, and the unencodable path stays fail-closed on the real adapter — the workstream is complete. Key-support negotiation remains separate unsupported work. |
| Deterministic vocabulary and configuration semantics | Closed, versioned terminal-capability registry with observable semantics and enforcement evidence | Non-empty terminal-capability receipts remain rejected; requested/effective equality is not enforcement proof. Owner decision 2026-07-19: deferred until a real subject demonstrates a capability need; the criterion stays transferred intact. |
| Concurrent event correlation | Explicit correlation and ordering for concurrent inputs or unsolicited/asynchronous events | V1 remains single-flight; idle unsolicited body records remain invalid; no wall-clock quiet period is evidence of causality or quiescence. Owner decision 2026-07-19: deferred until a demonstrated application requires concurrent or unsolicited work, per this workstream's own gate; the criterion stays transferred intact. |
| Production containment | Filesystem root mapping and lifecycle, traversal, symlink/reparse-point handling, child-process inheritance/containment, cleanup, and failure semantics | Owner decision 2026-07-18 (cooperation-tier design): OS containment is retired to an explicit non-goal — traversal, symlink/reparse, and child-process containment leave this boundary with it. Replacement scope is delivery-tier sandbox-root mapping with truthful `delivered` receipts; root mapping, existence validation, and host-owned lifecycle remain in scope there. Reopening containment requires a new owner-accepted design. |
| Production containment | Network allow-list DNS, address normalization, redirects, proxies, loopback, subprocess inheritance, and failure semantics | Owner decision 2026-07-18 (cooperation-tier design): OS-level network enforcement is retired to the same explicit non-goal. Replacement scope is deny-mode delivery with truthful `delivered` receipts; allow-list requests remain rejected fail-closed, and allow-list semantics (DNS, redirects, proxies, loopback) remain undefined and out of scope. |
| Distribution and release governance | Installed schema access API and exact wheel/sdist resource contract | Implemented: the canonical schema is a packaged resource with public byte/object accessors, and isolated wheel and sdist installation checks verify byte identity with the committed copy. Canonical `$id` publication is implemented; see the next row. |
| Distribution and release governance | Resolvable canonical schema publication for the documented `$id` | Owner-accepted design 2026-07-19 (`docs/agent/design/canonical-schema-publication.md`): the `$id` keeps its exact value on the owner-controlled `termverify.dev`, published via GitHub Pages with machine-enforced byte identity to the committed resource, with documentation served from the same origin. Slice 1 is implemented (issue #133, PR #134, merged 2026-07-19): the `$id` resolves via the `Pages` workflow's mirror of `main`, and the deploy run on the merged commit produced the live byte-identity evidence (verify job green; independent local fetch byte-identical, `application/json`). The `$id` stays identifier-first, runtime validation remains authoritative, and no required gate depends on the site. Slice 2 is implemented (issue #136, PR #137, merged 2026-07-19): the curated documentation site (MkDocs + Material, locked `docs` group) serves at the same origin with `README.md` as the landing page plus the knowledge and developer-guide trees, `docs/agent/` excluded (live 404), the reserved `/schemas/` prefix guarded fail-closed, and the deploy on the merged commit kept the schema URL byte-identical (verify job green; independent fetches confirm landing, knowledge, and developer-guide pages render). The design's authorized scope is complete. |
| Distribution and release governance | Release checklist, changelog/compatibility policy, security-disclosure process, and build/release provenance | Implemented as governance: reviewed checklist, changelog with pre-1.0 policy, private-disclosure process, and a tag-triggered attested draft-artifact workflow. No release is authorized, no index publishing exists, and the package remains pre-alpha. |
| Distribution and release governance | Reviewed behavior-based coverage-ratchet activation | Implemented: the committed `fail_under` floor is the integer floor of the reviewed observed total (94.43% at activation), raises require sustained durable coverage, and lowering requires explicit owner review. |
| Production terminal adapter | Direct native pseudoconsole ownership/close, native EOF and final-frame draining, process-tree teardown, cancellation/recovery, and truthful OS-level enforcement evidence | The accepted dependency decision (`docs/agent/design/terminal-adapter-dependency-decision.md`) authorizes reviewed implementation slices with pinned `pywinpty`/ConPTY behind its verification plan. Binding slices 2–4 landed durable Windows-matrix evidence for native ownership/close, EOF/final-frame drain, job-object process-tree teardown, and binding-level cancellation/recovery with hostile-child fixtures (plan items 2–4 and the binding half of item 5). Adapter slices 1–4 landed the fail-closed normalizer, truthful negotiation, epoch machinery, and real-path Windows integration evidence for items 5–8: classification, dimensions receipts through a real resize epoch, verbatim OSC readiness-marker passthrough, and replayable evidence normalization. The adapter enforces only the terminal constraint; the six non-terminal constraints remain truthfully not enforced at this boundary, and their enforcement claims stay with their own workstreams (the two production-containment rows were retired to an explicit non-goal on 2026-07-18; the rest remain transferred). |

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

On 2026-07-19 the owner resolved this gate's three open decisions in one
session: named-timezone enforcement and the terminal-capability registry are
deferred until demonstrated need (both criteria stay transferred intact —
deferral is not retirement and reopening needs only a new owner decision),
and the key-to-terminal byte mapping workstream proceeds under the accepted
[`key-to-terminal-byte-mapping.md`](../design/key-to-terminal-byte-mapping.md)
design. That design defines the closed, digest-bound
`termverify.key-encoding/v1` registry (fixed xterm-compatible normal-mode
byte forms, committed data and arithmetic, never derived from terminfo,
toolkit enums, or virtual-key codes), a fail-closed unencodable set with
recorded rationale, delivery-only honesty (no claim of subject decoding, no
input-mode tracking, no key-support negotiation), an unchanged transcript
protocol, and two authorized slices: the registry plus ConPTY dispatch
integration, then real-child Windows-matrix evidence.

The owner accepted slice 1 on 2026-07-19 (issue #141, PR #142, adversarial
review ACCEPT): `src/termverify/_key_encoding_v1.py` implements the
registry as committed data plus committed arithmetic, its full 934-chord
enumeration is digest-bound in `tests/test_key_encoding_v1.py` (SHA-256
`5df2113c9479ef68035ef74994d4502344a204a5f0b034633278e336137fcf3d`, 450
encodable chords, the four disclosed legacy byte collisions proven to be
the only ones), and `ConptyAdapter.dispatch` executes encodable `KeyInput`
chords by writing the registry bytes exactly once through the single-flight
child write and running the standard quiescent epoch, while an unencodable
chord is a structured runtime failure (`{"unsupported": "key-encoding",
"keys": [...]}`) before any child write. The registry, digest, fail-closed
rationale, and signal-byte disclosure are documented in `protocol.md` and
the ConPTY developer guide.

The owner accepted slice 2 on 2026-07-19 (issue #143, PR #144, adversarial
review ACCEPT after one must-fix — an honest-review-status correction to
this document — and one assertion-tightening should-fix), completing the
workstream: `tests/test_conpty_integration.py` carries the durable
Windows-matrix evidence — a cooperative raw-mode fixture subject (processed
input, line input, and echo cleared; virtual-terminal input set) observes
the exact registry bytes byte-identically for one representative chord per
encodable family class, including the disclosed signal byte 0x03
(`Control+c`) arriving as input under raw mode, echoes them into frames
with replay identity over the retained raw chunks, ends via native
end-of-stream through an in-band quit chord, and the unencodable path
stays fail-closed on the real adapter with OS-observed teardown. Both
authorized slices of the key-to-terminal byte mapping design are now
accepted; further key-input work (an extended encoding version, POSIX,
key-support negotiation) requires a new owner decision.

### 2. Concurrent event correlation

Introduce explicit versioned correlation only when a demonstrated application
requires concurrent or unsolicited work. Preserve transcript-position causality
and single-flight v1 rather than weakening it retroactively. This workstream does
not authorize replay/comparison. Owner decision 2026-07-19: explicitly deferred
until that demonstrated need exists; the criterion stays transferred intact.

### 3. Production containment

Specify and prove filesystem and network policy at the relevant direct or OS
boundary. Requested policy remains distinct from receipts and observations of
what was actually enforced. Fail unsupported rather than falling back to ambient
filesystem, DNS, proxy, loopback, or subprocess behavior.

The owner decided on 2026-07-18 (recorded in the accepted
[`cooperation-tier-constraint-ports.md`](../design/cooperation-tier-constraint-ports.md),
PR #124) that OS containment is retired to an explicit
non-goal: termverify verifies autonomous terminal applications whose authors
control the subject and is not an execution sandbox for untrusted code.
The same decision authorizes replacement scope at an honestly weaker tier:
all six non-terminal constraints become satisfiable through opt-in
cooperation ports whose receipts carry a mandatory enforcement-tier
disclosure (`termverify.enforcement-tier/v1`) and record the exact delivered
environment, while shipped defaults stay fail-closed and unchanged. Nothing
in that scope may claim containment, quiescence, or subject compliance; a
future owner-accepted design is required to reopen OS enforcement.

Cooperation-tier implementation slice 1 landed on 2026-07-18 (issue #125),
the enforcement-tier protocol amendment under the recorded pre-release rule
(transcript protocol stays v1): the closed `termverify.enforcement-tier/v1`
vocabulary (`os`, `constructive`, `delivered`; exact case-sensitive
membership, runtime validation authoritative, post-freeze changes require a
new vocabulary version); a mandatory `tier` on all seven enforcement
receipts with fail-closed delivered⇔`delivery` pairing (delivery records the
exact delivered environment variables, and for filesystem the working
directory, which no other constraint may name); the tier authorization
matrix validated fail-closed during receipt binding in shared negotiation —
the ConPTY adapter's own terminal negotiation states `os` and nothing else,
ports injected into the ConPTY adapter may state only `delivered`, ports
negotiated by the direct adapter may state only `constructive`, and an
unauthorized tier is a contract breach rejected as structured `StartFailed`,
never `StartUnsupported`; transcript `capability.result` validation, safe
evidence redaction (delivery values and cwd are redacted with
shape-preserving markers), and the committed fixtures amended in the same
change. Making `tier` mandatory is a deliberate source-level breaking change
for every external `ConstraintPorts`/`DirectApplication` implementer,
recorded in `CHANGELOG.md`. No cooperation port exists at the end of this
slice; nothing shipped can emit `delivered`, and shipped defaults still fail
closed unchanged.

Cooperation-tier implementation slice 2 landed on 2026-07-18 (issue #127):
the opt-in `termverify.cooperation` module with all six delivered-tier ports
under the accepted per-constraint contracts — `TERMVERIFY_SEED`,
`TERMVERIFY_CLOCK_INITIAL_MS` (initial manual time only),
`TERMVERIFY_LOCALE` (no `LANG`/`LC_ALL` delivery), `TZ=UTC0` plus
`TERMVERIFY_TIMEZONE=UTC` (UTC-only; non-UTC requests unsupported),
`TERMVERIFY_FS_ROOT` plus working directory from an explicit
`root_id -> host directory` mapping resolved through an injectable directory
probe (default: the real filesystem, the ports' single disclosed ambient
touchpoint; host-owned lifecycle), and `TERMVERIFY_NETWORK=deny` (deny-only;
allow-list stays rejected). `enforce_terminal` stays truthfully
`constraint-not-enforced`. `ConptyBindingPort.spawn` and the native binding
gained `env_overlay`/`cwd` with overlay composition in the binding (the
reviewed ratchet exclusion) and durable Windows-matrix evidence: the child
observes delivered variables, overlay-over-ambient precedence, ambient
inheritance underneath, and the delivered working directory. The ConPTY
adapter spawns evidence-driven — the overlay is assembled from the validated
receipts' delivery records with fail-closed disjointness and
single-working-directory invariants (violations are structured `StartFailed`
after negotiation). The carried slice-1 nit is closed: `DeliveryRecord` and
transcript delivery validation reject `=`/NUL in names and NUL in values and
cwd. Shipped defaults are unchanged and everything except the native binding
is cross-platform, fake-driven, and ratcheted. The sandbox disclosures are
recorded in `docs/developer-guide/conpty-adapter.md`. No end-to-end
successful real start is claimed; that evidence is slice 3.

Cooperation-tier implementation slice 3 landed on 2026-07-19 (issue #129),
completing the slices authorized by the cooperation-tier design: the
project's first fully successful verified terminal run, as durable
Windows-matrix integration evidence on the real path — cooperation ports
with a host-owned sandbox directory, default `ConptyBinding`, native child,
real `VtScreenNormalizer`. The successful start's receipts carry the
`delivered` tier with the exact delivery records (the terminal receipt
states `os` with no delivery), and a cooperating fixture subject reads
every delivered variable and its own working directory and echoes them into
frames — the delivery observable end to end, with no claim that the subject
honored anything beyond what the frames show. The run continues through a
text epoch, ends in native end-of-stream with the observed exit record, and
the retained raw `terminal.output` chunks replay to the recorded frames and
cursors. Forced stop and the deadline abort were re-exercised under the
cooperation ports with OS-observed teardown, and an unresolvable sandbox
root ends the start honestly as `StartUnsupported(filesystem)` before any
child exists.

Reassessment at slice-3 completion (the design names this the natural
point): the production-containment workstream's replacement scope is now
fully implemented and evidenced; its two retired rows stay retired
non-goals. Still transferred and unresolved at that reassessment, all blocked on
owner decisions: canonical schema `$id` publication, named-timezone
enforcement, the terminal-capability registry, concurrent event
correlation, and key-to-terminal byte mapping. Every one of those
decisions has since been taken on 2026-07-19: publication is implemented
(gate 4), key-to-terminal byte mapping proceeds under its accepted design
(gate 1), and the other three are deferred until demonstrated need
(gates 1 and 2). No further implementation slices are authorized by the
cooperation-tier design.

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

The owner accepted the canonical-publication design on 2026-07-19 (issue
#131):
[`canonical-schema-publication.md`](../design/canonical-schema-publication.md)
keeps the documented `$id` exactly as committed on the owner-controlled
`termverify.dev`, rejects GitHub URLs as canonical identifiers, and defines
the publication contract: GitHub Pages deployed from `main` by workflow,
`/schemas/<protocol>/<version>.schema.json` layout with the `/schemas/`
prefix reserved, byte identity with the committed resource enforced by a
post-deploy fetch check, human-facing documentation (MkDocs + Material,
CI-only) at the same origin, and `docs/agent/` excluded from the site. The
design authorizes two implementation slices — schema publication, then the
documentation site — gated on owner-manual IONOS DNS records, GitHub domain
verification, and Pages enablement. Accepting the design publishes nothing:
until slice 1's live byte-identity evidence lands, the `$id` remains an
identifier only, runtime validation remains authoritative, and no required
build/test path may depend on the site being reachable.

The owner accepted implementation slice 1 on 2026-07-19 (issue #133, PR
#134), after completing the owner-manual prerequisites (IONOS DNS records,
GitHub domain verification, Pages enablement with the Actions build source,
HTTPS enforcement). The `Pages` workflow now mirrors every committed
resource under `src/termverify/schemas/` to
`https://termverify.dev/schemas/<protocol>/<version>.schema.json` plus a
minimal landing page, deployed from `main` only, with a post-deploy check
that retries transient errors and stale bytes and fails the workflow on any
byte difference with the committed resource. The site builder and checker
are test-covered without network access; the deploy workflow is not part of
the required validation gate. The first deploy on the merged commit
produced the acceptance evidence: the verify job passed and an independent
fetch returned the schema byte-identical as `application/json`. The
`protocol.md` publication caveat was updated only with that evidence, per
the design.

The owner accepted implementation slice 2 on 2026-07-19 (issue #136, PR
#137), completing the design's authorized scope. The curated documentation
site serves from the same origin: `README.md` renders as the landing page
(its stale project-status paragraph was refreshed in the same change under
the same-change staleness rule) together with the `docs/knowledge/` and
`docs/developer-guide/` trees, built with MkDocs + Material from a locked
`docs` dependency group. Staging is curated and fail-closed: `docs/agent/`
is never staged (live requests 404), relative links to unpublished
repository files are rewritten to GitHub URLs, the MkDocs build runs
strict so a broken link fails the deploy, and docs output under the
reserved `/schemas/` prefix aborts the build. The required gate does not
depend on the docs tooling: the real-build tests skip when the `docs`
group is absent, and the Pages build job installs only that group. The
deploy on the merged commit is the acceptance evidence: landing,
knowledge, and developer-guide pages render live, and the verify job plus
an independent fetch confirmed the schema URL still serves bytes
identical to the committed resource.

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

The owner accepted adapter slice 2 on 2026-07-18 (issue #117, adversarially
reviewed): `termverify.conpty` with the `ConptyBindingPort`/`ConptyChildPort`
protocols (shaped exactly like `ConptyChild` plus an explicit
`is_supported()` probe implemented alongside `spawn` in
`termverify._conpty`), the default native-delegating binding, and
`ConptyAdapter` with truthful negotiation: the adapter owns only the
terminal constraint — non-empty capability requests and unsupported hosts
fail closed as `StartUnsupported(terminal)` before any spawn — and the
shipped `UnenforcedConstraintPorts` report the six non-terminal constraints
not enforced, so `start()` with defaults ends as `StartUnsupported(seed)`
before any child exists. The receipt-validating negotiation loop was
extracted unchanged from the direct adapter into shared
`termverify._negotiation`. A fully negotiated start fails closed with a
structured `StartFailed` disclosing the unimplemented epoch machinery; no
child is ever spawned, no successful start exists, and everything is
cross-platform, fake-driven, and fully ratcheted. Epoch machinery, marker
protocol, stop semantics, and Windows integration evidence remain slices 3
and 4, fail-closed until they land.

The owner accepted adapter slice 3 on 2026-07-18 (issue #119, adversarially
reviewed): the `ConptyAdapter` epoch machinery, entirely fake-driven and
fully ratcheted. Readiness is defined solely by a configurable exact marker
scanned in stream order (split chunks handled); the private-OSC default
remains **provisional** with no ConPTY passthrough claim — that evidence is
slice 4, and configurability is the mitigation. Raw chunks are fed to the
injected normalizer unmodified and retained as ordered `terminal.output`
events; observations carry the effective dimensions and the normalizer
snapshot at the epoch's manual time, with frame/dimension agreement enforced
fail-closed. The classification matrix is implemented as designed:
end-of-stream yields the observed native exit record (a missing or invalid
record is a structured failure, never fabricated); spawn, normalizer,
native, unexpected-close, and concurrent-I/O outcomes are structured
failures; every terminal result force-closes the binding with close
failures disclosed. The mandatory explicit abort deadline is armed via an
injectable watchdog before each blocking read and can only produce a
structured failure disclosing the policy; adversarial review forced
deadline attribution to be epoch-scoped, so an expiry aborts exactly the
epoch that armed it — even when a marker was still read — and only the
genuine aftermath of a deadline-driven close is ever attributed to the
deadline. Forced stop records the observed exit with a forced-termination
disclosure diagnostic bounding evidence at the last marker; `KeyInput`
uses the structured runtime-failure path. Disclosed follow-up for slice 4:
the watchdog wraps only reads per the accepted design; binding evidence
(issue #110) showed no conin write backpressure on the verified matrix,
and whether writes also need deadline protection is a slice-4
consideration. Windows integration evidence — real ConPTY path, marker
passthrough, cooperative fixture child, end-to-end dimensions observation —
remains slice 4 and fail-closed.

The owner accepted adapter slice 4 on 2026-07-18 (issue #121,
adversarially reviewed): Windows integration evidence on the real path —
default `ConptyBinding`, native `ConptyChild`, real `VtScreenNormalizer` —
on the full Windows CI matrix. The disclosed OSC assumption is resolved
with evidence: ConPTY relays the private `OSC 7791;ready ST` default
verbatim through the raw output stream, so the marker default is no longer
provisional and no printable-default amendment was needed; a
host-configured printable marker retains its own frame-visibility and
replay evidence. Real output exposed the v1 VT subset gap exactly as the
fail-closed design intended: ConPTY opens every session with `CSI 1 t`,
`CSI c`, `CSI ?1004h`, and `CSI ?9001h`, and the subset was amended
pre-release (no released artifact or recorded transcript carries the prior
semantics; version stays 1) to consume these four non-grid-affecting
sequences, everything else remaining fail-closed. A cooperative fixture
subject implements the design's cooperation contract, including detecting
a resize itself — a resize delivers no stdin bytes to a Windows console
client, so marker-after-resize cooperation is the subject's obligation, now
recorded in the design. End-to-end evidence: start-to-readiness with
cursor/frame evidence, a text epoch, a resize epoch whose child-observed
dimensions appear in the frame while the observation carries the new
effective dimensions, subject exit via native end-of-stream with the
observed exit record, forced stop with the forced-termination disclosure
and OS-observed teardown, and a deadline abort against a hanging subject
producing the structured failure disclosing the policy with the child tree
OS-observed dead. Replaying the normalizer over the retained raw
`terminal.output` chunks reproduces every frame and cursor — the design's
replay rule, executed against real ConPTY output. The disclosed write
follow-up is decided and recorded in the design: the watchdog wraps reads
only, because conin writes showed no backpressure, the bounded write-flood
test fails loudly on regression, and `cancel_io` cannot cancel conin
writes; new blocking-write evidence would reopen the decision. Adversarial
review surfaced a previously undisclosed platform behavior, now measured
and recorded as the design's DA-stall disclosure: conhost defers client
output while its unanswered `CSI c` device-attributes query waits
(~3.1 s constant on the verified machine, ~0.05 s with a DA1 response),
so every real start pays that wall-clock floor and a configured abort
deadline at or below it fails every real start by policy; the adapter
deliberately does not answer the query because a synthetic, unrecorded
conin response would undermine replayability — removing the stall is
possible future work behind a design amendment. Non-terminal
constraint enforcement, the capability registry, containment claims, and a
POSIX adapter remain outside this slice and fail-closed.

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
  decision remains mandatory — satisfied 2026-07-19 by the accepted
  [Phase 2 verification-core boundary decision](../design/phase-2-verification-core-boundary.md)
  (issue #146); Phase 2 authority flows from that decision alone, and any
  scope beyond it still requires a new owner decision.

## Transition rules

- This handover is **active** effective when the reviewed transition resolving
  issue #87 marks the predecessor `superseded`, archives it, and updates the
  index in the same merge.
- Mark **blocked** only when all safe work depends on an unresolved owner decision,
  unavailable independent review, or external enforcement evidence.
- Mark **complete** only when every transferred criterion is implemented and the
  integrated boundary passes its required review, when another named successor
  accepts every unresolved criterion intact, or — for criteria retired to an
  explicit non-goal by a recorded, reviewed owner decision (amendment
  2026-07-18) — when the retirement is recorded in the criterion's row and its
  design document; a retired criterion imposes no implementation obligation but
  its non-goal must not be silently reversed.
- Activation or completion of this handover does not activate Phase 2.
