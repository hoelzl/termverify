---
type: Protocol Design
title: TermVerify JSONL transcript protocol
description: Versioned wire contract for deterministic terminal-verification transcripts.
tags: [protocol, jsonl, terminal, observations, determinism]
review_by: 2027-01-20
---

# TermVerify JSONL transcript protocol

`termverify.transcript/v1` is the versioned wire contract for deterministic
terminal-verification transcripts: one UTF-8 JSON Lines file per verified run,
validated by the canonical codec and semantic lifecycle validator in
`src/termverify/transcript.py`. This page states where acceptance authority
lives; the contract itself is split into topic pages so a change reads only
the part it touches.

## At a glance

- One canonical RFC 8785 JSON object per LF-terminated line, under fixed
  resource limits.
- Every record shares one envelope (`protocol`, `run_id`, `seq`, `id`, `kind`,
  `payload`) and the records follow one lifecycle: `run.started`, capability
  results, initial readiness, single-flight input epochs, one terminal record.
- Deterministic constraints are *requested* in `run.started` and *receipted*
  per constraint with an enforcement tier; a `delivered` receipt is not
  containment.
- Inputs are semantic (`termverify.key/v1` chords, text, resize, mouse, clock,
  clipboard, stop); observations carry normalized state, events, and UI.
- The Python validator, not the schema and not this prose, decides acceptance.

## Topics

| Page | Contents |
| --- | --- |
| [Framing and limits](protocol/framing-and-limits.md) | JSONL framing, fixed v1 resource limits, canonical serialization |
| [Envelope and lifecycle](protocol/envelope-and-lifecycle.md) | Common envelope, record ordering, execution epochs, replay subject, terminal records |
| [Deterministic constraints](protocol/deterministic-constraints.md) | Requested configuration, capability results, enforcement tiers, delivery channels |
| [Inputs and observations](protocol/inputs-and-observations.md) | Input kinds, `termverify.key/v1` semantic chords, diagnostics, observations |
| [Key encoding](protocol/key-encoding.md) | The companion `termverify.key-encoding/v1` chord-to-bytes registry |
| [Compatibility and evolution](protocol/compatibility.md) | Version rejection, prototyping-stage amendment policy, post-stage rules |

## Schema and runtime authority

The standard Draft 2020-12 schema is a non-exhaustive structural and
record-local validation aid. Executable schema tests verify the metaschema,
canonical records, closed member sets, and the local constraints encoded in
it. Schema acceptance is not a conformance verdict: the
Python validator remains authoritative for complete protocol acceptance,
including record kinds and representable rules not yet encoded in the schema,
cross-record lifecycle, canonical ordering, and uniqueness projected onto
selected fields. In particular, terminal capabilities must be sorted and
network entries must be sorted and unique by `(host, port)` even though standard
schema-only validation cannot fully enforce those rules. Exhaustive per-kind
schema coverage or a custom vocabulary/validator is a separate compatibility
and distribution workstream.

The canonical committed schema is packaged as the installed resource
`termverify/schemas/termverify.transcript/v1.schema.json` in both wheel and
sdist. The public accessors `termverify.transcript_schema_v1_bytes()` and
`termverify.transcript_schema_v1_json()` return the exact resource bytes and a
fresh parsed object, and `termverify.TRANSCRIPT_SCHEMA_V1_ID` names the
documented `$id`. Isolated installed-artifact checks verify byte identity
between the installed resource and the committed schema.

The authoritative validator is reachable from the same place, so the aid is
never the easier import: `termverify.parse_transcript()`,
`termverify.serialize_transcript()`, and `termverify.TranscriptValidationError`
are on the public surface alongside the schema accessors, and remain
importable from `termverify.transcript` as identical objects.

The `$id` resolves: the canonical publication at
`https://termverify.dev/schemas/termverify.transcript/v1.schema.json` is a
byte-for-byte mirror of the committed resource, deployed from `main` by the
`Pages` workflow and verified after every deployment by a fetch check that
fails on any byte difference (see
[`docs/developer-guide/schema-publication.md`](../developer-guide/schema-publication.md)).
While the prototyping stage lasts the publication mirrors `main`, so
published bytes follow the in-place amendment rule in
[compatibility and evolution](protocol/compatibility.md). The `$id`
remains identifier-first: resolution is a distribution convenience,
consumers must not fetch it at validation time, no library or required gate
depends on the site being reachable, and neither publication nor installed
access changes the schema's non-exhaustive role or runtime authority.
