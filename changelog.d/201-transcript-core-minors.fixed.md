- **Transcript-core minors from the 2026-07-24 adversarial review are swept**
  (issue #201, Slice 8.2). The parse→serialize round-trip is closed at the
  budget margins: compat normalization (bare delivery → `spawn-env`)
  re-holds the normalized record to every per-record budget — value nodes,
  strings, and the canonical line-byte ceiling — and reports its added
  bytes so the whole-transcript ceiling is re-held too, so a legacy record
  whose canonical form exceeds any of them is rejected at parse instead of
  parsing and then failing to serialize. The duplicate-member error no
  longer echoes an attacker-controlled key unbounded — it quotes a
  bounded escaped excerpt, so a multi-megabyte key with embedded ANSI
  sequences cannot flood or inject into logs. Semantic rejections now name
  the failing record's `seq`, kind, and 1-based line
  (`record 9 (input.text, line 10): …`), making a rejection in a
  10,000-record transcript attributable in both coordinate systems; an
  *unknown* kind is attacker-chosen text and is deliberately not echoed —
  those rejections name the position only. The four causes that shared
  the identical "run.started terminal is invalid" message each state
  their own. The input-member closure that was enforced
  twice from the shared table (three times for `input.stop`) is enforced
  once — the restated checks were unreachable and uncovered — and the
  manual-clock chain rule both validation walks advance through now lives
  in one helper instead of two drifting copies. `_json_equivalent` carries
  the RFC 8785 integral-float caveat: `10.0` serializes to `10`, re-parses
  as `int`, and the type-strict comparison will not equate the two, so
  cross-source comparisons must not build on it unexamined. (The packaged
  JSON schema deliberately does not restate per-kind payload members, so
  after the dedup the member tables have a single executable source.)
