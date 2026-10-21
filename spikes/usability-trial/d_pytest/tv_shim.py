"""Cooperation shim: run a Python script, emitting a termverify readiness
marker every time the script blocks in input().  Needed because termverify
cannot wait for arbitrary output (only for its own marker)."""

import builtins
import itertools
import runpy
import sys

_count = itertools.count()
_orig_input = builtins.input


def _marked_input(prompt=""):
    sys.stdout.write(prompt + "\n")
    sys.stdout.write(f"<<termverify.ready:{next(_count)}>>\n")
    sys.stdout.flush()
    return _orig_input()


builtins.input = _marked_input
target = sys.argv[1]
sys.argv = sys.argv[1:]
runpy.run_path(target, run_name="__main__")
