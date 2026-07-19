# Release Process

This checklist defines how a termverify release is produced when one is
authorized. The checklist itself authorizes nothing: the project is pre-alpha,
and cutting the first supported external artifact additionally requires the
owner-reviewed completion state recorded in the active handover under
`docs/agent/handovers/`.

## Preconditions

1. `main` is green: the full validation gate in `AGENTS.md` passes, including
   the coverage ratchet, workflow-security, and dependency-vulnerability
   checks.
2. `CHANGELOG.md` has an accurate section for the new version: every breaking
   change carries a migration note, and no unreleased behavior is described as
   released.
3. Documentation matches behavior; executable checks win over prose, and any
   stale page found during review is fixed before the bump.
4. A human has reviewed the release pull request; agents must not approve or
   publish a release on their own authority.

## Cutting the release

1. On a release branch, run `uv --no-config run bump-my-version bump <part>`
   (for example `patch` or `minor`). bump-my-version updates the single
   version source of truth in `pyproject.toml` plus the project's own
   `[[package]]` entry in `uv.lock`, and creates a `Bump version X.Y.Z →
   A.B.C` commit (`[tool.bumpversion]` in `pyproject.toml`; `tag = false` —
   no local tag is ever created).
2. In the same branch, fold the pending changelog fragments into a dated
   release section: `uv --no-config run python scripts/collect_changelog.py
   A.B.C` (preview with `--dry-run`). This deletes the collected
   `changelog.d/` fragments; day-to-day PRs never touch `CHANGELOG.md`'s
   `[Unreleased]` section — they add fragments (`changelog.d/README.md`).
   Open the release PR for human review.
3. Merge the reviewed release pull request into `main`. The `Release`
   workflow detects the `Bump version` commit in the push and runs the gated
   pipeline: it waits for the `CI` workflow to be green on that commit,
   creates the annotated `vA.B.C` tag *after* the gate (a red commit is never
   tagged), builds the wheel and sdist with uv, runs the isolated
   installed-package contract checks against both artifacts, generates
   build-provenance attestations, publishes to PyPI via OIDC trusted
   publishing (no stored credentials; the `pypi` GitHub environment), and
   creates the GitHub release with the extracted changelog section and the
   attested artifacts attached.
4. As a fallback (for example to re-drive a failed publish after fixing
   credentials), push the `vA.B.C` tag manually at the release commit; the
   workflow verifies the tag matches the version in `pyproject.toml` and runs
   the same pipeline. Every step is idempotent: an existing tag, PyPI
   version, or GitHub release is left as-is.

## Provenance

- Build provenance comes from the tag-gated GitHub Actions workflow with
  `actions/attest-build-provenance`; local builds are never released. Verify
  with `gh attestation verify <artifact> --repo hoelzl/termverify`.
- PyPI publishing uses OIDC trusted publishing (`uv publish
  --trusted-publishing always`) scoped to the `pypi` environment of this
  repository; there are no long-lived PyPI tokens anywhere.
- All workflow actions are pinned to commit SHAs; the workflow-security scan
  (zizmor) covers the release workflow like any other.
- The GitHub release's artifacts are exactly the attested subjects; the
  pipeline never re-uploads modified artifacts.

## After publishing

1. Confirm the changelog heading, tag, and PyPI version agree. The collector
   already left a fresh `Unreleased` section in place for the next cycle.
2. Record follow-up work as issues rather than editing the published notes.
