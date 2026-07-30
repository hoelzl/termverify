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
2. **ADR status vocabulary**: every ``- **Status:**`` line under
   ``docs/agent/design/`` opens with a closed vocabulary token, so a stale
   ``proposed`` cannot linger unremarked (the drift the 2026-07-24 review
   found on the JSONL transport ADR) and novel status wording cannot creep
   in unreviewed.
3. **Registry counts**: prose that states a key-registry size must state
   the size the package ships (the 934 → 1,382 drift the review found in a
   handover). A claim site that disappears fails loudly: the claim table
   below and the prose move in lockstep, never independently.
"""

from __future__ import annotations

import re
import tomllib
from collections.abc import Sequence
from pathlib import Path

from termverify._key_encoding_v1 import all_key_chords
from termverify._key_v1 import KEY_NAMES

#: Closed ADR status vocabulary. ``findings`` covers imported review
#: reports that live under design/ without being decision records.
ADR_STATUS_TOKENS = frozenset(
    {"proposed", "accepted", "superseded", "rejected", "findings"}
)

_STATUS_PREFIX = "- **Status:**"

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
        changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
        if f"## [{version}] - " not in changelog:
            errors.append(
                f"pyproject.toml: version {version} carries no .dev marker,"
                f" but CHANGELOG.md has no release section for it — between"
                " releases main carries the next planned version as"
                " X.Y.Z.dev0 (docs/developer-guide/release.md)"
            )
    return errors


def validate_adr_status(root: Path) -> list[str]:
    """Return status-vocabulary violations under ``docs/agent/design``."""
    errors: list[str] = []
    for path in sorted((root / "docs" / "agent" / "design").glob("*.md")):
        for number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if not line.startswith(_STATUS_PREFIX):
                continue
            rest = line[len(_STATUS_PREFIX) :].strip()
            token = rest.split()[0].rstrip(",.;:") if rest else ""
            if token not in ADR_STATUS_TOKENS:
                errors.append(
                    f"{path}:{number}: status token {token!r} is outside the"
                    f" vocabulary {sorted(ADR_STATUS_TOKENS)}"
                )
    return errors


def validate_registry_counts(root: Path) -> list[str]:
    """Return registry-count violations for the claim sites at *root*."""
    expected = {"names": len(KEY_NAMES), "chords": len(all_key_chords())}
    errors: list[str] = []
    for relative, pattern, kind in REGISTRY_COUNT_CLAIMS:
        text = (root / relative).read_text(encoding="utf-8")
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
        + validate_adr_status(root)
        + validate_registry_counts(root)
    )
    if errors:
        print("\n".join(errors))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
