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
