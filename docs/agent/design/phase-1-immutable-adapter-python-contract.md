# Phase 1 Immutable Adapter Python Contract

- **Status:** proposed implementation for issue
  [#46](https://github.com/hoelzl/termverify/issues/46)
- **Date:** 2026-07-16
- **Depends on:** the accepted
  [execution contract](phase-1-adapter-execution-contract.md)
- **Scope:** public, framework-neutral Python values and structural protocols;
  no runner or adapter implementation

## Decision

The first Python adapter surface lives in `termverify.adapter`. It is a
synchronous, single-flight contract whose return values make lifecycle
boundaries explicit:

1. `Adapter.start()` returns `Started`, `StartUnsupported`, or `StartFailed`.
2. `Adapter.dispatch()` accepts only the currently approved `TextInput` and
   `Resize` values and returns `EpochCompleted` or `TerminalResult`.
3. `Adapter.advance_clock()` accepts `ClockAdvance` separately so manual time
   cannot be confused with host waiting.
4. `Adapter.stop()` accepts `Stop` and always returns `TerminalResult`.

`Started` includes the complete constraint-specific receipt set, startup
`Diagnostic` values, and the initial readiness `Observation`. An ordinary
successful input returns `EpochCompleted`, which combines diagnostics with one
quiescent observation. A subject exit or adapter failure returns
`TerminalResult`, with optional final observation, diagnostics, and a typed
terminal outcome. These result objects make the accepted transcript lifecycle
representable without adding asynchronous callbacks or hidden polling.

The module is public but deliberately is not re-exported from the package root.
Callers import from `termverify.adapter`; the module's explicit `__all__` is the
compatibility boundary.

## Immutable values

All contract records are frozen, slotted dataclasses or immutable scalar
values. Sequence fields require tuples. Application-defined JSON values are
copied recursively by `freeze_json()`: arrays become tuples and objects become
private mapping proxies whose nested values are also frozen. Mutating the
caller-owned source after construction cannot change an observation,
diagnostic, failure, or outcome.

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
requires the exact receipt type in configuration order and requires every
receipt to name the same deterministic run. Unsupported and failed startup
results retain only a valid enforced prefix.

`ConstraintPorts` makes the origin path structural: each `enforce_*` method
accepts only that constraint's requested value and returns only its matching
receipt, `ConstraintUnsupported`, or `AdapterFailure`. Strict mypy therefore
rejects substituting (for example) a clock receipt for a seed receipt before
the direct adapter exists.

A receipt value is a typed claim, not an in-process security token. Constructing
a dataclass does not prove enforcement. The follow-up direct adapter may accept
a receipt only as the synchronous return from the corresponding application
port, after the operation completes, for the active run and requested value.
It must reject a receipt synthesized from requested configuration or returned
by another path.

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
- a runner, transcript producer, replay engine, comparator, fake/direct adapter,
  or PTY implementation.

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

Focused tests must prove:

- valid configuration converts to the exact reviewed v1 shape;
- invalid and mutable-shaped construction is rejected;
- nested application JSON is copied and transitively immutable;
- observation and lifecycle result invariants fail closed;
- receipt type, order, run binding, and deferred-enforcement gates are checked;
- a test-only adapter satisfies the structural protocol under strict mypy and
  can start, dispatch, advance manual time, observe, and stop without ambient
  dependencies;
- full repository, package, and independent-review gates pass.
