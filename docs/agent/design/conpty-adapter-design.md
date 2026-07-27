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

- `ConptyBindingPort` is a structural `Protocol` in the new public module
  with three parts: an explicit **support probe** (`is_supported() -> bool`),
  a spawn factory (`argv`, keyword `rows`, `columns` → child), and the
  per-child surface `read()`, `write(text)`, `resize(rows=, columns=)`,
  `is_alive()`, `close(force=)`, `pid`, `exit_status`. **Amended 2026-07-18**
  ([cooperation-tier constraint ports](cooperation-tier-constraint-ports.md)):
  the spawn factory additionally accepts keyword `env_overlay` and `cwd`,
  composed onto the ambient environment inside the binding so the ratcheted
  adapter never reads ambient state. `ConptyChild`
  satisfies the child surface without modification; the probe is a new thin
  function implemented alongside `spawn` in `termverify._conpty` (the same
  precondition `spawn` already checks), so platform support is answerable at
  negotiation time — before any spawn — through the injected port, never by
  the ratcheted adapter reading ambient platform state. Fake bindings supply
  their own probe, so both the supported and unsupported negotiation paths
  are drivable on every platform.
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
| filesystem | injected port | Default: `constraint-not-enforced`. *(Amended 2026-07-18: containment enforcement was retired to an explicit non-goal; delivery-tier cooperation is the accepted replacement scope — see the [cooperation-tier design](cooperation-tier-constraint-ports.md).)* |
| network | injected port | Default: `constraint-not-enforced`. The job object does not block network; deny is not provable at this boundary. |

Consequences, stated explicitly:

- With the shipped default ports, `start()` returns
  `StartUnsupported(constraint="seed")` — the first constraint in negotiation
  order — **before any child is spawned**. That is the intended fail-closed
  outcome: the adapter never fabricates a receipt, and full verified terminal
  runs become possible only through explicitly injected ports. **Amended
  2026-07-18:** the owner-accepted path for such ports is the
  [cooperation-tier constraint ports design](cooperation-tier-constraint-ports.md) —
  opt-in ports whose receipts truthfully claim delivery-tier semantics;
  OS-level enforcement work is retired to a non-goal by the same decision.
  This matches the direct adapter, where
  enforcement already belongs to the injected application ports and
  requested/effective equality is insufficient as proof.
- The adapter intercepts `enforce_terminal` itself and does not delegate it:
  it owns the pseudoconsole, records the requested dimensions for spawn, and
  emits the `TerminalReceipt`. Injected ports cannot override terminal
  enforcement or claim capabilities. A configuration that requests non-empty
  terminal capabilities is classified fail-closed during negotiation as
  `ConstraintUnsupported("constraint-unsupported")` →
  `StartUnsupported(terminal)`; the adapter never attempts to construct a
  receipt the contract would reject.
- Platform support is decided during terminal negotiation through the binding
  port's support probe: when the probe reports no ConPTY (non-Windows, no
  ConPTY host), `enforce_terminal` reports
  `ConstraintUnsupported("constraint-unsupported")` and start ends as
  `StartUnsupported` before input dispatch, exactly as the dependency
  decision requires. A spawn that fails *after* a positive probe (including a
  late `ConptyUnsupportedError` misreport) is a start failure at initialize,
  not an unsupported result — the contract permits no unsupported outcome
  once all receipts exist.

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
  evidence at the epoch where it happened. Normalized frames must agree with
  those dimensions; `Frame` itself validates only internal consistency
  (`rows == len(lines)`), so that agreement is an adapter responsibility
  covered by tests, not a contract-enforced invariant.

## Epoch and readiness semantics (no wall-clock evidence)

The `Adapter` contract is single-flight manual time: `dispatch`/
`advance_clock`/`stop` are legal only in the idle state at the current manual
time, and an epoch ends in `EpochCompleted` (quiescence) or `TerminalResult`.
A real child is asynchronous, so quiescence needs an observable signal.

**Readiness marker.** A verified terminal subject must cooperate by emitting
an explicit readiness marker when it reaches quiescence: after startup
(initial readiness) and after processing each input. The marker is a
configurable printable prefix, a token the subject has not used before in the
run, and a fixed terminator — by default `<<termverify.ready:7>>` and so on.
The adapter scans for it in the decoded output stream independently of the
normalizer; raw chunks are always fed to the normalizer **unmodified**, so
replaying the normalizer over the raw evidence sees exactly what the adapter
fed it.

**Amended 2026-07-26 (issue #232): the OSC default was wrong, and a constant
marker is wrong.** This paragraph previously specified a private-use OSC
default, `"\x1b]7791;ready\x1b\\"`, on the strength of a Windows-matrix test
observing ConPTY relay that exact sequence verbatim between printable
sentinels. Relaying it verbatim is true and was never sufficient: ConPTY
renders text on one path and passes OSC through on another, and the OSC path
is *ahead*. Measured after the raw-byte read path (#197) made the gap
observable, a subject's single atomic write of `TV_BEFORE` + marker +
`TV_AFTER` arrives as the marker alone, then the text — so an OSC marker does
not bound the output it follows, and the adapter would end an epoch and
report a frame missing that output. The original evidence held only because
the previous binding's reads were slow enough that the renderer had already
flushed.

Two properties follow, and neither is optional:

1. **The marker is printable**, so it travels the renderer's path and is
   ordered against the output it bounds. The cost is that it occupies screen
   cells and appears in frames — no longer a host's opt-in but the default,
   and the reason subjects should emit it on its own newline-terminated line.
2. **Each marker carries a fresh token.** Rendered text is screen state and
   ConPTY re-emits screen state on every repaint, so a constant marker
   reappears in later epochs; without per-emission tokens an epoch completes
   on a marker its input never caused, which is how this was found. The
   adapter honours each token once. A token must match
   `[0-9A-Za-z._-]{1,64}`; anything else is not a marker, which makes a
   wrapped marker fail closed on the epoch deadline rather than be honoured
   with a mangled token.

The prefix remains configurable and has its own frame-visibility and replay
evidence. One consequence of the original evidence still stands:
a resize delivers no bytes to a Windows console client's stdin, so
marker-after-resize cooperation requires the subject to detect the new
dimensions itself (the fixture subject watches the reported terminal size);
that is part of the subject cooperation contract, not an adapter concern.
Subjects that cannot emit a marker cannot produce readiness
evidence and therefore cannot complete a verified terminal run — by design,
not by accident. The marker string is part of the run's explicit
configuration, recorded in evidence, and must be replay-stable.

> **Correction (2026-07-26, issue #233 review).** The marker protocol's
> adversarial review measured two claims above and found them wrong.
> First, the wrap mechanism: a marker wider than the terminal is delivered
> contiguous and *honoured* — wrapping is screen-buffer layout, not stream
> content — so the fail-closed skip defends against cursor-addressed
> mid-emission corruption of the marker's cells, not wraps. The integration
> suite pins the measured behaviour
> (`test_a_wrapped_marker_is_delivered_contiguous_and_honoured`). Second,
> "recorded in evidence": the configured prefix appears in no transcript
> record; it is recoverable only from the marker text the frames and raw
> chunks carry. The review also disclosed three marker-forgery channels the
> subject cooperation contract now names — stray prefix emission in
> ordinary output, console input echo, and escape-sequence payloads (see
> the developer guide) — and `_validate_marker_prefix` now rejects
> non-printable prefixes, which had allowed a host to configure the marker
> back onto the OSC pass-through path this amendment removed.

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

**Amendment (issue #194, adversarial review finding R2).** A per-read
watchdog does not bound an epoch: because it is re-armed for every read, a
subject trickling output just under the deadline never exceeds any single
read's deadline, so the marker never arrives and the epoch never ends. The
same configured deadline therefore also bounds the epoch **as a whole**,
checked between reads against an injected monotonic clock. Worst case is up
to twice the deadline — the epoch's own bound plus the read in flight when
it passes. This adds no policy and no evidence source: the abort is the
ordinary deadline abort, and its details name which bound fired (`read` for
a stalled read, `epoch` for a subject that produces output but never reaches
readiness) because the two need opposite remediations.

A read-count budget was implemented first and **rejected on measurement**:
real ConPTY barely coalesces (635 reads for a 2,000-line scroll), so a count
low enough to bound a trickle also aborted an ordinary few-thousand-line run
— a false abort of a cooperating subject, worse than the starvation it
prevents.

Retained evidence is bounded separately, because time bounds do not bound
memory: an epoch may retain only as much output as one observation record can
carry. The budget is derived from `termverify.transcript/v1` ceilings and
takes the tighter of two, because an epoch's chunks reach the record as a
**single** coalesced `terminal.output` string (issue #195): the per-string
ceiling that merged string meets on its own, and the per-record string sum
less what the rest of the record costs. Exceeding it fails the epoch rather
than retaining evidence that would not fit. The frame reserve counts UTF-8
bytes per cell, not cells: the codec measures bytes, and a non-ASCII screen
costs up to four bytes per cell. This bound is not a recordability guarantee
— the codec enforces further ceilings, notably the canonical-line limit
ESC-dense output reaches far sooner. It is adapter policy, not host policy,
and not configurable.

A separate chunk-count budget was implemented and then **deleted when #195
merged**. While each retained chunk became its own event, chunk count was a
real axis that bytes could not express — a subject redrawing in place reached
the per-collection ceiling with under 100 KB of payload — and the adapter had
to abort a cooperative subject to stay honest. Recorder-side coalescing
removes the axis rather than the symptom, so the bound went with it.

**Amendment (issue #226, rounds 7–8 of this slice's review).** Deleting the
chunk-count budget retired the collection ceiling as an *output* axis, not
as an axis. The frame meets three v1 ceilings in three different units, and
the byte budget models only one of them, so `_geometry_failure` now checks
all three before an epoch may read — rows against the collection ceiling
(one item per frame line, 16,384), columns against the per-string ceiling
(one line is one string, 262,144 at four bytes per cell), and cells through
the byte budget itself (523,264). All three are the same `budget:
"geometry"` failure class; the details name the axis that bound.

Neither of the first two follows from the third, which is why one check
could not serve. A 10-column, 20,000-row terminal is 200,000 cells —
two-and-a-half times below the cell threshold — and the codec rejects every
observation record it produces, for collection size. A 262,145-column,
1-row terminal is 262,145 cells and is rejected for string size once the
screen holds four-byte characters. Only a single-row terminal reaches the
column limit at all: at two rows, any width past 262,144 is already past
523,264 cells.

The two are not alike in one respect worth stating, because the checks look
symmetric and are not. The **row** ceiling is content-independent: 16,385
lines are 16,385 collection items whatever they contain. The **column**
ceiling is content-dependent, like the cell one — 262,145 columns of ASCII
record fine, and it is 262,145 columns of four-byte characters that the
codec rejects. The adapter reserves UTF-8's worst case per cell on both
content-dependent axes rather than admitting a run and discovering at
serialization which kind of screen it got, which is the same trade the cell
threshold already makes and which the guide discloses to hosts.

**The rejected alternative is worth recording, because it was shipped for a
round.** The first fix checked rows only and argued columns needed no check,
because a 262,144-column frame line is out of reach of a 16-bit `COORD`.
Measured on the Windows dev host, that argument is false in both halves:
`PTY()` range-checks nothing, and 262,145x1, 1,048,577x1 and 10x100,000 all
create a pseudoconsole and spawn into it. The review then drove a
single-row, 262,145-column run end to end through the real normalizer,
recorder and codec and got the admit-then-reject this slice exists to
prevent — at four bytes per cell, the regime the reserve is sized for.
A check that costs one comparison should not be gated on an
argument about what a host can request — the argument is where the defect
lives, and it is cheaper to check the axis than to be right about it.

> **Follow-up (issue #228, resolved 2026-07-27):** the same unchecked wrap
> let the terminal receipt claim `tier="os"` for a geometry the console
> never adopted — a request surviving the recordability gates could still
> truncate silently in the `COORD` wrap (measured: 65546 rows adopted as
> 10). The spawn now verifies adoption before handing out a session:
> predictable wrap misfires are refused from the measured model, and every
> other geometry is proven by a probe child's read-back of the adopted size.

The general lesson is the one this slice keeps re-learning in new clothes:
**a bound expressed in one unit does not cover a ceiling charged in
another.** Cells did not cover bytes (round 4), and bytes cover neither
collection items nor per-string length (rounds 7–8).

Ordering note, worth keeping: #195 merged first and silently invalidated this
byte budget in the *unsafe* direction. Deriving it from the per-record string
sum admitted epochs at 1.98x the per-string ceiling the merged string
actually meets, and the adapter's own test did not notice because it
replicated the codec's counting rule over the adapter's pre-coalescing
observation. Two lessons: a budget single-sourced from protocol ceilings
still has to be re-derived when the *shape* of the record those ceilings
apply to changes, and budget evidence should be pushed through the real
recorder and codec rather than through a replica of their rules.

**Write coverage, decided 2026-07-18 (issue #121):** the watchdog wraps
blocking reads only. Binding evidence showed no conin write backpressure on
the verified matrix (a 7.1 GiB flood against a never-reading child never
blocked, issue #110), the bounded write-flood test would fail loudly rather
than hang if some SKU regressed that behavior, and `cancel_io` cannot cancel
conin writes anyway — a write watchdog could only close the binding and then
wait out the same native call it cannot interrupt. Deadline protection for
writes is therefore not implemented; if future evidence shows a blocking
conin write, that evidence reopens this decision rather than being absorbed
silently.
**Disclosed ambient floor (DA stall), measured 2026-07-18 (issue #121):**
conhost's session preamble includes a `CSI c` primary device-attributes
query, and while that query waits for an answer the host defers the
client's output — measured on the verified machine as a constant ~3.1 s
before the first byte of subject output when the query goes unanswered,
versus ~0.05 s when a DA1 response is written to conin. The adapter does
not answer the query: injecting a synthetic terminal-identity response is
host-role conversation the evidence model does not yet record, and doing
it silently would put unrecorded bytes on the conin path of a replayable
run. The consequence is disclosed instead: every real start pays the
constant stall as wall-clock latency (never as evidence — timestamps stay
manual), and a configured `abort_deadline_ms` at or below the stall plus
spawn overhead fails every real start by policy. Hosts must budget the
deadline above this floor. A future slice may add a truthful, recorded
DA-response mechanism to remove the stall; changing that behavior amends
this document.

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
| Support probe reports no ConPTY | negotiation | `StartUnsupported(terminal)`, `constraint-unsupported` |
| Non-empty requested terminal capabilities | negotiation | `StartUnsupported(terminal)`, `constraint-unsupported` |
| Injected port reports unsupported | negotiation | `StartUnsupported` at that constraint |
| Spawn failure (`FileNotFoundError`, `OSError`, containment failure) | initialize | `StartFailed`, `adapter-start-failed` |
| End-of-stream before initial marker | initialize | `StartTerminated` with observed exit (subject exit only) |
| Deadline abort (`bound` names which fired, as on the dispatch row), invariant violation, native error | initialize | `StartFailed`, `adapter-start-failed` |
| Retained-output budget exhausted (`budget: "bytes"`) | initialize | `StartFailed`, `adapter-start-failed` |
| Geometry admits no recordable epoch (`budget: "geometry"`, naming the axis that bound: `terminal-rows`, `terminal-columns`, or `terminal-cells`) | initialize | `StartFailed`, `adapter-start-failed` |
| End-of-stream during epoch | dispatch/advance | `TerminalResult`, `RunFinished` with observed exit |
| Deadline abort | dispatch/advance | `TerminalResult`, `RunFailed` (`adapter-runtime-failed`, deadline disclosed, `observation=None` — no quiescent snapshot exists at abort, and none is fabricated; `bound` names which deadline fired — `"read"` for one stalled read, `"epoch"` for a subject that kept producing output without reaching readiness) |
| Retained-output budget exhausted, or geometry admits no recordable epoch | dispatch/advance | `TerminalResult`, `RunFailed` (`adapter-runtime-failed`); the geometry leg is reachable here because `dispatch(Resize(...))` moves the geometry between epochs |
| `ConptyConcurrentIOError`, unexpected `ConptyClosedError`, native error, resize failure | dispatch/advance | `TerminalResult`, `RunFailed` (`adapter-runtime-failed`) |
| Missing exit record where exit evidence is required | any | structured failure for that phase, never a fabricated `ExitStatus` |
| Forced stop | stop | `RunFinished(code 15)` with disclosure diagnostic |

Every terminal result — success or failure — closes the binding
(`force=True`) before returning: abort paths, forced stop, and also the
end-of-stream paths (`RunFinished`/`StartTerminated`), where the exit record
is captured before close and force-closing an already-exited tree only
releases the pty, job, and process handles. No handles, job objects, or
children outlive any terminal result — the leak freedom proven at the
binding level in slice 4 carries up unchanged.

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
  resize notifications. Boundary-insensitivity requirement: `feed(a + b)` is
  equivalent to `feed(a); feed(b)`, so the screen model depends on the
  concatenated text alone, never on how reads happened to chunk it.
- The observation's mandatory `ui.cursor` makes the normalizer a **hard
  dependency of any successful start** — `Started` cannot be constructed
  without cursor evidence, so no adapter slice may claim a successful run
  before a reviewed normalizer exists. Unit tests inject a fake normalizer.
  The shipped `ui` is minimal and truthful: no regions, no focus, cursor and
  mode from the screen model; semantic regions remain application-level
  concepts with no terminal enforcement.
- Raw evidence retention: each epoch's observation carries ordered
  `Event("terminal.output", {"chunk": <raw text>})` events containing the
  exact decoded chunks, including the readiness marker. Native read
  boundaries are not retained in transcripts: they are OS scheduling
  noise, so the recorder coalesces adjacent chunk events at record time
  (review finding R6, issue #195) — the adapter's in-memory observations
  keep the per-read chunks, and the recorded event preserves the exact
  concatenated text. Replaying the normalizer over the raw chunks must
  reproduce the frames — this is the replay check that makes frames
  trustworthy, and it aligns with the transcript schema's replay-subject
  `normalizer {id, version}` field: the normalizer's identity and version
  are recorded so a replay can verify it. The boundary-insensitivity
  requirement above is what keeps replay over coalesced chunks
  reproducing the same frames the live run's differently-chunked feeds
  produced.
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
enforcement and the capability registry remain blocked on the owner.
**Amended 2026-07-18:** containment enforcement is no longer merely blocked —
the owner retired it to an explicit non-goal; see the
[cooperation-tier constraint ports design](cooperation-tier-constraint-ports.md).

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
