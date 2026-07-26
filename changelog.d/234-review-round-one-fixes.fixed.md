- **A stray marker prefix in subject output no longer swallows the next real
  readiness marker.** `_scan_for_marker` searched for the terminator from the
  first prefix it found, so a subject that printed the prefix by accident
  consumed the *next* genuine marker's `>>` into one oversized token and
  skipped past the real marker — the epoch then ran to its deadline and the
  run reported a deadline abort against a correct subject. Rejected candidates
  now resume the search one character past where they *began*, not past where
  they ended. An unterminated candidate is also dropped once it outruns the
  longest legal token, which it could not previously do: one stray prefix
  retained every later byte of the run in the scan buffer and rescanned them
  on every read. (Adversarial review of #234, critical.)
- **A cancelled or failed wait no longer abandons a pending overlapped read.**
  Two exits from `_await_read` raised while the `ReadFile` was still
  outstanding, leaving the kernel owning an `OVERLAPPED` that is a frame local
  of `read_bytes` and a buffer a later read would reuse. Every non-success
  exit now cancels and waits the read out first.
- **End-of-stream is decided by the native signal, not inferred from a dead
  child.** `ConptyEndOfStreamError` carries the guarantee that every byte the
  pseudoconsole emitted has already been returned; the classifier re-derived
  it from liveness, so any read failure arriving after the child exited
  claimed that guarantee. It now dispatches on the native failure itself.
- **`ResizePseudoConsole` runs under the lock that protects the handle.** The
  handle was read under the lock and used outside it, so the end-of-stream
  path could hand it to the closing thread in between and the resize would run
  on a freed handle.
- **A pseudoconsole that never finishes closing is reported.** `close()`
  joined the closing thread with a timeout and returned normally when it
  expired, silently leaking the handle and the thread while claiming a
  release it had not made.
- **`is_supported()` answers the question it documents.** It returned
  `os.name == "nt"`, but pseudoconsoles arrived in Windows 10 1809 and the
  spawn fails closed without them, so negotiation could report supported on a
  host where every start would fail.
- **Empty decodes are no longer recorded as evidence.** A native read landing
  inside a multi-byte codepoint decodes to nothing until the rest arrives;
  those were retained as `terminal.output` events asserting the child emitted
  nothing, and they never advanced the epoch's byte counter.
- Test fixes from the same review: the no-native-pin assertion was pinned to
  pywinpty's `PTY` class name and had become unfalsifiable; the burst
  accounting inferred one repeat per reposition from a total instead of
  asserting the pairing; the split-marker test built its halves from three
  different markers and only ever cut inside the prefix; and the in-flight
  write test could not tell an overlapping close from a write that had already
  finished. Cross-platform tests now cover both behaviours #232 is about — a
  repainted marker being ignored and a malformed token being skipped — which
  had evidence only in the Windows-only integration module.
