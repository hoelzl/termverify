# Adversarial review — PR #177 (issue #173 slice 2: real JSONL pipe binding)

- **Reviewed SHA:** `9fef2242f9a271cac48b7f26863c698b5d665f4f` (verified at start and end — no drift)
- **Tree OID:** `45adf055a447a9e2befdc5cd38ae1d12c61fc675` (verified at start and end — no drift)
- **Scope:** `git diff origin/main...HEAD` — `_jsonl_pipe.py` (new, 602 lines), `JsonlBinding` delegate in `jsonl.py` (+23), fixture subject, binding + integration test suites, adapter guide, changelog fragment.
- **Baseline re-run:** full suite green at HEAD (1705 passed, 1 skipped, ~3 min); the 15 new slice-2 tests pass in isolation (8 s).

## Working-tree note (not a candidate defect)

During review the worktree acquired an **uncommitted** diff adding `# pragma: no cover — Windows-only containment` markers to 7 platform-branch lines in `_jsonl_pipe.py` (a parallel agent's coverage work — same class as the shared-worktree hazard in the review playbook). HEAD is untouched; every finding below is against the committed SHA, and the pragma comments change no behavior. Whoever owns that edit should commit or discard it before merge — and note one is arguably wrong: `if os.name != "nt": return cls(process)` (spawn's POSIX early return) executes on *Windows* too in the sense that the branch is evaluated, but the `return` itself is POSIX-only; marking the whole line POSIX-only is fine, but the three `try:`/`job:`/`process_handle:` markers at `_jsonl_pipe.py:262-265` are on lines that *do* execute on Windows — those pragmas are incorrect and will mislead coverage. Verify before committing.

---

## Findings

### F1 (Major) — Refused release-only close leaves the binding unusable yet half-owned — candidate defect
`_jsonl_pipe.py:385-417`. `close()` sets `_closed = True` and unowns `_process`/`_job`/`_process_handle` **before** checking `live and not force` and raising `RuntimeError`. After the refusal:
- the child is still alive but the binding holds no reference — only the kill-on-close job keeps it from leaking (the child's tree is contained but *abandoned*: no way to read/write/terminate through the binding);
- `write_line`/`read_line` raise `JsonlChildClosedError` (the child is live and answering — "closed" is a lie about the OS state);
- `exit_status` returns `None` forever (capture requires `_process`);
- retrying `close(force=True)` hits the `self._closed` early-return at line 387-393: `_closing` is False (reset in the finally), so it returns `None` silently — **the tree can never be torn down through the binding again**; it dies only when the parent process exits.

Probe-verified: after refusal, `write_line` → `JsonlChildClosedError` while the child still echoes; second `close(force=True)` returns without killing; the child survived (killed only by job sweep at probe-process exit). The suite never notices because `test_release_only_close_of_a_live_child_is_refused` wraps the call in `_reaped` (whose `close(force=True)` is the silent no-op — the *test process exiting* is what reaps).

Honesty angle: the binding claims "never abandons a live tree" — post-refusal it has done exactly that (kept alive only by containment, unreachable). Fix direction: run the liveness check *before* mutating state, or restore `self._process/_job/_process_handle` and `_closed = False` in an `except` arm before re-raising, so a refused close is a true no-op and a later forced close works. This is also the reference-binding contract hosts will copy.

### F2 (Minor) — "unbuffered-friendly framing" documented, not delivered — docs defect
`docs/developer-guide/jsonl-adapter.md:43-44` claims writes are "newline-terminated and flushed per message; reads deliver one framed line per call" and the spawning example (`jsonl-adapter.md:30-34`) shows `argv=[sys.executable, "-u", "subject.py"]`. Nothing in the binding enforces or checks child-side flushing: a subject spawned without `-u` that doesn't flush per message will hang every epoch until the abort deadline, diagnosed only as `epoch-timeout`. The protocol doc's subject obligations (control-protocol.md:230-235) likewise omit the flush obligation. Suggest: state the per-message flush obligation explicitly in both docs (or keep the claim but add it to subject obligation #1).

### F3 (Minor) — Docs example omits mandatory constructor args — docs defect
`jsonl-adapter.md:26-34`: `JsonlAdapter(argv=..., binding=binding)` is missing the mandatory `abort_deadline_ms` and `constraint_ports` — the snippet raises `TypeError` as written. Copy-paste-hostile for the guide's primary audience.

### F4 (Minor) — `teardown-forced` taxonomy code unreachable — test-gap / pre-existing dead code
`jsonl.py:133` defines `_TEARDOWN_FORCED`, normative in control-protocol.md:225, but no site emits it (deadline paths emit `epoch-timeout`/`handshake-timeout`). Pre-existing from slice 1 (already an observation in the PR #175 review); slice 2 ships the real teardown and still never produces the code. Either wire it into the deadline-abort details or drop it from the taxonomy in a protocol amendment; as-is the taxonomy promises a code the adapter cannot produce.

### F5 (Minor) — Mutation-detection assertion proves less than the docstring claims — test-gap
`tests/test_jsonl_integration.py:354-362`. The mutation flips one digit inside the recorded `frame.columns` of the resize observation, and `compare_transcripts(first, mutated)` is asserted non-equivalent. This proves the comparator compares *payload bytes*, but not specifically that it detects divergence *delivered by the transport* — the comparator would behave identically for a hand-built transcript. The genuinely transport-pinning half is the byte-identity of two real recorded runs (line 328), which *is* strong. Downgrade the docstring's "genuinely consuming the transport's transcript" claim or strengthen by mutating a transport-emitted field the normalizer could theoretically wash out (e.g. an observation event payload). Non-blocking.

### F6 (Minor) — Real `time.sleep(0.2)` in the interruption test — flakiness shape
`tests/test_jsonl_binding.py:276`: the `sleep(0.2)` after the reading-started event is the documented "event fires before the syscall blocks" mitigation, but on a loaded CI runner the read may still not have entered `read1` — the close then completes before the read starts and the test either passes vacuously (read hits the closed flag → same `JsonlChildClosedError`, assertion still true) or, worse, the read raises before blocking and the test's intent (syscall interruption via child death) goes unexercised while still green. The assertion shape can't distinguish the two paths. Acceptable as-is (both outcomes are contract-correct), but the test name over-promises; consider asserting the close also *killed* the child while the read was in flight (it does: `exit_status == 15` and `_wait_for_exit`) — already covered. Observation only.

### F7 (Observation) — Watchdog-expiry vs natural-delivery race resolved toward natural exit in 8/8 probe runs
Probe: timer armed at 30 ms, natural exit written at 15 ms. All 8 runs delivered the natural `JsonlEndOfStreamError` rather than the deadline abort. That's the *favorable* outcome but it's scheduling luck, not a guarantee — if the timer wins, the adapter correctly aborts (re-check of `expired` after disarm, `jsonl.py:775-784`). Both outcomes are honest; no defect. The adapter's contract ("deadline fired ⇒ no successful epoch") is pinned by slice-1 fake-watchdog tests.

### F8 (Observation) — Fixture's canonical serialization is a strict subset of the codec's — safe today, unenforced
Fixture `_emit` uses `json.dumps(separators=(",", ":"), sort_keys=True)`; probe-verified byte-identical to `rfc8785.dumps` for the fixture's entire value vocabulary (ASCII strings, ints, bools, null, nested containers). Divergence appears for non-ASCII text (fixture escapes, RFC 8785 emits raw UTF-8) and float forms (`1.0` → `1.0` vs `1`); the fixture emits neither. If a future fixture edit adds either, the wire silently becomes non-canonical — and the adapter's parser *accepts* non-canonical-but-valid JSON (probe: rejection is for CR/BOM/framing, not canonicality), so nothing would catch it. Consider a one-line comment in the fixture or a suite assertion that a fixture-emitted line round-trips `parse_message` (it would still pass — the pin would need a canonical-equality check against `serialize_message`). Test-gap, low priority.

### F9 (Observation) — POSIX branch sound by inspection
`os.killpg(process.pid, 9)` targets the child's own group (`start_new_session=True`), `ProcessLookupError` suppressed (already-dead race), exit record `-9` via `process.wait`. Correct. One caveat inherited from POSIX semantics: if the child double-forks a daemon that calls `setsid()`, it escapes the group — same disclosed-boundary class as the Windows microseconds-wide pre-assignment window (`_jsonl_pipe.py:18-21`). Both are documented containment boundaries, not defects.

### F10 (Observation) — ctypes prototypes, handle pairing, stdin detach — verified correct
All kernel32 prototypes have explicit `argtypes`/`restype` with `wintypes.HANDLE` (no truncation). `CreateJobObjectW`/`OpenProcess`/`CloseHandle` pairing: handles closed exactly once in `close()`'s finally (guarded by unowning under the lock); spawn-failure path closes both after `process.kill()/wait()`. The buffered stdin writer is detached before any close on both the forced path (`_terminate_tree`, line 494-496) and the final cleanup (`_close_pipes`, line 588) — the flush-on-wedged-child deadlock is designed out. Job assignment failure after `CreateProcess` fails closed (`spawn` lines 264-277). The `_wait_for_handle` + bounded `process.wait()` pair handles the signaled-vs-reaped gap correctly.

---

## Concurrency/lifecycle verdict (hunt area 1)

The close serialization is sound: single-flight read tracking with `_interrupted_read`, bounded 5 s delivery wait without holding the lock, `_close_done` for second-close waiters, `_closing` reset in `finally` so a crashed close doesn't wedge the event. Probe-verified: 4-thread concurrent close ×5 runs — exactly one teardown, `exit_status == 15` every time, no hangs; second close during an in-flight teardown blocks until `exit_status` is consultable; close-during-blocked-read returns promptly with the reader getting `JsonlChildClosedError` (never EOS); buffered-but-undelivered lines after a concurrent close are correctly dropped when the closed flag wins the race. No unbounded hang path found: every wait is bounded (`_CHILD_EXIT_WAIT_S=30`, `_READ_DELIVERY_WAIT_S=5`, `_REAP_GRACE_S=2`). No live-tree leak on any probed path except F1's post-refusal abandonment (contained, but unreachable — dies only at parent exit).

## Honest-records verdict (hunt area 2)

No fabricated exit status possible: `exit_status` is written only from `process.wait()`/`poll()` results; forced records are the OS-observed 15 (verified live: `exit_status == 15` after job termination) with `-9` on POSIX by `waitpid` semantics; the 2 s reaping grace on a claimed exit converts the OS gap into a bounded wait and reports `None` (fail-closed) after it — never a guess. Refusal semantics exist but are the F1 defect (refusal destroys usability). Adapter-side: `run.finished` with no OS record → `peer-lifecycle` failure (`jsonl.py:669-676`); claimed-vs-observed mismatch disclosed as a diagnostic with the OS record winning (`jsonl.py:686-703`). Sound.

## Protocol conformance verdict (hunt area 4)

The fixture's wire is codec-compatible canonical JSON for its full vocabulary (probe P4). The adapter's parser enforces framing (exactly-one-LF, no CR, no BOM — probes P1-P3), the envelope closure, kind vocabulary, and budgets. The integration test pins canonical byte-identity across two recorded runs through `run_scripted` + `compare_transcripts`. A subtly-wrong wire in the *fixture* (non-ASCII/floats) would not be caught — F8. The epoch close semantics (exactly one observation or terminal per epoch; exited-process evidence forbidden in epoch observations) are pinned by `_read_epoch`/`_run_stop_drain` and exercised live.

## Test strength verdict (hunt area 5)

83 assertions across the two new files; type-exact (`type(x) is Started`) rather than isinstance-only almost everywhere; the one regex `match="release-only close"` has no metacharacters. Natural-exit coverage is present (exit 3, exit 7, EOS-after-buffered-lines). Process hygiene: every test uses `_reaped`; post-suite leak checks found no survivors attributable to the candidate. Weak spots: F5 (mutation assertion), F6 (vacuous-pass shape), and the F1-hiding `_reaped` no-op in the refusal test.

## Security scan

Clean. No credentials, tokens, or secrets; no network I/O; the only `subprocess` executions are the binding's validated-argv spawn (`shutil.which` + list argv, `# noqa: S603` justified — `JsonlBinding` spawns host-supplied commands by design, same trust model as the ConPTY binding) and test-side liveness probes via `powershell Get-Process` (test-only, pid-interpolated ints). The fixture's `time.sleep(600)` is intentional hang simulation. `stderr=DEVNULL` on the child is a documented trade-off (subject stderr is not protocol; control-protocol.md:37-39) but does mean a crashing fixture hides its traceback — debugging friction, not a security issue.

---

## Final verdict

**CHANGES-REQUESTED** — one Major:

1. **F1 (Major, `_jsonl_pipe.py:385-417`):** make the refused release-only close a true no-op — check liveness before unowning, or restore ownership/state on the refusal path — so the binding stays usable and a subsequent `close(force=True)` can still tear the tree down. Add a test that continues I/O after the refusal and then force-closes successfully.

Everything else (F2-F6) is Minor docs/test-strength polish suitable for the same fix commit or follow-ups. The concurrency core, honest-records machinery, Windows containment, and protocol wiring are probe-verified sound; the suite is green at the reviewed SHA.

