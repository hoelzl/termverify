# Adversarial Review Remediation Handover

## Handover metadata

- **Status:** active — the acronym-prefixed sensitive-key fix merged in PR #57,
  and the maintainer accepted the semantic-field transformation policy on
  2026-07-16; implementation may proceed with the remaining ordered reviewable
  slices below. Atomic-write durability still has its separate decision gate.
- **Owner:** project maintainer
- **Created:** 2026-07-16
- **Updated:** 2026-07-16
- **Review required:** yes — evidence security, public immutable contracts, serializer behavior, and protocol-adjacent refactors require candidate-bound independent human-readable review.
- **Predecessor:** none; this is a focused remediation initiative nested within, but not a replacement for, the active [Phase 1 readiness hardening handover](phase-1-readiness-hardening-handover.md).
- **Source reviews:** [GPT-5.6 review](../design/adversarial-correctness-and-code-quality-review-gpt-5.6-sol-2026-07-16.md) and [Opus 4.8 review](../design/adversarial-correctness-and-code-quality-review-opus-4.8-2026-07-16.md).
- **Execution plan:** [detailed implementation plan](../../../.hermes/plans/2026-07-16_215137-adversarial-review-remediation.md).
- **Successor:** none
- **Completion:** every confirmed finding in both source reviews has an explicit verified disposition; all accepted fixes are integrated; the evidence-policy gate is accepted and implemented or explicitly transferred; the full repository gate passes; and an independent final review accepts the integrated result.

## Purpose and boundaries

This handover transfers the union of two independent adversarial reviews of revision `97778b99cdb03081335f70d5f4ed3b8ae6a0ef7c` into focused, reviewable remediation work. The reviews agree that the deterministic core is strong and that Pydantic or implementation inheritance would weaken rather than simplify its contracts. Their combined coverage nevertheless identifies evidence-redaction security defects, serializer and immutable-contract edge cases, direct-runtime drift, and concentrated validation complexity.

**In scope:**

- close confirmed evidence leakage and valid-evidence denial paths;
- normalize malformed serializer inputs and preserve JSON runtime type categories;
- enforce diagnostic-time coherence in public immutable results;
- preserve abort diagnostics and make direct-runtime state cleanup robust;
- decompose the lifecycle validator and consolidate repeated result handling;
- remove codec-private coupling and cautiously centralize stable vocabulary;
- add atomic safe-evidence replacement as an isolated durability slice.

**Out of scope:**

- Pydantic, `attrs`, `msgspec`, implementation inheritance, validator frameworks, or dynamic protocol registration;
- sensitive persistence, OS-account permissions, retention cleanup, or CI artifact upload;
- exhaustive JSON Schema expansion;
- unrelated open Phase 1 gates such as resource ceilings, installed schema access, fixture breadth, release controls, production PTY containment, or deferred key/timezone/network registries.

This handover is not an issue tracker. Use one focused issue, branch, external sibling worktree, and independently reviewable PR per coherent workstream. GitHub and Git own volatile status.

## Verified current state

- Both source reviews inspected the same `main` revision, `97778b99cdb03081335f70d5f4ed3b8ae6a0ef7c`.
- At that revision both report `477` passing tests, `92%` total branch coverage, and passing Ruff and mypy gates. The GPT-5.6 review also reports passing format checks; the Opus review reports differential fuzzing of locale grammar and execution epochs with no divergence.
- Slice 1 merged through [PR #57](https://github.com/hoelzl/termverify/pull/57)
  at `ab1cb57cd1d44cf2079694f0140842a9eb583e8e`. Its candidate-bound review
  approved the acronym-boundary correction with no blocking findings; all 10 CI
  checks passed against the reviewed head, including Python 3.12-3.14 on Ubuntu
  and Windows.
- Confirmed-good boundaries to preserve include duplicate-member rejection, RFC 8785 canonical-byte checking, lifecycle/epoch validation, exact receipt binding, deep-frozen adapter JSON values, single-flight runtime state, post-redaction semantic revalidation, and the deliberately non-exhaustive schema boundary.
- **Not independently rerun while originally authoring this handover:** the
  reviews' mutation probes and fuzz campaigns. Slice 1 separately reproduced its
  selected defect under strict TDD and passed 492 tests at 92% branch coverage
  plus the complete local gate before review. Later implementing agents must
  likewise reproduce their selected findings on current `main` before editing.

## Confirmed findings

### P0 — acronym-prefixed sensitive keys could pass repository governance — fixed

- **Evidence at the reviewed revision:** `src/termverify/evidence.py` used a
  lower/digit-to-upper boundary only. The Opus review executed the real
  governance path and showed `APIToken`/AWS-key and `AWSSecret`/JWT combinations
  passing while snake-case controls were rejected.
- **Historical impact:** a live credential could reach a committed public fixture
  despite all three governance scans.
- **Disposition:** fixed by PR #57. Acronym transitions are tokenized correctly,
  and the real fixture validator rejects dynamically constructed AWS/JWT-shaped
  regression cases without adding credential-like values to committed fixtures.

### P0 — arbitrary semantic strings and extension names are not fail-closed

- **Evidence:** credential regexes are the only defense for multiple known semantic members, and extension values are redacted while attacker-controlled `x-` names remain intact. AWS IDs, JWTs, Slack tokens, and PEM body material were reported to survive in such positions.
- **Impact:** safe persistence and fixture governance can publish secrets encoded in structurally valid fields.
- **Required outcome:** every defined string-bearing field and extension name receives an explicit preserve/transform/redact/reject classification; denylist regexes remain secondary only.

### P1 — whole-record screening rejects valid grammar-constrained values

- **Evidence:** legal `sk-...` run IDs, Slovak-style locale tags, and replay selectors collide with the `sk-` credential pattern and fail post-redaction validation or selector screening.
- **Impact:** valid transcripts can be denied safe persistence.
- **Required outcome:** credential scanning is scoped to fields where credentials can actually be represented; constrained structural identities remain valid and unchanged.

### P1 — programmatic serialization has an inconsistent exception/type boundary

- **Evidence:** non-object records and non-string keys can leak `AttributeError`; integral floats can compare equal to requested integer configuration and serialize/parse as integers.
- **Impact:** callers cannot rely on `TranscriptValidationError`, and the programmatic serializer can silently change JSON runtime type category even though wire bytes remain canonical.
- **Required outcome:** recursive runtime JSON-shape validation plus type-aware JSON equivalence; no claim that canonical wire parsing itself is defective.

### P1 — immutable result aggregates permit contradictory diagnostic times

- **Evidence:** direct construction of `Started`, `EpochCompleted`, `TerminalResult`, `StartTerminated`, and fully negotiated `StartFailed` can combine diagnostics with another manual time. `DirectAdapter` catches reachable cases, but alternate structural adapters need not.
- **Impact:** public immutable values do not fully carry their own invariants.
- **Required outcome:** constructor-level coherence with direct-runtime checks retained as defense in depth.

### P2 — runtime abort and startup cleanup lose evidence or can wedge defensively

- **Evidence:** abort failure replaces application details with only `{"abort": "failed"}`; an unexpected `Started` construction failure can leave state at `initializing` without abort.
- **Impact:** operator diagnostics are weakest during compound failure, and an invariant-bypassing producer can wedge a direct adapter.
- **Required outcome:** collision-safe detail preservation and cleanup-safe terminal state transition.

### P2 — duplication and layering create correctness-drift risk

- **Evidence:** `_validate_lifecycle()` is 569 lines with reported complexity `F (276)`; dispatch/clock classification tails are nearly identical and stop repeats terminal handling; adapter imports a codec-private locale predicate; constraint order and JSON aliases are duplicated.
- **Impact:** future protocol corrections can land incompletely or break a separate compatibility boundary.
- **Required outcome:** behavior-preserving pure helper extraction, one narrow result classifier, neutral locale grammar, and cautiously shared stable vocabulary.

### P3 — direct evidence writes can truncate on failure

- **Evidence:** `Path.write_bytes()` writes directly to the destination.
- **Impact:** interruption can leave a truncated safe transcript, though not an immediate confidentiality leak because bytes are sanitized first.
- **Required outcome:** separate temp-file-plus-atomic-replace durability slice; `fsync` level must be explicit.

## Material decisions

### Resolved

- **Canonical modeling:** retain frozen slotted dataclasses, closed unions, structural protocols, composition, and procedural validation. Do not adopt Pydantic, `attrs`, `msgspec`, or implementation inheritance.
- **Numeric-type disagreement:** implement type-aware equality as serializer API hardening. Record that canonical wire output was not shown incorrect.
- **Security metadata sharing:** centralize stable protocol vocabulary only. Keep evidence classification independently fail-closed and prove coverage with synchronization tests.
- **Atomic persistence scope:** atomic safe replacement is a late isolated improvement. Sensitive-mode permissions/cleanup and any stronger `fsync` guarantee are not implied.
- **Schema scope:** these findings do not authorize exhaustive schema work or make schema acceptance equivalent to runtime conformance.
- **Unbounded semantic strings and extension names:** accepted on 2026-07-16.
  Safe persistence transforms every such attacker-controlled value while
  preserving structural invariants: deterministic positional placeholders; a
  shared region-ID/focus map; matched requested/effective terminal-capability
  transformation; redacted code/signal values; and deterministic valid
  replacement names for every `x-` member. Grammar-constrained envelope,
  locale, replay-selector, numeric, and enum fields are preserved without
  free-text credential scans. Credential patterns remain secondary defense.

### Accepted decision context — unbounded semantic strings and extension names

Current v1 permits arbitrary strings in UI IDs/roles/mode, input key names, terminal capability names, stable codes, signal values, and `x-` names. A denylist cannot make arbitrary attacker-controlled strings public-safe.

- **Accepted outcome:** use the transformation policy recorded under Resolved.
- **Compatibility/security impact:** safe evidence deliberately loses unbounded
  semantic labels while retaining protocol structure and relationships. This
  is preferable to making current transcripts non-persistable or relying on a
  credential denylist.
- **Review boundary:** implementation still requires candidate-bound independent
  human-readable security review; acceptance of the policy is not approval of
  an implementation diff.

### Decision gate — safe-mode durability level

- **Recommended default:** same-directory unique temporary file, close, and atomic replace; explicitly document that this is atomic replacement rather than guaranteed crash-durable storage.
- **Alternative:** add file and directory `fsync` with a separately reviewed cross-platform contract.
- **Decision owner:** project maintainer.
- **Blocks:** only atomic persistence Workstream 6.

## Workstreams

### 1. Immediate evidence security and correctness

**Objective:** close the repository credential leak, then implement the accepted semantic-field policy without denying valid constrained records.

**Actions:**

1. **Completed in PR #57:** fix acronym splitting with focused unit and
   governance integration tests.
2. Document and implement the accepted semantic-field classification matrix.
3. Scope generic credential scanning away from envelope, locale, and replay selectors.
4. Transform arbitrary semantic strings and extension names under the accepted
   invariant-preserving policy.
5. Add AWS/JWT/Slack/PEM recognition as secondary defense with near-miss tests.

**Dependencies:** acronym fix is independent; the semantic-field decision is
accepted, so the full workstream may proceed after its focused tests define the
cross-field transformations.

**Acceptance criteria:**

- The leak and valid-`sk-` corpora pass their expected reject/persist outcomes through both safe persistence and fixture governance.
- Every defined record kind and string-bearing field has an explicit security disposition.
- Sanitized output revalidates canonically and preserves cross-field invariants.

### 2. Serializer and immutable-contract hardening

**Objective:** make public programmatic inputs fail consistently and immutable results internally coherent.

**Actions:**

1. Replace number-only traversal with recursive runtime JSON-shape validation.
2. Make recursive JSON equality distinguish boolean, integer, and float categories.
3. Validate diagnostic times in all result aggregates, including outer-context cases with no terminal observation.

**Dependencies:** none; serializer and aggregate slices should remain separate PRs.

**Acceptance criteria:**

- Malformed records/keys/host values raise only `TranscriptValidationError` at the codec boundary.
- Integral floats cannot satisfy protocol integer fields or effective/requested matching.
- Every aggregate constructor rejects mismatched diagnostic time.

### 3. Direct-runtime drift reduction and failure preservation

**Objective:** classify epoch results once and make compound failures diagnosable and terminal.

**Actions:**

1. Preserve original `AdapterFailure.details` when abort fails.
2. Add cleanup-safe handling for unexpected startup result-construction failure.
3. Extract one private classifier shared by dispatch, clock advance, and the applicable stop terminal path, while retaining explicit public preconditions and port calls.

**Dependencies:** follow aggregate-time changes to avoid simultaneous edits to the same contract boundary.

**Acceptance criteria:**

- Classification matrix tests cover valid and malformed result types for all operations.
- No failure path wedges in `initializing`/`active`; abort is attempted where required.
- Existing single-flight/reentrancy semantics remain green.

### 4. Narrow shared internals

**Objective:** remove private cross-layer coupling and low-value vocabulary duplication.

**Actions:**

1. Move RFC 5646 grammar/fixed vocabulary to a narrowly named internal module.
2. Share ordered v1 constraint names and derive required config membership from them.
3. Share the JSON value alias without breaking current import surfaces.
4. Keep evidence classification independent and add exhaustive defined-kind coverage tests.

**Dependencies:** after correctness/security semantics stabilize; before lifecycle extraction.

**Acceptance criteria:**

- Adapter no longer imports from codec-private namespace.
- Constraint/config order cannot drift silently.
- No generic utilities/rules registry or inheritance is introduced.

### 5. Lifecycle-validator decomposition

**Objective:** turn `_validate_lifecycle()` into a readable procedural orchestrator with cohesive pure helpers.

**Actions:**

1. Establish characterization and property evidence on current `main`.
2. Extract phases in current validation order, one at a time.
3. Preserve exception classes, public diagnostic categories, valid canonical bytes, and all lifecycle semantics.

**Dependencies:** follows serializer correctness and shared-internal work to avoid churn.

**Acceptance criteria:**

- Existing fixtures and generated lifecycle models retain behavior.
- The orchestrator visibly sequences closure, identity/start/config, negotiation, input/observation, epoch, time, and exit-coherence phases.
- No class hierarchy, visitor, or dynamic rules engine appears.

### 6. Atomic safe persistence

**Objective:** leave old evidence intact if a replacement write fails.

**Actions:**

1. Add failure-injection tests for write, close, replace, and cleanup.
2. Write validated bytes to a unique same-directory temporary file and atomically replace.
3. Document the accepted `fsync` boundary without enabling sensitive persistence.

**Dependencies:** evidence redaction semantics complete; durability decision accepted.

**Acceptance criteria:**

- Prior destination survives simulated pre-replace failure.
- No tested failure leaves a temporary file.
- Successful bytes remain canonical and semantically valid.

## Risks and non-negotiables

- Security fixes can accidentally corrupt protocol identities or config/effective equality; every redaction transformation must be record-aware and followed by `serialize_transcript()`.
- Pattern expansion alone is not completion for attacker-controlled fields.
- Refactors must preserve validation order and public diagnostics; do not mix behavior changes into lifecycle extraction.
- Exact-type checks, transitive immutability, duplicate-member rejection, canonical byte comparison, receipt binding, and lifecycle closure are non-negotiable.
- Do not turn evidence allowlists into aliases of codec metadata; a new record kind without explicit evidence classification must fail a test.
- No golden master or baseline may be auto-approved.
- Run candidate-bound independent review after material security/public-contract edits; green CI alone is insufficient.

## Validation evidence required

Focused commands are specified in the execution plan. Final completion requires the full `AGENTS.md` gate:

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
```

Also require a final reconciliation table against every ranked correctness and quality finding in both source reviews. Optional suggestions (exhaustive schema expansion, sensitive mode, broader release work) must be labeled deferred rather than silently treated as completed.

## Transition rules

- Mark **blocked** when the only remaining actionable work depends on an unresolved decision gate or external review.
- Mark **complete** only when all accepted fixes and refactors are integrated, both decision gates have explicit dispositions, the full gate passes, and independent final review accepts the candidate.
- Mark **superseded** when a named successor accepts every unresolved finding and decision intact.
- On **complete** or **superseded**, move this document to `docs/agent/handovers/archive/` and update `docs/agent/handovers/index.md`.
- This handover does not complete, supersede, or authorize Phase 2 under the separate Phase 1 readiness handover.
