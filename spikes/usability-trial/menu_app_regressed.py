"""A tiny full-screen menu TUI written to termverify's cooperation contract:
raw console input, ANSI full-screen redraw, readiness marker after every key."""

import ctypes
import os
import sys

ITEMS = ["Apple", "Bananas", "Cherry", "Durian"]
k32 = ctypes.windll.kernel32
h = k32.GetStdHandle(-10)
m = ctypes.c_uint32()
k32.GetConsoleMode(h, ctypes.byref(m))
k32.SetConsoleMode(h, (m.value & ~0x7) | 0x200)  # raw + VT input (from test fixture)
n = 0


def draw(sel, status=""):
    global n
    n += 1
    out = ["\x1b[?1049h\x1b[H\x1b[2J", "+--------------+\r\n"]
    for i, it in enumerate(ITEMS):
        out.append(("|> " if i == sel else "|  ") + it.ljust(11) + " |\r\n")
    out.append("+--------------+\r\n" + status + "\r\n")
    out.append(f"\x1b[22;1H<<termverify.ready:{n}>>\r\n")
    sys.stdout.write("".join(out))
    sys.stdout.flush()


def key():
    b = os.read(0, 1)
    if b == b"\x1b":
        b += os.read(0, 1)
        if b.endswith(b"["):
            b += os.read(0, 1)
    return b


sel = 0
draw(sel)
while True:
    k = key()
    if k == b"\x03":
        sys.stdout.write("\x1b[?1049l")
        sys.stdout.flush()
        sys.exit(130)
    elif k == b"\x1b[A":
        sel = (sel - 1) % len(ITEMS)
        draw(sel)
    elif k == b"\x1b[B":
        sel = (sel + 1) % len(ITEMS)
        draw(sel)
    elif k in (b"\r", b"\n"):
        draw(sel, f"Selected: {ITEMS[sel]}")
    else:
        draw(sel, f"unknown key {k!r}")
