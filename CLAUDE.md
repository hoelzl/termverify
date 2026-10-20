# Claude Code Entry Point

@AGENTS.md

## Claude Code Specifics

This file is a thin harness adapter: add nothing here except notes about
Claude Code mechanics. The portability rules are in
`docs/developer-guide/agent-harnesses.md`.

- Never store project knowledge only in Claude Code memory, `.claude/`, or
  session state; other harnesses cannot see it.
- Shared, reviewed configuration belongs in `.claude/settings.json`; personal
  overrides go in the gitignored `.claude/settings.local.json`.
