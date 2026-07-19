- **Changelog fragments.** Pending changelog entries are written as fragment
  files under `changelog.d/` (one per PR, `<pr-or-issue>-<slug>.<type>.md`)
  and folded into `CHANGELOG.md` at release time by
  `scripts/collect_changelog.py`, eliminating the `[Unreleased]` merge
  conflicts that dominated concurrent multi-agent work. Hand-written
  `[Unreleased]` entries are still folded in; malformed input aborts without
  modifying anything.
