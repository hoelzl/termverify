- **Bounded the ConPTY epoch on frame rows and frame width, not only on
  frame bytes.** The per-epoch geometry gate added in #194 reserved four
  bytes per cell and refused the epoch once nothing was left for output — a
  *cell* model, and the frame meets three `termverify.transcript/v1` ceilings
  in three different units. The other two are unreachable from the cell
  product:
  - A frame is one collection item per line, and a collection holds 16,384
    items, so a terminal of 10 columns and 20,000 rows — 200,000 cells, two
    and a half times below the 523,264-cell threshold — produced observation
    records the codec rejected for collection size.
  - One frame line is one string of `columns` code points, so a terminal of
    262,145 columns and 1 row — 262,145 cells — produced observation records
    the codec rejected for string size. Only a single-row terminal can reach
    this: at two rows, any width past 262,144 is already past the cell
    threshold.

  Both are now refused as the cell case is, in the same `budget: "geometry"`
  failure class, with `terminal-rows` or `terminal-columns` naming the axis
  that bound. Both were reachable: `TerminalConfiguration` requires only a
  positive int, and 262,145x1, 1,048,577x1 and 10x100,000 pseudoconsoles were
  each created and spawned into on the Windows dev host. (Resolves #226.
  Rounds 7 and 8 of the adversarial review of #194.)
- **Corrected several claims about the #194 budget that outlived their
  mechanism.** The developer guide said a 523,264-cell frame "still fits one
  record", which is false for a tall frame — 32,704x16 validates and its
  transpose does not. Its "worst case is twice the deadline" omitted the
  conin write, which `_conpty.py` discloses as running outside the deadline
  entirely; the write is not the only uncovered part of `dispatch`, so the
  guide now bounds the claim to the read phase rather than trading one
  over-claim for another. The budget docstring and #194's changelog fragment
  cited a box-drawn 100x30 TUI as the witness for the four-byte-per-cell
  reserve, where the per-string ceiling binds and the reserve is entirely
  slack. The guide's list of ceilings no epoch bound can model gained the
  32 MiB per-transcript ceiling, which accumulates across epochs and which
  no per-epoch check can see. The design document's classification table
  gained the rows it was missing for both `budget` abort classes and for the
  deadline abort's `bound` detail.
