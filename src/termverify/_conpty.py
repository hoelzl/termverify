"""Minimal Windows ConPTY binding boundary for the terminal adapter plan.

This module is the only place that touches ``pywinpty``. It stays deliberately
thin: every future adapter behavior above it must be testable cross-platform
against an injected fake binding, so this native boundary is excluded from the
coverage ratchet with recorded rationale in the developer guide. Nothing here
claims native EOF, final-frame drain completeness, process-tree teardown, or
cancellation recovery; those claims require the later verified slices of the
accepted terminal-adapter decision.

``write`` intentionally returns ``None``: the ConPTY write return value is not
a reliable byte-count receipt, and exposing it would fabricate evidence.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from typing import Any


class ConptyUnsupportedError(RuntimeError):
    """Raised when the ConPTY binding is used on a host without ConPTY."""


class ConptyChild:
    """Thin ownership wrapper around one pywinpty ConPTY child process."""

    def __init__(self, process: Any) -> None:
        self._process = process

    @classmethod
    def spawn(cls, argv: Sequence[str], *, rows: int, columns: int) -> ConptyChild:
        """Spawn a child on a ConPTY pseudoconsole with explicit dimensions."""
        if os.name != "nt":
            raise ConptyUnsupportedError(
                "the ConPTY binding requires Windows; this host has no ConPTY"
            )
        from winpty import Backend, PtyProcess

        process = PtyProcess.spawn(
            list(argv),
            dimensions=(rows, columns),
            backend=Backend.ConPTY,
        )
        return cls(process)

    def read(self, max_chars: int) -> str:
        """Read up to ``max_chars`` decoded characters from the child."""
        return str(self._process.read(max_chars))

    def write(self, text: str) -> None:
        """Write ``text`` to the child without claiming a byte-count receipt."""
        self._process.write(text)

    def resize(self, *, rows: int, columns: int) -> None:
        """Resize the pseudoconsole explicitly."""
        self._process.setwinsize(rows, columns)

    def is_alive(self) -> bool:
        """Report whether the child process is still alive."""
        return bool(self._process.isalive())

    def close(self, *, force: bool) -> None:
        """Close the binding's process handle, forcing termination if asked."""
        self._process.close(force=force)

    @property
    def exit_status(self) -> int | None:
        """Return the child's exit status once observed, else ``None``."""
        status = self._process.exitstatus
        return None if status is None else int(status)
