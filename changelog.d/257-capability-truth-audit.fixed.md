- **Published prose no longer claims machinery that `src/` does not ship**
  (issue #257, the repo-wide follow-up to README finding P5). A four-way
  audit of `docs/knowledge/`, `docs/developer-guide/`, `CHANGELOG.md`, and
  `SECURITY.md` against `src/` and the test suite repaired every unbacked
  present-tense capability claim doc-side: the architecture boundary no
  longer offers adapter-level state save/restore; the verification model
  marks the persistence oracle `[planned]`, scopes baseline governance to
  the validator that actually runs, and describes replay as reproducing the
  recorded (not "approved") outcome; the evidence-governance policy states
  that the baseline root is absent and baselines are disabled pending their
  enablement boundary rather than "governed" today; the control-protocol
  specification now matches the codec and adapter on exited-process
  observations (rejected from the child in every position, synthesized by
  the adapter from the OS boundary), on deadline aborts (no exit record is
  disclosed), on which resource ceilings the codec itself enforces, and on
  `at_ms`/chord validity being producer obligations; the transcript
  protocol page describes the shipped comparator's exact whole-payload
  equality instead of a layered domain-before-rendering evaluation;
  adapter-author docs say `ConstraintPorts` *applies* (not enforces)
  constraints, `encode_key_chord` returns a `str`, receipts carry no `x-`
  extension member, and `persist_transcript_evidence` is safe-evidence
  persistence rather than schema access; the developer guides label the
  property tier as this repository's own Hypothesis suite (no state-machine
  runner) and the PTY tier as Windows-only ConPTY; the release checklist
  attributes zizmor/OSV-Scanner to the CI-only Security workflow; and an
  unresolved merge-conflict marker inside the released 0.1.1 changelog
  section was removed.
