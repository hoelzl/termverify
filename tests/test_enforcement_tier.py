"""Enforcement-tier vocabulary, receipt amendment, and authorization matrix.

Slice 1 of the accepted cooperation-tier design
(`docs/agent/design/cooperation-tier-constraint-ports.md`): the closed
`termverify.enforcement-tier/v1` vocabulary, the mandatory `tier` field on
all seven enforcement receipts, the delivered-tier `delivery` pairing rules,
and the per-negotiation-path tier authorization matrix. Everything here is
cross-platform and fake-driven; no cooperation port exists in this slice.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import cast

import pytest

from termverify._enforcement_tier_v1 import is_enforcement_tier
from termverify.adapter import (
    ENFORCEMENT_TIERS,
    AdapterFailure,
    ClockConfiguration,
    ClockReceipt,
    ConstraintUnsupported,
    DeliveryRecord,
    EnforcementReceipt,
    EnforcementTier,
    FilesystemConfiguration,
    FilesystemReceipt,
    LocaleReceipt,
    NetworkConfiguration,
    NetworkReceipt,
    RunConfiguration,
    SeedReceipt,
    StartFailed,
    TerminalConfiguration,
    TerminalReceipt,
    TimezoneReceipt,
)
from termverify.conpty import ConptyAdapter, ConptyChildPort
from termverify.direct import DirectAdapter
from termverify.evidence import persist_transcript_evidence
from termverify.transcript import (
    JsonValue,
    TranscriptValidationError,
    parse_transcript,
    serialize_transcript,
)

RUN_ID = "run-tier"


def _configuration() -> RunConfiguration:
    return RunConfiguration(
        seed=42,
        clock=ClockConfiguration(initial_ms=0),
        locale="en-US",
        timezone="UTC",
        terminal=TerminalConfiguration(columns=80, rows=24, capabilities=()),
        filesystem=FilesystemConfiguration(root_id="fixture-root"),
        network=NetworkConfiguration.deny(),
    )


def _delivery(constraint: str) -> DeliveryRecord:
    if constraint == "filesystem":
        return DeliveryRecord(
            env={"TERMVERIFY_FS_ROOT": "C:\\sandbox\\fixture-root"},
            cwd="C:\\sandbox\\fixture-root",
        )
    return DeliveryRecord(env={f"TERMVERIFY_{constraint.upper()}": "value"})


def _receipt(
    constraint: str,
    tier: str,
    delivery: DeliveryRecord | None = None,
    run_id: str = RUN_ID,
) -> EnforcementReceipt:
    configuration = _configuration()
    effective = {
        "seed": configuration.seed,
        "clock": configuration.clock,
        "locale": configuration.locale,
        "timezone": configuration.timezone,
        "terminal": configuration.terminal,
        "filesystem": configuration.filesystem,
        "network": configuration.network,
    }[constraint]
    receipt_type = {
        "seed": SeedReceipt,
        "clock": ClockReceipt,
        "locale": LocaleReceipt,
        "timezone": TimezoneReceipt,
        "terminal": TerminalReceipt,
        "filesystem": FilesystemReceipt,
        "network": NetworkReceipt,
    }[constraint]
    return cast(
        EnforcementReceipt,
        receipt_type(
            run_id=run_id,
            effective=effective,
            tier=cast(EnforcementTier, tier),
            delivery=delivery,
        ),
    )


CONSTRAINTS = (
    "seed",
    "clock",
    "locale",
    "timezone",
    "terminal",
    "filesystem",
    "network",
)


# --- vocabulary -------------------------------------------------------------


def test_vocabulary_is_exactly_the_three_accepted_tiers_in_order() -> None:
    assert ENFORCEMENT_TIERS == ("os", "constructive", "delivered")


@pytest.mark.parametrize("tier", ["os", "constructive", "delivered"])
def test_vocabulary_membership_is_exact(tier: str) -> None:
    assert is_enforcement_tier(tier)


@pytest.mark.parametrize(
    "value",
    ["OS", "Delivered", "CONSTRUCTIVE", "delivered ", "", "sandbox", None, 1, b"os"],
)
def test_vocabulary_rejects_non_members_without_normalization(value: object) -> None:
    assert not is_enforcement_tier(value)


# --- mandatory tier on every receipt ---------------------------------------


@pytest.mark.parametrize("constraint", CONSTRAINTS)
def test_receipts_require_a_tier(constraint: str) -> None:
    configuration = _configuration()
    receipt_type, effective = {
        "seed": (SeedReceipt, configuration.seed),
        "clock": (ClockReceipt, configuration.clock),
        "locale": (LocaleReceipt, configuration.locale),
        "timezone": (TimezoneReceipt, configuration.timezone),
        "terminal": (TerminalReceipt, configuration.terminal),
        "filesystem": (FilesystemReceipt, configuration.filesystem),
        "network": (NetworkReceipt, configuration.network),
    }[constraint]

    with pytest.raises(TypeError):
        receipt_type(RUN_ID, effective)


@pytest.mark.parametrize("constraint", CONSTRAINTS)
@pytest.mark.parametrize("tier", ["OS", "enforced", "", "Delivered", 1, None])
def test_receipts_reject_tiers_outside_the_vocabulary(
    constraint: str, tier: object
) -> None:
    with pytest.raises((TypeError, ValueError), match="tier"):
        _receipt(constraint, cast(str, tier))


@pytest.mark.parametrize("constraint", CONSTRAINTS)
@pytest.mark.parametrize("tier", ["os", "constructive"])
def test_receipts_accept_vocabulary_tiers_without_delivery(
    constraint: str, tier: str
) -> None:
    receipt = _receipt(constraint, tier)
    assert receipt.tier == tier
    assert receipt.delivery is None


# --- delivered-tier pairing -------------------------------------------------


@pytest.mark.parametrize("constraint", CONSTRAINTS)
def test_delivered_tier_requires_a_delivery_record(constraint: str) -> None:
    with pytest.raises(ValueError, match="delivery"):
        _receipt(constraint, "delivered")


@pytest.mark.parametrize("constraint", CONSTRAINTS)
@pytest.mark.parametrize("tier", ["os", "constructive"])
def test_non_delivered_tiers_reject_a_delivery_record(
    constraint: str, tier: str
) -> None:
    with pytest.raises(ValueError, match="delivery"):
        _receipt(constraint, tier, _delivery(constraint))


@pytest.mark.parametrize("constraint", CONSTRAINTS)
def test_delivered_tier_carries_its_delivery_record(constraint: str) -> None:
    delivery = _delivery(constraint)
    receipt = _receipt(constraint, "delivered", delivery)
    assert receipt.tier == "delivered"
    assert receipt.delivery == delivery


@pytest.mark.parametrize("constraint", CONSTRAINTS)
def test_delivery_must_be_a_delivery_record(constraint: str) -> None:
    with pytest.raises(TypeError, match="delivery"):
        _receipt(
            constraint,
            "delivered",
            cast(DeliveryRecord, {"env": {"TERMVERIFY_SEED": "42"}}),
        )


def test_only_filesystem_delivery_names_a_working_directory() -> None:
    with pytest.raises(ValueError, match="working directory"):
        _receipt(
            "seed",
            "delivered",
            DeliveryRecord(env={"TERMVERIFY_SEED": "42"}, cwd="C:\\sandbox"),
        )


def test_filesystem_delivery_requires_its_working_directory() -> None:
    with pytest.raises(ValueError, match="working directory"):
        _receipt(
            "filesystem",
            "delivered",
            DeliveryRecord(env={"TERMVERIFY_FS_ROOT": "C:\\sandbox"}),
        )


# --- the delivery record ----------------------------------------------------


def test_delivery_record_freezes_its_environment() -> None:
    env = {"TERMVERIFY_SEED": "42"}
    record = DeliveryRecord(env=env)
    env["TERMVERIFY_SEED"] = "mutated"

    assert dict(record.env) == {"TERMVERIFY_SEED": "42"}
    with pytest.raises(TypeError):
        cast(dict[str, str], record.env)["TERMVERIFY_SEED"] = "mutated"


def test_delivery_record_requires_at_least_one_variable() -> None:
    with pytest.raises(ValueError, match="environment"):
        DeliveryRecord(env={})


@pytest.mark.parametrize(
    "env",
    [
        {"": "value"},
        {"TERMVERIFY_SEED": ""},
        {1: "value"},
        {"TERMVERIFY_SEED": 42},
        "TERMVERIFY_SEED=42",
        None,
    ],
)
def test_delivery_record_rejects_invalid_environments(env: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        DeliveryRecord(env=cast(dict[str, str], env))


@pytest.mark.parametrize("cwd", ["", 1, b"path"])
def test_delivery_record_rejects_invalid_working_directories(cwd: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        DeliveryRecord(env={"TERMVERIFY_FS_ROOT": "C:\\x"}, cwd=cast(str, cwd))


# --- authorization matrix: direct adapter ----------------------------------


class _DirectPorts:
    """Fake direct application ports stating one configurable tier."""

    def __init__(self, tier: str, delivery: bool = False) -> None:
        self._tier = tier
        self._delivery = delivery

    def _stamped(self, constraint: str, run_id: str) -> EnforcementReceipt:
        delivery = _delivery(constraint) if self._delivery else None
        return _receipt(constraint, self._tier, delivery, run_id=run_id)

    def enforce_seed(self, run_id: str, requested: int) -> object:
        del requested
        return self._stamped("seed", run_id)

    def enforce_clock(self, run_id: str, requested: ClockConfiguration) -> object:
        del requested
        return self._stamped("clock", run_id)

    def enforce_locale(self, run_id: str, requested: str) -> object:
        del requested
        return self._stamped("locale", run_id)

    def enforce_timezone(self, run_id: str, requested: str) -> object:
        del requested
        return self._stamped("timezone", run_id)

    def enforce_terminal(self, run_id: str, requested: TerminalConfiguration) -> object:
        del requested
        return self._stamped("terminal", run_id)

    def enforce_filesystem(
        self, run_id: str, requested: FilesystemConfiguration
    ) -> object:
        del requested
        return self._stamped("filesystem", run_id)

    def enforce_network(self, run_id: str, requested: NetworkConfiguration) -> object:
        del requested
        return self._stamped("network", run_id)

    def initialize(self) -> object:
        raise AssertionError("negotiation must fail before initialization")

    def dispatch(self, input_event: object) -> object:
        raise AssertionError("unreachable")

    def advance_clock(self, input_event: object) -> object:
        raise AssertionError("unreachable")

    def stop(self, input_event: object) -> object:
        raise AssertionError("unreachable")

    def abort(self, input_event: object) -> None:
        return None


@pytest.mark.parametrize(("tier", "delivery"), [("os", False), ("delivered", True)])
def test_direct_adapter_rejects_non_constructive_tiers_as_start_failed(
    tier: str, delivery: bool
) -> None:
    adapter = DirectAdapter(cast("object", _DirectPorts(tier, delivery)))  # type: ignore[arg-type]

    result = adapter.start(RUN_ID, _configuration())

    assert type(result) is StartFailed
    assert result.failure.code == "adapter-start-failed"
    assert result.enforced == ()
    details = cast(dict[str, object], result.failure.details)
    assert details["constraint"] == "seed"


# --- authorization matrix: conpty adapter ----------------------------------


class _Binding:
    """Fake binding: supported probe, refuses to spawn."""

    def __init__(self) -> None:
        self.spawn_calls = 0

    def is_supported(self) -> bool:
        return True

    def spawn(self, argv: Sequence[str], *, rows: int, columns: int) -> ConptyChildPort:
        self.spawn_calls += 1
        raise OSError("this negotiation fake refuses to spawn a child")


class _InjectedPorts:
    """Fake injected constraint ports stating one configurable tier."""

    def __init__(self, tier: str, delivery: bool = False) -> None:
        self._tier = tier
        self._delivery = delivery

    def _stamped(self, constraint: str, run_id: str) -> EnforcementReceipt:
        delivery = _delivery(constraint) if self._delivery else None
        return _receipt(constraint, self._tier, delivery, run_id=run_id)

    def enforce_seed(self, run_id: str, requested: int) -> object:
        del requested
        return self._stamped("seed", run_id)

    def enforce_clock(self, run_id: str, requested: ClockConfiguration) -> object:
        del requested
        return self._stamped("clock", run_id)

    def enforce_locale(self, run_id: str, requested: str) -> object:
        del requested
        return self._stamped("locale", run_id)

    def enforce_timezone(self, run_id: str, requested: str) -> object:
        del requested
        return self._stamped("timezone", run_id)

    def enforce_terminal(self, run_id: str, requested: TerminalConfiguration) -> object:
        raise AssertionError("terminal enforcement must never be delegated")

    def enforce_filesystem(
        self, run_id: str, requested: FilesystemConfiguration
    ) -> object:
        del requested
        return self._stamped("filesystem", run_id)

    def enforce_network(self, run_id: str, requested: NetworkConfiguration) -> object:
        del requested
        return self._stamped("network", run_id)


def _conpty_adapter(ports: _InjectedPorts) -> tuple[ConptyAdapter, _Binding]:
    binding = _Binding()
    adapter = ConptyAdapter(
        ("subject",),
        binding=binding,
        constraint_ports=cast("object", ports),  # type: ignore[arg-type]
        abort_deadline_ms=60_000,
    )
    return adapter, binding


@pytest.mark.parametrize("tier", ["constructive", "os"])
def test_conpty_adapter_rejects_non_delivered_injected_tiers_as_start_failed(
    tier: str,
) -> None:
    adapter, binding = _conpty_adapter(_InjectedPorts(tier))

    result = adapter.start(RUN_ID, _configuration())

    assert type(result) is StartFailed
    assert result.failure.code == "adapter-start-failed"
    assert result.enforced == ()
    details = cast(dict[str, object], result.failure.details)
    assert details["constraint"] == "seed"
    assert binding.spawn_calls == 0


def test_conpty_adapter_accepts_delivered_injected_receipts() -> None:
    adapter, binding = _conpty_adapter(_InjectedPorts("delivered", delivery=True))

    result = adapter.start(RUN_ID, _configuration())

    # Negotiation completes; the fake binding then refuses to spawn.
    assert type(result) is StartFailed
    assert len(result.enforced) == 7
    assert result.failure.details == {"during": "spawn"}
    assert binding.spawn_calls == 1
    terminal = result.enforced[4]
    assert type(terminal) is TerminalReceipt
    assert terminal.tier == "os"
    assert terminal.delivery is None
    seed = result.enforced[0]
    assert type(seed) is SeedReceipt
    assert seed.tier == "delivered"
    assert seed.delivery == _delivery("seed")


def test_conpty_terminal_receipt_states_the_os_tier() -> None:
    adapter, _ = _conpty_adapter(_InjectedPorts("delivered", delivery=True))

    result = adapter.start(RUN_ID, _configuration())

    assert type(result) is StartFailed
    receipt = result.enforced[4]
    assert type(receipt) is TerminalReceipt
    assert receipt.tier == "os"


# --- unsupported reports remain the honest refusal path ---------------------


def test_unsupported_report_is_still_distinct_from_tier_rejection() -> None:
    unsupported = ConstraintUnsupported(
        "seed", "constraint-not-enforced", "honestly not enforced"
    )
    assert unsupported.code == "constraint-not-enforced"
    failure = AdapterFailure("adapter-start-failed", "tier rejected")
    assert failure.code == "adapter-start-failed"


# --- transcript protocol amendment ------------------------------------------


BASIC_FIXTURE = Path("tests/fixtures/transcripts/v1/valid/basic.jsonl")


def _basic_records() -> list[dict[str, JsonValue]]:
    return parse_transcript(BASIC_FIXTURE.read_bytes())


def _capability_payload(
    records: list[dict[str, JsonValue]], index: int
) -> dict[str, JsonValue]:
    payload = records[index]["payload"]
    assert isinstance(payload, dict)
    return payload


def test_committed_fixture_capability_results_state_the_constructive_tier() -> None:
    records = _basic_records()
    for index in range(1, 8):
        assert _capability_payload(records, index)["tier"] == "constructive"


def test_enforced_capability_result_requires_a_tier() -> None:
    records = _basic_records()
    del _capability_payload(records, 1)["tier"]

    with pytest.raises(TranscriptValidationError, match="tier"):
        serialize_transcript(records)


@pytest.mark.parametrize("tier", ["OS", "enforced", "", 1, None, ["os"]])
def test_enforced_capability_result_rejects_non_vocabulary_tiers(
    tier: object,
) -> None:
    records = _basic_records()
    _capability_payload(records, 1)["tier"] = cast("JsonValue", tier)

    with pytest.raises(TranscriptValidationError, match="tier"):
        serialize_transcript(records)


def test_unsupported_capability_result_rejects_a_tier_member() -> None:
    records = parse_transcript(
        Path(
            "tests/fixtures/transcripts/v1/valid/unsupported-network.jsonl"
        ).read_bytes()
    )
    payload = records[7]["payload"]
    assert isinstance(payload, dict)
    assert payload["status"] == "unsupported"
    payload["tier"] = "constructive"

    with pytest.raises(TranscriptValidationError, match="member"):
        serialize_transcript(records)


@pytest.mark.parametrize("tier", ["os", "constructive"])
def test_non_delivered_capability_result_rejects_a_delivery_member(
    tier: str,
) -> None:
    records = _basic_records()
    payload = _capability_payload(records, 1)
    payload["tier"] = tier
    payload["delivery"] = {"env": {"TERMVERIFY_SEED": "0"}}

    with pytest.raises(TranscriptValidationError, match="delivery"):
        serialize_transcript(records)


def test_delivered_capability_result_requires_a_delivery_member() -> None:
    records = _basic_records()
    _capability_payload(records, 1)["tier"] = "delivered"

    with pytest.raises(TranscriptValidationError, match="delivery"):
        serialize_transcript(records)


def test_delivered_capability_result_round_trips() -> None:
    records = _basic_records()
    payload = _capability_payload(records, 1)
    payload["tier"] = "delivered"
    payload["delivery"] = {"env": {"TERMVERIFY_SEED": "0"}}
    filesystem = _capability_payload(records, 6)
    filesystem["tier"] = "delivered"
    filesystem["delivery"] = {
        "env": {"TERMVERIFY_FS_ROOT": "C:\\sandbox\\fixture-root"},
        "cwd": "C:\\sandbox\\fixture-root",
    }

    assert parse_transcript(serialize_transcript(records)) == records


@pytest.mark.parametrize(
    "delivery",
    [
        {},
        {"env": {}},
        {"env": {"": "x"}},
        {"env": {"TERMVERIFY_SEED": ""}},
        {"env": {"TERMVERIFY_SEED": 1}},
        {"env": "TERMVERIFY_SEED=0"},
        {"env": {"TERMVERIFY_SEED": "0"}, "cwd": "C:\\sandbox"},
        {"env": {"TERMVERIFY_SEED": "0"}, "unexpected": True},
        "delivered",
        None,
    ],
)
def test_delivered_capability_result_rejects_invalid_deliveries(
    delivery: object,
) -> None:
    records = _basic_records()
    payload = _capability_payload(records, 1)
    payload["tier"] = "delivered"
    payload["delivery"] = cast("JsonValue", delivery)

    with pytest.raises(TranscriptValidationError, match="delivery"):
        serialize_transcript(records)


def test_delivered_filesystem_capability_result_requires_a_cwd() -> None:
    records = _basic_records()
    filesystem = _capability_payload(records, 6)
    filesystem["tier"] = "delivered"
    filesystem["delivery"] = {"env": {"TERMVERIFY_FS_ROOT": "C:\\sandbox"}}

    with pytest.raises(TranscriptValidationError, match="delivery"):
        serialize_transcript(records)


# --- safe evidence redaction ------------------------------------------------


def test_safe_evidence_redacts_delivery_values_and_revalidates(
    tmp_path: Path,
) -> None:
    records = _basic_records()
    payload = _capability_payload(records, 6)
    payload["tier"] = "delivered"
    payload["delivery"] = {
        "env": {"TERMVERIFY_FS_ROOT": "C:\\Users\\secret\\sandbox"},
        "cwd": "C:\\Users\\secret\\sandbox",
    }
    destination = tmp_path / "safe.jsonl"

    persist_transcript_evidence(destination, records)

    persisted = parse_transcript(destination.read_bytes())
    redacted = persisted[6]["payload"]
    assert isinstance(redacted, dict)
    assert redacted["tier"] == "delivered"
    delivery = redacted["delivery"]
    assert isinstance(delivery, dict)
    assert "secret" not in serialize_transcript(persisted).decode("utf-8")
    env = delivery["env"]
    assert isinstance(env, dict)
    assert env and all("secret" not in name for name in env)
    assert all("secret" not in cast(str, value) for value in env.values())
    cwd = delivery["cwd"]
    assert isinstance(cwd, str) and "secret" not in cwd


def test_safe_evidence_preserves_the_stated_tier(tmp_path: Path) -> None:
    records = _basic_records()
    destination = tmp_path / "safe.jsonl"

    persist_transcript_evidence(destination, records)

    persisted = parse_transcript(destination.read_bytes())
    for index in range(1, 8):
        payload = persisted[index]["payload"]
        assert isinstance(payload, dict)
        assert payload["tier"] == "constructive"
