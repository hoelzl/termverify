# Agent Prompt: Adversarial Review Remediation Kickoff

> **Status:** delivered by
> [PR #57](https://github.com/hoelzl/termverify/pull/57) on 2026-07-16. This
> prompt is retained as the Slice 1 execution record; continue from the active
> handover and ordered plan rather than rerunning it.

## Assignment

Begin implementation of the active
[`adversarial-review-remediation-handover.md`](../handovers/adversarial-review-remediation-handover.md)
from current `main`. Do not stop after restating the plan: reproduce and deliver
**Slice 1, the acronym-prefixed sensitive-key security fix**, as one complete,
reviewable TDD change. Stop only at a real blocker or the candidate-bound review
boundary described below.

The project maintainer accepted the recommended evidence policy on 2026-07-16:
safe persistence must deterministically transform every unbounded semantic
string and every `x-` member name while preserving protocol structure and
cross-field invariants. Grammar-constrained envelope, locale, replay-selector,
numeric, and enum fields remain intact without free-text credential scans.
Credential patterns are secondary defense. This decision unblocks the later
semantic-redaction slice, but **do not bundle that larger slice into the first
acronym-fix PR**.

## Repository and isolation

- Repository: `C:\Users\tc\Programming\Python\Projects\termverify`
- Keep the primary checkout as the integration/planning checkout; do not develop
  directly in it.
- Create one external sibling worktree under
  `C:\Users\tc\Programming\Python\Worktrees\termverify\` and one focused
  `fix/` branch from current `origin/main`.
- Give every coding or review agent the worktree's explicit absolute path.
- Run `uv --no-config sync --all-groups --locked` once in the new worktree.
- Before creating the worktree, inspect `git status`, `git branch`, `git
  worktree list`, current GitHub issues/PRs, and `origin/main`. Do not overwrite,
  move, commit, or absorb unrelated primary-checkout changes.
- The review, handover, plan, and this prompt may initially be uncommitted in the
  primary checkout. If they are absent from the new worktree, read those exact
  files from the primary checkout as read-only source material. Do not copy them
  into the implementation PR merely to make them visible.

## Read first

1. `AGENTS.md`
2. `README.md`
3. `docs/knowledge/index.md`
4. `docs/knowledge/evidence-governance.md`
5. `docs/developer-guide/agent-workflow.md`
6. `docs/agent/handovers/adversarial-review-remediation-handover.md`
7. `.hermes/plans/2026-07-16_215137-adversarial-review-remediation.md`
8. Both `docs/agent/design/adversarial-correctness-and-code-quality-review-*-2026-07-16.md` reports
9. `src/termverify/evidence.py`
10. `scripts/validate_evidence_governance.py`
11. `tests/test_evidence.py`
12. `tests/test_validate_evidence_governance.py`

Trace the real governance call path before editing. Treat source and executable
checks as authoritative over prose if they disagree, and report any conflict
before changing accepted policy.

## First implementation slice: acronym-prefixed sensitive keys

### Required behavior

The sensitive-key tokenizer must recognize acronym-to-capitalized-word
boundaries as well as the existing lower/digit-to-upper boundary. At minimum:

| Key | Required parts/result |
| --- | --- |
| `api_token` | sensitive |
| `myTOKEN` | sensitive |
| `authorization` | sensitive |
| `APIToken` | `api`, `token`; sensitive |
| `AWSSecret` | `aws`, `secret`; sensitive |
| `DBPassword` | `db`, `password`; sensitive |
| `GHToken` | `gh`, `token`; sensitive |
| `XToken` | `x`, `token`; sensitive |

Include non-sensitive acronym/camel/snake/kebab controls so the fix does not
classify every capitalized identifier as secret.

### Strict TDD sequence

1. Add focused parameterized tests in `tests/test_evidence.py` for the complete
   table and controls.
2. Add integration tests in `tests/test_validate_evidence_governance.py` proving
   that the **real committed-fixture governance path** rejects synthetic AWS/JWT
   credential-shaped values beneath `APIToken` and `AWSSecret`. Construct these
   values inside tests; do not add them to committed `.jsonl` fixtures.
3. Run the focused tests and record which cases are genuine behavioral RED
   failures. Do not count setup errors or exception-message mismatches as TDD
   evidence.
4. Make the minimum production change in `src/termverify/evidence.py`: extend
   `_CAMEL_CASE_BOUNDARY` with the standard acronym boundary. Do not expand the
   credential pattern list or refactor semantic redaction in this first slice.
5. Re-run both focused modules and the full evidence/governance test subset.
6. Inspect sibling key paths to confirm the same tokenizer protects
   `redact_evidence()`, safe persistence, and the fixture governance script. Do
   not add duplicate path-specific fixes.

### Focused verification

```bash
uv --no-config run pytest tests/test_evidence.py -q
uv --no-config run pytest tests/test_validate_evidence_governance.py -q
uv --no-config run pytest tests/test_evidence.py tests/test_validate_evidence_governance.py -q
```

## Scope controls

### In scope for this first PR

- `_CAMEL_CASE_BOUNDARY` correction;
- direct key-tokenization/redaction regressions;
- real governance integration regressions;
- a narrowly necessary documentation correction only if current accepted prose
  would otherwise be false.

### Explicitly deferred to later handover slices

- whole-record `sk-` false-positive removal;
- deterministic transformation of UI IDs/roles/mode, input keys, terminal
  capabilities, codes, signal values, and `x-` names;
- AWS/JWT/Slack/PEM pattern expansion;
- serializer runtime JSON-shape and numeric-category hardening;
- diagnostic-time aggregate invariants;
- direct-runtime result consolidation and abort-detail preservation;
- shared vocabulary/locale modules;
- `_validate_lifecycle()` decomposition;
- atomic evidence replacement and the still-open `fsync` decision.

Do not introduce Pydantic, `attrs`, `msgspec`, implementation inheritance,
validator classes, a generic utilities module, dynamic registration, a protocol
version change, exhaustive schema work, sensitive persistence, or automatic
baseline updates.

## Review and delivery boundary

1. After focused tests pass, run the complete local gate:

   ```bash
   uv --no-config sync --all-groups --locked
   uv --no-config run pytest --cov --cov-report=term-missing
   uv --no-config run ruff check .
   uv --no-config run ruff format --check .
   uv --no-config run mypy src tests scripts
   uv --no-config run pre-commit run --all-files
   uv --no-config run pre-commit run --hook-stage pre-push --all-files
   uv --no-config build
   git diff --check
   ```

2. Inspect the complete diff for scope creep and credential-like literals in
   persistent fixtures.
3. Commit the coherent slice on its dedicated branch. If GitHub access is
   available, create or link one focused issue and open a **draft** PR.
4. Freeze the candidate head SHA/diff and obtain fresh independent human-readable
   review focused on security behavior, regression completeness, and accidental
   over-classification. A green CI run is not a substitute.
5. Reconcile every review finding. If the candidate changes materially, rerun
   the final review on the new candidate and verify CI belongs to the current PR
   head SHA.
6. Do not merge, mark the PR ready, or begin Slice 2 until the review result is
   reconciled and the maintainer has the candidate evidence. Report:
   - branch/worktree and candidate SHA;
   - genuine RED cases observed;
   - exact files changed;
   - focused and full-gate results;
   - independent-review disposition;
   - issue/PR URLs if created;
   - any blocker or source-of-truth conflict.

The next implementation session should resume from the handover's ordered plan,
not infer adjacent scope from this small regex change. The accepted semantic
transformation policy is durable context for the later evidence-hardening slice;
it does not authorize bundling that slice into this kickoff PR.
