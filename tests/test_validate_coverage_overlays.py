"""Tests for scripts/validate_coverage_overlays.py (issue #230 review)."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType


def load_validator() -> ModuleType:
    path = Path("scripts/validate_coverage_overlays.py")
    spec = importlib.util.spec_from_file_location("coverage_overlay_validator", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_PYPROJECT = """
[tool.coverage.run]
branch = true
source = ["termverify"]
omit = ["*/termverify/_conpty.py"]

[tool.coverage.report]
show_missing = true
skip_covered = true
exclude_also = ['# coverage: exclude-(posix|windows)']
fail_under = 94
precision = 2
"""


def _overlay(
    marker: str, *, fail_under: int = 94, source: str = '["termverify"]'
) -> str:
    return f"""
[tool.coverage.run]
branch = true
source = {source}
omit = ["*/termverify/_conpty.py"]

[tool.coverage.report]
show_missing = true
skip_covered = true
exclude_also = ['{marker}']
fail_under = {fail_under}
precision = 2
"""


def _write_repository(
    root: Path, *, windows: str | None = None, posix: str | None = None
) -> None:
    (root / "pyproject.toml").write_text(_PYPROJECT, encoding="utf-8")
    if windows is not None:
        (root / "coverage-windows.toml").write_text(windows, encoding="utf-8")
    if posix is not None:
        (root / "coverage-posix.toml").write_text(posix, encoding="utf-8")


def _consistent(root: Path) -> None:
    _write_repository(
        root,
        windows=_overlay("# coverage: exclude-windows"),
        posix=_overlay("# coverage: exclude-posix"),
    )


def test_the_repository_overlays_match_pyproject() -> None:
    validator = load_validator()
    assert validator.validate_coverage_overlays(Path.cwd()) == []


def test_consistent_synthetic_repository_passes(tmp_path: Path) -> None:
    validator = load_validator()
    _consistent(tmp_path)
    assert validator.validate_coverage_overlays(tmp_path) == []


def test_a_drifted_floor_is_reported(tmp_path: Path) -> None:
    validator = load_validator()
    _write_repository(
        tmp_path,
        windows=_overlay("# coverage: exclude-windows", fail_under=90),
        posix=_overlay("# coverage: exclude-posix"),
    )
    errors = validator.validate_coverage_overlays(tmp_path)
    assert any(
        "fail_under" in error and "coverage-windows.toml" in error for error in errors
    )


def test_a_drifted_source_is_reported(tmp_path: Path) -> None:
    validator = load_validator()
    _write_repository(
        tmp_path,
        windows=_overlay("# coverage: exclude-windows"),
        posix=_overlay("# coverage: exclude-posix", source='["other"]'),
    )
    errors = validator.validate_coverage_overlays(tmp_path)
    assert any("source" in error and "coverage-posix.toml" in error for error in errors)


def test_an_overlay_excluding_the_wrong_marker_is_reported(tmp_path: Path) -> None:
    validator = load_validator()
    _write_repository(
        tmp_path,
        windows=_overlay("# coverage: exclude-(posix|windows)"),
        posix=_overlay("# coverage: exclude-posix"),
    )
    errors = validator.validate_coverage_overlays(tmp_path)
    assert any(
        "exclude_also" in error and "coverage-windows.toml" in error for error in errors
    )


def test_a_missing_overlay_is_reported(tmp_path: Path) -> None:
    validator = load_validator()
    _write_repository(tmp_path, windows=_overlay("# coverage: exclude-windows"))
    errors = validator.validate_coverage_overlays(tmp_path)
    assert any("coverage-posix.toml" in error for error in errors)


def test_a_drifted_base_exclude_also_is_reported(tmp_path: Path) -> None:
    validator = load_validator()
    drifted = _PYPROJECT.replace(
        "exclude_also = ['# coverage: exclude-(posix|windows)']",
        "exclude_also = ['# coverage: exclude-windows']",
    )
    (tmp_path / "pyproject.toml").write_text(drifted, encoding="utf-8")
    (tmp_path / "coverage-windows.toml").write_text(
        _overlay("# coverage: exclude-windows"), encoding="utf-8"
    )
    (tmp_path / "coverage-posix.toml").write_text(
        _overlay("# coverage: exclude-posix"), encoding="utf-8"
    )
    errors = validator.validate_coverage_overlays(tmp_path)
    assert any(
        "exclude_also" in error and "pyproject.toml" in error for error in errors
    )


def test_malformed_toml_is_reported_as_a_violation(tmp_path: Path) -> None:
    validator = load_validator()
    (tmp_path / "pyproject.toml").write_text(_PYPROJECT, encoding="utf-8")
    (tmp_path / "coverage-windows.toml").write_text(
        _overlay("# coverage: exclude-windows"), encoding="utf-8"
    )
    (tmp_path / "coverage-posix.toml").write_text(
        "[tool.coverage.run\n", encoding="utf-8"
    )
    errors = validator.validate_coverage_overlays(tmp_path)
    assert any("coverage-posix.toml" in error and "TOML" in error for error in errors)


def test_an_additive_overlay_key_is_reported(tmp_path: Path) -> None:
    validator = load_validator()
    additive = _overlay("# coverage: exclude-windows").replace(
        'omit = ["*/termverify/_conpty.py"]',
        'omit = ["*/termverify/_conpty.py"]\nconcurrency = ["thread"]',
    )
    _write_repository(
        tmp_path,
        windows=additive,
        posix=_overlay("# coverage: exclude-posix"),
    )
    errors = validator.validate_coverage_overlays(tmp_path)
    assert any("coverage-windows.toml" in error for error in errors)
