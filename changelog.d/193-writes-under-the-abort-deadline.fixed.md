- **Put JSONL wire writes under the abort deadline.** Every write — the
  `session.hello`, each epoch input, and `input.stop` — ran outside the
  watchdog, so a subject that stops reading its stdin blocked the write as soon
  as the pipe buffer filled and `dispatch()` never returned: no deadline, no
  structured failure, no evidence, against a transport whose stated promise is
  that the abort deadline always produces one (adversarial review 2026-07-24,
  finding **C2**, critical). Writes now arm the same watchdog reads do, through
  one shared `_arm_abort` helper so the two paths cannot drift, and a write
  failure that follows the watchdog firing is attributed to the deadline rather
  than to the peer — the same late-close classification the read path already
  applied, and the same-file minor the review attached to this fix.
- **Terminate before releasing the child's stdin writer.** The forced teardown
  released the buffered writer first, specifically so nothing would later be
  pushed at a child that is not draining — but `detach()` flushes (#217), so
  against exactly that subject the flush blocked and the forced close stalled
  *before* it could kill the tree, which would have left the new write deadline
  unable to fire. Killing first makes the flush fail fast against a dead reader.
  Measured on the regression test: the non-reading-subject case went from
  blocking until the subject exited on its own (601 s, its own sleep) to a
  structured `epoch-timeout` at the configured deadline — 5.0 s for the 5 s
  deadline the test uses.
- **Disclosed: ConPTY conin writes remain outside the abort deadline.** The
  mechanism above does not port to the ConPTY binding — `pty.write` hands the
  bytes to pywinpty, which owns the conin handle, so nothing can cancel it to
  interrupt a blocked write, and a write cannot move to another thread because
  a concurrent `pty.write` against a blocked `pty.read` wedges the native
  pseudoconsole. Reaching the handle requires TermVerify's own ConPTY binding,
  which is the raw-byte read path's conclusion too (finding R7).
  `src/termverify/_conpty.py` now states the theoretical bound: if a subject
  stops draining conin and the console input buffer fills, the write blocks
  and the deadline cannot end it. Not observed on the verified matrix; stated
  rather than measured. (Refs #193, #217.)
