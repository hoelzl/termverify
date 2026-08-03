r"""No shipped docstring may contain an escape Python silently interpreted.

Issue #279's divergence measurement named byte sequences — ``\xe2\x82``,
``\xc0``, ``\x82`` — inside ``_terminal_binding.py``'s module docstring. That
docstring was not raw, so Python interpreted every one of them: the row
identifying the lone continuation byte became an invisible C1 control
character at runtime while continuing to read correctly in the source. The
one artifact three other documents pointed at was unreadable.

**Nothing caught it.** Those are *valid* escapes, so ruff's ``W605``
(invalid-escape-sequence) has nothing to say, and ``ruff check``, ``ruff
format --check`` and ``mypy`` were all green with the damage in the tree. Two
adversarial reviewers read the file and saw the source, which is correct; the
third read ``__doc__``, which is what ships.

**Two checks, because the first one alone was not enough.** The round-3 review
of #280 got an interpreted escape past the original version of this file twice
over, and both holes are worth naming:

1. It scanned ``src/termverify`` only, and the same commit shipped a cooked
   ``\xff`` in a ``tests/`` docstring.
2. It looked for control characters in the *rendered* text, and ``\xff``
   renders as ``ÿ`` — an ordinary lowercase letter. Five of the twelve byte
   values in #279's own table render as printable Latin-1. The original defect
   was caught only because ``\x82`` happens to land in the C1 range.

So the primary check now reads the **source literal**: a docstring that is not
raw may contain only escapes a prose author writes on purpose. Anything else
means a byte escape was eaten, whatever it happened to render as. The
rendered-character scan is kept as a second, independent net — it catches an
interpreted escape however it was produced, including forms the source scan
does not model.

**What neither check sees**, stated because overclaiming about a ratchet is
the same defect it guards: ``__doc__`` assigned or rewritten after class
creation, a docstring built by concatenation or an f-string (neither is a
docstring to ``ast``), and text that renders identically to what it should.
These make an escape *harder* to smuggle in by accident, which is what the
defect was; they do not make it impossible on purpose.
"""

from __future__ import annotations

import ast
import pathlib
import unicodedata
from typing import Final

import pytest

_REPOSITORY_ROOT: Final = pathlib.Path(__file__).resolve().parents[1]
_SCANNED_ROOTS: Final = (
    _REPOSITORY_ROOT / "src" / "termverify",
    _REPOSITORY_ROOT / "tests",
)

#: Controls a docstring may legitimately contain.
_PERMITTED_CHARACTERS: Final = frozenset("\n\t")

#: Escapes a prose author writes deliberately inside a cooked docstring. A
#: backslash-newline is a line continuation. Everything else — ``\x``, ``\u``,
#: ``\N``, ``\0``, ``\a``, ``\b``, ``\f``, ``\r``, ``\v`` — changes what the
#: reader sees, which in a docstring naming byte sequences is the defect.
_PERMITTED_ESCAPES: Final = frozenset("\\nt\"'\n")


def _interpreted_escapes(literal: str) -> list[str]:
    """Return the escapes in a *cooked* literal body that alter its text."""
    found: list[str] = []
    index = 0
    while index < len(literal):
        if literal[index] != "\\":
            index += 1
            continue
        following = literal[index + 1 : index + 2]
        if following in _PERMITTED_ESCAPES:
            # ``\\`` consumes both, so an escaped backslash cannot be read as
            # the start of the next escape.
            index += 2
            continue
        found.append(literal[index : index + 4])
        index += 2
    return found


def _offending_characters(text: str) -> list[tuple[int, str]]:
    """Return ``(index, name)`` for rendered characters that cannot be prose."""
    found: list[tuple[int, str]] = []
    for index, character in enumerate(text):
        if character in _PERMITTED_CHARACTERS:
            continue
        # Cc/Cs/Cn: controls, surrogates, and unassigned (which is what a
        # noncharacter such as U+FFFE reports). Cf catches the BOM and the
        # zero-width formatting characters. Co (private use) is assignable
        # text, not evidence of an escape, and is left out deliberately.
        if unicodedata.category(character) in {"Cc", "Cs", "Cn", "Cf"}:
            found.append(
                (index, unicodedata.name(character, f"U+{ord(character):04X}"))
            )
    return found


class _Docstring(ast.NodeVisitor):
    """Collect every docstring with both its rendered text and its source."""

    def __init__(self, source: str) -> None:
        self.source = source
        self.found: list[tuple[str, str, str]] = []

    def _record(self, name: str, node: ast.AST) -> None:
        body = getattr(node, "body", None)
        if not body or not isinstance(body[0], ast.Expr):
            return
        value = body[0].value
        if not isinstance(value, ast.Constant) or not isinstance(value.value, str):
            return
        segment = ast.get_source_segment(self.source, value) or ""
        self.found.append((name, value.value, segment))

    def visit_Module(self, node: ast.Module) -> None:  # noqa: N802
        self._record("<module>", node)
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802
        self._record(node.name, node)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        self._record(node.name, node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
        self._record(node.name, node)
        self.generic_visit(node)


def _docstrings(source: str) -> list[tuple[str, str, str]]:
    visitor = _Docstring(source)
    visitor.visit(ast.parse(source))
    return visitor.found


def _is_raw(segment: str) -> bool:
    prefix = segment[: segment.find('"') if '"' in segment else segment.find("'")]
    return "r" in prefix.lower()


def _body_of(segment: str) -> str:
    """The literal's text with its prefix and quotes removed."""
    for quote in ('"""', "'''", '"', "'"):
        start = segment.find(quote)
        if start != -1 and segment.endswith(quote):
            return segment[start + len(quote) : -len(quote)]
    return segment


def _scanned_modules() -> list[pathlib.Path]:
    return sorted(path for root in _SCANNED_ROOTS for path in root.rglob("*.py"))


def test_the_scan_reaches_both_trees_and_a_real_number_of_docstrings() -> None:
    """A denominator that bounds the *docstrings*, not just the files.

    The first version of this counted modules only, so a ``_docstrings`` that
    returned nothing at all left the whole sweep green — measured by the
    round-3 review, which made exactly that mutation and saw 27 passed.
    """
    modules = _scanned_modules()
    assert len(modules) >= 50, f"only {len(modules)} modules found"
    names = {module.name for module in modules}
    assert {"_terminal_binding.py", "_posix_pty.py", "test_vt.py"} <= names

    total = sum(
        len(_docstrings(module.read_text(encoding="utf-8"))) for module in modules
    )
    assert total >= 400, f"only {total} docstrings collected; the scan is not looking"


@pytest.mark.parametrize(
    "module",
    _scanned_modules(),
    ids=lambda path: f"{path.parent.name}/{path.name.removesuffix('.py')}",
)
def test_no_docstring_carries_an_interpreted_escape(module: pathlib.Path) -> None:
    source = module.read_text(encoding="utf-8")
    for name, rendered, segment in _docstrings(source):
        if segment and not _is_raw(segment):
            escapes = _interpreted_escapes(_body_of(segment))
            assert not escapes, (
                f"{module.name}:{name} is a cooked docstring containing"
                f" {escapes[:4]} — Python interprets those, so the shipped"
                f' text is not what the source shows. Make it raw (r""")'
                f" or double the backslashes."
            )
        offenders = _offending_characters(rendered)
        assert not offenders, (
            f"{module.name}:{name} renders {len(offenders)} character(s) that no"
            f" docstring writes on purpose — {offenders[:4]}."
        )


def test_both_checks_fail_on_the_defects_they_were_written_for() -> None:
    """Each net must catch what the other misses, and accept the fix.

    Without this the parametrized sweep is green on a clean tree, which is
    indistinguishable from a sweep that inspects nothing.
    """
    # The original #279 defect: renders as an invisible C1 control.
    assert _offending_characters("``\x82``")
    assert not _offending_characters(r"``\x82``")
    # The one that got past the first version: renders as an ordinary letter,
    # so only the source check sees it.
    assert not _offending_characters("``\xff``")
    assert _interpreted_escapes(r"``\xff``")
    assert not _interpreted_escapes(r"``\\xff``")
    # Deliberate prose escapes stay legal.
    assert not _interpreted_escapes(r"a line\nbreak and a quote\" and a slash\\")
    # Other smuggling routes the source check also sees.
    assert _interpreted_escapes(r"\u2028")
    assert _interpreted_escapes(r"\N{ZERO WIDTH SPACE}")
    assert _interpreted_escapes(r"\0")
    # And the BOM the rendered check missed until the round-3 review.
    assert _offending_characters("\ufeff")
