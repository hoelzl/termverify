"""Protocol-owned enforcement-tier vocabulary `termverify.enforcement-tier/v1`.

A closed, versioned vocabulary owned by the protocol exactly like the
timezone and key registries: exact case-sensitive membership, no aliases or
normalization, runtime validation authoritative. Post-freeze membership or
meaning changes require a new vocabulary version. Membership is not evidence
that an emitter exists; each tier's authorized emitting path is fixed by the
accepted cooperation-tier design
(`docs/agent/design/cooperation-tier-constraint-ports.md`) and enforced
fail-closed during receipt-binding validation.
"""

from __future__ import annotations

from typing import Literal, TypeGuard

type EnforcementTier = Literal["os", "constructive", "delivered"]

#: The closed v1 membership, in disclosure-strength order: ``os`` (applied by
#: an operating-system mechanism at the subject boundary), ``constructive``
#: (applied by construction of the controlled in-process runtime),
#: ``delivered`` (placed into the subject's spawn environment; honoring it is
#: subject cooperation — nothing is enforced).
ENFORCEMENT_TIERS: tuple[EnforcementTier, ...] = ("os", "constructive", "delivered")
_ENFORCEMENT_TIER_SET = frozenset(ENFORCEMENT_TIERS)


def is_enforcement_tier(value: object) -> TypeGuard[EnforcementTier]:
    """Return whether *value* is an exact v1 enforcement-tier member."""
    return type(value) is str and value in _ENFORCEMENT_TIER_SET
