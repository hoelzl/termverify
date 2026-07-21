# Channel-Tagged Delivery Records: A Design Amendment for Handshake and Wire-Message Delivery

- **Status:** accepted — owner decisions taken in session 2026-07-20
  (issue #173 thread, decision comment
  [#issuecomment-5022762230](https://github.com/hoelzl/termverify/issues/173#issuecomment-5022762230));
  passed candidate-bound adversarial review and merged as PR #174.
  This document authorizes the implementation items in "Evidence (per
  slice)" and does not itself add code.
- **Issue:** [#173](https://github.com/hoelzl/termverify/issues/173)
  (slice 1 of the JSONL control transport), blocking analysis at
  [#issuecomment-5022366679](https://github.com/hoelzl/termverify/issues/173#issuecomment-5022366679)
- **Date:** 2026-07-20
- **Inputs:** the accepted
  [JSONL control transport design](jsonl-control-transport.md) (whose
  "Constraint semantics across the process boundary" section this amends);
  the accepted
  [cooperation-tier constraint ports design](cooperation-tier-constraint-ports.md)
  (whose per-constraint delivery contracts this extends); the frozen
  `termverify.transcript/v1` protocol text
  (`docs/knowledge/protocol.md`, `src/termverify/transcript.py`); the
  adapter contract (`src/termverify/adapter.py`
  `DeliveryRecord`/`_validate_tier_and_delivery`); the
  `termverify.enforcement-tier/v1` registry
  (`src/termverify/_enforcement_tier_v1.py`).

## Problem

The evidence model recognizes exactly one delivery channel: placement
into the subject's spawn environment, recorded as
`{"env": {...}, "cwd"?: ...}`. The `delivered` tier is defined in those
terms, `DeliveryRecord` requires a non-empty environment, and both the
contract validator and the transcript validator reject anything else.

The JSONL control transport delivers two constraints through channels
the model cannot name:

- **terminal** — dimensions are carried in `session.hello.config`, the
  wire form of `run.started`'s configuration. There is no spawn-env
  delivery, so a truthful `delivered`-tier `TerminalReceipt` is
  unconstructable: every well-formed empty-capabilities start collapses
  to `StartFailed` during receipt binding (verified 2026-07-20 in the
  slice 1 worktree).
- **clock advances** — `input.clock` delivers manual-time advances as a
  live wire message during the run. The cooperation-tier design already
  discloses this channel's absence from the receipt model ("claims
  initial delivery, nothing more"); the disclosure is correct but names
  no mechanism by which a wire delivery could ever be claimed.

The terminal constraint blocked slice 1 of issue #173; the design's own
rule ("any design-level need for a transcript change suspends the slice
and returns to the owner") fired, and the owner elected a design
amendment over a validator-shaped workaround (the rejected Option A: a
sentinel environment variable satisfying the letter of the spawn-env
validators while the actual delivery channel is the handshake).

## Decision summary

1. **The delivery record becomes channel-tagged.** `delivery` gains a
   required `channel` member from a closed set fixed by this amendment:
   `spawn-env`, `hello-config`, `wire-message`. The record is
   discriminated: `spawn-env` carries the existing `env`/`cwd` members
   with unchanged rules; the other two channels carry no additional
   members — their evidence already exists elsewhere in the transcript
   (`run.started.config` members for `hello-config`; the control
   protocol's own message records for `wire-message`).
2. **Transcript/v1 is amended in place, additively.** The owner waived
   the version-bump requirement for this amendment (early lifecycle, all
   users controlled). The waiver is spent on procedure only: the
   amendment accepts a strict superset of pre-amendment documents, so
   every existing transcript remains conformant. The legacy bare
   `{"env": ..., "cwd"?}` form is accepted by normalization to
   `{"channel": "spawn-env", ...}` at the ingest boundary; emitters
   produce only the new form.
3. **The `delivered` tier definition is re-worded, not re-versioned.**
   The registry's membership is untouched (`os | constructive |
   delivered`). The `delivered` claim becomes: *the requested value was
   delivered to the subject, exactly as recorded, through the channel
   named in the delivery record; honoring it is subject cooperation;
   nothing is enforced.* One definition covers every channel in both
   protocols, avoiding a per-protocol meaning split.
4. **The model is complete now; the implementation is terminal-only.**
   All three channels are specified by this amendment. Issue #173 slice
   1 implements `spawn-env` (unchanged behavior) and `hello-config`
   (the terminal receipt). `wire-message` is admitted before an emitter
   exists — the same posture the tier registry took toward `delivered`
   before the cooperation ports landed — and gains an implementation
   when a receipt first claims it.
5. **Compat normalization is a named mechanism, not an ad-hoc branch.**
   `parse_transcript` applies a `_COMPAT_RULES` tuple of pure, total,
   normalize-toward-canonical functions between structural decode and
   validation. The legacy-delivery normalization is its first element.

## Design rules

These bind this amendment and every future compat-relevant change:

1. **Channels are a closed set inside v1 text.** `channel` membership
   (`spawn-env | hello-config | wire-message`) is fixed by the amended
   protocol text like `network.mode`'s `deny | allow-list` — not a new
   registry. A future channel amends the text again (or waits for v2,
   per the freeze posture at that time).
2. **Per-channel shapes are closed and disjoint.** `spawn-env`:
   required non-empty `env` (existing member rules unchanged), optional
   `cwd` (required for filesystem, forbidden otherwise). `hello-config`
   and `wire-message`: no members beyond `channel`. Any other member
   combination rejects.
3. **A channel tag names where delivery flowed; the claim never
   widens.** Every channel claims delivery-exactly-as-recorded, subject
   cooperation for honoring, and nothing enforced. `hello-config` for
   terminal claims: the dimensions in `run.started.config.terminal`
   were delivered in `session.hello.config`. It does not claim the
   subject applied them.
4. **Normalization is total, pure, and canonicalizing.** Compat rules
   transform a legacy document into its canonical form or reject it;
   they never relax acceptance, invent defaults, or add semantics.
   Validation proper sees only canonical form. A change that cannot be
   expressed under these constraints is not an alias — it is a semantic
   amendment and takes the design route.
5. **Compat rules are independent and self-describing.** Each rule is a
   named function with a docstring naming its introducing amendment.
   There is no ordering semantics; if two candidate rules interact, that
   is a design smell to surface, not an ordering feature to build.
6. **Emitters produce canonical form only.** The recorder and every
   adapter emit channel-tagged records; the legacy form exists only as
   ingest-side acceptance. Redaction consumes post-normalization
   records and emits canonical form, so redacted evidence revalidates
   regardless of the original's vintage.

## Reuse assessment

- **Discriminated JSON shapes in the existing protocols.** The
  channel-tagged record follows the established pattern of
  status-discriminated `capability.result` members (`enforced` vs
  `unsupported` member sets) and mode-discriminated `network.mode`
  shapes. No new structural technique is introduced.
- **Rejected: a separate `delivery-channel` sibling member.** It would
  require cross-member coherence rules ("channel says `hello-config`
  but `env` is present — reject? ignore?"), the exact ambiguity class
  the strict codec exists to refuse. One member, one closed shape per
  channel.
- **Rejected: a migration framework.** Versioned rule pipelines,
  ordering semantics, and plugin registries are speculative; the
  mechanism is a tuple of pure functions at the one ingest chokepoint
  (`parse_transcript`) that all transcript consumers share. The
  control/v1 codec is out of scope: it has no legacy corpus and gets
  its own list if it ever needs one.
- **Rejected: retrofitting the mechanism when a second rule arrives.**
  The first rule exists today; the list form costs about ten lines now
  and makes the policy ("compat normalization happens here, under these
  constraints") visible in code rather than discoverable by archaeology.

## Amended semantics

### The `delivery` record (transcript/v1, amended text)

For an `enforced` `capability.result` at the `delivered` tier, `delivery`
is required and is exactly one of:

| `channel` | Members | Claim |
| --- | --- | --- |
| `spawn-env` | `env` (required, non-empty), `cwd` (required iff constraint is `filesystem`, forbidden otherwise) | The recorded variables (and working directory) were placed into the subject's spawn environment. |
| `hello-config` | none | The constraint's `run.started.config` members were delivered to the subject in `session.hello.config`. |
| `wire-message` | none | The value was delivered as a control-protocol message during the run; the message record is the evidence. |

Member-name and value rules for `spawn-env.env` are unchanged
(non-empty names/values, no `=` or NUL in names, no NUL in values). The
legacy bare form `{"env": ..., "cwd"?}` (no `channel` member) is
accepted by normalization to `spawn-env`; a form carrying both `env`
and an explicit `channel` member rejects.

### The `delivered` tier row (registry text, amended)

| Tier | Claim |
| --- | --- |
| `delivered` | The requested value was delivered to the subject, exactly as recorded, through the channel named in the delivery record; honoring it is subject cooperation. Nothing is enforced. |

The other two rows and the registry membership are unchanged.

### Contract shapes

`DeliveryRecord` becomes channel-discriminated with the same validation
semantics the transcript states: `DeliveryRecord.spawn_env(env,
cwd=None)` preserves every current invariant (non-empty env, member
rules, cwd pairing); `DeliveryRecord.hello_config()` and
`DeliveryRecord.wire_message()` carry no payload. The keyword
`DeliveryRecord(env=..., cwd=...)` constructor remains as a
compatibility alias for `spawn_env`, so existing ports
(`cooperation.py`) compile unchanged; new code uses the named
constructors. `_validate_tier_and_delivery` validates the pairing per
channel.

### Which constraint claims which channel

- **JSONL adapter:** terminal → `hello-config`; seed, locale, timezone,
  filesystem, network → `spawn-env` via the cooperation ports,
  unchanged; clock → `spawn-env` initial delivery (`hello-config` is
  permissible text but the cooperation port already delivers
  `TERMVERIFY_CLOCK_INITIAL_MS`, and one constraint keeps one channel
  per adapter); clock *advances* are epoch evidence, not receipt claims
  — unchanged from the cooperation-tier disclosure.
- **ConPTY adapter:** unchanged; everything it claims today remains
  `spawn-env` (ports) or its own `os` terminal negotiation.
- **Direct adapter:** `constructive`, untouched.

### The compat-rule mechanism

`parse_transcript` gains, between structural decode and validation:

```
_COMPAT_RULES: tuple[Callable[[list[Record]], None], ...] = (
    _normalize_delivery_channel,  # amendment: channel-tagged delivery records
)
```

Each rule transforms records in place toward canonical form or raises
`TranscriptValidationError`. Rules are pure (no ambient state), total
(every input either normalizes or rejects), and independent. Validation
and every consumer downstream of `parse_transcript` (comparator,
replay, redaction, tests) see only canonical form. The mechanism's
constraints are rules 4–6 above; they are normative in the protocol
knowledge page alongside the amended delivery text.

## Architecture

No component boundaries change. Data flow for an ingested legacy
transcript:

```
bytes ──▶ structural decode ──▶ _COMPAT_RULES (normalize) ──▶ validate ──▶ consumers
                                     │                            │
                                     └─ rejects non-normalizable ─┘
```

Data flow for emission is unchanged except that receipts and the
recorder produce the channel-tagged form.

## Evidence (per slice)

- **Design amendment (this PR):** docs only — this document; amended
  tier/delivery text in `docs/knowledge/protocol.md`; a supersession note
  in `jsonl-control-transport.md` ("Constraint semantics across the
  process boundary" paragraph naming six spawn-time deliveries);
  changelog fragment. No code, no tests.
- **Issue #173 slice 1 (resumes after acceptance):** contract
  `DeliveryRecord` discrimination + compat constructor; transcript
  validator channel dispatch + `_COMPAT_RULES` with the legacy-delivery
  rule; recorder emission of the tagged form; redaction updated for
  channel shapes; schema update (`anyOf` legacy/canonical); mirrored
  tier/channel wording in `docs/knowledge/control-protocol.md` (the
  control protocol knowledge page lands with that slice);
  acceptance tests: legacy form validates and normalizes, a mixed
  `env`+`channel` form rejects, per-channel member rules, redaction
  round-trip on both vintages, JSONL terminal receipt at
  `hello-config`, all seven constraints start green against the fake
  child.
- **`wire-message` (future, unscheduled):** lands with the first
  receipt that claims it; requires no further text change.

## Non-goals

- **No registry or vocabulary re-versioning.** Tier membership is
  unchanged; the channel set is v1 text, not a registry.
- **No relaxation of the strict codec.** Normalization never widens
  acceptance beyond the documented legacy form; unknown `channel`
  values, mixed forms, and extra members all reject.
- **No shared compat abstraction across protocols.** The mechanism
  serves transcript ingest only.
- **No migration of stored transcripts.** Legacy documents remain
  conformant as-is.
- **No change to which tiers which adapters may state.** The
  authorization posture (JSONL all-`delivered`, ConPTY port
  restrictions, direct `constructive`) is unchanged.

## Risks

- **Two accepted forms at the ingest boundary.** Mitigation: the forms
  are structurally disjoint (`channel` presence vs `env` presence), the
  shim is total and fail-closed, and acceptance tests pin both sides of
  the boundary. The doubling is confined to `_COMPAT_RULES`; validation
  proper sees one shape.
- **The waiver becomes a habit.** The freeze waiver was granted for an
  additive amendment at an early lifecycle stage; this document records
  that the waiver bought procedure (no v2 ceremony), not compatibility
  breakage. Future non-additive needs still require a version bump or
  an explicit owner decision of the same gravity.
- **Channel proliferation.** Every future delivery mechanism will
  attract a channel request. Mitigation: rule 1 — the set is closed,
  additions take the design route, and `wire-message` itself is
  admitted-but-unemitted until a real receipt needs it.
- **`hello-config` reads as weaker evidence than `spawn-env`.** It is
  not: the transcript already records and validates the config members
  the claim points at, and the tier claim (delivered, not honored) is
  identical. The amended protocol text states this explicitly.

## Acceptance and sequencing

1. This document, the amended knowledge pages, the supersession note,
   and the changelog fragment land as one docs-only PR with owner
   acceptance.
2. Issue #173 slice 1 resumes in its worktree against the amended
   model, followed by the standard gate: full validation, draft PR,
   candidate-bound adversarial review, merge.
3. The amended transcript text takes effect immediately on merge of
   the implementation; the freeze posture of `termverify.control/v1`
   (freezes at first PyPI publication after its slice merges) is
   unchanged, and the amended transcript/v1 text freezes at the next
   publication carrying it.
