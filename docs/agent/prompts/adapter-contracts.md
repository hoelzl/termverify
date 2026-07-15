# Agent Prompt: Adapter Contracts

## Assignment

In an external sibling worktree on a dedicated `feat/` branch, define the
framework-neutral Phase 1 adapter contract and immutable deterministic run
configuration. This is the sequential foundation for direct-adapter, runner,
replay, and PTY work.

## Read first

1. `AGENTS.md`
2. `docs/knowledge/index.md`
3. `docs/knowledge/architecture.md`
4. `docs/knowledge/protocol.md`
5. `docs/agent/design/phase-1-protocol-and-windows-boundary.md`
6. `src/termverify/transcript.py` and its tests

## Scope

- Propose and implement minimal Python types/protocols for deterministic start,
  input dispatch, explicit clock advancement, structured observation, and stop.
- Keep the contract independent of terminal frameworks, clocks, randomness,
  filesystems, and network ambient state.
- Define how adapters report enforced constraints or a structured unsupported
  outcome before input dispatch.
- Use strict TDD: introduce focused red tests, make the minimum implementation,
  then run relevant wider checks.
- Produce a human-readable API rationale and verification plan when public
  types or compatibility commitments are introduced.

## Non-goals

- No ConPTY binding or production PTY adapter.
- No runner, replay engine, comparator, fixture application, or browser bridge.
- Do not change `termverify.transcript/v1` without an explicit compatibility
  analysis and human-review gate.

## Acceptance evidence

- Focused tests prove valid configuration and reject invalid values.
- A small fake adapter can start, dispatch, observe, advance manual time, and
  stop through the proposed contract.
- Strict mypy, Ruff, and the appropriate full repository gate pass.
- Open one focused PR; do not merge or approve architectural changes yourself.
