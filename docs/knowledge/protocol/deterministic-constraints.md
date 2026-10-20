---
type: Protocol Design
title: Requested deterministic constraints
description: Requested run configuration, capability results, enforcement tiers, and delivery channels of termverify.transcript/v1.
tags: [protocol, constraints, determinism, enforcement]
review_by: 2027-01-20
---

# Requested deterministic constraints

Part of the [`termverify.transcript/v1` protocol](../protocol.md).

## Configuration table

`run.started.payload.config` has all of the following required members:

| Member | Required shape and v1 rule |
| --- | --- |
| `seed` | canonical decimal string representing an unsigned 64-bit integer: `"0"` or a nonzero digit followed by digits, with no leading zeroes |
| `clock` | `{"mode": "manual", "initial_ms": non-negative integer}` |
| `locale` | literal `"C"`, or a well-formed RFC 5646 language tag |
| `timezone` | non-empty string naming the requested zone; only literal `"UTC"` may be reported as applied, so any other request is refused through `unsupported` (or the run fails before its receipt) |
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

`timezone` is a plain non-empty string: the zone the run requests. **There is no
timezone registry.** V1 can only ever apply the literal `UTC` — applying a named
zone requires zone data this protocol deliberately never consults — so a closed
registry existed only to validate requests that must then be refused anyway, at
the cost of pinning v1 to one TZDB release with no registry-version selector in
the record (adversarial review 2026-07-24, finding P4; registry removed by owner
decision 2026-07-24, preserved in Git history). Any future reintroduction, when
a vertical actually demands non-UTC zones, is a fresh design with a version
selector rather than a revival of this one.

The codec preserves the requested spelling exactly and performs no alias, case,
or preferred-name normalization; it never consults ambient `zoneinfo`,
operating-system data, environment, or network state, so a transcript records
what was asked for. A non-empty string is all that either the schema or the
runtime requires of the request, and an `x-` extension cannot change what a
request means.

Truthfulness therefore rests on the receipt, never on the request's vocabulary.
A timezone request is not enforcement evidence: v1 receipts permit only literal
`UTC` as an effective value, and an adapter that cannot apply a requested zone
terminates through structured `unsupported` rather than fabricating one.
Requesting `Mars/Olympus` is valid and unhelpful in exactly the way requesting
`Europe/Berlin` is: both are refused, and the refusal is the record.

The configuration requests a constraint; it does not itself prove enforcement.
What an adapter owes is a truthful receipt per constraint, never containment it
does not have. The adapter-facing contract is:

- It applies each requested constraint through an explicit mechanism and
  records which one. A constructive in-process runtime injects the requested
  seed and manual clock through application-facing ports; a cooperation port
  instead delivers the requested value to the subject through the channel named
  in the delivery record, and does nothing further. Advancing manual time is
  always an explicit `input.clock_advanced` record, never a wall-clock wait.
- It reports the effective value it actually applied, and configures the
  requested terminal dimensions and capabilities before the subject can observe
  them.
- It never records a stronger mechanism than it used. The filesystem and
  network constraints in particular are applied at whatever tier the adapter
  can support — an `os`-tier sandbox root or socket denial where a mechanism
  exists, otherwise `delivered`, where the requested policy is handed to the
  subject and honoring it is subject cooperation. A `delivered`-tier receipt is
  not containment: no receipt, claim, or document may imply that it is (owner
  decision 2026-07-18,
  [`cooperation-tier-constraint-ports.md`](../../agent/design/cooperation-tier-constraint-ports.md)).
- An adapter that cannot apply a requested constraint at any tier must record
  it `unsupported` and terminate through `run.unsupported`. A verified run may
  include `delivered`-tier constraints, and its constraint claims are no
  stronger than its weakest tier — which is why the tier is recorded per
  constraint rather than summarized per run.
- It emits one `capability.result` for each attempted constraint through the
  first unsupported constraint, with `constraint`, `status`, and
  status-dependent `effective`/`tier`/`delivery`/`reason` members. `status` is
  exactly `applied` or `unsupported`. `applied` states that the adapter carried
  out the constraint's application step and recorded the value it applied; the
  mandatory `tier` states what that step was worth — at `os` and
  `constructive` the constraint itself is in force, while at `delivered` what
  was applied is the delivery, and whether the subject honors the delivered
  value is not observable. There is no third status: the status word never
  claims enforcement the tier disclaims, and a constraint the adapter can
  neither enforce nor deliver is `unsupported`. The first unsupported result
  terminates the transcript with `run.unsupported` and no input dispatch.

`capability.result.payload.constraint` is one of `seed`, `clock`, `locale`,
`timezone`, `terminal`, `filesystem`, or `network`; it follows the table order
above. For `applied`, `effective` is required and is the applied configuration
value, and `tier` is required and states the enforcement tier (below). For
`unsupported`, `reason` is required and the next record is the matching
`run.unsupported` terminal record.

### Enforcement tiers

`termverify.enforcement-tier/v1` is a closed, case-sensitive vocabulary owned
by this protocol version exactly like the key registries: exact membership, no
aliases or normalization, runtime validation authoritative.
Post-freeze membership or meaning changes require a new vocabulary version.
Its members, in decreasing claim strength:

| Tier | Claim |
| --- | --- |
| `os` | The constraint is applied by an operating-system mechanism at the subject boundary; evidence exists at the OS level. |
| `constructive` | The constraint is applied by construction of the controlled in-process runtime: the emitting port asserts that the subject reaches the constrained resource only through it. Stating it truthfully is part of the injected application's port contract. |
| `delivered` | The requested value was delivered to the subject, exactly as recorded, through the channel named in the delivery record; honoring it is subject cooperation. Nothing is enforced. |

Every `applied` capability result carries a mandatory `tier`. A
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
ingest boundary; a form carrying `env` together with a `channel` other than
`spawn-env` is invalid. (The canonical `spawn-env` form itself carries both
`channel` and `env`, per the channel table above — it is the required
emitter output, not an invalid combination.) Emitters produce only the
channel-tagged form. Normalization is
performed by the codec's compat rules — named, pure, total,
normalize-toward-canonical functions applied between structural decode and
validation (`_COMPAT_RULES` in the runtime); they never relax acceptance,
and validation proper sees only the canonical form.

Membership in the
vocabulary is not evidence that an emitter exists: which tier a negotiation
path may state is fixed by the accepted cooperation-tier design and validated
fail-closed at runtime during receipt binding (an adapter's own terminal
negotiation may state `os`; ports injected into the terminal adapter may state
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
