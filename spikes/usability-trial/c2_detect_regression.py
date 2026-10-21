"""Attempt (c2): replay the recorded golden transcript against a regressed app."""

import sys

sys.argv = [sys.argv[0], "menu_app_regressed.py"]
src = open("c1_record_compare_replay.py").read().split("script = ")[0]
exec(src)
from termverify.comparator import render_report
from termverify.replay import replay_transcript

golden = open("menu.transcript.jsonl", "rb").read()
rep = replay_transcript(golden, make_adapter(), "run-regressed", SUBJECT)
print("equivalent:", rep.comparison.equivalent)
print(render_report(rep.comparison))
