- **Bounded the ConPTY epoch in time.** The abort deadline is re-armed per
  read, so a subject emitting one byte just under it and never emitting the
  readiness marker never exceeded any single read's deadline: the marker never
  arrived, `dispatch()` neither completed nor aborted, and the retained chunk
  list grew without bound (adversarial review 2026-07-24, finding **R2**). The
  same configured deadline now also bounds the epoch as a whole, checked
  between reads, so the trickle aborts through the ordinary deadline path with
  the ordinary deadline evidence. Worst case is up to twice the deadline — the
  epoch's bound plus the read in flight when it passes. The details now name
  which bound fired (`read` for a stalled read, `epoch` for a subject that
  produces output but never reaches readiness), because the two look identical
  otherwise and need opposite remediations.
  **This can abort runs that previously passed:** an epoch that legitimately
  takes longer than the deadline while producing output now fails by policy,
  so hosts with long-running epochs must raise the deadline — at the cost of
  slower hang detection, since one value serves both bounds.
- **Bounded an epoch's retained evidence at what one record can carry.** An
  epoch's chunks reach the transcript as a *single* coalesced
  `terminal.output` string (#195), so the adapter bounds retained bytes
  against the tighter of the two ceilings that string meets: the per-string
  ceiling, which binds at ordinary geometry, and the per-record string sum
  less what the rest of the record costs, which binds above roughly 261,000
  cells. Deriving the budget from the per-record sum alone admitted epochs at
  1.98x the per-string ceiling on a plain 80x24 run, which the codec then
  rejected — losing the whole run's evidence at the end.
  The budget is **computed from the terminal geometry** rather than fixed,
  because the frame's lines are the record's other large strings: a flat
  reserve was measurably wrong in both directions — too small at 200x328 and
  above, where the adapter admitted epochs the codec then rejected for size,
  and too large at 80x24, where it aborted epochs that recorded fine. The
  frame reserve counts **UTF-8 bytes per cell, not cells**: the codec measures
  bytes, and a box-drawn or CJK screen costs three to four bytes per cell, so
  counting cells under-reserved by up to 3x and a box-drawn TUI at 100x30 was
  admitted and then rejected. A terminal at 523,264 cells or more cannot hold
  even its own frame in one record, and now fails on its first read with
  `budget: "geometry"` rather than as a phantom output flood.
  Disclosed limit: the codec still owns recordability and enforces ceilings no
  budget can model, notably a canonical-line limit ESC-dense output reaches far
  sooner.
- **Dropped the separate chunk-count budget**, which #195 made unreachable.
  While every chunk was its own event, a subject redrawing in place could
  exhaust the protocol's per-collection ceiling with under 100 KB of output in
  seconds, and the adapter had to abort it. Coalescing removes the axis: no
  number of native reads can reach that ceiling, so a spinner is now bounded
  by the bytes it writes and nothing else.
- **Rejected a read-count budget on measurement.** A count low enough to bound
  a trickle also aborts a cooperative subject: real ConPTY barely coalesces
  (635 reads for a 2,000-line scroll), so a 1024-read budget failed a plain
  few-thousand-line run in about three seconds while a 30 s deadline never
  fired. A regression test pins that a 4,000-chunk epoch inside the deadline
  still succeeds. (Resolves #194.)
