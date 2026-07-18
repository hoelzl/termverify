# VT Normalizer Decision: Screen-Model Reuse Assessment and v1 Subset

- **Status:** accepted — decided 2026-07-18 under the maintainer's delegated
  autonomous authority; passed independent adversarial agent review before
  merge. This is the reuse/dependency assessment and design note required by
  implementation slice 1 of the accepted
  [ConPTY adapter design](conpty-adapter-design.md). It authorizes the
  `TerminalOutputNormalizer` port and the in-house implementation delivered
  in the same change.
- **Issue:** [#115](https://github.com/hoelzl/termverify/issues/115)
- **Date:** 2026-07-18
- **Inputs:** the accepted [ConPTY adapter design](conpty-adapter-design.md)
  (port shape, replay rule, marker semantics, mandatory cursor evidence);
  the `Frame`/`Cursor`/`UiObservation` contract in `termverify.adapter`;
  the transcript replay-subject `normalizer {id, version}` selector.

## Decision

The screen model is implemented **in-house** as `termverify.vt`: the
`TerminalOutputNormalizer` protocol exactly as fixed by the adapter design,
and a deterministic `VtScreenNormalizer` for a closed, documented VT subset,
with fail-closed handling of anything outside it. No dependency is added.

The third-party candidate `pyte` (the only maintained pure-Python terminal
screen emulator of note) is **rejected** on three grounds, each sufficient:

1. **License:** `pyte` is LGPL-3.0 (GitHub license metadata, 2026-07-18);
   termverify is Apache-2.0. An LGPL dependency imposes obligations on
   downstream distributors that nothing in this repository currently
   imposes, for functionality we can implement in a few hundred ratcheted
   lines.
2. **Maintenance:** the latest PyPI release is 0.8.2 from 2023-11-12 —
   about two and a half years without a release at assessment time — with
   59 open issues. The dependency decision for `pywinpty` accepted a
   single-maintainer bus factor for a native binding we cannot reasonably
   write; a dormant dependency for pure-Python logic we can own is not the
   same trade.
3. **Fail-open semantics:** `pyte` silently ignores escape sequences it
   does not recognize. For an evidence tool that is the wrong default: an
   unrecognized sequence means the frame may be wrong, and a wrong frame
   presented as evidence is worse than a structured failure. TermVerify's
   normalizer must fail closed on unknown grid-affecting input, which would
   mean wrapping and policing `pyte` rather than trusting it.

If implementation-time evidence invalidates the in-house choice, replacing
it requires amending this document, not silent substitution.

## Port and identity

- The protocol and implementation live in `termverify.vt`:
  `TerminalOutputNormalizer` with `feed(chunk: str) -> None`,
  `notify_resize(rows: int, columns: int) -> None`, and
  `snapshot() -> ScreenSnapshot`, constructed for a run with the initial
  dimensions. `ScreenSnapshot` is a frozen aggregate of the contract's
  `Frame` and `Cursor` plus the truthfully tracked screen `mode`
  (`"normal"` or `"alternate"`), feeding the observation's mandatory `ui`.
- Determinism: the snapshot is a pure function of the fed chunk sequence,
  the initial dimensions, and the resize notifications. No ambient state,
  no clock, no locale. Sequences split across `feed` chunks parse
  identically to unsplit input (incremental parser state).
- Replay identity: the normalizer identity is
  `id="termverify.vt", version="1"`, exposed as module constants and
  intended for the transcript replay-subject `normalizer {id, version}`
  selector. Any post-release change to the v1 subset's observable
  semantics requires a new version, exactly like the protocol registries.
- Cursor coordinates are 0-based (the `Cursor` contract requires only
  non-negative integers) and always clamped inside the current grid;
  `visible` tracks DECTCEM.

## The v1 subset (closed registry)

Chosen for what ConPTY's renderer emits to the host, per Microsoft's VT
sequence documentation and the repository's spike/binding evidence; the
Windows integration slice is the executable check of that coverage claim.

**Handled with grid semantics:**

- Printable characters with xterm-style deferred auto-wrap (the
  last-column pending-wrap quirk, documented in tests).
- C0: `BEL` (consumed), `BS`, `HT` (tab stops), `LF` (index, scrolls
  inside the margins at the bottom), `CR`.
- ESC: `7`/`8` (save/restore cursor), `D` (IND), `E` (NEL), `M` (RI),
  `H` (HTS), `c` (RIS full reset), charset designations `( ) * +` with a
  single final byte (consumed; no charset translation is claimed), `=`/`>`
  (keypad, consumed).
- CSI: `CUP H`/`HVP f`, `CUU A`, `CUD B`, `CUF C`, `CUB D`, `CNL E`,
  `CPL F`, `CHA G`, `VPA d`, `ED J` (0/1/2), `EL K` (0/1/2), `ICH @`,
  `DCH P`, `ECH X`, `IL L`, `DL M`, `SU S`, `SD T`, `DECSTBM r`,
  `TBC g` (0/3), `SGR m` (parsed and consumed — attributes are not
  evidence in v1), and DEC private modes `?25` (DECTCEM → cursor
  visibility), `?12` (cursor blink, consumed), `?1049`/`?1047`/`?1048`
  (alternate screen buffer with save/restore semantics; drives `mode`).
- String sequences: `OSC`, `DCS`, `SOS`, `PM`, `APC` are consumed in full
  (BEL- or ST-terminated) and never rendered — by ECMA-48 definition they
  carry no grid mutation, so wholesale consumption is deterministic and
  grid-safe. This is what keeps the readiness marker (a private OSC) out
  of frames as an outcome of screen-model semantics, exactly as the
  adapter design requires.

**Fail-closed:** any other C0 control, any unlisted ESC or CSI final byte,
and any unlisted DEC private mode raise `VtNormalizationError` carrying the
offending sequence — a structured error the adapter will classify as a
runtime failure. A frame is never silently wrong; it is either within the
claimed subset or the run fails loudly with the evidence of why.

**Documented v1 limitations (not claims):** frames are plain text —
colors, styling, and charset translation are consumed, not evidence; there
is no scrollback (the frame is the viewport; content scrolled off the top
is gone); wide-character cell arithmetic is not modeled (cells are code
points); `mode` reports only normal/alternate.

## Resize semantics

`notify_resize` crops or pads the grid preserving the top-left corner,
clamps the cursor, and resets the scroll margins to the full new screen.
This is deliberately the simplest deterministic rule: the adapter design
routes explicit `Resize` epochs through ConPTY, whose renderer repaints
after a resize, so the repaint — not the crop rule — determines the
content the next quiescent frame shows.

## Verification plan

- Strict TDD; the module is cross-platform, fully coverage-ratcheted, and
  pure (no ambient state), tested by construction from typed inputs.
- Tests pin: every subset entry's grid semantics; deferred-wrap behavior;
  scroll-margin behavior; alternate-buffer switch and restore; chunk-split
  parsing equivalence; OSC/DCS consumption including the readiness marker;
  the fail-closed error for unknown sequences; snapshot purity (same feeds
  → equal snapshots) and `Frame`/`Cursor` contract validity; resize
  crop/pad and clamping; identity constants.
- The adapter design's replay rule — replaying the normalizer over raw
  chunks reproduces the frames — is exercised here as the purity property;
  end-to-end replay against real ConPTY output is the Windows integration
  slice's evidence, which is also the executable check that the v1 subset
  actually covers ConPTY's output.

## Non-goals

No adapter or binding changes; no styling/attribute evidence; no
scrollback; no wide-character claims; no terminal-capability registry
activation; no dependency.
