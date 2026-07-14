# Development Environment

## Tooling

TermVerify uses uv for interpreter management, dependency resolution, virtual environments, and command execution. The supported baseline is Python 3.12; the project declares Python 3.12+ in `pyproject.toml`.

```bash
uv sync --all-groups
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src tests
```

Install the optional local hooks after the first sync:

```bash
uv run pre-commit install
```

## Repository layout

```text
src/termverify/       distributable library
 tests/                executable behavior contracts
 docs/knowledge/       durable OKF knowledge bundle
 docs/developer-guide/ contributor workflows
 docs/agent/design/    architectural decisions and reuse assessments
 skills/               proven reusable playbooks, added only when warranted
```

## Testing tiers

- **Unit:** pure normalization, comparison, protocol, and replay behavior.
- **Property/state machine:** generated legal and illegal interaction sequences.
- **Integration:** adapters running an application in process or subprocess mode.
- **PTY/end-to-end:** actual terminal input/output and semantic screen observations.

PTY tests must tolerate Windows and CI differences deliberately. A direct adapter remains the fast default; PTY support is required for production-fidelity scenarios, not for every unit test.
