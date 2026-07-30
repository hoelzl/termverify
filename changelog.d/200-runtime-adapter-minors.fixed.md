- **Runtime/adapter minors from the 2026-07-24 adversarial review are swept**
  (issue #200, Slice 8.1) — every section-4 runtime bullet now has a
  disposition. Fixed: a second concurrent `read_line` on the JSONL pipe
  binding raises the new `termverify.jsonl.JsonlConcurrentReadError` (a
  `RuntimeError`, mirroring the ConPTY side's `ConptyConcurrentIOError`)
  instead of `JsonlChildClosedError`, and the adapter re-raises it to the
  harness caller instead of classifying it — a harness defect no longer
  wears any subject failure code, neither the old `peer-lifecycle` nor
  the `peer-malformed` its blanket read-failure arm would otherwise
  assign; a refused release-only close decides the refusal inside the lock
  window before any closed state exists, so a concurrent read can no
  longer observe the transient `_closed` window and fail spuriously; the
  VT normalizer tolerates the secondary device-attributes query
  (`CSI > c`) and DEL as grid no-ops, as real terminals do — a conhost
  preamble emitting secondary-DA no longer fails every run on that host,
  while every other `>`-prefixed final stays fail-closed; the unreachable
  handshake branch of `_read_epoch` (handled by `_start_handshake`) and
  its startup-diagnostic budget selection are removed. Disclosed: a ConPTY
  close that cannot cancel in-flight native I/O within its bounded retry
  raises and leaks the blocked frame and its pinned handles for the life
  of the process — releasing them mid-call is the interpreter-crash case,
  so the leak is stated in the module docstring, the raise, and the
  developer guide. Recorded won't-fix: the 2-second exit-reap grace stays
  unconditional — the adapter's own failure paths never consult it, a
  conforming child's exit after a terminal message returns the wait in
  milliseconds, and a graceless probe would trade transcript determinism
  for latency only a breaching subject incurs. (The review's vestigial
  `if write is not None` in `jsonl.py` was already removed by an earlier
  phase.)
