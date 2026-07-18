# ConPTY Adapter and Cooperation Ports

`termverify.conpty.ConptyAdapter` drives one Windows terminal subject through
an injected ConPTY binding port. The adapter enforces only the terminal
constraint (dimensions are an OS-level pseudoconsole parameter; its receipt
states the `os` enforcement tier). The six non-terminal constraints belong to
injected `ConstraintPorts`, whose receipts may state only the `delivered`
tier under the `termverify.enforcement-tier/v1` authorization matrix.

## Wiring

The shipped default, `UnenforcedConstraintPorts`, truthfully reports every
non-terminal constraint as not enforced, so `start()` with defaults ends
fail-closed as `StartUnsupported(seed)` before any child exists. Verified
runs require an explicit host decision to inject
`termverify.cooperation.CooperationConstraintPorts`:

```python
from termverify.conpty import ConptyAdapter, ConptyBinding
from termverify.cooperation import CooperationConstraintPorts

adapter = ConptyAdapter(
    ["my-subject.exe"],
    binding=ConptyBinding(),
    constraint_ports=CooperationConstraintPorts(
        {"workspace": "C:\\hosts\\workspace-sandbox"},
    ),
    abort_deadline_ms=30_000,
)
```

`abort_deadline_ms` is mandatory host abort policy with no default; budget it
above the disclosed DA-stall floor (~3.1 s on the verified matrix) plus spawn
overhead, or every real start fails by policy.

## What the delivered tier means

A cooperation-port receipt claims exactly this: the recorded environment
variables (and, for filesystem, the working directory) were placed into the
subject's spawn environment. Honoring them is the subject's cooperation
obligation. Nothing is enforced, nothing blocks filesystem or socket access,
and no receipt ever claims the subject complied. OS containment is an
explicit non-goal by recorded owner decision
(`docs/agent/design/cooperation-tier-constraint-ports.md`).

Delivered variables per constraint: `TERMVERIFY_SEED`,
`TERMVERIFY_CLOCK_INITIAL_MS` (initial manual time only — manual-time
advances are never delivered to a running child), `TERMVERIFY_LOCALE` (the
BCP-47 tag; no `LANG`/`LC_ALL`), `TZ=UTC0` plus `TERMVERIFY_TIMEZONE=UTC`
(UTC-only; a non-UTC request is truthfully unsupported),
`TERMVERIFY_FS_ROOT` plus the working directory, and
`TERMVERIFY_NETWORK=deny` (deny-only; allow-list requests stay rejected).

The spawn is evidence-driven: the adapter assembles the child's environment
overlay from the delivery records in the validated receipts, so the
transcript records exactly what the child was given. The child inherits the
binding process's ambient environment underneath the overlay; ambient
contents are not evidence and are not recorded. An overlay variable always
wins over an ambient variable of the same name.

## Filesystem sandbox disclosures

The cooperation ports are constructed with an explicit
`root_id -> absolute host directory` mapping. At negotiation the port
resolves the mapped path through an injectable directory probe (default: the
real filesystem — the ports' single disclosed ambient touchpoint) and rejects
an unknown root id or a path that is not an existing directory as
`ConstraintUnsupported`.

- The existence check happens at negotiation time and is advisory; it is not
  containment and carries the ordinary time-of-check gap to spawn.
- Nothing prevents the subject or its descendants from reading or writing
  outside the root. That is the meaning of the `delivered` tier.
- Lifecycle is deliberately the host's: the port creates nothing, populates
  nothing, and deletes nothing.
- The delivered absolute path is recorded verbatim in the receipt, so
  transcripts embed host-specific paths. Safe-evidence persistence redacts
  delivery values and the working directory with shape-preserving markers.

## Subject cooperation contract

A verified subject emits the configured readiness marker after startup and
after processing each input, detects resizes itself (a resize delivers no
stdin bytes to a Windows console client), and reads its constraints from the
delivered environment variables.
