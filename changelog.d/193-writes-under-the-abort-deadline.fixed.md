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
  blocking for 601 s — until the subject exited on its own — to a structured
  `epoch-timeout` in 14 s.
