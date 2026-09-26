from pathlib import Path

from dartscore.vision.devices import VideoMode, list_linux_devices, parse_v4l2_formats

V4L2_OUTPUT = """\
ioctl: VIDIOC_ENUM_FMT
\tType: Video Capture

\t[0]: 'MJPG' (Motion-JPEG, compressed)
\t\tSize: Discrete 1280x720
\t\t\tInterval: Discrete 0.033s (30.000 fps)
\t\t\tInterval: Discrete 0.067s (15.000 fps)
\t\tSize: Discrete 640x480
\t\t\tInterval: Discrete 0.033s (30.000 fps)
\t[1]: 'YUYV' (YUYV 4:2:2)
\t\tSize: Discrete 1280x720
\t\t\tInterval: Discrete 0.100s (10.000 fps)
"""


def test_parse_v4l2_formats() -> None:
    formats = parse_v4l2_formats(V4L2_OUTPUT)
    assert formats == {
        "MJPG": [VideoMode(1280, 720, (30.0, 15.0)), VideoMode(640, 480, (30.0,))],
        "YUYV": [VideoMode(1280, 720, (10.0,))],
    }
    assert str(formats["MJPG"][0]) == "1280x720@30/15"


def _fake_node(sysfs: Path, name: str, index: int, label: str) -> None:
    node = sysfs / name
    node.mkdir(parents=True)
    (node / "index").write_text(f"{index}\n")
    (node / "name").write_text(f"{label}\n")


def test_list_linux_devices_skips_metadata_nodes_and_maps_links(tmp_path: Path) -> None:
    sysfs, dev, v4l = tmp_path / "sys", tmp_path / "dev", tmp_path / "dev" / "v4l"
    for n in range(4):
        (dev / f"video{n}").parent.mkdir(parents=True, exist_ok=True)
        (dev / f"video{n}").touch()
    _fake_node(sysfs, "video0", 0, "USB Camera A")
    _fake_node(sysfs, "video1", 1, "USB Camera A")
    _fake_node(sysfs, "video2", 0, "USB Camera B")
    _fake_node(sysfs, "video3", 1, "USB Camera B")
    (v4l / "by-path").mkdir(parents=True)
    (v4l / "by-path" / "pci-0000:00:14.0-usb-0:1:1.0-video-index0").symlink_to(dev / "video0")
    (v4l / "by-path" / "pci-0000:00:14.0-usb-0:2:1.0-video-index0").symlink_to(dev / "video2")

    devices = list_linux_devices(sysfs, v4l, dev, query_formats=False)

    assert [d.device for d in devices] == [str(dev / "video0"), str(dev / "video2")]
    assert devices[0].name == "USB Camera A"
    assert devices[1].by_path[0].endswith("usb-0:2:1.0-video-index0")
    assert devices[0].by_id == []
