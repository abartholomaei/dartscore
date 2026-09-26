from pathlib import Path

import cv2
import numpy as np
import pytest

from dartscore.vision.intrinsics import (
    ChessboardCollector,
    LensCalibration,
    Undistorter,
    calibrate,
    load_lens,
    save_lens,
)

PATTERN = (9, 6)
SQUARE_MM = 25.0
SQUARE_PX = 40
BORDER_PX = 40
IMAGE_SIZE = (1280, 720)
K = np.array([[900.0, 0, 640], [0, 900.0, 360], [0, 0, 1]])


def chessboard_texture() -> np.ndarray:
    cols, rows = PATTERN[0] + 1, PATTERN[1] + 1
    tex = np.full(
        (rows * SQUARE_PX + 2 * BORDER_PX, cols * SQUARE_PX + 2 * BORDER_PX), 255, np.uint8
    )
    for r in range(rows):
        for c in range(cols):
            if (r + c) % 2 == 0:
                y, x = BORDER_PX + r * SQUARE_PX, BORDER_PX + c * SQUARE_PX
                tex[y : y + SQUARE_PX, x : x + SQUARE_PX] = 0
    return tex


def render_view(tex: np.ndarray, rvec: np.ndarray, tvec: np.ndarray) -> np.ndarray:
    """Project the chessboard with a known camera matrix K (no distortion)."""
    rot, _ = cv2.Rodrigues(rvec)
    plane_to_img = K @ np.column_stack([rot[:, 0], rot[:, 1], tvec])
    # texture pixels → mm, origin at the first inner corner
    mm_per_px = SQUARE_MM / SQUARE_PX
    offset = BORDER_PX + SQUARE_PX
    tex_to_plane = np.array(
        [[mm_per_px, 0, -offset * mm_per_px], [0, mm_per_px, -offset * mm_per_px], [0, 0, 1]]
    )
    img = cv2.warpPerspective(tex, plane_to_img @ tex_to_plane, IMAGE_SIZE, borderValue=128)
    return cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)


@pytest.fixture(scope="module")
def views() -> list[np.ndarray]:
    tex = chessboard_texture()
    rng = np.random.default_rng(42)
    result = []
    for _ in range(12):
        rvec = rng.uniform(-0.35, 0.35, 3)
        tvec = np.array([rng.uniform(-150, 20), rng.uniform(-100, 0), rng.uniform(550, 750)])
        result.append(render_view(tex, rvec, tvec))
    return result


def test_calibration_recovers_focal_length(views: list[np.ndarray]) -> None:
    collector = ChessboardCollector(PATTERN, min_shift_px=10)
    accepted = sum(collector.offer(v) for v in views)
    assert accepted >= 8
    assert collector.image_size == IMAGE_SIZE

    result = calibrate(collector.detections, IMAGE_SIZE, PATTERN, SQUARE_MM)

    assert result.rms_error < 1.0
    assert result.camera_matrix[0, 0] == pytest.approx(900, rel=0.05)
    assert result.camera_matrix[1, 1] == pytest.approx(900, rel=0.05)


def test_collector_rejects_near_duplicates(views: list[np.ndarray]) -> None:
    collector = ChessboardCollector(PATTERN)
    assert collector.offer(views[0]) is True
    assert collector.offer(views[0]) is False


def test_calibrate_needs_enough_views() -> None:
    with pytest.raises(ValueError, match="At least 5"):
        calibrate([], IMAGE_SIZE)


def test_save_load_roundtrip_and_undistort(tmp_path: Path) -> None:
    cal = LensCalibration(
        camera_matrix=K,
        dist_coeffs=np.array([-0.3, 0.1, 0, 0, 0]),
        image_size=IMAGE_SIZE,
        rms_error=0.4,
        created_at="2026-09-26T12:00:00+00:00",
    )
    save_lens(cal, tmp_path, "cam1")
    loaded = load_lens(tmp_path, "cam1")
    assert loaded is not None
    np.testing.assert_allclose(loaded.camera_matrix, K)
    assert load_lens(tmp_path, "cam2") is None

    # half resolution is undistorted too (camera matrix is scaled)
    small = np.zeros((360, 640, 3), np.uint8)
    assert Undistorter(loaded).undistort(small).shape == small.shape
