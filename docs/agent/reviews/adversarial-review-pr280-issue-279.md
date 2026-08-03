---
type: review
status: current
subject: PR #280 (issue #279) — the POSIX end-of-stream decoder flush
date: 2026-08-03
---

# Adversarial review record — PR #280 / issue #279

Three fresh-context adversarial rounds, five reviewers, every round REJECT.
One report per review pass, per `docs/agent/reviews/README.md`; this is the
pass record for the slice.

## What the slice was, and what the reviews changed about it

Issue #279 reported that `_posix_pty.py` discards whatever its incremental
UTF-8 decoder holds at end of stream, so a subject that stops part-way
through a multibyte character produces a transcript claiming it wrote only
the bytes before it. That half was true and is fixed.

The issue's other half — that the ConPTY binding already surfaces the
replacement, making the two bindings unequal — was **measured false before
any code was written**, and that measurement reshaped the slice: the two
bindings already agreed, losing the same bytes for different reasons, so
fixing the POSIX side *opens* a divergence rather than closing one. Five
reviewers reproduced that independently, one by instrumenting the binding's
decoder and capturing raw conout bytes.

## The one finding that mattered most

Round 2 measured that the flush changes **run outcomes**, not only output
text. `vt.py` is fail-closed, so a `U+FFFD` arriving while its parser is
mid-sequence is rejected, the epoch fails, and the run reports
`adapter-runtime-failed` with the child's observed exit record discarded.

The failure mode predates this PR — a `\xff` tail reaches it with no flush
involved, measured on `main` — but the flush widens the class of input that
gets there, and the PR had disclosed only "a trailing `U+FFFD`". Filed as
**#283**, pinned at the normalizer in `tests/test_vt.py`, and flagged in the
handover for Phase 3, which is the slice that will meet it with real
subjects.

## The pattern, and what finally addressed it

**Every round rejected on the same defect: a true-sounding sentence one notch
wider than its evidence, and each round's correction authored the next
round's.** Four rounds running:

1. The falsified attribution ("bytes the *child* left unfinished") corrected
   in one place and left standing in three others — including the changelog,
   the only artifact that reaches users.
2. A close test whose docstring named a mutation ("widen to its supertype")
   that is a behavioural no-op catching nothing — inside the very test
   written to stop claiming unguarded guarantees.
3. The divergence stated as "exactly the incomplete-but-valid prefix, and
   otherwise they agree". The first clause survived; the second was measured
   false by `\xc0` and `\xe0\x80`, where the console host waits *structurally*
   on sequences Python rejects on sight.
4. That correction landed in `_terminal_binding.py`, the changelog and both
   test files — and was left verbatim in the handover and the PR body.

Two structural changes came out of it, and they are the transferable part:

- **The measurement is executable data, not prose.**
  `tests/_end_of_stream_tails.py` holds twelve trailing byte sequences with
  both platforms' expected text; each binding's suite parametrizes over it.
  A table that is data cannot go stale against itself, and a row cannot be
  added without obliging both platforms. Round 2 found eight of the table's
  rows pinned by nothing while the commit that wrote them said "an unpinned
  stated fact is the shape this project keeps finding to be false."
- **State a rule once and point at it.** The paraphrases were what kept going
  stale, not the rule. `_terminal_binding.py` now carries the rule and names
  the tests; the handover and changelog point at it instead of restating it.

The method that actually caught defect 3 before a reviewer did is worth
keeping: **stress the boundary of your own claim, not the claim itself.**
Twelve tail shapes on two real hosts falsified a sentence that four readings
of the code would not have.

## Other findings fixed in the round they were raised

- **A docstring escape bug with no gate behind it.** `_terminal_binding.py`'s
  module docstring was not raw, so `\xe2\x82`, `\xc0` and `\x82` were
  interpreted: the row identifying the lone continuation byte rendered as an
  invisible C1 control character at runtime while reading correctly in the
  source. `ruff`, `ruff format` and `mypy` were all green with it in the tree,
  and `W605` cannot fire because those escapes are *valid*. Two reviewers read
  the file and saw correct source; the third read `__doc__`.
  `tests/test_docstring_escapes.py` now scans every rendered docstring in the
  package for characters no docstring writes on purpose — a check on the
  output, not on the spelling — and it immediately found a **pre-existing**
  instance of the same bug in `_posix_pty.py`, shipped since #267.
- **The one-call deferral could lose the end of stream.** A close landing
  between the read that returned the flushed text and the read that owes the
  raise answered `TerminalClosedError`, which the adapter classifies as a
  failure — so a run that had already ended, exit record captured, would be
  reported as a binding closed outside the abort deadline. The watchdog's
  expiry *is* such a close. Both bindings now latch end of stream; the ConPTY
  side is pinned over its fake session even though its flush is unreachable
  through a real host, because a port contract honoured by one of two
  implementations is this repository's recurring defect.
- **Two unpinned adjacent paths**, both measured surviving by reviewers: the
  flush hoisted above `read`'s closed-binding guard, and the flush placed
  inside it before the raise.
- Numerous prose corrections: whose truncation the held bytes represent, the
  `ECHO` caveat on "bytes the subject wrote" (#273), "reports every byte" vs
  the single `U+FFFD` that stands for N bytes, and stale pass counts quoted
  from a run that predated the last test.

## Residue filed

- **#281** — `_capture_exit_status_after_eos` is pinned by nothing (deleting
  the call leaves the suite green) and costs 30s of every Ubuntu leg.
  Pre-existing from #274.
- **#282** — the two bindings disagree about which *complete* byte sequences
  are invalid UTF-8, not only about unfinished ones. Pre-existing; measured
  while bounding this change's divergence.
- **#283** — a normalizer rejection at end of stream discards the child's
  exit record. Pre-existing; widened by this change.

## Deliberately not changed

`CHANGELOG.md`'s released 0.1.1 section says "A `U+FFFD` in ConPTY evidence
now means the child genuinely emitted invalid UTF-8" — the sentence this
slice corrected elsewhere. Released sections are point-in-time records of
what was believed at release, and rewriting them would make the changelog a
worse history rather than a better one. Recorded here so the inconsistency is
deliberate rather than missed.
