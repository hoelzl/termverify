"""Every present-tense capability the README claims must exist in ``src/``.

Finding P5 of the 2026-07-24 adversarial review: four of the README's six
promised capabilities did not exist — property/state-machine testing, reviewed
golden snapshots, differential testing, and failure minimization / CI artifacts
were all stated in the present tense with nothing in ``src/`` behind them.

The owner's remedy (issue #199) was to list only what exists and move the rest
to a single vision document. Prose has no ratchet, which is precisely how that
drift happened, so this module gives the split one. What it enforces, exactly:

* the current-capability section is a pinned intro sentence plus top-level
  ``- `` bullets and nothing else — inserted prose, alternate or numbered
  markers, and nested lists all fail structurally;
* every bullet must name at least one ``termverify.<module>``, and every
  named module must import;
* no term belonging to a *planned* capability may appear anywhere in the
  section, and the guard terms are checked for coverage against the vision
  document's own planned-scope headings, so the two files ratchet each other
  rather than drifting independently.

Equally load-bearing is what it **cannot** catch — each shape demonstrated by
adversarial review of PR #256:

* a bullet naming a real module while claiming something that module does not
  do, or a false sentence indented to the bullet's content column so it
  renders inside the bullet — everything inside a bullet is semantic and
  belongs to human review;
* false claims in *other* README sections;
* planned capabilities described with synonyms the guard list lacks.

Those bounds belong to review and to the general prose-status validator
(Slice 8.4, #203); this module is the README-local structural ratchet, not
that validator.
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

#: A list marker at the start of a stripped line: ``-``, ``*``, ``+``, or a
#: numbered ``1.``/``1)`` item, followed by a literal space.
_LIST_MARKER = re.compile(r"([-*+]|\d+[.)]) ")

#: Markdown attaches a continuation line to a ``- `` item only from the
#: item's content column onward. A line indented less than this renders as
#: a standalone paragraph *between* the lists — which is how review round 3
#: slipped prose past the round-2 fix with a single leading space.
_CONTINUATION_INDENT = 2

#: The section's only permitted non-bullet prose, whitespace-normalized. Any
#: other prose — before, between, or after bullets — is a structural
#: violation, so a prose change in the section is always a deliberate act
#: that updates this pin.
_PINNED_INTRO = (
    "Every item below is implemented and covered by the test suite; "
    "the named module is where it lives."
)

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

    The heading must occupy a whole line, exactly once — substring matching
    let review round 3 plant a ``###`` lookalike that re-pointed every
    check, guards included, at a decoy body. The body stops at the next
    heading of the same or higher level — so a ``#`` section keeps its
    ``##`` subsections — and ignores headings inside fenced code blocks,
    since the architecture diagrams contain ``#`` characters.
    """
    anchors = list(re.finditer(rf"^{re.escape(heading)}[ \t]*$", text, re.MULTILINE))
    assert len(anchors) == 1, (
        f"expected exactly one {heading!r} line, found {len(anchors)}; if "
        "the section was renamed, update this test so the contract keeps "
        "applying instead of silently lapsing."
    )
    level = _level(heading)
    body = text[anchors[0].end() :]
    fenced = False
    kept: list[str] = []
    for line in body.splitlines():
        if line.startswith(("```", "~~~")):
            fenced = not fenced
        elif not fenced and line.startswith("#") and _level(line) <= level:
            break
        kept.append(line)
    return "\n".join(kept)


def _level(heading: str) -> int:
    return len(heading) - len(heading.lstrip("#"))


def _capability_section() -> str:
    return _section(_README.read_text(encoding="utf-8"), _CAPABILITY_HEADING)


def _parse_structure(section: str) -> tuple[str, list[str], list[str]]:
    """Split *section* into ``(prose, bullets, violations)``.

    The structural contract: the pinned intro, then top-level ``- `` bullets
    whose continuation lines are indented to the item's content column —
    nothing else. Alternate or numbered top-level markers, nested list
    markers, under-indented lines (which markdown renders as standalone
    paragraphs, not continuations), and prose after the first bullet are
    reported as violations instead of being silently absorbed into a
    neighboring bullet, which is how review rounds 2 and 3 slipped unchecked
    claims past earlier versions of this parser.
    """
    prose: list[str] = []
    bullets: list[str] = []
    violations: list[str] = []
    for raw in section.splitlines():
        line = raw.expandtabs(4)
        stripped = line.strip()
        if not stripped:
            continue
        # Count only true spaces: exotic whitespace such as NBSP is content
        # to markdown, so it must land in the indent-0 prose branch below.
        indent = len(line) - len(line.lstrip(" "))
        marker = _LIST_MARKER.match(stripped)
        if marker and indent == 0:
            bullets.append(stripped)
            if marker.group(1) != "-":
                violations.append(f"non-`- ` top-level marker: {stripped!r}")
        elif marker and indent > 0:
            violations.append(f"nested list item: {stripped!r}")
        elif indent >= _CONTINUATION_INDENT and bullets:
            bullets[-1] += "\n" + stripped
        elif indent > 0 and bullets:
            violations.append(
                f"under-indented, renders outside any bullet: {stripped!r}"
            )
        else:
            prose.append(stripped)
            if bullets:
                violations.append(f"prose after the first bullet: {stripped!r}")
    return " ".join(prose), bullets, violations


def _capability_bullets() -> list[str]:
    return _parse_structure(_capability_section())[1]


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


def test_the_capability_section_is_intro_plus_bullets_only() -> None:
    """Nothing in the section escapes the per-bullet contract.

    Prose outside the pinned intro, alternate or numbered top-level
    markers, and nested lists are how review round 2 smuggled unchecked
    claims past the first version of this module. Changing the intro is
    legitimate — it just has to update the pin here, deliberately.
    """
    prose, _, violations = _parse_structure(_capability_section())
    assert not violations, violations
    assert re.sub(r"\s+", " ", prose) == _PINNED_INTRO


#: The structural bypasses adversarial review rounds 2 and 3 ran against
#: earlier versions of this module's parser; each was absorbed silently
#: then. The doctored sections must now be rejected.
_REVIEW_EXPLOITS = {
    "an alternate-marker bullet": "* **Golden snapshots** — reviewed baselines.",
    "a numbered bullet": "1. Full differential coverage across adapters.",
    "a nested bullet inside a real one": "  - and proves the subject always halts.",
    "prose between bullets": "TermVerify also verifies overall correctness.",
    "prose indented one space": " TermVerify also verifies overall correctness.",
    "prose behind a no-break space": "\xa0TermVerify verifies whole programs.",
}


@pytest.mark.parametrize(
    "injection", _REVIEW_EXPLOITS.values(), ids=list(_REVIEW_EXPLOITS)
)
def test_the_parser_rejects_review_structural_exploits(injection: str) -> None:
    section = _capability_section()
    anchor = section.rindex("\n- ")
    doctored = section[:anchor] + "\n" + injection + section[anchor:]
    _, _, violations = _parse_structure(doctored)
    assert violations, f"the ratchet absorbed {injection!r} without failing"


def test_the_section_anchor_ignores_lookalike_headings() -> None:
    """A ``###`` decoy containing the heading must not re-point the checks.

    Round 3 planted a lookalike deeper heading whose line contains the
    real heading as a substring; substring anchoring then ran every check
    — including the deferred-term guards — against the decoy's compliant
    body while the real section lied freely.
    """
    decoy = f"#{_CAPABILITY_HEADING}\n\ndecoy\n\n{_CAPABILITY_HEADING}\n\nreal\n"
    assert _section(decoy, _CAPABILITY_HEADING).strip() == "real"


def test_a_duplicated_section_heading_fails_loudly() -> None:
    """Two literal headings would make 'which section is checked' ambiguous."""
    twice = f"{_CAPABILITY_HEADING}\n\na\n\n# unrelated\n\n{_CAPABILITY_HEADING}\n\nb\n"
    with pytest.raises(AssertionError):
        _section(twice, _CAPABILITY_HEADING)


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
