"""``scripts/check.py`` is the single entry point for the quality gates.

Issue #322: the always-on agent guide names one command instead of
repeating the gate list in prose, so the command list lives here, in code
that runs, and ``--list`` self-reports it.
"""

from __future__ import annotations

import importlib.util
from collections.abc import Sequence
from pathlib import Path
from types import ModuleType

import pytest


def load_check() -> ModuleType:
    path = Path("scripts/check.py")
    spec = importlib.util.spec_from_file_location("check_script", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RecordingRunner:
    def __init__(self, failing: Sequence[str] = ()) -> None:
        self.calls: list[tuple[str, ...]] = []
        self._failing = failing

    def __call__(self, command: Sequence[str]) -> int:
        self.calls.append(tuple(command))
        return 1 if any(word in command for word in self._failing) else 0


def test_quick_runs_only_the_pre_commit_hooks() -> None:
    check = load_check()
    runner = RecordingRunner()

    assert check.run_gates(check.gate_commands(full=False), runner) == 0

    assert runner.calls == [tuple(command) for command in check.QUICK]
    assert all("pre-commit" in call for call in runner.calls)


def test_full_adds_types_build_and_covered_tests() -> None:
    check = load_check()
    runner = RecordingRunner()

    assert check.run_gates(check.gate_commands(full=True), runner) == 0

    flattened = [" ".join(call) for call in runner.calls]
    assert flattened[0] == " ".join(check.QUICK[0])
    assert any("mypy src tests scripts" in call for call in flattened)
    assert any(call.endswith("uv --no-config build") for call in flattened)
    assert any("pytest --cov" in call for call in flattened)


def test_first_failure_stops_the_run_and_names_the_command(
    capsys: pytest.CaptureFixture[str],
) -> None:
    check = load_check()
    runner = RecordingRunner(failing=("mypy",))

    status = check.run_gates(check.gate_commands(full=True), runner)

    assert status == 1
    assert "mypy" in runner.calls[-1]
    assert "failed" in capsys.readouterr().out


def test_list_prints_the_commands_without_running_them(
    capsys: pytest.CaptureFixture[str],
) -> None:
    check = load_check()

    assert check.main(["--full", "--list"]) == 0

    out = capsys.readouterr().out
    assert "pytest --cov" in out and "pre-commit" in out


def test_main_delegates_to_the_injected_runner() -> None:
    check = load_check()
    runner = RecordingRunner()

    assert check.main([], runner=runner) == 0
    assert runner.calls == [tuple(command) for command in check.QUICK]


def test_default_runner_executes_the_command(monkeypatch: pytest.MonkeyPatch) -> None:
    check = load_check()
    seen: list[list[str]] = []

    def fake_call(command: list[str]) -> int:
        seen.append(command)
        return 0

    monkeypatch.setattr(check.subprocess, "call", fake_call)

    assert check.main([]) == 0
    assert seen == [list(command) for command in check.QUICK]


def test_full_covers_every_pre_push_hook() -> None:
    """``--full`` must not drift from the pre-push stage: every pre-push hook
    entry appears in the full gate (the test hook may add coverage flags)."""
    import yaml

    check = load_check()
    config = yaml.safe_load(Path(".pre-commit-config.yaml").read_text("utf-8"))
    pre_push = [
        hook["entry"]
        for repo in config["repos"]
        for hook in repo["hooks"]
        if "pre-push" in hook.get("stages", ())
    ]
    full = [" ".join(command) for command in check.gate_commands(full=True)]

    assert pre_push
    for entry in pre_push:
        assert any(command.startswith(entry) for command in full), entry
