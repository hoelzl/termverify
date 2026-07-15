# Phase 1 Worktree Agent Prompts

These prompts provide bounded starting context for concurrent TermVerify work.
They are not issue trackers or architectural approvals. Before editing, each
agent must read `AGENTS.md`, the current GitHub issue/PR state, and the source
of truth named in its prompt.

Create one external sibling worktree and one branch per prompt, as described in
[`docs/developer-guide/agent-workflow.md`](../../developer-guide/agent-workflow.md).
Do not run two prompts that edit the same public API, shared fixture, or test
module concurrently.

## Available prompts

- [Adapter contracts](adapter-contracts.md) — sequential foundation for the
  direct-adapter vertical slice.
- [ConPTY lifecycle spike](conpty-lifecycle-spike.md) — parallel research only;
  no production adapter or binding selection.
- [Phase 1 documentation reconciliation](phase1-documentation-reconciliation.md)
  — independent stale-documentation correction.
- [Transcript fixture corpus](transcript-fixture-corpus.md) — independent
  fixture/schema expansion constrained by the accepted v1 protocol.

The adapter-contract prompt establishes the API boundary. Runner, replay,
comparator, fake-application, and production-adapter implementation should wait
for that contract to be independently reviewed and accepted.
