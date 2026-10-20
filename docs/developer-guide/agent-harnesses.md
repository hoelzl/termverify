---
summary: How agent harnesses reach AGENTS.md, the portability rules, and which harness-specific files the repository ships.
---

# Agent Harnesses

Root `AGENTS.md` is the only authoritative agent instruction file. This guide
records how agent harnesses reach it and which harness-specific files the
repository deliberately does or does not ship. Read it before adding or
changing a harness entry point or harness configuration.

## Portability rules

- `AGENTS.md` is portable by design. Do not rely on a vendor-specific
  instruction import, plugin, model, or tool in the required build and test
  path. Harness-specific conveniences (Hermes, Claude Code, Codex, OpenCode,
  or others) belong in optional integrations.
- `AGENTS.md` and the documents it references are the only authoritative
  agent instructions. A harness entry point — for example the root
  `CLAUDE.md` for Claude Code — stays a thin pointer to `AGENTS.md` and may
  add only notes about that harness's mechanics, never project knowledge.
- Write durable knowledge to the repository locations in the
  [documentation map](../README.md). Never leave it only in a harness's
  private memory, state directory, or session context; other harnesses cannot
  see it.
- Harness state directories (`.hermes/`, `.claude/`) are local-only and
  gitignored, except deliberately shared harness configuration such as
  `.claude/settings.json`. Personal overrides go in
  `.claude/settings.local.json`. The authoritative copy of any plan or
  decision found in a harness directory belongs under `docs/agent/`.
- `AGENTS.md` and `CLAUDE.md` are loaded into every request by the harnesses
  that read them. Their size is gated by `scripts/validate_prose_status.py`;
  move task-specific detail into a guide like this one and leave a one-line
  pointer.

## Nested instruction files

The repository ships no nested `AGENTS.md` or `CLAUDE.md` files. Harnesses
resolve nested instruction files differently: Codex concatenates every
`AGENTS.md` from the project root down to the working directory, other
harnesses pick the nearest file, make nesting opt-in, or read their own file
names instead. Nested guidance would therefore reach each harness differently.
Directory-specific guidance belongs in the documentation indexes, which every
harness reads the same way.

## GitHub Copilot surfaces

Root `AGENTS.md` is the canonical repository instruction source for GitHub
Copilot. Which Copilot surfaces read `AGENTS.md`, and which read only
`.github/copilot-instructions.md`, changes between releases; the
[GitHub support matrix](https://docs.github.com/en/copilot/reference/custom-instructions-support)
is the authority.

TermVerify deliberately ships no `.github/copilot-instructions.md`, because it
would duplicate `AGENTS.md`. Surfaces that read only that file are out of
scope. Revisit the decision only if a contributor demonstrates a need on one
of them; if the file is added, it must stay a pointer to `AGENTS.md`.
