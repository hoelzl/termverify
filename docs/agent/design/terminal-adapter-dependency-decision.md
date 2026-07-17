# Terminal Adapter Dependency and Verification Decision

- **Status:** accepted — decided 2026-07-17 under the maintainer's delegated
  autonomous authority; the exact candidate passed independent adversarial
  agent review before merge; this document is the "separately accepted dependency and
  verification decision" that the pre-release boundary hardening handover
  requires before any spike promotion or `pywinpty` dependency.
- **Issue:** [#102](https://github.com/hoelzl/termverify/issues/102)
- **Date:** 2026-07-17
- **Inputs:** PR #53 spike evidence (`spikes/conpty-lifecycle/`),
  [Phase 1 protocol and Windows boundary decision](phase-1-protocol-and-windows-boundary.md),
  Workstream 5 of the
  [pre-release boundary hardening handover](../handovers/pre-release-boundary-hardening-handover.md).

## Decision

The first production terminal adapter targets Windows ConPTY through
**`pywinpty`, pinned, using `winpty.Backend.ConPTY` exclusively**. Legacy
WinPTY, stdlib `pty`, and a raw `ctypes` binding are rejected. Accepting this
decision authorizes implementation slices to add the pinned dependency and
build the adapter behind the verification plan below; it does not itself add
the dependency, promote the spike, or claim that any adapter exists.

The adapter's public boundary is the existing `Adapter`/`ConstraintPorts`
contract in `termverify.adapter`: the same immutable receipt, observation,
epoch, and terminal-result types the direct adapter produces, with identical
fail-closed semantics. On any platform, architecture, or Windows release where
the verified behavior below is not proven, the adapter reports structured
unsupported or failure results before input dispatch; it never degrades
silently and never fabricates a receipt.

## Rationale

- The PR #53 spike is the only executable feasibility evidence in the
  repository. With `pywinpty==3.0.5` and the ConPTY backend it demonstrated
  child creation, initial dimensions, echoed input, a marker-bounded 1 MiB
  output burst on a dedicated reader thread, explicit resize, forced close,
  and an integer exit status on Windows 11 x64 across CPython 3.12–3.14.
- Documented rejection trail: stdlib `pty` cannot work on Windows (CPython
  documents `pty` and `termios` as Unix-only, confirmed on the spike host,
  which lacked `os.openpty` and `os.forkpty`); the raw `ctypes`
  STARTUPINFOEX/attribute-list surface proved too large and unsafe for a
  maintained binding and its prototype failed to attach the child; legacy
  WinPTY contradicts the ConPTY-first boundary decision.
- No other Python binding has been assessed: `ptyprocess` (and therefore
  `pexpect`'s pty path) is POSIX-only. If implementation-time evidence
  invalidates `pywinpty`, selecting a replacement requires amending this
  document, not silent substitution.
- `pywinpty` is MIT-licensed (PyPI classifier and repository license),
  maintained by a Spyder core developer in the `andfoy/pywinpty` repository,
  and ships binary wheels; the single-maintainer bus factor is accepted risk,
  and exact wheel coverage for every supported CPython and architecture is
  verified, not assumed, in the plan below.

## Verification plan

Implementation proceeds in reviewed TDD slices; each numbered item needs
executable evidence on the `windows-latest` CI matrix (all supported CPython
versions) before the corresponding public claim is made. Wall-clock silence is
never evidence: every drain, quiescence, or teardown claim must come from an
observed native signal, exit record, or explicit port report.

1. **Dependency governance:** add `pywinpty` as a pinned dependency (Windows
   marker) in a reviewed change; record wheel availability per CPython version
   and architecture; OSV scanning covers it automatically. If a required wheel
   is missing, the adapter is unsupported on that target and says so.
2. **Native ownership and close:** the adapter owns the pseudoconsole
   lifecycle; closing releases the native handles deterministically, verified
   by handle behavior and child-observable effects, not by reader-thread
   state.
3. **EOF and final-frame drain:** output is serviced until the native output
   pipe reports EOF after child exit and close; the final frame delivered
   before EOF is byte-complete for a marker-bounded burst. A stopped reader
   thread is explicitly not acceptable evidence.
4. **Process-tree teardown:** the child and its descendants are terminated and
   reaped on stop and on abort, verified with a deliberately spawning child;
   job-object or equivalent OS mechanisms are part of the design space, and
   the chosen mechanism's guarantees are documented with its evidence.
5. **Cancellation and recovery:** stop during an in-flight epoch, child hang,
   output flood, and startup failure each classify into the existing
   structured failure/abort taxonomy without leaking handles or threads,
   verified with hostile-child fixtures.
6. **Dimensions and resize:** dimensions are set before child start and
   changed only by explicit resize, with receipts reflecting observed values.
7. **Truthful enforcement receipts:** the terminal adapter emits receipts only
   for constraints it actually enforces at the OS boundary; everything else is
   structured unsupported. Requested/effective equality remains insufficient
   as enforcement proof, exactly as in the direct adapter.
8. **Evidence normalization:** raw VT output is retained as diagnostic
   evidence while assertions run against normalized structured observations,
   per the Phase 1 boundary decision.

## Non-goals

- No filesystem or network containment claim; those remain fail-closed under
  their own workstream.
- No terminal-capability registry activation and no key-to-terminal-byte
  mapping; `KeyInput` dispatch semantics stay as accepted in the key-registry
  slice.
- No POSIX adapter selection; a POSIX binding is a separate future decision.
- No concurrent-event correlation and no Phase 2 activation.
