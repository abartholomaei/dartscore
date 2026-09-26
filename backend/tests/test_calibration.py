from pathlib import Path

import numpy as np
import pytest

from dartscore.config import CameraConfig
from dartscore.vision import board
from dartscore.vision.calibration import (
    BoardCalibration,
    CalibrationError,
    compute_overlay,
    fit_homography,
    load_board,
    measure_drift,
    save_board,
)
from dartscore.vision.sources import SyntheticSource


def synthetic_clicks(
    position_deg: float = 120,
) -> tuple[SyntheticSource, dict[str, tuple[float, float]]]:
    """Exact image coordinates of all calibration points in a synthetic camera."""
    source = SyntheticSource(CameraConfig(id="cam", source="synthetic", position_deg=position_deg))
    h = source.board_homography()
    pts = np.array([[p.x_mm, p.y_mm] for p in board.CALIBRATION_POINTS])
    proj = np.c_[pts, np.ones(len(pts))] @ h.T
    proj = proj[:, :2] / proj[:, 2:]
    clicks = {
        p.id: (float(x), float(y)) for p, (x, y) in zip(board.CALIBRATION_POINTS, proj, strict=True)
    }
    return source, clicks


def test_fit_recovers_synthetic_view() -> None:
    source, clicks = synthetic_clicks()
    required = {k: clicks[k] for k in ("20/1", "6/10", "3/19", "11/14")}

    fit = fit_homography(required)

    truth = source.board_homography()
    np.testing.assert_allclose(
        fit.homography / fit.homography[2, 2], truth / truth[2, 2], rtol=1e-6, atol=1e-6
    )
    assert fit.rms_px == pytest.approx(0, abs=1e-3)


def test_overdetermined_fit_reports_click_errors() -> None:
    _, clicks = synthetic_clicks()
    x, y = clicks["bull"]
    clicks["bull"] = (x + 6, y)  # one sloppy click

    fit = fit_homography(clicks)

    assert fit.rms_px > 0.5
    assert max(fit.errors_px, key=fit.errors_px.__getitem__) == "bull"


def test_scoring_through_calibration() -> None:
    source, clicks = synthetic_clicks(position_deg=240)
    fit = fit_homography(clicks)
    cal = BoardCalibration("cam", clicks, fit.homography, (1280, 720), False, None, fit.rms_px)

    # project T20 center into the image, then click there
    h = source.board_homography()
    p = h @ np.array([0, 103, 1])
    score, (x_mm, y_mm) = cal.score_at_pixel(p[0] / p[2], p[1] / p[2])

    assert score.label == "T20"
    assert (x_mm, y_mm) == pytest.approx((0, 103), abs=0.01)


def test_rejects_too_few_unknown_and_mirrored_points() -> None:
    _, clicks = synthetic_clicks()
    with pytest.raises(CalibrationError, match="At least 4"):
        fit_homography({k: clicks[k] for k in ("20/1", "6/10", "3/19")})
    with pytest.raises(CalibrationError, match="Unknown"):
        fit_homography({**clicks, "nope": (1, 2)})
    # swapping left/right points mirrors the board
    mirrored = {
        "20/1": clicks["20/1"],
        "6/10": clicks["11/14"],
        "3/19": clicks["3/19"],
        "11/14": clicks["6/10"],
    }
    with pytest.raises(CalibrationError, match="mirrored"):
        fit_homography(mirrored)


def test_overlay_has_all_rings_wires_and_labels() -> None:
    _, clicks = synthetic_clicks()
    overlay = compute_overlay(fit_homography(clicks).homography)
    assert len(overlay.rings) == 6
    assert len(overlay.wires) == 20
    assert [n for n, _ in overlay.labels] == list(board.SEGMENTS)


def test_save_load_keeps_history(tmp_path: Path) -> None:
    _, clicks = synthetic_clicks()
    fit = fit_homography(clicks)
    cal = BoardCalibration(
        "cam", clicks, fit.homography, (1280, 720), True, "2026-01-01", fit.rms_px
    )
    image = np.zeros((720, 1280, 3), np.uint8)

    save_board(cal, tmp_path, image)
    save_board(cal, tmp_path, image)
    loaded = load_board(tmp_path, "cam")

    assert loaded is not None
    assert loaded.points == cal.points
    assert loaded.undistorted is True
    np.testing.assert_allclose(loaded.homography, cal.homography)
    assert len(list((tmp_path / "cam" / "history").iterdir())) == 1
    assert load_board(tmp_path, "other") is None


def test_drift_detects_shifted_image() -> None:
    source = SyntheticSource(CameraConfig(id="cam", source="synthetic"))
    source.open()
    reference = source._base
    assert reference is not None
    shifted = np.roll(reference, shift=(6, 9), axis=(0, 1))

    assert measure_drift(reference, reference) < 1.0
    assert measure_drift(reference, shifted) == pytest.approx(np.hypot(6, 9), abs=2.0)
