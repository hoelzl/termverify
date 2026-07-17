from __future__ import annotations

import io
import runpy
import tarfile
from collections.abc import Callable
from pathlib import Path
from typing import cast

_GENERATOR = runpy.run_path(
    str(Path("scripts/generate_timezone_registry.py")),
    run_name="timezone_registry_generator",
)
TZDB_ZONE_SOURCES = cast(tuple[str, ...], _GENERATOR["TZDB_ZONE_SOURCES"])
extract_timezone_names = cast(
    Callable[[Path], tuple[str, ...]], _GENERATOR["extract_timezone_names"]
)


def _add_text(archive: tarfile.TarFile, name: str, text: str) -> None:
    data = text.encode("utf-8")
    info = tarfile.TarInfo(name)
    info.size = len(data)
    archive.addfile(info, io.BytesIO(data))


def test_extraction_selects_primary_zone_directives_and_utc_sentinel(
    tmp_path: Path,
) -> None:
    source = tmp_path / "tzdata.tar.gz"
    with tarfile.open(source, "w:gz") as archive:
        _add_text(archive, "version", "2026c\n")
        for name in TZDB_ZONE_SOURCES:
            content = (
                "Zone Africa/Canonical 0 - UTC\nLink Africa/Canonical Africa/Alias\n"
                if name == "africa"
                else ""
            )
            _add_text(archive, name, content)
        _add_text(archive, "backzone", "Zone Africa/Backzone 0 - UTC\n")
        _add_text(archive, "backward", "Link Africa/Canonical Legacy/Alias\n")
        _add_text(archive, "factory", "Zone Factory 0 - -00\n")

    assert extract_timezone_names(source) == ("Africa/Canonical", "UTC")
