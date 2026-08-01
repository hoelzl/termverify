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

**Three adversarial rounds rewrote this file twice, and one defect drove every
round: a check that matched the spelling its author had in mind rather than the
spellings Python has.** Round 1 got a native import past it using the spelling
the bindings themselves use. Round 2 got a real ``os.name`` conditional past it
with ``import os.path``, and a platform-named message past it in POSIX
vocabulary. The specific repairs are recorded at each check, not because the
history is interesting but because the next person to widen one of these needs
to know which kind of confidence was misplaced.

**What these checks are, and what they are not.** They are not a proof that no
platform can be read here; no static check over one file could be. Python has
too many ways to ask — ``sysconfig.get_platform()``, ``shutil.which``, an
environment variable, a deliberately failed import, a helper in another module.
What they do is make every *ordinary* way loud and make the forms this module
actually uses impossible to reintroduce quietly. The threshold stays a **review**
criterion as well as a checked one; these checks exist so that an honest
platform branch shows up in a diff, not so that a dishonest one is impossible.

Precisely:

- The token scan reads source text with comments and string literals removed,
  so it counts platform reads in *code*. That exclusion is the measurement, not
  a loophole: the threshold is about conditionals, and a docstring explaining
  why there are none is not one — this very paragraph names both tokens, and an
  unfiltered scan of the adapter's own docstring flagged the sentence describing
  the ratchet. It sees ``sys.platform`` and ``os.name`` written literally, which
  is how every occurrence in this repository is written, and nothing else.
- The import checks read the module's AST, so they see every ``import`` and
  ``from ... import`` at any nesting depth whether or not it executes: wrapped
  in a module-level ``try`` or ``if``, relative, aliased, or dotted. They do not
  see ``__import__`` or ``importlib``. They check the *names bound* rather than
  the module paths named, which is why ``import os.path`` counts — that spelling
  names no listed module and binds ``os`` anyway, and it is what carried round
  2's conditional across the threshold.
- The module list they check covers the modules whose job includes reporting the
  platform. It is deliberately not claimed to be exhaustive, because it cannot
  be.
- Behind both, :func:`test_importing_the_terminal_adapter_loads_no_native_binding`
  imports the adapter in a fresh interpreter and asks whether either native
  module came with it. For the native-import property specifically no spelling
  evades it, which is why the static checks above only have to produce a *good
  failure message*.
- The message scan reads every string literal that is neither a docstring nor an
  ``__all__`` entry, and checks each against vocabulary from both platforms. It
  does not see a banned word split across concatenated fragments (``"Con" +
  "PTY"``) or built from a variable, and it does not read comments — a comment
  narrating "the console" is invisible to it by construction, so that is a
  review question rather than a checked one.
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
import tokenize
from pathlib import Path

import pytest

import termverify.terminal

_SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src" / "termverify"

#: The package every module inspected here lives in, so a relative import can
#: be resolved to the absolute path the checks compare against.
_PACKAGE = "termverify"

#: The module the threshold is about: the adapter, above the binding port.
_ADAPTER = _SOURCE_ROOT / "terminal.py"

#: How a platform is read in Python, as it is actually written here.
_PLATFORM_READ = re.compile(r"sys\.platform|os\.name")

#: Modules whose purpose includes reporting the platform. ``platform`` and
#: ``sysconfig`` are listed although nothing in this repository uses either:
#: naming only the two in use would leave the obvious alternatives as silent
#: ways past this check, and round 2 demonstrated that with ``sysconfig``.
#: **Not** claimed to be exhaustive — see the module docstring.
_PLATFORM_MODULES = frozenset({"os", "sys", "platform", "sysconfig"})

#: The native bindings. Importable from the adapter module — that is how
#: ``ConptyBinding`` and ``PosixPtyBinding`` delegate — but only from inside
#: their methods, never at module scope.
_NATIVE_MODULES = frozenset({"termverify._conpty", "termverify._posix_pty"})

#: Platform vocabulary the adapter has no standing to use in anything it emits.
#: Both sides of the port, because the first two versions of this list were
#: Windows-only: round 2 replaced a resize message with "the ``TIOCSWINSZ``
#: ioctl on this Unix host … a Darwin or WSL kernel may clamp it" and it passed,
#: then did it again with "the console did not adopt …", because
#: ``pseudoconsole`` was banned and ``console`` was not. Listing what the code
#: said yesterday is how a ratchet ends up guarding one spelling.
#:
#: Matched case-insensitively, and as substrings except for the tokens short
#: enough to appear inside unrelated words (``nt`` is in "count", ``mac`` in
#: "machine"). Substring matching is what lets ``pseudoconsole`` see
#: ``CreatePseudoConsole``.
#:
#: ``terminal`` and ``pseudoterminal`` are deliberately absent: a ConPTY
#: pseudoconsole *is* a pseudoterminal, so they are the words that stay true
#: whichever binding is injected, and banning them would leave the messages
#: with nothing to call the thing they are about.
_PLATFORM_WORDS = re.compile(
    "|".join(
        (
            # Windows
            "conpty",
            "pseudoconsole",
            "conhost",
            "windows",
            "win32",
            "kernel32",
            "console",
            r"\bnt\b",
            # POSIX
            "posix",
            "linux",
            "darwin",
            "macos",
            r"\bmac\b",
            r"\bbsd\b",
            r"\bunix\b",
            r"\bwsl\b",
            "termios",
            "ioctl",
            "tiocswinsz",
            "openpty",
            "sigwinch",
            "killpg",
            "setsid",
        )
    ),
    re.IGNORECASE,
)


def _code_only(source: str) -> str:
    """``source`` with comments and string literals blanked out.

    Docstrings are string literals, so this is what lets the adapter document
    its own ratchet without tripping it. Each removed token is replaced by
    spaces rather than deleted so that line numbers in a failure still point
    at the right place.

    ``FSTRING_MIDDLE`` and ``TSTRING_MIDDLE`` are blanked alongside ``STRING``
    because from 3.12 (and 3.14 for t-strings) the literal text of those is
    tokenized as its own type and not as a ``STRING`` at all — so blanking only
    ``STRING`` left f-string prose readable to the scan. That was a false
    *positive* rather than a hole, and still a docstring that did not describe
    its own code. ``TSTRING_MIDDLE`` is fetched defensively because it does not
    exist before 3.14 and the CI matrix runs 3.12 through 3.14.

    The interpolated parts of an f-string tokenize as ordinary ``NAME``/``OP``
    tokens and are deliberately left alone: ``f"{sys.platform}"`` is a platform
    read and must still be counted.
    """
    literal = {tokenize.COMMENT, tokenize.STRING, tokenize.FSTRING_MIDDLE}
    tstring = getattr(tokenize, "TSTRING_MIDDLE", None)
    if tstring is not None:  # pragma: no cover - 3.14+ only
        literal.add(tstring)

    lines = source.splitlines(keepends=True)
    readline = iter(lines).__next__
    blanked = [list(line) for line in lines]
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
    """Every module path an import names, and every top-level name it binds.

    Three spellings defeated earlier versions of this function, each because it
    matched the form its author had in mind rather than the forms Python has:

    - ``from termverify import _conpty`` is what both bindings write, and its
      ``ImportFrom.module`` is ``"termverify"``. Matching ``node.module``
      against a native path missed the only spelling in the file, which is how
      round 1 hoisted the binding's own import to module scope with every check
      green. Each ``from X import a`` therefore names both ``X`` and ``X.a``.
    - ``import os.path`` *binds* ``os``, so it makes ``os.name`` reachable while
      naming a module that is not ``os``. Round 2 used exactly that to carry a
      real platform conditional above the binding port. Every dotted import
      therefore also yields its top-level package.
    - ``from . import _conpty`` and ``from ._conpty import X`` carry the package
      in ``ImportFrom.level``, which an earlier version ignored, so a relative
      native import at module scope was invisible to the static check. Relative
      imports resolve against ``termverify``, where every module inspected here
      lives.

    Some of what comes back is a *name* rather than a module, which costs
    nothing: every use is a membership test against a fixed set of paths.
    """
    if isinstance(node, ast.Import):
        names: set[str] = set()
        for alias in node.names:
            names.add(alias.name)
            names.add(alias.name.split(".")[0])
        return names

    base = node.module or ""
    if node.level:
        base = _PACKAGE if not base else f"{_PACKAGE}.{base}"
    if not base:  # pragma: no cover - an absolute `from` always has a module
        return {alias.name for alias in node.names}
    return {base, base.split(".")[0]} | {f"{base}.{alias.name}" for alias in node.names}


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
    inside it executes at import time and was invisible. Round 1 used exactly
    that shape — a try-wrapped native import, which is also the failed-import
    capability sniff this module's docstring names as a hazard.
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


def _dunder_all_literals(tree: ast.Module) -> set[int]:
    """``id()`` of every string literal inside the module's ``__all__``.

    The exclusion the message scan needs is **positional**, not by value. A
    value-based allowlist was tried and broken twice: once by adding a whole
    diagnostic's text to it, and once by interpolating an allowlisted class name
    into a message — ``f"forced {'ConptyBinding'} teardown"`` — where the
    literal is legitimately allowed *in* ``__all__`` and is a platform name
    anywhere else. Excluding by position permits the export list and nothing
    that merely quotes it.
    """
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(
            isinstance(target, ast.Name) and target.id == "__all__"
            for target in node.targets
        ):
            continue
        return {
            id(element)
            for element in ast.walk(node.value)
            if isinstance(element, ast.Constant) and isinstance(element.value, str)
        }
    raise AssertionError("the adapter module has no __all__ to exclude")


def _emitted_literals(tree: ast.Module) -> list[tuple[int, str]]:
    """Every string literal that is neither a docstring nor an ``__all__`` entry.

    Docstrings are excluded because they are prose for a reader, and prose about
    how ConPTY delivers output is exactly the knowledge this module should keep.
    What is left is the message and detail text the adapter emits.
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
    excluded = docstrings | _dunder_all_literals(tree)
    return [
        (node.lineno, node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in excluded
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


def test_the_terminal_adapter_binds_nothing_that_reports_a_platform() -> None:
    """The token scan's blind spot, narrowed from the other side.

    ``sys.platform`` is only reachable through a binding, and the adapter binds
    none of the modules whose job is to report the platform — so a future
    ``import os`` fails here before its first use can fail above. Checked at
    every nesting depth, because a function-scope ``import sys`` is the obvious
    way to hold the count at zero while reading the platform, and by *bound
    name* rather than by module path, because ``import os.path`` binds ``os``.
    """
    tree = ast.parse(_ADAPTER.read_text(encoding="utf-8"))

    reachable = _all_imports(tree) & _PLATFORM_MODULES

    assert reachable == set(), (
        f"{_ADAPTER.name} binds {sorted(reachable)}, which puts platform state"
        " within reach above the binding port"
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
    the one no spelling of an import can evade. A fresh interpreter imports the
    adapter and reports whether either native module came with it, which an
    in-process check cannot do — the rest of this suite has already imported
    both.
    """
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

    assert result.stdout.split() == ["0", "0"], (
        "importing termverify.terminal loaded a native binding;"
        f" (_conpty, _posix_pty) = {result.stdout.strip()!r}"
    )


def test_no_literal_the_terminal_adapter_emits_names_a_platform() -> None:
    """A platform conditional is not the only way to leak a platform.

    Everything checked here reaches a host or a transcript:
    ``AdapterFailure.message`` and its ``details`` values,
    ``ConstraintUnsupported``'s reason, a ``Diagnostic``'s text, and the
    ``RuntimeError`` messages raised at a lifecycle violation. The adapter holds
    a ``TerminalBindingPort`` and cannot see which binding is behind it, so a
    message naming one is a claim it has no evidence for — and before #268
    seventeen literals did, including a ``forced-termination`` diagnostic that
    would have told a Linux run its pty session ended by "forced ConPTY
    teardown".

    **What this cannot see**, and deliberately does not try to: a platform name
    arriving through ``str(error)`` from the binding itself. Those are recorded
    verbatim in a ``reason`` detail, and there naming the platform is *correct*
    — the binding knows what it is, and that is the one layer whose diagnostics
    should say so. Nor a banned word split across fragments (``"Con" + "PTY"``)
    or built from a variable, nor a comment.

    Every literal outside ``__all__`` is checked, with no shape filter and no
    value allowlist. Both were tried and broken: a filter skipping literals
    without a space in them let ``"forced " + "ConPTY" + " teardown"`` through,
    and a value allowlist let the same text through by being added to it — and
    would still let ``f"forced {'ConptyBinding'} teardown"`` through, because
    that literal is legitimately allowed in ``__all__``.
    """
    tree = ast.parse(_ADAPTER.read_text(encoding="utf-8"))

    offenders = [
        (line, text)
        for line, text in _emitted_literals(tree)
        if _PLATFORM_WORDS.search(text)
    ]

    assert offenders == [], (
        "the terminal adapter emits a literal naming a platform it cannot"
        f" see: {offenders}"
    )


def test_only_the_export_list_is_exempt_from_the_message_scan() -> None:
    """The exemption is positional, minimal, and load-bearing.

    Positional so it cannot be reused to waive prose; minimal so it covers the
    export list and nothing else; load-bearing because if no ``__all__`` entry
    named a platform the exemption would be dead code, and its removal would
    then pass unnoticed until the next binding is added.
    """
    tree = ast.parse(_ADAPTER.read_text(encoding="utf-8"))
    exempt_ids = _dunder_all_literals(tree)
    exempt = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) in exempt_ids
    }

    # Exactly the export list, and every entry a bare name.
    assert exempt == set(termverify.terminal.__all__)
    assert all(name.isidentifier() for name in exempt), sorted(exempt)

    # ...and it really is doing work: both bindings are named after a platform.
    platform_named = {name for name in exempt if _PLATFORM_WORDS.search(name)}
    assert platform_named == {"ConptyBinding", "PosixPtyBinding"}, platform_named


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
    # The three that got past the round-2 word list.
    assert _PLATFORM_WORDS.search("the console did not adopt it") is not None
    assert _PLATFORM_WORDS.search("the TIOCSWINSZ ioctl on this Unix host") is not None
    assert _PLATFORM_WORDS.search("a Darwin or WSL kernel may clamp it") is not None
    # ...without banning the two words a neutral message needs.
    assert _PLATFORM_WORDS.search("the terminal binding was closed") is None
    assert _PLATFORM_WORDS.search("through a pseudoterminal") is None
    # A short token may not fire inside an unrelated word.
    assert _PLATFORM_WORDS.search("the retained chunk count") is None
    assert _PLATFORM_WORDS.search("the state machine is idle") is None

    tree = ast.parse(_ADAPTER.read_text(encoding="utf-8"))
    assert len(_emitted_literals(tree)) > 100, "literal collector went dead"

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
