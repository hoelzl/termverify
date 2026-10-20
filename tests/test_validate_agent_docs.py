"""Agent records under ``docs/agent/`` carry machine-readable metadata.

Issue #322: status lived in free-form bold bullets, four records had none,
nothing recorded supersession, and review frontmatter came in three shapes.
The validator holds every record to one frontmatter contract so indexes can
be generated from it and stale status cannot hide.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest


def load_validator() -> ModuleType:
    path = Path("scripts/validate_agent_docs.py")
    spec = importlib.util.spec_from_file_location("agent_docs_validator", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _record(
    root: Path,
    relative: str,
    *,
    type_: str = "decision",
    status: str = "accepted",
    extra: str = "",
    body: str = "# Record\n",
) -> Path:
    path = root / "docs" / "agent" / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\n"
        f"type: {type_}\n"
        f"status: {status}\n"
        "date: 2026-07-19\n"
        "summary: One sentence that says what the record decides.\n"
        f"{extra}"
        "---\n\n"
        f"{body}",
        encoding="utf-8",
    )
    return path


def test_well_formed_records_are_valid(tmp_path: Path) -> None:
    _record(tmp_path, "design/adr.md")
    _record(tmp_path, "design/old-review.md", type_="review", status="resolved")
    _record(tmp_path, "reviews/pass.md", type_="review", status="findings")
    _record(tmp_path, "plans/plan.md", type_="plan", status="active")
    _record(tmp_path, "prompts/prompt.md", type_="prompt", status="retired")
    _record(tmp_path, "handovers/live.md", type_="handover", status="active")
    _record(
        tmp_path,
        "handovers/archive/done.md",
        type_="handover",
        status="complete",
    )
    validator = load_validator()

    assert validator.validate_agent_docs(tmp_path) == []


def test_navigation_files_are_exempt(tmp_path: Path) -> None:
    for name in ("README.md", "index.md"):
        path = tmp_path / "docs" / "agent" / "design" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# Navigation\n", encoding="utf-8")
    validator = load_validator()

    assert validator.validate_agent_docs(tmp_path) == []


def test_missing_frontmatter_is_reported(tmp_path: Path) -> None:
    path = tmp_path / "docs" / "agent" / "design" / "bare.md"
    path.parent.mkdir(parents=True)
    path.write_text("# Bare\n", encoding="utf-8")
    validator = load_validator()

    errors = validator.validate_agent_docs(tmp_path)

    assert len(errors) == 1
    assert "frontmatter" in errors[0]


def test_unterminated_or_non_mapping_frontmatter_is_reported(tmp_path: Path) -> None:
    root = tmp_path / "docs" / "agent" / "design"
    root.mkdir(parents=True)
    (root / "open.md").write_text("---\ntype: decision\n", encoding="utf-8")
    (root / "list.md").write_text("---\n- a\n- b\n---\n", encoding="utf-8")
    validator = load_validator()

    errors = validator.validate_agent_docs(tmp_path)

    assert len(errors) == 2


@pytest.mark.parametrize("field", ["type", "status", "date", "summary"])
def test_required_fields_are_enforced(tmp_path: Path, field: str) -> None:
    path = _record(tmp_path, "design/adr.md")
    text = path.read_text(encoding="utf-8")
    kept = [line for line in text.splitlines() if not line.startswith(f"{field}:")]
    path.write_text("\n".join(kept) + "\n", encoding="utf-8")
    validator = load_validator()

    errors = validator.validate_agent_docs(tmp_path)

    assert any(field in error for error in errors), errors


def test_status_outside_the_type_vocabulary_is_reported(tmp_path: Path) -> None:
    _record(tmp_path, "design/adr.md", status="simmering")
    validator = load_validator()

    errors = validator.validate_agent_docs(tmp_path)

    assert len(errors) == 1
    assert "simmering" in errors[0]


def test_type_not_allowed_in_folder_is_reported(tmp_path: Path) -> None:
    _record(tmp_path, "plans/adr.md", type_="decision")
    validator = load_validator()

    errors = validator.validate_agent_docs(tmp_path)

    assert len(errors) == 1
    assert "plans" in errors[0]


def test_unknown_folder_is_reported(tmp_path: Path) -> None:
    _record(tmp_path, "misc/adr.md")
    validator = load_validator()

    errors = validator.validate_agent_docs(tmp_path)

    assert len(errors) == 1
    assert "misc" in errors[0]


def test_malformed_date_is_reported(tmp_path: Path) -> None:
    path = _record(tmp_path, "design/adr.md")
    path.write_text(
        path.read_text(encoding="utf-8").replace("2026-07-19", "July 19"),
        encoding="utf-8",
    )
    validator = load_validator()

    errors = validator.validate_agent_docs(tmp_path)

    assert len(errors) == 1
    assert "date" in errors[0]


def test_multiline_summary_is_reported(tmp_path: Path) -> None:
    path = _record(tmp_path, "design/adr.md")
    path.write_text(
        path.read_text(encoding="utf-8").replace(
            "summary: One sentence that says what the record decides.",
            "summary: |\n  First line.\n  Second line.",
        ),
        encoding="utf-8",
    )
    validator = load_validator()

    errors = validator.validate_agent_docs(tmp_path)

    assert len(errors) == 1
    assert "summary" in errors[0]


def test_superseded_requires_an_existing_successor(tmp_path: Path) -> None:
    _record(tmp_path, "design/orphan.md", status="superseded")
    _record(
        tmp_path,
        "design/dangling.md",
        status="superseded",
        extra="superseded_by: docs/agent/design/missing.md\n",
    )
    validator = load_validator()

    errors = validator.validate_agent_docs(tmp_path)

    assert len(errors) == 2
    assert any("superseded_by" in error for error in errors)
    assert any("missing.md" in error for error in errors)


def test_supersession_links_resolve(tmp_path: Path) -> None:
    _record(tmp_path, "design/new.md", extra="supersedes: [docs/agent/design/old.md]\n")
    _record(
        tmp_path,
        "design/old.md",
        status="superseded",
        extra="superseded_by: docs/agent/design/new.md\n",
    )
    validator = load_validator()

    assert validator.validate_agent_docs(tmp_path) == []


def test_archived_handover_must_be_finished(tmp_path: Path) -> None:
    _record(tmp_path, "handovers/archive/stale.md", type_="handover", status="active")
    _record(tmp_path, "handovers/done.md", type_="handover", status="complete")
    validator = load_validator()

    errors = validator.validate_agent_docs(tmp_path)

    assert len(errors) == 2
    assert all("archive" in error for error in errors)


def test_body_status_bullet_must_agree_with_frontmatter(tmp_path: Path) -> None:
    _record(
        tmp_path,
        "handovers/live.md",
        type_="handover",
        status="active",
        body="# Handover\n\n- **Status:** blocked — waiting on a decision\n",
    )
    validator = load_validator()

    errors = validator.validate_agent_docs(tmp_path)

    assert len(errors) == 1
    assert "blocked" in errors[0]


def test_superseded_record_keeps_its_historical_status_bullet(tmp_path: Path) -> None:
    _record(tmp_path, "design/new.md")
    _record(
        tmp_path,
        "design/old.md",
        status="superseded",
        extra="superseded_by: docs/agent/design/new.md\n",
        body="# Old\n\n- **Status:** accepted — decided 2026-07-15\n",
    )
    validator = load_validator()

    assert validator.validate_agent_docs(tmp_path) == []


def test_review_status_bullets_are_point_in_time(tmp_path: Path) -> None:
    """Reviews are never rewritten: a ``findings`` bullet in the body may
    disagree with the living ``resolved`` frontmatter status."""
    _record(
        tmp_path,
        "reviews/pass.md",
        type_="review",
        status="resolved",
        body="# Review\n\n- **Status:** findings for maintainer triage\n",
    )
    validator = load_validator()

    assert validator.validate_agent_docs(tmp_path) == []


def test_main_runs_green_on_the_real_repository() -> None:
    validator = load_validator()

    assert validator.main() == 0


def test_main_reports_failures_with_a_nonzero_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _record(tmp_path, "design/adr.md", status="simmering")
    validator = load_validator()
    monkeypatch.chdir(tmp_path)

    assert validator.main() == 1
    assert "simmering" in capsys.readouterr().out
