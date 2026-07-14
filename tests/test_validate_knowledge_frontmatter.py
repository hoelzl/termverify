from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType


def load_validator() -> ModuleType:
    path = Path("scripts/validate_knowledge_frontmatter.py")
    spec = importlib.util.spec_from_file_location("knowledge_validator", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_validate_knowledge_frontmatter_accepts_index_and_typed_documents(
    tmp_path: Path,
) -> None:
    root = tmp_path / "knowledge"
    root.mkdir()
    (root / "index.md").write_text("# Index\n", encoding="utf-8")
    (root / "concept.md").write_text(
        "---\ntype: Concept\n---\n\n# Concept\n",
        encoding="utf-8",
    )

    validator = load_validator()

    assert validator.validate_knowledge_frontmatter(root) == []


def test_validate_knowledge_frontmatter_reports_missing_frontmatter_and_type(
    tmp_path: Path,
) -> None:
    root = tmp_path / "knowledge"
    root.mkdir()
    (root / "missing.md").write_text("# Missing\n", encoding="utf-8")
    (root / "untyped.md").write_text("---\ntitle: Untyped\n---\n", encoding="utf-8")

    validator = load_validator()

    assert validator.validate_knowledge_frontmatter(root) == [
        f"{root / 'missing.md'}: missing YAML frontmatter",
        f"{root / 'untyped.md'}: missing non-empty type",
    ]
