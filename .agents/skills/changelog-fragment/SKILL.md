---
name: changelog-fragment
description: Add the changelog entry for a TermVerify change. Use whenever a pull request changes behavior, the public API, a protocol, tooling, or documentation that users or contributors rely on — before opening the PR.
---

# Changelog fragment

Conventions: [`changelog.d/README.md`](../../../changelog.d/README.md).

1. Never edit `CHANGELOG.md` — not even its `[Unreleased]` section.
2. Create `changelog.d/<pr-or-issue>-<short-slug>.<type>.md`, where `<type>`
   is one of `added`, `changed`, `deprecated`, `removed`, `fixed`, `security`.
   Use the issue number when the PR number is not known yet.
3. Write the finished entry exactly as it should appear in the changelog:
   usually one `- **Bold summary (#N).** …` bullet in the style of the
   released sections. A breaking protocol or API change carries its migration
   note inside the fragment, under `changed` or `removed`.
4. Several fragments per PR are fine when the PR does several user-visible
   things; they are folded in filename order at release time by
   `scripts/collect_changelog.py`.
