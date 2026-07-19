"""Caller-bound replay of `termverify.transcript/v1` source transcripts.

The replay engine is a pure consumer of the frozen v1 protocol: it takes a
validated source transcript and a caller-supplied adapter, re-executes the
source's configuration and input sequence in transcript order under the
same single-flight discipline, records the new run with the slice-1
recorder, and returns the new transcript plus the slice-2 comparison of
the two.

Replay binding is disclosed, not enforced: the engine records the
caller-supplied `termverify.replay-subject/v1` selector in the new
transcript and reports whether it equals the source's selector, but it
never resolves, launches, or version-matches subjects — selector agreement
is part of the verdict, not a precondition. A source whose lifecycle ended
in a failed or unsupported start replays nothing and reports that
structurally.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from termverify._json import JsonValue
from termverify.adapter import (
    Adapter,
    ClockAdvance,
    ClockConfiguration,
    FilesystemConfiguration,
    JsonInput,
    KeyInput,
    ManualTime,
    NetworkConfiguration,
    Resize,
    RunConfiguration,
    Started,
    StartFailed,
    StartTerminated,
    StartUnsupported,
    Stop,
    TerminalConfiguration,
    TerminalResult,
    TextInput,
)
from termverify.comparator import ComparisonVerdict, compare_transcripts
from termverify.recorder import ScriptedInput, TranscriptRecorder
from termverify.transcript import (
    Record,
    TranscriptValidationError,
    _json_equivalent,
    parse_transcript,
)

__all__ = [
    "ReplayError",
    "ReplayNotRun",
    "ReplayRun",
    "replay_transcript",
]

#: The two v1 input kinds the adapter contract cannot dispatch. A source
#: containing them fails closed before any adapter call; nothing is
#: silently skipped or fabricated.
_UNDISPATCHABLE_INPUT_KINDS = frozenset({"input.mouse", "input.clipboard_set"})


class ReplayError(ValueError):
    """A structured replay contract violation."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class ReplayRun:
    """The outcome of one executed replay.

    ``dispatched_inputs`` may be smaller than ``source_inputs`` when the
    new run terminated early — the remaining inputs are never dispatched,
    and the comparison then shows the resulting divergence. The comparison
    is the slice-2 verdict of source (left) against the new transcript
    (right); ``subject_matches_source`` reports the disclosed-not-enforced
    selector agreement.
    """

    transcript: bytes
    comparison: ComparisonVerdict
    subject_matches_source: bool
    source_inputs: int
    dispatched_inputs: int
    result: StartTerminated | StartUnsupported | StartFailed | TerminalResult


@dataclass(frozen=True, slots=True)
class ReplayNotRun:
    """A structural report that the source admits no replay.

    A source whose lifecycle ended in a failed or unsupported start never
    reached execution, so there is no input sequence to re-dispatch; the
    engine starts nothing and reports the source's terminal kind.
    """

    source_kind: str
    message: str


def _configuration_from_payload(config: dict[str, JsonValue]) -> RunConfiguration:
    clock = cast(dict[str, JsonValue], config["clock"])
    terminal = cast(dict[str, JsonValue], config["terminal"])
    filesystem = cast(dict[str, JsonValue], config["filesystem"])
    network = cast(dict[str, JsonValue], config["network"])
    if network["mode"] == "deny":
        network_configuration = NetworkConfiguration.deny()
    else:
        allowed = cast(list[dict[str, JsonValue]], network["allowed"])
        network_configuration = NetworkConfiguration.allow_list(
            tuple(
                (cast(str, entry["host"]), cast(int, entry["port"]))
                for entry in allowed
            )
        )
    return RunConfiguration(
        seed=int(cast(str, config["seed"])),
        clock=ClockConfiguration(initial_ms=cast(int, clock["initial_ms"])),
        locale=cast(str, config["locale"]),
        timezone=cast(str, config["timezone"]),
        terminal=TerminalConfiguration(
            columns=cast(int, terminal["columns"]),
            rows=cast(int, terminal["rows"]),
            capabilities=tuple(cast(list[str], terminal["capabilities"])),
        ),
        filesystem=FilesystemConfiguration(root_id=cast(str, filesystem["root_id"])),
        network=network_configuration,
    )


def _input_from_record(record: Record) -> ScriptedInput:
    kind = cast(str, record["kind"])
    payload = cast(dict[str, JsonValue], record["payload"])
    at_ms = ManualTime(cast(int, payload["at_ms"]))
    if kind == "input.text":
        return TextInput(at_ms, cast(str, payload["text"]))
    if kind == "input.key":
        return KeyInput(at_ms, tuple(cast(list[str], payload["keys"])))
    if kind == "input.resize":
        return Resize(at_ms, cast(int, payload["columns"]), cast(int, payload["rows"]))
    if kind == "input.clock_advanced":
        return ClockAdvance(at_ms, cast(int, payload["delta_ms"]))
    assert kind == "input.stop", kind
    return Stop(at_ms)


def replay_transcript(
    source: bytes,
    adapter: Adapter,
    run_id: str,
    subject: dict[str, JsonInput],
) -> ReplayRun | ReplayNotRun:
    """Re-execute a validated source transcript against a caller-bound adapter.

    The source must pass the strict codec; invalid bytes raise a
    structured :class:`ReplayError`. A source containing an input kind the
    adapter contract cannot dispatch fails closed before any adapter call.
    A replay whose input sequence completes with the new run still open is
    a structured error: the engine fabricates no stop the source did not
    contain. An adapter that refuses to start is an honest executed replay
    — its refusal is recorded and compared like any other outcome.

    ``x-`` extension members in the source's config or input payloads are
    not carried into the re-executed run — the adapter contract has no
    place for them — so such a source can never replay equivalent; the
    comparison discloses the difference.
    """
    if type(source) is not bytes:
        raise ReplayError("invalid-source", "source transcript must be bytes")
    try:
        source_records = parse_transcript(source)
    except TranscriptValidationError as error:
        raise ReplayError("invalid-source", str(error)) from error
    terminal_kind = cast(str, source_records[-1]["kind"])
    reached_execution = any(
        record["kind"] == "observation" for record in source_records
    )
    if terminal_kind == "run.unsupported" or (
        terminal_kind == "run.failed" and not reached_execution
    ):
        return ReplayNotRun(
            source_kind=terminal_kind,
            message="the source run never reached execution;"
            " there is nothing to replay",
        )
    input_records = [
        record
        for record in source_records
        if cast(str, record["kind"]).startswith("input.")
    ]
    undispatchable = sorted(
        {
            record["kind"]
            for record in input_records
            if record["kind"] in _UNDISPATCHABLE_INPUT_KINDS
        }
    )
    if undispatchable:
        raise ReplayError(
            "replay-unsupported-input",
            "the adapter contract cannot dispatch source input kinds:"
            f" {', '.join(undispatchable)}",
        )
    inputs = [_input_from_record(record) for record in input_records]
    started_payload = cast(dict[str, JsonValue], source_records[0]["payload"])
    configuration = _configuration_from_payload(
        cast(dict[str, JsonValue], started_payload["config"])
    )
    source_subject = cast(dict[str, JsonValue], started_payload["subject"])

    recorder = TranscriptRecorder(run_id, configuration, subject)
    start = adapter.start(run_id, configuration)
    recorder.record_start(start)
    dispatched = 0
    result: StartTerminated | StartUnsupported | StartFailed | TerminalResult
    if type(start) is Started:
        terminal: TerminalResult | None = None
        for input_event in inputs:
            if type(input_event) is ClockAdvance:
                epoch_result = adapter.advance_clock(input_event)
            elif type(input_event) is Stop:
                epoch_result = adapter.stop(input_event)
            else:
                epoch_result = adapter.dispatch(
                    cast(KeyInput | TextInput | Resize, input_event)
                )
            recorder.record_epoch(input_event, epoch_result)
            dispatched += 1
            if type(epoch_result) is TerminalResult:
                terminal = epoch_result
                break
        if terminal is None:
            raise ReplayError(
                "replay-not-terminated",
                "the source input sequence ended while the replayed run was still open",
            )
        result = terminal
    else:
        result = cast(StartTerminated | StartUnsupported | StartFailed, start)
    new_transcript = recorder.transcript()
    subject_record = cast(
        dict[str, JsonValue],
        cast(dict[str, JsonValue], parse_transcript(new_transcript)[0]["payload"])[
            "subject"
        ],
    )
    return ReplayRun(
        transcript=new_transcript,
        comparison=compare_transcripts(source, new_transcript),
        subject_matches_source=_json_equivalent(source_subject, subject_record),
        source_inputs=len(inputs),
        dispatched_inputs=dispatched,
        result=result,
    )
