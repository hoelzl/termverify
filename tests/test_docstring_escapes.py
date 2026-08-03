"""No shipped docstring may contain an escape Python silently interpreted.

Issue #279's divergence table names byte sequences — ``\\xe2\\x82``, ``\\xc0``,
``\\x82`` — inside ``_terminal_binding.py``'s module docstring. That docstring
was not raw, so Python interpreted every one of them: the row identifying the
lone continuation byte, which is the row that establishes where the divergence
stops, became an invisible C1 control character at runtime while continuing to
read correctly in the source. The table stopped being a table, and the one
artifact three other documents point at for that divergence was unreadable.

**Nothing caught it.** Those are *valid* escapes, so ruff's ``W605``
(invalid-escape-sequence) has nothing to say, and ``ruff check``, ``ruff
format --check`` and ``mypy`` were all green with the damage in the tree. Two
adversarial reviewers read the file and saw the source, which is correct; the
third read ``__doc__``, which is what ships.

**What this checks, and why it is shaped this way.** Not "is the docstring
raw" and not "does the source contain ``\\x``" — both are checks against a
spelling, the defect shape this project has recorded a dozen times. It reads
the *rendered* docstring and looks for characters that a deliberate docstring
does not contain: C0 and C1 controls, and the surrogate/BOM/nonchar range. A
literal ``\\x82`` written correctly (escaped, or inside a raw string) produces
the four printable characters ``\\``, ``x``, ``8``, ``2`` and passes. The same
text written in a cooked string produces U+0082 and fails. Any other way of
smuggling an interpreted escape into a docstring fails the same way, because
the check is on the output rather than on how it was written.

Tab and newline are the only controls allowed, being the only two a docstring
legitimately carries.
"""

from __future__ import annotations

import ast
import pathlib
import unicodedata

import pytest

_SOURCE_ROOT = pathlib.Path(__file__).resolve().parents[1] / "src" / "termverify"

#: Controls a docstring may legitimately contain.
_PERMITTED = frozenset("\n\t")


def _offending_characters(text: str) -> list[tuple[int, str]]:
    """Return ``(index, name)`` for every character that cannot be deliberate."""
    found: list[tuple[int, str]] = []
    for index, character in enumerate(text):
        if character in _PERMITTED:
            continue
        category = unicodedata.category(character)
        # Cc = C0/C1 controls; Cs = surrogates; Cn = unassigned, which is what
        # a noncharacter such as U+FFFE reports. Co (private use) is left out
        # deliberately: it is assignable text, not evidence of an escape.
        if category in {"Cc", "Cs", "Cn"}:
            found.append(
                (index, unicodedata.name(character, f"U+{ord(character):04X}"))
            )
    return found


def _docstrings(tree: ast.Module) -> list[tuple[str, str]]:
    """Every docstring in the module, as ``(qualified-ish name, text)``."""
    collected: list[tuple[str, str]] = []
    module_doc = ast.get_docstring(tree, clean=False)
    if module_doc is not None:
        collected.append(("<module>", module_doc))
    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            and (doc := ast.get_docstring(node, clean=False)) is not None
        ):
            collected.append((node.name, doc))
    return collected


def _shipped_modules() -> list[pathlib.Path]:
    return sorted(_SOURCE_ROOT.rglob("*.py"))


def test_the_scan_covers_the_whole_shipped_package() -> None:
    """A denominator, so an empty sweep cannot read as a clean one."""
    modules = _shipped_modules()
    assert len(modules) >= 20, f"only {len(modules)} modules found under {_SOURCE_ROOT}"
    assert any(module.name == "_terminal_binding.py" for module in modules)


@pytest.mark.parametrize(
    "module", _shipped_modules(), ids=lambda path: path.name.removesuffix(".py")
)
def test_no_docstring_carries_an_interpreted_escape(module: pathlib.Path) -> None:
    tree = ast.parse(module.read_text(encoding="utf-8"), filename=str(module))
    for name, text in _docstrings(tree):
        offenders = _offending_characters(text)
        assert not offenders, (
            f"{module.name}:{name} renders {len(offenders)} character(s) that no"
            f" docstring writes on purpose — {offenders[:4]} — so an escape such"
            f" as \\x82 was interpreted rather than shown. Make the docstring raw"
            f' (r""") or double the backslashes.'
        )


def test_the_check_fails_on_the_defect_it_was_written_for() -> None:
    """The scan must reject the exact damage #279 shipped, and accept the fix.

    Without this the parametrized sweep above is green on a tree that has no
    defect in it, which is indistinguishable from a scan that inspects
    nothing.
    """
    cooked = "``\x82`` (lone continuation)"  # what a non-raw docstring produces
    raw = r"``\x82`` (lone continuation)"  # what the source is meant to show
    assert _offending_characters(cooked), "the scan missed an interpreted \\x82"
    assert not _offending_characters(raw), "the scan rejected a correctly shown one"
