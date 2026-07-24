# Adversarial RE-review — PR #177 (issue #173 slice 2: real JSONL pipe binding), successor candidate

- **Reviewed SHA:** `40ff752d815e4e3bee621cc0bda33f51d9a42a5e` — `git rev-parse HEAD` verified at start AND end: **no drift**
- **Tree OID:** `a1d7c34c7b896440c9fc19314a1cadbefae872dd` — verified at start AND end: **no drift**
- **Commits under review:** 2 on top of the prior candidate `9fef224` — `1f2c198` (refusal no-op + cross-platform coverage), `40ff752` (cross-platform mypy)
- **Scope:** `git diff origin/main...HEAD` — `_jsonl_pipe.py` (new, 619 lines), `JsonlBinding` delegate (+23), fixture subject, binding + integration suites, three docs, changelog fragment, one mypy override in `pyproject.toml`
- **Baseline re-run at the reviewed SHA:** full suite **1705 passed, 1 skipped** (~3:05); slice-2 files 15 passed in isolation; `ruff check` + `ruff format --check` clean; `mypy src tests scripts` clean (65 files). All **10 required CI checks GREEN on the exact reviewed SHA** (ubuntu+windows × py3.12/3.13/3.14, docs, packages, security), confirmed via `gh pr checks 177`.

---

## Prior-review dispositions (F1–F6) — verification results

### F1 (was Major) — Refused release-only close half-closed the binding → **RESOLVED, probe-verified**
`_jsonl_pipe.py:410-427`. The liveness check now runs **before** the try block, and the refusal path restores `_process`/`_job`/`_process_handle`, `_closed=False`, `_closing=False` under the lock before raising. The extended test (`tests/test_jsonl_binding.py:206-221`) pins the contract: post-refusal reads still deliver, echo still works, a later `close(force=True)` tears the tree down honestly (`exit_status == 15` / `-9`), and a further close returns immediately.

Independent probes (real subprocesses, run from outside the worktree against the worktree's `src`):
- **P1 refusal-no-op:** I/O after refusal works; forced close captures `exit_status == 15`; child verified DEAD at OS level (PowerShell `Get-Process`), not abandoned. PASS.
- **P2 refusal-during-blocked-read:** a `read_line` blocked in the syscall across the refusal survives — subsequent `write_line`/`read_line` delivers `TV_ECHO:after-refusal`; no interruption, no corruption. PASS. (Justified by the code: the refusal path restores state before `_terminate_tree` can ever run, so no read can be interrupted; the read buffer and single-flight flags are untouched.)
- **P3 forced-close-after-refusal-with-blocked-read:** refusal, then blocked read, then `close(force=True)` → reader gets `JsonlChildClosedError` (never EOS), `exit_status == 15`, child dead. PASS.
- **P4 concurrent-close stress:** 4 threads × 5 runs — exactly one teardown, uniform `exit_status == 15`, no hangs, child dead every run. PASS.
- **P5 second-close-blocks:** a second close arriving mid-teardown waits on `_close_done`; `exit_status` is consultable on return. PASS.
- **P6 double-refusal-then-force:** two consecutive refusals leave state coherent; I/O works; forced close honest. PASS.

### F2 (was Minor) — Flush obligation undocumented → **RESOLVED**
`jsonl-adapter.md:46-52` now states the subject's per-message flush obligation explicitly (with the `epoch-timeout` misdiagnosis warning); `control-protocol.md` adds it as subject obligation **#2** with the same content. Consistent wording both places.

### F3 (was Minor) — Docs example omitted mandatory constructor args → **RESOLVED, verified against the real API**
`jsonl-adapter.md:30-36` now shows positional argv, `abort_deadline_ms=60_000`, and `constraint_ports=CooperationConstraintPorts({...})`. Cross-checked member-for-member against `JsonlAdapter.__init__` (`jsonl.py:366-383`) and `CooperationConstraintPorts.__init__` (`cooperation.py:105-124`): the example as written type-checks and runs.

### F4 (was Minor) — `teardown-forced` taxonomy code unreachable → **NOT ADDRESSED (unchanged, non-blocking)**
`jsonl.py:133` still defines `_TEARDOWN_FORCED`; `control-protocol.md:225` still lists `teardown-forced` as normative; no site emits it (deadline paths emit `epoch-timeout` with the forced exit record in the terminal result). Second recurrence — per the review playbook this escalates in wording: the taxonomy promises a code the adapter cannot produce, and slice 2 shipped the real teardown paths without wiring it. Still Minor, but it now needs a tracked decision (wire it into the deadline-abort `details`, or amend the taxonomy in a follow-up) before the protocol text freezes further meaning around it.

### F5 (was Minor) — Mutation-detection assertion over-claimed → **RESOLVED**
`tests/test_jsonl_integration.py:354-358` comment now states exactly what is pinned (payload-byte comparison, not washing) and names the transport-pinning half (byte-identity of two real recorded runs, line ~351). Honest claim, no code change needed.

### F6 (was Minor) — `time.sleep(0.2)` vacuous-pass shape → **RESOLVED as documented**
Unchanged code; the prior review already classified it as observation-level (both outcomes contract-correct, and the teardown assertion `exit_status == 15` is pinned independently). No action required.

---

## New-change review (the fix commits)

**Refusal restore logic — sound.** The restore runs before any termination path can execute, so no read can have been interrupted (probe P2 confirms). One theoretical note: a *concurrent forced close* arriving inside the microseconds-wide pre-restore window waits on `_close_done`, which is only ever set by a close that reaches the `finally` — after a refusal the waiting thread parks until process exit. Exploiting it requires a host that fires `force=False` and `force=True` closes concurrently at the same instant, which contradicts the adapter's lifecycle (the adapter issues exactly one close per binding). Observation only, not a defect.

**Coverage pragmas — honest, not masking.** Six pragmas, all at `if` granularity on genuinely platform-conditional clauses (`_jsonl_pipe.py:75, 260, 458, 462, 512, 527`). The prior review's misapplied-markers concern is moot: those lines were restructured into the new `sys.platform == "win32"` blocks. Probe-verified the multi-line-condition form (`):  # pragma: no cover`) excludes the whole `if` including its branch arc under `--branch` coverage (`Branch 0` on the excluded clause) — no partial-branch debt is being hidden. The Windows legs ARE exercised on the Windows CI legs (all green), so these are platform-conditional exclusions, not dead code.

**`sys.platform == "win32"` switch + `warn_unreachable` override — sound on both platforms.** The switch makes mypy's platform narrowing agree with the code: on Windows the POSIX fallthrough (`return cls(process)`, the `killpg` leg) is unreachable, and a POSIX mypy sees the ctypes block as unreachable. The `pyproject.toml` override is module-scoped to `termverify._jsonl_pipe` only, with a comment documenting exactly why. No names leak across the boundary (`os.killpg` carries the targeted `type: ignore[attr-defined,unused-ignore]`). Verified mypy clean on Windows locally; the six Ubuntu CI legs green confirm the POSIX side.

**Docs/protocol renumbering — correct.** New obligation #2 inserted, #3–#7 renumbered consistently; no other doc cross-references those obligation numbers (checked: the obligations list is only referenced as "subject obligations", never by number).

---

## Original dimensions re-checked on the final diff

- **Concurrency/lifecycle:** close serialization (P4/P5), interrupted-read delivery (P3), bounded waits everywhere (`_CHILD_EXIT_WAIT_S=30`, `_READ_DELIVERY_WAIT_S=5`, `_REAP_GRACE_S=2`), no unbounded hang path, no tree leaks on any probed path (OS-level death verified per probe). Sound.
- **Honest records:** `exit_status` only ever from `process.wait()`/`poll()`; forced records are the OS-observed 15 (probes) / `-9` POSIX; refusal fabricates nothing and now abandons nothing. Sound.
- **Windows correctness:** ctypes prototypes with explicit `argtypes`/`restype` throughout; handle pairing closed exactly once in `close()`'s finally; spawn-failure path closes both handles; stdin detached before every close path (the wedged-child flush deadlock is designed out). Unchanged from the first review's verified-sound verdict; re-confirmed by probes.
- **Protocol conformance:** unchanged since the first review's sound verdict (canonical wire, framing enforcement, epoch close, replay identity pinned by the integration suite).
- **Test strength:** the extended refusal test now pins the no-op contract with post-refusal I/O and honest forced teardown — exactly the test the first review demanded. The `_reaped` cleanup wrapper no longer masks anything (its forced close is now a real no-op-after-settled, asserted in the test itself).
- **Docs/changelog:** fragment accurate (claims match shipped behavior); adapter-authors.md link correct; guide example runnable.
- **Security scan of added lines:** clean — no secrets, no network I/O, no new injection surface; the only subprocess spawn remains the validated-argv binding spawn (`# noqa: S603` justified, host-supplied commands by design).

## Findings (this pass)

1. **F4-recurrence (Minor, docs/test-gap):** `teardown-forced` taxonomy code still unreachable — second slice in a row. Needs a tracked decision (wire or amend), non-blocking for this PR.
2. **Observation:** refusal-vs-concurrent-forced-close window parks the forced close until process exit; unreachable through the adapter's single-close lifecycle. Documented here for the record; no fix needed.

---

## Final verdict

**READY-TO-MERGE** — the F1 Major is genuinely fixed and probe-verified (including the demanded "later forced close after a refusal still tears down honestly" property); F2/F3/F5 dispositions are real and verified against the code; the new coverage pragmas are honest and branch-debt-free; the mypy override is sound on both platforms; all 10 CI checks are green on the exact reviewed SHA; full local suite 1705 passed. F4 remains a Minor follow-up (unreachable taxonomy code, second recurrence — file an issue or wire it before further protocol text builds on it).
