from pathlib import Path

import pytest

from dartscore.config import CONFIG_ENV_VAR, load_settings

EXAMPLE_CONFIG = Path(__file__).parents[2] / "config.example.toml"


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(CONFIG_ENV_VAR, raising=False)
    monkeypatch.delenv("DARTSCORE_SERVER__PORT", raising=False)


def test_defaults_without_config_file() -> None:
    settings = load_settings()
    assert settings.server.port == 8000
    assert settings.cameras == []


def test_example_config_is_valid() -> None:
    settings = load_settings(EXAMPLE_CONFIG)
    assert len(settings.cameras) == 3
    assert {c.position_deg for c in settings.cameras} == {0.0, 120.0, 240.0}


def test_env_overrides_file(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DARTSCORE_SERVER__PORT", "9000")
    settings = load_settings(EXAMPLE_CONFIG)
    assert settings.server.port == 9000


def test_config_file_from_env_var(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    config = tmp_path / "custom.toml"
    config.write_text("[server]\nport = 8123\n")
    monkeypatch.setenv(CONFIG_ENV_VAR, str(config))
    assert load_settings().server.port == 8123


def test_unknown_keys_are_rejected(tmp_path: Path) -> None:
    config = tmp_path / "bad.toml"
    config.write_text("typo_key = 1\n")
    with pytest.raises(ValueError, match="typo_key"):
        load_settings(config)
