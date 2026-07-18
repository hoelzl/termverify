"""Opt-in cooperation-tier constraint ports: delivery, never enforcement.

This module implements slice 2 of the accepted cooperation-tier design
(`docs/agent/design/cooperation-tier-constraint-ports.md`). The ports make
the six non-terminal constraints satisfiable at the honestly disclosed
``delivered`` tier of `termverify.enforcement-tier/v1`: each receipt claims
exactly that the recorded values were placed into the subject's spawn
environment, and honoring them is the subject's documented cooperation
obligation. Nothing is enforced at an OS boundary, no receipt claims the
subject complied, and OS containment remains an explicit non-goal by
recorded owner decision.

Using these ports is an explicit host decision:
``UnenforcedConstraintPorts`` remains the ConPTY adapter's default, so
nothing is implicitly claimed.

Per-constraint delivery contracts (conventional platform variables are
delivered only where the requested value's meaning maps exactly and
portably):

- seed: ``TERMVERIFY_SEED=<decimal>``.
- clock: ``TERMVERIFY_CLOCK_INITIAL_MS=<decimal>`` — the initial manual
  time only. Disclosed: manual-time advances are never delivered to a
  running child; no recorded protocol channel for them exists.
- locale: ``TERMVERIFY_LOCALE=<tag>`` — no ``LANG``/``LC_ALL``, because
  mapping a BCP-47 tag to a platform locale string is not exact.
- timezone: ``TZ=UTC0`` (the exact portable POSIX spelling, parsed
  identically by the Windows CRT) plus ``TERMVERIFY_TIMEZONE=UTC``.
  Delivery is UTC-only; a non-UTC request is truthfully unsupported
  because named-timezone semantics remain a separate owner-blocked
  workstream.
- filesystem: ``TERMVERIFY_FS_ROOT=<absolute path>`` and the child's
  working directory, from an explicit ``root_id -> host directory``
  mapping. Lifecycle is deliberately the host's: the port creates,
  populates, and deletes nothing.
- network: ``TERMVERIFY_NETWORK=deny`` — deny mode only; an allow-list
  request stays rejected fail-closed. Nothing blocks sockets.

The filesystem existence-and-resolution check runs through an injectable
directory probe whose default is the real filesystem — the one disclosed
ambient touchpoint in these ports (owner decision 5), kept injectable so
every port remains fully fake-driven and ratcheted. The check happens at
negotiation time and is advisory: it is not containment and carries the
ordinary time-of-check gap to spawn.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Protocol, runtime_checkable

from termverify.adapter import (
    AdapterFailure,
    ClockConfiguration,
    ClockReceipt,
    ConstraintUnsupported,
    DeliveryRecord,
    FilesystemConfiguration,
    FilesystemReceipt,
    LocaleReceipt,
    NetworkConfiguration,
    NetworkReceipt,
    SeedReceipt,
    TerminalConfiguration,
    TerminalReceipt,
    TimezoneReceipt,
)

__all__ = [
    "CooperationConstraintPorts",
    "DirectoryProbePort",
    "RealDirectoryProbe",
]


@runtime_checkable
class DirectoryProbePort(Protocol):
    """Injectable existence-and-resolution check for sandbox root paths."""

    def resolve_directory(self, path: str) -> str | None:
        """Return the absolute resolved path of an existing directory, else None."""
        ...  # pragma: no cover - structural declaration


class RealDirectoryProbe:
    """Default probe against the real filesystem.

    This is the cooperation ports' single disclosed ambient touchpoint. The
    check is advisory negotiation-time evidence with the ordinary
    time-of-check gap to spawn; it claims existence at resolution time,
    never containment.
    """

    def resolve_directory(self, path: str) -> str | None:
        resolved = os.path.abspath(os.path.realpath(path))
        if not os.path.isdir(resolved):
            return None
        return resolved


class CooperationConstraintPorts:
    """Delivered-tier ports for all six non-terminal constraints."""

    def __init__(
        self,
        filesystem_roots: Mapping[str, str] | None = None,
        *,
        directory_probe: DirectoryProbePort | None = None,
    ) -> None:
        roots: dict[str, str] = {}
        if filesystem_roots is not None:
            if not isinstance(filesystem_roots, Mapping):
                raise TypeError(
                    "filesystem_roots must be a mapping of root ids to host"
                    " directory paths"
                )
            for root_id, path in filesystem_roots.items():
                if type(root_id) is not str or type(path) is not str:
                    raise TypeError("filesystem root ids and paths must be strings")
                if not root_id or not path:
                    raise ValueError("filesystem root ids and paths must be non-empty")
                roots[root_id] = path
        self._roots = roots
        self._probe: DirectoryProbePort = (
            directory_probe if directory_probe is not None else RealDirectoryProbe()
        )

    def enforce_seed(
        self, run_id: str, requested: int
    ) -> SeedReceipt | ConstraintUnsupported | AdapterFailure:
        return SeedReceipt(
            run_id,
            requested,
            "delivered",
            DeliveryRecord(env={"TERMVERIFY_SEED": str(requested)}),
        )

    def enforce_clock(
        self, run_id: str, requested: ClockConfiguration
    ) -> ClockReceipt | ConstraintUnsupported | AdapterFailure:
        return ClockReceipt(
            run_id,
            requested,
            "delivered",
            DeliveryRecord(
                env={"TERMVERIFY_CLOCK_INITIAL_MS": str(requested.initial_ms)}
            ),
        )

    def enforce_locale(
        self, run_id: str, requested: str
    ) -> LocaleReceipt | ConstraintUnsupported | AdapterFailure:
        return LocaleReceipt(
            run_id,
            requested,
            "delivered",
            DeliveryRecord(env={"TERMVERIFY_LOCALE": requested}),
        )

    def enforce_timezone(
        self, run_id: str, requested: str
    ) -> TimezoneReceipt | ConstraintUnsupported | AdapterFailure:
        if requested != "UTC":
            return ConstraintUnsupported(
                "timezone",
                "constraint-unsupported",
                "cooperation delivery is UTC-only: delivering a named"
                " timezone requires the separate owner-blocked"
                " named-timezone workstream",
            )
        return TimezoneReceipt(
            run_id,
            "UTC",
            "delivered",
            DeliveryRecord(env={"TZ": "UTC0", "TERMVERIFY_TIMEZONE": "UTC"}),
        )

    def enforce_terminal(
        self, run_id: str, requested: TerminalConfiguration
    ) -> TerminalReceipt | ConstraintUnsupported | AdapterFailure:
        del run_id, requested
        return ConstraintUnsupported(
            "terminal",
            "constraint-not-enforced",
            "terminal enforcement belongs to the adapter, which never"
            " delegates it; these cooperation ports cannot deliver it",
        )

    def enforce_filesystem(
        self, run_id: str, requested: FilesystemConfiguration
    ) -> FilesystemReceipt | ConstraintUnsupported | AdapterFailure:
        mapped = self._roots.get(requested.root_id)
        if mapped is None:
            return ConstraintUnsupported(
                "filesystem",
                "constraint-unsupported",
                "the requested sandbox root id is not mapped to a host"
                " directory, so the request cannot be delivered truthfully",
                {"root_id": requested.root_id},
            )
        resolved = self._probe.resolve_directory(mapped)
        if resolved is None:
            return ConstraintUnsupported(
                "filesystem",
                "constraint-unsupported",
                "the mapped sandbox root is not an existing directory, so"
                " the request cannot be delivered truthfully",
                {"root_id": requested.root_id},
            )
        return FilesystemReceipt(
            run_id,
            requested,
            "delivered",
            DeliveryRecord(env={"TERMVERIFY_FS_ROOT": resolved}, cwd=resolved),
        )

    def enforce_network(
        self, run_id: str, requested: NetworkConfiguration
    ) -> NetworkReceipt | ConstraintUnsupported | AdapterFailure:
        if requested.mode != "deny":
            return ConstraintUnsupported(
                "network",
                "constraint-unsupported",
                "cooperation delivery is deny-mode only; allow-list network"
                " semantics remain rejected fail-closed",
            )
        return NetworkReceipt(
            run_id,
            requested,
            "delivered",
            DeliveryRecord(env={"TERMVERIFY_NETWORK": "deny"}),
        )
