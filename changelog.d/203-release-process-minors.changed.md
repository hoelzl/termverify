- **Release/process minors from the 2026-07-24 adversarial review are swept**
  (issue #203, Slice 8.4, with the recorded owner decisions). `main` now
  carries the manual `.dev0` marker scheme: the in-tree version is
  `0.2.0.dev0`, the release commit is `bump-my-version bump pre` — a real
  `X.Y.Z.dev0 → X.Y.Z` strip, never a degenerate same-version bump — and
  the post-release step chooses the next planned version and restores the
  marker. The `Release` workflow refuses to release any dev-marked version
  on both the branch and the fallback tag path, so the post-release bump
  commit is inert, and the release checklist is exercisable as written
  (fragments are collected before the marker is stripped). The new
  `scripts/validate_prose_status.py` pre-commit validator holds three
  drift-prone claims to the code: version discipline (`[project]` and
  bumpversion versions agree; a marker-less tree must carry its release
  section in `CHANGELOG.md`), the closed ADR status vocabulary under
  `docs/agent/design/`, and registry counts stated in prose against the
  shipped `termverify.key/v1` registries — with removed claim sites
  failing loudly rather than passing silently. `release.md` now states
  that the automated release gate waits on the `CI` workflow only (the
  `Security` workflow's green state is the human-checked precondition),
  and the schema-distribution ADR records the `termverify.dev`
  hijack-surface risk and the accepted identifier-first mitigation
  posture, with the monitoring decision deferred to the first supported
  external artifact.
