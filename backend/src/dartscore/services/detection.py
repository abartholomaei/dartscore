"""Runs the dart detector on the live cameras and feeds the results into the active game.

Detected darts become throws (source "auto"), a detected takeout moves on to the next player.
Every detection is recorded with the images before and after the throw; together with the
stored (and possibly corrected) game events they form the training data for the model.
"""

import json
import threading
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

import cv2
import structlog

from dartscore.config import DetectionConfig
from dartscore.game import Dart, GameError
from dartscore.services.games import GameService
from dartscore.services.hub import EventHub
from dartscore.services.recordings import RecordingIndex
from dartscore.vision.calibration import BoardCalibration
from dartscore.vision.camera import CameraManager
from dartscore.vision.detection import DartDetection, DartDetector, Takeout
from dartscore.vision.intrinsics import Undistorter
from dartscore.vision.model import TipModel, load_model

log = structlog.get_logger(__name__)


class DetectionService:
    def __init__(
        self,
        config: DetectionConfig,
        cameras: CameraManager,
        games: GameService,
        hub: EventHub,
        recordings_dir: Path,
        model_file: Path | None = None,
    ) -> None:
        self.config = config
        self._cameras = cameras
        self._games = games
        self._hub = hub
        self._recordings_dir = recordings_dir
        # set by the app: makes new recordings findable for the visit photos
        self.recordings: RecordingIndex | None = None
        self._lock = threading.Lock()
        self._detector: DartDetector | None = None
        self._enabled = config.enabled
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._last_dart: dict[str, Any] | None = None
        self._last_published_state = ""
        self._model = load_model(model_file)
        games.add_listener(self._on_game_event)

    # --- control ------------------------------------------------------------------------

    @property
    def model(self) -> TipModel | None:
        """The optional tip model (also used by the referee)."""
        return self._model

    def configure(
        self, calibrations: dict[str, BoardCalibration], undistorters: dict[str, Undistorter]
    ) -> None:
        """(Re)builds the detector, e.g. after a calibration was saved or deleted."""
        with self._lock:
            usable = {cid: cal for cid, cal in calibrations.items() if self._cameras.get(cid)}
            self._detector = (
                DartDetector(self.config, usable, undistorters, self._model) if usable else None
            )
        log.info("detection_configured", cameras=sorted(usable))
        self._publish_status()

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="detection", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(3)
            self._thread = None

    def set_enabled(self, enabled: bool) -> None:
        with self._lock:
            self._enabled = enabled
            if self._detector is not None:
                self._detector.reset()
        self._publish_status()

    def reset(self) -> None:
        with self._lock:
            if self._detector is not None:
                self._detector.reset()
        self._publish_status()

    def status(self) -> dict[str, Any]:
        with self._lock:
            detector = self._detector
            return {
                "enabled": self._enabled,
                "available": detector is not None,
                "cameras": detector.camera_ids if detector else [],
                "model": str(self._model.path.name) if self._model else None,
                "state": detector.state.value if detector else "unavailable",
                "darts_in_turn": detector.darts_in_turn if detector else 0,
                "last_dart": self._last_dart,
                "last_evaluation": asdict(detector.last_evaluation) if detector else None,
            }

    # --- loop ---------------------------------------------------------------------------

    def _run(self) -> None:
        interval = 1 / self.config.rate_hz
        while not self._stop.is_set():
            started = time.monotonic()
            try:
                self._step(started)
            except Exception:
                log.exception("detection_step_failed")
            self._stop.wait(max(0.0, interval - (time.monotonic() - started)))

    def _step(self, now: float) -> None:
        with self._lock:
            detector = self._detector
            if detector is None or not self._enabled:
                return
            frames = {}
            for cid in detector.camera_ids:
                worker = self._cameras.get(cid)
                frame = worker.latest() if worker else None
                if frame is not None:
                    frames[cid] = frame.image
            if not frames:
                return
            events = detector.process(frames, now)
            state = detector.state.value
        for event in events:
            if isinstance(event, DartDetection):
                self._on_dart(detector, event)
            elif isinstance(event, Takeout):
                self._on_takeout()
        if state != self._last_published_state or events:
            self._last_published_state = state
            self._publish_status()

    def _on_dart(self, detector: DartDetector, dart: DartDetection) -> None:
        game_state: dict[str, Any] | None = None
        accepted = False
        active = self._games.active_state()
        if active and not active["finished"] and not active["awaiting_next"]:
            try:
                game_state = self._games.throw(
                    Dart(dart.segment, dart.multiplier),
                    source="auto",
                    x_mm=dart.x_mm,
                    y_mm=dart.y_mm,
                    confidence=dart.confidence,
                )
                accepted = True
            except GameError as exc:
                log.warning("detected_dart_rejected", code=exc.code)
        info = {
            **asdict(dart),
            "accepted": accepted,
            "time": datetime.now().isoformat(timespec="milliseconds"),
        }
        self._last_dart = info
        log.info(
            "dart_detected", label=dart.label, x=dart.x_mm, y=dart.y_mm, confidence=dart.confidence
        )
        self._hub.publish("dart", info)
        if self.config.record:
            self._record(detector, info, game_state)

    def _on_takeout(self) -> None:
        log.info("takeout_detected")
        self._hub.publish("takeout", None)
        active = self._games.active_state()
        if not active or active["finished"]:
            return
        turn = active.get("turn")
        # only move on if the current player actually threw (not after a manual "next")
        if active["awaiting_next"] or (
            turn and turn["player"] == active["current_player"] and turn["darts"]
        ):
            try:
                self._games.next_turn(source="auto")
            except GameError as exc:
                log.warning("takeout_rejected", code=exc.code)

    def _on_game_event(self, event: str) -> None:
        # a manual "next" or a new game: the detector starts counting darts from zero
        if event in ("next", "new_game"):
            with self._lock:
                if self._detector is not None:
                    self._detector.new_turn()

    def _record(
        self, detector: DartDetector, info: dict[str, Any], game_state: dict[str, Any] | None
    ) -> None:
        stamp = datetime.now()
        folder = self._recordings_dir / stamp.strftime("%Y-%m-%d") / stamp.strftime("%H%M%S_%f")
        try:
            folder.mkdir(parents=True, exist_ok=True)
            # the detector already took the new frame as reference, so "before" is the frame
            # of the previous reference kept by the detector
            for cid, image in detector.previous_reference_images().items():
                cv2.imwrite(
                    str(folder / f"{cid}_before.jpg"), image, [cv2.IMWRITE_JPEG_QUALITY, 92]
                )
            for cid, image in detector.reference_images().items():
                cv2.imwrite(str(folder / f"{cid}_after.jpg"), image, [cv2.IMWRITE_JPEG_QUALITY, 92])
            meta = {
                "detection": info,
                "game_id": game_state.get("id") if game_state else None,
                "event_seq": game_state.get("event_count", 0) - 1 if game_state else None,
                # all darts in the board after this throw (None if unknown) and the
                # calibrations the images were taken with; see dartscore.training
                "board_darts": detector.board_darts,
                "calibrations": detector.calibration_info(),
            }
            text = json.dumps(meta, indent=2, default=str)
            (folder / "meta.json").write_text(text)
            if self.recordings is not None:
                self.recordings.add(folder, json.loads(text))
        except OSError as exc:
            log.warning("recording_failed", error=str(exc))

    def _publish_status(self) -> None:
        self._hub.publish("detection", self.status())
