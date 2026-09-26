"""Linsenkalibrierung (Kamera-Intrinsics) mit Schachbrettmuster und Entzerrung.

Die 100°-Weitwinkel-Kameras verzerren stark; ohne Entzerrung wären Treffer am Bildrand ungenau.
Kalibriert wird einmal pro Kamera, das Ergebnis liegt als JSON im Datenordner.
"""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import cv2
import numpy as np
from numpy.typing import NDArray

from dartscore.vision.sources import Image

# Anzahl der inneren Ecken (Spalten x Zeilen), z. B. ein Schachbrett mit 10x7 Feldern
DEFAULT_PATTERN = (9, 6)


@dataclass(frozen=True)
class LensCalibration:
    camera_matrix: NDArray[np.float64]
    dist_coeffs: NDArray[np.float64]
    image_size: tuple[int, int]
    rms_error: float
    created_at: str

    def to_json(self) -> str:
        return json.dumps(
            {
                "camera_matrix": self.camera_matrix.tolist(),
                "dist_coeffs": self.dist_coeffs.ravel().tolist(),
                "image_size": list(self.image_size),
                "rms_error": self.rms_error,
                "created_at": self.created_at,
            },
            indent=2,
        )

    @classmethod
    def from_json(cls, text: str) -> "LensCalibration":
        data = json.loads(text)
        width, height = data["image_size"]
        return cls(
            camera_matrix=np.array(data["camera_matrix"], dtype=np.float64),
            dist_coeffs=np.array(data["dist_coeffs"], dtype=np.float64),
            image_size=(int(width), int(height)),
            rms_error=float(data["rms_error"]),
            created_at=data["created_at"],
        )


def lens_file(calibration_dir: Path, camera_id: str) -> Path:
    return calibration_dir / camera_id / "lens.json"


def save_lens(calibration: LensCalibration, calibration_dir: Path, camera_id: str) -> Path:
    path = lens_file(calibration_dir, camera_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(calibration.to_json())
    return path


def load_lens(calibration_dir: Path, camera_id: str) -> LensCalibration | None:
    path = lens_file(calibration_dir, camera_id)
    return LensCalibration.from_json(path.read_text()) if path.is_file() else None


def find_chessboard(
    image: Image, pattern: tuple[int, int] = DEFAULT_PATTERN
) -> NDArray[np.float32] | None:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
    found, corners = cv2.findChessboardCornersSB(
        gray, pattern, flags=cv2.CALIB_CB_NORMALIZE_IMAGE | cv2.CALIB_CB_EXHAUSTIVE
    )
    return np.asarray(corners, dtype=np.float32) if found else None


def board_points(pattern: tuple[int, int], square_mm: float) -> NDArray[np.float32]:
    cols, rows = pattern
    grid = np.zeros((rows * cols, 3), np.float32)
    grid[:, :2] = np.mgrid[0:cols, 0:rows].T.reshape(-1, 2) * square_mm
    return grid


def calibrate(
    detections: list[NDArray[np.float32]],
    image_size: tuple[int, int],
    pattern: tuple[int, int] = DEFAULT_PATTERN,
    square_mm: float = 25.0,
) -> LensCalibration:
    if len(detections) < 5:
        raise ValueError(f"Mindestens 5 Schachbrett-Aufnahmen nötig, vorhanden: {len(detections)}")
    object_points = [board_points(pattern, square_mm)] * len(detections)
    rms, camera_matrix, dist_coeffs, _, _ = cv2.calibrateCamera(
        object_points, detections, image_size, None, None
    )
    return LensCalibration(
        camera_matrix=np.asarray(camera_matrix, dtype=np.float64),
        dist_coeffs=np.asarray(dist_coeffs, dtype=np.float64).ravel(),
        image_size=image_size,
        rms_error=float(rms),
        created_at=datetime.now(UTC).isoformat(timespec="seconds"),
    )


class ChessboardCollector:
    """Sammelt Schachbrett-Aufnahmen und nimmt nur solche, die sich deutlich unterscheiden.

    So entsteht eine gute Abdeckung des Bildes (Ränder!), ohne 20 fast gleiche Bilder.
    """

    def __init__(self, pattern: tuple[int, int] = DEFAULT_PATTERN, min_shift_px: float = 40.0):
        self.pattern = pattern
        self.min_shift_px = min_shift_px
        self.detections: list[NDArray[np.float32]] = []
        self.image_size: tuple[int, int] | None = None

    def offer(self, image: Image) -> bool:
        """True, wenn das Bild aufgenommen wurde."""
        corners = find_chessboard(image, self.pattern)
        if corners is None:
            return False
        h, w = image.shape[:2]
        if self.image_size is None:
            self.image_size = (w, h)
        elif self.image_size != (w, h):
            raise ValueError("Bildgröße hat sich während der Kalibrierung geändert")
        for previous in self.detections:
            if np.mean(np.linalg.norm(previous - corners, axis=-1)) < self.min_shift_px:
                return False
        self.detections.append(corners)
        return True


class Undistorter:
    """Entzerrt Bilder; die Remap-Tabellen werden einmal pro Bildgröße berechnet."""

    def __init__(self, calibration: LensCalibration, alpha: float = 0.0) -> None:
        self.calibration = calibration
        self.alpha = alpha
        self._maps: dict[tuple[int, int], tuple[NDArray[np.float32], NDArray[np.float32]]] = {}

    def _maps_for(self, size: tuple[int, int]) -> tuple[NDArray[np.float32], NDArray[np.float32]]:
        if size not in self._maps:
            cal = self.calibration
            # Kameramatrix auf abweichende Auflösung skalieren
            sx, sy = size[0] / cal.image_size[0], size[1] / cal.image_size[1]
            matrix = cal.camera_matrix * np.array([[sx], [sy], [1.0]])
            new_matrix, _ = cv2.getOptimalNewCameraMatrix(
                matrix, cal.dist_coeffs, size, self.alpha, size
            )
            map1, map2 = cv2.initUndistortRectifyMap(
                matrix, cal.dist_coeffs, None, new_matrix, size, cv2.CV_32FC1
            )
            self._maps[size] = (np.asarray(map1), np.asarray(map2))
        return self._maps[size]

    def undistort(self, image: Image) -> Image:
        h, w = image.shape[:2]
        map1, map2 = self._maps_for((w, h))
        return np.asarray(cv2.remap(image, map1, map2, cv2.INTER_LINEAR), dtype=np.uint8)
