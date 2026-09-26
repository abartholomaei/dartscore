"""Detects connected cameras and their formats.

On Linux via sysfs and /dev/v4l (stable paths), otherwise by probing OpenCV indices.
"""

import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

import cv2


@dataclass(frozen=True)
class VideoMode:
    width: int
    height: int
    fps: tuple[float, ...]

    def __str__(self) -> str:
        rates = "/".join(f"{f:g}" for f in self.fps)
        return f"{self.width}x{self.height}@{rates}"


@dataclass
class VideoDevice:
    # path to open (/dev/videoN) or OpenCV index as a string
    device: str
    name: str
    # stable alternatives: by-id (serial number) and by-path (USB port)
    by_id: list[str] = field(default_factory=list)
    by_path: list[str] = field(default_factory=list)
    formats: dict[str, list[VideoMode]] = field(default_factory=dict)


_FORMAT_RE = re.compile(r"\[\d+\]: '(\w+)'")
_SIZE_RE = re.compile(r"Size: Discrete (\d+)x(\d+)")
_FPS_RE = re.compile(r"\(([\d.]+) fps\)")


def parse_v4l2_formats(output: str) -> dict[str, list[VideoMode]]:
    """Parse the output of ``v4l2-ctl --list-formats-ext``."""
    formats: dict[str, list[VideoMode]] = {}
    fourcc: str | None = None
    size: tuple[int, int] | None = None
    rates: list[float] = []

    def flush() -> None:
        if fourcc is not None and size is not None:
            formats[fourcc].append(VideoMode(size[0], size[1], tuple(rates)))

    for line in output.splitlines():
        if m := _FORMAT_RE.search(line):
            flush()
            fourcc, size, rates = m.group(1), None, []
            formats.setdefault(fourcc, [])
        elif m := _SIZE_RE.search(line):
            flush()
            size, rates = (int(m.group(1)), int(m.group(2))), []
        elif (m := _FPS_RE.search(line)) and size is not None:
            rates.append(float(m.group(1)))
    flush()
    return formats


def _query_formats(device: str) -> dict[str, list[VideoMode]]:
    exe = shutil.which("v4l2-ctl")
    if exe is None:
        return {}
    result = subprocess.run(
        [exe, "-d", device, "--list-formats-ext"],
        capture_output=True,
        text=True,
        check=False,
        timeout=5,
    )
    return parse_v4l2_formats(result.stdout) if result.returncode == 0 else {}


def _stable_links(link_dir: Path) -> dict[str, list[str]]:
    """Map /dev/videoN to its stable symlinks in /dev/v4l/by-id or by-path."""
    links: dict[str, list[str]] = {}
    if link_dir.is_dir():
        for link in sorted(link_dir.iterdir()):
            links.setdefault(link.resolve().name, []).append(str(link))
    return links


def list_linux_devices(
    sysfs: Path = Path("/sys/class/video4linux"),
    v4l_dir: Path = Path("/dev/v4l"),
    dev_dir: Path = Path("/dev"),
    query_formats: bool = True,
) -> list[VideoDevice]:
    by_id = _stable_links(v4l_dir / "by-id")
    by_path = _stable_links(v4l_dir / "by-path")
    devices = []
    for node in sorted(sysfs.glob("video*"), key=lambda p: int(p.name.removeprefix("video"))):
        # UVC cameras create two nodes each; index 0 delivers frames, 1 only metadata
        index_file = node / "index"
        if index_file.exists() and index_file.read_text().strip() != "0":
            continue
        name_file = node / "name"
        name = name_file.read_text().strip() if name_file.exists() else node.name
        device = str(dev_dir / node.name)
        devices.append(
            VideoDevice(
                device=device,
                name=name,
                by_id=by_id.get(node.name, []),
                by_path=by_path.get(node.name, []),
                formats=_query_formats(device) if query_formats else {},
            )
        )
    return devices


def probe_opencv_indices(max_index: int = 6) -> list[VideoDevice]:
    """Fallback for macOS/Windows: open indices 0..max_index one by one."""
    devices = []
    for index in range(max_index):
        cap = cv2.VideoCapture(index)
        try:
            if cap.isOpened():
                mode = VideoMode(
                    int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                    int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
                    (cap.get(cv2.CAP_PROP_FPS),),
                )
                devices.append(
                    VideoDevice(device=str(index), name=f"Camera {index}", formats={"?": [mode]})
                )
        finally:
            cap.release()
    return devices


def list_devices() -> list[VideoDevice]:
    if sys.platform.startswith("linux"):
        return list_linux_devices()
    return probe_opencv_indices()
