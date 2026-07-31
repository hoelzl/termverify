- **A POSIX pseudoterminal binding** (issue #267, slice 1 of the vertical) —
  `termverify._posix_pty` gives a real pty the same child surface the ConPTY
  binding answers, so the adapter above the binding port needs no platform
  branch. It owns the pty pair, the child's session and controlling
  terminal, an explicitly configured line discipline, geometry through
  `TIOCSWINSZ`, one incremental UTF-8 decoder for the child's life,
  interruptible reads and writes over `poll` plus a self-pipe, and `killpg`
  teardown with the same disclosed `setsid()`-escape boundary the JSONL
  transport states. The support probe claims **Linux only**: a platform CI
  does not verify reports unsupported before any spawn rather than running
  unverified. Nothing public consumes it yet — the adapter generalization
  (#268) and its integration evidence (#269) are separate slices.
