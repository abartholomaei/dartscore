"""Where an installed dartscore keeps its files.

A source checkout works relative to the current directory (``./config.toml``, ``./data``,
``./frontend/dist``). The release builds (PyInstaller bundles) instead run from a per-user
home folder that holds ``config.toml`` and ``data/``, and serve the frontend bundled with
them. ``DARTSCORE_HOME`` selects the home folder explicitly, also for a source checkout.
"""

import os
import sys
from pathlib import Path

HOME_ENV_VAR = "DARTSCORE_HOME"


def is_frozen() -> bool:
    """True when running from a release build instead of a Python environment."""
    return bool(getattr(sys, "frozen", False))


def bundle_dir() -> Path:
    """Folder with the files shipped inside a release build (frontend, config template)."""
    return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))


def default_home() -> Path:
    """Per-user folder for config.toml and data/ of an installed dartscore."""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "dartscore"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "dartscore"
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "dartscore"


def app_home() -> Path | None:
    """The home folder to run in, or None to stay in the current directory."""
    if explicit := os.environ.get(HOME_ENV_VAR):
        return Path(explicit).expanduser()
    return default_home() if is_frozen() else None


def default_frontend_dir() -> Path:
    if is_frozen():
        return bundle_dir() / "frontend"
    return Path("frontend/dist")
