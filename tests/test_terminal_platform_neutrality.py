"""The ratchet on issue #268's threshold: no platform above the binding port.

The generalization of the ConPTY adapter into one terminal adapter was
authorized on a premise, not on a hope: that every platform difference is
absorbed by the binding port (issue #204 boundary design, rule 1). The owner
attached a measurable trigger to it. At acceptance time
``src/termverify/conpty.py`` — now ``src/termverify/terminal.py`` — contained
**zero** ``sys.platform``/``os.name`` occurrences while the native modules held
all of them, and that zero is the threshold: a generalization that needs
platform branches above the port is a generalization that should not happen,
and the slice was to stop and return the list rather than accumulate them.

The count never had to rise, so this file exists to keep it that way. It is
the acceptance criterion of the slice expressed as a check, because a
criterion that lives only in an issue is one nobody runs.

**Every check here has been mutation-tested, and the first version of two of
them was not strong enough.** That history is recorded next to each, because
this repository has now found three successive rename pins weaker than they
read (#218 twice, #268 once), and the pattern is always the same: the check
matched the spelling the author happened to think of rather than the spelling
the code uses.

**What each check can and cannot see**, stated because a ratchet's parser is
itself an attack surface and overclaiming for one is the same defect it
guards against:

- The token scan reads source text with comments and string literals removed,
  so it counts platform reads in *code*. That exclusion is not a loophole, it
  is the measurement: the threshold is about conditionals, and a docstring
  explaining why there are none is not one — this very file's prose names both
  tokens, and an unfiltered scan of the adapter's own docstring flagged the
  sentence describing the ratchet. It sees ``sys.platform`` and ``os.name``
  written literally, which is how every occurrence in this repository is
  written. It does not see ``getattr(sys, "plat" + "form")``,
  ``eval("sys.platform")``, ``importlib.import_module("os").name``, a platform
  test smuggled through a helper in another module, or a conditional keyed on
  something else entirely (``shutil.which``, an environment variable, a failed
  import).
- The import checks read the module's AST, so they see every ``import`` and
  ``from ... import`` at any nesting depth, whether or not it ever executes,
  including one wrapped in a module-level ``try``/``if``. They do not see
  ``__import__`` or ``importlib``. They are what makes the string-literal
  exclusion above safe: every form the token scan cannot see still needs one of
  ``os``, ``sys`` or ``platform`` in scope, and none of the three may be
  imported here at all.
- The message scan reads every string literal that is not a docstring, and
  checks each against a case-insensitive word list with a small exact-match
  allowlist. It does not see a banned word split across concatenated fragments
  (``"Con" + "PTY"``) or assembled from a variable — but it does see a whole
  banned word in *any* fragment, which is what the first version of it missed.

What closes the gap the parser leaves is not a cleverer parser: it is that a
platform branch above this port has to be *justified in review*, and these
checks make an honest one visible in the diff. A dishonest one is a different
problem than this file solves.
"""

from __future__ import annotations

import ast
import re
import tokenize
from pathlib import Path

import pytest

_SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src" / "termverify"

#: The module the threshold is about: the adapter, above the binding port.
_ADAPTER = _SOURCE_ROOT / "terminal.py"

#: How a platform is read in Python, as it is actually written here.
_PLATFORM_READ = re.compile(r"sys\.platform|os\.name")

#: Modules that make platform state reachable. ``platform`` is included even
#: though nothing in this repository uses it: the point is that the adapter
#: has no business importing any of them, and naming only the two in use
#: would leave the obvious third as a silent way past this check.
_PLATFORM_MODULES = frozenset({"os", "sys", "platform"})

#: The native bindings. Importable from the adapter module — that is how
#: ``ConptyBinding`` and ``PosixPtyBinding`` delegate — but only from inside
#: their methods, never at module scope.
_NATIVE_MODULES = frozenset({"termverify._conpty", "termverify._posix_pty"})

#: Platform names the adapter has no standing to use in a message it emits.
#:
#: Matched case-insensitively and **without word boundaries**. The first
#: version had both wrong: it was case-sensitive, so ``CONPTY`` passed, and it
#: anchored on word boundaries, so every one of these inside a longer
#: identifier passed too — ``CreatePseudoConsole`` being the obvious one to name
#: in a message about a failed spawn. None of the seven occurs as a substring of
#: an innocent English word, so boundaries buy nothing and cost the compound
#: cases.
#:
#: ``pseudoterminal`` is deliberately absent: a ConPTY pseudoconsole *is* a
#: pseudoterminal, so it is the one word that stays true whichever binding is
#: injected, and banning it would leave the messages with nothing to call the
#: thing they are about.
_PLATFORM_WORDS = re.compile(
    r"conpty|pseudoconsole|windows|posix|linux|win32|conhost",
    re.IGNORECASE,
)

#: String literals that legitimately name a platform: the two bindings' own
#: class names, which appear as ``__all__`` entries. An exact-match allowlist
#: and not a shape heuristic — the first version of the message scan skipped
#: every literal without a space in it, on the theory that those are symbol
#: names rather than prose. The round-1 review broke it in one line:
#: ``"forced " + "ConPTY" + " teardown;"`` restored the exact pre-#268
#: diagnostic text, with the platform in a fragment the space filter dropped,
#: and every check in the repository stayed green.
_PLATFORM_NAMING_ALLOWED = frozenset({"ConptyBinding", "PosixPtyBinding"})


def _code_only(source: str) -> str:
    """``source`` with comments and string literals blanked out.

    Docstrings are string literals, so this is what lets the adapter document
    its own ratchet without tripping it. Each removed token is replaced by
    spaces rather than deleted so that line numbers in a failure still point
    at the right place.

    ``FSTRING_MIDDLE`` is blanked alongside ``STRING`` because from Python
    3.12 an f-string's literal text is tokenized as its own type and not as a
    ``STRING`` at all — so an earlier revision that blanked only ``STRING``
    left f-string prose readable to the scan, which is a false *positive*
    rather than a hole, and still a sentence that did not describe the code.
    The interpolated parts of an f-string tokenize as ordinary ``NAME``/``OP``
    tokens and are deliberately left alone: ``f"{sys.platform}"`` is a
    platform read and must still be counted.
    """
    lines = source.splitlines(keepends=True)
    readline = iter(lines).__next__
    blanked = [list(line) for line in lines]
    literal = {tokenize.COMMENT, tokenize.STRING, tokenize.FSTRING_MIDDLE}
    for token in tokenize.generate_tokens(readline):
        if token.type not in literal:
            continue
        (start_row, start_col), (end_row, end_col) = token.start, token.end
        for row in range(start_row, end_row + 1):
            line = blanked[row - 1]
            first = start_col if row == start_row else 0
            last = end_col if row == end_row else len(line)
            for column in range(first, min(last, len(line))):
                if line[column] != "\n":
                    line[column] = " "
    return "".join("".join(line) for line in blanked)


def _named_modules(node: ast.Import | ast.ImportFrom) -> set[str]:
    """Every module path an import statement could be naming.

    ``from termverify import _conpty`` is the form both bindings actually use,
    and its ``ImportFrom.module`` is ``"termverify"`` — so a check that matched
    ``node.module`` against a native module path missed the one spelling in the
    file. That is how the round-1 review hoisted the binding's own import line
    to module scope and kept every check green. Each ``from X import a`` is
    therefore taken to name both ``X`` and ``X.a``; some of those are not
    modules at all, which costs nothing for a membership test.
    """
    if isinstance(node, ast.Import):
        return {alias.name for alias in node.names}
    if node.module is None:
        # ``from . import x`` — relative, so it cannot name a native module by
        # the absolute paths this file checks.
        return {alias.name for alias in node.names}
    return {node.module} | {f"{node.module}.{alias.name}" for alias in node.names}


def _all_imports(tree: ast.Module) -> set[str]:
    """Every module named by any import, at any nesting depth."""
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import | ast.ImportFrom):
            modules |= _named_modules(node)
    return modules


def _module_scope_imports(tree: ast.Module) -> set[str]:
    """Every module named by an import that no function body encloses.

    Identified by *not being inside a function*, rather than by appearing in
    ``tree.body``. Iterating ``tree.body`` looks equivalent and is not: a
    module-level ``try:`` or ``if:`` wrapping an import contributes an
    ``ast.Try``/``ast.If`` to that list and no ``ast.Import``, so the import
    inside it executes at import time and was invisible. The round-1 review
    used exactly that shape — a try-wrapped native import, which is also the
    failed-import capability sniff this file's own docstring names as a hazard.
    """
    enclosed: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        for child in ast.walk(node):
            if isinstance(child, ast.Import | ast.ImportFrom):
                enclosed.add(id(child))

    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import | ast.ImportFrom) and id(node) not in enclosed:
            modules |= _named_modules(node)
    return modules


def _non_docstring_literals(tree: ast.Module) -> list[tuple[int, str]]:
    """Every string literal that is not a docstring, with its line.

    Docstrings are excluded because they are prose for a reader, and prose
    about how ConPTY delivers output is exactly the knowledge this module
    should keep. What is left is the message and detail text the adapter
    emits, plus its ``__all__`` entries.
    """
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef)
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
        and isinstance(node.body[0].value.value, str)
    }
    return [
        (node.lineno, node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    ]


def test_the_terminal_adapter_reads_no_platform() -> None:
    """Issue #268's threshold, as a number.

    A non-zero count here is the stop-and-return condition, not a lint
    failure to be waived: it means the binding port stopped absorbing the
    platform, and the alternative the owner kept live — a separate
    ``PosixPtyAdapter`` — is back on the table.
    """
    source = _code_only(_ADAPTER.read_text(encoding="utf-8"))
    occurrences = _PLATFORM_READ.findall(source)

    assert occurrences == [], (
        f"{_ADAPTER.name} reads the platform {len(occurrences)} time(s):"
        f" {sorted(set(occurrences))}. Issue #268 authorized one terminal"
        " adapter on the premise that the binding port absorbs every platform"
        " difference, with zero as the measured threshold. Do not waive this"
        " — take the list to the owner, as the boundary design requires."
    )


def test_the_terminal_adapter_imports_nothing_that_can_read_a_platform() -> None:
    """The token scan's blind spot, closed from the other side.

    ``sys.platform`` is only reachable through an import, and the adapter
    imports none of the three modules that make platform state reachable at
    all — so a future ``import os`` fails here before its first use can fail
    above. Checked at every nesting depth: a function-scope ``import sys`` is
    the obvious way to hold the count at zero while reading the platform.
    """
    tree = ast.parse(_ADAPTER.read_text(encoding="utf-8"))

    reachable = _all_imports(tree) & _PLATFORM_MODULES

    assert reachable == set(), (
        f"{_ADAPTER.name} imports {sorted(reachable)}, which makes platform"
        " state reachable above the binding port"
    )


def test_the_terminal_adapter_imports_no_native_binding_at_module_scope() -> None:
    """Platform-neutral has to survive ``import termverify.terminal``.

    Both shipped bindings import their native layer inside their methods, so
    a host on either platform can import this module, inject the binding it
    has, and never load the one it does not. A module-scope native import
    would make the neutral module unimportable on one of the two platforms —
    the same defect as a conditional, arriving at import time instead of at
    a branch.
    """
    tree = ast.parse(_ADAPTER.read_text(encoding="utf-8"))

    at_module_scope = _module_scope_imports(tree) & _NATIVE_MODULES

    assert at_module_scope == set(), (
        f"{_ADAPTER.name} imports {sorted(at_module_scope)} at module scope;"
        " native bindings belong inside the binding classes' methods"
    )
    # ...and the delegation this permits is really there, so the test above
    # cannot be satisfied by an adapter that reaches no native code at all.
    assert _all_imports(tree) >= _NATIVE_MODULES


def test_importing_the_terminal_adapter_loads_no_native_binding() -> None:
    """The property the AST check stands in for, measured directly.

    The static check is the one that gives a useful failure message; this is
    the one that cannot be evaded by a spelling. A fresh interpreter imports
    the adapter and reports whether either native module came with it, which
    an in-process check cannot do — the rest of this suite has already
    imported both.
    """
    import subprocess
    import sys

    probe = (
        "import sys; import termverify.terminal;"
        " print(int('termverify._conpty' in sys.modules),"
        " int('termverify._posix_pty' in sys.modules))"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        check=True,
    )

    assert result.stdout.split() == ["0", "0"], result.stdout


def test_no_message_the_terminal_adapter_emits_names_a_platform() -> None:
    """A platform conditional is not the only way to leak a platform.

    Everything below reaches a host or a transcript: ``AdapterFailure.message``
    and its ``details`` values, ``ConstraintUnsupported``'s reason, a
    ``Diagnostic``'s text, and the ``RuntimeError`` messages raised at a
    lifecycle violation. The adapter holds a ``TerminalBindingPort`` and cannot
    see which binding is behind it, so a message naming one is a claim it has
    no evidence for — and before #268 fourteen of them did, including a
    ``forced-termination`` diagnostic that would have told a Linux run its pty
    session ended by "forced ConPTY teardown".

    **What this cannot see**, and deliberately does not try to: a platform name
    arriving through ``str(error)`` from the binding itself. Those are recorded
    verbatim in a ``reason`` detail, and there naming the platform is
    *correct* — the binding knows what it is, and that is the one layer whose
    diagnostics should say so. Nor can it see a banned word split across
    fragments (``"Con" + "PTY"``) or built from a variable.

    Every literal is checked, with no shape filter. An earlier revision skipped
    literals without a space in them as "symbol names, not prose", and the
    round-1 review used that to restore the exact pre-#268 diagnostic text with
    the platform in a space-free fragment.
    """
    tree = ast.parse(_ADAPTER.read_text(encoding="utf-8"))

    offenders = [
        (line, text)
        for line, text in _non_docstring_literals(tree)
        if text not in _PLATFORM_NAMING_ALLOWED and _PLATFORM_WORDS.search(text)
    ]

    assert offenders == [], (
        "the terminal adapter emits a literal naming a platform it cannot"
        f" see: {offenders}"
    )


def test_the_platform_naming_allowlist_has_no_dead_entries() -> None:
    """An allowlist is the check's weakest part, so it may not grow quietly.

    Every entry must be a literal the module actually contains and actually
    needs. Without this, waiving a future offender is one line and leaves no
    trace of what was waived.
    """
    tree = ast.parse(_ADAPTER.read_text(encoding="utf-8"))
    literals = {text for _, text in _non_docstring_literals(tree)}

    used = {
        allowed
        for allowed in _PLATFORM_NAMING_ALLOWED
        if allowed in literals and _PLATFORM_WORDS.search(allowed)
    }

    assert used == set(_PLATFORM_NAMING_ALLOWED), (
        "these allowlist entries are not platform-naming literals in"
        f" {_ADAPTER.name}, so they waive nothing:"
        f" {sorted(set(_PLATFORM_NAMING_ALLOWED) - used)}"
    )


def test_the_scans_would_catch_what_they_are_for() -> None:
    """Each scan's own witness, because a filter that matches nothing passes.

    Every way this file could go quietly dead — a pattern that stopped
    matching, a literal collector that returns nothing, a blanking pass that
    erases the code it was meant to leave.
    """
    assert _PLATFORM_WORDS.search("the ConPTY binding was closed") is not None
    assert _PLATFORM_WORDS.search("the pseudoconsole did not adopt it") is not None
    assert _PLATFORM_WORDS.search("CONPTY") is not None, "must be case-insensitive"
    assert _PLATFORM_WORDS.search("CreatePseudoConsole") is not None
    assert _PLATFORM_WORDS.search("the terminal binding was closed") is None
    assert _PLATFORM_WORDS.search("through a pseudoterminal") is None

    tree = ast.parse(_ADAPTER.read_text(encoding="utf-8"))
    assert len(_non_docstring_literals(tree)) > 100, "literal collector went dead"

    # The blanking pass must leave code behind, or every scan over it is
    # vacuous. An f-string's *interpolation* is code and must survive it.
    blanked = _code_only('x = f"a sys.platform b"\ny = sys.platform\n')
    assert "sys.platform" in blanked, "blanking erased a real platform read"
    assert blanked.count("sys.platform") == 1, "f-string text was not blanked"


@pytest.mark.parametrize(
    "native",
    [
        pytest.param("_conpty.py", id="conpty"),
        pytest.param("_posix_pty.py", id="posix-pty"),
    ],
)
def test_the_native_bindings_are_where_the_platform_lives(native: str) -> None:
    """The other half of the premise, and the reason zero is achievable.

    Without this, ``terminal.py``'s zero would be consistent with a repository
    that has no platform-specific code at all — which would mean the platform
    difference had been dropped rather than absorbed. Each native binding is
    expected to read the platform, and the boundary design's own table records
    that it does.
    """
    source = _code_only((_SOURCE_ROOT / native).read_text(encoding="utf-8"))

    assert _PLATFORM_READ.search(source) is not None, (
        f"{native} reads no platform, so either it stopped claiming one or the"
        " scan in this file no longer matches how a platform read is written"
    )
