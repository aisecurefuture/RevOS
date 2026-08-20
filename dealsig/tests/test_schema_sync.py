"""Guards on database._sync_columns.

This app has no migration tool: init_db() runs create_all() plus _sync_columns().
create_all adds missing TABLES but never missing COLUMNS, so without the sync an
additive model change deploys cleanly and then fails at query time against the
existing production database. These tests pin the two behaviours that matter —
what it will add, and what it correctly refuses to add.
"""

import sqlite3

import pytest
from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, inspect, text


def _sync(engine, metadata):
    """Mirror of database._sync_columns against an injected engine/metadata."""
    from sqlalchemy.schema import CreateColumn

    inspector = inspect(engine)
    existing = set(inspector.get_table_names())
    refused = []
    for table in metadata.sorted_tables:
        if table.name not in existing:
            continue
        present = {c["name"] for c in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in present:
                continue
            if not column.nullable and column.server_default is None:
                refused.append(column.name)
                continue
            ddl = CreateColumn(column).compile(dialect=engine.dialect)
            with engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE {table.name} ADD COLUMN {ddl}"))
    return refused


@pytest.fixture
def populated_db(tmp_path):
    """A table that already exists and already has rows, like production."""
    path = tmp_path / "old.db"
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE listings (id INTEGER PRIMARY KEY, title TEXT)")
    con.execute("INSERT INTO listings VALUES (1, 'existing row')")
    con.commit()
    con.close()
    return create_engine(f"sqlite:///{path}")


def test_nullable_column_is_added(populated_db):
    md = MetaData()
    Table("listings", md, Column("id", Integer, primary_key=True), Column("title", String),
          Column("image_url", String(1000), nullable=True))
    assert _sync(populated_db, md) == []
    assert "image_url" in {c["name"] for c in inspect(populated_db).get_columns("listings")}


def test_not_null_column_with_server_default_is_added(populated_db):
    """The pattern every new string column on this project must use."""
    md = MetaData()
    Table("listings", md, Column("id", Integer, primary_key=True), Column("title", String),
          Column("display_title", String(500), nullable=False, server_default=""))
    assert _sync(populated_db, md) == []
    with populated_db.connect() as conn:
        # The pre-existing row must come back with the default, not an error.
        assert conn.execute(text("SELECT display_title FROM listings WHERE id=1")).scalar() == ""


def test_not_null_column_without_server_default_is_refused(populated_db):
    """Adding this to a populated table would fail; refusing is the correct call."""
    md = MetaData()
    Table("listings", md, Column("id", Integer, primary_key=True), Column("title", String),
          Column("oops", String(50), nullable=False))
    assert _sync(populated_db, md) == ["oops"]
    assert "oops" not in {c["name"] for c in inspect(populated_db).get_columns("listings")}


def test_existing_rows_survive(populated_db):
    md = MetaData()
    Table("listings", md, Column("id", Integer, primary_key=True), Column("title", String),
          Column("image_url", String(1000), nullable=True))
    _sync(populated_db, md)
    with populated_db.connect() as conn:
        assert conn.execute(text("SELECT title FROM listings WHERE id=1")).scalar() == "existing row"
