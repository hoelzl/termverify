# Phase 1 Immutable Adapter Python Contract

- **Status:** accepted and implemented by PRs
  [#47](https://github.com/hoelzl/termverify/pull/47) and
  [#49](https://github.com/hoelzl/termverify/pull/49)
- **Date:** 2026-07-16
- **Depends on:** the accepted
  [execution contract](phase-1-adapter-execution-contract.md)
- **Scope:** public, framework-neutral Python values and structural protocols;
  no runner or adapter implementation

## Decision

The first Python adapter surface lives in `termverify.adapter`. It is a
synchronous, single-flight contract whose return values make lifecycle
boundaries explicit:

1. `Adapter.start()` returns `Started`, `StartTerminated`, `StartUnsupported`, or
   `StartFailed`.
2. `Adapter.dispatch()` accepts only the currently approved `TextInput` and
   `Resize` values and returns `EpochCompleted` or `TerminalResult`.
3. `Adapter.advance_clock()` accepts `ClockAdvance` separately so manual time
   cannot be confused with host waiting.
4. `Adapter.stop()` accepts `Stop` and always returns `TerminalResult`.

`Started` includes the complete constraint-specific receipt set, startup
`Diagnostic` values, and the initial readiness `Observation`. `StartTerminated`
combines that fully negotiated receipt set with a terminal result when the
subject exits during initialization. Adapter failure before readiness remains
`StartFailed`, including after complete negotiation. An ordinary
successful input returns `EpochCompleted`, which combines diagnostics with one
quiescent observation. A subject exit or adapter failure returns
`TerminalResult`, with optional final observation, diagnostics, and a typed
terminal outcome. These result objects make the accepted transcript lifecycle
representable without adding asynchronous callbacks or hidden polling.

The module is public but deliberately is not re-exported from the package root.
Callers import from `termverify.adapter`; the module's explicit `__all__` is the
compatibility boundary.

Issue #48 deliberately corrects the inception-v1 constructor contract in place:
`EnforcedConstraints`, `StartUnsupported`, and `StartFailed` now require the
active `run_id` and requested configuration. This is a breaking change from the
short-lived shape merged in PR #47, made before any published release or
supported consumer contract so invalid receipt provenance does not become the
compatibility baseline. Callers testing against that transient commit must pass
those two values explicitly. After this correction, `__all__` remains the
compatibility boundary for subsequent work.

## Immutable values

All contract records are frozen, slotted dataclasses or attribute-free immutable
scalar values. Sequence fields require exact tuples, and retained nested
contract objects require their exact declared runtime types.
Application-defined JSON values are copied recursively by `freeze_json()`:
arrays become tuples and objects become private mapping proxies whose nested
values are also frozen. Mutating the caller-owned source after construction
cannot change an observation, diagnostic, failure, or outcome.

JSON scalar subclasses and string-literal equality impostors are rejected rather
than retained or compared polymorphically. This prevents mutable attributes or
custom equality from crossing an otherwise frozen public boundary.

`RunConfiguration` is composed only of immutable constraint values. Its
`to_protocol()` method returns a fresh mutable JSON-shaped object matching the
reviewed transcript-v1 configuration. That conversion is one-way: mutable wire
objects are not stored inside the adapter contract.

Construction rejects invalid integers, identifiers, dimensions, endpoint
ordering, duplicate entries, malformed locale syntax, non-finite JSON numbers,
and structurally inconsistent observations. Cross-record state rules such as
manual-time progression remain the responsibility of the direct adapter and
runner because one standalone input cannot validate them.

## Enforcement receipts

The seven receipt classes are intentionally distinct. `EnforcedConstraints`
binds the active run identifier and requested configuration, requires the exact
receipt type in configuration order, and validates every receipt's run and
effective value against that request. Unsupported and failed startup results
likewise retain the active run, request, and only a valid enforced prefix.

`ConstraintPorts` makes the origin path structural: each `enforce_*` method
accepts only that constraint's requested value and returns only its matching
receipt, `ConstraintUnsupported`, or `AdapterFailure`. Strict mypy therefore
rejects substituting (for example) a clock receipt for a seed receipt
independently of the direct adapter implementation.

A receipt value is a typed claim, not an in-process security token. Constructing
a dataclass does not prove enforcement. `DirectAdapter` accepts a receipt only as
the synchronous return from the corresponding application port when its exact
type, active run, and effective value match the request. The port is obligated to
return only after enforcement, but the adapter cannot determine how the port
constructed an otherwise matching receipt or prove external enforcement.

The types also encode the currently accepted semantic gates:

- named-timezone receipts other than `UTC` are rejected until timezone
  membership/version/alias policy is approved;
- terminal receipts reject non-empty capability selectors until the semantic
  terminal-capability registry is approved;
- network receipts support deny enforcement only; allow-list enforcement
  remains deferred;
- terminal and network configuration can still carry the reviewed wire syntax,
  allowing an adapter to return structured unsupported results rather than
  silently weakening the request.

## Intentional omissions

This contract does not expose:

- `input.key`, because the key-name registry is not approved;
- mouse or clipboard dispatch, which are not needed by the first direct slice;
- ambient time, randomness, locale, timezone, filesystem, terminal, or network
  access;
- arbitrary asynchronous observations while idle;
- a runner, transcript producer, replay engine, comparator, or PTY implementation.
  Deterministic direct execution is implemented separately in `termverify.direct`.

Adding another input class or enforcement claim is a compatibility decision,
not an invitation to pass generic dictionaries through the protocol.

## Wire compatibility

This PR does not change `termverify.transcript/v1`. The existing transcript
validator remains the authority for wire acceptance. The immutable values are
producer-side inputs whose eventual transcript conversion must still pass that
validator and canonical serializer. Tuple use inside this Python API does not
weaken the codec rule that protocol JSON arrays must be represented by lists at
the parse/serialize boundary; `to_protocol()` and future producer conversion
must create fresh lists.

## Verification

Focused tests prove:

- valid configuration converts to the exact reviewed v1 shape;
- invalid and mutable-shaped construction is rejected;
- nested application JSON is copied and transitively immutable;
- observation and lifecycle result invariants fail closed, including terminal
  completion during initialization and exited-process evidence on failures;
- receipt type, order, run/request binding, effective-value equality, and
  deferred-enforcement gates are checked;
- a test-only adapter satisfies the structural protocol under strict mypy and
  can start, dispatch, advance manual time, observe, and stop without ambient
  dependencies;
- full repository, package, and independent-review gates pass.
