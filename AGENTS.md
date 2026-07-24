# TermVerify — Agent Guide

TermVerify is a Python library and reference tooling for verifying autonomous terminal applications. It treats deterministic behavior, replayable evidence, and human review as product features.

## Start Here

1. Read `README.md` for the current public intent.
2. Read `docs/knowledge/index.md`, then retrieve only the knowledge pages relevant to the task.
3. Read the applicable document under `docs/developer-guide/` before changing tooling or workflows.
4. Treat executable checks and working code as authoritative over prose when they disagree; update stale documentation in the same change.

## Commands and Sources of Truth

| Question | Authoritative source |
| --- | --- |
| Dependencies and supported Python versions | `pyproject.toml` and `uv.lock` |
| Test, lint, format, and type-check commands | `pyproject.toml`, `.pre-commit-config.yaml`, and CI workflow |
| Public API | `src/termverify/` plus tests |
| Protocol conformance and compatibility | Runtime validation in `src/termverify/transcript.py` is authoritative for protocol acceptance; the packaged Draft 2020-12 schema (`termverify.transcript_schema_v1_bytes()`) is a non-exhaustive structural aid — schema acceptance is not conformance. Policy and rationale: `docs/knowledge/protocol.md`. TermVerify is in the prototyping stage: no protocol or registry is frozen, and incompatible in-place changes need no version bump or compatibility shim (owner decision 2026-07-24, `docs/agent/design/prototyping-stage-protocol-governance.md`) |
| Architecture decisions | `docs/knowledge/architecture.md` and ADRs under `docs/agent/design/` |
| Current work state | GitHub issues/PRs and `git status`; do not encode volatile state in this file |

## Non-Negotiable Engineering Rules

- Use `uv`; do not use `pip install` or edit `uv.lock` manually.
- Use Python 3.12+ and `src/` layout imports.
- Follow strict TDD for behavioral changes: write a focused failing test, run it, implement the minimum, rerun it, then run the relevant wider checks.
- Keep the deterministic core independent of terminal, clock, randomness, filesystem, and network ambient state. Inject those dependencies through explicit ports/configuration.
- Treat terminal output as evidence, not the sole correctness oracle. Prefer structured observations, state/event assertions, replay transcripts, and properties.
- Preserve replayability: seeds, terminal dimensions, locale, time, and filesystem sandbox must be explicit in verified runs.
- Do not update golden masters automatically. Snapshot or baseline changes require a human-readable diff and explicit review.
- Do not add a dependency, change the public protocol, or copy source from another project without documenting the rationale and verification plan.

## Documentation Placement

| Document kind | Location |
| --- | --- |
| Human-facing introduction and quick start | `README.md` |
| Developer guides and operating workflows | `docs/developer-guide/` |
| Durable architecture, protocol, terminology, and verification knowledge | `docs/knowledge/` (OKF bundle) |
| Agent design decisions, reuse assessments, and handovers | `docs/agent/design/` and `docs/agent/handovers/` |
| Durable implementation plans for accepted initiatives | `docs/agent/plans/` |
| Adversarial and independent review reports | `docs/agent/reviews/` |
| Reusable agent playbooks | `skills/` only after their workflow is proven and stable |

`docs/knowledge/` follows OKF: `index.md` files are navigation-only; every other Markdown document has YAML frontmatter with at least a `type` field.

## Validation Before Commit

```bash
uv --no-config sync --all-groups --locked
uv --no-config run pytest --cov --cov-report=term-missing
uv --no-config run ruff check .
uv --no-config run ruff format --check .
uv --no-config run mypy src tests scripts
uv --no-config run pre-commit run --all-files
uv --no-config run pre-commit run --hook-stage pre-push --all-files
uv --no-config build
```

Run the narrowest relevant command during development, then the appropriate wider gate before a commit. Keep changes focused; use a fresh reviewer context for nontrivial code changes.

## Parallel Worktrees

For concurrent work, use one branch and one external sibling worktree per
agent; keep the primary checkout as the clean integration point. Always give an
agent its assigned worktree as its working directory. Read
`docs/developer-guide/agent-workflow.md` before creating, sharing, or removing
worktrees; it defines the required isolation, setup, and cleanup rules.

## Agent-Harness Compatibility

This file is portable by design. Do not rely on a vendor-specific instruction import, plugin, model, or tool. Hermes-specific or other harness-specific conveniences belong in optional integrations, never in the required build/test path.

- `AGENTS.md` and the documents it references are the only authoritative agent instructions. Harness entry points (for example the root `CLAUDE.md` for Claude Code) must stay thin pointers to this file and may add only harness-mechanics notes, never project knowledge.
- Write durable knowledge — decisions, plans, handovers, workflow rules — to the repository locations in the Documentation Placement table. Never leave it only in a harness's private memory, state directory, or session context.
- Harness state directories (`.hermes/`, `.claude/`) are local-only and gitignored, except deliberately shared harness configuration such as `.claude/settings.json`. The authoritative copy of any plan or decision they contain must live under `docs/agent/`.

## GitHub Copilot Surfaces

Root `AGENTS.md` is the canonical repository instruction source for GitHub Copilot. Per the current [GitHub support matrix](https://docs.github.com/en/copilot/reference/custom-instructions-support), `AGENTS.md` is consumed by Copilot cloud agent, GitHub.com Copilot code review, VS Code Copilot Chat, Xcode, JetBrains, and Copilot CLI — the surfaces TermVerify intends to support. GitHub.com Copilot Chat, VS Code Copilot code review, Visual Studio, and Eclipse read only `.github/copilot-instructions.md`; TermVerify deliberately does not ship that file (it would duplicate this document) and treats those surfaces as out of scope. Revisit only if a contributor demonstrates need on one of them.
