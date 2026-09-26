"""Command-line entry point: start the server, list, test and calibrate cameras."""

import argparse
import sys
import time
from pathlib import Path

import cv2
import structlog
import uvicorn

from dartscore import __version__
from dartscore.api import create_app
from dartscore.config import CameraConfig, Settings, load_settings
from dartscore.log import configure_logging
from dartscore.vision.camera import CameraManager, CameraWorker
from dartscore.vision.devices import list_devices
from dartscore.vision.intrinsics import (
    ChessboardCollector,
    Undistorter,
    calibrate,
    lens_file,
    save_lens,
)

log = structlog.get_logger(__name__)


def cmd_serve(settings: Settings, _args: argparse.Namespace) -> None:
    log.info(
        "starting",
        version=__version__,
        host=settings.server.host,
        port=settings.server.port,
        cameras=len(settings.cameras),
    )
    uvicorn.run(
        create_app(settings),
        host=settings.server.host,
        port=settings.server.port,
        log_config=None,
        # open MJPEG streams would otherwise block shutdown indefinitely
        timeout_graceful_shutdown=3,
    )


def cmd_devices(_settings: Settings, _args: argparse.Namespace) -> None:
    found = list_devices()
    if not found:
        print("No cameras found.")
        return
    for d in found:
        print(f"{d.device}  {d.name}")
        for link in d.by_path:
            print(f"    by-path: {link}")
        for link in d.by_id:
            print(f"    by-id:   {link}")
        for fourcc, modes in d.formats.items():
            print(f"    {fourcc}: {', '.join(str(m) for m in modes)}")
    print(
        "\nTip: use the by-path paths in config.toml - they stay the same as long as "
        "each camera stays in the same USB port."
    )


def cmd_bench(settings: Settings, args: argparse.Namespace) -> None:
    """Read all cameras at once and measure the actual frame rate (USB bandwidth test)."""
    if not settings.cameras:
        sys.exit("No cameras in the configuration.")
    manager = CameraManager(settings.cameras)
    manager.start()
    print(f"Reading {len(settings.cameras)} cameras at once for {args.seconds} s ...")
    start_frames = {}
    statuses = []
    try:
        time.sleep(2)  # settle (exposure, first frames)
        start_frames = {w.id: w.status().frames for w in manager.workers()}
        time.sleep(args.seconds)
        statuses = [w.status() for w in manager.workers()]
    finally:
        manager.stop()

    ok = True
    header = f"{'Camera':<10}{'Status':<14}{'Format':<18}{'Target':>9}{'Actual':>9}"
    print(f"\n{header}{'Dropped':>10}")
    for worker, st in zip(manager.workers(), statuses, strict=True):
        cfg = worker.config
        measured = (st.frames - start_frames.get(st.id, 0)) / args.seconds
        fmt = f"{st.info.width}x{st.info.height} {st.info.fourcc}" if st.info else "-"
        print(
            f"{st.id:<10}{st.state.value:<14}{fmt:<18}{cfg.fps:>9}{measured:>9.1f}{st.dropped:>10}"
        )
        if st.last_error:
            print(f"    Error: {st.last_error}")
        if measured < 0.9 * cfg.fps:
            ok = False
    if not ok:
        print(
            "\nAt least one camera misses the target frame rate. Possible causes: "
            "format is not MJPG (see `dartscore devices`), several cameras on one "
            "USB controller (`lsusb -t`), exposure time too long in low light."
        )


def _parse_pattern(text: str) -> tuple[int, int]:
    cols, rows = text.lower().split("x")
    return int(cols), int(rows)


def cmd_calibrate_lens(settings: Settings, args: argparse.Namespace) -> None:
    cam = next((c for c in settings.cameras if c.id == args.camera), None)
    if cam is None:
        sys.exit(f"Camera {args.camera!r} not in the configuration.")
    pattern = _parse_pattern(args.pattern)
    collector = ChessboardCollector(pattern)
    out_dir = lens_file(settings.calibration_dir, cam.id).parent
    image_dir = out_dir / "lens_images"
    image_dir.mkdir(parents=True, exist_ok=True)

    if args.images:
        _collect_from_files(collector, Path(args.images))
    else:
        _collect_live(collector, cam, args.frames, image_dir)

    if collector.image_size is None:
        sys.exit("No chessboard detected.")
    result = calibrate(collector.detections, collector.image_size, pattern, args.square_mm)
    path = save_lens(result, settings.calibration_dir, cam.id)
    print(f"\nCalibration saved: {path}")
    print(f"Reprojection error: {result.rms_error:.3f} px ", end="")
    if result.rms_error < 0.5:
        print("(very good)")
    elif result.rms_error < 1.0:
        print("(acceptable)")
    else:
        print("(too high - keep the chessboard flat, cover more of the edges, recalibrate)")

    sample = next(iter(sorted(image_dir.glob("*.png"))), None)
    image = cv2.imread(str(sample)) if sample is not None else None
    if image is not None:
        preview = Undistorter(result).undistort(image)
        cv2.imwrite(str(out_dir / "lens_preview.png"), preview)
        print(f"Undistorted preview: {out_dir / 'lens_preview.png'}")


def _collect_from_files(collector: ChessboardCollector, folder: Path) -> None:
    files = sorted(p for p in folder.iterdir() if p.suffix.lower() in {".png", ".jpg", ".jpeg"})
    for path in files:
        image = cv2.imread(str(path))
        if image is not None and collector.offer(image):
            print(f"  OK {path.name}")
    print(f"{len(collector.detections)} of {len(files)} images usable.")


def _collect_live(
    collector: ChessboardCollector, cam: CameraConfig, target: int, image_dir: Path
) -> None:
    worker = CameraWorker(cam)
    worker.start()
    print(
        f"Hold the chessboard ({collector.pattern[0]}x{collector.pattern[1]} inner corners) in "
        f"front of camera {cam.id} and move it slowly: center, all edges and corners, slightly "
        f"tilted.\nNeeded: {target} captures. Press Ctrl+C to abort."
    )
    seq = 0
    try:
        while len(collector.detections) < target:
            frame = worker.wait_for_frame(seq, 2.0)
            if frame is None:
                status = worker.status()
                print(f"  waiting for camera ... ({status.state.value} {status.last_error or ''})")
                continue
            seq = frame.seq
            if collector.offer(frame.image):
                n = len(collector.detections)
                cv2.imwrite(str(image_dir / f"{n:02d}.png"), frame.image)
                print(f"  OK capture {n}/{target}")
            time.sleep(0.2)
    except KeyboardInterrupt:
        print(f"\nAborted, {len(collector.detections)} captures collected.")
    finally:
        worker.stop()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dartscore", description=__doc__)
    parser.add_argument("-c", "--config", type=Path, help="path to config.toml")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("serve", help="start the server (default)")
    sub.add_parser("devices", help="show connected cameras and formats")

    bench = sub.add_parser("bench", help="read all cameras at once and measure fps")
    bench.add_argument("--seconds", type=int, default=10)

    lens = sub.add_parser("calibrate-lens", help="calibrate lens distortion with a chessboard")
    lens.add_argument("--camera", required=True, help="camera ID from the configuration")
    lens.add_argument("--pattern", default="9x6", help="inner corners, columns x rows")
    lens.add_argument("--square-mm", type=float, default=25.0, help="side length of one square")
    lens.add_argument("--frames", type=int, default=20, help="number of captures")
    lens.add_argument("--images", help="instead of live: folder with existing captures")
    return parser


COMMANDS = {
    None: cmd_serve,
    "serve": cmd_serve,
    "devices": cmd_devices,
    "bench": cmd_bench,
    "calibrate-lens": cmd_calibrate_lens,
}


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    settings = load_settings(args.config)
    configure_logging(settings.logging)
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    COMMANDS[args.command](settings, args)
