- Replay-subject validation errors now name the offending selector and the
  specific defect: a missing or unknown top-level member, and per-selector
  missing/unknown members or a value that fails the identifier grammar.
  Previously every selector defect raised the uniform
  `"run.started subject <name> is invalid"`. This improves adapter-author
  diagnostics without changing acceptance — the same payloads are accepted
  and rejected as before, and error text is not part of the wire contract.
