"""Validate that the per-OS coverage overlays stay in sync with pyproject.toml.

The CI quality legs select ``coverage-windows.toml`` /
``coverage-posix.toml`` via ``COVERAGE_RCFILE`` (issue #230). Coverage reads
exactly one rcfile, so each overlay repeats the gating settings from
``pyproject.toml [tool.coverage]`` — and no pytest invocation ever compares
the copies, so drift would stay invisible (review finding on #241). This
validator is the mechanical check: shared keys must match, and each
overlay's ``exclude_also`` must select exactly its own platform marker.

``conpty-coverage.toml`` (#236) is deliberately out of scope: it is a
supplemental, non-gating measurement with intentionally different settings,
not a copy of the gating configuration.

Exits 1 and prints one line per violation on mismatch; exits 0 when clean.
"""

from __future__ import annotations

import sys
import tomllib
from collections.abc import Sequence
from pathlib import Path
from typing import Any

PYPROJECT = Path("pyproject.toml")
LOCAL_EXCLUDE = "# coverage: exclude-(posix|windows)"
OVERLAYS = {
    Path("coverage-windows.toml"): "# coverage: exclude-windows",
    Path("coverage-posix.toml"): "# coverage: exclude-posix",
}


def _coverage_sections(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        document = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as error:
        raise ValueError(f"invalid TOML — {error}") from error
    coverage = document.get("tool", {}).get("coverage", {})
    return coverage.get("run", {}), coverage.get("report", {})


def validate_coverage_overlays(repository_root: Path) -> list[str]:
    """Return overlay-consistency violations below *repository_root*."""
    pyproject_path = repository_root / PYPROJECT
    if not pyproject_path.exists():
        return [f"{PYPROJECT} is missing"]
    try:
        base_run, base_report = _coverage_sections(pyproject_path)
    except ValueError as error:
        return [f"{PYPROJECT}: {error}"]

    errors: list[str] = []
    if base_report.get("exclude_also") != [LOCAL_EXCLUDE]:
        errors.append(
            f"{PYPROJECT}: [tool.coverage.report] exclude_also must be "
            f"[{LOCAL_EXCLUDE!r}] so local runs exclude both platform markers"
        )
    for relative, marker in OVERLAYS.items():
        path = repository_root / relative
        if not path.exists():
            errors.append(f"{relative} is missing")
            continue
        try:
            overlay_run, overlay_report = _coverage_sections(path)
        except ValueError as error:
            errors.append(f"{relative}: {error}")
            continue
        if set(overlay_run) != set(base_run):
            errors.append(
                f"{relative}: [tool.coverage.run] keys "
                f"{sorted(set(overlay_run) ^ set(base_run))} are not present "
                "in both the overlay and pyproject.toml"
            )
        if set(overlay_report) != set(base_report):
            errors.append(
                f"{relative}: [tool.coverage.report] keys "
                f"{sorted(set(overlay_report) ^ set(base_report))} are not "
                "present in both the overlay and pyproject.toml"
            )
        for key in sorted(set(overlay_run) & set(base_run)):
            if overlay_run[key] != base_run[key]:
                errors.append(
                    f"{relative}: [tool.coverage.run] {key} = "
                    f"{overlay_run[key]!r} does not match pyproject.toml "
                    f"({base_run[key]!r})"
                )
        for key in sorted((set(overlay_report) & set(base_report)) - {"exclude_also"}):
            if overlay_report[key] != base_report[key]:
                errors.append(
                    f"{relative}: [tool.coverage.report] {key} = "
                    f"{overlay_report[key]!r} does not match pyproject.toml "
                    f"({base_report[key]!r})"
                )
        if overlay_report.get("exclude_also") != [marker]:
            errors.append(
                f"{relative}: [tool.coverage.report] exclude_also must be "
                f"[{marker!r}] — the overlay must exclude exactly the legs "
                "that cannot run on its platform"
            )
    return errors


def main(argv: Sequence[str] | None = None) -> int:
    del argv  # the validator always checks the current working tree
    errors = validate_coverage_overlays(Path.cwd())
    for error in errors:
        print(f"coverage overlay drift: {error}")
    if errors:
        return 1
    print("coverage overlays are consistent with pyproject.toml")
    return 0


if __name__ == "__main__":
    sys.exit(main())
