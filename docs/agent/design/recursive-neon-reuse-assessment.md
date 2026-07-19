# Recursive://Neon Reuse Assessment

Recursive://Neon is a valuable external subject and source of proven terminal interaction and parity-harness ideas. TermVerify will integrate with the living application before copying any subsystem.

## Status (reassessed 2026-07-19)

The original assessment predated the immutable adapter runtime. At TermVerify
`2c514be3805a2a24892d9f57bfe1ea12d74c70d9`, the direct integration can begin:

- `Adapter`, `ConstraintPorts`, `DirectApplication`, `DirectAdapter`, immutable
  observations, explicit readiness/quiescence, and semantic key input exist;
- the Windows path has a production ConPTY adapter, explicit readiness-marker
  epochs, a fail-closed VT normalizer, cooperation-tier constraint delivery,
  resize/process evidence, and `termverify.key-encoding/v1` dispatch; PR #144's
  durable Windows-matrix evidence proves a cooperative raw-mode child observes
  exact registry bytes for one representative of every encodable family class,
  replay identity holds, and an unencodable chord fails closed on the real
  adapter with OS-observed teardown;
- Phase 2 remains inactive: no generic scenario runner or transcript recorder,
  comparator, subject replay, report, differential orchestration, or governed
  content-preserving behavior-baseline workflow exists;
- the external adapter-author types are documented at their module paths but are
  not yet presented as a curated top-level compatibility surface or example.

This matches the evidence from another external subject in
[issue #114](https://github.com/hoelzl/termverify/issues/114): GlyphWright's
direct spike passes, but it had to hand-write transcript recording and cannot
yet ask TermVerify to compare or replay the resulting evidence.

PR #144 removes the prior generic key-delivery evidence gap but does not supply
the missing verification core. The recommendation is therefore unchanged, with
greater confidence in the later ConPTY profile: direct/core first, then a
subject-specific marker-emitting terminal harness. That harness still must prove
RecursiveNeon's raw-input compatibility, readiness after every completed epoch,
constraint cooperation, and VT-subset coverage; TermVerify does not claim
key-support negotiation or input-mode tracking for the subject.

## Example boundary

The first RecursiveNeon integration is the living editor through a direct,
in-process adapter. Work on that tracer can begin now, but a successful run must
wait until the subject can truthfully issue constructive receipts for all seven
constraints. The core profile therefore uses production editing and rendering
behavior with an explicit core keymap and semantic observation projection, keeps
RecursiveNeon's in-memory virtual filesystem, disables game, NPC, shell-mode,
hosted-app, user-configuration, and asynchronous features initially, and proves
registry isolation plus the absence of clock, network, and host-filesystem access.

That is a real editor in a deterministic simulated environment, not a toy editor.
RecursiveNeon's UUID-backed virtual filesystem is a security boundary; the
TermVerify example must not add native host-file access to game or editor logic.
A native-host editor or command-line application should be a separate TermVerify
subject that exercises delivered sandbox roots, real subprocesses, and host path
normalization without contaminating RecursiveNeon.

Adoption order:

1. experimental living-checkout direct editor tracer;
2. supported direct example after runner/recorder/comparison/replay/report exist;
3. optional provenance-tracked reduced snapshot after the living integration;
4. dedicated RecursiveNeon ConPTY harness emitting a readiness marker after
   startup and every completed input/resize epoch;
5. selected GNU Emacs differential scenarios after multi-target orchestration;
6. direct shell, full terminal shell, and browser transport as separate later
   capability tranches.

## Concepts to reuse or adapt

- PTY lifecycle management, key-sequence notation, readiness conditions, and semantic screen snapshots.
- The distinction between raw terminal evidence and fields such as body, cursor, mode/status area, and prompts.
- Scenario-based differential testing with explicit, documented intentional divergences.
- CI gating that fails on unexpected divergence and identifies stale approved baselines.
- CLI-first delivery: exercise terminal interaction before adding browser transport.

## Differences to preserve

Recursive://Neon's parity harness is specialized around GNU Emacs as a reference target. TermVerify must also work when there is no external golden master. Its general model therefore makes semantic, replay, property, metamorphic, persistence, and snapshot oracles peers.

RecursiveNeon's existing PTY driver is also not a substitute for TermVerify's
ConPTY adapter: its readiness calls are not consistently fail-closed and its
teardown does not provide TermVerify's process/drain evidence. Reuse scenario
intent, not transport lifecycle code.

The direct and terminal profiles also expose different evidence. Direct execution
can report structured editor state; ConPTY currently reports normalized terminal
frames, cursor, raw output, and process evidence. Full cross-mode semantic
agreement requires a separately designed structured telemetry channel and a
generic cross-mode comparator. Without those, compare only shared frame/cursor
evidence and assert direct semantic outcomes independently.

## Reuse procedure

1. Identify an exact candidate file or behavior and its Apache-2.0 provenance.
2. Prove the existing TermVerify behavior contract against the living checkout
   before transplanting code.
3. Extract the smallest independently useful component.
4. Remove project-specific assumptions and add tests for the generic contract.
5. Record attribution and licensing requirements in `NOTICE` when source is incorporated.
6. Verify the component first through the direct adapter and then, where
   applicable, through a dedicated readiness-marker ConPTY executable.

No code has been copied at project initialization time.
