- **Bounded the ConPTY epoch with per-epoch read and output budgets.** The
  abort deadline is re-armed per read, so a subject emitting one byte just
  under it and never emitting the readiness marker never exceeded any single
  read's deadline: the marker never arrived, `dispatch()` neither completed
  nor aborted, and the retained chunk list grew without bound (adversarial
  review 2026-07-24, finding **R2**). The epoch read loop now enforces two
  deterministic budgets — a read count, which bounds the epoch at
  budget × deadline rather than forever, and retained output bytes, which is
  single-sourced from `termverify.transcript/v1`'s per-record string ceiling
  because every chunk becomes a `terminal.output` event inside one
  observation record, so an epoch beyond it could never be recorded at all.
  Exhausting either is a structured failure disclosing which budget fired,
  never a claimed epoch. Deliberately *not* a second wall-clock input: the
  JSONL adapter's per-epoch diagnostic budget is the in-repo precedent, and
  wall-clock silence still decides nothing. (Resolves #194.)
