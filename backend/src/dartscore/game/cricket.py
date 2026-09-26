"""Cricket: close 15-20 and the bull, score on numbers the opponents have not closed."""

from dataclasses import dataclass
from typing import Any, Literal

from dartscore.game.base import Game, MatchSettings, Turn
from dartscore.game.dart import BULL, Dart

TARGETS = (20, 19, 18, 17, 16, 15, BULL)
MARKS_TO_CLOSE = 3

CricketVariant = Literal["standard", "cut_throat", "no_score"]


@dataclass(frozen=True)
class CricketSettings:
    variant: CricketVariant = "standard"


class CricketGame(Game):
    mode = "cricket"

    def __init__(self, player_count: int, settings: CricketSettings, match: MatchSettings) -> None:
        self.settings = settings
        super().__init__(player_count, match)

    def _start_leg(self) -> None:
        self.marks = [dict.fromkeys(TARGETS, 0) for _ in range(self.player_count)]
        self.points = [0] * self.player_count

    def _closed_by_all_others(self, player: int, target: int) -> bool:
        return all(
            self.marks[q][target] >= MARKS_TO_CLOSE for q in range(self.player_count) if q != player
        )

    def _score_dart(self, turn: Turn, dart: Dart) -> None:
        p = turn.player
        if dart.segment not in TARGETS:
            turn.values.append(0)
        else:
            target = dart.segment
            hits = dart.multiplier
            turn.values.append(hits)
            new_marks = self.marks[p][target] + hits
            extra = max(0, new_marks - max(MARKS_TO_CLOSE, self.marks[p][target]))
            self.marks[p][target] = min(new_marks, MARKS_TO_CLOSE)
            if extra and not self._closed_by_all_others(p, target):
                self._add_points(p, target, extra * target)

        if self._has_won(p):
            turn.checkout = True

    def _add_points(self, player: int, target: int, points: int) -> None:
        variant = self.settings.variant
        if variant == "standard":
            self.points[player] += points
        elif variant == "cut_throat":
            for q in range(self.player_count):
                if q != player and self.marks[q][target] < MARKS_TO_CLOSE:
                    self.points[q] += points

    def _has_won(self, player: int) -> bool:
        if any(self.marks[player][t] < MARKS_TO_CLOSE for t in TARGETS):
            return False
        others = [self.points[q] for q in range(self.player_count) if q != player]
        if not others or self.settings.variant == "no_score":
            return True
        if self.settings.variant == "cut_throat":
            return self.points[player] <= min(others)
        return self.points[player] >= max(others)

    def _leg_state(self) -> dict[str, Any]:
        return {
            "targets": list(TARGETS),
            "marks": [[m[t] for t in TARGETS] for m in self.marks],
            "points": list(self.points),
        }

    def settings_dict(self) -> dict[str, Any]:
        return {
            "variant": self.settings.variant,
            "legs_to_win": self.match.legs_to_win,
            "sets_to_win": self.match.sets_to_win,
        }
