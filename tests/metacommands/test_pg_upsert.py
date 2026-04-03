"""Unit tests for the PG_UPSERT metacommand handler.

All tests mock ``pg_upsert`` since PostgreSQL is not available in CI.
Tests verify argument parsing, subvar population, error handling,
autocommit toggling, and dispatch regex matching.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from execsql.exceptions import ErrInfo
from execsql.metacommands.upsert import (
    _ExecLogHandler,
    _FileWriterHandler,
    _build_result_from_qa_errors,
    _parse_tables_and_options,
    _qa_failure_msg,
    x_pg_upsert,
    x_pg_upsert_check,
    x_pg_upsert_qa,
)


# ---------------------------------------------------------------------------
# Fake pg_upsert models (avoid importing the real package)
# ---------------------------------------------------------------------------


@dataclass
class FakeQAError:
    table: str = ""
    check_type: str = ""
    details: str = ""

    def to_dict(self) -> dict[str, str]:
        return {"table": self.table, "check_type": self.check_type, "details": self.details}


@dataclass
class FakeTableResult:
    table_name: str = ""
    rows_updated: int = 0
    rows_inserted: int = 0
    qa_errors: list[Any] = field(default_factory=list)

    @property
    def qa_passed(self) -> bool:
        return len(self.qa_errors) == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "table_name": self.table_name,
            "rows_updated": self.rows_updated,
            "rows_inserted": self.rows_inserted,
            "qa_passed": self.qa_passed,
            "qa_errors": [e.to_dict() for e in self.qa_errors],
        }


@dataclass
class FakeUpsertResult:
    tables: list[Any] = field(default_factory=list)
    committed: bool = False
    staging_schema: str = ""
    base_schema: str = ""
    upsert_method: str = "upsert"
    started_at: str = "2026-04-03T10:00:00"
    finished_at: str = "2026-04-03T10:00:05"
    duration_seconds: float = 5.0

    @property
    def qa_passed(self) -> bool:
        return all(t.qa_passed for t in self.tables)

    @property
    def total_updated(self) -> int:
        return sum(t.rows_updated for t in self.tables)

    @property
    def total_inserted(self) -> int:
        return sum(t.rows_inserted for t in self.tables)

    def to_json(self, indent: int = 2) -> str:
        import json

        return json.dumps(self.to_dict(), indent=indent)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tables": [t.to_dict() for t in self.tables],
            "committed": self.committed,
            "staging_schema": self.staging_schema,
            "base_schema": self.base_schema,
            "upsert_method": self.upsert_method,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_seconds": self.duration_seconds,
            "qa_passed": self.qa_passed,
            "total_updated": self.total_updated,
            "total_inserted": self.total_inserted,
        }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class _FakeUserCancelledError(Exception):
    """Stand-in for pg_upsert.UserCancelledError when the package isn't installed."""


@pytest.fixture(autouse=True)
def mock_pg_upsert_module():
    """Inject a fake pg_upsert module into sys.modules for all tests.

    This avoids ModuleNotFoundError when the handler does
    ``from pg_upsert import ...`` at runtime.
    """
    import sys

    fake_mod = MagicMock()
    fake_mod.UserCancelledError = _FakeUserCancelledError
    fake_mod.PgUpsert = MagicMock()

    fake_models = MagicMock()
    fake_models.UpsertResult = FakeUpsertResult
    fake_models.TableResult = FakeTableResult
    fake_models.QAError = FakeQAError

    saved = {
        "pg_upsert": sys.modules.get("pg_upsert"),
        "pg_upsert.models": sys.modules.get("pg_upsert.models"),
    }
    sys.modules["pg_upsert"] = fake_mod
    sys.modules["pg_upsert.models"] = fake_models
    yield fake_mod
    # Restore
    for key, val in saved.items():
        if val is None:
            sys.modules.pop(key, None)
        else:
            sys.modules[key] = val


@pytest.fixture()
def mock_state():
    """Patch _state with a mock that looks like a PostgreSQL connection."""
    from execsql.types import dbt_postgres

    with patch("execsql.metacommands.upsert._state") as state:
        # Database mock — use the real dbt_postgres sentinel so != works
        db = MagicMock()
        db.type = dbt_postgres
        db.autocommit = True
        db.conn = MagicMock()
        state.dbs.current.return_value = db

        # Substitution vars
        state.subvars = MagicMock()

        # Config
        state.conf = MagicMock()
        state.conf.gui_framework = "textual"

        # Exec log
        state.exec_log = MagicMock()

        yield state, db


# ---------------------------------------------------------------------------
# _parse_tables_and_options tests
# ---------------------------------------------------------------------------


class TestParseTablesAndOptions:
    def test_simple_table_list(self):
        result = _parse_tables_and_options("books, authors")
        assert result["tables"] == ["books", "authors"]
        assert result["method"] == "upsert"
        assert result["commit"] is False
        assert result["interactive"] is False
        assert result["compact"] is False
        assert result["exclude_cols"] == []
        assert result["exclude_null_check_cols"] == []
        assert result["logfile"] is None

    def test_single_table(self):
        result = _parse_tables_and_options("books")
        assert result["tables"] == ["books"]

    def test_method_keyword(self):
        result = _parse_tables_and_options("books METHOD update")
        assert result["tables"] == ["books"]
        assert result["method"] == "update"

    def test_method_insert(self):
        result = _parse_tables_and_options("books METHOD insert")
        assert result["method"] == "insert"

    def test_commit_keyword(self):
        result = _parse_tables_and_options("books COMMIT")
        assert result["tables"] == ["books"]
        assert result["commit"] is True

    def test_interactive_keyword(self):
        result = _parse_tables_and_options("books INTERACTIVE")
        assert result["interactive"] is True

    def test_compact_keyword(self):
        result = _parse_tables_and_options("books COMPACT")
        assert result["compact"] is True

    def test_exclude_cols(self):
        result = _parse_tables_and_options("books EXCLUDE rev_time, created_at COMMIT")
        assert result["tables"] == ["books"]
        assert result["exclude_cols"] == ["rev_time", "created_at"]
        assert result["commit"] is True

    def test_exclude_null(self):
        result = _parse_tables_and_options("books EXCLUDE_NULL rev_time")
        assert result["exclude_null_check_cols"] == ["rev_time"]

    def test_all_keywords_combined(self):
        result = _parse_tables_and_options(
            'books, authors METHOD update EXCLUDE rev_time EXCLUDE_NULL created_at INTERACTIVE COMPACT LOGFILE "upsert.log" CLEANUP COMMIT',
        )
        assert result["tables"] == ["books", "authors"]
        assert result["method"] == "update"
        assert result["exclude_cols"] == ["rev_time"]
        assert result["exclude_null_check_cols"] == ["created_at"]
        assert result["interactive"] is True
        assert result["compact"] is True
        assert result["commit"] is True
        assert result["logfile"] == "upsert.log"
        assert result["cleanup"] is True

    def test_keyword_order_independent(self):
        r1 = _parse_tables_and_options("books COMPACT INTERACTIVE COMMIT")
        r2 = _parse_tables_and_options("books COMMIT INTERACTIVE COMPACT")
        assert r1["compact"] == r2["compact"] is True
        assert r1["interactive"] == r2["interactive"] is True
        assert r1["commit"] == r2["commit"] is True

    def test_logfile_unquoted(self):
        result = _parse_tables_and_options("books LOGFILE upsert.log COMMIT")
        assert result["logfile"] == "upsert.log"
        assert result["commit"] is True

    def test_logfile_double_quoted(self):
        result = _parse_tables_and_options('books LOGFILE "path/to/upsert log.txt"')
        assert result["logfile"] == "path/to/upsert log.txt"

    def test_logfile_single_quoted(self):
        result = _parse_tables_and_options("books LOGFILE 'my log.txt' COMMIT")
        assert result["logfile"] == "my log.txt"
        assert result["commit"] is True

    def test_no_logfile(self):
        result = _parse_tables_and_options("books COMMIT")
        assert result["logfile"] is None


# ---------------------------------------------------------------------------
# Dispatch regex tests
# ---------------------------------------------------------------------------


_RX_FULL = re.compile(
    r"^\s*PG_UPSERT\s+FROM\s+(?P<staging_schema>\S+)\s+TO\s+(?P<base_schema>\S+)\s+TABLES\s+(?P<tail>.+)$",
)
_RX_QA = re.compile(
    r"^\s*PG_UPSERT\s+QA\s+FROM\s+(?P<staging_schema>\S+)\s+TO\s+(?P<base_schema>\S+)\s+TABLES\s+(?P<tail>.+)$",
)
_RX_CHECK = re.compile(
    r"^\s*PG_UPSERT\s+CHECK\s+FROM\s+(?P<staging_schema>\S+)\s+TO\s+(?P<base_schema>\S+)\s+TABLES\s+(?P<tail>.+)$",
)


class TestDispatchRegex:
    def test_full_mode_basic(self):
        m = _RX_FULL.match("PG_UPSERT FROM staging TO public TABLES books, authors")
        assert m is not None
        assert m.group("staging_schema") == "staging"
        assert m.group("base_schema") == "public"
        assert m.group("tail") == "books, authors"

    def test_full_mode_with_options(self):
        m = _RX_FULL.match("PG_UPSERT FROM stg TO pub TABLES t1 METHOD update COMMIT")
        assert m is not None
        assert m.group("tail") == "t1 METHOD update COMMIT"

    def test_qa_mode(self):
        m = _RX_QA.match("PG_UPSERT QA FROM staging TO public TABLES books")
        assert m is not None
        assert m.group("staging_schema") == "staging"

    def test_check_mode(self):
        m = _RX_CHECK.match("PG_UPSERT CHECK FROM staging TO public TABLES books, authors")
        assert m is not None
        assert m.group("tail") == "books, authors"

    def test_full_does_not_match_qa(self):
        # The full pattern would match with staging_schema="QA" which is wrong,
        # so in dispatch.py the QA pattern is registered BEFORE the full pattern.
        # Here we just verify the QA pattern matches correctly.
        assert _RX_QA.match("PG_UPSERT QA FROM staging TO public TABLES books") is not None

    def test_leading_whitespace(self):
        m = _RX_FULL.match("  PG_UPSERT FROM staging TO public TABLES books")
        assert m is not None


# ---------------------------------------------------------------------------
# Import guard tests
# ---------------------------------------------------------------------------


class TestImportGuard:
    def test_missing_pg_upsert(self, mock_state):
        with patch.dict("sys.modules", {"pg_upsert": None}):
            with pytest.raises(ErrInfo) as exc_info:
                x_pg_upsert(
                    staging_schema="staging",
                    base_schema="public",
                    tail="books",
                    metacommandline="PG_UPSERT FROM staging TO public TABLES books",
                )
            assert "pip install execsql2[upsert]" in str(exc_info.value)


# ---------------------------------------------------------------------------
# DBMS guard tests
# ---------------------------------------------------------------------------


class TestDBMSGuard:
    def test_non_postgres_connection(self, mock_state):
        from execsql.types import dbt_sqlite

        state, db = mock_state
        db.type = dbt_sqlite

        with patch("execsql.metacommands.upsert._require_pg_upsert"):
            with pytest.raises(ErrInfo) as exc_info:
                x_pg_upsert(
                    staging_schema="staging",
                    base_schema="public",
                    tail="books",
                    metacommandline="PG_UPSERT FROM staging TO public TABLES books",
                )
            assert "PostgreSQL" in str(exc_info.value)
            assert "SQLite" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Full mode handler tests
# ---------------------------------------------------------------------------


class TestFullMode:
    def test_run_sets_subvars(self, mock_state):
        state, db = mock_state
        fake_result = FakeUpsertResult(
            tables=[
                FakeTableResult(table_name="books", rows_updated=10, rows_inserted=5),
                FakeTableResult(table_name="authors", rows_updated=3, rows_inserted=2),
            ],
            committed=True,
            staging_schema="staging",
            base_schema="public",
            upsert_method="upsert",
        )

        mock_pgupsert = MagicMock()
        mock_pgupsert.return_value.run.return_value = fake_result

        with (
            patch("execsql.metacommands.upsert._require_pg_upsert"),
            patch("execsql.metacommands.upsert._create_pgupsert") as mock_create,
        ):
            mock_create.return_value.run.return_value = fake_result
            x_pg_upsert(
                staging_schema="staging",
                base_schema="public",
                tail="books, authors COMMIT",
                metacommandline="PG_UPSERT FROM staging TO public TABLES books, authors COMMIT",
            )

        # Verify subvars were set
        calls = {c[0][0]: c[0][1] for c in state.subvars.add_substitution.call_args_list}
        assert calls["$PG_UPSERT_QA_PASSED"] == "TRUE"
        assert calls["$PG_UPSERT_ROWS_UPDATED"] == "13"
        assert calls["$PG_UPSERT_ROWS_INSERTED"] == "7"
        assert calls["$PG_UPSERT_COMMITTED"] == "TRUE"
        assert calls["$PG_UPSERT_STAGING_SCHEMA"] == "staging"
        assert calls["$PG_UPSERT_BASE_SCHEMA"] == "public"
        assert calls["$PG_UPSERT_TABLES"] == "books, authors"
        assert calls["$PG_UPSERT_METHOD"] == "upsert"
        assert "$PG_UPSERT_DURATION" in calls
        assert "$PG_UPSERT_STARTED_AT" in calls
        assert "$PG_UPSERT_FINISHED_AT" in calls
        assert "$PG_UPSERT_RESULT_JSON" in calls

    def test_qa_failure_raises_errinfo(self, mock_state):
        state, db = mock_state
        fake_result = FakeUpsertResult(
            tables=[
                FakeTableResult(
                    table_name="books",
                    qa_errors=[FakeQAError(table="books", check_type="null", details="col1 (5)")],
                ),
            ],
            staging_schema="staging",
            base_schema="public",
        )

        with (
            patch("execsql.metacommands.upsert._require_pg_upsert"),
            patch("execsql.metacommands.upsert._create_pgupsert") as mock_create,
        ):
            mock_create.return_value.run.return_value = fake_result
            with pytest.raises(ErrInfo) as exc_info:
                x_pg_upsert(
                    staging_schema="staging",
                    base_schema="public",
                    tail="books",
                    metacommandline="PG_UPSERT FROM staging TO public TABLES books",
                )
        err_msg = str(exc_info.value)
        assert "QA failed for: books" in err_msg
        # Subvars should still be set before the error
        assert state.subvars.add_substitution.called

    def test_commit_keyword_passed(self, mock_state):
        state, db = mock_state
        fake_result = FakeUpsertResult(
            tables=[FakeTableResult(table_name="books")],
            staging_schema="staging",
            base_schema="public",
        )

        with (
            patch("execsql.metacommands.upsert._require_pg_upsert"),
            patch("execsql.metacommands.upsert._create_pgupsert") as mock_create,
        ):
            mock_create.return_value.run.return_value = fake_result
            x_pg_upsert(
                staging_schema="staging",
                base_schema="public",
                tail="books COMMIT",
                metacommandline="PG_UPSERT FROM staging TO public TABLES books COMMIT",
            )
            # Verify _create_pgupsert was called with commit=True in opts
            call_opts = mock_create.call_args[0][3]  # 4th positional arg = opts
            assert call_opts["commit"] is True

    def test_no_commit_keyword(self, mock_state):
        state, db = mock_state
        fake_result = FakeUpsertResult(
            tables=[FakeTableResult(table_name="books")],
            staging_schema="staging",
            base_schema="public",
        )

        with (
            patch("execsql.metacommands.upsert._require_pg_upsert"),
            patch("execsql.metacommands.upsert._create_pgupsert") as mock_create,
        ):
            mock_create.return_value.run.return_value = fake_result
            x_pg_upsert(
                staging_schema="staging",
                base_schema="public",
                tail="books",
                metacommandline="PG_UPSERT FROM staging TO public TABLES books",
            )
            call_opts = mock_create.call_args[0][3]
            assert call_opts["commit"] is False


# ---------------------------------------------------------------------------
# QA mode handler tests
# ---------------------------------------------------------------------------


class TestQAMode:
    def test_qa_only_calls_qa_all(self, mock_state):
        state, db = mock_state

        with (
            patch("execsql.metacommands.upsert._require_pg_upsert"),
            patch("execsql.metacommands.upsert._create_pgupsert") as mock_create,
            patch("execsql.metacommands.upsert._build_result_from_qa_errors") as mock_build,
        ):
            mock_ups = mock_create.return_value
            mock_ups.qa_all.return_value = mock_ups
            mock_build.return_value = FakeUpsertResult(
                tables=[FakeTableResult(table_name="books")],
                staging_schema="staging",
                base_schema="public",
            )
            x_pg_upsert_qa(
                staging_schema="staging",
                base_schema="public",
                tail="books",
                metacommandline="PG_UPSERT QA FROM staging TO public TABLES books",
            )
            mock_ups.qa_all.assert_called_once()

    def test_qa_mode_never_commits(self, mock_state):
        state, db = mock_state

        with (
            patch("execsql.metacommands.upsert._require_pg_upsert"),
            patch("execsql.metacommands.upsert._create_pgupsert") as mock_create,
            patch("execsql.metacommands.upsert._build_result_from_qa_errors") as mock_build,
        ):
            mock_ups = mock_create.return_value
            mock_ups.qa_all.return_value = mock_ups
            mock_build.return_value = FakeUpsertResult(
                tables=[FakeTableResult(table_name="books")],
                staging_schema="staging",
                base_schema="public",
            )
            # Even with COMMIT in the tail, QA mode forces commit=False
            x_pg_upsert_qa(
                staging_schema="staging",
                base_schema="public",
                tail="books COMMIT",
                metacommandline="PG_UPSERT QA FROM staging TO public TABLES books COMMIT",
            )
            call_opts = mock_create.call_args[0][3]
            assert call_opts["commit"] is False


# ---------------------------------------------------------------------------
# CHECK mode handler tests
# ---------------------------------------------------------------------------


class TestCheckMode:
    def test_check_calls_column_existence_and_type_mismatch(self, mock_state):
        state, db = mock_state

        with (
            patch("execsql.metacommands.upsert._require_pg_upsert"),
            patch("execsql.metacommands.upsert._create_pgupsert") as mock_create,
            patch("execsql.metacommands.upsert._build_result_from_qa_errors") as mock_build,
        ):
            mock_ups = mock_create.return_value
            mock_ups.qa_column_existence.return_value = mock_ups
            mock_ups.qa_type_mismatch.return_value = mock_ups
            mock_build.return_value = FakeUpsertResult(
                tables=[FakeTableResult(table_name="books")],
                staging_schema="staging",
                base_schema="public",
            )
            x_pg_upsert_check(
                staging_schema="staging",
                base_schema="public",
                tail="books",
                metacommandline="PG_UPSERT CHECK FROM staging TO public TABLES books",
            )
            mock_ups.qa_column_existence.assert_called_once()
            mock_ups.qa_type_mismatch.assert_called_once()


# ---------------------------------------------------------------------------
# Autocommit toggle tests
# ---------------------------------------------------------------------------


class TestAutocommitToggle:
    def test_autocommit_disabled_then_restored(self, mock_state):
        state, db = mock_state
        db.autocommit = True
        call_order = []
        db.autocommit_off.side_effect = lambda: call_order.append("off")
        db.autocommit_on.side_effect = lambda: call_order.append("on")

        fake_result = FakeUpsertResult(
            tables=[FakeTableResult(table_name="books")],
            staging_schema="staging",
            base_schema="public",
        )

        with (
            patch("execsql.metacommands.upsert._require_pg_upsert"),
            patch("execsql.metacommands.upsert._create_pgupsert") as mock_create,
        ):
            mock_create.return_value.run.return_value = fake_result
            x_pg_upsert(
                staging_schema="staging",
                base_schema="public",
                tail="books",
                metacommandline="PG_UPSERT FROM staging TO public TABLES books",
            )
        assert call_order == ["off", "on"]

    def test_autocommit_not_toggled_when_already_off(self, mock_state):
        state, db = mock_state
        db.autocommit = False

        fake_result = FakeUpsertResult(
            tables=[FakeTableResult(table_name="books")],
            staging_schema="staging",
            base_schema="public",
        )

        with (
            patch("execsql.metacommands.upsert._require_pg_upsert"),
            patch("execsql.metacommands.upsert._create_pgupsert") as mock_create,
        ):
            mock_create.return_value.run.return_value = fake_result
            x_pg_upsert(
                staging_schema="staging",
                base_schema="public",
                tail="books",
                metacommandline="PG_UPSERT FROM staging TO public TABLES books",
            )
        db.autocommit_off.assert_not_called()
        db.autocommit_on.assert_not_called()


# ---------------------------------------------------------------------------
# UI mode mirroring tests
# ---------------------------------------------------------------------------


class TestUIModeMirroring:
    def test_mirrors_gui_framework(self, mock_state, mock_pg_upsert_module):
        state, db = mock_state
        state.conf.gui_framework = "textual"

        from execsql.metacommands.upsert import _create_pgupsert

        with patch("execsql.metacommands.upsert._state", state):
            _create_pgupsert(
                db,
                "staging",
                "public",
                {
                    "tables": ["books"],
                    "commit": False,
                    "interactive": False,
                    "compact": False,
                    "method": "upsert",
                    "exclude_cols": [],
                    "exclude_null_check_cols": [],
                },
            )
            call_kwargs = mock_pg_upsert_module.PgUpsert.call_args[1]
            assert call_kwargs["ui_mode"] == "textual"


# ---------------------------------------------------------------------------
# Interactive + COMPACT keyword tests
# ---------------------------------------------------------------------------


class TestInteractiveAndCompact:
    def test_interactive_passed_to_constructor(self, mock_state):
        state, db = mock_state
        fake_result = FakeUpsertResult(
            tables=[FakeTableResult(table_name="books")],
            staging_schema="staging",
            base_schema="public",
        )

        with (
            patch("execsql.metacommands.upsert._require_pg_upsert"),
            patch("execsql.metacommands.upsert._create_pgupsert") as mock_create,
        ):
            mock_create.return_value.run.return_value = fake_result
            x_pg_upsert(
                staging_schema="staging",
                base_schema="public",
                tail="books INTERACTIVE",
                metacommandline="PG_UPSERT FROM staging TO public TABLES books INTERACTIVE",
            )
            call_opts = mock_create.call_args[0][3]
            assert call_opts["interactive"] is True

    def test_compact_passed_to_constructor(self, mock_state):
        state, db = mock_state
        fake_result = FakeUpsertResult(
            tables=[FakeTableResult(table_name="books")],
            staging_schema="staging",
            base_schema="public",
        )

        with (
            patch("execsql.metacommands.upsert._require_pg_upsert"),
            patch("execsql.metacommands.upsert._create_pgupsert") as mock_create,
        ):
            mock_create.return_value.run.return_value = fake_result
            x_pg_upsert(
                staging_schema="staging",
                base_schema="public",
                tail="books COMPACT",
                metacommandline="PG_UPSERT FROM staging TO public TABLES books COMPACT",
            )
            call_opts = mock_create.call_args[0][3]
            assert call_opts["compact"] is True


# ---------------------------------------------------------------------------
# UserCancelledError test
# ---------------------------------------------------------------------------


class TestUserCancelled:
    def test_user_cancelled_raises_errinfo(self, mock_state):
        state, db = mock_state

        with (
            patch("execsql.metacommands.upsert._require_pg_upsert"),
            patch("execsql.metacommands.upsert._create_pgupsert") as mock_create,
        ):
            mock_create.return_value.run.side_effect = _FakeUserCancelledError("cancelled")

            with pytest.raises(ErrInfo) as exc_info:
                x_pg_upsert(
                    staging_schema="staging",
                    base_schema="public",
                    tail="books INTERACTIVE",
                    metacommandline="PG_UPSERT FROM staging TO public TABLES books INTERACTIVE",
                )
            assert "cancelled" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Logging bridge test
# ---------------------------------------------------------------------------


class TestQAFailureMessage:
    def test_lists_failed_tables(self):
        result = FakeUpsertResult(
            tables=[
                FakeTableResult(
                    table_name="books",
                    qa_errors=[FakeQAError(table="books", check_type="null", details="title (3)")],
                ),
                FakeTableResult(table_name="authors"),  # passes
                FakeTableResult(
                    table_name="genres",
                    qa_errors=[FakeQAError(table="genres", check_type="fk", details="parent_id (5)")],
                ),
            ],
        )
        msg = _qa_failure_msg(result)
        assert msg == "PG_UPSERT QA failed for: books, genres"

    def test_single_failed_table(self):
        result = FakeUpsertResult(
            tables=[
                FakeTableResult(
                    table_name="books",
                    qa_errors=[FakeQAError(table="books", check_type="pk", details="id (2)")],
                ),
            ],
        )
        msg = _qa_failure_msg(result)
        assert msg == "PG_UPSERT QA failed for: books"


# ---------------------------------------------------------------------------
# Logging bridge tests
# ---------------------------------------------------------------------------


class TestLoggingBridge:
    def test_exec_log_handler_routes_to_exec_log(self):
        mock_log = MagicMock()
        handler = _ExecLogHandler(mock_log)

        import logging

        record = logging.LogRecord(
            name="pg_upsert.display",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="QA check passed for table books",
            args=(),
            exc_info=None,
        )
        handler.emit(record)
        mock_log.log_user_msg.assert_called_once()
        assert "QA check passed" in mock_log.log_user_msg.call_args[0][0]

    def test_filewriter_handler_routes_to_filewriter(self):
        import logging

        with patch("execsql.utils.fileio.filewriter_write") as mock_fw:
            handler = _FileWriterHandler("test.log")
            record = logging.LogRecord(
                name="pg_upsert.display",
                level=logging.INFO,
                pathname="",
                lineno=0,
                msg="  ✓ public.books [1/3]",
                args=(),
                exc_info=None,
            )
            handler.emit(record)
            mock_fw.assert_called_once_with("test.log", "  ✓ public.books [1/3]\n")


# ---------------------------------------------------------------------------
# QA failure path tests for QA and CHECK modes
# ---------------------------------------------------------------------------


class TestQAModeFailure:
    def test_qa_failure_raises_errinfo(self, mock_state):
        state, db = mock_state

        failed_result = FakeUpsertResult(
            tables=[
                FakeTableResult(
                    table_name="books",
                    qa_errors=[FakeQAError(table="books", check_type="null", details="col1 (5)")],
                ),
            ],
            staging_schema="staging",
            base_schema="public",
        )

        with (
            patch("execsql.metacommands.upsert._require_pg_upsert"),
            patch("execsql.metacommands.upsert._create_pgupsert") as mock_create,
            patch("execsql.metacommands.upsert._build_result_from_qa_errors") as mock_build,
        ):
            mock_ups = mock_create.return_value
            mock_ups.qa_all.return_value = mock_ups
            mock_build.return_value = failed_result
            with pytest.raises(ErrInfo) as exc_info:
                x_pg_upsert_qa(
                    staging_schema="staging",
                    base_schema="public",
                    tail="books",
                    metacommandline="PG_UPSERT QA FROM staging TO public TABLES books",
                )
            assert "QA failed for: books" in str(exc_info.value)


class TestCheckModeFailure:
    def test_check_failure_raises_errinfo(self, mock_state):
        state, db = mock_state

        failed_result = FakeUpsertResult(
            tables=[
                FakeTableResult(
                    table_name="books",
                    qa_errors=[FakeQAError(table="books", check_type="column", details="missing_col")],
                ),
            ],
            staging_schema="staging",
            base_schema="public",
        )

        with (
            patch("execsql.metacommands.upsert._require_pg_upsert"),
            patch("execsql.metacommands.upsert._create_pgupsert") as mock_create,
            patch("execsql.metacommands.upsert._build_result_from_qa_errors") as mock_build,
        ):
            mock_ups = mock_create.return_value
            mock_ups.qa_column_existence.return_value = mock_ups
            mock_ups.qa_type_mismatch.return_value = mock_ups
            mock_build.return_value = failed_result
            with pytest.raises(ErrInfo) as exc_info:
                x_pg_upsert_check(
                    staging_schema="staging",
                    base_schema="public",
                    tail="books",
                    metacommandline="PG_UPSERT CHECK FROM staging TO public TABLES books",
                )
            assert "QA failed for: books" in str(exc_info.value)


# ---------------------------------------------------------------------------
# _build_result_from_qa_errors direct test
# ---------------------------------------------------------------------------


class TestBuildResultFromQAErrors:
    def test_groups_errors_by_table(self):
        mock_ups = MagicMock()
        mock_ups.tables = ["books", "authors"]
        mock_ups.qa_errors = [
            FakeQAError(table="books", check_type="null", details="title (3)"),
            FakeQAError(table="authors", check_type="pk", details="id (2)"),
            FakeQAError(table="books", check_type="fk", details="pub_id (1)"),
        ]
        mock_ups.staging_schema = "staging"
        mock_ups.base_schema = "public"
        mock_ups.upsert_method = "upsert"

        result = _build_result_from_qa_errors(mock_ups)
        assert result.staging_schema == "staging"
        assert result.base_schema == "public"
        assert result.upsert_method == "upsert"
        assert result.committed is False
        assert len(result.tables) == 2
        books = [t for t in result.tables if t.table_name == "books"][0]
        authors = [t for t in result.tables if t.table_name == "authors"][0]
        assert len(books.qa_errors) == 2
        assert len(authors.qa_errors) == 1
        assert not result.qa_passed

    def test_no_errors_means_passed(self):
        mock_ups = MagicMock()
        mock_ups.tables = ["books"]
        mock_ups.qa_errors = []
        mock_ups.staging_schema = "staging"
        mock_ups.base_schema = "public"
        mock_ups.upsert_method = "upsert"

        result = _build_result_from_qa_errors(mock_ups)
        assert result.qa_passed


# ---------------------------------------------------------------------------
# LOGFILE wiring test
# ---------------------------------------------------------------------------


class TestLogfileWiring:
    def test_logfile_passed_to_attach_log_handlers(self, mock_state):
        state, db = mock_state
        fake_result = FakeUpsertResult(
            tables=[FakeTableResult(table_name="books")],
            staging_schema="staging",
            base_schema="public",
        )

        with (
            patch("execsql.metacommands.upsert._require_pg_upsert"),
            patch("execsql.metacommands.upsert._create_pgupsert") as mock_create,
            patch("execsql.metacommands.upsert._attach_log_handlers") as mock_attach,
            patch("execsql.metacommands.upsert._detach_log_handlers"),
        ):
            mock_create.return_value.run.return_value = fake_result
            mock_attach.return_value = ([], [], {})
            x_pg_upsert(
                staging_schema="staging",
                base_schema="public",
                tail='books LOGFILE "upsert.log" COMMIT',
                metacommandline='PG_UPSERT FROM staging TO public TABLES books LOGFILE "upsert.log" COMMIT',
            )
            mock_attach.assert_called_once_with("upsert.log")


# ---------------------------------------------------------------------------
# Logger level restoration test
# ---------------------------------------------------------------------------


class TestLoggerLevelRestoration:
    def test_levels_restored_after_normal_run(self, mock_state):
        import logging

        state, db = mock_state
        display_logger = logging.getLogger("pg_upsert.display")
        main_logger = logging.getLogger("pg_upsert")
        orig_display = display_logger.level
        orig_main = main_logger.level

        fake_result = FakeUpsertResult(
            tables=[FakeTableResult(table_name="books")],
            staging_schema="staging",
            base_schema="public",
        )

        with (
            patch("execsql.metacommands.upsert._require_pg_upsert"),
            patch("execsql.metacommands.upsert._create_pgupsert") as mock_create,
            patch("execsql.metacommands.upsert.filewriter_write", create=True),
        ):
            mock_create.return_value.run.return_value = fake_result
            x_pg_upsert(
                staging_schema="staging",
                base_schema="public",
                tail='books LOGFILE "test.log"',
                metacommandline='PG_UPSERT FROM staging TO public TABLES books LOGFILE "test.log"',
            )

        assert display_logger.level == orig_display
        assert main_logger.level == orig_main


# ---------------------------------------------------------------------------
# CLEANUP keyword tests
# ---------------------------------------------------------------------------


class TestCleanup:
    def test_cleanup_keyword_parsed(self):
        result = _parse_tables_and_options("books CLEANUP COMMIT")
        assert result["cleanup"] is True

    def test_no_cleanup_by_default(self):
        result = _parse_tables_and_options("books COMMIT")
        assert result["cleanup"] is False

    def test_cleanup_calls_ups_cleanup(self, mock_state):
        state, db = mock_state
        fake_result = FakeUpsertResult(
            tables=[FakeTableResult(table_name="books")],
            staging_schema="staging",
            base_schema="public",
        )

        with (
            patch("execsql.metacommands.upsert._require_pg_upsert"),
            patch("execsql.metacommands.upsert._create_pgupsert") as mock_create,
        ):
            mock_ups = mock_create.return_value
            mock_ups.run.return_value = fake_result
            x_pg_upsert(
                staging_schema="staging",
                base_schema="public",
                tail="books CLEANUP COMMIT",
                metacommandline="PG_UPSERT FROM staging TO public TABLES books CLEANUP COMMIT",
            )
            mock_ups.cleanup.assert_called_once()

    def test_no_cleanup_without_keyword(self, mock_state):
        state, db = mock_state
        fake_result = FakeUpsertResult(
            tables=[FakeTableResult(table_name="books")],
            staging_schema="staging",
            base_schema="public",
        )

        with (
            patch("execsql.metacommands.upsert._require_pg_upsert"),
            patch("execsql.metacommands.upsert._create_pgupsert") as mock_create,
        ):
            mock_ups = mock_create.return_value
            mock_ups.run.return_value = fake_result
            x_pg_upsert(
                staging_schema="staging",
                base_schema="public",
                tail="books COMMIT",
                metacommandline="PG_UPSERT FROM staging TO public TABLES books COMMIT",
            )
            mock_ups.cleanup.assert_not_called()


# ---------------------------------------------------------------------------
# Callback per-table subvar tests
# ---------------------------------------------------------------------------


class TestCallback:
    def test_callback_sets_qa_table_subvars(self, mock_state):
        from execsql.metacommands.upsert import _make_callback

        state, db = mock_state

        # Create a fake QA_TABLE_COMPLETE event
        mock_event = MagicMock()
        mock_event.event = MagicMock()
        mock_event.event.value = "qa_table_complete"
        mock_event.table = "books"
        mock_event.qa_passed = True

        # We need the real CallbackEvent enum for comparison
        # Patch _state so the callback can access subvars
        with patch("execsql.metacommands.upsert._state", state):
            cb = _make_callback()

            # Simulate CallbackEvent.QA_TABLE_COMPLETE match
            from pg_upsert import CallbackEvent

            mock_event.event = CallbackEvent.QA_TABLE_COMPLETE
            cb(mock_event)

        calls = {c[0][0]: c[0][1] for c in state.subvars.add_substitution.call_args_list}
        assert calls["$PG_UPSERT_CURRENT_TABLE"] == "books"
        assert calls["$PG_UPSERT_TABLE_QA_PASSED"] == "TRUE"

    def test_callback_sets_upsert_table_subvars(self, mock_state):
        from execsql.metacommands.upsert import _make_callback
        from pg_upsert import CallbackEvent

        state, db = mock_state

        mock_event = MagicMock()
        mock_event.event = CallbackEvent.UPSERT_TABLE_COMPLETE
        mock_event.table = "authors"
        mock_event.rows_updated = 15
        mock_event.rows_inserted = 3

        with patch("execsql.metacommands.upsert._state", state):
            cb = _make_callback()
            cb(mock_event)

        calls = {c[0][0]: c[0][1] for c in state.subvars.add_substitution.call_args_list}
        assert calls["$PG_UPSERT_CURRENT_TABLE"] == "authors"
        assert calls["$PG_UPSERT_TABLE_ROWS_UPDATED"] == "15"
        assert calls["$PG_UPSERT_TABLE_ROWS_INSERTED"] == "3"
