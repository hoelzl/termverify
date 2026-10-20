---
type: Protocol Design
title: Transcript compatibility and evolution
description: Version rejection and the amendment policy for termverify.transcript/v1 and its registries.
tags: [protocol, compatibility, governance]
---

# Transcript compatibility and evolution

Part of the [`termverify.transcript/v1` protocol](../protocol.md).

`termverify.transcript/v1` readers must reject a different `protocol` value.

Whether the protocols are frozen is a governance decision, not a property of
this page: the current stage, its rationale, and its exit criterion are
recorded in
[`prototyping-stage-protocol-governance.md`](../../agent/design/prototyping-stage-protocol-governance.md).

While the prototyping stage lasts, the in-place amendment policy applies to every
TermVerify protocol and registry (`termverify.transcript/v1`,
`termverify.key/v1`, `termverify.key-encoding/v1`, and the JSONL control
protocol): reviewed contract corrections — including
incompatible ones — update the current version in place rather than creating
fictional compatibility history. No version bump, compatibility shim, or
per-change exception decision is required. Existing repository fixtures are
migrated in the same reviewed change, and the protocol pages are updated in
the same change. No backward compatibility is owed to any artifact, including
the published 0.1.0; version identifiers such as `/v1` name the current
shape so readers can reject foreign input, and are not stability promises.

The prototyping stage ends only by an explicit recorded owner decision that
TermVerify is usable by external clients — not by any release or publication
event. After that boundary, only optional `x-` extensions are additive
within a version, and new generic semantics, member types or meanings,
canonicalization, ordering rules, or stable error codes require a new
protocol version; the same applies to `termverify.key/v1` membership,
spelling, component roles, modifier ordering, and chord validity, for which
ambient toolkit or host registry growth never changes a published version.

A v1 transcript without `subject` is invalid and no tool may guess its
identity from ambient or undocumented out-of-band context. A caller with the
required stable selectors may explicitly reconstruct a current v1 transcript;
automatic migration is outside the codec. A future new version supplies its own
fixtures and migration/replay policy. A reader may preserve unknown `x-`
members when rewriting a transcript, but must not manufacture or interpret them.
