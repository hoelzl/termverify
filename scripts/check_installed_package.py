"""Check the installed termverify artifact against its distribution contract.

Run with an isolated interpreter whose only termverify comes from a built
wheel or sdist (for example ``uv run --no-project --with ./dist/*.whl``), so
every assertion below is evidence about the installed artifact rather than
the repository checkout.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "reference_schema",
        type=Path,
        help="repository path of the canonical committed v1 transcript schema",
    )
    arguments = parser.parse_args()

    import termverify
    from termverify.transcript import parse_transcript, serialize_transcript

    imported_from = Path(termverify.__file__ or "").resolve()
    repository_package = arguments.reference_schema.resolve().parents[2]
    if repository_package in imported_from.parents:
        raise AssertionError(
            "termverify was imported from the repository checkout, not an"
            " installed artifact; run with an isolated interpreter such as"
            " uv run --no-project --with <artifact>"
        )
    if termverify.__version__ != importlib.metadata.version("termverify"):
        raise AssertionError("installed version does not match package metadata")
    for callable_value in (
        parse_transcript,
        serialize_transcript,
        termverify.persist_transcript_evidence,
    ):
        if not callable(callable_value):
            raise AssertionError("installed public callable is missing")

    installed_bytes = termverify.transcript_schema_v1_bytes()
    reference_bytes = arguments.reference_schema.read_bytes()
    if installed_bytes != reference_bytes:
        raise AssertionError(
            "installed schema resource does not match the committed schema"
        )
    if json.loads(installed_bytes)["$id"] != termverify.TRANSCRIPT_SCHEMA_V1_ID:
        raise AssertionError("installed schema $id does not match the documented id")
    if termverify.transcript_schema_v1_json() != json.loads(reference_bytes):
        raise AssertionError("parsed installed schema does not match the committed one")

    print("installed package contract checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
