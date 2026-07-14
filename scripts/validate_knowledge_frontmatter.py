"""Validate the Open Knowledge Format frontmatter contract."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import yaml

EXEMPT_FILENAMES = frozenset({"index.md", "log.md"})


def validate_knowledge_frontmatter(root: Path) -> list[str]:
    """Return contract violations for Markdown documents below *root*."""
    errors: list[str] = []

    for path in sorted(root.rglob("*.md")):
        if path.name in EXEMPT_FILENAMES:
            continue

        text = path.read_text(encoding="utf-8")
        if not text.startswith("---\n"):
            errors.append(f"{path}: missing YAML frontmatter")
            continue

        _, frontmatter, *_ = text.split("---", 2)
        data = yaml.safe_load(frontmatter)
        if not isinstance(data, dict) or not data.get("type"):
            errors.append(f"{path}: missing non-empty type")

    return errors


def main(argv: Sequence[str] | None = None) -> int:
    del argv
    errors = validate_knowledge_frontmatter(Path("docs/knowledge"))
    if errors:
        print("\n".join(errors))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
