"""Drift-driven prose-status validator (owner decision 2026-07-24, Slice 8.4).

Three checks, each born from an observed drift, none aspiring to general
prose understanding:

1. **Version discipline** for the manual ``.dev0`` marker scheme:
   ``[project] version`` and ``[tool.bumpversion] current_version`` must
   agree, and a version *without* the marker is allowed only when
   ``CHANGELOG.md`` carries its release section — the shape a release
   branch has after the collect-then-strip steps in
   ``docs/developer-guide/release.md``. The marker requirement between
   releases is checklist policy; this check pins the consistency that
   policy relies on, without blocking the sanctioned release flow.
2. **Registry counts**: prose that states a key-registry size must state
   the size the package ships (the 934 → 1,382 drift the review found in a
   handover). A claim site that disappears fails loudly: the claim table
   below and the prose move in lockstep, never independently.
3. **Always-on budget**: ``AGENTS.md`` and ``CLAUDE.md`` are injected into
   every agent request, so their size is a per-request context cost that
   grows one helpful paragraph at a time (issue #322). The budget counts
   UTF-8 bytes; task-specific detail moves to an on-demand page and leaves
   a one-line pointer.

The ADR status-vocabulary check that used to live here moved to
``scripts/validate_agent_docs.py``, which validates machine-readable
frontmatter on every agent record instead of free-form status bullets
(issue #322).
"""

from __future__ import annotations

import re
import tomllib
from collections.abc import Sequence
from pathlib import Path

from termverify._key_encoding_v1 import all_key_chords
from termverify._key_v1 import KEY_NAMES

#: (relative path, claim pattern with one numeric group, expected count
#: callable) — one row per prose site that states a registry size.
REGISTRY_COUNT_CLAIMS: tuple[tuple[str, str, str], ...] = (
    ("docs/knowledge/protocol.md", r"registry has (\d+) entries", "names"),
    ("docs/knowledge/protocol.md", r"each of the (\d+) valid", "chords"),
    (
        "docs/agent/design/key-to-terminal-byte-mapping.md",
        r"admits exactly (\d+) chords",
        "chords",
    ),
    (
        "docs/agent/design/key-to-terminal-byte-mapping.md",
        r"over all (\d+) valid chords",
        "chords",
    ),
)


#: Byte budgets for the files every agent harness loads on every request.
ALWAYS_ON_BUDGETS: dict[str, int] = {"AGENTS.md": 4096, "CLAUDE.md": 1024}


def validate_always_on_budget(root: Path) -> list[str]:
    """Return budget violations for the always-loaded instruction files."""
    errors: list[str] = []
    for relative, budget in ALWAYS_ON_BUDGETS.items():
        path = root / relative
        if not path.is_file():
            errors.append(f"{relative}: missing")
            continue
        size = len(path.read_bytes())
        if size > budget:
            errors.append(
                f"{relative}: {size} bytes exceeds the always-on budget of"
                f" {budget} — move task-specific detail to an on-demand page"
                " (placement rules: docs/README.md) and leave a one-line"
                " pointer"
            )
    return errors


def validate_version_discipline(root: Path) -> list[str]:
    """Return version-discipline violations for the tree at *root*."""
    with (root / "pyproject.toml").open("rb") as stream:
        pyproject = tomllib.load(stream)
    version = pyproject["project"]["version"]
    current = pyproject["tool"]["bumpversion"]["current_version"]
    errors: list[str] = []
    if version != current:
        errors.append(
            f"pyproject.toml: [project] version {version} disagrees with"
            f" [tool.bumpversion] current_version {current}"
        )
    if ".dev" not in version:
        changelog_path = root / "CHANGELOG.md"
        if not changelog_path.is_file():
            errors.append(f"{changelog_path}: missing")
            return errors
        changelog = changelog_path.read_text(encoding="utf-8")
        if f"## [{version}] - " not in changelog:
            errors.append(
                f"pyproject.toml: version {version} carries no .dev marker,"
                f" but CHANGELOG.md has no release section for it — between"
                " releases main carries the next planned version as"
                " X.Y.Z.dev0 (docs/developer-guide/release.md)"
            )
    return errors


def validate_registry_counts(root: Path) -> list[str]:
    """Return registry-count violations for the claim sites at *root*."""
    expected = {"names": len(KEY_NAMES), "chords": len(all_key_chords())}
    errors: list[str] = []
    for relative, pattern, kind in REGISTRY_COUNT_CLAIMS:
        path = root / relative
        if not path.is_file():
            errors.append(
                f"{relative}: missing — update REGISTRY_COUNT_CLAIMS in"
                " scripts/validate_prose_status.py together with the prose"
            )
            continue
        text = path.read_text(encoding="utf-8")
        matches = re.findall(pattern, text)
        if not matches:
            errors.append(
                f"{relative}: claim pattern {pattern!r} not found — update"
                " REGISTRY_COUNT_CLAIMS in scripts/validate_prose_status.py"
                " together with the prose"
            )
            continue
        errors.extend(
            f"{relative}: states {stated} where the shipped registry has"
            f" {expected[kind]}"
            for stated in matches
            if int(stated) != expected[kind]
        )
    return errors


def main(argv: Sequence[str] | None = None) -> int:
    del argv
    root = Path()
    errors = (
        validate_version_discipline(root)
        + validate_registry_counts(root)
        + validate_always_on_budget(root)
    )
    if errors:
        print("\n".join(errors))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
