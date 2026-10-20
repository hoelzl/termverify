---
type: Glossary
title: TermVerify glossary
description: Core TermVerify vocabulary and the historical names used by older decision records.
tags: [glossary, terminology, renames]
---

# Glossary

## Core vocabulary

| Term | Meaning | Defined in |
| --- | --- | --- |
| Adapter | Drives one verified run of a subject: negotiates constraints, dispatches inputs, and captures observations. | [Architecture](architecture.md) |
| Binding | The platform layer beneath the terminal adapter's binding port, such as `ConptyBinding` or `PosixPtyBinding`. | [Architecture](architecture.md) |
| Capability result | The per-constraint receipt a run records before any input: `applied` with an effective value and tier, or `unsupported`. | [Deterministic constraints](protocol/deterministic-constraints.md) |
| Enforcement tier | How much an `applied` receipt is worth: `os`, `constructive`, or `delivered`. A `delivered` receipt is not containment. | [Enforcement tiers](protocol/deterministic-constraints.md#enforcement-tiers) |
| Epoch | One input, the diagnostics it caused, and the observation that closes it at deterministic quiescence, unless a terminal record closes it first. | [Envelope and lifecycle](protocol/envelope-and-lifecycle.md) |
| Observation | Normalized evidence captured at a quiescent point: state, events, UI, and optional frame and process layers. | [Inputs and observations](protocol/inputs-and-observations.md) |
| Subject | The application under test; a transcript identifies it by its versioned replay selector. | [Envelope and lifecycle](protocol/envelope-and-lifecycle.md) |
| Transcript | One canonical JSONL record of one verified run (`termverify.transcript/v1`). | [Protocol](protocol.md) |

## Historical names

Older decision records and handovers keep the names that were current when
they were written. The decisions they record are unchanged by these renames;
only the names moved.

| Renamed | Old name | Current name |
| --- | --- | --- |
| #218 (2026-07-29) | `ConstraintPorts.enforce_*` | `ConstraintPorts.apply_*` |
| #218 (2026-07-29) | `EnforcedConstraints` | `AppliedConstraints` |
| #218 (2026-07-29) | `UnenforcedConstraintPorts` | `ApplyNothingConstraintPorts` |
| #268 (2026-08-01) | module `termverify.conpty` (`src/termverify/conpty.py`) | `termverify.terminal` (`src/termverify/terminal.py`) |
| #268 (2026-08-01) | `ConptyAdapter` | `TerminalAdapter` |
| #268 (2026-08-01) | `ConptyBindingPort`, `ConptyChildPort`, `ConptyWatchdogPort` | `TerminalBindingPort`, `TerminalChildPort`, `TerminalWatchdogPort` |

Deliberately unchanged: `EnforcementReceipt`, `EnforcementTier`,
`termverify.enforcement-tier/v1`, and the `constraint-not-enforced` wire code
keep their names after #218 — the rename aligned names with the wire's
`applied` status, and these name the tier, the receipt, or a stable error code
rather than the status. `ConptyBinding`
keeps its name after #268: it is one of two implementations of the neutral
binding port, beside `PosixPtyBinding`, and every ConPTY-specific behavior an
older record describes is still a property of that binding. The private
native binding module `termverify._conpty` is unrelated to the old public
`termverify.conpty` module name.
