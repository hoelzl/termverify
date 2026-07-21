# Issue #173 Slice 1 — In-Progress Implementation Handover

## Handover metadata

- **Status:** draft — bounded session-continuation record for the in-progress,
  uncommitted implementation of issue #173 (slice 1 of the accepted
  [JSONL subprocess control transport design](../design/jsonl-control-transport.md)).
  This is not a new initiative handover; the active initiative record remains
  the [Pre-release boundary hardening handover](pre-release-boundary-hardening-handover.md).
- **Owner:** project maintainer
- **Created:** 2026-07-20
- **Review required:** yes — the slice touches a new public protocol surface
  (`termverify.control/v1`) and must pass candidate-bound adversarial review
  before merge, per the standing slice workflow.
- **Successor:** none

## Scope and non-goals

Slice 1 scope per the design's "Slices and sequencing" (issue #173):

- The `termverify.control/v1` message model and its strict codec
  (`src/termverify/control.py`).
- The `JsonlAdapter` (`src/termverify/jsonl.py`) implementing the full
  `termverify.adapter.Adapter` contract against an injected
  `JsonlBindingPort` (fake-child-tested, no real subprocess).
- The protocol knowledge page `docs/knowledge/control-protocol.md`.

Non-goals (explicitly out of this slice): slice 2 real-subprocess integration
evidence (its own follow-up issue), any change to the frozen v1 protocol
registries, and the native `JsonlBinding`/`JsonlChild` spawn implementation if
the design defers it.

## Verified current state

Worktree: `C:\Users\tc\Programming\Python\Worktrees\termverify\issue-173`,
branch `feat/issue-173-control-v1-slice1`, rebased onto merged main at
`1455c2b` (PR #174, the channel-tagged delivery amendment docs).

**Second session (2026-07-20, post-#174) — committed green state.** One
commit holds the amendment implementation plus the slice-1 code (control
codec, JsonlAdapter, tests). Key facts a successor must know:

- The slice-1 transport code (`src/termverify/control.py`,
  `src/termverify/jsonl.py`, `tests/test_control_codec.py`,
  `tests/test_jsonl_adapter.py`) had **never been committed to main** — it
  existed only in this worktree, so this commit is its first entry into git.
- Amendment implemented per the accepted design
  (`docs/agent/design/channel-tagged-delivery-records.md`, status now
  "accepted"): channel-discriminated `DeliveryRecord` with compat
  constructor, `_COMPAT_RULES` legacy normalization at wire ingest in
  `transcript.py`, channel dispatch in `_validate_capability_tier`,
  per-channel redaction in `evidence.py`, tagged emission in `recorder.py`.
- `session.hello` carries a required validated `at_ms` member in the control
  codec (divergence between the adapter and codec found and fixed).
- `JsonlAdapter._enforce_terminal` records `DeliveryRecord.hello_config()`
  (the parked defect from the first session is fixed).
- Stale test fakes repaired: `ui.cursor` is required by the codec, exit
  records use `{kind, value}`, `run.finished` has no `forced` member, and
  the spawn test asserts the real evidence-driven overlay.
- Full suite at handover: **1479 passed, 1 skipped** (Windows).

Remaining work (successor's checklist):

1. Decide schema posture: the packaged `v1.schema.json` is a shallow
   envelope aid with no `capability.result.delivery` coverage — document the
   no-change decision (or add anyOf coverage) in the PR.
2. Update `docs/knowledge/control-protocol.md` channel wording if stale.
3. Run full pre-commit gates (coverage, ruff, mypy, pre-commit, build).
4. Changelog fragment (conflict-free fragment scheme, PR #167).
5. Push and open a draft PR titled `Refs #173`.
6. Candidate-bound adversarial review, then merge.

Gate status at first-session handover (superseded by the above):

| Artifact | ruff check | ruff format | mypy | pytest |
| --- | --- | --- | --- | --- |
| `src/termverify/control.py` | pass | pass | pass | 13/13 in `test_control_codec.py` |
| `src/termverify/jsonl.py` | pass | pass | pass | partial (see below) |

`tests/test_jsonl_adapter.py`: 4 passing, 10 failing at last full run. **Every
observed failure was test-scaffolding shape, not adapter behavior**: the
`_config()` helper built `RunConfiguration` with wrong kwargs (`seed` as str,
`initial_ms`/`filesystem_mode`/`network_mode` flat kwargs, missing
`capabilities`). The final patch applied before this handover rewrote
`_config()` to the real signature — `seed: int`, `ClockConfiguration(initial_ms=0)`,
`FilesystemConfiguration(root_id="root")`, `NetworkConfiguration(mode="deny")`,
`TerminalConfiguration(columns=80, rows=24, capabilities=())` — and added the
`ClockConfiguration`, `FilesystemConfiguration`, `NetworkConfiguration`
imports. **That patch was applied but the test file was not re-run.** First
action on resume: `uv --no-config run pytest tests/test_jsonl_adapter.py -q`
and fix any remaining scaffolding/adapter mismatches.

## Real defects found and fixed by RED tests

1. **Codec kind vocabulary omitted `session.hello`** — `_INPUT_KINDS` in
   `control.py` lacked `session.hello`, so every legal handshake message was
   rejected as "envelope kind is outside the v1 vocabulary". Fixed by adding
   it; `input.stop` (not `run.stop`) is the correct stop kind per the protocol
   doc.
2. **Test asserted `x-` envelope members are rejected** — inverted relative to
   the protocol: `x-` prefixed members are allowed extensions; only non-`x-`
   unknown members are reserved/rejected. Test corrected.
3. **`run_id` identifier grammar is lowercase-only**
   (`abcdefghijklmnopqrstuvwxyz0123456789._-`); tests use
   `01hgw0mg5e6w1a6b0rzg3zqk0r`.

## Material decisions and unresolved decision gates

1. **Enforcement tier: `delivered`, not `declared`** — the frozen
   `termverify.enforcement-tier/v1` registry is `os | constructive | delivered`;
   `declared` does not exist. The initial jsonl.py draft used `declared` for
   handshake-declared terminal dimensions; mypy rejected it and the code now
   states `delivered` for all seven constraints (exact recorded values
   delivered; honoring is subject cooperation). **Open consistency gate:**
   `docs/knowledge/control-protocol.md` was written earlier with the
   `declared` framing in mind — its authorization-matrix row and any tier
   prose must be checked and reconciled to `delivered` before the PR.
2. **`constraint_ports` is required, no silent default** — `JsonlAdapter`
   refuses a missing `constraint_ports` argument (unlike `ConptyAdapter`,
   which defaults to `UnenforcedConstraintPorts`). Callers must declare
   enforcement posture explicitly. Tests use `UnenforcedConstraintPorts`
   explicitly.
3. **Codec `JsonValue` → contract `JsonInput` narrowing** is centralized in
   `_as_json_input()` in jsonl.py with a documented soundness argument; do not
   sprinkle ad-hoc casts elsewhere.

## Resume checklist (prioritized)

0. **OWNER DECISION GATE (2026-07-20, second session).** The slice is parked
   on a protocol-semantics question: a `delivered`-tier `TerminalReceipt` is
   unconstructable for handshake-delivered terminal constraints
   (`DeliveryRecord` requires ≥1 env var; terminal delivery is the
   `session.hello` config, not the spawn environment; frozen transcript/v1
   mirrors the requirement, so the recorder cannot consume the receipt).
   Full analysis + options posted as an issue #173 comment
   (`issuecomment-5022366679`). **Do not invent a resolution** — resume only
   after the owner picks option A (control/v1 tier-wording amendment +
   sentinel env marker), B (design amendment first), or C (new delivery
   shape). State below assumes no further code change until then.
1. Re-run `uv --no-config run pytest tests/test_jsonl_adapter.py -q`; fix
   remaining failures (expected: observation/frame payload shapes in the fake
   child's scripted replies, and exact `EpochCompleted`/`RunFinished` field
   assertions). Check failure messages against the adapter's actual parsing in
   `_run_epoch`/`_map_terminal` before editing.
2. Reconcile the `delivered` tier wording in
   `docs/knowledge/control-protocol.md` (finding 1 above).
3. Add slice tests for any uncovered branches needed by the coverage ratchet;
   then run the full gates from the worktree:
   `uv --no-config sync --all-groups --locked`,
   `uv --no-config run pytest --cov --cov-report=term-missing`,
   `uv --no-config run ruff check .`,
   `uv --no-config run ruff format --check .`,
   `uv --no-config run mypy src tests scripts`,
   `uv --no-config run pre-commit run --all-files`,
   `uv --no-config run pre-commit run --hook-stage pre-push --all-files`.
4. Write the changelog fragment (`changelog.d/` convention per the repo's
   fragment workflow), commit on `feat/issue-173-control-v1-slice1`, push,
   open the PR as **draft** with `Refs #173` (not closing), and request the
   candidate-bound adversarial review with the head SHA identified. Do not
   merge until review covers the exact candidate and CI on that head is green.

## Second-session progress (2026-07-20)

Scaffolding fixes applied (all test-shape, plus one real adapter defect):

- `_config()` locale `en_US.UTF-8` → `en-US` (BCP 47; `is_well_formed_language_tag`).
- All input events now wrap times in `ManualTime(...)`; key test uses the
  canonical `("Enter",)` chord (`("enter",)` is rejected by `is_key_chord`).
- `advance_clock` test uses `at_ms=ManualTime(0), delta_ms=100`; `stop` test
  uses `ManualTime(100)` (post-advance time).
- Tests use `CooperationConstraintPorts(filesystem_roots={"root": "."})`
  instead of `UnenforcedConstraintPorts` — the JSONL adapter refuses to
  declare enforcement its ports cannot provide, and unenforced ports return
  `ConstraintUnsupported` for every constraint.
- **Real defect fixed (RED→GREEN):** `session.hello` now carries `at_ms`
  (the design's required initial manual time; was absent).
- **Real defect fixed then REVERTED pending owner gate:** `_enforce_terminal`
  returned `tier="delivered"` without a `DeliveryRecord`, which
  `TerminalReceipt.__post_init__` rejects — see the owner gate above. The
  naive fix (`DeliveryRecord(env={})`) also fails (`DeliveryRecord` requires
  ≥1 env var). Current code state: the empty-env record variant is in place
  (tests still fail identically; the block is semantic, not mechanical).

Test status at park time: `test_control_codec.py` 13/13 pass;
`test_jsonl_adapter.py` 6 pass / 8 fail, every failure rooted in the
terminal-receipt gate above (start never reaches `idle`, so
dispatch/clock/stop tests fail downstream of the same cause).

## Risks and non-negotiables

- Protocol freeze is active (0.1.0 on PyPI): `termverify.control/v1` is a new
  protocol document and does not amend the frozen transcript/enforcement-tier
  registries; keep it that way.
- Do not weaken the strict codec (duplicate-member rejection, ceilings,
  canonical serialization) to make a test pass — fix the test instead.
- The deterministic core stays independent of ambient clock/terminal state;
  the watchdog and child I/O are the only injected ambient ports.
- All repo work stays in the dedicated worktree; the primary checkout remains
  the clean integration point.

## Transition criteria

- **Blocked:** if a semantic question about the v1 vocabulary or tier
  semantics arises that the design doc does not answer — escalate to the owner
  before inventing semantics.
- **Complete (this record):** slice 1 PR merged after candidate-bound review;
  this draft handover is then superseded by normal issue/PR state and may be
  removed or archived without a formal transition.
- **Superseded:** if the session's uncommitted work is abandoned and
  re-implemented from scratch, delete this file with the worktree.
