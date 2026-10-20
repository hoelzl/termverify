"""Documentation references must resolve (issue #322).

Agents follow relative links and backticked repository paths as lightweight
identifiers; a renamed file must not leave them dangling.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest


def load_checker() -> ModuleType:
    path = Path("scripts/check_doc_references.py")
    spec = importlib.util.spec_from_file_location("doc_reference_checker", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _write(root: Path, relative: str, text: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_resolving_links_paths_and_anchors_pass(tmp_path: Path) -> None:
    _write(tmp_path, "src/pkg/mod.py", "")
    _write(tmp_path, "docs/b.md", "# Page B\n\n## The `Fixed` v1 limits (x)\n")
    _write(
        tmp_path,
        "docs/a.md",
        "See [b](b.md), [limits](b.md#the-fixed-v1-limits-x), [top](#a),"
        " [web](https://example.com), and `src/pkg/mod.py`.\n\n# A\n",
    )
    checker = load_checker()

    assert checker.check(tmp_path) == []


def test_broken_links_anchors_and_paths_are_reported(tmp_path: Path) -> None:
    _write(tmp_path, "docs/b.md", "# Page B\n")
    _write(
        tmp_path,
        "docs/a.md",
        "[gone](missing.md) [anchor](b.md#nope) `scripts/gone.py`\n",
    )
    checker = load_checker()

    errors = checker.check(tmp_path)

    assert errors == [
        "docs/a.md:1: broken link missing.md",
        "docs/a.md:1: missing anchor b.md#nope",
        "docs/a.md:1: missing path `scripts/gone.py`",
    ]


def test_code_fences_frontmatter_globs_and_placeholders_are_skipped(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "docs/a.md",
        "---\nsummary: '[x](nowhere.md)'\n---\n\n"
        "```text\n[gone](missing.md) `src/gone.py`\n```\n\n"
        "`docs/agent/design/*.md` `docs/<name>.md` `tests/{a,b}.py`\n",
    )
    checker = load_checker()

    assert checker.check(tmp_path) == []


def test_allowed_missing_paths_and_excluded_trees_pass(tmp_path: Path) -> None:
    _write(tmp_path, "docs/a.md", "`examples/` and `tests/fixtures/baselines/x.json`\n")
    _write(tmp_path, "CHANGELOG.md", "`src/removed.py`\n")
    _write(tmp_path, "docs/agent/handovers/archive/old.md", "[x](gone.md)\n")
    checker = load_checker()

    assert checker.check(tmp_path) == []


def test_line_suffixes_after_a_path_are_ignored(tmp_path: Path) -> None:
    _write(tmp_path, "src/mod.py", "")
    _write(tmp_path, "docs/a.md", "`src/mod.py:12-14` and `src/mod.py`.\n")
    checker = load_checker()

    assert checker.check(tmp_path) == []


def test_duplicate_headings_get_numbered_anchors(tmp_path: Path) -> None:
    _write(tmp_path, "docs/b.md", "# B\n\n## Notes\n\n## Notes\n")
    checker = load_checker()

    assert checker.anchors(tmp_path / "docs/b.md") == {"b", "notes", "notes-1"}


def test_the_repository_references_resolve() -> None:
    checker = load_checker()

    assert checker.check(Path()) == []


def test_main_reports_failures_with_remediation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write(tmp_path, "docs/a.md", "[gone](missing.md)\n")
    checker = load_checker()
    monkeypatch.chdir(tmp_path)

    assert checker.main() == 1
    assert "ALLOWED_MISSING" in capsys.readouterr().out
    (tmp_path / "docs/a.md").write_text("fine\n", encoding="utf-8")
    assert checker.main() == 0


def test_wrong_case_targets_fail_even_on_case_insensitive_systems(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "docs/Guide.md", "# Guide\n")
    _write(tmp_path, "docs/a.md", "[g](guide.md) `docs/guide.md` [ok](Guide.md)\n")
    checker = load_checker()

    errors = checker.check(tmp_path)

    assert errors == [
        "docs/a.md:1: broken link guide.md",
        "docs/a.md:1: missing path `docs/guide.md`",
    ]


def test_titles_angle_brackets_queries_encoding_and_definitions(tmp_path: Path) -> None:
    _write(tmp_path, "docs/my page.md", "# My page\n")
    _write(
        tmp_path,
        "docs/a.md",
        '[t](<my page.md>) [u](my%20page.md?x=1) [v](my%20page.md "Title")\n'
        "[gone]: missing.md\n[ok]: <my page.md#my-page>\n",
    )
    checker = load_checker()

    assert checker.check(tmp_path) == ["docs/a.md:2: broken link missing.md"]


def test_hidden_tool_directories_are_not_scanned(tmp_path: Path) -> None:
    _write(tmp_path, ".pytest_cache/README.md", "[x](gone.md)\n")
    _write(tmp_path, ".claude/worktrees/w/docs/a.md", "[x](gone.md)\n")
    _write(tmp_path, ".agents/skills/s/SKILL.md", "[x](gone.md)\n")
    checker = load_checker()

    assert checker.check(tmp_path) == [
        ".agents/skills/s/SKILL.md:1: broken link gone.md"
    ]
