- **Generated documentation indexes (#322).**
  `scripts/build_doc_indexes.py` writes an `index.md` for
  `docs/agent/design/`, `reviews/`, `plans/`, `prompts/`, `handovers/`, and
  `docs/developer-guide/` from each page's frontmatter (status, date, and a
  one-line summary), with a "GENERATED — do not edit" header naming the
  command. `--check` runs in pre-commit and CI, so an index can no longer miss
  a page or disagree with one. The hand-maintained handover index and prompt
  list are replaced; developer-guide pages gained a `summary` field, and the
  developer-guide index is the section's landing page on termverify.dev.
