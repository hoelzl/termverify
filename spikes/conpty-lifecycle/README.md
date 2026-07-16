# Windows ConPTY lifecycle feasibility

## Question

**Given** a supported Windows host and an explicitly selected ConPTY binding,
**when** a synthetic child is created, driven from independently serviced input
and output channels, resized, and closed while still alive, **then** can the host
observe the requested dimensions, input, sustained output service, and child
termination without claiming production containment?

Issue: [#52](https://github.com/hoelzl/termverify/issues/52)

## Scope

This is an isolated feasibility probe. It is not a public adapter, a supported
runtime path, a deterministic-constraint receipt, or proof of process-tree,
filesystem, network, locale, clock, or security containment.

The probe emits only fixed synthetic markers. It does not print or persist the
child command, environment, current directory, account, hostname, user paths, or
raw terminal output.

## Host and command

Observed host:

```text
os.name=nt
platform=Windows-11-10.0.26200-SP0
python=3.12.9
machine=AMD64
```

Reproduce from the repository root without changing `pyproject.toml` or
`uv.lock`:

```bash
uv --no-config run --isolated --no-project --python 3.12 \
  --with pywinpty==3.0.5 \
  python spikes/conpty-lifecycle/probe.py
```

The probe explicitly requests `winpty.Backend.ConPTY`; it does not accept the
legacy WinPTY fallback. The pinned package is installed into an isolated,
transient uv environment and is not a TermVerify dependency.

## Binding approaches considered

| Approach | Result | Trade-off |
| --- | --- | --- |
| Python standard-library `pty` | Rejected on Windows | The module is present but cannot import without `termios`; this host also has neither `os.openpty` nor `os.forkpty`. |
| Direct `ctypes` calls to `kernel32` | Rejected for the durable spike | Dependency-free, but reproducing pipes, `STARTUPINFOEX`, attribute-list ownership, process startup, and teardown correctly is a large unsafe binding surface. An initial disposable prototype failed to attach the child correctly and was removed. |
| `pywinpty` 3.0.5 with explicit ConPTY backend | Selected for feasibility | Maintained Windows binding with CPython 3.12–3.14 wheels and direct create/read/write/resize/close/process-status operations; adopting it as a project dependency remains a separate decision. |

Microsoft requires synchronous ConPTY channels and recommends servicing input
and output separately to avoid deadlock. It also requires initial dimensions,
supports explicit resize, and warns that output must remain drained during
`ClosePseudoConsole`. The probe therefore uses dedicated input and output
threads and invokes the binding's close operation while the output reader is
active. The high-level binding does not expose direct `ClosePseudoConsole` or
native output-pipe EOF evidence, so this probe does not claim either one.

## Observed evidence

One successful result:

```json
{"alive_before_close":true,"binding":"pywinpty-conpty","binding_version":"3.0.5","burst_bytes":1048576,"close_completed":true,"errors":[],"exit_status":2,"initial_size":"80x24","input_echo":"synthetic-input","output_reader_stopped":true,"process_exit_observed":true,"resized_size":"100x30","verdict":"validated-binding-lifecycle","writer_stopped":true}
```

The Python 3.12 command completed five consecutive times with the same
structured result. The probe also produced the same validated binding-lifecycle
result under Python 3.13 and 3.14 on this host. The child:

1. reported the creation size as `80x24`;
2. received `synthetic-input` through the dedicated writer thread;
3. emitted and delivered a deterministic 1 MiB synthetic burst while the
   dedicated reader continued servicing output;
4. reported `100x30` after an explicit resize;
5. remained alive and blocked for input before close;
6. terminated after `PtyProcess.close(force=True)` completed;
7. left both host servicing threads stopped.

`exit_status=2` is evidence that the binding exposed a terminal child status on
this host. Its numeric value is not treated as a portable oracle because this
probe intentionally closes a live process.

## Verdict: PARTIAL

The binding-level lifecycle is validated, but the issue's native pseudoconsole
close/drain step remains an explicit blocker because `PtyProcess.close(force=True)`
disconnects its high-level reader and signals the child rather than exposing a
direct `ClosePseudoConsole` operation.

### What worked

- Explicit ConPTY selection created and drove a real synthetic child.
- Independent input and output servicing avoided the single-threaded I/O shape
  Microsoft warns can deadlock.
- The host reader received the complete 1 MiB synthetic burst before resize.
- Initial dimensions and resize were visible inside the child.
- Binding-level close completed, and child exit was observable through the
  binding's native process-status query.
- Five consecutive runs produced the same structured evidence.

### What did not establish

- No production terminal adapter or public API was implemented.
- No guarantee was established for process-tree/job-object containment, graceful
  shutdown, cancellation, timeout recovery, or older Windows close semantics.
- The high-level binding does not expose direct `ClosePseudoConsole`, native
  output-pipe EOF, or final-frame completeness; those teardown details remain a
  production-binding evaluation requirement.
- Raw VT output was not normalized into semantic observations.
- No deterministic seed, clock, locale, timezone, filesystem, or network policy
  was enforced or receipted.
- `pywinpty` was not accepted as a runtime dependency and was not evaluated on
  Windows ARM64 or every supported Windows release.

### Surprises

- A direct `ctypes` prototype was substantially more error-prone than the small
  visible API list suggests; successful HRESULTs alone did not prove that the
  child was actually attached to the intended pseudoconsole channels.
- The high-level ConPTY write operation reports an implementation-specific
  return value that is not a reliable character-count receipt. The synthetic
  child echo is the useful evidence that input arrived.
- A stopped high-level reader thread is not proof that the native ConPTY output
  pipe reached EOF or that every teardown frame was drained.

### Recommendation for the real build

Treat `pywinpty` as the leading binding candidate, but make dependency adoption a
separate reviewed decision. That decision should inspect its close and process
ownership semantics, define Windows version/architecture support, and require
Windows integration tests for output draining, cancellation, timeout recovery,
resize, process-tree teardown, and malformed/hostile child behavior. A future
terminal adapter must still earn every deterministic enforcement receipt and
must not describe this feasibility result as production containment.

## Sources

- [Microsoft: Creating a Pseudoconsole session](https://learn.microsoft.com/en-us/windows/console/creating-a-pseudoconsole-session)
- [Microsoft: CreatePseudoConsole](https://learn.microsoft.com/en-us/windows/console/createpseudoconsole)
- [Microsoft: ResizePseudoConsole](https://learn.microsoft.com/en-us/windows/console/resizepseudoconsole)
- [Microsoft: ClosePseudoConsole](https://learn.microsoft.com/en-us/windows/console/closepseudoconsole)
- [`pywinpty` 3.0.5 on PyPI](https://pypi.org/project/pywinpty/3.0.5/)
