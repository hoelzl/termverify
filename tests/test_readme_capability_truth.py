"""Every present-tense capability the README claims must exist in ``src/``.

Finding P5 of the 2026-07-24 adversarial review: four of the README's six
promised capabilities did not exist — property/state-machine testing, reviewed
golden snapshots, differential tests, and failure minimization / CI artifacts
were all stated in the present tense with nothing in ``src/`` behind them.

The owner's remedy (issue #199) was to list only what exists and move the rest
to a single vision document. Prose has no ratchet, which is precisely how that
drift happened, so this module gives the "what exists" half one: each README
capability bullet names the module that implements it, and every named module
must import. The aspirational half lives in ``docs/knowledge/product-vision.md``
and is deliberately *not* checked here — it is allowed to describe things that
do not exist yet, which is the whole point of separating the two.
"""

import importlib
import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_README = _REPO_ROOT / "README.md"
_VISION = _REPO_ROOT / "docs" / "knowledge" / "product-vision.md"

#: The README section whose bullets must be backed by code, delimited by its
#: heading and the next one. Keeping the contract anchored to a heading means
#: renaming the section fails loudly instead of silently disabling the test.
_CAPABILITY_HEADING = "## What TermVerify does today"

#: ``termverify.<module>`` inside backticks, e.g. ``` `termverify.recorder` ```.
_MODULE_REFERENCE = re.compile(r"`termverify\.([a-z_]+)`")


def _capability_section() -> str:
    text = _README.read_text(encoding="utf-8")
    assert _CAPABILITY_HEADING in text, (
        f"README no longer has a {_CAPABILITY_HEADING!r} section; if it was "
        "renamed, update _CAPABILITY_HEADING so this contract keeps applying."
    )
    start = text.index(_CAPABILITY_HEADING) + len(_CAPABILITY_HEADING)
    rest = text[start:]
    end = rest.index("\n## ") if "\n## " in rest else len(rest)
    return rest[:end]


def test_the_capability_section_names_modules() -> None:
    """A section with no module references would pass every check vacuously."""
    assert len(_CLAIMED_MODULES) >= 5, _CLAIMED_MODULES


_CLAIMED_MODULES = sorted(set(_MODULE_REFERENCE.findall(_capability_section())))


@pytest.mark.parametrize("module", _CLAIMED_MODULES)
def test_every_capability_the_readme_claims_has_a_module(module: str) -> None:
    importlib.import_module(f"termverify.{module}")


def test_the_readme_links_the_vision_document_exactly_once() -> None:
    """P5's remedy is single-sourcing: stated once, linked, not restated."""
    readme = _README.read_text(encoding="utf-8")
    links = readme.count("docs/knowledge/product-vision.md")
    assert links == 1, f"README links the vision document {links} times, expected 1"


def test_the_vision_document_exists_and_is_the_single_source() -> None:
    text = _VISION.read_text(encoding="utf-8")
    assert text.startswith("---"), "OKF frontmatter is required in docs/knowledge/"
    assert "type:" in text.split("---")[1]


@pytest.mark.parametrize(
    "aspiration",
    [
        "property",
        "golden",
        "differential",
        "minimiz",
        "POSIX",
    ],
)
def test_each_deferred_capability_is_claimed_only_by_the_vision_document(
    aspiration: str,
) -> None:
    """The four P5 capabilities, plus the POSIX adapter P6 found missing.

    The README may still *mention* them by linking the vision document; what
    it may not do is restate them as things TermVerify does. Checking the
    capability section specifically keeps this honest without banning the word
    from the whole file.
    """
    section = _capability_section().lower()
    assert aspiration.lower() not in section, (
        f"{aspiration!r} appears in the README's current-capability section; "
        "deferred scope belongs in docs/knowledge/product-vision.md"
    )
