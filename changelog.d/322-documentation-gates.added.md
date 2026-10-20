- **Mechanical documentation gates (#322).** `scripts/check_doc_references.py`
  fails on broken relative links, missing heading anchors, and backticked
  repository paths that no longer exist, across all living Markdown (with a
  per-path, reasoned allowance for records that must cite removed paths).
  `scripts/check_doc_freshness.py` requires a `review_by` date on every
  knowledge page and unfinished handover and caps working handovers at
  64 KiB; passed dates only warn in the commit and PR gates and fail in the
  new weekly `Documentation freshness` workflow, so no commit starts failing
  because the calendar moved. Both checks run in pre-commit and CI;
  `docs/README.md` lists every documentation gate and the doc-gardening
  procedure.
