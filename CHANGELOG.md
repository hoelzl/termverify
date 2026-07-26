# Changelog

All notable changes to the termverify package are documented in this file. The
format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
the package adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
with the pre-1.0 policy below.

## Versioning and compatibility policy

- **Package versions are not protocol versions.** The transcript wire contract
  (`termverify.transcript/v1`) and its closed registries
  (`termverify.key/v1`, `termverify.key-encoding/v1`) are versioned
  independently and are immutable after freeze; changing their membership or meaning requires
  a new protocol or registry version, never a package release note alone.
- **Before 1.0.0** every `0.x` release may contain breaking changes to the
  Python API. Breaking changes are listed under a **Changed** or **Removed**
  heading with a migration note; they are never silent.
- **Pre-1.0 status.** 0.1.0 is published on PyPI (2026-07-19); no stable/public
  support claim is made. Releases follow the checklist in
  `docs/developer-guide/release.md`.
- Golden masters, baselines, and fixtures never update automatically as part
  of a release; human-reviewed diffs remain mandatory.

## [Unreleased]

Unreleased changes are collected as fragment files in [`changelog.d/`](changelog.d/)
and folded into this file by `scripts/collect_changelog.py` at release time.

## [0.1.1] - 2026-07-27

### Added

- **Release pipeline.** CI-gated merge-driven release workflow: a `Bump
  version` commit on `main` (or an explicit matching `vX.Y.Z` tag push) waits
  for CI green on the commit, creates the annotated tag only after the gate,
  builds and contract-checks sdist and wheel, attests build provenance,
  publishes to PyPI via OIDC trusted publishing (`pypi` environment, no stored
  tokens), and creates the GitHub release with the extracted changelog
  section. Version management uses bump-my-version with `pyproject.toml` as
  the single source of truth. (PRs #160, #161; first exercised for 0.1.0.)

- **Changelog fragments.** Pending changelog entries are written as fragment
  files under `changelog.d/` (one per PR, `<pr-or-issue>-<slug>.<type>.md`)
  and folded into `CHANGELOG.md` at release time by
  `scripts/collect_changelog.py`, eliminating the `[Unreleased]` merge
  conflicts that dominated concurrent multi-agent work. Hand-written
  `[Unreleased]` entries are still folded in; malformed input aborts without
  modifying anything.

- Added the `termverify.control/v1` message model and strict codec plus `JsonlAdapter`, a `termverify.adapter.Adapter` implementation driving a JSONL-speaking subprocess over pipes (slice 1 of issue #173, fake-child tested): session handshake with required `at_ms`, epoch dispatch with observation/terminal-message close, live `input.clock` channel, and pipe-based teardown, with receipts recorded via the channel-tagged delivery model. Includes the `docs/knowledge/control-protocol.md` knowledge page.

- Added real-subprocess integration for the JSONL control transport (slice 2 of issue #173): `JsonlBinding` spawns a `termverify.control/v1` subject with binary pipes and honest tree containment (kill-on-close job object on Windows, process-group `SIGKILL` on POSIX), forced-stop teardown that captures the OS-observed exit record, and blocked-reader interruption via the child's death. Includes the `tests/fixtures/jsonl_echo_subject.py` reference subject and an integration suite proving the recorded run passes the transcript codec and comparator unchanged, plus the `docs/developer-guide/jsonl-adapter.md` operating guide.

### Changed

- Added the accepted-design proposal for the JSONL subprocess control
  transport (issue #114 ask 2): `termverify.control/v1`, a
  TermVerify-owned, closed, versioned wire protocol mapping the frozen
  transcript/v1 lifecycle onto an interactive pipe, plus `JsonlAdapter`
  as the third implementation of the adapter contract (after direct and
  ConPTY). The design records the Option A/B/C analysis (owner decision
  2026-07-20: Option B), the JSON-RPC/LSP reuse assessment, the
  malformed-peer failure taxonomy, spawn-time constraint delivery via
  the cooperation ports, a live `input.clock` channel (new capability
  versus ConPTY), and pipe-based teardown semantics. Docs-only: the two
  implementation slices await design acceptance.

- Replay-subject validation errors now name the offending selector and the
  specific defect: a missing or unknown top-level member, and per-selector
  missing/unknown members or a value that fails the identifier grammar.
  Previously every selector defect raised the uniform
  `"run.started subject <name> is invalid"`. This improves adapter-author
  diagnostics without changing acceptance — the same payloads are accepted
  and rejected as before, and error text is not part of the wire contract.

- **Breaking (owner-approved post-freeze registry exception; transcript
  protocol stays v1):** the `termverify.key/v1` modified-only base set is
  widened with the full printable ASCII punctuation row (32 characters:
  ``! " # $ % & ' ( ) * + , - . / : ; < = > ? @ [ \ ] ^ _ ` { | } ~``), each
  requiring a trigger modifier like letters and digits. This makes
  Emacs-lineage chords such as `["Control", "/"]`, `["Control", "_"]`, and
  `["Alt", "<"]`/`["Alt", ">"]` expressible through `KeyInput` for the first
  time; previously no valid chord could name a punctuation base. The change
  is purely additive — every previously valid chord and its encoding is
  unchanged — but it re-binds both reviewed digests: `termverify.key/v1`
  (67 → 99 entries) and the `termverify.key-encoding/v1` full enumeration
  (934 → 1382 chords, 450 → 482 encodable). Encoding semantics follow the
  existing digits/`Space` rule: `["Alt", p]` encodes to `ESC p`; `Control`,
  `Meta`, and `Shift` punctuation forms are unencodable and fail closed (no
  legacy byte form represents them). Migration: re-derive any pinned copy of
  either digest; ConPTY subjects now receive a structured
  `{"unsupported": "key-encoding", ...}` failure for punctuation
  `Control`/`Meta`/`Shift` chords instead of the chord being inexpressible.
  See `docs/agent/design/key-v1-punctuation-bases.md`.
  **Post-freeze exception (owner decision 2026-07-19, issue #155):** this
  amendment was implemented and adversarially reviewed before the 0.1.0
  release froze the inception policy, but merged after it. The owner
  approved landing it as a one-time in-place amendment to `termverify.key/v1`
  rather than cutting a `termverify.key/v2` registry, because the change is
  purely additive (no existing chord, spelling, or encoding is altered) and
  the wire-protocol version is unchanged. This exception does not set a
  precedent: any future change to registry membership, meaning, or spelling
  requires a new registry version per `docs/knowledge/protocol.md`.
=======
Unreleased changes are collected as fragment files in [`changelog.d/`](changelog.d/)
and folded into this file by `scripts/collect_changelog.py` at release time.

- Made pre-push failures fast and diagnosable (issue #168): the pre-push
  stage now runs the cheap checks first (mypy, distribution build) and the
  multi-minute test suite last, so a trivially fixable type or packaging
  error aborts the push in seconds instead of after the full suite. The
  developer guide now documents that git's generic `error: failed to push
  some refs` means a local pre-push hook failed (not a remote race), to
  rerun `pre-commit run --hook-stage pre-push --all-files` in the
  foreground to see the failing hook's banner, and never to retry with
  `--no-verify` (which pushes commits CI will reject).

- Amended the `termverify.transcript/v1` delivery model in place (additively, owner decision on issue #173): `delivered`-tier delivery records are now channel-tagged (`spawn-env`, `hello-config`, `wire-message`), so constraints delivered through the JSONL handshake or control-protocol messages can be claimed truthfully; legacy bare `env`/`cwd` records remain accepted via codec compat-rule normalization. Tier vocabulary membership is unchanged. See `docs/agent/design/channel-tagged-delivery-records.md`.

- **Review report placement.** Adversarial and independent review reports
  now live under `docs/agent/reviews/`: the `AGENTS.md` documentation
  placement table and the developer-guide repository layout name the
  directory, a README there records the filing conventions (one report per
  review pass, target-based file names, exact reviewed-SHA discipline,
  point-in-time records), and the three pending reports previously
  untracked at the repository root are filed there. (PR #183.)

- **Protocol freeze suspended; prototyping stage declared.** By owner
  decision (2026-07-24,
  `docs/agent/design/prototyping-stage-protocol-governance.md`), the
  inception freeze that fired with the 0.1.0 publication is suspended:
  every TermVerify protocol and registry may change incompatibly in place,
  without version bumps or per-change exceptions, until the owner
  explicitly declares TermVerify ready for external clients. No backward
  compatibility is owed to the published 0.1.0 artifact.
  `docs/knowledge/protocol.md` and `AGENTS.md` state the status.

- **Made `capability.result.status` tier-truthful: `enforced` → `applied`.**
  The transcript protocol mandated `status` ∈ {`enforced`, `unsupported`} and
  called a supported-but-not-enforced state invalid — while the `delivered`
  enforcement tier is defined as "honoring it is subject cooperation.
  **Nothing is enforced.**" Every delivered-tier constraint was therefore
  recorded on the wire as `enforced`: the tier system exists to avoid
  overstatement, and the status vocabulary it qualifies overstated anyway
  (adversarial review 2026-07-24, finding P2). The status word now says only
  that the adapter carried out the constraint's application step and recorded
  the value it applied; the already-mandatory `tier` says what that step was
  worth — at `os` and `constructive` the constraint is in force, at
  `delivered` what was applied is the delivery. `enforced` is not an accepted
  value: an in-place vocabulary correction under prototyping-stage governance,
  with no version bump, alias, or shim.
- **Removed the containment claims the cooperation tiers cannot support.**
  The same protocol section told adapter authors that an adapter "gives
  filesystem access only through the named sandbox root and denies network
  access by default", "injects the requested seed and manual clock", and
  "starts subprocesses with the requested locale" — none of which is true on
  the delivered path, where the cooperation ports set environment variables,
  never deliver manual-time advances, set no `LANG`/`LC_ALL`, and block no
  sockets. That contradicted both the shipped code and the accepted decision
  that no receipt, claim, or document may imply containment. The
  adapter-facing contract is now stated per tier, `architecture.md`'s
  "either enforces … or unsupported" binary is replaced by the tiered rule,
  and the run-level claim is that a run's constraint claims are *no stronger
  than* its weakest tier — an upper bound, not the equality the first draft
  of this change asserted (adversarial review of PR #216).
  Validator, the single emitter, repository fixtures, and every normative
  prose site move together; the packaged JSON Schema never encoded `status`,
  so it is unchanged. (Resolves #190.)

### Removed

- Removed the defined-but-never-emitted `teardown-forced` failure code from the `termverify.control/v1` taxonomy (issue #178). The deadline-abort path emits `epoch-timeout` and discloses the forced-termination exit record in the terminal result, which is the intended surface; the `epoch-timeout` row in `docs/knowledge/control-protocol.md` now carries that disclosure claim. This is a pre-freeze correction: `termverify.control/v1` has not yet been published to PyPI, so the taxonomy shrinks before the protocol freezes at first publication. No behavior changes — the removed code was unreachable.

- **Removed the `termverify.timezone/v1` registry.** A 374-line closed registry
  pinned to IANA TZDB 2026c by tarball SHA-256, with a generator and
  digest-bound tests, existed to validate timezone requests that v1 must then
  refuse anyway: only literal `UTC` can ever be applied, because applying a
  named zone needs zone data the protocol deliberately never consults. Its one
  concrete effect was to paint v1 into a corner — a record carries no
  registry-version selector, so any future TZDB zone would have required a whole
  new protocol version (adversarial review 2026-07-24, finding P4; owner
  decision 2026-07-24). `timezone` is now a plain non-empty string.
  **This widens acceptance**: `Mars/Olympus` is a structurally valid *request*,
  exactly as `Europe/Berlin` always was, and the refusal — a `capability.result`
  with `status: "unsupported"` and a matching `run.unsupported` — is what keeps
  the evidence truthful. What has not changed is the rule that actually protects
  it: only literal `UTC` may appear as an applied effective value, enforced by
  the runtime and beyond what schema validation can express. Deleted:
  `src/termverify/_timezone_v1.py`, `scripts/generate_timezone_registry.py`, and
  the registry's tests; Git history preserves them, and any reintroduction, when
  a vertical actually demands non-UTC zones, is a fresh design with a
  registry-version selector rather than a revival of this one. (Resolves #192.)

### Fixed

- Documented the ESC-prefixed-sequence input-reader disclosure (issue #169):
  the ConPTY input pipe delivers ESC-prefixed bytes verbatim to the child's
  console input buffer (a bare ESC arrives as an Escape keypress), but the
  Microsoft C runtime's wide-character console reader (`msvcrt.getwch()`,
  and with it Python's `sys.stdin` text IO) parses ESC-prefixed sequences
  itself — `ESC x` surfaces as just `x` with the Alt modifier lost,
  `ESC [ A` surfaces as the translated virtual key, and a lone ESC blocks
  inside the runtime's sequence-assembly wait, turning a bare-`Escape`
  epoch into an abort-deadline expiry. Subjects binding ESC-prefixed
  (Emacs-style meta) chords must read console input byte-wise (`os.read` on
  the stdin file descriptor, or `ReadFile`/`ReadConsoleA` on the input
  handle), as the ConPTY integration fixture demonstrates. No adapter or
  protocol change: delivery, not interpretation, unchanged.

- **Release-status truth in README and SECURITY.md.** Both documents denied
  the 0.1.0 PyPI release that happened on 2026-07-19 (adversarial-review
  finding C1). They now state the actual release, that the artifact is a
  distribution-pipeline exercise with no support or compatibility guarantee,
  and the prototyping-stage posture with a link to the recorded governance
  decision. (Resolves #185.)

- **Documentation corrections from the 2026-07-24 adversarial review
  (finding P1 and doc minors).** The spawn-env compatibility sentence in
  `protocol.md`, `channel-tagged-delivery-records.md`, and the
  `transcript.py` docstring no longer declares the canonical
  `{"channel": "spawn-env", "env": ...}` form invalid (only `env` with a
  *different* channel rejects). The JSONL control-transport ADR status is
  corrected to accepted (slices merged as PRs #175/#177). The stale
  934-chord count in the pre-release handover now records the amended
  1,382-chord enumeration and current digest. The JSONL adapter guide warns
  subjects to write protocol lines through a binary stream (text-mode
  `print` emits `\r\n` on Windows and every message rejects as
  `peer-malformed`). `control-protocol.md` gains full OKF frontmatter and
  its freeze sentence now defers to prototyping-stage governance.
  `development.md` no longer lists the nonexistent `skills/` directory.
  (Resolves #186.)

- **Bounded the JSONL read buffer at the protocol line ceiling.** A subject
  streaming newline-free bytes could grow the binding's read buffer without
  bound — the abort deadline bounds time, not memory (adversarial review
  2026-07-24, finding R1). `PipeJsonlChild.read_line` now stops
  accumulating once the buffered pseudo-line exceeds the
  `termverify.control/v1` framed-line ceiling without a buffered LF and
  returns the oversized buffer,
  which `parse_message` rejects by length — the flood fails through the
  existing `peer-malformed` path, OS-evidence-tested with a real flooding
  child. (Resolves #187.)

- **Fixed two defects in the pipe binding's new job-object checks.** The
  adversarial review of PR #211 (finding R3's remediation) found that (1) a
  child exiting inside the disclosed assignment window now failed the whole
  spawn: Windows refuses `AssignProcessToJobObject` on an exited process, so
  a legitimate fast subject was non-deterministically reported as a
  containment failure. That case is now read as "nothing left to contain" and
  the binding reports the child's real exit record. (2) A failed
  `TerminateJobObject` could strand the teardown: with a read still blocked
  on the child's pipe — the adapter's own watchdog shape, where the deadline
  timer closes while the main thread is in `read_line` — the pipe detach
  waited on the blocked reader's lock, the job handle was never released,
  kill-on-close never fired, the contained tree leaked and `close` never
  returned. The teardown now releases containment before it touches the
  pipes, so the sweep ends every remaining job member, the sweep unblocks the
  read, and the caller still learns the termination failed.
- **Made the pipe binding's containment prose match what it can deliver.**
  A second review round refuted the claims attached to those fixes: a job
  whose member was never assigned stays permanently empty, so it sweeps
  nothing, and a forced close of such a binding cannot terminate a
  descendant the exited child left behind. `spawn` and `close` now disclose
  that boundary — it is the same escape as the already-disclosed assignment
  window, since failing the spawn would not contain the descendant either —
  and describe the sweep as covering every remaining job *member* rather
  than "the tree". Pipe descriptors are also now released deterministically:
  the teardown closes the raw stream `detach` hands back instead of leaving
  it to a finalizer, the spawn's fail-closed path releases both pipes and
  both kernel handles even if the child cannot be reaped, and a failed
  teardown reaps the child with a non-blocking poll rather than not at all.
  (Refs #188, #213, #217.)

- **Checked the pipe binding's Windows job-object results.** The JSONL pipe
  binding discarded `AssignProcessToJobObject`'s BOOL return, so containment
  could fail silently and `PipeJsonlChild.spawn` would hand out a session
  whose docstring promises a contained child — a later forced close would
  then terminate an empty job (adversarial review 2026-07-24, finding R3).
  Both containment calls now go through checked wrappers mirroring the
  ConPTY binding's: a failed assignment fails the spawn closed (the child is
  killed, the handles released, the failure raised) and a failed
  `TerminateJobObject` is raised instead of read as a success — previously it
  surfaced only as a 30-second wait misreported as "the child did not
  terminate on forced close". Kill-on-close still sweeps the tree when the
  job handle is released, so neither path leaks a process.
  (Resolves #188.)

- **The control codec rejects unpaired surrogates.** `parse_message`
  accepted lone surrogates (arriving as valid UTF-8 line bytes via JSON
  escapes) that RFC 8785 canonical serialization rejects, so hostile input
  could crash the recording pipeline with an uncaught
  `TranscriptValidationError` instead of failing `peer-malformed`
  (adversarial review 2026-07-24, finding R5). `_validate_json_value` now
  encodes strings and object keys strictly, restoring parse/serialize
  symmetry in both codec directions; valid surrogate pairs (astral
  characters) still round-trip. (Resolves #189.)

- **Made doc/code authority polarity consistent.** `AGENTS.md` treats
  executable checks as authoritative over prose, while the control-protocol
  specification claimed the opposite — "the codec is wrong and this document
  wins" — so the two normative documents gave opposite answers to the same
  question (adversarial review 2026-07-24, finding P9). Owner decision
  2026-07-24: code wins everywhere for the duration of the prototyping
  stage. `docs/knowledge/control-protocol.md` now says so, `AGENTS.md` gains
  a control-protocol row naming `src/termverify/control.py` as the authority
  for wire acceptance, and the prototyping-stage governance record carries it
  as a numbered decision whose revisit is bound to that record's exit
  criterion — where doc-as-contract becomes defensible for a protocol
  third-party subjects implement. A doc/codec disagreement remains a defect either way: repaired
  doc-side by default, code-side through a test-first slice when the codec is
  the wrong one. (Resolves #191.)

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

- **Bounded the ConPTY epoch in time.** The abort deadline is re-armed per
  read, so a subject emitting one byte just under it and never emitting the
  readiness marker never exceeded any single read's deadline: the marker never
  arrived, `dispatch()` neither completed nor aborted, and the retained chunk
  list grew without bound (adversarial review 2026-07-24, finding **R2**). The
  same configured deadline now also bounds the epoch as a whole, checked
  between reads, so the trickle aborts through the ordinary deadline path with
  the ordinary deadline evidence. Worst case is up to twice the deadline — the
  epoch's bound plus the read in flight when it passes. The details now name
  which bound fired (`read` for a stalled read, `epoch` for a subject that
  produces output but never reaches readiness), because the two look identical
  otherwise and need opposite remediations.
  **This can abort runs that previously passed:** an epoch that legitimately
  takes longer than the deadline while producing output now fails by policy,
  so hosts with long-running epochs must raise the deadline — at the cost of
  slower hang detection, since one value serves both bounds.
- **Bounded an epoch's retained evidence at what one record can carry.** An
  epoch's chunks reach the transcript as a *single* coalesced
  `terminal.output` string (#195), so the adapter bounds retained bytes
  against the tighter of the two ceilings that string meets: the per-string
  ceiling, which binds at ordinary geometry, and the per-record string sum
  less what the rest of the record costs, which binds above roughly 261,000
  cells. Deriving the budget from the per-record sum alone admitted epochs at
  1.98x the per-string ceiling on a plain 80x24 run, which the codec then
  rejected — losing the whole run's evidence at the end.
  The budget is **computed from the terminal geometry** rather than fixed,
  because the frame's lines are the record's other large strings: a flat
  reserve was measurably wrong in both directions — too small at 200x328 and
  above, where the adapter admitted epochs the codec then rejected for size,
  and too large at 80x24, where it aborted epochs that recorded fine. The
  frame reserve counts **UTF-8 bytes per cell, not cells**: the codec measures
  bytes, and a box-drawn or CJK screen costs three to four bytes per cell, so
  counting cells under-reserved by up to 4x — observable above roughly 261,000
  cells, where the per-record sum is the binding ceiling and a large emoji
  frame was admitted and then rejected. At 523,264 cells or more the frame
  reserve leaves an observation record no room for output at all, and the
  run now fails with `budget: "geometry"` as soon as an epoch begins —
  before any read, so a resize past the threshold cannot slip through an
  epoch whose readiness marker was already buffered — rather than as a
  phantom output flood.
  Disclosed limit: the codec still owns recordability and enforces ceilings no
  budget can model, notably a canonical-line limit ESC-dense output reaches far
  sooner.
- **No chunk-count bound ships.** An earlier revision of this fix carried one;
  #195 made it unreachable and it was removed before merge. While every chunk
  was its own event, a subject redrawing in place could exhaust the protocol's
  per-collection ceiling with under 100 KB of output in seconds. Coalescing
  removes the axis: no number of native reads can reach that ceiling, so a
  spinner is bounded by the bytes it writes and nothing else.
- **Rejected a read-count budget on measurement.** A count low enough to bound
  a trickle also aborts a cooperative subject: real ConPTY barely coalesces
  (635 reads for a 2,000-line scroll), so a 1024-read budget failed a plain
  few-thousand-line run in about three seconds while a 30 s deadline never
  fired. A regression test pins that a 4,000-chunk epoch inside the deadline
  still succeeds. (Resolves #194.)

- **Coalesce adjacent `terminal.output` chunks at record time.** ConPTY read
  chunk boundaries are OS scheduling noise, not evidence, so the exact
  comparator made behaviorally identical runs diverge on how the OS happened
  to split the same output across native reads (adversarial review
  2026-07-24, finding **R6**; owner decision: recorder-side coalescing,
  option A1). The recorder now merges each run of adjacent observation
  events whose `type` is `terminal.output` and whose `data` is exactly
  `{"chunk": <str>}` into one event with the chunks concatenated; any other
  event passes through unchanged and bounds the merge. The exact comparator
  and its no-normalizers decision are untouched, and adapters keep their
  per-read chunk lists in memory — only the transcript loses the noise.
  Acceptance evidence: two runs of a deterministic fixture subject through
  the real ConPTY adapter now reach an equivalent comparator verdict, the
  DirectAdapter repeat-run pattern promoted to the real Windows path.
  Without the coalescing the test's no-adjacent-chunks check fails
  deterministically (ConPTY split every probed run), while the repeat-run
  comparison itself diverges only intermittently — the original R6
  symptom — which is why the test asserts both. (Resolves #195.)

- **A blocked POSIX read or write can no longer be wedged by a process the
  containment cannot reach.** The reader was a blocking `read1` on the child's
  buffered stdout, and nothing could interrupt it. A descendant that starts its
  own session (`setsid`) escapes the process-group kill, and while it holds the
  child's stdout write end no end-of-stream ever arrives — so the reader thread
  stayed blocked for the life of the verifier, the abort deadline produced no
  structured failure, and the teardown could strand itself behind the reader's
  own buffered lock inside a `finally`. Measured on the Ubuntu legs before the
  fix: the read was never woken.

  The POSIX binding now owns both pipes as raw descriptors and waits on
  `select` over the descriptor **and a self-pipe**; every close signals that
  pipe before terminating anything and before touching any descriptor. The
  interruption is the binding's own rather than one borrowed from containment,
  so it does not depend on reaching whoever holds the other end. Writes are
  covered the same way, so a child that stops draining its stdin cannot stall a
  write either. (Resolves #196, review finding **R4**.)
- **The stdin release on POSIX no longer flushes, because there is nothing left
  to flush.** Two comments claimed `detach()` released the buffered writer
  without flushing; it flushes, so the teardown stall they existed to prevent
  was not prevented — bounded only by the tree already being dead. Detaching
  now happens once at construction, where both buffers are provably empty, and
  teardown closes raw descriptors. (Resolves #217 on POSIX; the Windows
  teardown still releases a buffered writer, and that flush is still bounded
  only by the tree already being dead.)
- **The teardown deadlock behind a descendant-held pipe is closed on POSIX.**
  Same shape as the above and the general form of the ordering invariant the
  Windows handle release already followed: release every mechanism that can
  unblock an operation before performing an operation that can block on it.
  (Resolves #213 on POSIX; the Windows leg remains a disclosed boundary, since
  `select` does not work on anonymous pipe handles.)
- **Reworded the platform-parity claim, which overstated on both halves.**
  `JsonlBinding` promised "identical observable outcomes on every platform
  (real exit record, forced-termination record, **no survivors**)". Survivors
  are possible on both platforms — a `setsid()` descendant on POSIX, a process
  started inside the disclosed assignment window on Windows — and reaping them
  portably is out of scope by recorded decision. What is identical is the
  *failure classification*; what is now true everywhere is that a survivor
  cannot stall a teardown on POSIX or make a run report anything it did not
  observe. Recorded in `docs/knowledge/architecture.md`.

- **Read ConPTY output as raw bytes and decode it incrementally.** The binding
  took pre-decoded `str` from `pywinpty`, which decoded each native read in
  isolation: a read landing mid-codepoint turned the split character into
  `U+FFFD` and lost it outright, irreparably, in evidence (adversarial review
  2026-07-24, finding **R7**). Measured on this matrix, a 200,000-character
  burst of `U+65E5` produced 29 replacement characters across 21 reads and lost
  12 characters. `pywinpty` exposes no bytes-returning read and no way to reach
  the conout handle, and the damage cannot be repaired above it, so
  `termverify._conpty` now owns the pseudoconsole outright — `CreatePseudoConsole`,
  an `STARTUPINFOEX` spawn, and its own overlapped `ReadFile` loop on conout.
  `read()` still returns `str`, but one incremental UTF-8 decoder now spans a
  child's whole lifetime, so a split codepoint heals on the following read. A
  `U+FFFD` in ConPTY evidence now means the child genuinely emitted invalid
  UTF-8. Adversarial split-point tests cover every cut of two-, three-, and
  four-byte codepoints, a byte-at-a-time trickle, and a volume burst; they run
  on every platform against a fake native session. (Closes #197, refs #102.)
- **Dropped the `pywinpty` dependency.** Nothing imports it any more; the
  Windows dependency and its mypy override are gone from `pyproject.toml`, and
  the accepted terminal-adapter dependency decision is amended to record the
  replacement and the evidence for it.
- **Start programs whose path contains spaces.** The command line now quotes
  `argv[0]` like every other argument while the executable is named to the OS
  separately, so a spaced program path can no longer reach the child split
  across several arguments. (Refs the `_conpty.py` spawn minor in the same
  review.)
- **Write every byte handed to `write()`.** The previous binding issued one
  native call and accepted whatever it took; the loop now writes the whole
  payload. Conin sustains roughly 1 MiB/s — the console host turns every byte
  into input records — so a large payload holds the single-flight slot for
  proportionally longer than it used to.

- **Bounded the ConPTY epoch on frame rows and frame width, not only on
  frame bytes.** The per-epoch geometry gate added in #194 reserved four
  bytes per cell and refused the epoch once nothing was left for output — a
  *cell* model, and the frame meets three `termverify.transcript/v1` ceilings
  in three different units. The other two are unreachable from the cell
  product:
  - A frame is one collection item per line, and a collection holds 16,384
    items, so a terminal of 10 columns and 20,000 rows — 200,000 cells, two
    and a half times below the 523,264-cell threshold — produced observation
    records the codec rejected for collection size.
  - One frame line is one string of `columns` code points, so a terminal of
    262,145 columns and 1 row — 262,145 cells — produced observation records
    the codec rejected for string size once the screen held four-byte
    characters, which the shipped normalizer reaches one code point per
    cell. Unlike the row ceiling, this one is content-dependent: the same
    geometry records fine while the screen is ASCII, and the adapter
    reserves the worst case rather than waiting to find out. Only a
    single-row terminal can reach it at all: at two rows, any width past
    262,144 is already past the cell threshold.

  Both are now refused as the cell case is, in the same `budget: "geometry"`
  failure class, with `terminal-rows` or `terminal-columns` naming the axis
  that bound. Both were reachable: `TerminalConfiguration` requires only a
  positive int, and 262,145x1, 1,048,577x1 and 10x100,000 pseudoconsoles were
  each created and spawned into on the Windows dev host. (Resolves #226.
  Rounds 7 and 8 of the adversarial review of #194.)
- **Corrected several claims about the #194 budget that outlived their
  mechanism.** The developer guide said a 523,264-cell frame "still fits one
  record", which is false for a tall frame — 32,704x16 validates and its
  transpose does not. Its "worst case is twice the deadline" omitted the
  conin write, which `_conpty.py` discloses as running outside the deadline
  entirely; the write is not the only uncovered part of `dispatch`, so the
  guide now bounds the claim to the read phase rather than trading one
  over-claim for another. The budget docstring and #194's changelog fragment
  cited a box-drawn 100x30 TUI as the witness for the four-byte-per-cell
  reserve, where the per-string ceiling binds and the reserve is entirely
  slack. The guide's list of ceilings no epoch bound can model gained the
  32 MiB per-transcript ceiling, which accumulates across epochs and which
  no per-epoch check can see. The design document's classification table
  gained the rows it was missing for both `budget` abort classes and for the
  deadline abort's `bound` detail.

- **Platform legs are ratcheted where they run, not nowhere.** The
  `# pragma: no cover` markers on `_jsonl_pipe.py`'s platform legs were
  static source exclusions: a pragma on a `def` removed the whole body from
  measurement on **every** platform, so the POSIX I/O implementation was
  unratcheted even on Linux (and the Windows containment legs on Windows).
  The legs now carry per-OS markers (`# coverage: exclude-posix` /
  `# coverage: exclude-windows`), `pyproject.toml` excludes both for local
  runs, and each CI quality leg selects `coverage-windows.toml` or
  `coverage-posix.toml` via `COVERAGE_RCFILE` — an overlay that repeats the
  gating settings but excludes only the legs that cannot run there. Windows
  legs measured on Windows: module 75.59%, total 94.66% against the 94
  floor; the Ubuntu number is CI-validated on the PR. Overlay drift
  (repeated gating settings no pytest invocation compares) is checked
  mechanically by the new `scripts/validate_coverage_overlays.py`
  pre-commit hook. (Closes #230.)

- **The ConPTY readiness marker now actually bounds its epoch's output.** The
  marker was a private-use OSC sequence, chosen because a Windows-matrix test
  showed ConPTY relaying it verbatim. Relaying it verbatim was never
  sufficient: ConPTY renders text on one path and passes OSC through on
  another, and the OSC path is ahead. Measured — a subject's single atomic
  write of `TV_BEFORE` + marker + `TV_AFTER` arrives as the marker alone, then
  the text. The adapter therefore ended epochs on a marker whose output had
  not been delivered and reported frames missing it. The original evidence
  held only because the previous binding's reads were slow enough that the
  renderer had already flushed; the raw-byte read path (#197) made the gap
  observable and eight integration tests failed on it. (Closes #232.)
- **Breaking, prototyping-stage: markers are printable and carry a token.** A
  marker is now `READINESS_MARKER_PREFIX_DEFAULT` (configurable), a token the
  subject has not used before in the run, and `READINESS_MARKER_TERMINATOR` —
  `<<termverify.ready:7>>` and so on. Printable, so it travels the renderer's
  path and is ordered against the output it bounds. Tokenised, because
  rendered text is screen state and ConPTY re-emits screen state on every
  repaint: with a constant marker a resize's repaint completed an epoch whose
  input never sent one. The adapter honours each token once.
  `READINESS_MARKER_DEFAULT` is replaced by `READINESS_MARKER_PREFIX_DEFAULT`,
  and the `readiness_marker` constructor argument by
  `readiness_marker_prefix`.
- **Subjects must emit the marker on its own newline-terminated line.** It
  occupies screen cells now, so without the newline the next output continues
  on the same row; and a marker split across a line wrap has a malformed
  token, which is deliberately not honoured so the epoch fails closed on its
  deadline instead of completing wrongly. A token must match
  `[0-9A-Za-z._-]{1,64}`.

- **Marker-protocol corrections from the #233 adversarial review.** The
  review probed the tokenised printable readiness marker against a fresh
  oracle and the real console and found the scanner sound but the
  specification wrong in places. Measured corrections: a marker wider than
  the terminal is delivered contiguous and *honoured* — wrapping is
  screen-buffer layout, not stream content — so the token charset's
  fail-closed skip defends against cursor-addressed mid-emission corruption,
  not line wraps; the module docstring, design doc, and developer guide all
  claimed the opposite, and a new Windows integration test pins the measured
  behaviour. `_validate_marker_prefix` now rejects non-printable prefixes,
  closing a configuration path that recreated the #232 OSC-overtaking defect
  (e.g. `"\x1b]7791;"` as prefix). The subject cooperation contract now
  discloses the three measured marker-forgery channels — stray prefix
  emission in ordinary output, console input echo (`ENABLE_ECHO_INPUT`),
  and marker text inside escape-sequence payloads such as OSC titles — and
  that repeat-run transcript comparison requires run-stable token values.
  (Closes #233.)

- **A stray marker prefix in subject output no longer swallows the next real
  readiness marker.** `_scan_for_marker` searched for the terminator from the
  first prefix it found, so a subject that printed the prefix by accident
  consumed the *next* genuine marker's `>>` into one oversized token and
  skipped past the real marker — the epoch then ran to its deadline and the
  run reported a deadline abort against a correct subject. Rejected candidates
  now resume the search one character past where they *began*, not past where
  they ended. An unterminated candidate is also dropped once it outruns the
  longest legal token, which it could not previously do: one stray prefix
  retained every later byte of the run in the scan buffer and rescanned them
  on every read. (Adversarial review of #234, critical.)
- **A cancelled or failed wait no longer abandons a pending overlapped read.**
  Two exits from `_await_read` raised while the `ReadFile` was still
  outstanding, leaving the kernel owning an `OVERLAPPED` that is a frame local
  of `read_bytes` and a buffer a later read would reuse. Every non-success
  exit now cancels and waits the read out first.
- **End-of-stream is decided by the native signal, not inferred from a dead
  child.** `ConptyEndOfStreamError` carries the guarantee that every byte the
  pseudoconsole emitted has already been returned; the classifier re-derived
  it from liveness, so any read failure arriving after the child exited
  claimed that guarantee. It now dispatches on the native failure itself.
- **`ResizePseudoConsole` runs under the lock that protects the handle.** The
  handle was read under the lock and used outside it, so the end-of-stream
  path could hand it to the closing thread in between and the resize would run
  on a freed handle.
- **A pseudoconsole that never finishes closing is reported.** `close()`
  joined the closing thread with a timeout and returned normally when it
  expired, silently leaking the handle and the thread while claiming a
  release it had not made.
- **`is_supported()` answers the question it documents.** It returned
  `os.name == "nt"`, but pseudoconsoles arrived in Windows 10 1809 and the
  spawn fails closed without them, so negotiation could report supported on a
  host where every start would fail.
- **Empty decodes are no longer recorded as evidence.** A native read landing
  inside a multi-byte codepoint decodes to nothing until the rest arrives;
  those were retained as `terminal.output` events asserting the child emitted
  nothing, and they never advanced the epoch's byte counter.
- Test fixes from the same review: the no-native-pin assertion was pinned to
  pywinpty's `PTY` class name and had become unfalsifiable; the burst
  accounting inferred one repeat per reposition from a total instead of
  asserting the pairing; the split-marker test built its halves from three
  different markers and only ever cut inside the prefix; and the in-flight
  write test could not tell an overlapping close from a write that had already
  finished. Cross-platform tests now cover both behaviours #232 is about — a
  repainted marker being ignored and a malformed token being skipped — which
  had evidence only in the Windows-only integration module.

- **A maximum-length marker token is no longer lost when its terminator
  straddles two reads.** The rule that drops a candidate too long to still be
  a marker counted the token but not the terminator, so a 64-character token
  followed by a split `>>` was discarded one character short of viability —
  the marker vanished and a cooperating subject was reported as a deadline
  abort. A hex digest is 64 characters, which is an obvious choice for "a
  token I have not used before". The terminator search is bounded to the same
  span, which also stops one stray prefix from making the scan quadratic in
  the size of a read. (Round-two adversarial review of #234, critical.)
- **A resize can no longer block teardown.** Holding the session lock across
  `ResizePseudoConsole` fixed a use-after-free race but let a resize block the
  reader — and the reader is what stops draining conout, which the console
  host may be waiting on to finish that very resize. `close()` became
  blockable without bound, on the operation that backs the adapter's abort
  deadline. The handle is now pinned by a dedicated lock that only the closing
  path takes, so the reader never waits on a resize.
- **A stalled pseudoconsole close no longer masks the failure that caused the
  teardown.** It was raised from a `finally`, so it displaced errors that
  matter more — a child that would not die — and skipped the remaining
  teardown on the graceful path. It is recorded and reported only once the
  close has otherwise succeeded.
- **A host-configured marker prefix made only of token characters is
  rejected.** Such a prefix can be absorbed into a neighbouring candidate's
  token, so the genuine token is never recorded and the console's next repaint
  of that marker completes another epoch — the double-honour #232 exists to
  prevent. The default prefix was never affected.
- `is_supported()` gained the regression test its fix lacked, and the existing
  probe test no longer asserts the contract that fix repudiated — it would
  have failed on exactly the pre-1809 Windows the fix targets. The empty-decode
  skip, `_read_epoch_chunks`' one uncovered branch, gained a test too.
- Narrowed two destructor hazards the previous round's fixes opened: a
  part-built session no longer releases handles its caller still owns, and the
  read-cancellation helper no longer touches handles a concurrent close has
  already released.

- **ConPTY containment: the job-assignment window is closed.** The binding
  now creates its child with `CREATE_SUSPENDED`, assigns it to the
  kill-on-close job while still suspended, and only then resumes the main
  thread — no descendant can predate the job membership, so containment is
  a property of the spawn rather than a near-certainty. Every exception
  raised by the spawn's own statements between creation and resume —
  including the bookkeeping itself — terminates the suspended child (a
  suspended process cannot die of handle closes) and closes the thread
  handle; the residual window is a signal landing in the few bytecodes
  between `CreateProcessW`'s return and the handle capture. New
  Windows-matrix evidence: creation flags plus assign-before-resume call
  order, containment failure provably never resumes, and fault-injected
  failures at every point between creation and resume leave no suspended
  orphan and no leaked thread handle (OS-verified). The disclosed boundary
  is deleted from the module, and the architecture knowledge page and
  boundary-hardening handover record the closure. The JSONL transport's
  Windows spawn does not own `CreateProcess` and retains the window — a
  separate, disclosed boundary. (Closes #235.)

- **The native ConPTY binding is coverage-visible again.** The omit in
  `pyproject.toml` stood on a "deliberately thin wrapper" rationale that
  stopped being true when the binding took the pseudoconsole over from
  pywinpty (#197); both review rounds of #234 found defects in exactly the
  code the omit made invisible. The Windows CI legs now run a supplemental,
  non-gating measurement (`conpty-coverage.toml`) of the ConPTY suites
  against `termverify._conpty` and report with missing lines — the gaps are
  visible in every Windows-leg log, while the cross-platform gating floor
  stays OS-independent. Recorded disposition: Slice 8.3 of the 2026-07-24
  remediation handover. The stale rationale is corrected in the module
  docstring, the developer guide, and the `pyproject.toml` comment.
  (Closes #236.)

## [0.1.0] - 2026-07-19

### Added

- Deterministic transcript v1 codec, semantic lifecycle validator, and
  fail-closed resource limits with parser/serializer symmetry.
- Closed protocol-owned v1 registries for requested timezone names and
  semantic key chords, with an immutable direct-dispatch key representation.
- Immutable producer-side adapter contract and deterministic in-process direct
  runtime with structured failure classification.
- Safe transcript-persistence boundary with fail-closed evidence
  classification, redaction, and atomic same-directory replacement.
- Packaged canonical transcript schema with installed access API
  (`TRANSCRIPT_SCHEMA_V1_ID`, `transcript_schema_v1_bytes`,
  `transcript_schema_v1_json`) and isolated installed-artifact contract checks.
- No-regression coverage ratchet with a strict committed floor.
- Release governance: this changelog and policy, security-disclosure process,
  release checklist, and a CI-gated release workflow publishing to PyPI via
  OIDC trusted publishing with build-provenance attestation.
- Closed `termverify.enforcement-tier/v1` vocabulary (`os`, `constructive`,
  `delivered`) with a per-negotiation-path authorization matrix validated
  fail-closed during receipt binding, and a `DeliveryRecord` value for
  delivered-tier receipts.
- Opt-in `termverify.cooperation` module: `CooperationConstraintPorts`
  delivering all six non-terminal constraints at the `delivered` tier with
  the accepted per-constraint contracts (`TERMVERIFY_*` variables, `TZ=UTC0`
  UTC-only, sandbox-root working directory through an injectable directory
  probe, deny-only network), plus evidence-driven spawn: the ConPTY adapter
  assembles the child's environment overlay and working directory from the
  validated delivery records, with fail-closed disjointness invariants.
  Defaults are unchanged — `UnenforcedConstraintPorts` still fails closed.
- First fully successful verified terminal run as durable Windows-matrix
  integration evidence: cooperation ports with a host-owned sandbox, real
  ConPTY binding and normalizer, delivered-tier receipts, a cooperating
  subject echoing every delivered variable and its working directory into
  frames, subject exit via native end-of-stream, replay identity over the
  retained raw output, and forced-stop/deadline paths re-exercised.
- Closed `termverify.key-encoding/v1` registry: a digest-bound total mapping
  from each of the 934 valid `termverify.key/v1` chords to exactly one
  xterm-legacy normal-mode byte string or the explicit fail-closed verdict
  unencodable, with four disclosed legacy byte collisions. The ConPTY
  adapter's `dispatch` now executes encodable `KeyInput` chords by writing
  the registry bytes exactly once through the single-flight child write and
  running the standard quiescent epoch; an unencodable chord is a structured
  runtime failure (`{"unsupported": "key-encoding", "keys": [...]}`) before
  any child write, replacing the previous unconditional `KeyInput` rejection
  (`{"unsupported": "key-input"}`). Delivery only: no input-mode tracking,
  no key-support negotiation, no claim of subject decoding; processed-input
  signal bytes (for example `Control+c` → 0x03) are disclosed as
  subject-side interpretation.
- Real-child Windows-matrix evidence for the key-encoding registry: a
  cooperative raw-mode fixture subject (processed input, line input, and
  echo disabled; virtual-terminal input enabled) observes the exact
  registry bytes for one representative chord per encodable family class —
  including the signal byte 0x03 arriving as input under raw mode — echoes
  them into frames with replay identity, and the unencodable path stays
  fail-closed on the real adapter with OS-observed teardown.
- Phase 2 verification core, slice 1 (`termverify.recorder`): a public
  `TranscriptRecorder` that assembles the immutable adapter result values
  into `termverify.transcript/v1` records in occurrence order, enforcing
  the lifecycle shape at record time with structured
  `TranscriptRecorderError` values, and a minimal `run_scripted`
  orchestrator that drives one adapter through a scripted input sequence
  and returns validated transcript bytes plus the terminal outcome. Output
  passes only through the existing strict serializer; the codec remains
  the sole acceptance gate, no protocol member changes, and no scheduling,
  retry, timeout, or comparison capability is added. GlyphWright's spike
  transcript is imported unmodified as an external conformance fixture
  with provenance (`tests/fixtures/external/glyphwright-direct-spike/`).
- Phase 2 verification core, slice 2 (`termverify.comparator`): an exact
  transcript comparator — both inputs must pass the strict codec (an
  invalid side is a structured `TranscriptInputError`, never a comparison
  result), records compare by canonical semantic equality of envelope and
  payload over the full sequence with exactly one disclosed identity
  exclusion (envelope `run_id`), and the structured verdict lists every
  divergent record with its exact differing members in deterministic
  order. `render_report` renders a verdict as deterministic plain text
  (summary, first divergence position, bounded member-level diff); it is
  a rendering of the verdict only, never a second comparison
  implementation, and no test asserts stored report bytes as behavioral
  truth. No normalizers, tolerances, or per-scenario configuration exist;
  extending the exclusion set requires an owner-accepted amendment.
- Phase 2 verification core, slice 3 (`termverify.replay`): caller-bound
  transcript replay. `replay_transcript` takes a validated source
  transcript and a caller-supplied adapter, re-executes the source's
  configuration and input sequence in transcript order under the same
  single-flight discipline, records the new run with the slice-1
  recorder, and returns the new transcript plus the slice-2 comparison.
  Replay binding is disclosed, not enforced: the caller-supplied
  `termverify.replay-subject/v1` selector is recorded in the new
  transcript and selector agreement is reported, never a precondition. A
  source whose lifecycle ended in a failed or unsupported start replays
  nothing and reports that structurally; sources carrying input kinds the
  adapter contract cannot dispatch (`input.mouse`,
  `input.clipboard_set`) fail closed before any adapter call; early
  terminations disclose dispatched-versus-source input counts; a replay
  whose input sequence ends with the run still open is a structured
  error. No scheduling, retry, timeout, multi-subject, or differential
  semantics.
- Curated top-level adapter-author surface: every name in
  `termverify.adapter.__all__` and `termverify.direct.__all__` (the
  `Adapter`/`ConstraintPorts`/`DirectApplication` contract, `DirectAdapter`,
  and the immutable configuration/input/result/receipt/observation values)
  is now re-exported from `termverify` itself, identical to its module-path
  definition; both import styles are interchangeable and pinned by an
  import-surface test. Re-export only — no semantic change to the contract
  or the transcript protocol. Import-path commitment under the pre-1.0
  policy above: these top-level names and their module paths move only with
  a documented **Changed**/**Removed** entry. `termverify.conpty`,
  `termverify.cooperation`, and the verification core
  (`termverify.recorder`, `termverify.comparator`, `termverify.replay`)
  deliberately stay module-path-only. Documented for external adapter
  authors in `docs/developer-guide/adapter-authors.md`.

### Changed

- **Breaking (pre-release protocol amendment; transcript protocol stays
  v1):** every enforcement receipt (`SeedReceipt`, `ClockReceipt`,
  `LocaleReceipt`, `TimezoneReceipt`, `TerminalReceipt`, `FilesystemReceipt`,
  `NetworkReceipt`) now requires a mandatory `tier` from
  `termverify.enforcement-tier/v1`, and delivered-tier receipts must carry a
  `delivery` record (mandatory pairing in both directions). Migration: every
  external `ConstraintPorts`/`DirectApplication` implementation must add the
  tier to its receipt construction — direct applications state
  `constructive`, ports injected into the ConPTY adapter state `delivered`
  plus the delivery record, and the ConPTY adapter's own terminal negotiation
  states `os`. An unauthorized tier for a negotiation path is rejected as a
  structured `StartFailed`. Transcript `capability.result` records with
  `status: "enforced"` likewise require `tier` (and `delivery` exactly when
  the tier is `delivered`). No released artifact or recorded transcript
  carries the prior shapes.
- **Breaking:** `ConptyBindingPort.spawn` (and the native
  `termverify._conpty.ConptyChild.spawn`) gained keyword parameters
  `env_overlay` and `cwd`; external binding implementations must accept
  them. Omitting both preserves the prior spawn behavior exactly.
- **Breaking:** `DeliveryRecord` and transcript delivery validation now
  reject syntactically undeliverable environment entries — `=` or NUL in a
  variable name, NUL in a value or working directory — fail-closed.
