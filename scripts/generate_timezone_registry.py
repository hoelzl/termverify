"""Regenerate the protocol-owned v1 timezone-name module from pinned TZDB data."""

from __future__ import annotations

import argparse
import hashlib
import json
import tarfile
from collections.abc import Sequence
from pathlib import Path

TZDB_VERSION = "2026c"
TZDB_SOURCE_URL = "https://data.iana.org/time-zones/releases/tzdata2026c.tar.gz"
TZDB_SHA256 = "e4a178a4477f3d0ea77cc31828ff72aa38feff8d61aa13e7e99e142e9d902be4"
TZDB_ZONE_SOURCES = (
    "africa",
    "antarctica",
    "asia",
    "australasia",
    "europe",
    "northamerica",
    "southamerica",
    "etcetera",
)
DEFAULT_OUTPUT = Path("src/termverify/_timezone_v1.py")


def _read_member(archive: tarfile.TarFile, name: str) -> str:
    member = archive.extractfile(name)
    if member is None:
        raise ValueError(f"TZDB archive is missing {name}")
    return member.read().decode("utf-8")


def extract_timezone_names(source: Path) -> tuple[str, ...]:
    """Return sorted primary ``Zone`` names plus the v1 ``UTC`` sentinel."""
    names = ["UTC"]
    with tarfile.open(source) as archive:
        version = _read_member(archive, "version").strip()
        if version != TZDB_VERSION:
            raise ValueError(f"expected TZDB {TZDB_VERSION}, found {version}")
        for source_name in TZDB_ZONE_SOURCES:
            for line in _read_member(archive, source_name).splitlines():
                fields = line.split()
                if fields and fields[0] == "Zone":
                    names.append(fields[1])
    if len(names) != len(set(names)):
        raise ValueError("TZDB primary Zone names are not unique")
    return tuple(sorted(names))


def _render_module(names: tuple[str, ...]) -> str:
    entries = "\n".join(f"    {json.dumps(name)}," for name in names)
    sources = "\n".join(f"    {json.dumps(name)}," for name in TZDB_ZONE_SOURCES)
    return f'''\
"""Protocol-owned canonical timezone names for `termverify.transcript/v1`.

Generated from IANA TZDB 2026c by selecting ``Zone`` directives from the
primary regional sources named in ``_TZDB_ZONE_SOURCES`` and adding the v1
``UTC`` sentinel. ``Link`` aliases, ``backzone``, and ``factory`` are excluded.
"""

from __future__ import annotations

from typing import TypeGuard

TZDB_VERSION = "{TZDB_VERSION}"
TZDB_SOURCE_URL = "{TZDB_SOURCE_URL}"
TZDB_SHA256 = "{TZDB_SHA256}"
_TZDB_ZONE_SOURCES = (
{sources}
)

TIMEZONE_NAMES: tuple[str, ...] = (
{entries}
)
_TIMEZONE_NAME_SET = frozenset(TIMEZONE_NAMES)


def is_timezone_name(value: object) -> TypeGuard[str]:
    """Return whether *value* is an exact v1 canonical timezone name."""
    return type(value) is str and value in _TIMEZONE_NAME_SET
'''


def _sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    if _sha256(args.source) != TZDB_SHA256:
        parser.error(f"source must match {TZDB_SOURCE_URL} with SHA-256 {TZDB_SHA256}")
    names = extract_timezone_names(args.source)
    args.output.write_text(_render_module(names), encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
