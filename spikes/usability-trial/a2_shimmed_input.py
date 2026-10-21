"""Attempt (a), take 2: same program, wrapped in a marker-emitting shim."""

import os
import sys

from termverify import (
    ClockConfiguration,
    FilesystemConfiguration,
    ManualTime,
    NetworkConfiguration,
    RunConfiguration,
    TerminalConfiguration,
    TextInput,
)
from termverify.cooperation import CooperationConstraintPorts
from termverify.terminal import ConptyBinding, TerminalAdapter

config = RunConfiguration(
    seed=1,
    clock=ClockConfiguration(initial_ms=0),
    locale="en-US",
    timezone="UTC",
    terminal=TerminalConfiguration(columns=80, rows=24, capabilities=()),
    filesystem=FilesystemConfiguration(root_id="ws"),
    network=NetworkConfiguration(mode="deny"),
)
adapter = TerminalAdapter(
    [sys.executable, os.path.abspath("tv_shim.py"), os.path.abspath("greet.py")],
    binding=ConptyBinding(),
    constraint_ports=CooperationConstraintPorts({"ws": os.path.abspath("ws")}),
    abort_deadline_ms=10_000,
)
T0 = ManualTime(0)
start = adapter.start("run-1", config)
print("start:", type(start).__name__)


def show(res):
    print(type(res).__name__)
    obs = getattr(res, "observation", None)
    if obs and obs.frame:
        print("\n".join(l.rstrip() for l in obs.frame.lines if l.strip()))
    if hasattr(res, "outcome"):
        print("outcome:", res.outcome)
    if hasattr(res, "code"):
        print("failure:", res.code, res.message, res.details)


show(start)
r = adapter.dispatch(TextInput(T0, "Alice\r"))
show(r)
r = adapter.dispatch(TextInput(T0, "42\r"))
show(r)
