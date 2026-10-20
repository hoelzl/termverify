---
name: adversarial-review
description: Run an independent adversarial review of a TermVerify pull request or of the repository, and file it when it must be durable evidence. Use before merging a nontrivial code, protocol, or governance change, and when asked for a review pass.
---

# Adversarial review

Filing conventions: [`docs/agent/reviews/README.md`](../../../docs/agent/reviews/README.md).
Past reports, for calibration: [`docs/agent/reviews/index.md`](../../../docs/agent/reviews/index.md).

1. **Pin the candidate.** Record the exact head SHA under review and verify
   it again at the end; findings against anything else are not evidence.
2. **Use fresh context.** Each reviewer starts without the author's
   conversation. Give each one an attack angle — typically one for code and
   test strength (would the tests catch a plausible mutation?) and one for
   whether every sentence in the changed prose is true against the code.
3. **Reproduce, don't assert.** A finding names a file and line, a failure
   scenario, and preferably a command or test that demonstrates it. Rank
   findings by severity.
4. **Fix and re-review.** The author fixes or explicitly disposes of every
   finding; a new round reviews the new head. Stop when a round finds
   nothing that blocks the merge.
5. **Record the verdict.** By default it lives in the pull request. File a
   report under `docs/agent/reviews/` when the pass must be durable evidence —
   a whole-repository pass, or a review a plan or handover requires — with the
   record
   frontmatter (`type: review`, `status: findings`, then `resolved` once
   every finding is dispositioned) and regenerate the indexes with
   `uv --no-config run python scripts/build_doc_indexes.py`. Never rewrite a
   filed report; corrections go in a re-review report that links back.

An agent may review and propose, but must not approve its own snapshot or
golden-master change (`docs/developer-guide/agent-workflow.md`).
