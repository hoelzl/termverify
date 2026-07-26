- **The native ConPTY binding is coverage-visible again.** The omit in
  `pyproject.toml` stood on a "deliberately thin wrapper" rationale that
  stopped being true when the binding took the pseudoconsole over from
  pywinpty (#197); both review rounds of #234 found defects in exactly the
  code the omit made invisible. The Windows CI legs now run a supplemental,
  non-gating measurement (`conpty-coverage.toml`) of the ConPTY suites
  against `termverify._conpty` and report with missing lines — the gaps are
  visible in every Windows-leg log, while the cross-platform gating floor
  stays OS-independent. Recorded disposition: Slice 8.3 of the 2026-07-24
  remediation handover. The stale rationale is corrected in the module
  docstring, the developer guide, and the `pyproject.toml` comment.
  (Closes #236.)
