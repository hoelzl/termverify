---
type: Verification Model
title: Evidence and oracle model
description: Layered verification rules for autonomous terminal applications.
tags: [verification, replay, properties, snapshots, differential-testing]
---

# Evidence hierarchy

1. Structured state and ordered domain events.
2. Deterministic transcript replay.
3. Property and state-machine tests.
4. Differential tests against a genuine reference when available.
5. Reviewed semantic UI snapshots.
6. Raw terminal bytes and ANSI frames as diagnostics.

# Oracle types

A golden master is optional, never the only oracle.

- **Semantic:** explicit expected state/event assertions.
- **Replay:** a stored action transcript produces the approved outcome.
- **Property:** generated input preserves invariants.
- **Differential:** candidate and reference agree after normalization.
- **Metamorphic:** an equivalent transformation preserves a specified outcome.
- **Snapshot:** a reviewed normalized UI observation remains stable.
- **Persistence:** save/load preserves canonical semantic state.

# Baseline governance

Changed snapshots or approved divergences are behavioral changes. They need a readable diff, rationale, and independent review. CI detects unapproved changes; it does not create approval.

The accepted [evidence-governance policy](evidence-governance.md) defines the
redaction, capture, metadata, and validation controls that must be accepted and
implemented before baseline files or CI evidence artifacts are introduced.
