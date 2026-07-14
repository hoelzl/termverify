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
| Protocol schemas and compatibility | `docs/knowledge/protocol.md` and committed schema files |
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
| Reusable agent playbooks | `skills/` only after their workflow is proven and stable |

`docs/knowledge/` follows OKF: `index.md` files are navigation-only; every other Markdown document has YAML frontmatter with at least a `type` field.

## Validation Before Commit

```bash
uv sync --all-groups
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src tests
uv run pre-commit run --all-files
```

Run the narrowest relevant command during development, then the appropriate wider gate before a commit. Keep changes focused; use a fresh reviewer context for nontrivial code changes.

## Agent-Harness Compatibility

This file is portable by design. Do not rely on a vendor-specific instruction import, plugin, model, or tool. Hermes-specific or other harness-specific conveniences belong in optional integrations, never in the required build/test path.
