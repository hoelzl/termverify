---
type: review
status: findings
date: 2026-10-20
summary: 'Whole-project viability review: termverify cannot yet test ordinary programs; recommends a freeze, a time-boxed trial on tui-test, and a decision gate.'
---

# Viability review — 2026-10-20

- **Reviewed SHA:** `3de88adf4178c075f194df3fa2a64aa71bf52840` (`main` after
  the documentation overhaul, #323–#331).
- **Question:** can termverify be made useful for developing real programs,
  or should the project be abandoned?
- **Method:** three independent passes, each by a fresh-context agent:
  1. a hands-on usability trial on Windows 11 through the public API only,
     installed editable into a scratch virtual environment (scripts in
     `spikes/usability-trial/`);
  2. an analysis of the git history, the merged PRs (#1–#306), the open
     issues, and the active handovers;
  3. a survey of existing terminal-testing and agent-terminal tools as of
     October 2026.

  Key claims were spot-checked directly: the readiness-marker prefix in
  `src/termverify/terminal.py`, the marker emission in Drei's own terminal
  module, and the tui-test release and its PyPI wheels.

## Verdict

Do not continue building termverify as a general-purpose library in its
current form. Freeze it at what Drei needs, run a time-boxed trial of the one
capability no existing tool offers on top of an existing terminal driver, and
archive the project if that trial does not clearly pay off.

## Findings

### F1 — Ordinary programs cannot be tested

The terminal adapter requires the subject to print a fresh
`<<termverify.ready:N>>` token after start and after every input
(`READINESS_MARKER_PREFIX_DEFAULT` in `src/termverify/terminal.py`). In the
trial:

- an unmodified `input()` program failed to start (`StartFailed`: abort
  deadline expired before quiescence evidence was observed); a 15-line shim
  that patches `builtins.input` made it work;
- the Python REPL was drivable only through a `PYTHONSTARTUP` hack putting the
  marker into `sys.ps1`; multi-line definitions (the repeated `ps2` prompt
  repeats the token), arrow-key history (no new prompt, so no marker), and
  interrupting a running command with Ctrl-C all failed;
- TUI frameworks that do not let the author inject markers (Textual,
  prompt_toolkit) cannot be driven at all.

A full-screen app written to the contract worked well: arrow keys, Enter, and
Ctrl-C bytes were delivered, screen assertions were easy, and a pytest test
ran in 0.1–0.2 s.

### F2 — The user-facing layer is missing

- No quickstart, no runnable example, no `examples/` directory. The marker
  contract is stated only in the middle of
  `docs/developer-guide/conpty-adapter.md`. About 40 minutes to a first test.
- A first test requires a `RunConfiguration` with all seven constraints,
  `CooperationConstraintPorts` with a root mapping, `ManualTime` on every
  input, single-use adapters, and eight result types.
- No API to wait for text, to read the screen between epochs, to send keys
  that are not expected to produce a marker, to interrupt an epoch in
  progress, or to set the subject's environment or working directory.
- The subject's working directory is silently the sandbox root; a relative
  script path produced `StartTerminated` with no error text.
- The recorder and replay need a six-level subject selector that no
  user-facing document shows.
- The everyday path (terminal adapter, cooperation ports, recorder,
  comparator, replay) is outside the curated top-level package surface.

For comparison, pywinpty with pyte and a 15-line `expect` helper drove the
unmodified `input()` program, multi-line REPL definitions, and history in
about half the code, without touching the subject.

### F3 — Record, compare, and replay work, but transcripts do not travel

`run_scripted`, `compare_transcripts`, and `replay_transcript` worked; a
regression produced a clear report naming the differing frame lines.
Transcripts include the console title, which is the absolute interpreter
path, so the same app run from another interpreter path compares divergent.
The comparator has no normalizers by design, and teardown bytes on natural
exit vary between runs. Golden transcripts are therefore not portable across
machines or CI checkouts.

### F4 — Effort went to hardening and process, not capability

- **Timeline:** first commit 2026-07-14; last substantive merge #306 on
  2026-08-14; nothing then until the documentation overhaul.
- **Front-loaded features:** 84% of the feature PRs landed in the first six
  days. The last new user-visible capabilities were recorder, comparator, and
  replay (2026-07-19, #150/#152/#154) and the JSONL transport (2026-07-21,
  #177). The POSIX binding (#272, 2026-08-01) shipped explicitly unproven end
  to end.
- **Effort by category** (168 merged PRs, classified by title, bodies
  spot-checked):

  | Bucket | Share of PRs |
  |---|---|
  | Governance and process (handovers, reconciles, review records, ADRs, release, coverage ratchets) | 27% |
  | Features and capabilities | 15% |
  | Run-time fixes (teardown, end-of-stream, UTF-8 tails, deadlines) | 13% |
  | Protocol-validator strictness fixes | 13% |
  | Dependency bumps | 9% |
  | Protocol, specification, and schema design | 8% |
  | Docs, tests only, refactors, CI | 15% |

- **Size at #306:** `src/` 14.7k lines (about 9.9k code lines); `tests/`
  30.8k; `docs/agent/` 11.2k. The 0.1.1 changelog has 23 lines under "Added"
  and 518 under "Fixed".
- **The last 20 PRs before the overhaul** (#265–#306) added one capability,
  the unproven POSIX binding. The rest were handover churn, POSIX
  end-of-stream, teardown, and UTF-8 edge cases, loosening flaky ConPTY test
  oracles, and dependency bumps.

### F5 — The prescribed vertical slice was never built

The 2026-07-24 review (finding P6, strategic recommendation 10) prescribed a
vertical slice before further horizontal specification: a POSIX adapter plus
one end-to-end example. The active vertical handover (issue #204, opened
2026-07-24) has three completion criteria:

1. a POSIX adapter proven end to end in CI;
2. an `examples/` walkthrough that runs run → record → replay → compare →
   report in CI;
3. a recorded reassessment.

None is met. Phases 3–5 (#269, #270, #271) are still to do, because a chain
of evidence-first prerequisites (#274, #278, #279, #281, #283, #284) was
scheduled ahead of the first real POSIX run and consumed 2026-08-02 to
2026-08-14.

### F6 — Review loops fed themselves

- Each fix PR received its own adversarial review, and each review spawned
  residue issues: #274 from #272; #277–#279 from #274; #282–#284 from #280;
  #213 and #217 from #211 and #214.
- Several PRs ran four to six rounds (#227, #243, #256, #303).
- The most-churned files are the pre-release handover (49 commits),
  `transcript.py` (33), `_conpty.py` (32), and `protocol.md` (32).

### F7 — There is one real consumer

`hoelzl/drei` depends on `termverify>=0.1.1` and runs 22 ConPTY end-to-end
tests (about 1.3k lines) that drive its shipped editor through the terminal
adapter. It satisfies the marker contract by emitting markers from its own
terminal module, and it does not use the recorder, comparator, or replay.
GlyphWright has only a direct-adapter spike. PyPI downloads were about 92 in
the last month, mostly CI and mirrors.

### F8 — Existing tools now cover the terminal half

- **Microsoft tui-test** is the closest overlap.
  - Rewritten in Rust; 0.1.0 released 2026-10-03; actively pushed.
  - The `tui-test` PyPI package ships Windows, Linux, and macOS wheels
    (verified).
  - Per the survey: it drives programs through a real terminal (ConPTY on
    Windows), offers Playwright-style locators and snapshots, and writes
    failure traces its documentation directs agents to read.
- **termlens** (Rust, very active; partial Windows support) and a dozen young
  agent-terminal MCP servers cover much of the rest.
- **What no surveyed tool offers:**
  - a recorded determinism contract (clock, seed, locale, size, filesystem
    and network policy);
  - replay that re-drives the program rather than playing back recorded
    output;
  - one transcript shared by a semantic adapter and real-terminal runs, which
    would enable direct-versus-terminal differential runs and property testing
    over whole runs;
  - baselines that only a human may approve.

  termverify has some machinery for each, but all four remain planned scope
  in `docs/knowledge/product-vision.md`.

## Recommendation

1. **Freeze termverify.** Close or defer the POSIX vertical (#204, #269,
   #270, #271) and the open hardening issues. Do only what Drei needs to keep
   working. Building the vertical as planned would leave the marker contract
   in place, so it would not make the library usable for real programs.
2. **Adopt tui-test for real work.** Port two or three of Drei's
   end-to-end tests to it first; that quickly settles whether the Python
   binding works well on Windows.
3. **Time-box a trial of the unique part, two or three days.** Build a thin
   layer on tui-test that records the determinism inputs, re-drives a
   recorded script, compares meaningful screen states with normalization of
   noise such as titles and paths, and requires human approval of baseline
   changes. Optionally add a Hypothesis state machine that generates key
   sequences and shrinks failing runs; no surveyed tool does this. Keep only
   `termverify.transcript`, `termverify.comparator`, and
   `termverify.evidence`; drop the own terminal binding, VT normalizer, and
   marker requirement.
4. **Decision gate.** Continue only if the trial catches a real Drei bug or
   produces evidence that tui-test snapshots alone do not. Otherwise archive
   the project and keep tui-test.

If the project continues, change how it is run:

- start from one example that runs end to end;
- cap reviews at one or two rounds;
- keep governance records out of a prototype;
- let Drei's needs drive the roadmap.

## Caveats

- tui-test is two weeks past 0.1.0, so it is young. Its Python binding was
  not exercised in this review; only the published wheels were checked.
- Some survey details were not independently verified: termlens's Windows
  coverage, and how widely the agent-terminal MCP servers are used.
- The PR classification in F4 was done by hand from titles, with bodies
  spot-checked; treat the shares as approximate.
- The usability-trial scripts behind F1–F3 are kept, as they were run, in
  [`spikes/usability-trial/`](../../../spikes/usability-trial/README.md).
