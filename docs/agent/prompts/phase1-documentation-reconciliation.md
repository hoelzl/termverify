# Agent Prompt: Phase 1 Documentation Reconciliation

## Assignment

In an external sibling worktree on a dedicated `docs/` branch, reconcile stale
Phase 1 status language after the transcript-v1 contracts landed in PR #8 and
the quality-hardening handover closed in PR #9.

## Read first

1. `AGENTS.md`
2. `README.md`
3. `docs/knowledge/index.md`
4. `docs/knowledge/protocol.md`
5. `docs/knowledge/architecture.md`
6. `docs/agent/design/phase-1-protocol-and-windows-boundary.md`
7. `docs/agent/handovers/archive/quality-hardening-handover.md`

## Scope

- Update stale claims that the repository has no executable protocol contracts
  or that schemas/fixtures/serialization tests are pending.
- Preserve the boundary: adapter runtime, replay/comparison, and production PTY
  work are still not implemented.
- Update README/project-status language only when it can be grounded in merged
  code and tests.
- Keep durable knowledge and implementation-status wording consistent without
  turning navigation indexes or `AGENTS.md` into issue trackers.

## Non-goals

- No protocol change, adapter implementation, dependency change, or architectural
  decision.
- Do not reopen or duplicate closed issue state.

## Acceptance evidence

- Search shows no contradictory pending-contract claims in the touched scope.
- Documentation validation, relevant tests, and `git diff --check` pass.
- Open one focused documentation PR.
