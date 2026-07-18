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
import time
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import cast

CANONICAL_BASE_URL = "https://termverify.dev"
FETCH_TIMEOUT_SECONDS = 30.0
FETCH_ATTEMPTS = 8
FETCH_RETRY_DELAY_SECONDS = 15.0

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


def published_url(base_url: str, resource: Path) -> str:
    """Return the canonical published URL for one schema resource."""
    return f"{base_url.rstrip('/')}/{_SITE_SCHEMA_PREFIX}/{resource.as_posix()}"


def verify_with_retry(
    url: str,
    committed: bytes,
    *,
    fetcher: Callable[[str], bytes],
    attempts: int = FETCH_ATTEMPTS,
    delay_seconds: float = FETCH_RETRY_DELAY_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Verify one published schema, retrying transient errors and stale bytes.

    Retries cover both fetch failures (fresh deployment, DNS or TLS not yet
    settled) and byte mismatches (CDN still serving the previous deployment).
    The final attempt's failure propagates unchanged.
    """
    for attempt in range(attempts):
        if attempt:
            sleep(delay_seconds)
        try:
            verify_published_bytes(url, fetcher(url), committed)
        except (OSError, AssertionError):
            if attempt == attempts - 1:
                raise
        else:
            return


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
        url = published_url(arguments.base_url, resource)
        committed = (arguments.schemas_root / resource).read_bytes()
        verify_with_retry(url, committed, fetcher=_fetch)
        print(f"byte-identical: {url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
