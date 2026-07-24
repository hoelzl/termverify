# Prototyping-Stage Protocol Governance (Freeze Suspension)

- **Status:** accepted — decided 2026-07-24 by explicit owner direction,
  recorded during the remediation planning for the
  [2026-07-24 adversarial review](../reviews/adversarial-review-2026-07-24.md).
- **Issue:** tracking issue to be filed in Phase 0 of the
  [remediation handover](../handovers/adversarial-review-2026-07-24-remediation-handover.md);
  this record is the authoritative decision either way.
- **Date:** 2026-07-24
- **Inputs:** the 2026-07-24 adversarial review findings P2 (frozen
  `status: "enforced"` vocabulary contradicting the `delivered` tier), P3
  (freeze fired prematurely on a self-published artifact and needed a
  recorded exception within days — issue #155,
  [`key-v1-punctuation-bases.md`](key-v1-punctuation-bases.md)), and P4 (a
  frozen closed timezone registry v1 gains nothing from); the
  "Compatibility and evolution" policy in
  [`docs/knowledge/protocol.md`](../../knowledge/protocol.md); the state of
  the only known TermVerify users.

## Problem

The inception policy said the first declared real client or supported
external artifact freezes all TermVerify protocol and registry versions. The
0.1.0 PyPI publication on 2026-07-19 pulled that trigger — but no external
client exists, and none was created by the publication. Within days the
freeze forced a recorded "one-time exception" for a needed registry change,
and the adversarial review found frozen-in mistakes (P2's status vocabulary,
P4's dormant registry) whose proper fixes the freeze forbids.

The only known users of TermVerify are two of the owner's own early-stage
projects — **drei** (`C:\Users\tc\Programming\Python\Projects\drei`) and
**GlyphWright** (`C:\Users\tc\Programming\Python\Projects\glyphwright`) —
which *exist to drive TermVerify's design*. Maintaining backward
compatibility for them is inverted: they are expected to migrate with
TermVerify, not to pin it. Under these conditions the freeze produces only
ceremony: version-bump busywork, exception records, and the fiction that
current protocol versions are meaningful compatibility promises to someone.

## Decision

The freeze declared effective 2026-07-19 is **suspended**. TermVerify is in
the **prototyping stage** despite the 0.1.0 release, and remains there until
the owner explicitly declares it ready for external clients.

While the prototyping stage lasts:

1. **All TermVerify protocols and registries may change incompatibly in
   place** — `termverify.transcript/v1`, `termverify.key/v1`,
   `termverify.key-encoding/v1`, `termverify.timezone/v1`, and the JSONL
   control protocol. No version bump, compatibility shim, migration path, or
   per-change exception decision is required for an incompatible change.
2. **No backward compatibility is owed to anyone.** There are no external
   clients. The published 0.1.0 artifact is a distribution-pipeline
   exercise, not a supported compatibility surface. drei and GlyphWright are
   design-driver users and migrate with TermVerify; breaking them is
   acceptable and expected.
3. **The change discipline stays; the ceremony goes.** Protocol changes
   still require the normal slice loop (issue, TDD evidence, review), still
   migrate repository fixtures in the same reviewed change, and still update
   the protocol documentation in the same change. What is dropped is the
   compatibility ceremony, not the engineering rigor.
4. **Version identifiers remain as labels, not promises.** `/v1` continues
   to name the current shape so readers can reject foreign input; it does
   not imply stability across TermVerify revisions.

**Exit criterion:** the prototyping stage ends only by an explicit recorded
owner decision that TermVerify is usable by external clients — not by any
release, publication, or artifact event (the 0.1.0 experience shows those
are the wrong trigger). At that boundary, freeze and versioning guarantees
are re-established by a fresh recorded design (the review's recommendation
12 — e.g. "frozen for consumers, amendable by recorded owner decision until
a third-party consumer is declared" — is input to that future design).

## Consequences

- Review finding **P3** is resolved: the premature freeze is acknowledged
  and suspended rather than patched with accumulating exceptions.
- Review finding **P2** can be fixed properly on the wire (correct the
  `capability.result.status` vocabulary to be tier-truthful) instead of
  being papered over in prose.
- Review finding **P4**: the timezone registry may be trimmed, reworked, or
  removed in place; its disposition is a separate owner decision, no longer
  constrained by the freeze.
- The issue #155 amendment's framing as a "one-time post-freeze exception
  that sets no precedent" is historical — it dates from the
  2026-07-19 – 2026-07-24 window in which the freeze was considered active.
  The record stands; the precedent pressure is void.
- `docs/knowledge/protocol.md` "Compatibility and evolution" and the
  `AGENTS.md` protocol row state the prototyping status and link here, so
  future agents do not rediscover or re-impose the freeze.
- Review finding **P9** (doc/code authority polarity) is resolved in the
  same direction, by owner decision 2026-07-24: **code wins everywhere**
  for the duration of the prototyping stage, including for the control
  protocol, whose specification previously claimed the opposite. A
  doc/codec disagreement is a defect repaired doc-side by default, and
  code-side through an ordinary test-first slice when the codec is the
  wrong one. The polarity is a consequence of this stage, not a permanent
  stance: at the exit criterion above it is revisited together with freeze
  and versioning, because doc-as-contract becomes defensible once
  third-party subjects implement the control protocol against a
  specification that has stopped moving.

## Rejected alternatives

- **Keep the freeze, patch findings in prose** (P2 Option A/C): contains
  each overstatement behind documentation while the underlying protocol
  mistakes ossify; serves no consumer, since none exists.
- **Keep the freeze, amend via per-change recorded exceptions**: this is
  the trajectory the review flagged — the first test of the rule already
  required an exception, and each further "one-time" exception erodes the
  meaning of both the freeze and the exceptions.
- **Version-bump on every incompatible change** (`v2`, `v3`, …): creates
  fictional compatibility history for clients that do not exist and imposes
  migration busywork on the two internal design-driver projects.
