"""Team games: the game engine sees every team as one player with a shared score; the
members of a team take turns (team A: Alex, Maria, Alex, ...).

``teams`` is stored in the game settings as a list of member lists, each member being the
position of a game player (``GamePlayer.position``), e.g. [[0, 2], [1, 3]].
"""

from typing import Any

from dartscore.game.base import Game, GameError

MAX_TEAM_SIZE = 4


def teams_of(settings: dict[str, Any]) -> list[list[int]] | None:
    teams = settings.get("teams")
    return [list(map(int, team)) for team in teams] if teams else None


def engine_players(settings: dict[str, Any], members: int) -> int:
    """How many players the game engine plays with (teams, or everybody alone)."""
    teams = teams_of(settings)
    return len(teams) if teams else members


def validate_teams(teams: list[list[int]], members: int) -> list[list[int]]:
    flat = [m for team in teams for m in team]
    if len(teams) < 2:
        raise GameError("invalid_teams", "At least two teams are needed")
    if sorted(flat) != list(range(members)):
        raise GameError("invalid_teams", "Every player must be in exactly one team")
    if any(not 1 <= len(team) <= MAX_TEAM_SIZE for team in teams):
        raise GameError("invalid_teams", f"Teams have 1-{MAX_TEAM_SIZE} players")
    return [list(team) for team in teams]


def current_member(game: Game, teams: list[list[int]], team: int | None = None) -> int:
    """The member (game player position) of ``team`` (default: the team at the board) who
    throws the running or the next turn. Members rotate over the whole match."""
    team = game.current_player if team is None else team
    turns = sum(len(game.turns_of(team, leg)) for leg in game.legs)
    running = game.current_turn is not None and game.current_turn.player == team
    index = turns - 1 if running else turns
    members = teams[team]
    return members[index % len(members)]
