# Key-to-Terminal Byte Mapping for the ConPTY Adapter

- **Status:** accepted — decided 2026-07-19 by explicit owner direction in
  session. The owner selected this workstream from the four open decisions
  and deferred the other three (recorded below). This document defines the
  encoding contract and authorizes the implementation slices listed at the
  end. It adds no code itself; until slice 1 merges, the ConPTY adapter
  continues to reject every `KeyInput` as a structured runtime failure.
- **Issue:** [#139](https://github.com/hoelzl/termverify/issues/139)
- **Date:** 2026-07-19
- **Inputs:** the closed `termverify.key/v1` registry and chord grammar
  (`src/termverify/_key_v1.py`, documented in
  [`docs/knowledge/protocol.md`](../../knowledge/protocol.md)); the immutable
  `KeyInput` and the direct adapter's unchanged-forwarding dispatch contract
  (`docs/agent/design/phase-1-adapter-execution-contract.md`); the accepted
  ConPTY adapter design
  ([`conpty-adapter-design.md`](conpty-adapter-design.md)), which named this
  mapping an explicit non-goal at its boundary; the single-flight
  `ConptyChildPort.write(text: str)` input primitive and its native binding
  contract; the transferred "terminal-byte mapping and key-support
  negotiation" work in the
  [pre-release boundary hardening handover](../handovers/pre-release-boundary-hardening-handover.md);
  the protocol rule that an adapter "must fail rather than silently
  translate an unknown value, alias, or ambiguous escape sequence"
  (`protocol.md`).

## Decision summary

TermVerify gains a closed, versioned, digest-bound encoding registry,
`termverify.key-encoding/v1`, that maps each valid `termverify.key/v1` chord
either to one exact terminal byte sequence or to the explicit verdict
**unencodable**. The registry is owned by TermVerify and fixed by this
design: it is a committed table plus committed arithmetic, never derived
from terminfo, toolkit enums, OS virtual-key codes, locale, or any other
ambient host state. The ConPTY adapter's `dispatch` uses it to execute
`KeyInput` on the real terminal path: an encodable chord is written to the
child exactly once through the existing single-flight write primitive and
then runs the same quiescent input epoch as `TextInput`; an unencodable
chord is a structured runtime failure before any byte reaches the child.

The mapping is delivery, not interpretation. The adapter claims only that
the registry's exact string was handed to the disclosed native
console-input encoding path; it
claims nothing about how the subject decodes or reacts to them. Subject
reaction remains observable frame evidence, exactly as for `input.text`.
The transcript protocol is unchanged: `input.key` stays semantic, no
transcript record carries encoded bytes, and replay identity is unaffected
because replay consumes retained `terminal.output` chunks, not inputs.

## Owner decisions recorded (2026-07-19)

1. **Proceed with key-to-terminal byte mapping.** The registry and
   `KeyInput` exist and the direct adapter dispatches chords, but the ConPTY
   terminal path rejects every semantic key, so no realistic TUI subject
   (arrow keys, function keys, modified chords) can be exercised on the real
   path. This design and its slices are the authorized scope.
2. **Named-timezone enforcement is deferred until demonstrated need.** The
   request-level `termverify.timezone/v1` contract stands; cooperation
   delivery stays UTC-only and named-zone receipts stay fail-closed. No
   design work is authorized now.
3. **The terminal-capability registry is deferred until demonstrated need.**
   Non-empty terminal-capability receipts remain rejected; no capability
   vocabulary is designed ahead of a real subject that needs one with
   observable enforcement evidence.
4. **Concurrent event correlation is deferred until demonstrated need.** V1
   stays single-flight with transcript-position causality, per the
   handover's own gate ("only when a demonstrated application requires
   concurrent or unsolicited work").

Deferral is not retirement: the three deferred rows remain transferred
criteria in the handover and reopening any of them needs only a new owner
decision, not a new design to un-retire a non-goal.

## The encoding registry: `termverify.key-encoding/v1`

### Ownership and versioning

- The registry is a pure function from valid `termverify.key/v1` chords to
  `encoded bytes | unencodable`, total over the finite valid-chord set (the
  chord grammar admits exactly 1382 chords after the punctuation amendment in
  [`key-v1-punctuation-bases.md`](key-v1-punctuation-bases.md): 26 named bases
  × 16 canonical modifier subsets, plus 69 modified-only bases × the 14
  subsets containing a trigger modifier).
- It lives in one runtime module (working name
  `src/termverify/_key_encoding_v1.py`) as committed data and committed
  arithmetic. Runtime code is the single authority; no schema change is
  involved because the transcript never carries encodings.
- The full enumeration — every valid chord in a deterministic documented
  order together with its encoding or `unencodable` verdict — is
  digest-bound in executable tests, following the `termverify.key/v1`
  digest precedent, and the digest is recorded in the documentation.
- Versioning follows the established registry rule: during the pre-release
  inception period, reviewed corrections amend v1 in place; from the
  protocol freeze trigger onward, any change to an existing chord's
  encoding or verdict requires `termverify.key-encoding/v2`. Because
  encodings are not transcript values, a new encoding version does not by
  itself require a new transcript protocol version; it is a documented
  behavioral change of the adapter recorded in `CHANGELOG.md`.

### Encoding scheme

All encoded values are strings of code points in the range U+0001–U+007F,
written verbatim through the existing `ConptyChildPort.write(text: str)`
primitive — the same disclosed native console-input encoding path that
`input.text` already rides. The scheme is the fixed xterm-compatible legacy
encoding in its **normal (non-application) cursor-key form**; the adapter
neither tracks nor negotiates DECCKM or any other input mode (see honesty
boundaries).

The xterm modifier parameter is `1 + (Shift:1) + (Alt:2) + (Control:4) +
(Meta:8)`, computed from the chord's canonical modifier set.

| Chord family | Unmodified form | Modified form (parameter `m`) |
| --- | --- | --- |
| `ArrowUp`/`ArrowDown`/`ArrowRight`/`ArrowLeft`, `Home`, `End` (final byte `A`/`B`/`C`/`D`/`H`/`F`) | `ESC [ <final>` | `ESC [ 1 ; m <final>` — all 15 modified subsets encodable |
| Tilde family — `Insert` 2, `Delete` 3, `PageUp` 5, `PageDown` 6, `F5` 15, `F6` 17, `F7` 18, `F8` 19, `F9` 20, `F10` 21, `F11` 23, `F12` 24 | `ESC [ <n> ~` | `ESC [ <n> ; m ~` — all 15 modified subsets encodable |
| `F1`–`F4` (final byte `P`/`Q`/`R`/`S`) | `ESC O <final>` | `ESC [ 1 ; m <final>` — all 15 modified subsets encodable |
| `Enter`, `Tab`, `Escape`, `Backspace` | `CR` (0x0D), `HT` (0x09), `ESC` (0x1B), `DEL` (0x7F) | Exactly five modified chords are encodable: `["Shift", "Tab"]` → `ESC [ Z`, and `["Alt", <base>]` for each of the four bases → `ESC` prefix of the unmodified byte. Every other modified subset is **unencodable**. |
| Letters `a`–`z` | (not a valid chord — unmodified printables are `input.text`) | `["Control", x]` → the C0 byte `chr(ord(x) - 0x60)`; `["Alt", x]` → `ESC x`; `["Control", "Alt", x]` → `ESC` + C0 byte. Every subset containing `Shift` or `Meta` is **unencodable**. |
| Digits `0`–`9` | (not a valid chord) | `["Alt", d]` → `ESC d`. Every other subset is **unencodable**. |
| `Space` | (not a valid chord) | `["Alt", "Space"]` → `ESC SP` (0x1B 0x20). Every other subset is **unencodable**. |

Unencodable rationale, recorded so the fail-closed set is a decision rather
than an omission:

- **`Shift` with letters/digits/`Space`:** the legacy encoding cannot
  represent `Shift` distinctly for these bases; collapsing
  `["Control", "Shift", "a"]` to the bytes of `["Control", "a"]` would
  silently misrepresent the chord, which the protocol forbids.
- **`Meta` with letters/digits/`Space`:** legacy terminals have no distinct
  `Meta` byte form for these bases; aliasing `Meta` to `Alt` is exactly the
  alias rewriting v1 bans. (`Meta` on the CSI-parameterized families is
  encodable because the parameter arithmetic represents it exactly.)
- **`Control` with digits and `["Control", "Space"]`:** the historical
  control-digit encodings are inconsistent across terminals, and the
  candidates (for example NUL for `Control+Space`) put a NUL through the
  native wide-string boundary, where truncation is a known hostile-input
  hazard — the same reason `DeliveryRecord` rejects NUL. Fail closed.
- **Modified `Enter`/`Escape`/`Backspace` beyond `Alt`+base, and modified
  `Tab` beyond `Shift+Tab`/`Alt+Tab`:** the legacy byte space has no form
  that represents the modifier at all — the only candidate bytes are the
  base's own (`Control+Enter` has no encoding other than `Enter`'s `CR`),
  so emitting them would silently drop the modifier, which is exactly the
  misrepresentation the protocol forbids.

The governing principle: a chord is encodable exactly when the legacy
encoding represents every component of the chord by definition, and
unencodable when the only candidate bytes drop a modifier or misrepresent
the base. Distinct chords' correct encodings may still collide in the
legacy byte space, and four such collisions exist and are disclosed:
`["Control", "m"]` encodes to `CR`, byte-identical to `Enter`;
`["Control", "i"]` to `HT`, byte-identical to `Tab`; and therefore
`["Control", "Alt", "m"]` ≡ `["Alt", "Enter"]` and
`["Control", "Alt", "i"]` ≡ `["Alt", "Tab"]`. These are not
modifier-dropping: the C0 arithmetic *is* the definitional legacy encoding
of a `Control`+letter chord, every component is represented, and the
resulting byte ambiguity is inherent to legacy terminals and subject-side,
like every other interpretation concern — the transcript retains the
distinct semantic chords regardless of what bytes they share.

A future encoding version (for example one adopting an unambiguous
extended keyboard protocol) may shrink the unencodable set and resolve the
disclosed collisions; v1 never guesses.

### Signal-byte disclosure

Some encodable chords produce bytes that a Windows console child with
default processed input translates into control events rather than input
(`["Control", "c"]` → 0x03 → `CTRL_C_EVENT` for such a child). This is
subject-side interpretation, exactly like any other frame-observable
reaction: the adapter still delivers the registry bytes verbatim and makes
no attempt to detect, suppress, or compensate for processed-input
semantics. The developer-guide documentation must disclose this so subject
authors know cooperative raw-mode input handling is their responsibility.

## Adapter integration contract

- `ConptyAdapter.dispatch` replaces the current unconditional `KeyInput`
  rejection (`{"unsupported": "key-input"}`) with: encode via the registry;
  on an encodable chord, write the encoded string exactly once through the
  existing single-flight child write and run the standard quiescent input
  epoch (readiness marker, watchdog on reads, retained `terminal.output`
  chunks, normalizer) exactly as `TextInput` does today.
- An unencodable chord is a structured runtime failure **before any child
  write**: the existing `adapter-runtime-failed` path with details
  `{"unsupported": "key-encoding", "keys": [...]}`. Including the chord
  here aids live diagnosis without weakening safe evidence: under the
  evidence-governance policy, failure details are blanket-redacted by safe
  persistence, and its key-chord rule already replaces every persisted
  chord with the `["Escape"]` sentinel — chord identity is hidden by those
  existing rules, not by a claim that it is non-sensitive. The run aborts
  through the same machinery as every other
  runtime failure; there is no fallback to `input.text`, no partial write,
  and no silent degradation, matching the direct adapter's precedent.
- The transcript records the semantic `input.key` event exactly as before.
  No new transcript member, event kind, or receipt field is introduced;
  the transcript protocol stays v1 with no amendment. The adapter's package
  version pins the encoding registry version; a future encoding version is
  a CHANGELOG-recorded behavioral change.
- The direct adapter is untouched: it continues to forward `KeyInput`
  unchanged to the application boundary and never consults the encoding
  registry.

## Honesty boundaries

- **Delivery, not interpretation.** The only claim is that the registry's
  exact string was handed, exactly once, to the disclosed native
  console-input encoding path via the single-flight write — the same
  boundary `input.text` crosses, which returns no byte-count receipt. No
  claim is made that the child read the bytes, decoded
  them as the intended key, or reacted; that evidence is the subject's
  observable frames, as with every other input.
- **No input-mode tracking.** The adapter does not track, set, or respond
  to DECCKM/application cursor-key mode, win32-input-mode, bracketed
  paste, or any other input mode. Encodings are the fixed normal-mode
  forms defined above regardless of what modes the subject may have set.
  A subject that switches input modes and expects mode-dependent bytes
  sees the registry's fixed bytes; its reaction is still just observable
  evidence, and this limitation is documented, not compensated for.
- **No key-support negotiation.** There is no capability probing, no
  per-subject encodable set, and no receipt claiming key support. The
  encodable set is a global property of the registry version.

## Explicit non-goals

- No key-support negotiation or per-subject capability evidence (stays with
  the deferred terminal-capability registry decision).
- No CSI-u/fixterms, kitty keyboard protocol, xterm `modifyOtherKeys`, or
  win32-input-mode synthesis; any of these is a future
  `termverify.key-encoding/v2` owner decision.
- No DECCKM or input-mode state tracking in adapter or normalizer.
- No change to `termverify.key/v1` membership, chord grammar, or the
  transcript protocol; no new transcript members or event kinds.
- No change to the direct adapter's dispatch contract.
- No `input.mouse` encoding; mouse input on the terminal path remains
  rejected as today.
- No POSIX adapter work (separate undecided workstream).
- No claim of subject receipt, decoding, or compliance; no suppression or
  detection of console control events triggered by delivered bytes.

## Testing and coverage plan

- Registry unit tests: totality over all 1382 valid chords (every chord
  yields exactly one encoding or `unencodable`, and invalid chords are
  rejected); the digest test binding the full enumeration; exact-byte
  assertions for every family and rule row in the scheme table, including
  each unencodable rationale class.
- Adapter tests (cross-platform, fake child): an encodable chord writes
  exactly the registry bytes exactly once and runs a standard epoch; an
  unencodable chord produces the structured runtime failure with the
  documented details and provokes no child write; single-flight and
  state-gate behavior is unchanged.
- Windows-matrix integration evidence (slice 2): a cooperating fixture
  subject in raw/unprocessed input mode reads console input and echoes
  what it observed into frames for representative chords from each
  encodable family; replay identity holds over the retained chunks. The
  fixture must avoid or explicitly handle signal-generating bytes.
- Coverage stays ratcheted; the native binding module remains the single
  ratchet exclusion. Documentation updates (`protocol.md` companion note,
  `docs/developer-guide/conpty-adapter.md`) land in the same slice as the
  behavior they describe.

## Authorized implementation slices

1. **Slice 1 — encoding registry and ConPTY dispatch.** Add
   `termverify.key-encoding/v1` (module, digest-bound enumeration, unit
   tests), integrate it into `ConptyAdapter.dispatch` (encodable → single
   write + standard epoch; unencodable → structured runtime failure with
   `{"unsupported": "key-encoding", ...}`), and document the registry, its
   digest, the fail-closed set with rationale, and the signal-byte
   disclosure in `protocol.md` and the ConPTY developer guide. Acceptance
   evidence: full validation gate; fake-child tests show exact bytes
   written per family and fail-closed behavior with no child write.
2. **Slice 2 — real-child Windows evidence.** Extend the ConPTY
   integration suite with a cooperating fixture subject that observes
   delivered key bytes end to end for representative encodable chords and
   echoes them into frames, with replay identity, on the Windows matrix.
   Acceptance evidence: the durable matrix test demonstrates a real child
   observing the delivered bytes for at least one chord from each
   encodable family class, plus the unresolvable/unencodable path staying
   fail-closed on the real adapter.

Each slice follows the standard loop: focused issue, sibling worktree,
strict TDD for everything locally testable, the full validation gate, PR,
independent adversarial review, merge. Slice ordering is fixed — the
registry contract must not wait on real-child evidence, and no real-child
claim may precede slice 2.
