"""Minimal Windows ConPTY binding boundary for the terminal adapter plan.

This module owns the pseudoconsole itself: it creates the conin and conout
pipes, calls ``CreatePseudoConsole``, starts the child through an
``STARTUPINFOEX`` attribute list, and reads raw bytes off conout with its own
``ReadFile`` loop. Nothing stands between the caller and the pipe — no relay
reader thread whose death could masquerade as end-of-stream — so every
observable (output bytes, end-of-stream, liveness, exit status) is a direct
native signal.

It replaced ``pywinpty`` for finding R7. ``PTY.read`` returned pre-decoded
``str``, and a native read landing mid-codepoint was decoded in isolation:
the split character became ``U+FFFD`` and was lost outright, irreparably, in
evidence. A measured 200,000-character burst of ``U+65E5`` through that path
produced 29 replacement characters across 21 reads and lost 12 characters.
``pywinpty`` exposes no bytes-returning read and no way to reach the conout
handle, and the damage cannot be repaired above it, so obtaining raw bytes
meant owning the pseudoconsole — which means owning the spawn. ``read`` still
returns ``str``; the decode is now this module's, and it runs one incremental
decoder across every chunk of a child's lifetime so splits heal.

Process-tree containment uses a Windows job object created per spawn with
``JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`` and neither breakaway limit, so every
descendant the child starts inherits membership and cannot leave. The child
is created with ``CREATE_SUSPENDED`` and assigned to the job before its main
thread resumes (issue #235), so no descendant can predate the membership:
containment is a property of the spawn, not a near-certainty. Forced
close terminates the whole tree atomically with ``TerminateJobObject``;
releasing the binding closes the job handle, which makes the OS sweep any
survivors even if this process dies abruptly.

I/O is single-flight by contract: at most one native read or write may be in
flight, and overlap fails fast with ``ConptyConcurrentIOError``. The native
layer is not thread-safe for overlapped calls on one pseudoconsole —
concurrent writing against a blocked read intermittently crashes the
interpreter with a native access violation — and the transcript
protocol is single-flight anyway, so the binding refuses the overlap rather
than risking the crash. ``close`` is the one concurrent-safe operation; it
cancels in-flight I/O and waits it out before releasing the native object,
because releasing during a native call is the same crash.

Every future adapter behavior above this binding must stay testable
cross-platform against an injected fake binding, so this native boundary is
excluded from the cross-platform coverage ratchet — the gating floor must
not depend on the host OS. The binding is no longer thin, though (#197
roughly tripled it), so the Windows CI legs measure it against the ConPTY
suites with a supplemental, non-gating report (``conpty-coverage.toml``,
issue #236) that keeps its gaps visible; the recorded rationale lives in the
developer guide. Cancellation and recovery are evidenced at this
binding level only — startup failure fails closed for both a missing command
and a command the OS refuses to start, forced close recovers from hostile
children (output flood, busy spin, in-flight write) without leaking threads,
with handle release proven by the release-only close evidence, and conin
writes showed no backpressure on the verified matrix. Classification into
the structured failure/abort taxonomy is adapter behavior and remains
unclaimed here.

Disclosed boundary — conin writes run outside the abort deadline (finding
C2, issue #193). The JSONL transport arms that deadline around every wire
write; the mechanism still does not port here. This binding now owns the
conin handle, so reaching it is no longer the obstacle it was, but the
single-flight contract above exists precisely because a concurrent write
against a blocked read intermittently wedges the native pseudoconsole — so
the write cannot be moved to another thread, and the deadline still cannot
end it. Closing that boundary is #193's own work, deliberately not this
slice's. The bound: if a subject stops draining conin and the console input
buffer fills, ``write`` blocks and the adapter's abort deadline cannot end
it. Measured on this matrix, conin sustains roughly 1 MiB/s — the console
host turns every byte into input records — and the interactive inputs
written here are far smaller than any plausible buffer, so this remains a
stated bound rather than an observed failure.

``write`` intentionally returns ``None``: the ConPTY write return value is not
a reliable byte-count receipt, and exposing it would fabricate evidence. It
does write every byte it was given before returning, which the previous
binding's single native call did not — a large payload therefore occupies
the single-flight slot for proportionally longer than it used to.
"""

from __future__ import annotations

import codecs
import contextlib
import os
import shutil
import subprocess
import sys
import threading
import time
import uuid
from collections.abc import Mapping, Sequence
from typing import Any, Final, cast

_CHILD_EXIT_WAIT_MS = 30_000
_READ_CANCEL_TIMEOUT_SECONDS = 30.0
_READ_CANCEL_RETRY_SECONDS = 0.01
#: Bound on waiting for the thread that closes the pseudoconsole. The close
#: has normally already returned by then: end-of-stream is only observable
#: after the console host exited, which is what that thread waits for.
_PSEUDOCONSOLE_DRAIN_JOIN_SECONDS = 30.0


class _NativeEndOfStream(OSError):
    """Internal: the conout pipe genuinely broke; no more bytes will arrive."""


class _NativeReadCancelled(OSError):
    """Internal: an in-flight native read was ended by ``cancel_io``."""


#: Exit code set on every process in the tree by a forced close. The value
#: keeps parity with the previous single-process termination convention.
FORCED_TERMINATION_EXIT_CODE: Final = 15


class ConptyUnsupportedError(RuntimeError):
    """Raised when the ConPTY binding is used on a host without ConPTY."""


def is_supported() -> bool:
    """Report whether this host can create ConPTY pseudoconsoles.

    This is the explicit support probe the adapter consults during
    negotiation, answering the same precondition :meth:`ConptyChild.spawn`
    checks so platform support is decidable before any spawn is attempted.
    Being Windows is not sufficient: pseudoconsoles arrived in Windows 10
    1809, and an older host exports none of the entry points, so the probe
    asks whether this build actually has them rather than assuming. It
    inspects no session state and creates nothing.
    """
    return os.name == "nt" and _HAS_PSEUDOCONSOLE


class ConptyClosedError(RuntimeError):
    """Raised when an operation is attempted after the binding was closed."""


class ConptyConcurrentIOError(RuntimeError):
    """Raised when a read or write is attempted while another is in flight.

    The native layer is not thread-safe for overlapped calls on one
    pseudoconsole: concurrent ``pty.write`` against a blocked ``pty.read``
    intermittently dies with a native access violation. The transcript
    protocol is single-flight, so the binding forbids overlap outright and
    fails fast instead of risking the crash or deadlocking behind an
    indefinitely blocked read. ``close`` is the one concurrent-safe
    operation; it cancels in-flight I/O.
    """


class ConptyEndOfStreamError(Exception):
    """Raised by ``read`` when the native output pipe reports end-of-stream.

    Only raised while the binding is open: a read interrupted by ``close``
    raises :class:`ConptyClosedError` instead, because close may abandon
    buffered output. On this genuine end-of-stream path Windows pipe
    semantics deliver all buffered output before the read side observes the
    broken pipe, so every byte the pseudoconsole emitted has been returned by
    earlier ``read`` calls when this is raised.
    """


class ConptyGeometryMismatchError(OSError):
    """The pseudoconsole cannot, or provably did not, adopt the geometry.

    Raised by :meth:`ConptyChild.spawn` before a session is handed out when
    the requested terminal geometry cannot survive the console's signed
    16-bit ``COORD`` members, or when the adopted size measured by the
    geometry probe differs from the request. Subclasses ``OSError`` so
    existing spawn-failure handling applies; the structured members carry
    the geometry facts for the adapter's failure record (issue #228).
    """

    def __init__(
        self,
        message: str,
        *,
        requested: tuple[int, int],
        adopted: tuple[int, int] | None,
    ) -> None:
        super().__init__(message)
        #: The requested ``(rows, columns)``.
        self.requested = requested
        #: The adopted ``(rows, columns)`` measured by the probe, or ``None``
        #: when the refusal is predictive (nothing was spawned or measured).
        self.adopted = adopted


#: One ``COORD`` member is a signed 16-bit value; a request is wrapped into
#: it unchecked at ``CreatePseudoConsole`` time (issue #228).
_COORD_WRAP_MODULUS: Final = 65_536

#: The largest ``COORD`` member value that stays positive after the wrap.
_COORD_MAX_VALID: Final = 32_767


def _predict_geometry_refusal(rows: int, columns: int) -> str | None:
    """Why conhost cannot adopt this geometry exactly, or ``None``.

    Measured on the Windows dev host (issue #228): ``PTY()`` and
    ``CreatePseudoConsole`` range-check nothing, and the request is wrapped
    into the signed 16-bit ``COORD`` members with three observable misfires:

    - wraps to zero: ``CreatePseudoConsole`` rejects it (``E_INVALIDARG``);
    - wraps negative: the child dies at console attach with
      ``STATUS_DLL_INIT_FAILED`` (0xC0000142) — the run *started* and
      produced a cryptic exit status, not a geometry failure;
    - wraps to a smaller positive: the console silently adopts the wrapped
      size and the child runs at a geometry the receipt claims at
      ``tier="os"`` — the overclaim class this verification exists to close.

    Anything that survives the wrap unchanged (both members in
    ``[1, 32767]``) was adopted exactly by every host measured, up to
    32767x32767; the read-back probe guards the residual anyway.
    """
    for axis, value in (("rows", rows), ("columns", columns)):
        wrapped = value % _COORD_WRAP_MODULUS
        if wrapped == 0:
            return (
                f"the requested terminal geometry {columns}x{rows} cannot be"
                f" adopted: {axis}={value} wraps to zero in the console's"
                " signed 16-bit COORD member, which CreatePseudoConsole"
                " rejects"
            )
        if wrapped > _COORD_MAX_VALID:
            return (
                f"the requested terminal geometry {columns}x{rows} cannot be"
                f" adopted: {axis}={value} wraps to {wrapped - _COORD_WRAP_MODULUS}"
                " in the console's signed 16-bit COORD member, and conhost"
                " kills the child at console attach"
            )
        if wrapped != value:
            return (
                f"the requested terminal geometry {columns}x{rows} cannot be"
                f" adopted: {axis}={value} silently truncates to {wrapped} in"
                " the console's signed 16-bit COORD member, and the child"
                " would run at a size the receipt never recorded"
            )
    return None


#: One-liner probe child: read the 22-byte CONSOLE_SCREEN_BUFFER_INFO as raw
#: bytes (no class statements — compound statements are illegal in ``-c``),
#: then answer through the exit status, the one channel that is independent
#: of console size — a long token in the output stream is torn apart by
#: cursor repositioning at tiny geometries, but a 31-bit exit code survives
#: every console. Bit layout: ``(columns << 16) | rows`` from the console
#: window rect; a failed query answers 0, which decodes as invalid.
_GEOMETRY_PROBE_SOURCE: Final = (
    "import ctypes,struct;"
    "k=ctypes.windll.kernel32;"
    "b=(ctypes.c_ubyte*22)();"
    "ok=k.GetConsoleScreenBufferInfo(k.GetStdHandle(-11),b);"
    "d=struct.unpack('<11h',bytes(b));"
    "import sys;"
    "sys.exit((((d[7]-d[5]+1)<<16)|(d[8]-d[6]+1)) if ok else 0)"
)

_GEOMETRY_PROBE_TIMEOUT_SECONDS: Final = 30.0

#: Verified or measured adoptions by requested ``(rows, columns)``, for the
#: process lifetime — conhost adoption is deterministic per host, so one
#: probe per distinct geometry bounds the read-back cost. A benign race: two
#: concurrent first spawns at one geometry may both probe; the answers are
#: identical and idempotent.
_GEOMETRY_ADOPTIONS: dict[tuple[int, int], tuple[int, int]] = {}


def _probe_geometry(rows: int, columns: int) -> tuple[int, int]:
    """Measure the geometry the console actually adopts at this request.

    The ConPTY API has no parent-side size getter: ``ResizePseudoConsole``
    only sets, and the parent's conout handle is a pipe, not a console
    screen buffer. The adopted size is observable only from inside the
    console, so a probe child reads it and answers through its exit status.
    The probe spawns through the same suspended-then-contained machinery as
    a subject, minus the geometry verification it exists to perform.
    """
    child = ConptyChild._spawn_contained(
        [sys.executable, "-I", "-u", "-c", _GEOMETRY_PROBE_SOURCE],
        rows=rows,
        columns=columns,
    )
    try:
        deadline = time.monotonic() + _GEOMETRY_PROBE_TIMEOUT_SECONDS
        while child.is_alive() and time.monotonic() < deadline:
            time.sleep(0.05)
        if child.is_alive():
            raise OSError(
                "the ConPTY geometry probe child did not exit within"
                f" {_GEOMETRY_PROBE_TIMEOUT_SECONDS:.0f}s at {columns}x{rows}"
            )
        status = child.exit_status
    finally:
        child.close(force=True)
    if status is None:
        raise OSError("the ConPTY geometry probe produced no exit record")
    adopted_columns, adopted_rows = status >> 16, status & 0xFFFF
    if not (
        1 <= adopted_columns <= _COORD_MAX_VALID
        and 1 <= adopted_rows <= _COORD_MAX_VALID
    ):
        raise OSError(
            "the ConPTY geometry probe child failed"
            f" (exit status {status:#010x}) at {columns}x{rows}"
        )
    return (adopted_rows, adopted_columns)


def _verify_geometry(rows: int, columns: int) -> None:
    """Prove the console adopts this geometry exactly, or fail closed.

    Predictable misfires are refused from the measured model without
    spawning anything; everything else is proven by the probe child's
    read-back, cached per process. A refusal raises
    :class:`ConptyGeometryMismatchError` before any session is handed out,
    so a receipt can never claim ``tier="os"`` for a geometry the subject
    did not run at (issue #228).
    """
    refusal = _predict_geometry_refusal(rows, columns)
    if refusal is not None:
        raise ConptyGeometryMismatchError(
            refusal, requested=(rows, columns), adopted=None
        )
    requested = (rows, columns)
    if requested not in _GEOMETRY_ADOPTIONS:
        _GEOMETRY_ADOPTIONS[requested] = _probe_geometry(rows, columns)
    adopted = _GEOMETRY_ADOPTIONS[requested]
    if adopted != requested:
        raise ConptyGeometryMismatchError(
            f"requested terminal geometry {columns}x{rows} but the"
            f" pseudoconsole adopted {adopted[1]}x{adopted[0]}",
            requested=requested,
            adopted=adopted,
        )


if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    _SYNCHRONIZE = 0x0010_0000
    _PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    _PROCESS_SET_QUOTA = 0x0100
    _PROCESS_TERMINATE = 0x0001
    _WAIT_OBJECT_0 = 0
    _WAIT_TIMEOUT = 0x102
    _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
    _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
    _INFINITE = 0xFFFF_FFFF
    _INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
    _ERROR_INSUFFICIENT_BUFFER = 122
    _ERROR_BROKEN_PIPE = 109
    _ERROR_IO_PENDING = 997
    _ERROR_OPERATION_ABORTED = 995
    _PIPE_ACCESS_INBOUND = 0x0000_0001
    _PIPE_TYPE_BYTE = 0x0000_0000
    _PIPE_READMODE_BYTE = 0x0000_0000
    _PIPE_WAIT = 0x0000_0000
    _PIPE_REJECT_REMOTE_CLIENTS = 0x0000_0008
    _FILE_FLAG_OVERLAPPED = 0x4000_0000
    _FILE_FLAG_FIRST_PIPE_INSTANCE = 0x0008_0000
    _GENERIC_WRITE = 0x4000_0000
    _OPEN_EXISTING = 3
    _EXTENDED_STARTUPINFO_PRESENT = 0x0008_0000
    _STARTF_USESTDHANDLES = 0x0000_0100
    _CREATE_UNICODE_ENVIRONMENT = 0x0000_0400
    #: The child starts frozen and is assigned to its containment job before
    #: its main thread resumes, so no descendant can predate the membership
    #: (issue #235).
    _CREATE_SUSPENDED = 0x0000_0004
    _PROC_THREAD_ATTRIBUTE_PSEUDOCONSOLE = 0x0002_0016
    #: One native read never returns more than this many bytes. The value only
    #: caps a single ``ReadFile``; the pipe delivers whatever is available.
    _READ_BUFFER_BYTES = 64 * 1024
    #: Kernel buffer for the conout pipe. Sized well above one screenful
    #: because a full pipe stalls the console host's renderer, and a stalled
    #: renderer stops streaming and repaints the viewport instead — which
    #: re-emits rows this binding already delivered.
    _CONOUT_PIPE_BUFFER_BYTES = 1024 * 1024

    class _Coord(ctypes.Structure):
        _fields_ = [("X", wintypes.SHORT), ("Y", wintypes.SHORT)]

    class _Overlapped(ctypes.Structure):
        _fields_ = [
            ("Internal", ctypes.c_size_t),
            ("InternalHigh", ctypes.c_size_t),
            ("Offset", wintypes.DWORD),
            ("OffsetHigh", wintypes.DWORD),
            ("hEvent", wintypes.HANDLE),
        ]

    class _StartupInfoW(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("lpReserved", wintypes.LPWSTR),
            ("lpDesktop", wintypes.LPWSTR),
            ("lpTitle", wintypes.LPWSTR),
            ("dwX", wintypes.DWORD),
            ("dwY", wintypes.DWORD),
            ("dwXSize", wintypes.DWORD),
            ("dwYSize", wintypes.DWORD),
            ("dwXCountChars", wintypes.DWORD),
            ("dwYCountChars", wintypes.DWORD),
            ("dwFillAttribute", wintypes.DWORD),
            ("dwFlags", wintypes.DWORD),
            ("wShowWindow", wintypes.WORD),
            ("cbReserved2", wintypes.WORD),
            ("lpReserved2", ctypes.POINTER(wintypes.BYTE)),
            ("hStdInput", wintypes.HANDLE),
            ("hStdOutput", wintypes.HANDLE),
            ("hStdError", wintypes.HANDLE),
        ]

    class _StartupInfoExW(ctypes.Structure):
        _fields_ = [
            ("StartupInfo", _StartupInfoW),
            ("lpAttributeList", ctypes.c_void_p),
        ]

    class _ProcessInformation(ctypes.Structure):
        _fields_ = [
            ("hProcess", wintypes.HANDLE),
            ("hThread", wintypes.HANDLE),
            ("dwProcessId", wintypes.DWORD),
            ("dwThreadId", wintypes.DWORD),
        ]

    class _IoCounters(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_uint64),
            ("WriteOperationCount", ctypes.c_uint64),
            ("OtherOperationCount", ctypes.c_uint64),
            ("ReadTransferCount", ctypes.c_uint64),
            ("WriteTransferCount", ctypes.c_uint64),
            ("OtherTransferCount", ctypes.c_uint64),
        ]

    class _JobBasicLimits(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class _JobExtendedLimits(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", _JobBasicLimits),
            ("IoInfo", _IoCounters),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _kernel32.OpenProcess.restype = wintypes.HANDLE
    _kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    _kernel32.WaitForSingleObject.restype = wintypes.DWORD
    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    _kernel32.CloseHandle.restype = wintypes.BOOL
    _kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    _kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    _kernel32.SetInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    _kernel32.SetInformationJobObject.restype = wintypes.BOOL
    _kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    _kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
    _kernel32.ResumeThread.argtypes = [wintypes.HANDLE]
    _kernel32.ResumeThread.restype = wintypes.DWORD
    _kernel32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
    _kernel32.TerminateJobObject.restype = wintypes.BOOL
    _kernel32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    _kernel32.TerminateProcess.restype = wintypes.BOOL
    _kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, wintypes.LPDWORD]
    _kernel32.GetExitCodeProcess.restype = wintypes.BOOL
    _kernel32.CreatePipe.argtypes = [
        ctypes.POINTER(wintypes.HANDLE),
        ctypes.POINTER(wintypes.HANDLE),
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    _kernel32.CreatePipe.restype = wintypes.BOOL
    _kernel32.CreateNamedPipeW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
    ]
    _kernel32.CreateNamedPipeW.restype = wintypes.HANDLE
    _kernel32.CreateFileW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    _kernel32.CreateFileW.restype = wintypes.HANDLE
    _kernel32.CreateEventW.argtypes = [
        ctypes.c_void_p,
        wintypes.BOOL,
        wintypes.BOOL,
        wintypes.LPCWSTR,
    ]
    _kernel32.CreateEventW.restype = wintypes.HANDLE
    _kernel32.SetEvent.argtypes = [wintypes.HANDLE]
    _kernel32.SetEvent.restype = wintypes.BOOL
    _kernel32.ResetEvent.argtypes = [wintypes.HANDLE]
    _kernel32.ResetEvent.restype = wintypes.BOOL
    _kernel32.WaitForMultipleObjects.argtypes = [
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.BOOL,
        wintypes.DWORD,
    ]
    _kernel32.WaitForMultipleObjects.restype = wintypes.DWORD
    _kernel32.ReadFile.argtypes = [
        wintypes.HANDLE,
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.LPDWORD,
        ctypes.c_void_p,
    ]
    _kernel32.ReadFile.restype = wintypes.BOOL
    _kernel32.WriteFile.argtypes = [
        wintypes.HANDLE,
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.LPDWORD,
        ctypes.c_void_p,
    ]
    _kernel32.WriteFile.restype = wintypes.BOOL
    _kernel32.CancelIoEx.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
    _kernel32.CancelIoEx.restype = wintypes.BOOL
    _kernel32.GetOverlappedResult.argtypes = [
        wintypes.HANDLE,
        ctypes.c_void_p,
        wintypes.LPDWORD,
        wintypes.BOOL,
    ]
    _kernel32.GetOverlappedResult.restype = wintypes.BOOL
    _kernel32.InitializeProcThreadAttributeList.argtypes = [
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(ctypes.c_size_t),
    ]
    _kernel32.InitializeProcThreadAttributeList.restype = wintypes.BOOL
    _kernel32.UpdateProcThreadAttribute.argtypes = [
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.c_size_t,
        ctypes.c_void_p,
        ctypes.c_size_t,
        ctypes.c_void_p,
        ctypes.c_void_p,
    ]
    _kernel32.UpdateProcThreadAttribute.restype = wintypes.BOOL
    _kernel32.DeleteProcThreadAttributeList.argtypes = [ctypes.c_void_p]
    _kernel32.DeleteProcThreadAttributeList.restype = None
    _kernel32.CreateProcessW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.LPWSTR,
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.BOOL,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.LPCWSTR,
        ctypes.c_void_p,
        ctypes.c_void_p,
    ]
    _kernel32.CreateProcessW.restype = wintypes.BOOL
    #: ConPTY arrived in Windows 10 1809; older hosts export none of these.
    _HAS_PSEUDOCONSOLE = hasattr(_kernel32, "CreatePseudoConsole")
    if _HAS_PSEUDOCONSOLE:
        _kernel32.CreatePseudoConsole.argtypes = [
            _Coord,
            wintypes.HANDLE,
            wintypes.HANDLE,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.HANDLE),
        ]
        _kernel32.CreatePseudoConsole.restype = ctypes.c_long
        _kernel32.ResizePseudoConsole.argtypes = [wintypes.HANDLE, _Coord]
        _kernel32.ResizePseudoConsole.restype = ctypes.c_long
        _kernel32.ClosePseudoConsole.argtypes = [wintypes.HANDLE]
        _kernel32.ClosePseudoConsole.restype = None

    def _create_containment_job() -> int:
        """Create a kill-on-close job object for one pseudoconsole child."""
        job = _kernel32.CreateJobObjectW(None, None)
        if not job:
            raise OSError(f"CreateJobObject failed: {ctypes.get_last_error()}")
        limits = _JobExtendedLimits()
        limits.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not _kernel32.SetInformationJobObject(
            job,
            _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
            ctypes.byref(limits),
            ctypes.sizeof(limits),
        ):
            error = ctypes.get_last_error()
            _kernel32.CloseHandle(job)
            raise OSError(f"SetInformationJobObject failed: {error}")
        return int(job)

    def _open_containment_handle(pid: int) -> int:
        """Open the child's real process handle for assignment and waits."""
        handle = _kernel32.OpenProcess(
            _SYNCHRONIZE
            | _PROCESS_QUERY_LIMITED_INFORMATION
            | _PROCESS_SET_QUOTA
            | _PROCESS_TERMINATE,
            False,
            pid,
        )
        if not handle:
            raise OSError(f"OpenProcess({pid}) failed: {ctypes.get_last_error()}")
        return int(handle)

    def _assign_to_job(job: int, process_handle: int) -> None:
        if not _kernel32.AssignProcessToJobObject(job, process_handle):
            raise OSError(f"AssignProcessToJobObject failed: {ctypes.get_last_error()}")

    def _resume_main_thread(thread_handle: int) -> None:
        """Resume a child spawned with ``CREATE_SUSPENDED`` (issue #235)."""
        if _kernel32.ResumeThread(wintypes.HANDLE(thread_handle)) == 0xFFFFFFFF:
            raise OSError(f"ResumeThread failed: {ctypes.get_last_error()}")

    def _terminate_job(job: int, exit_code: int) -> None:
        if not _kernel32.TerminateJobObject(job, exit_code):
            raise OSError(f"TerminateJobObject failed: {ctypes.get_last_error()}")

    def _terminate_process(process_handle: int, exit_code: int) -> None:
        _kernel32.TerminateProcess(process_handle, exit_code)

    def _wait_for_handle(handle: int, timeout_ms: int) -> bool:
        """OS wait on a real handle; True once it is signaled, never a sleep.

        A wait failure is a real error, not a timeout, and is raised as such
        so it cannot masquerade as "the process did not terminate".
        """
        result = int(_kernel32.WaitForSingleObject(handle, timeout_ms))
        if result == _WAIT_OBJECT_0:
            return True
        if result == _WAIT_TIMEOUT:
            return False
        raise OSError(
            f"WaitForSingleObject failed ({result:#x}): {ctypes.get_last_error()}"
        )

    def _close_handle(handle: int) -> None:
        _kernel32.CloseHandle(handle)

    def _last_error(call: str) -> OSError:
        return OSError(f"{call} failed: {ctypes.get_last_error()}")

    def _make_overlapped_conout_pipe() -> tuple[int, int]:
        """Create the conout pipe with an overlapped, cancellable read end.

        ``CreatePipe`` cannot produce an overlapped handle, and a synchronous
        ``ReadFile`` on a pipe cannot be cancelled from the closing thread —
        the binding's close contract needs both. A named pipe can, so the
        read end is a first-instance, local-only named pipe server and the
        write end handed to the pseudoconsole is a client opened on it.

        ``FILE_FLAG_FIRST_PIPE_INSTANCE`` makes creation fail rather than
        join an existing instance, so another process cannot pre-create the
        name and receive this session's output; the name itself carries a
        ``uuid4`` so it is not guessable in the first place.
        """
        name = f"\\\\.\\pipe\\termverify-conout-{os.getpid()}-{uuid.uuid4().hex}"
        read_side = _kernel32.CreateNamedPipeW(
            name,
            _PIPE_ACCESS_INBOUND
            | _FILE_FLAG_OVERLAPPED
            | _FILE_FLAG_FIRST_PIPE_INSTANCE,
            _PIPE_TYPE_BYTE
            | _PIPE_READMODE_BYTE
            | _PIPE_WAIT
            | _PIPE_REJECT_REMOTE_CLIENTS,
            1,
            _CONOUT_PIPE_BUFFER_BYTES,
            _CONOUT_PIPE_BUFFER_BYTES,
            0,
            None,
        )
        if not read_side or int(read_side) == _INVALID_HANDLE_VALUE:
            raise _last_error("CreateNamedPipeW")
        write_side = _kernel32.CreateFileW(
            name, _GENERIC_WRITE, 0, None, _OPEN_EXISTING, 0, None
        )
        if not write_side or int(write_side) == _INVALID_HANDLE_VALUE:
            error = ctypes.get_last_error()
            _kernel32.CloseHandle(read_side)
            raise OSError(f"CreateFileW on the conout pipe failed: {error}")
        return int(read_side), int(write_side)

    def _close_pseudoconsole(pseudoconsole: int) -> None:
        _kernel32.ClosePseudoConsole(pseudoconsole)

    class _PseudoConsoleSession:
        """One natively owned ConPTY session: handles, child, and raw I/O.

        This is the object ``ConptyChild`` wraps. It exists because
        ``pywinpty`` hands out pre-decoded ``str`` and exposes no conout
        handle (finding R7): owning the raw output bytes means owning
        ``CreatePseudoConsole``, which means owning the ``STARTUPINFOEX``
        spawn as well. Every method here is a direct native call; no reader
        thread stands between the caller and the pipe.
        """

        def __init__(
            self,
            *,
            pseudoconsole: int,
            conout_read: int,
            conin_write: int,
            process_handle: int,
            thread_handle: int | None,
            pid: int,
            read_event: int,
            cancel_event: int,
        ) -> None:
            self._pseudoconsole: int | None = pseudoconsole
            self._conout_read: int | None = conout_read
            self._conin_write: int | None = conin_write
            self._process_handle: int | None = process_handle
            self._thread_handle: int | None = thread_handle
            self._read_event: int | None = read_event
            self._cancel_event: int | None = cancel_event
            self._pid = pid
            # Before the buffer: the destructor takes this lock, so an
            # allocation failure below must not leave it unset.
            self._lock = threading.Lock()
            #: Held across ``ResizePseudoConsole`` and by whoever closes the
            #: pseudoconsole, so the handle cannot be freed mid-resize
            #: without the reader ever waiting on a resize. Always taken
            #: before ``_lock``, never after.
            self._resize_lock = threading.Lock()
            self._closed = False
            self._stalled = False
            self._drain: threading.Thread | None = None
            self._buffer = ctypes.create_string_buffer(_READ_BUFFER_BYTES)
            # Last: until this is set the session is not fully built, and the
            # destructor must not release handles whose ownership still sits
            # with the caller that is constructing it.
            self._constructed = True

        @property
        def pid(self) -> int:
            return self._pid

        def resume_main_thread(self) -> None:
            """Resume the ``CREATE_SUSPENDED`` main thread exactly once (#235).

            The caller resumes only after the containment job holds the
            child. The session owns the thread handle until the resume
            succeeds and closes it immediately after, so the handle is
            released on every path — a failed resume leaves it owned here,
            for :meth:`close` during the caller's teardown.
            """
            handle = self._thread_handle
            if handle is None:
                raise ConptyClosedError("the main thread was already resumed")
            _resume_main_thread(handle)
            self._thread_handle = None
            _kernel32.CloseHandle(handle)

        def terminate_child(self, exit_code: int) -> None:
            """Terminate the child through the handle this session owns.

            The spawn's containment-setup failure paths call this before
            releasing anything: a suspended child cannot die of handle or
            pseudoconsole closes, and it is not in a job yet, so an
            unconditional terminate is the only path that cannot leak a
            frozen orphan (issue #235 review).
            """
            handle = self._process_handle
            if handle is not None:
                _kernel32.TerminateProcess(handle, exit_code)

        def isalive(self) -> bool:
            handle = self._process_handle
            if handle is None:
                return False
            return not _wait_for_handle(handle, 0)

        def get_exitstatus(self) -> int | None:
            """Return the child's native exit code once it has really exited.

            The code is read only after an OS wait says the process is
            signaled, so the ``STILL_ACTIVE`` sentinel can never be mistaken
            for a genuine exit status of 259.
            """
            handle = self._process_handle
            if handle is None or not _wait_for_handle(handle, 0):
                return None
            code = wintypes.DWORD(0)
            if not _kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                raise _last_error("GetExitCodeProcess")
            return int(code.value)

        def set_size(self, columns: int, rows: int) -> None:
            """Resize the pseudoconsole, on a handle that cannot be freed.

            Guarded by ``_resize_lock`` rather than by ``_lock``. The handle
            must not be closed underneath this native call, but holding the
            session lock across it would let a resize block the *reader*:
            the reader is what calls :meth:`_release_pseudoconsole` when the
            child exits, and a blocked reader stops draining conout, which is
            what the console host may be waiting on to finish the resize —
            a circular wait with no bound, on the one operation that has to
            stay responsive. Only whoever actually closes the handle takes
            this lock, so the reader never waits here.
            """
            with self._resize_lock:
                with self._lock:
                    pseudoconsole = self._pseudoconsole
                if pseudoconsole is None:
                    raise ConptyClosedError(
                        "the pseudoconsole is no longer owned by this session"
                    )
                result = _kernel32.ResizePseudoConsole(
                    pseudoconsole, _Coord(X=columns, Y=rows)
                )
            if result != 0:
                raise OSError(f"ResizePseudoConsole failed: {result:#010x}")

        def write(self, data: bytes) -> None:
            """Write every byte of ``data`` to conin, or raise.

            Disclosed boundary (finding C2, issue #193): this is a
            synchronous write on a blocking pipe and is deliberately not
            wired to the cancel event, so it stays outside the adapter's
            abort deadline exactly as before this slice.
            """
            handle = self._conin_write
            if handle is None:
                raise ConptyClosedError("the ConPTY session is closed")
            total = len(data)
            # Copied into a native buffer once; the loop then advances an
            # offset into it. Re-slicing the payload per partial write would
            # make a large write quadratic in its own size.
            buffer = ctypes.create_string_buffer(data, total)
            written = wintypes.DWORD(0)
            offset = 0
            while offset < total:
                if not _kernel32.WriteFile(
                    handle,
                    ctypes.byref(buffer, offset),
                    total - offset,
                    ctypes.byref(written),
                    None,
                ):
                    raise _last_error("WriteFile")
                if written.value == 0:
                    raise OSError("WriteFile made no progress on the conin pipe")
                offset += written.value

        def read_bytes(self) -> bytes:
            """Block until conout has bytes and return them undecoded.

            Raises :class:`_NativeEndOfStream` when the output pipe genuinely
            broke and :class:`_NativeReadCancelled` when ``cancel_io`` ended
            the read. ``ConptyChild`` maps both onto the binding's public
            exceptions; nothing here decides whether a failure is a close.
            """
            handle = self._conout_read
            read_event = self._read_event
            if handle is None or read_event is None:
                raise ConptyClosedError("the ConPTY session is closed")
            overlapped = _Overlapped()
            overlapped.hEvent = read_event
            _kernel32.ResetEvent(read_event)
            transferred = wintypes.DWORD(0)
            started = _kernel32.ReadFile(
                handle,
                self._buffer,
                _READ_BUFFER_BYTES,
                ctypes.byref(transferred),
                ctypes.byref(overlapped),
            )
            if not started:
                error = ctypes.get_last_error()
                if error != _ERROR_IO_PENDING:
                    raise self._read_failure(error)
                self._await_read(handle, overlapped)
                if not _kernel32.GetOverlappedResult(
                    handle, ctypes.byref(overlapped), ctypes.byref(transferred), False
                ):
                    raise self._read_failure(ctypes.get_last_error())
            count = int(transferred.value)
            if count == 0:
                # A completed zero-byte read on a byte-mode pipe means the
                # writer is gone; ConPTY never emits an empty write.
                raise _NativeEndOfStream(
                    "the native ConPTY output pipe reported end-of-stream"
                )
            # Slicing a ctypes character array already yields ``bytes``; the
            # reader is on the hot path for every frame the child emits, so
            # it makes exactly one copy. The stubs describe the slice as a
            # list, which is why this needs saying to the checker.
            return cast(bytes, self._buffer[:count])

        def _await_read(self, handle: int, overlapped: _Overlapped) -> None:
            """Wait for the pending read, a cancellation, or the child's exit.

            The child's exit is a wake reason because ConPTY keeps its own
            end of the output pipe open until the pseudoconsole is closed:
            without this, a read issued after the child exited would block
            forever instead of ever reaching end-of-stream. Closing the
            pseudoconsole makes the console host flush what it still holds
            and then drop the write end, so end-of-stream stays a real native
            signal and never a timeout.

            **Every exit but the successful one first ends the pending read.**
            The kernel owns ``overlapped`` and ``self._buffer`` until the
            operation completes, and ``overlapped`` is a frame local of
            :meth:`read_bytes`; returning while the read is still outstanding
            would let the kernel write a completion status into memory that
            has been freed, and later reads into a buffer under a stale one.
            """
            cancel_event = self._cancel_event
            read_event = self._read_event
            if cancel_event is None or read_event is None:
                # Deliberately does *not* cancel: reaching here means close
                # already unpublished the events, so it has closed or is
                # about to close these handle values. Cancelling a recycled
                # handle would reach unrelated I/O, and waiting on a closed
                # event returns at once without the read having drained —
                # the opposite of the guarantee cancelling is meant to give.
                raise ConptyClosedError("the ConPTY session is closed")
            process_handle = self._process_handle
            waited_out_child = process_handle is None
            while True:
                handles: list[int] = [read_event, cancel_event]
                if not waited_out_child and process_handle is not None:
                    handles.append(process_handle)
                array = (wintypes.HANDLE * len(handles))(*handles)
                index = int(
                    _kernel32.WaitForMultipleObjects(
                        len(handles), array, False, _INFINITE
                    )
                )
                if index == _WAIT_OBJECT_0:
                    return
                if index == _WAIT_OBJECT_0 + 1:
                    raise self._abandon_read(
                        handle,
                        overlapped,
                        _NativeReadCancelled(
                            "the in-flight native ConPTY read was cancelled"
                        ),
                    )
                if index == _WAIT_OBJECT_0 + 2:
                    # A signaled process handle stays signaled, so drop it
                    # from the wait set or the next pass would spin on it.
                    waited_out_child = True
                    self._release_pseudoconsole()
                    continue
                raise self._abandon_read(
                    handle, overlapped, _last_error("WaitForMultipleObjects")
                )

        def _abandon_read(
            self, handle: int, overlapped: _Overlapped, failure: BaseException
        ) -> BaseException:
            """Cancel the pending read and wait it out, then return ``failure``.

            The wait is deliberately blocking: it is what guarantees the
            kernel has finished with ``overlapped`` and the read buffer before
            this frame unwinds.
            """
            _kernel32.CancelIoEx(handle, ctypes.byref(overlapped))
            transferred = wintypes.DWORD(0)
            _kernel32.GetOverlappedResult(
                handle, ctypes.byref(overlapped), ctypes.byref(transferred), True
            )
            return failure

        def _read_failure(self, error: int) -> BaseException:
            if error == _ERROR_BROKEN_PIPE:
                return _NativeEndOfStream(
                    "the native ConPTY output pipe reported end-of-stream"
                )
            if error == _ERROR_OPERATION_ABORTED:
                return _NativeReadCancelled(
                    "the in-flight native ConPTY read was cancelled"
                )
            return OSError(f"ReadFile on the conout pipe failed: {error}")

        def _release_pseudoconsole(self) -> None:
            """Hand the pseudoconsole to a thread that closes it.

            ``ClosePseudoConsole`` waits for the console host to flush its
            pending output, which only drains while somebody reads — and the
            caller here *is* the reader, mid-read. Closing on a separate
            thread lets the read keep draining until the host exits and the
            write end drops, which is the end-of-stream signal this whole
            path exists to produce.

            The reader never blocks here: it only unpublishes the handle and
            starts the thread. Waiting for any in-flight resize to finish
            with it is that thread's job, not the reader's.
            """
            with self._lock:
                pseudoconsole = self._pseudoconsole
                if pseudoconsole is None or self._drain is not None:
                    return
                self._pseudoconsole = None
                self._drain = threading.Thread(
                    target=self._close_pseudoconsole_when_idle,
                    args=(pseudoconsole,),
                    name=f"termverify-conpty-drain-{self._pid}",
                    daemon=True,
                )
                self._drain.start()

        def _close_pseudoconsole_when_idle(self, pseudoconsole: int) -> None:
            """Close the pseudoconsole once no resize is using its handle."""
            with self._resize_lock:
                _close_pseudoconsole(pseudoconsole)

        def cancel_io(self) -> None:
            """Wake any in-flight read so ``close`` can proceed.

            The cancel event is never reset: it is only ever set while the
            session is being torn down, and a later read would have nothing
            left to observe.
            """
            cancel_event = self._cancel_event
            if cancel_event is not None:
                _kernel32.SetEvent(cancel_event)
            handle = self._conout_read
            if handle is not None:
                _kernel32.CancelIoEx(handle, None)

        def close(self) -> None:
            """Release every native handle this session owns, in a safe order.

            The conout read end goes first: with it gone the console host's
            pending writes fail immediately, so ``ClosePseudoConsole`` cannot
            block waiting for output nobody will read. Callers must ensure no
            read or write is in flight — ``ConptyChild.close`` cancels and
            waits them out before calling this.
            """
            with self._lock:
                if self._closed:
                    return
                self._closed = True
                pseudoconsole = self._pseudoconsole
                self._pseudoconsole = None
                drain = self._drain
                handles = [
                    self._conout_read,
                    self._conin_write,
                    self._process_handle,
                    self._thread_handle,
                    self._read_event,
                    self._cancel_event,
                ]
                self._conout_read = None
                self._conin_write = None
                self._process_handle = None
                self._thread_handle = None
                self._read_event = None
                self._cancel_event = None
            conout_read = handles[0]
            if conout_read is not None:
                _kernel32.CloseHandle(conout_read)
            if pseudoconsole is not None:
                self._close_pseudoconsole_when_idle(pseudoconsole)
            if drain is not None:
                drain.join(_PSEUDOCONSOLE_DRAIN_JOIN_SECONDS)
                # Recorded, not raised. This runs inside ``ConptyChild.close``'s
                # cleanup, where raising would replace whatever sent it there —
                # a child that would not die outranks a leaked handle — and
                # would skip the remaining teardown. The caller reads
                # :attr:`stalled` once the close has otherwise finished.
                self._stalled = drain.is_alive()
            for handle in handles[1:]:
                if handle is not None:
                    _kernel32.CloseHandle(handle)

        @property
        def stalled(self) -> bool:
            """Whether the pseudoconsole never finished closing.

            When true, its handle and the thread closing it are both still
            held: a close that reported success without saying so would be
            claiming a release it did not make.
            """
            return self._stalled

        def __del__(self) -> None:  # pragma: no cover - refcount backstop only
            if not getattr(self, "_constructed", False):
                # A part-built session never owned these handles; the code
                # constructing it still does, and closing them here would
                # make its own cleanup a double close.
                return
            with contextlib.suppress(Exception):
                self.close()

    def _open_session(
        argv: Sequence[str],
        *,
        rows: int,
        columns: int,
        env_overlay: Mapping[str, str] | None,
        cwd: str | None,
    ) -> _PseudoConsoleSession:
        """Create a pseudoconsole and start ``argv`` attached to it.

        The child is created ``CREATE_SUSPENDED`` (#235): the returned
        session's main thread is frozen, and the caller owns resuming it
        exactly once via :meth:`_PseudoConsoleSession.resume_main_thread` —
        after containment is established — or tearing the session down.
        Every handle created here is closed on any failure before the error
        escapes: a partially built session is never returned and never leaks.
        """
        if not _HAS_PSEUDOCONSOLE:
            raise ConptyUnsupportedError(
                "this Windows build exports no CreatePseudoConsole; ConPTY"
                " requires Windows 10 1809 or newer"
            )
        arguments = list(argv)
        command = shutil.which(arguments[0])
        if command is None:
            raise FileNotFoundError(
                f"the command was not found or was not executable: {arguments[0]}"
            )
        opened: list[int] = []
        pseudoconsole: int | None = None
        attributes: Any = None
        spawned: int | None = None
        try:
            conin_read = wintypes.HANDLE()
            conin_write = wintypes.HANDLE()
            if not _kernel32.CreatePipe(
                ctypes.byref(conin_read), ctypes.byref(conin_write), None, 0
            ):
                raise _last_error("CreatePipe")
            opened.extend((int(conin_read.value or 0), int(conin_write.value or 0)))
            conout_read, conout_write = _make_overlapped_conout_pipe()
            opened.extend((conout_read, conout_write))
            handle = wintypes.HANDLE()
            result = _kernel32.CreatePseudoConsole(
                _Coord(X=columns, Y=rows),
                conin_read,
                wintypes.HANDLE(conout_write),
                0,
                ctypes.byref(handle),
            )
            if result != 0:
                raise OSError(f"CreatePseudoConsole failed: {result:#010x}")
            pseudoconsole = int(handle.value or 0)
            # The pseudoconsole duplicated both of its own ends; dropping them
            # here is what lets this process observe end-of-stream later.
            for owned in (int(conin_read.value or 0), conout_write):
                _kernel32.CloseHandle(owned)
                opened.remove(owned)
            size = ctypes.c_size_t(0)
            _kernel32.InitializeProcThreadAttributeList(None, 1, 0, ctypes.byref(size))
            if ctypes.get_last_error() != _ERROR_INSUFFICIENT_BUFFER:
                raise _last_error("InitializeProcThreadAttributeList")
            attributes = (ctypes.c_ubyte * size.value)()
            if not _kernel32.InitializeProcThreadAttributeList(
                attributes, 1, 0, ctypes.byref(size)
            ):
                raise _last_error("InitializeProcThreadAttributeList")
            if not _kernel32.UpdateProcThreadAttribute(
                attributes,
                0,
                _PROC_THREAD_ATTRIBUTE_PSEUDOCONSOLE,
                ctypes.c_void_p(pseudoconsole),
                ctypes.sizeof(ctypes.c_void_p),
                None,
                None,
            ):
                raise _last_error("UpdateProcThreadAttribute")
            startup = _StartupInfoExW()
            startup.StartupInfo.cb = ctypes.sizeof(_StartupInfoExW)
            startup.lpAttributeList = ctypes.cast(attributes, ctypes.c_void_p)
            # Without STARTF_USESTDHANDLES the child is handed this process's
            # standard handles, and it uses them in preference to the console
            # it is attached to. When TermVerify itself runs with piped stdio
            # — every CI run, every test run — the child would then write its
            # output straight past the pseudoconsole and into TermVerify's own
            # stdout: attached to the right console, reporting to the wrong
            # place. Passing the flag with null handles suppresses that
            # inheritance, so the console supplies stdin, stdout, and stderr.
            # This is the failure the 2026-07-17 ctypes prototype hit and read
            # as "failed to attach the child"; the child was attached all
            # along.
            startup.StartupInfo.dwFlags = _STARTF_USESTDHANDLES
            startup.StartupInfo.hStdInput = None
            startup.StartupInfo.hStdOutput = None
            startup.StartupInfo.hStdError = None
            merged = dict(os.environ)
            if env_overlay is not None:
                merged.update(env_overlay)
            block = ctypes.create_unicode_buffer(
                "".join(f"{name}={value}\0" for name, value in merged.items()) + "\0"
            )
            # argv[0] is quoted into the command line like every other
            # argument, so a program path containing spaces starts the
            # program it names rather than a prefix of it.
            cmdline = ctypes.create_unicode_buffer(subprocess.list2cmdline(arguments))
            information = _ProcessInformation()
            if not _kernel32.CreateProcessW(
                command,
                cmdline,
                None,
                None,
                False,
                _EXTENDED_STARTUPINFO_PRESENT
                | _CREATE_UNICODE_ENVIRONMENT
                | _CREATE_SUSPENDED,
                block,
                cwd if cwd is not None else os.getcwd(),
                ctypes.byref(startup),
                ctypes.byref(information),
            ):
                raise OSError(
                    f"ConPTY spawn failed for {command}:"
                    f" CreateProcessW reported {ctypes.get_last_error()}"
                )
            # The child starts suspended (issue #235): the caller assigns it
            # to its containment job before resuming its main thread, so no
            # descendant can predate the membership. The thread handle is
            # the only resume path and stays owned until then. `spawned` is
            # captured first so the teardown below terminates the child on
            # any failure from here on (#235 review: the bookkeeping
            # statements must not form an unguarded window).
            spawned = int(information.hProcess or 0)
            process_handle = spawned
            thread_handle = int(information.hThread or 0)
            opened.extend((process_handle, thread_handle))
            read_event = _kernel32.CreateEventW(None, True, False, None)
            if not read_event:
                raise _last_error("CreateEventW")
            opened.append(int(read_event))
            cancel_event = _kernel32.CreateEventW(None, True, False, None)
            if not cancel_event:
                raise _last_error("CreateEventW")
            opened.append(int(cancel_event))
            session = _PseudoConsoleSession(
                pseudoconsole=pseudoconsole,
                conout_read=conout_read,
                conin_write=int(conin_write.value or 0),
                process_handle=process_handle,
                thread_handle=thread_handle,
                pid=int(information.dwProcessId),
                read_event=int(read_event),
                cancel_event=int(cancel_event),
            )
            # Ownership has moved to the session; the failure path below must
            # not close what it now owns.
            opened.clear()
            pseudoconsole = None
            spawned = None
        except BaseException:
            if spawned is not None:
                # A suspended child cannot die of handle or pseudoconsole
                # closes — terminate it or the failed spawn leaks a frozen
                # orphan (issue #235).
                _kernel32.TerminateProcess(spawned, FORCED_TERMINATION_EXIT_CODE)
            for owned in opened:
                _kernel32.CloseHandle(owned)
            if pseudoconsole is not None:
                _close_pseudoconsole(pseudoconsole)
            raise
        finally:
            if attributes is not None:
                _kernel32.DeleteProcThreadAttributeList(attributes)
        return session

else:

    def _unsupported() -> ConptyUnsupportedError:
        return ConptyUnsupportedError(
            "the ConPTY binding requires Windows; this host has no ConPTY"
        )

    def _create_containment_job() -> int:
        raise _unsupported()

    def _open_containment_handle(pid: int) -> int:
        raise _unsupported()

    def _assign_to_job(job: int, process_handle: int) -> None:
        raise _unsupported()

    def _resume_main_thread(thread_handle: int) -> None:
        raise _unsupported()

    def _terminate_job(job: int, exit_code: int) -> None:
        raise _unsupported()

    def _terminate_process(process_handle: int, exit_code: int) -> None:
        raise _unsupported()

    def _wait_for_handle(handle: int, timeout_ms: int) -> bool:
        raise _unsupported()

    def _close_handle(handle: int) -> None:
        raise _unsupported()

    def _open_session(
        argv: Sequence[str],
        *,
        rows: int,
        columns: int,
        env_overlay: Mapping[str, str] | None,
        cwd: str | None,
    ) -> Any:
        raise _unsupported()

    class _PseudoConsoleSession:
        """Placeholder so the name resolves off Windows; never instantiated.

        The Windows evidence tests assert against this class rather than
        against a class *name*, which is what keeps that assertion able to
        fail when the native session is renamed. Type checking runs on both
        platforms, so the name has to exist on both.
        """

        def __init__(self) -> None:
            raise _unsupported()

    _HAS_PSEUDOCONSOLE = False


class ConptyChild:
    """Thin ownership wrapper around one native ConPTY pseudoconsole child."""

    def __init__(
        self, pty: Any, pid: int, job: int | None, process_handle: int | None
    ) -> None:
        self._pty: Any | None = pty
        self._pid = pid
        self._job: int | None = job
        self._process_handle: int | None = process_handle
        self._exit_status: int | None = None
        self._lock = threading.Lock()
        self._pending_io = 0
        # One decoder per child, fed every native chunk in stream order, so a
        # read that lands between two bytes of one codepoint heals on the next
        # read instead of losing the character. ``replace`` therefore only
        # ever fires on bytes the child genuinely emitted as invalid UTF-8.
        self._decoder = codecs.getincrementaldecoder("utf-8")("replace")

    @classmethod
    def spawn(
        cls,
        argv: Sequence[str],
        *,
        rows: int,
        columns: int,
        env_overlay: Mapping[str, str] | None = None,
        cwd: str | None = None,
    ) -> ConptyChild:
        """Spawn a contained child on a ConPTY pseudoconsole.

        The child is created suspended and assigned to a fresh kill-on-close
        job object before its main thread resumes, so no descendant can
        predate the job membership (issue #235). If containment cannot be
        established, the child is terminated — never resumed — and the spawn
        fails closed: no uncontained session is ever handed out.

        ``env_overlay`` variables are overlaid onto this process's ambient
        environment at spawn time; an overlay variable always wins over an
        ambient variable of the same name. Disclosed: the child inherits the
        ambient environment underneath the overlay — ambient contents are
        not evidence and are not recorded, only the overlay is. ``cwd``
        selects the child's working directory; without it, the child starts
        in this process's current directory.

        Before any session is created the requested geometry is verified:
        predictable ``COORD`` wrap misfires are refused outright, and every
        other geometry must be proven adopted exactly by the geometry probe
        (issue #228) — a spawn that cannot run at the requested size raises
        :class:`ConptyGeometryMismatchError` instead of handing out a
        session at a size the receipt never recorded.
        """
        if os.name != "nt":
            raise ConptyUnsupportedError(
                "the ConPTY binding requires Windows; this host has no ConPTY"
            )
        _verify_geometry(rows, columns)
        return cls._spawn_contained(
            argv, rows=rows, columns=columns, env_overlay=env_overlay, cwd=cwd
        )

    @classmethod
    def _spawn_contained(
        cls,
        argv: Sequence[str],
        *,
        rows: int,
        columns: int,
        env_overlay: Mapping[str, str] | None = None,
        cwd: str | None = None,
    ) -> ConptyChild:
        """The spawn's mechanical half, with the geometry already verified.

        Split from :meth:`spawn` so the geometry probe can spawn its own
        child through the identical suspended-then-contained path without
        re-entering the verification it exists to perform.
        """
        pty = _open_session(
            argv, rows=rows, columns=columns, env_overlay=env_overlay, cwd=cwd
        )
        # The child exists — suspended — from here on. Every statement
        # after this point, including the pid bookkeeping itself, runs
        # inside the guard: an exception anywhere in the window must reach
        # the terminate-and-release teardown (#235 review round 3).
        pid: int | None = None
        job: int | None = None
        process_handle: int | None = None
        try:
            pid = int(pty.pid)
            job = _create_containment_job()
            process_handle = _open_containment_handle(pid)
            _assign_to_job(job, process_handle)
            pty.resume_main_thread()
        except BaseException as error:
            # Terminate unconditionally, through the handle the session
            # owns: the child is suspended, so it cannot die of the handle
            # and pseudoconsole closes below, and on the paths where the
            # job or the containment handle could not be established it is
            # in no job — anything less leaks a frozen orphan. The teardown
            # runs for BaseException, not just OSError: a KeyboardInterrupt
            # in this window must not leak the child either (#235 review).
            pty.terminate_child(FORCED_TERMINATION_EXIT_CODE)
            if process_handle is not None:
                _close_handle(process_handle)
            if job is not None:
                _close_handle(job)
            # Release the session explicitly — no read or write can be in
            # flight yet — and drop the reference so the raised exception's
            # traceback cannot pin what is left of it.
            pty.close()
            del pty
            if isinstance(error, OSError):
                raise OSError(
                    f"failed to contain ConPTY child {pid} in a job object"
                ) from error
            raise
        return cls(pty, pid, job, process_handle)

    @property
    def pid(self) -> int:
        """Return the child's OS process id."""
        return self._pid

    def read(self) -> str:
        """Block until pseudoconsole output is available and return it.

        Raises :class:`ConptyEndOfStreamError` when the binding is still open
        and the native output pipe reports end-of-stream after the child has
        exited; the native exit status has been captured by then. Raises
        :class:`ConptyClosedError` when the binding is closed before or while
        the read is in flight, and :class:`ConptyConcurrentIOError` when
        another read or write is already in flight. Any other native read
        failure — the binding open, the child alive — is re-raised unchanged.

        The native layer hands over raw bytes and this method owns the
        decode, running one incremental UTF-8 decoder across every chunk of
        the child's lifetime (finding R7). A native read that lands between
        two bytes of one codepoint therefore heals on the following read
        rather than losing the character to a replacement. At a genuine
        end-of-stream any bytes the decoder still holds are a sequence the
        child truly left unfinished: they are flushed as replacement text on
        this call, and the end-of-stream is raised by the next one.
        """
        pty = self._begin_io()
        try:
            chunk = pty.read_bytes()
        except Exception as error:
            replacement = self._classify_io_failure(pty, error, end_of_stream=True)
            # Drop the frame-local native reference before raising: the
            # exception's traceback keeps this frame alive, and a pinned
            # native object would defer the handle release indefinitely.
            del pty
            if replacement is None:
                raise
            if type(replacement) is ConptyEndOfStreamError:
                truncated = self._decoder.decode(b"", final=True)
                if truncated:
                    return truncated
            raise replacement from error
        finally:
            self._end_io()
        return self._decoder.decode(chunk)

    def write(self, text: str) -> None:
        """Write ``text`` to the child without claiming a byte-count receipt.

        Raises :class:`ConptyClosedError` when the binding is closed before
        or while the write is in flight, and
        :class:`ConptyConcurrentIOError` when another read or write is
        already in flight; other native write failures are re-raised
        unchanged.
        """
        pty = self._begin_io()
        try:
            pty.write(text.encode("utf-8"))
        except Exception as error:
            replacement = self._classify_io_failure(pty, error, end_of_stream=False)
            del pty
            if replacement is None:
                raise
            raise replacement from error
        finally:
            self._end_io()

    def resize(self, *, rows: int, columns: int) -> None:
        """Resize the pseudoconsole explicitly."""
        self._require_open().set_size(columns, rows)

    def is_alive(self) -> bool:
        """Report whether the child process is still alive.

        A closed binding reports ``False``: it no longer owns a live native
        session through which liveness could be observed.
        """
        pty = self._pty
        return False if pty is None else bool(pty.isalive())

    def close(self, *, force: bool) -> None:
        """Release native ownership; with ``force``, terminate the child's tree.

        The forced path terminates the entire job — the child and every
        descendant — atomically with ``TerminateJobObject`` (uniform exit
        code :data:`FORCED_TERMINATION_EXIT_CODE`), waits on the child's real
        process handle, and captures the native exit record before releasing
        the handles.

        A release-only close (``force=False``) of a live child records no
        exit status — the binding never observed a native exit record — while
        the pseudoconsole handle release itself makes ConPTY terminate the
        attached client, which callers can observe at the OS level. The close
        waits for that termination on the child's process handle and then
        closes the job handle, whose kill-on-close limit sweeps any remaining
        descendants; the no-kill path therefore cannot leak a process tree
        either.

        Close first unpublishes the native object so no new I/O can start,
        then cancels pending native I/O until every in-flight read and write
        has returned. Interrupted I/O surfaces :class:`ConptyClosedError` with
        its frame-local native reference dropped, so a held exception cannot
        pin the native object and the handles are released as soon as the
        last frame still holding it unwinds.
        """
        with self._lock:
            pty = self._pty
            if pty is None:
                return
            self._pty = None
            job = self._job
            process_handle = self._process_handle
            self._job = None
            self._process_handle = None
        child_exited = True
        stalled = False
        try:
            try:
                if force and pty.isalive():
                    if job is None:
                        # Defensive: unreachable on the only construction
                        # path; failing fast beats waiting on a live child.
                        raise OSError("no containment job to terminate")
                    _terminate_job(job, FORCED_TERMINATION_EXIT_CODE)
                    if process_handle is not None and not _wait_for_handle(
                        process_handle, _CHILD_EXIT_WAIT_MS
                    ):
                        raise OSError(
                            f"child process {self._pid} did not terminate on"
                            " forced close"
                        )
                if not pty.isalive():
                    self._capture_exit_status(pty)
            finally:
                try:
                    self._cancel_pending_io(pty)
                except BaseException:
                    # The cancel loop gave up, so a native call may still be
                    # inside the session; closing its handles underneath one
                    # is the crash this binding exists to avoid. Drop the
                    # reference instead and let the last in-flight frame's
                    # release run the session's destructor.
                    del pty
                    raise
                else:
                    try:
                        # No read or write is in flight any more, so the
                        # handles can be released here and now rather than
                        # whenever the last traceback holding them unwinds.
                        pty.close()
                        stalled = pty.stalled
                    finally:
                        del pty
            if not force and process_handle is not None:
                child_exited = _wait_for_handle(process_handle, _CHILD_EXIT_WAIT_MS)
        finally:
            if job is not None:
                # Kill-on-close sweeps every remaining job member, so even a
                # failed graceful path cannot leak the tree.
                _close_handle(job)
            if not child_exited and process_handle is not None:
                child_exited = _wait_for_handle(process_handle, _CHILD_EXIT_WAIT_MS)
            if process_handle is not None:
                _close_handle(process_handle)
        if not child_exited:
            raise OSError(
                f"child process {self._pid} did not terminate after handle release"
            )
        if stalled:
            # Reported only once everything else succeeded, so it can never
            # displace a failure that matters more — a child that would not
            # die, or a teardown step this close still owed.
            raise OSError(
                f"the pseudoconsole for child {self._pid} did not close within"
                f" {_PSEUDOCONSOLE_DRAIN_JOIN_SECONDS:.0f}s; its handle and the"
                " thread closing it are still held"
            )

    def _cancel_pending_io(self, pty: Any) -> None:
        """Cancel native I/O until no read or write frame can block on ``pty``."""
        deadline = time.monotonic() + _READ_CANCEL_TIMEOUT_SECONDS
        while True:
            with self._lock:
                pending = self._pending_io
            if pending == 0:
                return
            with contextlib.suppress(Exception):
                pty.cancel_io()
            if time.monotonic() >= deadline:
                raise OSError("pending native ConPTY I/O did not cancel during close")
            time.sleep(_READ_CANCEL_RETRY_SECONDS)

    @property
    def exit_status(self) -> int | None:
        """Return the natively observed exit status, else ``None``."""
        pty = self._pty
        if self._exit_status is None and pty is not None:
            self._capture_exit_status(pty)
        return self._exit_status

    def _require_open(self) -> Any:
        pty = self._pty
        if pty is None:
            raise ConptyClosedError("the ConPTY binding is closed")
        return pty

    def _begin_io(self) -> Any:
        """Atomically take the native object and count the in-flight call.

        At most one read or write may be in flight: overlapped native calls
        on one pseudoconsole can crash the interpreter, and blocking a write
        behind an indefinitely blocked read would deadlock, so overlap fails
        fast as :class:`ConptyConcurrentIOError`.
        """
        with self._lock:
            pty = self._pty
            if pty is None:
                raise ConptyClosedError("the ConPTY binding is closed")
            if self._pending_io > 0:
                raise ConptyConcurrentIOError(
                    "another native read or write is already in flight; the"
                    " binding is single-flight by contract"
                )
            self._pending_io += 1
            return pty

    def _end_io(self) -> None:
        with self._lock:
            self._pending_io -= 1

    def _classify_io_failure(
        self, pty: Any, failure: BaseException, *, end_of_stream: bool
    ) -> Exception | None:
        """Map a native I/O failure to the binding's honest exception, if any.

        A failure observed after ``close`` unpublished the native object is
        the close's own cancellation (or indistinguishable from it) and
        becomes :class:`ConptyClosedError` — never an end-of-stream claim,
        because close may have abandoned buffered output.

        Otherwise the *native* signal decides.
        :class:`ConptyEndOfStreamError` carries a guarantee — that every byte
        the pseudoconsole emitted has already been returned — which only the
        broken output pipe actually establishes. Inferring it from a dead
        child instead would attach that guarantee to any read failure that
        happened to arrive after the child exited. Anything else is the
        caller's to see unchanged (``None``).
        """
        if not pty.isalive():
            self._capture_exit_status(pty)
        if self._pty is None:
            return ConptyClosedError("the ConPTY binding was closed during native I/O")
        if end_of_stream and type(failure) is _NativeEndOfStream:
            return ConptyEndOfStreamError(
                "the native ConPTY output pipe reported end-of-stream"
            )
        return None

    def _capture_exit_status(self, pty: Any) -> None:
        status = pty.get_exitstatus()
        if status is not None:
            self._exit_status = int(status)
