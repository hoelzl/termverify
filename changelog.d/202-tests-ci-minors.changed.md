- **Tests/CI minors from the 2026-07-24 adversarial review are swept**
  (issue #202, Slice 8.3). Hypothesis now runs a derandomized profile on CI
  so a build's property-test verdict is reproducible from its logs, while
  local runs stay exploratory (owner decision 2026-07-24; `tests/conftest.py`).
  `scripts/` joined coverage measurement (owner decision 2026-07-24): the
  governance validators are ratcheted with the package, the floor was
  re-baselined once to the integer floor of the newly observed total
  (93, from 93.55% — the package-only total was 95.3%, so this reflects
  the validators' CLI legs, not a package regression), and
  `check_installed_package.py` — which runs only as a CI subprocess against
  built artifacts — became the second reviewed exclusion beside
  `_conpty.py`. The `OpenProcess`-after-termination flake recorded on the
  issue is fixed at its root: the ConPTY binding tests now open the child's
  OS handle inside the `CreateProcessW` interception, while the child is
  still suspended, so exit-code evidence can never race PID reaping, and
  the spy fails closed (a failed handle open terminates the suspended
  child rather than stranding it). The `TV_CWD` capture in the delivery
  tests is race-proofed the same way — the child brackets the path with
  an explicit terminator and the test strips injected VT sequences and
  wrap breaks before matching, closing the raw-output contamination flake
  this PR's own CI surfaced. The remaining arrangement sleeps were
  audited; each already carries an arrangement-not-evidence comment from
  earlier slices. Also: a direct invalid-UTF-8 fixture pins
  `_parse_line`'s `UnicodeDecodeError` leg; the quality, package, and docs
  CI jobs carry `timeout-minutes`; the test suite is a package
  (`tests/__init__.py`) so modules can share helpers; and the JSONL fake
  child grew public `fail_reads`/`fail_writes` arrangement methods,
  replacing twelve private-field pokes. (The `adapter._set_state` pokes
  remain: reaching a non-idle adapter state through the public protocol
  needs a hanging epoch, which is not a cheaper arrangement.)
