---
type: Verification Model
title: Evidence and oracle model
description: Layered verification rules for autonomous terminal applications.
tags: [verification, replay, properties, snapshots, differential-testing]
---

This document is the **model** TermVerify is built toward. It is not a
capability list: several layers and oracle types below have no implementation,
and are marked `[planned]`. What exists today is in `README.md`; why the
planned items are sequenced the way they are is in
[the product vision](product-vision.md), which is the single source for that.

# Evidence hierarchy

1. Structured state and ordered domain events.
2. Deterministic transcript replay.
3. Property and state-machine tests. `[planned]`
4. Differential tests against a genuine reference when available. `[planned]`
5. Reviewed semantic UI snapshots. `[planned]`
6. Raw terminal bytes and ANSI frames as diagnostics.

# Oracle types

A golden master is optional, never the only oracle.

- **Semantic:** explicit expected state/event assertions.
- **Replay:** a stored action transcript reproduces the recorded outcome.
- **Property:** generated input preserves invariants. `[planned]`
- **Differential:** candidate and reference agree after normalization. `[planned]`
- **Metamorphic:** an equivalent transformation preserves a specified outcome. `[planned]`
- **Snapshot:** a reviewed normalized UI observation remains stable. `[planned]`
- **Persistence:** save/load preserves canonical semantic state. `[planned]`

`[planned]` marks an oracle TermVerify does not yet supply machinery for. The
unmarked ones need no machinery beyond what ships: semantic oracles are
ordinary assertions over observations, and replay is `termverify.replay`. A
persistence oracle additionally needs save/load operations on the adapter
surface, which do not exist yet.

# Baseline governance

For baselines committed to the TermVerify repository, changed baseline files or
approved divergences are behavioral changes. They need a readable diff,
rationale, and explicit human review. Review may be independent or, while the
repository has one maintainer, an explicitly recorded maintainer self-review.
The evidence-governance validator — run by local pre-commit and by CI — rejects
a baseline whose approval or readable-diff records do not match; it never
creates approval. No baseline files are committed today, and the snapshot layer
above is `[planned]`. This repository policy does not prescribe baseline
governance for downstream projects.

The accepted [evidence-governance policy](evidence-governance.md) defines the
redaction, capture, metadata, and validation controls that must be accepted and
implemented before baseline files or CI evidence artifacts are introduced.
