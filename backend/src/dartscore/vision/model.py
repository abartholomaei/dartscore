"""Dart tip detection with a trained YOLO model (ONNX, see training/README.md).

The model finds dart tips (class 0) and the four calibration points (classes 1-4) as small
boxes; the box center is the keypoint. Both classic YOLO outputs (boxes + class scores, needs
NMS) and end-to-end outputs (YOLO26: ready boxes) are supported.
"""

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import structlog
from numpy.typing import NDArray

from dartscore.vision.sources import Image

log = structlog.get_logger(__name__)

TIP_CLASS = 0


@dataclass(frozen=True)
class Keypoint:
    cls: int
    x: float
    y: float
    confidence: float


def letterbox(image: Image, size: int) -> tuple[NDArray[np.float32], float, tuple[int, int]]:
    """Resize keeping the aspect ratio and pad to a square; returns the NCHW tensor, the scale
    and the padding (x, y) needed to map results back."""
    h, w = image.shape[:2]
    scale = min(size / w, size / h)
    nw, nh = round(w * scale), round(h * scale)
    resized = cv2.resize(image, (nw, nh), interpolation=cv2.INTER_LINEAR)
    pad_x, pad_y = (size - nw) // 2, (size - nh) // 2
    canvas = np.full((size, size, 3), 114, np.uint8)
    canvas[pad_y : pad_y + nh, pad_x : pad_x + nw] = resized
    tensor = (
        cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB).astype(np.float32).transpose(2, 0, 1)[None] / 255.0
    )
    return np.ascontiguousarray(tensor), scale, (pad_x, pad_y)


def decode(
    output: NDArray[np.float32], confidence: float, iou: float = 0.5
) -> list[tuple[int, float, float, float]]:
    """Model output -> (class, center x, center y, confidence) in model input pixels."""
    out = np.squeeze(output, axis=0)
    if out.ndim == 2 and out.shape[1] == 6:
        # end-to-end: x1, y1, x2, y2, score, class
        return [
            (int(c), float((x1 + x2) / 2), float((y1 + y2) / 2), float(s))
            for x1, y1, x2, y2, s, c in out
            if s >= confidence
        ]
    # classic: (4 + classes, anchors) with cx, cy, w, h
    preds = out.T
    scores = preds[:, 4:]
    classes = scores.argmax(axis=1)
    best = scores.max(axis=1)
    keep = best >= confidence
    preds, classes, best = preds[keep], classes[keep], best[keep]
    if len(preds) == 0:
        return []
    boxes = [
        [float(cx - w / 2), float(cy - h / 2), float(w), float(h)] for cx, cy, w, h in preds[:, :4]
    ]
    indices = cv2.dnn.NMSBoxesBatched(boxes, best.tolist(), classes.tolist(), confidence, iou)
    return [
        (int(classes[i]), float(preds[i, 0]), float(preds[i, 1]), float(best[i]))
        for i in np.array(indices).reshape(-1)
    ]


class TipModel:
    def __init__(self, path: Path, confidence: float = 0.3) -> None:
        import onnxruntime as ort

        self.path = path
        self.confidence = confidence
        self._session = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
        model_input = self._session.get_inputs()[0]
        self._input_name = model_input.name
        size = model_input.shape[-1]
        self.size = size if isinstance(size, int) else 640
        log.info("tip_model_loaded", path=str(path), input=self.size)

    def detect(self, image: Image) -> list[Keypoint]:
        tensor, scale, (pad_x, pad_y) = letterbox(image, self.size)
        output = self._session.run(None, {self._input_name: tensor})[0]
        return [
            Keypoint(cls, (x - pad_x) / scale, (y - pad_y) / scale, conf)
            for cls, x, y, conf in decode(np.asarray(output, dtype=np.float32), self.confidence)
        ]

    def tips(self, image: Image) -> list[Keypoint]:
        return [k for k in self.detect(image) if k.cls == TIP_CLASS]


def load_model(path: Path | None) -> TipModel | None:
    if path is None or not path.is_file():
        return None
    try:
        return TipModel(path)
    except Exception as exc:
        log.error("tip_model_failed", path=str(path), error=str(exc))
        return None
