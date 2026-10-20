---
type: Protocol Design
title: Transcript inputs and observations
description: Input kinds, termverify.key/v1 semantic key chords, diagnostics, and observations of termverify.transcript/v1.
tags: [protocol, inputs, keys, observations]
---

# Transcript inputs and observations

Part of the [`termverify.transcript/v1` protocol](../protocol.md).

## Inputs and observations

V1 input kinds are `input.key`, `input.text`, `input.resize`, `input.mouse`,
`input.clock_advanced`, `input.clipboard_set`, and `input.stop`. Every input
payload includes a non-negative integer `at_ms` manual-clock value and has the
following additional required members. No member not listed as optional is
permitted in a generic v1 input payload, except an `x-` extension member with
no generic v1 meaning.

| Kind | Required payload members |
| --- | --- |
| `input.key` | `keys`: ordered array containing one canonical `termverify.key/v1` semantic chord |
| `input.text` | `text`: Unicode string |
| `input.resize` | positive integer `columns` and `rows` |
| `input.mouse` | `action`: `press`, `release`, `move`, or `scroll`; non-negative integer `column` and `row`; `button` (`left`, `middle`, or `right`) for `press`/`release`; non-zero integer `delta` for `scroll` |
| `input.clock_advanced` | positive integer `delta_ms`; `at_ms` equals the preceding manual time plus `delta_ms` |
| `input.clipboard_set` | `text`: Unicode string |
| `input.stop` | no additional members |

### Semantic key chords

TermVerify owns the closed `termverify.key/v1` registry. An `input.key` record
represents one simultaneous semantic chord; a sequence of keystrokes requires
multiple input records and therefore multiple quiescent input epochs. The
`keys` array contains zero or more modifiers followed by exactly one base key.
Modifiers are unique and, when present, appear in this canonical order:
`Control`, `Alt`, `Shift`, `Meta`.

The exact v1 component registry has 99 entries:

- modifiers: `Control`, `Alt`, `Shift`, `Meta`;
- named bases: `Enter`, `Tab`, `Escape`, `Backspace`, `Delete`, `Insert`,
  `ArrowUp`, `ArrowDown`, `ArrowLeft`, `ArrowRight`, `Home`, `End`, `PageUp`,
  `PageDown`, and `F1` through `F12`;
- modified-only bases: lowercase ASCII `a` through `z`, ASCII `0` through `9`,
  `Space`, and the printable ASCII punctuation row
  ``! " # $ % & ' ( ) * + , - . / : ; < = > ? @ [ \ ] ^ _ ` { | } ~``.

A modified-only base requires at least one of `Control`, `Alt`, or `Meta`.
`Shift` alone does not make a printable base valid. Thus `["Control", "c"]`,
`["Alt", "1"]`, `["Control", "Space"]`, `["Control", "/"]`, and
`["Alt", "<"]` are valid; `["c"]`, `["1"]`, `["Space"]`, `["/"]`,
`["Shift", "a"]`, and `["Shift", "<"]` are invalid. Unmodified printable
insertion, including an ordinary space, punctuation, or uppercase letter,
uses `input.text`.

Names are exact and case-sensitive. V1 performs no trimming, case folding,
Unicode normalization, alias rewriting, or modifier reordering. Toolkit names,
OS virtual-key codes, physical-key locations, curses names, and terminal escape
sequences are not protocol values. In particular, `Ctrl`, `Cmd`, `Option`,
`Esc`, `Return`, lowercase `enter`, chord strings such as `Ctrl+C`, and encoded
bytes such as `\u001b[A` are invalid. `Space` is TermVerify's semantic name for
the space key when it participates in an approved modified chord; it is not a
raw whitespace identifier.

Neither `input.key` nor `input.text` is a raw terminal-byte channel. An adapter
maps a valid semantic value to its own application boundary and must fail rather
than silently translate an unknown value, alias, or ambiguous escape sequence.
An `x-` extension cannot add registry entries or change chord meaning. The
reviewed registry order is digest-bound in executable tests using newline-joined
UTF-8 names with a final LF; its SHA-256 is
`51955be77ab11b23240c642edd0e4f08dbd56389b82f99bbe2ee87871ce9d0a0`.

The registry and its membership predicate are on the package's public
surface as `termverify.KEY_NAMES` and `termverify.is_key_chord`; the module
that defines them is private and is not a supported import path. The
terminal adapter maps chords to bytes through the companion
[`termverify.key-encoding/v1` registry](key-encoding.md).

## Mouse input, diagnostics, and observations

For `input.mouse`, `button` and `delta` are forbidden for `move`; `delta` is
forbidden for `press` and `release`; and `button` is forbidden for `scroll`.
Clipboard values are sensitive evidence and their
[capture/redaction policy](../evidence-governance.md) requires persistence through
the evidence-aware writer; the raw codec is non-persistent.

`diagnostic` has required `at_ms`, non-empty string `code`, and string
`message` members; optional `details` holds a JSON value. It is non-oracle
information and cannot change a run's terminal status.

An `observation` payload has these required members:

- `at_ms`: manual-clock value at capture;
- `state`: application-defined JSON value after a documented normalizer;
- `events`: ordered array of `{"type": non-empty string, "data": JSON value}`
  objects;
- `ui`: an object with the required members below.

Terminal output records read-boundary-free: the recorder merges each run of
adjacent events whose `type` is `terminal.output` and whose `data` is exactly
`{"chunk": <string>}` into one event with the chunks concatenated, because
native read boundaries are OS scheduling noise, not subject behavior
(issue #195). Any other event passes through unchanged and ends the run of
adjacency. This is recorder behavior, not codec acceptance: the codec does
not reject a transcript that was produced without coalescing.

`ui.regions` is an ordered array of objects with non-empty `id` and `role`
strings and a `bounds` object containing non-negative integer `column` and
`row` plus positive integer `columns` and `rows`. Region IDs are unique within
the observation. `ui.focus` is a region ID or `null`; `ui.cursor` is
`{"column": non-negative integer, "row": non-negative integer, "visible": boolean}`;
and `ui.mode` is a string or `null`. A non-null focus must name one of the
observation's regions.

`frame` (a normalized rendered terminal frame) and `process` (lifecycle detail)
are optional evidence layers. When present, `frame` is
`{"lines": [string, ...], "columns": positive integer, "rows": positive integer}`
with `len(lines) == rows`; `process` is `{"state": "running"}` or
`{"state": "exited", "exit": <run.finished exit object>}`. The shipped
comparator compares whole record payloads by exact canonical equality, so a
`frame` difference and a `state` difference are both reported and a matching
frame cannot conceal a domain mismatch; it does not rank domain evidence above
rendering evidence. Application-specific values belong
under documented `x-` members or a registered normalizer, not under new generic
v1 member names.

When a transcript ends with `run.finished`, every exited-process observation
has the same exit `kind` and `value` as `run.finished.payload.exit`.
An exited-process observation is the final body record. Uninterpreted `x-`
extensions do not participate in the exit comparison. The relationship with
the other terminal outcomes is asymmetric.
`run.unsupported` has no body and therefore no process observation. A
`run.failed` transcript may retain independently captured exited-process
evidence; that evidence is orthogonal to the adapter or harness failure and has
no terminal exit value to match.
