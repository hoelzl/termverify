"""Assemble the static termverify.dev site for GitHub Pages deployment.

The published site is a pure function of committed repository content: every
schema resource under ``src/termverify/schemas`` is copied byte-for-byte to
``/schemas/<protocol>/<version>.schema.json`` and a minimal landing page is
generated. The build fails closed on any unexpected file so a stray artifact
can never be published, and it refuses a non-empty output directory so stale
content can never leak into a deployment.

This is deploy-workflow tooling only. It never joins the required build/test
path, and nothing in the library depends on it.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

CANONICAL_BASE_URL = "https://termverify.dev"
SITE_SCHEMA_PREFIX = "schemas"
DEFAULT_SCHEMAS_ROOT = Path("src/termverify/schemas")

_PROTOCOL_DIRECTORY = re.compile(r"^[a-z0-9._-]+$")
_SCHEMA_FILE = re.compile(r"^v[1-9][0-9]*\.schema\.json$")


def discover_schema_resources(schemas_root: Path) -> tuple[Path, ...]:
    """Return committed schema resources relative to ``schemas_root``.

    Every file must sit exactly one directory deep as
    ``<protocol>/<version>.schema.json``; anything else fails closed.
    """
    if not schemas_root.is_dir():
        raise ValueError(f"schema root {schemas_root} is not a directory")
    resources: list[Path] = []
    for path in sorted(schemas_root.rglob("*")):
        if path.is_symlink():
            relative = path.relative_to(schemas_root)
            raise ValueError(
                f"symlink in schema tree: {relative.as_posix()!r};"
                " only regular files are publishable"
            )
        if path.is_dir():
            continue
        relative = path.relative_to(schemas_root)
        if not (
            len(relative.parts) == 2
            and _PROTOCOL_DIRECTORY.match(relative.parts[0]) is not None
            and _SCHEMA_FILE.match(relative.parts[1]) is not None
        ):
            raise ValueError(
                f"unexpected file in schema tree: {relative.as_posix()!r};"
                " only <protocol>/<version>.schema.json is publishable"
            )
        resources.append(relative)
    if not resources:
        raise ValueError(f"no schema resources found under {schemas_root}")
    return tuple(resources)


def _landing_page(published: tuple[str, ...]) -> str:
    links = "\n".join(
        f'      <li><a href="/{path}">{CANONICAL_BASE_URL}/{path}</a></li>'
        for path in published
    )
    return f"""<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>TermVerify</title>
  </head>
  <body>
    <h1>TermVerify</h1>
    <p>
      A Python library and reference tooling for verifying autonomous
      terminal applications: deterministic behavior, replayable evidence,
      and human review as product features.
    </p>
    <p>
      Source, documentation, and issues:
      <a href="https://github.com/hoelzl/termverify">github.com/hoelzl/termverify</a>
    </p>
    <h2>Canonical schemas</h2>
    <ul>
{links}
    </ul>
    <p>
      Schemas published here mirror the committed repository resources
      byte-for-byte. They are non-exhaustive structural aids; runtime
      validation remains authoritative for protocol acceptance.
    </p>
  </body>
</html>
"""


def build_site(schemas_root: Path, output_dir: Path) -> tuple[str, ...]:
    """Build the site into ``output_dir`` and return published schema paths."""
    if output_dir.exists():
        if not output_dir.is_dir():
            raise ValueError(f"output path {output_dir} is not a directory")
        if any(output_dir.iterdir()):
            raise ValueError(f"output directory {output_dir} is not empty")
    resources = discover_schema_resources(schemas_root)
    published = tuple(
        f"{SITE_SCHEMA_PREFIX}/{resource.as_posix()}" for resource in resources
    )
    for resource in resources:
        target = output_dir / SITE_SCHEMA_PREFIX / resource
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(schemas_root / resource, target)
    (output_dir / "index.html").write_text(
        _landing_page(published), encoding="utf-8", newline="\n"
    )
    return published


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "output_dir",
        type=Path,
        help="directory to assemble the site into (must be absent or empty)",
    )
    parser.add_argument(
        "--schemas-root",
        type=Path,
        default=DEFAULT_SCHEMAS_ROOT,
        help="committed schema resource tree (default: %(default)s)",
    )
    arguments = parser.parse_args()
    published = build_site(arguments.schemas_root, arguments.output_dir)
    for path in published:
        print(f"published {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
