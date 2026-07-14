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
