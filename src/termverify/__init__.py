"""Protocol-driven verification for autonomous terminal applications."""

from importlib.metadata import version

from termverify.evidence import persist_transcript_evidence
from termverify.schema import (
    TRANSCRIPT_SCHEMA_V1_ID,
    transcript_schema_v1_bytes,
    transcript_schema_v1_json,
)

__all__ = [
    "TRANSCRIPT_SCHEMA_V1_ID",
    "__version__",
    "persist_transcript_evidence",
    "transcript_schema_v1_bytes",
    "transcript_schema_v1_json",
]

__version__ = version("termverify")
