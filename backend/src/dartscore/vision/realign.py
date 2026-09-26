"""Re-aligns a calibration after a camera was bumped.

The image taken at calibration time is matched against the current image with SIFT features
(board, number ring and surround offer plenty). The image-to-image homography carries the
original, precise calibration over to the new camera pose, so no new clicking is needed.
"""

from dataclasses import dataclass

import cv2
import numpy as np
from numpy.typing import NDArray

from dartscore.vision.sources import Image

MIN_INLIERS = 150


class RealignError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Realignment:
    # maps pixels of the reference image to pixels of the current image
    homography: NDArray[np.float64]
    inliers: int
    matches: int


def realign(reference: Image, current: Image, mask: NDArray[np.uint8] | None = None) -> Realignment:
    """``mask`` limits the features to a region (e.g. the board and its surround)."""
    sift = cv2.SIFT.create(nfeatures=3000)
    g1 = cv2.cvtColor(reference, cv2.COLOR_BGR2GRAY) if reference.ndim == 3 else reference
    g2 = cv2.cvtColor(current, cv2.COLOR_BGR2GRAY) if current.ndim == 3 else current
    k1, d1 = sift.detectAndCompute(g1, mask)
    k2, d2 = sift.detectAndCompute(g2, None)
    if d1 is None or d2 is None or len(k1) < MIN_INLIERS or len(k2) < MIN_INLIERS:
        raise RealignError("too_few_features", "Not enough image features")
    pairs = cv2.BFMatcher().knnMatch(d1, d2, k=2)
    # Lowe's ratio test: keep matches that are clearly better than the second best
    good = [p[0] for p in pairs if len(p) == 2 and p[0].distance < 0.75 * p[1].distance]
    if len(good) < MIN_INLIERS:
        raise RealignError("too_few_matches", f"Only {len(good)} matching features")
    src = np.array([k1[m.queryIdx].pt for m in good], dtype=np.float32)
    dst = np.array([k2[m.trainIdx].pt for m in good], dtype=np.float32)
    matrix, inlier_mask = cv2.findHomography(src, dst, cv2.RANSAC, 2.0)
    inliers = int(inlier_mask.sum()) if inlier_mask is not None else 0
    if matrix is None or inliers < MIN_INLIERS:
        raise RealignError("no_consistent_motion", f"Only {inliers} consistent matches")
    return Realignment(np.asarray(matrix, dtype=np.float64), inliers, len(good))


def displacement(homography: NDArray[np.float64], points: NDArray[np.float64]) -> float:
    """Mean movement (px) of the given reference image points under the homography."""
    moved = cv2.perspectiveTransform(points.reshape(-1, 1, 2).astype(np.float64), homography)
    return float(np.mean(np.linalg.norm(moved.reshape(-1, 2) - points.reshape(-1, 2), axis=1)))
