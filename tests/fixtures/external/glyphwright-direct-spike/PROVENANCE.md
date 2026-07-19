# GlyphWright direct-spike transcript — external conformance fixture

- **Source:** `spikes/termverify-direct-adapter/transcript.jsonl` in the
  [GlyphWright repository](https://github.com/hoelzl/glyphwright), an
  independent external application under test (issue #114).
- **Commit:** `bf80051c5af46ce8eda5b8569797f03b8ed98ffe`
  (2026-07-18), retrieved unmodified on 2026-07-19.
- **SHA-256:** `46daa2fcc25ead6310eabc3fad16a653d9bc99208fc5ccb04f5af1fc246449d3`
- **License:** GlyphWright is Apache-2.0; this fixture is redistributed
  under that license with this attribution and the accompanying
  `LICENSE` copy in this directory.
- **Classification:** public synthetic game-fixture content produced by
  GlyphWright's deterministic `reference-vale` fixture; it contains no
  personal, credential, or host-environment data.

## Role and disclosed protocol delta

This is the external conformance fixture required by the Phase 2 slice-1
evidence plan (`docs/agent/design/phase-2-verification-core-boundary.md`):
GlyphWright's hand-written spike recorder produced these 28 records against
`DirectAdapter`, and TermVerify's `TranscriptRecorder` must reproduce a
semantically identical transcript from the equivalent adapter result
sequence (`tests/test_recorder_conformance.py`).

Disclosed delta: the spike predates the 2026-07-18 enforcement-tier
protocol amendment that made `tier` mandatory on enforced
`capability.result` payloads, so this fixture alone no longer passes the
strict v1 codec. The conformance test asserts semantic member-level
agreement — every envelope member and every parsed payload value — on
everything except exactly that delta: the recorder's enforced capability
payloads equal the spike's plus `"tier": "constructive"`. The fixture is
deliberately kept unmodified; it is not a golden master and no test
asserts it as current-protocol truth.
