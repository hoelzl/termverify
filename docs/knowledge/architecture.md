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
