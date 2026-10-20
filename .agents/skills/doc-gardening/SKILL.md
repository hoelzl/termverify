---
name: doc-gardening
description: Find and repair stale, duplicated, or unreachable TermVerify documentation. Use when a documentation gate fails, when a review_by date is near or past, after a rename or refactor, and as a periodic maintenance pass.
---

# Doc gardening

Placement rules, metadata schema, and the gate table:
[`docs/README.md`](../../../docs/README.md#keeping-documentation-current).

1. **Run the gates** and start from what they report:
   `uv --no-config run python scripts/check.py` (all documentation gates
   run as pre-commit hooks).
2. **Re-verify overdue pages.** For each page whose `review_by` is near or
   past, check every claim against the code, tests, and executable checks.
   Code and checks win: repair the prose in the same change; change code
   only through a test-first slice.
3. **Remove volatile state.** Knowledge pages and guides state contracts,
   not progress. Phase, slice, or "today" claims move to GitHub, a handover,
   or the README's capability section, and the page links there instead.
4. **Prune copies.** A fact stated in two places keeps its canonical home
   (see the placement table) and the other place links to it.
5. **Repair references** reported by `scripts/check_doc_references.py`.
   Decisions and archived handovers are corrected only to fix dead links or
   paths or to mark supersession; a review report changes only in its
   frontmatter, so a dead path in its body gets an `ALLOWED_MISSING` entry
   instead. Renamed names go into the historical-names table of
   `docs/knowledge/glossary.md`.
6. **Move `review_by` forward** on every page you re-verified, regenerate the
   indexes (`uv --no-config run python scripts/build_doc_indexes.py`), add a
   changelog fragment if contributors rely on the change, and open a PR.
