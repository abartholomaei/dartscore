"""Database backups: a consistent copy via SQLite's online backup API, rotated daily."""

import sqlite3
import threading
from datetime import datetime
from pathlib import Path

import structlog

log = structlog.get_logger(__name__)

KEEP = 14
BACKUP_PREFIX = "dartscore-"


def create_backup(database: Path, backup_dir: Path, keep: int = KEEP) -> Path:
    """Copies the database while it may be in use and deletes the oldest backups."""
    backup_dir.mkdir(parents=True, exist_ok=True)
    target = backup_dir / f"{BACKUP_PREFIX}{datetime.now().strftime('%Y%m%d-%H%M%S-%f')[:-3]}.db"
    with sqlite3.connect(database) as source, sqlite3.connect(target) as dest:
        source.backup(dest)
    for old in list_backups(backup_dir)[keep:]:
        old.unlink(missing_ok=True)
    log.info("database_backup_created", path=str(target))
    return target


def list_backups(backup_dir: Path) -> list[Path]:
    """Newest first."""
    return sorted(backup_dir.glob(f"{BACKUP_PREFIX}*.db"), reverse=True)


def restore_backup(backup: Path, database: Path) -> None:
    """Replaces the database with a backup. Only while dartscore is stopped."""
    with sqlite3.connect(backup) as source, sqlite3.connect(database) as dest:
        source.backup(dest)
    log.info("database_restored", backup=str(backup))


class DailyBackup:
    """Creates a backup at startup (if the last one is older than a day) and then daily."""

    def __init__(self, database: Path, backup_dir: Path, interval_s: float = 24 * 3600) -> None:
        self._database = database
        self._backup_dir = backup_dir
        self._interval = interval_s
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="backup", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _due(self) -> bool:
        backups = list_backups(self._backup_dir)
        if not backups:
            return True
        age = datetime.now().timestamp() - backups[0].stat().st_mtime
        return age >= self._interval

    def _run(self) -> None:
        while not self._stop.is_set():
            if self._database.exists() and self._due():
                try:
                    create_backup(self._database, self._backup_dir)
                except (OSError, sqlite3.Error) as exc:
                    log.error("database_backup_failed", error=str(exc))
            self._stop.wait(3600)
