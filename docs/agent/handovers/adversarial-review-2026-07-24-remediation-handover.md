# Adversarial Review 2026-07-24 Remediation Handover

## Handover metadata

- **Status:** active — created 2026-07-24 at owner request to plan and track
  remediation of every finding in the
  [2026-07-24 adversarial review](../reviews/adversarial-review-2026-07-24.md)
  (reviewed revision: `main` @ `8f33e6c`).
- **Owner:** project maintainer
- **Created:** 2026-07-24
- **Updated:** 2026-07-25 (checkpoint: Phase 1 complete, Phase 2 two-thirds
  complete, next item Slice 2.2 / #188)
- **Review required:** yes — every slice that changes runtime behavior, the
  public API, protocol prose with normative force, or release/security claims
  requires TDD evidence, full validation, and an independent adversarial
  review pass per the standard slice loop. Doc-only hygiene slices require
  normal PR review.
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

### Phase 2 — One-comparison runtime hardening (review rec 2, 3) [IN PROGRESS]

Small, high-leverage behavioral fixes. Strict TDD each. Findings: **R1**,
**R3**, **R5**. Status 2026-07-25: Slices 2.1 (PR #208) and 2.3 (PR #209)
are merged with fresh-context adversarial reviews; **Slice 2.2 (#188) is
the next work item** — its design is settled (mirror the ConPTY binding's
checked `_assign_to_job`/`_terminate_job` wrappers in `_jsonl_pipe.py`;
the spawn path's existing `except OSError` block already fails closed;
tests monkeypatch the `_kernel32` function attributes to force the
failure legs, Windows-only).

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

### Phase 3 — Protocol-truthfulness reconciliation (review rec 7, partial) [TODO]

Prose with normative force; needs owner decisions on wording. Findings:
**P2**, **P9**.

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

### Phase 4 — Deadline coverage for writes (review rec 5) [TODO]

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

### Phase 5 — Fidelity boundaries: decide, fix, or disclose (review recs 6, 7) [TODO]

Findings: **R6**, **R4**, **R7**. Each starts with an owner decision recorded
in its issue.

- **Slice 5.1 — ConPTY replay-equivalence story (R6).**
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

### Phase 6 — Public API exports (review rec 8) [TODO]

Finding: minor `__init__.py` bullet. Export the authoritative codec
(`parse_transcript`, `serialize_transcript`, `TranscriptValidationError`) and
the documented closed registries (`KEY_NAMES`, `is_key_chord`,
`encode_key_chord`, `TIMEZONE_NAMES`) from the public `termverify` package so
third-party adapter authors need no underscore imports. Public-API change:
needs tests asserting the exports, doc updates (adapter-author guide, README
API mentions), and a changelog fragment. Do it pre-0.2.0 while cheap.

**Acceptance:** documented names importable from `termverify`; no doc tells
users to import private paths.

### Phase 7 — README capability truth (review rec 9) [TODO]

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
- **Slice 8.3 — Tests/CI minors:** per-OS supplemental (non-gating) coverage
  for `_conpty.py` (`pyproject.toml:67`); direct invalid-UTF-8 fixture for
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
- **Checkpoint 2026-07-25 (autonomous session paused by owner request):**
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
4. **Resume with Slice 2.2 (#188)** in a fresh sibling worktree from
   `origin/main`: add checked `_assign_to_job`/`_terminate_job` wrappers
   to `_jsonl_pipe.py` mirroring `_conpty.py:214-220`; call them from the
   spawn containment block (its `except OSError` already fails closed:
   kill, wait, close handles, raise) and `_terminate_tree`. Windows-only
   TDD by monkeypatching the `_kernel32` function attributes to return 0.
5. **Then Phase 3 onward in handover order** (3.1 #190 needs the
   vocabulary draft posted to the issue for owner sign-off first;
   timezone removal #192 and polarity docs #191 are unblocked).

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
