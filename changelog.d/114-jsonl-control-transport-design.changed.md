- Added the accepted-design proposal for the JSONL subprocess control
  transport (issue #114 ask 2): `termverify.control/v1`, a
  TermVerify-owned, closed, versioned wire protocol mapping the frozen
  transcript/v1 lifecycle onto an interactive pipe, plus `JsonlAdapter`
  as the third implementation of the adapter contract (after direct and
  ConPTY). The design records the Option A/B/C analysis (owner decision
  2026-07-20: Option B), the JSON-RPC/LSP reuse assessment, the
  malformed-peer failure taxonomy, spawn-time constraint delivery via
  the cooperation ports, a live `input.clock` channel (new capability
  versus ConPTY), and pipe-based teardown semantics. Docs-only: the two
  implementation slices await design acceptance.
