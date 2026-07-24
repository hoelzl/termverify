# TermVerify

Protocol-driven verification for autonomous terminal applications.

TermVerify is a Python library and reference toolkit for testing terminal and TUI applications through reproducible interaction. It combines direct semantic adapters with real PTY-driven runs, then compares structured observations rather than relying only on brittle raw-terminal snapshots.

## Why

An autonomous coding agent is most reliable when it can make a change, exercise the actual program, observe meaningful results, and leave behind replayable evidence. Terminal applications need this especially badly: unit tests alone do not prove that key bindings, focus, rendering, prompts, and real interaction work.

TermVerify provides a common foundation for:

- deterministic interaction transcripts and replay;
- semantic state and UI observations;
- property/state-machine testing;
- reviewed golden snapshots;
- differential tests against a reference implementation or execution mode;
- failure minimization and CI-ready artifacts.

## Project status

The repository is in its foundation phase. The reviewed transcript design has
an initial codec, semantic validator, mandatory safe transcript-persistence
boundary, immutable producer-side adapter contract, and deterministic in-process
direct runtime. Requested timezone names and semantic key chords use closed,
protocol-owned v1 registries; semantic keys also have an immutable direct-dispatch
representation. The canonical transcript schema ships inside the package with a
public access API, and isolated installation checks verify the wheel and sdist
resource contract; the schema's `$id` resolves at
[termverify.dev](https://termverify.dev/schemas/termverify.transcript/v1.schema.json)
as a byte-identical mirror of the committed resource, and runtime validation
remains authoritative. A strict no-regression coverage floor gates the full
suite. Release governance is defined — changelog policy, private security
disclosure, reviewed release checklist, and a tag-triggered attested release
workflow — and termverify 0.1.0 was published to PyPI on 2026-07-19 through
that CI-gated workflow. That publication was a distribution-pipeline
exercise, not a stability promise: TermVerify is in its **prototyping
stage**, no backward compatibility is guaranteed for any published artifact,
and protocols and APIs may change incompatibly without notice until the
owner declares readiness for external clients (recorded governance decision:
[prototyping-stage protocol governance](docs/agent/design/prototyping-stage-protocol-governance.md)). A Windows ConPTY
adapter with Windows-matrix evidence covers native pseudoconsole ownership
and close, end-of-stream draining, process-tree teardown,
cancellation/recovery, resize epochs, and replayable evidence normalization,
and the first fully verified terminal run has landed using opt-in
cooperation-tier constraint ports: the six non-terminal constraints are
delivered to the subject's environment with truthful `delivered` receipts,
honored by subject cooperation rather than OS enforcement. OS-level
containment is an explicit non-goal by recorded owner decision; TermVerify
verifies applications whose authors control the subject and is not an
execution sandbox for adversarial code. Configuration values or receipt
construction alone do not prove constraint enforcement.

## Design principles

1. **Semantic evidence first.** Verify state, events, and explicit UI semantics before comparing raw ANSI output.
2. **Production interaction still matters.** PTY/terminal tests validate the application a person or agent actually drives.
3. **Determinism is a contract.** Seeds, clock, locale, terminal size, filesystem sandbox, and network policy are explicit.
4. **Human review owns baselines.** Agents may propose snapshot updates; they never silently bless them.
5. **Harness-neutral by default.** The project works with Hermes, Claude Code, Codex, OpenCode, and ordinary CI without a required proprietary integration.

## Planned architecture

```text
application under test
  ├── direct semantic adapter ── fast properties, replay, differential tests
  └── PTY adapter ───────────── real terminal interaction and rendering evidence
               │
          TermVerify
  ├── run configuration and interaction protocol
  ├── observation normalization and comparison
  ├── transcript replay and shrinking
  ├── property/state-machine support
  └── reports and CI artifacts
```

See [the knowledge bundle](docs/knowledge/index.md) for the durable architecture and verification model.
Browser bridging is deferred until the terminal vertical slice proves a shared
abstraction is necessary.

## Development

Requirements: [uv](https://docs.astral.sh/uv/) and Python 3.12 or newer. The
minimum installer version is 3.12; the continuously supported and tested
versions are currently 3.12 through 3.14. Support for later Python releases is
not implied until they join the CI matrix.

```bash
uv --no-config sync --all-groups --locked
uv --no-config run pytest --cov --cov-report=term-missing
uv --no-config run ruff check .
uv --no-config run ruff format --check .
uv --no-config run mypy src tests scripts
uv --no-config run pre-commit run --all-files
uv --no-config run pre-commit run --hook-stage pre-push --all-files
uv --no-config build
uv --no-config run pre-commit install --hook-type pre-commit --hook-type pre-push
```

See [developer workflow](docs/developer-guide/agent-workflow.md) and [contributing guide](CONTRIBUTING.md).
External subjects implementing the producer contract start with the
[adapter-author surface](docs/developer-guide/adapter-authors.md).

## License

Apache License 2.0. See [LICENSE](LICENSE).
