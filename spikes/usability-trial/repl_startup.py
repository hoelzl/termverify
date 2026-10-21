# PYTHONSTARTUP hack: make every REPL prompt carry a fresh readiness marker.
import itertools
import sys

_n = itertools.count()


class _MarkedPrompt:
    def __init__(self, p):
        self.p = p

    def __str__(self):
        return f"<<termverify.ready:{next(_n)}>>\n{self.p}"


sys.ps1 = _MarkedPrompt(">>> ")
sys.ps2 = _MarkedPrompt("... ")
