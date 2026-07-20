- **Breaking (owner-approved post-freeze registry exception; transcript
  protocol stays v1):** the `termverify.key/v1` modified-only base set is
  widened with the full printable ASCII punctuation row (32 characters:
  ``! " # $ % & ' ( ) * + , - . / : ; < = > ? @ [ \ ] ^ _ ` { | } ~``), each
  requiring a trigger modifier like letters and digits. This makes
  Emacs-lineage chords such as `["Control", "/"]`, `["Control", "_"]`, and
  `["Alt", "<"]`/`["Alt", ">"]` expressible through `KeyInput` for the first
  time; previously no valid chord could name a punctuation base. The change
  is purely additive — every previously valid chord and its encoding is
  unchanged — but it re-binds both reviewed digests: `termverify.key/v1`
  (67 → 99 entries) and the `termverify.key-encoding/v1` full enumeration
  (934 → 1382 chords, 450 → 482 encodable). Encoding semantics follow the
  existing digits/`Space` rule: `["Alt", p]` encodes to `ESC p`; `Control`,
  `Meta`, and `Shift` punctuation forms are unencodable and fail closed (no
  legacy byte form represents them). Migration: re-derive any pinned copy of
  either digest; ConPTY subjects now receive a structured
  `{"unsupported": "key-encoding", ...}` failure for punctuation
  `Control`/`Meta`/`Shift` chords instead of the chord being inexpressible.
  See `docs/agent/design/key-v1-punctuation-bases.md`.
  **Post-freeze exception (owner decision 2026-07-19, issue #155):** this
  amendment was implemented and adversarially reviewed before the 0.1.0
  release froze the inception policy, but merged after it. The owner
  approved landing it as a one-time in-place amendment to `termverify.key/v1`
  rather than cutting a `termverify.key/v2` registry, because the change is
  purely additive (no existing chord, spelling, or encoding is altered) and
  the wire-protocol version is unchanged. This exception does not set a
  precedent: any future change to registry membership, meaning, or spelling
  requires a new registry version per `docs/knowledge/protocol.md`.
=======
Unreleased changes are collected as fragment files in [`changelog.d/`](changelog.d/)
and folded into this file by `scripts/collect_changelog.py` at release time.
