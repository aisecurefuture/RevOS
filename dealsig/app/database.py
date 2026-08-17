import logging
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

logger = logging.getLogger("dealsig.database")


class Base(DeclarativeBase):
    pass


def _engine_options(url: str) -> dict:
    if url.startswith("sqlite"):
        return {"connect_args": {"check_same_thread": False}}
    return {"pool_pre_ping": True, "pool_size": 5, "max_overflow": 10}


settings = get_settings()
engine = create_engine(settings.database_url, **_engine_options(settings.database_url))
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _sync_columns() -> None:
    """Add declared-but-missing columns to tables that already exist.

    create_all() creates missing TABLES but never missing COLUMNS, and this app
    has no migration tool. Without this, an additive model change deploys
    cleanly and then fails at query time on the production database.

    Deliberately conservative: it only adds columns that can be added safely to
    a populated table. Anything else (NOT NULL with no server default, type
    changes, renames, drops) is logged and left alone for a human.
    """
    from sqlalchemy import inspect, text
    from sqlalchemy.schema import CreateColumn

    inspector = inspect(engine)
    existing = set(inspector.get_table_names())
    for table in Base.metadata.sorted_tables:
        if table.name not in existing:
            continue  # create_all will build it in full
        present = {column["name"] for column in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in present:
                continue
            if not column.nullable and column.server_default is None:
                logger.warning(
                    "Column %s.%s is missing and cannot be added automatically "
                    "(NOT NULL with no server default). Add it by hand.",
                    table.name,
                    column.name,
                )
                continue
            ddl = CreateColumn(column).compile(dialect=engine.dialect)
            try:
                with engine.begin() as connection:
                    connection.execute(text(f"ALTER TABLE {table.name} ADD COLUMN {ddl}"))
                logger.info("Added missing column %s.%s", table.name, column.name)
            except Exception as exc:
                # The web app and the worker both call init_db() at startup, so
                # a concurrent add is expected and harmless.
                if "duplicate column" in str(exc).lower() or "already exists" in str(exc).lower():
                    continue
                logger.warning(
                    "Could not add column %s.%s (%s)", table.name, column.name, type(exc).__name__
                )


def init_db() -> None:
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _sync_columns()

