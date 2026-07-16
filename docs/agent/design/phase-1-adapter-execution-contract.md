# Phase 1 Adapter Execution Contract

- **Status:** accepted by the maintainer on 2026-07-16; executable lifecycle
  enforcement and canonical fixtures are tracked by
  [#44](https://github.com/hoelzl/termverify/issues/44), while public adapter
  types remain follow-up work.
- **Issue:** [#42](https://github.com/hoelzl/termverify/issues/42)
- **Date:** 2026-07-16
- **Scope:** API-neutral execution semantics for the fake/direct adapter and the
  narrow terminal lifecycle feasibility slice.

## Context

The transcript codec already validates deterministic configuration, ordered
capability results, manual-clock timestamps, defined record shapes, and one
final terminal record. Those rules do not yet say when an adapter is ready,
which observation closes an input dispatch, how deterministic quiescence is
established, or what evidence permits an adapter to claim that a requested
constraint was enforced. Implementing public adapter types before those rules
exist would turn incidental implementation choices into protocol behavior.

The project therefore adopts a deliberately serialized Phase 1 execution
model. It preserves deterministic replay and leaves explicit concurrent
correlation for a later protocol version if a real application requires it.
This decision authorizes an inception-v1 lifecycle correction under the
accepted pre-client compatibility policy. It requires no new record member or
kind. Issue #44 migrates the normative protocol prose, fixtures, validator, and
property model together; public adapter implementation remains outside this
decision document.

## Decision

### Execution states

A verified run follows this state machine:

```text
created
  -> negotiating
       -> unsupported -> terminal
       -> failed      -> terminal
       -> initializing
            -> failed         -> terminal
            -> subject exited -> terminal
            -> ready -> idle
                         -> input epoch -> idle | failed | subject exited
                         -> stopping    -> terminal
                         -> failed      -> terminal
                         -> subject exited -> terminal
```

`terminal` is absorbing. No operation or record follows it.

### Transactional negotiation

After `run.started`, the adapter attempts constraints in the protocol table
order. Each successful attempt returns a constraint-specific enforcement
receipt and emits one matching `capability.result` with `status: enforced`.
The adapter does not expose a dispatch-capable run handle until all requested
constraints are enforced.

The first unsupported constraint emits its `capability.result` followed
immediately by matching `run.unsupported`. It emits no observation or input.
An adapter fault may instead terminate negotiation with `run.failed`; zero or
more earlier constraints may already have emitted enforced results. A failed
negotiation is not an unsupported constraint and must not manufacture an
`unsupported` result.

### Initial readiness

A fully negotiated run enters initialization and emits exactly one initial
`observation` before accepting its first input. Zero or more diagnostics may
precede that observation after negotiation. The observation's position is the
v1 readiness marker; v1 does not add a `ready` flag or phase member. If the
subject exits during initialization, the adapter may emit one final observation
and then `run.finished` without ever accepting input.

For a direct adapter, readiness means the application-facing start operation
has completed, all deterministic ports are installed, and the returned state,
events, and UI evidence are a stable initial observation. For the terminal
feasibility slice, readiness additionally requires that the child and its
independent I/O drains have started and that initial terminal dimensions were
applied before the child could observe them.

A capture or adapter failure before the initial observation emits `run.failed`.
No input may be dispatched merely because capability negotiation completed.

### Single-flight input epochs

Phase 1 accepts at most one input dispatch at a time. Every non-stop input opens
one causal epoch. Until that epoch closes, the adapter rejects another input.
The epoch contains the input record, zero or more diagnostics, and then either:

- exactly one quiescent observation, which closes the epoch and returns the run
  to idle;
- a final optional observation followed by `run.finished` if the subject exits;
- or `run.failed` if dispatch, draining, normalization, or capture fails.

Transcript position supplies causality: the records after an input and before
its closing observation or terminal result belong to that input epoch. V1 does
not add correlation identifiers. A future concurrent adapter requires an
explicitly versioned correlation design rather than weakening this rule.

### Deterministic quiescence

A direct adapter reaches quiescence only when its application-facing port
reports that no deterministic work is pending and the adapter has synchronously
drained all currently available domain events and output for the epoch. The
port report is part of the application contract; an adapter may not infer it
from elapsed host time, an empty read observed once, thread scheduling, or a
quiet-period timeout.

Manual-clock work remains pending until the transcript dispatches
`input.clock_advanced`. The adapter never advances time to make an epoch settle.
If the application cannot expose a deterministic completion/quiescence boundary,
the adapter contract is incompatible with that application: initialization
ends with `run.failed` using `adapter-start-failed` rather than inventing a
configuration constraint or using a sleep or timeout as proof. A missing port
for one of the seven named deterministic constraints instead produces the
matching unsupported capability result during negotiation.

The first direct-adapter slice admits no unsolicited body records while idle.
State changes and events arise only from startup, the active input epoch, or an
explicit manual-clock advance. General spontaneous/asynchronous observations
need a future explicit polling or correlation contract. Diagnostics do not
create a hidden epoch and cannot carry semantic state transitions.

### Stop and draining

`input.stop` is the final accepted input and opens the stopping epoch. No later
input is valid. The adapter requests graceful subject termination through its
explicit stop port, continues draining output and events, and then emits:

- an optional final observation followed by `run.finished` when subject
  completion is observed; or
- `run.failed` when stop, drain, capture, or teardown fails.

A subject may also exit during startup or a non-stop input epoch. Once that
exit is observed, the adapter drains the epoch, may emit one final observation,
and emits `run.finished`. `run.finished` describes subject completion, including
its exit code or signal and means that no cleanup failure was observed. It does
not attest that unobservable or best-effort external cleanup fully succeeded;
a detected cleanup failure produces `run.failed` instead.

`run.failed` describes an adapter, harness, enforcement, dispatch, drain,
normalization, capture, or cleanup failure. An exited-process observation may
precede it when subject exit was captured before the adapter failure. That exit
evidence is orthogonal to the failure object because `run.failed` has no subject
exit value to match. `run.unsupported` remains negotiation-only and therefore
cannot contain exited-process body evidence.

For terminal implementations, EOF or a platform-equivalent broken output
channel is the completion evidence for output draining. A quiet output period
is not EOF. Windows ConPTY communication channels must remain independently
serviced through teardown because closing can emit a final frame and connected
clients may continue writing until they disconnect.

### Capability enforcement receipts

Requested/effective equality is necessary but never sufficient to claim
`status: enforced`. Each constraint attempt returns an internal typed receipt
from the path that applied the constraint. The adapter validates the receipt
before emitting the result. Receipts are not added to transcript v1; the
transcript carries their normalized effective value while executable adapter
contract tests prove their origin.

The minimum receipt meanings are:

| Constraint | Required enforcement-path evidence |
| --- | --- |
| `seed` | The application start path installed the requested unsigned seed before subject initialization. |
| `clock` | The subject received the requested manual-clock port and initial value; host elapsed time is not the port's source. |
| `locale` | The application port or subprocess-start path applied the requested locale before subject initialization and returned its effective selector. Syntax acceptance alone is not evidence. |
| `timezone` | The application port or subprocess-start path applied the requested timezone before subject initialization and returned its effective selector. Membership and tzdb policy remain a separate gate. |
| `terminal` | Initial dimensions and the approved semantic terminal capabilities were installed before subject initialization; later resize uses the same controlled path. |
| `filesystem` | A direct application port received the named sandbox root capability. A terminal/subprocess adapter reports unsupported until OS containment, traversal, link, child-process, and cleanup behavior are proven. |
| `network` | A direct application port received an enforcing deny/mediation capability. A terminal/subprocess adapter reports unsupported until OS-level network denial is proven. Allow-list enforcement remains deferred. |

A receipt is invalid if it is synthesized from the requested configuration,
returned before the enforcement operation completes, belongs to another run or
constraint, or reports a different effective value. Public receipt types are a
follow-up API decision; this document defines their required semantics only.

## Vocabulary ownership

### Keys

TermVerify will own a closed, versioned semantic key-name registry. Named
non-text keys will be selected from or deliberately mapped to stable W3C UI
Events `KeyboardEvent.key` meanings where they fit terminal interaction.
Printable insertion remains `input.text`; the registry does not duplicate
locale-dependent printable characters or expose physical keyboard locations.
Toolkit names, OS virtual-key codes, escape byte sequences, curses names, and
application-specific key enums are adapter mappings, not protocol values.

The initial registry, modifier/chord notation, spelling, and case require their
own executable compatibility review before `input.key` is exposed by a public
adapter. Existing non-empty-string validation and fixture values establish only
wire syntax, not an approved semantic registry.

### Terminal capabilities

TermVerify will likewise own a closed, versioned registry of semantic terminal
capabilities. Raw terminfo names are not the portable protocol: terminfo mixes
Boolean, numeric, and control-sequence capabilities and permits
implementation-specific installation and extensions. Host terminfo contents,
terminal model aliases, toolkit feature flags, and raw escape sequences are
inputs to adapter mapping and attestation, not v1 capability names.

The initial registry must define observable semantics and enforcement evidence
for each entry. Existing values such as `ansi` remain syntax-only inception
placeholders until that registry is reviewed; an adapter must not claim them as
enforced merely because the string is present in requested and effective
configuration.

## Direct and terminal boundaries

The fake/direct adapter is the first executable implementation of this state
machine. It may report enforcement only through explicit application ports and
must report unsupported when a port is absent or cannot establish the receipt.
It does not simulate OS containment.

The Phase 1 terminal work is an internal feasibility slice, not a production
adapter. It proves create, independent input/output drain, initial size, resize,
stop, EOF/exit observation, and cleanup with synthetic evidence. It does not
produce a verified body transcript unless every requested deterministic
constraint is truthfully enforced. Filesystem containment and network policy
remain unsupported until their accepted OS-level boundaries are demonstrated.

## Wire and validator consequences

Follow-up executable work must update the v1 lifecycle validator and fixtures
to enforce:

1. optional `run.failed` during negotiation, including before the first
   capability result;
2. exactly one initial observation after complete enforcement and before input;
3. one open input epoch at a time;
4. one quiescent observation closing each successful non-stop epoch;
5. stop as the final input;
6. `run.unsupported` only immediately after the first unsupported capability;
7. terminal closure of incomplete epochs on subject exit or adapter failure;
8. no unsolicited direct-adapter body records while idle.

These are accepted inception-v1 lifecycle corrections. They add no generic
member and do not authorize exhaustive schema work. Issue #44 updates protocol
prose, fixtures, validator, and property model as one reviewed candidate. The
public adapter/runtime entry gate remains closed until immutable contract types
and enforcement receipts are implemented and reviewed.

## Deferred decisions

This contract intentionally does not decide:

- the initial key-name or terminal-capability entries;
- explicit correlation for concurrent or unsolicited events;
- timezone database/version/alias policy;
- terminal filesystem containment or network allow-list semantics;
- transcript, line, record-count, nesting, or structured-value resource limits;
- schema package access and canonical `$id` hosting;
- production PTY API or dependency selection;
- sensitive evidence retention, baseline enablement, or artifact upload.

Each requires a focused issue and independently reviewable acceptance evidence.

## Acceptance evidence

Issue #44 supplies model-based lifecycle tests that demonstrate legal
transitions and reject input before readiness, overlapping epochs, idle
unsolicited records, input after stop, unsupported body records, body after
process exit, and records after terminal. Canonical fixtures cover startup
failure, unsupported negotiation, initial readiness, successful input epochs,
natural subject exit, and stop/drain. False enforcement receipts remain an
adapter-contract test requirement. The terminal feasibility slice must use a
harmless synthetic child and distinguish EOF/exit evidence from quiet-period
timing.

## References

- [TermVerify transcript protocol](../../knowledge/protocol.md)
- [Phase 1 protocol and Windows PTY boundary](phase-1-protocol-and-windows-boundary.md)
- [W3C UI Events KeyboardEvent key Values](https://www.w3.org/TR/uievents-key/)
- [The Open Group terminfo source format](https://pubs.opengroup.org/onlinepubs/7908799/xcurses/terminfo.html)
- [Microsoft pseudoconsole session guidance](https://learn.microsoft.com/en-us/windows/console/creating-a-pseudoconsole-session)
- [Microsoft `ClosePseudoConsole` guidance](https://learn.microsoft.com/en-us/windows/console/closepseudoconsole)
