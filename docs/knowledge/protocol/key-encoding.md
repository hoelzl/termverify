---
type: Protocol Design
title: Key encoding registry
description: The termverify.key-encoding/v1 registry mapping semantic key chords to xterm-legacy terminal bytes.
tags: [protocol, keys, terminal, encoding]
---

# Key encoding registry

Part of the [`termverify.transcript/v1` protocol](../protocol.md).

The terminal execution path has a companion registry to
[`termverify.key/v1`](inputs-and-observations.md#semantic-key-chords),
`termverify.key-encoding/v1` (public entry point:
`termverify.encode_key_chord`), that maps each of the 1382 valid
`termverify.key/v1` chords either to exactly one xterm-legacy normal-mode
byte string or to the explicit fail-closed verdict
**unencodable**. It is committed data plus committed arithmetic owned by
TermVerify — never derived from terminfo, toolkit enums, OS virtual-key
codes, or other ambient host state — and it is not a transcript value: an
`input.key` record stays semantic, no record carries encoded bytes, and this
registry can version independently of the transcript protocol. A chord is
encodable exactly when the legacy encoding represents every chord component
by definition; when the only candidate bytes would drop a modifier
(`Control+Enter`, `Control+/`), alias one modifier to another (`Meta` as
`Alt` on letters), or pass a NUL hazard (`Control+Space`), the registry
returns unencodable and the adapter fails rather than misrepresent the
chord. Four
byte collisions inherent to the legacy byte space are disclosed:
`["Control", "m"]`/`["Enter"]` (CR), `["Control", "i"]`/`["Tab"]` (HT), and
their two `Alt`-prefixed forms. The full enumeration — each chord joined
with `+`, then ` => ` and the space-joined two-digit lowercase hex code
points of its encoding or the word `unencodable`, newline-joined UTF-8 with
a final LF — is digest-bound in executable tests; its SHA-256 is
`72a17da549238053c88a925cf6bf2bbe93ed2b8564c7a09188075987fcdcda95`. The
[compatibility policy](compatibility.md) applies to this registry as well; details
of the adapter behavior live in the
[ConPTY developer guide](../../developer-guide/conpty-adapter.md).
