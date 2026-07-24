- **Documentation corrections from the 2026-07-24 adversarial review
  (finding P1 and doc minors).** The spawn-env compatibility sentence in
  `protocol.md`, `channel-tagged-delivery-records.md`, and the
  `transcript.py` docstring no longer declares the canonical
  `{"channel": "spawn-env", "env": ...}` form invalid (only `env` with a
  *different* channel rejects). The JSONL control-transport ADR status is
  corrected to accepted (slices merged as PRs #175/#177). The stale
  934-chord count in the pre-release handover now records the amended
  1,382-chord enumeration and current digest. The JSONL adapter guide warns
  subjects to write protocol lines through a binary stream (text-mode
  `print` emits `\r\n` on Windows and every message rejects as
  `peer-malformed`). `control-protocol.md` gains full OKF frontmatter and
  its freeze sentence now defers to prototyping-stage governance.
  `development.md` no longer lists the nonexistent `skills/` directory.
  (Resolves #186.)
