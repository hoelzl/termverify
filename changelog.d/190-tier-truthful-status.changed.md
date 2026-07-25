- **Made `capability.result.status` tier-truthful: `enforced` → `applied`.**
  The transcript protocol mandated `status` ∈ {`enforced`, `unsupported`} and
  called a supported-but-not-enforced state invalid — while the `delivered`
  enforcement tier is defined as "honoring it is subject cooperation.
  **Nothing is enforced.**" Every delivered-tier constraint was therefore
  recorded on the wire as `enforced`: the tier system exists to avoid
  overstatement, and the status vocabulary it qualifies overstated anyway
  (adversarial review 2026-07-24, finding P2). The status word now says only
  what happened — the adapter applied the constraint and recorded the
  effective value — and the already-mandatory `tier` carries the claim
  strength. `enforced` is not an accepted value: an in-place vocabulary
  correction under prototyping-stage governance, with no version bump, alias,
  or shim. The related seam is closed in the same change: "an adapter that
  cannot enforce a requested constraint must not claim a verified run" is
  replaced by the rule the shipped tiers actually support — record
  `unsupported` and terminate when a constraint cannot be applied at any
  tier, never record a tier stronger than the mechanism used, and read a run's
  verdict as exactly as strong as its weakest tier. Validator, the single
  emitter, repository fixtures, and both prose sites move together; the
  packaged JSON Schema never encoded `status`, so it is unchanged.
  (Resolves #190.)
