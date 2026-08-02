---
type: review
scope: PR #276 (issue #274, POSIX pty binding residue)
rounds: 3
verdicts: REJECT, REJECT, REJECT
recorded: 2026-08-02
---

# Adversarial review — PR #276, POSIX binding residue (#274)

Three rounds, two independent fresh-context reviewers each: one attacking code
and test strength, one attacking whether every sentence is true. Every round
returned REJECT, which is the loop's stop condition, and every finding was
fixed before the next round ran.

Recorded here because `AGENTS.md` places review reports under
`docs/agent/reviews/`, and because the *pattern* across the rounds is more
useful than any single finding.

## What the rounds found

| Round | Code | Prose |
| --- | --- | --- |
| 1 | 2 Major, 3 Minor | 3 Major, 6 Minor |
| 2 | 2 Major, 4 Minor | **1 Critical**, 2 Major, 5 Minor |
| 3 | see below | **1 Critical**, 3 Major, 5 Minor |

### Real defects in shipped code

1. **A `KeyboardInterrupt` inside `_adopt_wake_pipe` leaked the pty master and
   orphaned a live session-leader child.** The callee had been widened to
   `BaseException` while its caller — the half owning the master and the child
   — still caught `OSError`.
2. **`_release_descriptors` was unpinned on the success path.** Deleting the
   master's close, or the wake pipe's loop, left the entire suite green. The
   leak would have been total rather than rare.
3. **The handler the new exec-status bound feeds into had never executed**, and
   released the master outside a `finally`.
4. **All three spawn-failure paths signalled the pid, not the session**, so
   "no child outlives a failed spawn" was an overclaim invisible to tests
   whose subjects never fork.

### The recurring shape, and it is not the code

Across all three rounds the implementation held up under mutation; what failed
was **the evidence offered for it**.

- A bound pinned by a test that **hung** instead of failing, in a slice whose
  subject is that hangs are the bad failure mode.
- A 60-second budget that became 60 **milliseconds** with the suite green,
  because nothing asserted elapsed time.
- A containment test asserting "nothing else derives from this type" — trivially
  true for a leaf class, so the wrong base class passed 179 tests.
- Two spawn-failure tests that passed with the kill deleted, because releasing
  the master hangs up the terminal and the child dies of `SIGHUP` anyway.
- A mutation case that went stale and was **silently skipped** while the
  harness summary still read "as expected".

### The prose failure, three rounds running

Round 1 found eight false sentences. Round 2 found that three of them had been
repaired in the source and **left standing in the PR body**, under a commit
message claiming they were "corrected everywhere". Round 3 found a **fourth**
still live in the same document, under a fresh claim that every one had now
been checked against the tree.

The mechanism was the same each time: the source was corrected and the source
was re-read, while a second document restating the same claims was not. "I
fixed that" is not a check. What finally worked was mechanical — grep every
document for each corrected claim by keyword, and re-verify each hit against
the tree.

Round 3 also **measured a justification false**: a comment claimed CPython
checks for signals between adjacent `STORE_ATTR`s, so an interrupt could leave
a descriptor half-published. It cannot — the eval breaker runs at `RESUME` and
backward jumps, and ~20,000 interrupts delivered into exactly that store pair
produced zero half-assigned observations on 3.12 and 3.13.

## Reusable lessons

- **A test that hangs is a worse pin than a test that fails**, and this repo
  configures no per-test timeout. Run the call on a worker and assert on an
  event with a deadline.
- **Assert the units, not just the outcome.** A bound with no elapsed-time
  assertion cannot tell 60 s from 60 ms.
- **A containment assertion over siblings says nothing about ancestors.** Pin
  both directions explicitly.
- **A cleanup test must assert *which* signal ended the child.** On a pty, the
  hangup from releasing the master kills a session leader by itself, so "it is
  gone" proves nothing about the teardown.
- **A stale mutation anchor must fail, not skip**, and the summary must print
  its denominator — otherwise a case that stops being exercised reads as
  success.
- **The shared venv installs the project editable**, so its `.pth` names one
  worktree. A reviewer in another worktree tests someone else's source and sees
  green whatever they break. Always `PYTHONPATH=$PWD/src`, and verify
  `termverify.__file__` once.
- **One local venv is one interpreter; the matrix is three.** A 3.13-only loop
  let a `termios.IUTF8` failure reach CI, because that constant does not exist
  before 3.13.
- **A commit body cannot be edited by a later commit**, and GitHub's default
  squash message concatenates them. A branch that corrected its own false
  sentences must still be squashed with an explicit message, or the originals
  land on `main`.
