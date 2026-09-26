"""Kommandozeilen-Einstieg: lädt die Konfiguration und startet den Server."""

import argparse
from pathlib import Path

import structlog
import uvicorn

from dartscore import __version__
from dartscore.api import create_app
from dartscore.config import load_settings
from dartscore.log import configure_logging


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="dartscore", description=__doc__)
    parser.add_argument("-c", "--config", type=Path, help="Pfad zur config.toml")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = parser.parse_args(argv)

    settings = load_settings(args.config)
    configure_logging(settings.logging)
    settings.data_dir.mkdir(parents=True, exist_ok=True)

    log = structlog.get_logger(__name__)
    log.info(
        "starting",
        version=__version__,
        host=settings.server.host,
        port=settings.server.port,
        cameras=len(settings.cameras),
    )
    uvicorn.run(
        create_app(settings),
        host=settings.server.host,
        port=settings.server.port,
        log_config=None,
    )
