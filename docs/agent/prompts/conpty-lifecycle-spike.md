# Agent Prompt: ConPTY Lifecycle Spike

## Assignment

In an external sibling worktree on a dedicated `spike/` branch, perform a
narrow Windows ConPTY lifecycle feasibility spike. Produce evidence for a later
binding-selection decision; do not implement a production adapter.

## Read first

1. `AGENTS.md`
2. `docs/knowledge/architecture.md`
3. `docs/knowledge/protocol.md`
4. `docs/agent/design/phase-1-protocol-and-windows-boundary.md`
5. `docs/knowledge/evidence-governance.md`

## Scope

- Determine whether a justified binding approach can create a pseudoconsole,
  start a harmless child process, independently drain input/output, resize,
  close, and observe child exit on the supported Windows host.
- Capture only synthetic, non-sensitive evidence. Never persist credentials,
  tokens, user paths, or real terminal content.
- Document exact commands, host assumptions, observed limitations, cleanup
  behavior, candidate binding options, and a recommendation with trade-offs.
- If a dependency is proposed, document rationale and verification plan before
  changing `pyproject.toml` or `uv.lock`.

## Non-goals

- No public adapter API, production ConPTY implementation, or dependency change
  without an explicit reviewed decision.
- No browser bridge, screenshot baseline, or CI artifact upload.
- Do not claim a binding is production-ready from a feasibility spike.

## Acceptance evidence

- A reproducible synthetic smoke result or an explicit blocker with command
  output.
- A focused design note suitable for independent human review.
- Any disposable spike code remains isolated or is removed before a PR unless it
  is approved as durable test infrastructure.
