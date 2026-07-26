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
and — from Phase 2 slices 1–3 — the `termverify.recorder` transcript
recorder with its minimal scripted-run orchestrator, the
`termverify.comparator` exact comparator with its deterministic plain-text
report (equivalence excludes only the envelope `run_id`; the exclusion set
is closed), and the `termverify.replay` caller-bound replay engine
(selector agreement disclosed, never enforced). Oracle policies,
differential orchestration, and behavioral baselines remain outside the
accepted boundary.

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

## Process containment is bounded, and the boundary is disclosed

A subject's process tree is contained by a kill-on-close job object on Windows
and by a process group on POSIX. **Neither is escape-proof, and TermVerify does
not claim otherwise.** A process can leave the containment in a known way on
each platform: on POSIX by starting a new session (`setsid`), which no
process-group signal reaches; on Windows by being started inside the disclosed
microseconds-wide window between `CreateProcess` and job assignment, or by
descending from a child that exited before it could be assigned at all.

Such a survivor is **not reaped**. Reaping it portably would require cgroups or
a subreaper — horizontal platform machinery, rejected as out of scope by
recorded owner decision — so the honest position is disclosure, not a
guarantee. A verified run must not be read as asserting that no process
outlived it.

What *is* guaranteed, and what the platforms share, is narrower than the
containment claim it replaces:

- **Failure classification is identical on every platform.** A run ends in a
  structured result carrying a real exit record or a real forced-termination
  record. No record is fabricated, and no path ends in a hang.
- **A survivor cannot hold the verifier hostage.** This is the substantive
  guarantee, because the damaging case is not the orphan itself but the pipe
  end it holds: a reader blocked on a descriptor no containment can close used
  to wedge permanently, and to strand the teardown behind it. The POSIX pipe
  binding therefore interrupts its own blocked reads and writes through a
  self-pipe instead of relying on containment to reach the holder, so the abort
  deadline still produces a structured failure. Windows cannot use that
  mechanism — `select` does not work on anonymous pipe handles — and relies on
  the job object, so a holder outside the job remains a disclosed way to stall
  a teardown there.

The invariant behind both, stated because it has been violated twice: **release
every mechanism that can unblock an operation before performing an operation
that can block on it.** A teardown that blocks inside a `finally` cannot report
anything at all.

# Design constraints

- No required model provider, agent harness, web service, or GUI toolkit.
- Run configuration makes seed, clock, terminal dimensions, locale, timezone, filesystem root, and network policy explicit.
- The library owns generic protocols and comparison; applications own domain semantics through adapters and normalizers.
- An adapter either applies each requested deterministic constraint — at the
  strongest tier its mechanism supports, down to `delivered`, where honoring the
  value is subject cooperation — and reports the effective value with that tier,
  or returns a structured unsupported result before input dispatch; it never
  silently falls back to ambient state, and never records a tier stronger than
  the mechanism it used.
- Requested/effective equality does not prove enforcement. Each applied result
  is backed by a constraint-specific receipt from the path that applied the
  constraint; direct adapters can produce those receipts only through explicit
  application ports.
