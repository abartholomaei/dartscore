"""Alembic environment: uses the connection passed in by dartscore.storage.db.migrate,
or the URL from the config when run from the command line."""

from alembic import context
from sqlalchemy import create_engine

from dartscore.storage.models import Base

config = context.config
target_metadata = Base.metadata


def run() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        _run_with(connection)
        return
    engine = create_engine(config.get_main_option("sqlalchemy.url") or "")
    with engine.begin() as conn:
        _run_with(conn)


def _run_with(connection) -> None:  # type: ignore[no-untyped-def]
    # render_as_batch: SQLite cannot ALTER most things, batch mode recreates tables instead
    context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


run()
