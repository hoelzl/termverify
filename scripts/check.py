#!/usr/bin/env python3
"""Run the repository quality gates — run this script, do not copy its list.

Usage:
    uv --no-config run python scripts/check.py           # before a commit
    uv --no-config run python scripts/check.py --full    # before a push
    uv --no-config run python scripts/check.py --list    # print, don't run

The default runs the pre-commit hooks over all files. ``--full`` adds what
the pre-push stage and CI gate on: the type check, the distribution build,
and the test suite with the coverage ratchet. Run
``uv --no-config sync --all-groups --locked`` first in a fresh checkout or
worktree; syncing is not part of the gate because it would replace the
interpreter that runs this script.

The command list lives here, in code that runs, so prose elsewhere names
this script instead of repeating it (issue #322). The first failing command
stops the run; rerun it alone to see its full output.
"""

from __future__ import annotations

import argparse
import subprocess
from collections.abc import Callable, Sequence

Command = tuple[str, ...]
Runner = Callable[[Sequence[str]], int]

QUICK: tuple[Command, ...] = (
    ("uv", "--no-config", "run", "pre-commit", "run", "--all-files"),
)

FULL_EXTRA: tuple[Command, ...] = (
    ("uv", "--no-config", "run", "mypy", "src", "tests", "scripts"),
    ("uv", "--no-config", "build"),
    ("uv", "--no-config", "run", "pytest", "--cov", "--cov-report=term-missing"),
)


def gate_commands(*, full: bool) -> tuple[Command, ...]:
    """Return the gate commands in execution order, cheapest first."""
    return QUICK + FULL_EXTRA if full else QUICK


def _subprocess_runner(command: Sequence[str]) -> int:
    return subprocess.call(list(command))


def run_gates(commands: Sequence[Command], runner: Runner) -> int:
    """Run *commands* in order and return the first nonzero status."""
    for command in commands:
        rendered = " ".join(command)
        print(f"$ {rendered}", flush=True)
        status = runner(command)
        if status != 0:
            print(f"check failed: `{rendered}` exited with {status}", flush=True)
            return status
    return 0


def main(argv: Sequence[str] | None = None, runner: Runner | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the repository quality gates.")
    parser.add_argument(
        "--full", action="store_true", help="also run types, build, and tests"
    )
    parser.add_argument(
        "--list", action="store_true", help="print the commands without running"
    )
    args = parser.parse_args(argv)
    commands = gate_commands(full=args.full)
    if args.list:
        print("\n".join(" ".join(command) for command in commands))
        return 0
    return run_gates(commands, runner or _subprocess_runner)


if __name__ == "__main__":
    raise SystemExit(main())
