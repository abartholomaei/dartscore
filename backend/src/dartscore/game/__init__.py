"""Game logic: game modes, rules, turns, undo - independent of UI and detection."""

from typing import Any

from dartscore.game.base import DartEvent, Event, Game, GameError, MatchSettings, NextEvent
from dartscore.game.cricket import CricketGame, CricketSettings
from dartscore.game.dart import Dart
from dartscore.game.party import (
    GotchaGame,
    GotchaSettings,
    HalveItGame,
    HalveItSettings,
    KillerGame,
    KillerSettings,
    ScoreTrainingGame,
    ScoreTrainingSettings,
)
from dartscore.game.practice import (
    Checkout121Game,
    Checkout121Settings,
    SegmentTrainingGame,
    SegmentTrainingSettings,
)
from dartscore.game.training import (
    AroundTheClockGame,
    AroundTheClockSettings,
    BobsGame,
    BobsSettings,
    BullOffGame,
    CheckoutTrainingGame,
    CheckoutTrainingSettings,
    DoublesTrainingGame,
    DoublesTrainingSettings,
    ShanghaiGame,
    ShanghaiSettings,
)
from dartscore.game.x01 import X01Game, X01Settings

MODES = (
    "x01",
    "cricket",
    "around_the_clock",
    "shanghai",
    "bobs_27",
    "checkout_training",
    "doubles_training",
    "bull_off",
    "killer",
    "halve_it",
    "gotcha",
    "score_training",
    "segment_training",
    "checkout_121",
)

__all__ = [
    "MODES",
    "Dart",
    "DartEvent",
    "Event",
    "Game",
    "GameError",
    "NextEvent",
    "create_game",
    "replay_game",
]


def create_game(mode: str, player_count: int, settings: dict[str, Any]) -> Game:
    """Creates a game from stored/requested settings (unknown keys are rejected)."""
    options = dict(settings)
    try:
        match = MatchSettings(
            legs_to_win=int(options.pop("legs_to_win", 1)),
            sets_to_win=int(options.pop("sets_to_win", 1)),
        )
        if mode == "x01":
            return X01Game(player_count, X01Settings(**options), match)
        if mode == "cricket":
            return CricketGame(player_count, CricketSettings(**options), match)
        # training modes are played as a single leg
        if mode == "around_the_clock":
            return AroundTheClockGame(player_count, AroundTheClockSettings(**options))
        if mode == "shanghai":
            return ShanghaiGame(player_count, ShanghaiSettings(**options))
        if mode == "bobs_27":
            return BobsGame(player_count, BobsSettings(**options))
        if mode == "checkout_training":
            return CheckoutTrainingGame(player_count, CheckoutTrainingSettings(**options))
        if mode == "segment_training":
            return SegmentTrainingGame(player_count, SegmentTrainingSettings(**options))
        if mode == "checkout_121":
            return Checkout121Game(player_count, Checkout121Settings(**options))
        if mode == "killer":
            return KillerGame(player_count, KillerSettings(**options))
        if mode == "halve_it":
            return HalveItGame(player_count, HalveItSettings(**options))
        if mode == "gotcha":
            return GotchaGame(player_count, GotchaSettings(**options))
        if mode == "score_training":
            return ScoreTrainingGame(player_count, ScoreTrainingSettings(**options))
        if mode == "bull_off":
            return BullOffGame(player_count)
        if mode == "doubles_training":
            return DoublesTrainingGame(player_count, DoublesTrainingSettings(**options))
    except TypeError as exc:
        raise GameError("invalid_settings", str(exc)) from exc
    raise GameError("unknown_mode", f"Unknown game mode: {mode}")


def replay_game(
    mode: str, player_count: int, settings: dict[str, Any], events: list[Event]
) -> Game:
    game = create_game(mode, player_count, settings)
    game.events = list(events)
    game._replay()
    return game
