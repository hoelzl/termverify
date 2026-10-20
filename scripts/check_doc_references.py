#!/usr/bin/env python3
"""Check that documentation references resolve.

Usage:
    uv --no-config run python scripts/check_doc_references.py

Two kinds of reference are checked in every Markdown file outside the
exclusions below and outside dot-directories other than ``.agents/`` and
``.github/`` (issue #322):

1. **Relative Markdown links** — inline ``[text](path#anchor "title")``,
   angle-bracket ``[text](<path>)``, and reference definitions
   ``[ref]: path``. The target must exist with exactly this spelling —
   case-sensitively, as on Linux CI and GitHub, even on a case-insensitive
   file system — and an anchor into a Markdown file must name one of its ATX
   headings (GitHub slug rules: lowercase, punctuation dropped, spaces to
   hyphens). Image links and raw HTML are not checked.
2. **Backticked repository paths** — `` `src/termverify/x.py` `` and the
   like, starting with a top-level repository directory. Agents follow these
   as lightweight identifiers, so a renamed file must not leave them dangling.
   Globs and placeholders (``*``, ``<``, ``{``) are skipped.

References inside fenced code blocks are skipped. Historical records that
must keep citing a removed path list it in ``ALLOWED_MISSING`` with the
reason; the allowance is per path, never per file.
"""

from __future__ import annotations

import os
import re
import unicodedata
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from urllib.parse import unquote

#: Markdown trees that are point-in-time history, not navigation.
EXCLUDED_PREFIXES = (
    ".venv/",
    ".git/",
    "CHANGELOG.md",
    "changelog.d/",
    "docs/agent/handovers/archive/",
    "site/",
    ".site-docs/",
    "tests/fixtures/external/",
)

#: Dot-directories whose Markdown is project documentation.
VISIBLE_DOT_DIRECTORIES = frozenset({".agents", ".github"})

#: Top-level directories a backticked path may start with.
REPO_ROOTS = (
    "src/",
    "tests/",
    "scripts/",
    "docs/",
    ".github/",
    "spikes/",
    "changelog.d/",
    ".agents/",
)

#: Paths that are cited on purpose although they do not exist, with reasons.
ALLOWED_MISSING: Mapping[str, str] = {
    "tests/fixtures/baselines/": "reserved location of the disabled baseline store",
    "examples/": "planned examples directory of the POSIX vertical (issue #204)",
    "artifacts/": "disabled report root guarded by validate_evidence_governance.py",
    "reports/": "disabled report root guarded by validate_evidence_governance.py",
    "src/termverify/conpty.py": (
        "renamed to terminal.py by #268; records keep the old path"
        " (docs/knowledge/glossary.md)"
    ),
    ".github/copilot-instructions.md": (
        "deliberately not shipped (docs/developer-guide/agent-harnesses.md)"
    ),
    ".agents/skills/": "reserved for proven skills; created by phase 7 of #322",
}

_LINK = re.compile(r"(?<!!)\[[^\]]*\]\(\s*(<[^>]+>|[^)\s]+)(?:\s+\"[^\"]*\")?\s*\)")
_DEFINITION = re.compile(r"^\s{0,3}\[[^\]]+\]:\s*(<[^>]+>|\S+)")
_CODE = re.compile(r"`([^`\n]+)`")
_EXTERNAL = re.compile(r"^(?:[a-z][a-z0-9+.-]*:|//)", re.IGNORECASE)
_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")


def slugify(heading: str) -> str:
    """Return the GitHub/MkDocs-style anchor slug of a heading's text."""
    text = heading.replace("`", "").replace("*", "")
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = unicodedata.normalize("NFKC", text).strip().lower()
    text = "".join(ch for ch in text if ch.isalnum() or ch in " -_")
    return text.replace(" ", "-")


def markdown_lines(text: str) -> Iterator[tuple[int, str]]:
    """Yield ``(line number, line)`` outside fenced code and frontmatter."""
    in_fence = False
    lines = text.splitlines()
    start = 0
    if lines and lines[0] == "---":
        for index in range(1, len(lines)):
            if lines[index] == "---":
                start = index + 1
                break
    for number, line in enumerate(lines[start:], start=start + 1):
        if line.lstrip().startswith(("```", "~~~")):
            in_fence = not in_fence
            continue
        if not in_fence:
            yield number, line


def anchors(path: Path) -> set[str]:
    """Return the heading anchors of the Markdown file at *path*."""
    seen: dict[str, int] = {}
    result: set[str] = set()
    for _, line in markdown_lines(path.read_text(encoding="utf-8")):
        match = _HEADING.match(line)
        if not match:
            continue
        slug = slugify(match.group(2))
        count = seen.get(slug, 0)
        seen[slug] = count + 1
        result.add(slug if count == 0 else f"{slug}-{count}")
    return result


def exists_exactly(path: Path) -> bool:
    """Return whether *path* exists with exactly this spelling of every part."""
    absolute = Path(os.path.abspath(path))
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        try:
            names = os.listdir(current)
        except OSError:
            return False
        if part not in names:
            return False
        current = current / part
    return True


def _link_target(raw: str) -> str:
    target = raw[1:-1] if raw.startswith("<") and raw.endswith(">") else raw
    return unquote(target.split("?", 1)[0])


def _allowed(target: str) -> bool:
    return any(
        target == allowed or target.startswith(allowed) for allowed in ALLOWED_MISSING
    )


def check_file(root: Path, path: Path) -> list[str]:
    """Return unresolved references in the Markdown file at *path*."""
    relative = path.relative_to(root).as_posix()
    errors: list[str] = []
    text = path.read_text(encoding="utf-8")
    for number, line in markdown_lines(text):
        prose = _CODE.sub("``", line)
        targets = _LINK.findall(prose) + _DEFINITION.findall(prose)
        for raw in targets:
            target = _link_target(raw)
            if _EXTERNAL.match(target):
                continue
            file_part, _, anchor = target.partition("#")
            resolved = path.parent / file_part if file_part else path
            if file_part and not exists_exactly(resolved):
                errors.append(f"{relative}:{number}: broken link {target}")
                continue
            if (
                anchor
                and resolved.suffix == ".md"
                and resolved.is_file()
                and anchor not in anchors(resolved)
            ):
                errors.append(f"{relative}:{number}: missing anchor {target}")
        for code in _CODE.findall(line):
            candidate = code.strip().split(":")[0].rstrip(".,;")
            if not candidate.startswith(REPO_ROOTS) or any(
                ch in candidate for ch in "*<>{} "
            ):
                continue
            if not exists_exactly(root / candidate) and not _allowed(candidate):
                errors.append(f"{relative}:{number}: missing path `{candidate}`")
    return errors


def markdown_files(root: Path) -> list[Path]:
    """Return the Markdown files to check, sorted."""
    files: list[Path] = []
    for path in sorted(root.rglob("*.md")):
        relative = path.relative_to(root).as_posix()
        if relative.startswith(EXCLUDED_PREFIXES) or "/node_modules/" in relative:
            continue
        hidden = [part for part in Path(relative).parts[:-1] if part.startswith(".")]
        if any(part not in VISIBLE_DOT_DIRECTORIES for part in hidden):
            continue
        files.append(path)
    return files


def check(root: Path) -> list[str]:
    """Return every unresolved reference under *root*."""
    errors: list[str] = []
    for path in markdown_files(root):
        errors.extend(check_file(root, path))
    return errors


def main(argv: Sequence[str] | None = None) -> int:
    del argv
    errors = check(Path())
    if errors:
        print("\n".join(errors))
        print(
            "Fix the reference, or — only for a historical record that must"
            " keep citing a removed path — add the path with its reason to"
            " ALLOWED_MISSING in scripts/check_doc_references.py."
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
