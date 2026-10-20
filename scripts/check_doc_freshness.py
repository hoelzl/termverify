#!/usr/bin/env python3
"""Fail when living documentation is overdue for review or outgrows its budget.

Usage:
    uv --no-config run python scripts/check_doc_freshness.py

Documents that agents trust as current carry a ``review_by: YYYY-MM-DD``
frontmatter date (issue #322):

- every knowledge page under ``docs/knowledge/`` (``index.md`` excepted);
- every unfinished handover (``draft``, ``active``, ``blocked``) outside
  ``docs/agent/handovers/archive/``.

Once the date has passed the check fails, so prose cannot silently outlive
the code it describes. Reviewing means re-verifying the page against the code
and executable checks, repairing what drifted, and moving ``review_by``
forward — the doc-gardening procedure in ``docs/README.md``.

Unfinished handovers also have a byte budget: a handover is read whole when
work resumes, so completed phases belong in an archived record, not in the
working handover.
"""

from __future__ import annotations

import datetime
from collections.abc import Sequence
from pathlib import Path

import yaml

KNOWLEDGE = Path("docs") / "knowledge"
HANDOVERS = Path("docs") / "agent" / "handovers"
UNFINISHED = frozenset({"draft", "active", "blocked"})
HANDOVER_BUDGET = 64 * 1024


def _frontmatter(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}
    try:
        data = yaml.safe_load(text[4:end])
    except (yaml.YAMLError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _review_error(relative: str, data: dict[str, object], today: datetime.date) -> str:
    value = data.get("review_by")
    if isinstance(value, datetime.datetime) or not isinstance(value, datetime.date):
        return f"{relative}: missing or malformed review_by (YYYY-MM-DD)"
    if value < today:
        return (
            f"{relative}: review_by {value.isoformat()} has passed — re-verify the"
            " page against the code, repair any drift, and move review_by forward"
        )
    return ""


def living_documents(root: Path) -> list[tuple[Path, dict[str, object]]]:
    """Return the documents that must carry ``review_by``, sorted."""
    documents: list[tuple[Path, dict[str, object]]] = []
    for path in sorted((root / KNOWLEDGE).rglob("*.md")):
        if path.name != "index.md":
            documents.append((path, _frontmatter(path)))
    handovers = root / HANDOVERS
    for path in sorted(handovers.glob("*.md")):
        if path.name in {"index.md", "README.md"}:
            continue
        data = _frontmatter(path)
        if data.get("status") in UNFINISHED:
            documents.append((path, data))
    return documents


def check(root: Path, today: datetime.date) -> list[str]:
    """Return freshness and budget violations under *root* as of *today*."""
    errors: list[str] = []
    for path, data in living_documents(root):
        relative = path.relative_to(root).as_posix()
        error = _review_error(relative, data, today)
        if error:
            errors.append(error)
        if relative.startswith(HANDOVERS.as_posix()):
            size = len(path.read_bytes())
            if size > HANDOVER_BUDGET:
                errors.append(
                    f"{relative}: {size} bytes exceeds the {HANDOVER_BUDGET}-byte"
                    " working-handover budget — move completed phases into an"
                    " archived record and leave a pointer"
                )
    return errors


def main(argv: Sequence[str] | None = None, today: datetime.date | None = None) -> int:
    del argv
    errors = check(Path(), today or datetime.date.today())
    if errors:
        print("\n".join(errors))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
