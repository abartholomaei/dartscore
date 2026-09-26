"""Keeps the calibrations aligned when a camera gets bumped.

Once a minute, while nothing moves in front of the board, every calibrated camera is compared with
the image taken at calibration time; if it moved, the calibration is re-aligned automatically
(see dartscore.vision.realign).
"""

import threading
from collections.abc import Callable
from typing import Any

import structlog

from dartscore.config import DetectionConfig
from dartscore.services.hub import EventHub
from dartscore.vision.calibration import BoardCalibration
from dartscore.vision.camera import CameraManager
from dartscore.vision.intrinsics import Undistorter
from dartscore.vision.realign import RealignError
from dartscore.vision.sources import Image

log = structlog.get_logger(__name__)

INTERVAL_S = 60.0


class CalibrationMonitor:
    def __init__(
        self,
        config: DetectionConfig,
        calibrations: Callable[[], dict[str, BoardCalibration]],
        realign: Callable[[str, Image, float], tuple[BoardCalibration, float]],
        cameras: CameraManager,
        undistorters: dict[str, Undistorter],
        detection_status: Callable[[], dict[str, Any]],
        hub: EventHub,
        interval_s: float = INTERVAL_S,
    ) -> None:
        self._config = config
        self._calibrations = calibrations
        self._realign = realign
        self._cameras = cameras
        self._undistorters = undistorters
        self._detection_status = detection_status
        self._hub = hub
        self._interval = interval_s
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="calibration-monitor", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        while not self._stop.wait(self._interval):
            try:
                self.check()
            except Exception:
                log.exception("calibration_check_failed")

    def check(self) -> list[tuple[str, float]]:
        """Re-aligns moved cameras; returns (camera, moved px) for those that were updated."""
        if not self._config.auto_realign:
            return []
        # not while something moves in front of the board; darts in the board or a lasting
        # change (a bumped camera looks like one) do not disturb the feature matching
        if self._detection_status().get("state") == "motion":
            return []
        updated = []
        for camera_id, calibration in self._calibrations().items():
            worker = self._cameras.get(camera_id)
            frame = worker.latest() if worker else None
            if frame is None:
                continue
            image = frame.image
            undistorter = self._undistorters.get(camera_id)
            if calibration.undistorted and undistorter is not None:
                image = undistorter.undistort(image)
            try:
                _, moved = self._realign(camera_id, image, self._config.realign_threshold_px)
            except RealignError as exc:
                log.warning("calibration_realign_failed", camera=camera_id, code=exc.code)
                continue
            if moved >= self._config.realign_threshold_px:
                log.info("calibration_realigned", camera=camera_id, moved_px=round(moved, 1))
                self._hub.publish(
                    "calibration_realigned", {"camera": camera_id, "moved_px": round(moved, 1)}
                )
                updated.append((camera_id, moved))
        return updated
