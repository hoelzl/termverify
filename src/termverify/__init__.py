"""Protocol-driven verification for autonomous terminal applications."""

from importlib.metadata import version

from termverify.evidence import persist_transcript_evidence

__all__ = ["__version__", "persist_transcript_evidence"]

__version__ = version("termverify")
