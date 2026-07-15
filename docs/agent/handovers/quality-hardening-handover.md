# Quality Hardening Handover

## Handover metadata

- **Status:** active
- **Owner:** unassigned
- **Created:** 2026-07-14
- **Review required:** yes — independent human-readable review is required for
  protocol, artifact-security, baseline-governance, and CI-policy decisions.
- **Scope:** address the delivery, security, documentation, architecture, and
  workflow gaps identified by the July 2026 adversarial review before freezing
  Phase 1 public contracts.
- **Completion:** all workstreams below meet their acceptance criteria; every
  unresolved decision has an explicit, reviewed disposition; the full quality
  gate passes on the resulting repository state.

## Purpose and boundaries

TermVerify's Phase 0 foundation is intentionally small: its package exports a
version and its only test checks that export. The documented architecture and
workflow are the primary Phase 0 deliverables. This handover hardens the
foundation and specifies prerequisites for Phase 1; it does **not** implement
the `RunConfig`, event, observation, adapter, replay, or PTY runtime.

Do not use this document as an issue tracker. Create or reference one focused
issue and pull request per coherent change; record only material transitions,
decisions, and verified evidence here.

## Verified starting state

- The local gate passed on 2026-07-14: `uv sync --all-groups`, `uv run pytest`,
  `uv run ruff check .`, `uv run ruff format --check .`,
  `uv run mypy src tests`, and `uv run pre-commit run --all-files`.
- CI validates tests, Ruff lint/format, mypy, and OKF frontmatter on Ubuntu and
  Windows for Python 3.12 and 3.13.
- The repository has no protocol runner, adapter, fixture, snapshot, transcript,
  or artifact capture implementation yet.
- Package build/install verification was not performed in the review because
  the local execution-consent layer blocked the attempted build command.

## Resolved decisions

The following decisions were confirmed on 2026-07-14:

1. **Supply-chain controls:** use Dependabot for dependency and GitHub Action
   updates; add `zizmor` for workflow-policy checks, an OSV-based dependency
   audit, and repository-native secret scanning where available.
2. **Local and remote gates:** keep pre-commit fast (Ruff plus documentation
   validation) and add a pre-push gate for tests, mypy, package build, and
   security checks. CI remains the authoritative non-bypassable full gate.
3. **Python support:** Python 3.12 is the minimum version. Python 3.12, 3.13,
   and 3.14 are supported and must be continuously tested. The minimum-version
   declaration does not promise support for future Python releases until they
   are added to the tested support set.
4. **Coverage:** publish branch-coverage results in CI without an initial hard
   percentage threshold. Establish a reviewed no-regression/ratchet policy once
   Phase 1 has enough meaningful behavior to make the baseline useful.

## Implementation transition: 2026-07-15

The following delivery controls have been implemented locally and require a
reviewed commit and pull-request run before they are considered CI-verified:

- CI now requires the committed lockfile, uses immutable action SHAs, tests
  Python 3.12–3.14 on Ubuntu and Windows, runs coverage reporting without a
  threshold, and validates both wheel and sdist installation in an isolated
  environment.
- The OKF validator is a tested reusable script and runs in both CI and the
  fast pre-commit hook. Pre-push runs tests, strict mypy, and distribution
  builds; Ruff no longer mutates files through `--fix` during commits. The
  development-only `types-PyYAML` dependency supplies strict type information
  for the existing PyYAML-based documentation contract.
- Dependabot configuration, a pinned `zizmor` workflow, and a pinned
  OSV-Scanner workflow have been added. The local `zizmor` audit reported no
  findings; OSV-Scanner awaits its first CI run.
- GitHub configuration is verified: SHA pinning is required; Dependabot
  security updates, secret scanning, and secret-scanning push protection are
  enabled; `main` requires up-to-date checks, a pull request with zero required
  approvals for the single-maintainer workflow, stale-review dismissal,
  conversation resolution, and applies those rules to administrators. GitHub
  retained non-provider secret patterns as disabled.

Remote verification passed on 2026-07-15: the CI matrix, package-distribution,
and documentation-contract jobs passed in
`https://github.com/hoelzl/termverify/actions/runs/29373481944`; the `zizmor`
and OSV-Scanner jobs passed in
`https://github.com/hoelzl/termverify/actions/runs/29373481942`; and Dependabot
validated its configuration. The branch-protection policy retains required,
up-to-date checks and resolved conversations while requiring zero approvals for
the single-maintainer workflow.

Local verification passed on 2026-07-15: the full pytest suite with branch
coverage, Ruff check and format verification, strict mypy over `src`, `tests`,
and `scripts`, both pre-commit stages, OKF validation, wheel/sdist isolated
installation smoke tests, `zizmor`, Markdown-link validation, and
`git diff --check`.

## Workstream 3 design transition: 2026-07-15

Issue [#3](https://github.com/hoelzl/termverify/issues/3) tracks the focused
protocol and deterministic-boundary work. The accepted v1 JSONL design defines
canonical serialization, lifecycle and ordering, stable IDs, required
configuration, enforced-or-unsupported constraint reporting, and compatibility
rules. A Windows 11 / CPython 3.12 feasibility spike found the ConPTY kernel
APIs available but no usable stdlib PTY operations; it also confirmed the need
for separately drained streams, explicit initial sizing and resize, and
drain-aware teardown. Browser bridging is deferred unambiguously in the product
and architecture documents.

Independent human-readable review accepted this material protocol/architecture
decision on 2026-07-15. Workstream 3 remains active: no committed schemas,
fixtures, serialization/compatibility tests, or adapter constraint-propagation
tests exist yet. Those executable contracts are required before accepting Phase
1 adapter code.

## Workstream 1: deterministic and supply-chain-safe delivery

### Objective

Make CI test the committed environment and reduce workflow supply-chain risk.

### Actions

1. Change CI synchronization to `uv --no-config sync --all-groups --locked` in
   every job so developer-global uv settings cannot invalidate the committed
   lockfile.
2. Pin every third-party GitHub Action to a full commit SHA, with the release
   tag retained in a comment for maintainability.
3. Add an action-update mechanism and document the review policy for SHA
   updates.
4. Add a dependency vulnerability audit and secret/workflow-policy checks
   proportionate to the repository's maturity.
5. Configure repository branch protection outside this repository so required
   CI checks, a pull request, and resolved conversations are required for
   `main`. Require zero approvals while the repository is single-maintainer;
   revisit independent approval when a second maintainer joins. Record the
   configuration and verification evidence in the associated issue or pull
   request.

### Implementation policy

Use the selected Dependabot, `zizmor`, OSV-audit, and repository-native secret
scanning controls. Document each check's owner, false-positive handling, and
remediation path before making it required.

### Acceptance criteria

- CI fails when `uv.lock` is stale or absent.
- Every action reference is immutable.
- Dependency, secret, and workflow-policy checks have documented ownership and
  run on pull requests.
- Required checks and review requirements are verified in GitHub settings.

## Workstream 2: complete and aligned quality gates

### Objective

Ensure local hooks, CI, metadata, and published artifacts express the same
support and quality contract.

### Actions

1. Implement the accepted fast pre-commit gate (Ruff plus documentation
   validation) and the broader pre-push gate. Document that CI is the
   authoritative, non-bypassable full gate.
2. Make CI run `pre-commit run --all-files` or otherwise prove that every hook
   is represented by an equivalent CI check.
3. Decide whether Ruff's commit-time `--fix` behavior is retained; if so,
   document the required review/restage step.
4. Add a package job that builds wheel and sdist, installs each in a clean
   environment, and smoke-tests the installed package.
5. Run branch coverage in CI without an initial hard threshold, then document
   the reviewed no-regression/ratchet policy that will begin once Phase 1
   produces a meaningful baseline.
6. Add Python 3.14 to the CI matrix and document that Python 3.12 is the
   minimum version while only continuously tested releases are supported.
7. Add the concise pre-commit installation pointer to the README and correct
   agent guidance so it does not imply committed schema files exist before
   Phase 1.

### Acceptance criteria

- A contributor can identify one authoritative full gate and run it locally.
- CI exercises every enforced quality rule, artifact build, and declared Python
  version.
- Wheel and sdist installation tests pass without importing from the checkout.
- CI publishes branch coverage without a hard threshold, and the future
  no-regression/ratchet activation condition is documented.

## Workstream 3: protocol and deterministic-boundary prerequisites

### Objective

Prevent incompatible Phase 1 implementations and make determinism a testable
adapter responsibility rather than descriptive metadata.

### Actions

1. Publish a minimal versioned protocol design before implementation: JSONL
   envelope, canonical serialization, required/optional fields, stable IDs,
   ordering rules, error/lifecycle representation, and additive/incompatible
   change rules.
2. Add valid and invalid protocol fixtures plus serialization and compatibility
   tests before adapter code is accepted.
3. Specify the adapter-facing injection/enforcement contract for manual clock,
   seed, locale, timezone, terminal capabilities, filesystem sandbox, and
   network policy. Define what an adapter must report when it cannot enforce a
   requested constraint.
4. Run a narrow Windows/ConPTY feasibility spike before the Phase 1 adapter
   interface is frozen. Record the assumptions, command evidence, and resulting
   interface constraints in an architecture decision document.
5. Explicitly defer browser bridging until the terminal vertical slice proves
   the shared abstraction is necessary.

### Acceptance criteria

- A new implementation can produce interoperable v1 transcripts from fixtures
  without guessing field or ordering semantics.
- Tests demonstrate deterministic-constraint propagation or an explicit,
  structured unsupported result.
- The Phase 1 adapter interface accounts for verified Windows PTY constraints.
- Product and architecture documents state the browser deferral unambiguously.

## Workstream 4: evidence and baseline safety governance

### Policy transition: 2026-07-15

Issue [#5](https://github.com/hoelzl/termverify/issues/5) tracked this work and
closed with [PR #6](https://github.com/hoelzl/termverify/pull/6). The
independently human-reviewed policy defines transcript/clipboard/frame/
diagnostic/path/artifact classification, safe and non-persistent defaults,
bounded sensitive-mode retention, deterministic redaction, and baseline approval
records bound to canonical baseline and readable-diff digests. PR #6 added the
redactor, governance validator, nested-path redaction/approval tests, and the
fast local/CI hook; all required remote checks passed. Workstream 4 is complete.
CI artifact publication remains disabled until a separately reviewed policy
change enables it.

### Objective

Prevent sensitive terminal evidence from leaking and turn baseline-review policy
into enforceable controls before snapshots or artifacts are introduced.

### Actions

1. Define a data classification and redaction policy for transcripts, clipboard
   events, rendered frames, process errors, filesystem paths, and CI artifacts.
2. Define secure defaults: opt-in sensitive capture, redaction markers,
   retention guidance, access boundaries, and a non-persistent mode.
3. Design baseline/snapshot approval metadata, readable-diff requirements,
   ownership/review rules, and CI validation. Do not add baseline files until
   this design is reviewed.
4. Add tests that prove redaction and baseline-governance validation cannot be
   bypassed by normal fixture or artifact paths.

### Acceptance criteria

- Every future evidence type has documented handling and a tested redaction
  path.
- A proposed baseline change cannot pass CI without its required rationale and
  approval metadata.
- CI artifact publication is disabled until the policy and tests are in place.

## Recommended sequencing

1. Complete Workstream 1 steps 1–2 and Workstream 2 steps 4 and 6 first: these
   produce immediate confidence in every subsequent change.
2. Resolve the tool-selection and coverage decision gates, then finish the
   remaining delivery controls.
3. Complete Workstream 3 before accepting Phase 1 protocol implementation.
4. Complete Workstream 4 before adding transcripts, snapshots, or CI artifact
   upload.

## Risks and non-negotiables

- Do not add a dependency, public protocol, generated baseline, or copied code
  without rationale and a verification plan, as required by `AGENTS.md`.
- Do not automate approval of behavioral baselines.
- Keep the deterministic core independent from ambient terminal, time,
  randomness, filesystem, and network state.
- Keep security tooling proportionate: every new check must have an owner,
  remediation path, and tolerable signal quality.
- Do not treat an unverified CI/build claim as evidence; capture command output
  in the corresponding pull request or handover transition.

## Handover transition rules

Update this document when a workstream is completed, blocked on a decision, or
materially re-scoped. On completion, mark this document **complete**, add final
validation evidence and the Phase 1 successor (if any), then move it to
`docs/agent/handovers/archive/` and update the handover index.