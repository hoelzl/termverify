---
name: handover-lifecycle
description: Create, update, complete, supersede, or archive a TermVerify handover document. Use when an initiative crosses an ownership, phase, or context boundary, when resuming work from a handover, and when its completion criteria are met.
---

# Handover lifecycle

Rules: [`docs/developer-guide/agent-workflow.md`](../../../docs/developer-guide/agent-workflow.md#handover-lifecycle).
Metadata schema: [`docs/README.md`](../../../docs/README.md#agent-record-metadata).

**Create** `docs/agent/handovers/<initiative>-handover.md` with frontmatter
(`type: handover`, `status: draft` or `active`, `date`, one-line `summary`,
`issue`, `review_by` about six weeks out) and the sections the workflow guide
requires: scope, verified current state, decisions, risks, next actions,
validation evidence, completion or supersession criteria. Record evidence,
not issue-by-issue progress — GitHub tracks volatile state.

**Resume:** read the handover whole, then verify its "current state" against
GitHub and the code before acting; repair the handover if it drifted.

**Update** only at meaningful transitions, and move `review_by` forward when
you re-verify it. Keep it under the working-handover budget enforced by
`scripts/check_doc_freshness.py` by moving completed phases out.

**Finish:** set `status: complete` (or `superseded` with `superseded_by`),
make any body `- **Status:**` bullet agree, add a short Completion/Transition
section, `git mv` it to `docs/agent/handovers/archive/`, and regenerate the
indexes: `uv --no-config run python scripts/build_doc_indexes.py`.

A handover that changes architecture, protocol commitments, security posture,
or baseline governance needs human-readable independent review.
