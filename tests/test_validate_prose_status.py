"""The prose-status validator holds drift-prone status prose to the code.

Owner decision 2026-07-24 (review Slice 8.4): a minimal, drift-driven
validator — version discipline for the manual ``.dev0`` marker scheme, the
ADR status vocabulary, and registry counts stated in prose — in the
``scripts/`` validator pattern.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType


def load_validator() -> ModuleType:
    path = Path("scripts/validate_prose_status.py")
    spec = importlib.util.spec_from_file_location("prose_status_validator", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_pyproject(root: Path, version: str, current: str | None = None) -> None:
    (root / "pyproject.toml").write_text(
        "[project]\n"
        f'version = "{version}"\n'
        "\n"
        "[tool.bumpversion]\n"
        f'current_version = "{current if current is not None else version}"\n',
        encoding="utf-8",
    )


def test_dev_marked_tree_is_valid_without_a_release_section(tmp_path: Path) -> None:
    _write_pyproject(tmp_path, "0.2.0.dev0")
    (tmp_path / "CHANGELOG.md").write_text(
        "## [0.1.1] - 2026-07-27\n", encoding="utf-8"
    )

    validator = load_validator()

    assert validator.validate_version_discipline(tmp_path) == []


def test_marker_less_tree_requires_its_release_section(tmp_path: Path) -> None:
    _write_pyproject(tmp_path, "0.2.0")
    (tmp_path / "CHANGELOG.md").write_text(
        "## [0.1.1] - 2026-07-27\n", encoding="utf-8"
    )

    validator = load_validator()

    errors = validator.validate_version_discipline(tmp_path)
    assert len(errors) == 1
    assert "0.2.0" in errors[0] and "CHANGELOG" in errors[0]


def test_marker_less_tree_with_its_release_section_is_valid(tmp_path: Path) -> None:
    _write_pyproject(tmp_path, "0.2.0")
    (tmp_path / "CHANGELOG.md").write_text(
        "## [0.2.0] - 2026-08-01\n\n## [0.1.1] - 2026-07-27\n", encoding="utf-8"
    )

    validator = load_validator()

    assert validator.validate_version_discipline(tmp_path) == []


def test_version_and_bumpversion_current_must_agree(tmp_path: Path) -> None:
    _write_pyproject(tmp_path, "0.2.0.dev0", current="0.1.1")
    (tmp_path / "CHANGELOG.md").write_text(
        "## [0.1.1] - 2026-07-27\n", encoding="utf-8"
    )

    validator = load_validator()

    errors = validator.validate_version_discipline(tmp_path)
    assert len(errors) == 1
    assert "current_version" in errors[0]


def test_adr_status_vocabulary_accepts_the_closed_tokens(tmp_path: Path) -> None:
    design = tmp_path / "docs" / "agent" / "design"
    design.mkdir(parents=True)
    (design / "one.md").write_text(
        "# ADR\n\n- **Status:** accepted — decided 2026-07-19\n", encoding="utf-8"
    )
    (design / "two.md").write_text(
        "# ADR\n\n- **Status:** proposed\n", encoding="utf-8"
    )
    (design / "no-status.md").write_text("# Notes\n", encoding="utf-8")

    validator = load_validator()

    assert validator.validate_adr_status(tmp_path) == []


def test_adr_status_vocabulary_rejects_a_novel_token(tmp_path: Path) -> None:
    design = tmp_path / "docs" / "agent" / "design"
    design.mkdir(parents=True)
    (design / "weird.md").write_text(
        "# ADR\n\n- **Status:** simmering — we will see\n", encoding="utf-8"
    )

    validator = load_validator()

    errors = validator.validate_adr_status(tmp_path)
    assert len(errors) == 1
    assert "simmering" in errors[0]


def test_registry_counts_match_the_shipped_registries() -> None:
    """Run against the real repository tree: every claim site must exist
    and state the count the package ships."""
    validator = load_validator()

    assert validator.validate_registry_counts(Path()) == []


def test_registry_count_drift_is_reported(tmp_path: Path) -> None:
    validator = load_validator()
    for relative, _pattern, _expected in validator.REGISTRY_COUNT_CLAIMS:
        stale = tmp_path / relative
        stale.parent.mkdir(parents=True, exist_ok=True)
        stale.write_text(
            "The exact v1 component registry has 67 entries: it admits\n"
            "exactly 934 chords, each of the 934 valid, totality over all\n"
            "934 valid chords.\n",
            encoding="utf-8",
        )

    errors = validator.validate_registry_counts(tmp_path)

    assert len(errors) == len(validator.REGISTRY_COUNT_CLAIMS)


def test_removed_claim_sites_fail_loudly(tmp_path: Path) -> None:
    """A reworded or deleted claim must fail the check, not silently pass:
    the claim table and the prose move in lockstep."""
    validator = load_validator()
    for relative, _pattern, _expected in validator.REGISTRY_COUNT_CLAIMS:
        silent = tmp_path / relative
        silent.parent.mkdir(parents=True, exist_ok=True)
        silent.write_text("No counts stated here anymore.\n", encoding="utf-8")

    errors = validator.validate_registry_counts(tmp_path)

    assert len(errors) == len(validator.REGISTRY_COUNT_CLAIMS)
    assert all("not found" in error for error in errors)


def test_missing_claim_file_is_a_curated_error(tmp_path: Path) -> None:
    validator = load_validator()

    errors = validator.validate_registry_counts(tmp_path)

    assert len(errors) == len(validator.REGISTRY_COUNT_CLAIMS)
    assert all("missing" in error for error in errors)


def test_missing_changelog_is_a_curated_error(tmp_path: Path) -> None:
    _write_pyproject(tmp_path, "0.2.0")

    validator = load_validator()

    errors = validator.validate_version_discipline(tmp_path)
    assert len(errors) == 1
    assert "missing" in errors[0]


def test_main_runs_green_on_the_real_repository() -> None:
    validator = load_validator()

    assert validator.main() == 0


def test_main_reports_failures_with_a_nonzero_exit(
    tmp_path: Path, monkeypatch: object
) -> None:
    import pytest

    assert isinstance(monkeypatch, pytest.MonkeyPatch)
    _write_pyproject(tmp_path, "0.2.0")
    (tmp_path / "CHANGELOG.md").write_text("nothing released\n", encoding="utf-8")
    (tmp_path / "docs" / "agent" / "design").mkdir(parents=True)
    validator = load_validator()
    monkeypatch.chdir(tmp_path)

    assert validator.main() == 1
