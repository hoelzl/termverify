- **Adjacent `terminal.output` chunks are coalesced at record time.** A native
  terminal read returns whatever the OS had buffered when it ran, so two
  identical runs can split the same bytes across different chunks — and the
  exact comparator, which has no normalizers by design, would call them
  divergent. Chunk boundaries were reaching the transcript as separate events,
  making replay equivalence depend on scheduling noise (adversarial review
  2026-07-24, finding **R6**; owner decision 2026-07-24: coalesce recorder-side
  rather than teach the comparator to normalize). The recorder now merges runs
  of adjacent `terminal.output` events into one, so only the byte stream is
  recorded.
  Merging is deliberately narrow: it never crosses an observation, because each
  is its own record and its own point in the lifecycle, and never crosses a
  structural event, because the order of output relative to a state change *is*
  evidence. An output event whose payload is not the expected single `chunk`
  string passes through untouched rather than being guessed at. No committed
  fixture carries `terminal.output` events, so none needed migration; live
  ConPTY runs are what change shape. (Resolves #195.)
