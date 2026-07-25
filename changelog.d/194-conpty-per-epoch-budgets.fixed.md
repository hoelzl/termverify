- **Bounded the ConPTY epoch in time and in memory.** The abort deadline is
  re-armed per read, so a subject emitting one byte just under it and never
  emitting the readiness marker never exceeded any single read's deadline: the
  marker never arrived, `dispatch()` neither completed nor aborted, and the
  retained chunk list grew without bound (adversarial review 2026-07-24,
  finding **R2**). The same configured deadline now also bounds the epoch as a
  whole — which is what its name says — so the trickle aborts through the
  ordinary deadline path with the ordinary deadline evidence, and the worst
  case is the epoch deadline plus the read in flight when it passes. No second
  policy, no new evidence source, and the clock is injected so the bound is
  testable without sleeping.
- **Bounded an epoch's retained output at what one record can carry.** Every
  chunk becomes a `terminal.output` event inside a single observation record,
  whose aggregate string bytes `termverify.transcript/v1` caps; the budget is
  that ceiling less headroom for the record's other strings, and it counts the
  marker-bearing chunk too, so the marker cannot buy one extra unbounded read.
  This is a **memory** bound, disclosed as such: the codec owns recordability
  and enforces further ceilings — a per-string limit, and a canonical-line
  limit that ESC-dense output reaches far sooner because RFC 8785 escapes
  every control byte — which no static byte budget can model.
- **Rejected a read-count budget on measured evidence.** A count low enough to
  bound a trickle also aborts a cooperative subject: on the verified matrix
  real ConPTY hands back hundreds of small chunks for an ordinary scroll, so
  a 1024-read budget failed a plain few-thousand-line run — a false abort,
  worse than the starvation it would prevent. A regression test now pins that
  a 4000-chunk epoch inside the deadline still succeeds. (Resolves #194.)
