"""Attempt (c3): replay the golden transcript with the *same* app but a different
python.exe path (simulates another machine / CI checkout location)."""

import os
import sys

src = open("c1_record_compare_replay.py").read().split("script = ")[0]
exec(src)
from termverify.terminal import ConptyBinding, TerminalAdapter

base_py = os.path.join(sys.base_prefix, "python.exe")
adapter = TerminalAdapter(
    [base_py, APP],
    binding=ConptyBinding(),
    constraint_ports=CooperationConstraintPorts({"ws": os.path.abspath("ws")}),
    abort_deadline_ms=6000,
)
rep = replay_transcript(
    open("menu.transcript.jsonl", "rb").read(), adapter, "run-other-host", SUBJECT
)
print("equivalent:", rep.comparison.equivalent)
print(render_report(rep.comparison)[:700])
