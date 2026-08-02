- **A truncated multibyte tail no longer vanishes from POSIX evidence**
  (issue #279). `termverify._posix_pty` ran one incremental UTF-8 decoder for
  the child's lifetime but never flushed it, so whatever the decoder was
  holding when the pseudoterminal reached end-of-stream was discarded: a
  subject that exited part-way through a multibyte character produced a
  transcript asserting it wrote only the bytes before it. Measured: `b'START'`
  followed by two of the three bytes of `U+20AC` yielded `'START'`, with no
  marker of any kind. Those bytes are now flushed as replacement text on the
  read that meets end-of-stream, with the end-of-stream raised by the read
  after it, matching the ConPTY binding and the contract now stated on
  `TerminalEndOfStreamError`. A read interrupted by a *close* still does not
  flush, because a close may have abandoned output the child had already
  written.

  **This changes what reaches a transcript**, and in one direction: a POSIX
  run whose subject stopped mid-character gains a trailing `U+FFFD` it did not
  carry before. Runs whose output ends on a complete character are unaffected.
  The replacement goes into the ordinary output channel, so it is not
  distinguishable from a `U+FFFD` the subject itself emitted — the same trade
  the ConPTY binding has made since #197, recorded here rather than implied.

  The only way to reach the held bytes is for the subject not to have written
  the rest of them — being killed inside a `write`, or writing an incomplete
  sequence deliberately. Issue #279 also named a pty splitting the subject's
  final character across reads; that cause is **wrong**, because the master
  reports end-of-stream only once its buffer is drained and the last slave is
  gone, so every byte the subject did write arrives first and the incremental
  decoder heals the split.

  The issue's remaining claim — that the ConPTY binding already surfaced this
  replacement, making the two bindings unequal — was **measured false** on
  real console hosts and is recorded rather than quietly dropped. The console
  host is itself a UTF-8 decoder: it holds a subject's incomplete trailing
  sequence and discards it, so those bytes never reach the ConPTY binding and
  no flush of its decoder can recover them. Before this change both bindings
  lost the same two bytes for different reasons; closing the POSIX side's loss
  is what *creates* the divergence, deliberately, and it is recorded in
  `_terminal_binding.py` beside the two already there.

  The divergence this opens is narrower than it first reads, and the boundary
  is measured: it is exactly an incomplete but *valid* multibyte prefix. A
  trailing byte that can neither begin nor continue a sequence — `\xff`, or a
  lone continuation byte — is resolved on arrival by the console host and by
  the pty binding's decoder alike, so both record a replacement and the two
  agree. Each case is pinned by a real-subject test on its own platform, so a
  console host that changes its mind fails a test rather than silently
  re-converging the two.

  Bounding it also turned up divergences that are **not** this change's and
  are recorded rather than fixed: the console host resolves a byte only when
  it cannot structurally continue what the lead announced, so it waits on
  `\xc0` and on the overlong `\xe0\x80` where Python's decoder rejects both on
  sight, and it renders a surrogate with a different number of replacement
  characters. Those differences predate this release and are unchanged by it.

  Filed as a fix rather than a change: the Python API and the transcript
  protocol are both untouched, and a run that previously under-reported its
  subject's output now reports it. The transcript-content consequence is
  disclosed above rather than left to the type of this fragment.
