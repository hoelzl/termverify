- **BREAKING: the in-process API now says `applied` where it said `enforced`,
  matching the wire.** PR #216 made `capability.result.status` tier-truthful
  (`enforced` → `applied`) because a `delivered`-tier constraint is not
  enforced by anything; the Python API kept the older word, so an adapter
  author populated `EnforcedConstraints` and watched it produce a record
  saying `applied`. Nothing was false — `EnforcementReceipt.tier` has always
  carried claim strength honestly — but the seam is now closed.

  Migration, mechanical and complete (no shim, per the prototyping-stage
  posture):

  | Before | After |
  | --- | --- |
  | `ConstraintPorts.enforce_seed` … `enforce_network` (7 methods) | `apply_seed` … `apply_network` |
  | `EnforcedConstraints` | `AppliedConstraints` |
  | `StartUnsupported.enforced`, `StartFailed.enforced` (field and keyword) | `.applied` |
  | `termverify.conpty.UnenforcedConstraintPorts` | `ApplyNothingConstraintPorts` |

  **Deliberately unchanged**, because they name the *axis* of claim strength
  rather than a claim: `EnforcementReceipt`, `EnforcementTier`,
  `ENFORCEMENT_TIERS`, and the `termverify.enforcement-tier/v1` vocabulary —
  its `delivered` member means precisely that nothing is enforced, so the
  word is doing honest work. The `constraint-not-enforced` wire code also
  stays: it routes "cannot apply at any tier" to `run.unsupported`, which is
  what the protocol prose says it does.

  No transcript, control-protocol, or schema bytes change; this is a Python
  rename only.
