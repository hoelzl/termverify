- **The ConPTY readiness marker now actually bounds its epoch's output.** The
  marker was a private-use OSC sequence, chosen because a Windows-matrix test
  showed ConPTY relaying it verbatim. Relaying it verbatim was never
  sufficient: ConPTY renders text on one path and passes OSC through on
  another, and the OSC path is ahead. Measured — a subject's single atomic
  write of `TV_BEFORE` + marker + `TV_AFTER` arrives as the marker alone, then
  the text. The adapter therefore ended epochs on a marker whose output had
  not been delivered and reported frames missing it. The original evidence
  held only because the previous binding's reads were slow enough that the
  renderer had already flushed; the raw-byte read path (#197) made the gap
  observable and eight integration tests failed on it. (Closes #232.)
- **Breaking, prototyping-stage: markers are printable and carry a token.** A
  marker is now `READINESS_MARKER_PREFIX_DEFAULT` (configurable), a token the
  subject has not used before in the run, and `READINESS_MARKER_TERMINATOR` —
  `<<termverify.ready:7>>` and so on. Printable, so it travels the renderer's
  path and is ordered against the output it bounds. Tokenised, because
  rendered text is screen state and ConPTY re-emits screen state on every
  repaint: with a constant marker a resize's repaint completed an epoch whose
  input never sent one. The adapter honours each token once.
  `READINESS_MARKER_DEFAULT` is replaced by `READINESS_MARKER_PREFIX_DEFAULT`,
  and the `readiness_marker` constructor argument by
  `readiness_marker_prefix`.
- **Subjects must emit the marker on its own newline-terminated line.** It
  occupies screen cells now, so without the newline the next output continues
  on the same row; and a marker split across a line wrap has a malformed
  token, which is deliberately not honoured so the epoch fails closed on its
  deadline instead of completing wrongly. A token must match
  `[0-9A-Za-z._-]{1,64}`.
