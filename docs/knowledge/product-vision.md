---
type: Product Vision
title: TermVerify product vision
description: A reusable verification toolkit for autonomous terminal applications, and the sequenced scope it has not built yet.
tags: [agents, terminal, testing, verification]
---

# Problem

Terminal applications are often tested only through internal unit tests or fragile raw-output snapshots. Neither alone proves that a human or autonomous agent can drive the actual product reliably.

# Product

TermVerify is a reusable toolkit of contracts and runners for deterministic terminal interaction, structured observation, replay, and comparison. It is intended for games, editors, shells, dashboards, and other TUIs.

This document is the **single source** for scope that does not exist yet. Nothing below is a complete current capability — entries note plainly where partial machinery exists; `README.md` lists the current capabilities, and links here for the rest.

Other documents may *name* a planned item and link here — the README does, and [the verification model](verification-model.md) marks the layers and oracle types it describes `[planned]` — but the description, the rationale, and the sequencing live here and are not restated. That split exists because it failed once: the 2026-07-24 adversarial review found four of six README capabilities promised in the present tense with nothing in `src/` behind them (finding P5).

# Primary users

- maintainers of terminal/TUI applications;
- teams building coding agents that need executable feedback;
- developers who need durable regression evidence for interaction behavior.

# Intended architecture

The bracketed layers are not built. See *Planned scope* below for what each waits on.

```text
application under test
  ├── direct semantic adapter ── fast properties, replay, differential tests
  └── PTY adapter ───────────── real terminal interaction and rendering evidence
               │
          TermVerify
  ├── run configuration and interaction protocol   [built]
  ├── observation normalization and comparison     [built]
  ├── transcript replay                            [built]
  ├── shrinking / failure minimization             [planned]
  ├── property/state-machine support               [planned]
  └── reports and CI artifacts                     [planned]
```

The PTY adapter row is platform-neutral above its binding port, and only its Windows (ConPTY) binding is proven end to end; the POSIX path is planned.

# Planned scope

Stated once, here. Each entry says plainly what does not exist and what it waits on.

## A POSIX PTY adapter

The Ubuntu CI legs cannot yet exercise a real terminal end to end, so most TUIs run on a platform TermVerify has never driven through its own pipeline. This is the **first** planned item, not one among equals: the accepted direction is a vertical slice — a POSIX adapter plus one end-to-end `examples/` walkthrough that verifies a real, even trivial, TUI — before any further horizontal specification. Recorded as finding P6 and strategic recommendation 10 of the 2026-07-24 review, and tracked as the initiative in issue #204.

Two of that initiative's five slices have landed, which changes what remains rather than whether it remains. A real POSIX pseudoterminal binding exists (`termverify._posix_pty`, issue #267) and the adapter above the binding port is platform-neutral with `PosixPtyBinding` shipped beside `ConptyBinding` (issue #268). What does not exist is the evidence that the two work together: no leg anywhere drives a real subject through the adapter on a pty — readiness, a text epoch, a resize with observed dimensions, exit, forced stop, deadline abort. Until issue #269 lands that, the POSIX capability is planned scope and belongs here, not in the README, however much of its machinery is already in the package.

## Property and state-machine testing

TermVerify ships no property-testing support. `hypothesis` is a development dependency used only by TermVerify's own test suite; nothing in `src/` offers a strategy, a state machine, or a model-based runner to a subject author. Waits on the vertical slice above, which is what would show whether the useful unit is a strategy over inputs, over configurations, or over whole runs.

## Reviewed golden snapshots

The `termverify.baseline-approval/v1` sidecar format is specified and validator-tested, but the feature is disabled and no baseline files are committed. The governing rule is already accepted and unchanged: baselines are approved by a human against a human-readable diff, and agents never silently bless them. See [evidence governance](evidence-governance.md).

## Differential testing

Running the same script against two adapters — direct versus terminal, or a subject against a reference implementation — and diffing the transcripts is the intended payoff of the transcript being one closed, comparable artifact. `termverify.comparator` supplies the comparison half; nothing orchestrates the two runs. This was explicitly out of scope for the verification-core phase that built the comparator.

## Metamorphic oracles

Checking that an equivalent transformation of a run preserves a specified outcome — the same script at a different terminal size, or with equivalent input encodings. [The verification model](verification-model.md) lists this as an oracle type; nothing in `src/` supplies the transformation or the metamorphic equivalence relation. Shares the generator infrastructure with property testing above.

## State save/restore persistence

[The verification model](verification-model.md) lists a persistence oracle — save/load preserves canonical semantic state — as `[planned]`. No save or restore operation exists anywhere: the adapter surface is exactly start, dispatch, advance clock, and stop, and no input kind or transcript record captures a save or a load. The oracle needs those operations first, and the operations wait on a driving use case — a subject with real save/load semantics exercised through an adapter, which the vertical slice above is meant to surface.

## Failure minimization

Given a failing transcript, shrinking it to a minimal reproducing input sequence. Depends on property testing above for the generator side.

## CI artifacts and reports

Structured run reports and CI artifact uploads. Artifact uploads remain rejected until separately enabled, per [evidence governance](evidence-governance.md) — evidence can carry subject output, so publishing it is a governance decision before it is a feature.

# Non-goals

- replacing an application's domain test suite;
- prescribing a GUI framework or agent harness;
- making raw ANSI output the source of truth;
- automatically approving changed snapshots or behavioral baselines;
- OS-level containment of the subject: TermVerify verifies applications whose authors control the subject and is not an execution sandbox for adversarial code;
- adding browser bridging before a terminal vertical slice demonstrates that its abstraction is needed.
