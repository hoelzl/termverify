# Phase 1 Readiness Hardening Handover

## Handover metadata

- **Status:** active — the maintainer accepted the complete scope disposition on
  2026-07-17. Deterministic transcript resource governance remains the final
  Phase 1 implementation class; the amended fixture/schema/workflow completion
  definition and the draft successor boundary below must then pass integrated
  review. Phase 2 is not active.
- **Owner:** project maintainer
- **Created:** 2026-07-15
- **Updated:** 2026-07-17
- **Review required:** yes — accepted protocol compatibility,
  deterministic-enforcement, evidence-security, schema-authority, and
  baseline-governance decisions require executable implementation and
  independent human-readable review.
- **Predecessor:**
  [Quality hardening handover](archive/quality-hardening-handover.md)
- **Successor:** draft
  [Pre-release boundary hardening handover](pre-release-boundary-hardening-handover.md),
  which becomes active only in the later reviewed supersession/archive
  transition.
- **Completion boundary:** implement and independently review deterministic
  transcript byte, line, record-count, nesting, and structured-value limits;
  verify behavior-based executable coverage for every supported path under the
  amended fixture definition; preserve the deliberately non-exhaustive schema
  and existing pinned workflow-security boundary; pass the integrated gate; and
  transfer every disposition-3 criterion intact by activating the named
  successor. That transfer makes this handover `superseded`, not `complete`.

## Purpose and boundaries

This handover transfers the July 2026 adversarial foundation review into a
bounded prerequisite initiative. TermVerify's conceptual architecture remains
sound. Since that review, the public immutable adapter contracts and deterministic
direct execution slice have landed, but transcript/evidence completion criteria
and stable-publication claims remain gated below. Phase 1 now continues only
through the accepted transcript-resource slice and the integrated supersession
gate recorded below. The named successor remains draft until that boundary
passes.

**Current in scope:**

- implement deterministic, fail-closed transcript byte, line-byte, record-count,
  nesting, and structured-value limits with parser/serializer symmetry;
- verify the amended behavior-based fixture matrix, non-exhaustive schema role,
  and retained pinned workflow-security boundary against the integrated result;
- activate the named successor and supersede/archive this handover only after
  those gates and an exact-candidate independent review pass.

**Transferred or otherwise out of current implementation scope:**

- named-timezone, key-name, terminal-capability, concurrent-event, filesystem,
  network, production-terminal, schema-distribution, release, disclosure,
  provenance, and coverage-ratchet criteria listed in the accepted table below;
- transcript replay/comparison, application fixtures, or browser bridging;
- sensitive evidence retention, artifact publication, or behavioral baselines;
- exhaustive schema expansion or an additional workflow checker without a
  separate accepted workstream;
- automatic baseline approval or automatic acceptance of changed behavior;
- broad refactoring unrelated to the remaining resource boundary.

This document is not an issue tracker. Create one focused GitHub issue and one
independently reviewable pull request for each coherent workstream or accepted
decision. Keep volatile progress in GitHub and Git.

## Original verified state and reconciliation history

The snapshots in this section are historical review evidence. The closure audit
and accepted 2026-07-17 disposition below govern the current boundary.

The review used clean `main` at `33a661e` and three independent adversarial
review contexts. No tracked repository files were modified by the review.

- The complete documented local gate passed on Windows/Python 3.12.9: locked uv
  synchronization, 47 tests with branch coverage, Ruff check and format, strict
  mypy, both pre-commit stages, wheel/sdist build, and `git diff --check`.
- Coverage was 76% overall; `src/termverify/transcript.py` was 76% covered and
  retained 55 partially covered branches.
- CI and Security workflows for `33a661e` completed successfully.
- Local Markdown link targets were valid.
- The committed fixture corpus contains one valid transcript and one invalid
  wrong-protocol transcript.
- The built wheel contains the Python modules and `py.typed`, but not the
  committed transcript schema.
- The schema `$id` host did not resolve from the review environment.
- Four clean external worktrees exist for adapter contracts, ConPTY research,
  documentation reconciliation, and fixture expansion. Adapter-contract work
  must remain blocked until its entry gates below pass.
- At review time GitHub had no open Phase 1 issue or pull request and the
  handover index had no active handover.
- `actionlint` was not available locally. GitHub's pinned workflow-security and
  dependency-vulnerability jobs passed and remain the current remote evidence.

### Reconciliation through merged PR #39

The confirmed-finding lists below preserve the original review baseline. An
intermediate reconciliation after PRs #12, #13, and #15 on clean `main` at
`b20993d` found 145 passing tests and no open issues before the next focused
prerequisite was filed:

- PR #12 made parsing and serialization share envelope/lifecycle validation,
  enforced the accepted inception-v1 and baseline-review decisions, and aligned
  the immediate quality, package-version, support, and status controls.
- PR #13 established `persist_transcript_evidence()` as the fail-closed safe
  transcript persistence boundary and recursively governed committed transcript
  fixtures. Sensitive retention, baselines, reports, and artifact upload remain
  disabled rather than implicitly enabled.
- PR #15 bound `run.started` to the versioned replay subject, closed deterministic
  configuration selectors, and made the deliberately non-exhaustive
  `run.started` schema slice executable. It did not approve exhaustive per-kind
  schema coverage.
- PR #17 closed every defined runtime payload and nested generic protocol object
  to its declared members plus `x-` extensions, completing issue #16 without
  expanding the deliberately non-exhaustive schema.
- PR #19 made diagnostic and observation timestamps agree with the manual clock
  current at each record's position, completing issue #18 without adding
  readiness, causality, or asynchronous-drain semantics.
- PR #21 made every exited-process observation agree semantically with the final
  `run.finished` exit kind and value, completing issue #20. Uninterpreted `x-`
  extensions do not participate, and the relationship to `run.failed` and
  `run.unsupported` remains later decision work.
- PR #23 completed issue #22 by requiring literal, case-sensitive `C` or RFC
  5646 well-formed locale syntax through the shared parser/serializer semantic
  validator. The codec preserves caller spelling and case and performs no
  registry lookup, canonicalization, or preferred-value rewriting. Locale
  enforcement and attestation remain future adapter-contract work; syntax
  conformance does not prove that a requested locale was applied.
- A fresh probe after PR #23 reconfirmed that `not/a real timezone`, `../UTC`,
  and `Mars/Olympus` are accepted by both parser and serializer. The prose says
  IANA identifier or `UTC`, but does not yet choose a named/versioned tzdb,
  canonical-versus-alias policy, compatibility/update semantics, or another
  deterministic membership mechanism. No timezone implementation issue should
  invent those decisions or depend on ambient `zoneinfo` data.
- PR #25 completed issue #24 by enforcing action-dependent `input.mouse` member
  presence and absence through the shared parser/serializer semantic validator,
  including explicit JSON `null` values, while preserving uninterpreted `x-`
  extensions.
- PR #27 completed issue #26 by establishing string type before set membership
  for capability status, mouse action, and required mouse button values. Both
  transcript APIs now reject malformed array and object values with
  `TranscriptValidationError` while preserving valid enum-like values and
  action-dependent mouse-member rules.
- PR #29 completed issue #28 by enforcing presence of all four required
  `observation.ui` members through the shared validator. Missing `focus` now
  raises `TranscriptValidationError` instead of raw `KeyError`, missing `mode`
  is no longer accepted, and explicitly present nullable values plus
  uninterpreted `x-` extensions remain valid.
- PR #31 completed issue #30 by rejecting CRLF, mixed CRLF/LF, and bare-CR
  record separators before `bytes.splitlines()` can remove them. Canonical LF
  fixtures and serializer output remain byte-for-byte unchanged, and escaped
  carriage returns inside canonical JSON strings remain valid.
- PR #33 completed issue #32 by validating canonical decimal seed strings
  lexically against the unsigned-64-bit maximum instead of converting
  arbitrary input with `int()`. Both APIs now reject oversized and max-plus-one
  seeds cleanly while preserving zero, the valid maximum, and the existing
  leading-zero and ASCII-decimal rules.
- PR #35 completed issue #34 by normalizing JSON-decoder `ValueError` at the
  parser boundary while explicitly preserving the duplicate-member diagnostic.
  Oversized integer tokens now fail cleanly in envelope, state, and extension
  positions without changing ordinary malformed, non-finite, or noncanonical
  number behavior.
- PR #37 completed issue #36 by normalizing dependency `ValueError` at the
  serializer's RFC 8785 boundary. Programmatically constructed 5,000-digit
  Python integers now fail cleanly in state and extension positions while safe
  boundaries, ordinary range errors, parser behavior, and interpreter settings
  remain unchanged.
- PR #39 completed issue #38 by rejecting Python tuples recursively before the
  installed RFC 8785 implementation can silently canonicalize them as JSON
  arrays. Valid list-valued arrays retain semantic serialize/parse identity,
  while tuple values in application state and `x-` extensions fail through the
  transcript validation boundary.
- A fresh bounded audit of clean merged `main` after PR #39 found no further
  small protocol/runtime discrepancy that was clearly ready for another
  opportunistic malformed-input issue. The complete local gate passed with 325
  tests, 88% overall coverage, and 90% coverage for
  `src/termverify/transcript.py`; the current-head CI and Security workflows
  also passed.
- The maintainer accepted the proposed defaults for the next design workstream:
  single-flight causal epochs, a positional initial readiness observation,
  deterministic port-reported quiescence without wall-clock quiet windows, no
  unsolicited direct-adapter events in the first slice, constraint-specific
  enforcement receipts, drain-aware stop semantics, and protocol-owned key and
  terminal-capability vocabularies. At that reconciliation point these defaults
  still required a durable contract. PRs #43–#51 subsequently implemented the
  execution, immutable-value, receipt, and direct-runtime slices; the key and
  terminal-capability registries now transfer to the draft successor.

The adapter-contract entry gate remains closed after PR #39. Remaining gates
include the execution-epoch, readiness, quiescence, draining, vocabulary, and
negotiation/attestation contract in Workstream 2; locale enforcement and
timezone conformance; fixture/property coverage; resource limits; and the
deliberately bounded schema package-access criteria in Workstreams 3 and 6.
Neither the completed focused hardening issues through #38 nor the merged
schema slice authorizes adapter/runtime implementation or exhaustive schema
work.

### Closure audit through merged PR #53

The 2026-07-16 closure audit used clean `main` at merge commit `9250e60` and
rechecked the handover's completion conditions against source, tests, built
artifacts, and the merged CI/security evidence. It does **not** mark Phase 1
complete.

The following intended Phase 1 slices are now executable and reviewed:

- PR #43 accepted the single-flight adapter execution contract; PR #45 made its
  readiness, epoch, quiescence, draining, and terminal lifecycle rules part of
  transcript validation and the model-based fixture suite.
- PRs #47 and #49 established and hardened immutable, framework-neutral adapter
  values and constraint-specific receipts. PR #51 implemented the deterministic
  direct adapter with fail-closed negotiation, explicit application ports, and
  bounded lifecycle outcomes.
- PR #53 recorded a **partial**, binding-level Windows ConPTY feasibility result.
  It demonstrated explicit ConPTY selection, synthetic input/output servicing,
  initial size, resize, wrapper-level close, and child-status observation. It did
  not prove direct `ClosePseudoConsole`, native EOF/final-frame draining,
  process-tree containment, or production terminal enforcement.
- The merged PR #53 candidate passed 477 tests, the declared Python 3.12-3.14
  Windows/Ubuntu matrix, package, documentation-contract, workflow-security, and
  dependency-vulnerability checks, and an exact-tree independent review.

The closure audit originally found the following open or conflicting criteria.
The maintainer resolved every scope conflict on 2026-07-17. Issue #85 completes
the remaining resource-governance implementation; the amended integrated gate
and exact-candidate review remain before this handover can be superseded:

- **Resource governance — implemented within Phase 1 by issue #85:** parsing and
  serialization now enforce symmetric fixed ceilings of 32 MiB per transcript,
  4 MiB per canonical line, 10,000 records, 64 open containers, 16,384 immediate
  collection items, 100,000 value nodes per record, 1 MiB per decoded string or
  key, and 2 MiB aggregate decoded string/key bytes per record. Parser admission
  checks bytes, lines, records, and lexical nesting before decoding; iterative
  structured-value checks precede serializer canonicalization.
- **Fixture breadth — completion definition amended:** the committed corpus does
  not literally enumerate every terminal outcome, input kind, framing case, and
  compatibility case. Completion now requires reviewed behavior-based executable
  coverage of every supported path. Evidence may combine canonical fixtures,
  focused tests, and generated properties; exact fixtures remain required where
  canonical bytes or compatibility identity are the behavior under review.
- **Schema access — transferred intact:** the built wheel contains no schema
  resource, and `termverify.dev` did not resolve from the audit environment. The
  installed access and canonical publication contract moves to the named
  successor before the first supported external artifact.
- **Release controls — transferred intact:** release/security/provenance guidance
  and the coverage-ratchet activation point move to the named successor rather
  than being treated as Phase 1 evidence.

Key and non-empty terminal-capability vocabularies, named-timezone policy,
network allow-list semantics, and production OS/PTY enforcement are accepted
transfers to the draft successor rather than claimed Phase 1 evidence. Current
direct execution avoids ambient enforcement guessing through explicit
application ports and exact receipt binding, but syntax-level selectors remain
semantically unapproved.

### Owner scope disposition accepted on 2026-07-17

The maintainer accepted the following row-by-row disposition. Each criterion has
exactly one outcome:

| Criterion | Disposition | Governing boundary |
| --- | --- | --- |
| Transcript total bytes, line bytes, record count, explicit nesting depth, and structured-value depth/collection/string/value size | **Complete within Phase 1** | Deterministic fail-closed limits must be symmetric across parse and serialize without changing wire shape, canonical bytes, JSON runtime categories, or recursive tuple rejection. |
| Literal complete fixture and compatibility corpus | **Remove through amended completion definition** | Require reviewed behavior-based executable coverage of every supported path; use canonical fixtures where exact bytes/compatibility identity matter and focused/generated tests elsewhere. |
| Exhaustive additional per-kind Draft 2020-12 schema coverage | **Remove through amended completion definition** | The schema remains a non-exhaustive structural/local aid. Runtime validation remains authoritative; schema/runtime agreement is required for encoded rules only. |
| Additional workflow syntax/policy checker | **Remove through amended completion definition** | Retain the existing pinned `zizmor` and OSV-Scanner controls; require another checker only after reviewed evidence of maintained, non-duplicative signal. |
| Named-timezone membership, tzdb version, alias, update, and compatibility policy | **Transfer intact** | Draft successor: deterministic vocabulary and configuration semantics. Named-zone receipts remain rejected except `UTC`. |
| Semantic key-name registry | **Transfer intact** | Draft successor: deterministic vocabulary and configuration semantics. `input.key` remains absent from the immutable/direct surface. |
| Semantic terminal-capability registry and enforcement evidence | **Transfer intact** | Draft successor: deterministic vocabulary and configuration semantics. Non-empty capability receipts remain rejected. |
| Concurrent or unsolicited-event correlation | **Transfer intact** | Draft successor: concurrent event correlation. V1 remains single-flight with no idle unsolicited body records. |
| Filesystem mapping/lifecycle/traversal/link/reparse/child/cleanup/failure semantics | **Transfer intact** | Draft successor: production containment. Direct application-port routing is not OS-containment proof; terminal/subprocess enforcement remains unsupported. |
| Network allow-list DNS/address/redirect/proxy/loopback/inheritance/failure semantics | **Transfer intact** | Draft successor: production containment. Direct receipts remain deny-only; terminal/subprocess enforcement remains unsupported. |
| Installed schema access and canonical `$id` publication | **Transfer intact** | Draft successor: distribution and release governance, required before the first supported external artifact. |
| Direct native pseudoconsole close, native EOF/final-frame drain, and process-tree teardown beyond PR #53 | **Transfer intact** | Draft successor: production terminal adapter. The spike remains partial binding-level evidence. |
| Release/changelog/compatibility, security disclosure, provenance, and coverage-ratchet controls | **Transfer intact** | Draft successor: distribution and release governance, required before the first supported external artifact. |

Workstream 4's fail-closed evidence and baseline boundary is complete for the
current disabled-retention/disabled-publication scope. Workstream 5 is reconciled
by this audit candidate but remains subject to its candidate-bound review.

Consequently this handover remains active only for the integrated amended-gate
review. The pre-release successor is draft, and no Phase 2 handover is created or
activated. Native ConPTY close/drain and production containment remain successor
work; they are not misclassified as completed Phase 1 evidence.

The remaining transition sequence is intentionally narrow:

1. verify the issue #85 deterministic resource-limit implementation together
   with the amended behavior-based fixture matrix, deliberately non-exhaustive
   schema boundary, and retained pinned workflow-security controls against the
   integrated candidate;
2. run the full completion gate and independently review the exact integrated
   Phase 1 boundary;
3. in a later reviewed transition, activate the named successor so it accepts
   every disposition-3 criterion intact, mark this handover `superseded`, move it
   to `archive/`, and update the index in the same change;
4. keep Phase 2 inactive unless a separate owner-reviewed phase-boundary decision
   explicitly activates it.

These are separate implementation/review slices. None may expand the transcript
wire shape, turn the standard schema into an exhaustive conformance oracle, or
activate sensitive artifacts or baselines implicitly.

### Original confirmed P0 defects

1. **Serializer/parser asymmetry.** `serialize_transcript()` does not invoke the
   envelope validator and can emit a wrong protocol, wrong sequence, missing
   required members, or unknown non-extension members that its own parser
   rejects (`src/termverify/transcript.py:76-81`, `:104-121`, `:135-150`).
2. **Invalid lifecycle acceptance.** The runtime checks only the first and last
   kinds. It accepts repeated `run.started`, intermediate terminal records,
   records after a terminal, and a fully enforced run ending with an empty
   `run.unsupported` (`src/termverify/transcript.py:153-169`, `:259-287`,
   `:316-340`).
3. **Evidence-policy bypass.** Raw transcript serialization can retain clipboard
   values and arbitrary restricted data. The redactor is key/regex based and the
   governance validator scans only `tests/fixtures/baselines/`, not transcript
   fixtures or general persistent evidence (`src/termverify/evidence.py:13-76`,
   `scripts/validate_evidence_governance.py:13-61`).
4. **Schema-authority mismatch.** The committed schema permits any non-empty
   `kind` and any object payload, while its only test checks metadata. Independent
   implementations can be schema-valid but runtime-invalid
   (`schemas/termverify.transcript/v1.schema.json:7-19`,
   `tests/test_transcript_schema.py:9-17`).

### Original confirmed P1 defects and oversights

- Identifier grammar and RFC 5646/`C` locale syntax are now enforced. The
  named-timezone vocabulary, alias, registry-version, and update policy remains
  unimplemented and transfers intact to the draft successor; direct receipts
  continue to reject named zones other than `UTC`.
- Required terminal capabilities can be omitted when the echoed effective value
  omits them too; nested configuration objects are not consistently closed.
- At the original review baseline, Python `bool` values could satisfy JSON
  integer/equality rules for `seq`, mouse scroll delta, and capability effective
  values; the current validator rejects those cases.
- Unknown non-`x-` members are rejected for input payloads but accepted in many
  other generic payloads and nested objects.
- Observation and diagnostic times need only be non-negative and may contradict
  current manual time. Process-exit observations may contradict the terminal
  run result.
- V1 says generic input members are closed while also calling future optional
  generic payload members additive. Existing strict readers cannot satisfy both
  rules (`docs/knowledge/protocol.md:140-145`, `:193-200`).
- Normalized key names and terminal capability names have no canonical registry.
- Transcripts do not bind application/build, argv, environment, adapter,
  normalizer, state-schema, or platform identity strongly enough for durable
  replay interpretation.
- Deterministic readiness, input/observation causality, asynchronous draining,
  and capability-enforcement attestation are underspecified.
- Filesystem `root_id` and network allow-list enforcement omit containment,
  cleanup, symlink/reparse-point, DNS, redirect, proxy, address-normalization,
  and subprocess-inheritance semantics.
- The former `write_sanitized_evidence()` helper could emit non-standard JSON
  `NaN`; camelCase sensitive keys, UNC/device paths, traversal-shaped relative
  paths, modern credential forms, and secrets in free text could bypass its
  redaction. It has been replaced by the fail-closed transcript persistence
  boundary described in `docs/knowledge/evidence-governance.md`.
- Baseline approval validates self-authored metadata, not an independent review;
  `https://` without a host passes the current URL check.
- The fixture corpus and schema tests are too small to substantiate the claimed
  executable compatibility contract. No generated lifecycle or
  serializer/parser closure property exists.
- Deeply nested invalid JSON can escape as `RecursionError`; transcript size,
  line length, nesting depth, record count, and structured-value depth are
  unbounded.
- Durable status documents still claim that schema/runtime work is pending,
  while archived handovers declare it complete.
- Ruff is split between pre-commit v0.11.13 and uv-locked v0.15.20. The archived
  handover describes pre-push security checks that the hook does not contain.
- Python metadata and README say `>=3.12`/`3.12+`, while continuously verified
  support is currently 3.12-3.14.
- Version `0.1.0` is duplicated across package metadata, runtime code, tests, and
  CI. No release checklist, changelog policy, provenance workflow, or security
  disclosure document exists yet.
- `NOTICE:15-16` still says the canonical Apache-2.0 license will be installed,
  although `LICENSE` is present.
- The documented coverage ratchet has not been activated. Its activation point
  must be defined after the contract validator receives meaningful adversarial
  coverage; a percentage alone must not replace behavior-based acceptance.

## Material decisions

### Resolved by existing accepted project policy

- **Semantic evidence remains primary:** state/events precede frame or raw ANSI
  evidence; this review does not change the evidence hierarchy.
- **Determinism remains enforced-or-unsupported:** adapters must not silently
  fall back to ambient state.
- **Human ownership of baselines remains mandatory:** agents may propose but
  never approve behavioral baselines.
- **Browser bridging remains deferred:** no finding justifies adding it before a
  terminal vertical slice.
- **Framework-neutral core remains mandatory:** fixes must not introduce a TUI,
  agent-harness, or model-provider dependency into the deterministic core.
- **Python support wording:** retain `requires-python = ">=3.12"` as the minimum
  installer requirement, but state separately that only 3.12-3.14 are currently
  supported and tested. Do not imply automatic support for future releases.
- **Quality-tool alignment:** use one uv-locked Ruff version as the authoritative
  local and CI implementation unless a later reviewed tooling decision states
  otherwise.

### Owner decisions accepted on 2026-07-15

The project maintainer accepted all eight dispositions below. Their narrow
direct-adapter and feasibility slices are reflected in prose and executable
tests; stable runtime publication and Phase 2 remain gated by the open completion
items recorded in the closure audit above.

1. **Correction policy for the existing v1 contract.** Decide whether confirmed
   defects and missing replay metadata may be corrected in place before the
   first supported external release, or whether any required wire-shape change
   must introduce `termverify.transcript/v2`.
   - **Accepted disposition, clarified for inception:** no real client or
     supported external artifact currently exists, so correct v1 in place even
     when a correction is wire-incompatible. Incrementing a version now would
     falsely imply that a supported v1 existed. Preserve canonical fixtures when
     they remain valid and migrate repository-owned inception fixtures when they
     do not. Freeze this policy when the first real client or supported external
     artifact is declared; incompatible changes after that boundary require a
     new protocol version.
2. **V1 extension/evolution rule.** Decide whether generic optional members may
   be added within v1.
   - **Accepted disposition:** v1 generic members are closed; after the inception
     policy in decision 1 freezes, only `x-` members are additive and any new
     generic semantic member requires a new protocol version. Until that freeze,
     an explicitly reviewed inception correction may revise v1 in place under
     decision 1; ordinary unreviewed additions remain prohibited.
3. **Normative schema and distribution contract.** Decide whether the JSON
   Schema is a complete normative per-record contract or only an envelope aid,
   and how installed/external consumers obtain it.
   - **Accepted disposition:** use standard Draft 2020-12 JSON Schema as a
     non-exhaustive structural and local-validation aid, with executable
     metaschema and instance tests. Schema acceptance is not conformance; Python
     runtime validation remains authoritative for complete protocol acceptance,
     including record kinds and local rules not yet encoded, canonical ordering,
     projected uniqueness, and cross-record semantics. Exhaustive per-kind
     schema coverage, a custom vocabulary/validator, and their distribution
     contract require a separate approved workstream. Package the standard
     schema, test wheel contents, and use a resolvable canonical `$id` before
     public release.
4. **Replay subject and normalizer identity.** Decide which application, build,
   invocation, adapter, platform, and normalizer metadata is required in-band.
   - **Accepted disposition:** require `termverify.replay-subject/v1` in
     `run.started`, with stable application/version/build, fixture/version,
     adapter/version, normalizer/version, and state-schema/version selectors.
     Permit only normalized OS/architecture as optional platform identity. Raw
     argv, environment, hostname, account, and paths remain outside the subject.
     Safe persistence preserves these closed structural selectors and redacts
     extensions and other evidence. Do not rely on undocumented out-of-band
     context or guess missing identity during migration.
5. **Evidence codec versus persistence boundary.** Decide whether canonical
   transcript serialization may remain a pure in-memory codec for restricted
   data, with a separate mandatory sanitized writer, or whether every public
   serializer must reject/redact restricted evidence.
   - **Accepted disposition:** keep a pure validated codec explicitly documented
     as non-persistent, expose one evidence-aware persistence API that classifies
     and sanitizes before bytes are written, and prohibit repository/artifact
     persistence through the raw codec. Update policy wording to distinguish
     encoding from persistence.
6. **Baseline independent-review enforcement.** Decide what happens while the
   repository has one maintainer and branch protection requires zero approvals.
   - **Accepted disposition:** this policy governs only baselines committed to
     the TermVerify repository, not downstream projects. Keep the unused
     `termverify.baseline-approval/v1` format at v1 and support explicit
     `independent` and `maintainer-self-review` modes. Independent review requires
     distinct proposer and reviewer identities. Single-maintainer self-review
     permits the same identity but requires a separate explicit human approval
     action, a digest-bound readable behavioral diff, successful required
     checks, and a durable pull-request or issue URL. Agents and automation may
     propose but never approve baselines; independent review remains preferred
     whenever another qualified human is reasonably available.
7. **Initial filesystem/network enforcement scope.** Decide which policies a
   Phase 1 direct adapter and terminal adapter may truthfully report as enforced.
   - **Accepted disposition:** direct adapters may enforce only through explicit
     application ports; terminal/subprocess adapters report unsupported until
     OS-level containment is proven. Narrow the first terminal slice to network
     deny; defer allow-list enforcement until DNS/address semantics are accepted.
8. **Phase 1 terminal scope.** Decide whether Phase 1 ends at the immutable
   configuration/direct-adapter contract or includes one minimal real terminal
   lifecycle slice.
   - **Accepted disposition:** Phase 1 includes contract hardening, immutable
     configuration, a fake/direct adapter, and one narrow create/drain/resize/
     stop terminal feasibility slice; production PTY behavior remains later.

## Historical workstreams and accepted disposition

The original workstreams below are retained for provenance. The accepted
2026-07-17 table above governs current execution: only Workstream 1's transcript
resource limits remain Phase 1 implementation work; transferred and amended
criteria must not be reopened here.

### 1. Restore transcript contract integrity

**Objective:** make every successfully serialized transcript a valid,
unambiguous v1 transcript accepted by the matching parser.

**Actions:**

1. Write focused red tests for serializer/envelope asymmetry and every illegal
   lifecycle transition before implementation.
2. Centralize strict record validation and invoke it from parse and serialize.
3. Implement an explicit lifecycle state machine:
   `started -> ordered capabilities -> body -> one terminal -> EOF`.
4. Validate every terminal payload independently, then validate its relationship
   to capability negotiation.
5. Introduce shared strict JSON predicates, especially integer-not-boolean,
   exact member sets plus `x-` extensions, identifier grammar, exit values, and
   constraint-specific effective-value shapes.
6. Enforce accepted locale, timezone, terminal, filesystem, network, input,
   diagnostic, observation, frame, process, and timestamp rules.
7. Convert malformed/deep input failures into documented validation errors and
   add reviewed resource limits.

**Dependencies:** owner decisions 1 and 2 before changes that alter accepted wire
shape; no dependency for confirmed parser/serializer and lifecycle bug fixes.

**Acceptance criteria:**

- successful serialization always reparses to the same semantic records;
- no start/capability/body record follows a terminal and exactly one terminal is
  present;
- malformed unsupported results and cross-record contradictions are rejected;
- every documented local shape rule has focused positive and negative coverage;
- property tests generate legal and illegal lifecycle sequences;
- protocol compatibility changes receive independent human-readable review.

### 2. Define deterministic adapter semantics

**Objective:** eliminate guessing from the future adapter boundary without
implementing the production adapter prematurely.

**Actions:**

1. Specify normalized key and terminal-capability vocabularies.
2. Define subject/normalizer identity, input-observation correlation, readiness,
   quiescence, asynchronous event ordering, and manual-time consistency.
3. Define what evidence permits an adapter to attest each capability as
   `enforced` and require negotiation to complete transactionally before input.
4. Specify filesystem root mapping/lifecycle, cleanup, traversal,
   symlink/reparse-point, child-process, and failure behavior.
5. Specify network deny/allow-list semantics for DNS, addresses, redirects,
   proxies, loopback, subprocesses, and unsupported enforcement.
6. Reconcile the direct-adapter and terminal-slice Phase 1 boundary.

**Dependencies:** owner decisions 4, 7, and 8; Workstream 1 compatibility rules.

**Acceptance criteria:**

- a new direct and terminal adapter implementation can report every constraint
  without guessing or silently degrading it;
- impossible enforcement claims have executable contract tests;
- public types are introduced only after an accepted API rationale and
  verification plan;
- future production adapters and Phase 2 replay work do not cross the remaining
  resource, distribution, or semantic decision gates.

### 3. Make schema and fixtures genuinely executable

**Objective:** evolve the non-exhaustive schema aid and fixtures toward a portable
conformance corpus without treating schema acceptance as protocol acceptance.

**Actions:**

1. Apply owner decision 3 to the schema title, documentation, and normative role.
2. Define and test each additional record-local kind/payload shape with
   `$defs`/`oneOf`; exhaustive per-kind coverage is work in this separate stream.
3. Validate the schema against its metaschema and run it over all applicable
   valid and invalid fixture records.
4. Expand canonical fixtures for all terminal outcomes, unsupported positions,
   input kinds, optional evidence, extensions, framing/canonicalization errors,
   duplicate members, and lifecycle permutations.
5. Add old-reader/new-producer compatibility fixtures based on owner decision 2.
6. Package the schema or explicitly document and test the selected distribution
   mechanism; verify wheel and sdist contents.

**Dependencies:** Workstream 1 and owner decisions 1-3. Fixture expansion must not
bless behavior still under repair.

**Acceptance criteria:**

- schema and runtime verdicts agree for every rule the schema encodes; schema
  acceptance alone does not imply runtime acceptance;
- cross-record invalid fixtures are rejected by the semantic validator;
- fixture bytes round-trip canonically;
- consumers can obtain the exact schema identified by the documentation;
- package-install smoke tests exercise transcript imports and schema access, not
  only `__version__`.

### 4. Complete evidence safety and baseline governance

**Objective:** ensure no persistent path can claim safe evidence while retaining
secret, restricted, malformed, or unapproved content.

**Actions:**

1. Apply owner decision 5 by introducing one mandatory evidence-aware persistence
   boundary and clearly separating or restricting any raw codec.
2. Classify by record kind and semantic field so clipboard `payload.text`, state,
   events, diagnostics, frames, process data, and extensions receive the correct
   treatment.
3. Normalize key matching, expand maintained credential recognition, handle UNC
   and device paths, and validate relative paths against a known sandbox root.
4. Reject non-finite JSON numbers and define failure behavior for unsupported
   values.
5. Extend governance validation to every designated persistent fixture,
   baseline, report, and artifact root; reject unclassified evidence.
6. Add every test promised by `docs/knowledge/evidence-governance.md:129-134`,
   including nested destinations and sensitive-retention boundary failure.
7. Tighten approval URL/identity validation and apply owner decision 6. Ensure
   the readable-diff record demonstrates the behavioral difference rather than
   carrying only arbitrary explanatory prose.
8. Keep CI artifact publication and behavioral baselines disabled until this
   workstream is accepted.

**Dependencies:** owner decisions 5 and 6. Redactor and invalid-JSON fixes may
start independently.

**Acceptance criteria:**

- adversarial clipboard, camelCase secret, modern token, free-text credential,
  nested extension, UNC/device/traversal path, and non-finite-number cases cannot
  reach a safe persistent artifact;
- direct raw-codec persistence is prevented by API boundary and documented
  policy, or explicitly rejected by the accepted alternative;
- committed transcript fixtures are recursively safety-validated;
- sensitive retention establishes access/cleanup boundaries or fails closed;
- a baseline cannot pass without the accepted independent-review evidence.

### 5. Reconcile status, governance, and Phase execution

**Objective:** restore one trustworthy description of current project state and
one reviewable path to the Phase 1 completion or supersession boundary.

**Actions:**

1. Update `docs/knowledge/protocol.md`, the Windows-boundary decision, README,
   and current status wording to distinguish accepted design, implemented codec,
   incomplete conformance, implemented deterministic direct execution, and the
   still-unimplemented production PTY/OS boundary.
2. Preserve archived handovers as historical records; add concise historical
   context where readers could otherwise mistake old status for current state.
3. Create focused GitHub issues/PR boundaries from these workstreams and link
   them from this handover at material transitions only.
4. Record every owner decision and independent review in a durable design note or
   issue/PR review before unblocking dependent work.
5. Correct `NOTICE`, support wording, and the claimed pre-push/security boundary.
6. Keep the handover index navigation-only and update status only at meaningful
   transitions.

**Dependencies:** owner decisions determine final wording; stale-status fixes can
start immediately.

**Acceptance criteria:**

- searches find no current document claiming both that executable transcript
  contracts are absent and complete;
- the active handover, accepted decisions, GitHub issues, and agent prompts agree
  on stable-publication/production-adapter gates and Phase 1 scope;
- archived documents remain clearly historical and retain provenance;
- documentation validation and local-link checks pass.

### 6. Align quality, packaging, and release controls

**Objective:** make the green gate exercise the contract actually relied upon by
Phase 1 and remove avoidable release drift.

**Actions:**

1. Align pre-commit and uv on one Ruff version and document one authoritative
   gate implementation.
2. Reconcile security checks as CI-only or add maintained local equivalents; do
   not claim absent pre-push checks.
3. Establish one package-version source and update package tests/CI to consume it.
4. Add schema/content installation checks and a release checklist covering
   changelog, compatibility, provenance, and security disclosure before exposing
   stable Phase 1 APIs.
5. Introduce a reviewed coverage ratchet only after behavior-based adversarial
   coverage is meaningful; do not use coverage percentage as the sole oracle.
6. Add an available workflow syntax/policy check if it provides maintained,
   non-duplicative signal alongside zizmor.

**Dependencies:** schema packaging depends on owner decision 3; other alignment
may proceed independently.

**Acceptance criteria:**

- local direct commands, hooks, and CI use intentionally aligned tool versions;
- package version and schema availability cannot drift silently;
- every declared support version runs the same normative contract suite;
- the full validation gate below passes from a clean checkout.

## Required validation before completion

Run from the integration checkout after merging all reviewed workstreams:

```bash
uv --no-config sync --all-groups --locked
uv --no-config run pytest --cov --cov-report=term-missing
uv --no-config run ruff check .
uv --no-config run ruff format --check .
uv --no-config run mypy src tests scripts
uv --no-config run pre-commit run --all-files
uv --no-config run pre-commit run --hook-stage pre-push --all-files
uv --no-config build
git diff --check
git status --short --branch
```

Also require:

- green CI and Security workflows across the declared OS/Python matrix;
- isolated wheel and sdist tests for the transcript API; installed schema access
  belongs to the draft successor;
- independent review of protocol, evidence, baseline, and public API decisions;
- adversarial fixture/property results attached to the relevant PRs;
- no unreviewed baseline or CI artifact publication.

## Risks and non-negotiables

- A green current suite is not evidence that an untested protocol path is valid.
- Do not encode current invalid behavior into fixtures merely to increase fixture
  count or coverage.
- Do not claim enforcement from requested/effective value equality alone.
- Do not allow an adapter to dispatch input before every requested constraint is
  enforced or the run has terminated unsupported.
- Do not persist unknown evidence as public merely because no redaction pattern
  matched it.
- Do not silently change v1 compatibility, canonical bytes, stable error codes,
  or generic semantics without the accepted versioning decision and review.
- Do not make the schema and runtime competing sources of truth.
- Do not add dependencies for locale, schema, PTY, sandbox, or security behavior
  without a rationale and verification plan.
- Keep worktrees isolated. Sequence protocol/runtime/schema changes that touch
  shared public types or fixtures; parallelize only independent documentation,
  governance, and research work.

## Transition rules

- Mark **blocked** when an owner decision prevents all remaining safe work, a
  required independent review is unavailable, or a platform enforcement claim
  cannot be demonstrated.
- Keep **active** while prerequisite work can proceed without crossing an
  unresolved decision gate.
- This handover's accepted path is **superseded**, not complete: first verify the
  transcript-resource slice and amended completion gates, then activate the named
  successor so it accepts every transferred criterion intact.
- On **superseded**, move this document to
  `docs/agent/handovers/archive/`, update `docs/agent/handovers/index.md`, and
  preserve the final decisions and evidence.
