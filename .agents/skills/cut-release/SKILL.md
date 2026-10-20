---
name: cut-release
description: Prepare a TermVerify release branch and pull request, or bump main after a release. Use only when a release has been explicitly authorized by the maintainer; never to decide that one should happen.
---

# Cut a release

The checklist is [`docs/developer-guide/release.md`](../../../docs/developer-guide/release.md);
it is authoritative and this skill only orders the steps. Agents prepare the
release; a human reviews the release PR, and the `Release` workflow — never a
local build — tags and publishes.

1. Confirm authorization. Cutting the first supported external artifact
   additionally requires the owner-reviewed completion state recorded in the
   active handover. Then confirm the preconditions in the checklist:
   `uv --no-config run python scripts/check.py --full` is green, the
   `Security` workflow is green on the release commit, and documentation
   matches behavior.
2. On a release branch, fold the fragments:
   `uv --no-config run python scripts/collect_changelog.py A.B.C`
   (preview with `--dry-run`), then review the new section for migration
   notes and unreleased claims.
3. Strip the dev marker: `uv --no-config run bump-my-version bump pre`,
   which creates the `Bump version A.B.C.dev0 → A.B.C` commit.
4. Open the release PR for human review. Stop there.
5. After the workflow has published, follow "After publishing" in the
   checklist to bump `main` to the next planned `.dev0` version.
