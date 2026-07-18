# Cooperation-Tier Constraint Ports: Delivered Constraints, Truthful Tier Receipts, and the Containment Non-Goal

- **Status:** proposed — drafted 2026-07-18 at explicit owner direction. This
  line changes to *accepted* when the reviewing PR merges after independent
  adversarial review. The document records owner decisions taken in session on
  2026-07-18; it authorizes the implementation slices listed at the end and
  does not itself add code or claim any port exists.
- **Issue:** [#123](https://github.com/hoelzl/termverify/issues/123)
- **Date:** 2026-07-18
- **Inputs:** the `Adapter`/`ConstraintPorts` contract in `termverify.adapter`;
  the accepted [ConPTY adapter design](conpty-adapter-design.md) and its
  truthful-negotiation table; the merged adapter slices 1–4 (PRs
  #116/#118/#120/#122); the transferred-scope boundaries of the
  [pre-release boundary hardening handover](../handovers/pre-release-boundary-hardening-handover.md);
  the accepted timezone (`termverify.timezone/v1`) and key
  (`termverify.key/v1`) registry slices.

## Decision summary

The six non-terminal constraints (seed, clock, locale, timezone, filesystem,
network) become satisfiable through a new, **opt-in** `ConstraintPorts`
implementation whose receipts claim exactly what happens: the requested
constraint is **delivered** to the subject's spawn environment as explicit,
recorded values, and honoring it is the subject's documented cooperation
obligation. Nothing is enforced at an OS boundary, and no receipt says
otherwise.

To make that claim expressible without overstatement, every enforcement
receipt gains a mandatory **enforcement tier** from a new closed protocol
vocabulary, plus a `delivery` record for delivered-tier receipts containing
the exact values placed in the child's environment. This is a pre-release
protocol amendment under the recorded rule: no released artifact or recorded
transcript carries the prior shapes, so the transcript protocol version
stays 1.

The shipped adapter defaults do not change: `UnenforcedConstraintPorts`
remains the default and `start()` with defaults still fails closed as
`StartUnsupported(seed)`. Using the cooperation ports is an explicit host
decision. With them injected, `ConptyAdapter.start()` can succeed for the
first time — against a subject that honors the cooperation contract.

**OS containment is retired to an explicit non-goal** by owner decision
(2026-07-18): termverify verifies autonomous terminal applications whose
authors control the subject; it is not an execution sandbox for untrusted or
adversarial code. Reopening containment requires a new owner-accepted design;
until then no termverify claim, receipt, or document may imply containment.

## Owner decisions recorded (2026-07-18)

1. **Cooperation tier for all six non-terminal constraints.** Delivery plus
   subject cooperation is the accepted semantic, uniformly. This includes
   filesystem and network: the earlier framing of "sandbox containment" and
   "enforced network deny" is explicitly rejected in favor of one honestly
   disclosed tier across all six.
2. **Filesystem is sandbox-directory delivery only.** A named root maps to a
   host directory delivered as the child's working directory and environment;
   traversal, symlink/reparse handling, and child-process containment are
   *not* claimed and remain out of scope with the containment non-goal.
3. **Network is deny-mode delivery only.** The deny request is delivered and
   recorded; nothing blocks sockets. Allow-list requests remain rejected
   fail-closed, unchanged.
4. **Opt-in ports, unchanged defaults.** Cooperation ports ship as a separate
   implementation; `UnenforcedConstraintPorts` stays the default so nothing
   is implicitly claimed.
5. **Cross-platform ports.** The ports are pure, ambient-free at the ratcheted
   layer, and fully fake-driven on every platform. Real-path evidence exists
   only through the ConPTY adapter on the Windows matrix until a POSIX
   adapter workstream exists — a disclosed evidence boundary, not a code
   boundary.
6. **Pre-release amendment discipline.** All protocol-visible changes land
   under the recorded pre-release rule (precedent: the VT v1 subset
   amendment); versions stay 1.
7. **Containment retired to a non-goal** (see above). The rationale is
   recorded: a containment strategy serving no current user would slow or
   stall delivery of the usable core; the door stays open behind a future
   owner-accepted design if untrusted-subject execution ever becomes a goal.

## Enforcement-tier vocabulary

A new closed, versioned protocol vocabulary, `termverify.enforcement-tier/v1`,
owned by the protocol exactly like the timezone and key registries: exact
case-sensitive membership, no aliases or normalization, runtime validation
authoritative, post-freeze membership or meaning changes require a new
vocabulary version. Members — only values with landed, evidenced behavior are
admitted:

| Tier | Meaning | Who emits it today |
| --- | --- | --- |
| `os` | The constraint is applied by an operating-system mechanism at the subject boundary; evidence exists at the OS level. | `ConptyAdapter`'s own `TerminalReceipt`: dimensions are a pseudoconsole creation/resize parameter, proven by child observation on the Windows matrix. |
| `constructive` | The constraint is applied by construction of the controlled in-process runtime; the subject reaches the constrained resource only through the injected port. | `DirectAdapter` receipts: seed, clock, locale, timezone, terminal, filesystem, and (deny-only) network are routed through the deterministic core's explicit ports. |
| `delivered` | The requested value was placed, exactly as recorded, into the subject's spawn environment; honoring it is subject cooperation. Nothing is enforced. | The new cooperation ports, all six constraints. |

Receipt amendment (pre-release, version stays 1):

- Every enforcement receipt (`SeedReceipt`, `ClockReceipt`, `LocaleReceipt`,
  `TimezoneReceipt`, `TerminalReceipt`, `FilesystemReceipt`,
  `NetworkReceipt`) gains a mandatory `tier` field validated against the
  closed vocabulary.
- Delivered-tier receipts additionally carry a mandatory `delivery` record —
  frozen JSON of the exact environment variables (and, for filesystem, the
  working directory) delivered for that constraint. Non-delivered tiers carry
  no delivery record; the pairing is validated fail-closed in both
  directions (`tier == "delivered"` ⇔ delivery present).
- The transcript schema is amended only where it already encodes receipt
  shapes, preserving its deliberately non-exhaustive role; runtime validation
  remains authoritative.
- `DirectAdapter` and the existing ConPTY terminal negotiation are updated
  mechanically to state their tiers (`constructive` and `os` respectively).
  This is a truthfulness disclosure of behavior that already exists, not a
  behavior change.

A transcript consumer can now see, per constraint, exactly how strong every
claim is. The tier a receipt states is part of receipt-binding validation:
an adapter or port cannot emit a tier the negotiation path does not
authorize for it.

## Delivery mechanics

**Where deliveries live.** The delivery *is* the receipt's `delivery` record.
The adapter assembles the child's spawn environment overlay from the
delivered-tier receipts it validated during negotiation — evidence-driven
spawn, so what the transcript records is exactly what the child was given,
with no side channel between ports and spawn.

**Spawn plumbing.** `ConptyBindingPort.spawn` (and native
`termverify._conpty.spawn`) gain two keyword parameters:

- `env_overlay: Mapping[str, str] | None` — variables overlaid onto the
  binding process's ambient environment at `CreateProcess` time. The overlay
  composition happens in the binding (already the reviewed ratchet
  exclusion), so the ratcheted adapter never reads ambient environ state.
- `cwd: str | None` — the child's working directory.

Disclosure: the child inherits the binding process's ambient environment
underneath the overlay. Ambient contents are not evidence and are not
recorded; only the overlay is. Blocking inheritance entirely was considered
and rejected: a bare environment breaks real subjects (`SystemRoot`, `PATH`,
locale infrastructure) and would fabricate a determinism the tier does not
claim anyway. An overlay variable always wins over an ambient variable of
the same name.

**Collision discipline.** Each constraint delivers a fixed, closed set of
variable names (below). The adapter validates that the six delivery records
are mutually disjoint and that at most one names a working directory;
a violation is an invariant breach reported as structured `StartFailed`,
never silently merged.

**Failure semantics.** A request the cooperation ports cannot deliver
truthfully returns `ConstraintUnsupported` and start ends
`StartUnsupported` at that constraint, before any child exists — identical
to the existing negotiation discipline.

## Per-constraint delivery contracts

Conventional platform variables are delivered **only where the requested
value's meaning maps exactly and portably**; otherwise only the
`TERMVERIFY_`-namespaced variable is delivered and interpretation is the
subject's cooperation obligation.

| Constraint | Delivered | Notes |
| --- | --- | --- |
| seed | `TERMVERIFY_SEED=<decimal>` | Unsigned 64-bit decimal, exactly the validated requested seed. |
| clock | `TERMVERIFY_CLOCK_INITIAL_MS=<decimal>` | Initial manual time only. **Disclosed:** manual-time advances (`advance_clock`) move the adapter's evidence timeline and are never delivered to a running child — there is no channel. A subject that needs to observe advances must obtain them through its own explicit input contract; the clock receipt claims initial delivery, nothing more. |
| locale | `TERMVERIFY_LOCALE=<tag>` | The validated BCP-47 tag. No `LANG`/`LC_ALL` delivery: mapping a language tag to a platform locale string (`en-US` → `en_US.UTF-8`?) is not exact, and delivering an inexact conversion would record something other than what was requested. |
| timezone | `TZ=UTC` and `TERMVERIFY_TIMEZONE=UTC` | `TZ=UTC` qualifies as an exact conventional mapping. Requests remain validated against `termverify.timezone/v1`; **delivery remains UTC-only** — a non-`UTC` request returns `ConstraintUnsupported`, because named-timezone semantics are a separate owner-blocked workstream this design must not absorb. |
| filesystem | `TERMVERIFY_FS_ROOT=<absolute path>`, working directory = the same path | See the sandbox contract below. |
| network | `TERMVERIFY_NETWORK=deny` | Deny mode only. An allow-list request returns `ConstraintUnsupported`, unchanged. Nothing blocks sockets; the receipt's `delivered` tier says so. |

## Filesystem sandbox contract

The cooperation ports are constructed with an explicit mapping
`root_id → absolute host directory path`. At negotiation,
`enforce_filesystem`:

- rejects an unknown `root_id` or a mapped path that is not an existing
  directory with `ConstraintUnsupported` (the request cannot be delivered
  truthfully);
- resolves the mapped path to its absolute form and delivers it as both
  `TERMVERIFY_FS_ROOT` and the child's working directory.

Lifecycle is deliberately the host's: the port creates nothing, populates
nothing, and deletes nothing. Sandbox setup and cleanup are host harness
responsibilities, which keeps the port free of destructive behavior and
ambient side effects beyond one existence check.

Disclosures, stated in the document and in the developer guide when the
slice lands:

- The existence check happens at negotiation time and is advisory; it is
  not containment and carries the ordinary time-of-check gap to spawn.
- Nothing prevents the subject or its descendants from reading or writing
  outside the root. That is the meaning of the `delivered` tier.
- The delivered absolute path is recorded verbatim in the receipt, so
  transcripts embed host-specific paths. Explicitness of the sandbox in
  evidence is a standing project rule and wins here; if a future
  replay/comparison phase needs path canonicalization, that phase owns it.

## Evidence and replay consequences

- Delivered environment values are negotiation-time evidence in receipts,
  before any child exists — replay-stable by construction, and disjoint from
  the raw terminal output evidence.
- The subject-cooperation contract grows: alongside readiness markers and
  self-detected resizes, a cooperative subject reads its constraints from
  the delivered variables. The integration fixture subject must prove this
  observable end to end (echo delivered values into frames).
- Receipts never claim the subject honored a delivery. Assertions about
  subject behavior remain what they always were: application-level
  observations against the transcript.

## Non-goals and boundaries

- **No containment claims, now by explicit retirement rather than by
  deferral.** Untrusted or adversarial subjects are out of termverify's
  scope until an owner-accepted design reopens the question.
- No allow-list network semantics (DNS, redirects, proxies, loopback stay
  untouched and fail-closed).
- No named-timezone delivery or enforcement; `termverify.timezone/v1`
  request validation is unchanged and receipts stay UTC-only.
- No terminal-capability registry activation; no key-to-terminal byte
  mapping; no concurrent-event correlation; no POSIX adapter (ports are
  cross-platform, real-path evidence is Windows-only for now).
- No change to shipped defaults: `UnenforcedConstraintPorts` still fails
  closed, and nothing in this design weakens any fail-closed path.
- No claim that a delivered constraint was honored.

## Amendments to existing documents

Landed in the same review PR as this document:

- [ConPTY adapter design](conpty-adapter-design.md): dated amendment notes —
  `ConptyBindingPort.spawn` gains `env_overlay`/`cwd`; the
  truthful-negotiation table's six `constraint-not-enforced` defaults are
  unchanged but the "future owner-approved enforcement work" language now
  points here; the non-goals containment line points to the retirement
  decision.
- [Pre-release boundary hardening handover](../handovers/pre-release-boundary-hardening-handover.md):
  the two production-containment transferred rows record the owner's
  retirement decision and the cooperation-tier replacement scope; workstream
  gate 3 records the decision paragraph.

## Testing and coverage plan

- The cooperation ports and all receipt/tier validation are cross-platform,
  fake-driven, and fully coverage-ratcheted. `termverify._conpty` (which
  gains the native `env_overlay`/`cwd` support) remains the single ratchet
  exclusion; its new spawn behavior is proven by durable Windows-matrix
  binding tests (child observes delivered variables and working directory).
- Fake-binding adapter tests cover: overlay assembly from receipts, the
  collision and cwd-uniqueness invariants, `ConstraintUnsupported` paths
  (unknown root, non-directory root, allow-list request, non-UTC timezone),
  and tier/delivery pairing validation.
- Windows integration evidence: the first fully successful
  `ConptyAdapter.start()` on the real path — cooperation ports, real
  binding, real normalizer — with a fixture subject that echoes every
  delivered variable and its observed working directory into frames,
  through readiness, a text epoch, subject exit, and replay identity over
  the retained raw chunks.

## Implementation slices authorized by this design

1. **Enforcement-tier protocol amendment** — `termverify.enforcement-tier/v1`,
   mandatory `tier` on all seven receipts, `delivery` on delivered-tier
   receipts, pairing and binding validation, mechanical `constructive`/`os`
   assignment in `DirectAdapter` and `ConptyAdapter` terminal negotiation,
   schema touch-up where receipt shapes are encoded. No cooperation port
   exists yet; nothing can emit `delivered` at the end of this slice.
2. **Cooperation ports and spawn delivery** — the new public cooperation
   ports module, all six delivered-tier ports with the per-constraint
   contracts above, `ConptyBindingPort`/`termverify._conpty` spawn
   `env_overlay`/`cwd` support with Windows binding evidence, adapter overlay
   assembly from receipts with the collision invariants, fully fake-driven
   classification coverage.
3. **First verified terminal run — Windows integration evidence** — the
   end-to-end successful start with cooperation ports on the real path,
   the cooperating fixture subject, forced-stop and deadline paths
   re-exercised under the new ports, and replay identity.

Each slice follows the standard loop: focused issue, external worktree,
strict TDD, full validation gate, PR, adversarial fresh-context review,
merge. Completion of slice 3 produces the project's first fully successful
verified terminal run and is the natural point to reassess what remains
transferred in the handover.
