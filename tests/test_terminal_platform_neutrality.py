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
  ``from ... import`` statement at any nesting depth regardless of whether it
  ever executes. They do not see ``__import__`` or ``importlib``. They are
  what makes the string-literal exclusion above safe: every form the token
  scan cannot see still needs one of ``os``, ``sys`` or ``platform`` in scope,
  and none of the three may be imported here at all.

What closes the gap the parser leaves is not a cleverer parser: it is that a
platform branch above this port has to be *justified in review*, and the two
checks below make an honest one visible in the diff. A dishonest one is a
different problem than this file solves.
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


def _code_only(source: str) -> str:
    """``source`` with every comment and string literal blanked out.

    Docstrings are string literals, so this is what lets the adapter document
    its own ratchet without tripping it. Each removed token is replaced by
    spaces rather than deleted so that line numbers in a failure still point
    at the right place.
    """
    lines = source.splitlines(keepends=True)
    readline = iter(lines).__next__
    blanked = [list(line) for line in lines]
    for token in tokenize.generate_tokens(readline):
        if token.type not in (tokenize.COMMENT, tokenize.STRING):
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


def _module_scope_imports(tree: ast.Module) -> set[str]:
    """Every module named by a top-level ``import``/``from`` statement."""
    imported: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.add(node.module)
    return imported


def _all_imports(tree: ast.Module) -> set[str]:
    """Every module named by any ``import``/``from``, at any nesting depth."""
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.add(node.module)
    return imported


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


#: Platform names the adapter has no standing to use in a message it emits.
#: ``pseudoterminal`` is deliberately absent: a ConPTY pseudoconsole *is* a
#: pseudoterminal, so it is the one word that stays true whichever binding is
#: injected, and banning it would leave the messages with nothing to call the
#: thing they are about.
_PLATFORM_WORDS = re.compile(
    r"\b(ConPTY|Conpty|pseudoconsole|Windows|POSIX|Linux|win32|conhost)\b"
)


def _emitted_strings(tree: ast.Module) -> list[tuple[int, str]]:
    """Every string literal that is not a docstring, with its line.

    Docstrings are excluded because they are prose for a reader, and prose
    about how ConPTY delivers output is exactly the knowledge this module
    should keep. What is left is, in this module, the message and detail text
    the adapter emits — plus a handful of ``__all__`` entries and symbol
    names, which the length filter at the call site drops.
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


def test_no_message_the_terminal_adapter_emits_names_a_platform() -> None:
    """A platform conditional is not the only way to leak a platform.

    Everything below reaches a transcript: ``AdapterFailure.message``,
    ``ConstraintUnsupported``'s reason, ``Diagnostic``'s text. The adapter
    holds a ``TerminalBindingPort`` and cannot see which binding is behind it,
    so a message naming one is a claim it has no evidence for — and before
    #268 eleven of them did, including a ``forced-termination`` diagnostic
    that would have told a Linux run its pty session ended by "forced ConPTY
    teardown".

    **What this cannot see**, and deliberately does not try to: a platform
    name arriving through ``str(error)`` from the binding itself. Those are
    recorded verbatim in a ``reason`` detail, and there naming the platform is
    *correct* — the binding knows what it is, and that is the one layer whose
    diagnostics should say so.

    Also unseen: a name assembled at runtime, whether by f-string
    interpolation or concatenation of fragments that are individually clean.
    The filter is the literal text as written, which is how every message in
    this module is written.
    """
    tree = ast.parse(_ADAPTER.read_text(encoding="utf-8"))

    # Message-shaped: more than one word. Drops ``__all__`` entries, symbol
    # names, dict keys and detail labels, none of which are prose a reader of
    # a transcript sees as a sentence.
    offenders = [
        (line, text)
        for line, text in _emitted_strings(tree)
        if " " in text and _PLATFORM_WORDS.search(text)
    ]

    assert offenders == [], (
        "the terminal adapter emits a message naming a platform it cannot"
        f" see: {offenders}"
    )


def test_the_platform_word_scan_would_catch_a_platform_named_message() -> None:
    """The scan's own witness, because a filter that matches nothing passes.

    Two ways this file could go quietly dead — the pattern stopping matching,
    or the message-shaped filter dropping everything — and this catches both.
    """
    assert _PLATFORM_WORDS.search("the ConPTY binding was closed") is not None
    assert _PLATFORM_WORDS.search("the pseudoconsole did not adopt it") is not None
    assert _PLATFORM_WORDS.search("the terminal binding was closed") is None

    tree = ast.parse(_ADAPTER.read_text(encoding="utf-8"))
    message_shaped = [text for _, text in _emitted_strings(tree) if " " in text]

    assert len(message_shaped) > 50, len(message_shaped)


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
