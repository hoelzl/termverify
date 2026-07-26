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

It bounds an epoch two ways, not one. A watchdog around each blocking read
force-closes the child when a *single read* exceeds the deadline. That alone
would not bound the epoch — a subject trickling output just under the
deadline never exceeds any single read's deadline — so the same value is
**also** applied to the epoch as a whole, checked between reads. An epoch's
worst case in its **read** phase is therefore up to twice the configured
deadline. The failure details name which bound fired: `bound: "read"` means
one read stalled, `bound: "epoch"` means the subject kept producing output
but never reached readiness.

That covers reading, not writing. An input epoch writes to the pseudoconsole
input buffer before the read phase begins, and that write is under no
watchdog: if the buffer fills because the subject never reads its input, the
write blocks and the abort deadline cannot end it. No backpressure was
observed on the verified matrix, so this is a disclosed boundary rather than
a measured one, and it closes only when TermVerify owns the conin handle —
see the `termverify._conpty` module docstring and
[issue #193](https://github.com/hoelzl/termverify/issues/193). Budget the
deadline for the read phase and do not read the 2x figure as a bound on
`dispatch` as a whole.

**This can abort runs that previously passed.** Budget the deadline above
the longest single epoch a real subject needs, output included. An ordinary
few-thousand-line scroll finishes in a couple of seconds, but a subject that
legitimately works for a minute between readiness markers now needs a
deadline that covers it — and because one value serves both bounds, a
generous deadline also means slower hang detection.

One further bound is adapter policy, not host policy, and is not
configurable: an epoch may retain only as much output as one observation
record can carry. Exceeding it fails the epoch (`budget: "bytes"`) instead of
retaining evidence that would not fit.

Chunk *count* is not a separate bound. The recorder merges an epoch's
adjacent `terminal.output` chunks into a single event
([issue #195](https://github.com/hoelzl/termverify/issues/195)), because
chunk boundaries are OS read scheduling rather than subject behavior, so no
number of native reads can exhaust the protocol's per-collection ceiling. A
subject doing tight in-place updates — a spinner, a progress bar redrawing in
place — is bounded by the bytes it writes and nothing else.

The byte bound is **computed**, not fixed, and two ceilings feed it:

- The epoch's chunks reach the transcript as one merged string, so that
  string's own per-string ceiling applies. At ordinary geometry this is the
  binding one, and the scale is roughly 1 MB of output in a single epoch.
- The record's total string bytes, less what the rest of the record costs.
  That is dominated by the frame's lines, so a large terminal leaves less
  room for output than an 80×24 one — this binds at 261,121 total cells and
  above. Cells, not columns: an 80×3,265 terminal crosses it and is not wide.

The byte bound also depends on what the screen *contains*, not only its size:
the codec counts UTF-8 bytes, so a box-drawn or CJK frame costs three to four
bytes per cell. The adapter reserves the worst case, which is why a large
terminal leaves less room for output — and at **523,264 cells** the reserve
leaves no room for output at all, so no epoch can be recorded at that
geometry and the run fails with `budget: "geometry"` as soon as an epoch
begins, before any read.

That threshold is where the *adapter* stops, not where the record does: a
523,264-cell frame that also stays inside the row and column limits below
still fits one record with a few kilobytes to spare. The adapter refuses
because an epoch that can record a frame but no output is not a useful
epoch, and admitting it would mean discovering the problem only when the
transcript is serialized.

**Rows and columns are limits of their own, and cells express neither.** The
frame meets three ceilings in three different units, so the adapter checks
three axes and the failure details name the one that bound:

| Axis | Ceiling | Largest admitted | Detail key |
| --- | --- | --- | --- |
| rows | one collection item per frame line | 16,384 rows | `terminal-rows` |
| columns | one line is one string, at 4 bytes per cell | 262,144 columns | `terminal-columns` |
| cells | the frame's aggregate bytes against the record | 523,263 cells | `terminal-cells` |

Neither of the first two is implied by the third. A terminal 10 columns wide
and 20,000 rows tall is only 200,000 cells — well under the threshold above —
and still cannot be recorded, because its frame is 20,000 collection items. A
terminal 262,145 columns wide and 1 row tall is 262,145 cells and still
cannot be recorded, because that one line is 1 MiB plus four bytes, and one
string may be 1 MiB. Only a single-row terminal can reach the column limit
without the cell limit firing first: at two rows, any width past 262,144 is
already past 523,264 cells.

Nor does either imply the other, so a frame at the cell threshold is not
automatically recordable — 523,264 columns on a single row is one row and
523,264 cells, and its one line is just under 2 MiB, where one string may
be 1 MiB.

All three refuse the run the same way, with `budget: "geometry"`, as soon as
an epoch begins and before any read.

Do **not** try to fit inside the bound by emitting extra readiness markers
inside one epoch: the contract is exactly one marker per processed input, and
a surplus marker ends an epoch early and shifts every later epoch's output
onto the wrong input. Produce less output between inputs instead.

The bound covers the adapter's own retention; the codec still owns
recordability and enforces further ceilings, so a transcript can still be
rejected for size after epochs the adapter accepted. Two are worth naming:
a canonical-line limit that ESC-dense output reaches much sooner, since
RFC 8785 escapes every control byte; and a **32 MiB ceiling on the whole
transcript**, which no per-epoch bound can model because it accumulates
across epochs — a large frame that is individually recordable still reaches
it within a couple of dozen epochs, since every epoch records a full frame.

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

## Key input encoding

`dispatch` executes a semantic `KeyInput` chord through the closed
`termverify.key-encoding/v1` registry (see the
[protocol companion note](../knowledge/protocol.md)): an encodable chord's
exact registry string is written to the child exactly once through the
single-flight write — the same disclosed native console-input encoding path
`TextInput` rides — and then runs the standard quiescent input epoch. An
unencodable chord is a structured runtime failure before any byte reaches
the child (`adapter-runtime-failed` with details
`{"unsupported": "key-encoding", "keys": [...]}`); there is no fallback to
text input, no partial write, and no silent degradation.

The encoding is delivery, not interpretation:

- The adapter claims only that the registry bytes were handed to the native
  encoding path. Whether the subject reads, decodes, or reacts to them is
  frame-observable evidence, exactly as for `input.text`.
- Encodings are the fixed xterm-legacy **normal-mode** forms. The adapter
  never tracks or negotiates DECCKM/application cursor-key mode,
  win32-input-mode, or bracketed paste; a subject that switches input modes
  still receives the fixed normal-mode bytes.
- There is no key-support negotiation and no per-subject encodable set; the
  encodable set is a global property of the registry version.

**Signal-byte disclosure.** Some encodable chords produce bytes that a
Windows console child with default *processed input* turns into control
events instead of readable input — `["Control", "c"]` delivers 0x03, which
such a child receives as `CTRL_C_EVENT`. The adapter delivers the registry
bytes verbatim and never detects, suppresses, or compensates for
processed-input semantics: cooperative raw-mode (unprocessed) input handling
is the subject author's responsibility, and a fixture that must observe
signal-generating bytes as bytes has to disable processed input first.

Four legacy byte collisions are disclosed (`Control+m` ≡ `Enter`,
`Control+i` ≡ `Tab`, and their `Alt`-prefixed forms); the transcript retains
the distinct semantic chords regardless of the shared bytes.

**ESC-prefixed sequences and C runtime input readers (issue #169).** The
ConPTY input pipe delivers ESC-prefixed bytes to the child's console input
buffer verbatim: a child reading that buffer byte-wise (`os.read` on the
stdin file descriptor, or `ReadFile`/`ReadConsoleA` on the input handle)
observes `("Alt", "x")` exactly as the registry's `1b 78`, and a bare ESC
arrives as an Escape keypress. The Microsoft C runtime's *wide-character*
console reader — `msvcrt.getwch()`, and with it Python's `sys.stdin` text
IO and `_wread`-based paths — instead parses ESC-prefixed sequences itself:
`ESC x` surfaces as just `x` (the ESC is consumed and the Alt modifier is
lost), `ESC [ A` surfaces as the translated virtual key (`e0 48`), and a
lone ESC blocks inside the runtime's sequence-assembly wait — which is how
a subject reading through this layer makes a bare-`Escape` epoch expire
the abort deadline instead of delivering the byte. This is subject-side
input handling, exactly like the signal-byte disclosure above: the adapter
delivers the registry bytes and never detects or compensates for the
child's reader. A subject that binds ESC-prefixed (Emacs-style meta)
chords must read console input byte-wise; the integration fixture
demonstrates the working pattern.

Windows-matrix evidence (`tests/test_conpty_integration.py`) shows a real
raw-mode child observing the registry bytes byte-identically for one
representative chord per encodable family class — including the signal byte
0x03 arriving as input once processed input is disabled — and the
unencodable path staying fail-closed on the real adapter. A cooperative
raw-mode subject clears `ENABLE_PROCESSED_INPUT`, `ENABLE_LINE_INPUT`, and
`ENABLE_ECHO_INPUT` and sets `ENABLE_VIRTUAL_TERMINAL_INPUT` on its console
input handle, as the fixture there demonstrates.
