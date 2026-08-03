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
   otherwise they agree". Both clauses fell in the end: the second to `\xc0`
   and `\xe0\x80`, where the console host waits *structurally* on sequences
   Python rejects on sight; then the first to `\xed\xa0`, a surrogate lead
   CPython holds and flushes as *two* replacements — in the set the flush
   reports, while being a prefix of nothing valid.
4. That correction landed in `_terminal_binding.py`, the changelog and both
   test files — and was left verbatim in the handover and the PR body.

Two structural changes came out of it, and they are the transferable part:

- **The measurement is executable data, not prose.**
  `tests/_end_of_stream_tails.py` holds eighteen trailing byte sequences with
  both platforms' expected text; each binding's suite parametrizes over it.
  The column saying which rows this change opened is defined *operationally* —
  where the decoder still holds bytes — after four attempts to characterise it
  by a rule were each measured false. Some facts are only available as
  measurements, and writing them up as rules is how they go wrong.
  A table that is data cannot go stale against itself, and a row cannot be
  added without obliging both platforms. Round 2 found eight of the table's
  rows pinned by nothing while the commit that wrote them said "an unpinned
  stated fact is the shape this project keeps finding to be false."
- **State a rule once and point at it.** The paraphrases were what kept going
  stale, not the rule. `_terminal_binding.py` now carries the rule and names
  the tests; the handover and changelog point at it instead of restating it.

The method that caught half of defect 3 before a reviewer did is worth
keeping: **stress the boundary of your own claim, not the claim itself.** A
dozen tail shapes run against two real hosts falsified a sentence that four
readings of the code would not have. It is also worth noting what that method
did *not* catch — the replacement clause it produced was falsified in turn, by
a reviewer, which is why the column is now operational rather than described.

## Other findings fixed in the round they were raised

- **A docstring escape bug with no gate behind it.** `_terminal_binding.py`'s
  module docstring was not raw, so `\xe2\x82`, `\xc0` and `\x82` were
  interpreted: the row identifying the lone continuation byte rendered as an
  invisible C1 control character at runtime while reading correctly in the
  source. `ruff`, `ruff format` and `mypy` were all green with it in the tree,
  and `W605` cannot fire because those escapes are *valid*. Two reviewers read
  the file and saw correct source; the third read `__doc__`.
  `tests/test_docstring_escapes.py` guards it, and its own first version is a
  fresh instance of the #199 lesson that **a ratchet's parser is itself an
  attack surface**. That version scanned `src/` only and looked for control
  characters in the *rendered* text, so round 3 walked a cooked `\xff` past it
  in a `tests/` docstring — `\xff` renders as an ordinary lowercase letter,
  and the original defect was caught only because `\x82` happens to land in
  the C1 range. It now reads the source literal as well, across both trees.
  Between them the two nets found a **pre-existing** instance in
  `_posix_pty.py` shipped since #267, and one introduced minutes earlier in
  this slice, in the docstring that warns about the defect.
- **The one-call deferral can lose the end of stream**, and the attempt to fix
  it inside this slice is the clearest lesson of the whole pass. A close
  landing between the read that returned the flushed text and the read that
  owes the raise answers `TerminalClosedError`, so a run that had already
  ended, exit record captured, is reported as a failure. A latch was
  prototyped on both bindings and pinned on both.

  Round 3 then measured three things about it: the *mechanism* the PR gave was
  wrong (a watchdog close produces a deadline abort, not the failure named);
  the latch silently changed **abort attribution**, letting a run whose
  deadline expired be reported `RunFinished`, against a policy `terminal.py`
  states inline; and it bypassed the single-flight guard, so a widened race
  delivered the flushed tail to the wrong caller.

  **Reverted by owner decision.** The hazard is real, but latching it is a
  decision about the abort contract rather than about decoding, and it does
  not belong in a slice that fixes a decoder. `TerminalEndOfStreamError` now
  states the limitation instead of promising "never dropped", and **#284**
  carries the hazard with all of the measurements. The general shape is worth
  keeping: *a fix that answers a review finding but reaches into a contract
  the slice does not own is a new slice, not a smaller one.*
- **Two unpinned adjacent paths**, both measured surviving by reviewers: the
  flush hoisted above `read`'s closed-binding guard, and the flush placed
  inside it before the raise.
- Numerous prose corrections: whose truncation the held bytes represent, the
  `ECHO` caveat on "bytes the subject wrote" (#273), "reports every byte" when
  a flush emits replacements rather than bytes — and then "one `U+FFFD`
  however many bytes were held", which round 3 falsified with `\xed\xa0`
  flushing as two — and stale pass counts quoted from a run that predated the
  last test.

## Residue filed

- **#281** — `_capture_exit_status_after_eos` is pinned by nothing (deleting
  the call leaves the suite green) and costs 30s of every Ubuntu leg.
  Pre-existing from #274.
- **#282** — the two bindings disagree about which *complete* byte sequences
  are invalid UTF-8, not only about unfinished ones. Pre-existing; measured
  while bounding this change's divergence.
- **#283** — a normalizer rejection at end of stream discards the child's
  exit record. Pre-existing; widened by this change.
- **#284** — a close in the flush's one-call deferral gap drops the
  end-of-stream. Introduced by this change's own contract; the latch that
  would close it was prototyped here and reverted, with every measurement
  carried over.

## Deliberately not changed

`CHANGELOG.md`'s released 0.1.1 section says "A `U+FFFD` in ConPTY evidence
now means the child genuinely emitted invalid UTF-8" — the sentence this
slice corrected elsewhere. Released sections are point-in-time records of
what was believed at release, and rewriting them would make the changelog a
worse history rather than a better one. Recorded here so the inconsistency is
deliberate rather than missed.
