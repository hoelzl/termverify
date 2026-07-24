# TermVerify — Adversarial Design & Implementation Review

- **Date:** 2026-07-24
- **Revision reviewed:** `main` @ `8f33e6c`
- **Method:** Four independent adversarial review passes (protocol/transcript core; adapters and runtime; test suite; design/docs/governance), followed by a verification pass that independently confirmed the highest-severity claims against the source. Scale context: `src/` ≈ 10,400 lines, `tests/` ≈ 20,400 lines, governance/knowledge docs ≈ 6,600 lines.

## Executive summary

The code, tests, and release engineering are strong — in places exceptional. The transcript validator survives genuinely hostile input, the Windows teardown engineering is careful, the test suite is one of the better ones I have audited (real property tests, external conformance fixtures, OS-level evidence instead of mock-level evidence), and supply-chain hygiene is above average for any project, let alone a pre-1.0 solo effort.

The problems cluster in three places:

1. **The runtime's central promise — "the abort deadline always produces a structured failure" — has real holes.** Protocol writes run outside the watchdog (a non-reading subject hangs the verifier forever), the read buffer is unbounded ahead of the line-size check, the ConPTY deadline re-arms per read, and POSIX containment is escapable in a way that permanently wedges the reader thread.
2. **Status-bearing prose has drifted from reality, including on the single most consequential fact.** README and SECURITY.md both deny the PyPI release that the changelog, tag, and handover record. For a project whose brand is truthful, replayable evidence, this is the most damaging finding in the review — not because the fix is hard, but because it demonstrates the prose-consistency problem the governance system cannot ratchet.
3. **Horizontal specification has outrun the vertical product.** Four of the README's six promised capabilities do not exist in `src/` (two are explicitly disabled), there is no POSIX PTY adapter for a terminal-verification library, no end-to-end example, and no usage code anywhere — while two frozen wire protocols, four closed registries, a redaction matrix, a baseline-approval sidecar format with zero baselines, and a custom-domain schema mirror all shipped.

Everything below is ranked and cited. Findings marked ✅ were independently re-verified against the source during synthesis.

---

## 1. Critical findings

### C1 — README and SECURITY.md deny the release that happened ✅

`README.md:35-36` ("no release is authorized and nothing is published to a package index") and `SECURITY.md:5-11` ("No released artifact is supported yet… `main` (unreleased)") both contradict `CHANGELOG.md:18` ("0.1.0 is published on PyPI (2026-07-19)"), the `v0.1.0` tag, and the active handover. The README was edited after the release without fixing this, violating AGENTS.md's own "update stale documentation in the same change" rule. A security policy is exactly the document that must track release reality — a vulnerability reporter today is told no supported artifact exists.

**Why critical:** the project ratchets code coverage to two decimal places while its two most visible governance documents misstate whether the product is released. It is the clearest evidence for finding D6 (governance surface exceeds prose-consistency capacity).

### C2 — JSONL protocol writes are outside the abort deadline; a non-reading subject hangs the verifier forever ✅

`src/termverify/jsonl.py:866-875` (`_run_epoch` write step), `:1028-1039` (hello write), `:1315-1316` (stop write); binding write at `src/termverify/_jsonl_pipe.py:285-296`. The watchdog is armed only inside `_read_message` (`jsonl.py:528`). Every wire write (`stdin.write` + `flush` on a blocking pipe) runs before any deadline exists.

**Failure scenario:** dispatch a `TextInput` whose serialized message exceeds the OS pipe buffer (~4–64 KiB; the protocol allows 4 MiB lines) against a child that is wedged or malicious and not reading stdin. `write_line` blocks indefinitely and `dispatch()` never returns — defeating the module's own promise ("the only wall-clock input is the mandatory abort deadline… always produces a structured failure"). The ConPTY adapter has the same shape (`conpty.py:702-708`) but at least discloses "conin writes showed no backpressure on the verified matrix" (`_conpty.py:40`); the pipe transport indisputably has backpressure and discloses nothing.

---

## 2. Major findings — runtime and adapters

### R1 — Unbounded read buffer ahead of the 4 MiB line ceiling ✅

`src/termverify/_jsonl_pipe.py:328-365` (`_read_line_tracked`) accumulates `read1(65_536)` chunks with no cap until a `\n` appears; `parse_message`'s `_MAX_LINE_BYTES` check (`control.py:613-623`) runs only after the full "line" is buffered. A subject streaming newline-free bytes at pipe speed grows the verifier's buffer to gigabytes within a generous deadline — the deadline bounds time, not memory. Fix is one comparison in the read loop (fail as peer-malformed once the buffer exceeds `_MAX_LINE_BYTES + 1`).

### R2 — ConPTY abort deadline re-arms per read; a marker-less trickle starves an epoch forever

`src/termverify/conpty.py:528-558` arms/disarms the watchdog per chunk read; `:609-621` loops per chunk. A subject emitting one byte every `deadline − ε` ms and never emitting the readiness marker means no single read exceeds the deadline, the marker never arrives, `dispatch()` neither completes nor aborts, and `chunks` (`conpty.py:694`) grows without bound. The JSONL adapter is structurally protected (its per-epoch diagnostic budget caps reads at ~101, `jsonl.py:784-796`); the ConPTY epoch needs a per-epoch deadline or a chunk/byte budget.

### R3 — `AssignProcessToJobObject` result ignored in the pipe binding; Windows containment can silently fail ✅

`src/termverify/_jsonl_pipe.py:266` discards the BOOL return (prototype at `:95-96` has `restype = BOOL` and no `errcheck`), while every sibling call — `CreateJobObjectW` (`:145`), `SetInformationJobObject` (`:157`), `OpenProcess` — checks and raises. An assignment failure proceeds as if contained, contradicting the spawn docstring ("no uncontained session is ever handed out", `:232-236`); forced close then `TerminateJobObject`s an empty job while the child tree survives. The ConPTY binding gets this right (`_conpty.py:214-216`) — this is a regression introduced in the slice-2 copy. `TerminateJobObject`'s return is also unchecked at `:516`.

### R4 — POSIX process-group containment is escapable and then defeats the deadline permanently

`src/termverify/_jsonl_pipe.py:517-519` (`os.killpg`), `:439-445`, `:597-607`. Forced close relies on the child tree's death closing the stdout write end. A subject that double-forks with `setsid()` leaves a descendant (holding the inherited write end) outside the process group: `killpg` misses it, the blocked `read1` never returns, `interrupted.wait(5.0)` times out, and closing an fd under a blocked POSIX read does not reliably unblock it. Net effect: `close(force=True)` "succeeds" while the adapter thread stays blocked forever — the deadline produced no structured failure. The Windows leg (job objects) is genuinely robust; the cross-platform parity claim ("identical observable outcomes on every platform", `jsonl.py:208-215`) overstates the POSIX leg. Deserves at minimum a disclosed boundary like ConPTY's assignment-window disclosure.

### R5 — Control codec accepts lone surrogates the transcript codec rejects; hostile input crashes the recording pipeline

`src/termverify/control.py:529,559` never rejects unpaired surrogates (`json.loads('"\\ud800"')` yields a lone-surrogate `str` from valid UTF-8 line bytes), but `src/termverify/transcript.py:260-265,307-309` mandates RFC 8785 canonicalization, which raises on them. Path: `parse_message` accepts → adapter maps into an `Observation` (`jsonl.py:467-498`) → recorder appends → `serialize_transcript` raises `TranscriptValidationError` — an uncaught exception discarding the whole recording, instead of the structured `peer-malformed` failure the design promises. This also falsifies the codec's own symmetry claim (parse admits what serialize rejects, `control.py:658-689`). Fix: reject unpaired surrogates in `_validate_json_value`.

### R6 — ConPTY chunk boundaries are OS-scheduling-dependent and the comparator has no normalization, so ConPTY replays essentially always diverge

`src/termverify/conpty.py:594-607` records one `Event("terminal.output", {"chunk": …})` per native read; `src/termverify/comparator.py:187-229` is exact equality with "no normalizers, predicates, tolerances" by owner decision. How the byte stream splits into chunks depends on pipe timing, so two behaviorally identical runs record different event sequences and compare divergent member-by-member — the replay-equivalence verdict is unattainable for the flagship adapter for reasons unrelated to subject behavior. Needs either a v1 equivalence rule for concatenated adjacent `terminal.output` events or an explicit disclosure that ConPTY runs compare divergent-by-construction; today neither exists.

### R7 — ConPTY read path receives per-read-decoded `str`; UTF-8 split across native reads can corrupt evidence (risk, not demonstrated)

`src/termverify/_conpty.py:384` — pywinpty's `PTY.read` returns already-decoded `str`. If the native layer's per-read decode lands mid-codepoint (large non-ASCII frame under load), the chunk carries U+FFFD replacements the binding can never repair (it never sees bytes). Consequences: corrupted `terminal.output` evidence, non-replayable divergence, and — if corruption lands inside the readiness marker (`conpty.py:140`) — an epoch that runs to the deadline. pywinpty's internal buffering could not be audited to prove a split occurs; this warrants either a volume multi-byte integration test or a disclosed boundary note.

---

## 3. Major findings — protocol, design, and governance

### P1 — protocol.md states a normative rule the runtime does not (and must not) implement

`src/termverify/transcript.py:125-127` (docstring) and `docs/knowledge/protocol.md:355-356` both state "a form carrying both `env` and an explicit `channel` member is invalid" — yet the runtime at `transcript.py:664-666` accepts `{"channel": "spawn-env", "env": {...}}`, and must, because that is the canonical post-amendment form emitters are required to produce (protocol.md's own channel table, line 341). An independent implementer reading the spec literally will reject every canonical spawn-env record the reference emitter produces. The docstring's "never relaxes acceptance" proof is also unsound as written (its parenthetical omits the spawn-env case). Fix is doc-side; the sentence presumably means "…and a channel other than `spawn-env`."

### P2 — `status: "enforced"` is the recorded wire value for constraints whose tier definition says "Nothing is enforced"

`protocol.md:306-308` mandates `capability.result.status` ∈ {`enforced`, `unsupported`} and calls `supported-but-not-enforced` invalid — then the `delivered` tier (`protocol.md:330`) is defined as "honoring it is subject cooperation. **Nothing is enforced.**" A delivered-tier constraint is thus recorded on the wire as `status: enforced`. The tier system was bolted on precisely to avoid overstatement, but the status vocabulary it qualifies still overstates — and it is now frozen into v1. Related seam: `protocol.md:302-303` still says "An adapter that cannot enforce a requested constraint must not claim a verified run," which cannot coexist with the shipped cooperation-tier semantics and the README/CHANGELOG "first fully verified terminal run" claim. One of the two must be amended.

### P3 — The v1 freeze fired prematurely and its status is nowhere plainly stated

The freeze trigger is "the first declared real client or supported external artifact" (`protocol.md:522-526`); the 0.1.0 PyPI publication pulled it with no known third-party consumer, and within days the key-registry punctuation widening (#155) required a recorded "one-time exception… It sets no precedent" (`protocol.md:528-538`). A governance rule that needs an exception on its first test was set too early. Compounding it, `protocol.md:516-518` still describes the inception phase in the present tense; no document plainly states "v1 froze on 2026-07-19 with the 0.1.0 publication" — the single most important protocol status must be inferred from a parenthetical.

### P4 — The frozen closed timezone registry paints v1 into a corner it gains nothing from

`termverify.timezone/v1` is a 374-line registry pinned to TZDB 2026c by tarball SHA-256, with a generator and tests — for a protocol in which only literal `UTC` can ever be enforced (`protocol.md:286-290`) or delivered (`cooperation-tier-constraint-ports.md:186`). The entire registry exists to validate requests that must then be refused. Because a v1 record carries no registry-version selector (`protocol.md:282-285`), any future TZDB zone requires a whole new transcript protocol version. The cost is currently zero only because the registry is unused — which is the argument that it should not have shipped in v1.

### P5 — Vision vs. reality: four of README's six promised capabilities do not exist

`README.md:11-18` promises, in the present tense: property/state-machine testing (no library support; `hypothesis` is dev-only, used solely in TermVerify's own tests), reviewed golden snapshots (`evidence-governance.md:184`: "No baseline files are committed until this design is accepted and its validator is implemented"), differential tests (explicitly a non-goal of the only active phase, `phase-2-verification-core-boundary.md:186-187`), and failure minimization / CI artifacts (nothing in `src/`; artifact uploads "remain rejected until separately enabled," `evidence-governance.md:154-155`). What exists — codec/validator, adapter contract, direct runtime, ConPTY adapter + VT normalizer, cooperation ports, recorder, exact comparator, replay, JSONL adapter — is real and substantial, but the README should say so in the future tense for the rest.

### P6 — No POSIX PTY adapter, no end-to-end example, no usage code

`architecture.md:74-75`: "There is no POSIX PTY adapter yet." Most TUIs and most CI run on POSIX; the Ubuntu CI legs cannot exercise a real terminal. There is no `examples/` directory (acknowledged as future work in `adapter-authors.md:86-89`) and zero usage code in the README. The closest thing to an external subject — the GlyphWright spike fixture — no longer passes the strict v1 codec per its own PROVENANCE.md, and the "first fully verified terminal run" is a Windows integration test against a fixture subject that echoes its own environment. The horizontal layers all shipped before the platform where the product would most plausibly be used.

### P7 — Premature governance machinery

Specific mechanisms that ran ahead of any use: the fully specified, validator-tested `termverify.baseline-approval/v1` sidecar format (9 members, dual review modes, digest-bound diffs; `evidence-governance.md:157-202`, 411 lines of validator tests) for a feature that is disabled with zero instances; the termverify.dev schema mirror (owner-registered domain, Pages deploy workflow, post-deploy byte verification, a 214-line ADR, site-assembly tests) for a document that, by the project's own words, nothing may fetch at validation time and no gate depends on; and a pattern of vocabulary admitted before any emitter exists (`delivered` tier, `wire-message` channel — disclosed, but a pattern).

### P8 — Governance surface has exceeded prose-consistency capacity

The process is demonstrably followed (issues, worktrees, TDD, adversarial reviews, changelog fragments) — and yet README, SECURITY.md, an ADR status line (`jsonl-control-transport.md:3` still "proposed" though slices 1–2 merged), and the active handover (stale 934-chord count vs. 1382) all drifted within days, because the same fact is restated in many places with no consistency check. Prose invariants — unlike the digest-bound registries — have no ratchet. Where prose *is* checkable (registry digests, schema byte-identity, frontmatter presence), it *is* checked and correct; every drift found is in prose that isn't. That is the actionable pattern: either mechanize the checkable status facts (release status, ADR statuses, counts) or state each exactly once and link to it.

### P9 — Authority polarity is inverted between the two protocols

AGENTS.md: "runtime validation in `src/termverify/transcript.py` is authoritative for protocol acceptance" and "treat executable checks and working code as authoritative over prose." `control-protocol.md:16-19`: "on any disagreement the codec is wrong and this document wins." Whatever the merits of doc-first for an unfrozen protocol, AGENTS.md states the opposite rule with no exception and its sources-of-truth table does not mention `control.py` at all.

---

## 4. Minor findings

**Runtime/adapters**

- `jsonl.py:866-875` — a write failure after a late deadline-timer close is classified `peer-lifecycle` without consulting `_deadline_closed`, unlike the read path (`:761-765`) and unlike ConPTY (`conpty.py:702-721`); the normative failure taxonomy attributes a deadline aftermath to the peer.
- `control.py:615` — CRLF rejection is a silent Windows-only subject killer: a subject using `print(json.dumps(...))` works on POSIX and fails every message as `peer-malformed` on Windows (text-mode stdout emits `\r\n`). The committed fixture quietly avoids this via `sys.stdout.buffer` (`tests/fixtures/jsonl_echo_subject.py:50`); the adapter-author guide mandates flushing but not binary writing. One sentence in the guide saves a debugging session.
- `_jsonl_pipe.py:315-318` — a second concurrent `read_line` (a caller contract violation) raises `JsonlChildClosedError`, which the adapter classifies as `peer-lifecycle` — pinning a harness bug on the subject. Also `:385-427`: the release-only-close refusal transiently sets `_closed = True`, so a concurrent read in that window spuriously fails despite the "true no-op" comment.
- `jsonl.py:798-807` — dead code: the `phase == "handshake"` branch of `_read_epoch` is unreachable (handshake is handled by `_start_handshake`), including the `MAX_STARTUP_DIAGNOSTICS` budget selection at `:747-749`; `:866` tests `if write is not None` on a non-optional parameter (verified ✅) — vestige of the ConPTY signature.
- `vt.py:212-227,159-162` — the fail-closed VT subset rejects `CSI > … c` (secondary device attributes) and raises on DEL, both of which real terminals tolerate; a Windows build whose conhost preamble includes secondary-DA turns every run on that host into `adapter-runtime-failed`. Cheap insurance: no-op both, or record a disclosed platform boundary.
- `_conpty.py:509-521` — if `cancel_io` cannot unstick a native call within 30 s, close raises and the blocked frame plus pinned handles leak permanently (partially disclosed). `_jsonl_pipe.py:551-574` — `exit_status`'s 2 s reap grace runs on every `run.failed` with a still-live child: an unconditional 2-second stall per failed run.
- `_conpty.py:329-335` — whether pywinpty quotes an argv[0] containing spaces (`C:\Program Files\subject.exe`) is unverified; if not, `CommandLineToArgvW` shifts every argument. An integration test spawning from a space-containing path would settle it.

**Protocol core**

- `transcript.py:117-142,306` — compat normalization (bare → `spawn-env`) runs *after* the budget checks and adds nodes/bytes, so a legacy record at exactly `_MAX_JSON_VALUES` parses but `serialize_transcript(parse_transcript(x))` raises: parse→serialize round-trip is not closed at the margin.
- `transcript.py:321` — the duplicate-member error interpolates an attacker-controlled key of up to ~4 MiB (raised inside `object_pairs_hook`, before string budgets apply), which may contain control/ANSI characters — an unbounded, log-injectable exception message. Truncate or omit the key.
- `transcript.py:326-351,390-391,431-454,884-934` — semantic rejections carry no record index or member context; six unrelated causes share the identical "run.started terminal is invalid" message. For a product whose point is human review of evidence, non-attributable rejections in a 10,000-record transcript are a usability defect, not a style nit.
- `__init__.py` — the *authoritative* codec (`parse_transcript`, `serialize_transcript`, `TranscriptValidationError`) is not exported while the *non-authoritative* schema aid is; the documented closed registries (`KEY_NAMES`, `is_key_chord`, `encode_key_chord`, `TIMEZONE_NAMES`) live only in underscore modules, forcing third-party adapter authors to import private paths or re-transcribe 99 entries from prose. Cheap to fix pre-1.0; later it ossifies.
- `transcript.py:56-63,354-370,731-737,769-772,1078-1089` — input-member closure enforced twice (three times for `input.stop`) by independent tables, and the manual-clock chain computed twice; per record kind the member list exists in four places (two code paths, JSON schema, protocol.md). Pure drift risk in a 1,200-line hand-rolled validator.
- Behavior note: RFC 8785 emits integral floats as integers (`10.0` → `10` → re-parses as `int`), and `_json_equivalent` (`transcript.py:1092-1106`) is type-strict, so in-memory records are not `_json_equivalent` to their own serialized round-trip. No acceptance impact today; worth a docstring caveat before someone builds on it.

**Tests / CI**

- `pyproject.toml:67` — the 586-line `_conpty.py` is unconditionally omitted from coverage even on Windows legs where it could be measured; its untested branches accumulate invisibly. A non-gating per-OS supplemental report closes this without breaking the cross-platform ratchet.
- `transcript.py:301` — the `UnicodeDecodeError` leg of `_parse_line` has no direct test (no invalid-UTF-8 fixture in `test_transcript.py`); the except-tuple is line-covered via the `ValueError` path so coverage cannot flag it. The control codec *does* test this edge (`test_control_coverage.py:111`).
- `.github/workflows/ci.yml` — no `timeout-minutes` on the quality/package/docs jobs despite a suite spawning children that sleep 600 s; a pathological hang costs the 360-minute default × 6 matrix legs.
- `test_conpty_binding.py:412,836`, `test_jsonl_binding.py:291` — race-window "arrangement" sleeps mean a guarded interleaving can silently stop being exercised on differently-timed runners (tests still pass; regression power quietly decays). All waits are deadline-bounded, so false failures are unlikely.
- Hypothesis runs unseeded (no registered profile, no CI database) — defensible for bug-finding, but an unstated tension with the determinism brand; a latent bug can surface as an apparently unrelated red build.
- Cross-test-module imports (`test_comparator.py:522,531`, `test_conpty_integration.py:73`) with no `conftest.py`/`tests/__init__.py` rely on pytest rootdir sys.path behavior.
- `tests/test_jsonl_coverage.py:382,398,497` — several failure-path tests arrange state by mutating private fields (`child._read_error`, `adapter._set_state("active")`) rather than driving the public protocol; assertions are still behavioral, but these break on renames rather than on behavior changes.
- `scripts/` (including the governance validators the repo relies on) are mypy-strict-checked and tested but excluded from coverage measurement (`pyproject.toml:61`).

**Docs/process hygiene**

- `jsonl-control-transport.md:3` still "Status: proposed" though slices 1–2 are merged and another ADR calls it "accepted" — in a system where status lines carry authorization force.
- `pre-release-boundary-hardening-handover.md:276` — stale "934-chord" count (1,382 since the punctuation amendment).
- `development.md:59` lists a `skills/` directory that does not exist; `control-protocol.md` frontmatter is bare `type: protocol` while every sibling has title/description/tags (the validator only checks non-empty `type`, so the OKF convention is enforced far more loosely than documented).
- `release.md` precondition says the gate includes workflow-security and dependency-vulnerability checks; `development.md:27-28` says those are CI-only and they run in a separate Security workflow — whether the release gate actually waits on it is unstated.
- `pyproject.toml` remains `0.1.0` post-publication, so every `main` build produces `termverify-0.1.0` artifacts byte-different from the PyPI 0.1.0; no dev-version scheme. The first release also required a degenerate "Bump 0.1.0 → 0.1.0" commit to trigger the workflow — the checklist was not exercisable as written.
- termverify.dev is a hijack surface: byte-identity is verified only at deploy time; a lapsed registration or DNS compromise could serve arbitrary bytes at the canonical `$id` URL indefinitely with no monitoring. Mitigated by the no-fetch rule — which the project cannot impose on third parties.
- Untracked `review-pr177-summary.md` / `review-pr177-rereview-summary.md` sit at the repo root, against the project's own documentation-placement table. (This document adds a third; file it or delete them together.)

---

## 5. Strengths (calibration — these survived adversarial probing)

1. **The transcript validator is genuinely hostile-input-ready.** Fixed ceilings checked in documented order, iterative traversal, byte-level lexical nesting pre-scan (verified sound: structural bytes cannot appear in UTF-8 continuation bytes), duplicate-member rejection at decode time, per-line byte-for-byte RFC 8785 round-trip, and dunder-hostile-subclass tests proving the validator never calls attacker-controllable methods. A schema-vs-runtime fuzz of the seed rule (25k samples including boundaries) found zero mismatches, and no schema-accepts/runtime-rejects divergence was found anywhere.
2. **Teardown engineering in both native bindings shows real Windows expertise.** Kill-first-then-bounded-wait ordering, detach-before-close so forced teardown never flushes into a dead pipe, kill-on-close job objects as a crash-safe sweep, cancel-until-quiet with traceback-pinning-aware handle release — the failure modes most codebases get wrong.
3. **The test suite is real, not theater.** 154 one-branch-per-expectation control-codec tests, failure taxonomy tested as a first-class contract, external conformance against a foreign-tool fixture with provenance, OS-observed exit codes instead of mocks for process-tree teardown (including grandchild reaping), genuine algebraic property tests (comparator reflexivity/symmetry, codec round-trip, replay faithfulness), a clean pragma audit, and zero network/clock/filesystem ambient state in the deterministic suite.
4. **Disclosure discipline is exemplary where it is deliberate.** The tier system, containment-retirement owner decision, "delivery is not compliance" refrain, ambient-env-inheritance disclosure, and key-encoding collision disclosures are more honest than nearly any comparable tool. Where the project errs it errs by *drift*, almost never by intentional overclaim.
5. **Supply-chain and release engineering are above average**: SHA-pinned actions throughout, OIDC trusted publishing with no stored tokens, tag-only-after-CI-green, build-provenance attestation, isolated wheel+sdist resource-contract checks, zizmor + OSV on schedule, `persist-credentials: false`.
6. **Decision records are high quality**: owners, dates, issues, considered-and-rejected alternatives with sufficient grounds, risks with mitigations, and explicit slice authorizations (the Phase 2 boundary document's scope control is a model).

---

## 6. Prioritized recommendations

**Now (hours, high leverage):**
1. Fix README and SECURITY.md release status; state plainly, in protocol.md, that v1 froze on 2026-07-19 with 0.1.0 (C1, P3).
2. Bound the JSONL read buffer at `_MAX_LINE_BYTES` (R1) and check `AssignProcessToJobObject`'s return like its siblings (R3) — both are one-comparison fixes.
3. Reject unpaired surrogates in the control codec's `_validate_json_value` (R5).
4. Correct the spawn-env sentence in protocol.md and the docstring (P1); update the JSONL ADR status; fix the chord count; add the CRLF/binary-stdout sentence to the adapter-author guide.

**Next (days):**
5. Put writes under the abort deadline in the JSONL adapter (and decide/disclose for ConPTY) (C2); add a per-epoch deadline or byte budget to the ConPTY read loop (R2).
6. Decide the ConPTY replay-equivalence story: chunk-concatenation equivalence rule or an explicit divergent-by-construction disclosure (R6).
7. Disclose the POSIX double-fork containment boundary (R4) and reconcile the `status: "enforced"` / "nothing is enforced" seam plus the "must not claim a verified run" sentence (P2) — these are protocol-truthfulness issues in a project whose product is truthfulness.
8. Export the authoritative codec and the documented registries from the public API (minor list, `__init__.py`) while it is still cheap.
9. Rewrite README's capability list in the future tense, or cut it to what exists (P5).

**Strategic (the design-level feedback):**
10. Stop adding horizontal specification until one vertical exists: a POSIX PTY adapter and a single `examples/` walkthrough that verifies a real (even trivial) TUI end-to-end would validate more of the design than any further registry, sidecar format, or mirror infrastructure — and would have caught C2, R2, and R6 as user-visible problems (P4, P6, P7).
11. Mechanize or de-duplicate status-bearing prose: the governance system checks what is checkable and every drift found was in prose that is not. Single-source the release status, ADR statuses, and registry counts, or add a validator for them — the project already has the pattern (P8).
12. Revisit the freeze posture before 0.2.0: the trigger fired on a self-published artifact with no consumers and required an exception within days. Consider an explicit "frozen for consumers, amendable by recorded owner decision until a third-party consumer is declared" tier instead of accumulating "one-time" exceptions (P3, F8-style pressure will recur).
