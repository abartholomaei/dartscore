import numpy as np
import pytest

from dartscore.vision.model import decode, decode_heatmaps, letterbox


def test_decode_classic_output_with_nms() -> None:
    # (1, 4 + 5 classes, 3 anchors): two overlapping tips and one calibration point
    out = np.zeros((1, 9, 3), np.float32)
    out[0, :4, 0] = [100, 200, 16, 16]
    out[0, 4, 0] = 0.9
    out[0, :4, 1] = [101, 201, 16, 16]
    out[0, 4, 1] = 0.6  # duplicate of anchor 0, removed by NMS
    out[0, :4, 2] = [300, 50, 16, 16]
    out[0, 6, 2] = 0.8  # class 2
    result = sorted(decode(out, 0.3))
    assert [(c, x, y) for c, x, y, _ in result] == [(0, 100.0, 200.0), (2, 300.0, 50.0)]
    assert [s for *_, s in result] == pytest.approx([0.9, 0.8])


def test_decode_end_to_end_output() -> None:
    out = np.array([[[90, 190, 110, 210, 0.95, 0], [0, 0, 1, 1, 0.1, 0]]], np.float32)
    result = decode(out, 0.3)
    assert len(result) == 1
    cls, x, y, score = result[0]
    assert (cls, x, y) == (0, 100.0, 200.0)
    assert score == pytest.approx(0.95)


def test_letterbox_maps_back() -> None:
    image = np.zeros((720, 1280, 3), np.uint8)
    tensor, scale, (pad_x, pad_y) = letterbox(image, 640)
    assert tensor.shape == (1, 3, 640, 640)
    assert scale == 0.5
    assert (pad_x, pad_y) == (0, 140)


def test_decode_heatmaps_peaks_with_offsets() -> None:
    # 5 classes + dx, dy on a 20x20 grid, stride 4
    out = np.zeros((1, 7, 20, 20), np.float32)
    out[0, 0, 10, 5] = 0.9  # tip in cell (5, 10)
    out[0, 0, 10, 6] = 0.5  # its neighbour: not a local maximum
    out[0, 5, 10, 5], out[0, 6, 10, 5] = 0.25, 0.75
    out[0, 3, 2, 15] = 0.7  # calibration point, class 3
    out[0, 1, 18, 18] = 0.1  # below the confidence
    result = sorted(decode_heatmaps(out, classes=5, stride=4, confidence=0.3))
    assert [(c, x, y) for c, x, y, _ in result] == [(0, 21.0, 43.0), (3, 60.0, 8.0)]
    assert [s for *_, s in result] == pytest.approx([0.9, 0.7])
