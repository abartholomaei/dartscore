"""Kommandozeilen-Einstieg: Server starten, Kameras auflisten, testen und kalibrieren."""

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
    )


def cmd_devices(_settings: Settings, _args: argparse.Namespace) -> None:
    found = list_devices()
    if not found:
        print("Keine Kameras gefunden.")
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
        "\nTipp: In der config.toml die by-path-Pfade verwenden – sie bleiben gleich, solange "
        "jede Kamera im selben USB-Anschluss steckt."
    )


def cmd_bench(settings: Settings, args: argparse.Namespace) -> None:
    """Liest alle Kameras gleichzeitig und misst die echte Bildrate (USB-Bandbreitentest)."""
    if not settings.cameras:
        sys.exit("Keine Kameras in der Konfiguration.")
    manager = CameraManager(settings.cameras)
    manager.start()
    print(f"Lese {len(settings.cameras)} Kameras gleichzeitig für {args.seconds} s …")
    start_frames = {}
    statuses = []
    try:
        time.sleep(2)  # Einschwingen (Belichtung, erste Bilder)
        start_frames = {w.id: w.status().frames for w in manager.workers()}
        time.sleep(args.seconds)
        statuses = [w.status() for w in manager.workers()]
    finally:
        manager.stop()

    ok = True
    header = f"{'Kamera':<10}{'Status':<14}{'Format':<18}{'Ziel-fps':>9}{'Ist-fps':>9}"
    print(f"\n{header}{'verloren':>10}")
    for worker, st in zip(manager.workers(), statuses, strict=True):
        cfg = worker.config
        measured = (st.frames - start_frames.get(st.id, 0)) / args.seconds
        fmt = f"{st.info.width}x{st.info.height} {st.info.fourcc}" if st.info else "-"
        print(
            f"{st.id:<10}{st.state.value:<14}{fmt:<18}{cfg.fps:>9}{measured:>9.1f}{st.dropped:>10}"
        )
        if st.last_error:
            print(f"    Fehler: {st.last_error}")
        if measured < 0.9 * cfg.fps:
            ok = False
    if not ok:
        print(
            "\nMindestens eine Kamera erreicht die Ziel-Bildrate nicht. Mögliche Ursachen: "
            "Format nicht MJPG (siehe `dartscore devices`), mehrere Kameras an einem "
            "USB-Controller (`lsusb -t`), zu lange Belichtungszeit bei wenig Licht."
        )


def _parse_pattern(text: str) -> tuple[int, int]:
    cols, rows = text.lower().split("x")
    return int(cols), int(rows)


def cmd_calibrate_lens(settings: Settings, args: argparse.Namespace) -> None:
    cam = next((c for c in settings.cameras if c.id == args.camera), None)
    if cam is None:
        sys.exit(f"Kamera {args.camera!r} nicht in der Konfiguration.")
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
        sys.exit("Kein Schachbrett erkannt.")
    result = calibrate(collector.detections, collector.image_size, pattern, args.square_mm)
    path = save_lens(result, settings.calibration_dir, cam.id)
    print(f"\nKalibrierung gespeichert: {path}")
    print(f"Reprojektionsfehler: {result.rms_error:.3f} px ", end="")
    if result.rms_error < 0.5:
        print("(sehr gut)")
    elif result.rms_error < 1.0:
        print("(in Ordnung)")
    else:
        print("(zu hoch – Schachbrett flach halten, mehr Bildränder abdecken, erneut kalibrieren)")

    sample = next(iter(sorted(image_dir.glob("*.png"))), None)
    image = cv2.imread(str(sample)) if sample is not None else None
    if image is not None:
        preview = Undistorter(result).undistort(image)
        cv2.imwrite(str(out_dir / "lens_preview.png"), preview)
        print(f"Vorschau entzerrt: {out_dir / 'lens_preview.png'}")


def _collect_from_files(collector: ChessboardCollector, folder: Path) -> None:
    files = sorted(p for p in folder.iterdir() if p.suffix.lower() in {".png", ".jpg", ".jpeg"})
    for path in files:
        image = cv2.imread(str(path))
        if image is not None and collector.offer(image):
            print(f"  ✓ {path.name}")
    print(f"{len(collector.detections)} von {len(files)} Bildern verwendbar.")


def _collect_live(
    collector: ChessboardCollector, cam: CameraConfig, target: int, image_dir: Path
) -> None:
    worker = CameraWorker(cam)
    worker.start()
    print(
        f"Schachbrett ({collector.pattern[0]}x{collector.pattern[1]} innere Ecken) vor Kamera "
        f"{cam.id} halten und langsam bewegen: Mitte, alle Ränder und Ecken, leicht gekippt.\n"
        f"Benötigt: {target} Aufnahmen. Abbrechen mit Strg+C."
    )
    seq = 0
    try:
        while len(collector.detections) < target:
            frame = worker.wait_for_frame(seq, 2.0)
            if frame is None:
                status = worker.status()
                print(f"  warte auf Kamera … ({status.state.value} {status.last_error or ''})")
                continue
            seq = frame.seq
            if collector.offer(frame.image):
                n = len(collector.detections)
                cv2.imwrite(str(image_dir / f"{n:02d}.png"), frame.image)
                print(f"  ✓ Aufnahme {n}/{target}")
            time.sleep(0.2)
    except KeyboardInterrupt:
        print(f"\nAbgebrochen, {len(collector.detections)} Aufnahmen vorhanden.")
    finally:
        worker.stop()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dartscore", description=__doc__)
    parser.add_argument("-c", "--config", type=Path, help="Pfad zur config.toml")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("serve", help="Server starten (Standard)")
    sub.add_parser("devices", help="angeschlossene Kameras und Formate anzeigen")

    bench = sub.add_parser("bench", help="alle Kameras gleichzeitig lesen und fps messen")
    bench.add_argument("--seconds", type=int, default=10)

    lens = sub.add_parser("calibrate-lens", help="Linsenverzeichnung per Schachbrett kalibrieren")
    lens.add_argument("--camera", required=True, help="Kamera-ID aus der Konfiguration")
    lens.add_argument("--pattern", default="9x6", help="innere Ecken, Spalten x Zeilen")
    lens.add_argument("--square-mm", type=float, default=25.0, help="Kantenlänge eines Feldes")
    lens.add_argument("--frames", type=int, default=20, help="Anzahl Aufnahmen")
    lens.add_argument("--images", help="statt live: Ordner mit vorhandenen Aufnahmen")
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
