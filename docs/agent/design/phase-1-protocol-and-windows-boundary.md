# Phase 1 Protocol and Windows PTY Boundary Decision

- **Status:** accepted — independently human-reviewed on 2026-07-15; executable
  protocol fixtures and contract tests remain prerequisites for adapter code.
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

Browser bridging is explicitly deferred. Phase 1 proves a direct adapter and
one terminal vertical slice first. A browser bridge can be proposed only after
that slice demonstrates a concrete shared abstraction that cannot stay in the
terminal adapter.

## Windows/ConPTY feasibility spike

The spike ran on 2026-07-15 with the repository's managed interpreter:

```text
$ uv --no-config run python -c '<platform probe>'
os.name=nt
platform=Windows-11-10.0.26200-SP0
python=3.12.9 ... [MSC v.1943 64 bit (AMD64)]

$ uv --no-config run python -c '<stdlib and binding probe>'
pywinpty=False
pty=True
has_openpty=False
has_forkpty=False

$ uv --no-config run python -c '<kernel32 API probe>'
CreatePseudoConsole=<_FuncPtr ...>
ResizePseudoConsole=<_FuncPtr ...>
ClosePseudoConsole=<_FuncPtr ...>
```

The standard-library `pty` module is importable under this Git-Bash-hosted
Python process but does not provide `openpty` or `forkpty`; it is not a viable
Windows PTY implementation. ConPTY entry points are present in `kernel32`, so a
Windows adapter can use ConPTY directly or a separately justified binding. No
new dependency is selected by this spike.

Microsoft's [Create a Pseudoconsole session guidance](https://learn.microsoft.com/en-us/windows/console/creating-a-pseudoconsole-session)
requires synchronous input/output channels, warns that servicing both on one
thread can deadlock, requires a size at creation, supports explicit resize, and
requires draining output while closing. Its [virtual terminal sequence
guidance](https://learn.microsoft.com/en-us/windows/console/console-virtual-terminal-sequences)
also makes VT behavior conditional on console modes. These facts motivate the
interface constraints above; they do not demonstrate a production adapter.

## Consequences and follow-up

- Before adapter implementation, add canonical valid/invalid v1 JSONL fixtures
  and tests for serialization, ordering, version rejection, and unsupported
  deterministic constraints.
- The first Windows adapter must include a real child-process smoke test for
  create, input/output drain, resize, close, and exit; this documentation spike
  is not that test.
- Dependency selection for a ConPTY binding requires the rationale and
  verification plan required by `AGENTS.md`.
- Workstream 3 remains active until the executable fixtures and contract tests
  are reviewed and pass.