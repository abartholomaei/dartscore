import math

import numpy as np
import pytest

from dartscore.config import CameraConfig, DetectionConfig
from dartscore.vision import board
from dartscore.vision.calibration import BoardCalibration
from dartscore.vision.detection import (
    CameraView,
    DartDetection,
    DartDetector,
    DetectorState,
    Takeout,
    locate,
)
from dartscore.vision.model import Keypoint
from dartscore.vision.sources import SimulatedBoard, SyntheticSource

STEP = 1 / 15


class Rig:
    """Three simulated cameras around one simulated board, driven with a fake clock."""

    def __init__(self) -> None:
        self.board = SimulatedBoard()
        self.sources = {
            f"cam{i + 1}": SyntheticSource(
                CameraConfig(id=f"cam{i + 1}", source="synthetic", position_deg=i * 120),
                self.board,
            )
            for i in range(3)
        }
        calibrations = {
            cid: BoardCalibration(cid, {}, src.board_homography(), (1280, 720), False, None, 0.0)
            for cid, src in self.sources.items()
        }
        self.detector = DartDetector(DetectionConfig(), calibrations, {})
        self.now = 0.0

    def step(self, seconds: float) -> list[object]:
        events: list[object] = []
        for _ in range(max(1, round(seconds / STEP))):
            self.now += STEP
            frames = {cid: src.render() for cid, src in self.sources.items()}
            events += self.detector.process(frames, self.now)
        return events

    def throw(self, x: float, y: float) -> list[object]:
        self.board.darts.append((x, y))
        return self.step(1.0)


def polar(r: float, deg_from_top: float) -> tuple[float, float]:
    a = math.radians(90 - deg_from_top)
    return r * math.cos(a), r * math.sin(a)


@pytest.fixture
def rig() -> Rig:
    rig = Rig()
    rig.step(0.5)  # references
    return rig


def test_detects_single_dart(rig: Rig) -> None:
    events = rig.throw(0, 103)  # triple 20
    darts = [e for e in events if isinstance(e, DartDetection)]
    assert len(darts) == 1
    dart = darts[0]
    assert dart.label == "T20"
    assert math.hypot(dart.x_mm - 0, dart.y_mm - 103) < 4
    assert sum(h.used for h in dart.hits) >= 2
    assert rig.detector.state == DetectorState.IDLE


@pytest.mark.parametrize(
    ("r", "deg", "label"),
    [
        (50, 0, "S20"),
        (166, 90, "D6"),
        (103, 180, "T3"),
        (0, 0, "BULL"),
        (60, 234, "S16"),
    ],
)
def test_detects_fields_around_the_board(rig: Rig, r: float, deg: float, label: str) -> None:
    events = rig.throw(*polar(r, deg))
    darts = [e for e in events if isinstance(e, DartDetection)]
    assert [d.label for d in darts] == [label]


def test_three_darts_then_takeout(rig: Rig) -> None:
    labels = []
    for pos in [(0, 60), polar(60, 18), polar(60, 342)]:
        labels += [e.label for e in rig.throw(*pos) if isinstance(e, DartDetection)]
    assert labels == ["S20", "S1", "S5"]
    assert rig.detector.darts_in_turn == 3

    # hand comes in, darts are pulled, hand leaves
    rig.board.hand = True
    assert rig.step(1.0) == []
    assert rig.detector.state == DetectorState.BLOCKED
    rig.board.darts.clear()
    rig.step(0.5)
    rig.board.hand = False
    events = rig.step(1.0)
    assert any(isinstance(e, Takeout) for e in events)
    assert rig.detector.darts_in_turn == 0


def test_darts_pulled_one_by_one_are_not_new_darts(rig: Rig) -> None:
    rig.throw(0, 60)
    rig.throw(*polar(60, 90))
    rig.board.darts.pop()  # one dart removed without a hand in view
    events = rig.step(1.0)
    assert not any(isinstance(e, DartDetection) for e in events)
    rig.board.darts.pop()
    events = rig.step(1.0)
    assert any(isinstance(e, Takeout) for e in events)


def test_bounce_out_produces_nothing(rig: Rig) -> None:
    rig.board.darts.append((0, 60))
    rig.step(STEP)  # visible for a single frame
    rig.board.darts.pop()
    events = rig.step(1.0)
    assert events == []
    assert rig.detector.darts_in_turn == 0


def test_miss_outside_double_ring(rig: Rig) -> None:
    events = rig.throw(*polar(190, 45))
    darts = [e for e in events if isinstance(e, DartDetection)]
    assert [d.label for d in darts] == ["MISS"]


def test_fuse_drops_outlier() -> None:
    from dartscore.vision.detection import CameraHit, fuse

    hits = [
        CameraHit("a", (0, 0), (10.0, 10.0), 100),
        CameraHit("b", (0, 0), (11.0, 10.0), 100),
        CameraHit("c", (0, 0), (60.0, 10.0), 100),
    ]
    x, y, confidence, marked = fuse(hits, 12.0, 3)
    assert x == pytest.approx(10.5)
    assert y == pytest.approx(10.0)
    assert [h.used for h in marked] == [True, True, False]
    assert 0 < confidence < 1


def test_tip_is_lowest_point_of_the_dart() -> None:
    from dartscore.vision.detection import find_dart_tip

    reference = np.full((200, 200), 50, np.uint8)
    current = reference.copy()
    # a slanted "dart" from (100, 150) up to (110, 90)
    for t in np.linspace(0, 1, 200):
        x, y = int(100 + 10 * t), int(150 - 60 * t)
        current[y - 1 : y + 2, x - 1 : x + 2] = 230
    mask = np.full_like(reference, 255)
    found = find_dart_tip(reference, current, mask, 28, 20)
    assert found is not None
    (tx, ty), _ = found
    assert abs(tx - 100) < 3
    assert abs(ty - 150) < 3
    assert board.score_at(0, 0).label == "BULL"


def test_recovers_after_light_change(rig: Rig) -> None:
    # the light changes for good: a big lasting change without motion afterwards
    rig.board.light = 0.8
    rig.step(1.0)
    blocked = rig.detector.state
    rig.step(9.0)
    recovered = rig.detector.state
    assert (blocked, recovered) == (DetectorState.BLOCKED, DetectorState.IDLE)
    # the new view is the empty board: throwing works again (on a dark field: the simulated
    # dart is light and hard to see on cream fields in dimmed light)
    events = rig.throw(0, 60)
    assert [e.label for e in events if isinstance(e, DartDetection)] == ["S20"]


def _spoil_empty_reference(rig: Rig) -> None:
    """The stored empty board differs a little from the real one (e.g. taken at a restart
    while someone stood at the board): comparing with it alone never finds the board empty."""
    for cam in rig.detector._cameras.values():
        assert cam.empty_small is not None
        assert cam.mask_small is not None
        ys, xs = np.nonzero(cam.mask_small)
        y, x = int(ys.mean()), int(xs.min()) + 10  # a small spot inside the board area
        cam.empty_small = cam.empty_small.copy()
        cam.empty_small[y : y + 6, x : x + 6] = 255 - cam.empty_small[y : y + 6, x : x + 6]


@pytest.mark.parametrize("with_hand", [True, False])
def test_takeout_with_a_stale_empty_reference(rig: Rig, with_hand: bool) -> None:
    for turn in range(2):
        _spoil_empty_reference(rig)
        for pos in [(0, 60), polar(60, 18), polar(60, 342)]:
            rig.throw(*pos)
        assert rig.detector.darts_in_turn == 3
        rig.board.hand = with_hand
        if with_hand:
            rig.step(1.0)
        rig.board.darts.clear()
        events = rig.step(0.5)
        rig.board.hand = False
        events += rig.step(1.0)
        assert sum(isinstance(e, Takeout) for e in events) == 1, f"turn {turn}"
        assert rig.detector.darts_in_turn == 0


class _FakeModel:
    """Finds one tip at a fixed pixel in every image and counts how often it was asked."""

    def __init__(self, tip: tuple[float, float]) -> None:
        self.tip = tip
        self.calls = 0

    def tips(self, image: object) -> list[Keypoint]:
        self.calls += 1
        return [Keypoint(0, self.tip[0], self.tip[1], 0.9)]


def _views(tips: list[tuple[float, float] | None]) -> list[CameraView]:
    image = np.zeros((720, 1280, 3), np.uint8)
    homography = np.eye(3)
    return [
        CameraView(
            f"cam{i}",
            BoardCalibration(f"cam{i}", {}, homography, (1280, 720), False, None, 0.0),
            image,
            None if tip is None else (tip, 100),
        )
        for i, tip in enumerate(tips)
    ]


def test_locate_skips_the_model_when_the_classic_result_is_confident() -> None:
    model = _FakeModel((50.0, 50.0))
    config = DetectionConfig(model_below_confidence=0.7)
    located = locate(
        _views([(10.0, 10.0), (10.5, 10.0), (10.0, 10.5)]),
        config,
        3,
        model,  # type: ignore[arg-type]
    )
    assert located is not None
    x, y, confidence, _ = located
    assert confidence >= 0.7
    assert model.calls == 0
    assert (x, y) == pytest.approx((10.17, 10.17), abs=0.1)


def test_locate_asks_the_model_when_cameras_disagree() -> None:
    # the model tip is near the classic tip of every camera, so all three agree afterwards
    model = _FakeModel((12.0, 12.0))
    config = DetectionConfig(model_below_confidence=0.7)
    located = locate(
        _views([(10.0, 10.0), (40.0, 10.0), (10.0, 40.0)]),
        config,
        3,
        model,  # type: ignore[arg-type]
    )
    assert located is not None
    _, _, confidence, hits = located
    assert model.calls == 3
    assert confidence > 0.7
    assert all(h.used for h in hits)
