- **Platform legs are ratcheted where they run, not nowhere.** The
  `# pragma: no cover` markers on `_jsonl_pipe.py`'s platform legs were
  static source exclusions: a pragma on a `def` removed the whole body from
  measurement on **every** platform, so the POSIX I/O implementation was
  unratcheted even on Linux (and the Windows containment legs on Windows).
  The legs now carry per-OS markers (`# coverage: exclude-posix` /
  `# coverage: exclude-windows`), `pyproject.toml` excludes both for local
  runs, and each CI quality leg selects `coverage-windows.toml` or
  `coverage-posix.toml` via `COVERAGE_RCFILE` — an overlay that repeats the
  gating settings but excludes only the legs that cannot run there. Windows
  legs measured on Windows: module 75.59%, total 94.66% against the 94
  floor; the Ubuntu number is CI-validated on the PR. Overlay drift
  (repeated gating settings no pytest invocation compares) is checked
  mechanically by the new `scripts/validate_coverage_overlays.py`
  pre-commit hook. (Closes #230.)
