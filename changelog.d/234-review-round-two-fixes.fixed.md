- **A maximum-length marker token is no longer lost when its terminator
  straddles two reads.** The rule that drops a candidate too long to still be
  a marker counted the token but not the terminator, so a 64-character token
  followed by a split `>>` was discarded one character short of viability —
  the marker vanished and a cooperating subject was reported as a deadline
  abort. A hex digest is 64 characters, which is an obvious choice for "a
  token I have not used before". The terminator search is bounded to the same
  span, which also stops one stray prefix from making the scan quadratic in
  the size of a read. (Round-two adversarial review of #234, critical.)
- **A resize can no longer block teardown.** Holding the session lock across
  `ResizePseudoConsole` fixed a use-after-free race but let a resize block the
  reader — and the reader is what stops draining conout, which the console
  host may be waiting on to finish that very resize. `close()` became
  blockable without bound, on the operation that backs the adapter's abort
  deadline. The handle is now pinned by a dedicated lock that only the closing
  path takes, so the reader never waits on a resize.
- **A stalled pseudoconsole close no longer masks the failure that caused the
  teardown.** It was raised from a `finally`, so it displaced errors that
  matter more — a child that would not die — and skipped the remaining
  teardown on the graceful path. It is recorded and reported only once the
  close has otherwise succeeded.
- **A host-configured marker prefix made only of token characters is
  rejected.** Such a prefix can be absorbed into a neighbouring candidate's
  token, so the genuine token is never recorded and the console's next repaint
  of that marker completes another epoch — the double-honour #232 exists to
  prevent. The default prefix was never affected.
- `is_supported()` gained the regression test its fix lacked, and the existing
  probe test no longer asserts the contract that fix repudiated — it would
  have failed on exactly the pre-1809 Windows the fix targets. The empty-decode
  skip, `_read_epoch_chunks`' one uncovered branch, gained a test too.
- Narrowed two destructor hazards the previous round's fixes opened: a
  part-built session no longer releases handles its caller still owns, and the
  read-cancellation helper no longer touches handles a concurrent close has
  already released.
