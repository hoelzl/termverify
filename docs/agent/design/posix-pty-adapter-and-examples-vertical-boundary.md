# Vertical Boundary: A POSIX PTY Adapter and the First End-to-End Example

- **Status:** accepted — drafted 2026-07-31 at owner request as the boundary
  decision for [issue #204](https://github.com/hoelzl/termverify/issues/204),
  whose direction (vertical before horizontal) was accepted 2026-07-24 and is
  recorded as decision 9.1 of the archived
  [2026-07-24 remediation handover](../handovers/archive/adversarial-review-2026-07-24-remediation-handover.md).
  Accepted the same day with all five decisions taken as recommended, one of
  them conditionally — see "Decisions taken". Acceptance activates this
  initiative for exactly the scope below and authorizes its slices in order.
  No adapter, example, or platform claim exists until its slice lands with
  evidence and an adversarial-review verdict.
- **Renamed 2026-08-01 (#268):** decision 1 below was executed, so the module
  it names by its pre-generalization name is now `src/termverify/terminal.py`,
  and `ConptyAdapter` / `ConptyBindingPort` are `TerminalAdapter` /
  `TerminalBindingPort`. The measured conditional counts recorded below are the
  counts *at acceptance time* and are deliberately left as measured; the
  post-slice measurement lives in
  `tests/test_terminal_platform_neutrality.py`, which holds the threshold at
  zero. The trigger did not fire.
- **Issue:** [#204](https://github.com/hoelzl/termverify/issues/204);
  prioritization input is
  [#114](https://github.com/hoelzl/termverify/issues/114)
- **Date:** 2026-07-31
- **Inputs:** the accepted
  [terminal-adapter dependency decision](terminal-adapter-dependency-decision.md),
  which explicitly defers POSIX ("no POSIX adapter selection; a POSIX binding
  is a separate future decision") — this document is that decision; the
  accepted [ConPTY adapter design](conpty-adapter-design.md) and its shipped
  implementation (`src/termverify/conpty.py`, `src/termverify/_conpty.py`);
  the POSIX process and descriptor machinery already shipped in
  `src/termverify/_jsonl_pipe.py` (session leader, `poll` plus self-pipe,
  `killpg`, the disclosed `setsid()`-escape boundary); the VT normalizer
  (`src/termverify/vt.py`) and its
  [decision record](vt-normalizer-decision.md); the verification core
  accepted in [phase 2](phase-2-verification-core-boundary.md) (recorder,
  comparator, replay); issue #114 ask 4, which asked for an examples
  directory that still does not exist; and
  [prototyping-stage governance](prototyping-stage-protocol-governance.md),
  under which no compatibility is owed to any shipped name.

## Problem

TermVerify has three runtimes, a verification core, and a protocol — all
specified horizontally, none of them ever driven end to end by a real
terminal subject on the platform most terminal subjects run on. The
2026-07-24 review named this directly: the project has been specifying faster
than it has been proving, and its remaining unknowns are concentrated exactly
where no vertical has run.

Two concrete gaps stand out.

**No POSIX terminal evidence exists.** The one terminal adapter is Windows
ConPTY. Every terminal claim TermVerify makes — geometry receipts, the
readiness-marker contract, epoch quiescence, containment, forced teardown —
is proven on one platform whose pseudoconsole is the least conventional of
the two. Where ConPTY forced a compromise (a printable marker, because OSC
passes ahead of rendered text; a geometry the console silently substitutes,
issue #228), it is unknown which compromises are the *contract* and which are
ConPTY's.

**Nothing demonstrates the whole pipeline.** `examples/` does not exist. A
reader cannot see a subject go from "run it" to "recorded transcript" to
"replayed and compared, with a report" without assembling it from tests. That
is also why the pipeline's seams are untested *as a pipeline*: each component
has excellent unit evidence and no component has ever been handed the output
of a real terminal run by a real TUI.

## Decision summary

One initiative, deliberately narrow, with two halves that gate each other:

1. **A POSIX PTY binding and a platform-neutral terminal adapter above it.**
   The binding is TermVerify's own, built on the standard library, and owns
   the pty pair, the child's session, its line discipline, geometry, and
   teardown. The adapter above it is the *existing* ConPTY adapter
   generalized, not a second copy of the epoch machinery.
2. **An `examples/` end-to-end walkthrough** driven by a minimal synthetic
   TUI subject that lives in this repository: run, record, replay, compare,
   report — executed in CI so it cannot rot into prose.

The vertical's purpose is diagnostic as much as additive. Its findings —
which specifications the real path contradicts, which the real path never
touches — are the recorded input to lifting the horizontal moratorium. Wiring
drei and GlyphWright as design-driver subjects follows this initiative and is
outside its boundary.

## Design rules

These bind every slice.

1. **One epoch engine, not two.** The marker protocol, epoch loop, watchdog,
   geometry gate, classification matrix, and normalizer feed have exactly one
   implementation. A platform difference is absorbed by the binding port or
   disclosed as evidence; it is never absorbed by a second copy of a rule.
   This project's recorded failure mode is two implementations of one rule
   drifting until a false sentence is attached to one of them.
2. **The binding owns the ambient, the adapter stays pure.** Everything above
   the binding port remains cross-platform, fake-drivable on every platform,
   and fully coverage-ratcheted. The POSIX binding joins `termverify._conpty`
   as a reviewed ratchet exclusion only for its native leg, with the same
   per-OS overlay treatment `_jsonl_pipe.py` already uses.
3. **No new protocol.** No transcript record kind, payload member, registry,
   or vocabulary is added or changed. A need for one suspends the slice and
   returns to the owner — the same stop-and-return rule the verification core
   carries. The horizontal moratorium is in force for the duration.
4. **Wall-clock silence is never evidence.** Quiescence comes from an
   observed readiness marker or from end-of-stream plus an observed exit
   record. The abort deadline is host policy that can only produce a
   structured failure. Unchanged from the ConPTY design, and restated because
   a PTY makes "it looks quiet" easy to reach for.
5. **The line discipline is an explicit determinism input.** A pty's termios
   state is ambient: echo, canonical mode, signal characters, and newline
   translation all change what a subject sees and what reaches the
   transcript. The binding sets it explicitly and records what it set;
   inheriting whatever the host default happens to be would put ambient state
   into evidence, which the deterministic-core rule forbids.
6. **The example is executable, and it is not a golden master.** It runs in
   CI. It asserts the pipeline's verdict — that a replay compares equivalent
   — and never asserts stored transcript or report bytes as behavioral truth;
   baseline governance stays outside this boundary.
7. **Fail closed on the platform claim.** The binding answers support through
   an explicit probe before any spawn, exactly as `ConptyBindingPort` does. A
   platform the CI matrix does not verify reports unsupported; it does not
   run unverified and hope.

## What the POSIX binding owns

Shaped to satisfy the same child surface the ConPTY binding does (`read`,
`write`, `resize`, `is_alive`, `close(force=)`, `pid`, `exit_status`), so the
adapter above it needs no platform branch:

- **The pty pair and the spawn.** `openpty`, the child on the slave side as a
  session leader with the slave as its controlling terminal, the master
  retained as a raw descriptor. The environment overlay and working directory
  compose inside the binding, exactly as the ConPTY port's spawn factory
  does, so the ratcheted adapter never reads ambient state.
- **The line discipline**, per design rule 5.
- **Geometry**, set at creation and changed only by explicit resize, through
  `TIOCSWINSZ`. Unlike ConPTY, a POSIX resize also delivers `SIGWINCH` to the
  foreground process group, which is a *stronger* delivery than the Windows
  path and must be described as what it is rather than averaged with it.
- **Incremental UTF-8 decoding across reads**, by the same rule `_conpty.py`
  established after issue #197: one decoder for the life of the child, so a
  read landing mid-codepoint heals across chunks instead of embedding
  irreparable `U+FFFD` in evidence. Issue #279 added the other half of that
  rule, which was implicit here and unimplemented on this side: at
  end-of-stream the decoder is *flushed*, so a sequence nothing can now
  complete is reported as replacement text rather than discarded. It is now
  a stated port contract on `TerminalEndOfStreamError`, and the divergence
  it opens — a pty hands the binding those bytes where a Windows console
  host has already consumed them — is recorded in `_terminal_binding.py`.
- **Interruptible reads and writes**, reusing the mechanism
  `_jsonl_pipe.py` already ships on POSIX: `poll` over the descriptor plus a
  self-pipe, with every close signalling before it touches a descriptor, and
  in-flight tracking on both directions so a close cannot free a descriptor
  number under a live `os.write`.
- **Containment and teardown**: the child's own session, `killpg` on forced
  close, and the same disclosed boundary — a `setsid()` descendant escapes
  and is not reaped. That disclosure already exists for the JSONL transport
  and is restated, not weakened.
- **End-of-stream normalization.** A master whose last slave has closed does
  not report end-of-stream identically across POSIX platforms; the binding
  normalizes the platform's behavior into the same end-of-stream signal the
  adapter already handles. The actual behavior on each verified platform is
  established by measurement in the binding slice, not assumed here.

## Platform truths that differ from ConPTY

Named up front because the vertical exists to find these, and because
averaging them away would be the exact failure this project keeps catching in
review:

| Question | ConPTY (shipped) | POSIX PTY (expected) |
| --- | --- | --- |
| Geometry claim | `tier: "os"` is claimed for geometries the console silently substitutes (issue #228 measured the kill band) | `TIOCSWINSZ` applies the requested size; the receipt should be able to claim `os` honestly over a far wider range — **verify, do not assume** |
| Resize delivery | Delivers no stdin bytes; the subject must detect it | Delivers `SIGWINCH` to the foreground process group |
| Marker path | Printable and per-emission-token, because OSC passes ahead of rendered text and repaints re-emit screen state | A byte stream with no repaint re-emission, so the constraint that forced this on Windows does not apply |
| Output vocabulary | The VT normalizer's vocabulary grew against what ConPTY emits | A real POSIX TUI will emit sequences the normalizer rejects fail-closed — see Risks |

## The examples vertical

One directory, one subject, one walkthrough.

- **The subject** is a minimal synthetic TUI committed to this repository:
  deterministic, dependency-free, emitting the readiness-marker contract, with
  enough screen behavior to make frames worth comparing (a cursor, a redraw,
  a resize response) and no behavior that is not needed to show that.
- **The walkthrough** runs it under the terminal adapter, records with
  `TranscriptRecorder`, replays the transcript, compares the two, and renders
  the report — the first time those five components meet outside a test.
- **It runs in CI**, on every verified platform, and its assertions are the
  pipeline's verdicts rather than stored bytes (design rule 6).

The same walkthrough is what #114 ask 4 asked for and what the README can
point at instead of describing.

## Decisions taken

Owner, 2026-07-31. All five as recommended; decision 1 carries an explicit
re-evaluation trigger the owner added.

1. **Adapter structure: generalize `ConptyAdapter`** into one
   platform-neutral terminal adapter over a binding port. Prototyping-stage
   governance owes no compatibility for the rename.

   **Re-evaluation trigger, and it is measurable.** The generalization is
   authorized on the premise that platform differences are absorbed by the
   binding port — design rule 1. `src/termverify/conpty.py` today contains
   **zero** platform conditionals (`sys.platform`, `os.name`); the native
   modules hold them all (`_conpty.py`: 3, `_jsonl_pipe.py`: 14). That zero
   is the threshold. If the generalized adapter cannot be written without
   introducing platform branches above the binding port, the slice **stops
   and returns to the owner** with the specific list of conditionals and what
   each one is absorbing, rather than accumulating them — at which point a
   separate `PosixPtyAdapter` becomes the live alternative again. Holding the
   count at zero is an acceptance criterion of the slice and of its review; a
   ratchet on it is the natural mechanism but the slice chooses.

2. **Platform claim scope: Linux only, for now.** The support probe reports
   unsupported on every platform the CI matrix does not verify, including
   macOS — no unverified running. Adding `macos-latest` stays available as a
   later, separate change if a subject asks for it; nothing in the binding is
   to be shaped around a macOS claim that is not being made.
3. **Marker contract: one contract on both platforms.** Subjects implement
   the readiness marker once — printable, per-emission token — and it works
   on either adapter. The POSIX path does not need the constraints that
   forced this shape on ConPTY, and inherits them anyway rather than
   splitting the contract subjects must satisfy.
4. **Normalizer vocabulary: grow `vt.py` one measured sequence at a time**,
   each addition carrying the evidence that a real subject emits it. The
   fail-closed design is doing its job when it rejects; a rejection is a
   finding to be dispositioned, not an obstacle to route around. This
   deliberately does **not** reopen the
   [VT normalizer decision](vt-normalizer-decision.md); reopening it would
   need its own reuse assessment.
5. **Example subject: a synthetic in-repo TUI.** Deterministic, no
   dependency, and the walkthrough stays about TermVerify rather than about
   somebody else's application.

## Non-goals

Explicitly outside; each needs its own decision:

- **Wiring drei and GlyphWright**, and repairing the drifted GlyphWright
  conformance fixture. That is the initiative *after* this one — it is what
  the vertical makes possible, not part of it.
- **Lifting the horizontal moratorium.** This initiative produces the
  recorded input for that decision and does not take it.
- **New registries, sidecar formats, protocol vocabulary, or mirror
  infrastructure** (design rule 3), including terminal-capability registry
  activation and key-to-terminal byte-mapping changes.
- **Golden-master or baseline governance**, differential multi-target
  orchestration, normalizers-per-scenario, and cross-mode semantic
  comparison.
- **Containment enforcement claims** beyond what is already disclosed; the
  `setsid()` escape stays a disclosed boundary.
- **The Windows containment cluster** (issues #213, #217, #238) and the
  concurrent-I/O disposition slice (issue #261). #261 becomes cheap to red
  once a POSIX development path exists, and may be sequenced against it, but
  it is not this boundary's work.
- **Any release claim or version bump.**

## Risks

- **The normalizer meets a real TUI.** `vt.py` rejects unknown control
  characters, escape sequences, private modes, and erase selectors at
  fourteen distinct sites, and its vocabulary was grown against what ConPTY
  emits — issue #200 had to add secondary-DA and DEL tolerance because a
  conhost preamble failed every run on one host. A real POSIX TUI is a much
  wider emitter. This is the likeliest place the vertical stalls, and the
  likeliest place it pays for itself. Mitigation: decision 4 settled the
  policy before the slice starts — grow the vocabulary one measured sequence
  at a time — and the synthetic subject's vocabulary is a scope dial the
  owner controls.
- **The generalization touches shipped, working code.** Slice 2 refactors an
  adapter that took six review rounds to get right. Mitigation: it is a
  pure-refactor slice with no behavior change, gated on the existing suite
  staying green without edits to its assertions; any test that needs editing
  to pass is treated as evidence that the refactor changed behavior.
- **POSIX-only work cannot be developed red on the maintainer's host.** This
  is a Windows machine. Mitigation: the CI legs are the red, exactly as in
  PR #229 — push the failing test first and read the Ubuntu leg. That slice
  also recorded why this matters beyond convenience: the predicted failure
  was not the observed one, and only CI corrected the story.
- **Vertical scope creep.** A real subject generates feature requests at
  contact. Mitigation: design rule 3's stop-and-return, and the moratorium.

## Acceptance and sequencing

On acceptance, five slices, in order; each begins only when the previous is
accepted, since each consumes its predecessor:

1. **Binding** — `openpty`, spawn as session leader, explicit line
   discipline, geometry, interruptible I/O, incremental decode, teardown,
   end-of-stream normalization, support probe. Linux CI evidence with a
   cooperative fixture child.
2. **Adapter generalization** — the structural decision from item 1 of
   "Decisions taken" — one platform-neutral adapter — as a pure refactor with
   no behavior change, holding the zero-platform-conditional threshold that
   decision states.
3. **Integration evidence** — the real POSIX path end to end on the CI
   matrix: start to readiness, text epoch, resize epoch with observed
   dimensions and `SIGWINCH`, subject exit, forced stop, deadline abort with
   recovery. The mirror of what the ConPTY adapter already proves.
4. **The example subject and walkthrough**, executed in CI.
5. **Recorded reassessment** — what the vertical contradicted, what it never
   touched, and the resulting recommendation on the horizontal moratorium.
   This is a decision request to the owner, not an implementation slice.

Each implementation slice follows the standard loop: focused issue, external
sibling worktree, strict TDD, full validation gate, PR, fresh-context
adversarial review that gates the merge.
