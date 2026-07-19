"""External conformance: reproduce the GlyphWright spike transcript.

GlyphWright's hand-written spike recorder (issue #114) produced the
committed fixture against ``DirectAdapter``. ``TranscriptRecorder`` must
reproduce a semantically identical transcript from the equivalent adapter
result sequence. The spike predates the mandatory enforcement-tier member,
so the only tolerated difference is the recorder's ``"tier"`` on enforced
capability payloads; see the fixture's ``PROVENANCE.md``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from termverify.adapter import (
    ClockAdvance,
    ClockConfiguration,
    ClockReceipt,
    Cursor,
    Diagnostic,
    DispatchInput,
    EnforcedConstraints,
    EpochCompleted,
    Event,
    ExitStatus,
    FilesystemConfiguration,
    FilesystemReceipt,
    Frame,
    KeyInput,
    LocaleReceipt,
    ManualTime,
    NetworkConfiguration,
    NetworkReceipt,
    Observation,
    ProcessObservation,
    Region,
    Resize,
    RunConfiguration,
    RunFinished,
    SeedReceipt,
    Started,
    Stop,
    TerminalConfiguration,
    TerminalReceipt,
    TerminalResult,
    TextInput,
    TimezoneReceipt,
    UiObservation,
)
from termverify.recorder import TranscriptRecorder
from termverify.transcript import parse_transcript

FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "external"
    / "glyphwright-direct-spike"
    / "transcript.jsonl"
)


def _configuration_from_payload(config: dict[str, Any]) -> RunConfiguration:
    assert config["clock"]["mode"] == "manual"
    assert config["filesystem"]["mode"] == "sandbox"
    assert config["network"] == {"mode": "deny"}
    return RunConfiguration(
        seed=int(config["seed"]),
        clock=ClockConfiguration(initial_ms=config["clock"]["initial_ms"]),
        locale=config["locale"],
        timezone=config["timezone"],
        terminal=TerminalConfiguration(
            columns=config["terminal"]["columns"],
            rows=config["terminal"]["rows"],
            capabilities=tuple(config["terminal"]["capabilities"]),
        ),
        filesystem=FilesystemConfiguration(root_id=config["filesystem"]["root_id"]),
        network=NetworkConfiguration.deny(),
    )


def _constructive_constraints(
    run_id: str, configuration: RunConfiguration
) -> EnforcedConstraints:
    return EnforcedConstraints(
        run_id=run_id,
        requested=configuration,
        seed=SeedReceipt(run_id, configuration.seed, "constructive"),
        clock=ClockReceipt(run_id, configuration.clock, "constructive"),
        locale=LocaleReceipt(run_id, configuration.locale, "constructive"),
        timezone=TimezoneReceipt(run_id, configuration.timezone, "constructive"),
        terminal=TerminalReceipt(run_id, configuration.terminal, "constructive"),
        filesystem=FilesystemReceipt(run_id, configuration.filesystem, "constructive"),
        network=NetworkReceipt(run_id, configuration.network, "constructive"),
    )


def _observation_from_payload(payload: dict[str, Any]) -> Observation:
    ui = payload["ui"]
    process = payload.get("process")
    frame = payload.get("frame")
    return Observation(
        at_ms=ManualTime(payload["at_ms"]),
        state=payload["state"],
        events=tuple(
            Event(event["type"], event["data"]) for event in payload["events"]
        ),
        ui=UiObservation(
            regions=tuple(
                Region(
                    region["id"],
                    region["role"],
                    region["bounds"]["column"],
                    region["bounds"]["row"],
                    region["bounds"]["columns"],
                    region["bounds"]["rows"],
                )
                for region in ui["regions"]
            ),
            focus=ui["focus"],
            cursor=Cursor(
                ui["cursor"]["column"],
                ui["cursor"]["row"],
                ui["cursor"]["visible"],
            ),
            mode=ui["mode"],
        ),
        frame=Frame(
            lines=tuple(frame["lines"]),
            columns=frame["columns"],
            rows=frame["rows"],
        )
        if frame is not None
        else None,
        process=ProcessObservation.running()
        if process is not None and process["state"] == "running"
        else ProcessObservation.exited(
            ExitStatus(process["exit"]["kind"], process["exit"]["value"])
        )
        if process is not None
        else None,
    )


def _input_from_record(record: dict[str, Any]) -> DispatchInput | ClockAdvance | Stop:
    payload = record["payload"]
    at_ms = ManualTime(payload["at_ms"])
    kind = record["kind"]
    if kind == "input.text":
        return TextInput(at_ms, payload["text"])
    if kind == "input.key":
        return KeyInput(at_ms, tuple(payload["keys"]))
    if kind == "input.resize":
        return Resize(at_ms, payload["columns"], payload["rows"])
    if kind == "input.clock_advanced":
        return ClockAdvance(at_ms, payload["delta_ms"])
    assert kind == "input.stop"
    return Stop(at_ms)


def test_recorder_reproduces_the_glyphwright_spike_transcript() -> None:
    spike_records = [
        cast(dict[str, Any], json.loads(line))
        for line in FIXTURE.read_bytes()[:-1].split(b"\n")
    ]
    started_payload = spike_records[0]["payload"]
    run_id = spike_records[0]["run_id"]
    configuration = _configuration_from_payload(started_payload["config"])

    recorder = TranscriptRecorder(run_id, configuration, started_payload["subject"])
    body = spike_records[8:-1]
    terminal = spike_records[-1]
    assert body[0]["kind"] == "observation"
    recorder.record_start(
        Started(
            _constructive_constraints(run_id, configuration),
            _observation_from_payload(body[0]["payload"]),
        )
    )
    index = 1
    while index < len(body):
        input_record = body[index]
        assert input_record["kind"].startswith("input.")
        input_event = _input_from_record(input_record)
        index += 1
        diagnostics: list[Diagnostic] = []
        while body[index]["kind"] == "diagnostic":
            payload = body[index]["payload"]
            diagnostics.append(
                Diagnostic(
                    ManualTime(payload["at_ms"]),
                    payload["code"],
                    payload["message"],
                    payload.get("details"),
                )
            )
            index += 1
        assert body[index]["kind"] == "observation"
        observation = _observation_from_payload(body[index]["payload"])
        index += 1
        if index == len(body):
            assert terminal["kind"] == "run.finished"
            exit_payload = terminal["payload"]["exit"]
            recorder.record_epoch(
                input_event,
                TerminalResult(
                    observation,
                    RunFinished(
                        ExitStatus(exit_payload["kind"], exit_payload["value"])
                    ),
                    diagnostics=tuple(diagnostics),
                ),
            )
        else:
            recorder.record_epoch(
                input_event,
                EpochCompleted(observation, diagnostics=tuple(diagnostics)),
            )

    reproduced = parse_transcript(recorder.transcript())

    assert len(reproduced) == len(spike_records)
    for spike_record, record in zip(spike_records, reproduced, strict=True):
        for member in ("protocol", "run_id", "seq", "id", "kind"):
            assert record[member] == spike_record[member]
        expected_payload = dict(spike_record["payload"])
        if (
            spike_record["kind"] == "capability.result"
            and expected_payload["status"] == "enforced"
        ):
            expected_payload["tier"] = "constructive"
        assert record["payload"] == expected_payload, spike_record["id"]
