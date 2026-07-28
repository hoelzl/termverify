- **The authoritative transcript codec and the closed key registries are now
  on the public `termverify` surface.** `parse_transcript`,
  `serialize_transcript`, and `TranscriptValidationError` join the
  non-authoritative schema aid that was already exported, so the validator
  that actually decides `termverify.transcript/v1` acceptance is no longer
  the harder import; they stay importable from `termverify.transcript` as
  identical objects. `KEY_NAMES`, `is_key_chord`, and `encode_key_chord` are
  promoted out of private modules, so adapter authors validating a semantic
  chord or driving a real terminal no longer need an underscore import — the
  names are public, their defining modules are not. Purely additive: no
  existing name moved or changed meaning.
