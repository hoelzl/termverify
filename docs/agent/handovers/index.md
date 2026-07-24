# Handover Index

Handover lifecycle and authoring rules are defined in
[`docs/developer-guide/agent-workflow.md`](../../developer-guide/agent-workflow.md).
This index is navigation only; GitHub issues, pull requests, and Git remain the
source of truth for volatile work state.

## Active

- [Adversarial review 2026-07-24 remediation handover](adversarial-review-2026-07-24-remediation-handover.md)
  — **active**; plans and tracks remediation of every finding in the
  [2026-07-24 adversarial review](../reviews/adversarial-review-2026-07-24.md)
  (`main` @ `8f33e6c`) through phased, slice-based fixes, disclosures, and
  recorded owner decisions.
- [Pre-release boundary hardening handover](pre-release-boundary-hardening-handover.md)
  — **active**; accepts the transferred vocabulary, correlation, containment,
  schema-distribution, terminal-production, and release-governance boundaries.
  Each remains unsupported until separately accepted and implemented. Phase 2
  is active as of the accepted
  [Phase 2 verification-core boundary decision](../design/phase-2-verification-core-boundary.md)
  (2026-07-19, issue #146), for exactly that design's scope.

## Draft

None.

## Archive

- [Phase 1 readiness hardening handover](archive/phase-1-readiness-hardening-handover.md)
  — **superseded**; its amended completion boundary passed independent integrated
  review, and every transferred criterion moved intact to the active Pre-release
  Boundary Hardening successor. That supersession did not activate Phase 2.
- [Adversarial review remediation handover](archive/adversarial-review-remediation-handover.md)
  — **complete**; Slices 1–8 and every accepted source-review disposition were
  integrated, reconciled, and accepted by final independent review through PR
  #80.
- [Foundation handover](archive/foundation-handover.md) — **complete**; Phase 0
  established the initial package, workflow, documentation, and CI foundation.
- [Quality hardening handover](archive/quality-hardening-handover.md) —
  **complete**; delivered the July 2026 delivery controls, evidence governance,
  and executable transcript-v1 contract prerequisites.