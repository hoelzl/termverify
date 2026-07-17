"""Mutable JSON value shape used by v1 protocol boundaries."""

from __future__ import annotations

type JsonValue = (
    None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]
)
