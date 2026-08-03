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
  One `U+FFFD` stands for the whole held sequence, so a one-byte and a
  three-byte truncation look the same in the transcript.

  **For one class of subject it changes the run's outcome, not just its
  output.** `vt.py` is fail-closed, so a replacement character arriving while
  its parser is mid-sequence is rejected and the run reports
  `adapter-runtime-failed` with no exit record — a subject that truncates
  mid-character *while also* mid-escape-sequence now takes that path where it
  previously finished. The failure mode is not new: a trailing byte that can
  never be valid, such as `\xff`, is resolved by the decoder on arrival and
  reached the same rejection before this change. What is new is the class of
  input that reaches it. Whether a normalizer rejection should surrender the
  child's observed exit record is issue #283; the interaction itself is pinned
  in `tests/test_vt.py`.

  Reaching the held bytes requires the subject not to have written the rest of
  them — by being killed inside a `write`, or by writing an incomplete
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
  is measured: it is exactly an incomplete but *valid* multibyte prefix — the
  case where **both** decoders are still waiting for a byte that never comes.

  Bounding it turned up divergences that are **not** this change's and are
  recorded rather than fixed. The console host decodes structurally: it
  resolves a byte only when that byte cannot continue what the lead announced,
  so it goes on waiting through `\xc0` and the overlong `\xe0\x80`, both of
  which Python's decoder rejects on sight — and it renders a surrogate with a
  different number of replacement characters. Those differences predate this
  release and are unchanged by it; they are tracked as a separate issue.

  Every row of the measurement — twelve trailing byte sequences, both columns
  — is executable data parametrized by each binding's own test suite, so it is
  checked on both platforms on every run rather than restated in prose.

  Filed as a fix rather than a change: the Python API and the transcript
  protocol are both untouched, and a run that previously under-reported its
  subject's output now reports it. The transcript-content consequence is
  disclosed above rather than left to the type of this fragment.
