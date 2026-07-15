# RFC 8785 implementation choice

## Context

`termverify.transcript/v1` requires RFC 8785 canonical JSON bytes. Python's
standard `json` module does not guarantee RFC 8785/ECMAScript number rendering,
so it cannot be used as the canonicalization authority.

## Decision

Use the maintained `rfc8785` Python package to canonicalize each transcript
record. TermVerify retains its own JSONL framing, duplicate-member detection,
and semantic validation.

## Verification plan

- retain canonical valid-fixture byte round-trip tests;
- add regression tests for non-finite-number rejection and representative RFC
  8785 member ordering/number rendering;
- run the locked project quality gate after dependency resolution.
