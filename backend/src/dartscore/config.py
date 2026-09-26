"""Konfiguration aus TOML-Datei und Umgebungsvariablen.

Priorität (höchste zuerst): Umgebungsvariablen (``DARTSCORE_…``, verschachtelt mit ``__``,
z. B. ``DARTSCORE_SERVER__PORT=9000``) > Konfigurationsdatei > Standardwerte.
"""

import os
import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

CONFIG_ENV_VAR = "DARTSCORE_CONFIG"
DEFAULT_CONFIG_FILE = Path("config.toml")


class ServerConfig(BaseModel):
    # 0.0.0.0, damit Handy/Tablet/TV im Heimnetz zugreifen können
    host: str = "0.0.0.0"
    port: int = Field(default=8000, ge=1, le=65535)


class CameraConfig(BaseModel):
    id: str
    # Gerätepfad (z. B. /dev/v4l/by-id/...) oder OpenCV-Index als String
    device: str
    width: int = 1280
    height: int = 720
    fps: int = 30
    fourcc: str = Field(default="MJPG", min_length=4, max_length=4)
    # Montageposition um die Scheibe in Grad (0 = oben, im Uhrzeigersinn)
    position_deg: float = 0.0


class LoggingConfig(BaseModel):
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    json_output: bool = False


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="DARTSCORE_",
        env_nested_delimiter="__",
        extra="forbid",
    )

    data_dir: Path = Path("data")
    server: ServerConfig = ServerConfig()
    logging: LoggingConfig = LoggingConfig()
    cameras: list[CameraConfig] = []

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # Werte aus der TOML-Datei kommen als init-Argumente; Umgebung soll sie überschreiben.
        return env_settings, init_settings


def resolve_config_file(explicit: Path | None = None) -> Path | None:
    """Findet die Konfigurationsdatei: CLI-Argument > DARTSCORE_CONFIG > ./config.toml."""
    if explicit is not None:
        return explicit
    if env_path := os.environ.get(CONFIG_ENV_VAR):
        return Path(env_path)
    if DEFAULT_CONFIG_FILE.is_file():
        return DEFAULT_CONFIG_FILE
    return None


def load_settings(config_file: Path | None = None) -> Settings:
    path = resolve_config_file(config_file)
    values = {}
    if path is not None:
        with path.open("rb") as f:
            values = tomllib.load(f)
    return Settings(**values)
