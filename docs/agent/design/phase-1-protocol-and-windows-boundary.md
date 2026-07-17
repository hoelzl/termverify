# Phase 1 Protocol and Windows PTY Boundary Decision

- **Status:** accepted — independently human-reviewed on 2026-07-15 and
  reconciled with the partial executable feasibility result merged in PR #53.
- **Issue:** [#3](https://github.com/hoelzl/termverify/issues/3)
- **Date:** 2026-07-15

## Context

TermVerify needs a portable transcript and a direct/terminal adapter boundary
without making Windows a late, incompatible special case. The pre-implementation
protocol design is published in `docs/knowledge/protocol.md` as
`termverify.transcript/v1`.

## Decision

Phase 1 will accept a requested deterministic run only after the adapter emits
an enforced `capability.result` for every requested constraint. It will emit a
structured `run.unsupported` result before input dispatch when it cannot
enforce one. The direct adapter and future PTY adapter share this result shape;
neither may silently degrade a requested constraint.

The future terminal adapter interface must support all of the following:

1. asynchronous, separately drained input and output streams;
2. terminal dimensions supplied before child-process start and updated through
   an explicit resize operation;
3. explicit process-tree teardown and output draining before resources close;
4. a capability report that distinguishes `enforced` from `unsupported`;
5. normalized VT output as evidence, not an assumption that every host renders
   identically.

Browser bridging is explicitly deferred. Phase 1 includes a direct adapter and
one partial terminal-feasibility slice first. A browser bridge can be proposed
only after later production terminal work demonstrates a concrete shared
abstraction that cannot stay in the terminal adapter.

## Windows/ConPTY feasibility spike

PR #53 replaced the earlier presence-only probe with the isolated executable
probe under `spikes/conpty-lifecycle/`. On Windows 11 it used transient,
pinned `pywinpty==3.0.5` with explicit `Backend.ConPTY`; no project dependency or
lockfile changed. Repeated runs under Python 3.12 and focused runs under 3.13 and
3.14 observed a synthetic child, input, initial dimensions, resize, a bounded
1 MiB output burst, wrapper-level close, child status, and stopped servicing
threads.

The result is deliberately **partial** and binding-level. `PtyProcess.close`
signals the child and disconnects the high-level reader; the probe does not prove
that TermVerify directly called `ClosePseudoConsole`, observed native pipe EOF,
received every final frame, or contained a process tree. The standard-library
`pty` module is not usable on the tested Windows host: importing it requires the
unavailable `termios`, and `os.openpty`/`os.forkpty` are absent.

Microsoft's [Create a Pseudoconsole session guidance](https://learn.microsoft.com/en-us/windows/console/creating-a-pseudoconsole-session)
requires synchronous input/output channels, warns that servicing both on one
thread can deadlock, requires a size at creation, and supports explicit resize.
Its close guidance permits either closing the output pipe before
`ClosePseudoConsole` or continuing to service output until after that call
returns. TermVerify deliberately requires the latter path when final-frame and
EOF evidence are claimed. Microsoft's [virtual terminal sequence
guidance](https://learn.microsoft.com/en-us/windows/console/console-virtual-terminal-sequences)
also makes VT behavior conditional on console modes. These facts motivate the
interface constraints above; they do not demonstrate a production adapter.

## Consequences and follow-up

- Canonical lifecycle fixtures and deterministic execution-contract tests now
  exist. The active Phase 1 handover retains deterministic transcript resource
  governance and an amended behavior-based fixture gate; installed schema access
  transfers to the draft pre-release successor.
- The first production Windows adapter must provide direct, reviewable evidence
  for native pseudoconsole ownership, close, EOF/final-frame draining,
  process-tree teardown, and truthful OS-level enforcement. PR #53 is not that
  adapter.
- Dependency selection for a ConPTY binding or promotion of spike code into
  `termverify` requires the rationale and verification plan required by
  `AGENTS.md` plus a separate focused review.
