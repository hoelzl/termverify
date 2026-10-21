# Usability trial — 2026-10-20

## Question

Can a developer who reads only the user-facing documentation use termverify's
public API to test a real terminal program?

These are the scripts behind findings F1–F3 of the
[viability review](../../docs/agent/reviews/viability-review-2026-10-20.md).
They are kept as they were run, apart from `ruff format` and import sorting.
They are not tests of termverify, are not collected by the test suite, and
are not maintained.

## Scope

- **Host:** Windows 11, `ConptyBinding`, termverify at
  `3de88adf4178c075f194df3fa2a64aa71bf52840`, installed editable.
- **Rule:** public API only.
- **Not covered:** POSIX, and TUI frameworks that cannot emit readiness
  markers (Textual, prompt_toolkit).

## Running

Run every script from this directory, so that its relative paths resolve, with
the repository environment:

```text
mkdir ws
../../.venv/Scripts/python.exe b5_menu_tui.py
../../.venv/Scripts/python.exe -m pytest -p no:cacheprovider d_pytest
```

`ws/` is the sandbox root the scripts map, and `c1_record_compare_replay.py`
writes `menu.transcript.jsonl`, which carries absolute local paths;
`.gitignore` keeps both out of the repository.
Run `c1_record_compare_replay.py` before `c2_*` and `c3_*`, which replay its
transcript. `e_baseline_winpty_pyte.py` needs `pywinpty` and `pyte`, which are
not project dependencies.

## Scripts

| Script | Attempt | Outcome |
|---|---|---|
| `a1_naive_input.py` | An unmodified `input()` program (`greet.py`) | `StartFailed`: no readiness evidence |
| `a2_shimmed_input.py` | The same, through `tv_shim.py`, which patches `builtins.input` to print markers | Works |
| `b1_repl.py`, `b2_repl_single_line.py` | The Python REPL, with `repl_startup.py` putting the marker into `sys.ps1` | Single-line statements work; multi-line definitions fail |
| `b3_repl_interrupt.py` | Ctrl-C during `time.sleep(30)` | Fails: `dispatch` blocks until a marker arrives |
| `b4_repl_arrow.py` | ArrowUp history | Fails: no new prompt, so the deadline expires |
| `b5_menu_tui.py`, `b6_menu_noclear.py` | A full-screen menu written to the contract (`menu_app.py`, `menu_app_noclear.py`) | Works, including cursor-addressed redraw |
| `c1_record_compare_replay.py` | Record, compare, and replay a menu run | Works; repeat runs are equivalent |
| `c2_detect_regression.py` | Replay against `menu_app_regressed.py` | Clear report of the differing frame lines |
| `c3_portability.py` | Replay with another `python.exe` path | Divergent: the console title carries the path |
| `d_pytest/test_menu.py` | Use from pytest | Two pass; the third fails on purpose to show the failure a user sees |
| `e_baseline_winpty_pyte.py` | The same tasks with pywinpty and pyte | Unmodified subjects, about half the code |
