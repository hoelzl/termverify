# Issue 281 — POSIX EOS Exit-Capture Handover

## Handover metadata

- **Status:** PR review — [#301](https://github.com/hoelzl/termverify/pull/301)
  is open with all required CI checks green; the first adversarial review found
  two documentation inaccuracies that are being reconciled before delta review.
- **Issue:** [#281](https://github.com/hoelzl/termverify/issues/281)
- **Tracking:** [#285](https://github.com/hoelzl/termverify/issues/285)
- **Created:** 2026-08-04
- **Owner:** next TermVerify implementation session
- **Review required:** yes — fresh-context adversarial review must cover the
  exact PR head before merge.
- **Completion:** #281 is merged with its Linux/Python CI legs green, the issue
  is closed, tracker #285 records completion, and this handover is archived.

## Scope and non-goals

This transfer covers only #281: pin the POSIX binding's delayed
end-of-stream exit capture and remove the 30-second test cost that previously
proved nothing.

The candidate changes no production code and no public contract. It changes
one POSIX binding test, replaces a deliberately sleeping injected-fault child
with a short-lived child, and reconciles the active vertical handover with the
accepted sequence in #285. It deliberately does not fix or absorb the unrelated
ConPTY write-flood contradiction filed as #286.

## Local candidate

- **Integration checkout:**
  `C:\Users\tc\Programming\Python\Projects\termverify`
- **Worktree:**
  `C:\Users\tc\Programming\Python\Worktrees\termverify\issue-281`
- **Branch:** `fix/issue-281-pin-eos-exit-capture`
- **Implementation commit:** `8a0518a test: pin POSIX EOS exit capture (#281)`
- **Refreshed base:** `origin/main` at `b2c23cc`
- **Remote branch:** `origin/fix/issue-281-pin-eos-exit-capture`
- **Pull request:** [#301](https://github.com/hoelzl/termverify/pull/301)

Do not recreate the worktree or branch. Begin by inspecting them. The branch is
the only committed copy of the candidate.

## Verified candidate behavior

The modified EOS test patches the child's immediate `poll()` to keep returning
`None`, then drives the real PTY to end-of-stream. The bounded wait in
`_capture_exit_status_after_eos` reaps the real child and caches status `0`.
Because `poll()` remains patched, the public `exit_status` property cannot heal
a missing capture.

A targeted temporary mutation removed the call to
`_capture_exit_status_after_eos`. The focused test failed for the intended
reason:

```text
assert child.exit_status == 0
E assert None == 0
```

Restoring the call made the focused pair pass. The mutation was reverted and is
not present in Git.

Timing evidence on local WSL Linux:

- before: the injected-EIO/no-close test took **30.03s**;
- after: it took **0.05s**;
- full POSIX file: **69 passed, 1 skipped in 4.91s**;
- twenty shell-loop repetitions of the two focused EOS tests passed.

The cap is not the oracle. The cached exit transition is the oracle; the timing
only confirms that the test no longer spends the production 30-second bound.

## Validation already completed

All of the following passed on the committed candidate before the host-load
blocker appeared:

- `uv --no-config sync --all-groups --locked`
- focused WSL RED/GREEN and the full POSIX file;
- `uv --no-config run ruff check .`
- `uv --no-config run ruff format --check .`
- `uv --no-config run mypy src tests scripts`
- `uv --no-config run mypy --platform linux src tests scripts`
- `uv --no-config run pytest --cov --cov-report=term-missing`:
  **2091 passed, 70 skipped**, **93.64%**, in 266.82s;
- `uv --no-config run pre-commit run --all-files`;
- `uv --no-config run pre-commit run --hook-stage pre-push --all-files`;
- `uv --no-config build`.

The later `git push` reran the pre-push hook and failed in the unrelated Windows
ConPTY test
`test_write_flood_against_non_reading_child_never_blocked`. Two focused reruns
failed identically at the 60-second cap. The writer then observed
`ConptyClosedError` when teardown closed the binding. This contradiction is
recorded as [#286](https://github.com/hoelzl/termverify/issues/286), and #281 has
a status comment linking it. Do not bypass the hook or retry under the known
heavy load merely to obtain green output.

## Resume sequence

Resume began 2026-08-13. The replacement ConPTY progress test from #286 passed
on the refreshed branch, the focused POSIX pair passed in 0.86 seconds, the
full POSIX binding file passed with 68 tests and 2 platform/interpreter skips in
4.84 seconds, and a fresh mutation bypassing `_capture_exit_status_after_eos`
failed the focused oracle with `None != 0`. The mutation was reverted and the
tree was clean before the wider gate.

The exact pre-push stage then failed twice in succession at
`test_forced_close_waits_out_in_flight_large_write`, while that test passed
alone in 22.68 seconds. Both complete runs reached `_cancel_pending_io`'s
production safety disclosure after pending native I/O did not clear, with
2091 other tests passing and 70 skipped. This distinct order/load-sensitive
contradiction is [#299](https://github.com/hoelzl/termverify/issues/299). Per the
two-repeat stop rule, do not retry until lucky or bypass the hook; #299 must be
settled first. Issue #299 was resolved by PR #300 with a deterministic
state-transition oracle that removes native-write throughput from the close
ordering test.

On 2026-08-13, after merging PR #300 and refreshing this branch to `b2c23cc`:

- the focused POSIX pair passed in 1.05 seconds;
- the complete POSIX binding file passed with 68 tests and 2 skips in 6.47
  seconds;
- removing `_capture_exit_status_after_eos` again failed the focused oracle
  with `None != 0`, and restoring it passed;
- the formerly blocking ConPTY test passed in 0.75 seconds; and
- the exact pre-push stage passed, including the complete test suite.

## Current completion sequence

The candidate has been inspected, mutation-tested, fully gated, pushed, and
opened as draft PR #301. All required CI legs are green. The first fresh-context
review confirmed the executable evidence and requested only the documentation
corrections now present in the candidate.

1. Push the documentation corrections through the normal hook.
2. Wait for CI on the new exact head and obtain a clean delta review.
3. Verify GitHub's closing references still name exactly #281, mark PR #301
   ready, and merge with a merge commit.
4. Confirm #281 closed, update tracker #285 and the active vertical handover so
   #278 is the next actionable issue, archive this handover, update the handover
   index, pull `main`, and remove the issue worktree/local branch only after
   verifying the merge.

## Risks and non-negotiables

- Heavy-host timing is not product evidence. Resume under ordinary load rather
  than enlarging bounds or weakening tests.
- #286 remains a valid measured contradiction even if its focused test passes
  later on an idle host; do not close it merely to unblock #281.
- Do not alter `_CHILD_EXIT_WAIT_S` for test speed. The short-lived injected
  child avoids spending the production cap without changing production policy.
- Do not replace the cached-exit oracle with a later `exit_status` assertion
  whose `poll()` can independently reap the child.
- No protocol, taxonomy, release, or external-subject work is authorized here.
- After #281, tracker #285 sequences #278 next; do not jump directly to #269.

## Transition

- **PR review:** push the documentation corrections, wait for refreshed CI,
  and obtain clean delta review against the exact head before merge.
- **Become complete and archive** only after #281 merges and the tracker,
  active vertical handover, worktree, and branches are reconciled.
