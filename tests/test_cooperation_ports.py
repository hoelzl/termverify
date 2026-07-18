"""Cooperation ports and evidence-driven spawn delivery (slice 2).

Slice 2 of the accepted cooperation-tier design
(`docs/agent/design/cooperation-tier-constraint-ports.md`): the opt-in
delivered-tier constraint ports with their per-constraint delivery
contracts, the injectable directory probe, and the ConPTY adapter's spawn
overlay assembled from validated delivery records. Everything here is
cross-platform and fake-driven; the native spawn plumbing has its own
Windows-matrix evidence in ``test_conpty_binding.py``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

import pytest

from termverify.adapter import (
    AdapterFailure,
    ClockConfiguration,
    ClockReceipt,
    ConstraintUnsupported,
    DeliveryRecord,
    FilesystemConfiguration,
    FilesystemReceipt,
    NetworkConfiguration,
    NetworkReceipt,
    RunConfiguration,
    SeedReceipt,
    StartFailed,
    StartUnsupported,
    TerminalConfiguration,
)
from termverify.conpty import ConptyAdapter, ConptyChildPort
from termverify.cooperation import (
    CooperationConstraintPorts,
    DirectoryProbePort,
    RealDirectoryProbe,
)

RUN_ID = "run-cooperation"


def _configuration(
    timezone: str = "UTC",
    network: NetworkConfiguration | None = None,
    root_id: str = "sandbox",
) -> RunConfiguration:
    return RunConfiguration(
        seed=42,
        clock=ClockConfiguration(initial_ms=1_000),
        locale="en-US",
        timezone=timezone,
        terminal=TerminalConfiguration(columns=80, rows=24, capabilities=()),
        filesystem=FilesystemConfiguration(root_id=root_id),
        network=network if network is not None else NetworkConfiguration.deny(),
    )


class _FakeProbe:
    """Fake directory probe with scripted resolutions."""

    def __init__(self, resolutions: Mapping[str, str | None]) -> None:
        self._resolutions = dict(resolutions)
        self.calls: list[str] = []

    def resolve_directory(self, path: str) -> str | None:
        self.calls.append(path)
        return self._resolutions.get(path)


def _ports(
    roots: Mapping[str, str] | None = None,
    probe: DirectoryProbePort | None = None,
) -> CooperationConstraintPorts:
    if roots is None:
        roots = {"sandbox": "C:\\hosts\\sandbox"}
    if probe is None:
        probe = _FakeProbe({"C:\\hosts\\sandbox": "C:\\resolved\\sandbox"})
    return CooperationConstraintPorts(roots, directory_probe=probe)


# --- per-constraint delivery contracts --------------------------------------


def test_seed_delivery_is_the_exact_decimal() -> None:
    receipt = _ports().enforce_seed(RUN_ID, 42)

    assert type(receipt) is SeedReceipt
    assert receipt.run_id == RUN_ID
    assert receipt.effective == 42
    assert receipt.tier == "delivered"
    assert receipt.delivery == DeliveryRecord(env={"TERMVERIFY_SEED": "42"})


def test_seed_delivery_zero_is_delivered() -> None:
    receipt = _ports().enforce_seed(RUN_ID, 0)

    assert type(receipt) is SeedReceipt
    assert receipt.delivery is not None
    assert dict(receipt.delivery.env) == {"TERMVERIFY_SEED": "0"}


def test_clock_delivery_is_the_initial_manual_time_only() -> None:
    receipt = _ports().enforce_clock(RUN_ID, ClockConfiguration(initial_ms=1_000))

    assert receipt == ClockReceipt(
        RUN_ID,
        ClockConfiguration(initial_ms=1_000),
        "delivered",
        DeliveryRecord(env={"TERMVERIFY_CLOCK_INITIAL_MS": "1000"}),
    )


def test_locale_delivery_is_the_validated_tag_without_platform_variables() -> None:
    receipt = _ports().enforce_locale(RUN_ID, "en-US")

    assert receipt.tier == "delivered"  # type: ignore[union-attr]
    delivery = cast(DeliveryRecord, receipt.delivery)  # type: ignore[union-attr]
    assert dict(delivery.env) == {"TERMVERIFY_LOCALE": "en-US"}
    assert "LANG" not in delivery.env
    assert "LC_ALL" not in delivery.env


def test_timezone_delivery_is_utc_with_the_portable_posix_spelling() -> None:
    receipt = _ports().enforce_timezone(RUN_ID, "UTC")

    assert receipt.tier == "delivered"  # type: ignore[union-attr]
    delivery = cast(DeliveryRecord, receipt.delivery)  # type: ignore[union-attr]
    assert dict(delivery.env) == {"TZ": "UTC0", "TERMVERIFY_TIMEZONE": "UTC"}


def test_non_utc_timezone_request_is_unsupported() -> None:
    result = _ports().enforce_timezone(RUN_ID, "Europe/Berlin")

    assert type(result) is ConstraintUnsupported
    assert result.constraint == "timezone"
    assert result.code == "constraint-unsupported"


def test_terminal_enforcement_is_truthfully_not_enforced() -> None:
    result = _ports().enforce_terminal(
        RUN_ID, TerminalConfiguration(columns=80, rows=24, capabilities=())
    )

    assert type(result) is ConstraintUnsupported
    assert result.constraint == "terminal"
    assert result.code == "constraint-not-enforced"


def test_network_deny_delivery() -> None:
    receipt = _ports().enforce_network(RUN_ID, NetworkConfiguration.deny())

    assert receipt.tier == "delivered"  # type: ignore[union-attr]
    delivery = cast(DeliveryRecord, receipt.delivery)  # type: ignore[union-attr]
    assert dict(delivery.env) == {"TERMVERIFY_NETWORK": "deny"}


def test_network_allow_list_request_is_unsupported() -> None:
    result = _ports().enforce_network(
        RUN_ID, NetworkConfiguration.allow_list((("example.test", 443),))
    )

    assert type(result) is ConstraintUnsupported
    assert result.constraint == "network"
    assert result.code == "constraint-unsupported"


# --- filesystem sandbox contract --------------------------------------------


def test_filesystem_delivery_resolves_through_the_probe() -> None:
    probe = _FakeProbe({"C:\\hosts\\sandbox": "C:\\resolved\\sandbox"})
    ports = _ports(probe=probe)

    receipt = ports.enforce_filesystem(
        RUN_ID, FilesystemConfiguration(root_id="sandbox")
    )

    assert type(receipt) is FilesystemReceipt
    assert receipt.tier == "delivered"
    delivery = cast(DeliveryRecord, receipt.delivery)
    assert dict(delivery.env) == {"TERMVERIFY_FS_ROOT": "C:\\resolved\\sandbox"}
    assert delivery.cwd == "C:\\resolved\\sandbox"
    assert probe.calls == ["C:\\hosts\\sandbox"]


def test_unknown_sandbox_root_is_unsupported() -> None:
    probe = _FakeProbe({})
    ports = _ports(probe=probe)

    result = ports.enforce_filesystem(
        RUN_ID, FilesystemConfiguration(root_id="unmapped")
    )

    assert type(result) is ConstraintUnsupported
    assert result.constraint == "filesystem"
    assert result.code == "constraint-unsupported"
    assert probe.calls == []


def test_unresolvable_sandbox_root_is_unsupported() -> None:
    probe = _FakeProbe({"C:\\hosts\\sandbox": None})
    ports = _ports(probe=probe)

    result = ports.enforce_filesystem(
        RUN_ID, FilesystemConfiguration(root_id="sandbox")
    )

    assert type(result) is ConstraintUnsupported
    assert result.constraint == "filesystem"
    assert result.code == "constraint-unsupported"
    assert probe.calls == ["C:\\hosts\\sandbox"]


def test_ports_validate_the_root_mapping_at_construction() -> None:
    with pytest.raises(ValueError, match="root"):
        CooperationConstraintPorts({"": "C:\\x"})
    with pytest.raises(ValueError, match="root"):
        CooperationConstraintPorts({"sandbox": ""})
    with pytest.raises(TypeError):
        CooperationConstraintPorts(cast("Mapping[str, str]", {"sandbox": 1}))
    with pytest.raises(TypeError):
        CooperationConstraintPorts(cast("Mapping[str, str]", "sandbox"))


def test_ports_do_not_share_mutable_root_state() -> None:
    roots = {"sandbox": "C:\\hosts\\sandbox"}
    probe = _FakeProbe({"C:\\hosts\\sandbox": "C:\\resolved\\sandbox"})
    ports = CooperationConstraintPorts(roots, directory_probe=probe)
    roots["sandbox"] = "C:\\mutated"

    receipt = ports.enforce_filesystem(
        RUN_ID, FilesystemConfiguration(root_id="sandbox")
    )

    assert type(receipt) is FilesystemReceipt
    assert probe.calls == ["C:\\hosts\\sandbox"]


def test_real_directory_probe_resolves_existing_directories(
    tmp_path: Path,
) -> None:
    probe = RealDirectoryProbe()
    resolved = probe.resolve_directory(str(tmp_path))

    assert resolved is not None
    assert Path(resolved).is_absolute()
    assert Path(resolved).is_dir()


def test_real_directory_probe_rejects_missing_and_file_paths(
    tmp_path: Path,
) -> None:
    probe = RealDirectoryProbe()
    file_path = tmp_path / "file.txt"
    file_path.write_text("not a directory", encoding="utf-8")

    assert probe.resolve_directory(str(tmp_path / "missing")) is None
    assert probe.resolve_directory(str(file_path)) is None


def test_ports_create_and_delete_nothing(tmp_path: Path) -> None:
    root = tmp_path / "sandbox"
    root.mkdir()
    (root / "existing.txt").write_text("host-owned", encoding="utf-8")
    ports = CooperationConstraintPorts({"sandbox": str(root)})

    receipt = ports.enforce_filesystem(
        RUN_ID, FilesystemConfiguration(root_id="sandbox")
    )

    assert type(receipt) is FilesystemReceipt
    assert sorted(p.name for p in root.iterdir()) == ["existing.txt"]


# --- delivery record tightening (carried slice-1 review nit) ----------------


@pytest.mark.parametrize(
    "env",
    [
        {"A=B": "value"},
        {"NUL\0NAME": "value"},
        {"TERMVERIFY_SEED": "va\0lue"},
    ],
)
def test_delivery_record_rejects_undeliverable_variables(
    env: dict[str, str],
) -> None:
    with pytest.raises(ValueError, match="delivery env"):
        DeliveryRecord(env=env)


def test_delivery_record_rejects_nul_in_cwd() -> None:
    with pytest.raises(ValueError, match="cwd"):
        DeliveryRecord(env={"TERMVERIFY_FS_ROOT": "C:\\x"}, cwd="C:\\x\0y")


# --- evidence-driven spawn overlay ------------------------------------------


class _RecordingBinding:
    """Fake binding recording the spawn overlay; refuses to spawn."""

    def __init__(self) -> None:
        self.spawns: list[
            tuple[tuple[str, ...], int, int, dict[str, str] | None, str | None]
        ] = []

    def is_supported(self) -> bool:
        return True

    def spawn(
        self,
        argv: Sequence[str],
        *,
        rows: int,
        columns: int,
        env_overlay: Mapping[str, str] | None = None,
        cwd: str | None = None,
    ) -> ConptyChildPort:
        self.spawns.append(
            (
                tuple(argv),
                rows,
                columns,
                dict(env_overlay) if env_overlay is not None else None,
                cwd,
            )
        )
        raise OSError("this overlay fake refuses to spawn a child")


def _cooperation_adapter(
    ports: CooperationConstraintPorts | None = None,
) -> tuple[ConptyAdapter, _RecordingBinding]:
    binding = _RecordingBinding()
    if ports is None:
        ports = _ports(
            probe=_FakeProbe({"C:\\hosts\\sandbox": "C:\\resolved\\sandbox"})
        )
    adapter = ConptyAdapter(
        ("subject",),
        binding=binding,
        constraint_ports=ports,
        abort_deadline_ms=60_000,
    )
    return adapter, binding


def test_spawn_overlay_is_assembled_from_the_validated_receipts() -> None:
    adapter, binding = _cooperation_adapter()

    result = adapter.start(RUN_ID, _configuration())

    assert type(result) is StartFailed
    assert result.failure.details == {"during": "spawn"}
    assert len(binding.spawns) == 1
    argv, rows, columns, overlay, cwd = binding.spawns[0]
    assert argv == ("subject",)
    assert (rows, columns) == (24, 80)
    assert overlay == {
        "TERMVERIFY_SEED": "42",
        "TERMVERIFY_CLOCK_INITIAL_MS": "1000",
        "TERMVERIFY_LOCALE": "en-US",
        "TZ": "UTC0",
        "TERMVERIFY_TIMEZONE": "UTC",
        "TERMVERIFY_FS_ROOT": "C:\\resolved\\sandbox",
        "TERMVERIFY_NETWORK": "deny",
    }
    assert cwd == "C:\\resolved\\sandbox"


def test_unsupported_cooperation_request_still_ends_before_any_child() -> None:
    adapter, binding = _cooperation_adapter()

    result = adapter.start(RUN_ID, _configuration(timezone="Europe/Berlin"))

    assert type(result) is StartUnsupported
    assert result.constraint == "timezone"
    assert binding.spawns == []


class _CollidingPorts(CooperationConstraintPorts):
    """Hostile ports delivering a colliding variable name for the network."""

    def enforce_network(
        self, run_id: str, requested: NetworkConfiguration
    ) -> NetworkReceipt | ConstraintUnsupported | AdapterFailure:
        del requested
        return NetworkReceipt(
            run_id,
            NetworkConfiguration.deny(),
            "delivered",
            DeliveryRecord(env={"TERMVERIFY_SEED": "collision"}),
        )


def test_colliding_delivery_records_are_an_invariant_breach() -> None:
    ports = _CollidingPorts(
        {"sandbox": "C:\\hosts\\sandbox"},
        directory_probe=_FakeProbe({"C:\\hosts\\sandbox": "C:\\resolved\\sandbox"}),
    )
    adapter, binding = _cooperation_adapter(ports)

    result = adapter.start(RUN_ID, _configuration())

    assert type(result) is StartFailed
    assert result.failure.code == "adapter-start-failed"
    assert len(result.enforced) == 7
    details = cast(dict[str, object], result.failure.details)
    assert details.get("invariant") == "delivery-disjoint"
    assert binding.spawns == []


def test_overlay_is_omitted_without_delivered_receipts() -> None:
    # A start that never completes negotiation spawns nothing; the overlay
    # path is exercised only by delivered receipts. Mixed negotiation is not
    # constructible with shipped ports, so drive the assembly helper
    # directly for the no-delivery shape.
    from termverify.conpty import _assemble_spawn_overlay

    overlay, cwd = _assemble_spawn_overlay(())

    assert overlay is None
    assert cwd is None


def test_assembly_rejects_a_second_working_directory() -> None:
    from termverify.conpty import _assemble_spawn_overlay

    with pytest.raises(ValueError, match="working directory"):
        _assemble_spawn_overlay(
            (
                DeliveryRecord(env={"A": "1"}, cwd="C:\\one"),
                DeliveryRecord(env={"B": "2"}, cwd="C:\\two"),
            )
        )


def test_assembly_rejects_colliding_variable_names() -> None:
    from termverify.conpty import _assemble_spawn_overlay

    with pytest.raises(ValueError, match="disjoint"):
        _assemble_spawn_overlay(
            (
                DeliveryRecord(env={"A": "1"}),
                DeliveryRecord(env={"A": "2"}),
            )
        )


# --- negotiation compatibility ----------------------------------------------


def test_cooperation_ports_satisfy_the_conpty_authorization_matrix() -> None:
    adapter, binding = _cooperation_adapter()

    result = adapter.start(RUN_ID, _configuration())

    assert type(result) is StartFailed
    assert len(result.enforced) == 7
    for index, receipt in enumerate(result.enforced):
        if index == 4:
            assert receipt.tier == "os"
        else:
            assert receipt.tier == "delivered"


def test_cooperation_ports_reject_a_raising_probe_as_unsupported_only() -> None:
    class _RaisingProbe:
        def resolve_directory(self, path: str) -> str | None:
            raise OSError("probe exploded")

    ports = _ports(probe=_RaisingProbe())
    adapter, binding = _cooperation_adapter(ports)

    result = adapter.start(RUN_ID, _configuration())

    # A raising probe is a raising port: the negotiation loop classifies it
    # fail-closed as StartFailed at the filesystem constraint.
    assert type(result) is StartFailed
    details = cast(dict[str, object], result.failure.details)
    assert details == {"constraint": "filesystem"}
    assert binding.spawns == []


def test_unused_failure_is_adapter_failure_type() -> None:
    assert AdapterFailure("adapter-start-failed", "x").code == "adapter-start-failed"
