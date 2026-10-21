"""Attempt (b5): drive a cooperative full-screen menu TUI with arrows/Enter/Ctrl-C."""

import os
import sys

from termverify import (
    ClockConfiguration,
    FilesystemConfiguration,
    KeyInput,
    ManualTime,
    NetworkConfiguration,
    RunConfiguration,
    TerminalConfiguration,
)
from termverify.cooperation import CooperationConstraintPorts
from termverify.terminal import ConptyBinding, TerminalAdapter

config = RunConfiguration(
    seed=1,
    clock=ClockConfiguration(initial_ms=0),
    locale="en-US",
    timezone="UTC",
    terminal=TerminalConfiguration(columns=40, rows=24, capabilities=()),
    filesystem=FilesystemConfiguration(root_id="ws"),
    network=NetworkConfiguration(mode="deny"),
)
adapter = TerminalAdapter(
    [sys.executable, os.path.abspath("menu_app.py")],
    binding=ConptyBinding(),
    constraint_ports=CooperationConstraintPorts({"ws": os.path.abspath("ws")}),
    abort_deadline_ms=6000,
)
T0 = ManualTime(0)


def show(label, res):
    print(f"--- {label}: {type(res).__name__}")
    obs = getattr(res, "observation", None)
    if obs and obs.frame:
        print("\n".join(l.rstrip() for l in obs.frame.lines if l.strip()))
    if hasattr(res, "outcome"):
        print("outcome:", res.outcome)
    return res


show("start", adapter.start("run-1", config))
show("down", adapter.dispatch(KeyInput(T0, ("ArrowDown",))))
show("down", adapter.dispatch(KeyInput(T0, ("ArrowDown",))))
show("up", adapter.dispatch(KeyInput(T0, ("ArrowUp",))))
r = show("enter", adapter.dispatch(KeyInput(T0, ("Enter",))))
assert any("Selected: Banana" in l for l in r.observation.frame.lines)
show("ctrl-c", adapter.dispatch(KeyInput(T0, ("Control", "c"))))
