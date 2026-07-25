- **Made `capability.result.status` tier-truthful: `enforced` → `applied`.**
  The transcript protocol mandated `status` ∈ {`enforced`, `unsupported`} and
  called a supported-but-not-enforced state invalid — while the `delivered`
  enforcement tier is defined as "honoring it is subject cooperation.
  **Nothing is enforced.**" Every delivered-tier constraint was therefore
  recorded on the wire as `enforced`: the tier system exists to avoid
  overstatement, and the status vocabulary it qualifies overstated anyway
  (adversarial review 2026-07-24, finding P2). The status word now says only
  that the adapter carried out the constraint's application step and recorded
  the value it applied; the already-mandatory `tier` says what that step was
  worth — at `os` and `constructive` the constraint is in force, at
  `delivered` what was applied is the delivery. `enforced` is not an accepted
  value: an in-place vocabulary correction under prototyping-stage governance,
  with no version bump, alias, or shim.
- **Removed the containment claims the cooperation tiers cannot support.**
  The same protocol section told adapter authors that an adapter "gives
  filesystem access only through the named sandbox root and denies network
  access by default", "injects the requested seed and manual clock", and
  "starts subprocesses with the requested locale" — none of which is true on
  the delivered path, where the cooperation ports set environment variables,
  never deliver manual-time advances, set no `LANG`/`LC_ALL`, and block no
  sockets. That contradicted both the shipped code and the accepted decision
  that no receipt, claim, or document may imply containment. The
  adapter-facing contract is now stated per tier, `architecture.md`'s
  "either enforces … or unsupported" binary is replaced by the tiered rule,
  and the run-level claim is that a run's constraint claims are *no stronger
  than* its weakest tier — an upper bound, not the equality the first draft
  of this change asserted (adversarial review of PR #216).
  Validator, the single emitter, repository fixtures, and every normative
  prose site move together; the packaged JSON Schema never encoded `status`,
  so it is unchanged. (Resolves #190.)
