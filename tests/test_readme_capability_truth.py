"""Every present-tense capability the README claims must exist in ``src/``.

Finding P5 of the 2026-07-24 adversarial review: four of the README's six
promised capabilities did not exist — property/state-machine testing, reviewed
golden snapshots, differential testing, and failure minimization / CI artifacts
were all stated in the present tense with nothing in ``src/`` behind them.

The owner's remedy (issue #199) was to list only what exists and move the rest
to a single vision document. Prose has no ratchet, which is precisely how that
drift happened, so this module gives the split one:

* every bullet in the README's current-capability section must name at least
  one ``termverify`` module, and every named module must import;
* no term belonging to a *planned* capability may appear in that section;
* the guard terms are checked for coverage against the vision document's own
  planned-scope headings, so adding a planned capability there without
  guarding it here fails — the two files ratchet each other rather than
  drifting independently.

What this deliberately does **not** do is verify that a named module does what
the bullet says; no test can. It bounds the failure to "the claim names real
code", and the module-naming rule is what makes a bare aspirational sentence
impossible to slip in. The general prose-status validator is Slice 8.4 (#203).
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

#: A top-level list item: ``- `` at the start of a line.
_BULLET = re.compile(r"^- ", re.MULTILINE)

#: Guard terms per planned-scope heading in the vision document. Phrases and
#: word boundaries rather than bare substrings, so ordinary prose — "the
#: verdict exposes a `first_divergence` property", "minimizes ambient state" —
#: does not trip the guard. ``test_every_planned_capability_is_guarded``
#: asserts these keys still match the vision document's headings.
_DEFERRED_GUARDS: dict[str, tuple[str, ...]] = {
    "A POSIX PTY adapter": (r"posix",),
    "Property and state-machine testing": (
        r"property test\w*",
        r"property-based",
        r"state[- ]machine",
    ),
    "Reviewed golden snapshots": (r"golden", r"baseline\w*", r"snapshot\w*"),
    "Differential testing": (r"differential",),
    "Metamorphic oracles": (r"metamorphic",),
    "Failure minimization": (r"minimization", r"minimiz\w*ing", r"shrink\w*"),
    "CI artifacts and reports": (r"ci artifact\w*", r"artifact\w*"),
}


def _section(text: str, heading: str) -> str:
    """Return *heading*'s body.

    Stops at the next heading of the same or higher level — so a ``#``
    section keeps its ``##`` subsections — and ignores headings inside fenced
    code blocks, since the architecture diagrams contain ``#`` characters.
    """
    assert heading in text, (
        f"{heading!r} is missing; if the section was renamed, update this "
        "test so the contract keeps applying instead of silently lapsing."
    )
    level = _level(heading)
    body = text[text.index(heading) + len(heading) :]
    fenced = False
    kept: list[str] = []
    for line in body.splitlines():
        if line.startswith("```"):
            fenced = not fenced
        elif not fenced and line.startswith("#") and _level(line) <= level:
            break
        kept.append(line)
    return "\n".join(kept)


def _level(heading: str) -> int:
    return len(heading) - len(heading.lstrip("#"))


def _capability_section() -> str:
    return _section(_README.read_text(encoding="utf-8"), _CAPABILITY_HEADING)


def _capability_bullets() -> list[str]:
    section = _capability_section()
    starts = [match.start() for match in _BULLET.finditer(section)]
    bounds = [*starts, len(section)]
    return [section[bounds[i] : bounds[i + 1]] for i in range(len(starts))]


def _planned_headings() -> list[str]:
    scope = _section(_VISION.read_text(encoding="utf-8"), "# Planned scope")
    subheadings = [line for line in scope.splitlines() if line.startswith("## ")]
    return [line.removeprefix("## ").strip() for line in subheadings]


_CLAIMED_MODULES = sorted(set(_MODULE_REFERENCE.findall(_capability_section())))
_BULLETS = _capability_bullets()
_GUARDS = [
    (heading, pattern)
    for heading, patterns in _DEFERRED_GUARDS.items()
    for pattern in patterns
]


def test_the_capability_section_has_bullets_that_name_modules() -> None:
    """A section with no bullets would satisfy every per-bullet check."""
    assert len(_capability_bullets()) >= 5
    assert len(_CLAIMED_MODULES) >= 5, _CLAIMED_MODULES


@pytest.mark.parametrize("module", _CLAIMED_MODULES)
def test_every_capability_the_readme_claims_has_a_module(module: str) -> None:
    importlib.import_module(f"termverify.{module}")


@pytest.mark.parametrize("bullet", _BULLETS, ids=range(len(_BULLETS)))
def test_every_capability_bullet_names_its_implementing_module(bullet: str) -> None:
    """The rule that makes a bare aspirational sentence impossible to add."""
    assert _MODULE_REFERENCE.search(bullet), (
        "every bullet under "
        f"{_CAPABILITY_HEADING!r} must name the `termverify.<module>` that "
        f"implements it; this one names none:\n{bullet.strip()}"
    )


def test_the_readme_links_the_vision_document_exactly_once() -> None:
    """P5's remedy is single-sourcing: stated once, linked, not restated."""
    readme = _README.read_text(encoding="utf-8")
    links = readme.count("docs/knowledge/product-vision.md")
    assert links == 1, f"README links the vision document {links} times, expected 1"


def test_the_vision_document_exists_and_is_the_single_source() -> None:
    text = _VISION.read_text(encoding="utf-8")
    assert text.startswith("---"), "OKF frontmatter is required in docs/knowledge/"
    assert "type:" in text.split("---")[1]
    assert len(_planned_headings()) >= 5, _planned_headings()


def test_every_planned_capability_is_guarded() -> None:
    """Adding planned scope to the vision doc must extend the guard here.

    Without this, the guard list silently stops covering the document it is
    derived from — which is how the first version of this test let three
    deferred capabilities back into the README.
    """
    assert sorted(_DEFERRED_GUARDS) == sorted(_planned_headings())


@pytest.mark.parametrize(("heading", "pattern"), _GUARDS)
def test_no_planned_capability_is_claimed_by_readme(heading: str, pattern: str) -> None:
    """Deferred scope may be linked from the README, never claimed in it."""
    found = re.search(rf"\b{pattern}\b", _capability_section(), re.IGNORECASE)
    assert not found, (
        f"{found.group(0)!r} appears in the README's current-capability "
        f"section, but {heading!r} is planned scope; it belongs in "
        "docs/knowledge/product-vision.md"
    )
