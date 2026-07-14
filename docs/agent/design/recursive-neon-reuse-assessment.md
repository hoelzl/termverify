# Recursive://Neon Reuse Assessment

Recursive://Neon is a valuable source of proven terminal interaction and parity-harness ideas. TermVerify will mine it deliberately rather than copying a subsystem before its own contracts are defined.

## Concepts to reuse or adapt

- PTY lifecycle management, key-sequence notation, readiness conditions, and semantic screen snapshots.
- The distinction between raw terminal evidence and fields such as body, cursor, mode/status area, and prompts.
- Scenario-based differential testing with explicit, documented intentional divergences.
- CI gating that fails on unexpected divergence and identifies stale approved baselines.
- CLI-first delivery: exercise terminal interaction before adding browser transport.

## Differences to preserve

Recursive://Neon's parity harness is specialized around GNU Emacs as a reference target. TermVerify must also work when there is no external golden master. Its general model therefore makes semantic, replay, property, metamorphic, persistence, and snapshot oracles peers.

## Reuse procedure

1. Identify an exact candidate file or behavior and its Apache-2.0 provenance.
2. Write a TermVerify behavior contract before transplanting code.
3. Extract the smallest independently useful component.
4. Remove project-specific assumptions and add tests for the generic contract.
5. Record attribution and licensing requirements in `NOTICE` when source is incorporated.
6. Verify the component in both a direct-adapter and PTY-facing scenario where applicable.

No code has been copied at project initialization time.
