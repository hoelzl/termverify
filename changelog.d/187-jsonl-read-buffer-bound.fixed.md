- **Bounded the JSONL read buffer at the protocol line ceiling.** A subject
  streaming newline-free bytes could grow the binding's read buffer without
  bound — the abort deadline bounds time, not memory (adversarial review
  2026-07-24, finding R1). `PipeJsonlChild.read_line` now stops
  accumulating once the buffered pseudo-line exceeds the
  `termverify.control/v1` framed-line ceiling without a buffered LF and
  returns the oversized buffer,
  which `parse_message` rejects by length — the flood fails through the
  existing `peer-malformed` path, OS-evidence-tested with a real flooding
  child. (Resolves #187.)
