# Adversarial correctness and code-quality review

- **Date:** 2026-07-16
- **Revision reviewed:** `97778b99cdb03081335f70d5f4ed3b8ae6a0ef7c`
- **Branch:** `main`
- **Scope:** `src/termverify/`, its protocol and architecture documentation,
  schema, fixtures, and tests
- **Review mode:** read-only primary review plus two independent adversarial
  review passes
- **Focus:** correctness, malformed-input behavior, immutable-contract
  invariants, maintainability, Pydantic suitability, inheritance, and SOLID
  trade-offs

## Executive summary

TermVerify has a strong correctness-oriented foundation. The reviewed revision
passed all declared tests and static checks, and the review found no critical
failure in the accepted Phase 1 behavior. Canonical transcript framing,
duplicate-member rejection, lifecycle validation, enforcement receipts,
immutable adapter values, direct-adapter state transitions, and safe evidence
persistence are unusually well defended for a pre-alpha codebase.

The review found three concrete correctness weaknesses:

1. enforced capability values can use an invalid numeric runtime type, compare
   equal to the requested configuration, and silently change type during
   serialization;
2. public immutable result aggregates permit diagnostic timestamps that
   contradict their observation or effective clock;
3. malformed programmatic serializer inputs can leak raw `AttributeError`
   exceptions instead of the codec's public validation exception.

The principal maintainability risk is not the absence of a modeling framework.
It is the concentration of most wire validation in one 569-line function and
some duplication of runtime-result processing and protocol vocabulary.

The review therefore recommends **not** introducing Pydantic into the canonical
core and **not** adding implementation inheritance or domain base-class
hierarchies. Smaller pure validation functions, narrowly shared protocol
metadata, and continued use of frozen dataclasses, closed unions, structural
protocols, and composition fit the project better.

## Method

The review read and cross-checked:

- `README.md` and `AGENTS.md`;
- `docs/knowledge/protocol.md`;
- `docs/knowledge/architecture.md`;
- `docs/knowledge/evidence-governance.md`;
- `docs/knowledge/verification-model.md`;
- the accepted Phase 1 adapter execution contract;
- all modules under `src/termverify/`;
- the v1 JSON Schema;
- focused transcript, schema, adapter, direct-runtime, and evidence tests;
- the active Phase 1 readiness-hardening handover, including documented
  deferred boundaries.

The review combined source inspection with focused runtime mutation probes. A
valid canonical transcript fixture was copied and changed one property at a
time. Constructor probes exercised public immutable aggregates directly rather
than relying only on `DirectAdapter`, because structural `Adapter`
implementations and test doubles can return those values without passing
through `DirectAdapter`.

Documented open gates such as resource ceilings, fixture breadth, installed
schema access, release controls, timezone registry policy, key and terminal
capability registries, network allow-list enforcement, and production PTY
containment were treated as acknowledged scope. They are not presented below
as newly discovered implementation defects.

## Ranked correctness findings

### 1. Medium: capability effective values permit type-changing round trips

**Locations:**

- `src/termverify/transcript.py:445-449`
- `src/termverify/transcript.py:928-940`
- `docs/knowledge/protocol.md:184-190`
- `docs/knowledge/protocol.md:226-230`

For an enforced capability, the runtime checks that `effective` is equivalent
to the corresponding requested configuration value. The recursive
`_json_equivalent()` helper correctly distinguishes booleans and recursively
compares lists and dictionaries, but its scalar fallback uses ordinary Python
equality.

Python equality conflates distinct JSON runtime representations:

```python
0.0 == 0
80.0 == 80
```

The requested configuration is validated first and therefore contains the
required integer types. An independently supplied capability `effective` value
is not validated with the corresponding configuration predicate. Because
Python considers an integral float equal to the requested integer,
`_json_equivalent()` accepts it. RFC 8785 then renders the integral float as an
integer, so parsing the serialized transcript returns a different runtime
representation.

Focused probes starting from the canonical `basic.jsonl` fixture produced:

```text
clock effective initial_ms=0.0
  serialize: accepted
  reparsed effective initial_ms: 0 (int)

terminal effective columns=80.0
  serialize: accepted
  reparsed effective columns: 80 (int)
```

This weakens the exact effective-value check and violates the serializer-side
semantic round-trip expectation already used to reject host-only array
representations such as tuples.

**Recommended change:** make JSON equivalence recursively aware of runtime JSON
type categories. In particular, distinguish `bool`, `int`, and `float` before
comparing values. Preserve recursive list and dictionary comparison and the
existing treatment of extension values.

**Required regression coverage:** probe integral floats in at least:

- clock `initial_ms`;
- terminal `columns` and `rows`;
- network endpoint `port`;
- input, diagnostic, and observation timestamps;
- exit codes;
- nested capability effective values.

Positive controls should prove that valid requested/effective pairs and
ordinary application-defined numbers still round-trip as intended.

### 2. Medium: immutable result aggregates permit contradictory timestamps

**Locations:**

- `src/termverify/adapter.py:817-835`
- `src/termverify/adapter.py:896-919`
- `src/termverify/adapter.py:922-935`
- `src/termverify/adapter.py:938-974`
- `src/termverify/adapter.py:977-997`
- `src/termverify/direct.py:338-344`
- `src/termverify/direct.py:380-387`
- `src/termverify/direct.py:425-432`

The direct-adapter contract requires observations and diagnostics produced by
an operation to use the active manual time. `DirectAdapter` enforces this at its
application boundary. The public immutable result types, however, validate only
that diagnostics form a tuple containing exact `Diagnostic` values.

They do not bind diagnostic timestamps to a time already known by the
aggregate. Focused constructor probes with an observation at `ManualTime(0)`
and a diagnostic at `ManualTime(1)` showed that all of the following were
accepted:

```text
Started
EpochCompleted
TerminalResult
StartTerminated
StartFailed
```

This creates a gap between the public value contract and one particular
implementation. A structurally compatible `Adapter` or test double can return
an internally contradictory immutable result, requiring every consumer to
repeat `DirectAdapter`'s validation.

**Recommended change:** extend diagnostic validation to accept an expected time
where the containing aggregate can determine one:

- `Started`: the effective initial clock;
- `EpochCompleted`: the observation time;
- `TerminalResult`: the observation time when an observation exists;
- `StartTerminated`: the effective initial clock, including diagnostics when
  there is no terminal observation;
- `StartFailed`: the effective initial clock when startup diagnostics are
  permitted after complete negotiation.

Keep `DirectAdapter`'s checks as defense in depth. Add direct-construction tests
for every aggregate rather than testing wrong times only through the adapter.

### 3. Low: malformed serializer inputs can leak `AttributeError`

**Locations:**

- `src/termverify/transcript.py:127-151`
- `src/termverify/transcript.py:196-201`
- `src/termverify/transcript.py:992-995`

`serialize_transcript()` advertises validation of programmatic records. The
recursive pre-canonicalization check currently rejects tuples and non-finite
floats but does not validate the top-level record type or object-key types.
Later validators assume mappings with string keys.

Focused probes produced:

```text
serialize_transcript([[]])
  -> AttributeError: 'list' object has no attribute 'keys'

valid_records[0][1] = "bad"
serialize_transcript(valid_records)
  -> AttributeError: 'int' object has no attribute 'startswith'
```

Non-string keys in nested closed protocol objects can reach the same
`startswith()` assumption. The resulting exception surface depends on the
malformed value's location rather than on the public codec boundary.

**Recommended change:** replace the narrow number checker with a recursive
runtime JSON-shape validator that:

- rejects non-object top-level records;
- requires all object keys to be exact strings;
- rejects tuples and unsupported host values;
- rejects non-finite numbers;
- raises `TranscriptValidationError` consistently.

Add tests for non-object records and non-string keys in the envelope,
configuration, nested protocol objects, extensions, and open application data.

## Code-quality and architecture findings

### 1. Split the 569-line lifecycle validator into cohesive private functions

**Location:** `src/termverify/transcript.py:224-792`

`_validate_lifecycle()` currently performs all of the following:

- record-kind and payload-member closure;
- start and terminal placement;
- run identity and record-ID uniqueness;
- replay-subject validation;
- deterministic configuration validation;
- terminal payload validation;
- capability negotiation and effective-value comparison;
- clock configuration and clock transitions;
- all input payload validation;
- diagnostic validation;
- observation, UI, frame, event, and process validation;
- process-exit and terminal-result coherence;
- execution-epoch validation.

The function has 569 physical lines. Radon measured cyclomatic complexity
`F (276)`. The clock configuration predicate is physically separated from most
other configuration validation, illustrating how related invariants are
already becoming difficult to locate and review together.

**Recommended change:** retain one procedural orchestrator but extract focused,
same-module helpers such as:

1. `_validate_record_kinds_and_payload_closure`;
2. `_validate_run_identity`;
3. `_validate_run_started` and `_validate_run_config`;
4. `_validate_terminal_payload`;
5. `_validate_negotiation`;
6. `_validate_input_payloads`;
7. `_validate_diagnostics_and_observations`;
8. `_validate_execution_epochs`;
9. `_validate_evidence_times_and_exit_coherence`.

Preserve validation order and existing public diagnostics with characterization
tests. Do not replace the function with validator classes, visitors, a generic
rules engine, or dynamic registration.

### 2. Remove the adapter contract's dependency on a codec-private helper

**Locations:**

- `src/termverify/adapter.py:12`
- `src/termverify/transcript.py:855-925`

The framework-neutral adapter contract imports the private
`_is_well_formed_language_tag` predicate from the transcript codec. A codec
refactoring can therefore break the adapter module even though the two are
separate public compatibility boundaries.

**Recommended change:** move only the locale grammar predicate and its fixed
vocabulary into a narrowly named private neutral module imported by both the
codec and adapter contract. Avoid a general-purpose validation-utilities module.

### 3. Consolidate repeated direct-runtime result classification

**Locations:**

- `src/termverify/direct.py:367-405`
- `src/termverify/direct.py:407-450`
- `src/termverify/direct.py:452-480`

`dispatch()` and `advance_clock()` repeat nearly identical classification and
validation of `EpochCompleted`, `TerminalResult`, `AdapterFailure`, and malformed
responses. The terminal branch is repeated again in `stop()`.

This is a realistic correctness-drift risk: a future terminal-evidence rule can
be corrected in two methods but missed in the third.

**Recommended change:** extract one private result-classification helper
parameterized by:

- active `at_ms`;
- whether nonterminal `EpochCompleted` is allowed;
- operation-specific failure diagnostics.

Keep each public method's input type, clock relation, state transition, and
application-port invocation explicit. Do not introduce a command hierarchy or
Template Method superclass merely to remove this duplication.

### 4. Centralize stable protocol vocabulary cautiously

Constraint order appears independently in:

- `src/termverify/transcript.py:50-58`;
- `src/termverify/adapter.py:95-103`;
- `src/termverify/direct.py:212-263`.

Payload-member vocabularies appear in:

- `src/termverify/transcript.py:71-87`;
- `src/termverify/evidence.py:40-55`.

The `JsonValue` alias is also duplicated in `transcript.py` and `evidence.py`.

**Recommended change:** share the seven constraint names and order through a
small private v1 vocabulary module. Reuse the existing JSON-value alias rather
than redeclaring it.

Do not automatically make the evidence redaction whitelist an alias for codec
validation metadata. Redaction is a security boundary, and an independent
fail-closed classification can be valuable. If the lists remain intentionally
separate, add a synchronization test covering every defined record kind.

### 5. Consider atomic replacement for persisted evidence

**Location:** `src/termverify/evidence.py:107-109`

The persistence boundary validates and sanitizes bytes before writing, so a
partial write is not an immediate confidentiality leak. Direct
`Path.write_bytes()`, however, can leave a truncated transcript if the process
or filesystem fails during the write.

A future durability slice should consider writing a temporary file in the same
directory and atomically replacing the destination. Whether to require
`fsync()` should be an explicit evidence-durability policy decision.

## Pydantic assessment

### Recommendation

Do not replace or augment canonical core validation with Pydantic at this
stage.

Pydantic would make some local object shapes and tagged unions more concise,
but it would not replace the difficult parts of the accepted contract:

- exact JSONL byte framing;
- duplicate-member detection;
- RFC 8785 canonicalization and canonical-byte comparison;
- extension-member semantics;
- contiguous sequence and record identity;
- capability ordering and projected uniqueness;
- manual-clock evolution;
- execution epochs and terminal closure;
- cross-record process-exit coherence;
- safe redaction followed by semantic revalidation.

Those rules would remain custom validators or separate procedural passes. A
migration would therefore add a runtime dependency, a new error surface, and a
third model representation alongside immutable dataclasses and the deliberately
non-exhaustive JSON Schema.

Pydantic is coercive by default. Strict mode can reduce coercion, but the current
contract requires exact builtin types, rejection of scalar subclasses in public
immutable values, and transitive immutability of arbitrary JSON-shaped data.
Pydantic's frozen models do not by themselves supply the current deep-freeze
semantics. Achieving parity would require enough custom validation to recreate
much of the existing implementation.

### Possible future use

If TermVerify later needs ergonomic parsing for CLI configuration, web requests,
or plugin manifests, a separate optional Pydantic-based edge adapter could be
useful. It should:

- use strict models;
- convert immediately into the existing frozen core values;
- remain outside canonical transcript acceptance;
- be tested against the existing adversarial corpus;
- not make generated Pydantic schemas authoritative.

No current use case justifies adding that layer to the canonical core.

## Inheritance and SOLID assessment

### Inheritance

Do not introduce implementation inheritance or domain base classes for inputs,
receipts, records, or results.

The seven receipt types intentionally encode constraint identity. Exact-type
checks ensure that a receipt for one constraint cannot substitute for another.
Likewise, input and result unions intentionally define closed runtime contracts.
A common implementation superclass would add little behavior while weakening
or complicating those exact-type boundaries.

`DirectApplication(ConstraintPorts, Protocol)` is appropriate structural
interface composition, not problematic implementation inheritance. Although it
is broad, one application object intentionally binds enforcement and execution
to the same subject session. Split ownership only when a real implementation
demonstrates a second boundary; do not add plumbing solely to satisfy an
interface-count heuristic.

### SOLID

- **Single Responsibility:** the weakest area. `_validate_lifecycle()` and, to a
  lesser extent, `DirectAdapter.start()` contain too many distinct phases.
- **Open/Closed:** dynamic extensibility is not a goal for a closed, versioned
  canonical protocol. Explicit edits for a new protocol version are safer than
  plugin validators.
- **Liskov Substitution:** exact subtype rejection is an intentional invariant at
  the immutable and enforcement boundaries. Traditional class inheritance would
  work against it.
- **Interface Segregation:** `Adapter` and `ConstraintPorts` are appropriately
  focused. `DirectApplication` is broader by deliberate session-identity design.
- **Dependency Inversion:** strong. The deterministic runtime depends on
  application-facing protocols rather than ambient clock, terminal, filesystem,
  network, or framework implementations.

The useful SOLID improvement is therefore smaller cohesive pure functions and
narrowly shared vocabulary, not additional pattern classes.

## Confirmed-good areas

The review specifically confirmed the following strengths:

- parser and serializer share envelope and lifecycle validation;
- duplicate JSON members and noncanonical JSON are rejected;
- RFC 8785 dependency failures are normalized;
- seed bounds use lexical validation and reject oversized values cleanly;
- tuples and non-finite numbers are rejected at the serializer boundary;
- execution lifecycle enforces readiness, single-flight epochs, stop finality,
  terminal closure, and process-exit finality;
- exited-process evidence must match `run.finished` where required;
- nested generic protocol objects are closed while application-defined JSON
  values remain open;
- receipts are exact-type, run-bound, ordered, and effective-value-bound;
- deferred enforcement boundaries cannot be claimed through receipts;
- `DirectAdapter` is single-use and single-flight and rejects reentrant and
  concurrent operations;
- readiness publication and initial manual time are atomic;
- application exceptions become stable structured failures without leaking host
  exception text;
- JSON-bearing adapter values are copied and transitively frozen;
- safe evidence persistence follows copy, validate, classify/redact, revalidate,
  then write;
- evidence tests cover replay selectors, extensions, clipboard, application
  state, event data, frames, diagnostics, sandbox identity, and network hosts;
- schema scope is explicitly and accurately non-exhaustive;
- focused negative tests and Hypothesis-generated lifecycle tests provide strong
  behavioral coverage.

## Verification evidence

Commands and results at the reviewed revision:

```text
uv --no-config run pytest --cov --cov-report=term-missing
  477 passed
  92% total branch coverage

uv --no-config run ruff check .
  passed

uv --no-config run ruff format --check .
  passed

uv --no-config run mypy src tests scripts
  passed, no issues in 16 source files

radon cc src -s -a
  average complexity B (6.46)
  _validate_lifecycle: F (276)
```

The review and probes did not modify production code, tests, fixtures, schemas,
or existing documentation. No issue, commit, or pull request was created during
the review.

## Recommended implementation order

1. Fix type-aware capability effective-value comparison and add exact numeric-type
   regression probes.
2. Enforce diagnostic timestamp coherence in public result aggregates while
   retaining adapter boundary checks.
3. Normalize malformed runtime JSON shapes to `TranscriptValidationError`.
4. Split `_validate_lifecycle()` into cohesive private helpers without behavioral
   change.
5. Move locale grammar validation out of the transcript-private namespace.
6. Consolidate direct-runtime result classification.
7. Centralize only stable shared vocabulary and add synchronization tests where
   security metadata remains intentionally independent.
8. Address atomic evidence replacement in a separately scoped durability change.

The first three items are focused correctness slices. The remaining items are
reviewability and drift-reduction work and should not be bundled with protocol
semantics changes.
