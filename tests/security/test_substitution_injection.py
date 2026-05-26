"""Substitution-variable injection regression tests for B07a.

Closes audit finding F052 (zero substitution-injection regression tests)
and covers F001 (``!"!var!"!`` did not escape ``"``), F002 (``!'!var!'!``
did not escape ``\\`` on POSIX, breaking on MySQL default mode /
PostgreSQL E-strings), and the per-adapter quote-helper additions on
:class:`execsql.db.base.Database` (F021 for MySQL backticks + SQL Server
brackets).
"""

from __future__ import annotations

import pytest

from execsql.script.variables import SubVarSet


# ---------------------------------------------------------------------------
# Variables — substitution quoter escape semantics (F001, F002)
# ---------------------------------------------------------------------------


@pytest.fixture
def sv() -> SubVarSet:
    return SubVarSet()


class TestDoubleQuotedSubstitution:
    """!\"!var!\"! must double embedded \" so a value like
    ``foo"; DROP TABLE x; --`` produces a valid quoted identifier."""

    def test_simple_identifier_unchanged(self, sv):
        sv.add_substitution("table_name", "users")
        out, sub = sv.substitute('select * from !"!table_name!"!;')
        assert out == 'select * from "users";'

    def test_embedded_double_quote_doubled(self, sv):
        sv.add_substitution("attack", 'foo"; DROP TABLE x; --')
        out, _ = sv.substitute('select * from !"!attack!"!;')
        # The whole value lives inside a single quoted identifier.
        assert out == 'select * from "foo""; DROP TABLE x; --";'

    def test_only_double_quote(self, sv):
        sv.add_substitution("q", '"')
        out, _ = sv.substitute('select * from !"!q!"!;')
        assert out == 'select * from """";'


class TestSingleQuotedSubstitution:
    """!'!var!'! must double embedded ' and always escape \\ so MySQL
    default-mode and PostgreSQL E-string literals stay intact."""

    def test_simple_literal_unchanged(self, sv):
        sv.add_substitution("name", "Alice")
        out, _ = sv.substitute("select * from t where name = !'!name!'!;")
        assert out == "select * from t where name = 'Alice';"

    def test_embedded_apostrophe_doubled(self, sv):
        sv.add_substitution("name", "O'Brien")
        out, _ = sv.substitute("select * from t where name = !'!name!'!;")
        assert out == "select * from t where name = 'O''Brien';"

    def test_backslash_escaped_on_posix(self, sv):
        """F002 regression: ``\\'`` payload must not terminate the literal on
        MySQL default mode or PostgreSQL E-strings. Backslashes are now
        always doubled, not just on Windows hosts."""
        sv.add_substitution("attack", "x\\'; DROP TABLE t;--")
        out, _ = sv.substitute("insert into t values(!'!attack!'!);")
        # Backslash doubled, then ' doubled — yields a closed literal.
        assert out == "insert into t values('x\\\\''; DROP TABLE t;--');"

    def test_only_backslash(self, sv):
        sv.add_substitution("b", "\\")
        out, _ = sv.substitute("select !'!b!'!;")
        assert out == "select '\\\\';"


class TestNullByteRejection:
    """All three quoter forms reject embedded NUL bytes — most DBMS
    wire protocols truncate or reject them silently."""

    def test_double_quoted_rejects_nul(self, sv):
        sv.add_substitution("x", "table\x00name")
        with pytest.raises(ValueError, match="NUL byte"):
            sv.substitute('select * from !"!x!"!;')

    def test_single_quoted_rejects_nul(self, sv):
        sv.add_substitution("x", "val\x00ue")
        with pytest.raises(ValueError, match="NUL byte"):
            sv.substitute("select !'!x!'!;")

    def test_bare_token_rejects_nul(self, sv):
        sv.add_substitution("x", "any\x00thing")
        with pytest.raises(ValueError, match="NUL byte"):
            sv.substitute("select !!x!!;")


# ---------------------------------------------------------------------------
# Adapter quote helpers — F021
# ---------------------------------------------------------------------------


class TestDatabaseQuoteLiteral:
    """The new Database.quote_literal default escapes \\ and doubles '."""

    def test_default_quote_literal_escapes_backslash_and_apostrophe(self):
        from execsql.db.base import Database

        # Database is abstract — but quote_literal is a concrete method
        # we can test directly on the class binding.
        assert Database.quote_literal(None, "O'Brien") == "'O''Brien'"
        assert Database.quote_literal(None, "x\\y") == "'x\\\\y'"
        assert Database.quote_literal(None, None) == "NULL"

    def test_default_quote_literal_rejects_nul(self):
        from execsql.db.base import Database

        with pytest.raises(ValueError, match="NUL byte"):
            Database.quote_literal(None, "ab\x00c")


class TestQuoteIdentifierOverrides:
    """MySQL uses backticks, SQL Server uses brackets, base uses ANSI \"…\"."""

    def test_base_quote_identifier_ansi(self):
        from execsql.db.base import Database

        assert Database.quote_identifier(None, 'my"col') == '"my""col"'

    def test_mysql_quote_identifier_backticks(self):
        # Use unbound method on the class to avoid pymysql dependency at import.
        import execsql.db.mysql as mysql_mod

        assert mysql_mod.MySQLDatabase.quote_identifier(None, "my`col") == "`my``col`"

    def test_sqlserver_quote_identifier_brackets(self):
        import execsql.db.sqlserver as ss_mod

        assert ss_mod.SqlServerDatabase.quote_identifier(None, "my]col") == "[my]]col]"

    def test_quote_qualified_skips_empty_parts(self, tmp_path):
        # Instantiate a real SQLite adapter so quote_qualified_identifier
        # can dispatch through the instance binding.
        from execsql.db.sqlite import SQLiteDatabase

        db = SQLiteDatabase(str(tmp_path / "t.db"))
        try:
            assert db.quote_qualified_identifier(None, "t") == '"t"'
            assert db.quote_qualified_identifier("s", "t") == '"s"."t"'
            assert db.quote_qualified_identifier("", "t") == '"t"'
        finally:
            db.close()


# ---------------------------------------------------------------------------
# Exporter SQL injection — F025 (SQLite), F026 (DuckDB)
# ---------------------------------------------------------------------------


class TestExporterTableNameInjection:
    """A tablename containing SQL injection metacharacters must not
    break out of the identifier position."""

    def test_sqlite_exporter_tablename_quoted(self, tmp_path):
        from execsql.exporters.sqlite import export_sqlite

        outfile = tmp_path / "out.db"
        # Build a malicious tablename — leading quote would close the
        # identifier if interpolated unsafely, then run an extra
        # statement that drops an existing table.
        evil = 'x"; DROP TABLE u; --'
        # First create a baseline table that the attacker would target.
        import sqlite3

        sdb = sqlite3.connect(outfile)
        sdb.execute("CREATE TABLE u (id INTEGER);")
        sdb.commit()
        sdb.close()
        # Export with malicious tablename; quoting should protect ``u``.
        export_sqlite(str(outfile), hdrs=["c"], rows=[(1,)], append=False, tablename=evil)
        # The baseline ``u`` table must still exist.
        sdb = sqlite3.connect(outfile)
        rows = sdb.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
        sdb.close()
        names = [r[0] for r in rows]
        assert "u" in names, f"Baseline table u was dropped by injected tablename: {names}"
