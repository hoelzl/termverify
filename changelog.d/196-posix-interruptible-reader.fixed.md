- **A blocked POSIX read or write can no longer be wedged by a process the
  containment cannot reach.** The reader was a blocking `read1` on the child's
  buffered stdout, and nothing could interrupt it. A descendant that starts its
  own session (`setsid`) escapes the process-group kill, and while it holds the
  child's stdout write end no end-of-stream ever arrives — so the reader thread
  stayed blocked for the life of the verifier, the abort deadline produced no
  structured failure, and the teardown could strand itself behind the reader's
  own buffered lock inside a `finally`. Measured on the Ubuntu legs before the
  fix: the read was never woken.

  The POSIX binding now owns both pipes as raw descriptors and waits on
  `select` over the descriptor **and a self-pipe**; every close signals that
  pipe before terminating anything and before touching any descriptor. The
  interruption is the binding's own rather than one borrowed from containment,
  so it does not depend on reaching whoever holds the other end. Writes are
  covered the same way, so a child that stops draining its stdin cannot stall a
  write either. (Resolves #196, review finding **R4**.)
- **The stdin release on POSIX no longer flushes, because there is nothing left
  to flush.** Two comments claimed `detach()` released the buffered writer
  without flushing; it flushes, so the teardown stall they existed to prevent
  was not prevented — bounded only by the tree already being dead. Detaching
  now happens once at construction, where both buffers are provably empty, and
  teardown closes raw descriptors. (Resolves #217.)
- **The teardown deadlock behind a descendant-held pipe is closed on POSIX.**
  Same shape as the above and the general form of the ordering invariant the
  Windows handle release already followed: release every mechanism that can
  unblock an operation before performing an operation that can block on it.
  (Resolves #213 on POSIX; the Windows leg remains a disclosed boundary, since
  `select` does not work on anonymous pipe handles.)
- **Reworded the platform-parity claim, which overstated on both halves.**
  `JsonlBinding` promised "identical observable outcomes on every platform
  (real exit record, forced-termination record, **no survivors**)". Survivors
  are possible on both platforms — a `setsid()` descendant on POSIX, a process
  started inside the disclosed assignment window on Windows — and reaping them
  portably is out of scope by recorded decision. What is identical is the
  *failure classification*; what is now true everywhere is that a survivor
  cannot stall a teardown on POSIX or make a run report anything it did not
  observe. Recorded in `docs/knowledge/architecture.md`.
