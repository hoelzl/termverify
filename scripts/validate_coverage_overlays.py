"""Validate that the per-OS coverage overlays stay in sync with pyproject.toml.

The CI quality legs select ``coverage-windows.toml`` /
``coverage-posix.toml`` via ``COVERAGE_RCFILE`` (issue #230). Coverage reads
exactly one rcfile, so each overlay repeats the gating settings from
``pyproject.toml [tool.coverage]`` — and no pytest invocation ever compares
the copies, so drift would stay invisible (review finding on #241). This
validator is the mechanical check: shared keys must match, and each
overlay's ``exclude_also`` must select exactly its own platform marker.

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
SHARED_RUN_KEYS = ("branch", "source", "omit")
SHARED_REPORT_KEYS = ("show_missing", "skip_covered", "fail_under", "precision")


def _coverage_sections(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    document = tomllib.loads(path.read_text(encoding="utf-8"))
    coverage = document.get("tool", {}).get("coverage", {})
    return coverage.get("run", {}), coverage.get("report", {})


def validate_coverage_overlays(repository_root: Path) -> list[str]:
    """Return overlay-consistency violations below *repository_root*."""
    pyproject_path = repository_root / PYPROJECT
    if not pyproject_path.exists():
        return [f"{PYPROJECT} is missing"]
    base_run, base_report = _coverage_sections(pyproject_path)

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
        overlay_run, overlay_report = _coverage_sections(path)
        for key in SHARED_RUN_KEYS:
            if overlay_run.get(key) != base_run.get(key):
                errors.append(
                    f"{relative}: [tool.coverage.run] {key} = "
                    f"{overlay_run.get(key)!r} does not match pyproject.toml "
                    f"({base_run.get(key)!r})"
                )
        for key in SHARED_REPORT_KEYS:
            if overlay_report.get(key) != base_report.get(key):
                errors.append(
                    f"{relative}: [tool.coverage.report] {key} = "
                    f"{overlay_report.get(key)!r} does not match pyproject.toml "
                    f"({base_report.get(key)!r})"
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
