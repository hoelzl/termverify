# Worktree Agent Prompts

These prompts provide bounded starting context for concurrent TermVerify work.
They are not issue trackers or architectural approvals. Before editing, each
agent must read `AGENTS.md`, the current GitHub issue/PR state, and the source
of truth named in its prompt.

Create one external sibling worktree and one branch per prompt, as described in
[`docs/developer-guide/agent-workflow.md`](../../developer-guide/agent-workflow.md).
Do not run two prompts that edit the same public API, shared fixture, or test
module concurrently.

Every prompt carries a `status` in its frontmatter: `current` prompts may be
run; `retired` prompts were delivered or overtaken and are kept as execution
records only.

The generated [index](index.md) lists every prompt with its status.

The adapter-contract prompt establishes the API boundary. Runner, replay,
comparator, fake-application, and production-adapter implementation should wait
for that contract to be independently reviewed and accepted.
