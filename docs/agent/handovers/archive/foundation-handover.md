# Foundation Handover

## Feature overview

The foundation phase establishes TermVerify as a reusable Python project for protocol-driven verification of terminal applications. It intentionally delivers contracts, documentation, tooling, and a minimal public API before implementing runners or adapters.

## Design decisions

- **Library first:** TermVerify is a distributable `src/`-layout Python package, not a game-specific repository.
- **Deterministic protocol:** verified runs make environmental inputs explicit instead of reading ambient randomness, time, terminal size, locale, filesystem, or network state.
- **Two adapter modes:** direct adapters optimize property/replay tests; PTY/browser adapters verify the real user-facing path.
- **Layered oracles:** golden masters are optional. Semantic, replay, property, differential, metamorphic, persistence, and reviewed snapshot evidence are peers.
- **Portable agent context:** root `AGENTS.md` carries compact cross-harness rules; durable details use an OKF knowledge bundle.
- **Documentation generation:** OKF is used now for durable knowledge. OpenWiki is deferred until a vertical slice produces enough implementation to make generated documentation valuable and reviewable.

## Phase breakdown

### Phase 0: Foundation [DONE]

Create package metadata, test/lint/type tooling, portable agent documentation, OKF knowledge pages, CI, and this handover.

Acceptance criteria:

- `uv sync --all-groups` produces a locked environment.
- Targeted package API test passes.
- Quality and documentation checks run locally and in CI.
- The repository explains its architecture, verification model, documentation policy, and R://N reuse procedure.

### Phase 1: Deterministic contracts [TODO]

Implement immutable run configuration, input-event schemas, observation primitives, adapter protocol, and serialization tests.

Acceptance criteria:

- Valid deterministic configuration is serializable and rejects invalid values.
- A minimal fake application adapter can be started, dispatched to, observed, and stopped.
- No production code depends on a terminal UI framework.

### Phase 2: Transcript replay and semantic comparison [TODO]

Implement JSONL transcript parsing, deterministic replay, normalized observations, comparison verdicts, and readable reports.

### Phase 3: Reference fixtures [TODO]

Build a small deterministic tile-world application and a constrained editor fixture to dogfood direct and terminal adapters.

### Phase 4: PTY integration [TODO]

Implement a robust PTY process adapter with readiness conditions, terminal snapshots, artifacts, and Windows-compatible strategy.

## Current status

Phase 0 is complete and published on `main`. The repository has a locked uv environment, local pre-commit hooks, passing Python 3.12/3.13 CI, a validated OKF knowledge bundle, Apache-2.0 licensing, and the initial public package contract. No protocol runner, adapter, fixture, or copied R://N code exists yet.

## Next step

Begin Phase 1 with a focused design for `RunConfig`, `InputEvent`, `Observation`, and `ApplicationAdapter`. Write behavior tests before implementation and keep all types framework-neutral.

## Key files

- `AGENTS.md`: portable, compact project rules and source-of-truth table.
- `docs/knowledge/`: OKF durable design knowledge.
- `docs/developer-guide/agent-workflow.md`: agent-first evidence loop.
- `docs/agent/design/recursive-neon-reuse-assessment.md`: deliberate reuse procedure.
- `pyproject.toml`: package and quality-tool configuration.
- `.github/workflows/ci.yml`: Python and documentation-contract CI.

## Testing approach

The initial gate uses pytest, Ruff, mypy, pre-commit, and an OKF-frontmatter validation script. Later phases add unit, property, integration, and PTY tests.
