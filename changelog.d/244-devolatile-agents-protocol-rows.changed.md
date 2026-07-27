- **De-volatilized the protocol rows in `AGENTS.md`.** The transcript and
  control rows of the "Commands and Sources of Truth" table no longer embed
  the current governance stage inline (stage name, decision date, decision
  number); they keep the durable polarity rules — runtime validation / the
  strict codec is authoritative, the packaged schema is a structural aid,
  mismatches are repaired doc-side by default — and link
  `docs/agent/design/prototyping-stage-protocol-governance.md` for the
  current stage status. The governance record's Consequences bullet now
  reflects that division: `docs/knowledge/protocol.md` states the status,
  `AGENTS.md` links it.
