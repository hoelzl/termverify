- **Fixed two defects in the pipe binding's new job-object checks.** The
  adversarial review of PR #211 (finding R3's remediation) found that (1) a
  child exiting inside the disclosed assignment window now failed the whole
  spawn: Windows refuses `AssignProcessToJobObject` on an exited process, so
  a legitimate fast subject was non-deterministically reported as a
  containment failure. That case is now read as "nothing left to contain" and
  the binding reports the child's real exit record. (2) A failed
  `TerminateJobObject` could strand the teardown: with a read still blocked
  on the child's pipe — the adapter's own watchdog shape, where the deadline
  timer closes while the main thread is in `read_line` — the pipe detach
  waited on the blocked reader's lock, the job handle was never released,
  kill-on-close never fired, the tree leaked and `close` never returned. The
  teardown now releases containment before it touches the pipes, so the
  sweep ends the tree, the sweep unblocks the read, and the caller still
  learns the termination failed. The spawn's fail-closed path also releases
  the child's pipes instead of leaving them to the garbage collector, and the
  docstrings no longer claim more than the code delivers. (Refs #188.)
