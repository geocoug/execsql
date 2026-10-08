"""``execsql run -t p -n -e LATIN1`` creates the PostgreSQL database with that encoding."""

from __future__ import annotations

from unittest.mock import patch

import pytest

pytest.importorskip("psycopg")


def test_db_postgres_passes_the_encoding_to_the_adapter():
    from execsql.db.factory import db_Postgres
    from execsql.db.postgres import PostgresDatabase

    with patch.object(PostgresDatabase, "open_db"):
        db = db_Postgres("localhost", "newdb", user="u", pw_needed=False, encoding="LATIN1", new_db=True)
    assert db.encoding == "LATIN1"


def test_without_an_encoding_a_new_database_is_utf8():
    from execsql.db.factory import db_Postgres
    from execsql.db.postgres import PostgresDatabase

    with patch.object(PostgresDatabase, "open_db"):
        db = db_Postgres("localhost", "newdb", user="u", pw_needed=False, new_db=True)
    assert db.encoding == "UTF8"
