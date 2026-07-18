# ConPTY Adapter Design: Binding Mapping, Epoch Semantics, and Evidence Normalization

- **Status:** accepted — decided 2026-07-18 under the maintainer's delegated
  autonomous authority; passed independent adversarial agent review before
  merge. This document scopes verification-plan items 5 (classification half),
  6, 7, and 8 of the
  [terminal adapter dependency decision](terminal-adapter-dependency-decision.md)
  into an implementable design for the public terminal adapter. It authorizes
  the implementation slices listed at the end; it does not itself add code,
  claim any adapter exists, or amend the dependency decision.
- **Issue:** [#112](https://github.com/hoelzl/termverify/issues/112)
- **Date:** 2026-07-18
- **Inputs:** the accepted
  [dependency decision](terminal-adapter-dependency-decision.md) and its
  verification plan; the
  [Phase 1 protocol and Windows boundary decision](phase-1-protocol-and-windows-boundary.md);
  the `Adapter`/`ConstraintPorts` contract in `termverify.adapter` with
  `termverify.direct.DirectAdapter` as the reference implementation; the merged
  binding slices PR #105/#107/#109/#111 (`termverify._conpty.ConptyChild`);
  the transferred-scope boundaries of the
  [pre-release boundary hardening handover](../handovers/pre-release-boundary-hardening-handover.md).

## Decision summary

The public Windows terminal adapter is `ConptyAdapter`, implementing the
existing `Adapter` protocol unchanged. It is layered strictly above the native
binding through two injected ports — a **binding port** shaped exactly like
`ConptyChild` and a **normalizer port** that turns raw VT output into
structured screen evidence — plus injected constraint ports for the six
constraints the adapter does not own. All `ConptyAdapter` logic is
cross-platform, testable against fakes, and fully coverage-ratcheted;
`termverify._conpty` remains the single reviewed ratchet exclusion.

Readiness and quiescence on a real terminal are defined **only** by an
explicit readiness marker emitted by the subject and observed in the output
stream, or by native end-of-stream plus an observed exit record. Wall-clock
silence is never evidence of anything; the only wall-clock input is an
explicitly configured abort deadline that always produces a structured
failure, never a success.

## Layering and module mapping

```
termverify.conpty.ConptyAdapter          public, cross-platform, ratcheted
  ├─ ConptyBindingPort (Protocol)        structural twin of ConptyChild
  ├─ TerminalOutputNormalizer (Protocol) VT text -> screen evidence
  └─ ConstraintPorts (existing)          injected, six non-terminal constraints
termverify._conpty.ConptyChild           native, Windows-only, ratchet-excluded
```

- `ConptyBindingPort` is a structural `Protocol` in the new public module,
  mirroring the `ConptyChild` surface: a spawn factory
  (`argv`, keyword `rows`, `columns` → child), and per-child `read()`,
  `write(text)`, `resize(rows=, columns=)`, `is_alive()`,
  `close(force=)`, `pid`, `exit_status`. `ConptyChild` satisfies it without
  modification.
- The binding **exception taxonomy is part of the port contract** and stays
  canonical in `termverify._conpty` (`ConptyUnsupportedError`,
  `ConptyClosedError`, `ConptyConcurrentIOError`, `ConptyEndOfStreamError`).
  The module imports cross-platform (only `spawn` is Windows-only), so the
  ratcheted adapter may import the exception types directly. Moving them into
  a new shared module was considered and rejected as churn with no behavioral
  benefit; a fake binding raises the same types.
- The subject command line (`argv`) is a constructor argument of
  `ConptyAdapter`, exactly as `DirectAdapter` binds its application at
  construction. `RunConfiguration` deliberately carries no command.
- The adapter enforces the single-flight discipline the binding demands: it is
  synchronous and single-flight by the `Adapter` contract already, and it
  never issues overlapping `read`/`write` calls. `close` remains the one
  concurrent-safe operation and is reserved for the abort watchdog below.

## Truthful constraint negotiation (item 7)

`ConptyAdapter` mirrors `DirectAdapter`'s architecture: enforcement is a port
responsibility, negotiated in `CONSTRAINT_NAMES` order with the same
receipt-binding validation. The split is:

| Constraint | Owner | Shipped behavior |
| --- | --- | --- |
| terminal | **the adapter itself** | Enforced. Dimensions are an OS-level parameter of pseudoconsole creation and explicit resize — not advisory environment. Capabilities must be empty (`TerminalReceipt` already rejects non-empty capabilities; the registry remains unactivated). |
| seed | injected port | Default port: `constraint-not-enforced`. No OS mechanism binds a subject's RNG through a pseudoconsole; environment injection is subject cooperation, not boundary enforcement. |
| clock | injected port | Default: `constraint-not-enforced`. The child runs on ambient wall clock; manual-time injection is cooperation. |
| locale | injected port | Default: `constraint-not-enforced`. Environment variables are advisory to the child. |
| timezone | injected port | Default: `constraint-not-enforced`. Same; named-timezone enforcement additionally remains blocked on the owner. |
| filesystem | injected port | Default: `constraint-not-enforced`. Containment enforcement remains a transferred, owner-blocked workstream. |
| network | injected port | Default: `constraint-not-enforced`. The job object does not block network; deny is not provable at this boundary. |

Consequences, stated explicitly:

- With the shipped default ports, `start()` returns
  `StartUnsupported(constraint="seed")` — the first constraint in negotiation
  order — **before any child is spawned**. That is the intended fail-closed
  outcome: the adapter never fabricates a receipt, and full verified terminal
  runs become possible only through ports that genuinely enforce their
  constraint (a harness's documented cooperation contract, or future
  owner-approved enforcement work). This matches the direct adapter, where
  enforcement already belongs to the injected application ports and
  requested/effective equality is insufficient as proof.
- The adapter intercepts `enforce_terminal` itself and does not delegate it:
  it owns the pseudoconsole, records the requested dimensions for spawn, and
  emits the `TerminalReceipt`. Injected ports cannot override terminal
  enforcement or claim capabilities.
- Platform support is decided during terminal negotiation: on a host where the
  binding reports `ConptyUnsupportedError` semantics (non-Windows, no ConPTY),
  `enforce_terminal` reports `ConstraintUnsupported("constraint-unsupported")`
  and start ends as `StartUnsupported` before input dispatch, exactly as the
  dependency decision requires.

## Dimensions receipts (item 6)

- Requested dimensions are fixed at negotiation, applied at pseudoconsole
  creation (`spawn(rows=, columns=)`), and changed only by an explicit
  `Resize` dispatch, which calls the binding `resize` and is observed like any
  other epoch.
- The `TerminalReceipt` claims the creation-time mechanism. The *observed*
  evidence backing that claim is executable: the binding lifecycle test
  already proves a child observes the creation dimensions and the resized
  dimensions; the adapter integration slice must additionally show a child
  observing both through a full `start`/`dispatch(Resize)` epoch, on the
  `windows-latest` CI matrix.
- Every observation's `state` carries the current effective dimensions
  (`{"terminal": {"columns": C, "rows": R}}`), so a resize is visible in
  evidence at the epoch where it happened, and normalized frames must agree
  with them (`Frame` validates `rows == len(lines)`).

## Epoch and readiness semantics (no wall-clock evidence)

The `Adapter` contract is single-flight manual time: `dispatch`/
`advance_clock`/`stop` are legal only in the idle state at the current manual
time, and an epoch ends in `EpochCompleted` (quiescence) or `TerminalResult`.
A real child is asynchronous, so quiescence needs an observable signal.

**Readiness marker.** A verified terminal subject must cooperate by emitting
an explicit readiness marker when it reaches quiescence: after startup
(initial readiness) and after processing each input. The marker is a
configurable exact string with a private-use OSC default,
`"\x1b]7791;ready\x1b\\"` (OSC … ST). It is scanned for in the decoded output
stream; it is stripped from normalized frames but retained verbatim in raw
output evidence. Subjects that cannot emit a marker cannot produce readiness
evidence and therefore cannot complete a verified terminal run — by design,
not by accident. The marker string is part of the run's explicit
configuration, recorded in evidence, and must be replay-stable.

**Epoch algorithm** (identical for initialize, dispatch, and advance_clock,
except for the write step):

1. Write the input, if any: `TextInput.text` via binding `write`; `Resize`
   via binding `resize`; `advance_clock` and initialize write nothing.
2. Loop on single-flight `read()`. Each chunk is appended to the epoch's raw
   output evidence and fed to the normalizer.
3. Marker observed → the epoch is quiescent: build the observation at the
   epoch's manual time from the normalizer snapshot and return
   `EpochCompleted` (or `Started` from initialize), then return to idle.
4. `ConptyEndOfStreamError` → the child exited. Capture the native exit
   record; missing exit evidence is a structured failure, never fabricated.
   Result: `TerminalResult` with `RunFinished` and matching exited-process
   observation (from initialize: `StartTerminated`, whose outcome must be a
   subject exit).
5. `ConptyClosedError` caused by the armed abort deadline (below) →
   structured `adapter-runtime-failed` (`StartFailed` from initialize) with
   details disclosing the deadline policy.
6. Any other binding exception (`ConptyConcurrentIOError`, an unexpected
   `ConptyClosedError`, a native error) → `adapter-runtime-failed`
   (`StartFailed` from initialize) with the underlying failure in details.
   Concurrent-I/O errors cannot occur under the adapter's own single-flight
   discipline; observing one is an invariant violation and is still reported
   structurally, never swallowed.

**advance_clock** advances the adapter's manual evidence timeline only.
Whether and how a manual-time step reaches the subject is the clock port's
enforcement contract; the adapter's job is unchanged epoch mechanics: no
input bytes, read to the readiness marker. With the shipped default ports the
clock constraint is unsupported and this path is reachable only through an
enforcing injected port.

**Abort deadline.** A hang (no marker, no end-of-stream) must not block
forever, and no ambient timeout may be invented. The adapter therefore
requires an **explicit deadline configuration** at construction — there is no
default — and arms a watchdog before each blocking read that force-closes the
binding when the deadline expires (`close` is the binding's one
concurrent-safe operation; slice 4 proved this recovery at the binding
level). The deadline is host abort *policy*, disclosed in the resulting
structured failure's details; it is never evidence of quiescence and can
never produce a successful epoch. The watchdog trigger is injectable so the
classification path is fully testable against a fake binding.

**Time discipline.** All observation and diagnostic timestamps are the
epoch's manual time, satisfying the contract's `at_ms` invariants. Wall-clock
values never appear in evidence except, at most, inside disclosed failure
details of the abort policy.

## stop and teardown

`stop` is legal only when idle. The binding offers no graceful signal
channel, so cooperative shutdown belongs to the harness (dispatch a quit
input as a normal epoch, which ends in `TerminalResult` via end-of-stream).
`stop` itself is forced, truthful teardown:

- `close(force=True)`: job-object termination of the whole tree with the
  uniform forced exit code 15 (`FORCED_TERMINATION_EXIT_CODE`), native wait,
  and exit-record capture — the semantics proven in the binding slices.
- Result: `TerminalResult` with `RunFinished(ExitStatus("code", 15))`, an
  exited-process observation at the stop time, and a diagnostic disclosing
  forced termination. If the exit record cannot be captured, the result is a
  structured `RunFailed` instead; no exit evidence is fabricated.
- Output produced after the last epoch's readiness marker may be lost at
  forced close; evidence completeness is therefore bounded by the marker
  protocol, and the bound is documented, not hidden. Release-only close
  (`force=False`) records no exit status and is rejected for `stop`.

## Failure-taxonomy classification (item 5, classification half)

| Binding outcome | Phase | Classified result |
| --- | --- | --- |
| Platform/ConPTY unavailable | negotiation | `StartUnsupported(terminal)`, `constraint-unsupported` |
| Injected port reports unsupported | negotiation | `StartUnsupported` at that constraint |
| Spawn failure (`FileNotFoundError`, `OSError`, containment failure) | initialize | `StartFailed`, `adapter-start-failed` |
| End-of-stream before initial marker | initialize | `StartTerminated` with observed exit (subject exit only) |
| Deadline abort, invariant violation, native error | initialize | `StartFailed`, `adapter-start-failed` |
| End-of-stream during epoch | dispatch/advance | `TerminalResult`, `RunFinished` with observed exit |
| Deadline abort | dispatch/advance | `TerminalResult`, `RunFailed` (`adapter-runtime-failed`, deadline disclosed) |
| `ConptyConcurrentIOError`, unexpected `ConptyClosedError`, native error, resize failure | dispatch/advance | `TerminalResult`, `RunFailed` (`adapter-runtime-failed`) |
| Missing exit record where exit evidence is required | any | structured failure for that phase, never a fabricated `ExitStatus` |
| Forced stop | stop | `RunFinished(code 15)` with disclosure diagnostic |

Every abort path closes the binding (`force=True`) before returning, so no
handles, job objects, or children outlive a structured failure — the leak
freedom proven at the binding level in slice 4 carries up unchanged.

## Evidence normalization (item 8)

Raw VT output is evidence; assertions run against normalized structured
observations. The design fixes the **port and evidence shape** now and defers
the normalizer implementation choice to its own assessment:

- `TerminalOutputNormalizer` protocol: constructed for a run with the initial
  dimensions; `feed(chunk: str)` consumes decoded output in order;
  `notify_resize(rows, columns)` tracks explicit resizes; `snapshot()`
  returns the current screen model — the `Frame` (a `rows`-line grid) and the
  `Cursor` for the observation's mandatory `ui`. Determinism requirement: the
  snapshot is a pure function of the fed sequence, initial dimensions, and
  resize notifications.
- The observation's mandatory `ui.cursor` makes the normalizer a **hard
  dependency of any successful start** — `Started` cannot be constructed
  without cursor evidence, so no adapter slice may claim a successful run
  before a reviewed normalizer exists. Unit tests inject a fake normalizer.
  The shipped `ui` is minimal and truthful: no regions, no focus, cursor and
  mode from the screen model; semantic regions remain application-level
  concepts with no terminal enforcement.
- Raw evidence retention: each epoch's observation carries ordered
  `Event("terminal.output", {"chunk": <raw text>})` events containing the
  exact decoded chunks, including the readiness marker. Replaying the
  normalizer over the raw chunks must reproduce the frames — this is the
  replay check that makes frames trustworthy, and it aligns with the
  transcript schema's replay-subject `normalizer {id, version}` field: the
  normalizer's identity and version are recorded so a replay can verify it.
- Choosing the implementation (a minimal in-house VT interpreter for the
  sequences ConPTY actually emits, versus a third-party screen emulator such
  as `pyte`) requires its own reuse/dependency assessment with rationale and
  verification plan per `AGENTS.md`, exactly like the `pywinpty` decision.
  This document deliberately does not make that choice.

## Testing and coverage plan

- All `ConptyAdapter` logic lives above the ports, runs on every platform
  against a fake binding and fake normalizer, and is fully
  coverage-ratcheted. `termverify._conpty` remains the only ratchet
  exclusion.
- Fake-binding tests cover the entire classification matrix above, the
  single-flight and time-discipline invariants, the marker protocol
  (including markers split across read chunks and marker-free hangs), and
  watchdog-triggered aborts via the injectable trigger.
- Windows integration tests (CI `windows-latest`, all supported CPython
  versions) prove the real path end to end with a cooperative fixture child:
  start-to-readiness, text epoch, resize epoch with observed dimensions,
  subject exit, forced stop, and deadline abort with recovery.

## Non-goals and owner-blocked boundaries

Unchanged from the dependency decision and the handover: no key-to-terminal
byte mapping (a `KeyInput` dispatch that the terminal adapter cannot execute
uses the existing structured runtime-failure path, exactly as accepted in the
key-registry slice — no fallback, no silent degradation); no
terminal-capability registry activation; no containment enforcement claims;
no concurrent-event correlation; no POSIX adapter. Named-timezone
enforcement, capability registry, and containment enforcement remain blocked
on the owner.

## Implementation slices authorized by this design

1. **Normalizer decision and port** — reuse/dependency assessment for the
   screen-model implementation, its own design note, the
   `TerminalOutputNormalizer` port, and the chosen implementation under test.
2. **Adapter negotiation skeleton** — `ConptyBindingPort`, constructor
   surface, truthful negotiation, `StartUnsupported`/`StartFailed` paths,
   fake-binding tests (no successful start yet).
3. **Epoch machinery** — marker protocol, epoch loop, classification matrix,
   watchdog abort, stop semantics, all against fakes.
4. **Windows integration evidence** — the cooperative fixture child and the
   CI-matrix proof for items 5–8's public claims.

Each slice follows the standard loop: focused issue, external worktree,
strict TDD, full validation gate, PR, adversarial fresh-context review,
merge.
