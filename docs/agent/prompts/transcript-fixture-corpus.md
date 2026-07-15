# Agent Prompt: Transcript Fixture Corpus

## Assignment

In an external sibling worktree on a dedicated `test/` or `feat/` branch,
expand the committed `termverify.transcript/v1` fixture corpus and its
fixture-driven compatibility coverage without changing the accepted protocol.

## Read first

1. `AGENTS.md`
2. `docs/knowledge/protocol.md`
3. `docs/knowledge/evidence-governance.md`
4. `schemas/termverify.transcript/v1.schema.json`
5. `src/termverify/transcript.py`
6. `tests/test_transcript.py` and `tests/fixtures/transcripts/v1/`

## Scope

- Add synthetic canonical valid fixtures covering normal completion,
  early-unsupported constraints, observations with optional frame/process
  evidence, and permitted `x-` extensions.
- Add narrowly targeted invalid fixtures for lifecycle, payload, canonicalization,
  duplicate-member, and incompatible-protocol rejection paths.
- Add fixture-driven parser/serializer acceptance and rejection tests.
- Keep fixture evidence synthetic and comply with the accepted redaction and
  baseline-governance policy. Do not introduce real paths, secrets, clipboard
  content, or captured terminal sessions.
- Expand schema annotations only where they faithfully express existing accepted
  v1 envelope semantics; semantic cross-record validation remains executable.

## Non-goals

- No adapter API or runtime implementation.
- No protocol version change, baseline approval automation, or automatic golden
  master update.

## Acceptance evidence

- Each behavior starts with a focused red test or invalid fixture and ends green.
- Canonical fixture bytes have a readable, reviewable diff.
- Full relevant validation passes; open one focused PR for review.
