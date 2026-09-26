import numpy as np
import pytest

from dartscore.vision.model import decode, letterbox


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
