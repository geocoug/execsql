"""
Tests for execsql.db.tiers — database support tiers and the best-effort notice.

Two things are verified here: that every shipped adapter declares the tier the
documentation claims for it (so the README table and the code cannot drift
apart), and that the notice fires exactly when it should.
"""

from __future__ import annotations

import pytest

import execsql.state as _state
from execsql.db.access import AccessDatabase
from execsql.db.base import Database, DatabasePool
from execsql.db.dsn import DsnDatabase
from execsql.db.duckdb import DuckDBDatabase
from execsql.db.firebird import FirebirdDatabase
from execsql.db.mysql import MySQLDatabase
from execsql.db.oracle import OracleDatabase
from execsql.db.postgres import PostgresDatabase
from execsql.db.sqlite import SQLiteDatabase
from execsql.db.sqlserver import SqlServerDatabase
from execsql.db.tiers import SupportTier, announce_tier

# The support tiers documented in README.md and
# docs/getting-started/requirements.md.  Update both when this changes.
TIER_1 = [PostgresDatabase, MySQLDatabase, SqlServerDatabase, SQLiteDatabase, DuckDBDatabase]
TIER_2 = [AccessDatabase, FirebirdDatabase, OracleDatabase, DsnDatabase]


class _Recorder:
    """Stands in for WriteHooks, capturing only what reaches stderr."""

    def __init__(self) -> None:
        self.err: list[str] = []

    def write(self, msg: str) -> None:  # stdout — must never receive a notice
        raise AssertionError(f"tier notice must not go to stdout: {msg!r}")

    def write_err(self, msg: str) -> None:
        self.err.append(msg)


@pytest.fixture
def recorder(minimal_conf):
    """Capture stderr output with the notice enabled."""
    rec = _Recorder()
    _state.output = rec
    _state.conf.support_tier_notice = True
    return rec


# ---------------------------------------------------------------------------
# Declared tiers — guards the docs against drift
# ---------------------------------------------------------------------------


class TestDeclaredTiers:
    @pytest.mark.parametrize("adapter", TIER_1, ids=lambda a: a.__name__)
    def test_tier_1_adapters_are_supported(self, adapter):
        assert adapter.support_tier is SupportTier.SUPPORTED

    @pytest.mark.parametrize("adapter", TIER_2, ids=lambda a: a.__name__)
    def test_tier_2_adapters_are_best_effort(self, adapter):
        assert adapter.support_tier is SupportTier.BEST_EFFORT

    @pytest.mark.parametrize("adapter", TIER_2, ids=lambda a: a.__name__)
    def test_tier_2_adapters_name_themselves(self, adapter):
        """Tier 2 adapters set a human-readable name for the notice."""
        assert adapter.support_tier_name

    def test_every_adapter_is_accounted_for(self):
        """No adapter may exist outside the two documented tiers."""
        shipped = _concrete_adapters()
        assert shipped == set(TIER_1) | set(TIER_2)

    def test_base_class_defaults_to_supported(self):
        """A new adapter is Tier 1 unless it says otherwise — opt in to best-effort."""
        assert Database.support_tier is SupportTier.SUPPORTED


def _concrete_adapters() -> set[type[Database]]:
    """Every Database subclass defined in execsql.db.<backend>."""
    import importlib

    found = set()
    for name in ("access", "dsn", "duckdb", "firebird", "mysql", "oracle", "postgres", "sqlite", "sqlserver"):
        mod = importlib.import_module(f"execsql.db.{name}")
        for value in vars(mod).values():
            if isinstance(value, type) and issubclass(value, Database) and value.__module__ == mod.__name__:
                found.add(value)
    return found


# ---------------------------------------------------------------------------
# announce_tier
# ---------------------------------------------------------------------------


class TestAnnounceTier:
    def test_best_effort_writes_a_notice(self, recorder):
        announce_tier(SupportTier.BEST_EFFORT, "Firebird")
        assert len(recorder.err) == 1
        assert "Firebird" in recorder.err[0]
        assert "best-effort" in recorder.err[0]

    def test_notice_names_the_setting_that_silences_it(self, recorder):
        announce_tier(SupportTier.BEST_EFFORT, "Oracle")
        assert "support_tier_notice=No" in recorder.err[0]

    def test_supported_tier_is_silent(self, recorder):
        announce_tier(SupportTier.SUPPORTED, "PostgreSQL")
        assert recorder.err == []

    def test_repeated_announcement_is_silent(self, recorder):
        for _ in range(5):
            announce_tier(SupportTier.BEST_EFFORT, "Firebird")
        assert len(recorder.err) == 1

    def test_each_dbms_announces_separately(self, recorder):
        announce_tier(SupportTier.BEST_EFFORT, "Firebird")
        announce_tier(SupportTier.BEST_EFFORT, "Oracle")
        assert len(recorder.err) == 2

    def test_disabled_by_config(self, recorder):
        _state.conf.support_tier_notice = False
        announce_tier(SupportTier.BEST_EFFORT, "Firebird")
        assert recorder.err == []

    def test_silent_when_no_output_hooks(self, minimal_conf):
        """Library callers that have not started a run have no output; must not raise."""
        _state.output = None
        _state.conf.support_tier_notice = True
        announce_tier(SupportTier.BEST_EFFORT, "Firebird")  # must not raise

    def test_state_reset_clears_announcements(self, recorder):
        announce_tier(SupportTier.BEST_EFFORT, "Firebird")
        _state.reset()
        _state.output = recorder
        _state.conf = type("C", (), {"support_tier_notice": True})()
        announce_tier(SupportTier.BEST_EFFORT, "Firebird")
        assert len(recorder.err) == 2, "a fresh session should announce again"

    def test_logged_when_a_log_is_open(self, recorder):
        from unittest.mock import MagicMock

        from execsql.utils.fileio import Logger

        log = MagicMock(spec=Logger)
        _state.exec_log = log
        announce_tier(SupportTier.BEST_EFFORT, "Firebird")
        log.log_status_info.assert_called_once()


# ---------------------------------------------------------------------------
# The notice fires where connections actually enter the session
# ---------------------------------------------------------------------------


class _FakeBestEffort(SQLiteDatabase):
    """A Tier 1 adapter re-labelled Tier 2, so the path can be driven without a driver."""

    support_tier = SupportTier.BEST_EFFORT
    support_tier_name = "Pretend DB"


class TestDatabasePoolAnnounces:
    def test_adding_a_tier_2_connection_announces(self, recorder):
        DatabasePool().add("x", _FakeBestEffort(":memory:"))
        assert len(recorder.err) == 1
        assert "Pretend DB" in recorder.err[0]

    def test_adding_a_tier_1_connection_is_silent(self, recorder):
        DatabasePool().add("x", SQLiteDatabase(":memory:"))
        assert recorder.err == []

    def test_second_connection_to_same_dbms_is_silent(self, recorder):
        pool = DatabasePool()
        pool.add("a", _FakeBestEffort(":memory:"))
        pool.add("b", _FakeBestEffort(":memory:"))
        assert len(recorder.err) == 1

    def test_constructing_an_adapter_alone_does_not_announce(self, recorder):
        """The notice belongs to joining the session, not to object construction."""
        _FakeBestEffort(":memory:")
        assert recorder.err == []
