"""Attempt (d): termverify from pytest. ~25 lines of harness boilerplate."""

import sys
from pathlib import Path

import pytest
from termverify import (
    ClockConfiguration,
    EpochCompleted,
    ExitStatus,
    FilesystemConfiguration,
    KeyInput,
    ManualTime,
    NetworkConfiguration,
    RunConfiguration,
    RunFinished,
    Started,
    Stop,
    TerminalConfiguration,
    TextInput,
)
from termverify.cooperation import CooperationConstraintPorts
from termverify.terminal import ConptyBinding, TerminalAdapter

HERE = Path(__file__).parent
T0 = ManualTime(0)


@pytest.fixture
def spawn(tmp_path):
    adapters = []

    def _spawn(*argv, cols=40, rows=24):
        cfg = RunConfiguration(
            seed=1,
            clock=ClockConfiguration(initial_ms=0),
            locale="en-US",
            timezone="UTC",
            terminal=TerminalConfiguration(columns=cols, rows=rows, capabilities=()),
            filesystem=FilesystemConfiguration(root_id="ws"),
            network=NetworkConfiguration(mode="deny"),
        )
        a = TerminalAdapter(
            [sys.executable, *argv],
            binding=ConptyBinding(),
            constraint_ports=CooperationConstraintPorts({"ws": str(tmp_path)}),
            abort_deadline_ms=8000,
        )
        adapters.append(a)
        start = a.start("run", cfg)
        assert type(start) is Started, start
        return a, start

    yield _spawn
    for a in adapters:  # no context manager / close(); best effort
        try:
            a.stop(Stop(T0))
        except RuntimeError:
            pass


def screen(res):
    return "\n".join(l.rstrip() for l in res.observation.frame.lines)


def test_menu_select(spawn):
    app, start = spawn(str(HERE / "menu_app.py"))
    assert "|> Apple" in screen(start)
    app.dispatch(KeyInput(T0, ("ArrowDown",)))
    r = app.dispatch(KeyInput(T0, ("Enter",)))
    assert type(r) is EpochCompleted
    assert "Selected: Banana" in screen(r)
    end = app.dispatch(KeyInput(T0, ("Control", "c")))
    assert end.outcome == RunFinished(exit=ExitStatus(kind="code", value=130))


def test_greet_via_shim(spawn):
    app, start = spawn(str(HERE / "tv_shim.py"), str(HERE / "greet.py"))
    assert "name?" in screen(start)
    r = app.dispatch(TextInput(T0, "Alice\r"))
    assert "hello Alice" in screen(r)


def test_failure_message_when_text_never_appears(spawn):
    app, _ = spawn(str(HERE / "tv_shim.py"), str(HERE / "greet.py"))
    r = app.dispatch(TextInput(T0, "Ali"))  # no Enter: subject never answers
    assert type(r) is EpochCompleted, r  # expected to fail: shows what a user sees
