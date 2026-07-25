- **Bounded the ConPTY epoch on frame rows, not only on frame bytes.** The
  per-epoch geometry gate added in #194 reserved four bytes per cell and
  refused the epoch once nothing was left for output — a *cell* model, which
  cannot see the ceiling the codec charges per collection. A frame is recorded
  as one item per row, and `termverify.transcript/v1` caps a collection at
  16,384 items, so a terminal taller than 16,384 rows produces a record the
  codec rejects at any cell count: a 20,000x10 terminal is 200,000 cells, two
  and a half times below the 523,264-cell threshold, and every record it
  produced was rejected for collection size. The adapter now refuses it as it
  refuses the cell case, in the same `budget: "geometry"` failure class, with
  `terminal-rows` naming the axis that bound instead of `terminal-cells`.
  Reachable rather than theoretical: `TerminalConfiguration` requires only a
  positive int, and a 20,000-row pseudoconsole was created and spawned into on
  the Windows dev host. Columns get no matching check because the equivalent
  column limit — one frame line of 262,144 four-byte cells — is outside what
  the pseudoconsole's 16-bit dimensions can request, while 16,385 rows is not.
  (Resolves #226. Round-7 adversarial review of #194.)
- **Corrected three claims about the #194 budget that outlived their
  mechanism.** The developer guide said a 523,264-cell frame "still fits one
  record", which is false for a tall frame — 32,704x16 validates and its
  transpose does not; the guide's "worst case is twice the deadline" omitted
  the conin-write boundary disclosed in `_conpty.py`, which is the one part of
  `dispatch` the deadline does not cover; and the budget docstring and #194's
  changelog fragment cited a box-drawn 100x30 TUI as the witness for the
  four-byte-per-cell reserve, where the per-string ceiling binds and the frame
  reserve is entirely slack. The design document's classification table also
  gained the rows it was missing for both `budget` abort classes and for the
  deadline abort's `bound` detail.
