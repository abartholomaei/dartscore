import sys
from pathlib import Path

import pytest

from dartscore import cli, paths
from dartscore.config import CONFIG_ENV_VAR, load_settings


@pytest.fixture(autouse=True)
def isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(paths.HOME_ENV_VAR, raising=False)
    monkeypatch.delenv(CONFIG_ENV_VAR, raising=False)


def freeze(monkeypatch: pytest.MonkeyPatch, bundle: Path) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(bundle), raising=False)


def test_source_checkout_stays_in_the_current_directory() -> None:
    assert paths.app_home() is None
    assert load_settings().frontend_dir == Path("frontend/dist")


def test_release_build_uses_the_bundled_frontend(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    freeze(monkeypatch, tmp_path / "bundle")
    assert paths.app_home() == paths.default_home()
    assert load_settings().frontend_dir == tmp_path / "bundle" / "frontend"


@pytest.mark.parametrize(
    ("platform", "expected"),
    [
        ("linux", ".local/share/dartscore"),
        ("darwin", "Library/Application Support/dartscore"),
    ],
)
def test_default_home_per_platform(
    monkeypatch: pytest.MonkeyPatch, platform: str, expected: str
) -> None:
    monkeypatch.setattr(sys, "platform", platform)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    assert paths.default_home() == Path.home() / expected


def test_windows_home_is_in_local_appdata(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert paths.default_home() == tmp_path / "dartscore"


def test_first_start_creates_home_and_config(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "config.template.toml").write_text("[server]\nport = 8123\n")
    freeze(monkeypatch, bundle)
    home = tmp_path / "home"
    monkeypatch.setenv(paths.HOME_ENV_VAR, str(home))

    cli.enter_home()

    assert Path.cwd() == home.resolve()
    assert load_settings().server.port == 8123
    # an edited config is never overwritten
    (home / "config.toml").write_text("[server]\nport = 9000\n")
    cli.enter_home()
    assert load_settings().server.port == 9000


def test_launch_only_opens_the_browser_when_already_running(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    opened: list[str] = []
    monkeypatch.setattr(cli, "_dartscore_answers", lambda _url, timeout=1.0: True)
    monkeypatch.setattr("webbrowser.open", opened.append)
    monkeypatch.setattr(cli, "cmd_serve", lambda *_: pytest.fail("must not start a server"))

    cli.main(["launch"])

    assert opened == ["http://localhost:8000"]


def test_migrations_accept_percent_encoded_paths(tmp_path: Path) -> None:
    # str(engine.url) percent-encodes Windows paths (C%3A%5C...); alembic must not choke
    from dartscore.storage.db import alembic_config

    url = f"sqlite:///{tmp_path}/C%3A%5Cdata/dartscore.db"
    assert alembic_config(url).get_main_option("sqlalchemy.url") == url
