# Adversarial Review Remediation Implementation Plan

> **For the implementing agent:** Execute this plan one coherent reviewable slice at a time, using strict TDD and candidate-bound independent review. The maintainer accepted the recommended semantic-field transformation policy on 2026-07-16; the separate safe-write durability decision remains open.

> **Progress:** Slice 1 merged through
> [PR #57](https://github.com/hoelzl/termverify/pull/57) on 2026-07-16 after
> candidate-bound independent review. Resume with Slice 2; do not rerun the
> kickoff prompt against current `main`.

**Goal:** Apply the union of confirmed fixes and maintainability improvements from the two 2026-07-16 adversarial reviews without weakening canonical transcript validation, immutable value contracts, or fail-closed evidence handling.

**Architecture:** Keep the canonical core as frozen slotted dataclasses, closed unions, structural protocols, composition, and procedural validation. Correct security and public-boundary defects first; then extract cohesive pure helpers and narrowly shared v1 vocabulary without introducing Pydantic, implementation inheritance, a validator framework, or dynamic registration.

**Tech stack:** Python 3.12+, `uv`, pytest/Hypothesis, Ruff, mypy, pre-commit, RFC 8785 canonical JSON.

---

## 1. Source reviews and synthesis decisions

Implement against current `main`, but begin by reproducing every selected behavior because both reports reviewed exact revision `97778b99cdb03081335f70d5f4ed3b8ae6a0ef7c`.

Sources:

- `docs/agent/design/adversarial-correctness-and-code-quality-review-gpt-5.6-sol-2026-07-16.md`
- `docs/agent/design/adversarial-correctness-and-code-quality-review-opus-4.8-2026-07-16.md`
- `docs/agent/handovers/adversarial-review-remediation-handover.md`

### Reconciled disposition

| Topic | Disposition |
| --- | --- |
| Evidence acronym splitting | Confirmed High security defect; fix first. |
| Modern credential forms and attacker-controlled semantic members | Confirmed High security design gap. The maintainer accepted deterministic transformation of unbounded semantic strings and `x-` names while preserving protocol invariants. Pattern additions are secondary defense, never the sole control for arbitrary text. |
| `sk-` collisions in envelope, locale, and replay selectors | Confirmed Medium availability/correctness defect; stop scanning grammar-constrained structural fields with free-text credential regexes. |
| Serializer `AttributeError` leaks | Confirmed public-boundary defect; add one recursive runtime JSON-shape preflight and normalize all malformed shapes to `TranscriptValidationError`. |
| Integral float vs integer effective values | The reports agree on behavior and disagree on severity. Implement the fix as serializer API/type-contract hardening, not as a wire-canonicalization bug. Programmatic serialization must not silently change Python JSON type categories across serialize/parse. |
| Aggregate diagnostic times | Confirmed public immutable-contract gap; enforce in aggregate constructors and retain `DirectAdapter` checks as defense in depth. |
| Runtime abort details | Confirmed diagnostic-loss defect; preserve original application details while recording abort failure. |
| `Started` construction/state ordering | Defense-in-depth defect; ensure no constructor failure can leave the adapter in `initializing` or skip abort cleanup. |
| Lifecycle validator size | Confirmed principal maintainability risk; behavior-preserving pure-function extraction only after correctness fixes. |
| Direct result classification | Confirmed drift risk; consolidate classification while leaving operation-specific preconditions and port calls explicit. |
| Codec-private locale helper | Confirmed layering violation; move only language-tag grammar and fixed vocabulary to a neutral internal module. |
| Shared vocabulary | Centralize stable constraint order and the JSON alias. Keep evidence classification metadata independently fail-closed; add exhaustive synchronization tests instead of making security policy an alias of codec metadata. |
| Atomic evidence writes | Implement as a separate durability slice after redaction semantics stabilize. Atomic replacement is in scope; `fsync`, sensitive-mode permissions, lifetime, and cleanup remain explicit policy/future boundaries. |
| Pydantic/`attrs`/`msgspec` | Do not adopt in the canonical core. An optional future edge adapter needs a separate use case and decision. |
| Inheritance | Do not add domain or implementation base classes. Preserve exact-type and closed-union contracts. |
| Exhaustive JSON Schema | Not required by these fixes. Consider separately only if broader declarative interoperability coverage is explicitly approved. |

## 2. Dependency and review strategy

Recommended sequence:

```text
Slice 1 evidence emergency fix ───────────────┐
Slice 2 serializer strictness ────────────────┼─ independent
Slice 3 aggregate time coherence ─────────────┤
                                               ├─ Slice 4 direct runtime cleanup
Accepted evidence policy ── Slice 5 hardening ┤
                                               ├─ Slice 6 shared internals
                                               ├─ Slice 7 lifecycle decomposition
                                               └─ Slice 8 atomic persistence
```

Use one focused issue/branch/PR per numbered slice. Slices 1-3 may be developed independently only in separate external sibling worktrees and only if they do not edit the same test module. Sequence Slices 4-8 because they overlap public types, `direct.py`, `transcript.py`, or `evidence.py`. Do not make intermediate commits or PRs for an incomplete tracer bullet; each PR must deliver a coherent contract slice with its complete regression evidence.

For every slice:

1. Create or refresh an external sibling worktree from `origin/main` as documented in `docs/developer-guide/agent-workflow.md`.
2. Run `uv --no-config sync --all-groups --locked` once in that worktree.
3. Write focused failing tests and run them to establish genuine behavioral RED failures. Separate setup/message-mismatch failures from behavioral failures.
4. Implement the minimum coherent correction.
5. Run focused tests, then the relevant wider module tests.
6. Inspect the diff and run the full repository gate before requesting review.
7. Freeze the candidate SHA/diff and obtain independent human-readable review for security, protocol, public API, or behavior changes. Re-run review after material edits.

## 3. Slice 1 — Close the acronym-key credential leak

**Objective:** Ensure sensitive acronym-prefixed keys cannot pass either safe persistence or committed-fixture governance.

**Files:**

- Modify: `src/termverify/evidence.py`
- Modify: `tests/test_evidence.py`
- Modify: `tests/test_validate_evidence_governance.py`

**TDD steps:**

1. Add a parameterized key-tokenization/redaction test covering `api_token`, `myTOKEN`, `authorization`, `APIToken`, `AWSSecret`, `DBPassword`, `GHToken`, and `XToken`. Assert every sensitive form is redacted while a non-sensitive acronym key remains unchanged.
2. Add governance integration cases proving a fixture containing a synthetic credential beneath `APIToken` or `AWSSecret` is rejected by the real validator, not merely by a private helper.
3. Run the focused tests and confirm current behavior fails for all-caps-prefix cases.
4. Replace `_CAMEL_CASE_BOUNDARY` with the two-boundary form that splits lower/digit-to-upper and acronym-to-capitalized-word transitions.
5. Re-run both focused test modules. Verify existing snake-case, kebab-case, lowercase, and ordinary camelCase behavior remains unchanged.

**Acceptance criteria:**

- `APIToken` tokenizes as `api`, `token`; `AWSSecret` as `aws`, `secret`.
- The committed-fixture governance path rejects the same cases as safe persistence.
- No credential-like literal is added to a committed `.jsonl` fixture; construct it inside tests.

## 4. Slice 2 — Make the serializer boundary shape- and type-strict

**Objective:** Make every malformed programmatic JSON shape fail as `TranscriptValidationError` and preserve JSON runtime type categories in effective/requested comparisons.

**Files:**

- Modify: `src/termverify/transcript.py`
- Modify: `tests/test_transcript.py`
- Modify if lifecycle-specific placement is clearer: `tests/test_transcript_lifecycle.py`

**TDD steps:**

1. Add parameterized tests for non-object top-level records (`[]`, string, integer, `None`) and non-string keys in the envelope, config, each representative nested protocol object, an `x-` extension value object, and open application data. Assert only `TranscriptValidationError` escapes.
2. Retain tests for tuples and non-finite floats, then add unsupported host values to prove the new traversal is a complete runtime JSON-shape preflight rather than a number-only check.
3. Add capability-result tests with integral floats in clock `initial_ms`, terminal `columns`/`rows`, and network `port`. Add representative integral floats in input/diagnostic/observation `at_ms` and process/terminal exit-code positions. Assert protocol integer positions reject them.
4. Add a nested effective-value case proving `_json_equivalent()` distinguishes `bool`, `int`, and `float` recursively. Add positive controls for valid equal values and ordinary application-defined finite floats that the protocol permits.
5. Run the focused tests and record the genuine RED cases: raw `AttributeError`, accepted integral-float effective values, or type-changing round trips.
6. Replace `_validate_json_numbers()` with a recursive runtime JSON-shape validator that:
   - requires the outer `records` value to be a list and each record to be an object before iteration or envelope access;
   - requires every object key to have exact type `str`;
   - accepts only JSON-compatible scalar/container categories already supported by the API;
   - rejects tuples, unsupported host objects, and non-finite floats;
   - raises `TranscriptValidationError` consistently.
7. Make `_json_equivalent()` compare JSON type categories before scalar equality, explicitly separating booleans, integers, and floats while preserving recursive list/dict comparison.
8. Re-run transcript and schema tests. Verify parser duplicate-member and RFC 8785 canonical-byte checks are unchanged.

**Acceptance criteria:**

- No malformed programmatic input covered above leaks `AttributeError`, `KeyError`, or dependency-specific exceptions.
- Valid programmatic records still serialize canonically and parse back with the intended JSON type categories.
- No change is claimed for valid wire bytes: this slice hardens the programmatic serializer contract.

## 5. Slice 3 — Enforce diagnostic-time coherence in immutable aggregates

**Objective:** Make every public result aggregate internally time-coherent regardless of which structural `Adapter` implementation constructs it.

**Files:**

- Modify: `src/termverify/adapter.py`
- Modify: `tests/test_adapter.py`
- Verify, normally without semantic edits: `src/termverify/direct.py`, `tests/test_direct.py`

**TDD steps:**

1. Add direct-construction tests with mismatched diagnostics for `Started`, `EpochCompleted`, `TerminalResult`, `StartTerminated`, and `StartFailed`.
2. Cover both `TerminalResult` forms: observation present (time comes from observation) and observation absent (the outer `StartTerminated` supplies effective initial time).
3. For `StartFailed`, prove startup diagnostics are still forbidden before complete negotiation and, after complete negotiation, must match the effective initial clock.
4. Change `_validate_diagnostics()` to accept an optional expected `ManualTime`/integer and reject any diagnostic at another time.
5. Pass the expected time from each aggregate where determinable. Have `StartTerminated` validate its nested result diagnostics against the effective initial clock even when no terminal observation exists.
6. Retain the direct runtime checks and run adapter plus direct tests.

**Acceptance criteria:**

- All public aggregate constructors reject contradictory timestamps.
- Existing exact-type, deep-freeze, negotiation-prefix, and terminal-process invariants remain unchanged.

## 6. Slice 4 — Preserve abort diagnostics and consolidate runtime classification

**Objective:** Remove result-classification drift while preserving operation-specific state, time, and application-port behavior.

**Files:**

- Modify: `src/termverify/direct.py`
- Modify: `tests/test_direct.py`

**TDD steps:**

1. Add a runtime case where the application returns `AdapterFailure` with mapping details and abort fails. Assert original details survive alongside a deterministic abort-failure marker.
2. Add a case for non-mapping details and specify a stable nested representation; do not silently discard it.
3. Add defense-in-depth coverage for a post-initialization result-construction/invariant failure. Assert abort is attempted and state becomes terminal rather than remaining `initializing`.
4. Add or retain a classification matrix for `EpochCompleted`, `TerminalResult`, valid `AdapterFailure`, wrong failure code, foreign object, wrong time, and wrong terminal outcome across dispatch, clock advance, and stop.
5. Implement one private result-classification helper parameterized by active `at_ms`, whether nonterminal `EpochCompleted` is allowed, and operation-specific failure messages. Keep public input validation, manual-clock relation, lock transition, and the actual application port call explicit in each public method.
6. Merge abort metadata with original details. Use a documented collision-safe representation; never overwrite application-supplied details wholesale.
7. Construct/validate the `Started` result inside a cleanup-safe boundary. On an unexpected invariant failure, abort and transition terminal; do not set idle and do not wedge in `initializing`.
8. Run direct and adapter tests, including reentrancy and concurrent single-flight tests.

**Acceptance criteria:**

- Dispatch and clock-advance classification no longer have duplicated tails; stop reuses terminal classification without obscuring its distinct contract.
- Every malformed/exception path ends terminal after the appropriate abort attempt.
- Original failure code, message, and details remain inspectable when abort itself fails.

## 7. Slice 5 — Implement accepted semantic evidence classification

**Objective:** Make safe persistence both leak-resistant and complete for valid protocol records, with regexes only as secondary defense.

**Accepted decision (2026-07-16; candidate-bound independent security review remains required):**

The protocol currently permits arbitrary strings in UI IDs/roles/mode, key names, terminal capability names, stable diagnostic/error codes, signal values, and `x-` member names. Apply this accepted policy:

- Safe persistence treats every unbounded semantic string and every extension member name as attacker-controlled. It replaces content while preserving protocol invariants: positional placeholders for ordered collections; a deterministic region-ID mapping reused by `focus`; matched transformation of requested/effective terminal capabilities; redacted diagnostic/error/signal strings; and deterministic valid `x-redacted-NNNN` extension names. Grammar-constrained envelope, replay selector, locale, seed, numeric, and enum fields bypass free-text credential regexes because their validators exclude actual modern credential encodings.
- Rejection of all such transcripts was considered but not selected because it would make current valid evidence non-persistable until registries exist.
- Leaving arbitrary strings intact behind a credential denylist is rejected as not fail-closed.

**Files:**

- Modify first (decision): `docs/knowledge/evidence-governance.md`
- Modify: `src/termverify/evidence.py`
- Modify: `tests/test_evidence.py`
- Modify: `scripts/validate_evidence_governance.py`
- Modify: `tests/test_validate_evidence_governance.py`

**TDD/implementation steps:**

1. Add a field-classification matrix test covering every defined record kind and every string-bearing structural/semantic position.
2. Add valid-transcript persistence tests for `run_id = "sk-" + "a" * 22`, Slovak-style `sk-...` locale, and `sk-fixture-scenario-alpha` replay identity. Assert canonical safe persistence succeeds and preserves these structural values.
3. Add leak tests for AWS access IDs, JWTs, Slack tokens, PEM headers/body-like lines, acronym-sensitive keys, extension key names, and each unbounded semantic member. Test both `persist_transcript_evidence()` and the committed-fixture governance script.
4. Refactor redaction to operate record-first and field-first. Do not run generic free-text redaction over the whole envelope or validated grammar-constrained selectors.
5. Implement the accepted transformations in lockstep where protocol invariants cross fields (`ui.regions[].id`/`ui.focus`, config/effective terminal capabilities, process exit/final outcome if signal strings are transformed).
6. Rename or reject attacker-controlled `x-` keys according to the accepted policy; redacting only their values is insufficient.
7. Extend `_CREDENTIAL_PATTERNS` for modern recognizable forms only as a secondary net in genuinely free text. Include near-miss controls to bound false positives.
8. Remove `_contains_credential_shaped_selector()` checks from grammar-constrained selector fields once tests prove those grammars exclude the covered credential forms; keep structural validation before and after redaction.
9. Update governance prose and tests together. A path-specific exception or bypass is not acceptable.

**Acceptance criteria:**

- Every defined string-bearing field has an explicit `preserve`, `transform`, `blanket redact`, or `reject` disposition.
- Valid grammar-constrained records no longer fail merely because text resembles `sk-...`.
- The leak corpus cannot reach safe output or pass fixture governance.
- Sanitized records still pass `serialize_transcript()` and preserve required cross-record equality/coherence.

## 8. Slice 6 — Establish narrow shared internal vocabulary

**Objective:** Remove unstable cross-layer imports and selected drift without coupling evidence security policy to codec implementation details.

**Files:**

- Create: `src/termverify/_language_tag.py`
- Create or choose one narrow equivalent: `src/termverify/_protocol_v1.py`
- Create or choose one narrow equivalent: `src/termverify/_json.py`
- Modify: `src/termverify/transcript.py`
- Modify: `src/termverify/adapter.py`
- Modify: `src/termverify/direct.py`
- Modify: `src/termverify/evidence.py`
- Modify: relevant tests, primarily `tests/test_adapter.py`, `tests/test_transcript.py`, and `tests/test_evidence.py`

**Steps:**

1. Characterize public imports and `__all__` before moving aliases so no accidental API break occurs.
2. Move the RFC 5646 syntax predicate and grandfathered fixed vocabulary to `_language_tag.py`; import it from adapter and transcript. Do not create a generic validation-utilities module.
3. Define the ordered seven v1 constraint names once in `_protocol_v1.py`, retaining the public `ConstraintName` surface where currently exposed. Derive `required_config` from the shared order rather than an independent literal.
4. Define the JSON value alias once in `_json.py` and import/re-export as needed to preserve compatibility.
5. Keep codec payload closure and evidence classification maps separate. Add an exhaustive synchronization test proving every defined v1 record kind has an evidence disposition, while allowing intentionally different per-layer metadata.
6. Keep receipt types and enforcement callables local to adapter/direct code; do not turn vocabulary into a rules registry.

**Acceptance criteria:**

- `adapter.py` no longer imports a private name from `transcript.py`.
- A new constraint cannot silently diverge between required config and capability order.
- Evidence fails closed for a defined kind missing a security classification.
- No implementation inheritance, plugin validator, or dynamic dispatch registry is introduced.

## 9. Slice 7 — Decompose `_validate_lifecycle()` without behavior change

**Objective:** Reduce the 569-line validator's review complexity while preserving validation order, exception type, and stable diagnostic text.

**Files:**

- Modify: `src/termverify/transcript.py`
- Modify: `tests/test_transcript.py`
- Modify: `tests/test_transcript_lifecycle.py`
- Verify: `tests/test_transcript_schema.py`

**Steps:**

1. Before extraction, add characterization/property coverage that mutates valid fixtures one invariant at a time and records the same acceptance/rejection plus diagnostic category. Reuse existing Hypothesis lifecycle models; do not copy review-only probes blindly without rerunning them on current `main`.
2. Extract pure same-module helpers in current execution order, targeting cohesive phases such as:
   - record kinds and payload closure;
   - run identity/start/terminal placement;
   - replay subject and run config;
   - terminal payload;
   - capability negotiation/effective values;
   - input payloads;
   - diagnostics/observations/process/frame/UI;
   - execution epochs;
   - manual times and exit coherence.
3. Keep `_validate_lifecycle()` as a short procedural orchestrator with explicit data flow. Avoid classes, visitors, decorators, generic rule engines, or dynamic registration.
4. Extract one phase at a time and run focused characterization tests after each extraction.
5. Run complexity measurement for evidence only; do not chase an arbitrary threshold by fragmenting readable helpers.

**Acceptance criteria:**

- The existing valid corpus remains byte-identical through parse/serialize.
- Existing invalid fixtures and generated model cases retain acceptance/rejection behavior and stable public exception categories/messages.
- `_validate_lifecycle()` becomes an auditable orchestrator; each helper has one protocol responsibility.

## 10. Slice 8 — Make safe evidence replacement atomic

**Objective:** Prevent a failed overwrite from leaving a truncated destination while keeping sensitive-mode hardening out of scope.

**Files:**

- Modify: `src/termverify/evidence.py`
- Modify: `tests/test_evidence.py`
- Update only if policy is accepted: `docs/knowledge/evidence-governance.md`

**TDD steps:**

1. Add tests for a new destination, replacement of an existing destination, failure before replace, cleanup of temporary files, and preservation of the old destination on failure.
2. Write the fully validated canonical bytes to a uniquely created temporary file in the destination directory, close it, then atomically replace the destination.
3. Clean temporary files on every exception path. Avoid predictable names and cross-filesystem moves.
4. Decide separately whether safe mode requires file/data `fsync`; document the chosen durability level. Do not imply crash-durable directory metadata without directory sync.
5. Do not implement sensitive mode, `0600`/Windows ACL policy, 24-hour cleanup, or repository-containment changes in this slice.

**Acceptance criteria:**

- A simulated write/replace failure leaves any prior destination intact.
- Successful output remains canonical and revalidates.
- No orphan temporary file remains after tested failures.

## 11. Deliberate non-goals

- No Pydantic, `attrs`, or `msgspec` dependency in canonical transcript or immutable adapter contracts.
- No implementation/domain inheritance, command hierarchy, Template Method superclass, validator class graph, or plugin registry.
- No weakening of duplicate-member rejection, RFC 8785 canonical comparison, exact-type immutable values, deep freezing, lifecycle validation, or post-redaction revalidation.
- No automatic golden/baseline update.
- No sensitive persistence enablement.
- No exhaustive v1 JSON Schema expansion unless separately approved; schema acceptance remains non-exhaustive and non-authoritative for full conformance.
- No unrelated Phase 1 closure work (resource ceilings, installed schema access, fixture breadth, release controls, terminal production containment).

## 12. Validation and completion gate

During development, run the narrowest relevant test first. Before each PR review, run:

```bash
uv --no-config run pytest tests/test_evidence.py tests/test_validate_evidence_governance.py -q
uv --no-config run pytest tests/test_transcript.py tests/test_transcript_lifecycle.py tests/test_transcript_schema.py -q
uv --no-config run pytest tests/test_adapter.py tests/test_direct.py -q
```

Before declaring the initiative complete, run the full repository gate from `AGENTS.md`:

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

Completion additionally requires:

- explicit maintainer acceptance of the semantic evidence-classification policy;
- independent human-readable security review of Slice 5;
- independent review of public API/protocol-sensitive Slices 2-4 and the final integrated candidate;
- reconciliation of every finding from both source reviews as fixed, intentionally deferred with rationale, or rejected with evidence;
- no unreviewed changes to schema authority, sensitive retention, baseline governance, or protocol versioning.
