# `termverify.key/v1` Punctuation Base Amendment

- **Status:** accepted — decided 2026-07-19 by explicit owner direction. The
  owner selected the **full printable-ASCII punctuation row** over the curated
  `/ _ < >` subset proposed in the issue.
- **Issue:** [#155](https://github.com/hoelzl/termverify/issues/155)
- **Date:** 2026-07-19
- **Inputs:** the closed `termverify.key/v1` registry
  (`src/termverify/_key_v1.py`, documented in
  [`docs/knowledge/protocol.md`](../../knowledge/protocol.md)); the companion
  `termverify.key-encoding/v1` registry and its accepted design
  ([`key-to-terminal-byte-mapping.md`](key-to-terminal-byte-mapping.md)); the
  RecursiveNeon core-editor spike (PR hoelzl/RecursiveNeon#72) whose undo
  (`C-/`, `C-_`) and buffer-jump (`M-<`, `M->`) bindings are undrivable
  through `KeyInput` today.

## Problem

`termverify.key/v1` admits named bases (special keys) and modified-only bases
(lowercase ASCII letters, digits, `Space`). Printable ASCII punctuation has no
base, so a direct adapter cannot construct a valid `KeyInput` for any chord
whose base is punctuation. Real Emacs-lineage subjects bind exactly such
chords (`C-/` undo, `C-_` undo alias, `M-<` / `M->` buffer edges); the spike
mapped 14 of 18 RecursiveNeon core bindings and was blocked on the remaining
four. `TextInput` cannot express a modified chord, so there is no workaround
inside the direct architecture — the adapter fails closed.

## Decision

Extend the v1 modified-only base set with the full printable-ASCII
punctuation row, 32 characters:

```text
! " # $ % & ' ( ) * + , - . / : ; < = > ? @ [ \ ] ^ _ ` { | } ~
```

Each is a modified-only base under the existing grammar: it requires at least
one trigger modifier (`Control`, `Alt`, or `Meta`); `Shift` alone and the
unmodified form remain invalid (unmodified printable insertion stays
`input.text`). Chord validity, modifier ordering, and case-sensitivity rules
are unchanged.

This is an in-place amendment under the repository's pre-freeze inception
policy (`docs/knowledge/protocol.md`, "Compatibility and evolution"): no
released artifact or external client exists, so widening v1 is preferred to a
fictional v2. The freeze rule that post-freeze membership changes require a
new registry version is unchanged and now explicitly notes this amendment as
a pre-freeze change.

### Why the full row, not the curated subset

The curated subset (`/ _ < >`) closes only the four chords one spike hit.
Punctuation bindings are generic across every Emacs-lineage and readline
subject (a future GNU Emacs differential target, micro, shells). Adding them
piecemeal would force repeated pre-freeze amendments and repeated digest
churn; the full row closes the class in one reviewed change with one new
digest. The cost is identical per character — the encoding registry is
arithmetic, not a hand-maintained table.

## Encoding semantics (companion registry)

The `termverify.key-encoding/v1` registry requires no structural change: its
encoder already routes any non-letter modified-only base through the
digits/`Space` path. Under the accepted "represent every component by
definition" principle this yields, for each new punctuation base `p`:

- `["Alt", p]` → `ESC p` — **encodable** (one byte, modifier represented).
- `["Control", p]`, `["Meta", p]`, and every subset containing `Shift` →
  **unencodable** (fail closed). Legacy terminals have no consistent
  `Control`+punctuation byte form, and emitting the base's own byte would
  silently drop the modifier — the misrepresentation the protocol forbids.

Concretely the four motivating chords: `M-<` / `M->` become drivable and
encodable (`ESC <`, `ESC >`); `C-/` and `C-_` become drivable as semantic
chords (a direct subject reads them structurally) but remain unencodable on
the ConPTY byte path, where the adapter fails closed with the documented
`{"unsupported": "key-encoding", ...}` verdict — an honest result, since a
real legacy terminal cannot deliver `C-/` distinctly either.

### Updated cardinalities

| Quantity | Before | After |
| --- | --- | --- |
| `KEY_NAMES` entries | 67 | 99 |
| Valid chords | 934 | 1382 |
| Encodable chords | 450 | 482 |

The full-enumeration digest of `termverify.key/v1` and the digest-bound
enumeration of `termverify.key-encoding/v1` both change; the new SHA-256
values are recorded in `protocol.md` and pinned in executable tests. The
four disclosed legacy byte collisions are unaffected (punctuation adds no new
collision).

## Compatibility and migration

- The transcript protocol stays `termverify.transcript/v1`; `input.key`
  remains semantic and no record carries bytes. No schema member changes.
- Existing valid chords and their encodings are unchanged — this is purely
  additive. Any previously recorded transcript remains valid.
- Adapter authors gain the ability to express punctuation-base chords; no
  previously expressible chord changes meaning.
- `CHANGELOG.md` records the amendment under the pre-1.0 policy as a breaking
  protocol-registry change with a migration note (re-derive the digest;
  ConPTY subjects now fail closed on punctuation `Control`/`Meta`/`Shift`
  chords rather than the chord being inexpressible).

## Explicit non-goals

- No `Control`+punctuation encoding synthesis (no CSI-u / kitty /
  `modifyOtherKeys`); that remains a future `termverify.key-encoding/v2`
  owner decision, exactly as deferred in the encoding design.
- No change to modifier grammar, ordering, case rules, or the named-base set.
- No new transcript record kind or member.

## Testing and validation

- Update the `termverify.key/v1` digest test (67 → 99 entries) and its
  documented SHA-256.
- Update `termverify.key-encoding/v1` tests: enumeration count (934 → 1382),
  encodable-set size (450 → 482), the four-collision disclosure (unchanged),
  and the full-enumeration digest, plus exact-byte rows for representative
  punctuation (`Alt+<` → `ESC <`, `Alt+/` → `ESC /`) and fail-closed rows for
  `Control`/`Meta`/`Shift` punctuation forms.
- Add `is_key_chord` acceptance rows for punctuation chords and rejection
  rows for unmodified / `Shift`-only punctuation.
- Full validation gate: pytest with coverage above the ratchet floor, ruff
  check/format, mypy, pre-commit, and `uv build`.
