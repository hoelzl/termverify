# Adversarial Review 2026-07-24 Remediation Handover

## Handover metadata

- **Status:** active — created 2026-07-24 at owner request to plan and track
  remediation of every finding in the
  [2026-07-24 adversarial review](../reviews/adversarial-review-2026-07-24.md)
  (reviewed revision: `main` @ `8f33e6c`).
- **Owner:** project maintainer
- **Created:** 2026-07-24
- **Updated:** 2026-07-29 (checkpoint f: **Phases 1–7 complete**, 0.1.1
  released; next item is Phase 8 / #200–#203)
- **Review required:** yes — every slice that changes runtime behavior, the
  public API, protocol prose with normative force, or release/security claims
  requires TDD evidence, full validation, and an independent adversarial
  review pass per the standard slice loop. Doc-only hygiene slices require
  normal PR review. **The review gates the merge.** Two 2026-07-25 slices
  were merged while their reviews were still running and both reviews then
  found substantive defects in merged code, one of them a behavioral
  regression on `main`; see the checkpoint note in §4.
- **Predecessor:** none (the archived
  [adversarial review remediation handover](archive/adversarial-review-remediation-handover.md)
  covered the earlier review cycle through PR #80 and is complete; this
  handover addresses the new 2026-07-24 review and does not reopen it).
- **Successor:** none
- **Completion:** every finding in the 2026-07-24 review is either (a) fixed
  with verified evidence, (b) explicitly disclosed as a documented boundary,
  or (c) retired to a non-goal by a recorded owner decision. Findings must not
  be silently dropped; each phase below lists its findings and their required
  disposition. Strategic recommendations (Phase 9) complete by recorded owner
  decision, not necessarily by implementation.

## 1. Feature overview

**Initiative:** remediate all findings from the 2026-07-24 adversarial design
and implementation review of TermVerify (`main` @ `8f33e6c`).

The review confirmed the code, tests, and release engineering are strong but
found: (1) two critical issues — the README/SECURITY.md deny the 0.1.0 PyPI
release that actually happened, and JSONL protocol writes run outside the
abort deadline so a non-reading subject hangs the verifier forever; (2) seven
major runtime/adapter findings (unbounded read buffer, ConPTY deadline
re-arming, unchecked `AssignProcessToJobObject`, escapable POSIX containment,
lone-surrogate asymmetry between codecs, ConPTY chunk-boundary replay
divergence, ConPTY decode-boundary risk); (3) nine major protocol/design/
governance findings (spec/runtime contradiction on spawn-env, the
`enforced`-status vs. cooperation-tier seam, premature v1 freeze, unused
frozen timezone registry, README overpromising, missing POSIX adapter and
examples, premature governance machinery, prose-drift pattern, inverted
authority polarity); and ~30 minor findings across runtime, protocol core,
tests/CI, and docs.

This matters because TermVerify's product **is** truthful, replayable
evidence. The most damaging findings are exactly the ones where the project's
own claims (release status, deadline guarantee, parity claims) do not match
its behavior.

**Source of truth for finding detail:** the review document itself, with
file:line citations. This handover references findings by their review IDs
(C1–C2, R1–R7, P1–P9, and the minor-findings bullets) and adds the
remediation plan; do not restate the review's evidence here.

Relevant links:

- Review: `docs/agent/reviews/adversarial-review-2026-07-24.md`
- Reviewed revision: `8f33e6c`
- GitHub issues: to be filed per slice (Phase 0 below); record issue numbers
  in this document as they are created.

## 2. Design decisions

Decisions already in force that constrain this remediation:

- **Slice workflow is mandatory.** Each behavioral fix follows the standard
  loop: focused GitHub issue → external sibling worktree on its own branch →
  strict TDD (failing test first) → full validation gate → PR → adversarial
  review → merge (`docs/developer-guide/agent-workflow.md`). Doc-only slices
  still get an issue and PR but need no worktree isolation if sequenced.
- **The freeze is suspended: prototyping-stage governance (owner decision
  2026-07-24).** Recorded in
  `docs/agent/design/prototyping-stage-protocol-governance.md` and stated in
  `docs/knowledge/protocol.md` and `AGENTS.md`. Every TermVerify protocol
  and registry may change incompatibly in place, without version bumps,
  compatibility shims, or per-change exceptions, until the owner declares
  TermVerify ready for external clients. No backward compatibility is owed
  to the published 0.1.0 artifact; drei and GlyphWright are design-driver
  users that migrate with TermVerify. The slice discipline (issue, TDD,
  fixture migration and doc update in the same change, review) is
  unchanged — only the compatibility ceremony is dropped. This supersedes
  the frozen-surface caveats originally attached to Slices 2.3 and 3.1.
- **Failure taxonomy is normative.** Fixes that add failure paths (R1, C2,
  R2) must map new failures onto the existing structured taxonomy
  (`peer-malformed`, `peer-lifecycle`, deadline-attributed classes) rather
  than inventing new categories, unless a protocol amendment is separately
  decided.
- **Disclosure is an accepted disposition.** Where the review itself offers
  "fix or disclose" (R4, R6, R7, minor `_conpty.py` items), a documented
  boundary note in the style of the existing ConPTY assignment-window
  disclosure is acceptable; which of the two applies is an owner decision
  recorded in the slice issue.
- **Prose fixes must not create new drift.** C1/P3-class fixes touch facts
  stated in multiple places; each such slice must enumerate *all* restatement
  sites (the review lists them) and fix them in one change, per AGENTS.md's
  "update stale documentation in the same change" rule.
- **Ordering follows the review's leverage ranking.** Phases 1–2 are
  hours-scale, high-leverage, and unblock trust in the docs; Phases 4–5 are
  the substantive runtime work; Phase 9 items are strategic owner decisions
  and must not silently expand into implementation without a recorded
  decision.

Alternatives considered and rejected:

- *One mega-PR for all fixes* — rejected: violates the focused-slice rule,
  makes adversarial review ineffective, and mixes doc-only with
  behavior-changing work.
- *Fixing minors opportunistically inside major slices* — rejected except
  where a minor touches the identical lines (e.g., `TerminateJobObject`
  return check rides with R3): keeps review scopes honest.
- *Treating strategic items (P4, P6, P7) as ordinary fix slices* — rejected:
  they are direction decisions (build a POSIX adapter, de-scope registries)
  that belong to the owner, recorded under `docs/agent/design/`.

## 3. Phase breakdown

Phases are ordered by the review's own prioritization (§6 of the review).
Within a phase, slices are independent unless noted and may run in parallel
worktrees per the workflow rules.

### Phase 0 — Issue filing and sequencing [DONE 2026-07-24]

All issues are filed under the `review-2026-07-24` label:

| Issue | Slice / scope |
| --- | --- |
| #184 | Governance docs: prototyping-stage decision + this handover (resolved by the governance docs PR) |
| #185 | Slice 1.1 — release status in README/SECURITY + prototyping posture (C1) |
| #186 | Slice 1.2 — spawn-env sentence, ADR status, chord count, CRLF guidance, doc hygiene (P1) |
| #187 | Slice 2.1 — bound JSONL read buffer (R1) |
| #188 | Slice 2.2 — job-object return checks (R3) |
| #189 | Slice 2.3 — reject unpaired surrogates (R5) |
| #190 | Slice 3.1 — tier-truthful `capability.result.status` (P2) |
| #191 | Slice 3.2 — code-authoritative polarity (P9) |
| #192 | Timezone-registry removal (P4 / decision 9.4) |
| #193 | Slice 4.1 — writes under the abort deadline (C2) |
| #194 | Slice 4.2 — ConPTY per-epoch deadline/budget (R2) |
| #195 | Slice 5.1 — recorder-side chunk coalescing (R6) |
| #196 | Slice 5.2 — interruptible POSIX reader + containment disclosure (R4) |
| #197 | Slice 5.3 — raw-byte ConPTY read path, incremental decoding (R7) |
| #198 | Phase 6 — public API exports |
| #199 | Phase 7 — README current-only + vision doc (P5) |
| #200 | Slice 8.1 — runtime/adapter minors |
| #201 | Slice 8.2 — transcript-core minors |
| #202 | Slice 8.3 — tests/CI minors (Hypothesis profile, scripts coverage) |
| #203 | Slice 8.4 — release/process minors (.dev0 scheme, prose validator) |
| #204 | Vertical initiative tracker (decision 9.1; outside this handover's completion) |

Every review finding maps to an issue above or to a disposition already
recorded in this handover (9.3 freeze suspension — #184; PR-177 root files —
already resolved by PR #183).

### Phase 1 — Status-truth documentation fixes (review recs 1, 4) [DONE 2026-07-25]

Slice 1.1 merged as PR #206 (resolves #185); Slice 1.2 merged as PR #207
(resolves #186). The protocol.md freeze statement had already landed with
the governance PR #205. Original slice text follows for the record.

Doc-only. One or two PRs. Findings: **C1**, **P3** (statement part), **P1**
(doc side), plus the doc-hygiene minors that are pure prose.

- **Slice 1.1 — Release-status truth (C1 + P3 statement).**
  - `README.md:35-36`: replace "no release is authorized and nothing is
    published" with the actual state: 0.1.0 published to PyPI 2026-07-19 via
    the CI-gated Release workflow — and state the prototyping-stage posture:
    the artifact is a distribution-pipeline exercise, no compatibility is
    guaranteed, protocols and APIs may change incompatibly without notice
    (link the governance decision record).
  - `SECURITY.md:5-11`: supported-versions section must name 0.1.0 as a
    released artifact and state the actual support policy for it, consistent
    with the prototyping-stage posture.
  - ~~`docs/knowledge/protocol.md` freeze statement~~ **done 2026-07-24**:
    the "Compatibility and evolution" section now states that the freeze
    fired 2026-07-19 and was suspended 2026-07-24 (prototyping stage), and
    the stale present-tense inception prose is replaced (see
    `docs/agent/design/prototyping-stage-protocol-governance.md`).
  - Sweep for other restatements of release status before closing (the
    review's P8 lists the known drift sites).
- **Slice 1.2 — Spec/docstring corrections and doc hygiene.**
  - **P1:** correct `protocol.md:355-356` to "carrying both `env` and a
    channel *other than `spawn-env`*"; fix the matching docstring at
    `src/termverify/transcript.py:125-127` and repair its "never relaxes
    acceptance" argument to cover the spawn-env case. Doc/docstring-only — do
    not change runtime acceptance (the runtime is correct).
  - ADR status: `docs/agent/design/jsonl-control-transport.md:3` "proposed" →
    "accepted" (slices 1–2 merged).
  - Stale chord count: `docs/agent/handovers/pre-release-boundary-hardening-handover.md:276`
    934 → 1,382.
  - Adapter-author guide: add the CRLF/binary-stdout sentence (subjects must
    write protocol lines via a binary stream, e.g. `sys.stdout.buffer`;
    text-mode `print` emits `\r\n` on Windows and every message is rejected
    `peer-malformed`).
  - `docs/developer-guide/development.md:59`: remove or correct the
    nonexistent `skills/` directory entry.
  - `docs/knowledge/control-protocol.md` frontmatter: add title/description/
    tags to match siblings.
  - ~~Root-level `review-pr177-summary.md` / `review-pr177-rereview-summary.md`~~
    **already resolved by PR #183** (merged after the reviewed revision):
    both files now live under `docs/agent/reviews/`. No action; verify at
    slice time and drop.

**Acceptance:** no document in the repo denies the 0.1.0 release; protocol.md
and the transcript docstring no longer contradict runtime acceptance; each
listed hygiene item done. Validation: `pre-commit run --all-files` plus the
repo's docs validators.

### Phase 2 — One-comparison runtime hardening (review rec 2, 3) [DONE 2026-07-25]

Small, high-leverage behavioral fixes. Strict TDD each. Findings: **R1**,
**R3**, **R5** — all three merged with fresh-context adversarial reviews:
Slice 2.1 (PR #208), Slice 2.3 (PR #209), Slice 2.2 (PR #211 plus its
review follow-up #214).

- **Slice 2.1 — Bound the JSONL read buffer (R1). [DONE — PR #208]**
  Merged 2026-07-25 after a three-round adversarial review whose round 1
  correctly REJECTED the first implementation: the memory-bound guard
  fired even when an LF was buffered, which would have misclassified a
  conforming maximal framed line whose next message coalesced into the
  same reads. Final shape: the bound applies only to LF-free
  over-ceiling buffers; a real-child regression test (single-write
  maximal line + tail, deterministic coalescing) guards the exact bug;
  the flood test reads on a bounded joined thread. Review trail is on
  the PR. Original slice text:
  `src/termverify/_jsonl_pipe.py:328-365` (`_read_line_tracked`): fail once
  the accumulated buffer exceeds `_MAX_LINE_BYTES + 1` (import/share the
  ceiling from `control.py`) instead of buffering an unbounded newline-free
  stream. Classify as `peer-malformed`, consistent with the post-hoc
  `parse_message` check. Test: subject streaming newline-free bytes; assert
  structured failure and bounded memory (assert the loop exits by byte count,
  not by timing).
- **Slice 2.2 — Check job-object containment results (R3). [DONE — PR #211
  plus follow-up #214]** Merged 2026-07-25. Checked
  `_assign_to_job`/`_terminate_job` wrappers mirroring the ConPTY binding's,
  called from the spawn containment block and `_terminate_tree`, with
  Windows-only tests that force the native failure legs by replacing the
  bound `_kernel32` function.

  **This slice is the handover's clearest evidence for why the review step
  must gate the merge.** PR #211 was merged while its adversarial review was
  still running, and the review then found two defects in the merged code:

  1. *A regression on `main`.* Windows answers `ERROR_ACCESS_DENIED` when
     asked to assign an **already-exited** process to a job, so a subject
     that exited inside the disclosed assignment window was reported as a
     containment failure — a legitimate fast subject failing to spawn,
     non-deterministically. Fixed in #214: that case is read as nothing
     left to contain, and the binding reports the child's real exit.
  2. *A false claim plus a live deadlock.* The docstring and changelog
     asserted that a failed `TerminateJobObject` cannot leak the tree
     because kill-on-close still sweeps it. With a read in flight that was
     false: the raise skipped the delivery wait, `_close_pipes`' detach
     blocked forever on the blocked reader's lock, `CloseHandle(job)` was
     never reached, the tree leaked and `close` never returned — reachable
     through the adapter's own watchdog shape. Fixed in #214 by releasing
     containment **before** touching the pipes, on the stated invariant:
     *release every mechanism that can unblock a reader before performing
     any operation that can block behind one.*

  A third finding was pre-existing and deliberately not widened into the
  fix: the same `_close_pipes` deadlock is reachable with **no patching at
  all** when a descendant holds the child's stdout write end, which POSIX
  cannot unblock at all. Filed as **#213** for Slice 5.2 (#196), whose
  `poll`/self-pipe reader is the real remedy.

  **Round 2 of that review returned REJECT, and was right to.** It could
  not refute either functional fix — it verified the teardown reorder is
  safe on all five paths through `close` (the only assignment to
  `_exit_status` precedes the `finally`, and the property short-circuits on
  `_process is None`), that both new tests are red on revert, and that the
  reorder is a no-op on POSIX. What it refuted, by probe, were the *claims*
  attached to the fixes:

  - I had written that a window-leg binding's job "still sweeps, on
    release, any descendant that joined". **Impossible:** job membership
    comes only from assignment or inheritance through a member, so a job
    whose member was never assigned stays permanently empty. The probe then
    showed the consequence — with a job handle present, a descendant
    holding the child's stdout write end still hung `close` and leaked the
    tree, re-opening the very failure mode the round-1 fix addressed. The
    binding now **discloses** that boundary in `spawn` and `close` instead
    of denying it, and describes the sweep as covering every remaining job
    *member*, never "the tree".
  - The new pipe release **did not release**: after `detach` the descriptor
    belongs to the raw stream, so closing the buffered wrapper only raises
    (and `_suppress_os_errors` swallows `ValueError` too). Both pipes still
    reached their finalizers with a `ResourceWarning`. A shared
    `_release_pipes` now closes the raw stream on both paths.
  - `subprocess.TimeoutExpired` is not an `OSError`, so the timeout I added
    to the fail-closed wait could escape unclassified while leaking two
    kernel handles and both pipes. Now wrapped in `try/finally`.

  Two further findings are **recorded rather than fixed**:

  - **#217** — `io.BufferedWriter.detach()` *flushes*. Two comments claimed
    a release-without-flush, so the stdin-flush hang they exist to prevent
    is not actually prevented; it is bounded only because the tree is
    usually already dead. Belongs with #213 and Slice 5.2.
  - The window leg's uncontained descendant is **not observable on this
    toolchain**: the launcher's own outer job sweeps it before a test can
    look. Worth knowing — the containment covering that case is somebody
    else's, which is exactly why the binding must not claim credit for it.

  Original slice text follows.
- **Slice 2.2 — Check job-object containment results (R3).**
  `src/termverify/_jsonl_pipe.py:266`: check `AssignProcessToJobObject`'s
  BOOL return like the sibling calls (`CreateJobObjectW` `:145`,
  `SetInformationJobObject` `:157`) and raise on failure so no uncontained
  session is handed out — matching the docstring contract at `:232-236` and
  the ConPTY binding's correct pattern (`_conpty.py:214-216`). Also check
  `TerminateJobObject`'s return at `:516` (same-lines minor). Windows-only
  tests.
- **Slice 2.3 — Reject unpaired surrogates in the control codec (R5).
  [DONE — PR #209]** Merged 2026-07-25, adversarial review ACCEPT WITH
  NITS (all nits applied: explicit unpaired-surrogate sentence in the
  normative control-protocol.md framing rules, payload-positioned
  rejection test, hoisted import). Reviewer-verified: ingress-complete
  for the wire path; both codec directions now reject with the codec's
  own error. **Recorded scope note for Slices 8.1/8.2:** host-injected
  custom ConPTY/direct ports can still hand surrogate-bearing `str` to
  the recorder (trusted-host defense-in-depth, deliberately out of this
  slice). Original slice text:
  `src/termverify/control.py`: `_validate_json_value` must reject lone
  surrogates so `parse_message` never admits a string
  `serialize_transcript` will refuse — restoring codec symmetry and turning a
  recording-pipeline crash into a structured `peer-malformed` failure. Tests:
  the `json.loads('"\\ud800"')` path end-to-end (parse → observation →
  recorder → serialize no longer raises `TranscriptValidationError`); plus
  symmetry property test. (Prototyping-stage governance applies — no
  frozen-surface argument needed.)

**Acceptance:** each slice merged with red→green TDD evidence and full gate;
review sign-off that failure classification matches the taxonomy.

### Phase 3 — Protocol-truthfulness reconciliation (review rec 7, partial) [DONE 2026-07-25]

Prose with normative force; needs owner decisions on wording. Findings:
**P2**, **P9**.

Status 2026-07-25: **both slices are merged.** Slice 3.2 (#191) as PR #212
plus its review follow-up PR #215; Slice 3.1 (#190) as PR #216. The
Phase 3-adjacent timezone-registry removal (#192, decision 9.4) merged the
same day as PR #220. Slice 3.1 also *transferred* one item rather than
completing it — the in-process vocabulary deferral recorded below — which
became #218 and was executed under Phase 6 (PR #255, 2026-07-29). The
transfer is why this heading read `[IN PROGRESS]` until 2026-07-29 even
though nothing Phase 3 owned was outstanding after 2026-07-25; it is dated
here by its own completion, and #218 is counted under Phase 6, not twice.

**Slice 3.1 outcome (PR #216).** The chosen vocabulary is `enforced` →
**`applied`**: the status word states only that the adapter carried out the
constraint's application step and recorded the value it applied, and the
already-mandatory `tier` states what that step was worth — at `os` and
`constructive` the constraint is in force; at `delivered` what was applied
is the *delivery*, and whether the subject honors it is not observable.
There is no third status, and `enforced` is not an accepted value.

Rejected alternatives, recorded here so the reasoning is in-repo rather
than only in issue #190's comment thread:

- *Keep `enforced` for `os`/`constructive` and add `delivered` as a third
  status* — reintroduces exactly the `supported-but-not-enforced` state the
  spec calls invalid, and splits claim strength across two members.
- *Fold the tier into the status (`enforced-os`, …)* — duplicates `tier`,
  and the status vocabulary would then grow whenever the tier vocabulary
  does.
- *Drop `status`, make `tier`-or-`unsupported` the discriminator* — a
  larger structural change for no truthfulness gain; `status` is also what
  the terminal-record rule keys off.
- *A word with no residual claim at all (`negotiated`, `recorded`)* — raised
  by the slice's reviewer, who did not block on it. `applied` keeps a mild
  looseness at the `delivered` tier, addressed in prose rather than by a
  second migration; revisit if a vertical makes it bite.

The related seam moved in the same change: "an adapter that cannot enforce a
requested constraint must not claim a verified run" became the rule the
shipped tiers support — record `unsupported` and terminate when a constraint
cannot be applied at any tier, and never record a tier stronger than the
mechanism used. A run's constraint claims are **no stronger than** its
weakest tier; the first draft said "exactly as strong as", which the review
correctly called an overstatement (only an upper bound holds, and nothing
computes a min-tier).

**The review also found the P2 defect class still alive in prose the slice
had not touched**, which is the more valuable outcome. `protocol.md`'s
adapter-facing contract told authors that an adapter "gives filesystem
access only through the named sandbox root and denies network access by
default", "injects the requested seed and manual clock", and "starts
subprocesses with the requested locale and timezone" — while
`src/termverify/cooperation.py` discloses in its own words that nothing
blocks sockets, that the filesystem check is not containment, that
manual-time advances are never delivered, and that no `LANG`/`LC_ALL` is
set. Those sentences were a *stronger* overstatement than the status word,
and they contradicted the accepted 2026-07-18 decision that no receipt,
claim, or document may imply containment. The contract is now stated per
tier, and `architecture.md`'s "either enforces … or unsupported" binary
(one bullet above a line the slice had already edited) is replaced by the
tiered rule. **Lesson for later slices: when a vocabulary is corrected,
sweep the prose that the old vocabulary licensed, not just the sites that
name it.**

Scope facts established by that slice, worth not rediscovering:

- The packaged JSON Schema never encoded `status`, so no schema, `$id`, or
  mirror-publication work rides along with a status-vocabulary change.
- `recorder.py` holds the only emitter; `transcript.py` holds all validation.
- The external GlyphWright spike fixture stays byte-for-byte as retrieved
  (its recorded SHA-256 still verifies); its disclosed conformance delta
  widened from one member to two, recorded in `PROVENANCE.md` and the test.
- ~~Deliberately deferred and tracked as #218~~ **done 2026-07-29 — PR
  #255**, folded into Phase 6 as this bullet asked. The in-process API kept
  the older vocabulary at the time: `EnforcedConstraints` (public, exported),
  `StartUnsupported`/`StartFailed` `.enforced`, `UnenforcedConstraintPorts`,
  and — not noticed here — the seven `ConstraintPorts.enforce_*` ports, which
  the owner added to #218's scope so the rename closed the seam rather than
  moving it. **This bullet's original list also named `AdapterResult.enforced`
  and `StartOk`, neither of which ever existed**, and implied a
  `Started.enforced` that is really `Started.constraints`; the phantoms cost a
  later session real time, so they are corrected rather than struck. Nothing
  there was false (claim strength is carried by `EnforcementReceipt.tier`),
  but an adapter author populated `EnforcedConstraints` and watched it emit
  `applied`. The `constraint-not-enforced` wire code stays: renaming it has no
  truthfulness payoff.

- **Slice 3.1 — `status: "enforced"` vs. "Nothing is enforced" (P2).**
  **Owner decision 2026-07-24: fix the wire vocabulary properly (Option B),
  under prototyping-stage governance — in place, no version bump, no
  exception ceremony.** Make `capability.result.status` tier-truthful (e.g.,
  admit a `delivered`-tier-honest value or restructure status to carry the
  tier); update codec, emitters, fixtures, protocol.md, and the tier prose
  in the same reviewed change. Also amend or remove the "must not claim a
  verified run" sentence (`protocol.md:302-303`) so it is consistent with
  the shipped cooperation-tier semantics. Behavioral slice: strict TDD;
  draft the exact vocabulary in the issue for owner sign-off before
  implementation (wording matters; the mechanism is decided).
- **Slice 3.2 — Authority polarity (P9). [DONE — PRs #212, #215]**
  Merged 2026-07-25. `control-protocol.md` now states that it is normative
  for *intent*, not for acceptance, and that the codec wins; `AGENTS.md`
  carries a control-protocol sources-of-truth row (and its transcript row is
  retitled, since the addition made the old title ambiguous); the polarity
  is **decision 5** of the prototyping-stage record, listed in its Inputs
  and bound to its Exit criterion, so an agent re-freezing the protocol
  meets the revisit trigger where it matters. The adversarial review
  confirmed the repo-wide sweep found no other inverted statement and noted
  that `control.py`'s own module docstring already agreed with the new
  polarity. One recorded non-action: dated ADRs are not retro-edited, so
  `jsonl-control-transport.md`'s freeze-stale prose belongs to the P8/9.2
  mechanization slice, not here. Original slice text follows.
- **Slice 3.2 — Authority polarity (P9).**
  **Owner decision 2026-07-24: code wins everywhere (Option A) for the
  duration of the prototyping stage.** Amend `control-protocol.md:16-19` to
  drop "the codec is wrong and this document wins" and match AGENTS.md's
  executable-over-prose rule; add `control.py`/`control-protocol.md` to the
  AGENTS.md sources-of-truth table. A doc/codec disagreement is a defect,
  fixed doc-side by default (code-side via a normal TDD slice when the codec
  is genuinely wrong). Record in the change that polarity is revisited at
  the re-freeze boundary, where doc-as-contract for the subject-implemented
  control protocol becomes a defensible choice.

**Acceptance:** no two normative documents state opposite rules for the same
question; owner decision recorded (issue or ADR) for each slice.

### Phase 4 — Deadline coverage for writes (review rec 5) [DONE 2026-07-25]

Slice 4.1 merged as PR #221 (resolves #193); Slice 4.2 merged as PR #222
(resolves #194) after **six** adversarial review rounds. Original slice text
follows for the record.

**Slice 4.2's arc is this handover's best evidence for what the review step
actually buys, and it is not what the earlier phases suggested.** Rounds 1–4
each found the *bound* mis-sized against real measurement: a read-count
budget that aborted a cooperative subject (real ConPTY barely coalesces),
a flat headroom wrong on the chunk axis, then wrong on the frame axis, then
counting frame **cells** where the codec counts UTF-8 **bytes**. Rounds 5
and 6 found no arithmetic wrong at all — both found a *correct* bound
described by a false sentence:

- **Merge order silently invalidated a budget single-sourced from protocol
  ceilings.** Slice 5.1 (#195) merged first and made an epoch's chunks reach
  the transcript as one coalesced string, so they meet the per-string
  ceiling (1 MiB), not only the per-record string sum (2 MiB) the budget was
  derived from. Measured: a plain 80×24 run admitted 1.98× the ceiling and
  the codec rejected the record. **A budget derived from a protocol ceiling
  must be re-derived when the *shape* of the record that ceiling applies to
  changes** — single-sourcing the constant is not enough.
- **The adapter's own test hid it**, because it replicated the codec's
  counting rule over the adapter's *pre*-coalescing observation. Budget
  evidence now goes through the real `TranscriptRecorder` and codec. Rule
  worth generalizing: **do not assert against a replica of a component's
  rules when the component itself can be run.**
- **An untested failure leg is a documentation risk before it is a coverage
  one.** The geometry threshold was published to hosts as "~2.09 million
  cells" — the *byte* figure read as cells, off by 4×, and the same
  cells-vs-bytes class round 4 had already rejected. It survived because
  nothing tested the leg; a test asserting `terminal-cells` would have
  contradicted it immediately. The real threshold is 523,264.
- **A bound checked in the wrong place can be walked around.** The geometry
  check sat inside the read loop, below the early return taken when the
  readiness marker is already buffered — so a `dispatch(Resize(...))` past
  the threshold completed an epoch having consumed zero reads, and the codec
  then rejected the record. Found in round 6, in the commit that had just
  written the sentence asserting this was impossible.
- **Constants pinned by a test that restates them are not pinned.** Three
  separate times a constant survived mutation because the test fed it back
  or straddled its boundary from a distance. Each was closed by measuring
  behavior at the exact boundary instead.

Also merged in this phase's window: the timezone-registry removal (#192,
decision 9.4) as PR #220, and Slice 5.1 (#195) as PR #224.

### Phase 4 — original slice text [superseded]

The critical runtime fix. Findings: **C2**, **R2**. These change adapter
control flow; sequence after Phase 2 merges (they touch the same modules).

- **Slice 4.1 — JSONL writes under the abort deadline (C2).**
  Put every wire write (`_run_epoch` write step `jsonl.py:866-875`, hello
  `:1028-1039`, stop `:1315-1316`; binding write
  `_jsonl_pipe.py:285-296`) under the watchdog so a non-reading subject
  produces a structured deadline failure instead of hanging `dispatch()`
  forever. Likely shape: arm the deadline around the write, or move writes to
  the tracked thread with the same interrupt mechanism reads use — design in
  the issue first; the review does not prescribe a mechanism. Must preserve
  the module's promise ("the only wall-clock input is the mandatory abort
  deadline"). Test: subject that never reads stdin + input large enough to
  exceed the pipe buffer (use a size well above 64 KiB); assert structured
  deadline failure within the deadline. Also fix the same-file minor: write
  failures after a late deadline-timer close must consult `_deadline_closed`
  before classifying `peer-lifecycle` (`jsonl.py:866-875` vs. read path
  `:761-765`).
  For ConPTY conin writes — **owner decision 2026-07-24: fix-first with
  recorded fallback.** The slice implements deadline-covered conin writes
  using the mechanism developed for the JSONL fix; if that proves
  disproportionately invasive in the pywinpty binding, the implementer
  returns with evidence and the slice falls back, by recorded owner
  decision, to an explicit disclosure extending `_conpty.py:40` (writes
  outside the deadline, no backpressure observed on the verified matrix,
  theoretical bound stated).
- **Slice 4.2 — ConPTY per-epoch deadline / budget (R2).**
  `src/termverify/conpty.py:528-558`, `:609-621`: the watchdog re-arms per
  chunk, so a marker-less trickle (1 byte per deadline−ε) starves an epoch
  forever while `chunks` (`:694`) grows unboundedly. Add a per-epoch
  wall-clock deadline or a per-epoch chunk/byte budget (the JSONL adapter's
  ~101-read diagnostic budget, `jsonl.py:784-796`, is the in-repo precedent).
  Test: fake/fixture subject trickling bytes without the readiness marker;
  assert epoch aborts with structured failure and bounded chunk count.

**Acceptance:** with these merged, the review's failure scenarios for C2 and
R2 (non-reading subject; marker-less trickle) each produce a structured
failure within bounded time and memory, demonstrated by tests.

### Phase 5 — Fidelity boundaries: decide, fix, or disclose (review recs 6, 7) [DONE 2026-07-26]

Findings: **R6**, **R4**, **R7**. Each starts with an owner decision recorded
in its issue.

**Slice 5.2's scope grew during Phase 2 (2026-07-25).** Two verified issues
belong to it, both about a reader that cannot be unblocked — the same shape
R4 describes on POSIX, found on Windows: **#213** (`_close_pipes` blocks
indefinitely inside a `finally` when a descendant holds the child's stdout
write end; the job object only unblocks holders that are job *members*) and
**#217** (the `detach()` believed to release the stdin writer without
flushing actually flushes, so the teardown stall it exists to prevent is not
prevented). The `poll`/`select` + self-pipe reader this slice already plans
is the remedy for both; add each as a named acceptance scenario rather than
re-deriving them.

- **Slice 5.1 — ConPTY replay-equivalence story (R6). [DONE — PR #224]**
  Merged 2026-07-25, adversarial review: merge after nits, findings
  applied pre-merge. Coalescing lives at the recorder's single
  observation-payload seam (`_coalesce_output_events`), covering every
  adapter without crossing a record; adapters keep per-read chunks in
  memory. No stored fixture migration was needed: no transcript fixture
  contained `terminal.output` events, and the adapter-level chunk-split
  tests assert on in-memory observations. The Windows repeat-run
  comparison test is the acceptance evidence and additionally pins
  no-adjacent-chunks — the deterministic red without the fix, since
  comparator divergence alone reproduces only intermittently. `feed`
  boundary insensitivity is now an explicit normalizer-port requirement.
  **Owner decision 2026-07-24: recorder-side coalescing (Option A1).**
  Merge adjacent `terminal.output` chunks into one event at record time
  (within an epoch, between structural events), so chunk boundaries — OS
  scheduling noise, not evidence — never reach the transcript. The exact
  comparator and its "no normalizers" decision stay untouched. In-place
  transcript-shape change under prototyping-stage governance; migrate
  existing ConPTY fixtures in the same reviewed change. Acceptance evidence:
  repeat-run comparison over the real ConPTY adapter reaches an equivalent
  verdict (the DirectAdapter byte-identical repeat-run pattern is the
  precedent). If read-boundary detail ever proves useful for native-read
  debugging, it may be exposed as a diagnostic side channel, not as
  transcript events.
- **Slice 5.2 — POSIX containment boundary (R4). [DONE 2026-07-26 — PR #229]**
  Merged after two adversarial rounds, both REJECT. Shape: the POSIX binding
  owns **both** pipes as raw descriptors (wider than the issue's text, and
  what dissolves #217 there rather than describing it away), detached once in
  the constructor, with reads and writes waiting on `poll` over their
  descriptor plus a self-pipe; every close that proceeds signals it before
  terminating anything or touching a descriptor.

  **The red was observed on CI, not locally, and it corrected the story.**
  This dev host is Windows and the path is POSIX-only, so the test was pushed
  first and failed on all three Ubuntu legs with *"the blocked read was never
  woken"* — while `close(force=True)` **returned cleanly**. The
  `_close_pipes`-blocks-inside-a-`finally` shape #213 and #217 describe was
  not reached, because the immediate child had already exited. Worth keeping:
  the defect was a close that reported success and left a thread blocked on a
  descriptor it had just freed, which is worse than the hang that was
  predicted. *Prediction is not evidence even when the fix is right.*

  Lessons from the two rounds, both of a kind this handover keeps recording:

  - **A wake-up without an in-flight handshake trades a hang for silent
    corruption.** Round 1 found the write path had the self-pipe but no
    `_write_in_flight` tracking, so a close concurrent with a write — the
    *designed* path, since the watchdog closes from the timer thread — could
    free the stdin descriptor's number under a live `os.write`. Reads had the
    handshake; copying half a mechanism is worse than copying none, because
    the asymmetry ran toward the quieter failure.
  - **Order the fallible step before the irreversible one.** Round 1's own
    fail-closed spawn leg leaked both descriptors: it detached the wrappers
    and only then called the one operation that can fail (`os.pipe`), so the
    release path — which works through those wrappers — closed nothing, on a
    path whose trigger is descriptor exhaustion. Round 2 caught it.
  - **A test that pins the wrong half passes against the code it was written
    for.** The new write test asserted only that *something* raised, which
    also accepts the `EBADF` the defect itself produces. Assert the type.
  - **`# pragma: no cover` is static, not conditional.** A pragma on a `def`
    excludes that body on *every* platform, so the whole POSIX
    implementation is unratcheted on Linux too — deleting `_write_all`'s body
    would keep the gate green. The round-1 sentence claiming otherwise was
    *less* true than the one it replaced. Filed as **#230**; it is the third
    finding this cycle where a measurement was believed to cover something it
    did not.

  **Still open, deliberately:** #213 and #217 are POSIX-resolved only and were
  reopened/annotated to say so. Windows has no equivalent mechanism —
  `poll`/`select` do not work on anonymous pipe handles — so a pipe-end holder
  outside the job can still stall a teardown there. Also filed: **#228** (the
  ConPTY terminal receipt claims `tier: "os"` for geometries the console
  silently substitutes). Original slice text follows.
- **Slice 5.2 — POSIX containment boundary (R4).**
  **Owner decision 2026-07-24: harden the reader, disclose the survivor
  (Option C).** Two-part disposition splitting the finding at its natural
  seam:
  1. *Fix the wedged reader:* switch the POSIX read path
     (`_jsonl_pipe.py:328-365` reader, `:439-445`, `:597-607` teardown) to
     `poll`/`select` over child stdout plus a self-pipe; forced close writes
     the self-pipe so the reader wakes regardless of who holds the write
     end. Restores "the deadline always produces a structured failure" and
     makes `close(force=True)`'s success truthful. POSIX-only; develop
     against the Ubuntu CI legs; TDD with a double-forking `setsid()`
     fixture subject (CI-only integration test).
  2. *Disclose the surviving orphan:* a `killpg`-escaped descendant cannot
     be portably reaped (cgroups/subreaper are out of scope — rejected as
     horizontal platform machinery); record a containment boundary note à
     la the ConPTY assignment-window disclosure, and reword the "identical
     observable outcomes on every platform" claim (`jsonl.py:208-215`) to
     identical failure classification with a disclosed platform difference
     in containment strength.
- **Slice 5.3 — ConPTY decode boundary (R7). [DONE 2026-07-26 — PR #234]**
  Merged with #232 (the defect the slice exposed) after two adversarial
  rounds, **both Critical**, and with #233's separate marker-protocol review
  folded in. The mechanism owner touchpoint resolved toward the larger
  option: pywinpty 3.0.5 exposes no bytes-returning read and no route to the
  conout handle, and the loss is unrepairable above it, so TermVerify now
  owns `CreatePseudoConsole` and the `STARTUPINFOEX` spawn and decodes
  incrementally. The measured red: a 200,000-character `U+65E5` burst
  produced **29 replacement characters across 21 reads and lost 12
  characters outright**. `docs/agent/design/terminal-adapter-dependency-decision.md`
  was amended in the same change (pywinpty is off the read side).

  Both review rounds were found by the reviewer *running* the code, and both
  were in the marker scanner rather than the decoder: round 1, a resume past
  a rejected candidate's *end*, so a stray prefix in subject output swallowed
  the next real marker; round 2, the fix for it off by `len(terminator) - 1`,
  losing any 64-character token whose `>>` straddled two reads. Follow-ups
  filed and since closed: **#233** (owner-requested fresh review of the
  marker protocol — its fixes landed in this PR by fast-forward, so #237 was
  auto-marked merged), **#235** (the job-assignment window, now closable
  because we own `CreateProcessW`), **#236** (the coverage-omit rationale had
  gone stale — the binding tripled in size and both rounds' defects were in
  unmeasured code).

  Original slice text follows.
- **Slice 5.3 — ConPTY decode boundary (R7).**
  **Owner decision 2026-07-24: eliminate the bug class now (Option C).**
  Rebuild the ConPTY read path on raw bytes with incremental UTF-8 decoding
  in TermVerify's own binding, so a native read landing mid-codepoint heals
  across chunks instead of embedding irreparable U+FFFD in evidence.
  Design-first slice: pywinpty's `PTY.read` returns pre-decoded `str`
  (`_conpty.py:384`), so the issue must first evaluate how to obtain raw
  conout bytes — a pywinpty bytes-capable surface if one exists, or a direct
  ConPTY (`CreatePseudoConsole`) ctypes binding with our own `ReadFile`
  loop. The latter effectively replaces pywinpty on the read side and must
  be reconciled with
  `docs/agent/design/terminal-adapter-dependency-decision.md` in the same
  change. Acceptance evidence: the volume multi-byte integration test
  (large non-ASCII frames under load, repeated) passes with byte-exact
  evidence and demonstrably healed split codepoints (unit-test the
  incremental decoder on adversarial split points). Include the
  argv[0]-with-spaces integration test (`_conpty.py:329-335` minor) in this
  slice, since it exercises the same spawn surface.

**Acceptance:** each finding has a recorded decision and its chosen
disposition implemented; no undisclosed fidelity gap remains.

### Phase 6 — Public API exports (review rec 8) [DONE 2026-07-29]

**#198 merged as PR #254.** The codec (`parse_transcript`,
`serialize_transcript`, `TranscriptValidationError`) and the registry entry
points (`KEY_NAMES`, `is_key_chord`, `encode_key_chord`) are exported; the
registry names are public while their defining modules stay private, which is
the one deliberate exception to the guide's interchangeable-import rule.

**#218 merged as PR #255**, completing the phase. The in-process vocabulary
now matches the wire: `ConstraintPorts.enforce_*` → `apply_*`,
`EnforcedConstraints` → `AppliedConstraints`, `.enforced` → `.applied`,
`UnenforcedConstraintPorts` → `ApplyNothingConstraintPorts`. The owner
decided to include the `enforce_*` ports — #218's own list stopped at the
data types, which would have moved the seam rather than closed it — and chose
`ApplyNothingConstraintPorts` over the mechanical `Unapplied…`. The
enforcement-**tier** vocabulary (`EnforcementReceipt`, `EnforcementTier`,
`ENFORCEMENT_TIERS`, `termverify.enforcement-tier/v1`) and the
`constraint-not-enforced` wire code deliberately keep their names: they name
the axis of claim strength, on which `delivered` honestly means nothing is
enforced. A test pins that so the exception cannot decay into a
search-and-replace.

Original slice text follows for the record.

Finding: minor `__init__.py` bullet. Export the authoritative codec
(`parse_transcript`, `serialize_transcript`, `TranscriptValidationError`) and
the documented closed registries (`KEY_NAMES`, `is_key_chord`,
`encode_key_chord`) from the public `termverify` package so third-party
adapter authors need no underscore imports. **`TIMEZONE_NAMES` is not on
that list:** decision 9.4 removed the registry it named, so exporting it is
impossible (issue #192, merged 2026-07-25). Public-API change: needs tests
asserting the exports, doc updates (adapter-author guide, README API
mentions), and a changelog fragment. Do it pre-0.2.0 while cheap.

**Also in this phase's scope: #218** — the in-process API still calls its
receipts `enforced` after the wire became `applied`. Renaming existing public
names is not something this phase's original text covered, hence the issue.
**The symbol list #218 inherited from the review was stale**: `AdapterResult`
and `StartOk` never existed in the codebase, and what the issue called
`Started.enforced` is `Started.constraints`. Resolved by PR #255; the
authoritative record of what was renamed is now the migration table in
`CHANGELOG.md`, not prose here.

**Acceptance:** documented names importable from `termverify`; no doc tells
users to import private paths.

### Phase 7 — README capability truth (review rec 9) [DONE 2026-07-29]

**#199 merged as PR #256.** One deviation from the slice text below, which
said "one **new** vision document": `docs/knowledge/product-vision.md` already
existed, so it was extended rather than duplicated — creating a second vision
doc would have been the exact drift P5 is about. Its own opening sentence
carried the same overpromise ("supplies … property testing, and CI artifacts")
and was corrected in the same change. The README's "Planned architecture"
diagram moved there rather than being deleted, since it restated the
aspirational scope a second time in the same file.

`tests/test_readme_capability_truth.py` gives the split a ratchet — the
capability section must parse as a pinned intro plus top-level `- ` bullets
and nothing else, every module the README names must import, the vision doc
must be linked exactly once, and no planned capability from the vision
document's headings may reappear in the current-capability section. That is a
narrow, README-specific check on purpose; the general prose-status validator
stays with Slice 8.4 (#203).

Two adversarial review rounds ran on the PR. Round 1's findings were fixed
in-branch. Round 2's surviving Critical/Important findings were, with two
exceptions, **pre-existing P5-type defects in documents #199 never scoped**
(`architecture.md`, `verification-model.md`, `agent-workflow.md`,
`development.md`) — each round found more of them, in more files. **Owner
decision 2026-07-29: #199 stays at its written scope; the repo-wide
capability-truth audit is #257.** The two in-scope findings were fixed
in-branch: the ratchet's parser was weaker than its docstring claimed
(review broke it five of six ways; it now enforces the structural contract
above and its docstring states exactly which shapes remain uncatchable and
why they belong to #203 and review), and the `[planned]` marker this PR
added to the agent-workflow evidence hierarchy read as "avoid property
checks", contradicting `AGENTS.md` and the suite's own nine `@given` sites —
it now marks missing TermVerify machinery without demoting the layer.

A focused round 3 on that fix then broke the strengthened parser twice more:
a single leading space (or a no-break space) let prose between bullets be
absorbed as bullet continuation, and substring heading-anchoring let a `###`
lookalike heading re-point every check — deferred-term guards included — at
a decoy body. Both closed in-branch with the shapes pinned as tests:
continuation lines now require the markdown content column, exotic
whitespace counts as content, and the section heading must match a whole
line exactly once. Round 4 (on those fixes) returned no Critical; its
findings — duplicate headings rendering identically to the capability
title while differing at the byte level, an NBSP-led marker-shaped line
routed as a bullet against the parser comment's claim, a pin-coverage gap
on the space-only indent rule, zero-width splits defeating the guard
terms — were closed the same way: heading titles and guard text now
compare *folded* (format characters stripped, whitespace collapsed), with
ATX and single-line setext headings recognized at CommonMark's legal
indents, every shape pinned. A round-5 replay of all shapes from rounds
2–4 came back clean; its one residual (the new heading scanner missing
CommonMark's 0–3-space indent, plus an overclaiming docstring) was fixed,
and the genuinely unreachable shapes — multi-line setext titles, raw-HTML
headings, homoglyphs — moved to the docstring's disclosed-uncatchable
list. Rounds ended there: every demonstrated shape is either caught by a
pinned test or explicitly disclosed. The standing lesson: a ratchet's
parser is itself an attack surface, and each fix earns its own focused
review round.

Original slice text follows for the record.

Finding: **P5**. **Owner decision 2026-07-24: current capabilities only in
the README, plus one link to a single-sourced vision document (Option C).**
Rewrite `README.md:11-18` to list only what exists (codec/validator, adapter
contract, direct runtime, ConPTY adapter + VT normalizer, cooperation ports,
recorder, exact comparator, replay, JSONL adapter). Move the aspirational
scope (property/state-machine testing support, reviewed golden snapshots,
differential tests, failure minimization / CI artifacts) to one new vision
document under `docs/knowledge/` (OKF frontmatter required), stated once and
linked from the README — this deliberately applies the P8/9.2
single-sourcing remedy. The vision doc may state sequencing honestly (e.g.,
"after a POSIX adapter and an end-to-end example"). Coordinate with
Slice 1.1 (same file; Slice 1.1 also adds the prototyping-stage banner).

**Acceptance:** every present-tense capability claim in README corresponds to
code in `src/`.

### Phase 8 — Minor-findings sweep [TODO]

Group the remaining minors into four thematic slices. Each item's disposition
is fix, disclose, or a recorded won't-fix; none silently dropped. See review
§4 for full citations.

- **Slice 8.1 — Runtime/adapter minors:** concurrent `read_line` misclassified
  as `peer-lifecycle` + transient `_closed = True` window
  (`_jsonl_pipe.py:315-318`, `:385-427`); dead handshake branch and vestigial
  `if write is not None` (`jsonl.py:798-807`, `:747-749`, `:866`); VT
  fail-closed rejections of secondary-DA and DEL (`vt.py:212-227`,
  `:159-162`) — no-op or disclose; `cancel_io` 30 s leak disclosure
  (`_conpty.py:509-521`); unconditional 2 s reap stall on failed runs
  (`_jsonl_pipe.py:551-574`).
- **Slice 8.2 — Transcript-core minors:** compat-normalization budget margin
  breaks parse→serialize round-trip at exactly `_MAX_JSON_VALUES`
  (`transcript.py:117-142,306`); truncate attacker-controlled duplicate-key
  interpolation (`transcript.py:321`); add record-index/member context to
  semantic rejections (`transcript.py:326-351` etc.) — this one is a real
  usability defect, size it honestly; deduplicate the input-member closure
  tables and manual-clock chain or add a drift test
  (`transcript.py:56-63` etc.); docstring caveat for the RFC 8785
  integral-float / `_json_equivalent` asymmetry (`transcript.py:1092-1106`).
- **Slice 8.3 — Tests/CI minors** (two items **already done** out of order,
  because Phase 5 made them urgent: the `_conpty.py` supplemental coverage
  landed as PR #240 (#236) and the per-OS pragma overlays as PR #241 (#230)
  — see checkpoint e)**:** ~~per-OS supplemental (non-gating) coverage
  for `_conpty.py` (`pyproject.toml:67`)~~; direct invalid-UTF-8 fixture for
  `_parse_line`'s `UnicodeDecodeError` leg (`transcript.py:301`); add
  `timeout-minutes` to quality/package/docs CI jobs; review the race-window
  arrangement sleeps (`test_conpty_binding.py:412,836`,
  `test_jsonl_binding.py:291`) — document or strengthen; Hypothesis seeding
  — **owner decision 2026-07-24: derandomized CI profile, unseeded local**
  (register profiles in `conftest.py`; CI runs `derandomize=True` for
  reproducible builds, local runs stay exploratory); add `conftest.py` or
  `tests/__init__.py` for cross-test-module imports; migrate private-field
  arrangement in `test_jsonl_coverage.py:382,398,497` toward
  public-protocol arrangement where feasible; `scripts/` coverage — **owner
  decision 2026-07-24: include `scripts/` in coverage measurement** (the
  governance validators join the ratchet; one-time baseline adjustment in
  the same change).
- **Slice 8.4 — Release/process minors:** **owner decision 2026-07-24:
  manual `.dev0` marker scheme.** Bump `main` to `0.2.0.dev0` now; add a
  post-release checklist step ("bump to next-version`.dev0`") and make the
  release commit strip the marker (`X.Y.Z.dev0` → `X.Y.Z`), which also
  fixes the degenerate same-version bump-commit problem — the release
  checklist must be exercisable as written. Optionally add a tiny validator
  ("version on `main` must carry `.dev`") under the 9.2 mechanization
  pattern. Also: state in `release.md` whether the release gate waits on
  the Security workflow (`release.md` vs. `development.md:27-28`);
  termverify.dev hijack-surface note — record the monitoring/
  registration-lapse risk and mitigation posture in the schema-distribution
  ADR.

**Acceptance:** each §4 review bullet has a disposition traceable from its
slice PR or a recorded decision.

### Phase 9 — Strategic owner decisions (review recs 10–12) [TODO]

Not implementation phases — decision requests. File one issue each; outcomes
are recorded owner decisions under `docs/agent/design/`; any resulting
implementation gets its own future handover/boundary, not this one.

- **9.1 — Vertical before horizontal (P4, P6, P7 / rec 10): [DONE] resolved
  2026-07-24.** The owner adopted vertical-next, driven by real subjects:
  the initiative after (or interleaved with) remediation is a POSIX PTY
  adapter plus one `examples/` end-to-end walkthrough using a minimal
  synthetic TUI (stable documentation), followed immediately by wiring
  drei (`C:\Users\tc\Programming\Python\Projects\drei`) and GlyphWright
  (`C:\Users\tc\Programming\Python\Projects\glyphwright`) as the real
  design-driver verticals (repairing the drifted GlyphWright conformance
  fixture in the process). Moratorium on new horizontal specification
  (registries, sidecar formats, mirror infrastructure, protocol vocabulary
  not demanded by a vertical) until the POSIX adapter and example exist.
  This initiative gets its own design/boundary document and handover when
  started; it is outside this remediation handover's completion criteria.
- **9.2 — Mechanize status-bearing prose (P8 / rec 11): [DONE] resolved
  2026-07-24.** The owner adopted the minimal drift-driven hybrid:
  single-source where restructuring is natural (release status stated
  authoritatively in `CHANGELOG.md`, README/SECURITY carry one sentence or
  a link; roadmap single-sourced in the Slice 7 vision doc), and mechanize
  *only fact classes that have already drifted*, as a small script in the
  existing `scripts/` validator pattern: (1) the version on `main` carries
  `.dev` (pairs with the Slice 8.4 scheme); (2) ADR status lines use the
  allowed status vocabulary; (3) registry counts stated in prose match the
  code's registries. The validator grows only when a new fact class
  actually drifts — no speculative prose-checking framework (that would
  violate the 9.1 moratorium). Implement as a Phase 8 slice (fold into or
  alongside Slice 8.4).
- **9.3 — Freeze-posture revision (P3 / rec 12): [DONE] resolved
  2026-07-24.** The owner suspended the freeze entirely and declared the
  prototyping stage; see
  `docs/agent/design/prototyping-stage-protocol-governance.md`. Rec 12's
  "frozen for consumers" tier idea is recorded there as input to the future
  re-freeze design.
- **9.4 — Timezone-registry disposition (P4): [DONE] resolved 2026-07-24.**
  The owner chose removal: delete the `termverify.timezone/v1` registry,
  its generator, and its tests; the timezone constraint request becomes a
  plain string the adapter either enforces (`UTC`) or reports unsupported.
  In-place protocol change under prototyping-stage governance; update
  protocol.md and migrate fixtures in the same reviewed change; note in the
  change that git history preserves the registry, and any future
  reintroduction (when a vertical demands non-UTC zones) is a fresh design
  with a registry-version selector. Implement as a Phase 3-adjacent slice
  (protocol scope; can run as its own worktree). This also removes P4's
  affected `TIMEZONE_NAMES` from the Phase 6 export list — Phase 6 exports
  only the registries that survive.

**Acceptance:** four recorded decisions; this handover updated with pointers.

## 4. Current status

- **Completed (2026-07-24, uncommitted in working tree — commit with the
  first docs PR):**
  - Prototyping-stage governance decision recorded:
    `docs/agent/design/prototyping-stage-protocol-governance.md` (new),
    `docs/knowledge/protocol.md` "Compatibility and evolution" rewritten to
    state the freeze suspension, `AGENTS.md` protocol row updated, changelog
    fragment `changelog.d/+prototyping-stage-governance.changed.md` added
    (rename to the tracking-issue number in Phase 0). This resolves review
    finding P3's statement requirement and Phase 9.3, and unblocks Slices
    2.3, 3.1, and 9.4.
  - The review document exists at
    `docs/agent/reviews/adversarial-review-2026-07-24.md` (verify it is
    committed as part of Phase 0/1). `main` was at `8f33e6c` at review time.
- **Owner decision walkthrough completed 2026-07-24.** All up-front
  decisions are resolved and recorded inline in their slices: prototyping-
  stage governance (ADR; resolves P3/9.3, unblocks 2.3/3.1/9.4), P9
  polarity → code wins everywhere (3.2), ConPTY conin writes → fix-first
  with recorded fallback (4.1), R6 → recorder-side coalescing (5.1), R4 →
  harden reader + disclose survivor (5.2), R7 → eliminate via raw-byte
  read path with incremental decoding (5.3), P5 README → current-only +
  linked vision doc (7), versioning → manual `.dev0` marker (8.4),
  Hypothesis → derandomized CI profile (8.3), `scripts/` coverage →
  include (8.3), 9.1 → vertical-next driven by drei/GlyphWright with
  horizontal moratorium, 9.2 → minimal drift-driven prose mechanization,
  9.4 → remove the timezone registry. The PR-177 root-file minor was
  already resolved by PR #183.
- **Phase 0 complete (2026-07-24):** issues #184–#204 filed under the
  `review-2026-07-24` label (mapping table in Phase 0 above).
- **Checkpoint 2026-07-29f (sixth session).**
  - **Merged:** #198 (PR #254) — the authoritative codec and the key
    registries' entry points are now exported from `termverify`, so the
    non-authoritative schema aid is no longer the easier import and adapter
    authors need no underscore path. Then #218 (PR #255) — the in-process
    `enforced` vocabulary became `applied`, matching the wire. **Phase 6 is
    complete; Phases 1–6 are done.**
  - **Two owner decisions on #218, taken before implementing.** The issue's
    scope stopped at the data types (`EnforcedConstraints`, the `.enforced`
    fields), which would have left `ports.enforce_seed()` returning something
    stored in `AppliedConstraints` — moving the seam, not closing it. Owner
    chose to rename the seven `ConstraintPorts.enforce_*` ports too, breaking
    every external implementation including GlyphWright's, on the grounds
    that prototyping stage owes no shim and deferring costs the same break
    plus a second migration note. Owner also chose
    `ApplyNothingConstraintPorts` over the mechanical `Unapplied…`. The
    enforcement-*tier* names and `constraint-not-enforced` stay, pinned by a
    test: they name the axis of claim strength, on which `delivered` honestly
    means nothing is enforced.
  - **Two scripted-rename hazards worth carrying.** A blanket `sed` rewrote
    the string literals in `tests/test_public_surface.py` that assert the
    *old* names are gone, turning the guard into a tautology — the one place
    in the repo where a correct global rename is wrong. And `ruff --fix`
    re-sorts imports but not `__all__` literals (`RUF022` is not enabled and
    its order would fight the surface test's plain `sorted()`), so three
    `__all__` lists needed hand-sorting. Both were caught before any green
    run, but only because the surface tests exist — **and two review rounds
    on #255 then found those tests were themselves weaker than they read.**
    Round 1: the sortedness pin covered `termverify.__all__` alone, and the
    retired-name check never looked at `termverify.conpty`, so its
    `UnenforcedConstraintPorts` entry was a dead assertion. Round 2: the
    widened version still asserted `ApplyNothingConstraintPorts` only by name
    in `__all__`, so renaming a method back on the shipped class left all 14
    tests green, and most of the cross-product it generated could never fail.
    The final version splits retired *members* from retired *module names*,
    checks each where it could actually survive, and derives the port list
    from `CONSTRAINT_NAMES` instead of hand-copying it. Every assertion was
    then mutation-tested — five deliberate half-renames, all caught.
    A test that pins a rename deserves the same suspicion as the rename.
  - **Phase 7 (#199) followed as PR #256**, so **Phases 1–7 are complete**
    and only Phase 8's minors sweep remains inside this handover. The slice
    text asked for "one new vision document"; `docs/knowledge/product-vision.md`
    already existed, so it was extended instead — writing a second vision doc
    to satisfy a single-sourcing remedy would have been self-defeating, and
    that document's own opening sentence carried the same P5 overpromise it
    was being made the home for. Read the phase before assuming its
    instructions still describe the tree.
  - **The standing lesson held again, this time against this handover
    itself.** Two review rounds on PR #254 returned no Critical finding and
    nothing wrong with *which* names were exported, their identity, or the
    `__all__` curation. What they returned — 9 Important and 17 Minor across
    the two rounds — was dominated by untrue or unrepaired **statements**:
    the stale #218 symbol list #216 left behind (`AdapterResult` and
    `StartOk` never existed; corrected in place in the Phase 3 deferral
    bullet); a compatibility promise still extending to module paths
    the same page had just declared private; a docstring calling every
    `KEY_MODIFIED_BASES` entry an "ordinary printable character" when
    `Space` is in that tuple; a test named `..._round_trips` that never
    round-tripped; and — the sharpest one — a first draft of *this very
    checkpoint* that claimed the review "found no defect in the exported
    surface" while the same paragraph listed a defect in exported
    `encode_key_chord`, and miscounted the findings it was recording.
    One genuine code fix came out of it: `encode_key_chord` was annotated
    `Sequence[str]` while accepting only exact `list`/`tuple`, so `str`
    itself type-checked. Sixth instance; the pattern has not broken, and it
    now demonstrably applies to the records this project writes about its
    own reviews.
  - **One flake observed, not fixed:** `test_conpty_binding.py::
    test_a_containment_setup_failure_leaves_no_suspended_orphan[handle-open]`
    failed once in a pre-push run with `OpenProcess` →
    `ERROR_INVALID_PARAMETER` (the PID was fully reaped before the test
    opened its handle), then passed 10 isolated reruns and a full-file run
    on unmodified sources. Slice 8.3's race-window item names the
    arrangement *sleeps*, and this failure is in `_assert_os_terminated`,
    which has none — same slice, adjacent defect. Recorded on #202 with the
    traceback; not fixed here.
- **Checkpoint 2026-07-28e (fifth session).**
  - **Merged:** Slice 5.3 with #232 (PR #234, closes #197 and #232, with
    #233's review fixes folded in); #235 (PR #239); #236 (PR #240); #230
    (PR #241); #228 (PR #243). **Phase 5 is complete — all of Phases 1–5
    are done.** Working state clean: no open feature PRs, no worktrees, no
    local branches. Suite green on `main` @ `0509afe`: 1859 passed, 3
    skipped (the three skips are POSIX containment mechanisms).
  - **0.1.1 was released (PR #242, tag `v0.1.1` @ `d8dbaf2`, 2026-07-27).**
    The gated pipeline ran end to end — CI-green wait, tag, build and
    attest, PyPI via OIDC, GitHub release — folding 35 changelog fragments.
    This is the first release the checklist drove without manual repair.
    Two doc slices followed: #244 (PR #246, the volatile stage status left
    the Tier-1 `AGENTS.md` table) and #245 (PR #247, the project
    description is single-sourced from `README.md`).
  - **Part of Phase 8 was executed early, by necessity.** #236 and #230 are
    Slice 8.3 items that the Phase 5 work made urgent — the ConPTY binding
    tripled in size while excluded from coverage, and the bare pragmas hid
    both platforms' native legs. `_conpty.py` now has a supplemental
    non-gating Windows-leg measurement (82.34% at the time) and
    `_jsonl_pipe.py`'s 21 pragmas became per-OS markers with per-OS
    overlays, so each leg is ratcheted where it actually runs. Slice 8.3
    keeps its remaining items; deduct these two when sizing it.
  - **New issue: #238** — the JSONL transport still has the Windows
    job-assignment window that #235 closed for ConPTY. It cannot be closed
    the same way: `subprocess.Popen` accepts `CREATE_SUSPENDED` but never
    exposes the main thread handle `ResumeThread` needs, so the choice is
    owning the Windows spawn (the #197 pattern) or recording the
    disclosure. It joins the reopened Windows halves of **#213/#217** —
    three findings that are all one question, *does TermVerify own the
    Windows spawn and its pipe handles in the JSONL transport too*, and
    they should be sized as one slice rather than three.
  - **The standing lesson holds at a fifth instance.** #228 took five
    commits and three of them corrected sentences, not code: the kill-band
    claims were stronger than the measurements, and the last commit exists
    only to reword "prove" as "measure" throughout. The pattern this
    handover has recorded since checkpoint b — reviews above nit level find
    *false statements* — did not break.
- **Checkpoint 2026-07-26d (fourth session).**
  - **Merged:** the Slice 4.2 follow-up (PR #227, closes #226) and Slice 5.2
    (PR #229, closes #196). **Phase 5 has only 5.3 (#197) left.** Working
    state clean: no open PRs, no worktrees, no local branches.
  - **A seventh review of the already-merged Slice 4.2 found a MAJOR**, which
    is the checkpoint's main process result. #194's geometry gate reserved
    four bytes per cell and refused an epoch when nothing was left for
    output — a *cell* model that cannot see the ceiling the codec charges
    per **collection**: a frame is one item per row, capped at 16,384, so a
    10-column 20,000-row terminal is 200,000 cells (a third of the 523,264
    threshold) and every record it produced was rejected. Three further
    rounds followed on #227 itself, and the arc is worth carrying forward:
    - **Round 8** killed the fix's own rationale. It checked rows only and
      argued columns needed none because a 262,144-column frame line is out
      of reach of a 16-bit `COORD`. `PTY()` range-checks nothing — 262,145x1
      and 1,048,577x1 both create a pseudoconsole and spawn. The remedy was
      to stop arguing and check all three axes: **a check costing one
      comparison is not worth an argument about what a host can request.**
    - **Round 9** found that the defense-in-depth gate added in round 8 had
      *destroyed the test* for the original gate's placement. Both gates
      raise identically, so moving the check into the read loop — round 6's
      defect once more — passed the entire suite. **A redundant guard can
      silently un-pin the guard it backs up.**
    - **Round 10** accepted with nits. Net: four rounds, three of them
      turning on sentences rather than arithmetic.
  - **New issues:** **#228** (ConPTY receipt claims `tier: "os"` for
    geometries the console silently truncates — a claim-strength defect of
    the same family as #190), **#230** (`# pragma: no cover` on platform legs
    excludes them everywhere, so both platforms' native legs are
    unratcheted). **#213 and #217 were reopened**, POSIX-resolved only.
  - **The standing lesson, now with a fourth instance.** Every round above
    that found something above nit level found a *false statement*, not a
    broken test — and in three separate cases the fix for one round's false
    sentence authored the next round's. When implementing: write no sentence
    whose mechanism you have not just run. When reviewing: run the claim.
- **Checkpoint 2026-07-25c (third session).**
  - **Merged:** timezone-registry removal (PR #220, closes #192); Slice 4.1
    (PR #221, closes #193); Slice 5.1 (PR #224, closes #195); Slice 4.2
    (PR #222, closes #194). **Phases 1–4 are complete**, and Phase 5 has
    5.2 (#196) and 5.3 (#197) left. Working state clean: no open PRs, no
    outstanding worktrees or feature branches.
  - **Closed without merging:** PR #223, an earlier #195 implementation
    superseded by #224. Its worktree and branch are removed.
  - **The Slice 4.2 lessons are recorded in Phase 4 above, not here**,
    because they are about how budgets and their prose drift rather than
    about session state. The short form: a budget single-sourced from a
    protocol ceiling still breaks when the record's *shape* changes; a test
    that replicates a component's rules will share that component's blind
    spot; an untested failure leg drifts in prose before it drifts in code;
    and a constant is not pinned by a test that restates it.
  - **Process note that worked:** the review gated the merge this time, for
    all six rounds. Rounds 5 and 6 each found a defect that a green gate,
    green CI, and 100% branch coverage on the changed module did not —
    including one bound that a control-flow branch could walk around
    entirely. The cost was real (six rounds for one unbounded loop) and so
    was the return.
- **Checkpoint 2026-07-25b (second autonomous session).**
  - **Merged:** Slice 2.2 (PR #211, closes #188) and its review follow-up
    (PR #214, two review rounds); Slice 3.2 (PR #212, closes #191) and its
    review follow-up (PR #215); Slice 3.1 (PR #216, closes #190).
    **Phases 1 and 2 are complete; Phase 3 has only the timezone-registry
    removal (#192) left.** Working state clean: no open PRs, no outstanding
    worktrees or feature branches.
  - **New issues filed, all from review findings that were out of the
    reviewed slices' scope:**
    - **#213** — `_close_pipes` can deadlock behind a read blocked on a
      descendant-held pipe, verified against unmodified shipped code; the
      Windows twin of finding **R4**. Fold into Slice 5.2 (#196) as a named
      acceptance scenario. Its Windows exposure is narrowed, not removed, by
      PR #214: containment only unblocks a write-end holder that is a job
      *member*.
    - **#217** — the buffered-writer `detach()` used to "release without
      flushing" actually flushes, so the teardown stall it exists to prevent
      is not prevented. Same lines as #213; resolve together.
    - **#218** — the in-process API still calls its receipts `enforced`
      after the wire became `applied`; belongs in Phase 6, which as written
      covers only adding exports.
  - **Process lesson, recorded because it cost real defects.** Two PRs were
    merged through the GitHub UI while their adversarial reviews were still
    running, and both reviews then found substantive problems in
    already-merged code — including a behavioral regression on `main` (see
    Slice 2.2). **The review must gate the merge, not trail it.** Where a
    merge has already happened, the follow-up PR must reference the original
    issue and the review's finding numbers so the trail stays
    reconstructable.
  - **Reviews earn their cost by attacking claims, not just code.** Across
    three rounds this session, every finding above nit level was a *false or
    unsupported statement* in a docstring, changelog fragment, or knowledge
    page — not a broken test. Two were impossible on their face once
    checked against the OS (a job sweeping members it can never have) and
    one was a stronger overstatement than the finding being remediated. When
    reviewing, run the claim, not only the code; when implementing, write no
    guarantee whose mechanism cannot be named.
  - **Second lesson, cheap to avoid:** editing tracked files with Python's
    `pathlib.write_text` on Windows rewrites LF as CRLF, which silently
    breaks the transcript fixtures (the protocol requires LF) even though
    `.gitattributes` normalizes on commit. Use binary reads/writes for bulk
    edits, and check for `\r\n` in every touched file before running tests.
- **Checkpoint 2026-07-25 (first autonomous session, paused by owner request):**
  - **Merged:** governance docs (PR #205, closes #184); Slice 1.1
    (PR #206, closes #185); Slice 1.2 (PR #207, closes #186); Slice 2.1
    (PR #208, closes #187 — three-round adversarial review, round 1
    caught a real regression in the first implementation); Slice 2.3
    (PR #209, closes #189 — review ACCEPT WITH NITS, nits applied).
    Phase 1 is complete; Phase 2 is two-thirds complete.
  - **Working state is clean:** primary checkout on `main`, no
    outstanding worktrees or local branches, all merged branches
    deleted and pruned.
  - **Next work item when the loop resumes: Slice 2.2 (#188)** — design
    settled (see Phase 2 note), then Phases 3–8 in handover order.
  - Process note for future sessions: every PR must be up to date with
    `main` before merge (branch-protection), so merge strictly
    sequentially and rebase the next branch after each merge; run
    fresh-context adversarial reviews for behavioral slices — round 1
    of the Slice 2.1 review rejected a defect that all local tests had
    missed, which is exactly the evidence the loop exists to produce.
- **Remaining at-issue-time owner touchpoints (not up-front blockers):**
  - Slice 3.1: sign-off on the exact replacement wire vocabulary drafted in
    the issue.
  - Slice 4.1: sign-off only if the ConPTY fallback-to-disclosure is
    invoked (requires implementer evidence).
  - Slice 5.3: sign-off on the raw-byte mechanism chosen by the design step
    (pywinpty surface vs. direct ConPTY binding), since it may amend the
    terminal-adapter dependency decision.
- **Tests:** full suite green on `main` @ `8f33e6c` per the review; no
  remediation tests exist yet.

## 5. Next steps

1. ~~Phase 0: file the issues~~ **done 2026-07-24** — #184–#204.
2. ~~Phase 1 (Slices 1.1, 1.2)~~ **done 2026-07-25** — PRs #206, #207.
3. ~~Slices 2.1 and 2.3~~ **done 2026-07-25** — PRs #208, #209.
4. ~~Slice 2.2 (#188)~~ **done 2026-07-25** — PR #211 plus review
   follow-up #214.
5. ~~Slices 3.2 (#191) and 3.1 (#190)~~ **done 2026-07-25** — PRs #212 and
   #215; PR #216.
6. ~~Timezone-registry removal (#192), Slice 4.1 (#193), Slice 5.1 (#195),
   Slice 4.2 (#194)~~ **all done 2026-07-25** — PRs #220, #221, #224, #222.
   **Phases 1–4 are complete.**
7. ~~Slice 5.2 (#196)~~ **done 2026-07-26** — PR #229, plus the Slice 4.2
   follow-up PR #227 (#226) that a round-7 review of the merged #194 produced.
8. ~~Slice 5.3 (#197)~~ **done 2026-07-26** — PR #234, together with #232 and
   #233; then #235 (PR #239), #236 (PR #240), #230 (PR #241) and #228
   (PR #243). **Phase 5 is complete**, and 0.1.1 shipped (PR #242).
9. ~~Phase 6 (#198 and #218)~~ **done 2026-07-29** — PRs #254 and #255.
   #254 exported the authoritative codec and the key registries' entry
   points; #255 renamed the in-process `enforced` vocabulary to `applied`,
   including the `ConstraintPorts.enforce_*` ports by owner decision, and
   kept the enforcement-*tier* names and the `constraint-not-enforced` wire
   code by the same decision. **Phase 6 is complete.**

   Two method notes worth carrying, both from #255's sweep. A blanket `sed`
   silently rewrote the string literals in `tests/test_public_surface.py`
   that assert the *old* names are gone, turning the guard into a tautology —
   the one place in the repo where a correct global rename is wrong. And
   `ruff --fix` re-sorts imports but **not** `__all__` literals: `RUF022` is
   not enabled, and its isort-style order differs from the plain `sorted()`
   the surface test asserts, so enabling it would fight that test. Only
   `termverify.__all__` was covered when the sweep ran; the review of #255
   pointed out that `adapter`/`conpty`/`direct` had no net at all, and the
   test now covers all four. A scripted rename needs both checks.

10. ~~Phase 7 (#199)~~ **done 2026-07-29** — PR #256. The README lists only
    implemented capabilities, each naming its module;
    `docs/knowledge/product-vision.md` (which already existed, and was
    extended rather than duplicated) is the single source for planned scope.

11. **Resume with Phase 8 (#200–#203)**, minus the two 8.3 items #240/#241
    already executed — see checkpoint e, and deduct them when sizing 8.3.
    Note #203 owns the general prose-status validator; #199 deliberately
    added only a README-specific check, so that scope is untouched. The
    *manual* repo-wide capability-truth audit that PR #256's review rounds
    surfaced is #257 (outside this handover); doing it before #203 gives the
    validator a true baseline to ratchet.

    **Give the Windows containment findings one home.** #238 (JSONL spawn
    keeps the job-assignment window) and the reopened Windows halves of
    #213/#217 are the same question asked three times: whether the JSONL
    transport owns its Windows spawn and pipe handles the way `_conpty.py`
    now does. Size them as one slice with a recorded owner decision on
    own-the-spawn versus disclose, not as three minors. They are no longer
    Phase 5 work.

    Housekeeping when convenient: five dependabot PRs are open (#248–#252);
    only the `astral-sh/setup-uv` 8→9 major bump needs reading before merge.

Superseded next-step detail from the previous checkpoint, kept because the
file survey is still accurate:

6. ~~**Resume with the timezone-registry removal (#192, decision 9.4)**~~ in a
   fresh sibling worktree from a `main` containing #216. Scope surveyed and
   small: `src/termverify/_timezone_v1.py` (374 lines) and
   `scripts/generate_timezone_registry.py` are deleted with
   `tests/test_timezone_registry_generation.py`; the three call sites are
   `adapter.py:286`, `control.py:361`, and `transcript.py:508`
   (`is_timezone_name`); `tests/test_internal_v1.py` carries the registry
   tests; the packaged schema's `timezone` `$comment` names the registry and
   must change with it (schema bytes are mirrored from `main`, so the
   publication follows automatically). The constraint request becomes a
   plain non-empty string that an adapter either enforces as `UTC` or
   reports unsupported — note that this **widens acceptance**: a transcript
   requesting `Mars/Olympus` becomes structurally valid and must then take
   the `unsupported` path, so the tests must pin that behavior rather than
   just deleting the rejection tests.
7. **Then Phase 4 onward in handover order.** Phase 4 (#193 writes under the
   abort deadline, #194 ConPTY per-epoch budget) is the substantive runtime
   work and the largest remaining risk; #213 should be read alongside Slice
   5.2 (#196), since both concern a reader that cannot be unblocked.

Gotchas:

- Phase 2/4 slices touch Windows-only code paths; run the Windows legs
  locally (this dev machine is Windows 11) and remember `_conpty.py` is
  excluded from coverage — do not let new `_jsonl_pipe.py` branches follow it
  into invisibility.
- R5's fix tightens the *control* codec; be prepared to defend
  frozen-surface compatibility in review (see Phase 2.3).
- Slices 1.1 and 7 both edit `README.md` — sequence or combine.
- The review file itself, if untracked, must be committed under
  `docs/agent/reviews/` (that placement is per PR #183) before or with
  Slice 1.1.

## 6. Key files & architecture

No remediation files exist yet. Files this initiative will touch, by phase:

- `README.md`, `SECURITY.md`, `CHANGELOG.md` fragments — Phases 1, 7, 8.4
- `docs/knowledge/protocol.md` — Phases 1, 3
- `docs/knowledge/control-protocol.md`, `AGENTS.md` — Phase 3.2, Phase 1.2
- `docs/agent/design/jsonl-control-transport.md` — Phase 1.2 (status line)
- `docs/developer-guide/adapter-authors.md`, `development.md`, `release.md`
  — Phases 1.2, 8.4
- `src/termverify/_jsonl_pipe.py` — Phases 2.1, 2.2, 4.1, 8.1
- `src/termverify/jsonl.py` — Phases 4.1, 8.1
- `src/termverify/control.py` — Phase 2.3
- `src/termverify/conpty.py`, `src/termverify/_conpty.py` — Phases 4.2, 5.1,
  5.3, 8.1
- `src/termverify/vt.py` — Phase 8.1
- `src/termverify/transcript.py` — Phase 8.2 (plus docstring in 1.2)
- `src/termverify/comparator.py` — Phase 5.1 (only if equivalence rule chosen)
- `src/termverify/__init__.py` — Phase 6
- `tests/` — every behavioral slice; `pyproject.toml`, `.github/workflows/`
  — Phase 8.3

Conventions to continue: structured failure taxonomy for all new failure
paths; disclosures written next to the code *and* in the relevant
`docs/knowledge/` page; every behavioral PR carries a changelog fragment;
adversarial review for nontrivial slices with a fresh reviewer context.

## 7. Testing approach

- **Strict TDD per behavioral slice:** write the failing test reproducing the
  review's failure scenario first (the review gives concrete scenarios for
  C2, R1, R2, R4, R5, R6 — use them as the test specs), observe red,
  implement minimally, observe green.
- **Test styles by finding type:** hostile-subject fixtures for
  deadline/buffer findings (non-reading subject, newline-free streamer,
  marker-less trickler, double-forker); property tests for codec symmetry
  (R5: parse-accepts ⇒ serialize-accepts); Windows-only integration tests for
  job-object findings (R3) and ConPTY items (5.3); plain unit tests for
  classification fixes.
- **Full gate before every commit** (from AGENTS.md):

  ```bash
  uv --no-config sync --all-groups --locked
  uv --no-config run pytest --cov --cov-report=term-missing
  uv --no-config run ruff check .
  uv --no-config run ruff format --check .
  uv --no-config run mypy src tests scripts
  uv --no-config run pre-commit run --all-files
  uv --no-config run pre-commit run --hook-stage pre-push --all-files
  uv --no-config build
  ```

- **Coverage ratchet:** the project ratchets coverage; new branches in
  measured modules must be covered. `_conpty.py` is coverage-excluded
  (Phase 8.3 revisits this) — until then, ConPTY changes need explicit test
  evidence in the PR since the ratchet will not catch gaps there.
- **POSIX-only findings (R4):** cannot be exercised on this Windows dev
  machine beyond unit level; rely on the Ubuntu CI legs, and note that a true
  double-fork escape test may need to be a CI-only integration test (or the
  disclosure disposition sidesteps it).

## 8. Session notes

- The review's §5 (strengths) is calibration, not work: do not "fix" the
  validator, teardown, or supply-chain areas it praises.
- The review was produced by four adversarial passes plus an independent
  verification pass; findings marked ✅ were re-verified against source.
  Unmarked findings (R2, R4, P-series reasoning) should be re-confirmed
  against current source at slice start — file:line references are pinned to
  `8f33e6c` and will drift as slices merge. Earlier phases shift lines for
  later ones; always re-locate by symbol, not line.
- The owner's standing workflow preference (from prior sessions): the slice
  loop with delegated decisions — the agent proposes, files, implements, and
  requests review; the owner decides only at recorded decision points. The
  open questions in §4 are exactly those points.
- P2/P3-class fixes are where wording matters most: the project's brand is
  truthfulness, and the review explicitly frames these as
  protocol-truthfulness issues. Draft amendment text in the issue and get
  owner sign-off *before* editing frozen-adjacent protocol prose.
