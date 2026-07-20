- Documented the ESC-prefixed-sequence input-reader disclosure (issue #169):
  the ConPTY input pipe delivers ESC-prefixed bytes verbatim to the child's
  console input buffer (a bare ESC arrives as an Escape keypress), but the
  Microsoft C runtime's wide-character console reader (`msvcrt.getwch()`,
  and with it Python's `sys.stdin` text IO) parses ESC-prefixed sequences
  itself — `ESC x` surfaces as just `x` with the Alt modifier lost,
  `ESC [ A` surfaces as the translated virtual key, and a lone ESC blocks
  inside the runtime's sequence-assembly wait, turning a bare-`Escape`
  epoch into an abort-deadline expiry. Subjects binding ESC-prefixed
  (Emacs-style meta) chords must read console input byte-wise (`os.read` on
  the stdin file descriptor, or `ReadFile`/`ReadConsoleA` on the input
  handle), as the ConPTY integration fixture demonstrates. No adapter or
  protocol change: delivery, not interpretation, unchanged.
