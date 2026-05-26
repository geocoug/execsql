"""Substitution-variable injection + semantics regression tests for B07a.

This file is intentionally exhaustive. The substitution-variable engine
is the core trust boundary of execsql — every metacommand path feeds
user input through it, and a quiet behavior change in escape semantics
would break thousands of user scripts. The audit (F001, F002, F052)
called out two escape bugs; B07a fixed them and added a NUL byte
rejection. These tests pin down:

1. **What the fixes guarantee** (escape semantics, NUL rejection).
2. **What B07a does NOT change** (bare ``!!var!!``, case-insensitivity,
   nested-token fallback, recursive expansion, single-pass independence,
   variable name resolution).
3. **The per-adapter quote helpers** added on Database.
4. **The exporter SQL injection fixes** in SQLite and DuckDB.

Three code paths feed substitution:

* ``SubVarSet.substitute()`` — the primary path; regex-finds one token
  per call.
* ``SubVarSet._substitute_nested()`` — fallback for nested tokens like
  ``!!N_!!INNER!!_REST!!`` where the outer regex can't find a complete
  ``!!varname!!`` match.
* ``SubVarSet.substitute_all()`` — outer loop that calls ``substitute()``
  until no more substitutions happen (with a 100-iteration cycle cap).

Tests exercise all three.
"""

from __future__ import annotations

import pytest

from execsql.script.variables import SubVarSet


@pytest.fixture
def sv() -> SubVarSet:
    """Fresh empty SubVarSet for each test."""
    return SubVarSet()


# ===========================================================================
# Section 1 — Bare ``!!var!!`` form (NO escaping)
#
# The bare form is the workhorse. B07a must NOT have introduced any
# new escaping to it; only the explicit quoter forms got new behavior.
# ===========================================================================


class TestBareSubstitution:
    def test_simple_value(self, sv):
        sv.add_substitution("name", "world")
        out, ok = sv.substitute("hello !!name!!")
        assert (out, ok) == ("hello world", True)

    def test_empty_value(self, sv):
        sv.add_substitution("empty", "")
        out, ok = sv.substitute("[!!empty!!]")
        assert (out, ok) == ("[]", True)

    @pytest.mark.parametrize(
        "value",
        [
            "value with spaces",
            "multi\nline\nvalue",
            "value with !@#$%^&*() chars",
            "value with 'apostrophes'",
            'value with "double quotes"',
            "value with \\ backslashes \\",
            "value with ;DROP TABLE; SQL-like text",
            "Unicode: café résumé 日本語 🎉",
            "Numeric-looking: 123.456",
            "  leading and trailing whitespace  ",
        ],
    )
    def test_bare_preserves_value_verbatim(self, sv, value):
        """B07a regression: the bare form must NOT escape anything.

        The whole point of the bare form is that the SQL author controls
        the surrounding context. Adding escaping would break every
        existing script that uses ``!!table!!`` or ``!!keyword!!``.
        """
        sv.add_substitution("v", value)
        out, ok = sv.substitute(f"X{value}X | X!!v!!X")
        # The substituted value matches the original value exactly.
        assert out == f"X{value}X | X{value}X"
        assert ok is True

    def test_none_value_becomes_empty(self, sv):
        """None-valued variables expand to the empty string (legacy behavior)."""
        sv.add_substitution("v", None)
        out, ok = sv.substitute("[!!v!!]")
        assert (out, ok) == ("[]", True)

    def test_non_string_value_str_cast(self, sv):
        """Non-string values are str()-cast (legacy behavior)."""
        sv.add_substitution("v", 42)
        out, ok = sv.substitute("answer is !!v!!")
        assert (out, ok) == ("answer is 42", True)

    def test_undefined_variable_not_substituted(self, sv):
        out, ok = sv.substitute("hello !!undefined!!")
        assert (out, ok) == ("hello !!undefined!!", False)


# ===========================================================================
# Section 2 — Single-quoted ``!'!var!'!`` form
#
# Produces a SQL string literal:
#   * wraps in single quotes
#   * doubles embedded apostrophes
#   * escapes backslashes (B07a: was Windows-only; now always)
#
# F002: the previous Windows-only ``\\`` escape was unsafe on POSIX
# clients talking to MySQL default mode or PostgreSQL E-strings.
# ===========================================================================


class TestSingleQuotedSubstitution:
    def test_plain_value(self, sv):
        sv.add_substitution("name", "Alice")
        out, _ = sv.substitute("SELECT * FROM t WHERE name = !'!name!'!;")
        assert out == "SELECT * FROM t WHERE name = 'Alice';"

    def test_empty_value(self, sv):
        sv.add_substitution("e", "")
        out, _ = sv.substitute("SELECT !'!e!'!;")
        assert out == "SELECT '';"

    def test_apostrophe_doubled(self, sv):
        sv.add_substitution("name", "O'Brien")
        out, _ = sv.substitute("WHERE n = !'!name!'!;")
        assert out == "WHERE n = 'O''Brien';"

    def test_two_apostrophes(self, sv):
        sv.add_substitution("v", "a''b")
        out, _ = sv.substitute("v=!'!v!'!")
        assert out == "v='a''''b'"

    def test_backslash_doubled(self, sv):
        """B07a/F002: backslash must always be escaped (was Windows-only)."""
        sv.add_substitution("v", "a\\b")
        out, _ = sv.substitute("v=!'!v!'!")
        assert out == "v='a\\\\b'"

    def test_backslash_apostrophe_combination(self, sv):
        """F002 attack payload: ``\\'`` must not terminate the literal."""
        sv.add_substitution("attack", "x\\'; DROP TABLE t;--")
        out, _ = sv.substitute("INSERT INTO t VALUES(!'!attack!'!);")
        assert out == "INSERT INTO t VALUES('x\\\\''; DROP TABLE t;--');"

    def test_only_backslash(self, sv):
        sv.add_substitution("b", "\\")
        out, _ = sv.substitute("!'!b!'!")
        assert out == "'\\\\'"

    def test_only_apostrophe(self, sv):
        sv.add_substitution("q", "'")
        out, _ = sv.substitute("!'!q!'!")
        assert out == "''''"

    def test_unicode_value(self, sv):
        sv.add_substitution("v", "café résumé 日本語")
        out, _ = sv.substitute("name=!'!v!'!")
        assert out == "name='café résumé 日本語'"

    def test_escape_order_backslash_before_apostrophe(self, sv):
        """The escape order matters: doubling backslashes after
        doubling apostrophes would double the escaping. Verify the
        order is backslash → apostrophe."""
        sv.add_substitution("v", "\\'")
        out, _ = sv.substitute("!'!v!'!")
        # Expected: backslash → \\\\, then apostrophe → '' → "'\\\\''"
        assert out == "'\\\\'''"

    def test_does_not_consume_unrelated_apostrophes(self, sv):
        """Pre-existing apostrophes in the SURROUNDING SQL stay intact."""
        sv.add_substitution("v", "x")
        out, _ = sv.substitute("WHERE col = 'foo' AND v = !'!v!'!;")
        assert out == "WHERE col = 'foo' AND v = 'x';"


# ===========================================================================
# Section 3 — Double-quoted ``!"!var!"!`` form
#
# Produces a SQL quoted identifier:
#   * wraps in double quotes
#   * doubles embedded ``"`` (B07a: was missing; the F001 hole)
#
# F001 attack: ``foo"; DROP TABLE x; --`` used to produce a closing
# quote followed by a second statement.
# ===========================================================================


class TestDoubleQuotedSubstitution:
    def test_plain_identifier(self, sv):
        sv.add_substitution("table", "users")
        out, _ = sv.substitute('SELECT * FROM !"!table!"!;')
        assert out == 'SELECT * FROM "users";'

    def test_empty_value(self, sv):
        sv.add_substitution("e", "")
        out, _ = sv.substitute('!"!e!"!')
        assert out == '""'

    def test_embedded_double_quote_doubled(self, sv):
        """F001 regression: an attack value with ``"`` must not escape
        the identifier position."""
        sv.add_substitution("attack", 'foo"; DROP TABLE x; --')
        out, _ = sv.substitute('SELECT * FROM !"!attack!"!;')
        assert out == 'SELECT * FROM "foo""; DROP TABLE x; --";'

    def test_only_double_quote(self, sv):
        sv.add_substitution("q", '"')
        out, _ = sv.substitute('!"!q!"!')
        assert out == '""""'

    def test_double_quote_does_NOT_escape_backslash(self, sv):
        """The identifier form does not need backslash escaping —
        ANSI identifier quoting treats backslash as an ordinary char.
        Only the literal form (!'!…!'!) escapes ``\\``."""
        sv.add_substitution("v", "a\\b")
        out, _ = sv.substitute('!"!v!"!')
        assert out == '"a\\b"'

    def test_unicode_identifier(self, sv):
        sv.add_substitution("v", "café_table")
        out, _ = sv.substitute('!"!v!"!')
        assert out == '"café_table"'

    def test_does_not_consume_unrelated_double_quotes(self, sv):
        sv.add_substitution("t", "x")
        out, _ = sv.substitute('SELECT "literal" FROM !"!t!"!;')
        assert out == 'SELECT "literal" FROM "x";'


# ===========================================================================
# Section 4 — NUL byte rejection (B07a addition)
#
# Most DBMS wire protocols silently truncate at or reject NUL bytes,
# so refusing to interpolate them is defensive. CRITICALLY: the check
# must only fire for the variable actually being substituted, not for
# every iterated variable in the dict (the bug fixed in this session).
# ===========================================================================


class TestNullByteRejection:
    @pytest.mark.parametrize(
        "wrapper,token",
        [
            ("bare", "!!x!!"),
            ("single", "!'!x!'!"),
            ("double", '!"!x!"!'),
        ],
    )
    def test_nul_in_substituted_value_raises(self, sv, wrapper, token):
        sv.add_substitution("x", "ab\x00c")
        with pytest.raises(ValueError, match="NUL byte"):
            sv.substitute(f"SELECT {token};")

    def test_error_message_names_variable(self, sv):
        sv.add_substitution("password_var", "secret\x00leak")
        with pytest.raises(ValueError, match="password_var"):
            sv.substitute("!!password_var!!")

    def test_unrelated_nul_value_does_NOT_block_other_substitution(self, sv):
        """REGRESSION: ``_substitute_nested`` used to NUL-check every
        iterated variable, not just the one being substituted. A
        SubVarSet with one NUL-tainted variable would refuse to
        substitute ANY other variable until the bad one was removed.
        """
        sv.add_substitution("tainted", "has\x00nul")
        sv.add_substitution("clean", "value")
        # Force the _substitute_nested fallback by using a nested-token
        # form that the regex can't match in one pass.
        out, ok = sv.substitute("[!'!clean!'!]")
        assert (out, ok) == ("['value']", True)

    def test_nul_in_unreferenced_variable_via_nested_path(self, sv):
        """Same property via the explicit nested-fallback path."""
        sv.add_substitution("a_nul", "x\x00y")
        sv.add_substitution("normal", "ok")
        out, ok = sv._substitute_nested("here is !!normal!!")
        assert (out, ok) == ("here is ok", True)

    def test_nul_via_nested_fallback_path(self, sv):
        """When the NUL var IS the one being substituted via the
        nested fallback, it must still raise."""
        sv.add_substitution("bad", "x\x00y")
        with pytest.raises(ValueError, match="NUL byte"):
            sv._substitute_nested("[!!bad!!]")


# ===========================================================================
# Section 5 — Case insensitivity (legacy execsql semantic — must NOT break)
# ===========================================================================


class TestCaseInsensitivity:
    def test_token_case_matches_lowercased_name(self, sv):
        sv.add_substitution("myvar", "val")
        for token in ["!!myvar!!", "!!MYVAR!!", "!!MyVar!!", "!!myVAR!!"]:
            out, ok = sv.substitute(f"x{token}y")
            assert (out, ok) == ("xvaly", True)

    def test_quoted_forms_also_case_insensitive(self, sv):
        sv.add_substitution("name", "Alice")
        for token in ["!'!name!'!", "!'!NAME!'!", "!'!Name!'!"]:
            out, _ = sv.substitute(token)
            assert out == "'Alice'"


# ===========================================================================
# Section 6 — Nested-token fallback path
#
# Inputs like ``!!N_!!CHECK_GROUP!!_CHECKS!!`` need the per-variable
# substring scan in ``_substitute_nested`` because ``_TOKEN_RX``
# cannot find a clean outer match. This is a critical legacy path
# we MUST NOT break.
# ===========================================================================


class TestNestedFallback:
    def test_nested_token_inner_resolves_first(self, sv):
        sv.add_substitution("check_group", "ABC")
        # The outer !!N_..._CHECKS!! is malformed because of the inner
        # tokens, so _substitute_nested scans for any defined-var
        # substring. ``check_group`` matches first.
        out, ok = sv.substitute("!!N_!!CHECK_GROUP!!_CHECKS!!")
        assert (out, ok) == ("!!N_ABC_CHECKS!!", True)

    def test_nested_resolves_progressively_under_substitute_all(self, sv):
        sv.add_substitution("check_group", "ABC")
        sv.add_substitution("n_abc_checks", 42)
        # substitute_all loops; first iteration resolves inner, second
        # iteration completes the outer.
        out, ok = sv.substitute_all("!!N_!!CHECK_GROUP!!_CHECKS!!")
        assert (out, ok) == ("42", True)

    def test_substitute_nested_handles_all_three_forms(self, sv):
        sv.add_substitution("v", "X")
        # Force _substitute_nested directly (private, but stable API).
        for token, expected in [
            ("!!v!!", "X"),
            ("!'!v!'!", "'X'"),
            ('!"!v!"!', '"X"'),
        ]:
            out, ok = sv._substitute_nested(token)
            assert (out, ok) == (expected, True)


# ===========================================================================
# Section 7 — substitute_all (recursive expansion)
#
# Cycle detection + multi-pass resolution. Don't break the 100-iter cap.
# ===========================================================================


class TestSubstituteAll:
    def test_chained_substitution(self, sv):
        sv.add_substitution("a", "!!b!!")
        sv.add_substitution("b", "!!c!!")
        sv.add_substitution("c", "done")
        out, ok = sv.substitute_all("[!!a!!]")
        assert (out, ok) == ("[done]", True)

    def test_no_substitution_returns_input_unchanged(self, sv):
        out, ok = sv.substitute_all("just text")
        assert (out, ok) == ("just text", False)

    def test_cycle_detected(self, sv):
        sv.add_substitution("a", "!!b!!")
        sv.add_substitution("b", "!!a!!")
        with pytest.raises(RuntimeError, match="cycle"):
            sv.substitute_all("[!!a!!]")

    def test_quoter_form_preserved_through_recursion(self, sv):
        sv.add_substitution("inner", "O'Brien")
        sv.add_substitution("wrap", "!'!inner!'!")
        out, _ = sv.substitute_all("!!wrap!!")
        # Recursive expansion: !!wrap!! → !'!inner!'! → 'O''Brien'
        assert out == "'O''Brien'"


# ===========================================================================
# Section 8 — Multiple substitutions in one string
# ===========================================================================


class TestMultipleSubstitutions:
    def test_two_bare_vars(self, sv):
        sv.add_substitution("a", "X")
        sv.add_substitution("b", "Y")
        out, _ = sv.substitute_all("!!a!!-!!b!!")
        assert out == "X-Y"

    def test_same_var_referenced_twice(self, sv):
        sv.add_substitution("a", "X")
        out, _ = sv.substitute_all("!!a!!-!!a!!")
        assert out == "X-X"

    def test_mixed_quoter_forms_in_one_statement(self, sv):
        """A realistic SQL statement with all three substitution forms."""
        sv.add_substitution("table", "orders")
        sv.add_substitution("col", "name")
        sv.add_substitution("val", "O'Brien")
        out, _ = sv.substitute_all(
            'SELECT !"!col!"! FROM !"!table!"! WHERE !!col!! = !\'!val!\'!;',
        )
        assert out == "SELECT \"name\" FROM \"orders\" WHERE name = 'O''Brien';"


# ===========================================================================
# Section 9 — High-level substitute_vars integration
#
# This is what most callers actually use (script/engine.py). It wraps
# substitute_all and enforces a 100-iter max via _MAX_SUBSTITUTION_DEPTH.
# ===========================================================================


class TestSubstituteVarsIntegration:
    """substitute_vars is the high-level wrapper most callers use.

    It merges *localvars* with ``_state.subvars`` (the global pool),
    so we have to seed both for the tests to run standalone.
    """

    @pytest.fixture(autouse=True)
    def seed_state(self):
        import execsql.state as _state
        from execsql.script.variables import CounterVars

        saved_subvars = _state.subvars
        saved_counters = _state.counters
        _state.subvars = SubVarSet()
        _state.counters = CounterVars()
        yield
        _state.subvars = saved_subvars
        _state.counters = saved_counters

    def test_integration_basic(self):
        from execsql.script.engine import substitute_vars

        sv = SubVarSet()
        sv.add_substitution("user", "alice")
        sv.add_substitution("greeting", "hello !!user!!")
        out = substitute_vars("X !!greeting!! X", localvars=sv)
        assert out == "X hello alice X"

    def test_integration_with_quoter_forms(self):
        from execsql.script.engine import substitute_vars

        sv = SubVarSet()
        sv.add_substitution("name", "Bob's Co.")
        out = substitute_vars("SELECT * WHERE n = !'!name!'!", localvars=sv)
        assert out == "SELECT * WHERE n = 'Bob''s Co.'"

    def test_integration_recursion_cap_enforced(self):
        """substitute_vars enforces _MAX_SUBSTITUTION_DEPTH (100)
        to prevent runaway expansion."""
        from execsql.script.engine import substitute_vars

        sv = SubVarSet()
        sv.add_substitution("a", "!!b!!")
        sv.add_substitution("b", "!!a!!")
        with pytest.raises(RuntimeError, match="cycle"):
            substitute_vars("[!!a!!]", localvars=sv)


# ===========================================================================
# Section 10 — Database.quote_literal coverage
# ===========================================================================


class TestDatabaseQuoteLiteralExtra:
    """Cover every type path quote_literal might see."""

    def _q(self, value):
        from execsql.db.base import Database

        return Database.quote_literal(None, value)

    def test_none_returns_NULL_keyword(self):
        assert self._q(None) == "NULL"

    def test_plain_string(self):
        assert self._q("hello") == "'hello'"

    def test_apostrophe_doubled(self):
        assert self._q("O'Brien") == "'O''Brien'"

    def test_backslash_escaped(self):
        assert self._q("a\\b") == "'a\\\\b'"

    def test_both_apostrophe_and_backslash(self):
        # backslash → \\, apostrophe → ''
        assert self._q("\\'") == "'\\\\'''"

    def test_int_str_cast(self):
        assert self._q(42) == "'42'"

    def test_float_str_cast(self):
        assert self._q(3.14) == "'3.14'"

    def test_bool_str_cast(self):
        # str(True) is "True"
        assert self._q(True) == "'True'"

    def test_unicode(self):
        assert self._q("café") == "'café'"

    def test_empty_string(self):
        assert self._q("") == "''"

    def test_nul_byte_raises(self):
        with pytest.raises(ValueError, match="NUL byte"):
            self._q("ab\x00c")


# ===========================================================================
# Section 11 — Per-adapter quote_identifier
# ===========================================================================


class TestQuoteIdentifierPerAdapter:
    def test_base_ansi_default(self):
        from execsql.db.base import Database

        assert Database.quote_identifier(None, "col") == '"col"'
        assert Database.quote_identifier(None, 'my"col') == '"my""col"'

    def test_sqlite_inherits_ansi(self, tmp_path):
        from execsql.db.sqlite import SQLiteDatabase

        db = SQLiteDatabase(str(tmp_path / "a.db"))
        try:
            assert db.quote_identifier("col") == '"col"'
            assert db.quote_identifier('my"col') == '"my""col"'
        finally:
            db.close()

    def test_mysql_uses_backticks(self):
        from execsql.db.mysql import MySQLDatabase

        assert MySQLDatabase.quote_identifier(None, "col") == "`col`"
        assert MySQLDatabase.quote_identifier(None, "my`col") == "`my``col`"

    def test_sqlserver_uses_brackets(self):
        from execsql.db.sqlserver import SqlServerDatabase

        assert SqlServerDatabase.quote_identifier(None, "col") == "[col]"
        # SQL Server escapes ``]`` by doubling.
        assert SqlServerDatabase.quote_identifier(None, "my]col") == "[my]]col]"

    def test_idempotent_per_dialect(self):
        """Quoting an already-quoted identifier produces a
        doubly-quoted identifier (treating the embedded quote chars
        as literal). This is the SQL standard behaviour."""
        from execsql.db.base import Database
        from execsql.db.mysql import MySQLDatabase
        from execsql.db.sqlserver import SqlServerDatabase

        inner = Database.quote_identifier(None, "x")  # "x"
        outer = Database.quote_identifier(None, inner)  # """x"""
        assert outer == '"""x"""'

        my_inner = MySQLDatabase.quote_identifier(None, "x")  # `x`
        my_outer = MySQLDatabase.quote_identifier(None, my_inner)
        assert my_outer == "```x```"

        ss_inner = SqlServerDatabase.quote_identifier(None, "x")  # [x]
        ss_outer = SqlServerDatabase.quote_identifier(None, ss_inner)
        # The inner `[x]` has no `]` that needs doubling outside the
        # outer brackets; but the inner `]` does get doubled.
        assert ss_outer == "[[x]]]"


# ===========================================================================
# Section 12 — quote_qualified_identifier
# ===========================================================================


class TestQuoteQualifiedIdentifier:
    @pytest.fixture
    def sqlite_db(self, tmp_path):
        from execsql.db.sqlite import SQLiteDatabase

        db = SQLiteDatabase(str(tmp_path / "q.db"))
        yield db
        db.close()

    def test_table_only(self, sqlite_db):
        assert sqlite_db.quote_qualified_identifier(None, "t") == '"t"'

    def test_schema_and_table(self, sqlite_db):
        assert sqlite_db.quote_qualified_identifier("s", "t") == '"s"."t"'

    def test_empty_schema_skipped(self, sqlite_db):
        assert sqlite_db.quote_qualified_identifier("", "t") == '"t"'

    def test_three_part_identifier(self, sqlite_db):
        assert sqlite_db.quote_qualified_identifier("db", "s", "t") == '"db"."s"."t"'

    def test_parts_with_special_chars(self, sqlite_db):
        # Each part is quoted individually, so embedded ``"`` is doubled.
        assert sqlite_db.quote_qualified_identifier('a"b', "t") == '"a""b"."t"'


# ===========================================================================
# Section 13 — Exporter SQLi parity (F025 SQLite + F026 DuckDB)
# ===========================================================================


class TestExporterTableNameInjection:
    def test_sqlite_exporter_tablename_quoted(self, tmp_path):
        """F025: SQLite exporter must identifier-quote the tablename
        so an injected ``"; DROP TABLE x; --`` payload stays a single
        identifier, not a second statement."""
        from execsql.exporters.sqlite import export_sqlite
        import sqlite3

        outfile = tmp_path / "out.db"
        # Seed a baseline table the attacker would target.
        sdb = sqlite3.connect(outfile)
        sdb.execute("CREATE TABLE u (id INTEGER);")
        sdb.commit()
        sdb.close()
        # Inject — quoting should turn this into a single weird table name.
        evil = 'x"; DROP TABLE u; --'
        export_sqlite(str(outfile), hdrs=["c"], rows=[(1,)], append=False, tablename=evil)
        sdb = sqlite3.connect(outfile)
        names = [r[0] for r in sdb.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        sdb.close()
        assert "u" in names, f"Baseline table u was dropped: {names}"

    def test_duckdb_exporter_tablename_quoted(self, tmp_path):
        """F026: DuckDB exporter parity with SQLite — quoted tablename
        must protect a baseline target."""
        duckdb = pytest.importorskip("duckdb")
        from execsql.exporters.duckdb import export_duckdb

        outfile = tmp_path / "out.duckdb"
        ddb = duckdb.connect(str(outfile))
        ddb.execute("CREATE TABLE u (id INTEGER);")
        ddb.close()

        evil = 'x"; DROP TABLE u; --'
        export_duckdb(str(outfile), hdrs=["c"], rows=[(1,)], append=False, tablename=evil)

        ddb = duckdb.connect(str(outfile))
        names = [r[0] for r in ddb.execute("SELECT table_name FROM information_schema.tables").fetchall()]
        ddb.close()
        assert "u" in names, f"Baseline table u was dropped: {names}"
