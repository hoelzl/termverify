---
type: Protocol Design
title: Transcript framing and limits
description: JSONL framing, fixed v1 resource limits, and canonical serialization of termverify.transcript/v1.
tags: [protocol, jsonl, limits, canonicalization]
---

# Transcript framing and limits

Part of the [`termverify.transcript/v1` protocol](../protocol.md).

## JSONL framing

Each UTF-8 JSON Lines file is one transcript for one verified run. A line ends
with exactly one LF (`\n`); a final LF is required. Blank lines, comments, and
byte-order marks are invalid. Readers reject duplicate object member names and
unknown required semantics instead of silently choosing an interpretation.

## Fixed v1 resource limits

The canonical parser and programmatic serializer enforce the same fixed,
protocol-owned ceilings. They do not inherit interpreter recursion settings,
host memory, or ambient configuration:

| Resource | V1 maximum | Counting rule |
| --- | ---: | --- |
| Transcript bytes | 32 MiB (33,554,432 bytes) | Entire JSONL byte sequence, including every final LF. |
| Line bytes | 4 MiB (4,194,304 bytes) | One canonical JSON object, excluding its LF. |
| Records | 10,000 | JSONL objects in one transcript. |
| JSON nesting | 64 | Simultaneously open objects and arrays in one record, including the envelope object. |
| Collection items | 16,384 | Immediate members in one object or items in one array. |
| JSON values | 100,000 | Container and scalar value nodes in one record; object keys are not value nodes. |
| Individual string bytes | 1 MiB (1,048,576 bytes) | UTF-8 bytes of one decoded string value or object key. |
| Record string bytes | 2 MiB (2,097,152 bytes) | Aggregate UTF-8 bytes of every decoded string value and object key in one record. |

The parser checks total bytes, framing, record count, line bytes, and lexical JSON
nesting before JSON decoding. After decoding, it checks collection, value, and
string budgets before semantic validation. Brackets inside JSON strings do not
contribute to lexical nesting. The serializer traverses exact Python JSON values
iteratively, applies the same structured-value budgets before RFC 8785
canonicalization, then checks each canonical line and accumulates transcript
bytes before joining output. Strings longer than the individual byte ceiling in
code points are rejected before UTF-8 measurement, bounding that measurement;
malformed Unicode is normalized to `TranscriptValidationError` rather than
leaking a codec exception. A limit violation is a
`TranscriptValidationError`; interpreter recursion or allocation-dependent
behavior is not a conformance result. Every successfully serialized transcript
therefore remains admissible to the parser under the same ceilings.

## Canonical serialization

Transcript producers use the JSON Canonicalization Scheme
([RFC 8785](https://www.rfc-editor.org/rfc/rfc8785)) for each object, encoded
as UTF-8 and followed by LF. Therefore object-member order, whitespace, string
escaping, and number rendering do not vary by producer. Values that could lose
precision in another JSON implementation, including seeds and monotonic IDs,
are JSON strings rather than numbers.

Canonical bytes are the basis for fixture comparison and transcript digests;
the digest algorithm and value, if emitted, are an optional metadata field and
never replace parsing and semantic validation.
