"""Stable ordered vocabulary for the v1 protocol."""

from __future__ import annotations

from typing import Literal

type ConstraintName = Literal[
    "seed",
    "clock",
    "locale",
    "timezone",
    "terminal",
    "filesystem",
    "network",
]

CONSTRAINT_NAMES: tuple[ConstraintName, ...] = (
    "seed",
    "clock",
    "locale",
    "timezone",
    "terminal",
    "filesystem",
    "network",
)
REQUIRED_CONFIG_MEMBERS = frozenset(CONSTRAINT_NAMES)
