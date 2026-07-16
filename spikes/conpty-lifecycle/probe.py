"""Reproducible Windows ConPTY lifecycle feasibility probe.

Run with the transient, pinned binding shown in this spike's README. This is
isolated spike code, not a production adapter or containment boundary.
"""

from __future__ import annotations

import importlib.metadata
import json
import os
import queue
import re
import sys
import threading
from dataclasses import asdict, dataclass
from typing import Any, Final

_INITIAL_ROWS: Final = 24
_INITIAL_COLUMNS: Final = 80
_RESIZED_ROWS: Final = 30
_RESIZED_COLUMNS: Final = 100
_BURST_BYTES: Final = 1_048_576
_TIMEOUT_SECONDS: Final = 10.0


@dataclass(frozen=True)
class ProbeResult:
    verdict: str
    binding: str
    binding_version: str
    initial_size: str | None
    resized_size: str | None
    input_echo: str | None
    burst_bytes: int
    alive_before_close: bool
    process_exit_observed: bool
    output_reader_stopped: bool
    writer_stopped: bool
    close_completed: bool
    exit_status: int | None
    errors: tuple[str, ...]


def _child_script() -> str:
    return """\
import os
import sys

def size():
    value = os.get_terminal_size(sys.stdout.fileno())
    return f"{value.columns}x{value.lines}"

print(f"TV_INITIAL:{size()}", flush=True)
first = sys.stdin.readline().strip()
print(f"TV_INPUT:{first}", flush=True)
print("TV_BURST_START", flush=True)
for _ in range(1024):
    sys.stdout.write("Z" * 1024)
    sys.stdout.flush()
print("TV_BURST_DONE:1048576", flush=True)
second = sys.stdin.readline().strip()
print(f"TV_RESIZED:{size()}", flush=True)
print(f"TV_TRIGGER:{second}", flush=True)
print("TV_WAITING", flush=True)
sys.stdin.readline()
"""


def _extract_marker(output: str, name: str, pattern: str) -> str | None:
    match = re.search(r"TV_" + re.escape(name) + r":" + pattern, output)
    return None if match is None else match.group(1)


def run_probe() -> ProbeResult:
    binding_version = importlib.metadata.version("pywinpty")
    if os.name != "nt":
        return ProbeResult(
            verdict="unsupported-host",
            binding="pywinpty-conpty",
            binding_version=binding_version,
            initial_size=None,
            resized_size=None,
            input_echo=None,
            burst_bytes=0,
            alive_before_close=False,
            process_exit_observed=False,
            output_reader_stopped=False,
            writer_stopped=False,
            close_completed=False,
            exit_status=None,
            errors=("Windows ConPTY is required",),
        )

    from winpty import Backend, PtyProcess

    output: list[str] = []
    output_condition = threading.Condition()
    input_queue: queue.Queue[str | None] = queue.Queue()
    errors: list[str] = []
    closing = threading.Event()
    close_started = threading.Event()

    process: Any = PtyProcess.spawn(
        [sys.executable, "-I", "-u", "-c", _child_script()],
        dimensions=(_INITIAL_ROWS, _INITIAL_COLUMNS),
        backend=Backend.ConPTY,
    )

    def record_thread_error(message: str) -> None:
        with output_condition:
            errors.append(message)
            output_condition.notify_all()

    def wait_for(marker: str) -> bool:
        with output_condition:
            return output_condition.wait_for(
                lambda: marker in "".join(output) or bool(errors),
                timeout=_TIMEOUT_SECONDS,
            )

    def drain_output() -> None:
        try:
            while True:
                chunk = process.read(4096)
                if not chunk:
                    break
                with output_condition:
                    output.append(chunk)
                    output_condition.notify_all()
        except (EOFError, OSError) as error:
            if not closing.is_set():
                record_thread_error(f"output service failed: {type(error).__name__}")
        except Exception as error:
            record_thread_error(f"output service failed: {type(error).__name__}")
        finally:
            with output_condition:
                output_condition.notify_all()

    def drain_input() -> None:
        try:
            while True:
                item = input_queue.get()
                if item is None:
                    return
                process.write(item)
        except (EOFError, OSError) as error:
            if not closing.is_set():
                record_thread_error(f"input service failed: {type(error).__name__}")
        except Exception as error:
            record_thread_error(f"input service failed: {type(error).__name__}")

    reader = threading.Thread(
        target=drain_output,
        name="conpty-output-drain",
        daemon=True,
    )
    writer = threading.Thread(
        target=drain_input,
        name="conpty-input-drain",
        daemon=True,
    )

    close_errors: list[str] = []

    def close_process() -> None:
        try:
            process.close(force=True)
        except Exception as error:
            close_errors.append(f"close failed: {type(error).__name__}")

    reader_started = False
    writer_started = False

    try:
        reader.start()
        reader_started = True
        writer.start()
        writer_started = True

        if not wait_for("TV_INITIAL:"):
            errors.append("timed out waiting for initial-size marker")
        input_queue.put("synthetic-input\r\n")
        if not wait_for("TV_INPUT:synthetic-input"):
            errors.append("timed out waiting for input marker")
        if not wait_for(f"TV_BURST_DONE:{_BURST_BYTES}"):
            errors.append("timed out waiting for deterministic output burst")

        process.setwinsize(_RESIZED_ROWS, _RESIZED_COLUMNS)
        input_queue.put("measure-after-resize\r\n")
        if not wait_for("TV_WAITING"):
            errors.append("timed out waiting for resized-size marker")

        alive_before_close = bool(process.isalive())
        closing.set()
        closer = threading.Thread(
            target=close_process,
            name="conpty-close",
            daemon=True,
        )
        try:
            closer.start()
        except Exception:
            closing.clear()
            raise
        close_started.set()
        closer.join(_TIMEOUT_SECONDS)
        close_completed = not closer.is_alive()
        if not close_completed:
            errors.append("close did not complete before timeout")
        errors.extend(close_errors)

        input_queue.put(None)
        writer.join(_TIMEOUT_SECONDS)
        reader.join(_TIMEOUT_SECONDS)
        process_exit_observed = close_completed and not bool(process.isalive())
        if not process_exit_observed:
            errors.append("child exit was not observable after close")

        combined_output = "".join(output)
        initial_size = _extract_marker(combined_output, "INITIAL", r"(\d+x\d+)")
        resized_size = _extract_marker(combined_output, "RESIZED", r"(\d+x\d+)")
        input_echo = _extract_marker(combined_output, "INPUT", r"([^\r\n]+)")
        burst_start = combined_output.find("TV_BURST_START")
        burst_end = combined_output.find("TV_BURST_DONE")
        burst_bytes = (
            combined_output[burst_start:burst_end].count("Z")
            if 0 <= burst_start < burst_end
            else 0
        )
        exit_status = process.exitstatus if close_completed else None
        output_reader_stopped = not reader.is_alive()
        writer_stopped = not writer.is_alive()
        expected = (
            initial_size == f"{_INITIAL_COLUMNS}x{_INITIAL_ROWS}"
            and resized_size == f"{_RESIZED_COLUMNS}x{_RESIZED_ROWS}"
            and input_echo == "synthetic-input"
            and burst_bytes == _BURST_BYTES
            and alive_before_close
            and process_exit_observed
            and type(exit_status) is int
            and output_reader_stopped
            and writer_stopped
            and close_completed
            and not errors
        )
        return ProbeResult(
            verdict="validated-binding-lifecycle" if expected else "partial",
            binding="pywinpty-conpty",
            binding_version=binding_version,
            initial_size=initial_size,
            resized_size=resized_size,
            input_echo=input_echo,
            burst_bytes=burst_bytes,
            alive_before_close=alive_before_close,
            process_exit_observed=process_exit_observed,
            output_reader_stopped=output_reader_stopped,
            writer_stopped=writer_stopped,
            close_completed=close_completed,
            exit_status=exit_status,
            errors=tuple(errors),
        )
    finally:
        if not close_started.is_set():
            closing.set()
            cleanup_closer = threading.Thread(
                target=close_process,
                name="conpty-cleanup-close",
                daemon=True,
            )
            cleanup_closer.start()
            cleanup_closer.join(1)
        input_queue.put(None)
        if writer_started:
            writer.join(1)
        if reader_started:
            reader.join(1)


def main() -> int:
    try:
        result = run_probe()
    except Exception as error:
        result = ProbeResult(
            verdict="invalidated",
            binding="pywinpty-conpty",
            binding_version=importlib.metadata.version("pywinpty"),
            initial_size=None,
            resized_size=None,
            input_echo=None,
            burst_bytes=0,
            alive_before_close=False,
            process_exit_observed=False,
            output_reader_stopped=False,
            writer_stopped=False,
            close_completed=False,
            exit_status=None,
            errors=(type(error).__name__,),
        )
    print(json.dumps(asdict(result), sort_keys=True, separators=(",", ":")))
    return 0 if result.verdict == "validated-binding-lifecycle" else 1


if __name__ == "__main__":
    raise SystemExit(main())
