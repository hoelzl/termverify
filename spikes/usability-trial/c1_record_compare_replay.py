"""Attempt (c): record the menu-TUI run, re-record, compare, replay."""

import os
import sys

from termverify import (
    ClockConfiguration,
    FilesystemConfiguration,
    KeyInput,
    ManualTime,
    NetworkConfiguration,
    RunConfiguration,
    Stop,
    TerminalConfiguration,
)
from termverify.comparator import compare_transcripts, render_report
from termverify.cooperation import CooperationConstraintPorts
from termverify.recorder import run_scripted
from termverify.replay import replay_transcript
from termverify.terminal import ConptyBinding, TerminalAdapter

APP = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "menu_app.py")
config = RunConfiguration(
    seed=1,
    clock=ClockConfiguration(initial_ms=0),
    locale="en-US",
    timezone="UTC",
    terminal=TerminalConfiguration(columns=40, rows=24, capabilities=()),
    filesystem=FilesystemConfiguration(root_id="ws"),
    network=NetworkConfiguration(mode="deny"),
)


def make_adapter():  # adapters are single-use: one per run
    return TerminalAdapter(
        [sys.executable, APP],
        binding=ConptyBinding(),
        constraint_ports=CooperationConstraintPorts({"ws": os.path.abspath("ws")}),
        abort_deadline_ms=6000,
    )


SUBJECT = (
    {"name": "menu_app"}
    if "--naive-subject" in sys.argv
    else {
        "format": "termverify.replay-subject/v1",
        "application": {"id": "menu-app", "version": "1", "build": "dev"},
        "fixture": {"id": "menu", "version": "1"},
        "adapter": {"id": "termverify.terminal", "version": "1"},
        "normalizer": {"id": "termverify.vt", "version": "1"},
        "state_schema": {"id": "terminal-dimensions", "version": "1"},
    }
)
T0 = ManualTime(0)
script = (KeyInput(T0, ("ArrowDown",)), KeyInput(T0, ("Enter",)), Stop(T0))
run1 = run_scripted(make_adapter(), "run-1", config, SUBJECT, script)
print(
    "run1:",
    type(run1.result).__name__,
    run1.result.outcome,
    len(run1.transcript),
    "bytes",
)
with open("menu.transcript.jsonl", "wb") as f:
    f.write(run1.transcript)
run2 = run_scripted(make_adapter(), "run-2", config, SUBJECT, script)
v = compare_transcripts(run1.transcript, run2.transcript)
print("repeat-run compare:", v.equivalent if hasattr(v, "equivalent") else v.verdict)
print(render_report(v)[:1500])
rep = replay_transcript(run1.transcript, make_adapter(), "run-3", SUBJECT)
print(
    "replay:", type(rep).__name__, rep.comparison.equivalent, rep.subject_matches_source
)
print(render_report(rep.comparison)[:600])
