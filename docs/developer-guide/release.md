# Release Process

This checklist defines how a termverify release is produced when one is
authorized. The checklist itself authorizes nothing: the project is pre-alpha,
and cutting the first supported external artifact additionally requires the
owner-reviewed completion state recorded in the active handover under
`docs/agent/handovers/`.

## Preconditions

1. `main` is green: the full validation gate in `AGENTS.md` passes (including
   the coverage ratchet), and the CI-only `Security` workflow checks —
   workflow security (zizmor) and dependency vulnerabilities (OSV-Scanner) —
   are green on the release commit.
2. `CHANGELOG.md` has an accurate section for the new version: every breaking
   change carries a migration note, and no unreleased behavior is described as
   released.
3. Documentation matches behavior; executable checks win over prose, and any
   stale page found during review is fixed before the bump.
4. A human has reviewed the release pull request; agents must not approve or
   publish a release on their own authority.

## Version scheme

`main` always carries the *next planned* version with a `.dev0` marker
(owner decision 2026-07-24, review Slice 8.4): between releases the in-tree
version reads `A.B.C.dev0`, the release commit strips the marker to `A.B.C`
— a real commit, never a degenerate same-version bump — and the post-release
step chooses the next planned version and restores the marker. The `Release`
workflow refuses to release any version carrying the marker, so the
post-release `Bump version A.B.C → X.Y.Z.dev0` commit is inert, and
`scripts/validate_prose_status.py` (pre-commit) rejects a marker-less tree
whose `CHANGELOG.md` lacks the matching release section.

## Cutting the release

1. On a release branch, fold the pending changelog fragments into a dated
   release section for the planned version: `uv --no-config run python
   scripts/collect_changelog.py A.B.C` (preview with `--dry-run`). This
   deletes the collected `changelog.d/` fragments; day-to-day PRs never
   touch `CHANGELOG.md`'s `[Unreleased]` section — they add fragments
   (`changelog.d/README.md`). The fragments are collected before the marker
   is stripped so every commit on the branch keeps the prose-status
   validator green.
2. In the same branch, strip the dev marker: `uv --no-config run
   bump-my-version bump pre`. bump-my-version turns `A.B.C.dev0` into
   `A.B.C` in the single version source of truth in `pyproject.toml` plus
   the project's own `[[package]]` entry in `uv.lock`, and creates the
   `Bump version A.B.C.dev0 → A.B.C` commit the workflow keys on
   (`[tool.bumpversion]` in `pyproject.toml`; `tag = false` — no local tag
   is ever created). Open the release PR for human review.
3. Merge the reviewed release pull request into `main`. The `Release`
   workflow detects the `Bump version` commit in the push and runs the gated
   pipeline: it waits for the `CI` workflow to be green on that commit,
   creates the annotated `vA.B.C` tag *after* the gate (a red commit is never
   tagged), builds the wheel and sdist with uv, runs the isolated
   installed-package contract checks against both artifacts, generates
   build-provenance attestations, publishes to PyPI via OIDC trusted
   publishing (no stored credentials; the `pypi` GitHub environment), and
   creates the GitHub release with the extracted changelog section and the
   attested artifacts attached. The automated gate waits on the `CI`
   workflow only — the `Security` workflow's green state on the release
   commit is precondition 1, checked by the human, not an automated gate.
4. As a fallback (for example to re-drive a failed publish after fixing
   credentials), push the `vA.B.C` tag manually at the release commit; the
   workflow verifies the tag matches the version in `pyproject.toml`,
   refuses a dev-marked version, and runs the same pipeline. Every step is
   idempotent: an existing tag, PyPI version, or GitHub release is left
   as-is.

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
2. After the `Release` workflow completes, bump `main` to the next planned
   development version: `uv --no-config run bump-my-version bump <part>`
   (`minor` for `A.B.C → A.(B+1).0.dev0`, and `patch` or `major`
   accordingly). This is where the next version is chosen; the release
   itself only ever strips the marker. The resulting `Bump version` commit
   is ignored by the `Release` workflow because the new version carries
   the marker — and waiting for the workflow first keeps the strip commit
   and the re-bump out of one push, where the workflow would read the
   re-bumped dev version and skip the release (recoverable via the
   fallback tag, but avoidable).
3. Record follow-up work as issues rather than editing the published notes.
