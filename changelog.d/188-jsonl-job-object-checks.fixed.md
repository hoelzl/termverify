- **Checked the pipe binding's Windows job-object results.** The JSONL pipe
  binding discarded `AssignProcessToJobObject`'s BOOL return, so containment
  could fail silently and `PipeJsonlChild.spawn` would hand out a session
  whose docstring promises a contained child — a later forced close would
  then terminate an empty job (adversarial review 2026-07-24, finding R3).
  Both containment calls now go through checked wrappers mirroring the
  ConPTY binding's: a failed assignment fails the spawn closed (the child is
  killed, the handles released, the failure raised) and a failed
  `TerminateJobObject` is raised instead of read as a success — previously it
  surfaced only as a 30-second wait misreported as "the child did not
  terminate on forced close". Kill-on-close still sweeps the tree when the
  job handle is released, so neither path leaks a process.
  (Resolves #188.)
