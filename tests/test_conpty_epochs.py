"""Epoch-machinery evidence for the public ConPTY adapter (slice 3).

Everything here runs cross-platform against fake bindings, fake normalizers,
and a fake watchdog trigger: the readiness-marker protocol, the epoch loop,
the failure-classification matrix, watchdog-driven deadline aborts, and forced
stop teardown. Nothing here claims ConPTY passes the private-OSC marker
default through; that evidence lives in the Windows integration module
(`test_conpty_integration.py`).
"""

from __future__ import annotations

import os
import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from typing import cast

import pytest

from termverify._conpty import (
    ConptyClosedError,
    ConptyConcurrentIOError,
    ConptyEndOfStreamError,
)
from termverify.adapter import (
    AdapterFailure,
    ClockAdvance,
    ClockConfiguration,
    ClockReceipt,
    ConstraintUnsupported,
    Cursor,
    DeliveryRecord,
    EpochCompleted,
    ExitStatus,
    FilesystemConfiguration,
    FilesystemReceipt,
    Frame,
    JsonInput,
    KeyInput,
    LocaleReceipt,
    ManualTime,
    NetworkConfiguration,
    NetworkReceipt,
    Resize,
    RunConfiguration,
    RunFailed,
    RunFinished,
    SeedReceipt,
    Started,
    StartFailed,
    StartTerminated,
    Stop,
    TerminalConfiguration,
    TerminalReceipt,
    TerminalResult,
    TextInput,
    TimezoneReceipt,
)
from termverify.conpty import (
    _FIXED_RECORD_STRING_BYTES,
    _MAX_UTF8_BYTES_PER_CELL,
    READINESS_MARKER_DEFAULT,
    ConptyAdapter,
    ConptyChildPort,
    TimerWatchdog,
)
from termverify.recorder import TranscriptRecorder
from termverify.transcript import (
    _MAX_COLLECTION_ITEMS,
    _MAX_RECORD_STRING_BYTES,
    _MAX_STRING_BYTES,
)
from termverify.vt import ScreenSnapshot, VtNormalizationError

_MARKER = READINESS_MARKER_DEFAULT
_DEADLINE_MS = 60_000

#: Minimal valid replay subject, so budget evidence can be pushed through the
#: real recorder and codec rather than through a replica of their rules.
_REPLAY_SUBJECT: dict[str, JsonInput] = {
    "format": "termverify.replay-subject/v1",
    "application": {"id": "fixture-app", "version": "1", "build": "b1"},
    "fixture": {"id": "basic", "version": "1"},
    "adapter": {"id": "termverify.conpty", "version": "1"},
    "normalizer": {"id": "termverify.identity", "version": "1"},
    "state_schema": {"id": "fixture-state", "version": "1"},
}


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
    """One structurally valid fake delivery record per constraint.

    The filesystem record names this process's working directory: fakes
    never inspect it, but the Windows integration module reuses these ports
    against the real binding, whose child must start in a directory that
    actually exists.
    """
    if constraint == "filesystem":
        root = os.getcwd()
        return DeliveryRecord(env={"TERMVERIFY_FS_ROOT": root}, cwd=root)
    return DeliveryRecord(env={f"TERMVERIFY_{constraint.upper()}": "value"})


class _EnforcingPorts:
    """Fake injected ports stating the delivered tier for every constraint."""

    def enforce_seed(
        self, run_id: str, requested: int
    ) -> SeedReceipt | ConstraintUnsupported | AdapterFailure:
        return SeedReceipt(run_id, requested, "delivered", _delivery("seed"))

    def enforce_clock(
        self, run_id: str, requested: ClockConfiguration
    ) -> ClockReceipt | ConstraintUnsupported | AdapterFailure:
        return ClockReceipt(run_id, requested, "delivered", _delivery("clock"))

    def enforce_locale(
        self, run_id: str, requested: str
    ) -> LocaleReceipt | ConstraintUnsupported | AdapterFailure:
        return LocaleReceipt(run_id, requested, "delivered", _delivery("locale"))

    def enforce_timezone(
        self, run_id: str, requested: str
    ) -> TimezoneReceipt | ConstraintUnsupported | AdapterFailure:
        return TimezoneReceipt(run_id, requested, "delivered", _delivery("timezone"))

    def enforce_terminal(
        self, run_id: str, requested: TerminalConfiguration
    ) -> TerminalReceipt | ConstraintUnsupported | AdapterFailure:
        raise AssertionError("terminal enforcement must never be delegated")

    def enforce_filesystem(
        self, run_id: str, requested: FilesystemConfiguration
    ) -> FilesystemReceipt | ConstraintUnsupported | AdapterFailure:
        return FilesystemReceipt(
            run_id, requested, "delivered", _delivery("filesystem")
        )

    def enforce_network(
        self, run_id: str, requested: NetworkConfiguration
    ) -> NetworkReceipt | ConstraintUnsupported | AdapterFailure:
        return NetworkReceipt(run_id, requested, "delivered", _delivery("network"))


class _FakeChild:
    """Scripted per-child binding fake with binding-faithful close semantics."""

    def __init__(
        self,
        reads: Sequence[str | Exception] = (),
        *,
        exit_status: int | str | None = None,
        write_error: Exception | None = None,
        resize_error: Exception | None = None,
        close_error: Exception | None = None,
    ) -> None:
        self.reads = list(reads)
        self.reported_exit_status = exit_status
        self.write_error = write_error
        self.resize_error = resize_error
        self.close_error = close_error
        self.written: list[str] = []
        self.resizes: list[tuple[int, int]] = []
        self.closes: list[bool] = []
        self.closed = False
        #: Reads served, cumulative. `reads` is the *remaining* script, so it
        #: empties on every path and cannot witness that a read was skipped.
        self.reads_served = 0

    @property
    def pid(self) -> int:
        return 4711

    @property
    def exit_status(self) -> int | None:
        return cast("int | None", self.reported_exit_status)

    def read(self) -> str:
        if self.closed:
            raise ConptyClosedError("the ConPTY binding is closed")
        if not self.reads:
            raise AssertionError("the fake child was read past its script")
        item = self.reads.pop(0)
        self.reads_served += 1
        if isinstance(item, Exception):
            raise item
        return item

    def write(self, text: str) -> None:
        if self.closed:
            raise ConptyClosedError("the ConPTY binding is closed")
        if self.write_error is not None:
            raise self.write_error
        self.written.append(text)

    def resize(self, *, rows: int, columns: int) -> None:
        if self.resize_error is not None:
            raise self.resize_error
        self.resizes.append((rows, columns))

    def is_alive(self) -> bool:
        return not self.closed

    def close(self, *, force: bool) -> None:
        self.closes.append(force)
        if self.close_error is not None:
            raise self.close_error
        self.closed = True


class _FakeBinding:
    def __init__(
        self,
        child: _FakeChild | None = None,
        *,
        spawn_error: Exception | None = None,
    ) -> None:
        self.child = child if child is not None else _FakeChild()
        self._spawn_error = spawn_error
        self.spawns: list[tuple[tuple[str, ...], int, int]] = []

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
        self.spawns.append((tuple(argv), rows, columns))
        if self._spawn_error is not None:
            raise self._spawn_error
        return self.child


class _FakeNormalizer:
    def __init__(
        self,
        *,
        rows: int,
        columns: int,
        feed_error: Exception | None = None,
        snapshot_error: Exception | None = None,
        frame_dimensions: tuple[int, int] | None = None,
        frame_cell: str = " ",
    ) -> None:
        self.rows = rows
        self.columns = columns
        self.frame_cell = frame_cell
        self.feed_error = feed_error
        self.snapshot_error = snapshot_error
        self.frame_dimensions = frame_dimensions
        self.fed: list[str] = []
        self.resizes: list[tuple[int, int]] = []

    def feed(self, chunk: str) -> None:
        if self.feed_error is not None:
            raise self.feed_error
        self.fed.append(chunk)

    def notify_resize(self, *, rows: int, columns: int) -> None:
        self.resizes.append((rows, columns))
        self.rows = rows
        self.columns = columns

    def snapshot(self) -> ScreenSnapshot:
        if self.snapshot_error is not None:
            raise self.snapshot_error
        rows, columns = self.frame_dimensions or (self.rows, self.columns)
        return ScreenSnapshot(
            frame=Frame(
                lines=(self.frame_cell * columns,) * rows, columns=columns, rows=rows
            ),
            cursor=Cursor(column=0, row=0, visible=True),
            mode="normal",
        )


class _NormalizerFactory:
    def __init__(
        self,
        *,
        feed_error: Exception | None = None,
        snapshot_error: Exception | None = None,
        frame_dimensions: tuple[int, int] | None = None,
        frame_cell: str = " ",
    ) -> None:
        self._feed_error = feed_error
        self._snapshot_error = snapshot_error
        self._frame_dimensions = frame_dimensions
        self._frame_cell = frame_cell
        self.created: list[_FakeNormalizer] = []

    def __call__(self, *, rows: int, columns: int) -> _FakeNormalizer:
        normalizer = _FakeNormalizer(
            rows=rows,
            columns=columns,
            feed_error=self._feed_error,
            snapshot_error=self._snapshot_error,
            frame_dimensions=self._frame_dimensions,
            frame_cell=self._frame_cell,
        )
        self.created.append(normalizer)
        return normalizer


class _FakeWatchdog:
    """Recording watchdog whose trigger fires deterministically on demand."""

    def __init__(
        self,
        *,
        fire_at_arm: int | None = None,
        fire_at_disarm: int | None = None,
    ) -> None:
        self._fire_at_arm = fire_at_arm
        self._fire_at_disarm = fire_at_disarm
        self.arms: list[int] = []
        self.disarms = 0

    def arm(self, deadline_ms: int, expire: Callable[[], None]) -> Callable[[], None]:
        self.arms.append(deadline_ms)
        index = len(self.arms)
        if index == self._fire_at_arm:
            expire()

        def disarm() -> None:
            self.disarms += 1
            if index == self._fire_at_disarm:
                expire()

        return disarm


def _adapter(
    binding: _FakeBinding,
    *,
    normalizer_factory: _NormalizerFactory | None = None,
    watchdog: _FakeWatchdog | None = None,
    readiness_marker: str = _MARKER,
    abort_deadline_ms: int = _DEADLINE_MS,
    monotonic: Callable[[], float] | None = None,
) -> ConptyAdapter:
    return ConptyAdapter(
        ("subject", "--flag"),
        binding=binding,
        monotonic=monotonic,
        constraint_ports=_EnforcingPorts(),
        normalizer_factory=(
            normalizer_factory
            if normalizer_factory is not None
            else _NormalizerFactory()
        ),
        readiness_marker=readiness_marker,
        watchdog=watchdog if watchdog is not None else _FakeWatchdog(),
        abort_deadline_ms=abort_deadline_ms,
    )


def _started(
    reads: Sequence[str | Exception],
    *,
    exit_status: int | str | None = None,
    write_error: Exception | None = None,
    resize_error: Exception | None = None,
    close_error: Exception | None = None,
) -> tuple[ConptyAdapter, _FakeBinding, _NormalizerFactory, _FakeWatchdog]:
    binding = _FakeBinding(
        _FakeChild(
            reads,
            exit_status=exit_status,
            write_error=write_error,
            resize_error=resize_error,
            close_error=close_error,
        )
    )
    factory = _NormalizerFactory()
    watchdog = _FakeWatchdog()
    adapter = _adapter(binding, normalizer_factory=factory, watchdog=watchdog)
    result = adapter.start("run-conpty", _configuration())
    assert type(result) is Started
    return adapter, binding, factory, watchdog


# --- constructor surface ---------------------------------------------------


def test_constructor_requires_an_explicit_abort_deadline() -> None:
    with pytest.raises(TypeError):
        ConptyAdapter(("subject",), binding=_FakeBinding())  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        _adapter(_FakeBinding(), abort_deadline_ms=cast("int", "soon"))
    with pytest.raises(ValueError):
        _adapter(_FakeBinding(), abort_deadline_ms=0)


def test_constructor_validates_the_readiness_marker() -> None:
    with pytest.raises(TypeError):
        _adapter(_FakeBinding(), readiness_marker=cast("str", b"ready"))
    with pytest.raises(ValueError):
        _adapter(_FakeBinding(), readiness_marker="")


# --- start: readiness ------------------------------------------------------


def test_start_spawns_and_reaches_marker_readiness() -> None:
    binding = _FakeBinding(_FakeChild(["hello" + _MARKER]))
    factory = _NormalizerFactory()
    watchdog = _FakeWatchdog()
    adapter = _adapter(binding, normalizer_factory=factory, watchdog=watchdog)

    result = adapter.start("run-conpty", _configuration())

    assert type(result) is Started
    assert binding.spawns == [(("subject", "--flag"), 24, 80)]
    observation = result.observation
    assert observation.at_ms == 0
    assert observation.state == {"terminal": {"columns": 80, "rows": 24}}
    assert [event.type for event in observation.events] == ["terminal.output"]
    assert observation.events[0].data == {"chunk": "hello" + _MARKER}
    assert observation.process is None
    assert observation.frame is not None
    assert observation.frame.columns == 80
    assert observation.frame.rows == 24
    assert observation.ui.cursor == Cursor(column=0, row=0, visible=True)
    assert observation.ui.regions == ()
    assert factory.created[0].fed == ["hello" + _MARKER]
    assert watchdog.arms == [_DEADLINE_MS]
    assert watchdog.disarms == 1
    assert binding.child.closes == []


def test_start_finds_a_marker_split_across_chunks() -> None:
    split = len(_MARKER) // 2
    chunks = ["hi" + _MARKER[:split], _MARKER[split:]]
    binding = _FakeBinding(_FakeChild(chunks))
    factory = _NormalizerFactory()
    adapter = _adapter(binding, normalizer_factory=factory)

    result = adapter.start("run-conpty", _configuration())

    assert type(result) is Started
    assert [event.data for event in result.observation.events] == [
        {"chunk": chunks[0]},
        {"chunk": chunks[1]},
    ]
    assert factory.created[0].fed == chunks


def test_start_with_the_default_vt_normalizer_consumes_the_osc_marker() -> None:
    binding = _FakeBinding(_FakeChild(["hi" + _MARKER]))
    adapter = ConptyAdapter(
        ("subject",),
        binding=binding,
        constraint_ports=_EnforcingPorts(),
        watchdog=_FakeWatchdog(),
        abort_deadline_ms=_DEADLINE_MS,
    )

    result = adapter.start("run-conpty", _configuration())

    assert type(result) is Started
    frame = result.observation.frame
    assert frame is not None
    assert frame.lines[0].startswith("hi ")
    assert "\x1b" not in frame.lines[0]


def test_start_honors_a_configured_printable_marker() -> None:
    binding = _FakeBinding(_FakeChild(["banner<<READY>>"]))
    factory = _NormalizerFactory()
    adapter = _adapter(
        binding, normalizer_factory=factory, readiness_marker="<<READY>>"
    )

    result = adapter.start("run-conpty", _configuration())

    assert type(result) is Started
    assert factory.created[0].fed == ["banner<<READY>>"]


def test_marker_scanning_survives_long_marker_free_chunks() -> None:
    binding = _FakeBinding(_FakeChild(["x" * 200, "y" * 200, _MARKER]))
    adapter = _adapter(binding)

    result = adapter.start("run-conpty", _configuration())

    assert type(result) is Started
    assert len(result.observation.events) == 3


# --- start: classification -------------------------------------------------


def test_start_spawn_failure_is_start_failed() -> None:
    binding = _FakeBinding(spawn_error=FileNotFoundError("no such command"))
    adapter = _adapter(binding)

    result = adapter.start("run-conpty", _configuration())

    assert type(result) is StartFailed
    assert result.failure.code == "adapter-start-failed"
    assert result.failure.details == {"during": "spawn"}
    assert len(result.enforced) == 7


def test_start_normalizer_construction_failure_closes_the_child() -> None:
    class _BrokenFactory:
        def __call__(self, *, rows: int, columns: int) -> _FakeNormalizer:
            raise RuntimeError("normalizer exploded")

    binding = _FakeBinding(_FakeChild())
    adapter = _adapter(
        binding, normalizer_factory=cast("_NormalizerFactory", _BrokenFactory())
    )

    result = adapter.start("run-conpty", _configuration())

    assert type(result) is StartFailed
    assert result.failure.details == {"during": "normalizer"}
    assert binding.child.closes == [True]


def test_start_end_of_stream_before_marker_is_start_terminated() -> None:
    binding = _FakeBinding(
        _FakeChild(["partial", ConptyEndOfStreamError("end of stream")], exit_status=3)
    )
    adapter = _adapter(binding)

    result = adapter.start("run-conpty", _configuration())

    assert type(result) is StartTerminated
    assert result.result.outcome == RunFinished.code(3)
    observation = result.result.observation
    assert observation is not None
    assert observation.at_ms == 0
    assert observation.process is not None
    assert observation.process.state == "exited"
    assert [event.data for event in observation.events] == [{"chunk": "partial"}]
    assert binding.child.closes == [True]


def test_start_missing_exit_record_is_start_failed() -> None:
    binding = _FakeBinding(
        _FakeChild([ConptyEndOfStreamError("end of stream")], exit_status=None)
    )
    adapter = _adapter(binding)

    result = adapter.start("run-conpty", _configuration())

    assert type(result) is StartFailed
    assert result.failure.details == {"missing": "exit-record"}
    assert binding.child.closes == [True]


def test_start_deadline_abort_is_start_failed_with_disclosed_policy() -> None:
    binding = _FakeBinding(_FakeChild())
    watchdog = _FakeWatchdog(fire_at_arm=1)
    adapter = _adapter(binding, watchdog=watchdog)

    result = adapter.start("run-conpty", _configuration())

    assert type(result) is StartFailed
    assert result.failure.details == {
        "abort-deadline-ms": _DEADLINE_MS,
        "bound": "read",
    }
    assert "deadline" in result.failure.message
    assert binding.child.closed
    assert all(binding.child.closes)
    assert watchdog.disarms == 1


class _SteppingClock:
    """Monotonic fake that advances on a schedule, not per reading.

    Drives the per-epoch deadline with no sleeping, advancing every ``every``
    readings so a trickle needs several reads per tick. It does **not** make
    elapsed time independent of read count, and so does not by itself exclude
    a read-count bound: the chatty-epoch guard is what does that, by failing
    every read count low enough to bound a trickle.
    """

    def __init__(self, step_s: float, *, every: int = 3) -> None:
        self._step = step_s
        self._every = every
        self._now = 0.0
        self.readings = 0

    def __call__(self) -> float:
        now = self._now
        self.readings += 1
        if self.readings % self._every == 0:
            self._now += self._step
        return now


def test_a_marker_less_trickle_cannot_outlive_the_epoch_deadline() -> None:
    """A trickling subject must not hold an epoch open forever (finding R2).

    The watchdog is re-armed per read, so a subject emitting output just
    under the deadline never exceeds any single read's deadline: the marker
    never arrives and the epoch never ends. The same configured deadline
    therefore bounds the epoch as a whole.

    Driven by an injected clock rather than by sleeping, and deliberately
    *not* by a read count: real ConPTY barely coalesces, so a read budget
    low enough to bound a trickle also aborts an ordinary few-thousand-line
    scroll — falsely aborting a cooperative subject, which is worse than
    the starvation it would prevent.
    """
    clock = _SteppingClock(_DEADLINE_MS / 1000 / 4)
    binding = _FakeBinding(_FakeChild(["."] * 20))
    adapter = _adapter(binding, watchdog=_FakeWatchdog(), monotonic=clock)

    result = adapter.start("run-conpty", _configuration())

    assert type(result) is StartFailed
    # The ordinary deadline evidence, with the epoch bound named: a stalled
    # read and a subject that never reaches readiness look identical
    # otherwise, and they need opposite remediations.
    assert result.failure.details == {
        "abort-deadline-ms": _DEADLINE_MS,
        "bound": "epoch",
    }
    assert "deadline" in result.failure.message
    assert binding.child.closed
    assert all(binding.child.closes)
    # Bounded, not exhaustive: it stopped before the script ran out.
    assert binding.child.reads


def test_a_chatty_epoch_within_the_deadline_still_succeeds() -> None:
    """The bound must not abort a cooperative subject that simply talks a lot.

    Real ConPTY hands back hundreds of small chunks for an ordinary scroll,
    so this is the false-positive guard: thousands of reads, no marker until
    the end, and a clock that never reaches the epoch deadline.
    """
    reads = ["line\r\n"] * 4000
    reads.append(_MARKER)
    binding = _FakeBinding(_FakeChild(reads))
    adapter = _adapter(binding, watchdog=_FakeWatchdog())

    result = adapter.start("run-conpty", _configuration())

    assert type(result) is Started, result
    assert binding.child.reads == []


def test_an_output_flood_exhausts_the_per_epoch_byte_budget() -> None:
    """One epoch cannot retain more output than one record can carry.

    Every chunk becomes a `terminal.output` event in a single observation
    record, whose aggregate string bytes the protocol caps. This bounds
    memory; the codec still owns recordability and enforces further
    ceilings this budget cannot model.
    """
    chunk = "x" * 64 * 1024
    reads = [chunk] * (_MAX_RECORD_STRING_BYTES // len(chunk) + 2)
    binding = _FakeBinding(_FakeChild(reads))
    adapter = _adapter(binding, watchdog=_FakeWatchdog())

    result = adapter.start("run-conpty", _configuration())

    assert type(result) is StartFailed
    details = cast("Mapping[str, object]", result.failure.details)
    assert details["budget"] == "bytes"
    # The budget is computed from the terminal geometry, not a constant.
    budget = details["epoch-output-byte-budget"]
    assert isinstance(budget, int)
    assert budget < _MAX_RECORD_STRING_BYTES
    assert "one observation" in result.failure.message


@pytest.mark.parametrize(
    ("columns", "rows", "starts"),
    [
        (1000, 523, True),
        # Exactly at the documented threshold, and one column below it (16
        # cells: 32,703 x 16 is 523,248, the nearest point reachable on this
        # row count). Straddling it from a distance is not enough: with only
        # the 1000x523 and 1000x524 cases, weakening the check to
        # `budget < 0` stays green while making the documented number false
        # (round 6, finding 7).
        (32_704, 16, False),
        (32_703, 16, True),
        (1000, 524, False),
        (1024, 512, False),
    ],
)
def test_a_terminal_too_large_for_its_own_frame_fails_on_geometry(
    columns: int, rows: int, starts: bool
) -> None:
    """Past a threshold no epoch can be recorded, and the threshold is real.

    The frame is reserved at UTF-8's worst case per cell, so once the
    terminal reaches `(2 MiB - fixed) / 4` cells the reserve leaves the
    record no room for output at all. The guide and changelog quote this
    cell count to hosts, and the previous revision quoted the *byte* figure
    read as cells — off by 4x, the same cells-vs-bytes confusion round 4
    rejected this PR for.
    """
    threshold = (_MAX_RECORD_STRING_BYTES - _FIXED_RECORD_STRING_BYTES) // (
        _MAX_UTF8_BYTES_PER_CELL
    )
    assert threshold == 523_264, "the documented threshold moved"
    assert (rows * columns < threshold) is starts, "case does not straddle it"

    binding = _FakeBinding(_FakeChild([_MARKER]))
    adapter = _adapter(
        binding,
        watchdog=_FakeWatchdog(),
        normalizer_factory=_NormalizerFactory(frame_dimensions=(rows, columns)),
    )
    configuration = replace(
        _configuration(),
        terminal=TerminalConfiguration(columns=columns, rows=rows, capabilities=()),
    )

    result = adapter.start("run-conpty", configuration)

    if starts:
        assert type(result) is Started
        return
    assert type(result) is StartFailed
    assert result.failure.details == {
        "budget": "geometry",
        "terminal-cells": rows * columns,
    }
    # The mechanism, stated truthfully: at this threshold the record *can*
    # still hold the frame — measured, 523,264 emoji cells plus the record's
    # real fixed strings fit with ~3.8 KB to spare. What it cannot do is hold
    # the frame *and* any output once the reserve is taken (round 6, finding 2).
    assert "no room for output" in result.failure.message


@pytest.mark.parametrize(
    ("rows", "starts"),
    [
        (_MAX_COLLECTION_ITEMS, True),
        (_MAX_COLLECTION_ITEMS + 1, False),
        # The tallest geometry the real binding can request: `COORD` is 16-bit,
        # so this is the far end of the reachable range, not a fake-only value.
        (32_767, False),
    ],
)
def test_a_terminal_with_more_rows_than_a_frame_may_carry_fails_on_geometry(
    rows: int, starts: bool
) -> None:
    """Rows are a second geometry axis, and bytes do not model it.

    The byte budget reserves `4 * rows * columns` and refuses when nothing is
    left for output. That is a *cell* model, and the frame has a second cost
    the codec charges separately: `frame.lines` is one collection item per
    row, so above the v1 collection ceiling no epoch is recordable at any
    cell count. Ten columns keeps the cell product an order of magnitude
    below the 523,264-cell threshold, so only the row axis can refuse these.

    Reachable, not hypothetical: `TerminalConfiguration` requires a positive
    int and nothing more, and a 20,000-row pseudoconsole was created and
    spawned into on the Windows dev host. Round 7, finding 1.
    """
    columns = 10
    assert (
        rows * columns
        < (_MAX_RECORD_STRING_BYTES - _FIXED_RECORD_STRING_BYTES)
        // _MAX_UTF8_BYTES_PER_CELL
    ), "the cell threshold would refuse these anyway"

    binding = _FakeBinding(_FakeChild([_MARKER]))
    adapter = _adapter(
        binding,
        watchdog=_FakeWatchdog(),
        normalizer_factory=_NormalizerFactory(frame_dimensions=(rows, columns)),
    )
    configuration = replace(
        _configuration(),
        terminal=TerminalConfiguration(columns=columns, rows=rows, capabilities=()),
    )

    result = adapter.start("run-conpty", configuration)

    if starts:
        assert type(result) is Started
        # The admitted end of the boundary is proved recordable by the real
        # recorder and the real codec, not by restating the ceiling here.
        _recorded_transcript(result, configuration)
        return
    assert type(result) is StartFailed
    assert result.failure.details == {"budget": "geometry", "terminal-rows": rows}
    assert "more rows" in result.failure.message


def test_a_resize_past_the_threshold_cannot_slip_through_a_buffered_marker() -> None:
    """An epoch that never reads must still honor the geometry bound.

    `_read_epoch_chunks` returns early when the marker is already buffered,
    so while the check lived inside the read loop a resize past the
    threshold completed an epoch without consuming a read at all — and the
    codec then rejected the record, losing the run's evidence at the very
    end. That is the admit-then-reject failure this budget exists to
    prevent, reached at a geometry the guide calls unrecordable (round 6,
    finding 1).
    """
    # Two markers in one read: the second stays buffered in `_pending`, so
    # the resize epoch finds readiness without reading.
    binding = _FakeBinding(_FakeChild([_MARKER + _MARKER]))
    adapter = _adapter(binding, watchdog=_FakeWatchdog())
    started = adapter.start("run-conpty", _configuration())
    assert type(started) is Started
    reads_before_resize = binding.child.reads_served

    result = adapter.dispatch(Resize(ManualTime(0), columns=32_767, rows=16))

    assert type(result) is TerminalResult
    outcome = result.outcome
    assert type(outcome) is RunFailed
    assert outcome.failure.details == {
        "budget": "geometry",
        "terminal-cells": 16 * 32_767,
    }
    # No read was consumed by the resize epoch: it never entered the loop.
    # `reads == []` would not say this — the script is popped as it is served,
    # so it is empty on every path, including one that did read (round 7).
    assert binding.child.reads_served == reads_before_resize


def test_a_stalled_read_that_wins_the_close_race_is_not_relabelled() -> None:
    """A read the watchdog already killed stays `bound: "read"`.

    Such a read can return normally and arrive at the epoch check with the
    deadline spent, which looks exactly like a subject that produces output
    but never reaches readiness. Only the latter is `bound: "epoch"`, since
    the two need opposite remediations.
    """
    # Fires after the first read returns: the read won the race with expiry.
    watchdog = _FakeWatchdog(fire_at_disarm=1)
    clock = _SteppingClock(_DEADLINE_MS / 1000, every=1)
    binding = _FakeBinding(_FakeChild(["." * 8, _MARKER]))
    adapter = _adapter(binding, watchdog=watchdog, monotonic=clock)

    result = adapter.start("run-conpty", _configuration())

    assert type(result) is StartFailed
    assert result.failure.details == {
        "abort-deadline-ms": _DEADLINE_MS,
        "bound": "read",
    }


def test_the_byte_budget_counts_the_marker_bearing_chunk_too() -> None:
    """The marker must not buy an epoch one extra unbounded read.

    Honoring the marker before counting would let the retained output
    exceed the budget by a whole chunk — as much as a single ConPTY read
    may carry.
    """
    filler = "x" * 64 * 1024
    reads = [filler] * (_MAX_RECORD_STRING_BYTES // len(filler) - 1)
    reads.append("x" * 512 * 1024 + _MARKER)
    binding = _FakeBinding(_FakeChild(reads))
    adapter = _adapter(binding, watchdog=_FakeWatchdog())

    result = adapter.start("run-conpty", _configuration())

    assert type(result) is StartFailed
    details = cast("Mapping[str, object]", result.failure.details)
    assert details["budget"] == "bytes"


def _recorded_transcript(started: Started, configuration: RunConfiguration) -> bytes:
    """Record and serialize a start observation with the real codec.

    Nothing here replicates `termverify.transcript`'s counting rule. An
    earlier revision of this slice did, and the replica was the defect: it
    measured the adapter's *pre-coalescing* observation, one event per
    native read, while the recorder merges adjacent `terminal.output`
    chunks into a single event (issue #195, merged as PR #224). The replica
    therefore checked the epoch against the per-record string sum and never
    against the per-string ceiling the merged chunk actually meets.
    """
    recorder = TranscriptRecorder("run-conpty", configuration, _REPLAY_SUBJECT)
    recorder.record_start(started)
    recorder.record_epoch(
        Stop(ManualTime(0)), TerminalResult(None, RunFinished.code(0))
    )
    return recorder.transcript()


@pytest.mark.parametrize(
    ("columns", "rows"), [(80, 24), (200, 400), (400, 200), (800, 400)]
)
@pytest.mark.parametrize("cell", ["x", "─", "🙂"])
def test_the_largest_admitted_epoch_records_as_a_valid_transcript(
    columns: int, rows: int, cell: str
) -> None:
    """The bound must admit only epochs the codec actually accepts.

    The epoch grows until the adapter refuses, and the largest one it
    *accepted* is then recorded and serialized by the real recorder and the
    real codec. A budget derived from the wrong ceiling shows up as a
    `TranscriptValidationError` here rather than as a passing assertion,
    which is how three successive revisions of this budget hid: each was
    checked against a replica of the counting rule that shared the
    revision's own mistake.

    The geometries straddle the crossover deliberately. Below ~261,000 cells
    the per-string ceiling binds and the frame reserve is slack; 800x400
    puts the per-record string sum in front of it, which is the only regime
    where an under-sized per-cell reserve can be observed at all.
    """
    step = 8192
    configuration = replace(
        _configuration(),
        terminal=TerminalConfiguration(columns=columns, rows=rows, capabilities=()),
    )

    def attempt(payload_bytes: int) -> Started | None:
        """Start one epoch carrying `payload_bytes` across several chunks."""
        whole, tail = divmod(payload_bytes, step)
        chunks = ["y" * step] * whole + (["y" * tail] if tail else [])
        binding = _FakeBinding(_FakeChild([*chunks, _MARKER]))
        adapter = _adapter(
            binding,
            watchdog=_FakeWatchdog(),
            normalizer_factory=_NormalizerFactory(
                frame_dimensions=(rows, columns), frame_cell=cell
            ),
        )
        result = adapter.start("run-conpty", configuration)
        return result if type(result) is Started else None

    # Coarse sweep to bracket the bound, then a binary search to land on it
    # exactly. Byte granularity is not pedantry: at the 8 KiB step the search
    # stops up to a whole step short, and terms worth a few hundred bytes —
    # the record's fixed strings — sit inside that slack unobserved, which is
    # how an earlier revision left one pinned by nothing at all.
    low = 0
    high = step
    while attempt(high) is not None:
        low = high
        high += step
        if high > 4 * _MAX_STRING_BYTES:  # pragma: no cover - bound must exist
            raise AssertionError("the byte bound was never reached")
    while high - low > 1:
        middle = (low + high) // 2
        if attempt(middle) is None:
            high = middle
        else:
            low = middle
    assert low > 0, "no epoch was admitted at all"

    accepted = attempt(low)
    assert accepted is not None
    # Raises if the largest admitted epoch exceeds any v1 ceiling.
    _recorded_transcript(accepted, configuration)


def test_a_chunk_flood_is_bounded_by_bytes_alone() -> None:
    """Chunk count is no longer an axis, because chunks no longer are events.

    Before #195 every retained chunk became one item in the observation's
    `events` array, so a subject redrawing in place reached the protocol's
    collection ceiling with well under 100 KB of payload and the adapter
    needed a separate chunk bound. The recorder now merges adjacent chunks
    into a single event, so that ceiling is unreachable by chunk count and
    the same subject records fine. Deleting the chunk bound without this
    test would leave the deletion pinned by nothing.
    """
    flood = ["W"] * (_MAX_COLLECTION_ITEMS + 1)
    binding = _FakeBinding(_FakeChild([*flood, _MARKER]))
    adapter = _adapter(binding, watchdog=_FakeWatchdog())

    result = adapter.start("run-conpty", _configuration())

    assert type(result) is Started
    assert len(result.observation.events) == len(flood) + 1
    transcript = _recorded_transcript(result, _configuration())
    # The codec accepted it, and the chunks arrive as one coalesced event.
    assert transcript.count(b'"terminal.output"') == 1


def test_the_epoch_deadline_also_bounds_a_dispatch_epoch() -> None:
    """The epoch bound is not a start-only guard."""
    clock = _SteppingClock(_DEADLINE_MS / 1000 / 4)
    binding = _FakeBinding(_FakeChild([_MARKER, *(["."] * 40)]))
    adapter = _adapter(binding, watchdog=_FakeWatchdog(), monotonic=clock)
    assert type(adapter.start("run-conpty", _configuration())) is Started

    result = adapter.dispatch(TextInput(at_ms=ManualTime(0), text="go"))

    assert type(result) is TerminalResult, result
    outcome = result.outcome
    assert isinstance(outcome, RunFailed)
    assert outcome.failure.details == {
        "abort-deadline-ms": _DEADLINE_MS,
        "bound": "epoch",
    }


def test_a_budget_abort_in_a_dispatch_epoch_is_a_runtime_failure() -> None:
    """Every other budget test drives `start()`; dispatch must match."""
    chunk = "x" * 64 * 1024
    flood = [chunk] * (_MAX_RECORD_STRING_BYTES // len(chunk) + 2)
    adapter, binding, _, _ = _started([_MARKER, *flood])

    result = adapter.dispatch(TextInput(at_ms=ManualTime(0), text="go"))

    assert type(result) is TerminalResult, result
    outcome = result.outcome
    assert isinstance(outcome, RunFailed)
    assert outcome.failure.code == "adapter-runtime-failed"
    details = cast("Mapping[str, object]", outcome.failure.details)
    assert details["budget"] == "bytes"


def test_start_native_read_failure_is_start_failed() -> None:
    binding = _FakeBinding(_FakeChild([OSError("native read failed")]))
    adapter = _adapter(binding)

    result = adapter.start("run-conpty", _configuration())

    assert type(result) is StartFailed
    assert result.failure.details == {"during": "read"}
    assert binding.child.closes == [True]


def test_start_unexpected_close_is_start_failed() -> None:
    binding = _FakeBinding(_FakeChild([ConptyClosedError("closed")]))
    adapter = _adapter(binding)

    result = adapter.start("run-conpty", _configuration())

    assert type(result) is StartFailed
    assert result.failure.details == {"during": "read"}
    assert "outside the abort deadline" in result.failure.message


def test_start_concurrent_io_invariant_violation_is_start_failed() -> None:
    binding = _FakeBinding(_FakeChild([ConptyConcurrentIOError("overlap")]))
    adapter = _adapter(binding)

    result = adapter.start("run-conpty", _configuration())

    assert type(result) is StartFailed
    assert result.failure.details == {"during": "read", "invariant": "single-flight"}


def test_start_normalizer_feed_failure_is_start_failed() -> None:
    binding = _FakeBinding(_FakeChild(["boom"]))
    factory = _NormalizerFactory(
        feed_error=VtNormalizationError("unknown sequence", "boom")
    )
    adapter = _adapter(binding, normalizer_factory=factory)

    result = adapter.start("run-conpty", _configuration())

    assert type(result) is StartFailed
    assert result.failure.details == {"during": "normalize"}
    assert binding.child.closes == [True]


def test_start_snapshot_failure_is_start_failed() -> None:
    binding = _FakeBinding(_FakeChild([_MARKER]))
    factory = _NormalizerFactory(snapshot_error=RuntimeError("snapshot exploded"))
    adapter = _adapter(binding, normalizer_factory=factory)

    result = adapter.start("run-conpty", _configuration())

    assert type(result) is StartFailed
    assert result.failure.details == {"during": "snapshot"}


def test_start_frame_dimension_disagreement_is_start_failed() -> None:
    binding = _FakeBinding(_FakeChild([_MARKER]))
    factory = _NormalizerFactory(frame_dimensions=(10, 40))
    adapter = _adapter(binding, normalizer_factory=factory)

    result = adapter.start("run-conpty", _configuration())

    assert type(result) is StartFailed
    assert result.failure.details == {"during": "snapshot"}
    assert "dimensions" in result.failure.message


# --- dispatch epochs -------------------------------------------------------


def test_text_dispatch_writes_and_completes_an_epoch() -> None:
    adapter, binding, factory, watchdog = _started(["ready" + _MARKER])
    binding.child.reads.append("echo" + _MARKER)

    result = adapter.dispatch(TextInput(ManualTime(0), "x\r"))

    assert type(result) is EpochCompleted
    assert binding.child.written == ["x\r"]
    assert [event.data for event in result.observation.events] == [
        {"chunk": "echo" + _MARKER}
    ]
    assert result.observation.at_ms == 0
    assert result.observation.process is None
    assert factory.created[0].fed == ["ready" + _MARKER, "echo" + _MARKER]
    assert watchdog.arms == [_DEADLINE_MS, _DEADLINE_MS]
    assert watchdog.disarms == 2


def test_dispatch_requires_the_current_manual_time() -> None:
    adapter, _, _, _ = _started([_MARKER])

    with pytest.raises(ValueError):
        adapter.dispatch(TextInput(ManualTime(5), "x"))


@pytest.mark.parametrize(
    ("keys", "expected"),
    [
        (("Enter",), "\r"),
        (("ArrowUp",), "\x1b[A"),
        (("Control", "Shift", "ArrowLeft"), "\x1b[1;6D"),
        (("Delete",), "\x1b[3~"),
        (("Alt", "PageDown"), "\x1b[6;3~"),
        (("F1",), "\x1bOP"),
        (("Control", "F4"), "\x1b[1;5S"),
        (("Shift", "Tab"), "\x1b[Z"),
        (("Control", "c"), "\x03"),
        (("Control", "Alt", "m"), "\x1b\r"),
        (("Alt", "7"), "\x1b7"),
        (("Alt", "Space"), "\x1b "),
    ],
)
def test_encodable_key_dispatch_writes_registry_bytes_once_and_runs_an_epoch(
    keys: tuple[str, ...], expected: str
) -> None:
    adapter, binding, factory, watchdog = _started([_MARKER])
    binding.child.reads.append("reacted" + _MARKER)

    result = adapter.dispatch(KeyInput(ManualTime(0), keys))

    assert type(result) is EpochCompleted
    assert binding.child.written == [expected]
    assert [event.data for event in result.observation.events] == [
        {"chunk": "reacted" + _MARKER}
    ]
    assert factory.created[0].fed == [_MARKER, "reacted" + _MARKER]
    assert watchdog.arms == [_DEADLINE_MS, _DEADLINE_MS]
    assert watchdog.disarms == 2


def test_unencodable_key_dispatch_fails_closed_before_any_child_write() -> None:
    adapter, binding, _, _ = _started([_MARKER])

    result = adapter.dispatch(KeyInput(ManualTime(0), ("Control", "Enter")))

    assert type(result) is TerminalResult
    assert type(result.outcome) is RunFailed
    assert result.outcome.failure.code == "adapter-runtime-failed"
    assert result.outcome.failure.details == {
        "unsupported": "key-encoding",
        "keys": ("Control", "Enter"),
    }
    assert result.observation is None
    assert binding.child.written == []
    assert binding.child.closes == [True]
    with pytest.raises(RuntimeError):
        adapter.dispatch(TextInput(ManualTime(0), "x"))


def test_key_dispatch_write_failure_uses_the_structured_runtime_path() -> None:
    adapter, binding, _, _ = _started(
        [_MARKER], write_error=RuntimeError("write refused")
    )

    result = adapter.dispatch(KeyInput(ManualTime(0), ("ArrowUp",)))

    assert type(result) is TerminalResult
    assert type(result.outcome) is RunFailed
    assert result.outcome.failure.details == {"during": "write"}
    assert binding.child.closes == [True]


def test_resize_dispatch_resizes_child_and_normalizer() -> None:
    adapter, binding, factory, _ = _started([_MARKER])
    binding.child.reads.append("repainted" + _MARKER)

    result = adapter.dispatch(Resize(ManualTime(0), columns=100, rows=30))

    assert type(result) is EpochCompleted
    assert binding.child.resizes == [(30, 100)]
    assert factory.created[0].resizes == [(30, 100)]
    assert result.observation.state == {"terminal": {"columns": 100, "rows": 30}}
    frame = result.observation.frame
    assert frame is not None
    assert frame.columns == 100
    assert frame.rows == 30


def test_resize_failure_is_a_runtime_failure() -> None:
    adapter, binding, _, _ = _started([_MARKER], resize_error=OSError("resize failed"))

    result = adapter.dispatch(Resize(ManualTime(0), columns=100, rows=30))

    assert type(result) is TerminalResult
    assert type(result.outcome) is RunFailed
    assert result.outcome.failure.details == {"during": "resize"}
    assert binding.child.closes == [True]


def test_write_failure_is_a_runtime_failure() -> None:
    adapter, binding, _, _ = _started([_MARKER], write_error=OSError("write failed"))

    result = adapter.dispatch(TextInput(ManualTime(0), "x"))

    assert type(result) is TerminalResult
    assert type(result.outcome) is RunFailed
    assert result.outcome.failure.details == {"during": "write"}


def test_dispatch_end_of_stream_finishes_the_run() -> None:
    adapter, binding, _, _ = _started([_MARKER], exit_status=0)
    binding.child.reads.extend(["bye", ConptyEndOfStreamError("end of stream")])

    result = adapter.dispatch(TextInput(ManualTime(0), "quit\r"))

    assert type(result) is TerminalResult
    assert result.outcome == RunFinished.code(0)
    observation = result.observation
    assert observation is not None
    assert observation.process is not None
    assert observation.process.exit == ExitStatus("code", 0)
    assert [event.data for event in observation.events] == [{"chunk": "bye"}]
    assert binding.child.closes == [True]
    with pytest.raises(RuntimeError):
        adapter.dispatch(TextInput(ManualTime(0), "x"))


def test_dispatch_deadline_abort_has_no_observation() -> None:
    binding = _FakeBinding(_FakeChild([_MARKER]))
    watchdog = _FakeWatchdog(fire_at_arm=2)
    adapter = _adapter(binding, watchdog=watchdog)
    started = adapter.start("run-conpty", _configuration())
    assert type(started) is Started

    result = adapter.dispatch(TextInput(ManualTime(0), "hang\r"))

    assert type(result) is TerminalResult
    assert type(result.outcome) is RunFailed
    assert result.observation is None
    assert result.outcome.failure.details == {
        "abort-deadline-ms": _DEADLINE_MS,
        "bound": "read",
    }
    assert binding.child.closed


def test_expire_close_failure_still_classifies_the_deadline_abort() -> None:
    child = _FakeChild([_MARKER], close_error=OSError("close failed"))
    binding = _FakeBinding(child)
    watchdog = _FakeWatchdog(fire_at_arm=2)
    adapter = _adapter(binding, watchdog=watchdog)
    started = adapter.start("run-conpty", _configuration())
    assert type(started) is Started
    child.reads.append(ConptyClosedError("cancelled by close"))

    result = adapter.dispatch(TextInput(ManualTime(0), "hang\r"))

    assert type(result) is TerminalResult
    assert type(result.outcome) is RunFailed
    details = dict(cast("dict[str, object]", result.outcome.failure.details))
    assert details == {
        "abort-deadline-ms": _DEADLINE_MS,
        "bound": "read",
        "close": "failed",
    }


def test_deadline_expiry_racing_a_successful_read_still_aborts() -> None:
    binding = _FakeBinding(_FakeChild([_MARKER, "echo" + _MARKER]))
    watchdog = _FakeWatchdog(fire_at_disarm=2)
    adapter = _adapter(binding, watchdog=watchdog)
    started = adapter.start("run-conpty", _configuration())
    assert type(started) is Started

    result = adapter.dispatch(TextInput(ManualTime(0), "x"))

    assert type(result) is TerminalResult
    assert type(result.outcome) is RunFailed
    assert result.outcome.failure.details == {
        "abort-deadline-ms": _DEADLINE_MS,
        "bound": "read",
    }
    assert binding.child.closed


def test_deadline_expiry_with_failed_close_never_yields_success() -> None:
    child = _FakeChild([_MARKER, "late" + _MARKER], close_error=OSError("close failed"))
    binding = _FakeBinding(child)
    watchdog = _FakeWatchdog(fire_at_arm=2)
    adapter = _adapter(binding, watchdog=watchdog)
    started = adapter.start("run-conpty", _configuration())
    assert type(started) is Started

    result = adapter.dispatch(TextInput(ManualTime(0), "x"))

    assert type(result) is TerminalResult
    assert type(result.outcome) is RunFailed
    assert result.outcome.failure.details == {
        "abort-deadline-ms": _DEADLINE_MS,
        "bound": "read",
        "close": "failed",
    }
    assert "deadline" in result.outcome.failure.message


def test_close_failure_after_exit_is_a_runtime_failure() -> None:
    adapter, binding, _, _ = _started(
        [_MARKER], exit_status=0, close_error=OSError("close failed")
    )
    binding.child.reads.append(ConptyEndOfStreamError("end of stream"))

    result = adapter.dispatch(TextInput(ManualTime(0), "quit\r"))

    assert type(result) is TerminalResult
    assert type(result.outcome) is RunFailed
    assert result.outcome.failure.details == {"during": "close"}


def test_native_error_with_close_failure_disclosed_together() -> None:
    adapter, _, _, _ = _started(
        [_MARKER, OSError("native read failed")],
        close_error=OSError("close failed"),
    )

    result = adapter.dispatch(TextInput(ManualTime(0), "x"))

    assert type(result) is TerminalResult
    assert type(result.outcome) is RunFailed
    assert result.outcome.failure.details == {"during": "read", "close": "failed"}


def test_snapshot_failure_at_exit_is_a_runtime_failure() -> None:
    adapter, binding, factory, _ = _started([_MARKER], exit_status=0)
    binding.child.reads.append(ConptyEndOfStreamError("end of stream"))
    factory.created[0].snapshot_error = RuntimeError("snapshot exploded")

    result = adapter.dispatch(TextInput(ManualTime(0), "quit\r"))

    assert type(result) is TerminalResult
    assert type(result.outcome) is RunFailed
    assert result.outcome.failure.details == {"during": "snapshot"}
    assert binding.child.closed


def test_invalid_exit_record_is_a_runtime_failure() -> None:
    adapter, binding, _, _ = _started([_MARKER], exit_status="weird")
    binding.child.reads.append(ConptyEndOfStreamError("end of stream"))

    result = adapter.dispatch(TextInput(ManualTime(0), "x"))

    assert type(result) is TerminalResult
    assert type(result.outcome) is RunFailed
    assert result.outcome.failure.details == {"during": "exit-record"}


def test_buffered_marker_completes_the_next_epoch_without_reading() -> None:
    adapter, binding, _, _ = _started(["a" + _MARKER + "b" + _MARKER])

    result = adapter.dispatch(TextInput(ManualTime(0), "x"))

    assert type(result) is EpochCompleted
    assert result.observation.events == ()
    assert binding.child.written == ["x"]


# --- advance_clock ---------------------------------------------------------


def test_advance_clock_reads_to_the_marker_without_writing() -> None:
    adapter, binding, _, _ = _started([_MARKER])
    binding.child.reads.extend(["tick" + _MARKER, "tock" + _MARKER])

    result = adapter.advance_clock(ClockAdvance(ManualTime(5), delta_ms=5))

    assert type(result) is EpochCompleted
    assert result.observation.at_ms == 5
    assert binding.child.written == []

    followup = adapter.dispatch(TextInput(ManualTime(5), "x"))
    assert type(followup) is EpochCompleted
    assert followup.observation.at_ms == 5


def test_advance_clock_must_move_the_manual_time() -> None:
    adapter, _, _, _ = _started([_MARKER])

    with pytest.raises(ValueError):
        adapter.advance_clock(ClockAdvance(ManualTime(3), delta_ms=5))


# --- stop ------------------------------------------------------------------


def test_stop_forces_teardown_and_records_the_exit() -> None:
    adapter, binding, _, _ = _started([_MARKER], exit_status=15)

    result = adapter.stop(Stop(ManualTime(0)))

    assert type(result) is TerminalResult
    assert result.outcome == RunFinished.code(15)
    assert binding.child.closes == [True]
    observation = result.observation
    assert observation is not None
    assert observation.at_ms == 0
    assert observation.events == ()
    assert observation.process is not None
    assert observation.process.exit == ExitStatus("code", 15)
    assert len(result.diagnostics) == 1
    diagnostic = result.diagnostics[0]
    assert diagnostic.code == "forced-termination"
    assert diagnostic.at_ms == 0
    assert "readiness marker" in diagnostic.message
    with pytest.raises(RuntimeError):
        adapter.stop(Stop(ManualTime(0)))


def test_stop_missing_exit_record_is_a_runtime_failure() -> None:
    adapter, _, _, _ = _started([_MARKER], exit_status=None)

    result = adapter.stop(Stop(ManualTime(0)))

    assert type(result) is TerminalResult
    assert type(result.outcome) is RunFailed
    assert result.observation is None
    assert result.outcome.failure.details == {"missing": "exit-record"}


def test_stop_close_failure_is_a_runtime_failure() -> None:
    adapter, _, _, _ = _started(
        [_MARKER], exit_status=15, close_error=OSError("close failed")
    )

    result = adapter.stop(Stop(ManualTime(0)))

    assert type(result) is TerminalResult
    assert type(result.outcome) is RunFailed
    assert result.outcome.failure.details == {"during": "close"}


def test_stop_requires_the_current_manual_time() -> None:
    adapter, _, _, _ = _started([_MARKER])

    with pytest.raises(ValueError):
        adapter.stop(Stop(ManualTime(9)))


def test_stop_snapshot_failure_is_a_runtime_failure() -> None:
    adapter, _, factory, _ = _started([_MARKER], exit_status=15)
    factory.created[0].snapshot_error = RuntimeError("snapshot exploded")

    result = adapter.stop(Stop(ManualTime(0)))

    assert type(result) is TerminalResult
    assert type(result.outcome) is RunFailed
    assert result.outcome.failure.details == {"during": "snapshot"}


def test_invalid_exit_record_at_stop_is_a_runtime_failure() -> None:
    adapter, _, _, _ = _started([_MARKER], exit_status="weird")

    result = adapter.stop(Stop(ManualTime(0)))

    assert type(result) is TerminalResult
    assert type(result.outcome) is RunFailed
    assert result.outcome.failure.details == {"during": "exit-record"}


# --- default watchdog ------------------------------------------------------


def test_timer_watchdog_fires_after_the_deadline() -> None:
    fired = threading.Event()

    disarm = TimerWatchdog().arm(10, fired.set)

    assert fired.wait(5.0)
    disarm()


def test_timer_watchdog_disarm_cancels_the_trigger() -> None:
    fired = threading.Event()

    disarm = TimerWatchdog().arm(60_000, fired.set)
    disarm()

    assert not fired.wait(0.05)
