# Adversarial correctness and code-quality review

- **Date:** 2026-07-16
- **Revision reviewed:** `97778b99cdb03081335f70d5f4ed3b8ae6a0ef7c`
- **Branch:** `main`
- **Reviewer:** Claude Opus 4.8, primary review plus three independent
  adversarial subagents (transcript codec; adapter/direct runtime; evidence
  redaction) and one empirical Pydantic feasibility prototype
- **Scope:** `src/termverify/`, `scripts/validate_evidence_governance.py`, the
  v1 JSON Schema, and the protocol/architecture/evidence-governance knowledge
  pages
- **Focus:** correctness under hostile input, the Pydantic question, and the
  inheritance/SOLID question
- **Status:** findings for maintainer triage; no code changed by this review
- **Peer review:** a second independent report,
  [`adversarial-correctness-and-code-quality-review-gpt-5.6-sol-2026-07-16.md`](adversarial-correctness-and-code-quality-review-gpt-5.6-sol-2026-07-16.md),
  reviewed the same revision. Convergence and one substantive disagreement are
  recorded under [Relationship to the peer review](#relationship-to-the-peer-review).

## Executive summary

The deterministic core is unusually well defended. `transcript.py`,
`adapter.py`, and `direct.py` survived sustained adversarial attack — including
differential fuzzing of the BCP-47 parser and the execution-epoch state machine
against specification-derived reference models — with **no high-severity
correctness findings**. The canonical re-serialization check in `_parse_line()`
collapses most of the wire attack surface, and the `type(x) is Y` discipline in
the adapter contract holds everywhere it is claimed to hold.

Every confirmed defect of consequence is in **one module: `evidence.py`**, the
redaction layer. It fails in both directions:

1. **Secrets reach disk.** The camelCase key splitter never splits an all-caps
   prefix, so `APIToken`, `AWSSecret`, and `DBPassword` are not treated as
   sensitive. Because `scripts/validate_evidence_governance.py` gates
   *committed fixtures* on `redact_evidence()`, a live credential under such a
   key can be committed to the public repository today. The credential pattern
   list independently misses every credential format of the last decade (AWS,
   JWT, Slack, private-key bodies).
2. **Valid transcripts cannot be persisted.** The credential regexes are
   applied to grammar-constrained structural fields where a credential cannot
   hide. `sk-[A-Za-z0-9-]{20,}` collides with the identifier grammar and with
   the ISO 639-1 code for Slovak, so a legal `run_id`, `locale`, or subject
   selector is rewritten to a redaction marker and then fails the module's own
   re-validation.

On the two design questions:

- **Pydantic: do not adopt, on either surface.** This is not a matter of taste.
  The two properties the accepted contract is explicitly built on — transitive
  immutability and *rejection* of type impostors — are properties Pydantic
  cannot express and, in the second case, quietly inverts. Adopting it on the
  wire surface would additionally **delete** a working duplicate-member check.
  Evidence is in [the Pydantic assessment](#the-pydantic-question).
- **Inheritance: do not add.** The flat frozen-dataclass plus structural-
  `Protocol` design is correct and is doing real static work. The genuine
  structural problem is duplication, not a missing hierarchy: a 569-line
  validator, a result-classification tail copied three times verbatim, and the
  seven-constraint vocabulary written out six times.

The correctness of the core means the recommended refactors are unusually safe
to perform: they are behavior-preserving decompositions backed by 477 passing
tests at 92% coverage.

## Method

Four independent lines of attack were run against the revision above, each
required to substantiate findings by execution rather than inspection, and to
label every finding CONFIRMED (executed or traced) or PLAUSIBLE:

1. **Transcript codec.** Attempted to smuggle an invalid transcript past
   `parse_transcript()` and to force a valid transcript to be wrongly rejected.
2. **Adapter and direct runtime.** Attacked receipt binding, `ManualTime`,
   `freeze_json()`, single-flight state transitions, and the abort paths.
3. **Evidence redaction.** Threat model: the attacker controls transcript
   content (application state, event data, frame lines, `x-` members,
   identifiers). Goal 1, leak a secret to disk; goal 2, deny persistence of a
   legitimate transcript.
4. **Pydantic feasibility.** A prototype study against pydantic 2.13.4 /
   pydantic-core 2.46.4, required to run each decisive case rather than reason
   about it.

Every finding reproduced below was **re-verified by the primary reviewer
independently** of the subagent that first reported it. Findings that could not
be substantiated were discarded rather than reported as speculation; the
discarded set is recorded under [Attacks that
failed](#attacks-that-failed-confirmed-good), because negative results are
evidence about where the hardening budget has already paid off.

Documented deferrals — resource ceilings, timezone registry policy, key and
terminal capability registries, network allow-list enforcement, sensitive-mode
persistence — were treated as acknowledged scope and are not reported as
defects.

## Ranked correctness findings

### 1. High: an unredacted credential can pass the committed-fixture governance gate

**Locations:** `src/termverify/evidence.py:39` (`_CAMEL_CASE_BOUNDARY`),
`evidence.py:297-307`, `scripts/validate_evidence_governance.py:110,134,215-225`

`_CAMEL_CASE_BOUNDARY` is `(?<=[a-z0-9])(?=[A-Z])`. The lookbehind requires a
**lowercase** character before the capital, so a key whose sensitive word is
preceded by an all-caps run never splits into parts:

| key | `_key_parts()` | `_is_sensitive_key()` |
| --- | --- | --- |
| `api_token` | `['api', 'token']` | `True` |
| `myTOKEN` | `['my', 'token']` | `True` |
| `authorization` | `['authorization']` | `True` |
| `APIToken` | `['apitoken']` | **`False`** |
| `AWSSecret` | `['awssecret']` | **`False`** |
| `DBPassword` | `['dbpassword']` | **`False`** |
| `GHToken` | `['ghtoken']` | **`False`** |
| `XToken` | `['xtoken']` | **`False`** |

In isolation this is a redaction miss. It is escalated to High by
`scripts/validate_evidence_governance.py`, which gates fixtures committed to the
repository on `redact_evidence()` at three layers: a raw-text scan (line 110), a
per-member `_safety_object` hook (line 215), and a parsed-value scan (line 134).
All three delegate to the same two defenses — the credential patterns and the
key-name check — so a secret defeats all three at once when it defeats both.

Executed against the real gate:

```
key        secret                     text-scan  value-scan  verdict
api_token  AKIAIOSFODNN7EXAMPLE       False      True        REJECTED
APIToken   AKIAIOSFODNN7EXAMPLE       False      False       *** PASSES GOVERNANCE ***
AWSSecret  eyJhbGciOiJIUzI1NiJ9.eyJ…  False      False       *** PASSES GOVERNANCE ***
```

The `api_token` control is correctly rejected, which is what makes this a live
gap rather than a theoretical one: the gate works, and the splitter is the part
that fails.

**Recommendation.** Add the standard acronym boundary as an alternative:

```python
_CAMEL_CASE_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
```

This splits `APIToken` → `['api', 'token']` and `AWSSecret` → `['aws',
'secret']` while leaving every currently-passing case unchanged. Add the table
above as a regression test; it is the cheapest fix in this report and closes the
only path by which this repository can publish a secret.

### 2. High: regex screening is the only defense on attacker-controlled semantic members

**Locations:** `src/termverify/evidence.py:28-38` (`_CREDENTIAL_PATTERNS`),
`evidence.py:166-191`, `evidence.py:245-275`

`_CREDENTIAL_PATTERNS` recognizes `Bearer`, HTTP Basic, GitHub `gh[pousr]_`,
`sk-`, `key=value` shapes, and the `-----BEGIN … PRIVATE KEY-----` **header
line only**. Confirmed to survive `redact_evidence()` unmodified:

- AWS access key IDs — `AKIAIOSFODNN7EXAMPLE`
- JSON Web Tokens — `eyJhbGciOiJIUzI1NiJ9.…`
- Slack tokens — `xoxb-…`, `xoxp-…`
- Private-key **body** lines — `MIIEvQIBADANBgkq…` (only the header matches)

This is acceptable for fields that are blanket-redacted regardless of content,
and the blanket set is genuinely sound: `observation.state`, `events[].data`,
`frame.lines`, `input.text`/`input.clipboard_set` `text`, diagnostic `message`
and `details`, and all `x-` **values** are unconditionally replaced. Frame lines
being blanket-redacted also neutralizes the split-private-key case there.

The exposure is the complement — members that are *known* to the schema, are
therefore never blanket-redacted, and accept arbitrary strings, leaving the
pattern list as the sole screen:

| Member | evidence.py |
| --- | --- |
| `ui.regions[].id`, `ui.regions[].role` | 268 |
| `ui.focus`, `ui.mode` | 259 |
| `input.key.keys[]` | `_PAYLOAD_MEMBERS:45` |
| `config.terminal.capabilities[]` | 218 |
| `config.locale`, `config.timezone`, `config.seed` | 209 (and again as `capability.result.effective`, 245-255) |
| `diagnostic.code`, `error.code`, `run.unsupported.code` | 198 |
| `exit.value` when `kind == "signal"` | 157 |

`ui.regions[].role` is the sharpest instance: it accepts arbitrary strings, so
private-key material can be smuggled through it a line at a time, and the
`-----BEGIN-----` header — the only part the pattern list would catch — need
never appear.

Two structural gaps compound this. Dict **keys** are never redacted, only
values, so `record["x-AKIAIOSFODNN7EXAMPLE"]` persists its key intact while its
value is replaced; the validator permits any `x-`-prefixed key, making key names
an unbounded attacker-controlled channel. And `_redact_constraint_config()`
(`evidence.py:245-255`) has no branch for `seed`, `locale`, or `timezone`, so
those `effective` values are screened by regex alone — consistent with how
`config` treats them, so no re-validation break, but the same exposure twice.

**Recommendation.** Decide explicitly, and write the decision into
`docs/knowledge/evidence-governance.md`, whether these members are
**attacker-controlled free text** (then blanket-redact or constrain them to a
grammar, as `run_id` already is) or **trusted vocabulary** (then say so, and the
regex screen is redundant there). Extending the pattern list is worth doing —
AWS, JWT, Slack, and PEM bodies are cheap additions — but a pattern list is a
denylist, and a denylist is the wrong primary defense for a field whose whole
content is attacker-chosen. The blanket-redaction set is the right model; the
question is which members belong in it.

### 3. Medium: valid transcripts cannot be persisted (`sk-` grammar collision)

**Locations:** `src/termverify/evidence.py:32`, `evidence.py:97-100`,
`evidence.py:333-344`; interacts with `transcript.py:19`
(`_IDENTIFIER_PATTERN`) and `transcript.py:855` (`_is_well_formed_language_tag`)

`_redact_validated_transcript_record()` applies `redact_evidence()` to the
**whole record, including the envelope**. The pattern `\bsk-[A-Za-z0-9-]{20,}\b`
overlaps two grammars the validator itself enforces, so legal values are
rewritten into redaction markers and then fail the module's own final
`serialize_transcript(sanitized)` at `evidence.py:107`. Three confirmed
instances:

```
valid run_id per transcript grammar?  True          # "sk-" + "a"*22
redact_evidence(run_id) ->            <redacted:credential>
      => TranscriptValidationError: record identifier grammar is invalid

well-formed language tag?             True          # "sk-aaaaaaaa-bbbbbbbb-ccccc"
redact_evidence(locale) ->            <redacted:credential>
      => TranscriptValidationError: run.started locale is invalid
```

and a legitimate subject selector — `subject.fixture.id =
"sk-fixture-scenario-alpha"` — raises `ValueError: replay subject contains a
credential-shaped selector` from `_contains_credential_shaped_selector()`.

The locale case is systemic rather than contrived: `sk` is the ISO 639-1 code
for Slovak, so any Slovak locale with sufficient variant subtags collides.
`gh[pousr]_` cannot reach this, because underscore is outside the identifier
grammar; `sk-` is the whole exposure.

**Recommendation.** Scope redaction to payload and free-text positions. The
envelope (`protocol`, `run_id`, `seq`, `id`, `kind`), `config.locale`, and the
subject selectors are all constrained by the validator to grammars in which a
credential provably cannot hide — `[a-z0-9._-]+` cannot express a JWT, an AWS
key, or a PEM block. Screening them buys nothing and is the sole cause of all
three failures. This fix and finding 1's are independent and can land
separately.

### 4. Low: `serialize_transcript()` leaks `AttributeError` on malformed input

**Location:** `src/termverify/transcript.py:127-138`

Independently confirmed; also reported as finding 3 by the peer review, whose
analysis is correct and is not duplicated here.

```
[{'protocol': 'termverify.transcript/v1', …, 'payload': None}]
      -> TranscriptValidationError (public, good)
['not-a-dict']  -> LEAKED AttributeError: 'str' object has no attribute 'keys'
[42]            -> LEAKED AttributeError: 'int' object has no attribute 'keys'
```

`_validate_envelope()` reaches `record.keys()` before establishing that
`record` is a dict. The codec's documented public failure mode is
`TranscriptValidationError`; a caller cannot reasonably be asked to also catch
`AttributeError`. A `isinstance(record, dict)` guard at the top of
`_validate_envelope()` fixes it.

### 5. Low: `Started`/`StartTerminated` enforce clock coherence for the observation but not for diagnostics

**Locations:** `src/termverify/adapter.py:833`, `adapter.py:915-919`,
`adapter.py:989`

`Started(constraints, observation@0, diagnostics=(Diagnostic@999,))` constructs
successfully. `_validate_diagnostics()` is type-only and takes no reference time
to check against.

This is **not** the documented "cross-record rules belong to the adapter and
runner" carve-out — it is an *intra*-record inconsistency, and `Started` already
took on exactly this job for its observation, which makes the asymmetry look
accidental rather than chosen. There is no reachable defect today, because
`DirectAdapter` checks diagnostic times on every path (`direct.py:341-343`, and
`_terminal_time_is_valid()` at `direct.py:135-138`). It is a hole only for a
different `Adapter` implementation constructing these public aggregates
directly — which the contract explicitly invites, since `__all__` is the
compatibility boundary.

The peer review reports this as its finding 2 and ranks it Medium. That is a
defensible read; the ranking difference is about whether a non-`DirectAdapter`
producer is in scope today, not about the facts.

**Recommendation.** Give `_validate_diagnostics()` an optional expected `at_ms`
and pass the effective initial clock from `Started`/`StartTerminated`, and the
observation time from `EpochCompleted`/`TerminalResult`. This moves a check
`DirectAdapter` already performs into the value contract, where every producer
gets it.

### 6. Low: the abort path discards the failure details exactly when they matter most

**Location:** `src/termverify/direct.py:179-194`

When an application returns `AdapterFailure("adapter-runtime-failed", "boom",
{"stack": "deep", "errno": 7})` and abort **succeeds**, `details` survives.
When abort **fails**, `details` is replaced wholesale with `{"abort":
"failed"}`, destroying the application's diagnostics in the one case where the
operator most needs them. `code` and `message` survive both.

This mirrors `_abort_start()` (`direct.py:168-177`), whose behavior *is*
deliberate and tested — but
`test_startup_abort_failure_is_recorded_without_losing_original_failure` asserts
`details == {"abort": "failed"}` exactly, and "without losing" in its name
refers to `code` and `message`. The runtime path with application-supplied
details is covered by **no** test: every existing abort test uses an application
that raises, so there are never any details to lose. The gap is in the test
suite as much as the code.

**Recommendation.** Merge rather than replace — `{**original_details, "abort":
"failed"}` when the original is a mapping, or nest under a reserved key — and
add the missing case to the test suite.

### 7. Low: `Started` is constructed before the state is committed

**Location:** `src/termverify/direct.py:359-365`

Every other terminal path in `DirectAdapter` calls `_set_state("terminal")`
*before* constructing its result value. This is the only inverted one. If
`Started(...)` raised, the adapter would wedge in `"initializing"` forever,
`abort()` would never run, and the initialized application would leak; `start`,
`dispatch`, and `stop` would then all raise `RuntimeError`. Confirmed by
injecting an invariant-bypassing `EpochCompleted`: state stays
`"initializing"`, abort count 0.

**Not reachable from a conforming application.** `EpochCompleted.__post_init__`
already forbids exited-process evidence, and the `at_ms` check at
`direct.py:338-344` mirrors `Started`'s at `adapter.py:833` exactly — the two
are provably equal through the negotiated clock receipt. This is
defense-in-depth only. Committing the state in a `finally`, or constructing
`Started` before `_set_time_and_state()`, removes the asymmetry for the cost of
one line.

## The Pydantic question

**Recommendation: do not adopt Pydantic, on either surface. Do not adopt
`attrs` or `msgspec` either. Keep frozen slotted dataclasses and the
hand-written codec.**

This is not a stylistic preference, and it is not the usual
"hand-rolled-is-fine" defense. The two properties the accepted contract is built
on are properties Pydantic **cannot express**, and in one case **inverts**. All
results below were executed against pydantic 2.13.4 / pydantic-core 2.46.4; the
two decisive ones were re-run independently by the primary reviewer.

### `frozen=True` does not deep-freeze — the immutability requirement is unmet

The design contract requires that "mutating the caller-owned source after
construction cannot change an observation, diagnostic, failure, or outcome",
achieved today by `freeze_json()` copying arrays to tuples and objects to
mapping proxies. Pydantic's `frozen=True` blocks *rebinding the field*, not
mutating *through* it:

```python
class Doc(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True)
    data: JsonValue          # pydantic's own built-in JSON type

d = Doc(data={"a": [1, {"deep": "value"}]})
d.data = {}                           # rebind field   -> REJECTED ValidationError
d.data["a"].append("INJECTED")        # mutate through -> ACCEPTED
d.data["a"][1]["deep"] = "MUTATED"    # mutate through -> ACCEPTED
# d.data == {'a': [1, {'deep': 'MUTATED'}, 'INJECTED']}
```

No field type achieves transitive freezing: `dict[str, Any]`, `dict[str,
object]`, `tuple[Any, ...]`, `Mapping[str, Any]` (which yields a plain `dict`,
not a proxy), and pydantic's own `JsonValue` were all surveyed. The only
construction that worked was `Annotated[Any, BeforeValidator(freeze_json)]` —
that is, keeping `freeze_json()` unchanged and letting Pydantic call it.
**Pydantic contributes the call site and none of the logic on the single hardest
requirement.**

### Type impostors are retained or silently downcast — never rejected

The contract requires that impostors are "rejected rather than retained or
compared polymorphically". Pydantic offers three behaviors, none of which is
that:

```
dict[str, Any]        accepted; type=Liar  eq-impostor=True  mutable-attr=['PAYLOAD']  -> RETAINS
dict[str, object]     accepted; type=Liar  eq-impostor=True  mutable-attr=['PAYLOAD']  -> RETAINS
JsonValue (pydantic)  accepted; type=str   eq-impostor=False                           -> silently downcasts
top-level scalar      ACCEPTED, not rejected; type(n)=int, type(s)=str                 -> silently downcasts
```

Re-verified independently:

```
impostor in dict[str,object] -> retained as Liar | always-equal: True
```

In `Any`/`object` fields Pydantic **retains the mutable attribute and the
always-true `__eq__` intact** — precisely the breach the design decision exists
to prevent. At top level and inside `JsonValue` it does something arguably
worse: accepts and quietly downcasts, failing open and silently. To reject, one
writes `if type(v) is not int: raise` — the code already in `adapter.py`.

### Default mode inverts the failure mode

```
n="5"   -> ACCEPTED n=5      # str -> int
n=5.0   -> ACCEPTED n=5      # float -> int, silent truncation risk
n=True  -> ACCEPTED n=1      # bool -> int
b="yes" -> ACCEPTED b=True
```

`strict=True` does correctly reject `bool`→`int` — a genuine win worth roughly
the 13 lines of `_require_plain_int()`. But safety would then depend on never
omitting `strict=True` across ~30 models. The status quo is strict *by
construction*; Pydantic is lax by default with strictness opt-in. For a library
whose entire value proposition is deterministic strictness, that inverts the
failure mode.

### On the wire surface, adoption would delete a working check

Canonicality is a property of the **encoding**. Every schema library validates
the **decoded value**, which by definition no longer knows member order,
duplicate members, or whitespace, so `if _canonical_record(record) != line` has
no replacement in any of them. Worse:

```
duplicate member {"seq":0,"seq":1} -> pydantic ACCEPTED, seq=1   # SILENTLY DROPPED
```

`transcript.py` catches this today via `json.loads(...,
object_pairs_hook=_reject_duplicate_members)`. **pydantic-core's JSON path
exposes no equivalent hook**, so adopting it would remove a protocol check that
currently works. `msgspec` drops duplicates identically.

### The declarative rules already exist, declaratively

Classifying `transcript.py`'s 996 lines (approximate, ±5%):

| Bucket | Lines | Notes |
| --- | --- | --- |
| Declaratively expressible | ~470 | envelope, payload members, config/exit/observation shapes, `_validate_replay_subject()` |
| **Cannot** be expressed by any schema library | ~380 | byte canonicality and duplicates ~80; sequence invariants ~230; BCP-47 grammar ~71 |
| Imports and constants | ~100 | |

The ~380 is unreachable for any library: manual-clock progression, capability
ordering and effective-matches-config, exactly-one-final-terminal-record, the
epoch state machine, sortedness (JSON Schema has `uniqueItems`, not
sortedness), and `_is_well_formed_language_tag()`. So roughly 40% of the module
survives regardless.

The ~470 is the trap. **It is not greenfield — it is already declarative, in the
201-line `schemas/termverify.transcript/v1.schema.json`**, which expresses the
closed-plus-extensions rule natively:

```json
"patternProperties": {"^x-": {}}, "additionalProperties": false
```

Pydantic needs `extra="allow"` plus a hand-written validator *per model* (~5
lines × ~20 shapes) to reproduce what the schema states in one line. Adopting it
would create a **third** encoding of the wire rules.

The apparent redundancy between the schema and the validator is deliberate and
load-bearing, not accidental drift. `jsonschema` appears only in
`tests/test_transcript_schema.py`, never in `src/`. The schema is a published
interop artifact (`$id: https://termverify.dev/schemas/…`) for non-Python
implementers and must exist regardless of what Python does, and the tests encode
the boundary *as a specification* — asserting that the schema accepts what only
the runtime can reject:

```python
def test_runtime_owns_terminal_capability_ordering_beyond_schema():
    assert Draft202012Validator(_schema()).is_valid(records[0])
    with pytest.raises(TranscriptValidationError, match="terminal"):
```

The project has already answered this question deliberately and pinned the
answer with tests.

### Alternatives

- **`attrs`** — closest fit. `frozen`+`slots` works (64 B), and it rejects
  `True` and `Evil(5)` — but only via the *identical hand-written predicates*,
  relocated from `__post_init__` to `field(validator=...)`. Nested data stays
  mutable. A dependency in exchange for code motion.
- **`msgspec`** — disqualified for the value surface: `Struct.__init__`
  **does not validate at all** (`MStruct(n=True)` → `type(n) == bool`);
  strictness exists only on `decode`. Its decoder is genuinely strict, but it
  drops duplicate members and cannot see canonicality.
- **Plain frozen dataclasses (status quo)** — 40 B, rejects everything
  correctly, zero runtime dependencies.

### Cost side

`pydantic` pulls in `pydantic-core`, a compiled Rust binary, imposed on every
downstream consumer of a library that today has **exactly one** runtime
dependency (`rfc8785`, itself justified in a dedicated ADR). Pydantic models
also carry `__dict__` (256 B vs 48 B for `dataclass(frozen=True, slots=True)`,
5.3×), have no `slots=True` equivalent, and a frozen model holding a frozen JSON
field is **unhashable**, because frozen models hash a tuple of their field
values.

Measured against AGENTS.md's bar — *"do not add a dependency … without
documenting the rationale and verification plan"* — **there is no rationale to
document.** The ~1000 lines of `adapter.py` are not incidental boilerplate that
a library would absorb; they *are* the contract, and the evidence above shows
the library would quietly weaken it.

### If declarative coverage is the actual goal

`v1.schema.json`'s own `$comment` records that it specializes `run.started` only
and that other kinds currently receive envelope validation alone. **Extend that
schema.** It is the published artifact, it already expresses the `x-` rule
natively, it costs zero runtime dependencies, and `jsonschema` is already a dev
dependency with an established test pattern for asserting the
schema-versus-runtime boundary.

## The inheritance and SOLID question

**Recommendation: do not add implementation inheritance or domain base classes.**
The existing design is already the right one, and it is doing real work that a
hierarchy would destroy. The genuine problem is duplication.

### Why inheritance would be a regression here

- **Liskov substitutability is deliberately refused.** `type(x) is Y` throughout
  the adapter contract exists precisely so that a subclass is *not* an
  acceptable substitute — that is the documented "equality impostor" defense. A
  base class for the seven receipt types would reintroduce, as a design goal,
  the substitutability the contract spends its budget rejecting. The seven
  receipts being "intentionally distinct" is what lets strict mypy statically
  reject substituting a clock receipt for a seed receipt.
- **Interface segregation and dependency inversion are already right.**
  `ConstraintPorts` and `Adapter` are structural `Protocol`s; the deterministic
  runtime depends on those abstractions, not on implementations, with no
  ambient state. This is textbook DIP, achieved without a hierarchy.
- **Closed unions beat open polymorphism for a versioned protocol.**
  `StartResult`, `EpochResult`, and `EnforcementReceipt` are PEP 695 unions that
  mypy checks exhaustively. An open hierarchy would trade a compile-time
  exhaustiveness guarantee for runtime dispatch — the wrong direction for a
  closed, versioned wire contract.

### 1. Split the 569-line `_validate_lifecycle()` — the single largest quality issue

Measured: **569 lines, ~203 branch points**, against a project-wide next-largest
of 71.

| Module | Function | Lines | Branch points |
| --- | --- | --- | --- |
| `transcript.py` | `_validate_lifecycle` | **569** | **~203** |
| `transcript.py` | `_is_well_formed_language_tag` | 71 | ~33 |
| `direct.py` | `start` | 170 | ~15 |
| `transcript.py` | `_validate_execution_epochs` | 44 | ~16 |

It discharges roughly fifteen distinct responsibilities: record kinds, payload
members, `run.started` placement and members, terminal-record placement,
`run_id`/`id` uniqueness, the replay subject, six config constraints, terminal
payloads, capability negotiation and ordering, epoch validation, input records,
diagnostics, observations, and evidence times.

The instructive part is that **the fix already exists in this codebase**:
`adapter.py` demonstrates exactly the target pattern — small, named, per-type
validators — and `transcript.py` simply does not follow it. Extract
`_validate_config()`, `_validate_capability_negotiation()`,
`_validate_input_records()`, `_validate_observation_records()`, and
`_validate_terminal_record()` as pure functions over the already-parsed records.

This is a behavior-preserving decomposition, and the fuzzing results in
[Attacks that failed](#attacks-that-failed-confirmed-good) mean it can be done
with unusual confidence: the differential models built during this review can be
retained as property tests to prove the refactor changed nothing.

### 2. Consolidate the direct-runtime result classification

`dispatch()` and `advance_clock()` were diffed mechanically. Their entire
28-line tails are **byte-identical**; the only deltas are the intended ones:

```diff
-            result = self._application.dispatch(input_event)
+            result = self._application.advance_clock(input_event)
         except Exception:
-            return self._abort_runtime("application dispatch failed", ...)
+            return self._abort_runtime("application clock advance failed", ...)
```

`stop()` duplicates the terminal-handling half again. Three copies of the
epoch-result classification means three places to fix any future defect in it —
and findings 6 and 7 are both instances of exactly this class of asymmetry
creeping into one copy. Extract a single
`_run_epoch(port_call, input_event, failure_message)`; the `Callable` seam is
already the established idiom in this module (`_negotiate_constraint()`).

Note the one benign asymmetry found while diffing: `dispatch()` omits the
`self._manual_time is None` guard that `advance_clock()` has. It is harmless
(`at_ms != None` is always `True`, producing the same `ValueError`) but it is
the kind of drift that consolidation prevents.

### 3. Centralize the protocol vocabulary — six copies of the constraint order

The seven-constraint sequence is written out **six times**:

| Location | Form |
| --- | --- |
| `adapter.py:65` | `ConstraintName` `Literal` |
| `adapter.py:95` | `_CONSTRAINT_ORDER` tuple |
| `direct.py:213-263` | the inline `steps` tuple in `start()` |
| `evidence.py:209` | `frozenset` in `_redact_runtime_config()` |
| `transcript.py:50` | `_CONSTRAINTS` tuple |
| `transcript.py:275-283` | `required_config` set literal |

Adding a constraint means finding all six. This is the Open/Closed complaint in
its only form that matters here — not runtime extensibility, which is
explicitly not a goal for a closed versioned protocol, but the cost and risk of
a *deliberate* protocol revision.

The `_PAYLOAD_MEMBERS` table is duplicated between `transcript.py:80` and
`evidence.py:40`, and **has already drifted**:

```
kinds only in evidence:   ['capability.result', 'run.started']
kinds only in transcript: []
```

No live bug — `transcript.py` validates those two kinds inline instead — but the
drift is the point: the copies are diverging, silently, with nothing to detect
it.

There is a latent hazard in the same area. `transcript.py:445` does
`config[constraint]` with `constraint` drawn from `_CONSTRAINTS`, while
`required_config` at line 275 is an independent literal. They are identical
today. Should they ever diverge, that line raises a bare `KeyError` that escapes
`parse_transcript()`, whose `try` catches only `RecursionError` — turning a
protocol revision into an unhandled crash. `required_config = set(_CONSTRAINTS)`
removes the hazard for one line.

**Caveat on scope.** Centralize the *vocabulary* (the ordered constraint names,
the payload-member tables), not the *rules*. The codec and the adapter contract
should keep their own semantics: the peer review's warning against over-sharing
here is well taken, and the fact that `adapter.py:12` already reaches into the
codec for a private helper (below) shows the pull in this direction is real.

### 4. Remove the adapter contract's dependency on a codec-private helper

`adapter.py:12` imports `_is_well_formed_language_tag` — a private name — from
`termverify.transcript`. Independently identified by the peer review as its
code-quality finding 2; its analysis is correct. This inverts the intended
layering (the wire codec should not be the value contract's dependency) and
couples the public adapter surface to a name with no compatibility guarantee.
Promote the BCP-47 predicate to a shared internal module that both import.

### 5. Consider atomic replacement and mode hardening before sensitive mode

`evidence.py:108-109` uses `mkdir(parents=True, exist_ok=True)` plus
`write_bytes()`: non-atomic, and subject to the default umask. For **safe** mode
this is defensible, since the output is sanitized by construction, and
`evidence.py:87` correctly refuses `sensitive` mode outright — so there is no
live gap, and this is not reported above as a defect.

It is, however, a prerequisite. `docs/knowledge/evidence-governance.md:61-64`
requires sensitive-mode evidence to be readable only by the initiating OS
account, which needs temp-file-plus-rename, mode `0600`, and `O_EXCL`. The peer
review reaches the same conclusion. Worth doing when sensitive mode is
implemented, not before.

## Relationship to the peer review

The two reviews were conducted independently against the same revision and
**converge** on the principal conclusions: no critical defect in accepted Phase
1 behavior; reject Pydantic for the canonical core; reject implementation
inheritance; treat the 569-line validator as the principal maintainability risk;
consolidate the direct-runtime result classification; centralize protocol
vocabulary cautiously; and defer atomic persistence until sensitive mode. That
two independent adversarial passes agree on the shape of the codebase is itself
a useful signal.

They differ in coverage and in one substantive judgement.

**Coverage.** The peer review did not report the `evidence.py` redaction
defects (findings 1-3 above), which are this review's principal contribution and
include the only High-severity items in either report. This review, in turn,
did not independently discover the codec-private-helper coupling
(§[4](#4-remove-the-adapter-contracts-dependency-on-a-codec-private-helper)) or
the serializer exception leak, both credited above. Reading the two reports
together gives materially better coverage than either alone.

**Disagreement — the peer's finding 1 (Medium: "capability effective values
permit type-changing round trips").** This review **downgrades this to
cosmetic** and recommends against acting on it as a correctness defect. The
facts are agreed: `_json_equivalent()`'s scalar fallback uses `==`, so
`_json_equivalent(5.0, 5)` is `True`, and an enforced `effective` may hold a
float where the protocol specifies an integer. The disagreement is about
consequence:

```
_json_equivalent(5.0, 5)             = True
rfc8785.dumps({'initial_ms': 5.0})   = b'{"initial_ms":5}'
rfc8785.dumps({'initial_ms': 5})     = b'{"initial_ms":5}'
identical canonical bytes?           True
_json_equivalent(5.5, 5)             = False    # non-integral floats rejected
```

RFC 8785 renders an integral float and its integer to **identical canonical
bytes**, so the emitted wire output is correct and canonical in every case. On
the `parse_transcript()` path the issue cannot arise at all: `json.loads("5")`
yields an `int`, and the canonical re-check at `transcript.py:177` rejects any
float whose fractional part would survive. Non-integral floats are rejected by
`_json_equivalent()` itself; oversized integers raise `IntegerDomainError`
(a `CanonicalizationError`, already caught at `transcript.py:157`).

What remains is real but narrow: an in-memory record may hold a float where the
protocol says integer, so `parse(serialize(x))` need not preserve `x`'s Python
types. That is an API-purity observation about the programmatic serializer, not
a wire-correctness defect, and the wire is the protocol's authority. Recorded
here so the maintainer can adjudicate rather than inherit an unexplained
divergence between two reports.

## Attacks that failed (confirmed good)

Reported because negative results locate the hardening that has already paid
off, and because the differential models below are reusable as regression tests
for the refactors recommended above.

- **Line-splitting smuggling — refuted.** The hypothesis that
  `bytes.splitlines()` splits on `\x0b`, `\x0c`, `\x1c`-`\x1e`, or `U+0085`,
  allowing a record to bypass the `\r`/BOM/trailing-LF pre-checks, is **wrong**:
  unlike `str.splitlines()`, the bytes version splits only on `\n`, `\r`, and
  `\r\n`, both of the latter pre-rejected. Defense in depth also holds — raw
  `< 0x20` bytes inside a JSON string are rejected by `json.loads` strict mode.
  Verified: `b'a\x1cb\x1eb\xc2\x85c\x0cd'.splitlines()` returns a single element.
- **`_is_well_formed_language_tag()` — clean.** Differentially fuzzed against a
  regex built directly from the RFC 5646 ABNF plus the duplicate-variant and
  duplicate-singleton prohibitions: **0 divergences across ~3M generated tags**
  over three subtag pools. The grandfathered set is complete (all 26 tags).
- **`_validate_execution_epochs()` — clean.** Differentially fuzzed against a
  reference model transcribed from the specification's epoch rules: **0
  divergences over all 4ⁿ token sequences for n ≤ 7**.
- **Partial-negotiation body records — safe.** Body records provably cannot
  exist unless all seven capability results are present (both the
  `negotiation_failed` and `run.unsupported` branches force the body slice
  empty), so skipping `_validate_execution_epochs()` otherwise is behaviorally
  identical to calling it.
- **`_validate_evidence_times()` `cast(int, …)` — safe.** Body kinds are
  provably a subset of `{input.*, diagnostic, observation}`, each of which
  validates `at_ms` as a non-`bool` non-negative `int` beforehand.
- **Envelope `x-` spoofing — safe.** Keys are constrained to exactly
  `required ∪ {x-*}` by a superset *and* subset check; `x-seq` cannot shadow
  `seq`.
- **Receipt binding with `zip(strict=False)` — correct, not a hole.**
  `_validate_receipt_prefix()` rejects over-long prefixes first, so `receipts`
  is always the shortest input and every receipt is bound-checked.
  `strict=True` would break the legitimate prefix caller.
- **`ManualTime`, `ExitStatus`, `freeze_json()` — fail closed.**
  `ManualTime(True)` and foreign `int` subclasses raise `TypeError`;
  `ExitStatus("code", True)` raises `ValueError`; `str`-subclass dict keys and
  values raise `TypeError`; `list`/`dict` subclasses are accepted but *copied*,
  so immutability holds.
- **Equality impostors in negotiation — unreachable.** Every receipt's
  `effective` is exact-type-checked in `__post_init__` before any `==` runs.
- **Single-flight thread safety — holds.** The `idle → active` test-and-set is
  atomic under `_state_lock`; a concurrent second `dispatch()` observes
  `"active"` and raises. Making the application call outside the lock is correct
  and necessary to avoid deadlock on re-entry.
- **`EnforcedConstraints` at `direct.py:281` cannot raise.**
  `_negotiate_constraint()` has already verified exact type, `run_id`, and
  `effective ==` for all seven — a superset of what `__post_init__` re-checks.
  All `cast(...)` calls in `direct.py` are truthful.
- **Fuzzing and robustness.** 200k random record sequences leaked no
  non-`TranscriptValidationError` exception; 20k-level nesting yields
  `TranscriptValidationError` via the `RecursionError` handler on both paths;
  lone surrogates are rejected on both paths; all four valid fixtures round-trip
  byte-identically through `serialize_transcript(parse_transcript(x))`.
- **Redaction blanket set — sound.** `observation.state`, `events[].data`,
  `frame.lines`, `input.text`/`input.clipboard_set` `text`, diagnostic
  `message`/`details`, and all `x-` values are unconditionally replaced.
  Empty `records` raises from `serialize_transcript()` before `sanitized[0]` is
  indexed — no `IndexError` escapes. Subject `x-` members *are* redacted.

Baseline at the reviewed revision: **477 tests pass, 92% coverage**
(`adapter.py` 97%, `direct.py` 95%, `transcript.py` 91%, `evidence.py` 81% —
the weakest module is also the one with every confirmed defect).

## Recommended implementation order

Ordered by value per unit of risk. Items 1-3 are small, independent, and do not
interact with the refactors.

1. **Fix the camelCase acronym boundary** (finding 1). One regex alternative,
   plus the key table as a regression test. Closes the only path by which this
   repository can publish a live secret. Highest value in this report.
2. **Scope redaction away from grammar-constrained fields** (finding 3).
   Removes all three denial-of-evidence failures at once. Independent of item 1.
3. **Guard `_validate_envelope()` with `isinstance(record, dict)`** (finding 4)
   and **merge rather than replace abort details** (finding 6), adding the
   missing runtime-abort test.
4. **Decide and document the redaction policy for known semantic members**
   (finding 2) in `docs/knowledge/evidence-governance.md`, then extend
   `_CREDENTIAL_PATTERNS` for AWS/JWT/Slack/PEM bodies as a secondary net. The
   decision matters more than the patterns.
5. **Give `_validate_diagnostics()` an expected `at_ms`** (finding 5), moving a
   check `DirectAdapter` already performs into the value contract.
6. **Extract `_run_epoch()` in `direct.py`** (quality 2) and commit the
   `Started` state in a `finally` (finding 7) in the same change, since both
   touch the same three methods.
7. **Split `_validate_lifecycle()`** (quality 1), retaining the differential
   models from this review as property tests to prove the decomposition is
   behavior-preserving. Largest effort, largest maintainability payoff.
8. **Centralize the constraint vocabulary and payload-member tables** (quality
   3), including `required_config = set(_CONSTRAINTS)`, and **promote the BCP-47
   predicate out of the codec** (quality 4). Vocabulary only — not rules.
9. **Extend `v1.schema.json` beyond `run.started`** if broader declarative
   coverage is wanted. This is the constructive answer to the question that
   motivated the Pydantic evaluation.

Deliberately **not** recommended: adopting Pydantic, `attrs`, or `msgspec`;
adding implementation inheritance or domain base classes; and acting on the peer
review's finding 1 as a correctness defect.
