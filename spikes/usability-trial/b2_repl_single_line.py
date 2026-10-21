"""Attempt (b2): single-line statements, Ctrl-C, ArrowUp: drive the Python REPL (basic REPL + PYTHONSTARTUP marker hack)."""

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
    TextInput,
)
from termverify.cooperation import CooperationConstraintPorts
from termverify.terminal import ConptyBinding, TerminalAdapter

# No API to pass env to the subject: must mutate the host's own environment.
os.environ["PYTHONSTARTUP"] = os.path.abspath("repl_startup.py")
os.environ["PYTHON_BASIC_REPL"] = "1"
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
    [sys.executable, "-q"],
    binding=ConptyBinding(),
    constraint_ports=CooperationConstraintPorts({"ws": os.path.abspath("ws")}),
    abort_deadline_ms=int(sys.argv[1]) if len(sys.argv) > 1 else 6000,
)
T0 = ManualTime(0)


def show(label, res):
    print(f"--- {label}: {type(res).__name__}")
    obs = getattr(res, "observation", None)
    if obs and obs.frame:
        print("\n".join(l.rstrip() for l in obs.frame.lines if l.strip()))
    if hasattr(res, "code"):
        print("failure:", res.code, res.message, dict(res.details))
    if hasattr(res, "outcome"):
        print("outcome:", res.outcome)
    return res


show("start", adapter.start("run-1", config))
show("1+1", adapter.dispatch(TextInput(T0, "1+1\r")))
show("lambda", adapter.dispatch(TextInput(T0, "f = lambda: 7\r")))
show("call", adapter.dispatch(TextInput(T0, "f()*6\r")))
show("Ctrl-C at idle prompt", adapter.dispatch(KeyInput(T0, ("Control", "c"))))
show("ArrowUp (history)", adapter.dispatch(KeyInput(T0, ("ArrowUp",))))
