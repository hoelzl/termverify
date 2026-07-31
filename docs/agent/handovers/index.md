# Handover Index

Handover lifecycle and authoring rules are defined in
[`docs/developer-guide/agent-workflow.md`](../../developer-guide/agent-workflow.md).
This index is navigation only; GitHub issues, pull requests, and Git remain the
source of truth for volatile work state.

## Active

- [Pre-release boundary hardening handover](pre-release-boundary-hardening-handover.md)
  — **active**; accepts the transferred vocabulary, correlation, containment,
  schema-distribution, terminal-production, and release-governance boundaries.
  Each remains unsupported until separately accepted and implemented. Phase 2
  is active as of the accepted
  [Phase 2 verification-core boundary decision](../design/phase-2-verification-core-boundary.md)
  (2026-07-19, issue #146), for exactly that design's scope.

## Draft

- [POSIX PTY adapter and examples vertical handover](posix-pty-adapter-and-examples-vertical-handover.md)
  — **draft**; proposed context for the vertical tracked by issue #204. It
  becomes active only when the owner accepts the
  [vertical boundary decision](../design/posix-pty-adapter-and-examples-vertical-boundary.md)
  and answers its five decision requests; no slice is authorized before then.

## Archive

- [Adversarial review 2026-07-24 remediation handover](archive/adversarial-review-2026-07-24-remediation-handover.md)
  — **complete** (retired 2026-07-31); every finding in the
  [2026-07-24 adversarial review](../reviews/adversarial-review-2026-07-24.md)
  (`main` @ `8f33e6c`) was fixed, disclosed, or retired by a recorded owner
  decision across Phases 0–9. No successor: the initiative it names as next
  (a POSIX PTY adapter and an `examples/` vertical, issue #204) was
  deliberately left outside its completion criteria and gets its own handover.
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