"""Configuration from a TOML file and environment variables.

Precedence (highest first): environment variables (``DARTSCORE_...``, nested with ``__``,
e.g. ``DARTSCORE_SERVER__PORT=9000``) > config file > defaults.
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
    # 0.0.0.0 so phones/tablets/TVs on the home network can connect
    host: str = "0.0.0.0"
    port: int = Field(default=8000, ge=1, le=65535)


class CameraConfig(BaseModel):
    id: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    # "device" = real camera, "synthetic" = simulated camera for development without hardware
    source: Literal["device", "synthetic"] = "device"
    # device path (e.g. /dev/v4l/by-path/...) or OpenCV index as a string
    device: str = ""
    width: int = 1280
    height: int = 720
    fps: int = 30
    fourcc: str = Field(default="MJPG", min_length=4, max_length=4)
    # mounting position around the board in degrees (0 = top, clockwise)
    position_deg: float = 0.0
    # Linux only: camera controls set via v4l2-ctl, e.g.
    # {auto_exposure = 1, exposure_time_absolute = 150}. Names: `v4l2-ctl -d <device> -l`
    v4l2_controls: dict[str, int] = {}

    @model_validator(mode="after")
    def device_required(self) -> "CameraConfig":
        if self.source == "device" and not self.device:
            raise ValueError(f"Camera {self.id}: 'device' is missing")
        return self


class StreamConfig(BaseModel):
    """Preview streams for the browser (JPEG encoding costs CPU)."""

    max_fps: int = Field(default=10, ge=1, le=30)
    default_width: int = Field(default=640, ge=160, le=1920)
    jpeg_quality: int = Field(default=75, ge=30, le=95)


class DetectionConfig(BaseModel):
    """Automatic dart detection (classic image processing on the calibrated cameras)."""

    enabled: bool = True
    # analysis rate; the cameras keep running at full frame rate
    rate_hz: float = Field(default=15.0, ge=2, le=30)
    # frames are downscaled to this width for motion detection
    analysis_width: int = Field(default=640, ge=160, le=1920)
    # gray level difference that counts as a changed pixel
    pixel_threshold: int = Field(default=28, ge=5, le=120)
    # share of changed pixels (of the board region) that counts as motion
    motion_area: float = Field(default=0.0006, gt=0, lt=1)
    # quiet time after motion before a change is evaluated (s)
    settle_time: float = Field(default=0.3, ge=0.05, le=3)
    # smallest change that is a dart (share of the board region)
    min_dart_area: float = Field(default=0.00025, gt=0, lt=1)
    # larger changes are a hand, a person or darts being pulled
    max_dart_area: float = Field(default=0.03, gt=0, lt=1)
    # waiting for a big change to go away (hand, light switched on/off) ends after this many
    # quiet seconds: the current view becomes the new empty board
    blocked_timeout: float = Field(default=8.0, ge=1)
    # camera estimates farther apart than this (mm) are treated as outliers
    max_spread_mm: float = Field(default=12.0, gt=0)
    # save images of every detection (training data for the model, debugging)
    record: bool = True
    # trained dart tip model (ONNX); default: <data_dir>/models/darts.onnx if it exists
    model_path: Path | None = None
    # follow a bumped camera automatically: re-align its calibration (checked once a minute
    # while nothing moves at the board) when it moved by more than realign_threshold_px
    auto_realign: bool = True
    realign_threshold_px: float = Field(default=2.0, gt=0)


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
    # built frontend (npm run build); served by the backend if present
    frontend_dir: Path = Path("frontend/dist")
    server: ServerConfig = ServerConfig()
    logging: LoggingConfig = LoggingConfig()
    stream: StreamConfig = StreamConfig()
    detection: DetectionConfig = DetectionConfig()
    cameras: list[CameraConfig] = []

    @field_validator("cameras")
    @classmethod
    def unique_camera_ids(cls, cameras: list[CameraConfig]) -> list[CameraConfig]:
        ids = [c.id for c in cameras]
        if len(ids) != len(set(ids)):
            raise ValueError(f"Camera IDs must be unique: {ids}")
        return cameras

    @property
    def calibration_dir(self) -> Path:
        return self.data_dir / "calibration"

    @property
    def avatars_dir(self) -> Path:
        return self.data_dir / "avatars"

    @property
    def recordings_dir(self) -> Path:
        return self.data_dir / "recordings"

    @property
    def model_file(self) -> Path:
        return self.detection.model_path or self.data_dir / "models" / "darts.onnx"

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # TOML values arrive as init arguments; the environment should override them.
        return env_settings, init_settings


def resolve_config_file(explicit: Path | None = None) -> Path | None:
    """Find the config file: CLI argument > DARTSCORE_CONFIG > ./config.toml."""
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
