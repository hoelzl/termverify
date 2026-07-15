# Development Environment

## Tooling

TermVerify uses uv for interpreter management, dependency resolution, virtual
environments, and command execution. Python 3.12 is the minimum installer
version; the continuously supported and tested versions are currently 3.12
through 3.14. The open-ended `>=3.12` package declaration does not promise
support for later Python releases before they join the CI matrix.

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

The uv lockfile supplies the authoritative Ruff executable for direct commands,
hooks, and CI; the local pre-commit hooks invoke that executable rather than a
separately versioned mirror. The local pre-push stage runs tests, mypy, and
package builds; workflow-policy and dependency-vulnerability checks remain
CI-only.

Install the optional local hooks after the first sync:

```bash
uv --no-config run pre-commit install --hook-type pre-commit --hook-type pre-push
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
