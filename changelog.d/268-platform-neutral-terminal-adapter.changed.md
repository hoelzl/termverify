- **BREAKING: the ConPTY adapter is now one platform-neutral terminal
  adapter** (issue #268, slice 2 of the vertical). The epoch machinery was
  already platform-neutral — marker protocol, epoch loop, watchdog, geometry
  gate, classification matrix and normalizer feed all sat above the binding
  port — so this is a rename plus the two changes that make the neutrality
  real rather than nominal. No shim, per the prototyping-stage posture.

  Migration, mechanical and complete:

  | Before | After |
  | --- | --- |
  | `termverify.conpty` | `termverify.terminal` |
  | `ConptyAdapter` | `TerminalAdapter` |
  | `ConptyBindingPort` | `TerminalBindingPort` |
  | `ConptyChildPort` | `TerminalChildPort` |
  | `ConptyWatchdogPort` | `TerminalWatchdogPort` |

  **Deliberately unchanged:** `ConptyBinding`. It *is* the Windows
  pseudoconsole binding — one of two implementations of the neutral port — so
  renaming it would have made the platform-neutral module claim a
  pseudoconsole is platform-neutral. `PosixPtyBinding` joins it as the second,
  wrapping the `termverify._posix_pty` binding from #267. Hosts inject one; the
  adapter never asks which.

- **Binding failures are classified by kind, not by platform family.** The
  adapter caught the concrete `Conpty*Error` types, so a POSIX end-of-stream
  fell through to the generic read-failure branch and a clean subject exit
  would have been reported as a runtime failure. A shared taxonomy now sits
  below the adapter and above both bindings, each raising its own subclass, so
  a binding TermVerify has never heard of is classified correctly. This is
  internal to the package; no public name changes.

- **The adapter no longer names a platform in anything it emits.** Sixteen
  string literals said ConPTY, pseudoconsole or Windows — fourteen distinct
  texts, three of the sites sharing one. Twelve of the sixteen can reach a
  transcript, as `AdapterFailure.message`, `AdapterFailure.details` values,
  `ConstraintUnsupported` reasons and a `Diagnostic`: a Linux run would have
  been told its pty session ended by "forced ConPTY teardown". The other four
  are the `RuntimeError` texts raised to the host on a lifecycle violation,
  which reach no transcript and were neutralized for the same reason. A
  binding's *own* diagnostics still name its platform, recorded verbatim in a
  failure's `reason` detail, which is the one layer that knows what it is.
  Hosts matching on adapter message text will need to update those matches;
  the structured `details` **keys** are unchanged.

  Three properties are ratcheted in
  `tests/test_terminal_platform_neutrality.py`: zero `sys.platform`/`os.name`
  reads above the binding port, no import that could make one, and no emitted
  message naming a platform.

- **The POSIX path is not proven end to end yet.** `PosixPtyBinding` is
  shipped and the adapter above it is neutral, but the POSIX evidence stops at
  the binding's own tests. The adapter-level legs — start to readiness, a text
  epoch, a resize with observed dimensions and `SIGWINCH`, exit, forced stop,
  deadline abort — are issue #269. Until they land, treat Windows as the only
  proven terminal path.
