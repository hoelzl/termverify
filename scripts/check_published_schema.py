"""Verify that every published termverify.dev schema is byte-identical to
the committed resource.

Run by the Pages deploy workflow after deployment. A mismatch fails the
workflow so a drifted or hand-edited publication can never exist silently.
This check is deploy-workflow tooling only: it never joins the required
build/test path, and a site outage has no effect on library correctness.
"""

from __future__ import annotations

import argparse
import runpy
import sys
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import cast

CANONICAL_BASE_URL = "https://termverify.dev"
FETCH_TIMEOUT_SECONDS = 30.0

_BUILDER = runpy.run_path(
    str(Path(__file__).with_name("build_site.py")),
    run_name="site_builder",
)
_discover_schema_resources = cast(
    Callable[[Path], tuple[Path, ...]], _BUILDER["discover_schema_resources"]
)
_DEFAULT_SCHEMAS_ROOT = cast(Path, _BUILDER["DEFAULT_SCHEMAS_ROOT"])
_SITE_SCHEMA_PREFIX = cast(str, _BUILDER["SITE_SCHEMA_PREFIX"])


def verify_published_bytes(url: str, published: bytes, committed: bytes) -> None:
    """Fail unless the published bytes equal the committed bytes exactly."""
    if published != committed:
        raise AssertionError(
            f"published schema at {url} does not match the committed resource:"
            f" published {len(published)} bytes, committed {len(committed)} bytes"
        )


def _fetch(url: str) -> bytes:
    if not url.startswith("https://"):
        raise ValueError(f"refusing non-HTTPS canonical URL: {url}")
    with urllib.request.urlopen(  # noqa: S310 - HTTPS enforced above
        url, timeout=FETCH_TIMEOUT_SECONDS
    ) as response:
        return cast(bytes, response.read())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default=CANONICAL_BASE_URL,
        help="published site origin (default: %(default)s)",
    )
    parser.add_argument(
        "--schemas-root",
        type=Path,
        default=_DEFAULT_SCHEMAS_ROOT,
        help="committed schema resource tree (default: %(default)s)",
    )
    arguments = parser.parse_args()

    for resource in _discover_schema_resources(arguments.schemas_root):
        url = f"{arguments.base_url}/{_SITE_SCHEMA_PREFIX}/{resource.as_posix()}"
        committed = (arguments.schemas_root / resource).read_bytes()
        verify_published_bytes(url, _fetch(url), committed)
        print(f"byte-identical: {url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
