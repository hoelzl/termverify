"""Linux integration evidence for the POSIX terminal adapter boundary."""

from __future__ import annotations

import sys

import pytest

from termverify.adapter import (
    ExitStatus,
    ManualTime,
    RunFailed,
    Started,
    TerminalResult,
    TextInput,
)
from termverify.terminal import (
    READINESS_MARKER_PREFIX_DEFAULT,
    READINESS_MARKER_TERMINATOR,
    PosixPtyBinding,
    TerminalAdapter,
)
from tests.test_terminal_epochs import _configuration, _EnforcingPorts

_LINUX_ONLY = pytest.mark.skipif(
    not sys.platform.startswith("linux"),
    reason="POSIX terminal integration evidence is claimed on Linux only",
)


@_LINUX_ONLY
def test_eos_normalizer_rejection_retains_the_real_posix_exit() -> None:
    """EOS flush rejects only after the binding has captured exit code 7."""
    marker = READINESS_MARKER_PREFIX_DEFAULT + "1" + READINESS_MARKER_TERMINATOR + "\n"
    startup = "ready\n" + marker
    script = f"""\
import os
import sys

os.write(1, {startup!r}.encode())
sys.stdin.buffer.readline()
os.write(1, b"\\x1b[3\\xe2")
raise SystemExit(7)
"""
    adapter = TerminalAdapter(
        (sys.executable, "-I", "-u", "-c", script),
        binding=PosixPtyBinding(),
        constraint_ports=_EnforcingPorts(),
        abort_deadline_ms=60_000,
    )

    started = adapter.start("run-posix-normalizer-exit", _configuration())
    assert type(started) is Started

    result = adapter.dispatch(TextInput(ManualTime(0), "quit\n"))

    assert type(result) is TerminalResult
    assert type(result.outcome) is RunFailed
    assert result.outcome.failure.details == {
        "during": "normalize",
        "reason": "malformed control sequence",
        "sequence": "3�",
    }
    observation = result.observation
    assert observation is not None
    assert observation.process is not None
    assert observation.process.exit == ExitStatus("code", 7)
