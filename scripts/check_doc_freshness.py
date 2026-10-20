#!/usr/bin/env python3
"""Check review-by dates and size budgets of living documentation.

Usage:
    uv --no-config run python scripts/check_doc_freshness.py            # gate
    uv --no-config run python scripts/check_doc_freshness.py --overdue  # report

Documents that agents trust as current carry a ``review_by: YYYY-MM-DD``
frontmatter date (issue #322):

- every knowledge page under ``docs/knowledge/`` (``index.md`` excepted);
- every unfinished handover (``draft``, ``active``, ``blocked``) outside
  ``docs/agent/handovers/archive/``.

The default mode is the commit and pull-request gate. It fails only on facts
fixed in the tree — a missing or malformed ``review_by``, or a working
handover over its byte budget — and merely *warns* about dates that have
passed or fall within ``WARN_DAYS``. A date-based failure there would turn
every unrelated change red on the same day and make old commits fail their
own gates, which breaks bisection and release rebuilds.

``--overdue`` fails on passed dates. The weekly ``Documentation freshness``
workflow runs it on ``main``, so overdue pages surface as one visible failure
that the doc-gardening procedure in ``docs/README.md`` resolves: re-verify the
page against the code, repair any drift, and move ``review_by`` forward.
Dates are compared in UTC so local runs and CI agree.
"""

from __future__ import annotations

import argparse
import datetime
from collections.abc import Sequence
from pathlib import Path

import yaml

KNOWLEDGE = Path("docs") / "knowledge"
HANDOVERS = Path("docs") / "agent" / "handovers"
UNFINISHED = frozenset({"draft", "active", "blocked"})
HANDOVER_BUDGET = 64 * 1024
WARN_DAYS = 14


def _frontmatter(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
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


def living_documents(root: Path) -> list[tuple[Path, dict[str, object]]]:
    """Return the documents that must carry ``review_by``, sorted."""
    documents: list[tuple[Path, dict[str, object]]] = []
    for path in sorted((root / KNOWLEDGE).rglob("*.md")):
        if path.name != "index.md":
            documents.append((path, _frontmatter(path)))
    for path in sorted((root / HANDOVERS).glob("*.md")):
        if path.name in {"index.md", "README.md"}:
            continue
        data = _frontmatter(path)
        if data.get("status") in UNFINISHED:
            documents.append((path, data))
    return documents


def check(
    root: Path, today: datetime.date, *, overdue: bool = False
) -> tuple[list[str], list[str]]:
    """Return ``(errors, warnings)`` for the tree at *root* as of *today*."""
    errors: list[str] = []
    warnings: list[str] = []
    for path, data in living_documents(root):
        relative = path.relative_to(root).as_posix()
        value = data.get("review_by")
        if isinstance(value, datetime.datetime) or not isinstance(value, datetime.date):
            errors.append(f"{relative}: missing or malformed review_by (YYYY-MM-DD)")
        elif value < today:
            message = (
                f"{relative}: review_by {value.isoformat()} has passed — re-verify"
                " the page against the code, repair any drift, and move"
                " review_by forward"
            )
            (errors if overdue else warnings).append(message)
        elif (value - today).days <= WARN_DAYS:
            warnings.append(f"{relative}: review_by {value.isoformat()} is near")
        if relative.startswith(HANDOVERS.as_posix()):
            size = len(path.read_bytes())
            if size > HANDOVER_BUDGET:
                errors.append(
                    f"{relative}: {size} bytes exceeds the {HANDOVER_BUDGET}-byte"
                    " working-handover budget — move completed phases into an"
                    " archived record and leave a pointer"
                )
    return errors, warnings


def utc_today() -> datetime.date:
    return datetime.datetime.now(datetime.UTC).date()


def main(argv: Sequence[str] | None = None, today: datetime.date | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check documentation freshness.")
    parser.add_argument(
        "--overdue", action="store_true", help="fail on passed review_by dates"
    )
    args = parser.parse_args(argv)
    errors, warnings = check(Path(), today or utc_today(), overdue=args.overdue)
    for warning in warnings:
        print(f"warning: {warning}")
    if errors:
        print("\n".join(errors))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
