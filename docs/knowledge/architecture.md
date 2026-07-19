---
type: Architecture
title: TermVerify architecture
description: A layered adapter and runner design for semantic and production-terminal verification.
tags: [architecture, adapters, pty, terminal]
---

# Architecture

TermVerify separates application control from verification policy.

```text
Application under test
  ├── direct adapter: fast commands and structured observation
  └── production adapter: PTY/subprocess terminal path
                         │
                    TermVerify runners
  ├── deterministic run configuration
  ├── transcript dispatch and replay
  ├── observation normalization
  ├── comparator/oracle policies
  ├── property and state-machine integration
  └── reports and failure artifacts
```

The runner, comparison/replay, oracle-policy, and reporting rows describe the
Phase 2 verification-core layer, active under the accepted
`phase-2-verification-core-boundary.md` decision. At the current pre-release
boundary, TermVerify ships the adapter/runtime contracts, direct and Windows
terminal adapters, transcript codec/validation, safe redacted persistence,
and — from Phase 2 slice 1 — the `termverify.recorder` transcript recorder
with its minimal scripted-run orchestrator. Transcript comparison, replay,
oracle policies, and reports remain unimplemented until their authorized
slices land.

# Boundary

Applications expose a small adapter surface: start a deterministic run, dispatch an input event, advance an explicit clock, observe structured state/UI evidence, optionally save/restore state, and stop.

Phase 1 serializes that surface into single-flight execution epochs. Complete
capability negotiation is followed by one positional initial readiness
observation. Each later input is drained to an application-port-reported
quiescent observation or terminal result before another input is accepted.
Quiescence never depends on wall-clock quiet periods. The accepted
[adapter execution contract](../agent/design/phase-1-adapter-execution-contract.md)
defines readiness, causality, stop/drain behavior, and enforcement receipts
for the public immutable contracts and direct execution path. The protocol
validator, canonical fixtures, and generative property model implement the same
lifecycle semantics. `termverify.direct.DirectAdapter` composes explicit
constraint and application ports without consulting ambient time, terminal, or
process state.

The direct adapter is the default for fast unit and property tests. The Windows
production path is `termverify.conpty.ConptyAdapter`, layered over the reviewed
ConPTY binding and fail-closed `termverify.vt.VtScreenNormalizer`. It verifies
real terminal input, rendering, resize, EOF/exit evidence, forced teardown, and
process-tree handling through explicit readiness-marker epochs. A successful
Windows integration run has exercised the real binding, cooperation-tier
constraint delivery, text input, normalized/replayable frames, resize, and
observed exit. `termverify.key-encoding/v1` dispatch is implemented; real-child
Windows-matrix evidence proves exact byte delivery to a cooperative raw-mode
subject for one representative of every encodable family class, replay identity,
native exit through an in-band key, and fail-closed unencodable input with
OS-observed teardown. This is delivery evidence, not key-support negotiation,
input-mode tracking, or a claim that an arbitrary subject decodes every chord.

The production adapter does not claim OS filesystem/network containment. Its
terminal dimensions receipt is OS-level; the other constraints require explicit
subject-cooperation ports whose `delivered` receipts disclose delivery rather
than subject compliance. Non-empty terminal capabilities remain unsupported.
There is no POSIX PTY adapter yet. Browser bridging remains deferred until the
direct and terminal vertical slices prove that a shared abstraction is needed.

# Design constraints

- No required model provider, agent harness, web service, or GUI toolkit.
- Run configuration makes seed, clock, terminal dimensions, locale, timezone, filesystem root, and network policy explicit.
- The library owns generic protocols and comparison; applications own domain semantics through adapters and normalizers.
- An adapter either enforces each requested deterministic constraint and reports
  its effective value, or returns a structured unsupported result before input
  dispatch; it never silently falls back to ambient state.
- Requested/effective equality does not prove enforcement. Each enforced result
  is backed by a constraint-specific receipt from the path that applied the
  constraint; direct adapters can produce those receipts only through explicit
  application ports.
