# Claude Code Entry Point

@AGENTS.md

## Claude Code Specifics

This file is a thin harness adapter. All authoritative agent instructions live
in `AGENTS.md` and the documents it references; add nothing here except notes
about Claude Code mechanics.

- Write durable knowledge — decisions, plans, handovers, workflow rules — to
  the harness-independent locations in the `AGENTS.md` Documentation Placement
  table. Never store project knowledge only in Claude Code memory, `.claude/`,
  or session state; other harnesses cannot see it.
- Shared, reviewed Claude Code configuration belongs in
  `.claude/settings.json`. Personal overrides go in
  `.claude/settings.local.json`, which is gitignored.
