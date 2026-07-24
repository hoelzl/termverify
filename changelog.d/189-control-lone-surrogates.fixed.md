- **The control codec rejects unpaired surrogates.** `parse_message`
  accepted lone surrogates (arriving as valid UTF-8 line bytes via JSON
  escapes) that RFC 8785 canonical serialization rejects, so hostile input
  could crash the recording pipeline with an uncaught
  `TranscriptValidationError` instead of failing `peer-malformed`
  (adversarial review 2026-07-24, finding R5). `_validate_json_value` now
  encodes strings and object keys strictly, restoring parse/serialize
  symmetry in both codec directions; valid surrogate pairs (astral
  characters) still round-trip. (Resolves #189.)
