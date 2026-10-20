---
name: parallel-worktree
description: Create, hand off, or remove a Git worktree for concurrent TermVerify work. Use before starting a second line of work beside another agent, before delegating to a subagent in its own checkout, and after a worktree's branch has merged.
---

# Parallel worktree

The rules and their rationale are in
[`docs/developer-guide/agent-workflow.md`](../../../docs/developer-guide/agent-workflow.md#parallel-worktrees);
read that section first. The procedure:

1. From the clean integration checkout on `main`: `git fetch origin`.
2. Create an **external sibling** worktree on its own branch, on the same
   volume:
   `git worktree add -b <branch> <Projects>/../Worktrees/termverify/<name> origin/main`.
3. In the new worktree: `uv --no-config sync --all-groups --locked`.
4. One writing agent and one branch per worktree. When delegating, give the
   agent the worktree as its working directory and never let it edit the
   integration checkout or another agent's worktree.
5. Do not parallelize competing edits to public API/types, shared fixtures,
   or the same test modules.
6. After the branch merges: `git worktree remove <path>`, then
   `git branch -d <branch>`, then `git worktree prune`.
