# JSONL Adapter

`termverify.jsonl` implements the `termverify.control/v1` control protocol: an
`Adapter` that drives a subject subprocess over its standard pipes, one JSON
message per line in each direction. The protocol itself — the message model,
the epoch vocabulary, the lifecycle rules — is specified in
[the control-protocol knowledge page](../knowledge/control-protocol.md); this
guide covers operating the adapter and choosing its ports.

## When to use it

Use `JsonlAdapter` when the subject runs as a separate process and speaks (or
can be made to speak) `termverify.control/v1` on stdin/stdout — the
cross-platform, language-agnostic path. The alternatives:

- `DirectAdapter` — in-process Python subjects, highest determinism, no OS
  process boundary.
- `termverify.conpty` — real-terminal subjects on Windows that need a genuine
  console, not pipes.

## Spawning a subject

The adapter speaks to any `JsonlChildPort`; the concrete wiring lives in the
private `termverify._jsonl_pipe` module:

```python
from termverify.cooperation import CooperationConstraintPorts
from termverify.jsonl import JsonlAdapter, JsonlBinding

binding = JsonlBinding()
adapter = JsonlAdapter(
    [sys.executable, "-u", "subject.py"],
    binding=binding,
    abort_deadline_ms=60_000,
    constraint_ports=CooperationConstraintPorts({"fixture-root": "/tmp/subject-data"}),
)
```

`JsonlBinding` spawns the child binary with:

- **binary pipes** for stdin/stdout — the protocol is UTF-8 JSONL, so no
  platform newline translation may interfere. The subject has the matching
  obligation: **write protocol lines through a binary stream** (Python:
  `sys.stdout.buffer.write(...)`), never text-mode `print`. Text-mode
  stdout emits `\r\n` on Windows, and the codec rejects any line ending in
  `\r` — such a subject works on POSIX and fails every message as
  `peer-malformed` on Windows;
- **tree containment**: on Windows the child is assigned to a kill-on-close
  job object; on POSIX it becomes a process-group leader, so a forced stop
  terminates the whole tree, never a leaked grandchild;
- **unbuffered-friendly framing**: writes are newline-terminated and flushed
  per message; reads deliver one framed line per call. The subject has the
  matching obligation: it must flush its stdout **after every protocol
  message** (e.g. Python's `sys.stdout.buffer.flush()`, or run with `-u`).
  A buffered subject that withholds its reply hangs every epoch until the
  abort deadline, diagnosed only as `epoch-timeout` — the binding cannot
  distinguish "slow" from "flushing late".

The binding enforces honest teardown semantics:

- a forced `close` kills the tree, waits for the real exit, and captures the
  OS-observed exit record (the uniform forced code `15` on Windows,
  `-SIGKILL` on POSIX);
- a release-only close of a *live* child is refused — the binding never
  abandons a live tree and never fabricates an exit record;
- a blocked reader is interrupted by the child's death (its stdout write-end
  closes), surfaces `JsonlChildClosedError`, and the close waits — bounded —
  for that delivery before ownership returns;
- a second `close` arriving while another thread's close is in flight waits
  for that teardown to finish, so the adapter never observes a half-closed
  binding when it consults `exit_status`.

## Watchdog

Epoch deadlines are enforced by a `JsonlWatchdogPort`; the default
`TimerWatchdog` uses a `threading.Timer` per armed deadline and forces a
child close on expiry. Inject a fake watchdog in tests to control time.

## Reference fixture subject

`tests/fixtures/jsonl_echo_subject.py` is the protocol's reference
implementation for real-subprocess integration evidence: a cooperative
subject that negotiates, echoes text/key/resize/clock epochs, renders a
deterministic frame, honors `input.stop` (exit 3), exits naturally on
`"quit"` (exit 7), and hangs on `"hang"` (to exercise the abort-deadline
forced-stop path). The integration suite in `tests/test_jsonl_integration.py`
drives it through `run_scripted` and proves the recorded transcript passes
the comparator unchanged — the Phase 2 core consumes the transport as-is.
