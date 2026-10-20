"""Validate the metadata contract of agent records under ``docs/agent/``.

Every record — decision, assessment, review, plan, prompt, handover — opens
with YAML frontmatter, so indexes can be generated from it and stale status
cannot hide in free-form prose (issue #322)::

    ---
    type: decision            # see STATUSES for the closed type set
    status: accepted          # closed vocabulary per type
    date: 2026-07-19          # when the record was made or decided
    summary: One line that says what the record decides or finds.
    issue: 146                # optional: the record's own issue
    supersedes: [docs/agent/design/old.md]        # optional
    superseded_by: docs/agent/design/new.md       # required when superseded
    ---

Paths in ``supersedes`` and ``superseded_by`` are repository-relative, point
at other existing records under ``docs/agent/``, and use forward slashes.
Unknown keys are rejected (a misspelled key would otherwise vanish from the
generated indexes), and an unquoted value containing `` #`` is rejected
because YAML silently truncates it at the comment. ``README.md`` and
``index.md`` files are navigation, not records, and are exempt.

The frontmatter status is the living status; a body ``- **Status:**``
bullet outside code fences must agree with it, except in reviews
(point-in-time reports that are never rewritten) and in superseded records
(whose bullet is history). The schema and its rationale are documented in
``docs/README.md``.
"""

from __future__ import annotations

import datetime
import re
from collections.abc import Mapping, Sequence
from pathlib import Path

import yaml

AGENT_DOCS = Path("docs") / "agent"
EXEMPT_FILENAMES = frozenset({"README.md", "index.md"})
REQUIRED_FIELDS = ("type", "status", "date", "summary")
OPTIONAL_FIELDS = frozenset({"issue", "supersedes", "superseded_by"})
#: Keys some review reports carried before the schema existed.
LEGACY_REVIEW_FIELDS = frozenset({"scope", "rounds", "verdicts", "subject"})

#: Closed status vocabulary per record type.
STATUSES: Mapping[str, frozenset[str]] = {
    "decision": frozenset({"proposed", "accepted", "superseded", "rejected"}),
    "assessment": frozenset({"current", "superseded"}),
    "review": frozenset({"findings", "resolved"}),
    "plan": frozenset({"active", "completed", "abandoned"}),
    "prompt": frozenset({"current", "retired"}),
    "handover": frozenset({"draft", "active", "blocked", "complete", "superseded"}),
}

#: Record types each top-level folder may hold. Reviews filed before
#: ``reviews/`` existed stay under ``design/`` (``reviews/README.md``).
FOLDER_TYPES: Mapping[str, frozenset[str]] = {
    "design": frozenset({"decision", "assessment", "review"}),
    "reviews": frozenset({"review"}),
    "plans": frozenset({"plan"}),
    "prompts": frozenset({"prompt"}),
    "handovers": frozenset({"handover"}),
}

#: Statuses that mean "finished". Records under an ``archive/`` folder must
#: carry one; a handover outside it must not (the handover lifecycle in
#: docs/developer-guide/agent-workflow.md archives finished handovers).
FINISHED: Mapping[str, frozenset[str]] = {
    "handover": frozenset({"complete", "superseded"}),
    "plan": frozenset({"completed", "abandoned"}),
    "prompt": frozenset({"retired"}),
}

_STATUS_BULLET = "- **Status:**"
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_PLAIN_SCALAR_WITH_COMMENT = re.compile(r"^[A-Za-z_]+:\s+[^'\"\s|>\[{].*\s#")


def read_frontmatter(path: Path) -> tuple[dict[str, object] | None, str, str]:
    """Return ``(frontmatter, body, error)`` for the record at *path*."""
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return None, text, "missing YAML frontmatter"
    end = text.find("\n---\n", 4)
    if end == -1:
        return None, text, "unterminated YAML frontmatter"
    raw = text[4:end]
    for line in raw.splitlines():
        if _PLAIN_SCALAR_WITH_COMMENT.match(line):
            return (
                None,
                text,
                (
                    f"unquoted value containing ' #' would be truncated by YAML:"
                    f" {line!r} — quote the value"
                ),
            )
    try:
        data = yaml.safe_load(raw)
    except (yaml.YAMLError, ValueError) as exc:
        return None, text, f"invalid YAML frontmatter: {exc}"
    if not isinstance(data, dict):
        return None, text, "frontmatter is not a mapping"
    return data, text[end + 5 :], ""


def _date_text(value: object) -> str:
    if isinstance(value, datetime.date):
        return value.isoformat()
    return str(value)


def _validate_record(root: Path, path: Path) -> list[str]:
    relative = path.relative_to(root).as_posix()
    data, body, error = read_frontmatter(path)
    if data is None:
        return [f"{relative}: {error}"]

    errors = [
        f"{relative}: missing required field {field!r}"
        for field in REQUIRED_FIELDS
        if data.get(field) in (None, "")
    ]
    if errors:
        return errors

    record_type = str(data["type"])
    status = str(data["status"])
    folder_parts = path.relative_to(root / AGENT_DOCS).parts
    folder = folder_parts[0]
    archived = "archive" in folder_parts[1:-1]

    allowed_keys = set(REQUIRED_FIELDS) | OPTIONAL_FIELDS
    if record_type == "review":
        allowed_keys |= LEGACY_REVIEW_FIELDS
    errors.extend(
        f"{relative}: unknown frontmatter key {key!r}; allowed:"
        f" {sorted(allowed_keys)} (docs/README.md)"
        for key in data
        if key not in allowed_keys
    )

    allowed_types = FOLDER_TYPES.get(folder)
    if allowed_types is None:
        errors.append(
            f"{relative}: unknown folder {folder!r}; records live in"
            f" {sorted(FOLDER_TYPES)} (docs/README.md)"
        )
    elif record_type not in allowed_types:
        errors.append(
            f"{relative}: type {record_type!r} does not belong in {folder}/;"
            f" allowed: {sorted(allowed_types)}"
        )
    vocabulary = STATUSES.get(record_type)
    if vocabulary is None:
        errors.append(
            f"{relative}: unknown type {record_type!r}; known: {sorted(STATUSES)}"
        )
    elif status not in vocabulary:
        errors.append(
            f"{relative}: status {status!r} is outside the {record_type}"
            f" vocabulary {sorted(vocabulary)}"
        )

    if not _DATE.fullmatch(_date_text(data["date"])):
        errors.append(f"{relative}: date must be YYYY-MM-DD")
    summary = data["summary"]
    if not isinstance(summary, str) or not summary.strip():
        errors.append(f"{relative}: summary must be a non-empty string")
    elif "\n" in summary.strip():
        errors.append(f"{relative}: summary must be a single line")
    issue = data.get("issue")
    if issue is not None and (
        isinstance(issue, bool) or not isinstance(issue, int) or issue < 1
    ):
        errors.append(f"{relative}: issue must be a positive issue number")

    errors.extend(_validate_supersession(root, relative, data, status))
    errors.extend(_validate_placement(relative, record_type, status, archived))
    if record_type != "review" and status != "superseded":
        errors.extend(_validate_status_bullet(relative, body, status))
    return errors


def _supersession_target_error(root: Path, relative: str, target: object) -> str:
    text = str(target)
    if not isinstance(target, str):
        return f"{relative}: supersession target {text} must be one path string"
    if text == relative:
        return f"{relative}: a record cannot supersede itself"
    if "\\" in text or not text.startswith(f"{AGENT_DOCS.as_posix()}/"):
        return (
            f"{relative}: supersession target {text} must be a forward-slash"
            " path to a record under docs/agent/"
        )
    if not (root / text).is_file():
        return f"{relative}: supersession target {text} does not exist"
    return ""


def _validate_supersession(
    root: Path, relative: str, data: Mapping[str, object], status: str
) -> list[str]:
    errors: list[str] = []
    successor = data.get("superseded_by")
    if status == "superseded" and not successor:
        errors.append(f"{relative}: status superseded requires superseded_by")
    if successor and status != "superseded":
        errors.append(
            f"{relative}: superseded_by is set but the status is {status!r},"
            " not 'superseded'"
        )
    targets: list[object] = []
    if successor:
        targets.append(successor)
    predecessors = data.get("supersedes") or []
    targets.extend(predecessors if isinstance(predecessors, list) else [predecessors])
    for target in targets:
        error = _supersession_target_error(root, relative, target)
        if error:
            errors.append(error)
    return errors


def _validate_placement(
    relative: str, record_type: str, status: str, archived: bool
) -> list[str]:
    finished = FINISHED.get(record_type)
    if finished is None:
        if archived:
            return [
                f"{relative}: {record_type} records are never archived; their"
                " paths stay stable (docs/README.md)"
            ]
        return []
    if archived and status not in finished:
        return [
            f"{relative}: records under archive/ must be finished"
            f" ({sorted(finished)}), not {status!r}"
        ]
    if record_type == "handover" and not archived and status in finished:
        return [
            f"{relative}: a {status} handover moves to handovers/archive/"
            " (docs/developer-guide/agent-workflow.md)"
        ]
    return []


def _validate_status_bullet(relative: str, body: str, status: str) -> list[str]:
    errors: list[str] = []
    in_fence = False
    for line in body.splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence or not line.startswith(_STATUS_BULLET):
            continue
        rest = line[len(_STATUS_BULLET) :].strip()
        token = rest.split()[0].rstrip(",.;:") if rest else ""
        if token != status:
            errors.append(
                f"{relative}: body status bullet says {token!r} but the"
                f" frontmatter status is {status!r}; the frontmatter is the"
                " living status — update the bullet to match"
            )
    return errors


def validate_agent_docs(root: Path) -> list[str]:
    """Return metadata violations for every record under ``docs/agent``."""
    errors: list[str] = []
    for path in sorted((root / AGENT_DOCS).rglob("*.md")):
        if path.name in EXEMPT_FILENAMES:
            continue
        errors.extend(_validate_record(root, path))
    return errors


def main(argv: Sequence[str] | None = None) -> int:
    del argv
    errors = validate_agent_docs(Path())
    if errors:
        print("\n".join(errors))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
