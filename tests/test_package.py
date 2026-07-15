from importlib.metadata import version

from termverify import __version__, persist_transcript_evidence


def test_exposes_installed_package_version() -> None:
    assert __version__ == version("termverify")


def test_exposes_safe_transcript_persistence_boundary() -> None:
    assert callable(persist_transcript_evidence)
