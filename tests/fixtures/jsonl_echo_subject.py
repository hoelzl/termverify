#!/usr/bin/env python3
"""Reference fixture subject speaking `termverify.control/v1` (slice 2).

A cooperative, deterministic subject for the JSONL transport's
real-subprocess integration evidence. It reads canonical-JSON message
lines from stdin (bytes, UTF-8, LF-delimited — the ordinary pipe
obligation; no console-input caveats apply), answers the handshake, runs
single-flight epochs for every input kind, and closes runs honestly:

- On ``session.hello`` it validates the envelope, echoes the delivered
  environment variables (``TERMVERIFY_*``) and its working directory into
  a startup ``diagnostic``, and sends ``session.ready`` with an initial
  observation whose frame shows the delivered terminal dimensions.
- Each epoch echoes the input into the closing ``observation``: text as
  an event, a key chord as an event, a resize as the new frame
  dimensions (proving the child observed the delivered dimensions), and
  a clock advance as an event carrying the delivered manual time.
- ``input.stop`` closes the run with ``run.finished`` claiming the exit
  code 3, after which the process actually exits 3 — claimed and
  OS-observed records agree. The text command ``"quit"`` ends the epoch
  in a natural exit (code 7) with no terminal message, exercising the
  end-of-stream path; ``"hang"`` never answers, so only the abort
  deadline can end the epoch.
- ``"boom"`` as text sends ``run.failed`` with a subject error.

Determinism: no wall-clock, randomness, or ambient state beyond the
delivered environment; every observation is a pure function of the
inputs.
"""

from __future__ import annotations

import json
import os
import sys

_PROTOCOL = "termverify.control/v1"

#: Loose JSON containers — the fixture is a protocol speaker, not a
#: typed-model consumer; values are whatever JSON carries.
_Json = dict[str, object]


def _emit(kind: str, payload: _Json) -> None:
    line = json.dumps(
        {"protocol": _PROTOCOL, "kind": kind, "payload": payload},
        separators=(",", ":"),
        sort_keys=True,
    )
    sys.stdout.buffer.write(line.encode("utf-8") + b"\n")
    sys.stdout.buffer.flush()


def _ui() -> _Json:
    return {"regions": [], "cursor": {"column": 0, "row": 0, "visible": True}}


def _frame(columns: int, rows: int, *lines: str) -> _Json:
    padded = [line.ljust(columns)[:columns] for line in lines]
    blank = " " * columns
    return {
        "lines": (padded + [blank] * rows)[:rows],
        "columns": columns,
        "rows": rows,
    }


def _observation(
    state: _Json,
    events: list[object],
    columns: int,
    rows: int,
    *frame_lines: str,
) -> _Json:
    return {
        "state": state,
        "ui": _ui(),
        "events": events,
        "frame": _frame(columns, rows, *frame_lines),
    }


def main() -> int:
    columns, rows = 80, 24
    # --- handshake ---------------------------------------------------------
    line = sys.stdin.buffer.readline()
    hello = json.loads(line.decode("utf-8"))
    if hello.get("protocol") != _PROTOCOL or hello.get("kind") != "session.hello":
        _emit(
            "session.failed",
            {
                "error": {
                    "code": "bad-hello",
                    "message": "expected session.hello",
                    "details": None,
                }
            },
        )
        return 2
    config = hello["payload"]["config"]
    columns = config["terminal"]["columns"]
    rows = config["terminal"]["rows"]
    delivered = {
        name: os.environ.get(name, "<missing>")
        for name in (
            "TERMVERIFY_SEED",
            "TERMVERIFY_CLOCK_INITIAL_MS",
            "TERMVERIFY_LOCALE",
            "TZ",
            "TERMVERIFY_TIMEZONE",
            "TERMVERIFY_FS_ROOT",
            "TERMVERIFY_NETWORK",
        )
    }
    _emit(
        "diagnostic",
        {
            "code": "fixture-delivery",
            "message": "the fixture observed its delivered environment",
            "details": {
                "delivered": delivered,
                "cwd": os.getcwd(),
            },
        },
    )
    _emit(
        "session.ready",
        {
            "observation": _observation(
                {"fixture": "ready"},
                [],
                columns,
                rows,
                "TV_READY",
                f"TV_SIZE:{columns}x{rows}",
            )
        },
    )
    # --- epoch loop ---------------------------------------------------------
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            return 1
        message = json.loads(line.decode("utf-8"))
        kind = message["kind"]
        payload = message["payload"]
        if kind == "input.stop":
            _emit("run.finished", {"exit": {"kind": "code", "value": 3}})
            return 3
        if kind == "input.text":
            text = payload["text"]
            if text == "hang":
                import time

                time.sleep(600)
            if text == "boom":
                _emit(
                    "run.failed",
                    {
                        "error": {
                            "code": "subject-boom",
                            "message": "the fixture failed as requested",
                            "details": {"text": text},
                        }
                    },
                )
                return 4
            if text == "quit":
                # Natural exit without a terminal message: the run must end
                # in native end-of-stream with the OS-observed record.
                return 7
            _emit(
                "observation",
                _observation(
                    {"fixture": "text"},
                    [{"type": "fixture.text", "data": {"text": text}}],
                    columns,
                    rows,
                    f"TV_TEXT:{text}",
                ),
            )
            continue
        if kind == "input.key":
            keys = list(payload["keys"])
            chord = "+".join(keys)
            _emit(
                "observation",
                _observation(
                    {"fixture": "key"},
                    [{"type": "fixture.key", "data": {"keys": keys}}],
                    columns,
                    rows,
                    f"TV_KEY:{chord}",
                ),
            )
            continue
        if kind == "input.resize":
            columns = payload["columns"]
            rows = payload["rows"]
            _emit(
                "observation",
                _observation(
                    {"fixture": "resize"},
                    [
                        {
                            "type": "fixture.resize",
                            "data": {"columns": columns, "rows": rows},
                        }
                    ],
                    columns,
                    rows,
                    f"TV_RESIZED:{columns}x{rows}",
                ),
            )
            continue
        if kind == "input.clock":
            at_ms = payload["at_ms"]
            _emit(
                "observation",
                _observation(
                    {"fixture": "clock"},
                    [{"type": "fixture.clock", "data": {"at_ms": at_ms}}],
                    columns,
                    rows,
                    f"TV_CLOCK:{at_ms}",
                ),
            )
            continue
        _emit(
            "run.failed",
            {
                "error": {
                    "code": "unknown-input",
                    "message": f"the fixture does not know {kind}",
                    "details": None,
                }
            },
        )
        return 5


if __name__ == "__main__":
    sys.exit(main())
