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
separately versioned mirror. The local pre-push stage runs mypy, package
builds, and then the test suite — cheapest first, so a trivially fixable type
or packaging failure aborts the push in seconds rather than after the
multi-minute suite (issue #168); workflow-policy and
dependency-vulnerability checks remain CI-only.

When a push fails with only git's generic `error: failed to push some refs`,
the cause is local, not a remote race: a pre-push hook failed and its output
was lost to piping or buried under earlier hook output. Never retry with
`--no-verify` — that pushes commits CI will reject. Instead rerun the gate
in the foreground, where the failing hook's banner and captured output are
visible:

```bash
uv --no-config run pre-commit run --hook-stage pre-push --all-files
```

To skip the suite while diagnosing, run the cheap checks directly
(`uv --no-config run mypy src tests scripts`, then `uv --no-config build`)
before re-running the full stage.

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
 docs/agent/reviews/   adversarial and independent review reports
```

(A `skills/` directory for proven reusable playbooks is reserved by the
`AGENTS.md` placement table but does not exist yet.)

## Coverage ratchet

The combined line-and-branch coverage of the full suite is gated by the
committed `fail_under` floor in `pyproject.toml`. The floor is a no-regression
rule, not a target: it is the integer floor of the reviewed observed total at
activation or at the most recent accepted raise, never an invented aspiration.
The committed `precision = 2` makes the comparison a strict floor rather than
allowing integer rounding to absorb a regression.

- Raise the floor only when new durable behavior coverage keeps the observed
  total at least one point above the current floor across the CI matrix.
- Lowering the floor requires explicit owner review with the rationale recorded
  in the pull request that lowers it.
- Do not add tests whose only purpose is to move the number; coverage follows
  from the strict-TDD rule that every behavior change starts with a focused
  failing test.
- The floor is enforced by every `pytest --cov` run, which includes the CI
  quality matrix and the documented validation commands; the pre-push test
  hook deliberately runs without coverage for speed.
- `scripts/` is measured alongside the package (owner decision 2026-07-24,
  review Slice 8.3): the governance validators are load-bearing gates, so
  their coverage is ratcheted rather than invisible. Joining them re-based
  the floor once, to the integer floor of the newly observed total
  (93.55% on 2026-07-30 — the validators' CLI and error legs are less
  covered than the package; the package-only total was 95.3% at the
  re-baseline, so this is the honest number, not a package regression).
- Two reviewed coverage exclusions exist. The native ConPTY binding
  (`termverify._conpty`) executes only on Windows legs, so including it
  would make the cross-platform floor depend on the host OS. It is no
  longer the thin wrapper the exclusion once assumed (#197 roughly tripled
  it), so the Windows legs additionally measure it against the ConPTY
  suites with a supplemental, non-gating report (`conpty-coverage.toml`,
  #236) that keeps its gaps visible without making the floor OS-dependent;
  adapter logic above it is written against an injected binding and stays
  fully ratcheted. `scripts/check_installed_package.py` runs only as a CI
  subprocess against the built wheel and sdist, so no in-process test can
  execute it, and measuring it would only dilute the ratchet with
  permanently-missed statements. Adding any other exclusion requires the
  same owner review as lowering the floor.
- Platform-specific legs (today: `_jsonl_pipe.py`) carry per-OS markers —
  `# coverage: exclude-posix` / `# coverage: exclude-windows` — never a bare
  `# pragma: no cover`, which is a static source exclusion that would remove
  the leg on **every** platform (issue #230). `pyproject.toml` excludes both
  markers so local runs behave as before, and each CI quality leg sets
  `COVERAGE_RCFILE` to `coverage-windows.toml` or `coverage-posix.toml`,
  which repeats the gating settings but excludes only the legs that cannot
  run on that platform. Every leg is therefore ratcheted exactly where it
  runs. The overlays are self-contained (coverage reads one rcfile) and no
  pytest invocation ever compares them with `pyproject.toml`, so
  `scripts/validate_coverage_overlays.py` — a pre-commit hook — is the
  drift check for the repeated settings.

## Testing tiers

- **Unit:** pure normalization, comparison, protocol, and replay behavior.
- **Property:** Hypothesis strategies in this repository's own suite generate
  legal and illegal transcript and interaction sequences
  (e.g. `tests/test_transcript_lifecycle.py`). No state-machine or model-based
  runner exists; TermVerify-shipped property harnesses are `[planned]`.
- **Integration:** adapters running an application in process or subprocess mode.
- **PTY/end-to-end (Windows only today):** actual terminal input/output and
  normalized rendered-screen evidence through the ConPTY adapter; a POSIX PTY
  adapter is `[planned]`.

PTY tests must tolerate Windows and CI differences deliberately. A direct adapter remains the fast default; PTY support is required for production-fidelity scenarios, not for every unit test — and it exists only on Windows today.
