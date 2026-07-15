from importlib.metadata import version

from termverify import __version__


def test_exposes_installed_package_version() -> None:
    assert __version__ == version("termverify")
