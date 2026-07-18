"""Shared receipt-validating constraint negotiation for adapters.

Extracted from the direct adapter so every adapter negotiates the same way:
constraints run in ``CONSTRAINT_NAMES`` order, each step must return the
matching receipt bound to the run, the requested value, and the tier the
`termverify.enforcement-tier/v1` authorization matrix fixes for its
negotiation path; a ``ConstraintUnsupported`` report ends the start as
``StartUnsupported``, and anything else — a raising port, a mismatched
receipt, an unauthorized tier, a wrong-constraint report — fails closed as
``StartFailed``. An unauthorized tier is a contract breach, never an honest
unsupported report, so it is deliberately ``StartFailed`` rather than
``StartUnsupported``.
"""

from __future__ import annotations

from collections.abc import Callable

from termverify._enforcement_tier_v1 import EnforcementTier
from termverify._protocol_v1 import CONSTRAINT_NAMES
from termverify.adapter import (
    AdapterFailure,
    ClockReceipt,
    ConstraintName,
    ConstraintUnsupported,
    EnforcementReceipt,
    FilesystemReceipt,
    LocaleReceipt,
    NetworkReceipt,
    RunConfiguration,
    SeedReceipt,
    StartFailed,
    StartUnsupported,
    TerminalReceipt,
    TimezoneReceipt,
)

_RECEIPT_TYPES: tuple[type[EnforcementReceipt], ...] = (
    SeedReceipt,
    ClockReceipt,
    LocaleReceipt,
    TimezoneReceipt,
    TerminalReceipt,
    FilesystemReceipt,
    NetworkReceipt,
)

#: One negotiation step: a zero-argument enforcement operation per constraint,
#: in ``CONSTRAINT_NAMES`` order.
type NegotiationOperations = tuple[
    Callable[[], object],
    Callable[[], object],
    Callable[[], object],
    Callable[[], object],
    Callable[[], object],
    Callable[[], object],
    Callable[[], object],
]

#: The single authorized enforcement tier per constraint, in
#: ``CONSTRAINT_NAMES`` order, fixed by the adapter's negotiation path.
type AuthorizedTiers = tuple[
    EnforcementTier,
    EnforcementTier,
    EnforcementTier,
    EnforcementTier,
    EnforcementTier,
    EnforcementTier,
    EnforcementTier,
]


def start_failure(
    run_id: str,
    configuration: RunConfiguration,
    enforced: tuple[EnforcementReceipt, ...],
    constraint: ConstraintName,
) -> StartFailed:
    return StartFailed(
        run_id=run_id,
        requested=configuration,
        enforced=enforced,
        failure=AdapterFailure(
            "adapter-start-failed",
            "constraint enforcement failed",
            {"constraint": constraint},
        ),
    )


def negotiate_constraint(
    operation: Callable[[], object],
    expected_type: type[EnforcementReceipt],
    expected_value: object,
    authorized_tier: EnforcementTier,
    constraint: ConstraintName,
    run_id: str,
    configuration: RunConfiguration,
    enforced: tuple[EnforcementReceipt, ...],
) -> EnforcementReceipt | StartUnsupported | StartFailed:
    try:
        value = operation()
    except Exception:
        return start_failure(run_id, configuration, enforced, constraint)

    if type(value) is expected_type:
        receipt = value
        if (
            receipt.run_id == run_id
            and receipt.effective == expected_value
            and receipt.tier == authorized_tier
        ):
            return receipt
        return start_failure(run_id, configuration, enforced, constraint)
    if type(value) is ConstraintUnsupported:
        if value.constraint != constraint:
            return start_failure(run_id, configuration, enforced, constraint)
        return StartUnsupported(
            run_id=run_id,
            requested=configuration,
            enforced=enforced,
            constraint=value.constraint,
            code=value.code,
            message=value.message,
            details=value.details,
        )
    if type(value) is AdapterFailure and value.code == "adapter-start-failed":
        return StartFailed(
            run_id=run_id,
            requested=configuration,
            enforced=enforced,
            failure=value,
        )
    return start_failure(run_id, configuration, enforced, constraint)


def negotiate(
    run_id: str,
    configuration: RunConfiguration,
    operations: NegotiationOperations,
    authorized_tiers: AuthorizedTiers,
) -> tuple[EnforcementReceipt, ...] | StartUnsupported | StartFailed:
    """Run every enforcement operation in order and validate its receipt."""
    expected_values = (
        configuration.seed,
        configuration.clock,
        configuration.locale,
        configuration.timezone,
        configuration.terminal,
        configuration.filesystem,
        configuration.network,
    )
    receipts: list[EnforcementReceipt] = []
    for constraint, operation, receipt_type, expected_value, authorized_tier in zip(
        CONSTRAINT_NAMES,
        operations,
        _RECEIPT_TYPES,
        expected_values,
        authorized_tiers,
        strict=True,
    ):
        result = negotiate_constraint(
            operation,
            receipt_type,
            expected_value,
            authorized_tier,
            constraint,
            run_id,
            configuration,
            tuple(receipts),
        )
        if isinstance(result, (StartUnsupported, StartFailed)):
            return result
        receipts.append(result)
    return tuple(receipts)
