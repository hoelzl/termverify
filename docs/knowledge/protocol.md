---
type: Protocol Design
title: TermVerify JSONL transcript protocol
description: Versioned wire contract for deterministic terminal-verification transcripts.
tags: [protocol, jsonl, terminal, observations, determinism]
---

# TermVerify JSONL transcript protocol

This document defines the reviewed **design** for the first intended external
protocol: `termverify.transcript/v1`. The repository contains a canonical codec,
semantic lifecycle validator, non-exhaustive schema aid, and reviewed fixture and
property coverage. The archived Phase 1 handover completed deterministic
transcript resource governance through the fixed limits below and its amended
behavior-based fixture gate. Installed-schema and release controls remain intact
in the active pre-release successor before the first supported external artifact.
Neither that transfer nor the current runtime activates Phase 2.

## Schema and runtime authority

The standard Draft 2020-12 schema is a non-exhaustive structural and
record-local validation aid. Executable schema tests verify the metaschema,
canonical records, closed member sets, and the local constraints encoded for the
current inception slice. Schema acceptance is not a conformance verdict: the
Python validator remains authoritative for complete protocol acceptance,
including record kinds and representable rules not yet encoded in the schema,
cross-record lifecycle, canonical ordering, and uniqueness projected onto
selected fields. In particular, terminal capabilities must be sorted and
network entries must be sorted and unique by `(host, port)` even though standard
schema-only validation cannot fully enforce those rules. Exhaustive per-kind
schema coverage or a custom vocabulary/validator is a separate compatibility and
distribution workstream, not part of this replay-identity slice.

The canonical committed schema is packaged as the installed resource
`termverify/schemas/termverify.transcript/v1.schema.json` in both wheel and
sdist. The public accessors `termverify.transcript_schema_v1_bytes()` and
`termverify.transcript_schema_v1_json()` return the exact resource bytes and a
fresh parsed object, and `termverify.TRANSCRIPT_SCHEMA_V1_ID` names the
documented `$id`. Isolated installed-artifact checks verify byte identity
between the installed resource and the committed schema.

The `$id` resolves: the canonical publication at
`https://termverify.dev/schemas/termverify.transcript/v1.schema.json` is a
byte-for-byte mirror of the committed resource, deployed from `main` by the
`Pages` workflow and verified after every deployment by a fetch check that
fails on any byte difference (see
[`docs/developer-guide/schema-publication.md`](../developer-guide/schema-publication.md)).
During the declared inception period the publication mirrors `main`, so
published bytes follow the in-place v1 amendment rule below. The `$id`
remains identifier-first: resolution is a distribution convenience,
consumers must not fetch it at validation time, no library or required gate
depends on the site being reachable, and neither publication nor installed
access changes the schema's non-exhaustive role or runtime authority.

Each UTF-8 JSON Lines file is one transcript for one verified run. A line ends
with exactly one LF (`\n`); a final LF is required. Blank lines, comments, and
byte-order marks are invalid. Readers reject duplicate object member names and
unknown required semantics instead of silently choosing an interpretation.

## Fixed v1 resource limits

The canonical parser and programmatic serializer enforce the same fixed,
protocol-owned ceilings. They do not inherit interpreter recursion settings,
host memory, or ambient configuration:

| Resource | V1 maximum | Counting rule |
| --- | ---: | --- |
| Transcript bytes | 32 MiB (33,554,432 bytes) | Entire JSONL byte sequence, including every final LF. |
| Line bytes | 4 MiB (4,194,304 bytes) | One canonical JSON object, excluding its LF. |
| Records | 10,000 | JSONL objects in one transcript. |
| JSON nesting | 64 | Simultaneously open objects and arrays in one record, including the envelope object. |
| Collection items | 16,384 | Immediate members in one object or items in one array. |
| JSON values | 100,000 | Container and scalar value nodes in one record; object keys are not value nodes. |
| Individual string bytes | 1 MiB (1,048,576 bytes) | UTF-8 bytes of one decoded string value or object key. |
| Record string bytes | 2 MiB (2,097,152 bytes) | Aggregate UTF-8 bytes of every decoded string value and object key in one record. |

The parser checks total bytes, framing, record count, line bytes, and lexical JSON
nesting before JSON decoding. After decoding, it checks collection, value, and
string budgets before semantic validation. Brackets inside JSON strings do not
contribute to lexical nesting. The serializer traverses exact Python JSON values
iteratively, applies the same structured-value budgets before RFC 8785
canonicalization, then checks each canonical line and accumulates transcript
bytes before joining output. Strings longer than the individual byte ceiling in
code points are rejected before UTF-8 measurement, bounding that measurement;
malformed Unicode is normalized to `TranscriptValidationError` rather than
leaking a codec exception. A limit violation is a
`TranscriptValidationError`; interpreter recursion or allocation-dependent
behavior is not a conformance result. Every successfully serialized transcript
therefore remains admissible to the parser under the same ceilings.

## Canonical serialization

Transcript producers use the JSON Canonicalization Scheme
([RFC 8785](https://www.rfc-editor.org/rfc/rfc8785)) for each object, encoded
as UTF-8 and followed by LF. Therefore object-member order, whitespace, string
escaping, and number rendering do not vary by producer. Values that could lose
precision in another JSON implementation, including seeds and monotonic IDs,
are JSON strings rather than numbers.

Canonical bytes are the basis for fixture comparison and transcript digests;
the digest algorithm and value, if emitted, are an optional metadata field and
never replace parsing and semantic validation.

## Common envelope

Every line is an object with these required members:

| Member | Type | Meaning |
| --- | --- | --- |
| `protocol` | string | Exactly `termverify.transcript/v1`. |
| `run_id` | string | Caller-supplied stable identifier for this run. |
| `seq` | non-negative integer | Zero-based, contiguous line sequence. |
| `id` | string | Stable unique record identifier within `run_id`. |
| `kind` | string | Record type from the v1 set below. |
| `payload` | object | Data defined by `kind`; no omitted required members. |

`run_id` and `id` use lowercase ASCII letters, digits, `.`, `_`, and `-`; they
must be non-empty and generated by the caller or deterministic harness, never
from adapter ambient randomness. The recommended identifiers are the stable
`run-<fixture-or-request-name>` and `record-<zero-padded-seq>` forms. A reader
rejects a repeated `id`, a changed `run_id`, or a non-contiguous `seq`.

An extension member starts with `x-` and has no meaning to a generic v1 reader.
All other members are reserved. A producer must not use an extension to change
the meaning of a required v1 member.

## Record ordering and lifecycle

A valid transcript contains exactly this lifecycle shape:

1. `run.started` at `seq: 0`;
2. `capability.result` records in configuration-table order until all requested
   constraints are enforced, the first is unsupported, or an adapter failure
   terminates negotiation;
3. if initialization completes, exactly one initial readiness observation;
4. zero or more single-flight input epochs;
5. exactly one terminal record: `run.finished`, `run.failed`, or
   `run.unsupported`.

An adapter failure may terminate negotiation before any capability result or
after any enforced prefix. The transcript then contains only `run.started`, that
prefix, and `run.failed`. A subject that exits or an adapter that fails after
negotiation but before readiness may likewise terminate without an initial
observation. `run.unsupported` remains negotiation-only and has no body records.

### Execution epochs and causality

The initial readiness observation is the first semantic body record after all
seven capability results. Zero or more startup diagnostics may precede it, but
no input may. Its position, rather than an additional payload member, declares
that initialization completed and the subject is ready for input.

After readiness, v1 is single-flight. Each epoch contains:

1. exactly one input record;
2. zero or more diagnostics caused while handling that input;
3. exactly one observation that closes the epoch at deterministic quiescence,
   unless a terminal record closes it first.

The closing observation is the complete normalized evidence available at
quiescence, not an output chunk. Transcript order supplies causality, so another
input before that observation is invalid. Observations and diagnostics while
idle are invalid: diagnostics do not create hidden epochs. `input.stop` is the
final accepted input. Its drain epoch may contain diagnostics and an optional
final observation, followed by `run.finished` or `run.failed`; no later input is
valid.

A terminal record may also occur while idle when the subject exits naturally or
the adapter fails. This ordered model intentionally excludes unsolicited body
events in v1. General asynchronous work requires a future explicit polling,
draining, or correlation contract rather than wall-clock quiet-window polling.

No record follows a terminal record. Input records are ordered by dispatch;
observations are ordered by the point at which the adapter captured them; event
arrays inside an observation are ordered by application emission. Records never
claim wall-clock ordering: all timing uses the configured manual clock in
integer milliseconds. A capture failure is represented by `run.failed`, not by
silently dropping a record.

`run.started` has a `payload.config` object containing the requested
deterministic constraints. `capability.result` reports each constraint's actual
outcome before the adapter accepts the first input. `input.*` records describe
the requested user action; `observation` records contain the resulting
structured evidence; `diagnostic` carries non-oracle information such as a
normalized process warning.

`run.started.payload` is closed except for `x-` extensions and requires exactly
`config` plus `subject`. `subject` is a versioned replay selector with this v1
shape:

```json
{
  "format": "termverify.replay-subject/v1",
  "application": {"id": "example.app", "version": "1", "build": "build-1"},
  "fixture": {"id": "basic", "version": "1"},
  "adapter": {"id": "example.direct", "version": "1"},
  "normalizer": {"id": "example.identity", "version": "1"},
  "state_schema": {"id": "example.state", "version": "1"}
}
```

Every selector value uses the same lowercase ASCII identifier grammar as
`run_id`. Application identity separates its application version from the exact
build selector. Fixture identity selects the registered invocation without
embedding a raw command line or environment. Adapter, normalizer, and state
schema identities bind the interpretation needed for replay. An optional
`platform` object has exactly normalized `os` and `architecture` selectors.
Volatile hostname, account, absolute path, raw `argv`, and environment details
are not replay selectors and are forbidden as generic subject members. Every
subject and nested selector is closed except for uninterpreted `x-` extensions.

Terminal record payloads are:

| Kind | Required payload members |
| --- | --- |
| `run.finished` | `exit`: `{"kind": "code", "value": integer}` or `{"kind": "signal", "value": non-empty string}` |
| `run.failed` | `error`: `{"code": non-empty string, "message": string, "details"?: JSON value}` |
| `run.unsupported` | `constraint`, `code`, `message`, and optional `details`; `constraint` and `code` are non-empty strings |

Every defined record payload and nested generic protocol object is closed to
its listed members plus uninterpreted `x-` extensions. In particular,
`capability.result` permits `effective`, `tier`, and `delivery` only with
`enforced` and `reason` only with `unsupported`; `delivery` additionally
requires the `delivered` tier. Application-defined JSON values such as
observation `state`, event `data`, diagnostic `details`, and error `details`
remain open semantic values rather than generic protocol objects. The
`delivery.env` object (present only with the `spawn-env` channel, below) is a
value map of delivered environment-variable names, not a generic protocol
object: its member names are exact variable names with no `x-` extension
semantics.

`message` is diagnostic only. Consumers use stable `code` values for behavior;
v1 reserves `adapter-start-failed`, `adapter-runtime-failed`,
`constraint-unsupported`, and `constraint-not-enforced`.

## Requested deterministic constraints

`run.started.payload.config` has all of the following required members:

| Member | Required shape and v1 rule |
| --- | --- |
| `seed` | canonical decimal string representing an unsigned 64-bit integer: `"0"` or a nonzero digit followed by digits, with no leading zeroes |
| `clock` | `{"mode": "manual", "initial_ms": non-negative integer}` |
| `locale` | literal `"C"`, or a well-formed RFC 5646 language tag |
| `timezone` | exact member of the protocol-bound `termverify.timezone/v1` registry |
| `terminal` | `columns` and `rows` positive integers; `capabilities` sorted unique strings |
| `filesystem` | `{"mode": "sandbox", "root_id": string}` |
| `network` | `{"mode": "deny"}` or `{"mode": "allow-list", "allowed": [{"host": string, "port": integer 1–65535}]}`; `allowed` is sorted by host then port and has no duplicates |

The configuration object and each defined nested object are closed except for
uninterpreted `x-` extensions. Raw command lines, environment variables, host
paths, and other invocation or machine identity are not deterministic-constraint
members and cannot be added as generic configuration fields at any nesting level.

Locale validation applies the RFC 5646 language-tag syntax only, including
normal, private-use, and fixed grandfathered forms plus the RFC prohibition on
duplicate variants and extension singletons. It does not consult the IANA
Language Subtag Registry, reject deprecated tags, or claim registry-backed
validity. RFC 5646 language tags are case-insensitive, while the separate `C`
sentinel is literal and case-sensitive. The codec preserves the caller's
spelling and case exactly; v1 performs no locale normalization or
preferred-value rewriting. Validation is therefore independent of the host
locale, installed locale data, environment, and network.

`termverify.timezone/v1` is a closed, case-sensitive registry owned by this
protocol version. It contains the literal `UTC` sentinel and the names declared
by `Zone` directives in the `africa`, `antarctica`, `asia`, `australasia`,
`europe`, `northamerica`, `southamerica`, and `etcetera` sources from IANA TZDB
2026c. The pinned source is
`https://data.iana.org/time-zones/releases/tzdata2026c.tar.gz`, with SHA-256
`e4a178a4477f3d0ea77cc31828ff72aa38feff8d61aa13e7e99e142e9d902be4`.
`Link` aliases and names from `backzone` or `factory` are not members. The
committed registry is generated by `scripts/generate_timezone_registry.py`;
runtime acceptance never consults ambient `zoneinfo`, operating-system data,
environment, or network state.

The codec preserves accepted timezone spelling exactly and performs no alias,
case, or preferred-name normalization. An `x-` extension cannot add names or
change registry meaning. During the declared inception period before a first
supported external artifact, an owner-reviewed compatibility correction may
revise this v1 registry in place. After that boundary freezes, changing its
membership or meaning requires a new transcript protocol version because a v1
record carries no separate timezone-registry selector. JSON Schema deliberately
retains only the structural non-empty-string check; runtime validation owns
registry membership.

A valid named-timezone request is not enforcement evidence. V1 receipts still
permit only literal `UTC`; an adapter that cannot enforce an accepted named
request terminates through structured `unsupported` rather than fabricating an
effective value.

The configuration requests a constraint; it does not itself prove enforcement.
The adapter-facing contract is:

- It injects the requested seed and manual clock through an application-facing
  port. Advancing time is an explicit `input.clock_advanced` record, never a
  wall-clock wait.
- It starts subprocesses with the requested locale and timezone, configures the
  requested terminal dimensions/capabilities before the process can observe
  them, and reports the effective values it actually applied.
- It gives filesystem access only through the named sandbox root and denies
  network access by default. An adapter that cannot enforce a requested
  constraint must not claim a verified run.
- It emits one `capability.result` for each attempted constraint through the
  first unsupported constraint, with `constraint`, `status`, and
  status-dependent `effective`/`tier`/`delivery`/`reason` members. `status` is
  exactly `enforced` or `unsupported`; a `supported-but-not-enforced` state is
  invalid. The first unsupported result terminates the transcript with
  `run.unsupported` and no input dispatch.

`capability.result.payload.constraint` is one of `seed`, `clock`, `locale`,
`timezone`, `terminal`, `filesystem`, or `network`; it follows the table order
above. For `enforced`, `effective` is required and is the applied configuration
value, and `tier` is required and states the enforcement tier (below). For
`unsupported`, `reason` is required and the next record is the matching
`run.unsupported` terminal record.

### Enforcement tiers

`termverify.enforcement-tier/v1` is a closed, case-sensitive vocabulary owned
by this protocol version exactly like the timezone and key registries: exact
membership, no aliases or normalization, runtime validation authoritative.
Post-freeze membership or meaning changes require a new vocabulary version.
Its members, in decreasing claim strength:

| Tier | Claim |
| --- | --- |
| `os` | The constraint is applied by an operating-system mechanism at the subject boundary; evidence exists at the OS level. |
| `constructive` | The constraint is applied by construction of the controlled in-process runtime: the emitting port asserts that the subject reaches the constrained resource only through it. Stating it truthfully is part of the injected application's port contract. |
| `delivered` | The requested value was delivered to the subject, exactly as recorded, through the channel named in the delivery record; honoring it is subject cooperation. Nothing is enforced. |

Every `enforced` capability result carries a mandatory `tier`. A
`delivered`-tier result additionally carries a mandatory `delivery` object
naming the channel through which delivery flowed; no other tier may carry a
`delivery`. The `channel` member is a closed set fixed by this protocol
version (like `network.mode`, not a registry): exactly one of the following
shapes.

| `channel` | Members | Claim |
| --- | --- | --- |
| `spawn-env` | `env` (required, non-empty), `cwd` (required iff the constraint is `filesystem`, forbidden otherwise) | The recorded environment variables (and, for filesystem, working directory) were placed into the subject's spawn environment. |
| `hello-config` | none beyond `channel` | The constraint's `run.started.config` members — already recorded and validated in this transcript — were delivered to the subject in `session.hello.config` (`termverify.control/v1`). |
| `wire-message` | none beyond `channel` | The value was delivered as a control-protocol message during the run; the protocol's own message records are the evidence. |

`spawn-env` member rules are unchanged: `env` maps non-empty variable names
(no `=` or NUL) to non-empty values (no NUL); `cwd` is a non-empty NUL-free
string. A channel tag names where delivery flowed; the claim never widens —
every channel claims delivery exactly as recorded, subject cooperation for
honoring, and nothing enforced.

Compatibility (amendment of 2026-07-20, owner decision on issue #173): the
pre-amendment bare form `{"env": ..., "cwd"?}` with no `channel` member
remains accepted and is normalized to `{"channel": "spawn-env", ...}` at the
ingest boundary; a form carrying both `env` and an explicit `channel` member
is invalid. Emitters produce only the channel-tagged form. Normalization is
performed by the codec's compat rules — named, pure, total,
normalize-toward-canonical functions applied between structural decode and
validation (`_COMPAT_RULES` in the runtime); they never relax acceptance,
and validation proper sees only the canonical form.

Membership in the
vocabulary is not evidence that an emitter exists: which tier a negotiation
path may state is fixed by the accepted cooperation-tier design and validated
fail-closed at runtime during receipt binding (an adapter's own terminal
negotiation may state `os`; ports injected into the ConPTY adapter may state
only `delivered`; ports negotiated by the direct adapter may state only
`constructive`). The same posture applies to channels: `wire-message` is
admitted before any emitter exists. A transcript records the stated tier but
cannot know the
emitting path, so transcript validation checks vocabulary membership and the
tier/`delivery` pairing only. A receipt never claims the subject honored a
delivered value, and no tier claims containment.

This leaves applications responsible for exposing controllable ports; it keeps
the deterministic core independent from ambient time, randomness, terminal,
filesystem, and network state.

## Inputs and observations

V1 input kinds are `input.key`, `input.text`, `input.resize`, `input.mouse`,
`input.clock_advanced`, `input.clipboard_set`, and `input.stop`. Every input
payload includes a non-negative integer `at_ms` manual-clock value and has the
following additional required members. No member not listed as optional is
permitted in a generic v1 input payload, except an `x-` extension member with
no generic v1 meaning.

| Kind | Required payload members |
| --- | --- |
| `input.key` | `keys`: ordered array containing one canonical `termverify.key/v1` semantic chord |
| `input.text` | `text`: Unicode string |
| `input.resize` | positive integer `columns` and `rows` |
| `input.mouse` | `action`: `press`, `release`, `move`, or `scroll`; non-negative integer `column` and `row`; `button` (`left`, `middle`, or `right`) for `press`/`release`; non-zero integer `delta` for `scroll` |
| `input.clock_advanced` | positive integer `delta_ms`; `at_ms` equals the preceding manual time plus `delta_ms` |
| `input.clipboard_set` | `text`: Unicode string |
| `input.stop` | no additional members |

### Semantic key chords

TermVerify owns the closed `termverify.key/v1` registry. An `input.key` record
represents one simultaneous semantic chord; a sequence of keystrokes requires
multiple input records and therefore multiple quiescent input epochs. The
`keys` array contains zero or more modifiers followed by exactly one base key.
Modifiers are unique and, when present, appear in this canonical order:
`Control`, `Alt`, `Shift`, `Meta`.

The exact v1 component registry has 99 entries:

- modifiers: `Control`, `Alt`, `Shift`, `Meta`;
- named bases: `Enter`, `Tab`, `Escape`, `Backspace`, `Delete`, `Insert`,
  `ArrowUp`, `ArrowDown`, `ArrowLeft`, `ArrowRight`, `Home`, `End`, `PageUp`,
  `PageDown`, and `F1` through `F12`;
- modified-only bases: lowercase ASCII `a` through `z`, ASCII `0` through `9`,
  `Space`, and the printable ASCII punctuation row
  ``! " # $ % & ' ( ) * + , - . / : ; < = > ? @ [ \ ] ^ _ ` { | } ~``.

A modified-only base requires at least one of `Control`, `Alt`, or `Meta`.
`Shift` alone does not make a printable base valid. Thus `["Control", "c"]`,
`["Alt", "1"]`, `["Control", "Space"]`, `["Control", "/"]`, and
`["Alt", "<"]` are valid; `["c"]`, `["1"]`, `["Space"]`, `["/"]`,
`["Shift", "a"]`, and `["Shift", "<"]` are invalid. Unmodified printable
insertion, including an ordinary space, punctuation, or uppercase letter,
uses `input.text`.

Names are exact and case-sensitive. V1 performs no trimming, case folding,
Unicode normalization, alias rewriting, or modifier reordering. Toolkit names,
OS virtual-key codes, physical-key locations, curses names, and terminal escape
sequences are not protocol values. In particular, `Ctrl`, `Cmd`, `Option`,
`Esc`, `Return`, lowercase `enter`, chord strings such as `Ctrl+C`, and encoded
bytes such as `\u001b[A` are invalid. `Space` is TermVerify's semantic name for
the space key when it participates in an approved modified chord; it is not a
raw whitespace identifier.

Neither `input.key` nor `input.text` is a raw terminal-byte channel. An adapter
maps a valid semantic value to its own application boundary and must fail rather
than silently translate an unknown value, alias, or ambiguous escape sequence.
An `x-` extension cannot add registry entries or change chord meaning. The
reviewed registry order is digest-bound in executable tests using newline-joined
UTF-8 names with a final LF; its SHA-256 is
`51955be77ab11b23240c642edd0e4f08dbd56389b82f99bbe2ee87871ce9d0a0`.

#### Companion registry: `termverify.key-encoding/v1`

The terminal execution path has a companion registry,
`termverify.key-encoding/v1` (`src/termverify/_key_encoding_v1.py`), that maps
each of the 1382 valid `termverify.key/v1` chords either to exactly one
xterm-legacy normal-mode byte string or to the explicit fail-closed verdict
**unencodable**. It is committed data plus committed arithmetic owned by
TermVerify — never derived from terminfo, toolkit enums, OS virtual-key
codes, or other ambient host state — and it is not a transcript value: an
`input.key` record stays semantic, no record carries encoded bytes, and this
registry can version independently of the transcript protocol. A chord is
encodable exactly when the legacy encoding represents every chord component
by definition; when the only candidate bytes would drop a modifier
(`Control+Enter`, `Control+/`), alias one modifier to another (`Meta` as
`Alt` on letters), or pass a NUL hazard (`Control+Space`), the registry
returns unencodable and the adapter fails rather than misrepresent the
chord. Four
byte collisions inherent to the legacy byte space are disclosed:
`["Control", "m"]`/`["Enter"]` (CR), `["Control", "i"]`/`["Tab"]` (HT), and
their two `Alt`-prefixed forms. The full enumeration — each chord joined
with `+`, then ` => ` and the space-joined two-digit lowercase hex code
points of its encoding or the word `unencodable`, newline-joined UTF-8 with
a final LF — is digest-bound in executable tests; its SHA-256 is
`72a17da549238053c88a925cf6bf2bbe93ed2b8564c7a09188075987fcdcda95`. The
pre-freeze inception policy above applies to this registry as well; details
of the adapter behavior live in the
[ConPTY developer guide](../developer-guide/conpty-adapter.md).

For `input.mouse`, `button` and `delta` are forbidden for `move`; `delta` is
forbidden for `press` and `release`; and `button` is forbidden for `scroll`.
Clipboard values are sensitive evidence and their
[capture/redaction policy](evidence-governance.md) requires persistence through
the evidence-aware writer; the raw codec is non-persistent.

`diagnostic` has required `at_ms`, non-empty string `code`, and string
`message` members; optional `details` holds a JSON value. It is non-oracle
information and cannot change a run's terminal status.

An `observation` payload has these required members:

- `at_ms`: manual-clock value at capture;
- `state`: application-defined JSON value after a documented normalizer;
- `events`: ordered array of `{"type": non-empty string, "data": JSON value}`
  objects;
- `ui`: an object with the required members below.

`ui.regions` is an ordered array of objects with non-empty `id` and `role`
strings and a `bounds` object containing non-negative integer `column` and
`row` plus positive integer `columns` and `rows`. Region IDs are unique within
the observation. `ui.focus` is a region ID or `null`; `ui.cursor` is
`{"column": non-negative integer, "row": non-negative integer, "visible": boolean}`;
and `ui.mode` is a string or `null`. A non-null focus must name one of the
observation's regions.

`frame` (a normalized rendered terminal frame) and `process` (lifecycle detail)
are optional evidence layers. When present, `frame` is
`{"lines": [string, ...], "columns": positive integer, "rows": positive integer}`
with `len(lines) == rows`; `process` is `{"state": "running"}` or
`{"state": "exited", "exit": <run.finished exit object>}`. A comparator
evaluates `state` and `events` before optional rendering evidence; a matching
frame cannot conceal a domain mismatch. Application-specific values belong
under documented `x-` members or a registered normalizer, not under new generic
v1 member names.

When a transcript ends with `run.finished`, every exited-process observation
has the same exit `kind` and `value` as `run.finished.payload.exit`.
An exited-process observation is the final body record. Uninterpreted `x-`
extensions do not participate in the exit comparison. The relationship with
the other terminal outcomes is asymmetric.
`run.unsupported` has no body and therefore no process observation. A
`run.failed` transcript may retain independently captured exited-process
evidence; that evidence is orthogonal to the adapter or harness failure and has
no terminal exit value to match.

## Compatibility and evolution

`termverify.transcript/v1` readers must reject a different `protocol` value.
During the repository's inception phase there are no external clients or
supported transcript artifacts. Reviewed contract corrections, including the
required replay subject above, therefore update v1 in place rather than creating
fictional compatibility history. Existing repository fixtures are migrated in
the same reviewed change. The first declared real client or supported external
artifact freezes this inception policy: after that boundary, only optional `x-`
extensions are additive within a version, and new generic semantics, member
types or meanings, canonicalization, ordering rules, or stable error codes
require a new protocol version.

That freeze includes `termverify.key/v1` membership, spelling, component roles,
modifier ordering, and chord validity. A post-freeze change to any of them
requires a new transcript protocol and key-registry version; ambient toolkit or
host registry growth never changes v1. (One owner-approved exception: the
modified-only base set was widened once — see issue #155 and
`docs/agent/design/key-v1-punctuation-bases.md` — to add the printable ASCII
punctuation row. That amendment was designed, implemented, and adversarially
reviewed before the freeze but merged after it; the owner approved landing it
as a one-time in-place amendment because it is purely additive and leaves the
wire-protocol version unchanged. It sets no precedent — all later registry
changes require a new version.)

An inception transcript without `subject` is invalid and no tool may guess its
identity from ambient or undocumented out-of-band context. A caller with the
required stable selectors may explicitly reconstruct a current v1 transcript;
automatic migration is outside the codec. A future new version supplies its own
fixtures and migration/replay policy. A reader may preserve unknown `x-`
members when rewriting a transcript, but must not manufacture or interpret them.