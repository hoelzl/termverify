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
   stale page found during review is fixed before tagging.
4. The version in `pyproject.toml` is bumped in a reviewed pull request that
   also moves the `Unreleased` changelog entries under the new version heading.
5. A human has reviewed the release pull request; agents must not approve or
   tag a release on their own authority.

## Cutting the release

1. Merge the reviewed release pull request into `main`.
2. Tag the merge commit `vX.Y.Z` (matching `pyproject.toml` exactly) and push
   the tag.
3. The `Release` workflow builds the wheel and sdist with uv, runs the
   isolated installed-package contract checks against both artifacts,
   generates GitHub build-provenance attestations for them, and attaches them
   to a **draft** GitHub release.
4. Verify the draft: artifact names and sizes, attestation subjects
   (`gh attestation verify <artifact> --repo hoelzl/termverify`), and release
   notes copied from the changelog.
5. Publishing the draft release is a manual, human decision. There is no
   package-index (PyPI) publishing pipeline; adding one is a separate reviewed
   change with its own credentials and provenance decisions.

## Provenance

- Build provenance comes from the tag-triggered GitHub Actions workflow with
  `actions/attest-build-provenance`; local builds are never released.
- All workflow actions are pinned to commit SHAs; the workflow-security scan
  covers the release workflow like any other.
- The draft release's artifacts must be byte-identical to the attested
  subjects; re-uploading modified artifacts invalidates the release.

## After publishing

1. Confirm the changelog heading and tag agree, and start a fresh
   `Unreleased` section.
2. Record follow-up work as issues rather than editing the published notes.
