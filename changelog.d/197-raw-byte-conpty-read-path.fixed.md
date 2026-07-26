- **Read ConPTY output as raw bytes and decode it incrementally.** The binding
  took pre-decoded `str` from `pywinpty`, which decoded each native read in
  isolation: a read landing mid-codepoint turned the split character into
  `U+FFFD` and lost it outright, irreparably, in evidence (adversarial review
  2026-07-24, finding **R7**). Measured on this matrix, a 200,000-character
  burst of `U+65E5` produced 29 replacement characters across 21 reads and lost
  12 characters. `pywinpty` exposes no bytes-returning read and no way to reach
  the conout handle, and the damage cannot be repaired above it, so
  `termverify._conpty` now owns the pseudoconsole outright — `CreatePseudoConsole`,
  an `STARTUPINFOEX` spawn, and its own overlapped `ReadFile` loop on conout.
  `read()` still returns `str`, but one incremental UTF-8 decoder now spans a
  child's whole lifetime, so a split codepoint heals on the following read. A
  `U+FFFD` in ConPTY evidence now means the child genuinely emitted invalid
  UTF-8. Adversarial split-point tests cover every cut of two-, three-, and
  four-byte codepoints, a byte-at-a-time trickle, and a volume burst; they run
  on every platform against a fake native session. (Closes #197, refs #102.)
- **Dropped the `pywinpty` dependency.** Nothing imports it any more; the
  Windows dependency and its mypy override are gone from `pyproject.toml`, and
  the accepted terminal-adapter dependency decision is amended to record the
  replacement and the evidence for it.
- **Start programs whose path contains spaces.** The command line now quotes
  `argv[0]` like every other argument while the executable is named to the OS
  separately, so a spaced program path can no longer reach the child split
  across several arguments. (Refs the `_conpty.py` spawn minor in the same
  review.)
- **Write every byte handed to `write()`.** The previous binding issued one
  native call and accepted whatever it took; the loop now writes the whole
  payload. Conin sustains roughly 1 MiB/s — the console host turns every byte
  into input records — so a large payload holds the single-flight slot for
  proportionally longer than it used to.
