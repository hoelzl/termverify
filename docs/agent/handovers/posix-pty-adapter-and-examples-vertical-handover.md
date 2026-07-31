# POSIX PTY Adapter and Examples Vertical Handover

## Handover metadata

- **Status:** active — the working handover for the initiative tracked by
  [issue #204](https://github.com/hoelzl/termverify/issues/204). The
  [vertical boundary design](../design/posix-pty-adapter-and-examples-vertical-boundary.md)
  was accepted 2026-07-31 with all five decisions taken, which authorizes the
  slices below in order.
- **Owner:** project maintainer
- **Created:** 2026-07-31
- **Updated:** 2026-07-31 (boundary accepted; decisions recorded; Phase 0
  closed except issue filing)
- **Review required:** yes. Every slice that changes runtime behavior, the
  public API, or a platform claim needs TDD evidence, the full validation
  gate, and an independent fresh-context adversarial review. **The review
  gates the merge** — the predecessor initiative recorded two merges that
  outran their reviews and both reviews then found substantive defects in
  merged code, one a behavioral regression on `main`.
- **Predecessor:** the
  [2026-07-24 remediation handover](archive/adversarial-review-2026-07-24-remediation-handover.md)
  (complete, archived 2026-07-31). Its decision 9.1 chose this initiative as
  what follows, and deliberately placed it outside its own completion
  criteria.
- **Successor:** none. The drei and GlyphWright wiring that follows this
  vertical is a separate initiative with its own boundary and handover.
- **Completion:** a POSIX PTY adapter proven end to end on the CI matrix for
  every claim it makes; an `examples/` walkthrough that runs in CI and takes
  a real subject from run to recorded transcript to replay, comparison, and
  report; and a recorded reassessment of which horizontal specifications the
  vertical contradicted or never touched. Wiring the external subjects is
  explicitly *not* part of completion.

## 1. Feature overview

**Initiative:** build TermVerify's first vertical — a POSIX PTY adapter and
one end-to-end example — and use what it finds to decide what the horizontal
specification work was worth.

The problem, scope, platform differences, risks, and sequencing are stated
once, in the
[boundary design](../design/posix-pty-adapter-and-examples-vertical-boundary.md).
This handover does not restate them; it carries the working context a fresh
session needs and the state that changes as slices land.

Two facts set the shape of the work:

- **The adapter above the binding port is already platform-neutral.**
  `ConptyAdapter`'s epoch machinery, marker protocol, watchdog, geometry gate,
  and classification matrix are cross-platform, fake-drivable, and ratcheted
  today. The POSIX work is a binding plus a rename, not a second adapter —
  which is what decision 1 chose — under the stop-and-return trigger in §2.
- **Most of the POSIX machinery is already shipped**, in `_jsonl_pipe.py`:
  session-leader spawn, `poll` plus self-pipe for interruptible I/O with
  in-flight tracking in both directions, `killpg` teardown, and the disclosed
  `setsid()`-escape boundary. It was written for pipes, and the pty binding
  needs the same mechanisms against a master descriptor.

## 2. Design decisions

In force from the boundary design (read it, do not re-derive): one epoch
engine rather than two; the binding owns ambient state and the adapter stays
pure; no new protocol; wall-clock silence is never evidence; the line
discipline is an explicit determinism input; the example is executable and is
not a golden master; the platform claim fails closed.

Taken by the owner 2026-07-31, all five as recommended (full text and
rationale in the design's "Decisions taken"):

1. **Generalize `ConptyAdapter`** into one platform-neutral terminal adapter
   — **with a re-evaluation trigger.** `conpty.py` holds zero platform
   conditionals today (`_conpty.py` has 3, `_jsonl_pipe.py` 14). That zero is
   the threshold: if the generalization cannot be written without platform
   branches above the binding port, Phase 2 **stops and returns to the owner**
   with the specific list and what each conditional absorbs, and a separate
   `PosixPtyAdapter` becomes live again. Do not accumulate conditionals and
   report success.
2. **Linux only.** The probe reports unsupported everywhere CI does not
   verify, macOS included. Do not shape the binding around a macOS claim
   that is not being made.
3. **One marker contract on both platforms.** Subjects implement it once.
4. **Grow `vt.py` one measured sequence at a time**, each with the evidence
   that a real subject emits it. A rejection is a finding to disposition, not
   an obstacle to route around. The VT normalizer decision is not reopened.
5. **A synthetic in-repo TUI** as the example subject.

Inherited and not reopened here: the prototyping-stage freeze suspension (no
compatibility owed to any shipped name, so renames are cheap); the
cooperation-tier constraint model and its delivery-tier honesty; the
fail-closed VT normalizer; recorder-side output coalescing; and the
`termverify._conpty`-style reviewed ratchet exclusion for native legs with
per-OS coverage overlays.

## 3. Phase breakdown

### Phase 0 — Owner decisions and issue filing [DONE 2026-07-31]

All five decisions taken and recorded in §2 and in the design's "Decisions
taken"; the design is `accepted`. Slice issues are filed under the
`vertical-204` label and listed in §4.

### Phase 1 — The POSIX PTY binding [TODO — #267]

`openpty`, child as session leader with the slave as controlling terminal,
master retained as a raw descriptor, explicit line discipline, geometry via
`TIOCSWINSZ`, interruptible reads and writes, one incremental UTF-8 decoder
for the child's life, `killpg` teardown, end-of-stream normalization, and an
explicit support probe. Shaped to satisfy the same child surface
`ConptyChildPort` declares.

**Acceptance:** a cooperative fixture child on the Linux CI legs observes the
creation geometry and a resized geometry; a forced close terminates the
session and reports a real exit record; a blocked read wakes on close; the
support probe answers before any spawn. Measure and record the actual
end-of-stream behavior rather than assuming it.

### Phase 2 — Adapter generalization [TODO — #268]

One platform-neutral terminal adapter over the binding port, executed as a
**pure refactor with no behavior change**. The existing ConPTY suite must stay
green without edits to its assertions; a test that needs editing to pass is
evidence the refactor changed behavior, and is a stop-and-investigate, not a
fix-the-test. Decision 1's zero-platform-conditional threshold is an
acceptance criterion here, and crossing it is a stop-and-return.

### Phase 3 — POSIX integration evidence [TODO — #269]

The real path end to end on the CI matrix, mirroring what the ConPTY adapter
already proves: start to readiness, a text epoch, a resize epoch with observed
dimensions and `SIGWINCH`, subject exit, forced stop, and a deadline abort
with recovery. Every public claim the adapter makes needs a leg here.

### Phase 4 — The example subject and walkthrough [TODO — #270]

A minimal synthetic TUI in the repository (decision 5) and an
`examples/` walkthrough that runs it under the adapter, records, replays,
compares, and renders the report — executed in CI, asserting verdicts rather
than stored bytes. Update the README to point at it instead of describing it.

### Phase 5 — Recorded reassessment [TODO — #271]

Not an implementation phase. What did the vertical contradict? What did it
never touch? Which deferred horizontal item does a real subject now demand?
The output is a decision request to the owner covering the horizontal
moratorium, recorded under `docs/agent/design/`.

## 4. Current status

- **Nothing is implemented.** `main` is at the merge of PR #265
  (`0.2.0.dev0`), suite green. This handover and the boundary design are the
  initiative's only artifacts.
- **Phase 0 is complete.** Boundary accepted 2026-07-31 with all five
  decisions; issues filed under the `vertical-204` label:

  | Phase | Issue | Scope |
  | --- | --- | --- |
  | 1 | #267 | POSIX PTY binding |
  | 2 | #268 | Adapter generalization (carries the stop-and-return trigger) |
  | 3 | #269 | POSIX integration evidence |
  | 4 | #270 | Synthetic TUI and `examples/` walkthrough |
  | 5 | #271 | Recorded reassessment (decision request, not a slice) |

- **Next actionable work is Phase 1 (#267).**
- **Adjacent open issues, none of them this initiative's:** #261 (concurrent-
  I/O disposition — decided re-raise on 2026-07-31, needs a POSIX red, so it
  becomes cheap once Phase 1 exists and may be sequenced against it); the
  #213/#217/#238 Windows containment cluster; #114, whose asks 1–4 are all
  shipped except the examples directory Phase 4 creates.

## 5. Next steps

1. ~~Owner decisions and issue filing~~ **done 2026-07-31** — see §4.
2. **Start Phase 1 (#267)** in a fresh sibling worktree. Write the first
   failing test before the binding exists, push it, and read the red off the
   Ubuntu legs. Begin with the measurements the design deliberately refused to
   assume: the inherited line discipline, and what a master reports once its
   last slave closes.
3. Then #268, #269, #270 in order — each consumes its predecessor — and
   prepare #271 once they have landed.

## 6. Key files & architecture

Existing files this initiative reads or changes:

- `src/termverify/conpty.py` — the epoch engine to generalize; the ports
  (`ConptyBindingPort`, `ConptyChildPort`, `NormalizerFactory`,
  `ConptyWatchdogPort`) the POSIX binding must satisfy.
- `src/termverify/_conpty.py` — the native precedent: incremental decode,
  marker scanning, spawn ownership, ratchet exclusion.
- `src/termverify/_jsonl_pipe.py` — the POSIX mechanisms to reuse:
  `start_new_session`, `poll` plus self-pipe, in-flight tracking,
  `FORCED_TERMINATION_SIGNAL`, `killpg`, the containment disclosure.
- `src/termverify/vt.py` — the fail-closed normalizer a real TUI will test.
- `src/termverify/recorder.py`, `comparator.py`, `replay.py` — the pipeline
  the example walkthrough exercises.
- `pyproject.toml`, `coverage-posix.toml`, `coverage-windows.toml`,
  `.github/workflows/ci.yml` — coverage overlays and the CI matrix.
- New: the POSIX binding module, `examples/`, and the reassessment record.

## 7. Testing approach

- **CI is the red.** The maintainer's host is Windows and this work is
  POSIX-only. Push the failing test first and read the Ubuntu legs. PR #229
  recorded why this is more than a convenience: the predicted failure mode
  was not the observed one — the close returned cleanly and left a thread
  blocked on a descriptor it had just freed — and only CI corrected the
  story.
- **`mypy --platform linux` before pushing** anything touching a
  platform-split module. A Windows-local mypy type-checks only the win32
  branch; the Ubuntu legs have failed on a name missing from the `else`
  branch while every test passed on both platforms.
- **`# pragma: no cover` is static, not conditional** — on a `def` it excludes
  that body on every platform. Use the per-OS overlay markers
  `_jsonl_pipe.py` already uses (issue #230), so each native leg is ratcheted
  where it actually runs.
- **Hostile-subject fixtures** for the deadline and teardown paths: a
  non-reading child, a marker-less trickler, a double-forking `setsid()`
  escapee.
- **Full gate before every commit**, per `AGENTS.md`.

## 8. Session notes

Lessons the predecessor initiative paid for, carried because they apply
directly to this one:

- **Reviews above nit level find false *statements*, not broken code** —
  seven consecutive instances, including in the records the project writes
  about its own reviews. When implementing, write no sentence whose mechanism
  you have just not run. When reviewing, run the claim. This handover's own
  "expected" column for POSIX behavior is a set of predictions, and every one
  of them is to be measured before it is written down as fact.
- **A budget or bound derived from a protocol ceiling must be re-derived when
  the shape of what it bounds changes**, and a test that replicates a
  component's rules shares that component's blind spot — run the real
  component instead.
- **A redundant guard can silently un-pin the guard it backs up**, and a
  constant is not pinned by a test that restates it. Measure behavior at the
  exact boundary.
- **A test that pins a rename deserves the same suspicion as the rename** —
  relevant to Phase 2, where a blanket rename will meet the one list in the
  repo that must not be rewritten: the assertions that the old names are
  gone.
- **Editing tracked files with Python's `pathlib.write_text` on Windows
  rewrites LF as CRLF**, which silently breaks transcript fixtures. Use
  binary reads and writes for bulk edits.
- Branch protection requires up-to-date branches, so merge strictly
  sequentially and rebase the next branch after each merge. `git push` runs
  the full pre-push suite (several minutes) — background it.
