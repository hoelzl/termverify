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
  kill-on-close never fired, the contained tree leaked and `close` never
  returned. The teardown now releases containment before it touches the
  pipes, so the sweep ends every remaining job member, the sweep unblocks the
  read, and the caller still learns the termination failed.
- **Made the pipe binding's containment prose match what it can deliver.**
  A second review round refuted the claims attached to those fixes: a job
  whose member was never assigned stays permanently empty, so it sweeps
  nothing, and a forced close of such a binding cannot terminate a
  descendant the exited child left behind. `spawn` and `close` now disclose
  that boundary — it is the same escape as the already-disclosed assignment
  window, since failing the spawn would not contain the descendant either —
  and describe the sweep as covering every remaining job *member* rather
  than "the tree". Pipe descriptors are also now released deterministically:
  the teardown closes the raw stream `detach` hands back instead of leaving
  it to a finalizer, the spawn's fail-closed path releases both pipes and
  both kernel handles even if the child cannot be reaped, and a failed
  teardown reaps the child with a non-blocking poll rather than not at all.
  (Refs #188, #213, #217.)
