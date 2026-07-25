- **Made doc/code authority polarity consistent.** `AGENTS.md` treats
  executable checks as authoritative over prose, while the control-protocol
  specification claimed the opposite — "the codec is wrong and this document
  wins" — so the two normative documents gave opposite answers to the same
  question (adversarial review 2026-07-24, finding P9). Owner decision
  2026-07-24: code wins everywhere for the duration of the prototyping
  stage. `docs/knowledge/control-protocol.md` now says so, `AGENTS.md` gains
  a control-protocol row naming `src/termverify/control.py` as the authority
  for wire acceptance, and the prototyping-stage governance record states
  that the polarity is revisited at the re-freeze boundary — where
  doc-as-contract becomes defensible for a protocol third-party subjects
  implement. A doc/codec disagreement remains a defect either way: repaired
  doc-side by default, code-side through a test-first slice when the codec is
  the wrong one. (Resolves #191.)
