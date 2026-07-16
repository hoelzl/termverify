---
type: Architecture
title: TermVerify architecture
description: A layered adapter and runner design for semantic and PTY-backed terminal verification.
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

# Boundary

Applications expose a small adapter surface: start a deterministic run, dispatch an input event, advance an explicit clock, observe structured state/UI evidence, optionally save/restore state, and stop.

Phase 1 serializes that surface into single-flight execution epochs. Complete
capability negotiation is followed by one positional initial readiness
observation. Each later input is drained to an application-port-reported
quiescent observation or terminal result before another input is accepted.
Quiescence never depends on wall-clock quiet periods. The accepted
[adapter execution contract](../agent/design/phase-1-adapter-execution-contract.md)
defines readiness, causality, stop/drain behavior, and enforcement receipts
before public adapter types are introduced. This is the accepted target model;
the current v1 validator and canonical fixture remain authoritative until the
normative protocol, fixture, validator, and property model migrate together.

The direct adapter is the default for fast unit and property tests. The
production adapter verifies the real terminal path: input decoding, focus,
prompt handling, rendering, resize, and process lifecycle. Browser bridging is
deferred until a terminal vertical slice proves that a shared abstraction is
necessary.

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
