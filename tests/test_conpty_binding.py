"""Durable lifecycle evidence for the minimal Windows ConPTY binding.

These tests promote the PR #53 spike behaviors into repeatable CI evidence on
the Windows matrix: child creation, initial dimensions, echoed input, a
marker-bounded output burst serviced by a dedicated reader thread, explicit
resize, forced close, and an integer exit status. They deliberately claim
nothing about native output-pipe EOF, final-frame drain completeness,
process-tree teardown, or cancellation recovery; those remain later verified
slices of the accepted terminal-adapter plan.
"""

from __future__ import annotations

import os
import queue
import re
import sys
import threading
from typing import Final

import pytest

from termverify._conpty import ConptyChild, ConptyUnsupportedError

_INITIAL_ROWS: Final = 24
_INITIAL_COLUMNS: Final = 80
_RESIZED_ROWS: Final = 30
_RESIZED_COLUMNS: Final = 100
_BURST_CHUNK_BYTES: Final = 1024
_BURST_CHUNKS: Final = 1024
_BURST_BYTES: Final = _BURST_CHUNK_BYTES * _BURST_CHUNKS
_TIMEOUT_SECONDS: Final = 30.0

_CHILD_SCRIPT: Final = f"""\
import os
import sys

def size():
    value = os.get_terminal_size(sys.stdout.fileno())
    return f"{{value.columns}}x{{value.lines}}"

print(f"TV_INITIAL:{{size()}}", flush=True)
first = sys.stdin.readline().strip()
print(f"TV_INPUT:{{first}}", flush=True)
print("TV_BURST_START", flush=True)
for _ in range({_BURST_CHUNKS}):
    sys.stdout.write("Z" * {_BURST_CHUNK_BYTES})
    sys.stdout.flush()
print("TV_BURST_DONE:{_BURST_BYTES}", flush=True)
second = sys.stdin.readline().strip()
print(f"TV_RESIZED:{{size()}}", flush=True)
print(f"TV_TRIGGER:{{second}}", flush=True)
print("TV_WAITING", flush=True)
sys.stdin.readline()
"""


def test_spawn_fails_closed_off_windows() -> None:
    if os.name == "nt":
        pytest.skip("fail-closed spawn behavior is observable only off Windows")
    with pytest.raises(ConptyUnsupportedError):
        ConptyChild.spawn(
            [sys.executable, "-c", "pass"],
            rows=_INITIAL_ROWS,
            columns=_INITIAL_COLUMNS,
        )


@pytest.mark.skipif(os.name != "nt", reason="Windows ConPTY binding evidence")
def test_conpty_child_lifecycle_matches_spike_evidence() -> None:
    child = ConptyChild.spawn(
        [sys.executable, "-I", "-u", "-c", _CHILD_SCRIPT],
        rows=_INITIAL_ROWS,
        columns=_INITIAL_COLUMNS,
    )

    output: list[str] = []
    output_condition = threading.Condition()
    input_queue: queue.Queue[str | None] = queue.Queue()
    service_errors: list[str] = []
    closing = threading.Event()

    def wait_for(marker: str) -> None:
        with output_condition:
            arrived = output_condition.wait_for(
                lambda: marker in "".join(output) or bool(service_errors),
                timeout=_TIMEOUT_SECONDS,
            )
        assert arrived, f"timed out waiting for {marker!r}"
        assert not service_errors, service_errors

    def drain_output() -> None:
        try:
            while True:
                chunk = child.read(4096)
                if not chunk:
                    break
                with output_condition:
                    output.append(chunk)
                    output_condition.notify_all()
        except (EOFError, OSError) as error:
            if not closing.is_set():
                service_errors.append(f"output service: {type(error).__name__}")
        finally:
            with output_condition:
                output_condition.notify_all()

    def drain_input() -> None:
        try:
            while True:
                item = input_queue.get()
                if item is None:
                    return
                child.write(item)
        except (EOFError, OSError) as error:
            if not closing.is_set():
                service_errors.append(f"input service: {type(error).__name__}")

    reader = threading.Thread(target=drain_output, name="tv-output", daemon=True)
    writer = threading.Thread(target=drain_input, name="tv-input", daemon=True)
    try:
        reader.start()
        writer.start()
        wait_for("TV_INITIAL:")
        input_queue.put("synthetic-input\r\n")
        wait_for("TV_INPUT:synthetic-input")
        wait_for(f"TV_BURST_DONE:{_BURST_BYTES}")

        child.resize(rows=_RESIZED_ROWS, columns=_RESIZED_COLUMNS)
        input_queue.put("measure-after-resize\r\n")
        wait_for("TV_WAITING")

        assert child.is_alive()
    finally:
        closing.set()
        child.close(force=True)
        input_queue.put(None)
        if writer.ident is not None:
            writer.join(_TIMEOUT_SECONDS)
        if reader.ident is not None:
            reader.join(_TIMEOUT_SECONDS)

    assert not writer.is_alive()
    assert not reader.is_alive()
    assert not child.is_alive()
    assert type(child.exit_status) is int

    combined = "".join(output)
    initial = re.search(r"TV_INITIAL:(\d+x\d+)", combined)
    resized = re.search(r"TV_RESIZED:(\d+x\d+)", combined)
    assert initial is not None
    assert initial.group(1) == f"{_INITIAL_COLUMNS}x{_INITIAL_ROWS}"
    assert resized is not None
    assert resized.group(1) == f"{_RESIZED_COLUMNS}x{_RESIZED_ROWS}"
    burst_start = combined.find("TV_BURST_START")
    burst_end = combined.find("TV_BURST_DONE")
    assert 0 <= burst_start < burst_end
    assert combined[burst_start:burst_end].count("Z") == _BURST_BYTES
