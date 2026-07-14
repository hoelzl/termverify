from termverify import __version__


def test_exposes_initial_public_version() -> None:
    assert __version__ == "0.1.0"
