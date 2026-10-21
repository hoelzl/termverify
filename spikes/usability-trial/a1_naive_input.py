"""Attempt (a): drive an ordinary line-oriented program through ConPTY."""

import os
import sys
import time

from termverify import (
    ClockConfiguration,
    FilesystemConfiguration,
    NetworkConfiguration,
    RunConfiguration,
    TerminalConfiguration,
)
from termverify.cooperation import CooperationConstraintPorts
from termverify.terminal import ConptyBinding, TerminalAdapter

WS = os.path.abspath("ws")
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
    [sys.executable, "-c", "print('hello ' + input('name? '))"],
    binding=ConptyBinding(),
    constraint_ports=CooperationConstraintPorts({"ws": WS}),
    abort_deadline_ms=8_000,
)
t0 = time.monotonic()
start = adapter.start("run-1", config)
print(type(start).__name__, round(time.monotonic() - t0, 1), "s")
print(start)
