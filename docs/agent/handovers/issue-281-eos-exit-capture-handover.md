# Issue 281 — POSIX EOS Exit-Capture Handover

## Handover metadata

- **Status:** blocked — the candidate is complete locally, but the required
  pre-push gate is currently unreliable while the Windows host is under heavy
  load. Resume only after that external load has subsided.
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
- **Base:** `origin/main` at `3c5510d`
- **Remote branch:** absent at handover time; the pre-push hook rejected the
  push, so no draft PR exists.

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

After the UE5 rebuild and other heavy tasks have finished:

1. Inspect the candidate before doing anything:

   ```bash
   git -C 'C:\Users\tc\Programming\Python\Worktrees\termverify\issue-281' status --short --branch
   git -C 'C:\Users\tc\Programming\Python\Worktrees\termverify\issue-281' log -2 --oneline
   git -C 'C:\Users\tc\Programming\Python\Projects\termverify' status --short --branch
   ```

   Expect a clean issue worktree ahead of `origin/main`, a clean primary
   checkout on `main`, and no remote issue branch.

2. Run the formerly failing ConPTY test once on the now-idle host:

   ```bash
   uv --no-config run pytest tests/test_conpty_binding.py::test_write_flood_against_non_reading_child_never_blocked -q
   ```

   Run from the issue worktree. If it still fails, stop #281 again and
   investigate #286 as a separate issue; do not fold a Windows ConPTY change
   into this test-only POSIX candidate. If it passes, continue.

3. Re-run the focused POSIX pair in WSL and the exact pre-push stage. Confirm
   `termverify.__file__` resolves to this worktree if reusing a Linux venv.

4. Push normally — never with `--no-verify` — and verify the remote ref exists:

   ```bash
   git push -u origin fix/issue-281-pin-eos-exit-capture
   git ls-remote --heads origin fix/issue-281-pin-eos-exit-capture
   ```

   Prefer a tracked background push because the hook takes several minutes.

5. Open a **draft** PR from the primary checkout with explicit
   `--base main --head fix/issue-281-pin-eos-exit-capture`. The body must include
   `Closes #281`, the mutation RED, the restored GREEN, the before/after timing,
   the full gates, and the reason no changelog fragment is needed (test evidence
   and internal handover only; no user-visible behavior or API changed).

6. Wait for every claimed Linux/Python CI leg. Then run a fresh-context,
   read-only adversarial review against the exact PR head. The reviewer must
   independently verify that bypassing the capture fails the test, that the
   public `exit_status` oracle cannot self-heal through `poll()`, and that the
   faster injected-EIO leg still distinguishes close-caused from genuine EOS.

7. Resolve findings, re-gate substantive changes, mark the PR ready, and merge
   with a merge commit only after the exact reviewed head and CI are green.
   Verify GitHub's closing references name exactly #281 before merge.

8. Confirm #281 closed, check the #281 item in #285, update the active vertical
   handover to make #278 the next actionable issue if its wording is not already
   transition-safe, archive this handover, update the handover index, pull main,
   and remove the issue worktree/local branch only after verifying the merge.

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

- **Remain blocked** while the host is under known heavy load or if #286 still
  reproduces on an idle host.
- **Become active** when the idle-host ConPTY probe and required pre-push gate
  pass and the branch can be pushed without bypasses.
- **Become complete and archive** only after #281 merges and the tracker,
  active vertical handover, worktree, and branches are reconciled.
