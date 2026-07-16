# Direct Adapter

`termverify.direct.DirectAdapter` is the deterministic in-process execution path.
It implements the synchronous `Adapter` protocol by composing two application-owned
ports:

- `ConstraintPorts` applies the requested seed, manual clock, locale, timezone,
  terminal, filesystem, and network constraints.
- `DirectApplication` initializes the subject, handles input and clock epochs,
  reports quiescent observations, and drains shutdown to a terminal result.

## Wiring

Construct the adapter with one application object that implements both constraint
enforcement and execution. This identity requirement binds receipts to the same
subject session that is initialized:

```python
from termverify.direct import DirectAdapter

adapter = DirectAdapter(application)
result = adapter.start(run_id, configuration)
```

The adapter negotiates constraints in canonical order before calling
`application.initialize()`. A successful application operation returns
`EpochCompleted`; natural subject exit returns `TerminalResult` with a
`RunFinished` outcome; deterministic application failure returns `AdapterFailure`
with the operation-appropriate code. Applications must not prewrap failures in a
`TerminalResult`; the adapter owns failure cleanup and `RunFailed` construction.

## Execution rules

- The adapter is single-use and single-flight. It rejects operations before
  readiness, overlapping/reentrant operations, and operations after termination.
- `TextInput`, `Resize`, and `Stop` must use the current manual time.
  `ClockAdvance.at_ms` must equal the current time plus `delta_ms`.
- Application-reported observations and diagnostics must use the active epoch's
  manual time. Invalid or unexpected port responses fail closed.
- Port exceptions are contained and converted to stable structured failures;
  exception text is not exposed as replay evidence.
- After initialization begins, every adapter-detected failure invokes the
  synchronous `application.abort(Stop(...))` fallback before the failure becomes
  terminal. An abort exception is recorded as a stable cleanup-failure marker on
  `StartFailed` before readiness or `RunFailed` after readiness.
- Quiescence is reported by the application port. The adapter never infers it
  from wall-clock silence or a polling timeout.

Constraint receipts must exactly match the requested run and effective value.
An unsupported constraint or enforcement failure stops negotiation immediately;
the subject is not initialized.
