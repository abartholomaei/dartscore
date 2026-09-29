"""Diagnostics: cameras, detection and the load of the process, without SSH."""

import ctypes
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request

from dartscore.services.detection import DetectionService
from dartscore.vision.camera import CameraManager

router = APIRouter(prefix="/api", tags=["diagnostics"])

_cpu_lock = threading.Lock()
_last_cpu: tuple[float, float] | None = None  # (process cpu seconds, wall time)


def _cpu_percent() -> float | None:
    """CPU use of this process since the previous call (100 = one full core)."""
    global _last_cpu
    times = os.times()
    now = (times.user + times.system, time.monotonic())
    with _cpu_lock:
        previous, _last_cpu = _last_cpu, now
    if previous is None or now[1] - previous[1] <= 0:
        return None
    return round((now[0] - previous[0]) / (now[1] - previous[1]) * 100, 1)


def _memory_mb() -> float:
    if sys.platform == "win32":
        return round(_windows_working_set() / 1024**2, 1)
    statm = Path("/proc/self/statm")
    if statm.is_file():  # Linux: current resident size
        pages = int(statm.read_text().split()[1])
        return round(pages * os.sysconf("SC_PAGE_SIZE") / 1024**2, 1)
    import resource  # Unix only

    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss  # macOS: bytes, peak only
    return round(peak / 1024**2, 1)


def _windows_working_set() -> int:
    """Current working set of this process in bytes (GetProcessMemoryInfo)."""

    class Counters(ctypes.Structure):
        _fields_ = [
            ("cb", ctypes.c_ulong),
            ("PageFaultCount", ctypes.c_ulong),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    windll = ctypes.windll  # type: ignore[attr-defined]
    process = windll.kernel32.GetCurrentProcess()
    ok = windll.psapi.GetProcessMemoryInfo(process, ctypes.byref(counters), counters.cb)
    return int(counters.WorkingSetSize) if ok else 0


@router.get("/diagnostics")
def diagnostics(request: Request) -> dict[str, Any]:
    manager: CameraManager = request.app.state.cameras
    detection: DetectionService = request.app.state.detection
    try:
        load = [round(x, 2) for x in os.getloadavg()]
    except (OSError, AttributeError):  # not available on Windows
        load = []
    return {
        "process": {
            "cpu_percent": _cpu_percent(),
            "memory_mb": _memory_mb(),
            "threads": threading.active_count(),
            "cpus": os.cpu_count(),
            "load": load,
        },
        "cameras": [
            {
                "id": s.id,
                "state": s.state.value,
                "fps": round(s.fps, 1),
                "frames": s.frames,
                "dropped": s.dropped,
                "last_error": s.last_error,
            }
            for s in (w.status() for w in manager.workers())
        ],
        "detection": detection.status() | {"step_ms": round(detection.step_ms, 1)},
        "recent_darts": list(detection.recent_darts),
    }
