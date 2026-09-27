import random
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from dartscore.api import create_app
from dartscore.config import Settings
from dartscore.game import Dart, create_game
from dartscore.game.cricket import CricketGame
from dartscore.game.x01 import X01Game
from dartscore.services.bot import BotService, aim_point, choose_target, sigma_for_average
from dartscore.vision.board import score_at


def test_sigma_decreases_with_level() -> None:
    sigmas = [sigma_for_average(a) for a in (25, 40, 60, 80, 100, 140)]
    assert sigmas == sorted(sigmas, reverse=True)
    assert 15 < sigma_for_average(60) < 18


@pytest.mark.parametrize("label", ["T20", "D16", "S5", "T19", "BULL", "25"])
def test_aim_point_lies_in_the_target(label: str) -> None:
    dart = Dart.parse(label)
    score = score_at(*aim_point(dart))
    if dart.segment == 25:
        assert score.segment == 25  # both bull rings are aimed at the centre
    else:
        assert (score.segment, score.multiplier) == (dart.segment, dart.multiplier)


def test_x01_targets() -> None:
    game = create_game("x01", 2, {"start_score": 501})
    assert isinstance(game, X01Game)
    assert choose_target(game).label == "T20"
    game.remaining[0] = 40
    assert choose_target(game).label == "D20"
    game.remaining[0] = 170
    assert choose_target(game).label == "T20"
    game.remaining[0] = 159  # no finish: score
    assert choose_target(game).label == "T20"


def test_cricket_closes_highest_open_number() -> None:
    game = create_game("cricket", 2, {})
    assert isinstance(game, CricketGame)
    assert choose_target(game).label == "T20"
    game.marks[0][20] = 3
    assert choose_target(game).label == "T19"


def test_average_roughly_matches_level() -> None:
    rng = random.Random(3)
    from dartscore.services.bot import throw_at

    sigma = sigma_for_average(60)
    darts = [throw_at(Dart(20, 3), sigma, rng)[0] for _ in range(6000)]
    average = 3 * sum(d.points for d in darts) / len(darts)
    assert 55 < average < 67


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    with TestClient(create_app(Settings(data_dir=tmp_path / "data"))) as c:
        c.app.state.bots.stop()  # type: ignore[attr-defined]
        yield c


def test_bot_plays_its_turn_and_ignores_the_camera(client: TestClient) -> None:
    bots: BotService = client.app.state.bots  # type: ignore[attr-defined]
    games = client.app.state.games  # type: ignore[attr-defined]
    created = client.post(
        "/api/games",
        json={"mode": "x01", "settings": {"start_score": 501},
              "players": [{"guest_name": "Me"}, {"bot_level": 60}]},
    )  # fmt: skip
    assert created.status_code == 201, created.text
    assert created.json()["players"][1]["bot_level"] == 60
    assert not bots.step()  # the human is up
    for label in ("T20", "T20", "T20"):
        client.post("/api/games/active/throws", json={"dart": label})
    games.next_turn(source="auto")  # darts pulled
    with pytest.raises(Exception, match="bot"):
        games.throw(Dart(20, 1), source="auto")
    for _ in range(3):
        assert bots.step()
    state = games.active_state()
    assert state["turn"]["player"] == 1
    assert state["turn_sources"] == ["bot", "bot", "bot"]
    assert bots.step()  # pulls its darts
    assert games.active_state()["current_player"] == 0
    assert not bots.step()


def test_bots_only_play_x01_and_cricket(client: TestClient) -> None:
    response = client.post(
        "/api/games", json={"mode": "shanghai", "players": [{"guest_name": "A"}, {"bot_level": 50}]}
    )
    assert response.status_code in (409, 422)
    assert response.json()["detail"]["code"] == "bot_mode"


def test_offset_is_relative_to_the_target() -> None:
    from dartscore.services.bot import offset_xy

    # at the top (T20): outward = up, clockwise = right
    x, y = offset_xy(Dart(20, 3), 5.0, 2.0)
    assert (round(x, 6), round(y, 6)) == (2.0, 5.0)
    # at the bottom (T3): outward = down, clockwise = left
    x, y = offset_xy(Dart(3, 3), 5.0, 2.0)
    assert (round(x, 6), round(y, 6)) == (-2.0, -5.0)


def test_personal_bot_takes_level_and_bias_from_the_player(client: TestClient) -> None:
    from dartscore.services.aim import personal_profile

    games = client.app.state.games  # type: ignore[attr-defined]
    pid = client.post("/api/players", json={"name": "Alex"}).json()["id"]
    client.post("/api/games", json={"mode": "x01", "settings": {"start_score": 501},
                                    "players": [{"player_id": pid}]})  # fmt: skip
    # 21 scoring darts, all 6 mm high and 2 mm left of the T20
    for i in range(21):
        # scored as a miss so the remaining score stays above 170 (the label does not matter)
        games.throw(Dart.miss(), source="auto", x_mm=-2.0, y_mm=109.0, confidence=0.9)
        if i % 3 == 2:
            games.next_turn()
    client.post("/api/games/active/abort")
    profile = personal_profile(client.app.state.sessions, pid, 60)  # type: ignore[attr-defined]
    assert profile.bias == (6.0, -2.0)
    assert profile.double_sigma is None  # no doubles data yet

    created = client.post(
        "/api/games",
        json={"mode": "x01", "settings": {"start_score": 501},
              "players": [{"player_id": pid}, {"bot_of": pid}], "abort_active": True},
    )  # fmt: skip
    assert created.status_code == 201, created.text
    bot = created.json()["players"][1]
    assert bot["name"] == "Alex (Bot)"
    assert bot["bot_of"] == pid
    assert bot["bot_level"] == 50  # no finished X01 game yet: default level
