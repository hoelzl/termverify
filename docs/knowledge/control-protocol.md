---
type: protocol
---

# TermVerify JSONL control protocol (`termverify.control/v1`)

The control protocol is the live counterpart of
[`termverify.transcript/v1`](protocol.md): a subject subprocess speaks it
over its stdin/stdout pipes, and an adapter (`termverify.jsonl.JsonlAdapter`)
drives the run through it. The transcript protocol remains the evidence
format; the control protocol is the wire. Neither imports the other's
machinery, but the control protocol's lifecycle is the transcript
lifecycle made interactive, member for member: negotiation → readiness →
single-flight epochs → terminal.

This document is the normative specification of the protocol. The
authoritative runtime acceptance is the strict codec in
`src/termverify/control.py`; on any disagreement the codec is wrong and
this document wins — report the defect.

The protocol is **unfrozen** as of its introduction: it may still change
in place. It freezes at the first PyPI publication of a TermVerify
release that contains it; after that, amendments require a new protocol
version.

## Framing and canonical form

Transport is a pair of byte pipes: the adapter writes to the child's
stdin, the child writes to its stdout. Each message is exactly one line:

- one JSON object, serialized with the JSON Canonicalization Scheme
  (RFC 8785), encoded as UTF-8, terminated by exactly one LF (`\n`);
- no byte-order mark, no blank lines, no embedded CR;
- a reader rejects duplicate object member names and malformed JSON;
  it never chooses an interpretation.

The child's stderr is not part of the protocol. An adapter may drain it
as diagnostic evidence at its own discretion, but no protocol meaning
attaches to it.

## Fixed v1 resource limits

The codec enforces the same fixed, protocol-owned ceilings as the
transcript protocol's per-record budgets. They do not inherit
interpreter recursion settings, host memory, or ambient configuration:

| Resource | V1 maximum | Counting rule |
| --- | ---: | --- |
| Message line bytes | 4 MiB (4,194,304 bytes) | One canonical JSON message, excluding its LF. |
| JSON nesting | 64 | Simultaneously open objects and arrays in one message, including the envelope object. |
| Collection items | 16,384 | Immediate members in one object or items in one array. |
| JSON values | 100,000 | Container and scalar value nodes in one message; object keys are not value nodes. |
| Individual string bytes | 1 MiB (1,048,576 bytes) | UTF-8 bytes of one decoded string value or object key. |
| Message string bytes | 2 MiB (2,097,152 bytes) | Aggregate UTF-8 bytes of every decoded string value and object key in one message. |
| Startup diagnostics | 100 | `diagnostic` messages before `session.ready`. |
| Epoch diagnostics | 100 | `diagnostic` messages between an input and its closing message. |

A limit violation is a structured peer failure (`peer-malformed`),
never a silent truncation. The sender of an oversized message is a
defective peer.

## Common envelope

Every message is an object with these required members:

| Member | Type | Meaning |
| --- | --- | --- |
| `protocol` | string | Exactly `termverify.control/v1`. |
| `kind` | string | Message kind from the v1 set below. |
| `payload` | object | Data defined by `kind`; no omitted required members. |

An extension member starts with `x-` and has no meaning to a generic v1
peer. All other envelope members are reserved. A producer must not use
an extension to change the meaning of a required v1 member, and a
receiver rejects a non-`x-` member outside this envelope.

## Message kinds and lifecycle

The adapter-to-child kinds are `session.hello`, `input.text`,
`input.key`, `input.resize`, `input.clock`, `input.stop`.

The child-to-adapter kinds are `session.unsupported`, `session.failed`,
`session.ready`, `diagnostic`, `observation`, `run.finished`,
`run.failed`.

A session has exactly this shape, mirroring the transcript lifecycle:

1. The adapter sends exactly one `session.hello`, then waits.
2. The child replies with exactly one of: `session.unsupported`
   (negotiation ends, no run), `session.failed` (the child refuses or
   cannot start; the run failed), or `session.ready` (the run is
   ready). Zero or more `diagnostic` messages may precede `session.ready`
   but not the other two replies.
3. If ready: zero or more single-flight epochs (below).
4. The session ends with exactly one terminal message from the child:
   `run.finished` or `run.failed`, or with an adapter-side failure
   (malformed peer, deadline expiry, exit without a terminal message).

No child message is valid before `session.hello`. No input is valid
before `session.ready`. Nothing may follow a terminal message.

### Epochs

After readiness, the protocol is single-flight. Each epoch contains:

1. exactly one input message from the adapter;
2. zero or more `diagnostic` messages from the child, caused while
   handling that input;
3. exactly one `observation` from the child closing the epoch at
   deterministic quiescence, unless a terminal message closes it first.

Another input before the closing message is a `peer-lifecycle`
violation. `observation` or `diagnostic` while idle (no epoch open) is
a `peer-lifecycle` violation; diagnostics do not create hidden epochs.
`input.stop` is the final input; its drain epoch may contain
diagnostics and an optional final `observation`, followed by a terminal
message. A terminal message may also occur while idle when the subject
exits on its own.

This model intentionally excludes unsolicited body traffic. General
asynchronous work requires a future explicit polling, draining, or
correlation contract rather than wall-clock quiet-window polling.

## Message payloads

### `session.hello` (adapter → child)

| Member | Type | Meaning |
| --- | --- | --- |
| `run_id` | string | The run identifier, lowercase ASCII letters, digits, `.`, `_`, `-`; non-empty. |
| `config` | object | The requested deterministic constraints, exactly the `termverify.transcript/v1` `run.started.payload.config` shape (seed as a decimal string, clock mode and initial milliseconds, locale, timezone, terminal, filesystem, network). |
| `at_ms` | integer | The initial manual time in milliseconds, exactly `config.clock.initial_ms`. |

The child must treat the configuration as non-negotiable: it may refuse
(`session.unsupported`) or fail (`session.failed`), never reply with
different effective values.

### `session.unsupported` (child → adapter)

| Member | Type | Meaning |
| --- | --- | --- |
| `constraint` | string | The refused constraint name from the v1 set (`seed`, `clock`, `locale`, `timezone`, `terminal`, `filesystem`, `network`). |
| `code` | string | `constraint-unsupported` or `constraint-not-enforced`. |
| `message` | string | Human-readable reason. |
| `details` | JSON value | Optional structured detail. |

### `session.failed` (child → adapter)

| Member | Type | Meaning |
| --- | --- | --- |
| `error` | object | `{"code": non-empty string, "message": string, "details"?: JSON value}` — the transcript `run.failed` error shape. |

### `session.ready` (child → adapter)

| Member | Type | Meaning |
| --- | --- | --- |
| `observation` | object | An observation payload (below): the initial readiness observation, positionally declaring that initialization completed and the subject is ready for input. Its process observation must not report exit. |

### `diagnostic` (child → adapter)

| Member | Type | Meaning |
| --- | --- | --- |
| `code` | string | Non-empty diagnostic code. |
| `message` | string | Human-readable text. |
| `details` | JSON value | Optional structured detail. |

### Input messages (adapter → child)

| Kind | Payload members | Meaning |
| --- | --- | --- |
| `input.text` | `text`: string | Literal text input. |
| `input.key` | `keys`: array of strings | One canonical `termverify.key/v1` semantic chord. The child is a structured peer: no `termverify.key-encoding/v1` byte encoding is involved. |
| `input.resize` | `columns`, `rows`: positive integers | Terminal dimension change. |
| `input.clock` | `at_ms`: non-negative integer | The manual time the subject must treat as current from this epoch onward. The epoch opens at this time; it is the prior manual time plus the advance, and the first advance starts from the negotiated initial time. |
| `input.stop` | *(empty object)* | Request a cooperative shutdown; the drain epoch follows. |

### `observation` (child → adapter)

| Member | Type | Meaning |
| --- | --- | --- |
| `state` | JSON value | The subject's semantic state evidence. Opaque to the protocol; the subject's state schema gives it meaning. |
| `ui` | object | `{"regions": [...], "focus": string \| null, "cursor": {"column", "row", "visible"}, "mode": string \| null}` — the structured UI observation, same shape as the contract's `UiObservation` value (regions carry `id`, `role`, `column`, `row`, `columns`, `rows`; ids are unique; focus names a region). |
| `events` | array | Zero or more `{"type": non-empty string, "data": JSON value}` entries in application emission order. |
| `frame` | object or absent | `{"lines": array of strings, "columns", "rows"}` with `lines.length == rows`; the subject's rendered surface, if it has one. |
| `process` | object or absent | `{"state": "running"}` or `{"state": "exited", "exit": <exit record>}`. An exited process observation is valid only in a terminal epoch's closing observation. |

An exit record is `{"kind": "code", "value": integer}` or
`{"kind": "signal", "value": non-empty string}` — the transcript
`run.finished` exit shape.

### `run.finished` (child → adapter)

| Member | Type | Meaning |
| --- | --- | --- |
| `exit` | object | The exit record the subject claims. The adapter treats the OS-observed exit record as authoritative; a disclosed mismatch is adapter evidence, not a protocol violation. |

### `run.failed` (child → adapter)

| Member | Type | Meaning |
| --- | --- | --- |
| `error` | object | The `{"code", "message", "details"?}` error shape. The subject reports its own failure. |

## Timing and causality

Messages carry no timestamps. Causality is transport order, exactly as
transcript order supplies causality in the evidence format. All timing
claims live in the manual clock: the negotiated initial time, then each
`input.clock` target. Wall-clock input exists only as the adapter's
abort-deadline policy, which is host abort policy and never evidence of
subject behavior.

## Failure taxonomy (adapter-observed)

These are the adapter's structured failure codes for the failure class
a process boundary adds. They are `run.failed`/`StartFailed` material,
never diagnostics:

| Code | Meaning |
| --- | --- |
| `spawn-failed` | The child process could not be started. |
| `handshake-timeout` | The abort deadline expired before the child completed the handshake reply. |
| `peer-malformed` | A child message is not a valid v1 message: malformed JSON, wrong protocol tag, unknown kind, missing or misspelled required member, non-`x-` extension violation, or a resource-limit breach. |
| `peer-lifecycle` | A structurally valid message arrives out of lifecycle position: traffic before `session.hello` could only be a race on reused pipes, a second readiness, an observation with no epoch open, an input's closing message never arriving before the next input, or traffic after a terminal message. |
| `epoch-timeout` | The abort deadline expired with an epoch open: no closing observation or terminal message arrived in time. The deadline is host abort policy, not evidence. |
| `teardown-forced` | The adapter terminated the child tree (deadline expiry or forced stop); the exit record is the forced-termination record, disclosed as such. |

Subject-reported failures arrive as `session.failed` or `run.failed`
messages and keep the subject's own error codes.

## Subject obligations

A conforming subject:

1. reads stdin as bytes, decodes UTF-8, splits on LF — pipe input has
   none of the console-input parsing caveats a terminal has;
2. answers `session.hello` with exactly one handshake reply;
3. honors the negotiated constraints as delivered in its spawn
   environment and the hello configuration — delivery, not enforcement,
   is the adapter's boundary, so honoring is the subject's documented
   cooperation obligation. Receipts record the delivery channel per the
   amended `termverify.transcript/v1` delivery model
   ([channel-tagged delivery records](../agent/design/channel-tagged-delivery-records.md)):
   the six cooperation-port constraints are `spawn-env` deliveries, and
   the terminal constraint is a `hello-config` delivery whose evidence
   is the hello `config` itself;
4. treats `input.clock`'s target as its only current time from that
   epoch onward;
5. closes every epoch with exactly one `observation` or a terminal
   message, and never speaks out of turn;
6. exits after `run.finished` or `run.failed`, and may simply exit on
   its own — the adapter observes the real exit record at the OS
   boundary.
