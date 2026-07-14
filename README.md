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

The repository is in its foundation phase. The initial public contract, developer workflow, architecture, and verification model are documented; implementation begins with the deterministic run configuration and adapter boundary.

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
  └── PTY/browser adapter ───── real interaction and rendering evidence
               │
          TermVerify
  ├── run configuration and interaction protocol
  ├── observation normalization and comparison
  ├── transcript replay and shrinking
  ├── property/state-machine support
  └── reports and CI artifacts
```

See [the knowledge bundle](docs/knowledge/index.md) for the durable architecture and verification model.

## Development

Requirements: [uv](https://docs.astral.sh/uv/) and Python 3.12+ (uv manages the pinned interpreter automatically).

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

## License

Apache License 2.0. See [LICENSE](LICENSE).
