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
- **Bounded an epoch's retained evidence at what one record can carry.** Every
  chunk becomes a `terminal.output` event in a single observation record, so
  the adapter now bounds both retained bytes — counting each chunk's per-event
  overhead, which scales with chunk count — and retained chunk count, against
  `termverify.transcript/v1`'s per-record string and collection ceilings.
  Without the overhead accounting an ordinary 41,000-line scroll stayed inside
  the byte budget and still produced a transcript the codec rejected at the end
  of the run; without a chunk bound a spinner reached the collection ceiling
  with ~50 KB of payload. Disclosed limit: the codec still owns recordability
  and enforces ceilings no static budget can model, notably a canonical-line
  limit that ESC-dense output reaches far sooner.
- **Rejected a read-count budget on measurement.** A count low enough to bound
  a trickle also aborts a cooperative subject: real ConPTY barely coalesces
  (635 reads for a 2,000-line scroll), so a 1024-read budget failed a plain
  few-thousand-line run in about three seconds while a 30 s deadline never
  fired. A regression test pins that a 4,000-chunk epoch inside the deadline
  still succeeds. (Resolves #194.)
