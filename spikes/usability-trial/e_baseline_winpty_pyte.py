"""Baseline: same tasks with pywinpty + pyte (no subject cooperation needed)."""

import sys
import time

import pyte
from winpty import PtyProcess


class Term:
    def __init__(self, argv, cols=80, rows=24):
        self.p = PtyProcess.spawn(argv, dimensions=(rows, cols))
        self.screen = pyte.Screen(cols, rows)
        self.stream = pyte.Stream(self.screen)

    def text(self):
        return "\n".join(l.rstrip() for l in self.screen.display)

    def expect(self, needle, timeout=10):
        end = time.monotonic() + timeout
        while needle not in self.text():
            if time.monotonic() > end:
                raise TimeoutError(f"{needle!r} not on screen:\n{self.text()}")
            try:
                self.stream.feed(self.p.read(4096))
            except EOFError:
                raise AssertionError(f"exited before {needle!r}:\n{self.text()}")
        return self.text()

    def send(self, s):
        self.p.write(s)


# (a) unmodified line-oriented program
t = Term([sys.executable, "greet.py"])
t.expect("name?")
t.send("Alice\r")
t.expect("hello Alice")
t.send("42\r")
t.expect("Alice is 42")
print("(a) ok")
# (b) unmodified Python REPL: multi-line def, ArrowUp history, Ctrl-C interrupt
t = Term([sys.executable, "-q"])
t.expect(">>>")
t.send("def f():\r")
t.expect("...")
t.send("  return 7\r\r")
t.send("f()*6\r")
t.expect("42")
t.send("\x1b[A")
t.expect(">>> f()*6")
t.send("\r")
t.send("import time; time.sleep(30)\r")
time.sleep(0.5)
t.send("\x03")
t.expect("KeyboardInterrupt")
print("(b) ok")
t.p.terminate(force=True)
