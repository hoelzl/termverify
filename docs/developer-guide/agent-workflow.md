# Agent-First Development Workflow

TermVerify is developed so that human developers and autonomous coding agents can follow the same evidence-producing loop.

## Tight loop

1. **Orient:** read `AGENTS.md`, the smallest relevant knowledge pages, and executable sources of truth.
2. **Specify:** express one observable behavior as a unit test, property, transcript, or semantic snapshot expectation.
3. **Red:** run it and observe the expected failure.
4. **Green:** make the minimum implementation change.
5. **Exercise:** drive the application through the appropriate adapter; use PTY mode when the user-facing terminal path is relevant.
6. **Review:** inspect diffs and reports, then run the wider quality gate.
7. **Preserve:** turn every discovered bug into durable, replayable evidence.

## Context budget

Always-loaded instructions must stay short. Use this retrieval order:

```text
AGENTS.md
  → docs/knowledge/index.md
    → one or two relevant concept documents
      → source/tests for the exact behavior
```

Do not paste architecture dumps, old handovers, generated wiki pages, or volatile issue state into `AGENTS.md`.

## Parallel worktrees

Use Git worktrees when independent, reviewable changes can proceed without
editing the same public API or test fixture. The default layout is external
sibling worktrees, not nested copies inside this repository:

```text
C:\Users\<user>\Programming\Python\Projects\termverify        # clean integration checkout
C:\Users\<user>\Programming\Python\Worktrees\termverify\
  adapter-contracts\
  conpty-spike\
  docs-phase1-reconciliation\
```

An external layout prevents recursive repository scans, editor indexing, test
discovery, and agent context retrieval from crossing into other working copies.
Git still stores the worktree metadata in the primary checkout's `.git`
directory. A tool-specific nested location such as `.claude/worktrees/` is
allowed for that tool, but is not the repository's canonical layout.

Create worktrees from an updated integration checkout and keep all Windows
worktrees on the same volume:

```bash
git fetch origin
git worktree add -b feat/adapter-contracts \
  /c/Users/<user>/Programming/Python/Worktrees/termverify/adapter-contracts \
  origin/main
```

Rules:

1. Assign exactly one writing agent and one branch to each worktree.
2. Give every agent an explicit working directory; do not let it edit the
   integration checkout or another agent's worktree.
3. Keep the integration checkout on `main` and clean except while integrating
   a reviewed change. Do not develop directly in it.
4. Run `uv --no-config sync --all-groups --locked` in each new worktree before
   development. The shared uv download cache is safe; generated outputs remain
   isolated by worktree.
5. Do not parallelize competing edits to public API/types, shared fixtures, or
   the same test modules. Sequence dependent work behind an accepted contract.
6. Give each worktree a focused issue, PR, and validation evidence. A worktree
   is not a substitute for a branch or review boundary.
7. After merge, remove the physical worktree before deleting its local branch:

   ```bash
   git worktree remove /c/Users/<user>/Programming/Python/Worktrees/termverify/adapter-contracts
   git branch -d feat/adapter-contracts
   git worktree prune
   ```

Worktree-specific agent prompts live under `docs/agent/prompts/`; use them as
starting context, then inspect the current issue, branch, and source before
editing.

## Handover lifecycle

Handover documents preserve the verified context needed to transfer a bounded
initiative or phase. They are not task trackers: GitHub issues, pull requests,
and Git remain the source of truth for volatile work state.

Create one handover under `docs/agent/handovers/` when an initiative crosses a
meaningful ownership, phase, or context boundary. Name it
`<initiative>-handover.md`. An active handover must state its status, optional
owner, whether review is required, scope, verified current state, decisions,
risks, next actions, validation evidence, and completion or supersession
criteria.

Use these statuses:

- **draft:** proposed context, not yet accepted as the working handover;
- **active:** the current handover for its initiative;
- **blocked:** active work cannot proceed without an explicit decision or
  external dependency;
- **complete:** all documented completion criteria have been verified;
- **superseded:** a named successor replaces this handover.

Update handovers only at meaningful transitions and record evidence rather
than copying issue-by-issue progress. A handover that changes architectural
decisions, protocol commitments, security posture, or baseline governance
requires human-readable independent review.

When a handover becomes complete or superseded, move it to
`docs/agent/handovers/archive/` and update
`docs/agent/handovers/index.md` with its final status and successor, if any.
Do not delete it: the archived document and Git history preserve the rationale
needed for future work. `index.md` is navigation only; it must not duplicate
the handover's volatile detail.

## Evidence hierarchy

Prefer, in order:

1. direct semantic assertions over internal state/events;
2. deterministic transcript replay;
3. property/state-machine checks;
4. differential comparisons where a genuine reference exists;
5. reviewed UI semantic snapshots;
6. raw ANSI text only as diagnostic evidence.

## Review boundaries

An agent may generate code, fixtures, and candidate baseline updates. It must not silently approve its own snapshot/golden-master change. A human-readable report and independent review are required for changed expected behavior.
