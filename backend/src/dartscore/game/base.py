"""Shared game flow: players, turns of up to three darts, legs, sets, undo.

A game is event sourced: it is fully described by its settings and the list of events
(darts thrown and "next player" actions). Undo and corrections simply change the event list
and replay it, so the game state can never drift out of sync with what is stored.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar, Literal

from dartscore.game.dart import Dart

DARTS_PER_TURN = 3


class GameError(ValueError):
    """``code`` is stable and translated by the UI."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class DartEvent:
    dart: Dart
    kind: Literal["dart"] = "dart"
    # where the dart landed on the board (mm, x right, y up) if known (camera detection);
    # only arcade modes use it, all others score by field
    position: tuple[float, float] | None = None


@dataclass(frozen=True)
class NextEvent:
    """Darts pulled / next player. Missing darts of an unfinished turn count as misses."""

    kind: Literal["next"] = "next"


Event = DartEvent | NextEvent


# eq=False: turns are compared by identity; two turns with the same darts are still different
# turns (list.index() would otherwise find the wrong one)
@dataclass(eq=False)
class Turn:
    player: int
    darts: list[Dart] = field(default_factory=list)
    # per dart: points (X01, 0 if not counted) or marks (Cricket)
    values: list[int] = field(default_factory=list)
    # darts filled in as misses because the turn ended early
    implicit_misses: int = 0
    bust: bool = False
    # this turn won the leg
    checkout: bool = False
    # the turn ends before three darts without winning (training modes, e.g. target reached)
    stop: bool = False
    # no further darts accepted until the next player
    closed: bool = False
    # board position (mm) per dart, None if unknown (see DartEvent.position)
    positions: list[tuple[float, float] | None] = field(default_factory=list)

    @property
    def total(self) -> int:
        return 0 if self.bust else sum(self.values)


@dataclass
class Leg:
    number: int
    set_number: int
    starter: int
    turns: list[Turn] = field(default_factory=list)
    winner: int | None = None


@dataclass(frozen=True)
class MatchSettings:
    legs_to_win: int = 1
    sets_to_win: int = 1

    def __post_init__(self) -> None:
        if not 1 <= self.legs_to_win <= 21 or not 1 <= self.sets_to_win <= 13:
            raise GameError("invalid_settings", "legs_to_win must be 1-21, sets_to_win 1-13")


class Game(ABC):
    mode: ClassVar[str]
    min_players: ClassVar[int] = 1
    max_players: ClassVar[int] = 8

    def __init__(self, player_count: int, match: MatchSettings) -> None:
        if not self.min_players <= player_count <= self.max_players:
            raise GameError(
                "invalid_player_count",
                f"{self.mode} needs {self.min_players}-{self.max_players} players",
            )
        self.player_count = player_count
        self.match = match
        self.events: list[Event] = []
        self._reset()

    # --- mode specific ------------------------------------------------------------------

    @abstractmethod
    def _start_leg(self) -> None:
        """Reset the per-leg state (scores, marks)."""

    @abstractmethod
    def _score_dart(self, turn: Turn, dart: Dart) -> None:
        """Apply a dart to the leg state: append the value to ``turn.values`` and set
        ``turn.bust`` / ``turn.checkout`` as needed."""

    def _after_turn(self, turn: Turn) -> int | None:
        """Called when a turn is complete (three darts, bust or next player). Modes can settle
        per-turn scores here; returning a player index ends the leg with that winner."""
        return None

    def _next_player(self, player: int) -> int:
        """Who throws after ``player``; modes with eliminated players skip them."""
        return (player + 1) % self.player_count

    def player_result(self, player: int) -> dict[str, int]:
        """Mode specific result of a player for statistics (score, hits); empty by default."""
        return {}

    def turns_of(self, player: int, leg: Leg | None = None) -> list[Turn]:
        return [t for t in (leg or self.legs[-1]).turns if t.player == player]

    @abstractmethod
    def _leg_state(self) -> dict[str, Any]:
        """Mode specific part of the state for the UI."""

    @abstractmethod
    def settings_dict(self) -> dict[str, Any]:
        """Settings needed to recreate this game (stored with it)."""

    # --- public API ---------------------------------------------------------------------

    @property
    def finished(self) -> bool:
        return self.winner is not None

    @property
    def turn_complete(self) -> bool:
        """The turn is complete and the darts still have to be pulled."""
        return self._awaiting_next

    @property
    def current_turn(self) -> Turn | None:
        leg = self.legs[-1]
        return leg.turns[-1] if leg.turns and not leg.turns[-1].closed else None

    def throw(self, dart: Dart, position: tuple[float, float] | None = None) -> None:
        event = DartEvent(dart, position=position)
        self._apply(event)
        self.events.append(event)

    def next_turn(self) -> None:
        self._apply(NextEvent())
        self.events.append(NextEvent())

    def undo(self) -> Event:
        if not self.events:
            raise GameError("nothing_to_undo", "Nothing to undo")
        event = self.events.pop()
        self._replay()
        return event

    def dart_event_index(self, turn_index: int, dart_index: int) -> int:
        """Position in ``events`` of the ``dart_index``-th dart of the ``turn_index``-th turn of
        the current leg (negative indices count from the end)."""
        leg = self.legs[-1]
        try:
            turn = leg.turns[turn_index]
            _ = turn.darts[dart_index]
        except IndexError as exc:
            raise GameError("no_such_dart", "No such dart in the current leg") from exc
        if dart_index < 0:
            dart_index += len(turn.darts)
        if dart_index >= len(turn.darts) - turn.implicit_misses:
            raise GameError("no_such_dart", "Implicit misses cannot be corrected")
        return self._event_position(leg, leg.turns.index(turn), dart_index)

    def replace_dart(self, turn_index: int, dart_index: int, dart: Dart) -> int:
        """Correct a dart (see ``dart_event_index``); returns its position in ``events``."""
        position = self.dart_event_index(turn_index, dart_index)
        backup = list(self.events)
        self.events[position] = DartEvent(dart)
        try:
            self._replay()
        except GameError:
            self.events = backup
            self._replay()
            raise
        return position

    def state(self) -> dict[str, Any]:
        leg = self.legs[-1]
        # right after a leg was won, show its final turn until the darts are pulled
        shown_leg = self.legs[-2] if self._leg_break and len(self.legs) > 1 else leg
        if self.finished:
            shown_leg = leg
        turn = shown_leg.turns[-1] if shown_leg.turns else None
        return {
            "mode": self.mode,
            "settings": self.settings_dict(),
            "player_count": self.player_count,
            "current_player": self.current_player,
            "leg": leg.number,
            "set": leg.set_number,
            "legs_won": list(self.legs_won),
            "sets_won": list(self.sets_won),
            "turn": None
            if turn is None
            else {
                "player": turn.player,
                "darts": [d.label for d in turn.darts],
                "values": list(turn.values),
                "bust": turn.bust,
                "checkout": turn.checkout,
                "closed": turn.closed,
            },
            "awaiting_next": self._awaiting_next or (self._leg_break and not self.finished),
            "leg_winner": shown_leg.winner,
            "finished": self.finished,
            "winner": self.winner,
            **self._leg_state(),
        }

    # --- internals ----------------------------------------------------------------------

    def _reset(self) -> None:
        # True between a won leg and the next action (darts pulled or first dart of next leg)
        self._leg_break = False
        # the current turn is complete (3 darts or bust), waiting for "next"
        self._awaiting_next = False
        self.legs: list[Leg] = []
        self.legs_won = [0] * self.player_count
        self.sets_won = [0] * self.player_count
        self.winner: int | None = None
        self._new_leg(starter=0, set_number=1)

    def _replay(self) -> None:
        self._reset()
        for event in self.events:
            self._apply(event)

    def _new_leg(self, starter: int, set_number: int) -> None:
        number = sum(1 for leg in self.legs if leg.set_number == set_number) + 1
        self.legs.append(Leg(number=number, set_number=set_number, starter=starter))
        self.current_player = starter
        self._start_leg()

    def _apply(self, event: Event) -> None:
        if self.finished:
            raise GameError("game_finished", "The game is already finished")
        leg = self.legs[-1]
        if self._leg_break:
            self._leg_break = False
            if isinstance(event, NextEvent):
                # darts pulled after the winning turn; the next leg is already set up
                return
        if isinstance(event, DartEvent):
            if self._awaiting_next:
                raise GameError("turn_closed", "Turn complete - pull the darts first")
            turn = self.current_turn
            if turn is None:
                turn = Turn(player=self.current_player)
                leg.turns.append(turn)
            turn.darts.append(event.dart)
            turn.positions.append(event.position)
            self._score_dart(turn, event.dart)
            if turn.checkout:
                leg.winner = turn.player
            if turn.bust or turn.checkout or turn.stop or len(turn.darts) >= DARTS_PER_TURN:
                turn.closed = True
                self._awaiting_next = True
                if leg.winner is None:
                    winner = self._after_turn(turn)
                    if winner is not None:
                        leg.winner = winner
            if leg.winner is not None:
                self._awaiting_next = False
                self._finish_leg(leg)
            return

        # next player
        turn = self.current_turn
        if turn is None and not self._awaiting_next:
            # nobody threw: the whole turn counts as three misses
            turn = Turn(player=self.current_player)
            leg.turns.append(turn)
        if turn is not None:
            while len(turn.darts) < DARTS_PER_TURN and not turn.closed:
                turn.darts.append(Dart.miss())
                turn.positions.append(None)
                turn.implicit_misses += 1
                self._score_dart(turn, Dart.miss())
                if turn.bust or turn.checkout or turn.stop:
                    break
            if not turn.closed:
                turn.closed = True
                winner = turn.player if turn.checkout else self._after_turn(turn)
                if winner is not None:
                    leg.winner = winner
                    self._awaiting_next = False
                    self._finish_leg(leg)
                    return
        self._awaiting_next = False
        self.current_player = self._next_player(self.current_player)

    def _finish_leg(self, leg: Leg) -> None:
        assert leg.winner is not None
        self.legs_won[leg.winner] += 1
        set_number = leg.set_number
        if self.legs_won[leg.winner] >= self.match.legs_to_win:
            self.sets_won[leg.winner] += 1
            if self.sets_won[leg.winner] >= self.match.sets_to_win:
                self.winner = leg.winner
                return
            self.legs_won = [0] * self.player_count
            set_number += 1
        # the starting player rotates every leg (and continues across sets)
        self._new_leg((leg.starter + 1) % self.player_count, set_number)
        self._leg_break = True

    def _event_position(self, leg: Leg, turn_index: int, dart_index: int) -> int:
        """Index in ``self.events`` of a dart, found by replaying and counting."""
        target = (self.legs.index(leg), turn_index, dart_index)
        self._reset()
        for position, event in enumerate(self.events):
            if isinstance(event, DartEvent):
                cur_leg = self.legs[-1]
                turn = self.current_turn
                t_index = len(cur_leg.turns) - 1 if turn is not None else len(cur_leg.turns)
                d_index = len(turn.darts) if turn is not None else 0
                if (len(self.legs) - 1, t_index, d_index) == target:
                    self._replay()
                    return position
            self._apply(event)
        self._replay()
        raise GameError("no_such_dart", "Dart not found")
