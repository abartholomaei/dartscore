"""Board calibration: a homography per camera between the board plane (mm) and the image (px).

The dart tip touches the board plane, so a plane-to-image homography is the exact model once
lens distortion is removed. Users click known board points (see ``board.CALIBRATION_POINTS``)
in each camera image. If a lens calibration exists, points are clicked in the undistorted image
and the homography refers to undistorted pixel coordinates.
"""

import json
import math
import shutil
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import cv2
import numpy as np
from numpy.typing import NDArray

from dartscore.vision import board
from dartscore.vision.intrinsics import Undistorter
from dartscore.vision.sources import Image

Point = tuple[float, float]

# the image is compared at this width when checking for drift
_DRIFT_WIDTH = 320
DRIFT_WARN_PX = 4.0


class CalibrationError(ValueError):
    """``code`` is stable and translated by the UI; the message is for logs and the API."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class BoardCalibration:
    camera_id: str
    # clicked image coordinates per calibration point id
    points: dict[str, Point]
    # 3x3, board plane (mm) -> image (px)
    homography: NDArray[np.float64]
    image_size: tuple[int, int]
    # True: coordinates refer to the undistorted image (lens calibration applied)
    undistorted: bool
    # created_at of the lens calibration used; a newer lens calibration invalidates this one
    lens_created_at: str | None
    rms_px: float
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat(timespec="seconds"))

    def board_to_image(self, points_mm: NDArray[np.float64]) -> NDArray[np.float64]:
        return _apply(self.homography, points_mm)

    def image_to_board(self, points_px: NDArray[np.float64]) -> NDArray[np.float64]:
        return _apply(np.linalg.inv(self.homography), points_px)

    def score_at_pixel(self, x: float, y: float) -> tuple[board.Score, Point]:
        bx, by = self.image_to_board(np.array([[x, y]]))[0]
        return board.score_at(bx, by), (float(bx), float(by))

    def to_json(self) -> str:
        return json.dumps(
            {
                "camera_id": self.camera_id,
                "points": {k: list(v) for k, v in self.points.items()},
                "homography": self.homography.tolist(),
                "image_size": list(self.image_size),
                "undistorted": self.undistorted,
                "lens_created_at": self.lens_created_at,
                "rms_px": self.rms_px,
                "created_at": self.created_at,
            },
            indent=2,
        )

    @classmethod
    def from_json(cls, text: str) -> "BoardCalibration":
        data = json.loads(text)
        width, height = data["image_size"]
        return cls(
            camera_id=data["camera_id"],
            points={k: (float(v[0]), float(v[1])) for k, v in data["points"].items()},
            homography=np.array(data["homography"], dtype=np.float64),
            image_size=(int(width), int(height)),
            undistorted=bool(data["undistorted"]),
            lens_created_at=data.get("lens_created_at"),
            rms_px=float(data["rms_px"]),
            created_at=data["created_at"],
        )


def _apply(matrix: NDArray[np.float64], points: NDArray[np.float64]) -> NDArray[np.float64]:
    pts = np.asarray(points, dtype=np.float64).reshape(-1, 1, 2)
    return np.asarray(cv2.perspectiveTransform(pts, matrix), dtype=np.float64).reshape(-1, 2)


@dataclass(frozen=True)
class HomographyFit:
    homography: NDArray[np.float64]
    rms_px: float
    # reprojection error per point id (0 for exactly determined fits with 4 points)
    errors_px: dict[str, float]


def fit_homography(points: dict[str, Point]) -> HomographyFit:
    unknown = set(points) - set(board.CALIBRATION_POINTS_BY_ID)
    if unknown:
        raise CalibrationError("unknown_points", f"Unknown calibration points: {sorted(unknown)}")
    if len(points) < board.REQUIRED_POINTS:
        raise CalibrationError(
            "too_few_points", f"At least {board.REQUIRED_POINTS} points required, got {len(points)}"
        )
    ids = list(points)
    board_pts = np.array(
        [
            [board.CALIBRATION_POINTS_BY_ID[i].x_mm, board.CALIBRATION_POINTS_BY_ID[i].y_mm]
            for i in ids
        ]
    )
    image_pts = np.array([points[i] for i in ids], dtype=np.float64)
    found, _ = cv2.findHomography(board_pts, image_pts, 0)
    if found is None or not np.all(np.isfinite(found)):
        raise CalibrationError(
            "invalid_plane", "Points do not define a valid board plane (collinear or duplicated?)"
        )
    matrix: NDArray[np.float64] = np.asarray(found, dtype=np.float64)
    if _is_mirrored(matrix):
        raise CalibrationError(
            "mirrored", "Board appears mirrored - check the order of the clicked points"
        )
    projected = _apply(matrix, board_pts)
    errors = np.linalg.norm(projected - image_pts, axis=1)
    return HomographyFit(
        homography=matrix,
        rms_px=float(math.sqrt(np.mean(errors**2))),
        errors_px={i: round(float(e), 2) for i, e in zip(ids, errors, strict=True)},
    )


def _is_mirrored(homography: NDArray[np.float64]) -> bool:
    """20 -> 6 -> 3 run clockwise on the board. Seen from the front (image y pointing down)
    that is a positive signed area; a negative one means the points were clicked mirrored."""
    ids = ("20/1", "6/10", "3/19")
    pts = np.array(
        [
            [board.CALIBRATION_POINTS_BY_ID[i].x_mm, board.CALIBRATION_POINTS_BY_ID[i].y_mm]
            for i in ids
        ]
    )
    a, b, c = _apply(homography, pts)
    cross = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    return bool(cross < 0)


@dataclass(frozen=True)
class Overlay:
    """Board wires projected into the image, for drawing on top of camera images."""

    rings: list[list[Point]]
    wires: list[tuple[Point, Point]]
    labels: list[tuple[int, Point]]


def compute_overlay(homography: NDArray[np.float64], steps: int = 120) -> Overlay:
    angles = np.linspace(0, 2 * np.pi, steps + 1)
    circle = np.stack([np.cos(angles), np.sin(angles)], axis=1)
    radii = (
        board.R_BULL,
        board.R_OUTER_BULL,
        board.R_TRIPLE_INNER,
        board.R_TRIPLE_OUTER,
        board.R_DOUBLE_INNER,
        board.R_DOUBLE_OUTER,
    )
    rings = [_round_points(_apply(homography, circle * r)) for r in radii]

    wires = []
    labels = []
    r_label = (board.R_DOUBLE_OUTER + board.R_BOARD) / 2
    for i, number in enumerate(board.SEGMENTS):
        edge = math.radians(90.0 - (i + 0.5) * board.SEGMENT_ANGLE_DEG)
        direction = np.array([math.cos(edge), math.sin(edge)])
        ends = _round_points(
            _apply(
                homography,
                np.stack([direction * board.R_OUTER_BULL, direction * board.R_DOUBLE_OUTER]),
            )
        )
        wires.append((ends[0], ends[1]))
        mid = math.radians(90.0 - i * board.SEGMENT_ANGLE_DEG)
        pos = _apply(homography, np.array([[r_label * math.cos(mid), r_label * math.sin(mid)]]))
        labels.append((number, _round_points(pos)[0]))
    return Overlay(rings=rings, wires=wires, labels=labels)


def _round_points(points: NDArray[np.float64]) -> list[Point]:
    return [(round(float(x), 1), round(float(y), 1)) for x, y in points]


# --- storage -----------------------------------------------------------------------------


def board_file(calibration_dir: Path, camera_id: str) -> Path:
    return calibration_dir / camera_id / "board.json"


def reference_file(calibration_dir: Path, camera_id: str) -> Path:
    return calibration_dir / camera_id / "board_reference.png"


def save_board(
    calibration: BoardCalibration, calibration_dir: Path, reference: Image | None = None
) -> Path:
    """Saves the calibration; the previous one is kept in history/ for rollback."""
    path = board_file(calibration_dir, calibration.camera_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        history = path.parent / "history"
        history.mkdir(exist_ok=True)
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
        shutil.copy2(path, history / f"board-{stamp}.json")
    path.write_text(calibration.to_json())
    if reference is not None:
        cv2.imwrite(str(reference_file(calibration_dir, calibration.camera_id)), reference)
    return path


def load_board(calibration_dir: Path, camera_id: str) -> BoardCalibration | None:
    path = board_file(calibration_dir, camera_id)
    return BoardCalibration.from_json(path.read_text()) if path.is_file() else None


def delete_board(calibration_dir: Path, camera_id: str) -> None:
    board_file(calibration_dir, camera_id).unlink(missing_ok=True)
    reference_file(calibration_dir, camera_id).unlink(missing_ok=True)


# --- drift -------------------------------------------------------------------------------


def _drift_gray(image: Image) -> NDArray[np.float32]:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    h, w = gray.shape[:2]
    small = cv2.resize(
        gray, (_DRIFT_WIDTH, round(h * _DRIFT_WIDTH / w)), interpolation=cv2.INTER_AREA
    )
    return np.asarray(small, dtype=np.float32)


def measure_drift(reference: Image, current: Image) -> float:
    """Estimated shift in pixels (at full resolution) between the calibration reference image
    and the current image. Darts in the board or light changes cause small values; a moved
    camera or board shows up as a clear shift."""
    ref, cur = _drift_gray(reference), _drift_gray(current)
    if ref.shape != cur.shape:
        return float("inf")
    window = cv2.createHanningWindow(ref.shape[::-1], cv2.CV_32F)
    (dx, dy), _ = cv2.phaseCorrelate(ref, cur, window)
    scale = reference.shape[1] / _DRIFT_WIDTH
    return float(math.hypot(dx, dy) * scale)


def change_lens(
    calibration: BoardCalibration, old: Undistorter | None, new: Undistorter | None
) -> BoardCalibration:
    """Carries the clicked points over to another lens calibration (or none), so a new lens
    calibration does not require clicking the board again. The homography is fitted anew
    because (un)distortion is not a projective mapping."""
    if not calibration.points:
        raise CalibrationError("no_points", "The calibration has no clicked points to convert")
    size = calibration.image_size
    ids = list(calibration.points)
    points = np.array([calibration.points[i] for i in ids], dtype=np.float64)
    if calibration.undistorted:
        if old is None:
            raise CalibrationError("lens_missing", "The lens calibration used is not available")
        points = old.distort_points(points, size)
    if new is not None:
        points = new.undistort_points(points, size)
    converted = {
        i: (round(float(x), 2), round(float(y), 2)) for i, (x, y) in zip(ids, points, strict=True)
    }
    fit = fit_homography(converted)
    return BoardCalibration(
        camera_id=calibration.camera_id,
        points=converted,
        homography=fit.homography,
        image_size=size,
        undistorted=new is not None,
        lens_created_at=new.calibration.created_at if new else None,
        rms_px=fit.rms_px,
    )
