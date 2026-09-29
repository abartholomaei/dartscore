"""Database connection and migrations."""

from pathlib import Path

import structlog
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

log = structlog.get_logger(__name__)

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def database_url(data_dir: Path) -> str:
    return f"sqlite:///{(data_dir / 'dartscore.db').resolve()}"


def create_db_engine(url: str) -> Engine:
    engine = create_engine(url, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_connection, _record) -> None:  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        # write-ahead log: readers don't block the writer, safer on power loss
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()

    return engine


def alembic_config(url: str) -> Config:
    config = Config()
    # alembic's configparser treats % as interpolation; str(engine.url) percent-encodes
    # characters such as the ":" and "\\" of Windows paths
    config.set_main_option("script_location", str(MIGRATIONS_DIR).replace("%", "%%"))
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return config


def migrate(engine: Engine) -> None:
    """Brings the database schema up to date (creates it on first start)."""
    config = alembic_config(str(engine.url))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
    log.info("database_ready", url=str(engine.url))


def session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(engine, expire_on_commit=False)
