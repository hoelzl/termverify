# Issue 278 — POSIX teardown evidence handover

## Handover metadata

- **Status:** implementation candidate
- **Issue:** [#278](https://github.com/hoelzl/termverify/issues/278)
- **Tracking:** [#285](https://github.com/hoelzl/termverify/issues/285)
- **Created:** 2026-08-13
- **Owner:** next TermVerify implementation/review session
- **Review required:** yes — fresh-context adversarial review of the exact PR head before merge
- **Completion:** PR merged with Linux/Python CI green, issue #278 closed, tracker #285 advances to #283, and this handover is archived

## Scope

Pin the already-correct POSIX PTY teardown invariants that survived the round-3 mutation review of issue #274. This is a test-only slice: no runtime behavior, public API, protocol, or containment boundary changes.

The documented `setsid()` descendant escape remains a non-claim.

## Candidate evidence

Seven deterministic distinctions now cover the issue body and owner acceptance comment:

1. `test_close_waits_for_an_in_flight_write_before_releasing_descriptors`
   holds a write frame with scripted events and proves descriptor release stays unreachable until the write delivery event is set.
2. `test_forced_close_wakes_and_waits_for_io_before_terminating_the_session`
   records the exact wake → read delivery → write delivery → terminate order.
3. `test_abandoning_a_child_without_a_process_group_falls_back_to_its_pid`
   scripts `killpg(...)=ESRCH` and independently observes the pid fallback and reap.
4. `test_a_raising_close_still_releases_every_owned_descriptor`
   injects `EPERM` and asks the OS whether all three owned descriptors are invalid after the raise.
5. `test_a_forced_close_targets_the_owned_process_group`
   distinguishes the process-group signal from pid-only termination and retains the real exit record.
6. `test_a_release_only_close_of_a_live_child_is_refused`
   now proves the refusal is a no-op by continuing use and then performing a successful forced close with exit evidence.
7. `test_a_second_close_waits_for_the_first_to_capture_the_exit_record`
   replaces its 0.5-second scheduling window with leader/follower barriers and proves the follower blocks until exit capture completes.

Existing `test_a_blocked_read_is_woken_by_a_forced_close` continues to pin the real self-pipe wake path and its classification.

## Mutation record

Each listed mutation was applied to the production source and reverted by its exact inverse edit:

- delete `self._interrupted_write.wait(...)` → blocked-write test fails because close skips the delivery wait;
- move termination before wake/waits → ordering test fails at termination with an empty trace;
- delete `_abandon_spawned_child`'s `process.kill()` → fallback test fails `process.killed`;
- delete the `finally` descriptor release → exceptional-release test finds an open descriptor;
- replace process-group termination with `process.kill()` → group-target test records no `killpg` call;
- set `_closed` before raising the release-only refusal → strengthened refusal test cannot perform honest later teardown (the test cleanup was then made direct/bounded so this mutation cannot stall the suite);
- return immediately in the follower-close branch → follower barrier is never entered and the concurrent-close test fails.

Production `src/termverify/_posix_pty.py` is byte-identical to `origin/main` after restoration.

## Verification completed

- seven focused probes: pass;
- full POSIX binding file: 73 passed, 2 skipped in 3.85s;
- ten complete POSIX binding file repetitions: pass;
- Linux-platform mypy over `src tests scripts`: pass;
- Windows-host focused mypy/ruff/format checks: run during development; rerun after final formatting before commit.

## Remaining sequence

1. Run final focused/static checks after the last formatting edit.
2. Run the full repository gates on Windows and the full POSIX coverage/gate in WSL.
3. Commit and push through the real pre-push hook.
4. Open the draft PR with `Closes #278` and obtain fresh-context adversarial review.
5. Merge only at the exact reviewed, green head; then advance tracker #285 to #283 and archive this handover.

## Risks and non-negotiables

- Do not convert scripted barriers back into sleeps or throughput thresholds.
- Do not broaden containment to descendants that escaped with `setsid()`.
- Do not change production timeouts to satisfy evidence.
- Failure cleanup must join/reap helper activity before monkeypatch restoration.
- Any surviving mutation invalidates the candidate until its oracle is corrected.
