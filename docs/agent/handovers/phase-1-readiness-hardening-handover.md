# Phase 1 Readiness Hardening Handover

## Handover metadata

- **Status:** active — all owner decision gates were accepted on 2026-07-15;
  public adapter/runtime implementation remains blocked on the prerequisite
  workstreams below.
- **Owner:** project maintainer
- **Created:** 2026-07-15
- **Updated:** 2026-07-16
- **Review required:** yes — accepted protocol compatibility,
  deterministic-enforcement, evidence-security, schema-authority, and
  baseline-governance decisions require executable implementation and
  independent human-readable review.
- **Predecessor:**
  [Quality hardening handover](archive/quality-hardening-handover.md)
- **Successor:** none
- **Completion:** all P0/P1 findings below have executable regression coverage;
  every decision gate has an accepted disposition; documentation, schema,
  runtime, fixtures, package artifacts, and quality gates agree; and an
  independent review accepts the resulting Phase 1 boundary.

## Purpose and boundaries

This handover transfers the July 2026 adversarial foundation review into a
bounded prerequisite initiative. TermVerify's conceptual architecture remains
sound, but the current `termverify.transcript/v1` implementation and evidence
controls do not yet enforce all claims made by the accepted specifications.
Phase 1 may continue only through the hardening and research work defined here
until the public adapter/runtime boundary is explicitly unblocked.

**In scope:**

- repair parser/serializer symmetry and transcript lifecycle validation;
- reconcile all accepted v1 prose, schema, fixtures, and runtime rules;
- resolve protocol evolution, replay identity, normalization, causality, and
  deterministic-enforcement semantics;
- complete evidence classification, redaction, safe persistence, retention, and
  baseline-approval enforcement;
- expand adversarial fixtures, properties, package checks, and resource limits;
- reconcile Phase status and establish the current Phase 1 execution boundary;
- align local/CI quality tooling and release-facing compatibility claims.

**Out of scope:**

- production direct or PTY adapter implementation before the entry gates pass;
- transcript replay/comparison, application fixtures, or browser bridging;
- automatic baseline approval or automatic acceptance of changed behavior;
- broad refactoring unrelated to a confirmed finding or accepted decision.

This document is not an issue tracker. Create one focused GitHub issue and one
independently reviewable pull request for each coherent workstream or accepted
decision. Keep volatile progress in GitHub and Git.

## Verified current state

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

### Reconciliation through merged PR #21 and issue #22

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
- A fresh probe after PR #21 confirmed that malformed locale values including
  `not a tag!`, `en_US`, and the incomplete private-use singleton `x` remained
  accepted. Issue [#22](https://github.com/hoelzl/termverify/issues/22) is the
  next focused prerequisite: accept literal `C` or RFC 5646 well-formed syntax,
  preserve caller spelling and case, and avoid registry lookup or normalization.
  Timezone conformance remains separate because its accepted vocabulary and
  platform-independent registry/version mechanism still require a decision.

The adapter-contract entry gate remains closed during and after issue #22.
Remaining gates
include other Workstream 1 local and cross-record rules, the deterministic
vocabularies and negotiation/attestation semantics in Workstream 2,
locale enforcement/attestation and timezone conformance, fixture/property
coverage, resource limits, and the deliberately bounded schema package-access
criteria in Workstreams 3 and 6.
Neither issues #16/#18/#20/#22 nor the merged schema slice authorizes
adapter/runtime implementation or exhaustive schema work.

### Confirmed P0 defects

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

### Confirmed P1 defects and oversights

- Identifier grammar, BCP 47/`C` locale, and IANA/`UTC` timezone rules are not
  enforced (`docs/knowledge/protocol.md:47-51`, `:101-107` versus
  `src/termverify/transcript.py:143-148`, `:256-258`).
- Required terminal capabilities can be omitted when the echoed effective value
  omits them too; nested configuration objects are not consistently closed.
- Python `bool` values can satisfy JSON integer/equality rules for `seq`, mouse
  scroll delta, and capability effective values.
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

The project maintainer accepted all eight dispositions below. Public
adapter/runtime implementation remains blocked until they are reflected in the
applicable prose and executable tests.

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

## Workstreams

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
- the adapter-contract worktree remains unchanged until this entry gate passes.

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
one reviewable path into Phase 1.

**Actions:**

1. Update `docs/knowledge/protocol.md`, the Windows-boundary decision, README,
   and current status wording to distinguish accepted design, implemented codec,
   incomplete conformance, and unimplemented adapter runtime.
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
  on adapter entry gates and Phase 1 scope;
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
- isolated wheel and sdist tests for transcript API and schema access;
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
- Mark **complete** only when the metadata completion condition and all required
  validation evidence are verified on the integrated result.
- Mark **superseded** only when a named successor handover accepts the remaining
  scope and this document links to it.
- On **complete** or **superseded**, move this document to
  `docs/agent/handovers/archive/`, update `docs/agent/handovers/index.md`, and
  preserve the final decisions and evidence.
