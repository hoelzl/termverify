- **Adjacent `terminal.output` chunks are coalesced at record time.** A native
  terminal read returns whatever the OS had buffered when it ran, so two
  identical runs can split the same bytes across different chunks — and the
  exact comparator, which has no normalizers by design, would call them
  divergent. Chunk boundaries were reaching the transcript as separate events,
  making replay equivalence depend on scheduling noise (adversarial review
  2026-07-24, finding **R6**; owner decision 2026-07-24: coalesce recorder-side
  rather than teach the comparator to normalize). The recorder now merges each
  maximal run of adjacent `terminal.output` events into one, so read
  boundaries inside an observation no longer reach the transcript. Verified as
  the acceptance evidence the slice asks for: two identical runs of a real
  ConPTY subject now reach an equivalent verdict, and compared *divergent*
  before the change.
  Merging is deliberately narrow: it never crosses an observation, because each
  is its own record and its own point in the lifecycle, and never crosses a
  structural event, because the order of output relative to a state change *is*
  evidence. An output event whose payload is not the expected single `chunk`
  string passes through untouched rather than being guessed at. No committed
  fixture carries `terminal.output` events, so none needed migration; live
  runs are what change shape.
  Three disclosed consequences: which *observation* a read lands in is still
  read-boundary dependent for a subject that emits without waiting for input;
  the per-string codec ceiling now binds where the per-record aggregate used
  to, so an epoch emitting more than a mebibyte of output is refused by the
  codec until the adapter-side bound of #194 turns that into a structured
  epoch failure; and a transcript recorded before this change, or by a
  third-party emitter that chose its own boundaries, can no longer replay
  equivalent against a freshly recorded run. (Resolves #195.)
