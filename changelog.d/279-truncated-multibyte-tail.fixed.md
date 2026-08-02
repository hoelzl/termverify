- **A truncated multibyte tail no longer vanishes from POSIX evidence**
  (issue #279). `termverify._posix_pty` ran one incremental UTF-8 decoder for
  the child's lifetime but never flushed it, so whatever the decoder was
  holding when the pseudoterminal reached end-of-stream was discarded: a
  subject that exited mid-codepoint — killed inside a `write`, or splitting
  its final character across the last read — produced a transcript asserting
  it wrote only the bytes before it. Measured: `b'START'` followed by two of
  the three bytes of `U+20AC` yielded `'START'`, with no marker of any kind.
  Those bytes are now flushed as replacement text on the read that meets
  end-of-stream, with the end-of-stream raised by the read after it, matching
  the ConPTY binding and the contract now stated on
  `TerminalEndOfStreamError`. A read interrupted by a *close* still does not
  flush, because a close may have abandoned output the child had already
  written.

  **This changes what reaches a transcript**, and in one direction: a POSIX
  run whose subject ended mid-codepoint gains a trailing `U+FFFD` it did not
  carry before. Runs whose output ends on a complete character are
  unaffected.

  The issue's other claim — that the ConPTY binding already surfaced this
  replacement, making the two bindings unequal — was **measured false** on a
  real console host and is recorded rather than quietly dropped. The console
  host is itself a UTF-8 decoder: it holds a subject's incomplete trailing
  sequence and discards it, so those bytes never reach the ConPTY binding and
  no flush of its decoder can recover them. Before this change both bindings
  lost the same two bytes for different reasons; closing the POSIX side's
  loss is what *creates* the divergence, deliberately, and it is recorded in
  `_terminal_binding.py` beside the two already there. Both behaviors are now
  pinned by real-subject tests on their own platform, so a console host that
  changes its mind fails a test rather than silently re-converging the two.
