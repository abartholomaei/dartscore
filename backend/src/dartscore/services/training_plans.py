"""Training plans: multi-session programmes built from the practice modes, each drill with a
goal on the mode's own score (e.g. "Bob's 27: finish with 50 or more").

Plans are built in; a player works through one plan at a time. A drill is started as an
ordinary game, its result is recorded when that game ends. The next session opens once every
drill of the current one has been played (goals missed can be repeated but do not block).
"""

import threading
from collections.abc import Callable
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from dartscore.game import GameError
from dartscore.services.games import GameService, PlayerRef
from dartscore.storage.models import GamePlayer, GameRecord, Player, TrainingPlanRecord, utcnow

log = structlog.get_logger(__name__)


def _drill(mode: str, settings: dict[str, Any], goal: int) -> dict[str, Any]:
    """``goal``: the mode's score (player result) that counts as achieved."""
    return {"mode": mode, "settings": settings, "goal": goal}


# key -> sessions -> drills; the texts are translated in the web app (plans.<key>)
PLANS: dict[str, list[list[dict[str, Any]]]] = {
    "doubles_week": [
        [_drill("doubles_training", {"order": "sequential"}, 6), _drill("bobs_27", {}, 0)],
        [
            _drill(
                "segment_training", {"number": 16, "ring": "double", "end": "darts", "limit": 33}, 4
            ),
            _drill(
                "segment_training", {"number": 20, "ring": "double", "end": "darts", "limit": 33}, 4
            ),
        ],
        [_drill("doubles_training", {"order": "random"}, 7), _drill("bobs_27", {}, 20)],
        [
            _drill(
                "checkout_training",
                {"count": 10, "min_score": 2, "max_score": 40, "darts_per_target": 6},
                5,
            ),
            _drill(
                "segment_training", {"number": 0, "ring": "double", "end": "darts", "limit": 33}, 4
            ),
        ],
        [_drill("doubles_training", {"order": "random"}, 8), _drill("bobs_27", {}, 50)],
    ],
    "scoring": [
        [
            _drill("score_training", {"rounds": 10}, 450),
            _drill(
                "segment_training", {"number": 20, "ring": "triple", "end": "darts", "limit": 33}, 4
            ),
        ],
        [
            _drill("score_training", {"rounds": 10}, 500),
            _drill(
                "segment_training", {"number": 19, "ring": "triple", "end": "darts", "limit": 33}, 4
            ),
        ],
        [_drill("score_training", {"rounds": 20}, 1000), _drill("halve_it", {}, 150)],
        [
            _drill("score_training", {"rounds": 10}, 550),
            _drill(
                "segment_training",
                {"number": 20, "ring": "triple", "end": "darts", "limit": 66},
                10,
            ),
        ],
        [
            _drill("score_training", {"rounds": 20}, 1100),
            _drill("halve_it", {"targets": "bermuda"}, 200),
        ],
    ],
    "finishing": [
        [
            _drill(
                "checkout_training",
                {"count": 10, "min_score": 41, "max_score": 80, "darts_per_target": 9},
                5,
            ),
            _drill("checkout_121", {"attempts": 5}, 121),
        ],
        [
            _drill(
                "checkout_training",
                {"count": 10, "min_score": 2, "max_score": 40, "darts_per_target": 3},
                4,
            ),
            _drill(
                "segment_training", {"number": 25, "ring": "any", "end": "darts", "limit": 33}, 6
            ),
        ],
        [
            _drill(
                "checkout_training",
                {"count": 10, "min_score": 61, "max_score": 100, "darts_per_target": 9},
                4,
            ),
            _drill("checkout_121", {"attempts": 10}, 123),
        ],
        [
            _drill(
                "checkout_training",
                {"count": 10, "min_score": 81, "max_score": 120, "darts_per_target": 9},
                3,
            ),
            _drill("bobs_27", {}, 30),
        ],
        [
            _drill(
                "checkout_training",
                {"count": 10, "min_score": 41, "max_score": 120, "darts_per_target": 6},
                4,
            ),
            _drill("checkout_121", {"attempts": 10}, 125),
        ],
    ],
    "allround": [
        [
            _drill("around_the_clock", {"variant": "single"}, 21),
            _drill("shanghai", {"rounds": 7}, 60),
        ],
        [_drill("halve_it", {}, 120), _drill("doubles_training", {"order": "sequential"}, 5)],
        [
            _drill("around_the_clock", {"variant": "double", "include_bull": False}, 10),
            _drill("score_training", {"rounds": 10}, 450),
        ],
        [
            _drill("shanghai", {"rounds": 20}, 200),
            _drill(
                "checkout_training",
                {"count": 5, "min_score": 41, "max_score": 100, "darts_per_target": 9},
                2,
            ),
        ],
        [_drill("halve_it", {"targets": "bermuda"}, 150), _drill("bobs_27", {}, 10)],
    ],
}


class TrainingPlanService:
    def __init__(self, sessions: sessionmaker[Session], games: GameService) -> None:
        self._sessions = sessions
        self._games = games
        self._lock = threading.Lock()
        self.on_change: Callable[[], None] | None = None
        games.add_listener(self._on_game_event)

    @staticmethod
    def catalog() -> list[dict[str, Any]]:
        return [{"key": key, "sessions": sessions} for key, sessions in PLANS.items()]

    def current(self, player_id: int) -> dict[str, Any] | None:
        with self._sessions() as session:
            record = self._active(session, player_id)
            return self._view(record) if record else None

    def start(self, player_id: int, plan: str) -> dict[str, Any]:
        if plan not in PLANS:
            raise GameError("invalid_settings", f"Unknown plan {plan}")
        with self._sessions() as session:
            if session.get(Player, player_id) is None:
                raise GameError("player_not_found", f"Player {player_id} not found")
            old = self._active(session, player_id)
            if old is not None:
                old.status = "stopped"
            record = TrainingPlanRecord(player_id=player_id, plan=plan, status="active", results=[])
            session.add(record)
            session.commit()
            log.info("training_plan_started", player=player_id, plan=plan)
            return self._view(record)

    def stop(self, player_id: int) -> None:
        with self._sessions() as session:
            record = self._active(session, player_id)
            if record is not None:
                record.status = "stopped"
                session.commit()

    def start_drill(self, player_id: int, session_index: int, drill_index: int) -> dict[str, Any]:
        with self._lock, self._sessions() as session:
            record = self._active(session, player_id)
            if record is None:
                raise GameError("invalid_settings", "No training plan is running")
            view = self._view(record)
            if session_index > view["current_session"]:
                raise GameError("invalid_settings", "Finish the current session first")
            drill = self._drill(record.plan, session_index, drill_index)
            state = self._games.create(
                drill["mode"], dict(drill["settings"]), [PlayerRef(player_id)]
            )
            results = list(record.results)
            results.append(
                {"session": session_index, "drill": drill_index, "game_id": state["id"],
                 "score": None, "achieved": None}
            )  # fmt: skip
            record.results = results
            session.commit()
            return state

    # --- internals ------------------------------------------------------------------

    @staticmethod
    def _drill(plan: str, session_index: int, drill_index: int) -> dict[str, Any]:
        try:
            return PLANS[plan][session_index][drill_index]
        except (KeyError, IndexError) as exc:
            raise GameError("invalid_settings", "No such drill") from exc

    @staticmethod
    def _active(session: Session, player_id: int) -> TrainingPlanRecord | None:
        return session.scalars(
            select(TrainingPlanRecord)
            .where(TrainingPlanRecord.player_id == player_id, TrainingPlanRecord.status == "active")
            .order_by(TrainingPlanRecord.id.desc())
        ).first()

    def _view(self, record: TrainingPlanRecord) -> dict[str, Any]:
        sessions = PLANS[record.plan]
        done = {(r["session"], r["drill"]) for r in record.results if r["score"] is not None}
        best: dict[tuple[int, int], dict[str, Any]] = {}
        for r in record.results:
            if r["score"] is None:
                continue
            key = (r["session"], r["drill"])
            if key not in best or r["score"] > best[key]["score"]:
                best[key] = r
        current = next(
            (
                i
                for i, drills in enumerate(sessions)
                if any((i, d) not in done for d in range(len(drills)))
            ),
            len(sessions),
        )
        return {
            "id": record.id,
            "plan": record.plan,
            "status": record.status,
            "started_at": record.started_at.isoformat(),
            "current_session": current,
            "sessions": [
                [
                    drill
                    | {
                        "best": best.get((i, d), {}).get("score"),
                        "achieved": bool(best.get((i, d), {}).get("achieved")),
                        "played": sum(
                            1
                            for r in record.results
                            if (r["session"], r["drill"]) == (i, d) and r["score"] is not None
                        ),
                    }
                    for d, drill in enumerate(drills)
                ]
                for i, drills in enumerate(sessions)
            ],
        }

    def _on_game_event(self, event: str) -> None:
        if event != "change":
            return
        state = self._games.active_state()
        if not state or not state.get("finished"):
            return
        try:
            self._record(int(state["id"]))
        except Exception:
            log.exception("training_plan_result_failed")

    def _record(self, game_id: int) -> None:
        with self._lock, self._sessions() as session:
            gp = session.scalars(select(GamePlayer).where(GamePlayer.game_id == game_id)).first()
            game = session.get(GameRecord, game_id)
            if gp is None or gp.player_id is None or game is None:
                return
            record = self._active(session, gp.player_id)
            if record is None:
                return
            results = [dict(r) for r in record.results]
            entry = next(
                (r for r in results if r["game_id"] == game_id and r["score"] is None), None
            )
            if entry is None:
                return
            score = (gp.stats or {}).get("score")
            entry["score"] = int(score) if score is not None else 0
            goal = self._drill(record.plan, entry["session"], entry["drill"])["goal"]
            entry["achieved"] = entry["score"] >= goal
            record.results = results
            view = self._view(record)
            if view["current_session"] >= len(PLANS[record.plan]):
                record.status, record.finished_at = "finished", utcnow()
            session.commit()
            log.info("training_plan_result", player=gp.player_id, **entry)
            if self.on_change:
                self.on_change()
