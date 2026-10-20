"""Living documentation carries a review-by date and a size budget (#322)."""

from __future__ import annotations

import datetime
import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

TODAY = datetime.date(2026, 10, 20)


def load_checker() -> ModuleType:
    path = Path("scripts/check_doc_freshness.py")
    spec = importlib.util.spec_from_file_location("doc_freshness_checker", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write(root: Path, relative: str, front: str, body: str = "# Page\n") -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{front}---\n\n{body}", encoding="utf-8")


def _tree(root: Path, review_by: str = "2026-12-01") -> None:
    _write(root, "docs/knowledge/page.md", f"type: Concept\nreview_by: {review_by}\n")
    _write(
        root, "docs/knowledge/sub/deep.md", f"type: Concept\nreview_by: {review_by}\n"
    )
    (root / "docs/knowledge/index.md").write_text("# Index\n", encoding="utf-8")
    _write(
        root,
        "docs/agent/handovers/live.md",
        f"type: handover\nstatus: active\nreview_by: {review_by}\n",
    )
    _write(
        root,
        "docs/agent/handovers/archive/old.md",
        "type: handover\nstatus: complete\n",
    )


def test_current_documents_pass(tmp_path: Path) -> None:
    _tree(tmp_path)
    checker = load_checker()

    assert checker.check(tmp_path, TODAY) == []


def test_review_by_today_is_still_current(tmp_path: Path) -> None:
    _tree(tmp_path, review_by="2026-10-20")
    checker = load_checker()

    assert checker.check(tmp_path, TODAY) == []


def test_overdue_documents_fail_with_the_remedy(tmp_path: Path) -> None:
    _tree(tmp_path, review_by="2026-10-19")
    checker = load_checker()

    errors = checker.check(tmp_path, TODAY)

    assert len(errors) == 3
    assert all("move review_by forward" in error for error in errors)


@pytest.mark.parametrize("value", ["", "soon", "2026-10-20T10:00:00"])
def test_missing_or_malformed_review_by_fails(tmp_path: Path, value: str) -> None:
    _write(tmp_path, "docs/knowledge/page.md", f"type: Concept\nreview_by: {value}\n")
    checker = load_checker()

    errors = checker.check(tmp_path, TODAY)

    assert errors == [
        "docs/knowledge/page.md: missing or malformed review_by (YYYY-MM-DD)"
    ]


def test_unparsable_frontmatter_counts_as_missing(tmp_path: Path) -> None:
    for name, text in (
        ("bare.md", "# No frontmatter\n"),
        ("open.md", "---\ntype: x\n"),
        ("bad.md", "---\nreview_by: 2026-13-45\n---\n"),
        ("list.md", "---\n- a\n---\n"),
    ):
        path = tmp_path / "docs/knowledge" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    checker = load_checker()

    assert len(checker.check(tmp_path, TODAY)) == 4


def test_finished_and_archived_handovers_are_exempt(tmp_path: Path) -> None:
    _write(
        tmp_path, "docs/agent/handovers/done.md", "type: handover\nstatus: complete\n"
    )
    (tmp_path / "docs/agent/handovers/index.md").write_text("# Index\n", "utf-8")
    checker = load_checker()

    assert checker.check(tmp_path, TODAY) == []


def test_oversized_working_handover_fails(tmp_path: Path) -> None:
    checker = load_checker()
    _write(
        tmp_path,
        "docs/agent/handovers/big.md",
        "type: handover\nstatus: active\nreview_by: 2026-12-01\n",
        body="x" * (checker.HANDOVER_BUDGET + 1),
    )

    errors = checker.check(tmp_path, TODAY)

    assert len(errors) == 1
    assert "archived record" in errors[0]


def test_the_repository_documents_are_current() -> None:
    checker = load_checker()

    assert checker.check(Path(), datetime.date.today()) == []


def test_main_reports_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _tree(tmp_path, review_by="2026-01-01")
    checker = load_checker()
    monkeypatch.chdir(tmp_path)

    assert checker.main(today=TODAY) == 1
    assert "has passed" in capsys.readouterr().out
    _tree(tmp_path)
    assert checker.main(today=TODAY) == 0
