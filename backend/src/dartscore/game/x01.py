"""X01 (301, 501, ...): count down to exactly zero."""

from dataclasses import dataclass
from typing import Any

from dartscore.game.base import Game, GameError, MatchSettings, Turn
from dartscore.game.checkout import InOutRule, is_valid_finisher, is_valid_opener, suggest_checkout
from dartscore.game.dart import Dart

START_SCORES = (101, 170, 301, 501, 701, 901, 1001)


@dataclass(frozen=True)
class X01Settings:
    start_score: int = 501
    in_rule: InOutRule = "single"
    out_rule: InOutRule = "double"

    def __post_init__(self) -> None:
        if self.start_score not in START_SCORES:
            raise GameError("invalid_settings", f"start_score must be one of {START_SCORES}")


class X01Game(Game):
    mode = "x01"

    def __init__(self, player_count: int, settings: X01Settings, match: MatchSettings) -> None:
        self.settings = settings
        super().__init__(player_count, match)

    def _start_leg(self) -> None:
        self.remaining = [self.settings.start_score] * self.player_count
        self.opened = [self.settings.in_rule == "single"] * self.player_count

    def _score_dart(self, turn: Turn, dart: Dart) -> None:
        p = turn.player
        if not self.opened[p]:
            if not is_valid_opener(dart, self.settings.in_rule):
                turn.values.append(0)
                return
            self.opened[p] = True

        new = self.remaining[p] - dart.points
        min_left = 1 if self.settings.out_rule == "single" else 2
        busted = new < 0 or 0 < new < min_left
        if new == 0 and not is_valid_finisher(dart, self.settings.out_rule):
            busted = True
        turn.values.append(dart.points)
        if busted:
            turn.bust = True
            # back to the score at the start of the turn
            self.remaining[p] += sum(turn.values[:-1])
            return
        self.remaining[p] = new
        if new == 0:
            turn.checkout = True

    def checkout_suggestion(self) -> list[str] | None:
        p = self.current_player
        turn = self.current_turn
        darts_left = 3 - (len(turn.darts) if turn else 0)
        if not self.opened[p] or self.finished:
            return None
        route = suggest_checkout(self.remaining[p], darts_left, self.settings.out_rule)
        return [d.label for d in route] if route else None

    def _leg_state(self) -> dict[str, Any]:
        return {
            "remaining": list(self.remaining),
            "opened": list(self.opened),
            "checkout": self.checkout_suggestion(),
        }

    def settings_dict(self) -> dict[str, Any]:
        return {
            "start_score": self.settings.start_score,
            "in_rule": self.settings.in_rule,
            "out_rule": self.settings.out_rule,
            "legs_to_win": self.match.legs_to_win,
            "sets_to_win": self.match.sets_to_win,
        }
