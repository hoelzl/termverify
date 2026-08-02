- **POSIX pty binding residue** (issue #274, deferred from #267) — the
  issue's three findings against `termverify._posix_pty`, plus what
  reviewing them turned up in the same code. A release-only close of a live child raised a bare
  `RuntimeError`, the supertype of three of the module's four error types,
  so a handler written for that refusal silently swallowed a closed
  binding, a single-flight violation and an unsupported host;
  `PosixPtyLiveChildError` carries it now. `os.set_blocking` failing during
  adoption stranded both wake descriptors, because the only handler for it
  released the master alone. The spawn's wait for the trampoline's exec
  status had no bound at all — a child that stalled before its `execv` hung
  the spawn with no diagnostic — and is now capped. The line discipline
  also stops deviating from the conventional terminal in two flags it never
  named: `ECHOK` and `ECHOKE` are on again, so the `^U` this binding
  installs as `cc[VKILL]` echoes its erasure the way the erase character
  already did. And `IUTF8` is now set on **every** supported interpreter:
  `termios.IUTF8` arrives only in Python 3.13, so reading it defensively
  left the flag off on 3.12 — the same subject on the same kernel erasing a
  multibyte character one way under 3.12 and another under 3.13.
