"""Konfiguration aus TOML-Datei und Umgebungsvariablen.

Priorität (höchste zuerst): Umgebungsvariablen (``DARTSCORE_…``, verschachtelt mit ``__``,
z. B. ``DARTSCORE_SERVER__PORT=9000``) > Konfigurationsdatei > Standardwerte.
"""

import os
import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator
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
    id: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    # "device" = echte Kamera, "synthetic" = simulierte Kamera für Entwicklung ohne Hardware
    source: Literal["device", "synthetic"] = "device"
    # Gerätepfad (z. B. /dev/v4l/by-path/...) oder OpenCV-Index als String
    device: str = ""
    width: int = 1280
    height: int = 720
    fps: int = 30
    fourcc: str = Field(default="MJPG", min_length=4, max_length=4)
    # Montageposition um die Scheibe in Grad (0 = oben, im Uhrzeigersinn)
    position_deg: float = 0.0
    # Nur Linux: Kamera-Controls, die per v4l2-ctl gesetzt werden, z. B.
    # {auto_exposure = 1, exposure_time_absolute = 150}. Namen: `v4l2-ctl -d <gerät> -l`
    v4l2_controls: dict[str, int] = {}

    @model_validator(mode="after")
    def device_required(self) -> "CameraConfig":
        if self.source == "device" and not self.device:
            raise ValueError(f"Kamera {self.id}: 'device' fehlt")
        return self


class StreamConfig(BaseModel):
    """Vorschau-Streams für den Browser (kostet CPU fürs JPEG-Kodieren)."""

    max_fps: int = Field(default=10, ge=1, le=30)
    default_width: int = Field(default=640, ge=160, le=1920)
    jpeg_quality: int = Field(default=75, ge=30, le=95)


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
    # gebautes Frontend (npm run build); wird vom Backend mit ausgeliefert, falls vorhanden
    frontend_dir: Path = Path("frontend/dist")
    server: ServerConfig = ServerConfig()
    logging: LoggingConfig = LoggingConfig()
    stream: StreamConfig = StreamConfig()
    cameras: list[CameraConfig] = []

    @field_validator("cameras")
    @classmethod
    def unique_camera_ids(cls, cameras: list[CameraConfig]) -> list[CameraConfig]:
        ids = [c.id for c in cameras]
        if len(ids) != len(set(ids)):
            raise ValueError(f"Kamera-IDs müssen eindeutig sein: {ids}")
        return cameras

    @property
    def calibration_dir(self) -> Path:
        return self.data_dir / "calibration"

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
