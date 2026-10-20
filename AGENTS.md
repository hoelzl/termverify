# TermVerify — Agent Guide

TermVerify treats deterministic behavior, replayable evidence, and human review
as product features. `README.md` is the canonical public description. This file
is the agent-facing map: it is loaded on every request, so it holds only what
every task needs and points to the rest.

## Where to look

Read only what the task needs:

| Task | Start with |
| --- | --- |
| Product scope and current capabilities | `README.md` |
| Concepts: architecture, protocols, evidence, verification | `docs/knowledge/index.md`, then one or two pages |
| Tooling, adapters, workflows, release (read before changing them) | `docs/developer-guide/index.md` |
| Past decisions, reviews, plans, handovers | `docs/README.md` (map of `docs/agent/`) |
| Writing, moving, or retiring a document | `docs/README.md` (placement rules) |
| Harness entry points and configuration | `docs/developer-guide/agent-harnesses.md` |
| Parallel worktrees (read before creating, sharing, or removing one) | `docs/developer-guide/agent-workflow.md` |
| Changelog fragments, handovers, reviews, releases, worktrees, doc gardening | `.agents/skills/` (each `SKILL.md` says when to use it) |

When delegating to another agent in a worktree, always give it that worktree as
its working directory.

## Sources of truth

Executable checks and working code are authoritative over prose. A
disagreement is a defect: repair the prose by default, in the same change, and
change code only through a test-first slice.

| Question | Authoritative source |
| --- | --- |
| Dependencies | `pyproject.toml`, `uv.lock` |
| Supported Python versions | `docs/developer-guide/development.md` (the CI matrix) |
| Quality gates | `scripts/check.py` (prints each command it runs) |
| Public API | `src/termverify/` plus tests |
| Transcript acceptance (`termverify.transcript/v1`) | `src/termverify/transcript.py`; the packaged schema is a non-exhaustive aid, not a conformance verdict; policy in `docs/knowledge/protocol.md` |
| Control-protocol acceptance (`termverify.control/v1`) | `src/termverify/control.py`; specification in `docs/knowledge/control-protocol.md` |
| Protocol freeze, compatibility stage, and the scope of code-over-prose for protocols | `docs/agent/design/prototyping-stage-protocol-governance.md` |
| Current work state | GitHub issues and pull requests, `git status` — never this file |

## Non-negotiable engineering rules

- Use `uv --no-config`; never `pip install` or edit `uv.lock` by hand.
- Use Python 3.12+ and `src/` layout imports.
- Strict TDD for behavioral changes: write a focused failing test, run it,
  implement the minimum, rerun it, then run the wider checks.
- Keep the deterministic core free of ambient terminal, clock, randomness,
  filesystem, and network state; inject them through explicit ports.
- Terminal output is evidence, not the sole oracle. Prefer structured
  observations, state/event assertions, replay transcripts, and properties.
- Verified runs make seeds, terminal dimensions, locale, time, and the
  filesystem sandbox explicit.
- Never update golden masters automatically; a baseline change needs a
  human-readable diff and explicit review.
- Adding a dependency, changing the public protocol, or copying source from
  another project needs a documented rationale and verification plan.
- Durable knowledge goes into the repository (see `docs/README.md`), never
  only into a harness's memory or session state.

## Before committing

Run the narrowest relevant test while developing, then
`uv --no-config run python scripts/check.py` (pre-commit hooks) before a
commit and `scripts/check.py --full` before a push. Keep changes focused; use a
fresh reviewer context for nontrivial code changes.
