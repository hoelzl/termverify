# Review Reports

Durable records of adversarial and independent reviews live here: pre-merge
PR reviews, re-reviews of fix candidates, and broader whole-repository
passes. Filing them under `docs/agent/reviews/` keeps them out of the
repository root and separates them from the design decisions under
`docs/agent/design/` that a review may reference.

## Filing a report

- One report per review pass. Name it after the reviewed target:
  `review-pr<N>-<slug>.md` for a pull request (for example
  `review-pr177-summary.md`, `review-pr177-rereview-summary.md`), or
  `<scope>-review-<YYYY-MM-DD>.md` for a broader pass (for example
  `adversarial-review-2026-07-24.md`).
- Every report names the exact commit SHA it reviewed; findings against
  anything else are not review evidence.
- Reports are point-in-time records, like handovers: file the report as
  produced and do not rewrite it afterwards. Corrections and follow-ups go
  in a new re-review report that links back to the original.
- GitHub issues and pull requests remain the source of truth for volatile
  work state; a report records the verdict and its evidence, not the
  remediation tracking.

Review reports filed before this directory existed may remain under
`docs/agent/design/` where other documents link to them; do not move
acceptance records just to tidy up.
